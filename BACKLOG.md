# Project Backlog (2026-ready)

Backlog organized in 3 iterations. Each item lists target files to change.

## Iteration 1 — MVP (stabilize current pipeline)
1) RTSP source via local server
   - Files: `README.md`, `config.example.yaml`
   - Add MediaMTX/FFmpeg instructions and example `rtsp://localhost:8554/live`.

2) Stream health endpoint + fallback
   - Files: `src/ingest/rtsp_reader.py`, `src/api/app.py`
   - Add `/health/stream` (ok/fail) and fallback to local MP4.

3) Structured logging
   - Files: `src/metrics.py`, `src/api/app.py`
   - Emit JSON logs with `request_id`, model version, latency.

4) Runbook docs
   - Files: `README.md`
   - Add “local mp4”, “camera index”, “rtsp server” run recipes.

## Iteration 2 — Beta (streaming + MLOps)
5) Kafka/Kinesis ingestion of metadata
   - Files: `src/ingest/kinesis_producer.py` or `src/ingest/kafka_producer.py`
   - Send `{timestamp, topk, source, latency}` events.

6) Message schema
   - Files: `schemas/inference_event.json`
   - Add JSON schema (or Avro/Protobuf) + validator in `src/ingest/`.

7) Model registry (MLflow)
   - Files: `src/model/train.py`, `src/model/infer.py`, `infra/`
   - Track metrics, artifacts, versions.

8) Continuous Training (CT)
   - Files: `.github/workflows/ct.yml`, `src/model/train.py`
   - Scheduled retrain + publish model.

9) Test suite expansion
   - Files: `tests/test_infer.py`, `tests/test_stream.py`
   - Smoke + integration tests with a sample video.

## Iteration 3 — Production (robust + secure + scalable)
10) Drift monitoring
    - Files: `src/monitoring/drift.py`
    - PSI/KL divergence on logits or embeddings.

11) Auth + rate limits
    - Files: `src/api/app.py`
    - API key/JWT + per-endpoint throttling.

12) Autoscaling + cost controls
    - Files: `infra/main.tf`
    - ECS autoscaling, CPU/RAM guardrails.

13) A/B model versions
    - Files: `src/model/infer.py`, `src/api/app.py`
    - Route by header or percentage, rollback on errors.
