param(
  [string]$Repo = "igorsavinkin/stream-video-processing"
)

$ErrorActionPreference = "Stop"

function New-Issue($title, $body, $labels) {
  $labelArgs = @()
  if ($labels -and $labels.Count -gt 0) {
    $labelArgs = @("--label", ($labels -join ","))
  }
  $result = gh issue create --repo $Repo --title $title --body $body @labelArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to create issue: $title"
  }
  Write-Host "Created: $title"
  Write-Host "URL: $result"
}

function Ensure-Label($label, $color) {
  $result = gh label create $label --repo $Repo --color $color --force
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to create label: $label"
  }
  Write-Host "Label ensured: $label"
}

Write-Host "Creating issues in $Repo ..."

Ensure-Label "iteration-1" "0e8a16"
Ensure-Label "iteration-2" "1d76db"
Ensure-Label "iteration-3" "5319e7"
Ensure-Label "p0" "b60205"
Ensure-Label "p1" "d93f0b"
Ensure-Label "p2" "fbca04"

New-Issue "Iteration 1: RTSP source via local server" @"
Goal: Add local RTSP source instructions and example URL.

Files:
- README.md
- config.example.yaml

Checklist:
- Add MediaMTX/FFmpeg setup steps
- Add example rtsp://localhost:8554/live
"@ @("iteration-1","p0")

New-Issue "Iteration 1: Stream health endpoint + fallback" @"
Goal: Add /health/stream and fallback to local MP4 when RTSP fails.

Files:
- src/ingest/rtsp_reader.py
- src/api/app.py

Checklist:
- Add /health/stream (ok/fail)
- Add fallback to local MP4
"@ @("iteration-1","p0")

New-Issue "Iteration 1: Structured logging" @"
Goal: Emit JSON logs with request_id, model version, latency.

Files:
- src/metrics.py
- src/api/app.py

Checklist:
- JSON logs with request_id
- include model version + latency
"@ @("iteration-1","p1")

New-Issue "Iteration 1: Runbook docs" @"
Goal: Add run recipes for local mp4, camera index, rtsp server.

Files:
- README.md

Checklist:
- local mp4 recipe
- camera index recipe
- rtsp server recipe
"@ @("iteration-1","p1")

New-Issue "Iteration 2: Kafka/Kinesis ingestion of metadata" @"
Goal: Send inference metadata events to streaming platform.

Files:
- src/ingest/kinesis_producer.py OR src/ingest/kafka_producer.py

Checklist:
- Send {timestamp, topk, source, latency} events
- Add retries + backoff
"@ @("iteration-2","p1")

New-Issue "Iteration 2: Message schema" @"
Goal: Define event schema and validator.

Files:
- schemas/inference_event.json

Checklist:
- Define schema (JSON/Avro/Protobuf)
- Add validator in src/ingest/
"@ @("iteration-2","p1")

New-Issue "Iteration 2: Model registry (MLflow)" @"
Goal: Track metrics, artifacts, and model versions in MLflow.

Files:
- src/model/train.py
- src/model/infer.py
- infra/

Checklist:
- Log metrics/artifacts
- Register model versions
"@ @("iteration-2","p2")

New-Issue "Iteration 2: Continuous Training (CT)" @"
Goal: Scheduled retraining and model publishing.

Files:
- .github/workflows/ct.yml
- src/model/train.py

Checklist:
- Scheduled retrain
- Publish model to registry
"@ @("iteration-2","p2")

New-Issue "Iteration 2: Test suite expansion" @"
Goal: Add smoke and integration tests with a sample video.

Files:
- tests/test_infer.py
- tests/test_stream.py

Checklist:
- Smoke tests
- Integration tests with sample video
"@ @("iteration-2","p1")

New-Issue "Iteration 3: Drift monitoring" @"
Goal: Add drift detection (PSI/KL) with alert thresholds.

Files:
- src/monitoring/drift.py

Checklist:
- PSI/KL on logits/embeddings
- Alert thresholds
"@ @("iteration-3","p2")

New-Issue "Iteration 3: Auth + rate limits" @"
Goal: Protect API with auth and throttling.

Files:
- src/api/app.py

Checklist:
- API key/JWT
- Per-endpoint throttling
"@ @("iteration-3","p0")

New-Issue "Iteration 3: Autoscaling + cost controls" @"
Goal: Add ECS autoscaling and CPU/RAM guardrails.

Files:
- infra/main.tf

Checklist:
- ECS autoscaling
- CPU/RAM guardrails
"@ @("iteration-3","p1")

New-Issue "Iteration 3: A/B model versions" @"
Goal: Route traffic between model versions and support rollback.

Files:
- src/model/infer.py
- src/api/app.py

Checklist:
- Route by header or percentage
- Rollback on errors
"@ @("iteration-3","p2")

Write-Host "Done."
