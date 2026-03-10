"""
Kafka consumer for inference events.

This module provides components for consuming inference events from Kafka,
processing them, and managing batches for Parquet writing.
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Callable
from enum import Enum

from src.config import Settings
from src.ingest.schema_validator import validate_event

logger = logging.getLogger("kafka_consumer")


class ConsumerState(str, Enum):
    """Consumer state enumeration."""
    IDLE = "idle"
    POLLING = "polling"
    PROCESSING = "processing"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class ProcessedEvent:
    """Processed event ready for batch writing."""
    raw_event: Dict[str, Any]
    validated_event: Dict[str, Any]
    processing_timestamp: float
    validation_errors: List[str]
    partition: Optional[int] = None
    offset: Optional[int] = None


class EventProcessor:
    """Processes raw Kafka messages into validated events."""

    def __init__(self, config: Settings):
        """Initialize event processor.

        Args:
            config: Application configuration
        """
        self.config = config
        self.stats = {
            "processed": 0,
            "valid": 0,
            "invalid": 0,
            "validation_errors": 0,
        }

    def process(self, message: bytes, partition: Optional[int] = None,
                offset: Optional[int] = None) -> Optional[ProcessedEvent]:
        """Process a single Kafka message.

        Args:
            message: Raw Kafka message bytes
            partition: Kafka partition (optional)
            offset: Kafka offset (optional)

        Returns:
            ProcessedEvent if successful, None if processing failed
        """
        self.stats["processed"] += 1
        processing_timestamp = time.time()

        try:
            raw_event = json.loads(message.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error("Failed to decode message: %s", e)
            self.stats["invalid"] += 1
            return None

        # Validate against schema
        is_valid, errors = validate_event(raw_event, return_errors=True)
        if not is_valid:
            logger.warning(
                "Event validation failed: %s. Errors: %s",
                raw_event.get("request_id", "unknown"),
                errors
            )
            self.stats["validation_errors"] += 1
            # We still create a processed event but mark it as invalid
            # This allows for dead-letter queue or error handling
            return ProcessedEvent(
                raw_event=raw_event,
                validated_event={},
                processing_timestamp=processing_timestamp,
                validation_errors=errors,
                partition=partition,
                offset=offset
            )

        # Enrich event with metadata
        enriched_event = self._enrich_event(raw_event)

        self.stats["valid"] += 1
        return ProcessedEvent(
            raw_event=raw_event,
            validated_event=enriched_event,
            processing_timestamp=processing_timestamp,
            validation_errors=[],
            partition=partition,
            offset=offset
        )

    def _enrich_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich event with additional metadata.

        Args:
            event: Original event dictionary

        Returns:
            Enriched event dictionary
        """
        enriched = event.copy()
        # Add processing metadata
        enriched["_processing_timestamp"] = time.time()
        enriched["_processing_date"] = datetime.utcnow().isoformat() + "Z"
        # Add source system identifier
        enriched["_source_system"] = "kafka_to_parquet"
        # Add version
        enriched["_schema_version"] = "1.0"
        
        # Extract date fields from event timestamp for partitioning
        timestamp = event.get("timestamp")
        if timestamp is not None:
            try:
                # timestamp is Unix seconds (float)
                dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                enriched["year"] = dt.year
                enriched["month"] = dt.month
                enriched["day"] = dt.day
            except (ValueError, TypeError, OSError) as e:
                logger.warning("Failed to extract date from timestamp %s: %s", timestamp, e)
                # Fallback to current date
                dt = datetime.utcnow()
                enriched["year"] = dt.year
                enriched["month"] = dt.month
                enriched["day"] = dt.day
        else:
            # No timestamp, use current date
            dt = datetime.utcnow()
            enriched["year"] = dt.year
            enriched["month"] = dt.month
            enriched["day"] = dt.day
            logger.warning("Event missing timestamp, using current date for partitioning")
        
        return enriched

    def get_stats(self) -> Dict[str, int]:
        """Get processing statistics."""
        return self.stats.copy()


class BatchManager:
    """Manages batches of processed events for Parquet writing."""

    def __init__(self, config: Settings):
        """Initialize batch manager.

        Args:
            config: Application configuration
        """
        self.config = config
        self.batch: List[ProcessedEvent] = []
        self.batch_size = config.parquet_batch_size
        self.max_batch_age = config.parquet_flush_interval_seconds
        self.batch_created_time = time.time()
        self.stats = {
            "batches_created": 0,
            "events_batched": 0,
            "batches_flushed": 0,
            "events_flushed": 0,
        }

    def add_event(self, event: ProcessedEvent) -> bool:
        """Add event to current batch.

        Args:
            event: Processed event to add

        Returns:
            True if batch is ready for flush (size or age threshold reached),
            False otherwise
        """
        self.batch.append(event)
        self.stats["events_batched"] += 1

        # Check if batch is ready for flush
        size_ready = len(self.batch) >= self.batch_size
        age_ready = (time.time() - self.batch_created_time) >= self.max_batch_age

        return size_ready or age_ready

    def get_batch(self) -> List[ProcessedEvent]:
        """Get current batch of events."""
        return self.batch.copy()

    def flush(self) -> List[ProcessedEvent]:
        """Flush current batch and return it.

        Returns:
            List of events that were in the batch
        """
        if not self.batch:
            return []

        flushed = self.batch.copy()
        self.stats["batches_flushed"] += 1
        self.stats["events_flushed"] += len(flushed)

        # Reset batch
        self.batch = []
        self.batch_created_time = time.time()
        self.stats["batches_created"] += 1

        logger.info(
            "Batch flushed: %d events, total batches: %d",
            len(flushed),
            self.stats["batches_flushed"]
        )
        return flushed

    def should_flush(self) -> bool:
        """Check if current batch should be flushed.

        Returns:
            True if batch should be flushed based on size or age
        """
        if not self.batch:
            return False

        size_ready = len(self.batch) >= self.batch_size
        age_ready = (time.time() - self.batch_created_time) >= self.max_batch_age

        return size_ready or age_ready

    def get_stats(self) -> Dict[str, int]:
        """Get batch statistics."""
        return self.stats.copy()


class KafkaEventConsumer:
    """Main Kafka consumer for inference events."""

    def __init__(self, config: Settings):
        """Initialize Kafka consumer.

        Args:
            config: Application configuration
        """
        self.config = config
        self.state = ConsumerState.IDLE
        self.consumer = None
        self.processor = EventProcessor(config)
        self.batch_manager = BatchManager(config)
        self.callbacks = {
            "on_batch_ready": [],
            "on_error": [],
            "on_state_change": [],
        }
        self.stats = {
            "messages_received": 0,
            "messages_processed": 0,
            "messages_failed": 0,
            "poll_cycles": 0,
            "last_poll_time": 0,
        }

    def _initialize_consumer(self):
        """Initialize Kafka consumer instance."""
        try:
            from kafka import KafkaConsumer
            from kafka.errors import KafkaError
        except ImportError:
            raise ImportError(
                "kafka-python is required for Kafka consumer. "
                "Install it with: pip install kafka-python"
            )

        try:
            self.consumer = KafkaConsumer(
                self.config.kafka_topic,
                bootstrap_servers=self.config.kafka_bootstrap_servers.split(","),
                group_id=self.config.kafka_consumer_group_id,
                auto_offset_reset=self.config.kafka_consumer_auto_offset_reset,
                enable_auto_commit=self.config.kafka_consumer_enable_auto_commit,
                auto_commit_interval_ms=self.config.kafka_consumer_auto_commit_interval_ms,
                max_poll_records=self.config.kafka_consumer_max_poll_records,
                max_poll_interval_ms=self.config.kafka_consumer_max_poll_interval_ms,
                session_timeout_ms=self.config.kafka_consumer_session_timeout_ms,
                heartbeat_interval_ms=self.config.kafka_consumer_heartbeat_interval_ms,
                value_deserializer=lambda v: v,  # Keep raw bytes
                consumer_timeout_ms=self.config.kafka_consumer_poll_timeout_ms,
            )
            logger.info(
                "Kafka consumer initialized: topic=%s, group_id=%s",
                self.config.kafka_topic,
                self.config.kafka_consumer_group_id
            )
        except Exception as e:
            logger.error("Failed to initialize Kafka consumer: %s", e)
            raise

    def add_callback(self, event: str, callback: Callable):
        """Add callback for specific events.

        Args:
            event: Event type ('on_batch_ready', 'on_error', 'on_state_change')
            callback: Callback function
        """
        if event in self.callbacks:
            self.callbacks[event].append(callback)
        else:
            logger.warning("Unknown event type: %s", event)

    def _change_state(self, new_state: ConsumerState):
        """Change consumer state and notify callbacks.

        Args:
            new_state: New state
        """
        old_state = self.state
        self.state = new_state
        logger.debug("Consumer state changed: %s -> %s", old_state, new_state)

        for callback in self.callbacks["on_state_change"]:
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.error("Error in state change callback: %s", e)

    def start(self):
        """Start consuming messages."""
        if self.state != ConsumerState.IDLE:
            logger.warning("Consumer already started, state: %s", self.state)
            return

        self._change_state(ConsumerState.POLLING)

        if not self.consumer:
            self._initialize_consumer()

        logger.info("Starting Kafka consumer")

        try:
            while self.state == ConsumerState.POLLING:
                self._poll_cycle()
        except KeyboardInterrupt:
            logger.info("Consumer interrupted by user")
            self._change_state(ConsumerState.STOPPING)
        except Exception as e:
            logger.error("Consumer error: %s", e)
            self._change_state(ConsumerState.ERROR)
            raise
        finally:
            self.stop()

    def _poll_cycle(self):
        """Single poll cycle: poll, process, handle batch."""
        self.stats["poll_cycles"] += 1
        self.stats["last_poll_time"] = time.time()

        try:
            # Poll for messages
            poll_timeout = self.config.kafka_consumer_poll_timeout_ms
            raw_messages = self.consumer.poll(
                timeout_ms=poll_timeout,
                max_records=self.config.kafka_consumer_max_poll_records
            )
        except Exception as e:
            logger.error("Poll error: %s", e)
            for callback in self.callbacks["on_error"]:
                try:
                    callback("poll_error", e)
                except Exception as cb_err:
                    logger.error("Error in error callback: %s", cb_err)
            return

        if not raw_messages:
            # No messages, check if we should flush based on age
            if self.batch_manager.should_flush():
                self._flush_batch()
            return

        # Process messages
        self._change_state(ConsumerState.PROCESSING)
        processed_count = 0

        for tp, messages in raw_messages.items():
            for message in messages:
                self.stats["messages_received"] += 1
                processed = self.processor.process(
                    message.value,
                    partition=message.partition,
                    offset=message.offset
                )

                if processed:
                    self.stats["messages_processed"] += 1
                    batch_ready = self.batch_manager.add_event(processed)
                    processed_count += 1

                    if batch_ready:
                        self._flush_batch()
                else:
                    self.stats["messages_failed"] += 1

        logger.debug(
            "Poll cycle completed: %d messages processed, batch size: %d",
            processed_count,
            len(self.batch_manager.batch)
        )

        self._change_state(ConsumerState.POLLING)

    def _flush_batch(self):
        """Flush current batch and notify callbacks."""
        batch = self.batch_manager.flush()
        if not batch:
            return

        logger.info("Batch ready for writing: %d events", len(batch))

        for callback in self.callbacks["on_batch_ready"]:
            try:
                callback(batch)
            except Exception as e:
                logger.error("Error in batch ready callback: %s", e)

    def stop(self):
        """Stop consumer gracefully."""
        if self.state == ConsumerState.STOPPING:
            return

        self._change_state(ConsumerState.STOPPING)

        # Flush any remaining events
        if self.batch_manager.batch:
            logger.info("Flushing final batch before shutdown")
            self._flush_batch()

        # Close Kafka consumer
        if self.consumer:
            try:
                self.consumer.close()
                logger.info("Kafka consumer closed")
            except Exception as e:
                logger.error("Error closing consumer: %s", e)

        self._change_state(ConsumerState.IDLE)
        logger.info("Consumer stopped")

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive consumer statistics."""
        return {
            "consumer": self.stats.copy(),
            "processor": self.processor.get_stats(),
            "batch_manager": self.batch_manager.get_stats(),
            "state": self.state.value,
            "batch_size": len(self.batch_manager.batch),
            "batch_age": time.time() - self.batch_manager.batch_created_time,
        }