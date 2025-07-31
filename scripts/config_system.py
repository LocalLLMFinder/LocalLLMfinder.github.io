#!/usr/bin/env python3
"""
Enhanced Configuration System for GGUF Models Sync

This module provides comprehensive configuration management for all sync parameters,
environment-specific configurations, validation, and deployment support.
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class SyncMode(Enum):
    """Enumeration of sync modes."""
    INCREMENTAL = "incremental"
    FULL = "full"
    AUTO = "auto"

class Environment(Enum):
    """Enumeration of deployment environments."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"

class LogLevel(Enum):
    """Enumeration of log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

@dataclass
class RateLimitConfig:
    """Configuration for API rate limiting."""
    requests_per_second: float = 1.2
    requests_per_hour: int = 5000
    max_concurrent_requests: int = 50
    backoff_base: float = 2.0
    backoff_jitter: bool = True
    max_retries: int = 5
    timeout_seconds: int = 30

@dataclass
class SyncBehaviorConfig:
    """Configuration for sync behavior."""
    mode: SyncMode = SyncMode.AUTO
    incremental_window_hours: int = 48
    full_sync_threshold_hours: int = 168  # Weekly
    significant_change_threshold: float = 0.1
    force_full_sync: bool = False
    enable_multi_strategy_discovery: bool = True
    enable_deduplication: bool = True

@dataclass
class ValidationConfig:
    """Configuration for data validation."""
    enable_schema_validation: bool = True
    enable_file_verification: bool = True
    enable_completeness_checking: bool = True
    min_completeness_score: float = 0.95
    enable_quality_scoring: bool = True
    enable_automatic_fixes: bool = True
    validation_timeout_seconds: int = 300

@dataclass
class ErrorHandlingConfig:
    """Configuration for error handling and recovery."""
    enable_error_recovery: bool = True
    enable_exponential_backoff: bool = True
    enable_categorized_errors: bool = True
    enable_notifications: bool = True
    max_recovery_attempts: int = 3
    recovery_delay_seconds: int = 60
    preserve_data_on_failure: bool = True

@dataclass
class MonitoringConfig:
    """Configuration for monitoring and alerting."""
    enable_detailed_logging: bool = True
    enable_progress_tracking: bool = True
    progress_report_interval_seconds: int = 900  # 15 minutes
    enable_performance_metrics: bool = True
    enable_alerts: bool = True
    alert_channels: List[str] = field(default_factory=lambda: ["log", "github"])
    enable_dashboard: bool = False

@dataclass
class PerformanceConfig:
    """Configuration for performance optimization."""
    enable_streaming_processing: bool = True
    enable_data_compression: bool = True
    enable_caching: bool = True
    cache_ttl_hours: int = 24
    memory_limit_mb: int = 2048
    enable_parallel_processing: bool = True
    chunk_size: int = 100
    enable_adaptive_parameters: bool = True

@dataclass
class StorageConfig:
    """Configuration for data storage."""
    data_directory: str = "data"
    backup_directory: str = "data/backups"
    reports_directory: str = "reports"
    logs_directory: str = "logs"
    website_output_directory: str = "."  # Root directory for website files like gguf_models.json
    enable_backups: bool = True
    backup_retention_days: int = 30
    enable_compression: bool = True

@dataclass
class NotificationConfig:
    """Configuration for notifications."""
    enable_success_notifications: bool = False
    enable_failure_notifications: bool = True
    enable_warning_notifications: bool = True
    enable_critical_notifications: bool = True
    notification_channels: List[str] = field(default_factory=lambda: ["log"])
    webhook_urls: List[str] = field(default_factory=list)
    email_recipients: List[str] = field(default_factory=list)

@dataclass
class SecurityConfig:
    """Configuration for security settings."""
    enable_token_validation: bool = True
    enable_rate_limit_protection: bool = True
    enable_request_signing: bool = False
    enable_audit_logging: bool = True
    mask_sensitive_data: bool = True
    allowed_domains: List[str] = field(default_factory=lambda: ["huggingface.co"])

@dataclass
class DynamicRetentionConfig:
    """Configuration for dynamic model retention system."""
    retention_days: int = 30
    top_models_count: int = 20
    update_schedule_cron: str = "0 2 * * *"  # Daily at 2 AM
    enable_cleanup: bool = True
    cleanup_batch_size: int = 100
    preserve_download_threshold: int = 1000  # Always preserve models with 1000+ downloads
    enable_ranking_history: bool = True
    ranking_history_days: int = 90
    enable_retention_mode: bool = False  # Enable/disable retention mode
    recent_models_priority: bool = True  # Prioritize recent models in merging
    top_models_storage_path: str = "data/top_models.json"
    retention_metadata_path: str = "data/retention_metadata.json"

@dataclass
class SyncConfiguration:
    """Main configuration class containing all sync parameters."""
    
    # Environment and basic settings
    environment: Environment = Environment.PRODUCTION
    log_level: LogLevel = LogLevel.INFO
    debug_mode: bool = False
    dry_run: bool = False
    
    # Component configurations
    rate_limiting: RateLimitConfig = field(default_factory=RateLimitConfig)
    sync_behavior: SyncBehaviorConfig = field(default_factory=SyncBehaviorConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    error_handling: ErrorHandlingConfig = field(default_factory=ErrorHandlingConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    dynamic_retention: DynamicRetentionConfig = field(default_factory=DynamicRetentionConfig)
    
    # API and external service settings
    huggingface_token: Optional[str] = None
    api_base_url: str = "https://huggingface.co"
    user_agent: str = "GGUF-Models-Sync/1.0"
    
    # Workflow and deployment settings
    workflow_timeout_hours: int = 6
    enable_github_actions_integration: bool = True
    enable_pages_deployment: bool = True
    
    # Custom settings for extensibility
    custom_settings: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization validation and setup."""
        # Load token from environment if not provided
        if not self.huggingface_token:
            self.huggingface_token = os.getenv('HUGGINGFACE_TOKEN')
        
        # Ensure directories exist
        self._ensure_directories()
        
        # Apply environment-specific overrides
        self._apply_environment_overrides()

    def _ensure_directories(self):
        """Ensure all required directories exist."""
        directories = [
            self.storage.data_directory,
            self.storage.backup_directory,
            self.storage.reports_directory,
            self.storage.logs_directory
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)

    def _apply_environment_overrides(self):
        """Apply environment-specific configuration overrides."""
        if self.environment == Environment.DEVELOPMENT:
            self.debug_mode = True
            self.log_level = LogLevel.DEBUG
            self.rate_limiting.requests_per_second = 0.5  # Slower for dev
            self.monitoring.progress_report_interval_seconds = 300  # More frequent
            
        elif self.environment == Environment.TESTING:
            self.dry_run = True
            self.rate_limiting.max_concurrent_requests = 10  # Lower for testing
            self.sync_behavior.incremental_window_hours = 1  # Shorter window
            self.validation.validation_timeout_seconds = 60  # Faster validation
            
        elif self.environment == Environment.STAGING:
            self.notifications.enable_success_notifications = True
            self.monitoring.enable_dashboard = True
            
        elif self.environment == Environment.PRODUCTION:
            self.error_handling.preserve_data_on_failure = True
            self.notifications.enable_critical_notifications = True
            self.security.enable_audit_logging = True

class ConfigurationManager:
    """Manages configuration loading, validation, and environment-specific settings."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.config: Optional[SyncConfiguration] = None
        self._validation_errors: List[str] = []
    
    def _get_default_config_path(self) -> str:
        """Get the default configuration file path."""
        # Check for environment-specific config first
        env = os.getenv('SYNC_ENVIRONMENT', 'production').lower()
        env_config_path = f"config/sync-config-{env}.yaml"
        
        if Path(env_config_path).exists():
            return env_config_path
        
        # Fall back to default config
        return "config/sync-config.yaml"
    
    def load_configuration(self) -> SyncConfiguration:
        """Load configuration from file with environment variable overrides."""
        logger.info(f"📋 Loading configuration from {self.config_path}")
        
        # Start with default configuration
        config_dict = {}
        
        # Load from file if it exists
        if Path(self.config_path).exists():
            config_dict = self._load_config_file()
        else:
            logger.warning(f"⚠️ Configuration file not found: {self.config_path}")
            logger.info("📋 Using default configuration")
        
        # Apply environment variable overrides
        config_dict = self._apply_environment_overrides(config_dict)
        
        # Create configuration object
        self.config = self._create_configuration(config_dict)
        
        # Validate configuration
        if not self.validate_configuration():
            raise ValueError(f"Configuration validation failed: {self._validation_errors}")
        
        logger.info("✅ Configuration loaded and validated successfully")
        return self.config
    
    def _load_config_file(self) -> Dict[str, Any]:
        """Load configuration from YAML or JSON file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                if self.config_path.endswith('.yaml') or self.config_path.endswith('.yml'):
                    return yaml.safe_load(f) or {}
                elif self.config_path.endswith('.json'):
                    return json.load(f) or {}
                else:
                    raise ValueError(f"Unsupported config file format: {self.config_path}")
        except Exception as e:
            logger.error(f"❌ Failed to load configuration file: {e}")
            return {}
    
    def _apply_environment_overrides(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to configuration."""
        logger.info("🔧 Applying environment variable overrides")
        
        # Environment variable mappings
        env_mappings = {
            'SYNC_ENVIRONMENT': ('environment', lambda x: Environment(x.lower())),
            'SYNC_MODE': ('sync_behavior.mode', lambda x: SyncMode(x.lower())),
            'LOG_LEVEL': ('log_level', lambda x: LogLevel(x.upper())),
            'DEBUG_MODE': ('debug_mode', lambda x: x.lower() == 'true'),
            'DRY_RUN': ('dry_run', lambda x: x.lower() == 'true'),
            
            # Rate limiting
            'MAX_CONCURRENCY': ('rate_limiting.max_concurrent_requests', int),
            'REQUESTS_PER_SECOND': ('rate_limiting.requests_per_second', float),
            'REQUESTS_PER_HOUR': ('rate_limiting.requests_per_hour', int),
            'MAX_RETRIES': ('rate_limiting.max_retries', int),
            'TIMEOUT_SECONDS': ('rate_limiting.timeout_seconds', int),
            
            # Sync behavior
            'INCREMENTAL_WINDOW_HOURS': ('sync_behavior.incremental_window_hours', int),
            'FULL_SYNC_THRESHOLD_HOURS': ('sync_behavior.full_sync_threshold_hours', int),
            'FORCE_FULL_SYNC': ('sync_behavior.force_full_sync', lambda x: x.lower() == 'true'),
            
            # Monitoring
            'ENABLE_DETAILED_LOGGING': ('monitoring.enable_detailed_logging', lambda x: x.lower() == 'true'),
            'PROGRESS_REPORT_INTERVAL': ('monitoring.progress_report_interval_seconds', int),
            'ENABLE_PERFORMANCE_METRICS': ('monitoring.enable_performance_metrics', lambda x: x.lower() == 'true'),
            
            # Workflow
            'WORKFLOW_TIMEOUT_HOURS': ('workflow_timeout_hours', int),
            
            # API
            'HUGGINGFACE_TOKEN': ('huggingface_token', str),
            'API_BASE_URL': ('api_base_url', str),
            
            # Dynamic retention
            'RETENTION_DAYS': ('dynamic_retention.retention_days', int),
            'TOP_MODELS_COUNT': ('dynamic_retention.top_models_count', int),
            'UPDATE_SCHEDULE_CRON': ('dynamic_retention.update_schedule_cron', str),
            'ENABLE_CLEANUP': ('dynamic_retention.enable_cleanup', lambda x: x.lower() == 'true'),
            'CLEANUP_BATCH_SIZE': ('dynamic_retention.cleanup_batch_size', int),
            'PRESERVE_DOWNLOAD_THRESHOLD': ('dynamic_retention.preserve_download_threshold', int),
            'ENABLE_RANKING_HISTORY': ('dynamic_retention.enable_ranking_history', lambda x: x.lower() == 'true'),
            'RANKING_HISTORY_DAYS': ('dynamic_retention.ranking_history_days', int),
            'ENABLE_RETENTION_MODE': ('dynamic_retention.enable_retention_mode', lambda x: x.lower() == 'true'),
            'RECENT_MODELS_PRIORITY': ('dynamic_retention.recent_models_priority', lambda x: x.lower() == 'true'),
            'TOP_MODELS_STORAGE_PATH': ('dynamic_retention.top_models_storage_path', str),
            'RETENTION_METADATA_PATH': ('dynamic_retention.retention_metadata_path', str),
        }
        
        # Apply overrides
        for env_var, (config_path, converter) in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                try:
                    converted_value = converter(env_value)
                    self._set_nested_value(config_dict, config_path, converted_value)
                    logger.debug(f"🔧 Override: {config_path} = {converted_value}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to apply override {env_var}: {e}")
        
        return config_dict
    
    def _set_nested_value(self, config_dict: Dict[str, Any], path: str, value: Any):
        """Set a nested value in the configuration dictionary."""
        keys = path.split('.')
        current = config_dict
        
        # Navigate to the parent of the target key
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Set the final value
        current[keys[-1]] = value
    
    def _create_configuration(self, config_dict: Dict[str, Any]) -> SyncConfiguration:
        """Create SyncConfiguration object from dictionary."""
        try:
            # Handle nested configurations
            nested_configs = {
                'rate_limiting': RateLimitConfig,
                'sync_behavior': SyncBehaviorConfig,
                'validation': ValidationConfig,
                'error_handling': ErrorHandlingConfig,
                'monitoring': MonitoringConfig,
                'performance': PerformanceConfig,
                'storage': StorageConfig,
                'notifications': NotificationConfig,
                'security': SecurityConfig,
                'dynamic_retention': DynamicRetentionConfig,
            }
            
            # Create nested configuration objects
            for key, config_class in nested_configs.items():
                if key in config_dict and isinstance(config_dict[key], dict):
                    nested_dict = config_dict[key].copy()
                    
                    # Handle enums in nested configurations
                    if key == 'sync_behavior' and 'mode' in nested_dict and isinstance(nested_dict['mode'], str):
                        nested_dict['mode'] = SyncMode(nested_dict['mode'].lower())
                    
                    config_dict[key] = config_class(**nested_dict)
            
            # Handle enums
            if 'environment' in config_dict and isinstance(config_dict['environment'], str):
                config_dict['environment'] = Environment(config_dict['environment'].lower())
            
            if 'log_level' in config_dict and isinstance(config_dict['log_level'], str):
                config_dict['log_level'] = LogLevel(config_dict['log_level'].upper())
            
            return SyncConfiguration(**config_dict)
            
        except Exception as e:
            logger.error(f"❌ Failed to create configuration object: {e}")
            # Return default configuration on error
            return SyncConfiguration()
    
    def validate_configuration(self) -> bool:
        """Validate the loaded configuration."""
        if not self.config:
            self._validation_errors.append("Configuration not loaded")
            return False
        
        self._validation_errors.clear()
        
        # Validate required fields
        if not self.config.huggingface_token:
            self._validation_errors.append("Hugging Face token is required")
        
        # Validate rate limiting
        if self.config.rate_limiting.requests_per_second <= 0:
            self._validation_errors.append("Requests per second must be positive")
        
        if self.config.rate_limiting.max_concurrent_requests <= 0:
            self._validation_errors.append("Max concurrent requests must be positive")
        
        # Validate sync behavior
        if self.config.sync_behavior.incremental_window_hours <= 0:
            self._validation_errors.append("Incremental window hours must be positive")
        
        if self.config.sync_behavior.full_sync_threshold_hours <= 0:
            self._validation_errors.append("Full sync threshold hours must be positive")
        
        # Validate validation config
        if self.config.validation.min_completeness_score < 0 or self.config.validation.min_completeness_score > 1:
            self._validation_errors.append("Min completeness score must be between 0 and 1")
        
        # Validate directories
        try:
            Path(self.config.storage.data_directory).mkdir(parents=True, exist_ok=True)
            Path(self.config.storage.reports_directory).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self._validation_errors.append(f"Cannot create required directories: {e}")
        
        # Validate workflow timeout
        if self.config.workflow_timeout_hours <= 0 or self.config.workflow_timeout_hours > 24:
            self._validation_errors.append("Workflow timeout must be between 1 and 24 hours")
        
        # Validate dynamic retention configuration
        if self.config.dynamic_retention.retention_days <= 0:
            self._validation_errors.append("Retention days must be positive")
        
        if self.config.dynamic_retention.retention_days > 365:
            self._validation_errors.append("Retention days cannot exceed 365 days")
        
        if self.config.dynamic_retention.top_models_count <= 0:
            self._validation_errors.append("Top models count must be positive")
        
        if self.config.dynamic_retention.top_models_count > 1000:
            self._validation_errors.append("Top models count cannot exceed 1000")
        
        if self.config.dynamic_retention.cleanup_batch_size <= 0:
            self._validation_errors.append("Cleanup batch size must be positive")
        
        if self.config.dynamic_retention.preserve_download_threshold < 0:
            self._validation_errors.append("Preserve download threshold cannot be negative")
        
        if self.config.dynamic_retention.ranking_history_days <= 0:
            self._validation_errors.append("Ranking history days must be positive")
        
        if self.config.dynamic_retention.ranking_history_days > 365:
            self._validation_errors.append("Ranking history days cannot exceed 365 days")
        
        # Validate cron expression format (basic validation)
        cron_parts = self.config.dynamic_retention.update_schedule_cron.split()
        if len(cron_parts) != 5:
            self._validation_errors.append("Update schedule cron must have 5 parts (minute hour day month weekday)")
        
        # Validate storage paths
        try:
            top_models_dir = Path(self.config.dynamic_retention.top_models_storage_path).parent
            retention_metadata_dir = Path(self.config.dynamic_retention.retention_metadata_path).parent
            top_models_dir.mkdir(parents=True, exist_ok=True)
            retention_metadata_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self._validation_errors.append(f"Cannot create dynamic retention directories: {e}")
        
        # Log validation results
        if self._validation_errors:
            for error in self._validation_errors:
                logger.error(f"❌ Validation error: {error}")
            return False
        
        logger.info("✅ Configuration validation passed")
        return True
    
    def save_configuration(self, output_path: Optional[str] = None) -> bool:
        """Save current configuration to file."""
        if not self.config:
            logger.error("❌ No configuration to save")
            return False
        
        output_path = output_path or self.config_path
        
        try:
            # Convert to dictionary
            config_dict = asdict(self.config)
            
            # Convert enums to strings
            config_dict['environment'] = self.config.environment.value
            config_dict['log_level'] = self.config.log_level.value
            config_dict['sync_behavior']['mode'] = self.config.sync_behavior.mode.value
            
            # Ensure directory exists
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Save as YAML
            with open(output_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_dict, f, default_flow_style=False, indent=2)
            
            logger.info(f"💾 Configuration saved to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to save configuration: {e}")
            return False
    
    def get_configuration_summary(self) -> Dict[str, Any]:
        """Get a summary of the current configuration."""
        if not self.config:
            return {"error": "No configuration loaded"}
        
        return {
            "environment": self.config.environment.value,
            "sync_mode": self.config.sync_behavior.mode.value,
            "debug_mode": self.config.debug_mode,
            "dry_run": self.config.dry_run,
            "max_concurrency": self.config.rate_limiting.max_concurrent_requests,
            "requests_per_second": self.config.rate_limiting.requests_per_second,
            "incremental_window_hours": self.config.sync_behavior.incremental_window_hours,
            "full_sync_threshold_hours": self.config.sync_behavior.full_sync_threshold_hours,
            "enable_validation": self.config.validation.enable_schema_validation,
            "enable_monitoring": self.config.monitoring.enable_detailed_logging,
            "workflow_timeout_hours": self.config.workflow_timeout_hours,
            "dynamic_retention": {
                "enable_retention_mode": self.config.dynamic_retention.enable_retention_mode,
                "retention_days": self.config.dynamic_retention.retention_days,
                "top_models_count": self.config.dynamic_retention.top_models_count,
                "enable_cleanup": self.config.dynamic_retention.enable_cleanup,
                "preserve_download_threshold": self.config.dynamic_retention.preserve_download_threshold,
                "update_schedule": self.config.dynamic_retention.update_schedule_cron
            },
            "config_file": self.config_path,
            "validation_status": "valid" if not self._validation_errors else "invalid",
            "validation_errors": self._validation_errors
        }

def create_default_configuration() -> SyncConfiguration:
    """Create a default configuration with recommended settings."""
    return SyncConfiguration(
        environment=Environment.PRODUCTION,
        log_level=LogLevel.INFO,
        rate_limiting=RateLimitConfig(
            requests_per_second=1.2,
            max_concurrent_requests=50,
            max_retries=5
        ),
        sync_behavior=SyncBehaviorConfig(
            mode=SyncMode.AUTO,
            incremental_window_hours=48,
            full_sync_threshold_hours=168
        ),
        validation=ValidationConfig(
            enable_schema_validation=True,
            min_completeness_score=0.95
        ),
        monitoring=MonitoringConfig(
            enable_detailed_logging=True,
            progress_report_interval_seconds=900
        ),
        dynamic_retention=DynamicRetentionConfig(
            retention_days=30,
            top_models_count=20,
            enable_retention_mode=False,
            enable_cleanup=True
        )
    )

def load_configuration(config_path: Optional[str] = None) -> SyncConfiguration:
    """Convenience function to load configuration."""
    manager = ConfigurationManager(config_path)
    return manager.load_configuration()

if __name__ == "__main__":
    # Example usage and testing
    logging.basicConfig(level=logging.INFO)
    
    try:
        config = load_configuration()
        print("✅ Configuration loaded successfully")
        
        manager = ConfigurationManager()
        summary = manager.get_configuration_summary()
        print(f"📋 Configuration summary: {json.dumps(summary, indent=2)}")
        
    except Exception as e:
        print(f"❌ Configuration loading failed: {e}")