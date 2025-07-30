#!/usr/bin/env python3
"""
Robust Error Handling and Recovery System

This module provides comprehensive error handling, categorization, recovery mechanisms,
and reporting for the GGUF model synchronization system.
"""

import asyncio
import json
import logging
import random
import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union, Set
from pathlib import Path
import aiohttp
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

class ErrorCategory(Enum):
    """Categories of errors that can occur during synchronization."""
    NETWORK = "network"
    API = "api"
    DATA = "data"
    SYSTEM = "system"
    VALIDATION = "validation"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"

class ErrorSeverity(Enum):
    """Severity levels for errors."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class RecoveryAction(Enum):
    """Types of recovery actions that can be taken."""
    RETRY = "retry"
    SKIP = "skip"
    ABORT = "abort"
    FALLBACK = "fallback"
    NOTIFY = "notify"
    WAIT_AND_RETRY = "wait_and_retry"

@dataclass
class ErrorContext:
    """Context information for an error occurrence."""
    operation: str
    model_id: Optional[str] = None
    url: Optional[str] = None
    request_data: Optional[Dict[str, Any]] = None
    response_data: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    additional_info: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ErrorRecord:
    """Record of an error occurrence with categorization and context."""
    error: Exception
    category: ErrorCategory
    severity: ErrorSeverity
    context: ErrorContext
    recovery_action: RecoveryAction
    retry_count: int = 0
    resolved: bool = False
    resolution_time: Optional[datetime] = None
    error_id: str = field(default_factory=lambda: f"err_{int(time.time() * 1000)}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error record to dictionary for serialization."""
        return {
            'error_id': self.error_id,
            'error_type': type(self.error).__name__,
            'error_message': str(self.error),
            'category': self.category.value,
            'severity': self.severity.value,
            'context': {
                'operation': self.context.operation,
                'model_id': self.context.model_id,
                'url': self.context.url,
                'timestamp': self.context.timestamp.isoformat(),
                'additional_info': self.context.additional_info
            },
            'recovery_action': self.recovery_action.value,
            'retry_count': self.retry_count,
            'resolved': self.resolved,
            'resolution_time': self.resolution_time.isoformat() if self.resolution_time else None
        }

class ErrorClassifier:
    """Classifies errors into categories and determines severity."""
    
    def __init__(self):
        self.classification_rules = self._build_classification_rules()
    
    def classify_error(self, error: Exception, context: ErrorContext) -> tuple[ErrorCategory, ErrorSeverity]:
        """Classify an error and determine its severity."""
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        # Check each classification rule
        for rule in self.classification_rules:
            if rule['matcher'](error, error_str, error_type, context):
                return rule['category'], rule['severity']
        
        # Default classification
        return ErrorCategory.UNKNOWN, ErrorSeverity.MEDIUM
    
    def _build_classification_rules(self) -> List[Dict[str, Any]]:
        """Build classification rules for different error types."""
        return [
            # Network errors
            {
                'matcher': lambda e, s, t, c: any(indicator in s for indicator in [
                    'connection', 'network', 'dns', 'socket', 'timeout', 'unreachable'
                ]) or t in ['ConnectionError', 'TimeoutError', 'DNSError'],
                'category': ErrorCategory.NETWORK,
                'severity': ErrorSeverity.MEDIUM
            },
            
            # Rate limiting errors
            {
                'matcher': lambda e, s, t, c: any(indicator in s for indicator in [
                    '429', 'rate limit', 'too many requests', 'quota exceeded', 'throttled'
                ]) or (hasattr(e, 'status') and e.status == 429),
                'category': ErrorCategory.RATE_LIMIT,
                'severity': ErrorSeverity.LOW
            },
            
            # Authentication errors
            {
                'matcher': lambda e, s, t, c: any(indicator in s for indicator in [
                    '401', '403', 'unauthorized', 'forbidden', 'authentication', 'token'
                ]) or (hasattr(e, 'status') and e.status in [401, 403]),
                'category': ErrorCategory.AUTHENTICATION,
                'severity': ErrorSeverity.HIGH
            },
            
            # API errors
            {
                'matcher': lambda e, s, t, c: any(indicator in s for indicator in [
                    '400', '404', '500', '502', '503', '504', 'bad request', 'not found',
                    'internal server error', 'bad gateway', 'service unavailable'
                ]) or (hasattr(e, 'status') and 400 <= e.status < 600),
                'category': ErrorCategory.API,
                'severity': ErrorSeverity.MEDIUM  # Default severity for API errors
            },
            
            # Data validation errors
            {
                'matcher': lambda e, s, t, c: any(indicator in s for indicator in [
                    'validation', 'schema', 'invalid data', 'malformed', 'parse error'
                ]) or t in ['ValidationError', 'JSONDecodeError', 'ValueError'],
                'category': ErrorCategory.DATA,
                'severity': ErrorSeverity.MEDIUM
            },
            
            # System errors
            {
                'matcher': lambda e, s, t, c: any(indicator in s for indicator in [
                    'memory', 'disk', 'permission', 'file not found', 'access denied'
                ]) or t in ['MemoryError', 'PermissionError', 'FileNotFoundError'],
                'category': ErrorCategory.SYSTEM,
                'severity': ErrorSeverity.HIGH
            },
            
            # Timeout errors
            {
                'matcher': lambda e, s, t, c: 'timeout' in s or t in ['TimeoutError', 'asyncio.TimeoutError'],
                'category': ErrorCategory.TIMEOUT,
                'severity': ErrorSeverity.MEDIUM
            }
        ]
    
    def _determine_api_severity(self, error: Exception) -> ErrorSeverity:
        """Determine severity for API errors based on status code."""
        if hasattr(error, 'status'):
            if error.status in [400, 404]:  # Client errors that might be recoverable
                return ErrorSeverity.LOW
            elif error.status in [401, 403]:  # Authentication issues
                return ErrorSeverity.HIGH
            elif error.status >= 500:  # Server errors
                return ErrorSeverity.MEDIUM
        return ErrorSeverity.MEDIUM

class RetryStrategy(ABC):
    """Abstract base class for retry strategies."""
    
    @abstractmethod
    async def should_retry(self, error_record: ErrorRecord) -> bool:
        """Determine if an operation should be retried."""
        pass
    
    @abstractmethod
    async def calculate_delay(self, error_record: ErrorRecord) -> float:
        """Calculate delay before retry."""
        pass

class ExponentialBackoffStrategy(RetryStrategy):
    """Exponential backoff retry strategy with jitter."""
    
    def __init__(self, 
                 base_delay: float = 1.0,
                 max_delay: float = 60.0,
                 max_retries: int = 5,
                 jitter_factor: float = 0.1,
                 backoff_multiplier: float = 2.0):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.jitter_factor = jitter_factor
        self.backoff_multiplier = backoff_multiplier
    
    async def should_retry(self, error_record: ErrorRecord) -> bool:
        """Determine if operation should be retried based on error category and retry count."""
        # Don't retry if max retries exceeded
        if error_record.retry_count >= self.max_retries:
            return False
        
        # Don't retry critical authentication errors
        if (error_record.category == ErrorCategory.AUTHENTICATION and 
            error_record.severity == ErrorSeverity.CRITICAL):
            return False
        
        # Don't retry certain data errors
        if (error_record.category == ErrorCategory.DATA and 
            'malformed' in str(error_record.error).lower()):
            return False
        
        # Retry most other errors
        return error_record.category in [
            ErrorCategory.NETWORK,
            ErrorCategory.API,
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.TIMEOUT,
            ErrorCategory.SYSTEM
        ]
    
    async def calculate_delay(self, error_record: ErrorRecord) -> float:
        """Calculate exponential backoff delay with jitter."""
        base_wait = self.base_delay * (self.backoff_multiplier ** error_record.retry_count)
        max_wait = min(base_wait, self.max_delay)
        
        # Add jitter to prevent thundering herd
        jitter = random.uniform(0, self.jitter_factor * max_wait)
        total_wait = max_wait + jitter
        
        # Special handling for rate limit errors
        if error_record.category == ErrorCategory.RATE_LIMIT:
            # Longer delays for rate limiting
            total_wait *= 2
        
        return total_wait

class RecoveryProcedure(ABC):
    """Abstract base class for recovery procedures."""
    
    @abstractmethod
    async def can_recover(self, error_record: ErrorRecord) -> bool:
        """Check if this procedure can recover from the error."""
        pass
    
    @abstractmethod
    async def execute_recovery(self, error_record: ErrorRecord, context: Dict[str, Any]) -> bool:
        """Execute the recovery procedure."""
        pass

class NetworkRecoveryProcedure(RecoveryProcedure):
    """Recovery procedure for network-related errors."""
    
    async def can_recover(self, error_record: ErrorRecord) -> bool:
        return error_record.category == ErrorCategory.NETWORK
    
    async def execute_recovery(self, error_record: ErrorRecord, context: Dict[str, Any]) -> bool:
        """Attempt to recover from network errors."""
        logger.info(f"🔧 Attempting network recovery for error: {error_record.error_id}")
        
        # Wait for network to stabilize
        await asyncio.sleep(5)
        
        # Try alternative endpoints if available
        if 'alternative_endpoints' in context:
            logger.info("🔄 Trying alternative endpoints")
            return True
        
        # Check network connectivity
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://httpbin.org/status/200', timeout=10) as response:
                    if response.status == 200:
                        logger.info("✅ Network connectivity restored")
                        return True
        except Exception as e:
            logger.warning(f"❌ Network connectivity check failed: {e}")
        
        return False

class DataRecoveryProcedure(RecoveryProcedure):
    """Recovery procedure for data-related errors."""
    
    async def can_recover(self, error_record: ErrorRecord) -> bool:
        return error_record.category == ErrorCategory.DATA
    
    async def execute_recovery(self, error_record: ErrorRecord, context: Dict[str, Any]) -> bool:
        """Attempt to recover from data errors."""
        logger.info(f"🔧 Attempting data recovery for error: {error_record.error_id}")
        
        # Try to fix common data issues
        if 'model_data' in context:
            model_data = context['model_data']
            fixes_applied = False
            
            # Fix missing required fields
            if self._fix_missing_fields(model_data):
                logger.info("✅ Fixed missing data fields")
                fixes_applied = True
            
            # Fix data type issues
            if self._fix_data_types(model_data):
                logger.info("✅ Fixed data type issues")
                fixes_applied = True
            
            return fixes_applied
        
        return False
    
    def _fix_missing_fields(self, data: Dict[str, Any]) -> bool:
        """Fix missing required fields in model data."""
        fixes_applied = False
        
        # Add default values for missing fields
        defaults = {
            'downloads': 0,
            'likes': 0,
            'tags': [],
            'files': [],
            'description': '',
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        for field, default_value in defaults.items():
            if field not in data or data[field] is None:
                data[field] = default_value
                fixes_applied = True
        
        return fixes_applied
    
    def _fix_data_types(self, data: Dict[str, Any]) -> bool:
        """Fix data type issues in model data."""
        fixes_applied = False
        
        # Fix numeric fields
        for field in ['downloads', 'likes']:
            if field in data and isinstance(data[field], str):
                try:
                    data[field] = int(data[field])
                    fixes_applied = True
                except ValueError:
                    data[field] = 0
                    fixes_applied = True
        
        # Fix list fields
        for field in ['tags', 'files']:
            if field in data and not isinstance(data[field], list):
                data[field] = []
                fixes_applied = True
        
        return fixes_applied

@dataclass
class NotificationConfig:
    """Configuration for error notifications."""
    email_enabled: bool = False
    email_smtp_server: str = ""
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_recipients: List[str] = field(default_factory=list)
    
    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_headers: Dict[str, str] = field(default_factory=dict)
    
    log_file_path: str = "error_notifications.log"
    
    # Notification thresholds
    critical_error_threshold: int = 1  # Notify immediately for critical errors
    error_rate_threshold: float = 0.1  # Notify if error rate exceeds 10%
    consecutive_failures_threshold: int = 5  # Notify after 5 consecutive failures

class NotificationSystem:
    """System for sending notifications about critical errors."""
    
    def __init__(self, config: NotificationConfig):
        self.config = config
        self.notification_history: List[Dict[str, Any]] = []
        self.last_notification_time: Dict[str, float] = {}
        self.notification_cooldown = 300  # 5 minutes cooldown between similar notifications
    
    async def notify_critical_error(self, error_record: ErrorRecord, context: Dict[str, Any] = None):
        """Send notification for critical errors."""
        if error_record.severity != ErrorSeverity.CRITICAL:
            return
        
        notification_key = f"{error_record.category.value}_{type(error_record.error).__name__}"
        current_time = time.time()
        
        # Check cooldown
        if (notification_key in self.last_notification_time and 
            current_time - self.last_notification_time[notification_key] < self.notification_cooldown):
            return
        
        message = self._format_critical_error_message(error_record, context)
        
        # Send notifications
        await self._send_email_notification("Critical Error Alert", message)
        await self._send_webhook_notification(error_record, message)
        await self._log_notification(error_record, message)
        
        self.last_notification_time[notification_key] = current_time
    
    async def notify_error_pattern(self, pattern_description: str, error_records: List[ErrorRecord]):
        """Send notification for error patterns (e.g., high error rate)."""
        message = self._format_pattern_notification(pattern_description, error_records)
        
        await self._send_email_notification("Error Pattern Alert", message)
        await self._send_webhook_notification(None, message)
        await self._log_notification(None, message)
    
    def _format_critical_error_message(self, error_record: ErrorRecord, context: Dict[str, Any] = None) -> str:
        """Format critical error message for notifications."""
        message_parts = [
            f"🚨 CRITICAL ERROR ALERT 🚨",
            f"",
            f"Error ID: {error_record.error_id}",
            f"Category: {error_record.category.value}",
            f"Severity: {error_record.severity.value}",
            f"Error Type: {type(error_record.error).__name__}",
            f"Error Message: {str(error_record.error)}",
            f"",
            f"Context:",
            f"  Operation: {error_record.context.operation}",
            f"  Model ID: {error_record.context.model_id or 'N/A'}",
            f"  URL: {error_record.context.url or 'N/A'}",
            f"  Timestamp: {error_record.context.timestamp.isoformat()}",
            f"  Retry Count: {error_record.retry_count}",
            f"",
            f"Recovery Action: {error_record.recovery_action.value}",
        ]
        
        if context:
            message_parts.extend([
                f"",
                f"Additional Context:",
                json.dumps(context, indent=2, default=str)
            ])
        
        return "\n".join(message_parts)
    
    def _format_pattern_notification(self, pattern_description: str, error_records: List[ErrorRecord]) -> str:
        """Format error pattern notification message."""
        message_parts = [
            f"⚠️ ERROR PATTERN DETECTED ⚠️",
            f"",
            f"Pattern: {pattern_description}",
            f"Number of errors: {len(error_records)}",
            f"Time range: {min(r.context.timestamp for r in error_records)} to {max(r.context.timestamp for r in error_records)}",
            f"",
            f"Error breakdown:"
        ]
        
        # Group errors by category
        category_counts = {}
        for record in error_records:
            category = record.category.value
            category_counts[category] = category_counts.get(category, 0) + 1
        
        for category, count in category_counts.items():
            message_parts.append(f"  {category}: {count}")
        
        return "\n".join(message_parts)
    
    async def _send_email_notification(self, subject: str, message: str):
        """Send email notification if configured."""
        if not self.config.email_enabled or not self.config.email_recipients:
            return
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config.email_username
            msg['To'] = ', '.join(self.config.email_recipients)
            msg['Subject'] = f"GGUF Sync Alert: {subject}"
            
            msg.attach(MIMEText(message, 'plain'))
            
            with smtplib.SMTP(self.config.email_smtp_server, self.config.email_smtp_port) as server:
                server.starttls()
                server.login(self.config.email_username, self.config.email_password)
                server.send_message(msg)
            
            logger.info("📧 Email notification sent successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to send email notification: {e}")
    
    async def _send_webhook_notification(self, error_record: Optional[ErrorRecord], message: str):
        """Send webhook notification if configured."""
        if not self.config.webhook_enabled or not self.config.webhook_url:
            return
        
        try:
            payload = {
                'message': message,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error_record': error_record.to_dict() if error_record else None
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.webhook_url,
                    json=payload,
                    headers=self.config.webhook_headers,
                    timeout=10
                ) as response:
                    if response.status == 200:
                        logger.info("🔗 Webhook notification sent successfully")
                    else:
                        logger.warning(f"⚠️ Webhook notification failed with status: {response.status}")
        
        except Exception as e:
            logger.error(f"❌ Failed to send webhook notification: {e}")
    
    async def _log_notification(self, error_record: Optional[ErrorRecord], message: str):
        """Log notification to file."""
        try:
            log_entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'message': message,
                'error_record': error_record.to_dict() if error_record else None
            }
            
            with open(self.config.log_file_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry) + '\n')
            
        except Exception as e:
            logger.error(f"❌ Failed to log notification: {e}")

class ErrorRecoverySystem:
    """Comprehensive error handling and recovery system."""
    
    def __init__(self, 
                 retry_strategy: RetryStrategy = None,
                 notification_config: NotificationConfig = None):
        self.classifier = ErrorClassifier()
        self.retry_strategy = retry_strategy or ExponentialBackoffStrategy()
        self.notification_system = NotificationSystem(notification_config or NotificationConfig())
        
        # Recovery procedures
        self.recovery_procedures: List[RecoveryProcedure] = [
            NetworkRecoveryProcedure(),
            DataRecoveryProcedure()
        ]
        
        # Error tracking
        self.error_records: List[ErrorRecord] = []
        self.error_patterns: Dict[str, List[ErrorRecord]] = {}
        self.consecutive_failures = 0
        self.total_operations = 0
        self.start_time = time.time()
    
    async def handle_error(self, 
                          error: Exception, 
                          context: ErrorContext,
                          operation_func: Callable = None,
                          operation_args: tuple = None,
                          operation_kwargs: Dict[str, Any] = None) -> Any:
        """Handle an error with comprehensive recovery mechanisms."""
        # Classify the error
        category, severity = self.classifier.classify_error(error, context)
        
        # Determine recovery action
        recovery_action = self._determine_recovery_action(category, severity)
        
        # Create error record
        error_record = ErrorRecord(
            error=error,
            category=category,
            severity=severity,
            context=context,
            recovery_action=recovery_action
        )
        
        # Track the error
        self._track_error(error_record)
        
        logger.warning(f"🚨 Error occurred: {error_record.error_id}")
        logger.warning(f"   Category: {category.value}, Severity: {severity.value}")
        logger.warning(f"   Message: {str(error)}")
        logger.warning(f"   Recovery Action: {recovery_action.value}")
        
        # Handle based on recovery action
        if recovery_action == RecoveryAction.RETRY:
            return await self._handle_retry(error_record, operation_func, operation_args, operation_kwargs)
        elif recovery_action == RecoveryAction.WAIT_AND_RETRY:
            return await self._handle_wait_and_retry(error_record, operation_func, operation_args, operation_kwargs)
        elif recovery_action == RecoveryAction.FALLBACK:
            return await self._handle_fallback(error_record, context)
        elif recovery_action == RecoveryAction.NOTIFY:
            await self.notification_system.notify_critical_error(error_record)
            return None
        elif recovery_action == RecoveryAction.ABORT:
            await self.notification_system.notify_critical_error(error_record)
            raise error
        else:  # SKIP
            logger.info(f"⏭️ Skipping operation due to error: {error_record.error_id}")
            return None
    
    def _determine_recovery_action(self, category: ErrorCategory, severity: ErrorSeverity) -> RecoveryAction:
        """Determine the appropriate recovery action for an error."""
        # Critical errors require immediate notification
        if severity == ErrorSeverity.CRITICAL:
            return RecoveryAction.NOTIFY
        
        # Rate limiting requires waiting and retry
        if category == ErrorCategory.RATE_LIMIT:
            return RecoveryAction.WAIT_AND_RETRY
        
        # Network and API errors can usually be retried
        if category in [ErrorCategory.NETWORK, ErrorCategory.API, ErrorCategory.TIMEOUT]:
            return RecoveryAction.RETRY
        
        # Authentication errors should abort
        if category == ErrorCategory.AUTHENTICATION and severity == ErrorSeverity.HIGH:
            return RecoveryAction.ABORT
        
        # Data errors might be recoverable
        if category == ErrorCategory.DATA:
            return RecoveryAction.RETRY
        
        # System errors require notification
        if category == ErrorCategory.SYSTEM:
            return RecoveryAction.NOTIFY
        
        # Default to skip
        return RecoveryAction.SKIP
    
    async def _handle_retry(self, 
                           error_record: ErrorRecord,
                           operation_func: Callable,
                           operation_args: tuple,
                           operation_kwargs: Dict[str, Any]) -> Any:
        """Handle retry recovery action."""
        if not await self.retry_strategy.should_retry(error_record):
            logger.warning(f"❌ Max retries exceeded for error: {error_record.error_id}")
            return None
        
        # Attempt recovery procedures
        recovery_context = {
            'operation_func': operation_func,
            'operation_args': operation_args or (),
            'operation_kwargs': operation_kwargs or {}
        }
        
        for procedure in self.recovery_procedures:
            if await procedure.can_recover(error_record):
                logger.info(f"🔧 Attempting recovery with {type(procedure).__name__}")
                if await procedure.execute_recovery(error_record, recovery_context):
                    logger.info(f"✅ Recovery successful")
                    break
        
        # Increment retry count and retry
        error_record.retry_count += 1
        
        try:
            logger.info(f"🔄 Retrying operation (attempt {error_record.retry_count + 1})")
            result = await operation_func(*operation_args, **operation_kwargs)
            
            # Mark as resolved
            error_record.resolved = True
            error_record.resolution_time = datetime.now(timezone.utc)
            self.consecutive_failures = 0
            
            logger.info(f"✅ Retry successful for error: {error_record.error_id}")
            return result
            
        except Exception as retry_error:
            # Handle the retry error recursively
            retry_context = ErrorContext(
                operation=error_record.context.operation,
                model_id=error_record.context.model_id,
                additional_info={'original_error_id': error_record.error_id}
            )
            return await self.handle_error(retry_error, retry_context, operation_func, operation_args, operation_kwargs)
    
    async def _handle_wait_and_retry(self,
                                    error_record: ErrorRecord,
                                    operation_func: Callable,
                                    operation_args: tuple,
                                    operation_kwargs: Dict[str, Any]) -> Any:
        """Handle wait and retry recovery action."""
        if not await self.retry_strategy.should_retry(error_record):
            logger.warning(f"❌ Max retries exceeded for error: {error_record.error_id}")
            return None
        
        # Calculate delay
        delay = await self.retry_strategy.calculate_delay(error_record)
        logger.info(f"⏳ Waiting {delay:.2f}s before retry for error: {error_record.error_id}")
        await asyncio.sleep(delay)
        
        # Proceed with retry
        return await self._handle_retry(error_record, operation_func, operation_args, operation_kwargs)
    
    async def _handle_fallback(self, error_record: ErrorRecord, context: ErrorContext) -> Any:
        """Handle fallback recovery action."""
        logger.info(f"🔄 Attempting fallback for error: {error_record.error_id}")
        
        # Implement fallback strategies based on context
        if context.operation == "fetch_model_data":
            # Return minimal model data
            return {
                'id': context.model_id,
                'name': context.model_id,
                'description': 'Data unavailable due to sync error',
                'files': [],
                'downloads': 0,
                'likes': 0,
                'tags': [],
                'error_fallback': True
            }
        
        return None
    
    def _track_error(self, error_record: ErrorRecord):
        """Track error for pattern analysis and reporting."""
        self.error_records.append(error_record)
        self.total_operations += 1
        
        # Track consecutive failures
        if not error_record.resolved:
            self.consecutive_failures += 1
        
        # Track error patterns
        pattern_key = f"{error_record.category.value}_{type(error_record.error).__name__}"
        if pattern_key not in self.error_patterns:
            self.error_patterns[pattern_key] = []
        self.error_patterns[pattern_key].append(error_record)
        
        # Check for notification triggers
        asyncio.create_task(self._check_notification_triggers())
    
    async def _check_notification_triggers(self):
        """Check if any notification triggers have been met."""
        # Check consecutive failures threshold
        if self.consecutive_failures >= self.notification_system.config.consecutive_failures_threshold:
            await self.notification_system.notify_error_pattern(
                f"Consecutive failures threshold exceeded: {self.consecutive_failures}",
                self.error_records[-self.consecutive_failures:]
            )
        
        # Check error rate threshold
        if self.total_operations > 10:  # Only check after sufficient operations
            error_rate = len(self.error_records) / self.total_operations
            if error_rate > self.notification_system.config.error_rate_threshold:
                await self.notification_system.notify_error_pattern(
                    f"Error rate threshold exceeded: {error_rate:.2%}",
                    self.error_records
                )
    
    def generate_error_report(self) -> Dict[str, Any]:
        """Generate comprehensive error report."""
        current_time = time.time()
        elapsed_time = current_time - self.start_time
        
        # Calculate statistics
        total_errors = len(self.error_records)
        resolved_errors = sum(1 for r in self.error_records if r.resolved)
        error_rate = total_errors / self.total_operations if self.total_operations > 0 else 0
        resolution_rate = resolved_errors / total_errors if total_errors > 0 else 0
        
        # Group errors by category and severity
        category_stats = {}
        severity_stats = {}
        
        for record in self.error_records:
            # Category stats
            cat = record.category.value
            if cat not in category_stats:
                category_stats[cat] = {'total': 0, 'resolved': 0}
            category_stats[cat]['total'] += 1
            if record.resolved:
                category_stats[cat]['resolved'] += 1
            
            # Severity stats
            sev = record.severity.value
            if sev not in severity_stats:
                severity_stats[sev] = {'total': 0, 'resolved': 0}
            severity_stats[sev]['total'] += 1
            if record.resolved:
                severity_stats[sev]['resolved'] += 1
        
        # Most common error patterns
        pattern_frequency = {
            pattern: len(records) 
            for pattern, records in self.error_patterns.items()
        }
        top_patterns = sorted(pattern_frequency.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            'report_timestamp': datetime.now(timezone.utc).isoformat(),
            'sync_duration_seconds': elapsed_time,
            'total_operations': self.total_operations,
            'total_errors': total_errors,
            'resolved_errors': resolved_errors,
            'error_rate': error_rate,
            'resolution_rate': resolution_rate,
            'consecutive_failures': self.consecutive_failures,
            'category_breakdown': category_stats,
            'severity_breakdown': severity_stats,
            'top_error_patterns': top_patterns,
            'recent_errors': [
                record.to_dict() 
                for record in self.error_records[-10:]  # Last 10 errors
            ]
        }
    
    async def save_error_report(self, filepath: str = "error_report.json"):
        """Save error report to file."""
        report = self.generate_error_report()
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📊 Error report saved to: {filepath}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save error report: {e}")

# Convenience function for easy integration
async def with_error_handling(operation_func: Callable,
                             operation_name: str,
                             error_recovery_system: ErrorRecoverySystem,
                             model_id: str = None,
                             url: str = None,
                             *args, **kwargs) -> Any:
    """Execute an operation with comprehensive error handling."""
    context = ErrorContext(
        operation=operation_name,
        model_id=model_id,
        url=url
    )
    
    try:
        return await operation_func(*args, **kwargs)
    except Exception as e:
        return await error_recovery_system.handle_error(
            e, context, operation_func, args, kwargs
        )