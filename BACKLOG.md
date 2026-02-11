# Project Backlog (2026-ready)

Backlog organized in 3 iterations. Each item lists target files to change.

## Iteration 1 — MVP (stabilize current pipeline)
1) RTSP source via local server
   - Priority: P0
   - Estimate: 2-4h
   - Files: `README.md`, `config.example.yaml`
   - Checklist:
     - [ ] Add MediaMTX/FFmpeg setup steps
     - [ ] Add example `rtsp://localhost:8554/live`

2) Stream health endpoint + fallback
   - Priority: P0
   - Estimate: 3-6h
   - Files: `src/ingest/rtsp_reader.py`, `src/api/app.py`
   - Checklist:
     - [ ] Add `/health/stream` endpoint (ok/fail)
     - [ ] Add fallback to local MP4 on failure

3) Structured logging
   - Priority: P1
   - Estimate: 2-4h
   - Files: `src/metrics.py`, `src/api/app.py`
   - Checklist:
     - [ ] Emit JSON logs with `request_id`
     - [ ] Include model version + latency

4) Runbook docs
   - Priority: P1
   - Estimate: 1-2h
   - Files: `README.md`
   - Checklist:
     - [ ] “local mp4” recipe
     - [ ] “camera index” recipe
     - [ ] “rtsp server” recipe

## Iteration 2 — Beta (streaming + MLOps)
5) Kafka/Kinesis ingestion of metadata
   - Priority: P1
   - Estimate: 1-2d
   - Files: `src/ingest/kinesis_producer.py` or `src/ingest/kafka_producer.py`
   - Checklist:
     - [ ] Send `{timestamp, topk, source, latency}` events
     - [ ] Add retries + backoff

6) Message schema
   - Priority: P1
   - Estimate: 4-6h
   - Files: `schemas/inference_event.json`
   - Checklist:
     - [ ] Define schema (JSON/Avro/Protobuf)
     - [ ] Add validator in `src/ingest/`

7) Model registry (MLflow)
   - Priority: P2
   - Estimate: 1-2d
   - Files: `src/model/train.py`, `src/model/infer.py`, `infra/`
   - Checklist:
     - [ ] Log metrics/artifacts
     - [ ] Register model versions

8) Continuous Training (CT)
   - Priority: P2
   - Estimate: 1-2d
   - Files: `.github/workflows/ct.yml`, `src/model/train.py`
   - Checklist:
     - [ ] Scheduled retrain
     - [ ] Publish model to registry

9) Test suite expansion
   - Priority: P1
   - Estimate: 1d
   - Files: `tests/test_infer.py`, `tests/test_stream.py`
   - Checklist:
     - [ ] Smoke tests
     - [ ] Integration tests with sample video

## Iteration 3 — Production (robust + secure + scalable)
10) Drift monitoring
    - Priority: P2
    - Estimate: 2-3d
    - Files: `src/monitoring/drift.py`
    - Checklist:
      - [ ] PSI/KL on logits/embeddings
      - [ ] Alert thresholds

11) Auth + rate limits
    - Priority: P0
    - Estimate: 1-2d
    - Files: `src/api/app.py`
    - Checklist:
      - [ ] API key/JWT
      - [ ] Per-endpoint throttling

12) Autoscaling + cost controls
    - Priority: P1
    - Estimate: 1-2d
    - Files: `infra/main.tf`
    - Checklist:
      - [ ] ECS autoscaling
      - [ ] CPU/RAM guardrails

13) A/B model versions
    - Priority: P2
    - Estimate: 1-2d
    - Files: `src/model/infer.py`, `src/api/app.py`
    - Checklist:
      - [ ] Route by header or percentage
      - [ ] Rollback on errors
