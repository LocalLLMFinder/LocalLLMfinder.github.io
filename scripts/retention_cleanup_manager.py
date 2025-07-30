#!/usr/bin/env python3
"""
RetentionCleanupManager for Dynamic Model Retention System

This module implements the RetentionCleanupManager class that handles cleanup
of old models while preserving top models, with safe deletion logic, storage
space calculation, and comprehensive reporting functionality.
"""

import asyncio
import json
import logging
import os
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict

# Import existing systems for integration
from config_system import SyncConfiguration, DynamicRetentionConfig
from error_handling import with_error_handling, ErrorContext

logger = logging.getLogger(__name__)

@dataclass
class ModelRetentionMetadata:
    """Metadata for model retention tracking."""
    model_id: str
    first_seen: datetime
    last_updated: datetime
    source: str  # 'recent' or 'top'
    download_count: int
    retention_reason: str  # 'recent', 'top_20', 'high_downloads'
    cleanup_eligible: bool
    file_size_bytes: int = 0
    file_paths: List[str] = None
    
    def __post_init__(self):
        if self.file_paths is None:
            self.file_paths = []

@dataclass
class CleanupReport:
    """Report of cleanup operations performed."""
    timestamp: datetime
    models_evaluated: int
    models_removed: int
    models_preserved: int
    storage_freed_bytes: int
    storage_freed_mb: float
    cleanup_duration_seconds: float
    top_models_preserved: int
    high_download_preserved: int
    recent_models_preserved: int
    errors_encountered: List[str]
    removed_model_ids: List[str]
    preserved_model_ids: List[str]
    success: bool
    
    def __post_init__(self):
        self.storage_freed_mb = self.storage_freed_bytes / (1024 * 1024)

class RetentionCleanupManager:
    """
    Manages cleanup of old models while preserving top models.
    
    This class implements safe deletion logic with comprehensive preservation
    rules, storage optimization, and detailed reporting capabilities.
    """
    
    def __init__(self, config: SyncConfiguration):
        """
        Initialize the RetentionCleanupManager.
        
        Args:
            config: System configuration containing retention settings
        """
        self.config = config
        self.retention_config = config.dynamic_retention
        self.retention_days = self.retention_config.retention_days
        
        # Storage paths
        self.data_dir = Path(config.storage.data_directory)
        self.backup_dir = Path(config.storage.backup_directory)
        self.retention_dir = self.data_dir / "retention"
        self.metadata_file = self.retention_dir / "retention_metadata.json"
        
        # Ensure directories exist
        self.retention_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"🧹 Initialized RetentionCleanupManager:")
        logger.info(f"   • Retention period: {self.retention_days} days")
        logger.info(f"   • Cleanup enabled: {self.retention_config.enable_cleanup}")
        logger.info(f"   • Batch size: {self.retention_config.cleanup_batch_size}")
        logger.info(f"   • Preserve threshold: {self.retention_config.preserve_download_threshold}")
    
    async def cleanup_old_models(self, top_models: List[str]) -> CleanupReport:
        """
        Remove old models while preserving top models.
        
        Args:
            top_models: List of model IDs that should be preserved (top models)
            
        Returns:
            CleanupReport containing cleanup statistics and results
        """
        logger.info(f"🧹 Starting cleanup of models older than {self.retention_days} days...")
        start_time = datetime.now()
        
        if not self.retention_config.enable_cleanup:
            logger.info("⏸️ Cleanup is disabled in configuration")
            return CleanupReport(
                timestamp=datetime.now(timezone.utc),
                models_evaluated=0,
                models_removed=0,
                models_preserved=0,
                storage_freed_bytes=0,
                storage_freed_mb=0.0,
                cleanup_duration_seconds=0,
                top_models_preserved=0,
                high_download_preserved=0,
                recent_models_preserved=0,
                errors_encountered=[],
                removed_model_ids=[],
                preserved_model_ids=[],
                success=True
            )
        
        try:
            # Load current retention metadata
            metadata = await self._load_retention_metadata()
            
            # Identify models for removal
            models_to_remove, models_to_preserve = self.identify_models_for_removal(
                metadata, top_models
            )
            
            logger.info(f"📊 Cleanup analysis:")
            logger.info(f"   • Models evaluated: {len(metadata)}")
            logger.info(f"   • Models to remove: {len(models_to_remove)}")
            logger.info(f"   • Models to preserve: {len(models_to_preserve)}")
            
            # Perform cleanup in batches
            removed_models, storage_freed, errors = await self._remove_models_in_batches(
                models_to_remove
            )
            
            # Update metadata after cleanup
            await self._update_metadata_after_cleanup(removed_models)
            
            # Calculate preservation statistics
            preservation_stats = self._calculate_preservation_stats(
                models_to_preserve, top_models
            )
            
            # Calculate cleanup duration
            cleanup_duration = (datetime.now() - start_time).total_seconds()
            
            # Create cleanup report
            report = CleanupReport(
                timestamp=datetime.now(timezone.utc),
                models_evaluated=len(metadata),
                models_removed=len(removed_models),
                models_preserved=len(models_to_preserve),
                storage_freed_bytes=storage_freed,
                storage_freed_mb=storage_freed / (1024 * 1024),
                cleanup_duration_seconds=cleanup_duration,
                top_models_preserved=preservation_stats['top_models'],
                high_download_preserved=preservation_stats['high_downloads'],
                recent_models_preserved=preservation_stats['recent'],
                errors_encountered=errors,
                removed_model_ids=[m.model_id for m in removed_models],
                preserved_model_ids=[m.model_id for m in models_to_preserve],
                success=len(errors) == 0
            )
            
            # Log cleanup results
            logger.info(f"✅ Cleanup completed in {cleanup_duration:.1f}s:")
            logger.info(f"   • Models removed: {report.models_removed}")
            logger.info(f"   • Storage freed: {report.storage_freed_mb:.1f} MB")
            logger.info(f"   • Top models preserved: {report.top_models_preserved}")
            logger.info(f"   • High download preserved: {report.high_download_preserved}")
            logger.info(f"   • Recent models preserved: {report.recent_models_preserved}")
            
            if errors:
                logger.warning(f"⚠️ {len(errors)} errors encountered during cleanup")
                for error in errors[:5]:  # Log first 5 errors
                    logger.warning(f"   • {error}")
            
            return report
            
        except Exception as e:
            cleanup_duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Cleanup failed: {e}")
            
            return CleanupReport(
                timestamp=datetime.now(timezone.utc),
                models_evaluated=0,
                models_removed=0,
                models_preserved=0,
                storage_freed_bytes=0,
                storage_freed_mb=0.0,
                cleanup_duration_seconds=cleanup_duration,
                top_models_preserved=0,
                high_download_preserved=0,
                recent_models_preserved=0,
                errors_encountered=[str(e)],
                removed_model_ids=[],
                preserved_model_ids=[],
                success=False
            )
    
    def identify_models_for_removal(self, all_models: List[ModelRetentionMetadata], 
                                  top_models: List[str]) -> Tuple[List[ModelRetentionMetadata], List[ModelRetentionMetadata]]:
        """
        Identify which models should be removed and which should be preserved.
        
        Args:
            all_models: List of all models with retention metadata
            top_models: List of model IDs that are currently in top models
            
        Returns:
            Tuple of (models_to_remove, models_to_preserve)
        """
        logger.info("🔍 Analyzing models for cleanup eligibility...")
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        top_models_set = set(top_models)
        
        models_to_remove = []
        models_to_preserve = []
        
        for model in all_models:
            should_preserve = False
            preservation_reason = []
            
            # Check if model is in current top models
            if model.model_id in top_models_set:
                should_preserve = True
                preservation_reason.append("current_top_model")
            
            # Check if model has high download count (always preserve)
            elif model.download_count >= self.retention_config.preserve_download_threshold:
                should_preserve = True
                preservation_reason.append("high_downloads")
            
            # Check if model is recent (within retention period)
            elif model.last_updated >= cutoff_date:
                should_preserve = True
                preservation_reason.append("recent")
            
            # Check if model was recently seen (first_seen within retention period)
            elif model.first_seen >= cutoff_date:
                should_preserve = True
                preservation_reason.append("recently_discovered")
            
            # Update model metadata with preservation decision
            model.cleanup_eligible = not should_preserve
            if should_preserve:
                model.retention_reason = ", ".join(preservation_reason)
            
            # Add to appropriate list
            if should_preserve:
                models_to_preserve.append(model)
            else:
                models_to_remove.append(model)
        
        logger.info(f"📊 Model analysis completed:")
        logger.info(f"   • Total models: {len(all_models)}")
        logger.info(f"   • To remove: {len(models_to_remove)}")
        logger.info(f"   • To preserve: {len(models_to_preserve)}")
        
        # Log preservation reasons
        preservation_counts = defaultdict(int)
        for model in models_to_preserve:
            for reason in model.retention_reason.split(", "):
                preservation_counts[reason] += 1
        
        logger.info("🛡️ Preservation reasons:")
        for reason, count in preservation_counts.items():
            logger.info(f"   • {reason}: {count} models")
        
        return models_to_remove, models_to_preserve
    
    async def _remove_models_in_batches(self, models_to_remove: List[ModelRetentionMetadata]) -> Tuple[List[ModelRetentionMetadata], int, List[str]]:
        """
        Remove model data in batches with error handling.
        
        Args:
            models_to_remove: List of models to remove
            
        Returns:
            Tuple of (successfully_removed_models, total_storage_freed, errors)
        """
        if not models_to_remove:
            logger.info("📭 No models to remove")
            return [], 0, []
        
        logger.info(f"🗑️ Removing {len(models_to_remove)} models in batches of {self.retention_config.cleanup_batch_size}...")
        
        successfully_removed = []
        total_storage_freed = 0
        errors = []
        
        # Process models in batches
        batch_size = self.retention_config.cleanup_batch_size
        for i in range(0, len(models_to_remove), batch_size):
            batch = models_to_remove[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(models_to_remove) + batch_size - 1) // batch_size
            
            logger.info(f"🔄 Processing batch {batch_num}/{total_batches} ({len(batch)} models)...")
            
            for model in batch:
                try:
                    # Calculate storage before removal
                    storage_freed = await self._calculate_model_storage_size(model)
                    
                    # Remove model data
                    await self._remove_single_model_data(model)
                    
                    # Update tracking
                    successfully_removed.append(model)
                    total_storage_freed += storage_freed
                    
                    logger.debug(f"✅ Removed {model.model_id} ({storage_freed / 1024 / 1024:.1f} MB)")
                    
                except Exception as e:
                    error_msg = f"Failed to remove {model.model_id}: {e}"
                    errors.append(error_msg)
                    logger.error(f"❌ {error_msg}")
            
            # Small delay between batches to avoid overwhelming the system
            if i + batch_size < len(models_to_remove):
                await asyncio.sleep(0.1)
        
        logger.info(f"✅ Batch removal completed:")
        logger.info(f"   • Successfully removed: {len(successfully_removed)} models")
        logger.info(f"   • Storage freed: {total_storage_freed / 1024 / 1024:.1f} MB")
        logger.info(f"   • Errors: {len(errors)}")
        
        return successfully_removed, total_storage_freed, errors
    
    async def _remove_single_model_data(self, model: ModelRetentionMetadata) -> None:
        """
        Remove data for a single model with backup creation.
        
        Args:
            model: Model metadata for the model to remove
        """
        # Create backup before removal if backup is enabled
        if self.config.storage.enable_backups:
            await self._create_model_backup(model)
        
        # Remove model files
        for file_path in model.file_paths:
            try:
                path = Path(file_path)
                if path.exists():
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        shutil.rmtree(path)
                    logger.debug(f"🗑️ Removed: {file_path}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to remove {file_path}: {e}")
                raise
        
        # Remove model from main data files if present
        await self._remove_from_data_files(model.model_id)
    
    async def _create_model_backup(self, model: ModelRetentionMetadata) -> None:
        """
        Create backup of model data before removal.
        
        Args:
            model: Model to backup
        """
        try:
            backup_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            model_backup_dir = self.backup_dir / f"{model.model_id}_{backup_timestamp}"
            model_backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Backup model files
            for file_path in model.file_paths:
                try:
                    source_path = Path(file_path)
                    if source_path.exists():
                        if source_path.is_file():
                            backup_path = model_backup_dir / source_path.name
                            shutil.copy2(source_path, backup_path)
                        elif source_path.is_dir():
                            backup_path = model_backup_dir / source_path.name
                            shutil.copytree(source_path, backup_path)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to backup {file_path}: {e}")
            
            # Save model metadata
            metadata_backup = model_backup_dir / "metadata.json"
            with open(metadata_backup, 'w', encoding='utf-8') as f:
                # Convert datetime objects to ISO strings for JSON serialization
                model_dict = asdict(model)
                model_dict['first_seen'] = model.first_seen.isoformat()
                model_dict['last_updated'] = model.last_updated.isoformat()
                json.dump(model_dict, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"💾 Created backup for {model.model_id} at {model_backup_dir}")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to create backup for {model.model_id}: {e}")
            # Don't raise - backup failure shouldn't stop cleanup
    
    async def _remove_from_data_files(self, model_id: str) -> None:
        """
        Remove model from main data files (gguf_models.json, etc.).
        
        Args:
            model_id: ID of the model to remove from data files
        """
        # Remove from main GGUF models file
        gguf_models_file = self.data_dir / "gguf_models.json"
        if gguf_models_file.exists():
            try:
                with open(gguf_models_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Remove model if present
                original_count = len(data)
                data = [model for model in data if model.get('id') != model_id]
                
                if len(data) < original_count:
                    with open(gguf_models_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    logger.debug(f"🗑️ Removed {model_id} from gguf_models.json")
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to remove {model_id} from gguf_models.json: {e}")
        
        # Remove from estimated sizes file
        sizes_file = self.data_dir / "gguf_models_estimated_sizes.json"
        if sizes_file.exists():
            try:
                with open(sizes_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if model_id in data:
                    del data[model_id]
                    with open(sizes_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    logger.debug(f"🗑️ Removed {model_id} from estimated sizes")
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to remove {model_id} from estimated sizes: {e}")
    
    async def _calculate_model_storage_size(self, model: ModelRetentionMetadata) -> int:
        """
        Calculate the storage size of a model's files.
        
        Args:
            model: Model metadata
            
        Returns:
            int: Total size in bytes
        """
        total_size = 0
        
        for file_path in model.file_paths:
            try:
                path = Path(file_path)
                if path.exists():
                    if path.is_file():
                        total_size += path.stat().st_size
                    elif path.is_dir():
                        for sub_path in path.rglob('*'):
                            if sub_path.is_file():
                                total_size += sub_path.stat().st_size
            except Exception as e:
                logger.debug(f"Warning: Could not calculate size for {file_path}: {e}")
        
        return total_size
    
    def _calculate_preservation_stats(self, preserved_models: List[ModelRetentionMetadata], 
                                    top_models: List[str]) -> Dict[str, int]:
        """
        Calculate statistics about preserved models.
        
        Args:
            preserved_models: List of models that were preserved
            top_models: List of current top model IDs
            
        Returns:
            Dictionary with preservation statistics
        """
        top_models_set = set(top_models)
        
        stats = {
            'top_models': 0,
            'high_downloads': 0,
            'recent': 0,
            'other': 0
        }
        
        for model in preserved_models:
            if model.model_id in top_models_set:
                stats['top_models'] += 1
            elif model.download_count >= self.retention_config.preserve_download_threshold:
                stats['high_downloads'] += 1
            elif 'recent' in model.retention_reason:
                stats['recent'] += 1
            else:
                stats['other'] += 1
        
        return stats
    
    async def _load_retention_metadata(self) -> List[ModelRetentionMetadata]:
        """
        Load retention metadata from storage.
        
        Returns:
            List of ModelRetentionMetadata objects
        """
        try:
            if not self.metadata_file.exists():
                logger.info("📁 No retention metadata found, scanning data directory...")
                return await self._scan_and_create_metadata()
            
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            metadata_list = []
            for item in data.get('models', []):
                metadata = ModelRetentionMetadata(
                    model_id=item['model_id'],
                    first_seen=datetime.fromisoformat(item['first_seen']),
                    last_updated=datetime.fromisoformat(item['last_updated']),
                    source=item['source'],
                    download_count=item['download_count'],
                    retention_reason=item['retention_reason'],
                    cleanup_eligible=item['cleanup_eligible'],
                    file_size_bytes=item.get('file_size_bytes', 0),
                    file_paths=item.get('file_paths', [])
                )
                metadata_list.append(metadata)
            
            logger.info(f"📖 Loaded {len(metadata_list)} model metadata entries")
            return metadata_list
            
        except Exception as e:
            logger.error(f"❌ Failed to load retention metadata: {e}")
            logger.info("🔄 Falling back to scanning data directory...")
            return await self._scan_and_create_metadata()
    
    async def _scan_and_create_metadata(self) -> List[ModelRetentionMetadata]:
        """
        Scan data directory and create metadata for existing models.
        
        Returns:
            List of ModelRetentionMetadata objects
        """
        logger.info("🔍 Scanning data directory for existing models...")
        
        metadata_list = []
        current_time = datetime.now(timezone.utc)
        
        # Load main GGUF models data
        gguf_models_file = self.data_dir / "gguf_models.json"
        if gguf_models_file.exists():
            try:
                with open(gguf_models_file, 'r', encoding='utf-8') as f:
                    models_data = json.load(f)
                
                for model_data in models_data:
                    model_id = model_data.get('id', '')
                    if not model_id:
                        continue
                    
                    # Estimate file paths (this is a best guess)
                    file_paths = []
                    
                    # Check for common model file locations
                    potential_paths = [
                        self.data_dir / f"{model_id}.json",
                        self.data_dir / "models" / model_id,
                        self.data_dir / "cache" / model_id
                    ]
                    
                    for path in potential_paths:
                        if path.exists():
                            file_paths.append(str(path))
                    
                    # Calculate file size
                    file_size = 0
                    for file_path in file_paths:
                        try:
                            path = Path(file_path)
                            if path.is_file():
                                file_size += path.stat().st_size
                            elif path.is_dir():
                                for sub_path in path.rglob('*'):
                                    if sub_path.is_file():
                                        file_size += sub_path.stat().st_size
                        except:
                            pass
                    
                    metadata = ModelRetentionMetadata(
                        model_id=model_id,
                        first_seen=current_time,  # Unknown, use current time
                        last_updated=current_time,
                        source='unknown',
                        download_count=model_data.get('downloads', 0),
                        retention_reason='existing_model',
                        cleanup_eligible=False,  # Don't clean up until we have proper tracking
                        file_size_bytes=file_size,
                        file_paths=file_paths
                    )
                    
                    metadata_list.append(metadata)
                
                logger.info(f"📊 Created metadata for {len(metadata_list)} existing models")
                
                # Save the created metadata
                await self._save_retention_metadata(metadata_list)
                
            except Exception as e:
                logger.error(f"❌ Failed to scan existing models: {e}")
        
        return metadata_list
    
    async def _save_retention_metadata(self, metadata_list: List[ModelRetentionMetadata]) -> None:
        """
        Save retention metadata to storage.
        
        Args:
            metadata_list: List of metadata to save
        """
        try:
            # Convert to serializable format
            serializable_data = []
            for metadata in metadata_list:
                data_dict = asdict(metadata)
                data_dict['first_seen'] = metadata.first_seen.isoformat()
                data_dict['last_updated'] = metadata.last_updated.isoformat()
                serializable_data.append(data_dict)
            
            # Create storage data
            storage_data = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'total_models': len(metadata_list),
                'models': serializable_data
            }
            
            # Save to file
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(storage_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Saved retention metadata for {len(metadata_list)} models")
            
        except Exception as e:
            logger.error(f"❌ Failed to save retention metadata: {e}")
            raise
    
    async def _update_metadata_after_cleanup(self, removed_models: List[ModelRetentionMetadata]) -> None:
        """
        Update metadata after cleanup to remove cleaned up models.
        
        Args:
            removed_models: List of models that were successfully removed
        """
        try:
            # Load current metadata
            current_metadata = await self._load_retention_metadata()
            
            # Remove cleaned up models from metadata
            removed_ids = {model.model_id for model in removed_models}
            updated_metadata = [
                model for model in current_metadata 
                if model.model_id not in removed_ids
            ]
            
            # Save updated metadata
            await self._save_retention_metadata(updated_metadata)
            
            logger.info(f"📝 Updated metadata: removed {len(removed_models)} cleaned up models")
            
        except Exception as e:
            logger.error(f"❌ Failed to update metadata after cleanup: {e}")
            # Don't raise - this is not critical for cleanup success
    
    def generate_cleanup_report(self, removed_count: int, preserved_count: int, 
                              storage_freed_mb: float) -> Dict[str, Any]:
        """
        Generate cleanup statistics report.
        
        Args:
            removed_count: Number of models removed
            preserved_count: Number of models preserved
            storage_freed_mb: Storage space freed in MB
            
        Returns:
            Dictionary containing cleanup report
        """
        return {
            'cleanup_summary': {
                'models_removed': removed_count,
                'models_preserved': preserved_count,
                'storage_freed_mb': storage_freed_mb,
                'cleanup_enabled': self.retention_config.enable_cleanup,
                'retention_days': self.retention_days,
                'preserve_download_threshold': self.retention_config.preserve_download_threshold
            },
            'configuration': {
                'cleanup_batch_size': self.retention_config.cleanup_batch_size,
                'enable_backups': self.config.storage.enable_backups,
                'backup_retention_days': self.config.storage.backup_retention_days
            },
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    async def cleanup_with_error_handling(self, top_models: List[str], 
                                        error_recovery_system=None) -> CleanupReport:
        """
        Cleanup old models with comprehensive error handling.
        
        Args:
            top_models: List of model IDs to preserve
            error_recovery_system: Optional error recovery system
            
        Returns:
            CleanupReport with success/failure information
        """
        if error_recovery_system:
            return await with_error_handling(
                lambda: self.cleanup_old_models(top_models),
                "retention_cleanup",
                error_recovery_system,
                model_id="retention_cleanup_manager"
            )
        else:
            return await self.cleanup_old_models(top_models)