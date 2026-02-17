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

## Runbook: Common Video Source Recipes

Quick reference for setting up different video sources.

### Recipe 1: Local MP4 File

Use a local video file directly as the video source.

**Option A: Via config file**
1. Edit `config.example.yaml`:
   ```yaml
   rtsp_url: C:/path/to/your/video.mp4
   ```
   Or use forward slashes: `C:/Users/username/Videos/video.mp4`

2. Run the API:
   ```bash
   set APP_CONFIG_PATH=config.example.yaml
   uvicorn src.api.app:app --host 0.0.0.0 --port 8000
   ```

**Option B: Via environment variable**
```bash
set APP_RTSP_URL=C:/path/to/your/video.mp4
uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

**Notes:**
- The video will loop automatically
- Supports common formats: MP4, AVI, MOV, etc.
- Use absolute paths for best results
- Windows: Use forward slashes or escaped backslashes

### Recipe 2: Camera by Index

Use a camera device by its index (0, 1, 2, etc.).

**Option A: Via config file**
1. Edit `config.example.yaml`:
   ```yaml
   rtsp_url: 0
   ```
   Use `0` for first camera, `1` for second, etc.

2. Run the API:
   ```bash
   set APP_CONFIG_PATH=config.example.yaml
   uvicorn src.api.app:app --host 0.0.0.0 --port 8000
   ```

**Option B: Via environment variable**
```bash
set APP_RTSP_URL=0
uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

**Option C: Auto-detect camera**
```yaml
rtsp_url: auto
```
This will automatically find and use the first available camera.

**Option D: Camera by name (Windows)**
```yaml
rtsp_url: video=USB Video Device
camera_name: USB Video Device
```
Specify the exact camera name if you have multiple cameras.

**Notes:**
- Camera index starts at 0
- On Windows, the system will try MSMF backend first, then DSHOW
- Use `auto` to let the system find the first available camera

### Recipe 3: RTSP Server

Use an RTSP stream from a server (local or remote).

**For local RTSP server (MediaMTX):**
See the detailed setup in the [Local RTSP server setup](#local-rtsp-server-setup-mediamtxffmpeg) section above.

**Quick setup:**
1. Start MediaMTX (see setup instructions above)
2. Stream video to MediaMTX:
   ```bash
   ffmpeg -re -stream_loop -1 -i your_video.mp4 -c copy -f rtsp rtsp://localhost:8554/live
   ```
3. Configure the service:
   ```yaml
   rtsp_url: rtsp://localhost:8554/live
   ```

**For remote RTSP server:**
```yaml
rtsp_url: rtsp://example.com:8554/stream
```

**Via environment variable:**
```bash
set APP_RTSP_URL=rtsp://localhost:8554/live
uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

**Notes:**
- Default RTSP port is 8554
- Ensure firewall allows RTSP traffic
- The service will automatically reconnect if the stream drops
- Use `/health/stream` endpoint to check stream health

### Local RTSP server setup (MediaMTX/FFmpeg)

For local development and testing, you can set up a local RTSP server using MediaMTX or FFmpeg:

**Prerequisites:** Install FFmpeg (required for streaming video to MediaMTX):
- **Windows**: 
  - Using winget: `winget install ffmpeg`
  - Using Chocolatey: `choco install ffmpeg`
  - Manual: Download from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html) and add to PATH
- **Linux**: `sudo apt install ffmpeg` (Ubuntu/Debian) or `sudo yum install ffmpeg` (RHEL/CentOS)
- **Mac**: `brew install ffmpeg`

#### Option 1: MediaMTX (recommended)
1. Download MediaMTX binary from [https://github.com/bluenviron/mediamtx/releases](https://github.com/bluenviron/mediamtx/releases):
   - **Windows**: Download `mediamtx_vX.X.X_windows_amd64.zip` (or `.exe`)
   - **Linux/Mac**: Download the appropriate binary for your platform
   - Extract the archive to any directory (e.g., `C:\tools\mediamtx\` or `~/tools/mediamtx/`)
2. Run MediaMTX:
   ```bash
   # Windows
   mediamtx.exe
   
   # Linux/Mac
   ./mediamtx
   ```
   MediaMTX will start and listen on `rtsp://localhost:8554` by default.
3. Stream a video file to MediaMTX using FFmpeg:
   ```bash
   ffmpeg -re -stream_loop -1 -i your_video.mp4 -c copy -f rtsp rtsp://localhost:8554/live
   ```
4. Use the RTSP URL in your config:
   ```yaml
   rtsp_url: rtsp://localhost:8554/live
   ```

#### Option 2: FFmpeg RTSP server
1. Stream a video file directly with FFmpeg:
   ```bash
   ffmpeg -re -stream_loop -1 -i your_video.mp4 -c copy -f rtsp rtsp://localhost:8554/live
   ```
2. Use the RTSP URL in your config:
   ```yaml
   rtsp_url: rtsp://localhost:8554/live
   ```

**Note:** The default RTSP port is 8554. Make sure no firewall is blocking this port.

#### Viewing the RTSP stream

Once your video is streaming to MediaMTX, you can view it using:

- **VLC Media Player** (recommended):
  1. Download from [https://www.videolan.org/vlc/](https://www.videolan.org/vlc/)
  2. Open VLC → Media → Open Network Stream (or press `Ctrl+N`)
  3. Enter: `rtsp://localhost:8554/live`
  4. Click Play

- **FFplay** (comes with FFmpeg):
  ```bash
  ffplay rtsp://localhost:8554/live
  ```

- **Other players**: PotPlayer, MPC-HC, or any RTSP-compatible media player

## ML Models

The service supports two model types:

### MobileNetV3 Small (default)
- **Type:** Image classifier
- **Training:** Pretrained on ImageNet-1K (1000 classes)
- **Input:** Single video frame (BGR image)
- **Output:** Top-k class predictions with confidence scores
- **Example output:**
  ```json
  [
    {"label": "golden_retriever", "score": 0.85},
    {"label": "Labrador_retriever", "score": 0.10},
    {"label": "dog", "score": 0.03}
  ]
  ```
- **What it recognizes:** 1000 object classes from ImageNet (e.g., "dog", "cat", "car", "person", "bicycle", "bird", "airplane", "groom", "oboe", etc.)
- **Configuration:** Default model, no additional setup required

### Faster R-CNN Person Detector (optional)
- **Type:** Object detector
- **Training:** Pretrained on COCO dataset (80 classes)
- **Input:** Single video frame
- **Output:** Binary classification: "person" / "no_person"
- **Example output:**
  ```json
  [
    {"label": "person", "score": 0.92},
    {"label": "no_person", "score": 0.0}
  ]
  ```
- **Use case:** Simple presence detection (is there a person in the frame?)
- **Configuration:** Set `APP_MODEL_NAME=person_detector`

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
