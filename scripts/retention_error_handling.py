#!/usr/bin/env python3
"""
Comprehensive Error Handling and Recovery System for Dynamic Model Retention

This module provides specialized error handling, recovery mechanisms, circuit breaker
patterns, and rollback functionality specifically for the dynamic model retention system.
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union, Set
from pathlib import Path
import aiohttp
import random

# Import base error handling system
from error_handling import (
    ErrorRecoverySystem, ErrorContext, ErrorCategory, ErrorSeverity, 
    RecoveryAction, ErrorRecord, RetryStrategy, ExponentialBackoffStrategy,
    NotificationConfig, NotificationSystem
)

logger = logging.getLogger(__name__)

class RetentionErrorCategory(Enum):
    """Specific error categories for retention system."""
    API_RATE_LIMIT = "api_rate_limit"
    DATA_CORRUPTION = "data_corruption"
    STORAGE_FAILURE = "storage_failure"
    TOP_MODEL_UPDATE_FAILURE = "top_model_update_failure"
    RECENT_MODEL_EXTRACTION_FAILURE = "recent_model_extraction_failure"
    CLEANUP_FAILURE = "cleanup_failure"
    MERGE_FAILURE = "merge_failure"
    ROLLBACK_FAILURE = "rollback_failure"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"

@dataclass
class RetentionErrorContext(ErrorContext):
    """Extended error context for retention operations."""
    phase: Optional[str] = None  # top_models, recent_models, merge, cleanup
    models_processed: int = 0
    models_failed: int = 0
    storage_path: Optional[str] = None
    backup_available: bool = False
    rollback_point: Optional[str] = None

@dataclass
class CircuitBreakerState:
    """State tracking for circuit breaker pattern."""
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    failure_threshold: int = 5
    recovery_timeout: int = 300  # 5 minutes
    half_open_max_calls: int = 3
    half_open_calls: int = 0

class RetentionCircuitBreaker:
    """Circuit breaker implementation for API calls and critical operations."""
    
    def __init__(self, 
                 failure_threshold: int = 5,
                 recovery_timeout: int = 300,
                 half_open_max_calls: int = 3):
        self.states: Dict[str, CircuitBreakerState] = {}
        self.default_failure_threshold = failure_threshold
        self.default_recovery_timeout = recovery_timeout
        self.default_half_open_max_calls = half_open_max_calls
    
    def get_state(self, operation_key: str) -> CircuitBreakerState:
        """Get or create circuit breaker state for an operation."""
        if operation_key not in self.states:
            self.states[operation_key] = CircuitBreakerState(
                failure_threshold=self.default_failure_threshold,
                recovery_timeout=self.default_recovery_timeout,
                half_open_max_calls=self.default_half_open_max_calls
            )
        return self.states[operation_key]
    
    async def call(self, operation_key: str, operation: Callable, *args, **kwargs) -> Any:
        """Execute operation with circuit breaker protection."""
        state = self.get_state(operation_key)
        
        # Check if circuit is open
        if state.state == "OPEN":
            if self._should_attempt_reset(state):
                state.state = "HALF_OPEN"
                state.half_open_calls = 0
                logger.info(f"🔄 Circuit breaker for {operation_key} moving to HALF_OPEN")
            else:
                raise CircuitBreakerOpenError(f"Circuit breaker is OPEN for {operation_key}")
        
        # Handle half-open state
        if state.state == "HALF_OPEN":
            if state.half_open_calls >= state.half_open_max_calls:
                raise CircuitBreakerOpenError(f"Circuit breaker HALF_OPEN limit exceeded for {operation_key}")
            state.half_open_calls += 1
        
        try:
            result = await operation(*args, **kwargs)
            
            # Success - reset failure count
            if state.state == "HALF_OPEN":
                state.state = "CLOSED"
                logger.info(f"✅ Circuit breaker for {operation_key} reset to CLOSED")
            
            state.failure_count = 0
            state.last_failure_time = None
            
            return result
            
        except Exception as e:
            await self._record_failure(state, operation_key)
            raise e
    
    async def _record_failure(self, state: CircuitBreakerState, operation_key: str):
        """Record a failure and update circuit breaker state."""
        state.failure_count += 1
        state.last_failure_time = datetime.now(timezone.utc)
        
        if state.failure_count >= state.failure_threshold:
            state.state = "OPEN"
            logger.warning(f"🚨 Circuit breaker for {operation_key} opened after {state.failure_count} failures")
    
    def _should_attempt_reset(self, state: CircuitBreakerState) -> bool:
        """Check if circuit breaker should attempt reset."""
        if state.last_failure_time is None:
            return True
        
        time_since_failure = datetime.now(timezone.utc) - state.last_failure_time
        return time_since_failure.total_seconds() >= state.recovery_timeout

class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""
    pass

class RetentionRetryStrategy(ExponentialBackoffStrategy):
    """Specialized retry strategy for retention operations."""
    
    def __init__(self):
        super().__init__(
            base_delay=2.0,
            max_delay=120.0,
            max_retries=3,
            jitter_factor=0.2,
            backoff_multiplier=2.5
        )
    
    async def should_retry(self, error_record: ErrorRecord) -> bool:
        """Determine if retention operation should be retried."""
        # Don't retry if max retries exceeded
        if error_record.retry_count >= self.max_retries:
            return False
        
        # Special handling for retention-specific errors
        error_str = str(error_record.error).lower()
        
        # Always retry rate limit errors with longer delays
        if "rate limit" in error_str or "429" in error_str:
            return True
        
        # Retry network and API errors
        if error_record.category in [ErrorCategory.NETWORK, ErrorCategory.API]:
            return True
        
        # Don't retry data corruption errors
        if "corruption" in error_str or "malformed" in error_str:
            return False
        
        # Retry storage failures
        if "storage" in error_str or "file" in error_str:
            return True
        
        return super().should_retry(error_record)
    
    async def calculate_delay(self, error_record: ErrorRecord) -> float:
        """Calculate delay with special handling for retention operations."""
        base_delay = await super().calculate_delay(error_record)
        
        # Longer delays for rate limiting
        if "rate limit" in str(error_record.error).lower():
            return base_delay * 3
        
        # Shorter delays for storage operations
        if "storage" in str(error_record.error).lower():
            return base_delay * 0.5
        
        return base_delay

@dataclass
class RollbackPoint:
    """Represents a point in time that can be rolled back to."""
    timestamp: datetime
    phase: str
    data_snapshot: Dict[str, Any]
    file_backups: Dict[str, str]  # original_path -> backup_path
    description: str

class RetentionRollbackManager:
    """Manages rollback functionality for retention operations."""
    
    def __init__(self, backup_dir: str = "data/backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.rollback_points: List[RollbackPoint] = []
        self.max_rollback_points = 10
    
    async def create_rollback_point(self, phase: str, description: str, 
                                  files_to_backup: List[str] = None) -> str:
        """Create a rollback point before a critical operation."""
        timestamp = datetime.now(timezone.utc)
        rollback_id = f"rollback_{phase}_{int(timestamp.timestamp())}"
        
        file_backups = {}
        if files_to_backup:
            for file_path in files_to_backup:
                if Path(file_path).exists():
                    backup_path = self.backup_dir / f"{rollback_id}_{Path(file_path).name}"
                    await self._backup_file(file_path, str(backup_path))
                    file_backups[file_path] = str(backup_path)
        
        rollback_point = RollbackPoint(
            timestamp=timestamp,
            phase=phase,
            data_snapshot={},
            file_backups=file_backups,
            description=description
        )
        
        self.rollback_points.append(rollback_point)
        
        # Cleanup old rollback points
        if len(self.rollback_points) > self.max_rollback_points:
            old_point = self.rollback_points.pop(0)
            await self._cleanup_rollback_point(old_point)
        
        logger.info(f"📸 Created rollback point: {rollback_id}")
        return rollback_id
    
    async def rollback_to_point(self, rollback_id: str) -> bool:
        """Rollback to a specific rollback point."""
        rollback_point = None
        for point in self.rollback_points:
            if f"rollback_{point.phase}_{int(point.timestamp.timestamp())}" == rollback_id:
                rollback_point = point
                break
        
        if not rollback_point:
            logger.error(f"❌ Rollback point not found: {rollback_id}")
            return False
        
        try:
            logger.info(f"🔄 Rolling back to: {rollback_point.description}")
            
            # Restore files
            for original_path, backup_path in rollback_point.file_backups.items():
                if Path(backup_path).exists():
                    await self._restore_file(backup_path, original_path)
                    logger.info(f"✅ Restored file: {original_path}")
            
            logger.info(f"✅ Rollback completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Rollback failed: {e}")
            return False
    
    async def _backup_file(self, source_path: str, backup_path: str):
        """Create a backup of a file."""
        import shutil
        shutil.copy2(source_path, backup_path)
    
    async def _restore_file(self, backup_path: str, target_path: str):
        """Restore a file from backup."""
        import shutil
        shutil.copy2(backup_path, target_path)
    
    async def _cleanup_rollback_point(self, rollback_point: RollbackPoint):
        """Clean up files associated with a rollback point."""
        for backup_path in rollback_point.file_backups.values():
            try:
                Path(backup_path).unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"⚠️ Failed to cleanup backup file {backup_path}: {e}")

class RetentionFallbackManager:
    """Manages fallback mechanisms for failed operations."""
    
    def __init__(self, config_dir: str = "data"):
        self.config_dir = Path(config_dir)
        self.fallback_data_dir = self.config_dir / "fallback"
        self.fallback_data_dir.mkdir(parents=True, exist_ok=True)
    
    async def get_fallback_top_models(self) -> List[Dict[str, Any]]:
        """Get fallback top models from previous successful update."""
        fallback_file = self.fallback_data_dir / "last_successful_top_models.json"
        
        if not fallback_file.exists():
            logger.warning("⚠️ No fallback top models available")
            return []
        
        try:
            with open(fallback_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"📋 Using fallback top models from {data.get('timestamp', 'unknown')}")
            return data.get('models', [])
            
        except Exception as e:
            logger.error(f"❌ Failed to load fallback top models: {e}")
            return []
    
    async def save_successful_top_models(self, models: List[Dict[str, Any]]):
        """Save successful top models as fallback data."""
        fallback_file = self.fallback_data_dir / "last_successful_top_models.json"
        
        try:
            data = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'models': models,
                'count': len(models)
            }
            
            with open(fallback_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
            
            logger.info(f"💾 Saved {len(models)} top models as fallback data")
            
        except Exception as e:
            logger.error(f"❌ Failed to save fallback top models: {e}")
    
    async def get_fallback_recent_models(self, days_back: int = 7) -> List[Dict[str, Any]]:
        """Get fallback recent models by extending the time window."""
        logger.info(f"🔍 Attempting fallback recent models extraction with {days_back} days window")
        
        # This would integrate with the DateFilteredExtractor
        # For now, return empty list as placeholder
        return []
    
    async def use_cached_data(self, cache_key: str) -> Optional[List[Dict[str, Any]]]:
        """Use cached data as fallback."""
        cache_file = self.fallback_data_dir / f"cache_{cache_key}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if cache is not too old (24 hours)
            cache_time = datetime.fromisoformat(data['timestamp'])
            if datetime.now(timezone.utc) - cache_time > timedelta(hours=24):
                logger.warning(f"⚠️ Cache for {cache_key} is too old, ignoring")
                return None
            
            logger.info(f"📋 Using cached data for {cache_key}")
            return data.get('data', [])
            
        except Exception as e:
            logger.error(f"❌ Failed to load cached data for {cache_key}: {e}")
            return None

class RetentionErrorRecoverySystem(ErrorRecoverySystem):
    """Specialized error recovery system for retention operations."""
    
    def __init__(self, config_dir: str = "data"):
        # Initialize with retention-specific retry strategy
        super().__init__(
            retry_strategy=RetentionRetryStrategy(),
            notification_config=NotificationConfig()
        )
        
        # Add retention-specific components
        self.circuit_breaker = RetentionCircuitBreaker()
        self.rollback_manager = RetentionRollbackManager()
        self.fallback_manager = RetentionFallbackManager(config_dir)
        
        # Track retention-specific metrics
        self.phase_failures: Dict[str, int] = {}
        self.api_call_failures: Dict[str, int] = {}
        self.storage_failures: int = 0
    
    async def handle_api_rate_limit(self, error: Exception, context: RetentionErrorContext) -> Any:
        """Handle API rate limiting with exponential backoff and circuit breaker."""
        logger.warning(f"🚦 API rate limit encountered for {context.operation}")
        
        # Record rate limit failure
        operation_key = f"api_{context.operation}"
        self.api_call_failures[operation_key] = self.api_call_failures.get(operation_key, 0) + 1
        
        # Calculate backoff delay
        retry_count = self.api_call_failures[operation_key]
        base_delay = min(60 * (2 ** retry_count), 1800)  # Max 30 minutes
        jitter = random.uniform(0.8, 1.2)
        delay = base_delay * jitter
        
        logger.info(f"⏳ Waiting {delay:.1f}s before retrying API call")
        await asyncio.sleep(delay)
        
        return None
    
    async def handle_data_corruption(self, error: Exception, context: RetentionErrorContext) -> bool:
        """Handle data corruption with validation and recovery."""
        logger.error(f"🔧 Data corruption detected in {context.phase}: {error}")
        
        # Try to recover from rollback point
        if context.rollback_point:
            logger.info(f"🔄 Attempting rollback to: {context.rollback_point}")
            if await self.rollback_manager.rollback_to_point(context.rollback_point):
                return True
        
        # Try to use fallback data
        if context.phase == "top_models":
            fallback_models = await self.fallback_manager.get_fallback_top_models()
            if fallback_models:
                logger.info(f"📋 Using {len(fallback_models)} fallback top models")
                return True
        
        # Try cached data
        if context.storage_path:
            cache_key = Path(context.storage_path).stem
            cached_data = await self.fallback_manager.use_cached_data(cache_key)
            if cached_data:
                return True
        
        logger.error(f"❌ Unable to recover from data corruption")
        return False
    
    async def handle_storage_failure(self, error: Exception, context: RetentionErrorContext) -> bool:
        """Handle storage failures with alternative storage and recovery."""
        logger.error(f"💾 Storage failure in {context.phase}: {error}")
        self.storage_failures += 1
        
        # Try alternative storage location
        if context.storage_path:
            alternative_path = f"{context.storage_path}.backup"
            try:
                # Create alternative storage directory
                Path(alternative_path).parent.mkdir(parents=True, exist_ok=True)
                logger.info(f"📁 Using alternative storage: {alternative_path}")
                return True
            except Exception as alt_error:
                logger.error(f"❌ Alternative storage also failed: {alt_error}")
        
        # Try to recover from rollback
        if context.rollback_point:
            return await self.rollback_manager.rollback_to_point(context.rollback_point)
        
        return False
    
    async def handle_phase_failure(self, phase: str, error: Exception, 
                                 context: RetentionErrorContext) -> Dict[str, Any]:
        """Handle failure of an entire phase with comprehensive recovery."""
        logger.error(f"🚨 Phase failure in {phase}: {error}")
        
        self.phase_failures[phase] = self.phase_failures.get(phase, 0) + 1
        
        recovery_result = {
            'phase': phase,
            'recovered': False,
            'fallback_used': False,
            'rollback_performed': False,
            'error_message': str(error)
        }
        
        # Phase-specific recovery strategies
        if phase == "top_models":
            fallback_models = await self.fallback_manager.get_fallback_top_models()
            if fallback_models:
                recovery_result['recovered'] = True
                recovery_result['fallback_used'] = True
                recovery_result['data'] = fallback_models
        
        elif phase == "recent_models":
            # Try with extended time window
            fallback_models = await self.fallback_manager.get_fallback_recent_models(days_back=7)
            if fallback_models:
                recovery_result['recovered'] = True
                recovery_result['fallback_used'] = True
                recovery_result['data'] = fallback_models
        
        elif phase == "cleanup":
            # Cleanup failures are less critical, can be skipped
            logger.warning(f"⚠️ Skipping cleanup phase due to failure")
            recovery_result['recovered'] = True
            recovery_result['skipped'] = True
        
        # Try rollback if other methods failed
        if not recovery_result['recovered'] and context.rollback_point:
            if await self.rollback_manager.rollback_to_point(context.rollback_point):
                recovery_result['recovered'] = True
                recovery_result['rollback_performed'] = True
        
        return recovery_result
    
    async def with_circuit_breaker(self, operation_key: str, operation: Callable, 
                                 *args, **kwargs) -> Any:
        """Execute operation with circuit breaker protection."""
        try:
            return await self.circuit_breaker.call(operation_key, operation, *args, **kwargs)
        except CircuitBreakerOpenError as e:
            logger.error(f"🚨 Circuit breaker open: {e}")
            raise e
    
    async def create_phase_rollback_point(self, phase: str, files_to_backup: List[str] = None) -> str:
        """Create a rollback point before starting a phase."""
        description = f"Before {phase} phase execution"
        return await self.rollback_manager.create_rollback_point(phase, description, files_to_backup)
    
    def get_error_metrics(self) -> Dict[str, Any]:
        """Get comprehensive error metrics for monitoring."""
        return {
            'total_errors': len(self.error_records),
            'phase_failures': dict(self.phase_failures),
            'api_call_failures': dict(self.api_call_failures),
            'storage_failures': self.storage_failures,
            'circuit_breaker_states': {
                key: {
                    'state': state.state,
                    'failure_count': state.failure_count,
                    'last_failure': state.last_failure_time.isoformat() if state.last_failure_time else None
                }
                for key, state in self.circuit_breaker.states.items()
            },
            'consecutive_failures': self.consecutive_failures,
            'error_rate': len(self.error_records) / max(self.total_operations, 1),
            'uptime_seconds': time.time() - self.start_time
        }

# Decorator for easy error handling in retention operations
def with_retention_error_handling(phase: str = None, create_rollback: bool = False):
    """Decorator to add comprehensive error handling to retention operations."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Get or create error recovery system
            if not hasattr(wrapper, '_error_system'):
                wrapper._error_system = RetentionErrorRecoverySystem()
            
            error_system = wrapper._error_system
            
            # Create rollback point if requested
            rollback_id = None
            if create_rollback and phase:
                rollback_id = await error_system.create_phase_rollback_point(phase)
            
            # Create error context
            context = RetentionErrorContext(
                operation=func.__name__,
                phase=phase,
                rollback_point=rollback_id
            )
            
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                return await error_system.handle_error(e, context, func, args, kwargs)
        
        return wrapper
    return decorator

if __name__ == "__main__":
    # Example usage and testing
    async def test_retention_error_handling():
        """Test the retention error handling system."""
        error_system = RetentionErrorRecoverySystem()
        
        # Test circuit breaker
        async def failing_operation():
            raise Exception("Simulated API failure")
        
        try:
            await error_system.with_circuit_breaker("test_api", failing_operation)
        except Exception as e:
            print(f"Expected error: {e}")
        
        # Test rollback
        rollback_id = await error_system.create_phase_rollback_point("test_phase")
        print(f"Created rollback point: {rollback_id}")
        
        # Get metrics
        metrics = error_system.get_error_metrics()
        print(f"Error metrics: {json.dumps(metrics, indent=2, default=str)}")
    
    asyncio.run(test_retention_error_handling())