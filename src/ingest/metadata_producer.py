"""Metadata producer for Kafka/Kinesis ingestion of inference events."""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger("metadata_producer")


class StreamingBackend(str, Enum):
    """Supported streaming backends."""

    KAFKA = "kafka"
    KINESIS = "kinesis"
    NONE = "none"


@dataclass
class MetadataEvent:
    """Metadata event structure for inference results."""

    timestamp: float
    topk: list[dict[str, Any]]
    source: str
    latency_ms: float
    model_name: Optional[str] = None
    device: Optional[str] = None
    has_person: Optional[bool] = None
    request_id: Optional[str] = None
    frame_index: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp,
            "topk": self.topk,
            "source": self.source,
            "latency_ms": round(self.latency_ms, 2),
            "model_name": self.model_name,
            "device": self.device,
            "has_person": self.has_person,
            "request_id": self.request_id,
            "frame_index": self.frame_index,
        }


class MetadataProducer(ABC):
    """Abstract base class for metadata producers."""

    @abstractmethod
    def send(self, event: MetadataEvent) -> bool:
        """Send a metadata event. Returns True if successful, False otherwise."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the producer and release resources."""
        pass


class KafkaProducer(MetadataProducer):
    """Kafka producer for metadata events."""

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        max_retries: int = 3,
        retry_backoff_ms: int = 100,
    ):
        """Initialize Kafka producer.

        Args:
            bootstrap_servers: Kafka broker addresses (comma-separated)
            topic: Kafka topic name
            max_retries: Maximum number of retry attempts
            retry_backoff_ms: Initial backoff delay in milliseconds
        """
        try:
            from kafka import KafkaProducer as _KafkaProducer
            from kafka.errors import KafkaError
        except ImportError:
            raise ImportError(
                "kafka-python is required for Kafka support. "
                "Install it with: pip install kafka-python"
            )

        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.max_retries = max_retries
        self.retry_backoff_ms = retry_backoff_ms
        self._kafka_error = KafkaError

        try:
            self.producer = _KafkaProducer(
                bootstrap_servers=bootstrap_servers.split(","),
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                retries=max_retries,
            )
            logger.info(
                "Kafka producer initialized: bootstrap_servers=%s, topic=%s",
                bootstrap_servers,
                topic,
            )
        except Exception as e:
            logger.error("Failed to initialize Kafka producer: %s", e)
            raise

    def send(self, event: MetadataEvent) -> bool:
        """Send event to Kafka with retry logic."""
        event_dict = event.to_dict()
        for attempt in range(self.max_retries + 1):
            try:
                future = self.producer.send(self.topic, event_dict)
                # Wait for the message to be sent (with timeout)
                future.get(timeout=5)
                logger.debug("Sent metadata event to Kafka: topic=%s", self.topic)
                return True
            except self._kafka_error as e:
                if attempt < self.max_retries:
                    backoff_ms = self.retry_backoff_ms * (2 ** attempt)
                    logger.warning(
                        "Kafka send failed (attempt %d/%d), retrying in %d ms: %s",
                        attempt + 1,
                        self.max_retries + 1,
                        backoff_ms,
                        e,
                    )
                    time.sleep(backoff_ms / 1000.0)
                else:
                    logger.error(
                        "Failed to send metadata event to Kafka after %d attempts: %s",
                        self.max_retries + 1,
                        e,
                    )
                    return False
            except Exception as e:
                logger.error("Unexpected error sending to Kafka: %s", e)
                return False
        return False

    def close(self) -> None:
        """Close Kafka producer."""
        try:
            self.producer.close(timeout=5)
            logger.info("Kafka producer closed")
        except Exception as e:
            logger.warning("Error closing Kafka producer: %s", e)


class KinesisProducer(MetadataProducer):
    """Kinesis producer for metadata events."""

    def __init__(
        self,
        stream_name: str,
        region: str = "us-east-1",
        max_retries: int = 3,
        retry_backoff_ms: int = 100,
    ):
        """Initialize Kinesis producer.

        Args:
            stream_name: Kinesis stream name
            region: AWS region
            max_retries: Maximum number of retry attempts
            retry_backoff_ms: Initial backoff delay in milliseconds
        """
        try:
            import boto3
            from botocore.exceptions import ClientError, BotoCoreError
        except ImportError:
            raise ImportError(
                "boto3 is required for Kinesis support. "
                "Install it with: pip install boto3"
            )

        self.stream_name = stream_name
        self.region = region
        self.max_retries = max_retries
        self.retry_backoff_ms = retry_backoff_ms
        self._client_error = ClientError
        self._boto_error = BotoCoreError

        try:
            self.client = boto3.client("kinesis", region_name=region)
            logger.info(
                "Kinesis producer initialized: stream_name=%s, region=%s",
                stream_name,
                region,
            )
        except Exception as e:
            logger.error("Failed to initialize Kinesis producer: %s", e)
            raise

    def send(self, event: MetadataEvent) -> bool:
        """Send event to Kinesis with retry logic."""
        event_dict = event.to_dict()
        data = json.dumps(event_dict).encode("utf-8")

        # Use timestamp as partition key for even distribution
        partition_key = str(int(event.timestamp * 1000))

        for attempt in range(self.max_retries + 1):
            try:
                self.client.put_record(
                    StreamName=self.stream_name,
                    Data=data,
                    PartitionKey=partition_key,
                )
                logger.debug("Sent metadata event to Kinesis: stream=%s", self.stream_name)
                return True
            except (self._client_error, self._boto_error) as e:
                if attempt < self.max_retries:
                    backoff_ms = self.retry_backoff_ms * (2 ** attempt)
                    logger.warning(
                        "Kinesis send failed (attempt %d/%d), retrying in %d ms: %s",
                        attempt + 1,
                        self.max_retries + 1,
                        backoff_ms,
                        e,
                    )
                    time.sleep(backoff_ms / 1000.0)
                else:
                    logger.error(
                        "Failed to send metadata event to Kinesis after %d attempts: %s",
                        self.max_retries + 1,
                        e,
                    )
                    return False
            except Exception as e:
                logger.error("Unexpected error sending to Kinesis: %s", e)
                return False
        return False

    def close(self) -> None:
        """Close Kinesis producer (no-op for boto3 client)."""
        # boto3 clients don't need explicit closing
        logger.debug("Kinesis producer closed")


class NoOpProducer(MetadataProducer):
    """No-op producer for when streaming is disabled."""

    def send(self, event: MetadataEvent) -> bool:
        """No-op send."""
        return True

    def close(self) -> None:
        """No-op close."""
        pass


def create_producer(
    backend: StreamingBackend,
    **kwargs: Any,
) -> MetadataProducer:
    """Factory function to create a metadata producer.

    Args:
        backend: Streaming backend type
        **kwargs: Backend-specific configuration

    Returns:
        MetadataProducer instance

    Examples:
        >>> # Kafka
        >>> producer = create_producer(
        ...     StreamingBackend.KAFKA,
        ...     bootstrap_servers="localhost:9092",
        ...     topic="inference-events"
        ... )
        >>> # Kinesis
        >>> producer = create_producer(
        ...     StreamingBackend.KINESIS,
        ...     stream_name="inference-events",
        ...     region="us-east-1"
        ... )
    """
    if backend == StreamingBackend.KAFKA:
        return KafkaProducer(
            bootstrap_servers=kwargs.get("bootstrap_servers", "localhost:9092"),
            topic=kwargs.get("topic", "inference-events"),
            max_retries=kwargs.get("max_retries", 3),
            retry_backoff_ms=kwargs.get("retry_backoff_ms", 100),
        )
    elif backend == StreamingBackend.KINESIS:
        return KinesisProducer(
            stream_name=kwargs.get("stream_name", "inference-events"),
            region=kwargs.get("region", "us-east-1"),
            max_retries=kwargs.get("max_retries", 3),
            retry_backoff_ms=kwargs.get("retry_backoff_ms", 100),
        )
    else:
        return NoOpProducer()
