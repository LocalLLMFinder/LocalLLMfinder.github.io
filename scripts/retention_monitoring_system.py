#!/usr/bin/env python3
"""
Dynamic Model Retention Monitoring System

This module provides comprehensive monitoring and alerting capabilities specifically
for the dynamic model retention system, including detailed logging for retention
operations, metrics collection for API usage and storage efficiency, and alert
conditions for failed updates and data inconsistencies.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
import aiofiles
import os

class RetentionOperation(Enum):
    """Types of retention operations."""
    RECENT_EXTRACTION = "recent_extraction"
    TOP_MODELS_UPDATE = "top_models_update"
    DATA_MERGE = "data_merge"
    CLEANUP = "cleanup"
    DEDUPLICATION = "deduplication"
    VALIDATION = "validation"

class RetentionAlertType(Enum):
    """Types of retention-specific alerts."""
    HIGH_API_USAGE = "high_api_usage"
    FAILED_UPDATE = "failed_update"
    DATA_INCONSISTENCY = "data_inconsistency"
    STORAGE_THRESHOLD = "storage_threshold"
    CLEANUP_FAILURE = "cleanup_failure"
    RANKING_ANOMALY = "ranking_anomaly"

@dataclass
class RetentionMetrics:
    """Metrics specific to retention operations."""
    # API Usage Metrics
    api_calls_made: int = 0
    api_calls_successful: int = 0
    api_calls_failed: int = 0
    api_response_time_ms: float = 0.0
    rate_limit_hits: int = 0
    
    # Processing Time Metrics
    recent_extraction_time_ms: float = 0.0
    top_models_update_time_ms: float = 0.0
    cleanup_time_ms: float = 0.0
    merge_time_ms: float = 0.0
    total_processing_time_ms: float = 0.0
    
    # Storage Efficiency Metrics
    models_before_cleanup: int = 0
    models_after_cleanup: int = 0
    storage_freed_mb: float = 0.0
    storage_used_mb: float = 0.0
    deduplication_savings: int = 0
    
    # Data Quality Metrics
    recent_models_fetched: int = 0
    top_models_updated: int = 0
    duplicates_removed: int = 0
    validation_errors: int = 0
    data_consistency_score: float = 100.0
    
    # Retention-specific Metrics
    retention_days_configured: int = 30
    top_models_count_configured: int = 20
    models_preserved_by_top_status: int = 0
    models_removed_by_age: int = 0

@dataclass
class RetentionAlert:
    """Retention-specific alert data."""
    alert_type: RetentionAlertType
    severity: str
    message: str
    timestamp: datetime
    operation: Optional[RetentionOperation] = None
    metrics: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary for serialization."""
        return {
            'alert_type': self.alert_type.value,
            'severity': self.severity,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'operation': self.operation.value if self.operation else None,
            'metrics': self.metrics or {},
            'context': self.context or {}
        }

class RetentionMonitoringSystem:
    """Monitoring system specifically for dynamic model retention operations."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.logger = self._setup_retention_logger()
        
        # Current operation tracking
        self.current_operation: Optional[RetentionOperation] = None
        self.operation_start_time: Optional[datetime] = None
        self.metrics = RetentionMetrics()
        
        # Alert thresholds
        self.api_usage_threshold = self.config.get('api_usage_threshold', 1000)
        self.processing_time_threshold_ms = self.config.get('processing_time_threshold_ms', 300000)  # 5 minutes
        self.storage_threshold_mb = self.config.get('storage_threshold_mb', 10240)  # 10GB
        self.data_consistency_threshold = self.config.get('data_consistency_threshold', 95.0)
        
        # Historical data
        self.operation_history: deque = deque(maxlen=1000)
        self.alert_history: deque = deque(maxlen=500)
        
        # Performance tracking
        self.api_response_times: deque = deque(maxlen=100)
        self.processing_times: Dict[RetentionOperation, deque] = {
            op: deque(maxlen=50) for op in RetentionOperation
        }
    
    def _setup_retention_logger(self) -> logging.Logger:
        """Setup specialized logger for retention operations."""
        logger = logging.getLogger('retention_monitoring')
        logger.setLevel(logging.DEBUG)
        
        # Create logs directory if it doesn't exist
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Setup file handler with structured format
        handler = logging.FileHandler(
            log_dir / "retention_monitoring.log",
            mode='a',
            encoding='utf-8'
        )
        
        # Structured logging format for retention operations
        formatter = logging.Formatter(
            '%(asctime)s - RETENTION - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return logger
    
    def start_operation(self, operation: RetentionOperation, context: Optional[Dict] = None):
        """Start monitoring a retention operation."""
        self.current_operation = operation
        self.operation_start_time = datetime.now(timezone.utc)
        
        context_str = f" - Context: {json.dumps(context)}" if context else ""
        self.logger.info(f"🚀 Starting {operation.value} operation{context_str}")
        
        # Log structured operation start
        self._log_structured_event("operation_start", {
            'operation': operation.value,
            'timestamp': self.operation_start_time.isoformat(),
            'context': context or {}
        })
    
    def end_operation(self, success: bool = True, context: Optional[Dict] = None):
        """End monitoring of current retention operation."""
        if not self.current_operation or not self.operation_start_time:
            return
        
        end_time = datetime.now(timezone.utc)
        duration_ms = (end_time - self.operation_start_time).total_seconds() * 1000
        
        # Update processing time metrics
        if self.current_operation == RetentionOperation.RECENT_EXTRACTION:
            self.metrics.recent_extraction_time_ms = duration_ms
        elif self.current_operation == RetentionOperation.TOP_MODELS_UPDATE:
            self.metrics.top_models_update_time_ms = duration_ms
        elif self.current_operation == RetentionOperation.CLEANUP:
            self.metrics.cleanup_time_ms = duration_ms
        elif self.current_operation == RetentionOperation.DATA_MERGE:
            self.metrics.merge_time_ms = duration_ms
        
        # Store performance data
        self.processing_times[self.current_operation].append(duration_ms)
        
        status = "✅ SUCCESS" if success else "❌ FAILED"
        context_str = f" - Context: {json.dumps(context)}" if context else ""
        
        self.logger.info(
            f"{status} {self.current_operation.value} operation completed in {duration_ms:.1f}ms{context_str}"
        )
        
        # Log structured operation end
        self._log_structured_event("operation_end", {
            'operation': self.current_operation.value,
            'success': success,
            'duration_ms': duration_ms,
            'timestamp': end_time.isoformat(),
            'context': context or {}
        })
        
        # Check for performance alerts
        if duration_ms > self.processing_time_threshold_ms:
            self._create_alert(
                RetentionAlertType.FAILED_UPDATE,
                "warning",
                f"{self.current_operation.value} operation exceeded time threshold: {duration_ms:.1f}ms",
                {'duration_ms': duration_ms, 'threshold_ms': self.processing_time_threshold_ms}
            )
        
        # Store operation history
        self.operation_history.append({
            'operation': self.current_operation.value,
            'start_time': self.operation_start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_ms': duration_ms,
            'success': success,
            'context': context or {}
        })
        
        self.current_operation = None
        self.operation_start_time = None
    
    def log_api_call(self, endpoint: str, response_time_ms: float, success: bool, 
                     status_code: Optional[int] = None, error_message: Optional[str] = None):
        """Log API call with detailed metrics."""
        self.metrics.api_calls_made += 1
        if success:
            self.metrics.api_calls_successful += 1
        else:
            self.metrics.api_calls_failed += 1
        
        # Update response time metrics
        self.api_response_times.append(response_time_ms)
        self.metrics.api_response_time_ms = sum(self.api_response_times) / len(self.api_response_times)
        
        status = "✅" if success else "❌"
        error_info = f" - Error: {error_message}" if error_message else ""
        status_info = f" - Status: {status_code}" if status_code else ""
        
        self.logger.info(
            f"{status} API Call to {endpoint} - {response_time_ms:.1f}ms{status_info}{error_info}"
        )
        
        # Log structured API call
        self._log_structured_event("api_call", {
            'endpoint': endpoint,
            'response_time_ms': response_time_ms,
            'success': success,
            'status_code': status_code,
            'error_message': error_message,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
        # Check for API usage alerts
        if self.metrics.api_calls_made > self.api_usage_threshold:
            self._create_alert(
                RetentionAlertType.HIGH_API_USAGE,
                "warning",
                f"High API usage detected: {self.metrics.api_calls_made} calls",
                {'api_calls': self.metrics.api_calls_made, 'threshold': self.api_usage_threshold}
            )
    
    def log_rate_limit_hit(self, wait_time_seconds: float, endpoint: str):
        """Log rate limit hit with wait time."""
        self.metrics.rate_limit_hits += 1
        
        self.logger.warning(
            f"⏳ Rate limit hit on {endpoint} - waiting {wait_time_seconds:.1f}s"
        )
        
        # Log structured rate limit event
        self._log_structured_event("rate_limit_hit", {
            'endpoint': endpoint,
            'wait_time_seconds': wait_time_seconds,
            'total_hits': self.metrics.rate_limit_hits,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    def log_storage_metrics(self, used_mb: float, freed_mb: float = 0.0, 
                           models_before: int = 0, models_after: int = 0):
        """Log storage efficiency metrics."""
        self.metrics.storage_used_mb = used_mb
        self.metrics.storage_freed_mb += freed_mb
        self.metrics.models_before_cleanup = models_before
        self.metrics.models_after_cleanup = models_after
        
        if freed_mb > 0:
            self.logger.info(
                f"💾 Storage cleanup: {freed_mb:.1f}MB freed, {models_before - models_after} models removed"
            )
        
        self.logger.info(f"💾 Current storage usage: {used_mb:.1f}MB")
        
        # Log structured storage metrics
        self._log_structured_event("storage_metrics", {
            'used_mb': used_mb,
            'freed_mb': freed_mb,
            'models_before': models_before,
            'models_after': models_after,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
        # Check for storage threshold alerts
        if used_mb > self.storage_threshold_mb:
            self._create_alert(
                RetentionAlertType.STORAGE_THRESHOLD,
                "warning",
                f"Storage usage exceeds threshold: {used_mb:.1f}MB",
                {'used_mb': used_mb, 'threshold_mb': self.storage_threshold_mb}
            )
    
    def log_data_quality_metrics(self, recent_fetched: int, top_updated: int, 
                                duplicates_removed: int, validation_errors: int):
        """Log data quality and consistency metrics."""
        self.metrics.recent_models_fetched = recent_fetched
        self.metrics.top_models_updated = top_updated
        self.metrics.duplicates_removed = duplicates_removed
        self.metrics.validation_errors = validation_errors
        self.metrics.deduplication_savings = duplicates_removed
        
        # Calculate data consistency score
        total_operations = recent_fetched + top_updated + duplicates_removed
        if total_operations > 0:
            error_rate = validation_errors / total_operations
            self.metrics.data_consistency_score = max(0, (1 - error_rate) * 100)
        
        self.logger.info(
            f"📊 Data Quality: {recent_fetched} recent, {top_updated} top, "
            f"{duplicates_removed} duplicates removed, {validation_errors} errors"
        )
        self.logger.info(f"📊 Data Consistency Score: {self.metrics.data_consistency_score:.1f}%")
        
        # Log structured data quality metrics
        self._log_structured_event("data_quality_metrics", {
            'recent_fetched': recent_fetched,
            'top_updated': top_updated,
            'duplicates_removed': duplicates_removed,
            'validation_errors': validation_errors,
            'consistency_score': self.metrics.data_consistency_score,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
        # Check for data consistency alerts
        if self.metrics.data_consistency_score < self.data_consistency_threshold:
            self._create_alert(
                RetentionAlertType.DATA_INCONSISTENCY,
                "error",
                f"Data consistency below threshold: {self.metrics.data_consistency_score:.1f}%",
                {
                    'consistency_score': self.metrics.data_consistency_score,
                    'threshold': self.data_consistency_threshold,
                    'validation_errors': validation_errors
                }
            )
    
    def log_retention_specific_metrics(self, retention_days: int, top_count: int,
                                     preserved_by_top: int, removed_by_age: int):
        """Log retention-specific configuration and results."""
        self.metrics.retention_days_configured = retention_days
        self.metrics.top_models_count_configured = top_count
        self.metrics.models_preserved_by_top_status = preserved_by_top
        self.metrics.models_removed_by_age = removed_by_age
        
        self.logger.info(
            f"🔄 Retention Config: {retention_days} days, top {top_count} models"
        )
        self.logger.info(
            f"🔄 Retention Results: {preserved_by_top} preserved by top status, "
            f"{removed_by_age} removed by age"
        )
        
        # Log structured retention metrics
        self._log_structured_event("retention_metrics", {
            'retention_days': retention_days,
            'top_count': top_count,
            'preserved_by_top': preserved_by_top,
            'removed_by_age': removed_by_age,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    
    def _log_structured_event(self, event_type: str, data: Dict[str, Any]):
        """Log structured event data for machine processing."""
        structured_log = {
            'event_type': event_type,
            'data': data,
            'metrics_snapshot': {
                'api_calls_made': self.metrics.api_calls_made,
                'api_success_rate': (
                    self.metrics.api_calls_successful / max(1, self.metrics.api_calls_made) * 100
                ),
                'storage_used_mb': self.metrics.storage_used_mb,
                'data_consistency_score': self.metrics.data_consistency_score
            }
        }
        
        self.logger.debug(f"STRUCTURED_EVENT: {json.dumps(structured_log)}")
    
    def _create_alert(self, alert_type: RetentionAlertType, severity: str, 
                     message: str, metrics: Optional[Dict] = None):
        """Create and log a retention-specific alert."""
        alert = RetentionAlert(
            alert_type=alert_type,
            severity=severity,
            message=message,
            timestamp=datetime.now(timezone.utc),
            operation=self.current_operation,
            metrics=metrics,
            context={'current_metrics': self.get_current_metrics_summary()}
        )
        
        self.alert_history.append(alert)
        
        # Log alert with appropriate level
        if severity == "critical":
            self.logger.critical(f"🚨 CRITICAL ALERT: {message}")
        elif severity == "error":
            self.logger.error(f"❌ ERROR ALERT: {message}")
        elif severity == "warning":
            self.logger.warning(f"⚠️  WARNING ALERT: {message}")
        else:
            self.logger.info(f"ℹ️  INFO ALERT: {message}")
        
        # Log structured alert
        self._log_structured_event("alert_created", alert.to_dict())
    
    def get_current_metrics_summary(self) -> Dict[str, Any]:
        """Get current metrics summary for reporting."""
        return {
            'api_calls_made': self.metrics.api_calls_made,
            'api_success_rate': (
                self.metrics.api_calls_successful / max(1, self.metrics.api_calls_made) * 100
            ),
            'avg_api_response_time_ms': self.metrics.api_response_time_ms,
            'rate_limit_hits': self.metrics.rate_limit_hits,
            'total_processing_time_ms': self.metrics.total_processing_time_ms,
            'storage_used_mb': self.metrics.storage_used_mb,
            'storage_freed_mb': self.metrics.storage_freed_mb,
            'recent_models_fetched': self.metrics.recent_models_fetched,
            'top_models_updated': self.metrics.top_models_updated,
            'duplicates_removed': self.metrics.duplicates_removed,
            'data_consistency_score': self.metrics.data_consistency_score,
            'retention_days': self.metrics.retention_days_configured,
            'top_models_count': self.metrics.top_models_count_configured
        }
    
    async def generate_monitoring_report(self) -> Dict[str, Any]:
        """Generate comprehensive monitoring report."""
        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'metrics': self.get_current_metrics_summary(),
            'recent_operations': list(self.operation_history)[-10:],  # Last 10 operations
            'recent_alerts': [alert.to_dict() for alert in list(self.alert_history)[-5:]],  # Last 5 alerts
            'performance_summary': {
                'avg_processing_times_ms': {
                    op.value: sum(times) / len(times) if times else 0
                    for op, times in self.processing_times.items()
                },
                'api_response_time_trend': list(self.api_response_times)[-20:],  # Last 20 API calls
            },
            'health_status': self._calculate_health_status()
        }
        
        return report
    
    def _calculate_health_status(self) -> str:
        """Calculate overall health status based on metrics."""
        issues = []
        
        # Check API success rate
        if self.metrics.api_calls_made > 0:
            success_rate = (self.metrics.api_calls_successful / self.metrics.api_calls_made) * 100
            if success_rate < 95:
                issues.append("low_api_success_rate")
        
        # Check data consistency
        if self.metrics.data_consistency_score < self.data_consistency_threshold:
            issues.append("low_data_consistency")
        
        # Check storage usage
        if self.metrics.storage_used_mb > self.storage_threshold_mb:
            issues.append("high_storage_usage")
        
        # Check recent alerts
        recent_critical_alerts = [
            alert for alert in list(self.alert_history)[-10:]
            if alert.severity in ["critical", "error"]
        ]
        if recent_critical_alerts:
            issues.append("recent_critical_alerts")
        
        if not issues:
            return "healthy"
        elif len(issues) == 1:
            return "warning"
        else:
            return "critical"
    
    async def save_monitoring_report(self, report: Dict[str, Any]):
        """Save monitoring report to file."""
        try:
            reports_dir = Path("reports/retention")
            reports_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_path = reports_dir / f"retention_monitoring_report_{timestamp}.json"
            
            async with aiofiles.open(report_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(report, indent=2))
            
            self.logger.info(f"💾 Monitoring report saved to {report_path}")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to save monitoring report: {e}")
    
    def reset_metrics(self):
        """Reset metrics for new monitoring cycle."""
        self.metrics = RetentionMetrics()
        self.logger.info("🔄 Metrics reset for new monitoring cycle")


# Global instance for easy access
retention_monitor = RetentionMonitoringSystem()