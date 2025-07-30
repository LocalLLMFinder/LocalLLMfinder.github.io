#!/usr/bin/env python3
"""
Retention Monitoring Integration

This module integrates the retention monitoring system with the existing
monitoring infrastructure and GitHub Actions notifications.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import aiohttp
import aiofiles

try:
    from retention_monitoring_system import (
        RetentionMonitoringSystem, 
        RetentionAlertType, 
        RetentionOperation,
        retention_monitor
    )
except ImportError:
    # Try relative import if absolute fails
    from .retention_monitoring_system import (
        RetentionMonitoringSystem, 
        RetentionAlertType, 
        RetentionOperation,
        retention_monitor
    )

try:
    from monitoring_system import MonitoringSystem, AlertSeverity, ErrorCategory
except ImportError:
    try:
        from .monitoring_system import MonitoringSystem, AlertSeverity, ErrorCategory
    except ImportError:
        # Fallback if monitoring system is not available
        MonitoringSystem = None
        AlertSeverity = None
        ErrorCategory = None

class RetentionMonitoringIntegration:
    """Integration layer for retention monitoring with existing systems."""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.logger = logging.getLogger('retention_integration')
        
        # Initialize retention monitoring
        self.retention_monitor = retention_monitor
        
        # Initialize main monitoring system if available
        self.main_monitor = None
        if MonitoringSystem:
            try:
                self.main_monitor = MonitoringSystem()
            except Exception as e:
                self.logger.warning(f"Could not initialize main monitoring system: {e}")
        
        # GitHub Actions integration
        self.github_token = os.getenv('GITHUB_TOKEN')
        self.github_repo = os.getenv('GITHUB_REPOSITORY', 'unknown/repo')
        self.workflow_run_id = os.getenv('GITHUB_RUN_ID')
        
        # Notification settings
        self.enable_github_notifications = self.config.get('enable_github_notifications', True)
        self.enable_main_monitor_integration = self.config.get('enable_main_monitor_integration', True)
        
        # Alert thresholds for GitHub notifications
        self.github_alert_threshold = self.config.get('github_alert_threshold', 'error')
    
    async def start_retention_monitoring(self, operation_type: str, context: Optional[Dict] = None):
        """Start monitoring a retention operation with full integration."""
        try:
            # Map operation type to enum
            operation = RetentionOperation(operation_type)
        except ValueError:
            self.logger.warning(f"Unknown operation type: {operation_type}")
            return
        
        # Start retention-specific monitoring
        self.retention_monitor.start_operation(operation, context)
        
        # Integrate with main monitoring system
        if self.main_monitor and self.enable_main_monitor_integration:
            try:
                # Log to main monitoring system
                self.main_monitor.logger.info(
                    f"🔄 Starting retention operation: {operation_type}"
                )
            except Exception as e:
                self.logger.warning(f"Failed to integrate with main monitor: {e}")
        
        # Log to GitHub Actions if running in CI
        if self.workflow_run_id:
            await self._log_to_github_actions(
                "notice",
                f"Starting retention operation: {operation_type}",
                context
            )
    
    async def end_retention_monitoring(self, success: bool = True, context: Optional[Dict] = None):
        """End retention monitoring with full integration."""
        # End retention-specific monitoring
        self.retention_monitor.end_operation(success, context)
        
        # Get metrics summary for integration
        metrics = self.retention_monitor.get_current_metrics_summary()
        
        # Integrate with main monitoring system
        if self.main_monitor and self.enable_main_monitor_integration:
            try:
                # Update main monitoring with retention metrics
                if hasattr(self.main_monitor, 'update_performance_metrics'):
                    self.main_monitor.update_performance_metrics(
                        memory_mb=metrics.get('storage_used_mb', 0),
                        cpu_percent=0,  # Not tracked in retention
                        network_requests=metrics.get('api_calls_made', 0),
                        data_transferred_mb=0  # Could be calculated if needed
                    )
                
                # Log completion to main system
                status = "SUCCESS" if success else "FAILED"
                self.main_monitor.logger.info(
                    f"🔄 Retention operation completed: {status} - "
                    f"API calls: {metrics.get('api_calls_made', 0)}, "
                    f"Storage: {metrics.get('storage_used_mb', 0):.1f}MB"
                )
            except Exception as e:
                self.logger.warning(f"Failed to integrate with main monitor: {e}")
        
        # Log to GitHub Actions
        if self.workflow_run_id:
            status_type = "notice" if success else "error"
            await self._log_to_github_actions(
                status_type,
                f"Retention operation completed: {'SUCCESS' if success else 'FAILED'}",
                {'metrics': metrics}
            )
        
        # Check for alerts that need GitHub notification
        await self._check_and_send_github_alerts()
    
    async def log_retention_api_call(self, endpoint: str, response_time_ms: float, 
                                   success: bool, status_code: Optional[int] = None,
                                   error_message: Optional[str] = None):
        """Log API call with integration to main monitoring."""
        # Log to retention monitoring
        self.retention_monitor.log_api_call(
            endpoint, response_time_ms, success, status_code, error_message
        )
        
        # Integrate with main monitoring system
        if self.main_monitor and self.enable_main_monitor_integration:
            try:
                if not success and error_message:
                    # Log error to main system
                    error_category = ErrorCategory.API if ErrorCategory else None
                    if error_category and hasattr(self.main_monitor, 'log_error'):
                        self.main_monitor.log_error(
                            error_category,
                            f"Retention API call failed: {error_message}",
                            context={'endpoint': endpoint, 'status_code': status_code}
                        )
            except Exception as e:
                self.logger.warning(f"Failed to integrate API call with main monitor: {e}")
    
    async def log_retention_storage_metrics(self, used_mb: float, freed_mb: float = 0.0,
                                          models_before: int = 0, models_after: int = 0):
        """Log storage metrics with integration."""
        # Log to retention monitoring
        self.retention_monitor.log_storage_metrics(used_mb, freed_mb, models_before, models_after)
        
        # Check for storage alerts that need GitHub notification
        if used_mb > self.retention_monitor.storage_threshold_mb:
            await self._send_github_alert(
                "warning",
                f"Retention storage usage high: {used_mb:.1f}MB",
                {
                    'used_mb': used_mb,
                    'threshold_mb': self.retention_monitor.storage_threshold_mb,
                    'models_count': models_after
                }
            )
    
    async def log_retention_data_quality(self, recent_fetched: int, top_updated: int,
                                       duplicates_removed: int, validation_errors: int):
        """Log data quality metrics with integration."""
        # Log to retention monitoring
        self.retention_monitor.log_data_quality_metrics(
            recent_fetched, top_updated, duplicates_removed, validation_errors
        )
        
        # Check for data quality alerts
        consistency_score = self.retention_monitor.metrics.data_consistency_score
        if consistency_score < self.retention_monitor.data_consistency_threshold:
            await self._send_github_alert(
                "error",
                f"Retention data consistency low: {consistency_score:.1f}%",
                {
                    'consistency_score': consistency_score,
                    'validation_errors': validation_errors,
                    'threshold': self.retention_monitor.data_consistency_threshold
                }
            )
    
    async def generate_integrated_report(self) -> Dict[str, Any]:
        """Generate comprehensive report with integration data."""
        # Get retention monitoring report
        retention_report = await self.retention_monitor.generate_monitoring_report()
        
        # Add integration-specific data
        integration_data = {
            'integration_status': {
                'main_monitor_available': self.main_monitor is not None,
                'main_monitor_enabled': self.enable_main_monitor_integration,
                'github_integration_enabled': self.enable_github_notifications,
                'github_workflow_run_id': self.workflow_run_id
            },
            'github_actions_context': {
                'repository': self.github_repo,
                'run_id': self.workflow_run_id,
                'has_token': bool(self.github_token)
            }
        }
        
        # Combine reports
        integrated_report = {
            **retention_report,
            'integration': integration_data,
            'report_type': 'integrated_retention_monitoring'
        }
        
        return integrated_report
    
    async def _check_and_send_github_alerts(self):
        """Check for recent alerts that need GitHub notification."""
        if not self.enable_github_notifications or not self.workflow_run_id:
            return
        
        # Get recent alerts from retention monitor
        recent_alerts = list(self.retention_monitor.alert_history)[-5:]  # Last 5 alerts
        
        for alert in recent_alerts:
            # Check if alert severity meets threshold for GitHub notification
            if self._should_send_github_alert(alert.severity):
                await self._send_github_alert(
                    alert.severity,
                    alert.message,
                    {
                        'alert_type': alert.alert_type.value,
                        'operation': alert.operation.value if alert.operation else None,
                        'metrics': alert.metrics or {}
                    }
                )
    
    def _should_send_github_alert(self, severity: str) -> bool:
        """Determine if alert should be sent to GitHub based on severity."""
        severity_levels = ['info', 'warning', 'error', 'critical']
        threshold_index = severity_levels.index(self.github_alert_threshold)
        alert_index = severity_levels.index(severity) if severity in severity_levels else 0
        
        return alert_index >= threshold_index
    
    async def _send_github_alert(self, severity: str, message: str, context: Optional[Dict] = None):
        """Send alert to GitHub Actions."""
        if not self.enable_github_notifications or not self.workflow_run_id:
            return
        
        await self._log_to_github_actions(severity, message, context)
    
    async def _log_to_github_actions(self, level: str, message: str, context: Optional[Dict] = None):
        """Log message to GitHub Actions with appropriate formatting."""
        if not self.workflow_run_id:
            return
        
        try:
            # Format message for GitHub Actions
            github_message = f"[RETENTION] {message}"
            
            if context:
                # Add context as details
                context_str = json.dumps(context, indent=2)
                github_message += f"\n\nDetails:\n```json\n{context_str}\n```"
            
            # Map severity levels to GitHub Actions commands
            if level in ['error', 'critical']:
                print(f"::error::{github_message}")
            elif level == 'warning':
                print(f"::warning::{github_message}")
            else:
                print(f"::notice::{github_message}")
            
            # Also log to regular logger
            self.logger.info(f"GitHub Actions log [{level.upper()}]: {message}")
            
        except Exception as e:
            self.logger.error(f"Failed to log to GitHub Actions: {e}")
    
    async def create_github_issue_on_critical_failure(self, error_details: Dict[str, Any]):
        """Create GitHub issue for critical retention failures."""
        if not self.github_token or not self.enable_github_notifications:
            return
        
        try:
            # Prepare issue data
            title = f"🚨 Critical Retention System Failure - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            body = f"""
# Critical Retention System Failure

A critical failure has occurred in the dynamic model retention system.

## Error Details

```json
{json.dumps(error_details, indent=2)}
```

## System Metrics

```json
{json.dumps(self.retention_monitor.get_current_metrics_summary(), indent=2)}
```

## Recommended Actions

1. Check the retention monitoring logs for detailed error information
2. Verify Hugging Face API connectivity and rate limits
3. Check storage availability and permissions
4. Review recent configuration changes
5. Consider running the retention system in recovery mode

## Automatic Detection

This issue was automatically created by the retention monitoring system.
Workflow Run ID: {self.workflow_run_id}

---
*Generated by Dynamic Model Retention Monitoring System*
            """
            
            # Create issue via GitHub API
            issue_data = {
                'title': title,
                'body': body,
                'labels': ['bug', 'critical', 'retention-system', 'automated']
            }
            
            headers = {
                'Authorization': f'token {self.github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            url = f"https://api.github.com/repos/{self.github_repo}/issues"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=issue_data, headers=headers) as response:
                    if response.status == 201:
                        issue_data = await response.json()
                        issue_url = issue_data.get('html_url')
                        self.logger.info(f"✅ Created GitHub issue for critical failure: {issue_url}")
                        
                        # Log to GitHub Actions
                        await self._log_to_github_actions(
                            "error",
                            f"Critical failure issue created: {issue_url}",
                            {'issue_number': issue_data.get('number')}
                        )
                    else:
                        error_text = await response.text()
                        self.logger.error(f"❌ Failed to create GitHub issue: {response.status} - {error_text}")
        
        except Exception as e:
            self.logger.error(f"❌ Exception while creating GitHub issue: {e}")
    
    async def save_integrated_report(self):
        """Save integrated monitoring report."""
        try:
            report = await self.generate_integrated_report()
            
            # Save to retention monitoring system
            await self.retention_monitor.save_monitoring_report(report)
            
            # Also save to main reports directory if available
            reports_dir = Path("reports")
            reports_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_path = reports_dir / f"integrated_retention_report_{timestamp}.json"
            
            async with aiofiles.open(report_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(report, indent=2))
            
            self.logger.info(f"💾 Integrated report saved to {report_path}")
            
            # Log to GitHub Actions
            if self.workflow_run_id:
                await self._log_to_github_actions(
                    "notice",
                    f"Integrated monitoring report saved: {report_path.name}",
                    {'health_status': report.get('health_status', 'unknown')}
                )
        
        except Exception as e:
            self.logger.error(f"❌ Failed to save integrated report: {e}")


# Global instance for easy access
retention_integration = RetentionMonitoringIntegration()


# Convenience functions for easy integration
async def start_retention_operation(operation_type: str, context: Optional[Dict] = None):
    """Convenience function to start retention operation monitoring."""
    await retention_integration.start_retention_monitoring(operation_type, context)

async def end_retention_operation(success: bool = True, context: Optional[Dict] = None):
    """Convenience function to end retention operation monitoring."""
    await retention_integration.end_retention_monitoring(success, context)

async def log_api_call(endpoint: str, response_time_ms: float, success: bool, 
                      status_code: Optional[int] = None, error_message: Optional[str] = None):
    """Convenience function to log API calls."""
    await retention_integration.log_retention_api_call(
        endpoint, response_time_ms, success, status_code, error_message
    )

async def log_storage_metrics(used_mb: float, freed_mb: float = 0.0,
                            models_before: int = 0, models_after: int = 0):
    """Convenience function to log storage metrics."""
    await retention_integration.log_retention_storage_metrics(
        used_mb, freed_mb, models_before, models_after
    )

async def log_data_quality(recent_fetched: int, top_updated: int,
                         duplicates_removed: int, validation_errors: int):
    """Convenience function to log data quality metrics."""
    await retention_integration.log_retention_data_quality(
        recent_fetched, top_updated, duplicates_removed, validation_errors
    )

async def create_critical_failure_issue(error_details: Dict[str, Any]):
    """Convenience function to create GitHub issue for critical failures."""
    await retention_integration.create_github_issue_on_critical_failure(error_details)

async def save_monitoring_report():
    """Convenience function to save integrated monitoring report."""
    await retention_integration.save_integrated_report()