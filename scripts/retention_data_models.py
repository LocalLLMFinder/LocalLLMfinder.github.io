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


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects by converting them to ISO format strings."""
    
    def default(self, obj):
        """Override default method to handle datetime objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


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
        """Convert ModelRetentionMetadata to dictionary for JSON serialization."""
        result = asdict(self)
        
        # Convert datetime objects to ISO strings
        if isinstance(result.get('first_seen'), datetime):
            result['first_seen'] = result['first_seen'].isoformat()
        if isinstance(result.get('last_updated'), datetime):
            result['last_updated'] = result['last_updated'].isoformat()
        
        return result
    
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
        """Save model retention metadata to JSON file with comprehensive error handling."""
        try:
            logger.debug(f"Starting save_metadata for {len(metadata_list)} records")
            
            # Validate input
            if not isinstance(metadata_list, list):
                raise TypeError(f"Expected list of ModelRetentionMetadata, got {type(metadata_list)}")
            
            # Convert to dict with individual error handling
            data = []
            failed_conversions = []
            
            for i, item in enumerate(metadata_list):
                try:
                    if not isinstance(item, ModelRetentionMetadata):
                        raise TypeError(f"Item {i} is not ModelRetentionMetadata: {type(item)}")
                    
                    item_dict = item.to_dict()
                    data.append(item_dict)
                    
                except Exception as convert_error:
                    logger.warning(f"Failed to convert metadata item {i} (model_id: {getattr(item, 'model_id', 'unknown')}): {convert_error}")
                    failed_conversions.append((i, str(convert_error)))
            
            if failed_conversions:
                logger.warning(f"Failed to convert {len(failed_conversions)} metadata items out of {len(metadata_list)}")
                for idx, error in failed_conversions:
                    logger.warning(f"  Item {idx}: {error}")
            
            if not data:
                raise ValueError("No valid metadata items to save after conversion")
            
            # Save with error handling
            self._save_json(self.metadata_file, data)
            logger.info(f"Successfully saved {len(data)} metadata records ({len(failed_conversions)} failed)")
            
        except (TypeError, ValueError) as e:
            logger.error(f"Data validation error in save_metadata: {e}")
            logger.error(f"Input type: {type(metadata_list)}, Length: {len(metadata_list) if hasattr(metadata_list, '__len__') else 'N/A'}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in save_metadata: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            raise RuntimeError(f"Metadata save failed: {e}")
    
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
        """Save top model rankings to JSON file with comprehensive error handling."""
        try:
            logger.debug(f"Starting save_rankings for {len(rankings_list)} records")
            
            # Validate input
            if not isinstance(rankings_list, list):
                raise TypeError(f"Expected list of TopModelRanking, got {type(rankings_list)}")
            
            # Convert to dict with individual error handling
            data = []
            failed_conversions = []
            
            for i, item in enumerate(rankings_list):
                try:
                    if not isinstance(item, TopModelRanking):
                        raise TypeError(f"Item {i} is not TopModelRanking: {type(item)}")
                    
                    item_dict = item.to_dict()
                    data.append(item_dict)
                    
                except Exception as convert_error:
                    logger.warning(f"Failed to convert ranking item {i} (model_id: {getattr(item, 'model_id', 'unknown')}, rank: {getattr(item, 'rank', 'unknown')}): {convert_error}")
                    failed_conversions.append((i, str(convert_error)))
            
            if failed_conversions:
                logger.warning(f"Failed to convert {len(failed_conversions)} ranking items out of {len(rankings_list)}")
                for idx, error in failed_conversions:
                    logger.warning(f"  Item {idx}: {error}")
            
            if not data:
                raise ValueError("No valid ranking items to save after conversion")
            
            # Save with error handling
            self._save_json(self.rankings_file, data)
            logger.info(f"Successfully saved {len(data)} ranking records ({len(failed_conversions)} failed)")
            
        except (TypeError, ValueError) as e:
            logger.error(f"Data validation error in save_rankings: {e}")
            logger.error(f"Input type: {type(rankings_list)}, Length: {len(rankings_list) if hasattr(rankings_list, '__len__') else 'N/A'}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in save_rankings: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            raise RuntimeError(f"Rankings save failed: {e}")
    
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
        """Save update report to JSON file (append to list) with comprehensive error handling."""
        try:
            # Validate report before processing
            if not isinstance(report, UpdateReport):
                raise TypeError(f"Expected UpdateReport instance, got {type(report)}")
            
            logger.debug(f"Starting save_report for report with timestamp: {report.timestamp}")
            
            # Load existing reports with error handling
            try:
                reports = self._load_json(self.reports_file, [])
                logger.debug(f"Loaded {len(reports)} existing reports")
            except Exception as load_error:
                logger.warning(f"Failed to load existing reports, starting with empty list: {load_error}")
                reports = []
            
            # Convert report to dict with error handling
            try:
                report_dict = report.to_dict()
                logger.debug(f"Successfully converted report to dict with keys: {list(report_dict.keys())}")
            except Exception as convert_error:
                logger.error(f"Failed to convert report to dict: {convert_error}")
                logger.error(f"Report object: {report}")
                raise RuntimeError(f"Report serialization failed during to_dict(): {convert_error}")
            
            # Add new report
            reports.append(report_dict)
            
            # Keep only last 100 reports to prevent file from growing too large
            if len(reports) > 100:
                reports = reports[-100:]
                logger.debug(f"Trimmed reports list to last 100 entries")
            
            # Save with comprehensive error handling
            try:
                self._save_json(self.reports_file, reports)
                logger.info(f"Successfully saved update report (total reports: {len(reports)})")
            except Exception as save_error:
                logger.error(f"Failed to save reports to {self.reports_file}: {save_error}")
                
                # Attempt to save just the current report as backup
                try:
                    backup_file = self.reports_file.with_suffix('.single_report_backup.json')
                    self._save_json(backup_file, [report_dict])
                    logger.warning(f"Saved current report as backup to {backup_file}")
                except Exception as backup_error:
                    logger.error(f"Failed to save report backup: {backup_error}")
                
                raise RuntimeError(f"Report save failed: {save_error}")
                
        except TypeError as e:
            logger.error(f"Type error in save_report: {e}")
            logger.error(f"Report type: {type(report)}, Report value: {report}")
            raise
        except ValueError as e:
            logger.error(f"Value error in save_report: {e}")
            logger.error(f"Report validation may have failed: {report}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in save_report: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Report details: timestamp={getattr(report, 'timestamp', 'N/A')}, "
                        f"success={getattr(report, 'success', 'N/A')}")
            raise RuntimeError(f"Unexpected error during report save: {e}")
    
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
        """Save data to JSON file with atomic write using custom DateTimeEncoder and comprehensive error handling."""
        temp_file = file_path.with_suffix('.tmp')
        
        try:
            # Primary serialization attempt with custom encoder
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, cls=DateTimeEncoder)
            
            # Atomic move
            temp_file.replace(file_path)
            logger.debug(f"Successfully saved JSON data to {file_path}")
            
        except (TypeError, ValueError) as e:
            # Handle JSON serialization errors specifically
            logger.error(f"JSON serialization error for {file_path}: {e}")
            logger.error(f"Data type causing error: {type(data)}")
            
            # Clean up temp file
            if temp_file.exists():
                temp_file.unlink()
            
            # Attempt fallback serialization
            try:
                logger.info(f"Attempting fallback serialization for {file_path}")
                self._fallback_save_json(file_path, data)
                logger.warning(f"Fallback serialization succeeded for {file_path}")
            except Exception as fallback_error:
                logger.error(f"Fallback serialization also failed for {file_path}: {fallback_error}")
                raise RuntimeError(f"Both primary and fallback serialization failed for {file_path}. "
                                 f"Primary error: {e}, Fallback error: {fallback_error}")
        
        except (IOError, OSError, PermissionError) as e:
            # Handle file system errors
            logger.error(f"File system error while saving {file_path}: {e}")
            
            # Clean up temp file
            if temp_file.exists():
                temp_file.unlink()
            
            # Try alternative temp file location
            try:
                logger.info(f"Attempting save with alternative temp file for {file_path}")
                alt_temp_file = file_path.with_suffix(f'.tmp_{os.getpid()}')
                with open(alt_temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, cls=DateTimeEncoder)
                alt_temp_file.replace(file_path)
                logger.warning(f"Alternative temp file save succeeded for {file_path}")
            except Exception as alt_error:
                logger.error(f"Alternative temp file save also failed for {file_path}: {alt_error}")
                raise RuntimeError(f"File system error persists for {file_path}. "
                                 f"Original error: {e}, Alternative error: {alt_error}")
        
        except Exception as e:
            # Handle any other unexpected errors
            logger.error(f"Unexpected error while saving {file_path}: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            
            # Clean up temp file
            if temp_file.exists():
                temp_file.unlink()
            
            raise RuntimeError(f"Unexpected error during JSON save for {file_path}: {e}")
    
    def _fallback_save_json(self, file_path: Path, data: Any) -> None:
        """Fallback serialization mechanism that converts problematic objects to strings."""
        logger.info(f"Starting fallback serialization for {file_path}")
        
        try:
            # Convert data to a more serializable format
            serializable_data = self._make_serializable(data)
            
            temp_file = file_path.with_suffix('.fallback_tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(serializable_data, f, indent=2, ensure_ascii=False, default=str)
            
            # Atomic move
            temp_file.replace(file_path)
            logger.info(f"Fallback serialization completed for {file_path}")
            
        except Exception as e:
            # Clean up fallback temp file
            fallback_temp = file_path.with_suffix('.fallback_tmp')
            if fallback_temp.exists():
                fallback_temp.unlink()
            
            logger.error(f"Fallback serialization failed for {file_path}: {e}")
            raise
    
    def _make_serializable(self, obj: Any) -> Any:
        """Convert objects to JSON-serializable format with detailed logging."""
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        
        elif isinstance(obj, datetime):
            logger.debug(f"Converting datetime object: {obj}")
            return obj.isoformat()
        
        elif isinstance(obj, dict):
            logger.debug(f"Processing dictionary with {len(obj)} keys")
            result = {}
            for key, value in obj.items():
                try:
                    result[str(key)] = self._make_serializable(value)
                except Exception as e:
                    logger.warning(f"Failed to serialize dict key '{key}': {e}, converting to string")
                    result[str(key)] = str(value)
            return result
        
        elif isinstance(obj, (list, tuple)):
            logger.debug(f"Processing {type(obj).__name__} with {len(obj)} items")
            result = []
            for i, item in enumerate(obj):
                try:
                    result.append(self._make_serializable(item))
                except Exception as e:
                    logger.warning(f"Failed to serialize {type(obj).__name__} item {i}: {e}, converting to string")
                    result.append(str(item))
            return result
        
        elif hasattr(obj, 'to_dict'):
            logger.debug(f"Using to_dict() method for {type(obj).__name__}")
            try:
                return self._make_serializable(obj.to_dict())
            except Exception as e:
                logger.warning(f"to_dict() method failed for {type(obj).__name__}: {e}, converting to string")
                return str(obj)
        
        elif hasattr(obj, '__dict__'):
            logger.debug(f"Using __dict__ for {type(obj).__name__}")
            try:
                return self._make_serializable(obj.__dict__)
            except Exception as e:
                logger.warning(f"__dict__ serialization failed for {type(obj).__name__}: {e}, converting to string")
                return str(obj)
        
        else:
            logger.debug(f"Converting {type(obj).__name__} to string")
            return str(obj)
    
    def _load_json(self, file_path: Path, default: Any = None) -> Any:
        """Load data from JSON file with comprehensive error handling."""
        if not file_path.exists():
            logger.debug(f"File {file_path} does not exist, returning default value")
            return default
        
        try:
            logger.debug(f"Loading JSON data from {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.debug(f"Successfully loaded JSON data from {file_path} (type: {type(data)})")
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in {file_path}: {e}")
            logger.error(f"Error at line {e.lineno}, column {e.colno}: {e.msg}")
            
            # Try to read file content for debugging
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                logger.error(f"File content length: {len(content)} characters")
                if len(content) < 1000:  # Only log small files
                    logger.error(f"File content: {content}")
                else:
                    logger.error(f"File content (first 500 chars): {content[:500]}...")
            except Exception as read_error:
                logger.error(f"Could not read file content for debugging: {read_error}")
            
            logger.warning(f"Using default value due to JSON decode error")
            return default
            
        except (IOError, OSError, PermissionError) as e:
            logger.error(f"File system error loading {file_path}: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            
            # Check file permissions and size
            try:
                stat = file_path.stat()
                logger.error(f"File size: {stat.st_size} bytes, mode: {oct(stat.st_mode)}")
            except Exception as stat_error:
                logger.error(f"Could not get file stats: {stat_error}")
            
            logger.warning(f"Using default value due to file system error")
            return default
            
        except UnicodeDecodeError as e:
            logger.error(f"Unicode decode error in {file_path}: {e}")
            logger.error(f"Error at position {e.start}-{e.end}: {e.reason}")
            
            # Try different encodings
            for encoding in ['latin-1', 'cp1252', 'utf-16']:
                try:
                    logger.info(f"Attempting to read {file_path} with {encoding} encoding")
                    with open(file_path, 'r', encoding=encoding) as f:
                        data = json.load(f)
                    logger.warning(f"Successfully loaded {file_path} using {encoding} encoding")
                    return data
                except Exception as encoding_error:
                    logger.debug(f"Failed to load with {encoding}: {encoding_error}")
            
            logger.warning(f"All encoding attempts failed, using default value")
            return default
            
        except Exception as e:
            logger.error(f"Unexpected error loading {file_path}: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.warning(f"Using default value due to unexpected error")
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