#!/usr/bin/env python3
"""
Data Freshness Tracking System

This module provides comprehensive data freshness tracking and user-facing indicators
for the GGUF Model Discovery system. It tracks sync timestamps, model modification
times, and provides freshness guarantees.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)

class FreshnessStatus(Enum):
    """Enumeration of data freshness statuses."""
    FRESH = "fresh"           # Data is current (< 24 hours)
    STALE = "stale"          # Data is old (24-25 hours)
    VERY_STALE = "very_stale" # Data is very old (> 25 hours)
    UNKNOWN = "unknown"       # Freshness cannot be determined

@dataclass
class FreshnessMetadata:
    """Metadata about data freshness."""
    last_sync_timestamp: datetime
    sync_duration_seconds: float
    total_models_processed: int
    sync_mode: str
    sync_success: bool
    models_with_timestamps: int
    models_without_timestamps: int
    oldest_model_timestamp: Optional[datetime] = None
    newest_model_timestamp: Optional[datetime] = None
    freshness_score: float = 1.0
    staleness_warnings: List[str] = None
    
    def __post_init__(self):
        if self.staleness_warnings is None:
            self.staleness_warnings = []

@dataclass
class ModelFreshnessInfo:
    """Freshness information for individual models."""
    model_id: str
    last_modified: Optional[datetime]
    last_synced: datetime
    freshness_status: FreshnessStatus
    hours_since_modified: Optional[float] = None
    hours_since_synced: float = 0.0
    
    def __post_init__(self):
        # Calculate hours since last sync
        now = datetime.now(timezone.utc)
        self.hours_since_synced = (now - self.last_synced).total_seconds() / 3600
        
        # Calculate hours since last modification if available
        if self.last_modified:
            self.hours_since_modified = (now - self.last_modified).total_seconds() / 3600

class FreshnessTracker:
    """Tracks and manages data freshness for the GGUF model system."""
    
    def __init__(self, metadata_file: str = "data/freshness_metadata.json"):
        self.metadata_file = Path(metadata_file)
        self.current_sync_start = datetime.now(timezone.utc)
        self.model_freshness_info: List[ModelFreshnessInfo] = []
        
    def start_sync_tracking(self) -> None:
        """Start tracking a new sync operation."""
        self.current_sync_start = datetime.now(timezone.utc)
        self.model_freshness_info = []
        logger.info(f"🕐 Started freshness tracking at {self.current_sync_start.isoformat()}")
    
    def track_model_freshness(self, model_data: Dict[str, Any]) -> ModelFreshnessInfo:
        """Track freshness information for a single model."""
        model_id = model_data.get('modelId', model_data.get('id', 'unknown'))
        
        # Parse last modified timestamp
        last_modified = None
        last_modified_str = model_data.get('lastModified')
        if last_modified_str:
            try:
                from dateutil import parser as date_parser
                last_modified = date_parser.parse(last_modified_str)
                if last_modified.tzinfo is None:
                    last_modified = last_modified.replace(tzinfo=timezone.utc)
            except Exception as e:
                logger.debug(f"Could not parse lastModified for {model_id}: {e}")
        
        # Determine freshness status
        freshness_status = self._determine_freshness_status(last_modified)
        
        # Create freshness info
        freshness_info = ModelFreshnessInfo(
            model_id=model_id,
            last_modified=last_modified,
            last_synced=self.current_sync_start,
            freshness_status=freshness_status
        )
        
        self.model_freshness_info.append(freshness_info)
        return freshness_info
    
    def _determine_freshness_status(self, last_modified: Optional[datetime]) -> FreshnessStatus:
        """Determine the freshness status of a model."""
        if not last_modified:
            return FreshnessStatus.UNKNOWN
        
        now = datetime.now(timezone.utc)
        hours_since_modified = (now - last_modified).total_seconds() / 3600
        
        if hours_since_modified <= 24:
            return FreshnessStatus.FRESH
        elif hours_since_modified <= 25:
            return FreshnessStatus.STALE
        else:
            return FreshnessStatus.VERY_STALE
    
    def generate_freshness_metadata(self, sync_duration: float, total_models: int, 
                                  sync_mode: str, sync_success: bool) -> FreshnessMetadata:
        """Generate comprehensive freshness metadata for the sync."""
        logger.info("📊 Generating freshness metadata...")
        
        # Count models with/without timestamps
        models_with_timestamps = sum(1 for info in self.model_freshness_info if info.last_modified)
        models_without_timestamps = len(self.model_freshness_info) - models_with_timestamps
        
        # Find oldest and newest model timestamps
        model_timestamps = [info.last_modified for info in self.model_freshness_info if info.last_modified]
        oldest_timestamp = min(model_timestamps) if model_timestamps else None
        newest_timestamp = max(model_timestamps) if model_timestamps else None
        
        # Calculate freshness score (percentage of models with fresh data)
        fresh_models = sum(1 for info in self.model_freshness_info 
                          if info.freshness_status == FreshnessStatus.FRESH)
        freshness_score = fresh_models / len(self.model_freshness_info) if self.model_freshness_info else 0.0
        
        # Generate staleness warnings
        staleness_warnings = self._generate_staleness_warnings()
        
        metadata = FreshnessMetadata(
            last_sync_timestamp=self.current_sync_start,
            sync_duration_seconds=sync_duration,
            total_models_processed=total_models,
            sync_mode=sync_mode,
            sync_success=sync_success,
            models_with_timestamps=models_with_timestamps,
            models_without_timestamps=models_without_timestamps,
            oldest_model_timestamp=oldest_timestamp,
            newest_model_timestamp=newest_timestamp,
            freshness_score=freshness_score,
            staleness_warnings=staleness_warnings
        )
        
        logger.info(f"✅ Freshness metadata generated:")
        logger.info(f"   • Freshness score: {freshness_score:.1%}")
        logger.info(f"   • Models with timestamps: {models_with_timestamps}/{len(self.model_freshness_info)}")
        logger.info(f"   • Staleness warnings: {len(staleness_warnings)}")
        
        return metadata
    
    def _generate_staleness_warnings(self) -> List[str]:
        """Generate staleness warnings based on current data state."""
        warnings = []
        now = datetime.now(timezone.utc)
        
        # Check overall sync staleness
        hours_since_sync = (now - self.current_sync_start).total_seconds() / 3600
        if hours_since_sync > 25:
            warnings.append(f"Data is {hours_since_sync:.1f} hours old (last sync: {self.current_sync_start.isoformat()})")
        
        # Check for high percentage of stale models
        stale_models = sum(1 for info in self.model_freshness_info 
                          if info.freshness_status in [FreshnessStatus.STALE, FreshnessStatus.VERY_STALE])
        if self.model_freshness_info:
            stale_percentage = stale_models / len(self.model_freshness_info)
            if stale_percentage > 0.1:  # More than 10% stale
                warnings.append(f"{stale_percentage:.1%} of models have stale data")
        
        # Check for models without timestamps
        models_without_timestamps = sum(1 for info in self.model_freshness_info if not info.last_modified)
        if models_without_timestamps > 0:
            percentage = models_without_timestamps / len(self.model_freshness_info) if self.model_freshness_info else 0
            if percentage > 0.05:  # More than 5% without timestamps
                warnings.append(f"{percentage:.1%} of models lack modification timestamps")
        
        return warnings
    
    def add_freshness_to_model_data(self, model_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add freshness information to model data."""
        freshness_info = self.track_model_freshness(model_data)
        
        # Add freshness fields to model data
        enhanced_model_data = model_data.copy()
        enhanced_model_data.update({
            'lastSynced': self.current_sync_start.isoformat(),
            'freshnessStatus': freshness_info.freshness_status.value,
            'hoursSinceModified': freshness_info.hours_since_modified,
            'hoursSinceSynced': freshness_info.hours_since_synced
        })
        
        return enhanced_model_data
    
    def save_freshness_metadata(self, metadata: FreshnessMetadata) -> None:
        """Save freshness metadata to file."""
        try:
            # Ensure directory exists
            self.metadata_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to serializable format
            metadata_dict = asdict(metadata)
            
            # Convert datetime objects to ISO strings
            if metadata_dict['last_sync_timestamp']:
                metadata_dict['last_sync_timestamp'] = metadata.last_sync_timestamp.isoformat()
            if metadata_dict['oldest_model_timestamp']:
                metadata_dict['oldest_model_timestamp'] = metadata.oldest_model_timestamp.isoformat()
            if metadata_dict['newest_model_timestamp']:
                metadata_dict['newest_model_timestamp'] = metadata.newest_model_timestamp.isoformat()
            
            # Save to file
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Freshness metadata saved to {self.metadata_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save freshness metadata: {e}")
    
    def load_previous_freshness_metadata(self) -> Optional[FreshnessMetadata]:
        """Load previous freshness metadata from file."""
        try:
            if not self.metadata_file.exists():
                logger.debug(f"📁 No freshness metadata file found at {self.metadata_file}")
                return None
            
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                metadata_dict = json.load(f)
            
            # Convert ISO strings back to datetime objects
            from dateutil import parser as date_parser
            
            if metadata_dict.get('last_sync_timestamp'):
                metadata_dict['last_sync_timestamp'] = date_parser.parse(metadata_dict['last_sync_timestamp'])
            if metadata_dict.get('oldest_model_timestamp'):
                metadata_dict['oldest_model_timestamp'] = date_parser.parse(metadata_dict['oldest_model_timestamp'])
            if metadata_dict.get('newest_model_timestamp'):
                metadata_dict['newest_model_timestamp'] = date_parser.parse(metadata_dict['newest_model_timestamp'])
            
            # Handle missing fields for backward compatibility
            metadata_dict.setdefault('staleness_warnings', [])
            
            metadata = FreshnessMetadata(**metadata_dict)
            logger.info(f"📖 Loaded freshness metadata: last sync {metadata.last_sync_timestamp.isoformat()}")
            
            return metadata
            
        except Exception as e:
            logger.warning(f"⚠️ Could not load freshness metadata: {e}")
            return None
    
    def get_freshness_summary(self) -> Dict[str, Any]:
        """Get a summary of current freshness status."""
        if not self.model_freshness_info:
            return {
                'total_models': 0,
                'fresh_models': 0,
                'stale_models': 0,
                'very_stale_models': 0,
                'unknown_freshness': 0,
                'freshness_score': 0.0,
                'last_sync': self.current_sync_start.isoformat(),
                'hours_since_sync': 0.0
            }
        
        # Count models by freshness status
        status_counts = {status: 0 for status in FreshnessStatus}
        for info in self.model_freshness_info:
            status_counts[info.freshness_status] += 1
        
        # Calculate hours since sync
        now = datetime.now(timezone.utc)
        hours_since_sync = (now - self.current_sync_start).total_seconds() / 3600
        
        return {
            'total_models': len(self.model_freshness_info),
            'fresh_models': status_counts[FreshnessStatus.FRESH],
            'stale_models': status_counts[FreshnessStatus.STALE],
            'very_stale_models': status_counts[FreshnessStatus.VERY_STALE],
            'unknown_freshness': status_counts[FreshnessStatus.UNKNOWN],
            'freshness_score': status_counts[FreshnessStatus.FRESH] / len(self.model_freshness_info),
            'last_sync': self.current_sync_start.isoformat(),
            'hours_since_sync': hours_since_sync
        }

class WebsiteFreshnessIndicator:
    """Generates freshness indicators for website display."""
    
    @staticmethod
    def generate_freshness_indicator_data(metadata: FreshnessMetadata) -> Dict[str, Any]:
        """Generate data for website freshness indicators."""
        now = datetime.now(timezone.utc)
        hours_since_sync = (now - metadata.last_sync_timestamp).total_seconds() / 3600
        
        # Determine overall freshness status
        if hours_since_sync <= 24:
            overall_status = "fresh"
            status_color = "green"
            status_icon = "✅"
        elif hours_since_sync <= 25:
            overall_status = "stale"
            status_color = "yellow"
            status_icon = "⚠️"
        else:
            overall_status = "very_stale"
            status_color = "red"
            status_icon = "❌"
        
        # Generate user-friendly messages
        if hours_since_sync < 1:
            time_message = "Updated less than 1 hour ago"
        elif hours_since_sync < 24:
            time_message = f"Updated {int(hours_since_sync)} hours ago"
        else:
            days = int(hours_since_sync / 24)
            remaining_hours = int(hours_since_sync % 24)
            if days == 1 and remaining_hours == 0:
                time_message = "Updated 1 day ago"
            elif remaining_hours == 0:
                time_message = f"Updated {days} days ago"
            else:
                time_message = f"Updated {days} day{'s' if days > 1 else ''} and {remaining_hours} hours ago"
        
        return {
            'lastSyncTimestamp': metadata.last_sync_timestamp.isoformat(),
            'lastSyncFormatted': metadata.last_sync_timestamp.strftime('%Y-%m-%d %H:%M UTC'),
            'hoursSinceSync': round(hours_since_sync, 1),
            'overallStatus': overall_status,
            'statusColor': status_color,
            'statusIcon': status_icon,
            'timeMessage': time_message,
            'freshnessScore': round(metadata.freshness_score, 3),
            'totalModels': metadata.total_models_processed,
            'modelsWithTimestamps': metadata.models_with_timestamps,
            'syncDuration': round(metadata.sync_duration_seconds, 1),
            'syncMode': metadata.sync_mode,
            'syncSuccess': metadata.sync_success,
            'stalenessWarnings': metadata.staleness_warnings,
            'showStalenessWarning': hours_since_sync > 25 or len(metadata.staleness_warnings) > 0
        }
    
    @staticmethod
    def save_website_freshness_data(indicator_data: Dict[str, Any], 
                                   output_file: str = "data/freshness_indicators.json") -> None:
        """Save freshness indicator data for website consumption."""
        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(indicator_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Website freshness indicators saved to {output_path}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save website freshness indicators: {e}")

# Convenience function for easy integration
def track_sync_freshness(models_data: List[Dict[str, Any]], sync_duration: float, 
                        sync_mode: str, sync_success: bool = True) -> Dict[str, Any]:
    """
    Convenience function to track freshness for a complete sync operation.
    
    Args:
        models_data: List of model data dictionaries
        sync_duration: Duration of sync in seconds
        sync_mode: Mode of sync (incremental/full)
        sync_success: Whether sync was successful
    
    Returns:
        Dictionary with freshness indicator data for website
    """
    tracker = FreshnessTracker()
    tracker.start_sync_tracking()
    
    # Track freshness for all models and enhance data
    enhanced_models = []
    for model_data in models_data:
        enhanced_model = tracker.add_freshness_to_model_data(model_data)
        enhanced_models.append(enhanced_model)
    
    # Generate and save metadata
    metadata = tracker.generate_freshness_metadata(
        sync_duration=sync_duration,
        total_models=len(models_data),
        sync_mode=sync_mode,
        sync_success=sync_success
    )
    
    tracker.save_freshness_metadata(metadata)
    
    # Generate website indicators
    indicator_data = WebsiteFreshnessIndicator.generate_freshness_indicator_data(metadata)
    WebsiteFreshnessIndicator.save_website_freshness_data(indicator_data)
    
    return {
        'enhanced_models': enhanced_models,
        'freshness_metadata': metadata,
        'website_indicators': indicator_data
    }