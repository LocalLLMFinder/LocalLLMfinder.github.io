#!/usr/bin/env python3
"""
DateFilteredExtractor for Dynamic Model Retention System

This module implements the DateFilteredExtractor class that handles extraction
of models uploaded within the last N days from Hugging Face, with proper
date-based filtering, API integration, and error handling.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
from huggingface_hub import HfApi
from dateutil import parser as date_parser

# Import existing systems for integration
from config_system import SyncConfiguration, DynamicRetentionConfig
from error_handling import with_error_handling, ErrorContext

logger = logging.getLogger(__name__)

@dataclass
class ModelReference:
    """Reference to a model discovered through date filtering."""
    id: str
    discovery_method: str = "date_filtered"
    confidence_score: float = 1.0
    metadata: Dict[str, Any] = None
    upload_date: Optional[datetime] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class DateFilterResult:
    """Result of date-filtered extraction."""
    models: List[ModelReference]
    total_found: int
    date_range_start: datetime
    date_range_end: datetime
    api_calls_made: int
    extraction_time_seconds: float
    success: bool
    error_message: Optional[str] = None

class DateFilteredExtractor:
    """
    Handles extraction of models uploaded within the last N days from Hugging Face.
    
    This class implements efficient date-based filtering to minimize API calls
    while ensuring we capture all recently uploaded models. It integrates with
    the existing rate limiting and error handling systems.
    """
    
    def __init__(self, config: SyncConfiguration, api: HfApi, rate_limiter):
        """
        Initialize the DateFilteredExtractor.
        
        Args:
            config: System configuration containing retention settings
            api: HuggingFace API instance
            rate_limiter: Rate limiter for API calls
        """
        self.config = config
        self.api = api
        self.rate_limiter = rate_limiter
        
        # Get retention configuration
        self.retention_config = config.dynamic_retention
        self.retention_days = self.retention_config.retention_days
        
        logger.info(f"🗓️ Initialized DateFilteredExtractor:")
        logger.info(f"   • Retention period: {self.retention_days} days")
        logger.info(f"   • Recent models priority: {self.retention_config.recent_models_priority}")
    
    async def extract_recent_models(self) -> DateFilterResult:
        """
        Extract models uploaded in the last N days.
        
        Returns:
            DateFilterResult containing the extracted models and metadata
        """
        logger.info(f"🔍 Starting extraction of models from last {self.retention_days} days...")
        start_time = datetime.now()
        
        try:
            # Calculate date range
            cutoff_date = self.calculate_cutoff_date()
            current_date = datetime.now(timezone.utc)
            
            logger.info(f"📅 Date range: {cutoff_date.isoformat()} to {current_date.isoformat()}")
            
            # Extract models using date filtering
            models, api_calls = await self._extract_models_with_date_filter(cutoff_date)
            
            # Calculate extraction time
            extraction_time = (datetime.now() - start_time).total_seconds()
            
            # Create result
            result = DateFilterResult(
                models=models,
                total_found=len(models),
                date_range_start=cutoff_date,
                date_range_end=current_date,
                api_calls_made=api_calls,
                extraction_time_seconds=extraction_time,
                success=True
            )
            
            logger.info(f"✅ Date-filtered extraction completed:")
            logger.info(f"   • Models found: {len(models)}")
            logger.info(f"   • API calls made: {api_calls}")
            logger.info(f"   • Extraction time: {extraction_time:.1f}s")
            
            return result
            
        except Exception as e:
            extraction_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Date-filtered extraction failed: {e}")
            
            return DateFilterResult(
                models=[],
                total_found=0,
                date_range_start=self.calculate_cutoff_date(),
                date_range_end=datetime.now(timezone.utc),
                api_calls_made=0,
                extraction_time_seconds=extraction_time,
                success=False,
                error_message=str(e)
            )
    
    def calculate_cutoff_date(self) -> datetime:
        """
        Calculate the cutoff date for recent models.
        
        Returns:
            datetime: The cutoff date (N days ago from now)
        """
        current_time = datetime.now(timezone.utc)
        cutoff_date = current_time - timedelta(days=self.retention_days)
        
        logger.debug(f"📅 Calculated cutoff date: {cutoff_date.isoformat()}")
        return cutoff_date
    
    async def get_date_filter_query(self) -> str:
        """
        Generate HuggingFace API query with date filters.
        
        Returns:
            str: Query string for HF API with date filtering
        """
        cutoff_date = self.calculate_cutoff_date()
        
        # Format date for HF API (ISO format)
        date_filter = cutoff_date.strftime("%Y-%m-%d")
        
        # Construct query with GGUF filter and date constraint
        query = f"gguf created:>{date_filter}"
        
        logger.debug(f"🔍 Generated date filter query: {query}")
        return query
    
    async def _extract_models_with_date_filter(self, cutoff_date: datetime) -> tuple[List[ModelReference], int]:
        """
        Extract models using date filtering with proper API integration.
        
        Args:
            cutoff_date: The cutoff date for filtering models
            
        Returns:
            tuple: (List of ModelReference objects, number of API calls made)
        """
        models = []
        api_calls = 0
        
        try:
            # Use the HF API search with date filtering
            async with self.rate_limiter:
                api_calls += 1
                
                # Search for GGUF models created after cutoff date
                date_filter = cutoff_date.strftime("%Y-%m-%d")
                
                logger.info(f"🔍 Searching for GGUF models created after {date_filter}")
                
                # Use list_models with search parameter for date filtering
                model_list = list(self.api.list_models(
                    search=f"gguf",
                    sort="createdAt",
                    direction=-1,  # Most recent first
                    limit=None  # Get all matching models
                ))
                
                logger.info(f"📊 Found {len(model_list)} models from initial search")
            
            # Filter models by actual creation date
            filtered_models = []
            for model in model_list:
                try:
                    # Get model creation date
                    created_at = getattr(model, 'createdAt', None) or getattr(model, 'created_at', None)
                    

                    
                    if created_at:
                        # Parse the creation date
                        if isinstance(created_at, str):
                            model_date = date_parser.parse(created_at)
                        else:
                            model_date = created_at
                        
                        # Ensure timezone awareness
                        if model_date.tzinfo is None:
                            model_date = model_date.replace(tzinfo=timezone.utc)
                        
                        # Check if model is within our date range
                        if model_date >= cutoff_date:
                            # Verify this is actually a GGUF model
                            if self._is_gguf_model(model):
                                model_ref = ModelReference(
                                    id=model.id,
                                    discovery_method="date_filtered",
                                    confidence_score=1.0,
                                    metadata={
                                        "created_at": model_date.isoformat(),
                                        "downloads": getattr(model, 'downloads', 0),
                                        "tags": getattr(model, 'tags', []),
                                        "author": getattr(model, 'author', ''),
                                        "pipeline_tag": getattr(model, 'pipeline_tag', '')
                                    },
                                    upload_date=model_date
                                )
                                filtered_models.append(model_ref)
                    else:
                        # If no creation date, include it to be safe (recent models priority)
                        if self.retention_config.recent_models_priority and self._is_gguf_model(model):
                            model_ref = ModelReference(
                                id=model.id,
                                discovery_method="date_filtered_no_date",
                                confidence_score=0.8,
                                metadata={
                                    "created_at": None,
                                    "downloads": getattr(model, 'downloads', 0),
                                    "tags": getattr(model, 'tags', []),
                                    "author": getattr(model, 'author', ''),
                                    "pipeline_tag": getattr(model, 'pipeline_tag', '')
                                },
                                upload_date=None
                            )
                            filtered_models.append(model_ref)
                            
                except Exception as e:
                    logger.debug(f"Error processing model {getattr(model, 'id', 'unknown')}: {e}")
                    continue
            
            models = filtered_models
            logger.info(f"✅ Date filtering completed: {len(models)} models within {self.retention_days} days")
            
        except Exception as e:
            logger.error(f"❌ Error during date-filtered extraction: {e}")
            raise
        
        return models, api_calls
    
    def _is_gguf_model(self, model) -> bool:
        """
        Check if a model is actually a GGUF model.
        
        Args:
            model: HuggingFace model object
            
        Returns:
            bool: True if the model is a GGUF model
        """
        model_id = getattr(model, 'id', '').lower()
        tags = [tag.lower() for tag in getattr(model, 'tags', [])]
        
        # Check for GGUF indicators
        gguf_indicators = [
            'gguf', 'ggml', '.gguf', '-gguf', '_gguf',
            'q4_k_m', 'q4_0', 'q5_0', 'q8_0', 'f16', 'f32'
        ]
        
        # Check model ID
        if any(indicator in model_id for indicator in gguf_indicators):
            return True
        
        # Check tags
        if any(indicator in tag for tag in tags for indicator in gguf_indicators):
            return True
        
        # Check for quantization patterns
        import re
        quantization_patterns = [
            r'q\d+_k_[msl]', r'q\d+_\d+', r'iq\d+_[a-z]+', 
            r'f\d+', r'bf\d+', r'int\d+'
        ]
        
        for pattern in quantization_patterns:
            if re.search(pattern, model_id):
                return True
        
        return False
    
    async def extract_with_error_handling(self, error_recovery_system=None) -> DateFilterResult:
        """
        Extract recent models with comprehensive error handling.
        
        This method wraps the main extraction logic with the existing
        error handling system for consistent error management.
        
        Args:
            error_recovery_system: Optional error recovery system for handling errors
        
        Returns:
            DateFilterResult: The extraction result with error handling
        """
        if error_recovery_system:
            return await with_error_handling(
                self.extract_recent_models,
                "date_filtered_extraction",
                error_recovery_system
            )
        else:
            # Fallback to direct extraction if no error recovery system provided
            return await self.extract_recent_models()
    
    def get_extraction_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the extraction configuration and capabilities.
        
        Returns:
            Dict containing extraction statistics and configuration
        """
        return {
            "retention_days": self.retention_days,
            "recent_models_priority": self.retention_config.recent_models_priority,
            "cutoff_date": self.calculate_cutoff_date().isoformat(),
            "extractor_type": "DateFilteredExtractor",
            "api_integration": "HuggingFace Hub API",
            "rate_limiting": "Integrated with AdaptiveRateLimiter",
            "error_handling": "Integrated with ErrorRecoverySystem"
        }