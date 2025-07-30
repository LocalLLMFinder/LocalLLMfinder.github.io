#!/usr/bin/env python3
"""
ScheduledUpdateOrchestrator for Dynamic Model Retention System

This module implements the ScheduledUpdateOrchestrator class that manages the complete
update workflow with sequential phase execution, comprehensive error handling with
rollback capabilities, and detailed reporting and metrics collection.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from huggingface_hub import HfApi

# Import existing systems for integration
from config_system import SyncConfiguration, DynamicRetentionConfig
from error_handling import ErrorRecoverySystem, ErrorContext, NotificationConfig
from date_filtered_extractor import DateFilteredExtractor, DateFilterResult
from top_models_manager import TopModelsManager, TopModelsUpdateResult
from retention_cleanup_manager import RetentionCleanupManager, CleanupReport
from data_merger import DataMerger, MergeResult

logger = logging.getLogger(__name__)

@dataclass
class PhaseResult:
    """Result of a single phase execution."""
    phase_name: str
    success: bool
    duration_seconds: float
    data_count: int
    error_message: Optional[str] = None
    metrics: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metrics is None:
            self.metrics = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert PhaseResult to dictionary for JSON serialization."""
        return asdict(self)

@dataclass
class UpdateReport:
    """Comprehensive update report for the complete workflow."""
    timestamp: datetime
    total_duration_seconds: float
    overall_success: bool
    phases_completed: int
    phases_failed: int
    
    # Phase results
    top_models_phase: Optional[PhaseResult] = None
    recent_models_phase: Optional[PhaseResult] = None
    merge_phase: Optional[PhaseResult] = None
    cleanup_phase: Optional[PhaseResult] = None
    
    # Summary statistics
    total_models_processed: int = 0
    top_models_updated: int = 0
    recent_models_fetched: int = 0
    models_merged: int = 0
    duplicates_removed: int = 0
    models_cleaned_up: int = 0
    storage_freed_mb: float = 0.0
    api_calls_made: int = 0
    
    # Error information
    errors_encountered: List[str] = None
    rollback_performed: bool = False
    rollback_successful: bool = False
    
    def __post_init__(self):
        if self.errors_encountered is None:
            self.errors_encountered = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert UpdateReport to dictionary for JSON serialization."""
        result = asdict(self)
        
        # Convert datetime to ISO string
        if isinstance(result.get('timestamp'), datetime):
            result['timestamp'] = result['timestamp'].isoformat()
        
        return result

class ScheduledUpdateOrchestrator:
    """
    Orchestrates the complete daily update process with proper sequencing.
    
    This class manages the sequential execution of all update phases:
    1. Top models update
    2. Recent models extraction  
    3. Data merge and deduplication
    4. Cleanup of old models
    
    It provides comprehensive error handling, rollback capabilities, and
    detailed reporting for monitoring and debugging purposes.
    """
    
    def __init__(self, config: SyncConfiguration, api: HfApi = None, rate_limiter = None):
        """
        Initialize the ScheduledUpdateOrchestrator.
        
        Args:
            config: System configuration containing retention settings
            api: HuggingFace API instance (optional, will create if not provided)
            rate_limiter: Rate limiter for API calls (optional)
        """
        self.config = config
        self.retention_config = config.dynamic_retention
        
        # Initialize API if not provided
        if api is None:
            self.api = HfApi(token=config.huggingface_token)
        else:
            self.api = api
        
        # Initialize rate limiter if not provided
        if rate_limiter is None:
            # Create a simple rate limiter placeholder
            self.rate_limiter = self._create_simple_rate_limiter()
        else:
            self.rate_limiter = rate_limiter
        
        # Initialize component managers
        self.date_extractor = DateFilteredExtractor(config, self.api, self.rate_limiter)
        self.top_manager = TopModelsManager(config, self.api, self.rate_limiter)
        self.cleanup_manager = RetentionCleanupManager(config)
        self.data_merger = DataMerger(config)
        
        # Initialize error recovery system with retention-specific capabilities
        notification_config = NotificationConfig(
            email_enabled=config.notifications.enable_failure_notifications,
            webhook_enabled=len(config.notifications.webhook_urls) > 0,
            webhook_url=config.notifications.webhook_urls[0] if config.notifications.webhook_urls else ""
        )
        
        # Import retention-specific error handling
        from retention_error_handling import RetentionErrorRecoverySystem
        self.error_recovery = RetentionErrorRecoverySystem(config.storage.data_directory)
        
        # Storage paths
        self.reports_dir = Path(config.storage.reports_directory)
        self.backup_dir = Path(config.storage.backup_directory)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"🎯 Initialized ScheduledUpdateOrchestrator:")
        logger.info(f"   • Retention mode: {'enabled' if self.retention_config.enable_retention_mode else 'disabled'}")
        logger.info(f"   • Top models count: {self.retention_config.top_models_count}")
        logger.info(f"   • Retention days: {self.retention_config.retention_days}")
        logger.info(f"   • Cleanup enabled: {self.retention_config.enable_cleanup}")
    
    def _create_simple_rate_limiter(self):
        """Create a simple rate limiter for API calls."""
        class SimpleRateLimiter:
            def __init__(self, requests_per_second=1.2):
                self.requests_per_second = requests_per_second
                self.last_request_time = 0
                
            async def __aenter__(self):
                import time
                import asyncio
                current_time = time.time()
                time_since_last = current_time - self.last_request_time
                min_interval = 1.0 / self.requests_per_second
                
                if time_since_last < min_interval:
                    sleep_time = min_interval - time_since_last
                    await asyncio.sleep(sleep_time)
                
                self.last_request_time = time.time()
                return self
                
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        return SimpleRateLimiter(self.config.rate_limiting.requests_per_second)
    
    async def run_daily_update(self) -> UpdateReport:
        """
        Execute the complete daily update process.
        
        Returns:
            UpdateReport containing comprehensive results and metrics
        """
        logger.info("🚀 Starting daily update orchestration...")
        start_time = datetime.now()
        
        # Initialize report
        report = UpdateReport(
            timestamp=datetime.now(timezone.utc),
            total_duration_seconds=0.0,
            overall_success=False,
            phases_completed=0,
            phases_failed=0
        )
        
        # Create backup before starting
        backup_created = await self._create_pre_update_backup()
        if not backup_created:
            logger.warning("⚠️ Failed to create pre-update backup, continuing anyway...")
        
        try:
            # Phase 1: Update top models
            logger.info("📊 Phase 1: Updating top models...")
            top_result = await self._execute_phase_with_error_handling(
                "top_models_update",
                self.update_top_models_phase
            )
            report.top_models_phase = top_result
            
            if top_result.success:
                report.phases_completed += 1
                report.top_models_updated = top_result.data_count
                report.api_calls_made += top_result.metrics.get('api_calls_made', 0)
            else:
                report.phases_failed += 1
                report.errors_encountered.append(f"Top models phase: {top_result.error_message}")
            
            # Phase 2: Extract recent models
            logger.info("🗓️ Phase 2: Extracting recent models...")
            recent_result = await self._execute_phase_with_error_handling(
                "recent_models_extraction", 
                self.extract_recent_models_phase
            )
            report.recent_models_phase = recent_result
            
            if recent_result.success:
                report.phases_completed += 1
                report.recent_models_fetched = recent_result.data_count
                report.api_calls_made += recent_result.metrics.get('api_calls_made', 0)
            else:
                report.phases_failed += 1
                report.errors_encountered.append(f"Recent models phase: {recent_result.error_message}")
            
            # Phase 3: Merge and deduplicate data
            logger.info("🔄 Phase 3: Merging and deduplicating data...")
            merge_result = await self._execute_phase_with_error_handling(
                "data_merge",
                self.merge_and_deduplicate_phase,
                top_result.metrics.get('models', []) if top_result.success else [],
                recent_result.metrics.get('models', []) if recent_result.success else []
            )
            report.merge_phase = merge_result
            
            if merge_result.success:
                report.phases_completed += 1
                report.models_merged = merge_result.data_count
                report.duplicates_removed = merge_result.metrics.get('duplicates_removed', 0)
            else:
                report.phases_failed += 1
                report.errors_encountered.append(f"Merge phase: {merge_result.error_message}")
            
            # Phase 4: Cleanup old models (only if cleanup is enabled)
            if self.retention_config.enable_cleanup:
                logger.info("🧹 Phase 4: Cleaning up old models...")
                
                # Get top models list for preservation
                top_models_list = []
                if top_result.success and 'models' in top_result.metrics:
                    top_models_list = [m.id if hasattr(m, 'id') else m.get('id', '') 
                                     for m in top_result.metrics['models']]
                
                cleanup_result = await self._execute_phase_with_error_handling(
                    "cleanup",
                    self.cleanup_phase,
                    top_models_list
                )
                report.cleanup_phase = cleanup_result
                
                if cleanup_result.success:
                    report.phases_completed += 1
                    report.models_cleaned_up = cleanup_result.metrics.get('models_removed', 0)
                    report.storage_freed_mb = cleanup_result.metrics.get('storage_freed_mb', 0.0)
                else:
                    report.phases_failed += 1
                    report.errors_encountered.append(f"Cleanup phase: {cleanup_result.error_message}")
            else:
                logger.info("⏸️ Phase 4: Cleanup disabled, skipping...")
            
            # Calculate totals
            report.total_models_processed = (
                report.top_models_updated + 
                report.recent_models_fetched
            )
            
            # Determine overall success
            critical_phases_successful = (
                report.top_models_phase and report.top_models_phase.success and
                report.recent_models_phase and report.recent_models_phase.success and
                report.merge_phase and report.merge_phase.success
            )
            
            report.overall_success = critical_phases_successful and report.phases_failed == 0
            
            # Calculate total duration
            report.total_duration_seconds = (datetime.now() - start_time).total_seconds()
            
            # Log final results
            if report.overall_success:
                logger.info("✅ Daily update orchestration completed successfully!")
                logger.info(f"📊 Summary:")
                logger.info(f"   • Total duration: {report.total_duration_seconds:.1f}s")
                logger.info(f"   • Models processed: {report.total_models_processed}")
                logger.info(f"   • Top models updated: {report.top_models_updated}")
                logger.info(f"   • Recent models fetched: {report.recent_models_fetched}")
                logger.info(f"   • Models merged: {report.models_merged}")
                logger.info(f"   • Duplicates removed: {report.duplicates_removed}")
                if self.retention_config.enable_cleanup:
                    logger.info(f"   • Models cleaned up: {report.models_cleaned_up}")
                    logger.info(f"   • Storage freed: {report.storage_freed_mb:.1f} MB")
                logger.info(f"   • API calls made: {report.api_calls_made}")
                logger.info(f"   • Phases completed: {report.phases_completed}")
            else:
                logger.error("❌ Daily update orchestration failed!")
                logger.error(f"   • Phases completed: {report.phases_completed}")
                logger.error(f"   • Phases failed: {report.phases_failed}")
                logger.error(f"   • Errors: {len(report.errors_encountered)}")
                for error in report.errors_encountered:
                    logger.error(f"     - {error}")
                
                # Attempt rollback if configured
                if self.config.error_handling.preserve_data_on_failure:
                    logger.info("🔄 Attempting rollback...")
                    rollback_success = await self._perform_rollback()
                    report.rollback_performed = True
                    report.rollback_successful = rollback_success
            
            # Save report
            await self._save_update_report(report)
            
            return report
            
        except Exception as e:
            # Handle unexpected errors
            report.total_duration_seconds = (datetime.now() - start_time).total_seconds()
            report.overall_success = False
            report.errors_encountered.append(f"Unexpected error: {str(e)}")
            
            logger.error(f"❌ Unexpected error during orchestration: {e}")
            
            # Attempt rollback
            if self.config.error_handling.preserve_data_on_failure:
                logger.info("🔄 Attempting emergency rollback...")
                rollback_success = await self._perform_rollback()
                report.rollback_performed = True
                report.rollback_successful = rollback_success
            
            await self._save_update_report(report)
            return report
    
    async def update_top_models_phase(self) -> Tuple[List, Dict[str, Any]]:
        """
        Phase 1: Update top models list.
        
        Returns:
            Tuple of (models_list, metrics_dict)
        """
        logger.info("🏆 Executing top models update phase...")
        
        result = await self.top_manager.update_top_models()
        
        if not result.success:
            raise Exception(f"Top models update failed: {result.error_message}")
        
        metrics = {
            'models': result.models,
            'rankings': result.rankings,
            'api_calls_made': result.api_calls_made,
            'changes_detected': result.changes_detected,
            'new_entries': result.new_entries,
            'dropped_entries': result.dropped_entries,
            'update_time_seconds': result.update_time_seconds
        }
        
        logger.info(f"✅ Top models phase completed: {len(result.models)} models updated")
        return result.models, metrics
    
    async def extract_recent_models_phase(self) -> Tuple[List, Dict[str, Any]]:
        """
        Phase 2: Extract recent models.
        
        Returns:
            Tuple of (models_list, metrics_dict)
        """
        logger.info("📅 Executing recent models extraction phase...")
        
        result = await self.date_extractor.extract_recent_models()
        
        if not result.success:
            raise Exception(f"Recent models extraction failed: {result.error_message}")
        
        metrics = {
            'models': result.models,
            'total_found': result.total_found,
            'date_range_start': result.date_range_start.isoformat(),
            'date_range_end': result.date_range_end.isoformat(),
            'api_calls_made': result.api_calls_made,
            'extraction_time_seconds': result.extraction_time_seconds
        }
        
        logger.info(f"✅ Recent models phase completed: {len(result.models)} models extracted")
        return result.models, metrics
    
    async def merge_and_deduplicate_phase(self, recent_models: List, top_models: List) -> Tuple[List, Dict[str, Any]]:
        """
        Phase 3: Merge and deduplicate data.
        
        Args:
            recent_models: List of recent models from phase 2
            top_models: List of top models from phase 1
            
        Returns:
            Tuple of (merged_models_list, metrics_dict)
        """
        logger.info("🔄 Executing merge and deduplication phase...")
        
        result = self.data_merger.merge_datasets(recent_models, top_models)
        
        if not result.success:
            raise Exception(f"Data merge failed: {result.error_message}")
        
        metrics = {
            'merged_models': result.merged_models,
            'total_models': result.total_models,
            'recent_models_count': result.recent_models_count,
            'top_models_count': result.top_models_count,
            'duplicates_removed': result.duplicates_removed,
            'merge_time_seconds': result.merge_time_seconds,
            'data_integrity_score': result.data_integrity_score,
            'merge_statistics': result.merge_statistics
        }
        
        logger.info(f"✅ Merge phase completed: {len(result.merged_models)} models merged")
        return result.merged_models, metrics
    
    async def cleanup_phase(self, top_models: List[str]) -> Tuple[int, Dict[str, Any]]:
        """
        Phase 4: Clean up old models.
        
        Args:
            top_models: List of top model IDs to preserve
            
        Returns:
            Tuple of (models_removed_count, metrics_dict)
        """
        logger.info("🧹 Executing cleanup phase...")
        
        result = await self.cleanup_manager.cleanup_old_models(top_models)
        
        if not result.success:
            raise Exception(f"Cleanup failed: {result.errors_encountered}")
        
        metrics = {
            'models_evaluated': result.models_evaluated,
            'models_removed': result.models_removed,
            'models_preserved': result.models_preserved,
            'storage_freed_bytes': result.storage_freed_bytes,
            'storage_freed_mb': result.storage_freed_mb,
            'cleanup_duration_seconds': result.cleanup_duration_seconds,
            'top_models_preserved': result.top_models_preserved,
            'high_download_preserved': result.high_download_preserved,
            'recent_models_preserved': result.recent_models_preserved,
            'removed_model_ids': result.removed_model_ids,
            'preserved_model_ids': result.preserved_model_ids
        }
        
        logger.info(f"✅ Cleanup phase completed: {result.models_removed} models removed")
        return result.models_removed, metrics
    
    async def _execute_phase_with_error_handling(self, phase_name: str, phase_func, *args) -> PhaseResult:
        """
        Execute a phase with comprehensive error handling and recovery.
        
        Args:
            phase_name: Name of the phase for logging and error tracking
            phase_func: Function to execute for this phase
            *args: Arguments to pass to the phase function
            
        Returns:
            PhaseResult containing execution results and metrics
        """
        start_time = datetime.now()
        
        # Create rollback point before critical phases
        rollback_id = None
        if phase_name in ["top_models_update", "recent_models_extraction", "data_merge"]:
            try:
                files_to_backup = [
                    f"{self.config.storage.data_directory}/gguf_models.json",
                    f"{self.config.storage.data_directory}/top_models.json",
                    f"{self.config.storage.data_directory}/retention_metadata.json"
                ]
                rollback_id = await self.error_recovery.create_phase_rollback_point(
                    phase_name, files_to_backup
                )
            except Exception as backup_error:
                logger.warning(f"⚠️ Failed to create rollback point for {phase_name}: {backup_error}")
        
        try:
            # Execute the phase with circuit breaker protection for API-heavy operations
            if phase_name in ["top_models_update", "recent_models_extraction"]:
                data, metrics = await self.error_recovery.with_circuit_breaker(
                    f"phase_{phase_name}", phase_func, *args
                )
            else:
                data, metrics = await phase_func(*args)
            
            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds()
            
            # Save successful data as fallback for future failures
            if phase_name == "top_models_update" and data:
                try:
                    await self.error_recovery.fallback_manager.save_successful_top_models(
                        [model.__dict__ if hasattr(model, '__dict__') else model for model in data]
                    )
                except Exception as save_error:
                    logger.warning(f"⚠️ Failed to save fallback data: {save_error}")
            
            # Create successful result
            return PhaseResult(
                phase_name=phase_name,
                success=True,
                duration_seconds=duration,
                data_count=len(data) if isinstance(data, list) else (data if isinstance(data, int) else 0),
                metrics=metrics
            )
            
        except Exception as e:
            # Handle phase error with comprehensive recovery
            duration = (datetime.now() - start_time).total_seconds()
            
            logger.error(f"❌ Phase '{phase_name}' failed: {e}")
            
            # Import retention error context
            from retention_error_handling import RetentionErrorContext
            
            # Create retention-specific error context
            error_context = RetentionErrorContext(
                operation=f"orchestrator_phase_{phase_name}",
                phase=phase_name,
                models_processed=0,
                models_failed=1,
                storage_path=f"{self.config.storage.data_directory}/{phase_name}_data.json",
                backup_available=rollback_id is not None,
                rollback_point=rollback_id,
                additional_info={
                    'phase_name': phase_name,
                    'phase_duration': duration,
                    'args_count': len(args)
                }
            )
            
            # Attempt phase-specific recovery
            recovery_result = await self.error_recovery.handle_phase_failure(
                phase_name, e, error_context
            )
            
            # If recovery was successful, return recovered data
            if recovery_result.get('recovered', False):
                logger.info(f"✅ Phase '{phase_name}' recovered successfully")
                
                recovered_data = recovery_result.get('data', [])
                recovery_metrics = {
                    'recovery_method': 'fallback' if recovery_result.get('fallback_used') else 'rollback',
                    'original_error': str(e),
                    'recovery_successful': True
                }
                
                return PhaseResult(
                    phase_name=phase_name,
                    success=True,
                    duration_seconds=duration,
                    data_count=len(recovered_data) if isinstance(recovered_data, list) else 0,
                    metrics=recovery_metrics
                )
            
            # Recovery failed, create failed result
            return PhaseResult(
                phase_name=phase_name,
                success=False,
                duration_seconds=duration,
                data_count=0,
                error_message=str(e),
                metrics={
                    'recovery_attempted': True,
                    'recovery_successful': False,
                    'recovery_method': recovery_result.get('recovery_method', 'none')
                }
            )
    
    async def _create_pre_update_backup(self) -> bool:
        """
        Create backup before starting update process.
        
        Returns:
            bool: True if backup was created successfully
        """
        if not self.config.storage.enable_backups:
            logger.info("📁 Backups disabled, skipping pre-update backup")
            return True
        
        try:
            logger.info("💾 Creating pre-update backup...")
            
            backup_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = self.backup_dir / f"pre_update_{backup_timestamp}"
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Backup critical data files
            data_dir = Path(self.config.storage.data_directory)
            critical_files = [
                "gguf_models.json",
                "gguf_models_estimated_sizes.json",
                "top_models.json",
                "retention_metadata.json"
            ]
            
            backup_count = 0
            for filename in critical_files:
                source_file = data_dir / filename
                if source_file.exists():
                    backup_file = backup_dir / filename
                    import shutil
                    shutil.copy2(source_file, backup_file)
                    backup_count += 1
                    logger.debug(f"💾 Backed up: {filename}")
            
            # Create backup manifest
            manifest = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'backup_type': 'pre_update',
                'files_backed_up': backup_count,
                'backup_directory': str(backup_dir),
                'retention_config': asdict(self.retention_config)
            }
            
            manifest_file = backup_dir / "backup_manifest.json"
            with open(manifest_file, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            
            logger.info(f"✅ Pre-update backup created: {backup_count} files backed up")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create pre-update backup: {e}")
            return False
    
    async def _perform_rollback(self) -> bool:
        """
        Perform rollback to previous state.
        
        Returns:
            bool: True if rollback was successful
        """
        try:
            logger.info("🔄 Performing rollback to previous state...")
            
            # Find the most recent backup
            backup_dirs = [d for d in self.backup_dir.iterdir() 
                          if d.is_dir() and d.name.startswith('pre_update_')]
            
            if not backup_dirs:
                logger.error("❌ No backup found for rollback")
                return False
            
            # Sort by timestamp (most recent first)
            backup_dirs.sort(key=lambda x: x.name, reverse=True)
            latest_backup = backup_dirs[0]
            
            logger.info(f"🔄 Rolling back from backup: {latest_backup.name}")
            
            # Restore files from backup
            data_dir = Path(self.config.storage.data_directory)
            restored_count = 0
            
            for backup_file in latest_backup.iterdir():
                if backup_file.name == "backup_manifest.json":
                    continue
                
                target_file = data_dir / backup_file.name
                import shutil
                shutil.copy2(backup_file, target_file)
                restored_count += 1
                logger.debug(f"🔄 Restored: {backup_file.name}")
            
            logger.info(f"✅ Rollback completed: {restored_count} files restored")
            return True
            
        except Exception as e:
            logger.error(f"❌ Rollback failed: {e}")
            return False
    
    async def _save_update_report(self, report: UpdateReport) -> None:
        """
        Save update report to file.
        
        Args:
            report: UpdateReport to save
        """
        try:
            # Create report filename with timestamp
            timestamp_str = report.timestamp.strftime("%Y%m%d_%H%M%S")
            report_filename = f"update_report_{timestamp_str}.json"
            report_path = self.reports_dir / report_filename
            
            # Convert report to dictionary
            report_dict = asdict(report)
            
            # Convert datetime objects to ISO strings
            report_dict['timestamp'] = report.timestamp.isoformat()
            
            # Handle nested datetime objects in phase results
            for phase_key in ['top_models_phase', 'recent_models_phase', 'merge_phase', 'cleanup_phase']:
                if report_dict[phase_key] and 'metrics' in report_dict[phase_key]:
                    metrics = report_dict[phase_key]['metrics']
                    for key, value in metrics.items():
                        if isinstance(value, datetime):
                            metrics[key] = value.isoformat()
            
            # Save report
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report_dict, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"📊 Update report saved: {report_path}")
            
            # Also save as latest report
            latest_report_path = self.reports_dir / "latest_update_report.json"
            with open(latest_report_path, 'w', encoding='utf-8') as f:
                json.dump(report_dict, f, indent=2, ensure_ascii=False, default=str)
            
        except Exception as e:
            logger.error(f"❌ Failed to save update report: {e}")
    
    def _create_simple_rate_limiter(self):
        """Create a simple rate limiter for API calls."""
        class SimpleRateLimiter:
            def __init__(self, requests_per_second=1.2):
                self.requests_per_second = requests_per_second
                self.last_request_time = 0
            
            async def __aenter__(self):
                current_time = asyncio.get_event_loop().time()
                time_since_last = current_time - self.last_request_time
                min_interval = 1.0 / self.requests_per_second
                
                if time_since_last < min_interval:
                    await asyncio.sleep(min_interval - time_since_last)
                
                self.last_request_time = asyncio.get_event_loop().time()
                return self
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        return SimpleRateLimiter(self.config.rate_limiting.requests_per_second)
    
    def get_orchestrator_status(self) -> Dict[str, Any]:
        """
        Get current orchestrator status and configuration.
        
        Returns:
            Dict containing orchestrator status information
        """
        return {
            "orchestrator_type": "ScheduledUpdateOrchestrator",
            "retention_mode_enabled": self.retention_config.enable_retention_mode,
            "configuration": {
                "retention_days": self.retention_config.retention_days,
                "top_models_count": self.retention_config.top_models_count,
                "cleanup_enabled": self.retention_config.enable_cleanup,
                "cleanup_batch_size": self.retention_config.cleanup_batch_size,
                "preserve_download_threshold": self.retention_config.preserve_download_threshold,
                "update_schedule": self.retention_config.update_schedule_cron
            },
            "components": {
                "date_extractor": "DateFilteredExtractor",
                "top_manager": "TopModelsManager", 
                "cleanup_manager": "RetentionCleanupManager",
                "data_merger": "DataMerger",
                "error_recovery": "ErrorRecoverySystem"
            },
            "storage_paths": {
                "reports_directory": str(self.reports_dir),
                "backup_directory": str(self.backup_dir)
            },
            "error_handling": {
                "preserve_data_on_failure": self.config.error_handling.preserve_data_on_failure,
                "max_recovery_attempts": self.config.error_handling.max_recovery_attempts,
                "enable_notifications": self.config.notifications.enable_failure_notifications
            }
        }

# Convenience function for external usage
async def run_scheduled_update(config: SyncConfiguration = None) -> UpdateReport:
    """
    Convenience function to run a scheduled update.
    
    Args:
        config: Optional configuration (will load default if not provided)
        
    Returns:
        UpdateReport containing the results
    """
    if config is None:
        from config_system import load_configuration
        config = load_configuration()
    
    orchestrator = ScheduledUpdateOrchestrator(config)
    return await orchestrator.run_daily_update()

if __name__ == "__main__":
    # Example usage and testing
    import asyncio
    
    async def main():
        logging.basicConfig(level=logging.INFO)
        
        try:
            from config_system import load_configuration
            config = load_configuration()
            
            # Enable retention mode for testing
            config.dynamic_retention.enable_retention_mode = True
            
            orchestrator = ScheduledUpdateOrchestrator(config)
            
            print("🎯 Starting orchestrated update...")
            report = await orchestrator.run_daily_update()
            
            print(f"\n📊 Update Report:")
            print(f"   Success: {report.overall_success}")
            print(f"   Duration: {report.total_duration_seconds:.1f}s")
            print(f"   Phases completed: {report.phases_completed}")
            print(f"   Models processed: {report.total_models_processed}")
            
            if report.errors_encountered:
                print(f"   Errors: {len(report.errors_encountered)}")
                for error in report.errors_encountered:
                    print(f"     - {error}")
            
        except Exception as e:
            print(f"❌ Orchestration failed: {e}")
    
    asyncio.run(main())