"""
Metrics integration for Kafka to Parquet pipeline.

This module provides integration with the existing metrics system,
allowing Kafka consumer metrics to be logged in the same JSON format
as other system metrics.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger("kafka_to_parquet.metrics")


class KafkaParquetMetrics:
    """Metrics collector for Kafka to Parquet pipeline."""
    
    def __init__(self, log_every: int = 1000):
        """
        Args:
            log_every: Log metrics every N processed events
        """
        self.log_every = log_every
        self.processed_count = 0
        self.batch_count = 0
        self.error_count = 0
        self.dead_letter_count = 0
        self.s3_upload_count = 0
        self.s3_upload_bytes = 0
        self.last_log_time = datetime.now(timezone.utc)
        
    def record_event_processed(self) -> None:
        """Record that an event was successfully processed."""
        self.processed_count += 1
        if self.processed_count % self.log_every == 0:
            self._log_metrics()
    
    def record_batch_written(self, event_count: int, file_size_bytes: int) -> None:
        """Record that a batch was written to S3."""
        self.batch_count += 1
        self.s3_upload_count += 1
        self.s3_upload_bytes += file_size_bytes
        self._log_metrics()
    
    def record_error(self) -> None:
        """Record that an error occurred."""
        self.error_count += 1
    
    def record_dead_letter(self) -> None:
        """Record that an event was sent to dead letter queue."""
        self.dead_letter_count += 1
    
    def _log_metrics(self) -> None:
        """Log metrics in JSON format compatible with existing system."""
        now = datetime.now(timezone.utc)
        time_since_last = (now - self.last_log_time).total_seconds()
        
        metrics = {
            "type": "kafka_parquet_metrics",
            "timestamp": now.isoformat(),
            "processed_total": self.processed_count,
            "batches_written": self.batch_count,
            "errors_total": self.error_count,
            "dead_letter_total": self.dead_letter_count,
            "s3_uploads": self.s3_upload_count,
            "s3_upload_bytes": self.s3_upload_bytes,
            "events_per_second": round(self.log_every / max(time_since_last, 1e-6), 2),
            "log_every": self.log_every,
        }
        
        logger.info(json.dumps(metrics))
        self.last_log_time = now
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current metrics as dictionary."""
        return {
            "processed_count": self.processed_count,
            "batch_count": self.batch_count,
            "error_count": self.error_count,
            "dead_letter_count": self.dead_letter_count,
            "s3_upload_count": self.s3_upload_count,
            "s3_upload_bytes": self.s3_upload_bytes,
        }


# Global metrics instance
_global_metrics: KafkaParquetMetrics = None


def init_metrics(log_every: int = 1000) -> None:
    """Initialize global metrics instance."""
    global _global_metrics
    _global_metrics = KafkaParquetMetrics(log_every=log_every)


def get_metrics() -> KafkaParquetMetrics:
    """Get global metrics instance."""
    if _global_metrics is None:
        init_metrics()
    return _global_metrics


def record_event_processed() -> None:
    """Record event processed using global metrics."""
    get_metrics().record_event_processed()


def record_batch_written(event_count: int, file_size_bytes: int) -> None:
    """Record batch written using global metrics."""
    get_metrics().record_batch_written(event_count, file_size_bytes)


def record_error() -> None:
    """Record error using global metrics."""
    get_metrics().record_error()


def record_dead_letter() -> None:
    """Record dead letter using global metrics."""
    get_metrics().record_dead_letter()