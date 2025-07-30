#!/usr/bin/env python3
"""
Data Completeness Verification and Monitoring System

This module implements comprehensive data completeness verification against
Hugging Face statistics, monitoring, and alerting capabilities.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from enum import Enum

import aiohttp
import aiofiles
from huggingface_hub import HfApi

logger = logging.getLogger(__name__)

class CompletenessStatus(Enum):
    """Status of completeness verification."""
    EXCELLENT = "excellent"  # >= 98%
    GOOD = "good"           # >= 95%
    WARNING = "warning"     # >= 90%
    CRITICAL = "critical"   # < 90%

class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"

@dataclass
class CompletenessMetrics:
    """Metrics for data completeness verification."""
    total_models_discovered: int = 0
    total_models_processed: int = 0
    total_models_with_gguf: int = 0
    huggingface_gguf_count: int = 0
    completeness_score: float = 0.0
    completeness_status: CompletenessStatus = CompletenessStatus.CRITICAL
    missing_models: List[str] = field(default_factory=list)
    failed_models: List[str] = field(default_factory=list)
    verification_time: float = 0.0
    last_verification: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Quality metrics
    models_with_complete_data: int = 0
    models_with_accessible_files: int = 0
    average_model_completeness: float = 0.0
    
    # Discovery strategy metrics
    discovery_coverage: Dict[str, int] = field(default_factory=dict)
    strategy_effectiveness: Dict[str, float] = field(default_factory=dict)

@dataclass
class MissingModelInfo:
    """Information about a missing model."""
    model_id: str
    expected_source: str
    last_seen: Optional[datetime] = None
    recovery_attempts: int = 0
    recovery_status: str = "pending"

@dataclass
class CompletenessAlert:
    """Alert for completeness issues."""
    severity: AlertSeverity
    title: str
    message: str
    timestamp: datetime
    metrics: Dict[str, Any] = field(default_factory=dict)
    suggested_actions: List[str] = field(default_factory=list)

class HuggingFaceStatsCollector:
    """Collects statistics from Hugging Face for comparison."""
    
    def __init__(self, api: HfApi, rate_limiter):
        self.api = api
        self.rate_limiter = rate_limiter
        self.stats_cache: Dict[str, Tuple[Any, datetime]] = {}
        self.cache_duration = 3600  # 1 hour cache
    
    async def get_total_gguf_models_count(self) -> int:
        """Get the total count of models with GGUF files from Hugging Face."""
        cache_key = "total_gguf_count"
        
        # Check cache first
        if cache_key in self.stats_cache:
            count, cached_time = self.stats_cache[cache_key]
            if (datetime.now(timezone.utc) - cached_time).total_seconds() < self.cache_duration:
                logger.debug(f"Using cached GGUF count: {count}")
                return count
        
        try:
            logger.info("🔍 Fetching total GGUF models count from Hugging Face...")
            
            async with self.rate_limiter:
                # Use the API to count models with GGUF filter
                models = list(self.api.list_models(
                    filter="gguf",
                    limit=None,  # Get all models to count them
                    sort="downloads",
                    direction=-1
                ))
            
            count = len(models)
            
            # Cache the result
            self.stats_cache[cache_key] = (count, datetime.now(timezone.utc))
            
            logger.info(f"📊 Total GGUF models on Hugging Face: {count}")
            return count
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch GGUF models count: {e}")
            # Return cached value if available, otherwise return 0
            if cache_key in self.stats_cache:
                count, _ = self.stats_cache[cache_key]
                logger.warning(f"⚠️ Using stale cached count: {count}")
                return count
            return 0
    
    async def get_model_statistics(self, model_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get detailed statistics for specific models."""
        stats = {}
        
        for model_id in model_ids[:10]:  # Limit to avoid rate limiting
            try:
                async with self.rate_limiter:
                    model_info = self.api.model_info(model_id)
                    
                stats[model_id] = {
                    'downloads': getattr(model_info, 'downloads', 0),
                    'likes': getattr(model_info, 'likes', 0),
                    'tags': getattr(model_info, 'tags', []),
                    'last_modified': getattr(model_info, 'lastModified', None),
                    'created_at': getattr(model_info, 'createdAt', None)
                }
                
                # Small delay to avoid overwhelming the API
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.debug(f"Could not fetch stats for {model_id}: {e}")
                stats[model_id] = {}
        
        return stats

class CompletenessVerifier:
    """Verifies data completeness against Hugging Face statistics."""
    
    def __init__(self, api: HfApi, rate_limiter, config: Dict[str, Any] = None):
        self.api = api
        self.rate_limiter = rate_limiter
        self.config = config or {}
        self.stats_collector = HuggingFaceStatsCollector(api, rate_limiter)
        self.metrics = CompletenessMetrics()
        self.missing_models: Dict[str, MissingModelInfo] = {}
        
        # Configuration
        self.min_completeness_threshold = self.config.get('min_completeness_threshold', 95.0)
        self.warning_threshold = self.config.get('warning_threshold', 90.0)
        self.excellent_threshold = self.config.get('excellent_threshold', 98.0)
    
    async def verify_completeness(self, processed_models: List[Dict[str, Any]], 
                                discovery_results: Optional[Dict[str, Any]] = None) -> CompletenessMetrics:
        """Perform comprehensive completeness verification."""
        start_time = time.time()
        logger.info("🔍 Starting data completeness verification...")
        
        # Reset metrics
        self.metrics = CompletenessMetrics()
        self.metrics.total_models_processed = len(processed_models)
        
        # Get Hugging Face statistics
        hf_gguf_count = await self.stats_collector.get_total_gguf_models_count()
        self.metrics.huggingface_gguf_count = hf_gguf_count
        
        # Count models with GGUF files
        models_with_gguf = [m for m in processed_models if m.get('files', [])]
        self.metrics.total_models_with_gguf = len(models_with_gguf)
        
        # Calculate basic completeness score
        if hf_gguf_count > 0:
            self.metrics.completeness_score = (self.metrics.total_models_with_gguf / hf_gguf_count) * 100
        else:
            self.metrics.completeness_score = 0.0
        
        # Determine completeness status
        self.metrics.completeness_status = self._determine_completeness_status(
            self.metrics.completeness_score
        )
        
        # Analyze discovery coverage if provided
        if discovery_results:
            await self._analyze_discovery_coverage(discovery_results)
        
        # Analyze model quality and completeness
        await self._analyze_model_quality(processed_models)
        
        # Detect missing models
        await self._detect_missing_models(processed_models, hf_gguf_count)
        
        self.metrics.verification_time = time.time() - start_time
        self.metrics.last_verification = datetime.now(timezone.utc)
        
        # Log verification results
        self._log_verification_results()
        
        return self.metrics
    
    def _determine_completeness_status(self, score: float) -> CompletenessStatus:
        """Determine completeness status based on score."""
        if score >= self.excellent_threshold:
            return CompletenessStatus.EXCELLENT
        elif score >= self.min_completeness_threshold:
            return CompletenessStatus.GOOD
        elif score >= self.warning_threshold:
            return CompletenessStatus.WARNING
        else:
            return CompletenessStatus.CRITICAL
    
    async def _analyze_discovery_coverage(self, discovery_results: Dict[str, Any]) -> None:
        """Analyze the effectiveness of different discovery strategies."""
        logger.info("📊 Analyzing discovery strategy coverage...")
        
        strategy_results = discovery_results.get('strategy_results', [])
        
        for result in strategy_results:
            strategy_name = result.get('strategy', 'unknown')
            models_found = len(result.get('models', []))
            success = result.get('success', False)
            
            self.metrics.discovery_coverage[strategy_name] = models_found
            
            if success and self.metrics.total_models_with_gguf > 0:
                effectiveness = (models_found / self.metrics.total_models_with_gguf) * 100
                self.metrics.strategy_effectiveness[strategy_name] = effectiveness
        
        # Log strategy effectiveness
        logger.info("🎯 Discovery strategy effectiveness:")
        for strategy, effectiveness in self.metrics.strategy_effectiveness.items():
            logger.info(f"   • {strategy}: {effectiveness:.1f}% coverage")
    
    async def _analyze_model_quality(self, processed_models: List[Dict[str, Any]]) -> None:
        """Analyze the quality and completeness of processed models."""
        logger.info("🔍 Analyzing model data quality...")
        
        complete_models = 0
        accessible_models = 0
        total_completeness = 0.0
        
        for model in processed_models:
            # Check data completeness
            validation_info = model.get('_validation', {})
            model_completeness = validation_info.get('completeness_score', 0.0)
            total_completeness += model_completeness
            
            if model_completeness >= 80.0:  # Consider 80%+ as complete
                complete_models += 1
            
            # Check file accessibility
            if validation_info.get('file_accessibility', {}).get('all_accessible', False):
                accessible_models += 1
        
        self.metrics.models_with_complete_data = complete_models
        self.metrics.models_with_accessible_files = accessible_models
        
        if processed_models:
            self.metrics.average_model_completeness = total_completeness / len(processed_models)
        
        logger.info(f"📊 Model quality analysis:")
        logger.info(f"   • Complete data: {complete_models}/{len(processed_models)} ({complete_models/len(processed_models)*100:.1f}%)")
        logger.info(f"   • Accessible files: {accessible_models}/{len(processed_models)} ({accessible_models/len(processed_models)*100:.1f}%)")
        logger.info(f"   • Average completeness: {self.metrics.average_model_completeness:.1f}%")
    
    async def _detect_missing_models(self, processed_models: List[Dict[str, Any]], 
                                   expected_count: int) -> None:
        """Detect potentially missing models."""
        logger.info("🔍 Detecting missing models...")
        
        processed_ids = {model.get('id', '') for model in processed_models}
        missing_count = max(0, expected_count - len(processed_models))
        
        if missing_count > 0:
            logger.warning(f"⚠️ Potentially missing {missing_count} models")
            
            # Try to identify specific missing models by sampling from HF
            try:
                # Get a sample of recent models from HF to identify missing ones
                async with self.rate_limiter:
                    recent_models = list(self.api.list_models(
                        filter="gguf",
                        limit=100,  # Sample recent models
                        sort="lastModified",
                        direction=-1
                    ))
                
                for model in recent_models:
                    if model.id not in processed_ids:
                        missing_info = MissingModelInfo(
                            model_id=model.id,
                            expected_source="huggingface_recent",
                            last_seen=getattr(model, 'lastModified', None)
                        )
                        self.missing_models[model.id] = missing_info
                        self.metrics.missing_models.append(model.id)
                
                logger.info(f"🔍 Identified {len(self.metrics.missing_models)} specific missing models")
                
            except Exception as e:
                logger.warning(f"⚠️ Could not identify specific missing models: {e}")
    
    def _log_verification_results(self) -> None:
        """Log comprehensive verification results."""
        logger.info("📊 === COMPLETENESS VERIFICATION RESULTS ===")
        logger.info(f"🎯 Completeness Score: {self.metrics.completeness_score:.2f}%")
        logger.info(f"📈 Status: {self.metrics.completeness_status.value.upper()}")
        logger.info(f"📊 Models Processed: {self.metrics.total_models_processed}")
        logger.info(f"🔍 Models with GGUF: {self.metrics.total_models_with_gguf}")
        logger.info(f"🌐 HuggingFace GGUF Count: {self.metrics.huggingface_gguf_count}")
        
        if self.metrics.missing_models:
            logger.warning(f"⚠️ Missing Models: {len(self.metrics.missing_models)}")
            logger.debug(f"   Examples: {self.metrics.missing_models[:5]}")
        
        logger.info(f"✅ Complete Data: {self.metrics.models_with_complete_data}/{self.metrics.total_models_processed}")
        logger.info(f"🔗 Accessible Files: {self.metrics.models_with_accessible_files}/{self.metrics.total_models_processed}")
        logger.info(f"⏱️ Verification Time: {self.metrics.verification_time:.1f}s")
        logger.info("=" * 50)

class MissingModelRecovery:
    """Handles recovery of missing models."""
    
    def __init__(self, api: HfApi, rate_limiter):
        self.api = api
        self.rate_limiter = rate_limiter
        self.recovery_attempts: Dict[str, int] = {}
        self.max_recovery_attempts = 3
    
    async def attempt_recovery(self, missing_models: Dict[str, MissingModelInfo]) -> Dict[str, Any]:
        """Attempt to recover missing models."""
        logger.info(f"🔄 Attempting recovery of {len(missing_models)} missing models...")
        
        recovered_models = []
        failed_recoveries = []
        
        for model_id, missing_info in missing_models.items():
            if missing_info.recovery_attempts >= self.max_recovery_attempts:
                logger.debug(f"⏭️ Skipping {model_id} - max recovery attempts reached")
                continue
            
            try:
                logger.info(f"🔄 Attempting recovery of {model_id}...")
                
                async with self.rate_limiter:
                    model_info = self.api.model_info(model_id)
                
                # Check if model actually has GGUF files
                if self._has_gguf_files(model_info):
                    recovered_models.append({
                        'id': model_id,
                        'recovery_method': 'direct_fetch',
                        'model_info': model_info
                    })
                    missing_info.recovery_status = "recovered"
                    logger.info(f"✅ Successfully recovered {model_id}")
                else:
                    missing_info.recovery_status = "no_gguf_files"
                    logger.debug(f"ℹ️ {model_id} exists but has no GGUF files")
                
                missing_info.recovery_attempts += 1
                await asyncio.sleep(0.2)  # Rate limiting
                
            except Exception as e:
                missing_info.recovery_attempts += 1
                missing_info.recovery_status = f"failed: {str(e)}"
                failed_recoveries.append(model_id)
                logger.debug(f"❌ Failed to recover {model_id}: {e}")
        
        logger.info(f"✅ Recovery complete: {len(recovered_models)} recovered, {len(failed_recoveries)} failed")
        
        return {
            'recovered_models': recovered_models,
            'failed_recoveries': failed_recoveries,
            'recovery_rate': len(recovered_models) / len(missing_models) * 100 if missing_models else 0
        }
    
    def _has_gguf_files(self, model_info) -> bool:
        """Check if a model has GGUF files."""
        try:
            # Check model files for GGUF extensions
            files = getattr(model_info, 'siblings', [])
            for file_info in files:
                filename = getattr(file_info, 'rfilename', '')
                if filename.lower().endswith('.gguf'):
                    return True
            return False
        except Exception:
            return False

class CompletenessAlertSystem:
    """Handles alerting for completeness issues."""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.alerts: List[CompletenessAlert] = []
        self.notification_channels = self.config.get('notification_channels', ['log'])
        self.alert_thresholds = {
            'critical_completeness': self.config.get('critical_threshold', 90.0),
            'warning_completeness': self.config.get('warning_threshold', 95.0),
            'missing_models_threshold': self.config.get('missing_models_threshold', 50)
        }
    
    async def evaluate_and_alert(self, metrics: CompletenessMetrics) -> List[CompletenessAlert]:
        """Evaluate metrics and generate alerts if necessary."""
        logger.info("🚨 Evaluating completeness metrics for alerts...")
        
        self.alerts.clear()
        
        # Check completeness score
        await self._check_completeness_score(metrics)
        
        # Check missing models
        await self._check_missing_models(metrics)
        
        # Check data quality
        await self._check_data_quality(metrics)
        
        # Send alerts
        if self.alerts:
            await self._send_alerts()
        else:
            logger.info("✅ No alerts generated - all metrics within acceptable ranges")
        
        return self.alerts
    
    async def _check_completeness_score(self, metrics: CompletenessMetrics) -> None:
        """Check completeness score and generate alerts."""
        score = metrics.completeness_score
        
        if score < self.alert_thresholds['critical_completeness']:
            alert = CompletenessAlert(
                severity=AlertSeverity.CRITICAL,
                title="Critical Data Completeness Issue",
                message=f"Data completeness is critically low: {score:.2f}% (threshold: {self.alert_thresholds['critical_completeness']}%)",
                timestamp=datetime.now(timezone.utc),
                metrics={
                    'completeness_score': score,
                    'threshold': self.alert_thresholds['critical_completeness'],
                    'missing_count': metrics.huggingface_gguf_count - metrics.total_models_with_gguf
                },
                suggested_actions=[
                    "Investigate discovery strategy failures",
                    "Check API rate limiting issues",
                    "Verify network connectivity",
                    "Consider running full sync mode"
                ]
            )
            self.alerts.append(alert)
            
        elif score < self.alert_thresholds['warning_completeness']:
            alert = CompletenessAlert(
                severity=AlertSeverity.WARNING,
                title="Data Completeness Warning",
                message=f"Data completeness below warning threshold: {score:.2f}% (threshold: {self.alert_thresholds['warning_completeness']}%)",
                timestamp=datetime.now(timezone.utc),
                metrics={
                    'completeness_score': score,
                    'threshold': self.alert_thresholds['warning_completeness']
                },
                suggested_actions=[
                    "Monitor next sync cycle",
                    "Review discovery strategy effectiveness",
                    "Check for temporary API issues"
                ]
            )
            self.alerts.append(alert)
    
    async def _check_missing_models(self, metrics: CompletenessMetrics) -> None:
        """Check for missing models and generate alerts."""
        missing_count = len(metrics.missing_models)
        
        if missing_count >= self.alert_thresholds['missing_models_threshold']:
            alert = CompletenessAlert(
                severity=AlertSeverity.WARNING,
                title="High Number of Missing Models",
                message=f"Detected {missing_count} missing models (threshold: {self.alert_thresholds['missing_models_threshold']})",
                timestamp=datetime.now(timezone.utc),
                metrics={
                    'missing_count': missing_count,
                    'threshold': self.alert_thresholds['missing_models_threshold'],
                    'examples': metrics.missing_models[:5]
                },
                suggested_actions=[
                    "Run missing model recovery procedure",
                    "Check discovery strategy coverage",
                    "Verify API access permissions"
                ]
            )
            self.alerts.append(alert)
    
    async def _check_data_quality(self, metrics: CompletenessMetrics) -> None:
        """Check data quality metrics and generate alerts."""
        if metrics.total_models_processed == 0:
            return
        
        complete_data_rate = (metrics.models_with_complete_data / metrics.total_models_processed) * 100
        accessible_files_rate = (metrics.models_with_accessible_files / metrics.total_models_processed) * 100
        
        if complete_data_rate < 80.0:
            alert = CompletenessAlert(
                severity=AlertSeverity.WARNING,
                title="Low Data Quality",
                message=f"Only {complete_data_rate:.1f}% of models have complete data",
                timestamp=datetime.now(timezone.utc),
                metrics={
                    'complete_data_rate': complete_data_rate,
                    'models_with_complete_data': metrics.models_with_complete_data,
                    'total_models': metrics.total_models_processed
                },
                suggested_actions=[
                    "Review data validation rules",
                    "Check API response completeness",
                    "Investigate data processing issues"
                ]
            )
            self.alerts.append(alert)
        
        if accessible_files_rate < 90.0:
            alert = CompletenessAlert(
                severity=AlertSeverity.WARNING,
                title="File Accessibility Issues",
                message=f"Only {accessible_files_rate:.1f}% of models have accessible files",
                timestamp=datetime.now(timezone.utc),
                metrics={
                    'accessible_files_rate': accessible_files_rate,
                    'models_with_accessible_files': metrics.models_with_accessible_files,
                    'total_models': metrics.total_models_processed
                },
                suggested_actions=[
                    "Check file URL validity",
                    "Verify network connectivity",
                    "Review file accessibility verification logic"
                ]
            )
            self.alerts.append(alert)
    
    async def _send_alerts(self) -> None:
        """Send alerts through configured channels."""
        logger.info(f"🚨 Sending {len(self.alerts)} alerts...")
        
        for alert in self.alerts:
            # Log alert (always enabled)
            severity_emoji = {
                AlertSeverity.INFO: "ℹ️",
                AlertSeverity.WARNING: "⚠️",
                AlertSeverity.CRITICAL: "🚨",
                AlertSeverity.EMERGENCY: "🆘"
            }
            
            emoji = severity_emoji.get(alert.severity, "🔔")
            logger.warning(f"{emoji} ALERT [{alert.severity.value.upper()}]: {alert.title}")
            logger.warning(f"   Message: {alert.message}")
            logger.warning(f"   Time: {alert.timestamp.isoformat()}")
            
            if alert.suggested_actions:
                logger.warning("   Suggested Actions:")
                for action in alert.suggested_actions:
                    logger.warning(f"     • {action}")
            
            # Additional notification channels could be implemented here
            # (email, Slack, webhooks, etc.)

class CompletenessMonitor:
    """Main completeness monitoring system coordinator."""
    
    def __init__(self, api: HfApi, rate_limiter, config: Dict[str, Any] = None):
        self.api = api
        self.rate_limiter = rate_limiter
        self.config = config or {}
        
        self.verifier = CompletenessVerifier(api, rate_limiter, config)
        self.recovery_system = MissingModelRecovery(api, rate_limiter)
        self.alert_system = CompletenessAlertSystem(config)
        
        self.monitoring_enabled = self.config.get('monitoring_enabled', True)
        self.auto_recovery_enabled = self.config.get('auto_recovery_enabled', True)
    
    async def perform_completeness_check(self, processed_models: List[Dict[str, Any]], 
                                       discovery_results: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Perform comprehensive completeness check and monitoring."""
        if not self.monitoring_enabled:
            logger.info("📊 Completeness monitoring is disabled")
            return {'monitoring_enabled': False}
        
        logger.info("🔍 Starting comprehensive completeness monitoring...")
        start_time = time.time()
        
        # Verify completeness
        metrics = await self.verifier.verify_completeness(processed_models, discovery_results)
        
        # Attempt recovery if enabled and needed
        recovery_results = {}
        if self.auto_recovery_enabled and metrics.missing_models:
            recovery_results = await self.recovery_system.attempt_recovery(
                self.verifier.missing_models
            )
        
        # Generate alerts
        alerts = await self.alert_system.evaluate_and_alert(metrics)
        
        # Compile comprehensive report
        monitoring_time = time.time() - start_time
        
        report = {
            'monitoring_enabled': True,
            'completeness_metrics': {
                'score': metrics.completeness_score,
                'status': metrics.completeness_status.value,
                'total_processed': metrics.total_models_processed,
                'total_with_gguf': metrics.total_models_with_gguf,
                'huggingface_count': metrics.huggingface_gguf_count,
                'missing_count': len(metrics.missing_models),
                'complete_data_count': metrics.models_with_complete_data,
                'accessible_files_count': metrics.models_with_accessible_files,
                'average_completeness': metrics.average_model_completeness,
                'verification_time': metrics.verification_time
            },
            'discovery_analysis': {
                'strategy_coverage': metrics.discovery_coverage,
                'strategy_effectiveness': metrics.strategy_effectiveness
            },
            'recovery_results': recovery_results,
            'alerts': [
                {
                    'severity': alert.severity.value,
                    'title': alert.title,
                    'message': alert.message,
                    'timestamp': alert.timestamp.isoformat(),
                    'metrics': alert.metrics,
                    'suggested_actions': alert.suggested_actions
                }
                for alert in alerts
            ],
            'monitoring_time': monitoring_time,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"✅ Completeness monitoring completed in {monitoring_time:.1f}s")
        return report
    
    async def save_completeness_metadata(self, report: Dict[str, Any], 
                                       output_file: str = "data/completeness_metadata.json") -> None:
        """Save completeness metadata to file."""
        try:
            # Ensure data directory exists
            data_dir = Path(output_file).parent
            data_dir.mkdir(exist_ok=True)
            
            async with aiofiles.open(output_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(report, indent=2))
            
            logger.info(f"💾 Completeness metadata saved to {output_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save completeness metadata: {e}")

# Export main classes and functions
__all__ = [
    'CompletenessMonitor',
    'CompletenessVerifier', 
    'CompletenessMetrics',
    'CompletenessStatus',
    'CompletenessAlert',
    'AlertSeverity',
    'MissingModelRecovery',
    'CompletenessAlertSystem'
]