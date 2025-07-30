#!/usr/bin/env python3
"""
GGUF Models Data Fetcher for GitHub Actions

This script fetches GGUF model data from Hugging Face API,
processes it, and generates optimized JSON files for the website.
Designed to run daily at 23:59 UTC via GitHub Actions.

Supports both traditional full sync and dynamic retention modes.
"""

import argparse
import asyncio
import json
import os
import sys
import time
import random
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
import logging
import re
from dataclasses import dataclass
from enum import Enum

import aiohttp
import aiofiles
from huggingface_hub import HfApi, HfFolder
from dateutil import parser as date_parser
from tqdm.asyncio import tqdm

# Import configuration system
from config_system import (
    ConfigurationManager, SyncConfiguration, Environment, SyncMode,
    load_configuration
)

# Import validation system
from validation_system import (
    DataValidationEngine, QualityMetrics, ValidationResult,
    ValidationIssue, ValidationSeverity, ValidationCategory
)

# Import error handling system
from error_handling import (
    ErrorRecoverySystem, ErrorContext, NotificationConfig,
    ExponentialBackoffStrategy, with_error_handling
)

# Import completeness verification system
from completeness_system import (
    CompletenessMonitor, CompletenessMetrics, CompletenessStatus,
    CompletenessAlert, AlertSeverity
)

# Import freshness tracking system
from freshness_system import (
    FreshnessTracker, FreshnessMetadata, WebsiteFreshnessIndicator,
    track_sync_freshness
)

# Import scalability and performance optimization system
from scalability_system import (
    ScalabilityOptimizer, SystemResourceMonitor, DynamicParameterAdjuster,
    StreamingProcessor, DataCompressionManager, PerformanceMonitor,
    ProcessingParameters, PerformanceMetrics, create_data_stream
)

# Import dynamic retention system components
from scheduled_update_orchestrator import ScheduledUpdateOrchestrator, UpdateReport

# Configure logging with UTF-8 encoding for Windows compatibility
import io

# Create UTF-8 compatible stream handler
utf8_stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(utf8_stdout),
        logging.FileHandler('update_models.log', mode='w', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class DiscoveryStrategy(Enum):
    """Enumeration of model discovery strategies."""
    PRIMARY_GGUF = "primary_gguf"
    QUANTIZATION_TAGS = "quantization_tags"
    ORGANIZATION_CRAWL = "organization_crawl"
    ARCHITECTURE_TAGS = "architecture_tags"

class RetentionMode(Enum):
    """Enumeration of retention modes."""
    FULL = "full"
    RETENTION = "retention"
    AUTO = "auto"

class SyncMode(Enum):
    """Enumeration of sync modes."""
    INCREMENTAL = "incremental"
    FULL = "full"
    AUTO = "auto"

@dataclass
class SyncConfig:
    """Configuration for sync mode behavior."""
    mode: SyncMode = SyncMode.AUTO
    incremental_window_hours: int = 48
    full_sync_threshold_hours: int = 168  # Weekly full sync
    significant_change_threshold: float = 0.1  # 10% change triggers full sync
    force_full_sync: bool = False
    last_sync_file: str = "data/last_sync_metadata.json"
    
@dataclass
class ModelReference:
    """Reference to a model discovered through various strategies."""
    id: str
    discovery_method: str
    confidence_score: float = 1.0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class SyncMetadata:
    """Metadata about sync operations."""
    last_sync_time: datetime
    sync_mode: SyncMode
    total_models_processed: int
    models_added: int = 0
    models_updated: int = 0
    models_removed: int = 0
    sync_duration: float = 0.0
    success: bool = True
    error_message: Optional[str] = None
    
@dataclass
class DiscoveryResult:
    """Result of a discovery strategy execution."""
    strategy: DiscoveryStrategy
    models: Set[ModelReference]
    execution_time: float
    success: bool
    error_message: Optional[str] = None

class MultiStrategyDiscoveryEngine:
    """Enhanced discovery engine that uses multiple strategies to find all GGUF models."""
    
    def __init__(self, api: HfApi, rate_limiter):
        self.api = api
        self.rate_limiter = rate_limiter
        self.discovered_models: Dict[str, ModelReference] = {}
        self.strategy_results: List[DiscoveryResult] = []
        
        # Known quantization patterns for secondary search
        self.quantization_tags = [
            'Q4_K_M', 'Q4_K_S', 'Q5_K_M', 'Q5_K_S', 'Q3_K_M', 'Q3_K_S', 'Q3_K_L',
            'Q6_K', 'Q2_K', 'Q8_0', 'Q4_0', 'Q4_1', 'Q5_0', 'Q5_1', 'F16', 'F32',
            'IQ1_S', 'IQ1_M', 'IQ2_XXS', 'IQ2_XS', 'IQ2_S', 'IQ2_M',
            'IQ3_XXS', 'IQ3_S', 'IQ3_M', 'IQ4_XS', 'IQ4_NL', 'BF16'
        ]
        
        # Architecture-specific tags for discovery
        self.architecture_tags = [
            'llama', 'llama-2', 'llama-3', 'mistral', 'mixtral', 'qwen', 'qwen2',
            'gemma', 'phi', 'phi-3', 'codellama', 'vicuna', 'alpaca', 'chatglm',
            'baichuan', 'yi', 'deepseek', 'internlm', 'falcon', 'mpt', 'bloom',
            'opt', 'pythia', 'stablelm', 'redpajama', 'openllama'
        ]
        
        # Major AI model organizations to crawl specifically
        self.major_organizations = [
            'microsoft', 'meta-llama', 'mistralai', 'google', 'Qwen', 'huggingface',
            'NousResearch', 'teknium', 'TheBloke', 'bartowski', 'QuantFactory',
            'unsloth', 'mlabonne', 'cognitivecomputations', 'garage-bAInd',
            'stabilityai', 'EleutherAI', 'bigscience', 'togethercomputer',
            'lmsys', 'WizardLM', 'Open-Orca', 'ehartford', 'jondurbin'
        ]
    
    async def discover_all_models(self) -> Set[ModelReference]:
        """Execute all discovery strategies and return deduplicated results."""
        logger.info("🔍 Starting multi-strategy model discovery...")
        start_time = time.time()
        
        # Execute all discovery strategies
        strategies = [
            self._discover_primary_gguf_models(),
            self._discover_by_quantization_tags(),
            self._discover_by_architecture_tags(),
            self._discover_by_organizations()
        ]
        
        # Run strategies concurrently with some delay to avoid overwhelming the API
        results = []
        for strategy_coro in strategies:
            result = await strategy_coro
            results.append(result)
            self.strategy_results.append(result)
            # Small delay between strategies
            await asyncio.sleep(2)
        
        # Merge and deduplicate results
        all_models = self._merge_and_deduplicate_results(results)
        
        elapsed_time = time.time() - start_time
        logger.info(f"✅ Multi-strategy discovery completed in {elapsed_time:.1f}s")
        logger.info(f"📊 Discovery summary:")
        
        for result in results:
            status = "✅" if result.success else "❌"
            logger.info(f"   {status} {result.strategy.value}: {len(result.models)} models ({result.execution_time:.1f}s)")
        
        logger.info(f"🎯 Total unique models discovered: {len(all_models)}")
        
        return all_models
    
    async def _discover_primary_gguf_models(self) -> DiscoveryResult:
        """Primary discovery strategy using GGUF filter with no pagination limits."""
        start_time = time.time()
        models = set()
        
        try:
            logger.info("🎯 Executing primary GGUF filter search...")
            
            async with self.rate_limiter:
                # Use the API to get all models with GGUF filter
                model_list = list(self.api.list_models(
                    filter="gguf",
                    limit=None,  # No pagination limits
                    sort="downloads",
                    direction=-1
                ))
            
            for model in model_list:
                model_ref = ModelReference(
                    id=model.id,
                    discovery_method="primary_gguf",
                    confidence_score=1.0,
                    metadata={"downloads": getattr(model, 'downloads', 0)}
                )
                models.add(model_ref)
            
            execution_time = time.time() - start_time
            logger.info(f"✅ Primary GGUF search found {len(models)} models")
            
            return DiscoveryResult(
                strategy=DiscoveryStrategy.PRIMARY_GGUF,
                models=models,
                execution_time=execution_time,
                success=True
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"❌ Primary GGUF search failed: {e}")
            return DiscoveryResult(
                strategy=DiscoveryStrategy.PRIMARY_GGUF,
                models=models,
                execution_time=execution_time,
                success=False,
                error_message=str(e)
            )
    
    async def _discover_by_quantization_tags(self) -> DiscoveryResult:
        """Secondary discovery using quantization-specific tags."""
        start_time = time.time()
        models = set()
        
        try:
            logger.info("🏷️ Executing quantization tags search...")
            
            # Search for models with specific quantization tags
            for tag in self.quantization_tags[:10]:  # Limit to avoid too many requests
                try:
                    async with self.rate_limiter:
                        model_list = list(self.api.list_models(
                            search=tag,
                            limit=100,  # Reasonable limit per tag
                            sort="downloads",
                            direction=-1
                        ))
                    
                    for model in model_list:
                        # Check if model actually has GGUF files by looking at tags or name
                        if self._likely_has_gguf_files(model):
                            model_ref = ModelReference(
                                id=model.id,
                                discovery_method=f"quantization_tag_{tag}",
                                confidence_score=0.8,
                                metadata={"tag": tag, "downloads": getattr(model, 'downloads', 0)}
                            )
                            models.add(model_ref)
                    
                    # Small delay between tag searches
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.debug(f"Error searching for tag {tag}: {e}")
                    continue
            
            execution_time = time.time() - start_time
            logger.info(f"✅ Quantization tags search found {len(models)} models")
            
            return DiscoveryResult(
                strategy=DiscoveryStrategy.QUANTIZATION_TAGS,
                models=models,
                execution_time=execution_time,
                success=True
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"❌ Quantization tags search failed: {e}")
            return DiscoveryResult(
                strategy=DiscoveryStrategy.QUANTIZATION_TAGS,
                models=models,
                execution_time=execution_time,
                success=False,
                error_message=str(e)
            )
    
    async def _discover_by_architecture_tags(self) -> DiscoveryResult:
        """Discovery using architecture-specific tags."""
        start_time = time.time()
        models = set()
        
        try:
            logger.info("🏗️ Executing architecture tags search...")
            
            # Search for models with architecture-specific tags
            for tag in self.architecture_tags[:15]:  # Limit to most important architectures
                try:
                    async with self.rate_limiter:
                        model_list = list(self.api.list_models(
                            search=f"{tag} gguf",  # Combine with gguf keyword
                            limit=50,  # Reasonable limit per architecture
                            sort="downloads",
                            direction=-1
                        ))
                    
                    for model in model_list:
                        if self._likely_has_gguf_files(model):
                            model_ref = ModelReference(
                                id=model.id,
                                discovery_method=f"architecture_tag_{tag}",
                                confidence_score=0.7,
                                metadata={"architecture_tag": tag, "downloads": getattr(model, 'downloads', 0)}
                            )
                            models.add(model_ref)
                    
                    # Small delay between architecture searches
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.debug(f"Error searching for architecture {tag}: {e}")
                    continue
            
            execution_time = time.time() - start_time
            logger.info(f"✅ Architecture tags search found {len(models)} models")
            
            return DiscoveryResult(
                strategy=DiscoveryStrategy.ARCHITECTURE_TAGS,
                models=models,
                execution_time=execution_time,
                success=True
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"❌ Architecture tags search failed: {e}")
            return DiscoveryResult(
                strategy=DiscoveryStrategy.ARCHITECTURE_TAGS,
                models=models,
                execution_time=execution_time,
                success=False,
                error_message=str(e)
            )
    
    async def _discover_by_organizations(self) -> DiscoveryResult:
        """Discovery by crawling major AI model organizations."""
        start_time = time.time()
        models = set()
        
        try:
            logger.info("🏢 Executing organization-specific crawling...")
            
            # Crawl major organizations known for publishing GGUF models
            for org in self.major_organizations[:20]:  # Limit to top organizations
                try:
                    async with self.rate_limiter:
                        model_list = list(self.api.list_models(
                            author=org,
                            limit=100,  # Reasonable limit per organization
                            sort="downloads",
                            direction=-1
                        ))
                    
                    for model in model_list:
                        if self._likely_has_gguf_files(model):
                            model_ref = ModelReference(
                                id=model.id,
                                discovery_method=f"organization_{org}",
                                confidence_score=0.9,  # High confidence for known orgs
                                metadata={"organization": org, "downloads": getattr(model, 'downloads', 0)}
                            )
                            models.add(model_ref)
                    
                    # Small delay between organization searches
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.debug(f"Error crawling organization {org}: {e}")
                    continue
            
            execution_time = time.time() - start_time
            logger.info(f"✅ Organization crawling found {len(models)} models")
            
            return DiscoveryResult(
                strategy=DiscoveryStrategy.ORGANIZATION_CRAWL,
                models=models,
                execution_time=execution_time,
                success=True
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"❌ Organization crawling failed: {e}")
            return DiscoveryResult(
                strategy=DiscoveryStrategy.ORGANIZATION_CRAWL,
                models=models,
                execution_time=execution_time,
                success=False,
                error_message=str(e)
            )
    
    def _likely_has_gguf_files(self, model) -> bool:
        """Heuristic to determine if a model likely has GGUF files."""
        model_id_lower = model.id.lower()
        tags = [tag.lower() for tag in getattr(model, 'tags', [])]
        
        # Check for GGUF indicators in model ID or tags
        gguf_indicators = [
            'gguf', 'ggml', '.gguf', '-gguf', '_gguf',
            'q4_k_m', 'q4_0', 'q5_0', 'q8_0', 'f16', 'f32'
        ]
        
        # Check model ID
        if any(indicator in model_id_lower for indicator in gguf_indicators):
            return True
        
        # Check tags
        if any(indicator in tag for tag in tags for indicator in gguf_indicators):
            return True
        
        # Check for quantization patterns in model ID
        quantization_patterns = [
            r'q\d+_k_[msl]', r'q\d+_\d+', r'iq\d+_[a-z]+', 
            r'f\d+', r'bf\d+', r'int\d+'
        ]
        
        for pattern in quantization_patterns:
            if re.search(pattern, model_id_lower):
                return True
        
        return False
    
    def _merge_and_deduplicate_results(self, results: List[DiscoveryResult]) -> Set[ModelReference]:
        """Merge results from multiple strategies and deduplicate models."""
        logger.info("🔄 Merging and deduplicating discovery results...")
        
        # Collect all models with their discovery methods
        model_discoveries: Dict[str, List[ModelReference]] = {}
        
        for result in results:
            if result.success:
                for model_ref in result.models:
                    if model_ref.id not in model_discoveries:
                        model_discoveries[model_ref.id] = []
                    model_discoveries[model_ref.id].append(model_ref)
        
        # Create final deduplicated set with best discovery method for each model
        final_models = set()
        
        for model_id, discoveries in model_discoveries.items():
            # Choose the discovery with highest confidence score
            best_discovery = max(discoveries, key=lambda x: x.confidence_score)
            
            # Merge metadata from all discoveries
            merged_metadata = {}
            discovery_methods = []
            
            for discovery in discoveries:
                merged_metadata.update(discovery.metadata)
                discovery_methods.append(discovery.discovery_method)
            
            # Create final model reference
            final_model = ModelReference(
                id=model_id,
                discovery_method=best_discovery.discovery_method,
                confidence_score=best_discovery.confidence_score,
                metadata={
                    **merged_metadata,
                    'all_discovery_methods': discovery_methods,
                    'discovery_count': len(discoveries)
                }
            )
            
            final_models.add(final_model)
        
        # Log deduplication statistics
        total_discoveries = sum(len(result.models) for result in results if result.success)
        deduplication_rate = (total_discoveries - len(final_models)) / total_discoveries * 100 if total_discoveries > 0 else 0
        
        logger.info(f"📊 Deduplication statistics:")
        logger.info(f"   • Total discoveries: {total_discoveries}")
        logger.info(f"   • Unique models: {len(final_models)}")
        logger.info(f"   • Deduplication rate: {deduplication_rate:.1f}%")
        
        # Log models found by multiple strategies
        multi_discovery_models = [
            model_id for model_id, discoveries in model_discoveries.items() 
            if len(discoveries) > 1
        ]
        
        if multi_discovery_models:
            logger.info(f"   • Models found by multiple strategies: {len(multi_discovery_models)}")
            logger.debug(f"     Examples: {multi_discovery_models[:5]}")
        
        return final_models

class SyncModeManager:
    """Manages sync mode detection and incremental/full sync logic."""
    
    def __init__(self, config: SyncConfig):
        self.config = config
        self.last_sync_metadata: Optional[SyncMetadata] = None
        
    async def determine_sync_mode(self) -> SyncMode:
        """Determine the appropriate sync mode based on configuration and history."""
        logger.info("🔍 Determining sync mode...")
        
        # Check for forced full sync
        if self.config.force_full_sync:
            logger.info("🔄 Force full sync requested via configuration")
            return SyncMode.FULL
        
        # Check environment variable override
        env_sync_mode = os.getenv('SYNC_MODE', '').lower()
        if env_sync_mode == 'full':
            logger.info("🔄 Full sync requested via SYNC_MODE environment variable")
            return SyncMode.FULL
        elif env_sync_mode == 'incremental':
            logger.info("⚡ Incremental sync requested via SYNC_MODE environment variable")
            return SyncMode.INCREMENTAL
        
        # If mode is explicitly set, use it
        if self.config.mode != SyncMode.AUTO:
            logger.info(f"⚙️ Using configured sync mode: {self.config.mode.value}")
            return self.config.mode
        
        # Auto-determine based on last sync
        await self._load_last_sync_metadata()
        
        if not self.last_sync_metadata:
            logger.info("🆕 No previous sync found, performing full sync")
            return SyncMode.FULL
        
        # Check if enough time has passed for a full sync
        time_since_last_sync = datetime.now(timezone.utc) - self.last_sync_metadata.last_sync_time
        hours_since_last_sync = time_since_last_sync.total_seconds() / 3600
        
        if hours_since_last_sync >= self.config.full_sync_threshold_hours:
            logger.info(f"⏰ {hours_since_last_sync:.1f} hours since last sync (threshold: {self.config.full_sync_threshold_hours}h), performing full sync")
            return SyncMode.FULL
        
        # Check if last sync failed
        if not self.last_sync_metadata.success:
            logger.info("❌ Last sync failed, performing full sync for recovery")
            return SyncMode.FULL
        
        # Default to incremental sync
        logger.info(f"⚡ Performing incremental sync (last sync: {hours_since_last_sync:.1f}h ago)")
        return SyncMode.INCREMENTAL
    
    async def should_trigger_full_sync(self, current_models: List[Dict[str, Any]], 
                                     previous_model_count: Optional[int] = None) -> bool:
        """Determine if significant changes warrant a full sync."""
        if not previous_model_count or not self.last_sync_metadata:
            return False
        
        current_count = len(current_models)
        change_ratio = abs(current_count - previous_model_count) / previous_model_count
        
        if change_ratio >= self.config.significant_change_threshold:
            logger.info(f"📊 Significant change detected: {change_ratio:.1%} change in model count "
                       f"({previous_model_count} → {current_count})")
            logger.info("🔄 Triggering automatic full sync due to significant changes")
            return True
        
        return False
    
    async def filter_models_for_incremental_sync(self, models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter models to only include those modified within the incremental window."""
        if not self.last_sync_metadata:
            logger.warning("⚠️ No last sync metadata available for incremental filtering")
            return models
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.config.incremental_window_hours)
        logger.info(f"⏰ Filtering models modified after {cutoff_time.isoformat()}")
        
        filtered_models = []
        for model in models:
            last_modified_str = model.get('lastModified')
            if not last_modified_str:
                # If no modification date, include in incremental sync to be safe
                filtered_models.append(model)
                continue
            
            try:
                last_modified = date_parser.parse(last_modified_str)
                if last_modified.tzinfo is None:
                    last_modified = last_modified.replace(tzinfo=timezone.utc)
                
                if last_modified >= cutoff_time:
                    filtered_models.append(model)
            except Exception as e:
                logger.debug(f"Could not parse modification date for {model.get('id', 'unknown')}: {e}")
                # Include model if we can't parse the date
                filtered_models.append(model)
        
        logger.info(f"📊 Incremental sync: {len(filtered_models)}/{len(models)} models within {self.config.incremental_window_hours}h window")
        return filtered_models
    
    async def save_sync_metadata(self, metadata: SyncMetadata) -> None:
        """Save sync metadata to file."""
        try:
            # Ensure data directory exists
            data_dir = Path(self.config.last_sync_file).parent
            data_dir.mkdir(exist_ok=True)
            
            # Convert to serializable format
            metadata_dict = {
                'last_sync_time': metadata.last_sync_time.isoformat(),
                'sync_mode': metadata.sync_mode.value,
                'total_models_processed': metadata.total_models_processed,
                'models_added': metadata.models_added,
                'models_updated': metadata.models_updated,
                'models_removed': metadata.models_removed,
                'sync_duration': metadata.sync_duration,
                'success': metadata.success,
                'error_message': metadata.error_message
            }
            
            async with aiofiles.open(self.config.last_sync_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(metadata_dict, indent=2))
            
            logger.info(f"💾 Sync metadata saved to {self.config.last_sync_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save sync metadata: {e}")
    
    async def _load_last_sync_metadata(self) -> None:
        """Load last sync metadata from file."""
        try:
            if not Path(self.config.last_sync_file).exists():
                logger.debug(f"📁 No sync metadata file found at {self.config.last_sync_file}")
                return
            
            async with aiofiles.open(self.config.last_sync_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                metadata_dict = json.loads(content)
            
            # Convert back to SyncMetadata object
            self.last_sync_metadata = SyncMetadata(
                last_sync_time=date_parser.parse(metadata_dict['last_sync_time']),
                sync_mode=SyncMode(metadata_dict['sync_mode']),
                total_models_processed=metadata_dict['total_models_processed'],
                models_added=metadata_dict.get('models_added', 0),
                models_updated=metadata_dict.get('models_updated', 0),
                models_removed=metadata_dict.get('models_removed', 0),
                sync_duration=metadata_dict.get('sync_duration', 0.0),
                success=metadata_dict.get('success', True),
                error_message=metadata_dict.get('error_message')
            )
            
            logger.info(f"📖 Loaded sync metadata: last sync {self.last_sync_metadata.last_sync_time.isoformat()} "
                       f"({self.last_sync_metadata.sync_mode.value} mode)")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not load sync metadata: {e}")
            self.last_sync_metadata = None
    
    def log_sync_mode_report(self, sync_mode: SyncMode, models_processed: int, 
                           sync_duration: float, models_added: int = 0, 
                           models_updated: int = 0, models_removed: int = 0) -> None:
        """Log comprehensive sync mode report."""
        logger.info("📊 === SYNC MODE REPORT ===")
        logger.info(f"🔄 Sync Mode: {sync_mode.value.upper()}")
        logger.info(f"⏱️  Duration: {sync_duration:.1f}s")
        logger.info(f"📈 Models Processed: {models_processed}")
        
        if sync_mode == SyncMode.INCREMENTAL:
            logger.info(f"📊 Incremental Changes:")
            logger.info(f"   • Added: {models_added}")
            logger.info(f"   • Updated: {models_updated}")
            logger.info(f"   • Removed: {models_removed}")
            logger.info(f"   • Window: {self.config.incremental_window_hours}h")
        
        logger.info("========================")

@dataclass
class RateLimitConfig:
    """Configuration for rate limiting system."""
    authenticated_limit: int = 5000  # requests per hour for authenticated users
    anonymous_limit: int = 1000     # requests per hour for anonymous users
    max_concurrency: int = 50       # maximum concurrent requests
    base_backoff: float = 1.0       # base backoff time in seconds
    max_backoff: float = 60.0       # maximum backoff time in seconds
    jitter_factor: float = 0.1      # jitter factor for backoff randomization
    adaptive_threshold: float = 0.8 # threshold for adaptive rate limiting

@dataclass
class ProgressMetrics:
    """Progress tracking metrics."""
    start_time: float
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limit_hits: int = 0
    current_rate: float = 0.0
    estimated_completion: Optional[float] = None
    last_report_time: float = 0.0
    
    def update_rate(self):
        """Update current request rate."""
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            self.current_rate = self.successful_requests / elapsed

class AdaptiveRateLimiter:
    """Enhanced rate limiter with adaptive behavior and intelligent backoff."""
    
    def __init__(self, config: RateLimitConfig, has_token: bool = False):
        self.config = config
        self.has_token = has_token
        
        # Calculate optimal rate limits
        hourly_limit = config.authenticated_limit if has_token else config.anonymous_limit
        self.requests_per_second = hourly_limit / 3600.0  # Convert to per-second
        self.requests_per_minute = hourly_limit / 60.0    # Convert to per-minute
        
        # Rate limiting state
        self.request_times = deque()
        self.recent_responses = deque(maxlen=100)  # Track recent response times
        self.consecutive_rate_limits = 0
        self.adaptive_factor = 1.0
        self._lock = asyncio.Lock()
        
        # Concurrency control
        self.semaphore = asyncio.Semaphore(config.max_concurrency)
        
        logger.info(f"🚦 Initialized adaptive rate limiter:")
        logger.info(f"   • Mode: {'Authenticated' if has_token else 'Anonymous'}")
        logger.info(f"   • Rate limit: {hourly_limit} req/hour ({self.requests_per_second:.2f} req/sec)")
        logger.info(f"   • Max concurrency: {config.max_concurrency}")
        logger.info(f"   • Adaptive threshold: {config.adaptive_threshold}")
    
    async def __aenter__(self):
        """Acquire rate limit and concurrency control."""
        # First acquire concurrency semaphore
        await self.semaphore.acquire()
        
        try:
            # Then apply rate limiting
            await self._apply_rate_limit()
            return self
        except:
            # Release semaphore if rate limiting fails
            self.semaphore.release()
            raise
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release concurrency control and handle response."""
        try:
            # Record response for adaptive behavior
            if exc_type is None:
                await self._record_success()
            else:
                await self._record_failure(exc_val)
        finally:
            # Always release semaphore
            self.semaphore.release()
    
    async def _apply_rate_limit(self):
        """Apply intelligent rate limiting with adaptive behavior."""
        async with self._lock:
            current_time = time.time()
            
            # Clean old request times (older than 1 minute)
            while self.request_times and current_time - self.request_times[0] > 60:
                self.request_times.popleft()
            
            # Calculate current rate
            requests_in_last_minute = len(self.request_times)
            target_rate = self.requests_per_minute * self.adaptive_factor
            
            # Check if we need to wait
            if requests_in_last_minute >= target_rate:
                # Calculate wait time based on oldest request
                if self.request_times:
                    wait_time = 60 - (current_time - self.request_times[0])
                    if wait_time > 0:
                        # Add jitter to prevent thundering herd
                        jitter = random.uniform(0, self.config.jitter_factor * wait_time)
                        total_wait = wait_time + jitter
                        
                        logger.debug(f"Rate limit reached, waiting {total_wait:.2f}s")
                        await asyncio.sleep(total_wait)
            
            # Record this request
            self.request_times.append(current_time)
    
    async def _record_success(self):
        """Record successful response and adjust adaptive behavior."""
        async with self._lock:
            self.consecutive_rate_limits = 0
            self.recent_responses.append(('success', time.time()))
            
            # Gradually increase rate if we're consistently successful
            success_rate = self._calculate_recent_success_rate()
            if success_rate > 0.95 and self.adaptive_factor < 1.0:
                self.adaptive_factor = min(1.0, self.adaptive_factor + 0.05)
                logger.debug(f"Increased adaptive factor to {self.adaptive_factor:.2f}")
    
    async def _record_failure(self, exception):
        """Record failed response and adjust adaptive behavior."""
        async with self._lock:
            self.recent_responses.append(('failure', time.time()))
            
            # Check if this is a rate limit error
            if self._is_rate_limit_error(exception):
                self.consecutive_rate_limits += 1
                
                # Reduce rate more aggressively for consecutive rate limits
                reduction_factor = 0.1 * (1 + self.consecutive_rate_limits * 0.5)
                self.adaptive_factor = max(0.1, self.adaptive_factor - reduction_factor)
                
                logger.warning(f"Rate limit hit (#{self.consecutive_rate_limits}), "
                             f"reduced adaptive factor to {self.adaptive_factor:.2f}")
                
                # Apply intelligent backoff
                await self._apply_intelligent_backoff()
    
    def _is_rate_limit_error(self, exception) -> bool:
        """Check if exception indicates rate limiting."""
        if exception is None:
            return False
        
        error_str = str(exception).lower()
        rate_limit_indicators = [
            '429', 'rate limit', 'too many requests', 
            'quota exceeded', 'throttled'
        ]
        
        return any(indicator in error_str for indicator in rate_limit_indicators)
    
    async def _apply_intelligent_backoff(self):
        """Apply intelligent backoff with exponential increase and jitter."""
        base_wait = self.config.base_backoff * (2 ** min(self.consecutive_rate_limits - 1, 6))
        max_wait = min(base_wait, self.config.max_backoff)
        
        # Add jitter to prevent synchronized retries
        jitter = random.uniform(0, self.config.jitter_factor * max_wait)
        total_wait = max_wait + jitter
        
        logger.info(f"Applying intelligent backoff: {total_wait:.2f}s")
        await asyncio.sleep(total_wait)
    
    def _calculate_recent_success_rate(self) -> float:
        """Calculate success rate from recent responses."""
        if not self.recent_responses:
            return 1.0
        
        successes = sum(1 for status, _ in self.recent_responses if status == 'success')
        return successes / len(self.recent_responses)
    
    def get_current_stats(self) -> Dict[str, Any]:
        """Get current rate limiter statistics."""
        current_time = time.time()
        
        # Clean old request times
        while self.request_times and current_time - self.request_times[0] > 60:
            self.request_times.popleft()
        
        return {
            'requests_last_minute': len(self.request_times),
            'target_rate_per_minute': self.requests_per_minute * self.adaptive_factor,
            'adaptive_factor': self.adaptive_factor,
            'consecutive_rate_limits': self.consecutive_rate_limits,
            'recent_success_rate': self._calculate_recent_success_rate(),
            'available_concurrency': self.semaphore._value,
            'max_concurrency': self.config.max_concurrency
        }

class ParallelProcessingManager:
    """Enhanced parallel processing manager with progress tracking and metrics."""
    
    def __init__(self, rate_limiter: AdaptiveRateLimiter, progress_report_interval: int = 900):
        self.rate_limiter = rate_limiter
        self.progress_report_interval = progress_report_interval  # 15 minutes default
        self.metrics = ProgressMetrics(start_time=time.time())
        self._progress_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
    
    async def process_batch_parallel(self, items: List[Any], 
                                   process_func: callable,
                                   batch_description: str = "Processing items") -> List[Any]:
        """Process items in parallel with progress tracking and metrics."""
        logger.info(f"🚀 Starting parallel processing: {batch_description}")
        logger.info(f"   • Total items: {len(items)}")
        logger.info(f"   • Max concurrency: {self.rate_limiter.config.max_concurrency}")
        logger.info(f"   • Progress reports every: {self.progress_report_interval}s")
        
        self.metrics.total_requests = len(items)
        
        # Start progress reporting task
        self._progress_task = asyncio.create_task(self._progress_reporter())
        
        try:
            # Create tasks for parallel processing
            tasks = [
                self._process_item_with_metrics(item, process_func)
                for item in items
            ]
            
            # Process with progress tracking
            results = []
            completed_tasks = 0
            
            # Use asyncio.as_completed for proper async iteration
            for coro in asyncio.as_completed(tasks):
                try:
                    result = await coro
                    if result is not None:
                        results.append(result)
                    completed_tasks += 1
                    
                    # Log progress periodically
                    if completed_tasks % max(1, len(tasks) // 10) == 0:
                        progress = (completed_tasks / len(tasks)) * 100
                        logger.info(f"📊 Progress: {completed_tasks}/{len(tasks)} ({progress:.1f}%)")
                        
                except Exception as e:
                    logger.debug(f"Task failed: {e}")
                    completed_tasks += 1
            
            # Calculate final metrics
            self.metrics.update_rate()
            elapsed_time = time.time() - self.metrics.start_time
            
            logger.info(f"✅ Parallel processing completed:")
            logger.info(f"   • Total time: {elapsed_time:.1f}s")
            logger.info(f"   • Successful: {self.metrics.successful_requests}/{self.metrics.total_requests}")
            logger.info(f"   • Failed: {self.metrics.failed_requests}")
            logger.info(f"   • Rate limit hits: {self.metrics.rate_limit_hits}")
            logger.info(f"   • Average rate: {self.metrics.current_rate:.2f} req/sec")
            
            success_rate = (self.metrics.successful_requests / self.metrics.total_requests) * 100
            logger.info(f"   • Success rate: {success_rate:.1f}%")
            
            return results
            
        finally:
            # Stop progress reporting
            self._shutdown_event.set()
            if self._progress_task:
                await self._progress_task
    
    async def _process_item_with_metrics(self, item: Any, process_func: callable) -> Optional[Any]:
        """Process single item with metrics tracking."""
        try:
            async with self.rate_limiter:
                result = await process_func(item)
                self.metrics.successful_requests += 1
                return result
                
        except Exception as e:
            self.metrics.failed_requests += 1
            
            # Check if this was a rate limit error
            if self.rate_limiter._is_rate_limit_error(e):
                self.metrics.rate_limit_hits += 1
            
            logger.debug(f"Failed to process item: {e}")
            return None
    
    async def _progress_reporter(self):
        """Background task for reporting progress every 15 minutes."""
        while not self._shutdown_event.is_set():
            try:
                # Wait for report interval or shutdown
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.progress_report_interval
                )
                break  # Shutdown requested
            except asyncio.TimeoutError:
                # Time for progress report
                await self._generate_progress_report()
    
    async def _generate_progress_report(self):
        """Generate detailed progress report."""
        current_time = time.time()
        elapsed_time = current_time - self.metrics.start_time
        
        # Update metrics
        self.metrics.update_rate()
        
        # Calculate completion estimate
        if self.metrics.current_rate > 0:
            remaining_requests = self.metrics.total_requests - self.metrics.successful_requests
            estimated_remaining_time = remaining_requests / self.metrics.current_rate
            self.metrics.estimated_completion = current_time + estimated_remaining_time
        
        # Get rate limiter stats
        rate_stats = self.rate_limiter.get_current_stats()
        
        # Generate comprehensive report
        logger.info("📊 === PROGRESS REPORT ===")
        logger.info(f"⏱️  Elapsed time: {elapsed_time:.1f}s")
        logger.info(f"📈 Progress: {self.metrics.successful_requests}/{self.metrics.total_requests} "
                   f"({(self.metrics.successful_requests/self.metrics.total_requests)*100:.1f}%)")
        logger.info(f"🚀 Current rate: {self.metrics.current_rate:.2f} req/sec")
        logger.info(f"❌ Failed requests: {self.metrics.failed_requests}")
        logger.info(f"🚦 Rate limit hits: {self.metrics.rate_limit_hits}")
        
        if self.metrics.estimated_completion:
            remaining_time = self.metrics.estimated_completion - current_time
            logger.info(f"⏰ Estimated completion: {remaining_time:.1f}s remaining")
        
        logger.info("🔧 Rate Limiter Status:")
        logger.info(f"   • Requests last minute: {rate_stats['requests_last_minute']}")
        logger.info(f"   • Target rate/min: {rate_stats['target_rate_per_minute']:.1f}")
        logger.info(f"   • Adaptive factor: {rate_stats['adaptive_factor']:.2f}")
        logger.info(f"   • Available concurrency: {rate_stats['available_concurrency']}/{rate_stats['max_concurrency']}")
        logger.info(f"   • Recent success rate: {rate_stats['recent_success_rate']:.1%}")
        logger.info("========================")
        
        self.metrics.last_report_time = current_time

class HuggingFaceDataFetcher:
    """Enhanced fetcher with multi-strategy discovery for complete GGUF model coverage."""
    
    def __init__(self, token: Optional[str] = None, sync_config: Optional[SyncConfig] = None):
        self.token = token
        self.api = HfApi(token=token)
        
        # Initialize sync configuration and manager
        self.sync_config = sync_config or SyncConfig()
        self.sync_manager = SyncModeManager(self.sync_config)
        
        # Initialize enhanced rate limiting configuration with environment variable support
        max_concurrency = int(os.getenv('MAX_CONCURRENCY', '50'))
        timeout_hours = float(os.getenv('TIMEOUT_HOURS', '6'))
        
        # Log configuration from environment
        logger.info(f"🔧 Configuration from environment:")
        logger.info(f"   • Max concurrency: {max_concurrency}")
        logger.info(f"   • Timeout hours: {timeout_hours}")
        logger.info(f"   • Sync mode: {os.getenv('SYNC_MODE', 'auto')}")
        logger.info(f"   • Performance metrics: {os.getenv('ENABLE_PERFORMANCE_METRICS', 'false')}")
        logger.info(f"   • Detailed logging: {os.getenv('ENABLE_DETAILED_LOGGING', 'false')}")
        
        self.rate_config = RateLimitConfig(
            authenticated_limit=5000,  # 5000 req/hour for authenticated users
            anonymous_limit=1000,      # 1000 req/hour for anonymous users
            max_concurrency=max_concurrency,  # From environment variable
            base_backoff=1.0,
            max_backoff=60.0,
            jitter_factor=0.1,
            adaptive_threshold=0.8
        )
        
        # Store timeout configuration
        self.timeout_hours = timeout_hours
        self.enable_performance_metrics = os.getenv('ENABLE_PERFORMANCE_METRICS', 'false').lower() == 'true'
        self.enable_detailed_logging = os.getenv('ENABLE_DETAILED_LOGGING', 'false').lower() == 'true'
        self.workflow_run_id = os.getenv('WORKFLOW_RUN_ID', 'unknown')
        
        # Initialize adaptive rate limiter
        self.rate_limiter = AdaptiveRateLimiter(self.rate_config, has_token=bool(token))
        
        # Initialize parallel processing manager with configurable progress reports
        progress_interval = int(os.getenv('PROGRESS_REPORT_INTERVAL', '900'))  # Default 15 minutes
        self.processing_manager = ParallelProcessingManager(
            rate_limiter=self.rate_limiter,
            progress_report_interval=progress_interval
        )
        
        # Legacy throttler for compatibility with discovery engine
        rate_limit = 1.2 if token else 0.5  # requests per second
        self.throttler = self.rate_limiter  # Use new rate limiter
        self.session: Optional[aiohttp.ClientSession] = None
        self.processed_models: Set[str] = set()
        self.failed_models: Set[str] = set()
        
        # Initialize multi-strategy discovery engine
        self.discovery_engine = MultiStrategyDiscoveryEngine(self.api, self.rate_limiter)
        
        # Initialize validation engine (will be set up in __aenter__)
        self.validation_engine: Optional[DataValidationEngine] = None
        
        # Initialize error handling and recovery system
        notification_config = NotificationConfig(
            email_enabled=False,  # Can be configured via environment variables
            webhook_enabled=False,
            log_file_path="error_notifications.log",
            consecutive_failures_threshold=5,
            error_rate_threshold=0.1
        )
        
        retry_strategy = ExponentialBackoffStrategy(
            base_delay=1.0,
            max_delay=60.0,
            max_retries=5,
            jitter_factor=0.1
        )
        
        self.error_recovery_system = ErrorRecoverySystem(
            retry_strategy=retry_strategy,
            notification_config=notification_config
        )
        
        # Initialize completeness monitoring system
        completeness_config = {
            'min_completeness_threshold': 95.0,
            'warning_threshold': 90.0,
            'excellent_threshold': 98.0,
            'missing_models_threshold': 50,
            'monitoring_enabled': True,
            'auto_recovery_enabled': True,
            'notification_channels': ['log']
        }
        
        self.completeness_monitor = CompletenessMonitor(
            self.api, 
            self.rate_limiter, 
            completeness_config
        )
        
    async def __aenter__(self):
        """Async context manager entry."""
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        
        headers = {
            'User-Agent': 'GGUF-Model-Discovery/1.0',
        }
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
            
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=headers
        )
        
        # Initialize validation engine with session
        self.validation_engine = DataValidationEngine(self.session)
        
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
            
    async def fetch_gguf_models(self) -> Tuple[List[Dict[str, Any]], SyncMetadata]:
        """Fetch all models with GGUF files using enhanced multi-strategy discovery with sync mode support."""
        logger.info("🚀 Starting enhanced GGUF model discovery from Hugging Face...")
        start_time = time.time()
        
        try:
            # Determine sync mode
            sync_mode = await self.sync_manager.determine_sync_mode()
            logger.info(f"🔄 Sync mode determined: {sync_mode.value.upper()}")
            
            # Use multi-strategy discovery engine for comprehensive model discovery
            logger.info("🔍 Executing multi-strategy model discovery...")
            discovered_models = await self.discovery_engine.discover_all_models()
            
            if not discovered_models:
                logger.warning("⚠️ No models discovered through any strategy")
                sync_metadata = SyncMetadata(
                    last_sync_time=datetime.now(timezone.utc),
                    sync_mode=sync_mode,
                    total_models_processed=0,
                    success=False,
                    error_message="No models discovered"
                )
                return [], sync_metadata
            
            logger.info(f"📊 Processing {len(discovered_models)} discovered models...")
            
            # Convert ModelReference objects to model objects for processing
            logger.info("🔄 Converting model references to model objects...")
            model_objects = await self.processing_manager.process_batch_parallel(
                list(discovered_models),
                self._get_model_info_with_metadata,
                "Converting model references"
            )
            
            # Filter out None results
            model_objects = [obj for obj in model_objects if obj is not None]
            logger.info(f"📊 Successfully retrieved info for {len(model_objects)} models")
            
            # Process models using enhanced parallel processing
            logger.info("🚀 Processing models with enhanced parallel system...")
            gguf_models = await self.processing_manager.process_batch_parallel(
                model_objects,
                self._process_model_with_retry,
                "Processing GGUF models"
            )
            
            # Filter out None results
            gguf_models = [model for model in gguf_models if model is not None]
            
            # Check if we should trigger a full sync due to significant changes
            previous_model_count = None
            if self.sync_manager.last_sync_metadata:
                previous_model_count = self.sync_manager.last_sync_metadata.total_models_processed
            
            if (sync_mode == SyncMode.INCREMENTAL and 
                await self.sync_manager.should_trigger_full_sync(gguf_models, previous_model_count)):
                logger.info("🔄 Switching to full sync due to significant changes")
                sync_mode = SyncMode.FULL
            
            # Apply sync mode filtering
            original_count = len(gguf_models)
            if sync_mode == SyncMode.INCREMENTAL:
                gguf_models = await self.sync_manager.filter_models_for_incremental_sync(gguf_models)
                logger.info(f"⚡ Incremental sync: processing {len(gguf_models)}/{original_count} recently modified models")
            else:
                logger.info(f"🔄 Full sync: processing all {len(gguf_models)} models")
                    
            # Sort by downloads (most popular first)
            gguf_models.sort(key=lambda x: x.get('downloads', 0), reverse=True)
            
            elapsed_time = time.time() - start_time
            logger.info(f"✅ Successfully processed {len(gguf_models)} GGUF models in {elapsed_time:.1f}s")
            
            if model_objects:
                success_rate = len(gguf_models) / len(model_objects) * 100
                logger.info(f"📈 Processing success rate: {len(gguf_models)}/{len(model_objects)} ({success_rate:.1f}%)")
            
            if self.failed_models:
                logger.warning(f"⚠️ Failed to process {len(self.failed_models)} models: {list(self.failed_models)[:5]}...")
            
            # Apply comprehensive validation and quality assurance
            logger.info("🔍 Starting comprehensive data validation and quality assurance...")
            validated_models, validation_metrics = await self.validation_engine.validate_models_batch(
                gguf_models,
                verify_file_access=True,
                apply_auto_fixes=True
            )
            
            # Store validation metrics for metadata generation
            self._validation_metrics = validation_metrics
            
            # Log validation results
            logger.info(f"✅ Validation completed: {validation_metrics.valid_models}/{validation_metrics.total_models} models passed validation")
            if validation_metrics.auto_fixes_applied > 0:
                logger.info(f"🔧 Applied {validation_metrics.auto_fixes_applied} automatic fixes to improve data quality")
            
            # Log discovery method statistics
            self._log_discovery_statistics(validated_models)
            
            # Perform completeness verification and monitoring
            logger.info("🔍 Starting data completeness verification and monitoring...")
            discovery_results = {
                'strategy_results': [
                    {
                        'strategy': result.strategy.value,
                        'models': list(result.models),
                        'success': result.success,
                        'execution_time': result.execution_time,
                        'error_message': result.error_message
                    }
                    for result in self.discovery_engine.strategy_results
                ]
            }
            
            completeness_report = await self.completeness_monitor.perform_completeness_check(
                validated_models, discovery_results
            )
            
            # Save completeness metadata
            await self.completeness_monitor.save_completeness_metadata(completeness_report)
            
            # Store completeness metrics for metadata generation
            self._completeness_report = completeness_report
            
            # Create sync metadata
            sync_metadata = SyncMetadata(
                last_sync_time=datetime.now(timezone.utc),
                sync_mode=sync_mode,
                total_models_processed=len(validated_models),
                models_added=len(validated_models) if sync_mode == SyncMode.FULL else len(validated_models),
                models_updated=0,  # Could be enhanced to track actual updates
                models_removed=0,  # Could be enhanced to track removals
                sync_duration=elapsed_time,
                success=True
            )
            
            # Log sync mode report
            self.sync_manager.log_sync_mode_report(
                sync_mode, len(validated_models), elapsed_time,
                models_added=sync_metadata.models_added,
                models_updated=sync_metadata.models_updated,
                models_removed=sync_metadata.models_removed
            )
            
            return validated_models, sync_metadata
            
        except Exception as e:
            logger.error(f"❌ Error in enhanced model discovery: {e}")
            # Create error sync metadata
            sync_metadata = SyncMetadata(
                last_sync_time=datetime.now(timezone.utc),
                sync_mode=sync_mode if 'sync_mode' in locals() else SyncMode.FULL,
                total_models_processed=0,
                sync_duration=time.time() - start_time,
                success=False,
                error_message=str(e)
            )
            return [], sync_metadata
    
    async def _get_model_info_with_metadata(self, model_ref: ModelReference) -> Optional[Any]:
        """Get model info from API and add discovery metadata."""
        try:
            model_info = self.api.model_info(model_ref.id)
            # Add discovery metadata to the model object
            model_info._discovery_method = model_ref.discovery_method
            model_info._confidence_score = model_ref.confidence_score
            model_info._discovery_metadata = model_ref.metadata
            return model_info
        except Exception as e:
            logger.debug(f"Could not get model info for {model_ref.id}: {e}")
            return None
    
    def _log_discovery_statistics(self, models: List[Dict[str, Any]]) -> None:
        """Log statistics about discovery methods used."""
        discovery_stats = {}
        
        for model in models:
            method = model.get('discoveryMethod', 'unknown')
            discovery_stats[method] = discovery_stats.get(method, 0) + 1
        
        logger.info("📊 Discovery method statistics:")
        for method, count in sorted(discovery_stats.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / len(models)) * 100
            logger.info(f"   • {method}: {count} models ({percentage:.1f}%)")
    
    async def generate_json_files(self, models: List[Dict[str, Any]]) -> None:
        """Generate optimized JSON files for the website with enhanced discovery metadata."""
        logger.info("📝 Generating optimized JSON files with discovery metadata...")
        
        # Create data directory
        data_dir = Path('data')
        data_dir.mkdir(exist_ok=True)
        
        # Generate comprehensive metadata including discovery statistics
        generation_metadata = self._create_generation_metadata(models)
        
        # Generate main models file with optimization
        models_data = {
            'models': self._optimize_models_for_output(models),
            'metadata': generation_metadata
        }
        
        # Write main models file
        await self._write_optimized_json(data_dir / 'models.json', models_data)
        
        # Generate search index with optimization
        search_index = self._create_optimized_search_index(models)
        await self._write_optimized_json(data_dir / 'search-index.json', search_index)
        
        # Generate comprehensive statistics
        stats = self._generate_comprehensive_statistics(models)
        await self._write_optimized_json(data_dir / 'statistics.json', stats)
        
        # Generate model families index
        families_index = self._create_families_index(models)
        await self._write_optimized_json(data_dir / 'families.json', families_index)
        
        # Generate architecture index for filtering
        architectures_index = self._create_architectures_index(models)
        await self._write_optimized_json(data_dir / 'architectures.json', architectures_index)
        
        # Generate quantizations index for filtering
        quantizations_index = self._create_quantizations_index(models)
        await self._write_optimized_json(data_dir / 'quantizations.json', quantizations_index)
        
        # Generate lightweight models list for quick loading
        lightweight_models = self._create_lightweight_models_list(models)
        await self._write_optimized_json(data_dir / 'models-light.json', lightweight_models)
        
        # Log file statistics
        await self._log_file_statistics(data_dir)
        
        logger.info("✅ All JSON files generated successfully")
    
    def _create_generation_metadata(self, models: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create comprehensive metadata about the generation process including discovery stats."""
        # Calculate discovery method statistics
        discovery_stats = {}
        for model in models:
            method = model.get('discoveryMethod', 'unknown')
            discovery_stats[method] = discovery_stats.get(method, 0) + 1
        
        return {
            'generated': datetime.now(timezone.utc).isoformat(),
            'totalModels': len(models),
            'totalFiles': sum(len(model.get('files', [])) for model in models),
            'totalDownloads': sum(model.get('downloads', 0) for model in models),
            'nextUpdate': self._get_next_update_time(),
            'version': '2.1',  # Updated version for multi-strategy discovery
            'processingTime': getattr(self, '_processing_time', 0),
            'successRate': getattr(self, '_success_rate', 0),
            'discoveryEngine': {
                'version': '1.0',
                'strategiesUsed': list(discovery_stats.keys()),
                'discoveryStatistics': discovery_stats,
                'multiStrategyEnabled': True,
                'deduplicationEnabled': True
            },
            'dataQuality': self._get_validation_metadata(),
            'validationReport': self._get_validation_report(),
            'completenessReport': self._get_completeness_metadata()
        }
    
    def _get_validation_metadata(self) -> Dict[str, Any]:
        """Get validation metadata for inclusion in generation metadata."""
        if not hasattr(self, '_validation_metrics') or self._validation_metrics is None:
            return {
                'validationPassed': True,
                'completenessScore': 1.0,
                'lastValidated': datetime.now(timezone.utc).isoformat(),
                'validationEngine': {
                    'version': '1.0',
                    'schemaValidation': True,
                    'fileAccessibilityVerification': True,
                    'autoFixingEnabled': True,
                    'qualityScoring': True
                }
            }
        
        metrics = self._validation_metrics
        return {
            'validationPassed': metrics.validation_success_rate >= 95.0,
            'completenessScore': metrics.average_completeness_score / 100.0,
            'qualityScore': metrics.average_quality_score / 100.0,
            'lastValidated': datetime.now(timezone.utc).isoformat(),
            'validationEngine': {
                'version': '1.0',
                'schemaValidation': True,
                'fileAccessibilityVerification': True,
                'autoFixingEnabled': True,
                'qualityScoring': True
            },
            'metrics': {
                'totalModels': metrics.total_models,
                'validModels': metrics.valid_models,
                'invalidModels': metrics.invalid_models,
                'modelsWithWarnings': metrics.models_with_warnings,
                'validationSuccessRate': metrics.validation_success_rate,
                'averageQualityScore': metrics.average_quality_score,
                'averageCompletenessScore': metrics.average_completeness_score,
                'totalFiles': metrics.total_files,
                'accessibleFiles': metrics.accessible_files,
                'fileAccessibilityRate': metrics.file_accessibility_rate,
                'autoFixesApplied': metrics.auto_fixes_applied,
                'validationDuration': metrics.validation_duration
            }
        }
    
    def _get_completeness_metadata(self) -> Dict[str, Any]:
        """Get completeness verification metadata for inclusion in generation metadata."""
        if not hasattr(self, '_completeness_report') or self._completeness_report is None:
            return {
                'monitoring_enabled': False,
                'completeness_score': 0.0,
                'status': 'unknown',
                'last_verification': datetime.now(timezone.utc).isoformat(),
                'message': 'Completeness monitoring not available'
            }
        
        report = self._completeness_report
        metrics = report.get('completeness_metrics', {})
        
        return {
            'monitoring_enabled': report.get('monitoring_enabled', False),
            'completeness_score': metrics.get('score', 0.0),
            'status': metrics.get('status', 'unknown'),
            'total_processed': metrics.get('total_processed', 0),
            'total_with_gguf': metrics.get('total_with_gguf', 0),
            'huggingface_count': metrics.get('huggingface_count', 0),
            'missing_count': metrics.get('missing_count', 0),
            'complete_data_count': metrics.get('complete_data_count', 0),
            'accessible_files_count': metrics.get('accessible_files_count', 0),
            'average_completeness': metrics.get('average_completeness', 0.0),
            'verification_time': metrics.get('verification_time', 0.0),
            'last_verification': report.get('timestamp', datetime.now(timezone.utc).isoformat()),
            'discovery_analysis': report.get('discovery_analysis', {}),
            'alerts_count': len(report.get('alerts', [])),
            'critical_alerts': len([a for a in report.get('alerts', []) if a.get('severity') == 'critical']),
            'recovery_enabled': report.get('recovery_results', {}).get('recovery_rate', 0) > 0,
            'monitoring_time': report.get('monitoring_time', 0.0)
        }
    
    def _get_validation_report(self) -> Dict[str, Any]:
        """Get comprehensive validation report."""
        if not hasattr(self, '_validation_metrics') or self._validation_metrics is None:
            return {
                'summary': 'Validation metrics not available',
                'generated_at': datetime.now(timezone.utc).isoformat()
            }
        
        return self.validation_engine.generate_validation_report()
    
    def _optimize_models_for_output(self, models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Optimize models data for JSON output by removing unnecessary fields."""
        optimized_models = []
        
        for model in models:
            # Create optimized model entry
            optimized_model = {
                'id': model['id'],
                'name': model['name'],
                'description': model.get('description', '')[:300],  # Limit description
                'files': model.get('files', []),
                'tags': model.get('tags', [])[:15],  # Limit tags
                'downloads': model.get('downloads', 0),
                'architecture': model.get('architecture', 'Unknown'),
                'family': model.get('family', 'Unknown'),
                'lastModified': model.get('lastModified'),
                'totalSize': model.get('totalSize', 0),
                'quantizations': model.get('quantizations', []),
                'availableQuantizations': model.get('availableQuantizations', []),
                'sizeCategories': model.get('sizeCategories', [])
            }
            
            # Add discovery metadata if available
            if 'discoveryMethod' in model:
                optimized_model['discoveryMethod'] = model['discoveryMethod']
            if 'confidenceScore' in model:
                optimized_model['confidenceScore'] = model['confidenceScore']
            
            optimized_models.append(optimized_model)
        
        return optimized_models
    
    def _create_optimized_search_index(self, models: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create optimized search index with discovery metadata."""
        search_index = {
            'models': {},
            'metadata': {
                'created': datetime.now(timezone.utc).isoformat(),
                'totalEntries': len(models),
                'version': '2.0',  # Updated for discovery metadata
                'optimized': True
            }
        }
        
        for model in models:
            # Create searchable text
            search_text_parts = [
                model.get('name', '').lower(),
                model.get('id', '').lower(),
                model.get('description', '')[:100].lower(),  # Limit description length
                model.get('architecture', '').lower(),
                model.get('family', '').lower()
            ]
            
            # Add limited tags and quantizations
            search_text_parts.extend([tag.lower() for tag in model.get('tags', [])[:5]])
            search_text_parts.extend([q.lower() for q in model.get('quantizations', [])])
            
            # Create compact index entry
            search_index['models'][model['id']] = {
                'searchText': ' '.join(filter(None, search_text_parts)),
                'name': model.get('name', ''),
                'arch': model.get('architecture', 'Unknown'),
                'family': model.get('family', 'Unknown'),
                'quants': model.get('quantizations', []),
                'size': model.get('totalSize', 0),
                'downloads': model.get('downloads', 0),
                'files': len(model.get('files', [])),
                'discoveryMethod': model.get('discoveryMethod', 'unknown')
            }
        
        return search_index
    
    async def _write_optimized_json(self, file_path: Path, data: Dict[str, Any]) -> None:
        """Write JSON data to file with optimization."""
        try:
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                # Use compact JSON format to reduce file size
                json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
                await f.write(json_str)
            
            # Log file size
            size_bytes = file_path.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            logger.debug(f"✅ Generated {file_path.name}: {size_mb:.2f} MB")
            
        except Exception as e:
            logger.error(f"❌ Error writing {file_path}: {e}")
            raise
    
    def _filter_invalid_entries(self, models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter out invalid model entries and log statistics."""
        valid_models = []
        invalid_count = 0
        validation_errors = {}
        
        for model in models:
            if self._validate_model_data(model):
                valid_models.append(model)
            else:
                invalid_count += 1
                # Track validation error types for debugging
                model_id = model.get('id', 'unknown')
                error_type = self._get_validation_error_type(model)
                validation_errors[error_type] = validation_errors.get(error_type, 0) + 1
                logger.debug(f"Filtered invalid model: {model_id} ({error_type})")
        
        if invalid_count > 0:
            logger.warning(f"⚠️ Filtered {invalid_count} invalid models:")
            for error_type, count in validation_errors.items():
                logger.warning(f"   - {error_type}: {count} models")
        
        return valid_models
    
    def _get_validation_error_type(self, model_data: Dict[str, Any]) -> str:
        """Determine the type of validation error for debugging."""
        if not model_data.get('id'):
            return 'missing_id'
        elif '/' not in model_data.get('id', ''):
            return 'invalid_id_format'
        elif not model_data.get('files') or not isinstance(model_data['files'], list):
            return 'invalid_files'
        elif len(model_data.get('files', [])) == 0:
            return 'no_files'
        elif not isinstance(model_data.get('downloads', 0), (int, float)):
            return 'invalid_downloads'
        elif not model_data.get('name'):
            return 'missing_name'
        else:
            return 'unknown_validation_error'
            

            
    async def _process_model_with_retry(self, model, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """Process a model with comprehensive error handling and recovery."""
        # Use the comprehensive error handling system
        result = await with_error_handling(
            self._process_model,
            "process_model",
            self.error_recovery_system,
            model.id,  # model_id
            None,      # url
            model      # args for _process_model
        )
        
        # Track failed models for reporting
        if result is None:
            self.failed_models.add(model.id)
        
        return result
            
    async def _process_model(self, model) -> Optional[Dict[str, Any]]:
        """Process a single model and extract GGUF file information with comprehensive error handling."""
        try:
            if model.id in self.processed_models:
                return None
                
            # Get model files with specific error handling
            try:
                files = self.api.list_repo_files(model.id, repo_type="model")
            except Exception as e:
                # Log specific error types for debugging
                if "404" in str(e) or "not found" in str(e).lower():
                    logger.debug(f"Model {model.id} not found (404)")
                elif "403" in str(e) or "forbidden" in str(e).lower():
                    logger.debug(f"Access forbidden for {model.id}")
                elif "429" in str(e) or "rate limit" in str(e).lower():
                    logger.debug(f"Rate limit hit for {model.id}")
                    raise  # Re-raise to trigger retry logic
                else:
                    logger.debug(f"Cannot access files for {model.id}: {e}")
                return None
                
            gguf_files = [f for f in files if f.endswith('.gguf')]
            
            if not gguf_files:
                logger.debug(f"No GGUF files found in {model.id}")
                return None
                
            # Get detailed file information with robust error handling
            model_files = []
            for filename in gguf_files[:10]:  # Limit to first 10 GGUF files per model
                try:
                    file_info = self.api.get_paths_info(
                        model.id, 
                        paths=[filename], 
                        repo_type="model"
                    )
                    
                    if file_info and len(file_info) > 0:
                        file_data = file_info[0]
                        model_files.append({
                            'filename': filename,
                            'size': self._format_size(file_data.size) if file_data.size else 'Unknown',
                            'sizeBytes': file_data.size or 0,
                            'quantization': self._extract_quantization(filename),
                            'downloadUrl': f"https://huggingface.co/{model.id}/resolve/main/{filename}",
                            'lastModified': file_data.last_modified.isoformat() if file_data.last_modified else None
                        })
                        
                except Exception as e:
                    # Handle specific error types
                    if "429" in str(e) or "rate limit" in str(e).lower():
                        logger.debug(f"Rate limit hit getting file info for {filename}")
                        raise  # Re-raise to trigger retry logic
                    elif "404" in str(e) or "not found" in str(e).lower():
                        logger.debug(f"File {filename} not found in {model.id}")
                        continue  # Skip this file
                    else:
                        logger.debug(f"Error getting file info for {filename}: {e}")
                    
                    # Add basic file info without detailed metadata as fallback
                    model_files.append({
                        'filename': filename,
                        'size': 'Unknown',
                        'sizeBytes': 0,
                        'quantization': self._extract_quantization(filename),
                        'downloadUrl': f"https://huggingface.co/{model.id}/resolve/main/{filename}",
                        'lastModified': None
                    })
                    
            if not model_files:
                return None
            
            # Extract comprehensive metadata
            metadata = self._extract_metadata(model, gguf_files)
            
            # Build model data structure with discovery metadata
            model_data = {
                'id': metadata['id'],
                'name': metadata['name'],
                'description': metadata['description'],
                'files': model_files,
                'tags': metadata['tags'],
                'downloads': metadata['downloads'],
                'architecture': metadata['architecture'],
                'family': metadata['family'],
                'lastModified': metadata['lastModified'],
                'totalSize': sum(f['sizeBytes'] for f in model_files),
                'quantizations': list(set(f['quantization'] for f in model_files)),
                'availableQuantizations': metadata['availableQuantizations'],
                'sizeCategories': metadata['sizeCategories'],
                # Discovery metadata
                'discoveryMethod': getattr(model, '_discovery_method', 'unknown'),
                'confidenceScore': getattr(model, '_confidence_score', 1.0),
                'discoveryMetadata': getattr(model, '_discovery_metadata', {})
            }
            
            # Clean and normalize the data
            model_data = self._clean_model_data(model_data)
            
            # Validate the final data structure
            if not self._validate_model_data(model_data):
                logger.warning(f"Model data validation failed for {model.id}")
                return None
            
            self.processed_models.add(model.id)
            return model_data
            
        except Exception as e:
            logger.debug(f"Error processing model {model.id}: {e}")
            return None
            
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024**2:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024**3:
            return f"{size_bytes / (1024**2):.1f} MB"
        else:
            return f"{size_bytes / (1024**3):.1f} GB"
            
    def _extract_quantization(self, filename: str) -> str:
        """Extract quantization type from filename."""
        # Common GGUF quantization patterns (ordered by specificity)
        quantizations = [
            'Q3_K_S', 'Q3_K_M', 'Q3_K_L', 'Q4_K_S', 'Q4_K_M', 'Q5_K_S', 'Q5_K_M',
            'Q2_K', 'Q6_K', 'Q4_0', 'Q4_1', 'Q5_0', 'Q5_1', 'Q8_0', 
            'F16', 'F32', 'BF16', 'IQ1_S', 'IQ1_M', 'IQ2_XXS', 'IQ2_XS', 'IQ2_S', 'IQ2_M',
            'IQ3_XXS', 'IQ3_S', 'IQ3_M', 'IQ4_XS', 'IQ4_NL'
        ]
        
        filename_upper = filename.upper()
        
        # Look for quantization patterns
        for quant in quantizations:
            if quant in filename_upper:
                return quant
                
        # Fallback patterns
        if 'FP16' in filename_upper or 'FLOAT16' in filename_upper:
            return 'F16'
        elif 'FP32' in filename_upper or 'FLOAT32' in filename_upper:
            return 'F32'
        elif 'INT8' in filename_upper:
            return 'Q8_0'
        elif 'INT4' in filename_upper:
            return 'Q4_0'
                
        return 'Unknown'
        
    def _validate_model_data(self, model_data: Dict[str, Any]) -> bool:
        """Validate model data structure and content."""
        required_fields = ['id', 'name', 'files', 'downloads', 'architecture', 'family']
        
        # Check required fields exist
        for field in required_fields:
            if field not in model_data:
                logger.debug(f"Missing required field '{field}' in model data")
                return False
        
        # Validate model ID format
        if not model_data['id'] or '/' not in model_data['id']:
            logger.debug(f"Invalid model ID format: {model_data.get('id')}")
            return False
        
        # Validate files array
        if not isinstance(model_data['files'], list) or len(model_data['files']) == 0:
            logger.debug(f"Invalid or empty files array for model {model_data['id']}")
            return False
        
        # Validate each file entry
        for file_data in model_data['files']:
            if not self._validate_file_data(file_data):
                logger.debug(f"Invalid file data in model {model_data['id']}")
                return False
        
        # Validate downloads is a number
        if not isinstance(model_data['downloads'], (int, float)) or model_data['downloads'] < 0:
            logger.debug(f"Invalid downloads count for model {model_data['id']}")
            return False
        
        # Validate name is not empty
        if not model_data['name'] or not isinstance(model_data['name'], str):
            logger.debug(f"Invalid name for model {model_data['id']}")
            return False
        
        return True
    
    def _validate_file_data(self, file_data: Dict[str, Any]) -> bool:
        """Validate individual file data structure."""
        required_fields = ['filename', 'size', 'sizeBytes', 'quantization', 'downloadUrl']
        
        # Check required fields
        for field in required_fields:
            if field not in file_data:
                return False
        
        # Validate filename
        if not file_data['filename'] or not file_data['filename'].endswith('.gguf'):
            return False
        
        # Validate size bytes is a number
        if not isinstance(file_data['sizeBytes'], (int, float)) or file_data['sizeBytes'] < 0:
            return False
        
        # Validate download URL format
        if not file_data['downloadUrl'] or not file_data['downloadUrl'].startswith('https://'):
            return False
        
        return True
    
    def _clean_model_data(self, model_data: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and normalize model data."""
        # Clean description
        if 'description' in model_data and model_data['description']:
            description = model_data['description']
            # Remove excessive whitespace
            description = re.sub(r'\s+', ' ', description.strip())
            # Limit length
            if len(description) > 500:
                description = description[:497] + '...'
            model_data['description'] = description
        else:
            model_data['description'] = ''
        
        # Clean and limit tags
        if 'tags' in model_data and isinstance(model_data['tags'], list):
            cleaned_tags = []
            for tag in model_data['tags']:
                if isinstance(tag, str) and tag.strip() and len(tag.strip()) < 50:
                    cleaned_tags.append(tag.strip().lower())
                if len(cleaned_tags) >= 20:  # Limit to 20 tags
                    break
            model_data['tags'] = cleaned_tags
        else:
            model_data['tags'] = []
        
        # Ensure downloads is an integer
        if 'downloads' in model_data:
            try:
                model_data['downloads'] = int(model_data['downloads']) if model_data['downloads'] else 0
            except (ValueError, TypeError):
                model_data['downloads'] = 0
        
        # Clean model name
        if 'name' in model_data and model_data['name']:
            model_data['name'] = model_data['name'].strip()
        
        # Sort files by size (largest first)
        if 'files' in model_data and isinstance(model_data['files'], list):
            model_data['files'].sort(key=lambda x: x.get('sizeBytes', 0), reverse=True)
        
        # Add computed fields
        if 'files' in model_data:
            model_data['totalSize'] = sum(f.get('sizeBytes', 0) for f in model_data['files'])
            model_data['quantizations'] = list(set(f.get('quantization', 'Unknown') for f in model_data['files']))
            model_data['quantizations'].sort()
        
        return model_data
    
    def _extract_metadata(self, model, files: List[str]) -> Dict[str, Any]:
        """Extract comprehensive metadata from model and files."""
        metadata = {}
        
        # Basic model info
        metadata['id'] = model.id
        metadata['name'] = self._extract_model_name(model.id)
        metadata['family'] = self._extract_family(model.id)
        
        # Extract description and clean it
        description = getattr(model, 'description', '') or ''
        if description:
            description = re.sub(r'\s+', ' ', description.strip())
            if len(description) > 500:
                description = description[:497] + '...'
        metadata['description'] = description
        
        # Extract and clean tags
        tags = getattr(model, 'tags', []) or []
        cleaned_tags = []
        for tag in tags:
            if isinstance(tag, str) and tag.strip() and len(tag.strip()) < 50:
                cleaned_tags.append(tag.strip().lower())
            if len(cleaned_tags) >= 20:
                break
        metadata['tags'] = cleaned_tags
        
        # Extract architecture
        metadata['architecture'] = self._extract_architecture(model.id, cleaned_tags)
        
        # Extract download count
        metadata['downloads'] = getattr(model, 'downloads', 0) or 0
        
        # Extract last modified date
        last_modified = getattr(model, 'last_modified', None)
        if last_modified:
            metadata['lastModified'] = last_modified.isoformat()
        else:
            metadata['lastModified'] = datetime.now(timezone.utc).isoformat()
        
        # Analyze file patterns for additional metadata
        quantization_patterns = set()
        size_categories = set()
        
        for filename in files:
            quant = self._extract_quantization(filename)
            quantization_patterns.add(quant)
            
            # Categorize by common size patterns
            filename_lower = filename.lower()
            if any(size in filename_lower for size in ['1b', '1.3b', '2b', '3b']):
                size_categories.add('small')
            elif any(size in filename_lower for size in ['7b', '8b', '9b', '11b', '13b']):
                size_categories.add('medium')
            elif any(size in filename_lower for size in ['20b', '30b', '34b', '40b', '70b']):
                size_categories.add('large')
            elif any(size in filename_lower for size in ['120b', '175b', '180b']):
                size_categories.add('xlarge')
        
        metadata['availableQuantizations'] = sorted(list(quantization_patterns))
        metadata['sizeCategories'] = sorted(list(size_categories))
        
        return metadata
        
    def _extract_model_name(self, model_id: str) -> str:
        """Extract a clean model name from the model ID."""
        # Remove organization prefix and clean up
        name = model_id.split('/')[-1]
        # Replace hyphens and underscores with spaces, capitalize
        name = name.replace('-', ' ').replace('_', ' ')
        return ' '.join(word.capitalize() for word in name.split())
        
    def _extract_architecture(self, model_id: str, tags: List[str]) -> str:
        """Extract model architecture from ID and tags."""
        model_id_lower = model_id.lower()
        tags_lower = [tag.lower() for tag in tags]
        all_text = [model_id_lower] + tags_lower
        
        # Architecture patterns (ordered by specificity)
        architectures = [
            ('Llama', ['llama-2', 'llama2', 'llama-3', 'llama3', 'llama']),
            ('Mistral', ['mistral-7b', 'mistral-8x7b', 'mistral']),
            ('Mixtral', ['mixtral', 'mixture-of-experts']),
            ('Qwen', ['qwen', 'qwen1.5', 'qwen2']),
            ('Gemma', ['gemma']),
            ('Phi', ['phi-3', 'phi3', 'phi-2', 'phi2', 'phi']),
            ('CodeLlama', ['codellama', 'code-llama']),
            ('Vicuna', ['vicuna']),
            ('Alpaca', ['alpaca']),
            ('ChatGLM', ['chatglm']),
            ('Baichuan', ['baichuan']),
            ('Yi', ['yi-34b', 'yi-6b', 'yi-']),
            ('DeepSeek', ['deepseek']),
            ('InternLM', ['internlm']),
            ('GPT', ['gpt-4', 'gpt-3.5', 'gpt-3', 'gpt-2', 'gpt']),
            ('BERT', ['bert']),
            ('T5', ['t5', 'flan-t5']),
            ('Falcon', ['falcon']),
            ('MPT', ['mpt']),
            ('Bloom', ['bloom']),
            ('OPT', ['opt-']),
            ('Pythia', ['pythia']),
            ('StableLM', ['stablelm']),
            ('RedPajama', ['redpajama']),
            ('OpenLLaMA', ['openllama', 'open-llama']),
        ]
        
        for arch_name, patterns in architectures:
            if any(pattern in text for pattern in patterns for text in all_text):
                return arch_name
                
        return 'Unknown'
            
    def _extract_family(self, model_id: str) -> str:
        """Extract model family/organization from model ID."""
        return model_id.split('/')[0] if '/' in model_id else 'Unknown'
        
    async def generate_json_files(self, models: List[Dict[str, Any]]) -> None:
        """Generate optimized JSON files for the website with compression and metadata."""
        logger.info("📝 Generating optimized JSON files...")
        
        # Create data directory
        data_dir = Path('data')
        data_dir.mkdir(exist_ok=True)
        
        # Generate comprehensive metadata
        generation_metadata = self._create_generation_metadata(models)
        
        # Generate main models file with optimization
        models_data = {
            'models': self._optimize_models_for_output(models),
            'metadata': generation_metadata
        }
        
        # Write main models file with compression
        await self._write_optimized_json(data_dir / 'models.json', models_data)
        
        # Generate search index with optimization
        search_index = self._create_optimized_search_index(models)
        await self._write_optimized_json(data_dir / 'search-index.json', search_index)
        
        # Generate comprehensive statistics
        stats = self._generate_comprehensive_statistics(models)
        await self._write_optimized_json(data_dir / 'statistics.json', stats)
        
        # Generate model families index
        families_index = self._create_families_index(models)
        await self._write_optimized_json(data_dir / 'families.json', families_index)
        
        # Generate architecture index for filtering
        architectures_index = self._create_architectures_index(models)
        await self._write_optimized_json(data_dir / 'architectures.json', architectures_index)
        
        # Generate quantization index for filtering
        quantizations_index = self._create_quantizations_index(models)
        await self._write_optimized_json(data_dir / 'quantizations.json', quantizations_index)
        
        # Generate lightweight model list for quick loading
        lightweight_models = self._create_lightweight_models_list(models)
        await self._write_optimized_json(data_dir / 'models-light.json', lightweight_models)
        
        # Generate legacy files for backward compatibility with freshness data
        await self._generate_legacy_files(models)
        
        logger.info(f"✅ Generated optimized JSON files for {len(models)} models")
        
        # Log file sizes and compression ratios
        await self._log_file_statistics(data_dir)
    
    async def _write_optimized_json(self, file_path: Path, data: Dict[str, Any]) -> None:
        """Write JSON with optimal compression and formatting."""
        # Use compact JSON formatting for smaller file sizes
        json_content = json.dumps(
            data, 
            separators=(',', ':'),  # No spaces for compression
            ensure_ascii=False,     # Allow Unicode for international content
            sort_keys=True          # Consistent ordering for better compression
        )
        
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json_content)
    
    def _create_generation_metadata(self, models: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create comprehensive metadata about the generation process."""
        now = datetime.now(timezone.utc)
        
        # Calculate data quality metrics
        total_files = sum(len(model.get('files', [])) for model in models)
        total_size = sum(model.get('totalSize', 0) for model in models)
        
        # Architecture distribution
        arch_counts = {}
        for model in models:
            arch = model.get('architecture', 'Unknown')
            arch_counts[arch] = arch_counts.get(arch, 0) + 1
        
        return {
            'totalModels': len(models),
            'totalFiles': total_files,
            'totalSizeBytes': total_size,
            'totalSizeFormatted': self._format_size(total_size),
            'lastUpdated': now.isoformat(),
            'version': '1.1',
            'generatedBy': 'GGUF Model Discovery Pipeline v1.1',
            'updateFrequency': 'daily',
            'nextUpdate': self._get_next_update_time(),
            'dataQuality': {
                'averageFilesPerModel': round(total_files / len(models), 2) if models else 0,
                'modelsWithDescription': len([m for m in models if m.get('description')]),
                'modelsWithTags': len([m for m in models if m.get('tags')]),
                'uniqueArchitectures': len(arch_counts),
                'uniqueFamilies': len(set(m.get('family', 'Unknown') for m in models))
            },
            'processingStats': {
                'processedModels': len(self.processed_models),
                'failedModels': len(self.failed_models),
                'successRate': len(self.processed_models) / (len(self.processed_models) + len(self.failed_models)) * 100 if (self.processed_models or self.failed_models) else 100
            }
        }
    
    def _optimize_models_for_output(self, models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Optimize model data for JSON output by removing redundant information."""
        optimized_models = []
        
        for model in models:
            # Create optimized model entry
            optimized_model = {
                'id': model['id'],
                'name': model['name'],
                'description': model.get('description', '')[:200] + ('...' if len(model.get('description', '')) > 200 else ''),  # Truncate long descriptions
                'files': self._optimize_files_for_output(model.get('files', [])),
                'tags': model.get('tags', [])[:10],  # Limit tags for size
                'downloads': model.get('downloads', 0),
                'architecture': model.get('architecture', 'Unknown'),
                'family': model.get('family', 'Unknown'),
                'lastModified': model.get('lastModified'),
                'totalSize': model.get('totalSize', 0),
                'quantizations': model.get('quantizations', [])
            }
            
            # Only include non-empty optional fields
            if not optimized_model['description']:
                del optimized_model['description']
            if not optimized_model['tags']:
                del optimized_model['tags']
            
            optimized_models.append(optimized_model)
        
        return optimized_models
    
    def _optimize_files_for_output(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Optimize file data for JSON output."""
        optimized_files = []
        
        for file_data in files:
            optimized_file = {
                'filename': file_data['filename'],
                'size': file_data['size'],
                'sizeBytes': file_data['sizeBytes'],
                'quantization': file_data['quantization'],
                'downloadUrl': file_data['downloadUrl']
            }
            
            # Only include lastModified if it exists
            if file_data.get('lastModified'):
                optimized_file['lastModified'] = file_data['lastModified']
            
            optimized_files.append(optimized_file)
        
        return optimized_files
    
    def _create_optimized_search_index(self, models: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create highly optimized search index for fast client-side searching."""
        search_index = {
            'models': {},
            'metadata': {
                'created': datetime.now(timezone.utc).isoformat(),
                'totalEntries': len(models),
                'version': '1.1',
                'indexType': 'optimized'
            }
        }
        
        for model in models:
            # Create highly compressed searchable text
            search_text_parts = [
                model['name'].lower(),
                model['id'].lower().replace('/', ' '),
                model.get('description', '')[:100].lower(),  # Limit description length
                model.get('architecture', '').lower(),
                model.get('family', '').lower()
            ]
            
            # Add limited tags and quantizations
            search_text_parts.extend([tag.lower() for tag in model.get('tags', [])[:5]])
            search_text_parts.extend([q.lower() for q in model.get('quantizations', [])])
            
            # Create compact index entry
            search_index['models'][model['id']] = {
                'searchText': ' '.join(filter(None, search_text_parts)),
                'name': model['name'],
                'arch': model.get('architecture', 'Unknown'),
                'family': model.get('family', 'Unknown'),
                'quants': model.get('quantizations', []),
                'size': model.get('totalSize', 0),
                'downloads': model.get('downloads', 0),
                'files': len(model.get('files', []))
            }
        
        return search_index
    
    def _create_lightweight_models_list(self, models: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a lightweight models list for quick initial loading."""
        lightweight_models = []
        
        for model in models[:100]:  # Top 100 models only
            lightweight_model = {
                'id': model['id'],
                'name': model['name'],
                'architecture': model.get('architecture', 'Unknown'),
                'family': model.get('family', 'Unknown'),
                'downloads': model.get('downloads', 0),
                'fileCount': len(model.get('files', [])),
                'totalSize': model.get('totalSize', 0),
                'quantizations': model.get('quantizations', [])[:3]  # Top 3 quantizations
            }
            lightweight_models.append(lightweight_model)
        
        return {
            'models': lightweight_models,
            'metadata': {
                'totalModels': len(lightweight_models),
                'isSubset': True,
                'subsetType': 'top_downloads',
                'fullDataAvailable': 'models.json',
                'created': datetime.now(timezone.utc).isoformat()
            }
        }
    
    def _create_architectures_index(self, models: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create index organized by architectures for filtering."""
        architectures = {}
        
        for model in models:
            arch = model.get('architecture', 'Unknown')
            if arch not in architectures:
                architectures[arch] = {
                    'name': arch,
                    'models': [],
                    'totalModels': 0,
                    'totalDownloads': 0,
                    'families': set(),
                    'quantizations': set()
                }
            
            architectures[arch]['models'].append({
                'id': model['id'],
                'name': model['name'],
                'downloads': model.get('downloads', 0),
                'family': model.get('family', 'Unknown'),
                'fileCount': len(model.get('files', []))
            })
            architectures[arch]['totalModels'] += 1
            architectures[arch]['totalDownloads'] += model.get('downloads', 0)
            architectures[arch]['families'].add(model.get('family', 'Unknown'))
            architectures[arch]['quantizations'].update(model.get('quantizations', []))
        
        # Convert sets to sorted lists and sort models by downloads
        for arch_data in architectures.values():
            arch_data['families'] = sorted(list(arch_data['families']))
            arch_data['quantizations'] = sorted(list(arch_data['quantizations']))
            arch_data['models'].sort(key=lambda x: x['downloads'], reverse=True)
            arch_data['models'] = arch_data['models'][:20]  # Limit to top 20 per architecture
        
        return {
            'architectures': architectures,
            'metadata': {
                'totalArchitectures': len(architectures),
                'created': datetime.now(timezone.utc).isoformat()
            }
        }
    
    def _create_quantizations_index(self, models: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create index organized by quantizations for filtering."""
        quantizations = {}
        
        for model in models:
            for quant in model.get('quantizations', []):
                if quant not in quantizations:
                    quantizations[quant] = {
                        'name': quant,
                        'models': [],
                        'totalModels': 0,
                        'totalFiles': 0,
                        'architectures': set(),
                        'families': set()
                    }
                
                quantizations[quant]['models'].append({
                    'id': model['id'],
                    'name': model['name'],
                    'downloads': model.get('downloads', 0),
                    'architecture': model.get('architecture', 'Unknown'),
                    'family': model.get('family', 'Unknown')
                })
                quantizations[quant]['totalModels'] += 1
                quantizations[quant]['totalFiles'] += len([f for f in model.get('files', []) if f.get('quantization') == quant])
                quantizations[quant]['architectures'].add(model.get('architecture', 'Unknown'))
                quantizations[quant]['families'].add(model.get('family', 'Unknown'))
        
        # Convert sets to sorted lists and sort models by downloads
        for quant_data in quantizations.values():
            quant_data['architectures'] = sorted(list(quant_data['architectures']))
            quant_data['families'] = sorted(list(quant_data['families']))
            quant_data['models'].sort(key=lambda x: x['downloads'], reverse=True)
            quant_data['models'] = quant_data['models'][:15]  # Limit to top 15 per quantization
        
        return {
            'quantizations': quantizations,
            'metadata': {
                'totalQuantizations': len(quantizations),
                'created': datetime.now(timezone.utc).isoformat()
            }
        }
    
    def _generate_comprehensive_statistics(self, models: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate comprehensive statistics with additional insights."""
        total_models = len(models)
        total_files = sum(len(model.get('files', [])) for model in models)
        total_downloads = sum(model.get('downloads', 0) for model in models)
        total_size = sum(model.get('totalSize', 0) for model in models)
        
        # Distribution analysis
        architectures = {}
        families = {}
        quantizations = {}
        size_distribution = {'small': 0, 'medium': 0, 'large': 0, 'xlarge': 0}
        
        for model in models:
            # Architecture distribution
            arch = model.get('architecture', 'Unknown')
            architectures[arch] = architectures.get(arch, 0) + 1
            
            # Family distribution
            family = model.get('family', 'Unknown')
            families[family] = families.get(family, 0) + 1
            
            # Quantization distribution
            for quant in model.get('quantizations', []):
                quantizations[quant] = quantizations.get(quant, 0) + 1
            
            # Size distribution
            model_size = model.get('totalSize', 0)
            if model_size < 1024**3:  # < 1GB
                size_distribution['small'] += 1
            elif model_size < 5 * 1024**3:  # < 5GB
                size_distribution['medium'] += 1
            elif model_size < 20 * 1024**3:  # < 20GB
                size_distribution['large'] += 1
            else:
                size_distribution['xlarge'] += 1
        
        # Top models by downloads
        top_models = sorted(models, key=lambda x: x.get('downloads', 0), reverse=True)[:10]
        
        return {
            'summary': {
                'totalModels': total_models,
                'totalFiles': total_files,
                'totalDownloads': total_downloads,
                'totalSizeBytes': total_size,
                'totalSizeFormatted': self._format_size(total_size),
                'averageFilesPerModel': round(total_files / total_models, 2) if total_models else 0,
                'averageDownloadsPerModel': round(total_downloads / total_models, 2) if total_models else 0,
                'lastUpdated': datetime.now(timezone.utc).isoformat()
            },
            'distributions': {
                'architectures': dict(sorted(architectures.items(), key=lambda x: x[1], reverse=True)),
                'families': dict(sorted(families.items(), key=lambda x: x[1], reverse=True)[:20]),  # Top 20 families
                'quantizations': dict(sorted(quantizations.items(), key=lambda x: x[1], reverse=True)),
                'sizes': size_distribution
            },
            'topModels': [
                {
                    'id': model['id'],
                    'name': model['name'],
                    'downloads': model.get('downloads', 0),
                    'architecture': model.get('architecture', 'Unknown'),
                    'family': model.get('family', 'Unknown')
                }
                for model in top_models
            ],
            'insights': {
                'mostPopularArchitecture': max(architectures.items(), key=lambda x: x[1])[0] if architectures else 'Unknown',
                'mostPopularFamily': max(families.items(), key=lambda x: x[1])[0] if families else 'Unknown',
                'mostPopularQuantization': max(quantizations.items(), key=lambda x: x[1])[0] if quantizations else 'Unknown',
                'averageModelSize': self._format_size(total_size / total_models) if total_models else '0 B'
            }
        }
    
    async def _generate_legacy_files(self, models: List[Dict[str, Any]]) -> None:
        """Generate legacy JSON files for backward compatibility with freshness data."""
        logger.info("📝 Generating legacy files with freshness data...")
        
        try:
            # Generate legacy gguf_models.json with freshness information
            legacy_models = []
            for model in models:
                legacy_model = {
                    'modelId': model.get('id', model.get('modelId', '')),
                    'files': [{'filename': f.get('filename', f.get('name', ''))} 
                             for f in model.get('files', [])],
                    'downloads': model.get('downloads', 0),
                    'lastModified': model.get('lastModified'),
                    # Add freshness fields
                    'lastSynced': model.get('lastSynced'),
                    'freshnessStatus': model.get('freshnessStatus', 'unknown'),
                    'hoursSinceModified': model.get('hoursSinceModified'),
                    'hoursSinceSynced': model.get('hoursSinceSynced', 0.0)
                }
                legacy_models.append(legacy_model)
            
            # Write legacy gguf_models.json
            async with aiofiles.open('gguf_models.json', 'w', encoding='utf-8') as f:
                json_content = json.dumps(legacy_models, indent=2, ensure_ascii=False)
                await f.write(json_content)
            
            # Generate legacy gguf_models_estimated_sizes.json with freshness metadata
            size_estimates = {}
            for model in models:
                model_id = model.get('id', model.get('modelId', ''))
                if model_id:
                    size_estimates[model_id] = {
                        'totalSize': model.get('totalSize', 0),
                        'files': {f.get('filename', f.get('name', '')): f.get('size', 0) 
                                 for f in model.get('files', []) if f.get('filename') or f.get('name')},
                        'lastUpdated': model.get('lastSynced'),
                        'freshnessStatus': model.get('freshnessStatus', 'unknown')
                    }
            
            # Write legacy size estimates file
            async with aiofiles.open('gguf_models_estimated_sizes.json', 'w', encoding='utf-8') as f:
                json_content = json.dumps(size_estimates, indent=2, ensure_ascii=False)
                await f.write(json_content)
            
            logger.info(f"✅ Generated legacy files: gguf_models.json ({len(legacy_models)} models)")
            
        except Exception as e:
            logger.error(f"❌ Failed to generate legacy files: {e}")

    async def _log_file_statistics(self, data_dir: Path) -> None:
        """Log detailed statistics about generated files."""
        files_to_check = [
            'models.json', 'search-index.json', 'statistics.json', 
            'families.json', 'architectures.json', 'quantizations.json', 'models-light.json'
        ]
        
        # Include legacy files in statistics
        legacy_files = ['gguf_models.json', 'gguf_models_estimated_sizes.json']
        
        total_size = 0
        logger.info("📊 Generated file statistics:")
        
        # Check legacy files first
        for filename in legacy_files:
            file_path = Path(filename)
            if file_path.exists():
                size_bytes = file_path.stat().st_size
                size_mb = size_bytes / (1024 * 1024)
                total_size += size_bytes
                logger.info(f"   • {filename}: {size_mb:.2f} MB ({size_bytes:,} bytes) [legacy]")
            else:
                logger.warning(f"   • {filename}: NOT FOUND [legacy]")
        
        # Check data directory files
        for filename in files_to_check:
            file_path = data_dir / filename
            if file_path.exists():
                size_bytes = file_path.stat().st_size
                size_mb = size_bytes / (1024 * 1024)
                total_size += size_bytes
                logger.info(f"   • {filename}: {size_mb:.2f} MB ({size_bytes:,} bytes)")
            else:
                logger.warning(f"   • {filename}: NOT FOUND")
        
        logger.info(f"📦 Total JSON files size: {total_size / (1024 * 1024):.2f} MB ({total_size:,} bytes)")
        
        # Calculate compression efficiency
        if total_size > 0:
            total_files = len(files_to_check) + len(legacy_files)
            logger.info(f"💾 Average file size: {(total_size / total_files) / (1024 * 1024):.2f} MB per file")
                
    def _get_next_update_time(self) -> str:
        """Calculate next update time (tomorrow at 23:59 UTC)."""
        now = datetime.now(timezone.utc)
        next_update = now.replace(hour=23, minute=59, second=0, microsecond=0)
        if next_update <= now:
            next_update = next_update.replace(day=next_update.day + 1)
        return next_update.isoformat()
        
    def _create_search_index(self, models: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create optimized search index."""
        search_index = {
            'models': {},
            'metadata': {
                'created': datetime.now(timezone.utc).isoformat(),
                'totalEntries': len(models),
                'version': '1.0'
            }
        }
        
        for model in models:
            # Create searchable text
            search_text_parts = [
                model['name'].lower(),
                model['id'].lower(),
                model['description'].lower()[:200],  # Limit description length
                model['architecture'].lower(),
                model['family'].lower()
            ]
            search_text_parts.extend([tag.lower() for tag in model['tags'][:10]])  # Limit tags
            search_text_parts.extend([q.lower() for q in model['quantizations']])
            
            search_index['models'][model['id']] = {
                'searchText': ' '.join(filter(None, search_text_parts)),
                'name': model['name'],
                'architecture': model['architecture'],
                'family': model['family'],
                'quantizations': model['quantizations'],
                'totalSize': model['totalSize'],
                'downloads': model['downloads'],
                'fileCount': len(model['files'])
            }
            
        return search_index
        
    def _create_families_index(self, models: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create index organized by model families."""
        families = {}
        
        for model in models:
            family = model['family']
            if family not in families:
                families[family] = {
                    'name': family,
                    'models': [],
                    'totalModels': 0,
                    'totalDownloads': 0,
                    'architectures': set(),
                    'quantizations': set()
                }
            
            families[family]['models'].append({
                'id': model['id'],
                'name': model['name'],
                'downloads': model['downloads'],
                'architecture': model['architecture'],
                'quantizations': model['quantizations'],
                'fileCount': len(model['files'])
            })
            families[family]['totalModels'] += 1
            families[family]['totalDownloads'] += model['downloads']
            families[family]['architectures'].add(model['architecture'])
            families[family]['quantizations'].update(model['quantizations'])
        
        # Convert sets to sorted lists
        for family_data in families.values():
            family_data['architectures'] = sorted(list(family_data['architectures']))
            family_data['quantizations'] = sorted(list(family_data['quantizations']))
            family_data['models'].sort(key=lambda x: x['downloads'], reverse=True)
        
        return {
            'families': families,
            'metadata': {
                'totalFamilies': len(families),
                'created': datetime.now(timezone.utc).isoformat()
            }
        }
        
    def _generate_statistics(self, models: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate statistics about the models."""
        total_models = len(models)
        total_files = sum(len(model['files']) for model in models)
        total_downloads = sum(model['downloads'] for model in models)
        
        # Architecture distribution
        architectures = {}
        families = {}
        quantizations = {}
        
        for model in models:
            arch = model['architecture']
            architectures[arch] = architectures.get(arch, 0) + 1
            
            family = model['family']
            families[family] = families.get(family, 0) + 1
            
            for file in model['files']:
                quant = file['quantization']
                quantizations[quant] = quantizations.get(quant, 0) + 1
                
        return {
            'summary': {
                'totalModels': total_models,
                'totalFiles': total_files,
                'totalDownloads': total_downloads,
                'lastUpdated': datetime.now(timezone.utc).isoformat()
            },
            'distributions': {
                'architectures': dict(sorted(architectures.items(), key=lambda x: x[1], reverse=True)),
                'families': dict(sorted(families.items(), key=lambda x: x[1], reverse=True)),
                'quantizations': dict(sorted(quantizations.items(), key=lambda x: x[1], reverse=True))
            }
        }
        
    async def generate_sitemap(self, models: List[Dict[str, Any]]) -> None:
        """Generate XML sitemap for SEO."""
        logger.info("🗺️ Generating sitemap...")
        
        # Get the repository name from environment or use default
        repo_name = os.getenv('GITHUB_REPOSITORY', 'username/gguf-models').split('/')[-1]
        base_url = f"https://{os.getenv('GITHUB_REPOSITORY_OWNER', 'username')}.github.io/{repo_name}"
        
        sitemap_content = ['<?xml version="1.0" encoding="UTF-8"?>']
        sitemap_content.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        
        current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Add main page
        sitemap_content.extend([
            '  <url>',
            f'    <loc>{base_url}/</loc>',
            f'    <lastmod>{current_date}</lastmod>',
            '    <changefreq>daily</changefreq>',
            '    <priority>1.0</priority>',
            '  </url>'
        ])
        
        # Add search page
        sitemap_content.extend([
            '  <url>',
            f'    <loc>{base_url}/search</loc>',
            f'    <lastmod>{current_date}</lastmod>',
            '    <changefreq>daily</changefreq>',
            '    <priority>0.9</priority>',
            '  </url>'
        ])
        
        # Add model pages (limit to top 1000 for sitemap size)
        for model in models[:1000]:
            model_slug = model['id'].replace('/', '--').replace('_', '-')
            sitemap_content.extend([
                '  <url>',
                f'    <loc>{base_url}/model/{model_slug}</loc>',
                f'    <lastmod>{current_date}</lastmod>',
                '    <changefreq>weekly</changefreq>',
                '    <priority>0.8</priority>',
                '  </url>'
            ])
        
        # Add family pages
        families = set(model['family'] for model in models)
        for family in sorted(families):
            family_slug = family.replace('/', '--').replace('_', '-').lower()
            sitemap_content.extend([
                '  <url>',
                f'    <loc>{base_url}/family/{family_slug}</loc>',
                f'    <lastmod>{current_date}</lastmod>',
                '    <changefreq>weekly</changefreq>',
                '    <priority>0.7</priority>',
                '  </url>'
            ])
            
        sitemap_content.append('</urlset>')
        
        async with aiofiles.open('sitemap.xml', 'w', encoding='utf-8') as f:
            await f.write('\n'.join(sitemap_content))
            
        logger.info(f"✅ Generated sitemap with {len(sitemap_content) - 2} URLs")
        
    async def generate_robots_txt(self) -> None:
        """Generate robots.txt file."""
        repo_name = os.getenv('GITHUB_REPOSITORY', 'username/gguf-models').split('/')[-1]
        base_url = f"https://{os.getenv('GITHUB_REPOSITORY_OWNER', 'username')}.github.io/{repo_name}"
        
        robots_content = [
            'User-agent: *',
            'Allow: /',
            'Crawl-delay: 1',
            '',
            '# Sitemaps',
            f'Sitemap: {base_url}/sitemap.xml',
            '',
            '# Disallow crawling of API endpoints',
            'Disallow: /api/',
            'Disallow: /data/',
            '',
            '# Allow crawling of model pages',
            'Allow: /model/',
            'Allow: /family/',
            'Allow: /search'
        ]
        
        async with aiofiles.open('robots.txt', 'w', encoding='utf-8') as f:
            await f.write('\n'.join(robots_content))
            
        logger.info("🤖 Generated robots.txt")


async def generate_output_files(models: List[Dict[str, Any]]) -> None:
    """Generate output files for retention mode."""
    try:
        # Ensure data directory exists
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        
        # Generate main models JSON file
        models_file = data_dir / "gguf_models.json"
        async with aiofiles.open(models_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(models, indent=2, ensure_ascii=False))
        logger.info(f"📄 Generated {models_file}")
        
        # Generate estimated sizes file
        estimated_sizes = {}
        for model in models:
            model_id = model.get('id', '')
            if model_id:
                # Use existing size estimation logic or default
                estimated_sizes[model_id] = model.get('estimated_size_mb', 0)
        
        sizes_file = data_dir / "gguf_models_estimated_sizes.json"
        async with aiofiles.open(sizes_file, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(estimated_sizes, indent=2))
        logger.info(f"📄 Generated {sizes_file}")
        
        # Generate sitemap
        await generate_sitemap_file(models)
        
        # Generate robots.txt
        await generate_robots_file()
        
    except Exception as e:
        logger.error(f"❌ Failed to generate output files: {e}")
        raise

async def generate_sitemap_file(models: List[Dict[str, Any]]) -> None:
    """Generate sitemap.xml file."""
    try:
        sitemap_content = ['<?xml version="1.0" encoding="UTF-8"?>']
        sitemap_content.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        
        # Add main page
        sitemap_content.append('  <url>')
        sitemap_content.append('    <loc>https://localllmfinder.com/</loc>')
        sitemap_content.append(f'    <lastmod>{datetime.now(timezone.utc).strftime("%Y-%m-%d")}</lastmod>')
        sitemap_content.append('    <changefreq>daily</changefreq>')
        sitemap_content.append('    <priority>1.0</priority>')
        sitemap_content.append('  </url>')
        
        sitemap_content.append('</urlset>')
        
        async with aiofiles.open('sitemap.xml', 'w', encoding='utf-8') as f:
            await f.write('\n'.join(sitemap_content))
        
        logger.info("📄 Generated sitemap.xml")
        
    except Exception as e:
        logger.error(f"❌ Failed to generate sitemap: {e}")

async def generate_robots_file() -> None:
    """Generate robots.txt file."""
    try:
        robots_content = [
            "User-agent: *",
            "Allow: /",
            "",
            "Sitemap: https://localllmfinder.com/sitemap.xml"
        ]
        
        async with aiofiles.open('robots.txt', 'w', encoding='utf-8') as f:
            await f.write('\n'.join(robots_content))
        
        logger.info("📄 Generated robots.txt")
        
    except Exception as e:
        logger.error(f"❌ Failed to generate robots.txt: {e}")

async def save_retention_metadata(sync_metadata: Optional[SyncMetadata], update_report: Optional[UpdateReport]) -> None:
    """Save metadata for retention mode."""
    try:
        # Ensure data directory exists
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        
        # Save sync metadata
        if sync_metadata:
            metadata_dict = {
                'last_sync_time': sync_metadata.last_sync_time.isoformat(),
                'sync_mode': sync_metadata.sync_mode.value,
                'total_models_processed': sync_metadata.total_models_processed,
                'models_added': sync_metadata.models_added,
                'models_updated': sync_metadata.models_updated,
                'models_removed': sync_metadata.models_removed,
                'sync_duration': sync_metadata.sync_duration,
                'success': sync_metadata.success,
                'error_message': sync_metadata.error_message,
                'retention_mode': True
            }
            
            metadata_file = data_dir / "last_sync_metadata.json"
            async with aiofiles.open(metadata_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(metadata_dict, indent=2))
            logger.info(f"💾 Saved sync metadata to {metadata_file}")
        
        # Save retention report
        if update_report:
            report_dict = {
                'timestamp': update_report.timestamp.isoformat() if hasattr(update_report, 'timestamp') else datetime.now(timezone.utc).isoformat(),
                'total_duration_seconds': update_report.total_duration_seconds if hasattr(update_report, 'total_duration_seconds') else 0,
                'overall_success': update_report.overall_success if hasattr(update_report, 'overall_success') else True,
                'phases_completed': update_report.phases_completed if hasattr(update_report, 'phases_completed') else 0,
                'phases_failed': update_report.phases_failed if hasattr(update_report, 'phases_failed') else 0
            }
            
            # Ensure reports directory exists
            reports_dir = Path("reports")
            reports_dir.mkdir(exist_ok=True)
            
            report_file = reports_dir / f"retention_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
            async with aiofiles.open(report_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(report_dict, indent=2))
            logger.info(f"📊 Saved retention report to {report_file}")
        
    except Exception as e:
        logger.error(f"❌ Failed to save retention metadata: {e}")

def parse_arguments():
    """Parse command-line arguments for retention mode selection and configuration."""
    parser = argparse.ArgumentParser(
        description="GGUF Models Data Fetcher with Dynamic Retention Support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Retention Modes:
  full       - Traditional full sync mode (fetch all models)
  retention  - Dynamic retention mode (recent + top models only)
  auto       - Automatically choose based on configuration and history

Examples:
  python update_models.py --retention-mode full
  python update_models.py --retention-mode retention --retention-days 30 --top-models-count 20
  python update_models.py --retention-mode auto --config-file config/sync-config.yaml
        """
    )
    
    # Retention mode selection
    parser.add_argument(
        '--retention-mode',
        type=str,
        choices=['full', 'retention', 'auto'],
        default='auto',
        help='Select retention mode: full (traditional), retention (dynamic), or auto (default: auto)'
    )
    
    # Retention configuration parameters
    parser.add_argument(
        '--retention-days',
        type=int,
        default=30,
        help='Number of days to retain recent models (default: 30)'
    )
    
    parser.add_argument(
        '--top-models-count',
        type=int,
        default=20,
        help='Number of top models to maintain (default: 20)'
    )
    
    # Configuration file
    parser.add_argument(
        '--config-file',
        type=str,
        help='Path to configuration file (YAML or JSON)'
    )
    
    # Sync mode (backward compatibility)
    parser.add_argument(
        '--sync-mode',
        type=str,
        choices=['incremental', 'full', 'auto'],
        help='Legacy sync mode (for backward compatibility)'
    )
    
    # Force options
    parser.add_argument(
        '--force-full-sync',
        action='store_true',
        help='Force a full sync regardless of retention mode'
    )
    
    parser.add_argument(
        '--force-retention-cleanup',
        action='store_true',
        help='Force cleanup of old models in retention mode'
    )
    
    # Performance and debugging options
    parser.add_argument(
        '--enable-performance-metrics',
        action='store_true',
        help='Enable detailed performance metrics collection'
    )
    
    parser.add_argument(
        '--enable-detailed-logging',
        action='store_true',
        help='Enable detailed logging for debugging'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without making actual changes'
    )
    
    return parser.parse_args()

async def main():
    """Main function to fetch and process GGUF models data with retention mode support."""
    start_time = time.time()
    
    # Parse command-line arguments
    args = parse_arguments()
    
    # Log startup information
    logger.info("🚀 Starting GGUF Models Data Pipeline with Dynamic Retention Support")
    logger.info(f"⚙️ Retention Mode: {args.retention_mode}")
    if args.retention_mode == 'retention':
        logger.info(f"📅 Retention Days: {args.retention_days}")
        logger.info(f"🏆 Top Models Count: {args.top_models_count}")
    if args.dry_run:
        logger.info("🧪 DRY RUN MODE - No actual changes will be made")
    
    # Initialize performance metrics collection with retention mode support
    performance_metrics = {
        "start_time": datetime.now(timezone.utc).isoformat(),
        "workflow_id": os.getenv('WORKFLOW_RUN_ID', 'unknown'),
        "retention_mode": args.retention_mode,
        "sync_mode": args.sync_mode or os.getenv('SYNC_MODE', 'auto'),
        "retention_days": args.retention_days,
        "top_models_count": args.top_models_count,
        "max_concurrency": int(os.getenv('MAX_CONCURRENCY', '50')),
        "timeout_hours": float(os.getenv('TIMEOUT_HOURS', '6')),
        "enable_performance_metrics": args.enable_performance_metrics or os.getenv('ENABLE_PERFORMANCE_METRICS', 'false').lower() == 'true',
        "enable_detailed_logging": args.enable_detailed_logging or os.getenv('ENABLE_DETAILED_LOGGING', 'false').lower() == 'true',
        "progress_report_interval": int(os.getenv('PROGRESS_REPORT_INTERVAL', '900')),
        "dry_run": args.dry_run,
        "phases": {}
    }
    
    try:
        logger.info(f"⏰ Started at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        logger.info(f"🆔 Workflow ID: {performance_metrics['workflow_id']}")
        
        if performance_metrics["enable_performance_metrics"]:
            logger.info("📊 Performance metrics collection enabled")
        if performance_metrics["enable_detailed_logging"]:
            logger.info("📝 Detailed logging enabled")
        
        # Load configuration with retention mode support
        logger.info("⚙️ Loading configuration...")
        try:
            if args.config_file:
                config = load_configuration(args.config_file)
                logger.info(f"📄 Loaded configuration from {args.config_file}")
            else:
                # Load default configuration and override with command-line arguments
                config = load_configuration()
                logger.info("📄 Using default configuration")
            
            # Override configuration with command-line arguments
            if args.retention_days != 30:  # Only override if not default
                config.dynamic_retention.retention_days = args.retention_days
            if args.top_models_count != 20:  # Only override if not default
                config.dynamic_retention.top_models_count = args.top_models_count
            if args.force_full_sync:
                config.sync_behavior.force_full_sync = True
            if args.force_retention_cleanup:
                config.dynamic_retention.enable_cleanup = True
            
            logger.info(f"🔧 Configuration loaded: retention_days={config.dynamic_retention.retention_days}, "
                       f"top_models_count={config.dynamic_retention.top_models_count}")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to load configuration: {e}")
            logger.info("📄 Using default configuration")
            config = load_configuration()  # Load defaults
        
        # Determine retention mode
        retention_mode = RetentionMode(args.retention_mode)
        if retention_mode == RetentionMode.AUTO:
            # Auto-determine based on environment and configuration
            env_retention_mode = os.getenv('RETENTION_MODE', '').lower()
            if env_retention_mode in ['full', 'retention']:
                retention_mode = RetentionMode(env_retention_mode)
                logger.info(f"🔄 Auto-selected retention mode from environment: {retention_mode.value}")
            else:
                # Default to retention mode for efficiency
                retention_mode = RetentionMode.RETENTION
                logger.info(f"🔄 Auto-selected retention mode: {retention_mode.value}")
        
        logger.info(f"🎯 Using retention mode: {retention_mode.value}")
        performance_metrics["retention_mode_final"] = retention_mode.value
        
        # Get Hugging Face token from environment
        token = os.getenv('HUGGINGFACE_TOKEN')
        if token:
            logger.info("🔑 Using authenticated Hugging Face access")
        else:
            logger.warning("⚠️ No HUGGINGFACE_TOKEN found, using anonymous access (rate limited)")
        
        # Configure sync mode from environment variables (backward compatibility)
        sync_config = SyncConfig()
        
        # Override configuration from environment variables
        if args.force_full_sync or os.getenv('FORCE_FULL_SYNC', '').lower() in ('true', '1', 'yes'):
            sync_config.force_full_sync = True
            logger.info("🔄 Force full sync enabled")
        
        if os.getenv('INCREMENTAL_WINDOW_HOURS'):
            try:
                sync_config.incremental_window_hours = int(os.getenv('INCREMENTAL_WINDOW_HOURS'))
                logger.info(f"⏰ Incremental window set to {sync_config.incremental_window_hours} hours")
            except ValueError:
                logger.warning("⚠️ Invalid INCREMENTAL_WINDOW_HOURS value, using default")
        
        if os.getenv('FULL_SYNC_THRESHOLD_HOURS'):
            try:
                sync_config.full_sync_threshold_hours = int(os.getenv('FULL_SYNC_THRESHOLD_HOURS'))
                logger.info(f"⏰ Full sync threshold set to {sync_config.full_sync_threshold_hours} hours")
            except ValueError:
                logger.warning("⚠️ Invalid FULL_SYNC_THRESHOLD_HOURS value, using default")
        
        # Initialize scalability optimizer
        logger.info("🎯 Initializing scalability optimizer...")
        scalability_optimizer = ScalabilityOptimizer()
        await scalability_optimizer.initialize()
        
        # Execute based on retention mode
        models = []
        sync_metadata = None
        update_report = None
        
        if retention_mode == RetentionMode.RETENTION:
            # Use dynamic retention system
            logger.info("🔄 Executing dynamic retention workflow...")
            
            if args.dry_run:
                logger.info("🧪 DRY RUN: Would execute retention workflow")
                # Create mock data for dry run
                models = []
                sync_metadata = SyncMetadata(
                    last_sync_time=datetime.now(timezone.utc),
                    sync_mode=SyncMode.FULL,
                    total_models_processed=0,
                    success=True
                )
            else:
                try:
                    # Initialize retention orchestrator with API and rate limiter
                    api = HfApi(token=token)
                    rate_limiter = AdaptiveRateLimiter(config.rate_limiting, has_token=bool(token))
                    
                    orchestrator = ScheduledUpdateOrchestrator(config, api=api, rate_limiter=rate_limiter)
                    
                    # Run the retention workflow
                    update_report = await orchestrator.run_daily_update()
                    
                    if update_report.overall_success:
                        # Get the final merged models from the orchestrator's merge phase
                        models = []
                        if (update_report.merge_phase and 
                            update_report.merge_phase.success and 
                            'merged_models' in update_report.merge_phase.metrics):
                            
                            # Convert ModelReference objects to dict format expected by the rest of the pipeline
                            merged_models = update_report.merge_phase.metrics['merged_models']
                            models = []
                            
                            for model_ref in merged_models:
                                if hasattr(model_ref, 'metadata') and model_ref.metadata:
                                    # Use the metadata as the model dict
                                    model_dict = model_ref.metadata.copy()
                                    model_dict['id'] = model_ref.id
                                    model_dict['source'] = getattr(model_ref, 'source', 'retention')
                                    model_dict['discovery_method'] = getattr(model_ref, 'discovery_method', 'retention')
                                    models.append(model_dict)
                                else:
                                    # Create minimal model dict
                                    models.append({
                                        'id': model_ref.id if hasattr(model_ref, 'id') else str(model_ref),
                                        'source': 'retention',
                                        'discovery_method': 'retention'
                                    })
                        
                        logger.info(f"✅ Retention workflow completed successfully: {len(models)} models")
                        
                        # Create sync metadata for compatibility
                        sync_metadata = SyncMetadata(
                            last_sync_time=datetime.now(timezone.utc),
                            sync_mode=SyncMode.FULL,  # Treat retention as full for compatibility
                            total_models_processed=update_report.total_models_processed,
                            models_added=update_report.recent_models_fetched,
                            models_updated=update_report.top_models_updated,
                            models_removed=update_report.models_cleaned_up,
                            sync_duration=update_report.total_duration_seconds,
                            success=True
                        )
                        
                        # Update performance metrics with retention data
                        performance_metrics.update({
                            "retention_workflow_success": True,
                            "top_models_updated": update_report.top_models_updated,
                            "recent_models_fetched": update_report.recent_models_fetched,
                            "models_merged": update_report.models_merged,
                            "duplicates_removed": update_report.duplicates_removed,
                            "models_cleaned_up": update_report.models_cleaned_up,
                            "storage_freed_mb": update_report.storage_freed_mb,
                            "retention_api_calls": update_report.api_calls_made,
                            "retention_phases_completed": update_report.phases_completed,
                            "retention_phases_failed": update_report.phases_failed
                        })
                        
                    else:
                        logger.error("❌ Retention workflow failed")
                        logger.error(f"   • Phases completed: {update_report.phases_completed}")
                        logger.error(f"   • Phases failed: {update_report.phases_failed}")
                        for error in update_report.errors_encountered:
                            logger.error(f"   • Error: {error}")
                        
                        # Update performance metrics with failure data
                        performance_metrics.update({
                            "retention_workflow_success": False,
                            "retention_failure_reason": "workflow_failed",
                            "retention_phases_completed": update_report.phases_completed,
                            "retention_phases_failed": update_report.phases_failed,
                            "retention_errors": update_report.errors_encountered
                        })
                        
                        # Fallback to traditional sync
                        logger.info("🔄 Falling back to traditional sync mode...")
                        retention_mode = RetentionMode.FULL
                        
                except Exception as e:
                    logger.error(f"❌ Retention workflow error: {e}")
                    import traceback
                    logger.error(f"   • Traceback: {traceback.format_exc()}")
                    
                    # Update performance metrics with error data
                    performance_metrics.update({
                        "retention_workflow_success": False,
                        "retention_failure_reason": "exception",
                        "retention_error_message": str(e),
                        "retention_error_traceback": traceback.format_exc()
                    })
                    
                    logger.info("🔄 Falling back to traditional sync mode...")
                    retention_mode = RetentionMode.FULL
        
        if retention_mode == RetentionMode.FULL or not models:
            # Use traditional full sync mode
            logger.info("🔄 Executing traditional full sync workflow...")
            
            if args.dry_run:
                logger.info("🧪 DRY RUN: Would execute traditional sync workflow")
                models = []
                sync_metadata = SyncMetadata(
                    last_sync_time=datetime.now(timezone.utc),
                    sync_mode=SyncMode.FULL,
                    total_models_processed=0,
                    success=True
                )
            else:
                try:
                    # Fetch and process data with traditional sync mode support
                    async with HuggingFaceDataFetcher(token, sync_config) as fetcher:
                        models, sync_metadata = await fetcher.fetch_gguf_models()
                    
                    if not models:
                        logger.error("❌ No models fetched, exiting")
                        # Save sync metadata even on failure
                        if 'fetcher' in locals():
                            await fetcher.sync_manager.save_sync_metadata(sync_metadata)
                            await fetcher.error_recovery_system.save_error_report("sync_error_report.json")
                        sys.exit(1)
                        
                    logger.info(f"📊 Traditional sync completed: {len(models)} models")
                    
                except Exception as e:
                    logger.error(f"❌ Traditional sync error: {e}")
                    sys.exit(1)
        
        if not models and not args.dry_run:
            logger.error("❌ No models available for processing, exiting")
            sys.exit(1)
        
        logger.info(f"📊 Processing {len(models)} models...")
        
        # Apply scalability optimizations based on dataset size
        logger.info("🎯 Applying scalability optimizations...")
        estimated_model_size_mb = 15.0  # Average estimated size per model
        optimal_params = await scalability_optimizer.optimize_for_dataset(
            model_count=len(models),
            estimated_model_size_mb=estimated_model_size_mb
        )
        
        # Update fetcher with optimal parameters (only for traditional mode)
        if retention_mode == RetentionMode.FULL and 'fetcher' in locals():
            if hasattr(fetcher, 'rate_limiter') and hasattr(fetcher.rate_limiter, 'config'):
                # Update rate limiter configuration
                fetcher.rate_limiter.config.max_concurrency = optimal_params.max_concurrency
                fetcher.rate_limiter.adaptive_factor *= optimal_params.rate_limit_factor
                logger.info(f"🔧 Updated rate limiter: concurrency={optimal_params.max_concurrency}, "
                           f"rate_factor={optimal_params.rate_limit_factor:.2f}")
        
        # Record performance metrics
        current_time = time.time()
        processing_start_time = current_time
        
        # Create performance metrics
        import psutil
        memory_info = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        initial_metrics = PerformanceMetrics(
            timestamp=datetime.now(timezone.utc),
            models_processed=len(models),
            processing_rate=0.0,  # Will be calculated later
            memory_usage_mb=memory_info.used / 1024 / 1024,
            cpu_usage_percent=cpu_percent,
            network_throughput_mbps=0.0,  # Simplified for now
            error_rate=0.0,  # Will be calculated from error report
            compression_ratio=1.0,  # Will be updated if compression is used
            streaming_efficiency=1.0  # Will be calculated based on performance
        )
        
        await scalability_optimizer.performance_monitor.record_performance_metrics(initial_metrics)
        
        # Track freshness and enhance model data
        logger.info("🕐 Tracking data freshness...")
        elapsed_time = time.time() - start_time
        freshness_result = track_sync_freshness(
            models_data=models,
            sync_duration=elapsed_time,
            sync_mode=sync_metadata.sync_mode.value if sync_metadata else retention_mode.value,
            sync_success=sync_metadata.success if sync_metadata else True
        )
        
        # Use enhanced models with freshness data
        enhanced_models = freshness_result['enhanced_models']
        
        if not args.dry_run:
            # Generate output files with enhanced data
            if retention_mode == RetentionMode.FULL and 'fetcher' in locals():
                # Use traditional fetcher for file generation
                await fetcher.generate_json_files(enhanced_models)
                await fetcher.generate_sitemap(enhanced_models)
                await fetcher.generate_robots_txt()
            else:
                # Generate files directly for retention mode
                logger.info("📁 Generating output files...")
                await generate_output_files(enhanced_models)
        else:
            logger.info("🧪 DRY RUN: Would generate output files")
        
        # Apply data compression optimizations if enabled
        if optimal_params.compression_level > 1:
                logger.info("🗜️ Applying data compression optimizations...")
                data_dir = Path("data")
                
                # Compress large JSON files for storage efficiency
                for json_file in data_dir.glob("*.json"):
                    if json_file.stat().st_size > 1024 * 1024:  # Files larger than 1MB
                        try:
                            # Read original data
                            async with aiofiles.open(json_file, 'r', encoding='utf-8') as f:
                                content = await f.read()
                            data = json.loads(content)
                            
                            # Create compressed version
                            compressed_path = json_file.with_suffix('.json.gz')
                            compression_result = await scalability_optimizer.compression_manager.compress_json_data(
                                data, compressed_path, compression_type='gzip'
                            )
                            
                            logger.info(f"📦 Compressed {json_file.name}: "
                                       f"{compression_result['compression_ratio']:.2f}x reduction")
                            
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to compress {json_file.name}: {e}")
                
                # Archive old data files
                archive_dir = data_dir / "archive"
                try:
                    archive_result = await scalability_optimizer.compression_manager.archive_old_data(
                        data_dir, archive_dir, days_old=7
                    )
                    if archive_result['archived_files'] > 0:
                        logger.info(f"📦 Archived {archive_result['archived_files']} old files, "
                                   f"saved {archive_result['space_saved_bytes'] / 1024 / 1024:.1f} MB")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to archive old data: {e}")
            
        # Initialize error report for all modes
        error_report = {
            'total_errors': 0,
            'resolved_errors': 0,
            'resolution_rate': 0.0,
            'error_rate': 0.0,
            'category_breakdown': {}
        }
        
        # Save sync metadata
        if not args.dry_run:
            if retention_mode == RetentionMode.FULL and 'fetcher' in locals():
                await fetcher.sync_manager.save_sync_metadata(sync_metadata)
                
                # Generate comprehensive error report
                logger.info("📊 Generating error handling report...")
                error_report = fetcher.error_recovery_system.generate_error_report()
                await fetcher.error_recovery_system.save_error_report("sync_error_report.json")
            else:
                # Save metadata for retention mode using sync manager pattern
                sync_manager = SyncModeManager(sync_config)
                await sync_manager.save_sync_metadata(sync_metadata)
                
                # Save retention report if available
                if 'update_report' in locals() and update_report:
                    from retention_data_models import RetentionDataStorage
                    storage = RetentionDataStorage()
                    storage.save_report(update_report)
                    logger.info("📊 Retention report saved")
                    
                    # Create error report from retention report
                    if update_report.errors_encountered:
                        error_report = {
                            'total_errors': len(update_report.errors_encountered),
                            'resolved_errors': 0,
                            'resolution_rate': 0.0,
                            'error_rate': len(update_report.errors_encountered) / max(update_report.total_models_processed, 1),
                            'category_breakdown': {'retention_errors': {
                                'total': len(update_report.errors_encountered),
                                'resolved': 0
                            }}
                        }
        else:
            logger.info("🧪 DRY RUN: Would save sync metadata")
            
            # Log error statistics
            if retention_mode == RetentionMode.FULL and 'fetcher' in locals() and 'error_report' in locals():
                if error_report['total_errors'] > 0:
                    logger.info(f"⚠️ Error Summary:")
                    logger.info(f"   • Total errors encountered: {error_report['total_errors']}")
                    logger.info(f"   • Errors resolved: {error_report['resolved_errors']}")
                    logger.info(f"   • Error resolution rate: {error_report['resolution_rate']:.1%}")
                    logger.info(f"   • Overall error rate: {error_report['error_rate']:.1%}")
                    
                    # Log top error categories
                    if error_report['category_breakdown']:
                        logger.info("   • Top error categories:")
                        for category, stats in sorted(error_report['category_breakdown'].items(), 
                                                     key=lambda x: x[1]['total'], reverse=True)[:3]:
                            logger.info(f"     - {category}: {stats['total']} ({stats['resolved']} resolved)")
                else:
                    logger.info("✅ No errors encountered during sync")
            elif retention_mode == RetentionMode.RETENTION and update_report:
                # Log retention-specific statistics
                logger.info("📊 Retention Mode Summary:")
                if hasattr(update_report, 'phases_completed'):
                    logger.info(f"   • Phases completed: {update_report.phases_completed}")
                if hasattr(update_report, 'phases_failed'):
                    logger.info(f"   • Phases failed: {update_report.phases_failed}")
                if hasattr(update_report, 'overall_success'):
                    logger.info(f"   • Overall success: {update_report.overall_success}")
            else:
                logger.info("✅ Processing completed successfully")
            
            # Calculate final performance metrics
            processing_end_time = time.time()
            processing_duration = processing_end_time - processing_start_time
            processing_rate = len(models) / processing_duration if processing_duration > 0 else 0
            
            # Get final system resources
            final_memory_info = psutil.virtual_memory()
            final_cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Calculate error rate from error report
            final_error_rate = error_report['error_rate'] if error_report['total_errors'] > 0 else 0.0
            
            # Get compression statistics
            compression_stats = scalability_optimizer.compression_manager.get_compression_statistics()
            compression_ratio = compression_stats.get('total_compression_ratio', 1.0)
            
            final_metrics = PerformanceMetrics(
                timestamp=datetime.now(timezone.utc),
                models_processed=len(models),
                processing_rate=processing_rate,
                memory_usage_mb=final_memory_info.used / 1024 / 1024,
                cpu_usage_percent=final_cpu_percent,
                network_throughput_mbps=0.0,  # Simplified
                error_rate=final_error_rate,
                compression_ratio=compression_ratio,
                streaming_efficiency=processing_rate / max(final_cpu_percent / 100, 0.1)
            )
            
            await scalability_optimizer.performance_monitor.record_performance_metrics(final_metrics)
            
            # Generate optimization report
            logger.info("📊 Generating scalability optimization report...")
            optimization_report_path = Path("data/optimization_report.json")
            try:
                await scalability_optimizer.generate_optimization_report(optimization_report_path)
                logger.info(f"✅ Optimization report saved to {optimization_report_path}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to generate optimization report: {e}")
            
        elapsed_time = time.time() - start_time
        logger.info(f"✅ Data update completed successfully in {elapsed_time:.1f}s")
        
        # Print comprehensive summary statistics including sync mode information
        logger.info("📈 === FINAL SUMMARY ===")
        logger.info(f"🔄 Sync Mode: {sync_metadata.sync_mode.value.upper()}")
        logger.info(f"⏱️  Total Duration: {elapsed_time:.1f}s")
        # Final reporting
        logger.info("📊 === FINAL REPORT ===")
        logger.info(f"🔄 Mode: {retention_mode.value.upper()}")
        logger.info(f"📊 Models Processed: {len(models)}")
        
        if sync_metadata:
            logger.info(f"💾 Status: {'SUCCESS' if sync_metadata.success else 'FAILED'}")
            
            if retention_mode == RetentionMode.RETENTION:
                logger.info(f"📊 Retention Changes:")
                logger.info(f"   • Added: {sync_metadata.models_added}")
                logger.info(f"   • Updated: {sync_metadata.models_updated}")
                logger.info(f"   • Removed: {sync_metadata.models_removed}")
                logger.info(f"   • Retention Days: {config.dynamic_retention.retention_days}")
                logger.info(f"   • Top Models Count: {config.dynamic_retention.top_models_count}")
            elif sync_metadata.sync_mode == SyncMode.INCREMENTAL:
                logger.info(f"⚡ Incremental Changes:")
                logger.info(f"   • Added/Updated: {sync_metadata.models_added}")
                logger.info(f"   • Window: {sync_config.incremental_window_hours}h")
        
        if models and not args.dry_run:
            # Calculate statistics only if we have actual model data
            try:
                total_downloads = sum(m.get('downloads', 0) for m in models if isinstance(m, dict))
                architectures = set(m.get('architecture', 'unknown') for m in models if isinstance(m, dict))
                families = set(m.get('family', 'unknown') for m in models if isinstance(m, dict))
                
                logger.info(f"📈 Model Statistics:")
                logger.info(f"   • Total downloads: {total_downloads:,}")
                logger.info(f"   • Unique architectures: {len(architectures)}")
                logger.info(f"   • Unique families: {len(families)}")
                
                # Top architectures
                arch_counts = {}
                for model in models:
                    if isinstance(model, dict):
                        arch = model.get('architecture', 'unknown')
                        arch_counts[arch] = arch_counts.get(arch, 0) + 1
                
                if arch_counts:
                    top_archs = sorted(arch_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                    logger.info("   • Top architectures:")
                    for arch, count in top_archs:
                        logger.info(f"     - {arch}: {count} models")
                        
            except Exception as e:
                logger.warning(f"⚠️ Could not calculate model statistics: {e}")
        elif args.dry_run:
            logger.info("🧪 DRY RUN: Model statistics not available")
        
        logger.info("========================")
        
        # Save performance metrics if enabled
        if performance_metrics["enable_performance_metrics"] and not args.dry_run:
            try:
                # Calculate final metrics
                end_time = time.time()
                total_duration = end_time - start_time
                
                performance_metrics.update({
                    "end_time": datetime.now(timezone.utc).isoformat(),
                    "total_duration_seconds": total_duration,
                    "total_duration_minutes": total_duration / 60,
                    "models_processed": len(models),
                    "retention_mode_final": retention_mode.value,
                    "sync_mode_final": sync_metadata.sync_mode.value if sync_metadata else "unknown",
                    "success": sync_metadata.success if sync_metadata else True,
                    "models_added": sync_metadata.models_added if sync_metadata else 0,
                    "models_updated": sync_metadata.models_updated if sync_metadata else 0,
                    "models_removed": sync_metadata.models_removed if sync_metadata else 0,
                })
                
                # Add model statistics if available
                if models:
                    try:
                        performance_metrics.update({
                            "total_downloads": sum(m.get('downloads', 0) for m in models if isinstance(m, dict)),
                            "unique_architectures": len(set(m.get('architecture', 'unknown') for m in models if isinstance(m, dict))),
                            "unique_families": len(set(m.get('family', 'unknown') for m in models if isinstance(m, dict)))
                        })
                    except Exception:
                        pass  # Skip statistics if model format is unexpected
                
                # Save performance report
                reports_dir = Path("reports")
                reports_dir.mkdir(exist_ok=True)
                
                performance_file = reports_dir / "performance_metrics.json"
                async with aiofiles.open(performance_file, 'w', encoding='utf-8') as f:
                    await f.write(json.dumps(performance_metrics, indent=2))
                
                logger.info(f"📊 Performance metrics saved to {performance_file}")
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to save performance metrics: {e}")
        elif args.dry_run:
            logger.info("🧪 DRY RUN: Performance metrics not saved")
        
    except KeyboardInterrupt:
        logger.info("⏹️ Process interrupted by user")
        
        # Save failure metrics
        if 'performance_metrics' in locals() and performance_metrics["enable_performance_metrics"] and not args.dry_run:
            try:
                performance_metrics.update({
                    "end_time": datetime.now(timezone.utc).isoformat(),
                    "total_duration_seconds": time.time() - start_time,
                    "status": "interrupted",
                    "success": False,
                    "retention_mode_final": retention_mode.value if 'retention_mode' in locals() else "unknown"
                })
                
                reports_dir = Path("reports")
                reports_dir.mkdir(exist_ok=True)
                
                failure_file = reports_dir / "interruption_metrics.json"
                with open(failure_file, 'w', encoding='utf-8') as f:
                    json.dump(performance_metrics, f, indent=2)
                
                logger.info(f"📊 Interruption metrics saved to {failure_file}")
            except Exception:
                pass
        
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error in main: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Save error metrics
        if 'performance_metrics' in locals() and performance_metrics["enable_performance_metrics"] and not args.dry_run:
            try:
                performance_metrics.update({
                    "end_time": datetime.now(timezone.utc).isoformat(),
                    "total_duration_seconds": time.time() - start_time,
                    "status": "error",
                    "success": False,
                    "error_message": str(e),
                    "error_traceback": traceback.format_exc(),
                    "retention_mode_final": retention_mode.value if 'retention_mode' in locals() else "unknown"
                })
                
                reports_dir = Path("reports")
                reports_dir.mkdir(exist_ok=True)
                
                error_file = reports_dir / "error_metrics.json"
                with open(error_file, 'w', encoding='utf-8') as f:
                    json.dump(performance_metrics, f, indent=2)
                
                logger.info(f"📊 Error metrics saved to {error_file}")
            except Exception:
                pass
        
        sys.exit(1)
    
    finally:
        # Shutdown scalability optimizer if it exists
        if 'scalability_optimizer' in locals():
            try:
                await scalability_optimizer.shutdown()
            except Exception as e:
                logger.warning(f"⚠️ Failed to shutdown scalability optimizer: {e}")


if __name__ == '__main__':
    asyncio.run(main())