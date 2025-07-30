#!/usr/bin/env python3
"""
TopModelsManager for Dynamic Model Retention System

This module implements the TopModelsManager class that handles daily updates
of the top N most downloaded models from Hugging Face, with ranking comparison,
change detection, and persistent storage functionality.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, asdict
from huggingface_hub import HfApi

# Import existing systems for integration
from config_system import SyncConfiguration, DynamicRetentionConfig
from error_handling import with_error_handling, ErrorContext

logger = logging.getLogger(__name__)

@dataclass
class ModelReference:
    """Reference to a model discovered through top models ranking."""
    id: str
    discovery_method: str = "top_models"
    confidence_score: float = 1.0
    metadata: Dict[str, Any] = None
    download_count: int = 0
    rank: int = 0
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ModelReference to dictionary for JSON serialization."""
        return asdict(self)

@dataclass
class TopModelRanking:
    """Top model ranking with historical data."""
    model_id: str
    rank: int
    download_count: int
    previous_rank: Optional[int] = None
    rank_change: int = 0  # positive = moved up, negative = moved down
    days_in_top: int = 1
    first_top_date: datetime = None
    last_updated: datetime = None
    
    def __post_init__(self):
        if self.first_top_date is None:
            self.first_top_date = datetime.now(timezone.utc)
        if self.last_updated is None:
            self.last_updated = datetime.now(timezone.utc)

@dataclass
class TopModelsUpdateResult:
    """Result of top models update operation."""
    models: List[ModelReference]
    rankings: List[TopModelRanking]
    total_fetched: int
    api_calls_made: int
    update_time_seconds: float
    changes_detected: int
    new_entries: int
    dropped_entries: int
    success: bool
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert TopModelsUpdateResult to dictionary for JSON serialization."""
        result = asdict(self)
        
        # Convert ModelReference and TopModelRanking objects to dicts
        if self.models:
            result['models'] = [asdict(model) for model in self.models]
        if self.rankings:
            result['rankings'] = [ranking.to_dict() if hasattr(ranking, 'to_dict') else asdict(ranking) for ranking in self.rankings]
        
        return result

class TopModelsManager:
    """
    Manages daily updates of the top N most downloaded models.
    
    This class handles fetching, ranking, storage, and change detection
    for the most popular models on Hugging Face, ensuring they remain
    accessible regardless of their upload date.
    """
    
    def __init__(self, config: SyncConfiguration, api: HfApi, rate_limiter):
        """
        Initialize the TopModelsManager.
        
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
        self.top_count = self.retention_config.top_models_count
        
        # Storage paths
        self.storage_dir = Path("data/retention")
        self.top_models_file = self.storage_dir / "top_models.json"
        self.rankings_file = self.storage_dir / "top_rankings.json"
        
        # Initialize error handling
        from retention_error_handling import RetentionErrorRecoverySystem
        self.error_recovery = RetentionErrorRecoverySystem()
        self.history_file = self.storage_dir / "ranking_history.json"
        
        # Ensure storage directory exists
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"🏆 Initialized TopModelsManager:")
        logger.info(f"   • Top models count: {self.top_count}")
        logger.info(f"   • Storage directory: {self.storage_dir}")
        logger.info(f"   • Enable ranking history: {self.retention_config.enable_ranking_history}")
    
    async def update_top_models(self) -> TopModelsUpdateResult:
        """
        Fetch and update the top N most downloaded models.
        
        Returns:
            TopModelsUpdateResult containing the updated models and metadata
        """
        logger.info(f"🔄 Starting top {self.top_count} models update...")
        start_time = datetime.now()
        
        try:
            # Fetch current top models from HF API
            current_models, api_calls = await self._fetch_top_models_from_api()
            
            # Load previous rankings for comparison
            previous_rankings = await self._load_previous_rankings()
            
            # Create new rankings with change detection
            new_rankings = self._create_rankings_with_changes(current_models, previous_rankings)
            
            # Save updated data
            await self._save_top_models(current_models)
            await self._save_rankings(new_rankings)
            
            # Update ranking history if enabled
            if self.retention_config.enable_ranking_history:
                await self._update_ranking_history(new_rankings)
            
            # Calculate statistics
            changes_detected = sum(1 for r in new_rankings if r.rank_change != 0)
            new_entries = sum(1 for r in new_rankings if r.previous_rank is None)
            dropped_entries = len(previous_rankings) - len([r for r in new_rankings if r.previous_rank is not None])
            
            # Calculate update time
            update_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"✅ Top models update completed in {update_time:.1f}s")
            logger.info(f"📊 Update statistics:")
            logger.info(f"   • Models fetched: {len(current_models)}")
            logger.info(f"   • Changes detected: {changes_detected}")
            logger.info(f"   • New entries: {new_entries}")
            logger.info(f"   • Dropped entries: {dropped_entries}")
            logger.info(f"   • API calls made: {api_calls}")
            
            return TopModelsUpdateResult(
                models=current_models,
                rankings=new_rankings,
                total_fetched=len(current_models),
                api_calls_made=api_calls,
                update_time_seconds=update_time,
                changes_detected=changes_detected,
                new_entries=new_entries,
                dropped_entries=dropped_entries,
                success=True
            )
            
        except Exception as e:
            update_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"❌ Top models update failed: {e}")
            
            return TopModelsUpdateResult(
                models=[],
                rankings=[],
                total_fetched=0,
                api_calls_made=0,
                update_time_seconds=update_time,
                changes_detected=0,
                new_entries=0,
                dropped_entries=0,
                success=False,
                error_message=str(e)
            )
    
    async def get_current_top_models(self) -> List[ModelReference]:
        """
        Get currently stored top models.
        
        Returns:
            List of ModelReference objects for current top models
        """
        try:
            if not self.top_models_file.exists():
                logger.info("📁 No stored top models found")
                return []
            
            with open(self.top_models_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            models = []
            for model_data in data.get('models', []):
                model = ModelReference(
                    id=model_data['id'],
                    discovery_method=model_data.get('discovery_method', 'top_models'),
                    confidence_score=model_data.get('confidence_score', 1.0),
                    metadata=model_data.get('metadata', {}),
                    download_count=model_data.get('download_count', 0),
                    rank=model_data.get('rank', 0)
                )
                models.append(model)
            
            logger.info(f"📖 Loaded {len(models)} stored top models")
            return models
            
        except Exception as e:
            logger.error(f"❌ Failed to load current top models: {e}")
            return []
    
    async def get_current_rankings(self) -> List[TopModelRanking]:
        """
        Get current top model rankings.
        
        Returns:
            List of TopModelRanking objects
        """
        return await self._load_previous_rankings()
    
    def compare_rankings(self, old_rankings: List[TopModelRanking], 
                        new_rankings: List[TopModelRanking]) -> Dict[str, Any]:
        """
        Compare rankings and generate change report.
        
        Args:
            old_rankings: Previous rankings
            new_rankings: New rankings
            
        Returns:
            Dictionary containing comparison statistics and changes
        """
        logger.info("📊 Comparing rankings for changes...")
        
        # Create lookup dictionaries
        old_by_id = {r.model_id: r for r in old_rankings}
        new_by_id = {r.model_id: r for r in new_rankings}
        
        # Track changes
        changes = {
            'moved_up': [],
            'moved_down': [],
            'new_entries': [],
            'dropped_out': [],
            'no_change': []
        }
        
        # Analyze new rankings
        for new_ranking in new_rankings:
            model_id = new_ranking.model_id
            
            if model_id in old_by_id:
                old_ranking = old_by_id[model_id]
                rank_change = old_ranking.rank - new_ranking.rank  # Positive = moved up
                
                if rank_change > 0:
                    changes['moved_up'].append({
                        'model_id': model_id,
                        'old_rank': old_ranking.rank,
                        'new_rank': new_ranking.rank,
                        'change': rank_change
                    })
                elif rank_change < 0:
                    changes['moved_down'].append({
                        'model_id': model_id,
                        'old_rank': old_ranking.rank,
                        'new_rank': new_ranking.rank,
                        'change': rank_change
                    })
                else:
                    changes['no_change'].append({
                        'model_id': model_id,
                        'rank': new_ranking.rank
                    })
            else:
                changes['new_entries'].append({
                    'model_id': model_id,
                    'rank': new_ranking.rank,
                    'download_count': new_ranking.download_count
                })
        
        # Find dropped models
        for old_ranking in old_rankings:
            if old_ranking.model_id not in new_by_id:
                changes['dropped_out'].append({
                    'model_id': old_ranking.model_id,
                    'old_rank': old_ranking.rank,
                    'download_count': old_ranking.download_count
                })
        
        # Generate summary statistics
        summary = {
            'total_changes': len(changes['moved_up']) + len(changes['moved_down']) + 
                           len(changes['new_entries']) + len(changes['dropped_out']),
            'moved_up_count': len(changes['moved_up']),
            'moved_down_count': len(changes['moved_down']),
            'new_entries_count': len(changes['new_entries']),
            'dropped_out_count': len(changes['dropped_out']),
            'no_change_count': len(changes['no_change']),
            'stability_ratio': len(changes['no_change']) / len(new_rankings) if new_rankings else 0
        }
        
        logger.info(f"📈 Ranking comparison completed:")
        logger.info(f"   • Total changes: {summary['total_changes']}")
        logger.info(f"   • Moved up: {summary['moved_up_count']}")
        logger.info(f"   • Moved down: {summary['moved_down_count']}")
        logger.info(f"   • New entries: {summary['new_entries_count']}")
        logger.info(f"   • Dropped out: {summary['dropped_out_count']}")
        logger.info(f"   • Stability ratio: {summary['stability_ratio']:.1%}")
        
        return {
            'summary': summary,
            'changes': changes,
            'comparison_timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    async def _fetch_top_models_from_api(self) -> tuple[List[ModelReference], int]:
        """
        Fetch top N models by download count from HF API.
        
        Returns:
            Tuple of (models list, api_calls_made)
        """
        logger.info(f"🌐 Fetching top {self.top_count} models from Hugging Face API...")
        
        api_calls = 0
        models = []
        
        try:
            async with self.rate_limiter:
                # Fetch models sorted by downloads, with GGUF filter
                model_list = list(self.api.list_models(
                    filter="gguf",
                    limit=self.top_count * 2,  # Fetch extra to account for filtering
                    sort="downloads",
                    direction=-1
                ))
                api_calls += 1
            
            # Sort models by download count to ensure proper ranking
            sorted_models = sorted(model_list[:self.top_count * 2], 
                                 key=lambda m: getattr(m, 'downloads', 0), 
                                 reverse=True)
            
            # Process and rank top models
            for i, model in enumerate(sorted_models[:self.top_count]):
                model_ref = ModelReference(
                    id=model.id,
                    discovery_method="top_models",
                    confidence_score=1.0,
                    metadata={
                        "tags": getattr(model, 'tags', []),
                        "created_at": getattr(model, 'created_at', None),
                        "last_modified": getattr(model, 'last_modified', None),
                        "library_name": getattr(model, 'library_name', None)
                    },
                    download_count=getattr(model, 'downloads', 0),
                    rank=i + 1
                )
                models.append(model_ref)
            
            logger.info(f"✅ Successfully fetched {len(models)} top models")
            
            # Log top 5 for verification
            if models:
                logger.info("🏆 Top 5 models:")
                for model in models[:5]:
                    logger.info(f"   {model.rank}. {model.id} ({model.download_count:,} downloads)")
            
            return models, api_calls
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch top models from API: {e}")
            raise
    
    def _create_rankings_with_changes(self, current_models: List[ModelReference], 
                                    previous_rankings: List[TopModelRanking]) -> List[TopModelRanking]:
        """
        Create new rankings with change detection.
        
        Args:
            current_models: Current top models from API
            previous_rankings: Previous rankings for comparison
            
        Returns:
            List of TopModelRanking objects with change information
        """
        logger.info("🔄 Creating rankings with change detection...")
        
        # Create lookup for previous rankings
        previous_by_id = {r.model_id: r for r in previous_rankings}
        
        new_rankings = []
        current_time = datetime.now(timezone.utc)
        
        for model in current_models:
            previous_ranking = previous_by_id.get(model.id)
            
            if previous_ranking:
                # Model was in previous rankings
                rank_change = previous_ranking.rank - model.rank  # Positive = moved up
                days_in_top = previous_ranking.days_in_top + 1
                first_top_date = previous_ranking.first_top_date
            else:
                # New model in top rankings
                rank_change = 0  # No previous rank to compare
                days_in_top = 1
                first_top_date = current_time
            
            ranking = TopModelRanking(
                model_id=model.id,
                rank=model.rank,
                download_count=model.download_count,
                previous_rank=previous_ranking.rank if previous_ranking else None,
                rank_change=rank_change,
                days_in_top=days_in_top,
                first_top_date=first_top_date,
                last_updated=current_time
            )
            
            new_rankings.append(ranking)
        
        logger.info(f"📊 Created {len(new_rankings)} rankings with change detection")
        return new_rankings
    
    async def _save_top_models(self, models: List[ModelReference]) -> None:
        """
        Save top models to persistent storage.
        
        Args:
            models: List of top models to save
        """
        try:
            # Convert models to serializable format
            models_data = []
            for model in models:
                # Convert datetime objects in metadata to ISO strings
                serializable_metadata = {}
                for key, value in model.metadata.items():
                    if isinstance(value, datetime):
                        serializable_metadata[key] = value.isoformat()
                    else:
                        serializable_metadata[key] = value
                
                model_dict = {
                    'id': model.id,
                    'discovery_method': model.discovery_method,
                    'confidence_score': model.confidence_score,
                    'metadata': serializable_metadata,
                    'download_count': model.download_count,
                    'rank': model.rank
                }
                models_data.append(model_dict)
            
            # Create storage data
            storage_data = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'top_count': self.top_count,
                'models': models_data,
                'total_models': len(models)
            }
            
            # Save to file
            with open(self.top_models_file, 'w', encoding='utf-8') as f:
                json.dump(storage_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Saved {len(models)} top models to {self.top_models_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save top models: {e}")
            raise
    
    async def _save_rankings(self, rankings: List[TopModelRanking]) -> None:
        """
        Save rankings to persistent storage.
        
        Args:
            rankings: List of rankings to save
        """
        try:
            # Convert rankings to serializable format
            rankings_data = []
            for ranking in rankings:
                ranking_dict = asdict(ranking)
                # Convert datetime objects to ISO strings
                ranking_dict['first_top_date'] = ranking.first_top_date.isoformat()
                ranking_dict['last_updated'] = ranking.last_updated.isoformat()
                rankings_data.append(ranking_dict)
            
            # Create storage data
            storage_data = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'rankings': rankings_data,
                'total_rankings': len(rankings)
            }
            
            # Save to file
            with open(self.rankings_file, 'w', encoding='utf-8') as f:
                json.dump(storage_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Saved {len(rankings)} rankings to {self.rankings_file}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save rankings: {e}")
            raise
    
    async def _load_previous_rankings(self) -> List[TopModelRanking]:
        """
        Load previous rankings from storage.
        
        Returns:
            List of previous TopModelRanking objects
        """
        try:
            if not self.rankings_file.exists():
                logger.info("📁 No previous rankings found")
                return []
            
            with open(self.rankings_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            rankings = []
            for ranking_data in data.get('rankings', []):
                ranking = TopModelRanking(
                    model_id=ranking_data['model_id'],
                    rank=ranking_data['rank'],
                    download_count=ranking_data['download_count'],
                    previous_rank=ranking_data.get('previous_rank'),
                    rank_change=ranking_data.get('rank_change', 0),
                    days_in_top=ranking_data.get('days_in_top', 1),
                    first_top_date=datetime.fromisoformat(ranking_data['first_top_date']),
                    last_updated=datetime.fromisoformat(ranking_data['last_updated'])
                )
                rankings.append(ranking)
            
            logger.info(f"📖 Loaded {len(rankings)} previous rankings")
            return rankings
            
        except Exception as e:
            logger.error(f"❌ Failed to load previous rankings: {e}")
            return []
    
    async def _update_ranking_history(self, rankings: List[TopModelRanking]) -> None:
        """
        Update ranking history for trend analysis.
        
        Args:
            rankings: Current rankings to add to history
        """
        if not self.retention_config.enable_ranking_history:
            return
        
        try:
            # Load existing history
            history = []
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            
            # Add current rankings to history
            current_entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'rankings': [
                    {
                        'model_id': r.model_id,
                        'rank': r.rank,
                        'download_count': r.download_count,
                        'rank_change': r.rank_change
                    }
                    for r in rankings
                ]
            }
            
            history.append(current_entry)
            
            # Keep only recent history (based on configuration)
            max_history_days = self.retention_config.ranking_history_days
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_history_days)
            
            # Filter history to keep only recent entries
            filtered_history = []
            for entry in history:
                entry_date = datetime.fromisoformat(entry['timestamp'])
                if entry_date >= cutoff_date:
                    filtered_history.append(entry)
            
            # Save updated history
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(filtered_history, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📈 Updated ranking history: {len(filtered_history)} entries kept")
            
        except Exception as e:
            logger.error(f"❌ Failed to update ranking history: {e}")
            # Don't raise - history is not critical
    
    async def update_top_models_with_error_handling(self, error_recovery_system=None) -> TopModelsUpdateResult:
        """
        Update top models with comprehensive error handling.
        
        Args:
            error_recovery_system: Optional error recovery system for advanced error handling
            
        Returns:
            TopModelsUpdateResult with success/failure information
        """
        if error_recovery_system:
            return await with_error_handling(
                self.update_top_models,
                "update_top_models",
                error_recovery_system,
                model_id="top_models_manager"
            )
        else:
            return await self.update_top_models()