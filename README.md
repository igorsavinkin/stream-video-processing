# Stream Video ML Service

End-to-end ML service for RTSP video streams: ingestion, preprocessing, model
inference, API wrapper, Dockerization, CI/CD, and AWS ECS Fargate deployment.

## Features
- RTSP frame ingestion with sampling and reconnection
- Preprocessing and optional dataset capture
- Image classification using a pretrained MobileNetV3 model
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

## Capture dataset
Collect frames from the stream to build a training dataset:
```bash
python -m src.ingest.capture --output data/raw --max-frames 200
```

## API endpoints
- `GET /health` basic health check
- `POST /predict` image upload (multipart/form-data)
- `GET /stream` Server-Sent Events (SSE) with predictions from RTSP stream

## Docker
```bash
docker build -t stream-ml-service .
docker run --env-file .env -p 8000:8000 stream-ml-service
```

## CI/CD & AWS
1. Create AWS resources using Terraform in `infra/`.
2. Configure GitHub Actions secrets:
   - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`
   - `ECR_REPOSITORY`, `ECS_CLUSTER`, `ECS_SERVICE`
3. Push to main to trigger build/push/deploy.

## Monitoring
- Application logs go to stdout and are collected by CloudWatch Logs in ECS.
- Metrics snapshots are logged in JSON format by `src/metrics.py`.
