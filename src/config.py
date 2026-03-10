from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    rtsp_url: str = Field(
        default="rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mov"
    )
    frame_sample_fps: int = 2
    frame_width: int = 640
    frame_height: int = 360
    model_name: str = "resnet50"
    device: str = "cpu"
    metrics_log_every: int = 50
    save_processed: bool = False
    processed_dir: str = "data/processed"
    class_topk: int = 5
    person_score_threshold: float = 0.6
    detection_threshold: float = 0.5
    camera_name: Optional[str] = None
    config_path: Optional[str] = None
    log_level: str = "INFO"
    capture_inference: bool = False
    capture_dir: str = "data/inference"
    capture_every_n: int = 10
    capture_s3_bucket: Optional[str] = None
    capture_s3_prefix: str = "inference"
    fallback_mp4_path: Optional[str] = None
    # Streaming metadata ingestion
    streaming_backend: str = "none"  # "kafka", "kinesis", or "none"
    kafka_bootstrap_servers: Optional[str] = None
    kafka_topic: str = "inference-events"
    kinesis_stream_name: Optional[str] = None
    kinesis_region: str = "us-east-1"
    streaming_max_retries: int = 3
    streaming_retry_backoff_ms: int = 100
    # Auth & rate limiting
    api_keys: str = ""  # comma-separated list of valid API keys; empty = auth disabled
    rate_limit_predict: str = "30/minute"  # rate limit for /predict
    rate_limit_stream: str = "10/minute"   # rate limit for /stream
    rate_limit_default: str = "60/minute"  # rate limit for other endpoints

    # Kafka to Parquet consumer settings
    kafka_consumer_enabled: bool = False
    kafka_consumer_group_id: str = "inference-parquet-consumer"
    kafka_consumer_auto_offset_reset: str = "earliest"
    kafka_consumer_max_poll_records: int = 100
    kafka_consumer_session_timeout_ms: int = 45000
    kafka_consumer_heartbeat_interval_ms: int = 3000
    kafka_consumer_max_poll_interval_ms: int = 300000
    kafka_consumer_log_level: str = "INFO"

    # Parquet writer settings
    parquet_s3_bucket: Optional[str] = None
    parquet_s3_prefix: str = "inference-parquet"
    parquet_batch_size: int = 1000
    parquet_flush_interval_seconds: int = 60
    parquet_compression: str = "snappy"
    parquet_partition_columns: str = "year,month,day"  # comma-separated
    parquet_max_file_size_mb: int = 128
    parquet_enable_s3_multipart: bool = True
    parquet_s3_region: Optional[str] = None
    parquet_dead_letter_queue_path: Optional[str] = None
    parquet_metrics_log_every: int = 60  # seconds between metrics logs

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        extra="ignore",
        protected_namespaces=(),
    )


class YamlSettings(BaseModel):
    rtsp_url: Optional[str] = None
    frame_sample_fps: Optional[int] = None
    frame_width: Optional[int] = None
    frame_height: Optional[int] = None
    model_name: Optional[str] = None
    device: Optional[str] = None
    metrics_log_every: Optional[int] = None
    save_processed: Optional[bool] = None
    processed_dir: Optional[str] = None
    class_topk: Optional[int] = None
    person_score_threshold: Optional[float] = None
    detection_threshold: Optional[float] = None
    camera_name: Optional[str] = None
    log_level: Optional[str] = None
    capture_inference: Optional[bool] = None
    capture_dir: Optional[str] = None
    capture_every_n: Optional[int] = None
    capture_s3_bucket: Optional[str] = None
    capture_s3_prefix: Optional[str] = None
    fallback_mp4_path: Optional[str] = None
    # Streaming metadata ingestion
    streaming_backend: Optional[str] = None
    kafka_bootstrap_servers: Optional[str] = None
    kafka_topic: Optional[str] = None
    kinesis_stream_name: Optional[str] = None
    kinesis_region: Optional[str] = None
    streaming_max_retries: Optional[int] = None
    streaming_retry_backoff_ms: Optional[int] = None
    # Auth & rate limiting
    api_keys: Optional[str] = None
    rate_limit_predict: Optional[str] = None
    rate_limit_stream: Optional[str] = None
    rate_limit_default: Optional[str] = None

    # Kafka to Parquet consumer settings
    kafka_consumer_enabled: Optional[bool] = None
    kafka_consumer_group_id: Optional[str] = None
    kafka_consumer_auto_offset_reset: Optional[str] = None
    kafka_consumer_max_poll_records: Optional[int] = None
    kafka_consumer_session_timeout_ms: Optional[int] = None
    kafka_consumer_heartbeat_interval_ms: Optional[int] = None
    kafka_consumer_max_poll_interval_ms: Optional[int] = None
    kafka_consumer_log_level: Optional[str] = None

    # Parquet writer settings
    parquet_s3_bucket: Optional[str] = None
    parquet_s3_prefix: Optional[str] = None
    parquet_batch_size: Optional[int] = None
    parquet_flush_interval_seconds: Optional[int] = None
    parquet_compression: Optional[str] = None
    parquet_partition_columns: Optional[str] = None
    parquet_max_file_size_mb: Optional[int] = None
    parquet_enable_s3_multipart: Optional[bool] = None
    parquet_s3_region: Optional[str] = None
    parquet_dead_letter_queue_path: Optional[str] = None
    parquet_metrics_log_every: Optional[int] = None

    model_config = {
        "protected_namespaces": (),
    }


def load_settings() -> Settings:
    settings = Settings()
    config_path = settings.config_path or os.getenv("APP_CONFIG_PATH")
    if not config_path:
        return settings

    path = Path(config_path)
    if not path.exists():
        return settings

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    yaml_settings = YamlSettings(**payload)
    merged = settings.model_copy(update=yaml_settings.model_dump(exclude_none=True))
    return merged


settings = load_settings()
