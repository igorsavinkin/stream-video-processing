"""
Kafka to Parquet pipeline module.

This module provides components for consuming inference events from Kafka,
processing them, and writing to S3 in Parquet format.
"""

from .kafka_consumer import KafkaEventConsumer, EventProcessor, BatchManager
from .parquet_writer import ParquetSchemaManager, S3ParquetWriter, S3Uploader
from .metrics_integration import KafkaParquetMetrics, init_metrics, get_metrics, record_event_processed, record_batch_written, record_error, record_dead_letter

__all__ = [
    "KafkaEventConsumer",
    "EventProcessor",
    "BatchManager",
    "ParquetSchemaManager",
    "S3ParquetWriter",
    "S3Uploader",
    "KafkaParquetMetrics",
    "init_metrics",
    "get_metrics",
    "record_event_processed",
    "record_batch_written",
    "record_error",
    "record_dead_letter",
]