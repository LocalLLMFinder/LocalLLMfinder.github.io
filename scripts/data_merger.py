#!/usr/bin/env python3
"""
DataMerger for Dynamic Model Retention System

This module implements the DataMerger class that combines recent models and top models
datasets while handling deduplication, source metadata tracking, and data validation
during merge operations.
"""

import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict
import json

# Import existing systems for integration
from config_system import SyncConfiguration, DynamicRetentionConfig
from error_handling import with_error_handling, ErrorContext

logger = logging.getLogger(__name__)

@dataclass
class ModelReference:
    """Unified model reference for merged datasets."""
    id: str
    discovery_method: str = "unknown"
    confidence_score: float = 1.0
    metadata: Dict[str, Any] = None
    source: str = "unknown"  # 'recent', 'top', 'merged'
    priority_score: float = 0.0
    upload_date: Optional[datetime] = None
    download_count: int = 0
    rank: Optional[int] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class MergeResult:
    """Result of dataset merge operation."""
    merged_models: List[ModelReference]
    total_models: int
    recent_models_count: int
    top_models_count: int
    duplicates_removed: int
    merge_time_seconds: float
    data_integrity_score: float
    success: bool
    error_message: Optional[str] = None
    merge_statistics: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.merge_statistics is None:
            self.merge_statistics = {}

class DataMerger:
    """
    Combines recent models and top models datasets with deduplication and validation.
    
    This class handles the complex task of merging two different model datasets
    while preserving data integrity, applying proper prioritization, and tracking
    source metadata for debugging and analytics purposes.
    """
    
    def __init__(self, config: SyncConfiguration):
        """
        Initialize the DataMerger.
        
        Args:
            config: System configuration containing retention settings
        """
        self.config = config
        self.retention_config = config.dynamic_retention
        
        # Priority weights for different sources
        self.priority_weights = {
            'top': 1.0,      # Top models get highest priority
            'recent': 0.8,   # Recent models get medium priority
            'merged': 0.6    # Previously merged models get lower priority
        }
        
        logger.info(f"🔄 Initialized DataMerger:")
        logger.info(f"   • Top models priority weight: {self.priority_weights['top']}")
        logger.info(f"   • Recent models priority weight: {self.priority_weights['recent']}")
        logger.info(f"   • Recent models priority: {self.retention_config.recent_models_priority}")
    
    def merge_datasets(self, recent_models: List, top_models: List) -> MergeResult:
        """
        Merge recent and top models with deduplication and prioritization.
        
        Args:
            recent_models: List of models from DateFilteredExtractor
            top_models: List of models from TopModelsManager
            
        Returns:
            MergeResult containing the merged dataset and statistics
        """
        logger.info(f"🔄 Starting dataset merge:")
        logger.info(f"   • Recent models: {len(recent_models)}")
        logger.info(f"   • Top models: {len(top_models)}")
        
        start_time = datetime.now()
        
        try:
            # Normalize input models to unified format
            normalized_recent = self._normalize_recent_models(recent_models)
            normalized_top = self._normalize_top_models(top_models)
            
            logger.info(f"📊 Normalized models:")
            logger.info(f"   • Recent models normalized: {len(normalized_recent)}")
            logger.info(f"   • Top models normalized: {len(normalized_top)}")
            
            # Add source metadata
            recent_with_source = self.add_source_metadata(normalized_recent, "recent")
            top_with_source = self.add_source_metadata(normalized_top, "top")
            
            # Combine all models
            all_models = recent_with_source + top_with_source
            
            # Deduplicate models
            deduplicated_models = self.deduplicate_models(all_models)
            
            # Apply prioritization
            prioritized_models = self.prioritize_models(deduplicated_models)
            
            # Validate data integrity
            integrity_score = self._validate_data_integrity(prioritized_models)
            
            # Calculate merge time
            merge_time = (datetime.now() - start_time).total_seconds()
            
            # Generate merge statistics
            merge_stats = self._generate_merge_statistics(
                recent_models, top_models, prioritized_models, 
                len(all_models) - len(deduplicated_models)
            )
            
            result = MergeResult(
                merged_models=prioritized_models,
                total_models=len(prioritized_models),
                recent_models_count=len(recent_with_source),
                top_models_count=len(top_with_source),
                duplicates_removed=len(all_models) - len(deduplicated_models),
                merge_time_seconds=merge_time,
                data_integrity_score=integrity_score,
                success=True,
                merge_statistics=merge_stats
            )
            
            logger.info(f"✅ Dataset merge completed:")
            logger.info(f"   • Total merged models: {len(prioritized_models)}")
            logger.info(f"   • Duplicates removed: {result.duplicates_removed}")
            logger.info(f"   • Data integrity score: {integrity_score:.2f}")
            logger.info(f"   • Merge time: {merge_time:.1f}s")
            
            return result
            
        except Exception as e:
            merge_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Dataset merge failed: {e}")
            
            return MergeResult(
                merged_models=[],
                total_models=0,
                recent_models_count=len(recent_models) if recent_models else 0,
                top_models_count=len(top_models) if top_models else 0,
                duplicates_removed=0,
                merge_time_seconds=merge_time,
                data_integrity_score=0.0,
                success=False,
                error_message=str(e)
            )
    
    def deduplicate_models(self, models: List[ModelReference]) -> List[ModelReference]:
        """
        Remove duplicate models based on model ID with priority handling.
        
        Args:
            models: List of models that may contain duplicates
            
        Returns:
            List of deduplicated models with highest priority versions kept
        """
        logger.info(f"🔍 Starting deduplication of {len(models)} models...")
        
        # Group models by ID
        models_by_id = defaultdict(list)
        for model in models:
            models_by_id[model.id].append(model)
        
        deduplicated = []
        duplicates_found = 0
        
        for model_id, model_group in models_by_id.items():
            if len(model_group) == 1:
                # No duplicates for this model
                deduplicated.append(model_group[0])
            else:
                # Handle duplicates - keep the highest priority version
                duplicates_found += len(model_group) - 1
                
                # Sort by priority score (highest first)
                sorted_models = sorted(model_group, key=lambda m: m.priority_score, reverse=True)
                best_model = sorted_models[0]
                
                # Merge metadata from all versions
                merged_metadata = self._merge_model_metadata(model_group)
                best_model.metadata.update(merged_metadata)
                
                # Update source to indicate it's merged if from multiple sources
                sources = set(m.source for m in model_group)
                if len(sources) > 1:
                    best_model.source = "merged"
                    best_model.metadata["original_sources"] = list(sources)
                
                deduplicated.append(best_model)
                
                logger.debug(f"🔄 Deduplicated {model_id}: kept {best_model.source} version "
                           f"(priority: {best_model.priority_score:.2f})")
        
        logger.info(f"✅ Deduplication completed:")
        logger.info(f"   • Original models: {len(models)}")
        logger.info(f"   • Deduplicated models: {len(deduplicated)}")
        logger.info(f"   • Duplicates removed: {duplicates_found}")
        
        return deduplicated
    
    def add_source_metadata(self, models: List[ModelReference], source: str) -> List[ModelReference]:
        """
        Add metadata indicating data source (recent/top).
        
        Args:
            models: List of models to add source metadata to
            source: Source identifier ('recent', 'top', etc.)
            
        Returns:
            List of models with source metadata added
        """
        logger.debug(f"📝 Adding source metadata '{source}' to {len(models)} models")
        
        for model in models:
            model.source = source
            model.metadata["data_source"] = source
            model.metadata["source_timestamp"] = datetime.now(timezone.utc).isoformat()
            
            # Calculate priority score based on source
            model.priority_score = self._calculate_priority_score(model, source)
        
        return models
    
    def prioritize_models(self, models: List[ModelReference]) -> List[ModelReference]:
        """
        Apply prioritization logic for merged dataset.
        
        Args:
            models: List of models to prioritize
            
        Returns:
            List of models sorted by priority
        """
        logger.info(f"📊 Applying prioritization to {len(models)} models...")
        
        # Sort models by priority score (highest first)
        prioritized = sorted(models, key=lambda m: m.priority_score, reverse=True)
        
        # Log priority distribution
        priority_distribution = defaultdict(int)
        for model in prioritized:
            priority_range = f"{model.priority_score:.1f}"
            priority_distribution[priority_range] += 1
        
        logger.info(f"📈 Priority distribution:")
        for priority_range, count in sorted(priority_distribution.items(), reverse=True):
            logger.info(f"   • Priority {priority_range}: {count} models")
        
        return prioritized
    
    def _normalize_recent_models(self, recent_models: List) -> List[ModelReference]:
        """
        Normalize recent models to unified ModelReference format.
        
        Args:
            recent_models: Raw recent models from DateFilteredExtractor
            
        Returns:
            List of normalized ModelReference objects
        """
        normalized = []
        
        for model in recent_models:
            # Handle different input formats
            if hasattr(model, 'id'):
                # Already a ModelReference-like object
                normalized_model = ModelReference(
                    id=model.id,
                    discovery_method=getattr(model, 'discovery_method', 'date_filtered'),
                    confidence_score=getattr(model, 'confidence_score', 1.0),
                    metadata=getattr(model, 'metadata', {}).copy(),
                    upload_date=getattr(model, 'upload_date', None),
                    download_count=getattr(model, 'metadata', {}).get('downloads', 0)
                )
            elif isinstance(model, dict):
                # Dictionary format
                normalized_model = ModelReference(
                    id=model['id'],
                    discovery_method=model.get('discovery_method', 'date_filtered'),
                    confidence_score=model.get('confidence_score', 1.0),
                    metadata=model.get('metadata', {}).copy(),
                    upload_date=model.get('upload_date'),
                    download_count=model.get('metadata', {}).get('downloads', 0)
                )
            else:
                logger.warning(f"⚠️ Unknown recent model format: {type(model)}")
                continue
            
            normalized.append(normalized_model)
        
        return normalized
    
    def _normalize_top_models(self, top_models: List) -> List[ModelReference]:
        """
        Normalize top models to unified ModelReference format.
        
        Args:
            top_models: Raw top models from TopModelsManager
            
        Returns:
            List of normalized ModelReference objects
        """
        normalized = []
        
        for model in top_models:
            # Handle different input formats
            if hasattr(model, 'id'):
                # Already a ModelReference-like object
                normalized_model = ModelReference(
                    id=model.id,
                    discovery_method=getattr(model, 'discovery_method', 'top_models'),
                    confidence_score=getattr(model, 'confidence_score', 1.0),
                    metadata=getattr(model, 'metadata', {}).copy(),
                    download_count=getattr(model, 'download_count', 0),
                    rank=getattr(model, 'rank', None)
                )
            elif isinstance(model, dict):
                # Dictionary format
                normalized_model = ModelReference(
                    id=model['id'],
                    discovery_method=model.get('discovery_method', 'top_models'),
                    confidence_score=model.get('confidence_score', 1.0),
                    metadata=model.get('metadata', {}).copy(),
                    download_count=model.get('download_count', 0),
                    rank=model.get('rank')
                )
            else:
                logger.warning(f"⚠️ Unknown top model format: {type(model)}")
                continue
            
            normalized.append(normalized_model)
        
        return normalized
    
    def _calculate_priority_score(self, model: ModelReference, source: str) -> float:
        """
        Calculate priority score for a model based on source and characteristics.
        
        Args:
            model: Model to calculate priority for
            source: Source of the model ('recent', 'top', etc.)
            
        Returns:
            float: Priority score (higher = higher priority)
        """
        base_priority = self.priority_weights.get(source, 0.5)
        
        # Adjust priority based on model characteristics
        priority_adjustments = 0.0
        
        # Higher download count increases priority
        if model.download_count > 0:
            # Logarithmic scaling for download count
            import math
            download_bonus = min(0.2, math.log10(model.download_count + 1) / 10)
            priority_adjustments += download_bonus
        
        # Higher confidence score increases priority
        confidence_bonus = (model.confidence_score - 0.5) * 0.1
        priority_adjustments += confidence_bonus
        
        # Top-ranked models get additional priority
        if model.rank and model.rank <= 10:
            rank_bonus = (11 - model.rank) * 0.01  # Top 10 get 0.01-0.10 bonus
            priority_adjustments += rank_bonus
        
        final_priority = base_priority + priority_adjustments
        
        logger.debug(f"🎯 Priority for {model.id}: {final_priority:.3f} "
                    f"(base: {base_priority}, adjustments: {priority_adjustments:+.3f})")
        
        return final_priority
    
    def _merge_model_metadata(self, model_group: List[ModelReference]) -> Dict[str, Any]:
        """
        Merge metadata from multiple versions of the same model.
        
        Args:
            model_group: List of ModelReference objects for the same model ID
            
        Returns:
            Dict containing merged metadata
        """
        merged_metadata = {}
        
        # Collect all metadata keys
        all_keys = set()
        for model in model_group:
            all_keys.update(model.metadata.keys())
        
        # Merge metadata with conflict resolution
        for key in all_keys:
            values = []
            for model in model_group:
                if key in model.metadata and model.metadata[key] is not None:
                    values.append(model.metadata[key])
            
            if not values:
                continue
            
            # Conflict resolution strategy
            if key in ['downloads', 'download_count']:
                # Use maximum download count
                merged_metadata[key] = max(values) if values else 0
            elif key in ['created_at', 'upload_date']:
                # Use earliest creation date
                merged_metadata[key] = min(values) if values else None
            elif key == 'tags':
                # Merge and deduplicate tags
                all_tags = set()
                for tag_list in values:
                    if isinstance(tag_list, list):
                        all_tags.update(tag_list)
                merged_metadata[key] = list(all_tags)
            else:
                # Use value from highest priority source
                merged_metadata[key] = values[0]  # First value (from highest priority model)
        
        return merged_metadata
    
    def _validate_data_integrity(self, models: List[ModelReference]) -> float:
        """
        Validate data integrity and return integrity score.
        
        Args:
            models: List of models to validate
            
        Returns:
            float: Data integrity score (0.0 to 1.0)
        """
        if not models:
            return 1.0  # Empty dataset is technically valid
        
        logger.info(f"🔍 Validating data integrity for {len(models)} models...")
        
        total_checks = 0
        passed_checks = 0
        
        for model in models:
            # Check 1: Model ID is valid
            total_checks += 1
            if model.id and isinstance(model.id, str) and len(model.id.strip()) > 0:
                passed_checks += 1
            
            # Check 2: Source is valid
            total_checks += 1
            if model.source in ['recent', 'top', 'merged']:
                passed_checks += 1
            
            # Check 3: Priority score is reasonable
            total_checks += 1
            if 0.0 <= model.priority_score <= 2.0:
                passed_checks += 1
            
            # Check 4: Metadata is valid
            total_checks += 1
            if isinstance(model.metadata, dict):
                passed_checks += 1
            
            # Check 5: Download count is non-negative
            total_checks += 1
            if model.download_count >= 0:
                passed_checks += 1
        
        integrity_score = passed_checks / total_checks if total_checks > 0 else 1.0
        
        logger.info(f"📊 Data integrity validation:")
        logger.info(f"   • Total checks: {total_checks}")
        logger.info(f"   • Passed checks: {passed_checks}")
        logger.info(f"   • Integrity score: {integrity_score:.2f}")
        
        if integrity_score < 0.9:
            logger.warning(f"⚠️ Low data integrity score: {integrity_score:.2f}")
        
        return integrity_score
    
    def _generate_merge_statistics(self, recent_models: List, top_models: List, 
                                 merged_models: List[ModelReference], 
                                 duplicates_removed: int) -> Dict[str, Any]:
        """
        Generate comprehensive merge statistics.
        
        Args:
            recent_models: Original recent models
            top_models: Original top models
            merged_models: Final merged models
            duplicates_removed: Number of duplicates removed
            
        Returns:
            Dict containing detailed merge statistics
        """
        # Source distribution
        source_distribution = defaultdict(int)
        for model in merged_models:
            source_distribution[model.source] += 1
        
        # Priority distribution
        priority_ranges = {
            'high': 0,    # > 1.0
            'medium': 0,  # 0.5 - 1.0
            'low': 0      # < 0.5
        }
        
        for model in merged_models:
            if model.priority_score > 1.0:
                priority_ranges['high'] += 1
            elif model.priority_score >= 0.5:
                priority_ranges['medium'] += 1
            else:
                priority_ranges['low'] += 1
        
        # Download count statistics
        download_counts = [m.download_count for m in merged_models if m.download_count > 0]
        download_stats = {}
        if download_counts:
            download_stats = {
                'min': min(download_counts),
                'max': max(download_counts),
                'avg': sum(download_counts) / len(download_counts),
                'total_models_with_downloads': len(download_counts)
            }
        
        return {
            'input_statistics': {
                'recent_models_input': len(recent_models) if recent_models else 0,
                'top_models_input': len(top_models) if top_models else 0,
                'total_input': (len(recent_models) if recent_models else 0) + 
                              (len(top_models) if top_models else 0)
            },
            'merge_statistics': {
                'total_merged': len(merged_models),
                'duplicates_removed': duplicates_removed,
                'deduplication_rate': duplicates_removed / (len(merged_models) + duplicates_removed) 
                                    if (len(merged_models) + duplicates_removed) > 0 else 0
            },
            'source_distribution': dict(source_distribution),
            'priority_distribution': priority_ranges,
            'download_statistics': download_stats,
            'merge_timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def merge_with_error_handling(self, recent_models: List, top_models: List, 
                                error_recovery_system=None) -> MergeResult:
        """
        Merge datasets with comprehensive error handling.
        
        Args:
            recent_models: List of recent models
            top_models: List of top models
            error_recovery_system: Optional error recovery system
            
        Returns:
            MergeResult with error handling
        """
        if error_recovery_system:
            return with_error_handling(
                lambda: self.merge_datasets(recent_models, top_models),
                "data_merge",
                error_recovery_system,
                model_id="data_merger"
            )
        else:
            return self.merge_datasets(recent_models, top_models)
    
    def get_merge_configuration(self) -> Dict[str, Any]:
        """
        Get current merge configuration and settings.
        
        Returns:
            Dict containing merge configuration
        """
        return {
            "priority_weights": self.priority_weights,
            "recent_models_priority": self.retention_config.recent_models_priority,
            "merger_type": "DataMerger",
            "deduplication_strategy": "priority_based",
            "metadata_merge_strategy": "conflict_resolution",
            "integrity_validation": "enabled"
        }