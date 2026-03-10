"""
Parquet writer module for Kafka to S3 pipeline.

Contains:
- ParquetSchemaManager: Manages Parquet schema definition and validation
- S3Uploader: Handles S3 uploads with retry and multipart support
- S3ParquetWriter: Writes batches of events to Parquet files and uploads to S3
"""

import json
import logging
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast

import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError, BotoCoreError

from src.config import settings

logger = logging.getLogger(__name__)


class ParquetSchemaManager:
    """Manages Parquet schema definition and validation for inference events."""

    def __init__(self) -> None:
        self._schema = self._build_schema()
        self._field_names = [field.name for field in self._schema]

    def _build_schema(self) -> pa.Schema:
        """Build PyArrow schema based on inference event JSON schema."""
        # Define schema based on inference_event.json
        # We'll flatten topk array into separate columns for top-3 predictions
        # This is a design decision: we could store as list of structs, but for
        # analytics, flattening is often more convenient.
        fields = [
            # Required fields
            pa.field("timestamp", pa.float64(), nullable=False),
            pa.field("source", pa.string(), nullable=False),
            pa.field("latency_ms", pa.float64(), nullable=False),
            # Optional fields
            pa.field("model_name", pa.string(), nullable=True),
            pa.field("device", pa.string(), nullable=True),
            pa.field("has_person", pa.bool_(), nullable=True),
            pa.field("request_id", pa.string(), nullable=True),
            pa.field("frame_index", pa.int64(), nullable=True),
            # Top-k predictions flattened
            pa.field("top1_label", pa.string(), nullable=True),
            pa.field("top1_score", pa.float64(), nullable=True),
            pa.field("top2_label", pa.string(), nullable=True),
            pa.field("top2_score", pa.float64(), nullable=True),
            pa.field("top3_label", pa.string(), nullable=True),
            pa.field("top3_score", pa.float64(), nullable=True),
            # Processing metadata (added by consumer)
            pa.field("processing_timestamp", pa.float64(), nullable=False),
            pa.field("kafka_topic", pa.string(), nullable=True),
            pa.field("kafka_partition", pa.int64(), nullable=True),
            pa.field("kafka_offset", pa.int64(), nullable=True),
            pa.field("batch_id", pa.string(), nullable=True),
        ]
        return pa.schema(fields)

    @property
    def schema(self) -> pa.Schema:
        """Get the Parquet schema."""
        return self._schema

    @property
    def field_names(self) -> List[str]:
        """Get list of field names in the schema."""
        return self._field_names

    def validate_event(self, event: Dict[str, Any]) -> bool:
        """Validate event against schema (basic validation)."""
        try:
            # Check required fields
            if "timestamp" not in event or "source" not in event or "latency_ms" not in event:
                return False
            # Check types
            if not isinstance(event["timestamp"], (int, float)):
                return False
            if not isinstance(event["source"], str):
                return False
            if not isinstance(event["latency_ms"], (int, float)):
                return False
            # Check topk structure if present
            if "topk" in event and event["topk"] is not None:
                if not isinstance(event["topk"], list):
                    return False
                # Validate each element
                for item in event["topk"]:
                    if not isinstance(item, dict):
                        return False
                    if "label" not in item or "score" not in item:
                        return False
            return True
        except (KeyError, TypeError):
            return False

    def transform_event(self, event: Dict[str, Any], **metadata: Any) -> Dict[str, Any]:
        """
        Transform raw event into flattened dictionary matching Parquet schema.
        
        Args:
            event: Raw inference event dictionary
            **metadata: Additional metadata (kafka_topic, partition, offset, batch_id, etc.)
        
        Returns:
            Transformed dictionary with all schema fields
        """
        transformed: Dict[str, Any] = {
            "timestamp": float(event.get("timestamp", 0.0)),
            "source": str(event.get("source", "")),
            "latency_ms": float(event.get("latency_ms", 0.0)),
            "model_name": event.get("model_name"),
            "device": event.get("device"),
            "has_person": event.get("has_person"),
            "request_id": event.get("request_id"),
            "frame_index": event.get("frame_index"),
            # Initialize top-k fields
            "top1_label": None,
            "top1_score": None,
            "top2_label": None,
            "top2_score": None,
            "top3_label": None,
            "top3_score": None,
            # Date fields for partitioning (extracted from timestamp)
            "year": int(event.get("year", datetime.utcnow().year)),
            "month": int(event.get("month", datetime.utcnow().month)),
            "day": int(event.get("day", datetime.utcnow().day)),
            # Processing metadata
            "processing_timestamp": time.time(),
            "kafka_topic": metadata.get("kafka_topic"),
            "kafka_partition": metadata.get("kafka_partition"),
            "kafka_offset": metadata.get("kafka_offset"),
            "batch_id": metadata.get("batch_id"),
        }

        # Flatten topk array
        topk = event.get("topk", [])
        if isinstance(topk, list) and len(topk) > 0:
            for i, item in enumerate(topk[:3]):  # Take up to top 3
                if isinstance(item, dict):
                    label = item.get("label")
                    score = item.get("score")
                    if i == 0:
                        transformed["top1_label"] = str(label) if label is not None else None
                        transformed["top1_score"] = float(score) if score is not None else None
                    elif i == 1:
                        transformed["top2_label"] = str(label) if label is not None else None
                        transformed["top2_score"] = float(score) if score is not None else None
                    elif i == 2:
                        transformed["top3_label"] = str(label) if label is not None else None
                        transformed["top3_score"] = float(score) if score is not None else None

        # Convert None values to appropriate nulls (PyArrow will handle)
        return transformed


class S3Uploader:
    """Handles S3 uploads with retry, multipart, and error handling."""

    def __init__(
        self,
        bucket: Optional[str] = None,
        region: Optional[str] = None,
        enable_multipart: bool = True,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """
        Initialize S3 uploader.
        
        Args:
            bucket: S3 bucket name (defaults to settings.parquet_s3_bucket)
            region: AWS region (defaults to settings.parquet_s3_region)
            enable_multipart: Whether to use multipart upload for large files
            max_retries: Maximum number of retry attempts for failed uploads
            retry_delay: Delay between retries in seconds
        """
        self.bucket = bucket or settings.parquet_s3_bucket
        self.region = region or settings.parquet_s3_region
        self.enable_multipart = enable_multipart
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        if self.bucket is None:
            raise ValueError("S3 bucket must be specified via bucket parameter or settings.parquet_s3_bucket")
        
        self._client = None
        self._logger = logging.getLogger(f"{__name__}.S3Uploader")

    @property
    def client(self):
        """Lazy-loaded S3 client."""
        if self._client is None:
            try:
                import boto3
                if self.region:
                    self._client = boto3.client("s3", region_name=self.region)
                else:
                    self._client = boto3.client("s3")
            except ImportError:
                raise ImportError(
                    "boto3 is required for S3 uploads. Install it with: pip install boto3"
                )
        return self._client

    def upload_file(
        self,
        local_path: Union[str, Path],
        s3_key: str,
        content_type: str = "application/parquet",
        metadata: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Upload a file to S3 with retry logic.
        
        Args:
            local_path: Path to local file
            s3_key: S3 object key
            content_type: Content type for the object
            metadata: Optional metadata dict
        
        Returns:
            True if upload succeeded, False otherwise
        """
        local_path = Path(local_path)
        if not local_path.exists():
            self._logger.error("upload_file_failed reason=file_not_found path=%s", local_path)
            return False
        
        file_size = local_path.stat().st_size
        use_multipart = self.enable_multipart and file_size > 10 * 1024 * 1024  # 10 MB threshold
        
        for attempt in range(self.max_retries + 1):
            try:
                if use_multipart:
                    success = self._upload_multipart(local_path, s3_key, content_type, metadata)
                else:
                    success = self._upload_singlepart(local_path, s3_key, content_type, metadata)
                
                if success:
                    self._logger.info(
                        "upload_succeeded key=%s size=%d multipart=%s attempt=%d",
                        s3_key, file_size, use_multipart, attempt + 1
                    )
                    return True
                else:
                    # _upload_* methods should raise exceptions on failure, but handle gracefully
                    self._logger.warning("upload_failed_no_exception key=%s attempt=%d", s3_key, attempt + 1)
                    
            except (ClientError, BotoCoreError, IOError) as exc:
                self._logger.warning(
                    "upload_failed key=%s attempt=%d error=%s",
                    s3_key, attempt + 1, str(exc)
                )
                if attempt == self.max_retries:
                    self._logger.error("upload_failed_max_retries key=%s", s3_key)
                    return False
                time.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff
        
        return False

    def _upload_singlepart(
        self,
        local_path: Path,
        s3_key: str,
        content_type: str,
        metadata: Optional[Dict[str, str]],
    ) -> bool:
        """Upload file using single-part upload."""
        extra_args = {"ContentType": content_type}
        if metadata:
            extra_args["Metadata"] = metadata
        
        self.client.upload_file(
            str(local_path),
            self.bucket,
            s3_key,
            ExtraArgs=extra_args,
        )
        return True

    def _upload_multipart(
        self,
        local_path: Path,
        s3_key: str,
        content_type: str,
        metadata: Optional[Dict[str, str]],
    ) -> bool:
        """Upload file using multipart upload (for large files)."""
        from boto3.s3.transfer import TransferConfig
        
        config = TransferConfig(
            multipart_threshold=10 * 1024 * 1024,  # 10 MB
            max_concurrency=10,
            multipart_chunksize=8 * 1024 * 1024,  # 8 MB
            use_threads=True,
        )
        
        extra_args = {"ContentType": content_type}
        if metadata:
            extra_args["Metadata"] = metadata
        
        self.client.upload_file(
            str(local_path),
            self.bucket,
            s3_key,
            ExtraArgs=extra_args,
            Config=config,
        )
        return True

    def generate_s3_key(
        self,
        prefix: Optional[str] = None,
        partition: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> str:
        """
        Generate S3 key with optional partitioning.
        
        Args:
            prefix: Base prefix (defaults to settings.parquet_s3_prefix)
            partition: Partition path (e.g., 'year=2026/month=03/day=09')
            filename: Filename (defaults to UUID + .parquet)
        
        Returns:
            S3 key string
        """
        if prefix is None:
            prefix = settings.parquet_s3_prefix or "inference-parquet"
        
        if filename is None:
            filename = f"{uuid.uuid4().hex}.parquet"
        
        parts = [prefix]
        if partition:
            parts.append(partition)
        parts.append(filename)
        
        # Remove empty parts and join
        parts = [p for p in parts if p]
        return "/".join(parts)


class S3ParquetWriter:
    """Writes batches of events to Parquet files and uploads to S3."""

    def __init__(
        self,
        schema_manager: Optional[ParquetSchemaManager] = None,
        uploader: Optional[S3Uploader] = None,
        compression: Optional[str] = None,
        max_file_size_mb: Optional[int] = None,
    ) -> None:
        """
        Initialize Parquet writer.
        
        Args:
            schema_manager: ParquetSchemaManager instance (creates default if None)
            uploader: S3Uploader instance (creates default if None)
            compression: Parquet compression algorithm (defaults to settings.parquet_compression)
            max_file_size_mb: Maximum file size in MB before rotation (defaults to settings.parquet_max_file_size_mb)
        """
        self.schema_manager = schema_manager or ParquetSchemaManager()
        self.uploader = uploader or S3Uploader()
        self.compression = compression or settings.parquet_compression
        self.max_file_size_mb = max_file_size_mb or settings.parquet_max_file_size_mb
        
        self._current_batch: List[Dict[str, Any]] = []
        self._current_file_size = 0
        self._temp_dir = Path(tempfile.gettempdir()) / "kafka_parquet"
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        
        self._logger = logging.getLogger(f"{__name__}.S3ParquetWriter")
        self._stats = {
            "events_written": 0,
            "files_uploaded": 0,
            "upload_errors": 0,
            "last_upload_time": None,
        }

    def write_batch(
        self,
        events: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        force_flush: bool = False,
    ) -> bool:
        """
        Write a batch of events to Parquet file(s).
        
        Args:
            events: List of raw inference events
            metadata: Optional metadata to pass to transform_event (e.g., kafka_topic, batch_id)
            force_flush: If True, flush current batch to S3 even if size limit not reached
        
        Returns:
            True if all events were successfully written, False otherwise
        """
        if not events:
            return True
        
        metadata = metadata or {}
        transformed_events = []
        
        # Transform and validate events
        for event in events:
            if not self.schema_manager.validate_event(event):
                self._logger.warning("invalid_event_skipped event=%s", event.get("request_id", "unknown"))
                continue
            
            transformed = self.schema_manager.transform_event(event, **metadata)
            transformed_events.append(transformed)
        
        if not transformed_events:
            self._logger.debug("no_valid_events_in_batch")
            return True
        
        # Add to current batch
        self._current_batch.extend(transformed_events)
        self._stats["events_written"] += len(transformed_events)
        
        # Estimate batch size (rough approximation)
        batch_size_bytes = len(json.dumps(transformed_events).encode("utf-8"))
        self._current_file_size += batch_size_bytes
        
        # Check if we should flush
        should_flush = (
            force_flush or
            len(self._current_batch) >= settings.parquet_batch_size or
            (self.max_file_size_mb > 0 and
             self._current_file_size >= self.max_file_size_mb * 1024 * 1024)
        )
        
        if should_flush:
            return self._flush_to_s3()
        
        return True

    def _flush_to_s3(self) -> bool:
        """Flush current batch to Parquet file and upload to S3."""
        if not self._current_batch:
            return True
        
        try:
            # Create PyArrow table
            table = pa.Table.from_pylist(self._current_batch, schema=self.schema_manager.schema)
            
            # Write to temporary Parquet file
            temp_file = self._temp_dir / f"batch_{uuid.uuid4().hex}.parquet"
            pq.write_table(
                table,
                temp_file,
                compression=self.compression,
                version='2.6',
            )
            
            # Generate S3 key with date partitioning
            now = datetime.utcnow()
            partition = f"year={now.year:04d}/month={now.month:02d}/day={now.day:02d}"
            s3_key = self.uploader.generate_s3_key(partition=partition)
            
            # Upload to S3
            success = self.uploader.upload_file(temp_file, s3_key)
            
            if success:
                self._stats["files_uploaded"] += 1
                self._stats["last_upload_time"] = time.time()
                self._logger.info(
                    "batch_uploaded events=%d size_kb=%d key=%s",
                    len(self._current_batch),
                    temp_file.stat().st_size // 1024,
                    s3_key,
                )
            else:
                self._stats["upload_errors"] += 1
                self._logger.error("batch_upload_failed events=%d", len(self._current_batch))
            
            # Clean up temp file
            try:
                temp_file.unlink()
            except OSError:
                pass
            
            # Reset batch
            self._current_batch.clear()
            self._current_file_size = 0
            
            return success
            
        except Exception as exc:
            self._logger.exception("flush_to_s3_failed error=%s", str(exc))
            self._stats["upload_errors"] += 1
            return False

    def flush(self) -> bool:
        """Force flush any remaining events in the buffer."""
        return self._flush_to_s3()

    def get_stats(self) -> Dict[str, Any]:
        """Get writer statistics."""
        return {
            **self._stats,
            "current_batch_size": len(self._current_batch),
            "current_file_size_mb": self._current_file_size / (1024 * 1024),
        }

    def close(self) -> None:
        """Close writer and flush any remaining data."""
        if self._current_batch:
            self._logger.info("closing_writer_flushing_remaining events=%d", len(self._current_batch))
            self.flush()