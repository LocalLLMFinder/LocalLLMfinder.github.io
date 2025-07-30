"""
Data models and storage schemas for the dynamic model retention system.

This module provides dataclasses for model retention metadata, top model rankings,
and update reports, along with JSON serialization/deserialization capabilities
and data validation.
"""

import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Union
from pathlib import Path
import os

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
    
    def __post_init__(self):
        """Validate data after initialization."""
        self._validate()
    
    def _validate(self):
        """Validate model retention metadata."""
        if not self.model_id or not isinstance(self.model_id, str):
            raise ValueError("model_id must be a non-empty string")
        
        if self.source not in ['recent', 'top']:
            raise ValueError("source must be 'recent' or 'top'")
        
        if self.retention_reason not in ['recent', 'top_20', 'high_downloads']:
            raise ValueError("retention_reason must be 'recent', 'top_20', or 'high_downloads'")
        
        if not isinstance(self.download_count, int) or self.download_count < 0:
            raise ValueError("download_count must be a non-negative integer")
        
        if not isinstance(self.cleanup_eligible, bool):
            raise ValueError("cleanup_eligible must be a boolean")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with ISO format dates."""
        data = asdict(self)
        data['first_seen'] = self.first_seen.isoformat()
        data['last_updated'] = self.last_updated.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModelRetentionMetadata':
        """Create instance from dictionary with date parsing."""
        data = data.copy()
        data['first_seen'] = datetime.fromisoformat(data['first_seen'])
        data['last_updated'] = datetime.fromisoformat(data['last_updated'])
        return cls(**data)


@dataclass
class TopModelRanking:
    """Top model ranking with historical data."""
    model_id: str
    rank: int
    download_count: int
    previous_rank: Optional[int] = None
    rank_change: int = 0  # positive = moved up, negative = moved down
    days_in_top: int = 1
    first_top_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __post_init__(self):
        """Validate data after initialization."""
        self._validate()
    
    def _validate(self):
        """Validate top model ranking data."""
        if not self.model_id or not isinstance(self.model_id, str):
            raise ValueError("model_id must be a non-empty string")
        
        if not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError("rank must be a positive integer")
        
        if not isinstance(self.download_count, int) or self.download_count < 0:
            raise ValueError("download_count must be a non-negative integer")
        
        if self.previous_rank is not None and (not isinstance(self.previous_rank, int) or self.previous_rank < 1):
            raise ValueError("previous_rank must be None or a positive integer")
        
        if not isinstance(self.rank_change, int):
            raise ValueError("rank_change must be an integer")
        
        if not isinstance(self.days_in_top, int) or self.days_in_top < 1:
            raise ValueError("days_in_top must be a positive integer")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with ISO format dates."""
        data = asdict(self)
        data['first_top_date'] = self.first_top_date.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TopModelRanking':
        """Create instance from dictionary with date parsing."""
        data = data.copy()
        data['first_top_date'] = datetime.fromisoformat(data['first_top_date'])
        return cls(**data)


@dataclass
class UpdateReport:
    """Comprehensive update report."""
    timestamp: datetime
    duration_seconds: float
    recent_models_fetched: int
    top_models_updated: int
    models_merged: int
    duplicates_removed: int
    models_cleaned_up: int
    storage_freed_mb: float
    api_calls_made: int
    errors_encountered: List[str]
    success: bool
    
    def __post_init__(self):
        """Validate data after initialization."""
        self._validate()
    
    def _validate(self):
        """Validate update report data."""
        if not isinstance(self.duration_seconds, (int, float)) or self.duration_seconds < 0:
            raise ValueError("duration_seconds must be a non-negative number")
        
        integer_fields = [
            'recent_models_fetched', 'top_models_updated', 'models_merged',
            'duplicates_removed', 'models_cleaned_up', 'api_calls_made'
        ]
        
        for field_name in integer_fields:
            value = getattr(self, field_name)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        
        if not isinstance(self.storage_freed_mb, (int, float)) or self.storage_freed_mb < 0:
            raise ValueError("storage_freed_mb must be a non-negative number")
        
        if not isinstance(self.errors_encountered, list):
            raise ValueError("errors_encountered must be a list")
        
        if not isinstance(self.success, bool):
            raise ValueError("success must be a boolean")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with ISO format dates."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UpdateReport':
        """Create instance from dictionary with date parsing."""
        data = data.copy()
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class RetentionDataStorage:
    """Storage manager for retention data models with JSON serialization."""
    
    def __init__(self, base_path: str = "data"):
        """Initialize storage with base path."""
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)
        
        # Define storage file paths
        self.metadata_file = self.base_path / "model_retention_metadata.json"
        self.rankings_file = self.base_path / "top_model_rankings.json"
        self.reports_file = self.base_path / "update_reports.json"
    
    def save_metadata(self, metadata_list: List[ModelRetentionMetadata]) -> None:
        """Save model retention metadata to JSON file."""
        try:
            data = [item.to_dict() for item in metadata_list]
            self._save_json(self.metadata_file, data)
            logger.info(f"Saved {len(metadata_list)} metadata records")
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
            raise
    
    def load_metadata(self) -> List[ModelRetentionMetadata]:
        """Load model retention metadata from JSON file."""
        try:
            data = self._load_json(self.metadata_file, [])
            metadata_list = [ModelRetentionMetadata.from_dict(item) for item in data]
            logger.info(f"Loaded {len(metadata_list)} metadata records")
            return metadata_list
        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
            return []
    
    def save_rankings(self, rankings_list: List[TopModelRanking]) -> None:
        """Save top model rankings to JSON file."""
        try:
            data = [item.to_dict() for item in rankings_list]
            self._save_json(self.rankings_file, data)
            logger.info(f"Saved {len(rankings_list)} ranking records")
        except Exception as e:
            logger.error(f"Failed to save rankings: {e}")
            raise
    
    def load_rankings(self) -> List[TopModelRanking]:
        """Load top model rankings from JSON file."""
        try:
            data = self._load_json(self.rankings_file, [])
            rankings_list = [TopModelRanking.from_dict(item) for item in data]
            logger.info(f"Loaded {len(rankings_list)} ranking records")
            return rankings_list
        except Exception as e:
            logger.error(f"Failed to load rankings: {e}")
            return []
    
    def save_report(self, report: UpdateReport) -> None:
        """Save update report to JSON file (append to list)."""
        try:
            # Load existing reports
            reports = self._load_json(self.reports_file, [])
            
            # Add new report
            reports.append(report.to_dict())
            
            # Keep only last 100 reports to prevent file from growing too large
            if len(reports) > 100:
                reports = reports[-100:]
            
            self._save_json(self.reports_file, reports)
            logger.info("Saved update report")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
            raise
    
    def load_reports(self, limit: Optional[int] = None) -> List[UpdateReport]:
        """Load update reports from JSON file."""
        try:
            data = self._load_json(self.reports_file, [])
            reports_list = [UpdateReport.from_dict(item) for item in data]
            
            if limit:
                reports_list = reports_list[-limit:]
            
            logger.info(f"Loaded {len(reports_list)} report records")
            return reports_list
        except Exception as e:
            logger.error(f"Failed to load reports: {e}")
            return []
    
    def _save_json(self, file_path: Path, data: Any) -> None:
        """Save data to JSON file with atomic write."""
        temp_file = file_path.with_suffix('.tmp')
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Atomic move
            temp_file.replace(file_path)
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            raise e
    
    def _load_json(self, file_path: Path, default: Any = None) -> Any:
        """Load data from JSON file with error handling."""
        if not file_path.exists():
            return default
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load {file_path}: {e}, using default")
            return default
    
    def validate_storage_integrity(self) -> Dict[str, bool]:
        """Validate integrity of all stored data."""
        results = {}
        
        # Validate metadata
        try:
            metadata = self.load_metadata()
            results['metadata'] = True
            logger.info(f"Metadata validation passed: {len(metadata)} records")
        except Exception as e:
            results['metadata'] = False
            logger.error(f"Metadata validation failed: {e}")
        
        # Validate rankings
        try:
            rankings = self.load_rankings()
            results['rankings'] = True
            logger.info(f"Rankings validation passed: {len(rankings)} records")
        except Exception as e:
            results['rankings'] = False
            logger.error(f"Rankings validation failed: {e}")
        
        # Validate reports
        try:
            reports = self.load_reports()
            results['reports'] = True
            logger.info(f"Reports validation passed: {len(reports)} records")
        except Exception as e:
            results['reports'] = False
            logger.error(f"Reports validation failed: {e}")
        
        return results


class DataMigrationManager:
    """Manager for migrating existing data to new schema format."""
    
    def __init__(self, storage: RetentionDataStorage):
        """Initialize with storage instance."""
        self.storage = storage
    
    def migrate_legacy_data(self, legacy_data_path: str) -> bool:
        """Migrate legacy data to new schema format."""
        try:
            legacy_path = Path(legacy_data_path)
            if not legacy_path.exists():
                logger.info("No legacy data found, skipping migration")
                return True
            
            logger.info(f"Starting migration from {legacy_data_path}")
            
            # Load legacy data (assuming it's a simple JSON format)
            with open(legacy_path, 'r', encoding='utf-8') as f:
                legacy_data = json.load(f)
            
            # Convert to new format
            migrated_metadata = self._convert_legacy_to_metadata(legacy_data)
            
            # Save in new format
            if migrated_metadata:
                self.storage.save_metadata(migrated_metadata)
                logger.info(f"Successfully migrated {len(migrated_metadata)} records")
            
            # Create backup of legacy data
            backup_path = legacy_path.with_suffix('.backup')
            legacy_path.rename(backup_path)
            logger.info(f"Legacy data backed up to {backup_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False
    
    def _convert_legacy_to_metadata(self, legacy_data: Any) -> List[ModelRetentionMetadata]:
        """Convert legacy data format to ModelRetentionMetadata."""
        metadata_list = []
        current_time = datetime.now(timezone.utc)
        
        try:
            # Handle different legacy data formats
            if isinstance(legacy_data, list):
                for item in legacy_data:
                    if isinstance(item, dict) and 'id' in item:
                        metadata = ModelRetentionMetadata(
                            model_id=item['id'],
                            first_seen=current_time,
                            last_updated=current_time,
                            source='recent',  # Default assumption
                            download_count=item.get('downloads', 0),
                            retention_reason='recent',
                            cleanup_eligible=True
                        )
                        metadata_list.append(metadata)
            
            elif isinstance(legacy_data, dict):
                for model_id, model_data in legacy_data.items():
                    if isinstance(model_data, dict):
                        metadata = ModelRetentionMetadata(
                            model_id=model_id,
                            first_seen=current_time,
                            last_updated=current_time,
                            source='recent',
                            download_count=model_data.get('downloads', 0),
                            retention_reason='recent',
                            cleanup_eligible=True
                        )
                        metadata_list.append(metadata)
            
            logger.info(f"Converted {len(metadata_list)} legacy records")
            return metadata_list
            
        except Exception as e:
            logger.error(f"Failed to convert legacy data: {e}")
            return []
    
    def create_schema_backup(self) -> str:
        """Create backup of current schema data."""
        try:
            backup_dir = self.storage.base_path / "backups"
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"schema_backup_{timestamp}"
            backup_path.mkdir(exist_ok=True)
            
            # Copy current data files
            for file_path in [self.storage.metadata_file, self.storage.rankings_file, self.storage.reports_file]:
                if file_path.exists():
                    backup_file = backup_path / file_path.name
                    backup_file.write_text(file_path.read_text(encoding='utf-8'), encoding='utf-8')
            
            logger.info(f"Schema backup created at {backup_path}")
            return str(backup_path)
            
        except Exception as e:
            logger.error(f"Failed to create schema backup: {e}")
            raise


# Utility functions for data validation and schema checking
def validate_model_data(data: Dict[str, Any], model_class) -> bool:
    """Validate data against a model class schema."""
    try:
        model_class.from_dict(data)
        return True
    except (ValueError, TypeError, KeyError) as e:
        logger.warning(f"Data validation failed for {model_class.__name__}: {e}")
        return False


def get_schema_version() -> str:
    """Get current schema version."""
    return "1.0.0"


def check_schema_compatibility(data_version: str) -> bool:
    """Check if data version is compatible with current schema."""
    current_version = get_schema_version()
    # Simple version check - in production, implement proper semver comparison
    return data_version == current_version