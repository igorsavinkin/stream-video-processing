"""Unit tests for Kafka to Parquet pipeline components."""

import json
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import pyarrow as pa
import pyarrow.parquet as pq

from src.config import Settings
from src.kafka_to_parquet.kafka_consumer import (
    KafkaEventConsumer,
    EventProcessor,
    BatchManager,
    ConsumerState,
)
from src.kafka_to_parquet.parquet_writer import (
    ParquetSchemaManager,
    S3Uploader,
    S3ParquetWriter,
)
from src.kafka_to_parquet.metrics_integration import KafkaParquetMetrics


class TestKafkaEventConsumer:
    """Tests for KafkaEventConsumer class."""

    def test_initialization(self):
        """Test consumer initialization with configuration."""
        mock_config = MagicMock()
        mock_config.kafka_bootstrap_servers = "localhost:9092"
        mock_config.kafka_topic = "test-topic"
        mock_config.kafka_consumer_group_id = "test-group"
        mock_config.kafka_consumer_max_poll_records = 100
        mock_config.kafka_consumer_auto_offset_reset = "earliest"
        mock_config.kafka_consumer_enable_auto_commit = False
        mock_config.kafka_consumer_session_timeout_ms = 45000
        mock_config.kafka_consumer_heartbeat_interval_ms = 3000
        mock_config.kafka_consumer_max_poll_interval_ms = 300000

        with patch("src.kafka_to_parquet.kafka_consumer.KafkaConsumer") as mock_kafka:
            consumer = KafkaEventConsumer(mock_config)
            assert consumer.state == ConsumerState.IDLE
            # topic and max_poll_records are accessed via config, not stored as attributes
            assert consumer.config == mock_config
            mock_kafka.assert_called_once_with(
                bootstrap_servers="localhost:9092",
                group_id="test-group",
                auto_offset_reset="earliest",
                enable_auto_commit=False,
                session_timeout_ms=45000,
                heartbeat_interval_ms=3000,
                max_poll_interval_ms=300000,
                max_poll_records=100,
                value_deserializer=lambda v: v,  # Real implementation uses lambda
            )

    def test_start_stop(self):
        """Test starting and stopping the consumer."""
        mock_config = MagicMock()
        mock_config.kafka_bootstrap_servers = "localhost:9092"
        mock_config.kafka_topic = "test-topic"

        mock_kafka_consumer = MagicMock()
        mock_kafka_consumer.subscribe = MagicMock()

        with patch("kafka.KafkaConsumer",
                   return_value=mock_kafka_consumer):
            consumer = KafkaEventConsumer(mock_config)
            
            # Start consumer
            consumer.start()
            assert consumer.state == ConsumerState.POLLING
            mock_kafka_consumer.subscribe.assert_called_once_with(["test-topic"])
            
            # Stop consumer
            consumer.stop()
            assert consumer.state == ConsumerState.STOPPING
            mock_kafka_consumer.close.assert_called_once()

    def test_poll_no_messages(self):
        """Test poll cycle with no messages."""
        mock_config = MagicMock()
        mock_config.kafka_bootstrap_servers = "localhost:9092"
        mock_config.kafka_topic = "test-topic"

        mock_kafka_consumer = MagicMock()
        mock_kafka_consumer.poll = MagicMock(return_value={})

        with patch("kafka.KafkaConsumer",
                   return_value=mock_kafka_consumer):
            consumer = KafkaEventConsumer(mock_config)
            consumer._consumer = mock_kafka_consumer
            consumer.state = ConsumerState.POLLING
            
            processed = consumer._poll_cycle()
            assert processed == 0
            mock_kafka_consumer.poll.assert_called_once_with(timeout_ms=1000)


class TestEventProcessor:
    """Tests for EventProcessor class."""

    def test_process_valid_event(self):
        """Test processing a valid inference event."""
        config = MagicMock(spec=Settings)
        processor = EventProcessor(config)
        
        # Mock validate_event to return valid
        with patch('src.ingest.schema_validator.validate_event') as mock_validate:
            mock_validate.return_value = (True, [])
            
            message = json.dumps({
                "event_id": "test-123",
                "timestamp": "2025-01-01T12:00:00Z",
                "model_name": "resnet50",
                "predictions": [
                    {"class_id": 1, "class_name": "cat", "confidence": 0.9},
                    {"class_id": 2, "class_name": "dog", "confidence": 0.1},
                ],
                "metadata": {
                    "frame_id": 100,
                    "camera_id": "cam1",
                    "processing_time_ms": 50.5,
                }
            }).encode('utf-8')
            
            result = processor.process(message, partition=0, offset=100)
            assert result is not None
            assert result.raw_event["event_id"] == "test-123"
            assert result.validated_event["event_id"] == "test-123"
            assert result.validation_errors == []
            assert result.partition == 0
            assert result.offset == 100
            assert result.processing_timestamp > 0
            mock_validate.assert_called_once()

    def test_process_invalid_json(self):
        """Test processing a message with invalid JSON."""
        config = MagicMock(spec=Settings)
        processor = EventProcessor(config)
        
        result = processor.process(b"invalid json", partition=0, offset=100)
        assert result is None
        assert processor.stats["invalid"] == 1

    def test_process_validation_failed(self):
        """Test processing an event that fails schema validation."""
        config = MagicMock(spec=Settings)
        processor = EventProcessor(config)
        
        with patch('src.ingest.schema_validator.validate_event') as mock_validate:
            mock_validate.return_value = (False, ["Missing required field: event_id"])
            
            message = json.dumps({"timestamp": "2025-01-01T12:00:00Z"}).encode('utf-8')
            result = processor.process(message, partition=0, offset=100)
            assert result is not None
            assert result.raw_event == {"timestamp": "2025-01-01T12:00:00Z"}
            assert result.validated_event == {}
            assert result.validation_errors == ["Missing required field: event_id"]
            assert processor.stats["validation_errors"] == 1

    def test_stats_tracking(self):
        """Test that statistics are properly tracked."""
        config = MagicMock(spec=Settings)
        processor = EventProcessor(config)
        
        with patch('src.ingest.schema_validator.validate_event') as mock_validate:
            mock_validate.return_value = (True, [])
            
            # Process valid event
            message = json.dumps({
                "event_id": "test",
                "timestamp": "2025-01-01T12:00:00Z",
                "model_name": "test",
                "predictions": []
            }).encode('utf-8')
            
            result = processor.process(message)
            assert result is not None
            assert processor.stats["processed"] == 1
            assert processor.stats["valid"] == 1
            assert processor.stats["invalid"] == 0
            assert processor.stats["validation_errors"] == 0
            
            # Process invalid JSON
            processor.process(b"invalid")
            assert processor.stats["processed"] == 2
            assert processor.stats["invalid"] == 1
            
            # Process validation error
            mock_validate.return_value = (False, ["error"])
            processor.process(message)
            assert processor.stats["processed"] == 3
            assert processor.stats["validation_errors"] == 1


class TestBatchManager:
    """Tests for BatchManager class."""

    def test_initialization(self):
        """Test BatchManager initialization."""
        config = MagicMock(spec=Settings)
        config.parquet_batch_size = 100
        config.parquet_flush_interval_seconds = 30
        
        manager = BatchManager(config)
        
        assert manager.config == config
        assert manager.batch_size == 100
        assert manager.max_batch_age == 30
        assert manager.batch == []
        assert manager.batch_created_time > 0
        assert manager.stats["events_added"] == 0
        assert manager.stats["batches_flushed"] == 0

    def test_add_event(self):
        """Test adding events to batch."""
        config = MagicMock(spec=Settings)
        config.parquet_batch_size = 10
        config.parquet_flush_interval_seconds = 30
        
        manager = BatchManager(config)
        
        event1 = {"event_id": "event-1"}
        event2 = {"event_id": "event-2"}
        
        manager.add_event(event1)
        manager.add_event(event2)
        
        assert len(manager.batch) == 2
        assert manager.batch[0] == event1
        assert manager.batch[1] == event2
        assert manager.stats["events_added"] == 2

    def test_should_flush_by_size(self):
        """Test should_flush returns True when batch size reached."""
        config = MagicMock(spec=Settings)
        config.parquet_batch_size = 2
        config.parquet_flush_interval_seconds = 30
        
        manager = BatchManager(config)
        
        # Add one event - should not flush
        manager.add_event({"event_id": "event-1"})
        assert not manager.should_flush()
        
        # Add second event - should flush
        manager.add_event({"event_id": "event-2"})
        assert manager.should_flush()

    def test_should_flush_by_age(self, monkeypatch):
        """Test should_flush returns True when batch age reached."""
        config = MagicMock(spec=Settings)
        config.parquet_batch_size = 100  # Large size
        config.parquet_flush_interval_seconds = 0.1  # Very short age
        
        manager = BatchManager(config)
        
        # Add one event
        manager.add_event({"event_id": "event-1"})
        
        # Initially should not flush
        assert not manager.should_flush()
        
        # Monkeypatch time to simulate aging
        original_time = manager.batch_created_time
        with monkeypatch.context() as m:
            m.setattr(time, "time", lambda: original_time + 0.2)  # Age > max_batch_age
            assert manager.should_flush()

    def test_flush(self):
        """Test flush returns events and clears batch."""
        config = MagicMock(spec=Settings)
        config.parquet_batch_size = 10
        config.parquet_flush_interval_seconds = 30
        
        manager = BatchManager(config)
        
        events = [
            {"event_id": "event-1"},
            {"event_id": "event-2"},
            {"event_id": "event-3"},
        ]
        
        for event in events:
            manager.add_event(event)
        
        flushed = manager.flush()
        
        assert flushed == events
        assert len(manager.batch) == 0
        assert manager.stats["batches_flushed"] == 1
        assert manager.stats["events_added"] == 3
        assert manager.batch_created_time > 0  # Should be reset

    def test_get_stats(self):
        """Test get_stats returns correct statistics."""
        config = MagicMock(spec=Settings)
        config.parquet_batch_size = 10
        config.parquet_flush_interval_seconds = 30
        
        manager = BatchManager(config)
        
        # Initial stats
        stats = manager.get_stats()
        assert stats["events_added"] == 0
        assert stats["batches_flushed"] == 0
        
        # Add events and flush
        manager.add_event({"event_id": "event-1"})
        manager.add_event({"event_id": "event-2"})
        manager.flush()
        
        stats = manager.get_stats()
        assert stats["events_added"] == 2
        assert stats["batches_flushed"] == 1


class TestParquetSchemaManager:
    """Tests for ParquetSchemaManager class."""

    def test_schema_property(self):
        """Test that schema property returns a PyArrow Schema."""
        manager = ParquetSchemaManager()
        schema = manager.schema
        assert isinstance(schema, pa.Schema)
        # Check some expected fields
        field_names = manager.field_names
        assert "event_id" in field_names
        assert "timestamp" in field_names
        assert "model_name" in field_names
        assert "year" in field_names
        assert "month" in field_names
        assert "day" in field_names
        assert "top1_label" in field_names
        assert "top1_score" in field_names
        assert "processing_time_ms" in field_names
        assert "kafka_topic" in field_names
        assert "kafka_partition" in field_names
        assert "kafka_offset" in field_names

    def test_field_names_property(self):
        """Test field_names property returns list of strings."""
        manager = ParquetSchemaManager()
        field_names = manager.field_names
        assert isinstance(field_names, list)
        assert all(isinstance(name, str) for name in field_names)
        # Should contain at least these fields
        expected_fields = {"event_id", "timestamp", "model_name", "year", "month", "day"}
        assert expected_fields.issubset(set(field_names))

    def test_validate_event_valid(self):
        """Test validate_event with a valid event."""
        manager = ParquetSchemaManager()
        event = {
            "event_id": "test-123",
            "timestamp": "2025-01-01T12:00:00Z",
            "model_name": "resnet50",
            "processing_timestamp": "2025-01-01T12:00:01Z",
            "year": 2025,
            "month": 1,
            "day": 1,
            "top1_label": "cat",
            "top1_score": 0.9,
            "top2_label": "dog",
            "top2_score": 0.08,
            "top3_label": "bird",
            "top3_score": 0.02,
            "frame_id": 100,
            "camera_id": "cam1",
            "processing_time_ms": 50.5,
            "kafka_topic": "inference-events",
            "kafka_partition": 0,
            "kafka_offset": 12345,
        }
        validated = manager.validate_event(event)
        assert isinstance(validated, dict)
        # Should contain all original fields plus any defaults
        assert validated["event_id"] == "test-123"
        assert validated["top1_label"] == "cat"
        assert validated["top1_score"] == 0.9
        # Should have numeric types for partition/offset
        assert isinstance(validated["kafka_partition"], int)
        assert isinstance(validated["kafka_offset"], int)

    def test_validate_event_missing_optional_fields(self):
        """Test validate_event with missing optional fields (should add defaults)."""
        manager = ParquetSchemaManager()
        event = {
            "event_id": "test-456",
            "timestamp": "2025-01-01T12:00:00Z",
            "model_name": "resnet50",
            "processing_timestamp": "2025-01-01T12:00:01Z",
            "year": 2025,
            "month": 1,
            "day": 1,
            "top1_label": "dog",
            "top1_score": 0.8,
            # Missing top2, top3, frame_id, camera_id, processing_time_ms, kafka fields
        }
        validated = manager.validate_event(event)
        # Should still contain required fields
        assert validated["event_id"] == "test-456"
        assert validated["top1_label"] == "dog"
        # Missing optional fields should have defaults (e.g., empty string or 0)
        assert validated.get("top2_label") == ""
        assert validated.get("top2_score") == 0.0
        assert validated.get("top3_label") == ""
        assert validated.get("top3_score") == 0.0
        assert validated.get("frame_id") == 0
        assert validated.get("camera_id") == ""
        assert validated.get("processing_time_ms") == 0.0
        assert validated.get("kafka_topic") == ""
        assert validated.get("kafka_partition") == -1
        assert validated.get("kafka_offset") == -1

    def test_validate_event_invalid_type(self):
        """Test validate_event with invalid field type (should coerce or raise)."""
        manager = ParquetSchemaManager()
        event = {
            "event_id": "test-789",
            "timestamp": "2025-01-01T12:00:00Z",
            "model_name": "resnet50",
            "processing_timestamp": "2025-01-01T12:00:01Z",
            "year": "2025",  # string instead of int
            "month": "1",
            "day": "1",
            "top1_label": "cat",
            "top1_score": "0.9",  # string instead of float
            "kafka_partition": "0",  # string instead of int
        }
        validated = manager.validate_event(event)
        # Should attempt to coerce types
        assert isinstance(validated["year"], int)
        assert validated["year"] == 2025
        assert isinstance(validated["month"], int)
        assert validated["month"] == 1
        assert isinstance(validated["day"], int)
        assert validated["day"] == 1
        assert isinstance(validated["top1_score"], float)
        assert validated["top1_score"] == 0.9
        assert isinstance(validated["kafka_partition"], int)
        assert validated["kafka_partition"] == 0

    def test_validate_event_missing_required_field(self):
        """Test validate_event with missing required field (should raise KeyError)."""
        manager = ParquetSchemaManager()
        event = {
            # Missing event_id
            "timestamp": "2025-01-01T12:00:00Z",
            "model_name": "resnet50",
        }
        with pytest.raises(KeyError):
            manager.validate_event(event)


class TestS3Uploader:
    """Tests for S3Uploader class."""

    @patch("src.kafka_to_parquet.parquet_writer.settings")
    def test_initialization(self, mock_settings):
        """Test S3Uploader initialization."""
        mock_settings.parquet_s3_bucket = "test-bucket"
        mock_settings.parquet_s3_region = "us-east-1"
        mock_settings.parquet_enable_s3_multipart = True
        mock_settings.parquet_s3_prefix = "inference-parquet"
        
        with patch("boto3.client") as mock_boto:
            uploader = S3Uploader()
            assert uploader.bucket == "test-bucket"
            assert uploader.region == "us-east-1"
            assert uploader.enable_multipart is True
            mock_boto.assert_called_once_with("s3", region_name="us-east-1")

    @patch("src.kafka_to_parquet.parquet_writer.settings")
    def test_generate_s3_key(self, mock_settings):
        """Test S3 key generation with partitioning."""
        mock_settings.parquet_s3_prefix = "inference-events/parquet"
        
        uploader = S3Uploader()
        
        # Test with partition
        key = uploader.generate_s3_key(
            prefix="custom-prefix",
            partition="year=2025/month=01/day=01",
            filename="events_20250101_120000.parquet"
        )
        assert key == "custom-prefix/year=2025/month=01/day=01/events_20250101_120000.parquet"
        
        # Test without partition
        key = uploader.generate_s3_key(
            prefix="custom-prefix",
            partition=None,
            filename="events.parquet"
        )
        assert key == "custom-prefix/events.parquet"
        
        # Test default prefix from settings
        key = uploader.generate_s3_key(
            prefix=None,
            partition=None,
            filename="events.parquet"
        )
        assert key == "inference-events/parquet/events.parquet"
        
        # Test default filename (UUID)
        with patch("src.kafka_to_parquet.parquet_writer.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "abc123"
            key = uploader.generate_s3_key(
                prefix="prefix",
                partition="year=2025/month=01"
            )
            assert key == "prefix/year=2025/month=01/abc123.parquet"

    @patch("src.kafka_to_parquet.parquet_writer.settings")
    @patch("boto3.client")
    def test_upload_file(self, mock_boto_client, mock_settings):
        """Test file upload to S3."""
        mock_settings.parquet_s3_bucket = "test-bucket"
        mock_settings.parquet_s3_region = "us-east-1"
        mock_settings.parquet_enable_s3_multipart = False
        
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        
        uploader = S3Uploader()
        
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            f.write(b"test parquet data")
            temp_path = f.name
        
        try:
            uploader.upload_file(
                local_path=temp_path,
                s3_key="test/key.parquet",
                content_type="application/parquet",
                metadata={"source": "test"}
            )
            
            mock_s3.upload_file.assert_called_once_with(
                str(Path(temp_path)),
                "test-bucket",
                "test/key.parquet",
                ExtraArgs={
                    "ContentType": "application/parquet",
                    "Metadata": {"source": "test"}
                }
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch("src.kafka_to_parquet.parquet_writer.settings")
    @patch("boto3.client")
    def test_upload_file_with_retry_success(self, mock_boto_client, mock_settings):
        """Test retry logic on successful upload."""
        mock_settings.parquet_s3_bucket = "test-bucket"
        mock_settings.parquet_s3_region = "us-east-1"
        mock_settings.parquet_enable_s3_multipart = False
        
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        
        uploader = S3Uploader()
        
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            f.write(b"test")
            temp_path = f.name
        
        try:
            # First call raises error, second succeeds
            mock_s3.upload_file.side_effect = [
                Exception("Network error"),
                None  # Success on retry
            ]
            
            # Should retry and succeed
            uploader.upload_file(
                local_path=temp_path,
                s3_key="test/key.parquet"
            )
            
            assert mock_s3.upload_file.call_count == 2
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch("src.kafka_to_parquet.parquet_writer.settings")
    @patch("boto3.client")
    def test_upload_file_multipart(self, mock_boto_client, mock_settings):
        """Test multipart upload for large files."""
        mock_settings.parquet_s3_bucket = "test-bucket"
        mock_settings.parquet_s3_region = "us-east-1"
        mock_settings.parquet_enable_s3_multipart = True
        
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        
        uploader = S3Uploader()
        
        # Create a file larger than 10 MB threshold
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            # Write 11 MB of data
            f.write(b"x" * (11 * 1024 * 1024))
            temp_path = f.name
        
        try:
            # Mock the TransferConfig import
            with patch("src.kafka_to_parquet.parquet_writer.TransferConfig"):
                uploader.upload_file(
                    local_path=temp_path,
                    s3_key="test/large.parquet"
                )
                # Should call upload_file with Config parameter
                mock_s3.upload_file.assert_called_once()
                call_kwargs = mock_s3.upload_file.call_args[1]
                assert "Config" in call_kwargs
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @patch("src.kafka_to_parquet.parquet_writer.settings")
    @patch("boto3.client")
    def test_upload_file_failure_after_max_retries(self, mock_boto_client, mock_settings):
        """Test upload failure after max retries."""
        mock_settings.parquet_s3_bucket = "test-bucket"
        mock_settings.parquet_s3_region = "us-east-1"
        mock_settings.parquet_enable_s3_multipart = False
        
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        mock_s3.upload_file.side_effect = Exception("Persistent error")
        
        uploader = S3Uploader()
        
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            f.write(b"test")
            temp_path = f.name
        
        try:
            success = uploader.upload_file(
                local_path=temp_path,
                s3_key="test/key.parquet"
            )
            assert success is False
            assert mock_s3.upload_file.call_count == 4  # max_retries + 1 = 4
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestS3ParquetWriter:
    """Tests for S3ParquetWriter class."""

    def test_initialization(self):
        """Test S3ParquetWriter initialization."""
        mock_schema_manager = MagicMock(spec=ParquetSchemaManager)
        mock_uploader = MagicMock(spec=S3Uploader)
        
        writer = S3ParquetWriter(
            schema_manager=mock_schema_manager,
            uploader=mock_uploader,
            compression="snappy",
            max_file_size_mb=128
        )
        
        assert writer.schema_manager == mock_schema_manager
        assert writer.uploader == mock_uploader
        assert writer.compression == "snappy"
        assert writer.max_file_size_mb == 128
        assert writer.temp_dir is not None

    def test_initialization_default_uploader(self):
        """Test initialization with default uploader (creates S3Uploader)."""
        mock_schema_manager = MagicMock(spec=ParquetSchemaManager)
        
        with patch("src.kafka_to_parquet.parquet_writer.S3Uploader") as mock_uploader_class:
            mock_uploader = MagicMock()
            mock_uploader_class.return_value = mock_uploader
            
            writer = S3ParquetWriter(schema_manager=mock_schema_manager)
            
            assert writer.schema_manager == mock_schema_manager
            assert writer.uploader == mock_uploader
            mock_uploader_class.assert_called_once()

    def test_write_batch(self):
        """Test writing a batch of events to Parquet."""
        mock_schema_manager = MagicMock(spec=ParquetSchemaManager)
        mock_uploader = MagicMock(spec=S3Uploader)
        mock_uploader.generate_s3_key.return_value = "prefix/year=2025/month=01/day=01/test.parquet"
        mock_uploader.upload_file = MagicMock()
        
        events = [
            {
                "event_id": "event-1",
                "timestamp": "2025-01-01T12:00:00Z",
                "model_name": "resnet50",
                "processing_timestamp": "2025-01-01T12:00:01Z",
                "year": 2025,
                "month": 1,
                "day": 1,
                "top1_label": "cat",
                "top1_score": 0.9,
                "frame_id": 100,
                "camera_id": "cam1",
                "processing_time_ms": 50.5,
            }
        ]
        
        # Mock pyarrow table creation
        mock_table = MagicMock()
        with patch("src.kafka_to_parquet.parquet_writer.pa.Table.from_pylist", return_value=mock_table) as mock_from_pylist:
            with patch("src.kafka_to_parquet.parquet_writer.pq.write_table") as mock_write:
                with patch("tempfile.mktemp", return_value="/tmp/test.parquet"):
                    writer = S3ParquetWriter(
                        schema_manager=mock_schema_manager,
                        uploader=mock_uploader,
                        compression="snappy"
                    )
                    writer.write_batch(events)
                    
                    # Validate each event
                    assert mock_schema_manager.validate_event.call_count == 1
                    
                    # Create table from validated events
                    mock_from_pylist.assert_called_once_with(events)
                    
                    # Write to temporary file
                    mock_write.assert_called_once_with(
                        mock_table,
                        "/tmp/test.parquet",
                        compression="snappy"
                    )
                    
                    # Generate S3 key and upload
                    mock_uploader.generate_s3_key.assert_called_once_with(
                        prefix="inference-events",
                        partition={"year": 2025, "month": 1, "day": 1},
                        filename="test.parquet"
                    )
                    mock_uploader.upload_file.assert_called_once_with(
                        local_path="/tmp/test.parquet",
                        s3_key="prefix/year=2025/month=01/day=01/test.parquet",
                        content_type="application/parquet",
                        metadata={"batch_size": 1}
                    )

    def test_write_batch_empty(self):
        """Test writing empty batch (should do nothing)."""
        mock_schema_manager = MagicMock(spec=ParquetSchemaManager)
        mock_uploader = MagicMock(spec=S3Uploader)
        
        writer = S3ParquetWriter(
            schema_manager=mock_schema_manager,
            uploader=mock_uploader
        )
        
        # Should not raise any exception and not call any methods
        writer.write_batch([])
        
        mock_schema_manager.validate_event.assert_not_called()
        mock_uploader.upload_file.assert_not_called()

    def test_write_batch_with_metadata(self):
        """Test writing batch with custom metadata."""
        mock_schema_manager = MagicMock(spec=ParquetSchemaManager)
        mock_uploader = MagicMock(spec=S3Uploader)
        mock_uploader.generate_s3_key.return_value = "prefix/year=2025/month=01/day=01/test.parquet"
        mock_uploader.upload_file = MagicMock()
        
        events = [
            {
                "event_id": "event-1",
                "timestamp": "2025-01-01T12:00:00Z",
                "model_name": "resnet50",
                "processing_timestamp": "2025-01-01T12:00:01Z",
                "year": 2025,
                "month": 1,
                "day": 1,
                "top1_label": "cat",
                "top1_score": 0.9,
            }
        ]
        
        metadata = {"source": "test", "batch_id": "123"}
        
        with patch("src.kafka_to_parquet.parquet_writer.pa.Table.from_pylist"):
            with patch("src.kafka_to_parquet.parquet_writer.pq.write_table"):
                with patch("tempfile.mktemp", return_value="/tmp/test.parquet"):
                    writer = S3ParquetWriter(
                        schema_manager=mock_schema_manager,
                        uploader=mock_uploader
                    )
                    writer.write_batch(events, metadata=metadata)
                    
                    # Metadata should be passed to upload
                    mock_uploader.upload_file.assert_called_once()
                    call_kwargs = mock_uploader.upload_file.call_args.kwargs
                    assert call_kwargs["metadata"] == {"batch_size": 1, "source": "test", "batch_id": "123"}


class TestKafkaParquetMetrics:
    """Tests for KafkaParquetMetrics class."""

    def test_initialization(self):
        """Test metrics initialization."""
        metrics = KafkaParquetMetrics()
        assert metrics.events_processed == 0
        assert metrics.batches_written == 0
        assert metrics.errors == 0
        assert metrics.dead_letters == 0
        assert metrics.last_log_time is not None
        assert metrics.start_time is not None

    def test_record_event_processed(self):
        """Test recording processed events."""
        metrics = KafkaParquetMetrics()
        metrics.record_event_processed(5)
        assert metrics.events_processed == 5
        metrics.record_event_processed()
        assert metrics.events_processed == 6

    def test_record_batch_written(self):
        """Test recording batch written."""
        metrics = KafkaParquetMetrics()
        metrics.record_batch_written(10)
        assert metrics.batches_written == 1
        assert metrics.events_processed == 10
        metrics.record_batch_written(5)
        assert metrics.batches_written == 2
        assert metrics.events_processed == 15

    def test_record_error(self):
        """Test recording errors."""
        metrics = KafkaParquetMetrics()
        metrics.record_error()
        assert metrics.errors == 1
        metrics.record_error()
        assert metrics.errors == 2

    def test_record_dead_letter(self):
        """Test recording dead letters."""
        metrics = KafkaParquetMetrics()
        metrics.record_dead_letter()
        assert metrics.dead_letters == 1

    def test_get_stats(self):
        """Test getting metrics statistics."""
        metrics = KafkaParquetMetrics()
        metrics.record_event_processed(100)
        metrics.record_batch_written(100)
        metrics.record_error()
        metrics.record_dead_letter()
        
        with patch("time.time", return_value=metrics.start_time + 60):
            stats = metrics.get_stats()
            
            assert stats["events_processed"] == 100
            assert stats["batches_written"] == 1
            assert stats["errors"] == 1
            assert stats["dead_letters"] == 1
            assert stats["uptime_seconds"] == 60
            assert stats["processing_rate_per_second"] == 100 / 60

    @patch("src.kafka_to_parquet.metrics_integration.logging.getLogger")
    def test_log_metrics(self, mock_get_logger):
        """Test logging metrics in JSON format."""
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        
        metrics = KafkaParquetMetrics()
        metrics.record_event_processed(50)
        metrics.record_batch_written(50)
        
        # Mock time to control uptime
        with patch("time.time", return_value=metrics.start_time + 120):
            metrics.log_metrics()
            
            # Verify logger was called with JSON message
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0]
            assert len(call_args) == 1
            log_message = call_args[0]
            
            # Should be a JSON string
            import json
            log_dict = json.loads(log_message)
            assert log_dict["component"] == "kafka_to_parquet"
            assert log_dict["events_processed"] == 50
            assert log_dict["batches_written"] == 1
            assert log_dict["uptime_seconds"] == 120
            assert "processing_rate_per_second" in log_dict


if __name__ == "__main__":
    pytest.main([__file__, "-v"])