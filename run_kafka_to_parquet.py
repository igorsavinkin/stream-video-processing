#!/usr/bin/env python3
"""
Entry point script for Kafka to S3 Parquet pipeline.

This script:
1. Loads configuration from environment and config.yaml
2. Initializes Kafka consumer, event processor, and Parquet writer
3. Starts the consumer loop
4. Handles graceful shutdown on SIGINT/SIGTERM
"""

import argparse
import logging
import signal
import sys
import time
from typing import Optional

from src.config import settings
from src.kafka_to_parquet import (
    KafkaEventConsumer,
    EventProcessor,
    BatchManager,
    ParquetSchemaManager,
    S3ParquetWriter,
    S3Uploader,
    init_metrics,
)

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Reduce noise from libraries
    logging.getLogger("kafka").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def create_pipeline_components() -> tuple:
    """
    Create and connect all pipeline components.
    
    Returns:
        Tuple of (consumer, processor, writer)
    """
    # Check if Kafka consumer is enabled
    if not settings.kafka_consumer_enabled:
        raise RuntimeError(
            "Kafka consumer is disabled in configuration. "
            "Set KAFKA_CONSUMER_ENABLED=true or kafka_consumer_enabled: true"
        )
    
    # Check if S3 bucket is configured
    if not settings.parquet_s3_bucket:
        raise RuntimeError(
            "S3 bucket for Parquet storage is not configured. "
            "Set PARQUET_S3_BUCKET or parquet_s3_bucket in configuration"
        )
    
    logger.info("Creating pipeline components...")
    
    # Initialize metrics
    init_metrics(log_every=settings.parquet_metrics_log_every)
    
    # 1. Create Parquet writer components
    schema_manager = ParquetSchemaManager()
    uploader = S3Uploader(
        bucket=settings.parquet_s3_bucket,
        region=settings.parquet_s3_region,
        enable_multipart=settings.parquet_enable_s3_multipart,
    )
    writer = S3ParquetWriter(
        schema_manager=schema_manager,
        uploader=uploader,
        compression=settings.parquet_compression,
        max_file_size_mb=settings.parquet_max_file_size_mb,
    )
    
    # 2. Create batch manager
    batch_manager = BatchManager(
        batch_size=settings.parquet_batch_size,
        flush_interval_seconds=settings.parquet_flush_interval_seconds,
        writer=writer,
    )
    
    # 3. Create event processor
    processor = EventProcessor(
        batch_manager=batch_manager,
        dead_letter_queue_path=settings.parquet_dead_letter_queue_path,
    )
    
    # 4. Create Kafka consumer
    consumer = KafkaEventConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        topic=settings.kafka_topic,
        group_id=settings.kafka_consumer_group_id,
        processor=processor,
        max_poll_records=settings.kafka_consumer_max_poll_records,
        auto_offset_reset=settings.kafka_consumer_auto_offset_reset,
        enable_auto_commit=settings.kafka_consumer_enable_auto_commit,
        session_timeout_ms=settings.kafka_consumer_session_timeout_ms,
        heartbeat_interval_ms=settings.kafka_consumer_heartbeat_interval_ms,
        max_poll_interval_ms=settings.kafka_consumer_max_poll_interval_ms,
    )
    
    logger.info("Pipeline components created successfully")
    return consumer, processor, writer


class PipelineRunner:
    """Manages pipeline lifecycle and graceful shutdown."""
    
    def __init__(self, consumer, processor, writer):
        self.consumer = consumer
        self.processor = processor
        self.writer = writer
        self.shutdown_requested = False
        self.stats_interval = 60  # seconds
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info("Received shutdown signal %s", signum)
        self.shutdown_requested = True
    
    def run(self) -> int:
        """Run the main pipeline loop."""
        logger.info("Starting Kafka to Parquet pipeline")
        logger.info("Configuration:")
        logger.info("  Kafka: %s/%s", settings.kafka_bootstrap_servers, settings.kafka_topic)
        logger.info("  S3: bucket=%s, prefix=%s", settings.parquet_s3_bucket, settings.parquet_s3_prefix)
        logger.info("  Batch: size=%d, flush_interval=%ds", 
                   settings.parquet_batch_size, settings.parquet_flush_interval_seconds)
        
        try:
            # Start consumer
            self.consumer.start()
            last_stats_time = time.time()
            
            # Main loop
            while not self.shutdown_requested:
                # Check consumer status
                if not self.consumer.is_running():
                    logger.error("Consumer has stopped unexpectedly")
                    break
                
                # Periodically log statistics
                current_time = time.time()
                if current_time - last_stats_time >= self.stats_interval:
                    self._log_statistics()
                    last_stats_time = current_time
                
                # Sleep briefly to avoid busy waiting
                time.sleep(1.0)
            
            # Shutdown requested
            logger.info("Shutdown requested, stopping pipeline...")
            return self._shutdown()
            
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            return self._shutdown()
        except Exception as exc:
            logger.exception("Pipeline failed with error: %s", exc)
            return 1
    
    def _log_statistics(self) -> None:
        """Log current pipeline statistics."""
        consumer_stats = self.consumer.get_stats()
        processor_stats = self.processor.get_stats()
        writer_stats = self.writer.get_stats()
        
        logger.info("Pipeline statistics:")
        logger.info("  Consumer: %s", consumer_stats)
        logger.info("  Processor: %s", processor_stats)
        logger.info("  Writer: %s", writer_stats)
    
    def _shutdown(self) -> int:
        """Perform graceful shutdown."""
        exit_code = 0
        
        try:
            # Stop consumer
            logger.info("Stopping Kafka consumer...")
            self.consumer.stop()
            
            # Flush any remaining batches
            logger.info("Flushing remaining events...")
            self.processor.flush()
            
            # Close writer
            logger.info("Closing Parquet writer...")
            self.writer.close()
            
            # Final statistics
            self._log_statistics()
            logger.info("Pipeline shutdown complete")
            
        except Exception as exc:
            logger.exception("Error during shutdown: %s", exc)
            exit_code = 1
        
        return exit_code


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Kafka to S3 Parquet pipeline for inference events"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to config.yaml file (default: auto-detected)"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Load configuration if specified
    if args.config:
        from src.config import load_config
        load_config(args.config)
        logger.info("Loaded configuration from %s", args.config)
    
    try:
        # Create pipeline components
        consumer, processor, writer = create_pipeline_components()
        
        # Create and run pipeline
        runner = PipelineRunner(consumer, processor, writer)
        return runner.run()
        
    except Exception as exc:
        logger.exception("Failed to start pipeline: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())