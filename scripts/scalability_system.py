#!/usr/bin/env python3
"""
Scalability and Performance Optimization System

This module provides automatic processing parameter adjustment, streaming processing,
parallel optimizations, data compression, and performance monitoring capabilities
for the GGUF model synchronization system.
"""

import asyncio
import json
import logging
import os
import sys
import time
import gzip
import lzma
import zlib
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, AsyncGenerator, Tuple, Union
import psutil
import aiofiles
from concurrent.futures import ThreadPoolExecutor
import threading

logger = logging.getLogger(__name__)

@dataclass
class SystemResources:
    """Current system resource utilization."""
    cpu_percent: float
    memory_percent: float
    memory_available_gb: float
    disk_free_gb: float
    network_io_mbps: float
    load_average: float

@dataclass
class ProcessingParameters:
    """Dynamic processing parameters based on system state."""
    max_concurrency: int
    batch_size: int
    rate_limit_factor: float
    memory_threshold_mb: int
    enable_streaming: bool
    compression_level: int
    chunk_size: int

@dataclass
class PerformanceMetrics:
    """Performance metrics for monitoring and optimization."""
    timestamp: datetime
    models_processed: int
    processing_rate: float  # models per second
    memory_usage_mb: float
    cpu_usage_percent: float
    network_throughput_mbps: float
    error_rate: float
    compression_ratio: float
    streaming_efficiency: float
    
@dataclass
class ScalingRecommendation:
    """Recommendations for infrastructure scaling."""
    current_performance: PerformanceMetrics
    bottleneck_type: str  # 'cpu', 'memory', 'network', 'api_rate'
    severity: str  # 'low', 'medium', 'high', 'critical'
    recommendation: str
    estimated_improvement: float
    cost_impact: str  # 'low', 'medium', 'high'

class SystemResourceMonitor:
    """Monitors system resources and provides real-time metrics."""
    
    def __init__(self, monitoring_interval: float = 1.0):
        self.monitoring_interval = monitoring_interval
        self.resource_history = deque(maxlen=300)  # 5 minutes at 1s intervals
        self._monitoring_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
    async def start_monitoring(self):
        """Start continuous resource monitoring."""
        logger.info("🔍 Starting system resource monitoring")
        self._monitoring_task = asyncio.create_task(self._monitor_resources())
        
    async def stop_monitoring(self):
        """Stop resource monitoring."""
        logger.info("⏹️ Stopping system resource monitoring")
        self._shutdown_event.set()
        if self._monitoring_task:
            await self._monitoring_task
            
    async def get_current_resources(self) -> SystemResources:
        """Get current system resource utilization."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available_gb = memory.available / (1024**3)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_free_gb = disk.free / (1024**3)
            
            # Network I/O (simplified)
            network_io = psutil.net_io_counters()
            network_io_mbps = (network_io.bytes_sent + network_io.bytes_recv) / (1024**2)
            
            # Load average (Unix-like systems)
            try:
                load_average = os.getloadavg()[0] if hasattr(os, 'getloadavg') else cpu_percent / 100
            except (OSError, AttributeError):
                load_average = cpu_percent / 100
                
            return SystemResources(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_available_gb=memory_available_gb,
                disk_free_gb=disk_free_gb,
                network_io_mbps=network_io_mbps,
                load_average=load_average
            )
            
        except Exception as e:
            logger.warning(f"Failed to get system resources: {e}")
            # Return safe defaults
            return SystemResources(
                cpu_percent=50.0,
                memory_percent=50.0,
                memory_available_gb=4.0,
                disk_free_gb=10.0,
                network_io_mbps=10.0,
                load_average=0.5
            )
    
    async def _monitor_resources(self):
        """Background task for continuous resource monitoring."""
        while not self._shutdown_event.is_set():
            try:
                resources = await self.get_current_resources()
                self.resource_history.append((time.time(), resources))
                
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.monitoring_interval
                )
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in resource monitoring: {e}")
                await asyncio.sleep(self.monitoring_interval)
    
    def get_resource_trends(self, window_seconds: int = 60) -> Dict[str, float]:
        """Get resource usage trends over specified window."""
        if not self.resource_history:
            return {}
            
        current_time = time.time()
        cutoff_time = current_time - window_seconds
        
        # Filter recent data
        recent_data = [
            (timestamp, resources) for timestamp, resources in self.resource_history
            if timestamp >= cutoff_time
        ]
        
        if len(recent_data) < 2:
            return {}
        
        # Calculate trends
        cpu_values = [r.cpu_percent for _, r in recent_data]
        memory_values = [r.memory_percent for _, r in recent_data]
        
        return {
            'cpu_trend': (cpu_values[-1] - cpu_values[0]) / len(cpu_values),
            'memory_trend': (memory_values[-1] - memory_values[0]) / len(memory_values),
            'cpu_avg': sum(cpu_values) / len(cpu_values),
            'memory_avg': sum(memory_values) / len(memory_values),
            'cpu_max': max(cpu_values),
            'memory_max': max(memory_values)
        }

class DynamicParameterAdjuster:
    """Automatically adjusts processing parameters based on system state and model count."""
    
    def __init__(self, resource_monitor: SystemResourceMonitor):
        self.resource_monitor = resource_monitor
        self.base_parameters = ProcessingParameters(
            max_concurrency=50,
            batch_size=100,
            rate_limit_factor=1.0,
            memory_threshold_mb=1024,
            enable_streaming=False,
            compression_level=6,
            chunk_size=1000
        )
        
    async def calculate_optimal_parameters(self, model_count: int, 
                                         estimated_model_size_mb: float = 10.0) -> ProcessingParameters:
        """Calculate optimal processing parameters based on current conditions."""
        logger.info(f"🎯 Calculating optimal parameters for {model_count} models")
        
        # Get current system resources
        resources = await self.resource_monitor.get_current_resources()
        trends = self.resource_monitor.get_resource_trends()
        
        # Calculate base parameters
        params = ProcessingParameters(
            max_concurrency=self._calculate_optimal_concurrency(resources, model_count),
            batch_size=self._calculate_optimal_batch_size(resources, model_count),
            rate_limit_factor=self._calculate_rate_limit_factor(resources, trends),
            memory_threshold_mb=self._calculate_memory_threshold(resources),
            enable_streaming=self._should_enable_streaming(resources, model_count, estimated_model_size_mb),
            compression_level=self._calculate_compression_level(resources),
            chunk_size=self._calculate_chunk_size(resources, model_count)
        )
        
        logger.info(f"📊 Optimal parameters calculated:")
        logger.info(f"   • Max concurrency: {params.max_concurrency}")
        logger.info(f"   • Batch size: {params.batch_size}")
        logger.info(f"   • Rate limit factor: {params.rate_limit_factor:.2f}")
        logger.info(f"   • Memory threshold: {params.memory_threshold_mb}MB")
        logger.info(f"   • Streaming enabled: {params.enable_streaming}")
        logger.info(f"   • Compression level: {params.compression_level}")
        logger.info(f"   • Chunk size: {params.chunk_size}")
        
        return params
    
    def _calculate_optimal_concurrency(self, resources: SystemResources, model_count: int) -> int:
        """Calculate optimal concurrency based on system resources."""
        base_concurrency = 50
        
        # Adjust based on CPU availability
        if resources.cpu_percent < 30:
            cpu_factor = 1.5
        elif resources.cpu_percent < 60:
            cpu_factor = 1.0
        elif resources.cpu_percent < 80:
            cpu_factor = 0.7
        else:
            cpu_factor = 0.5
        
        # Adjust based on memory availability
        if resources.memory_available_gb > 8:
            memory_factor = 1.2
        elif resources.memory_available_gb > 4:
            memory_factor = 1.0
        elif resources.memory_available_gb > 2:
            memory_factor = 0.8
        else:
            memory_factor = 0.5
        
        # Adjust based on model count (larger datasets need more concurrency)
        if model_count > 10000:
            scale_factor = 1.5
        elif model_count > 5000:
            scale_factor = 1.2
        elif model_count > 1000:
            scale_factor = 1.0
        else:
            scale_factor = 0.8
        
        optimal_concurrency = int(base_concurrency * cpu_factor * memory_factor * scale_factor)
        return max(10, min(optimal_concurrency, 100))  # Clamp between 10-100
    
    def _calculate_optimal_batch_size(self, resources: SystemResources, model_count: int) -> int:
        """Calculate optimal batch size for processing."""
        base_batch_size = 100
        
        # Larger batches for more memory
        if resources.memory_available_gb > 8:
            memory_factor = 2.0
        elif resources.memory_available_gb > 4:
            memory_factor = 1.5
        elif resources.memory_available_gb > 2:
            memory_factor = 1.0
        else:
            memory_factor = 0.5
        
        # Adjust for dataset size
        if model_count > 20000:
            size_factor = 2.0
        elif model_count > 10000:
            size_factor = 1.5
        elif model_count > 5000:
            size_factor = 1.0
        else:
            size_factor = 0.8
        
        optimal_batch_size = int(base_batch_size * memory_factor * size_factor)
        return max(50, min(optimal_batch_size, 500))  # Clamp between 50-500
    
    def _calculate_rate_limit_factor(self, resources: SystemResources, 
                                   trends: Dict[str, float]) -> float:
        """Calculate rate limiting adjustment factor."""
        base_factor = 1.0
        
        # Reduce rate if system is under stress
        if resources.cpu_percent > 80 or resources.memory_percent > 85:
            stress_factor = 0.7
        elif resources.cpu_percent > 60 or resources.memory_percent > 70:
            stress_factor = 0.85
        else:
            stress_factor = 1.0
        
        # Consider trends
        trend_factor = 1.0
        if trends.get('cpu_trend', 0) > 5 or trends.get('memory_trend', 0) > 5:
            trend_factor = 0.9  # Slow down if resources are increasing rapidly
        
        return base_factor * stress_factor * trend_factor
    
    def _calculate_memory_threshold(self, resources: SystemResources) -> int:
        """Calculate memory threshold for streaming activation."""
        # Use 70% of available memory as threshold
        available_mb = resources.memory_available_gb * 1024 * 0.7
        return max(512, min(int(available_mb), 4096))  # Clamp between 512MB-4GB
    
    def _should_enable_streaming(self, resources: SystemResources, 
                               model_count: int, estimated_model_size_mb: float) -> bool:
        """Determine if streaming processing should be enabled."""
        # Estimate total memory needed
        estimated_total_mb = model_count * estimated_model_size_mb
        available_mb = resources.memory_available_gb * 1024
        
        # Enable streaming if dataset is large or memory is limited
        if estimated_total_mb > available_mb * 0.8:
            return True
        
        if model_count > 15000:  # Large datasets benefit from streaming
            return True
        
        if resources.memory_available_gb < 4:  # Limited memory systems
            return True
        
        return False
    
    def _calculate_compression_level(self, resources: SystemResources) -> int:
        """Calculate optimal compression level based on CPU availability."""
        if resources.cpu_percent < 30:
            return 9  # Maximum compression when CPU is available
        elif resources.cpu_percent < 60:
            return 6  # Balanced compression
        elif resources.cpu_percent < 80:
            return 3  # Light compression
        else:
            return 1  # Minimal compression when CPU is stressed
    
    def _calculate_chunk_size(self, resources: SystemResources, model_count: int) -> int:
        """Calculate optimal chunk size for streaming processing."""
        base_chunk_size = 1000
        
        # Larger chunks for more memory
        if resources.memory_available_gb > 8:
            memory_factor = 2.0
        elif resources.memory_available_gb > 4:
            memory_factor = 1.5
        else:
            memory_factor = 1.0
        
        # Adjust for dataset size
        if model_count > 50000:
            size_factor = 0.5  # Smaller chunks for very large datasets
        elif model_count > 20000:
            size_factor = 0.8
        else:
            size_factor = 1.0
        
        optimal_chunk_size = int(base_chunk_size * memory_factor * size_factor)
        return max(100, min(optimal_chunk_size, 5000))  # Clamp between 100-5000

class StreamingProcessor:
    """Handles streaming processing for large datasets to manage memory constraints."""
    
    def __init__(self, chunk_size: int = 1000, memory_threshold_mb: int = 1024):
        self.chunk_size = chunk_size
        self.memory_threshold_mb = memory_threshold_mb
        self.processed_count = 0
        self.total_count = 0
        
    async def process_stream(self, data_source: AsyncGenerator[Any, None],
                           process_func: callable,
                           output_handler: callable) -> Dict[str, Any]:
        """Process data in streaming fashion with memory management."""
        logger.info(f"🌊 Starting streaming processing (chunk size: {self.chunk_size})")
        
        start_time = time.time()
        chunk_buffer = []
        total_processed = 0
        total_errors = 0
        
        try:
            async for item in data_source:
                chunk_buffer.append(item)
                
                # Process chunk when buffer is full or memory threshold reached
                if (len(chunk_buffer) >= self.chunk_size or 
                    await self._should_process_chunk()):
                    
                    processed, errors = await self._process_chunk(
                        chunk_buffer, process_func, output_handler
                    )
                    
                    total_processed += processed
                    total_errors += errors
                    
                    # Clear buffer and log progress
                    chunk_buffer.clear()
                    await self._log_streaming_progress(total_processed, total_errors)
                    
                    # Optional memory cleanup
                    await self._cleanup_memory()
            
            # Process remaining items in buffer
            if chunk_buffer:
                processed, errors = await self._process_chunk(
                    chunk_buffer, process_func, output_handler
                )
                total_processed += processed
                total_errors += errors
            
            elapsed_time = time.time() - start_time
            
            logger.info(f"✅ Streaming processing completed:")
            logger.info(f"   • Total processed: {total_processed}")
            logger.info(f"   • Total errors: {total_errors}")
            logger.info(f"   • Processing time: {elapsed_time:.1f}s")
            logger.info(f"   • Rate: {total_processed/elapsed_time:.2f} items/sec")
            
            return {
                'total_processed': total_processed,
                'total_errors': total_errors,
                'processing_time': elapsed_time,
                'processing_rate': total_processed / elapsed_time if elapsed_time > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"❌ Streaming processing failed: {e}")
            raise
    
    async def _should_process_chunk(self) -> bool:
        """Check if chunk should be processed based on memory usage."""
        try:
            memory = psutil.virtual_memory()
            memory_used_mb = (memory.total - memory.available) / (1024**2)
            return memory_used_mb > self.memory_threshold_mb
        except:
            return False
    
    async def _process_chunk(self, chunk: List[Any], process_func: callable,
                           output_handler: callable) -> Tuple[int, int]:
        """Process a single chunk of data."""
        processed_count = 0
        error_count = 0
        
        try:
            # Process chunk items
            results = []
            for item in chunk:
                try:
                    result = await process_func(item)
                    if result is not None:
                        results.append(result)
                        processed_count += 1
                except Exception as e:
                    logger.debug(f"Error processing item: {e}")
                    error_count += 1
            
            # Handle output
            if results:
                await output_handler(results)
            
        except Exception as e:
            logger.error(f"Error processing chunk: {e}")
            error_count += len(chunk)
        
        return processed_count, error_count
    
    async def _log_streaming_progress(self, total_processed: int, total_errors: int):
        """Log streaming processing progress."""
        if total_processed % (self.chunk_size * 10) == 0:  # Log every 10 chunks
            success_rate = (total_processed / (total_processed + total_errors)) * 100 if (total_processed + total_errors) > 0 else 0
            logger.info(f"🌊 Streaming progress: {total_processed} processed, "
                       f"{total_errors} errors ({success_rate:.1f}% success)")
    
    async def _cleanup_memory(self):
        """Perform memory cleanup between chunks."""
        # Force garbage collection
        import gc
        gc.collect()
        
        # Small delay to allow system cleanup
        await asyncio.sleep(0.1)

class DataCompressionManager:
    """Manages data compression and archiving for storage efficiency."""
    
    def __init__(self, compression_level: int = 6):
        self.compression_level = compression_level
        self.compression_stats = {
            'files_compressed': 0,
            'original_size': 0,
            'compressed_size': 0,
            'compression_time': 0.0
        }
        
    async def compress_json_data(self, data: Dict[str, Any], 
                               output_path: Path,
                               compression_type: str = 'gzip') -> Dict[str, Any]:
        """Compress JSON data with specified compression algorithm."""
        logger.info(f"🗜️ Compressing data to {output_path} using {compression_type}")
        
        start_time = time.time()
        
        # Serialize data to JSON
        json_data = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
        original_size = len(json_data.encode('utf-8'))
        
        # Compress data
        compressed_data = await self._compress_data(json_data.encode('utf-8'), compression_type)
        compressed_size = len(compressed_data)
        
        # Write compressed data
        async with aiofiles.open(output_path, 'wb') as f:
            await f.write(compressed_data)
        
        compression_time = time.time() - start_time
        compression_ratio = original_size / compressed_size if compressed_size > 0 else 1.0
        
        # Update statistics
        self.compression_stats['files_compressed'] += 1
        self.compression_stats['original_size'] += original_size
        self.compression_stats['compressed_size'] += compressed_size
        self.compression_stats['compression_time'] += compression_time
        
        logger.info(f"✅ Compression completed:")
        logger.info(f"   • Original size: {original_size / 1024:.1f} KB")
        logger.info(f"   • Compressed size: {compressed_size / 1024:.1f} KB")
        logger.info(f"   • Compression ratio: {compression_ratio:.2f}x")
        logger.info(f"   • Time: {compression_time:.2f}s")
        
        return {
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': compression_ratio,
            'compression_time': compression_time,
            'compression_type': compression_type
        }
    
    async def decompress_json_data(self, input_path: Path,
                                 compression_type: str = 'gzip') -> Dict[str, Any]:
        """Decompress JSON data."""
        logger.info(f"📂 Decompressing data from {input_path} using {compression_type}")
        
        start_time = time.time()
        
        # Read compressed data
        async with aiofiles.open(input_path, 'rb') as f:
            compressed_data = await f.read()
        
        # Decompress data
        decompressed_data = await self._decompress_data(compressed_data, compression_type)
        
        # Parse JSON
        json_str = decompressed_data.decode('utf-8')
        data = json.loads(json_str)
        
        decompression_time = time.time() - start_time
        
        logger.info(f"✅ Decompression completed in {decompression_time:.2f}s")
        
        return data
    
    async def _compress_data(self, data: bytes, compression_type: str) -> bytes:
        """Compress data using specified algorithm."""
        def _compress_sync():
            if compression_type == 'gzip':
                return gzip.compress(data, compresslevel=self.compression_level)
            elif compression_type == 'lzma':
                return lzma.compress(data, preset=self.compression_level)
            elif compression_type == 'zlib':
                return zlib.compress(data, level=self.compression_level)
            else:
                raise ValueError(f"Unsupported compression type: {compression_type}")
        
        # Run compression in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, _compress_sync)
    
    async def _decompress_data(self, data: bytes, compression_type: str) -> bytes:
        """Decompress data using specified algorithm."""
        def _decompress_sync():
            if compression_type == 'gzip':
                return gzip.decompress(data)
            elif compression_type == 'lzma':
                return lzma.decompress(data)
            elif compression_type == 'zlib':
                return zlib.decompress(data)
            else:
                raise ValueError(f"Unsupported compression type: {compression_type}")
        
        # Run decompression in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, _decompress_sync)
    
    async def archive_old_data(self, data_directory: Path, 
                             archive_directory: Path,
                             days_old: int = 7) -> Dict[str, Any]:
        """Archive old data files to save space."""
        logger.info(f"📦 Archiving files older than {days_old} days")
        
        current_time = time.time()
        cutoff_time = current_time - (days_old * 24 * 3600)
        
        archived_files = 0
        total_space_saved = 0
        
        # Ensure archive directory exists
        archive_directory.mkdir(parents=True, exist_ok=True)
        
        # Find old files
        for file_path in data_directory.glob('*.json'):
            if file_path.stat().st_mtime < cutoff_time:
                try:
                    # Compress and move to archive
                    archive_path = archive_directory / f"{file_path.stem}.json.gz"
                    
                    # Read original file
                    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                        data = await f.read()
                    
                    original_size = len(data.encode('utf-8'))
                    
                    # Compress and save to archive
                    compressed_data = await self._compress_data(data.encode('utf-8'), 'gzip')
                    async with aiofiles.open(archive_path, 'wb') as f:
                        await f.write(compressed_data)
                    
                    # Remove original file
                    file_path.unlink()
                    
                    space_saved = original_size - len(compressed_data)
                    total_space_saved += space_saved
                    archived_files += 1
                    
                    logger.debug(f"Archived {file_path.name} -> {archive_path.name} "
                               f"(saved {space_saved / 1024:.1f} KB)")
                    
                except Exception as e:
                    logger.warning(f"Failed to archive {file_path}: {e}")
        
        logger.info(f"✅ Archiving completed:")
        logger.info(f"   • Files archived: {archived_files}")
        logger.info(f"   • Space saved: {total_space_saved / 1024 / 1024:.1f} MB")
        
        return {
            'archived_files': archived_files,
            'space_saved_bytes': total_space_saved,
            'archive_directory': str(archive_directory)
        }
    
    def get_compression_statistics(self) -> Dict[str, Any]:
        """Get compression statistics."""
        total_ratio = (self.compression_stats['original_size'] / 
                      self.compression_stats['compressed_size'] 
                      if self.compression_stats['compressed_size'] > 0 else 1.0)
        
        return {
            'files_compressed': self.compression_stats['files_compressed'],
            'total_original_size_mb': self.compression_stats['original_size'] / 1024 / 1024,
            'total_compressed_size_mb': self.compression_stats['compressed_size'] / 1024 / 1024,
            'total_compression_ratio': total_ratio,
            'total_compression_time': self.compression_stats['compression_time'],
            'space_saved_mb': (self.compression_stats['original_size'] - 
                              self.compression_stats['compressed_size']) / 1024 / 1024
        }

class PerformanceMonitor:
    """Monitors performance metrics and provides scaling recommendations."""
    
    def __init__(self):
        self.metrics_history = deque(maxlen=1000)  # Keep last 1000 metrics
        self.performance_thresholds = {
            'cpu_high': 80.0,
            'memory_high': 85.0,
            'error_rate_high': 5.0,
            'processing_rate_low': 1.0
        }
        
    async def record_performance_metrics(self, metrics: PerformanceMetrics):
        """Record performance metrics for analysis."""
        self.metrics_history.append(metrics)
        
        # Log significant performance events
        if metrics.cpu_usage_percent > self.performance_thresholds['cpu_high']:
            logger.warning(f"⚠️ High CPU usage detected: {metrics.cpu_usage_percent:.1f}%")
        
        if metrics.memory_usage_mb > self.performance_thresholds['memory_high']:
            logger.warning(f"⚠️ High memory usage detected: {metrics.memory_usage_mb:.1f}MB")
        
        if metrics.error_rate > self.performance_thresholds['error_rate_high']:
            logger.warning(f"⚠️ High error rate detected: {metrics.error_rate:.1f}%")
    
    async def generate_scaling_recommendations(self) -> List[ScalingRecommendation]:
        """Generate scaling recommendations based on performance history."""
        if not self.metrics_history:
            return []
        
        recommendations = []
        recent_metrics = list(self.metrics_history)[-10:]  # Last 10 metrics
        
        # Analyze CPU bottlenecks
        avg_cpu = sum(m.cpu_usage_percent for m in recent_metrics) / len(recent_metrics)
        if avg_cpu > 85:
            recommendations.append(ScalingRecommendation(
                current_performance=recent_metrics[-1],
                bottleneck_type='cpu',
                severity='high',
                recommendation='Consider upgrading to a higher CPU instance or reducing concurrency',
                estimated_improvement=30.0,
                cost_impact='medium'
            ))
        
        # Analyze memory bottlenecks
        avg_memory = sum(m.memory_usage_mb for m in recent_metrics) / len(recent_metrics)
        if avg_memory > 3000:  # 3GB threshold
            recommendations.append(ScalingRecommendation(
                current_performance=recent_metrics[-1],
                bottleneck_type='memory',
                severity='high',
                recommendation='Consider upgrading to a higher memory instance or enabling streaming',
                estimated_improvement=40.0,
                cost_impact='medium'
            ))
        
        # Analyze processing rate
        avg_rate = sum(m.processing_rate for m in recent_metrics) / len(recent_metrics)
        if avg_rate < 2.0:  # Less than 2 models per second
            recommendations.append(ScalingRecommendation(
                current_performance=recent_metrics[-1],
                bottleneck_type='api_rate',
                severity='medium',
                recommendation='Consider optimizing API calls or increasing rate limits',
                estimated_improvement=50.0,
                cost_impact='low'
            ))
        
        # Analyze error rates
        avg_error_rate = sum(m.error_rate for m in recent_metrics) / len(recent_metrics)
        if avg_error_rate > 10:
            recommendations.append(ScalingRecommendation(
                current_performance=recent_metrics[-1],
                bottleneck_type='network',
                severity='high',
                recommendation='Network issues detected. Consider improving network connectivity',
                estimated_improvement=25.0,
                cost_impact='high'
            ))
        
        return recommendations
    
    async def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        if not self.metrics_history:
            return {'error': 'No performance data available'}
        
        recent_metrics = list(self.metrics_history)[-100:]  # Last 100 metrics
        
        # Calculate statistics
        cpu_values = [m.cpu_usage_percent for m in recent_metrics]
        memory_values = [m.memory_usage_mb for m in recent_metrics]
        rate_values = [m.processing_rate for m in recent_metrics]
        error_values = [m.error_rate for m in recent_metrics]
        
        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'metrics_count': len(recent_metrics),
            'cpu_stats': {
                'average': sum(cpu_values) / len(cpu_values),
                'max': max(cpu_values),
                'min': min(cpu_values)
            },
            'memory_stats': {
                'average_mb': sum(memory_values) / len(memory_values),
                'max_mb': max(memory_values),
                'min_mb': min(memory_values)
            },
            'processing_rate_stats': {
                'average': sum(rate_values) / len(rate_values),
                'max': max(rate_values),
                'min': min(rate_values)
            },
            'error_rate_stats': {
                'average': sum(error_values) / len(error_values),
                'max': max(error_values),
                'min': min(error_values)
            },
            'recommendations': await self.generate_scaling_recommendations()
        }
        
        return report
    
    async def save_performance_report(self, output_path: Path):
        """Save performance report to file."""
        report = await self.generate_performance_report()
        
        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(report, indent=2, ensure_ascii=False))
        
        logger.info(f"📊 Performance report saved to {output_path}")

class ScalabilityOptimizer:
    """Main orchestrator for scalability and performance optimizations."""
    
    def __init__(self):
        self.resource_monitor = SystemResourceMonitor()
        self.parameter_adjuster = DynamicParameterAdjuster(self.resource_monitor)
        self.streaming_processor = StreamingProcessor()
        self.compression_manager = DataCompressionManager()
        self.performance_monitor = PerformanceMonitor()
        
    async def initialize(self):
        """Initialize the scalability optimizer."""
        logger.info("🚀 Initializing scalability optimizer")
        await self.resource_monitor.start_monitoring()
        
    async def shutdown(self):
        """Shutdown the scalability optimizer."""
        logger.info("⏹️ Shutting down scalability optimizer")
        await self.resource_monitor.stop_monitoring()
        
    async def optimize_for_dataset(self, model_count: int, 
                                 estimated_model_size_mb: float = 10.0) -> ProcessingParameters:
        """Optimize processing parameters for a specific dataset."""
        logger.info(f"🎯 Optimizing for dataset: {model_count} models")
        
        # Calculate optimal parameters
        params = await self.parameter_adjuster.calculate_optimal_parameters(
            model_count, estimated_model_size_mb
        )
        
        # Update streaming processor configuration
        self.streaming_processor.chunk_size = params.chunk_size
        self.streaming_processor.memory_threshold_mb = params.memory_threshold_mb
        
        # Update compression manager configuration
        self.compression_manager.compression_level = params.compression_level
        
        return params
    
    async def process_with_optimization(self, data_source: AsyncGenerator[Any, None],
                                      process_func: callable,
                                      output_handler: callable,
                                      use_streaming: bool = True) -> Dict[str, Any]:
        """Process data with full optimization pipeline."""
        start_time = time.time()
        
        if use_streaming:
            logger.info("🌊 Using streaming processing for optimization")
            result = await self.streaming_processor.process_stream(
                data_source, process_func, output_handler
            )
        else:
            logger.info("⚡ Using standard processing")
            # Fallback to standard processing
            result = {'total_processed': 0, 'total_errors': 0, 'processing_time': 0}
        
        # Record performance metrics
        elapsed_time = time.time() - start_time
        resources = await self.resource_monitor.get_current_resources()
        
        metrics = PerformanceMetrics(
            timestamp=datetime.now(timezone.utc),
            models_processed=result.get('total_processed', 0),
            processing_rate=result.get('processing_rate', 0),
            memory_usage_mb=psutil.virtual_memory().used / 1024 / 1024,
            cpu_usage_percent=resources.cpu_percent,
            network_throughput_mbps=resources.network_io_mbps,
            error_rate=(result.get('total_errors', 0) / max(result.get('total_processed', 1), 1)) * 100,
            compression_ratio=1.0,  # Will be updated if compression is used
            streaming_efficiency=result.get('processing_rate', 0) / max(resources.cpu_percent / 100, 0.1)
        )
        
        await self.performance_monitor.record_performance_metrics(metrics)
        
        return result
    
    async def generate_optimization_report(self, output_path: Path):
        """Generate comprehensive optimization report."""
        logger.info("📊 Generating optimization report")
        
        # Get current system state
        resources = await self.resource_monitor.get_current_resources()
        trends = self.resource_monitor.get_resource_trends()
        
        # Get performance report
        performance_report = await self.performance_monitor.generate_performance_report()
        
        # Get compression statistics
        compression_stats = self.compression_manager.get_compression_statistics()
        
        # Generate scaling recommendations
        recommendations = await self.performance_monitor.generate_scaling_recommendations()
        
        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'system_resources': asdict(resources),
            'resource_trends': trends,
            'performance_metrics': performance_report,
            'compression_statistics': compression_stats,
            'scaling_recommendations': [asdict(rec) for rec in recommendations],
            'optimization_summary': {
                'streaming_enabled': True,
                'compression_enabled': True,
                'adaptive_parameters': True,
                'performance_monitoring': True
            }
        }
        
        # Save report
        async with aiofiles.open(output_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(report, indent=2, ensure_ascii=False))
        
        logger.info(f"✅ Optimization report saved to {output_path}")
        
        # Log key insights
        if recommendations:
            logger.info("🔍 Key optimization recommendations:")
            for rec in recommendations[:3]:  # Top 3 recommendations
                logger.info(f"   • {rec.bottleneck_type.upper()}: {rec.recommendation}")
        
        return report

# Utility functions for integration
async def create_data_stream(data_list: List[Any]) -> AsyncGenerator[Any, None]:
    """Convert a list to an async generator for streaming processing."""
    for item in data_list:
        yield item
        await asyncio.sleep(0)  # Allow other tasks to run

async def batch_output_handler(results: List[Any], output_file: Path):
    """Handle batch output for streaming processing."""
    # This would be customized based on the specific output format needed
    async with aiofiles.open(output_file, 'a', encoding='utf-8') as f:
        for result in results:
            await f.write(json.dumps(result) + '\n')