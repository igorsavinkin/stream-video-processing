# Stream Video ML Service

End-to-end ML service for RTSP video streams: ingestion, preprocessing, model
inference, API wrapper, Dockerization, CI/CD, and AWS ECS Fargate deployment.

## Features
- RTSP frame ingestion with sampling and reconnection
- Preprocessing and optional dataset capture
- Image classification using a pretrained MobileNetV3 model
- Optional person detection (yes/no) using Faster R-CNN (COCO)
- FastAPI endpoints: health, predict, stream (SSE)
- Docker and docker-compose for local runs
- CI/CD pipeline template for ECR + ECS Fargate
- Terraform templates for minimal AWS infrastructure

## Quick start (local)
1. Create a virtual environment and install deps:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Optional: provide config via YAML (or use env vars):
   ```bash
   set APP_CONFIG_PATH=config.example.yaml
   ```
3. Run API:
   ```bash
   uvicorn src.api.app:app --host 0.0.0.0 --port 8000
   ```

Open `http://localhost:8000/docs` to test endpoints.

## RTSP source
Set `APP_RTSP_URL` in your environment or edit `config.example.yaml`.

## Person detection (yes/no)
Use the built-in COCO person detector instead of ImageNet classification:
```bash
set APP_MODEL_NAME=person_detector
set APP_PERSON_SCORE_THRESHOLD=0.6
```
When enabled, `predictions` includes `person` and `no_person`, plus `has_person`.

## Capture dataset
Collect frames from the stream to build a training dataset (`data/raw` folder):
```bash
python -m src.ingest.capture --output data/raw --max-frames 200
```

## API endpoints
- `GET /health` basic health check
- `POST /predict` image upload (multipart/form-data)
- `GET /stream` Server-Sent Events (SSE) with predictions from RTSP stream

## Tests
Install dev dependencies and run the test suite:
```bash
pip install -r requirements-dev.txt
pytest
```

## Docker
```bash
docker build -t stream-ml-service .
docker run --env-file .env -p 8000:8000 stream-ml-service
```
**Note:** Docker is optional for local development (you can run via `uvicorn` and a venv).  
Docker is required for the CI/CD flow (GitHub Actions builds the image and deploys it to AWS ECS).

## SSE viewer & Postman
- Open `tools/sse_viewer.html` in a browser and click Connect.
- Import `tools/postman_collection.json` into Postman.

## CI/CD & AWS
1. Create AWS resources using Terraform in `infra/`.
2. Configure GitHub Actions secrets:
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`
   - `ECR_REPOSITORY`, `ECS_CLUSTER`, `ECS_SERVICE`
3. Push to main to trigger build/push/deploy.

## Monitoring
- Application logs go to stdout and are collected by CloudWatch Logs in ECS.
- Metrics snapshots are emitted as single-line JSON for CloudWatch parsing.

## Inference dataset capture
Enable capture of inference frames + metadata for retraining:

Environment variables:
- `APP_CAPTURE_INFERENCE=true`
- `APP_CAPTURE_DIR=data/inference`
- `APP_CAPTURE_EVERY_N=10`
- `APP_CAPTURE_S3_BUCKET=your-s3-bucket` (optional)
- `APP_CAPTURE_S3_PREFIX=inference`

Captured data layout:
- `YYYY/MM/DD/<timestamp>_<uuid>.jpg`
- `YYYY/MM/DD/<timestamp>_<uuid>.json`
