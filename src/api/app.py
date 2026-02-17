from __future__ import annotations

import io
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

import cv2
from src.config import load_settings
from src.inference_capture import InferenceCapture
from src.ingest.rtsp_reader import RTSPFrameReader
from src.metrics import Metrics
from src.model.infer import load_model, predict_bgr, predict_pil


settings = load_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("api")
from contextlib import asynccontextmanager


def _log_request(request_id: str, endpoint: str, method: str, latency_ms: float, **kwargs) -> None:
    """Emit structured JSON log for API requests."""
    log_data = {
        "type": "api_request",
        "request_id": request_id,
        "endpoint": endpoint,
        "method": method,
        "latency_ms": round(latency_ms, 2),
        "model_name": settings.model_name,
        "model_version": settings.model_name,  # Using model_name as version identifier
        "device": settings.device,
    }
    log_data.update(kwargs)
    logger.info(json.dumps(log_data))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global model, preprocess, categories, device, model_kind
    model, preprocess, categories, device, model_kind = load_model(settings)
    logger.info("model_loaded=%s", settings.model_name)
    logger.info(
        "settings_loaded rtsp_url=%s model_name=%s device=%s frame=%sx%s fps=%s camera_name=%s",
        settings.rtsp_url,
        settings.model_name,
        settings.device,
        settings.frame_width,
        settings.frame_height,
        settings.frame_sample_fps,
        settings.camera_name,
    )
    yield


app = FastAPI(title="Stream Video ML Service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
metrics = Metrics(
    log_every=settings.metrics_log_every,
    dimensions={
        "service": "stream-ml-service",
        "model_name": settings.model_name,
        "device": settings.device,
        "camera_name": settings.camera_name,
    },
)
capture = InferenceCapture(
    enabled=settings.capture_inference,
    output_dir=Path(settings.capture_dir),
    every_n=settings.capture_every_n,
    s3_bucket=settings.capture_s3_bucket or None,
    s3_prefix=settings.capture_s3_prefix,
)

model = None
preprocess = None
categories = None
device = None
model_kind = "classifier"


@app.get("/health")
def health(request: Request) -> dict:
    request_id = str(uuid.uuid4())
    start_time = time.perf_counter()
    try:
        result = {"status": "ok"}
        latency_ms = (time.perf_counter() - start_time) * 1000
        _log_request(request_id, "/health", "GET", latency_ms, status_code=200)
        return result
    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        _log_request(request_id, "/health", "GET", latency_ms, status_code=500, error=str(e))
        raise


@app.get("/health/stream")
def health_stream(request: Request, rtsp_url: Optional[str] = None) -> dict:
    """Check if the RTSP stream is accessible and healthy."""
    request_id = str(uuid.uuid4())
    start_time = time.perf_counter()
    url = rtsp_url or settings.rtsp_url
    timeout = 3.0  # seconds
    
    try:
        # Try to open the stream and read one frame
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            return {
                "status": "fail",
                "rtsp_url": url,
                "error": "Failed to open stream",
            }
        
        # Set a timeout for reading
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout * 1000)
        start_time = time.time()
        ok, frame = cap.read()
        elapsed = time.time() - start_time
        cap.release()
        
        latency_ms = (time.perf_counter() - start_time) * 1000
        if ok and frame is not None:
            result = {
                "status": "ok",
                "rtsp_url": url,
                "frame_shape": list(frame.shape) if frame is not None else None,
                "response_time_ms": round(elapsed * 1000, 2),
            }
            _log_request(request_id, "/health/stream", "GET", latency_ms, status_code=200, rtsp_url=url, stream_status="ok")
            return result
        else:
            result = {
                "status": "fail",
                "rtsp_url": url,
                "error": "Failed to read frame from stream",
                "response_time_ms": round(elapsed * 1000, 2),
            }
            _log_request(request_id, "/health/stream", "GET", latency_ms, status_code=200, rtsp_url=url, stream_status="fail", error="Failed to read frame")
            return result
    except Exception as e:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.exception("Stream health check failed")
        result = {
            "status": "fail",
            "rtsp_url": url,
            "error": str(e),
        }
        _log_request(request_id, "/health/stream", "GET", latency_ms, status_code=500, rtsp_url=url, stream_status="fail", error=str(e))
        return result


@app.post("/predict")
async def predict(request: Request, file: UploadFile = File(...)) -> dict:
    request_id = str(uuid.uuid4())
    start_time = time.perf_counter()
    try:
        payload = await file.read()
        image = Image.open(io.BytesIO(payload)).convert("RGB")
        inference_start = time.perf_counter()
        results = predict_pil(
            model,
            preprocess,
            categories,
            device,
            image,
            settings.class_topk,
            model_kind=model_kind,
            person_score_threshold=settings.person_score_threshold,
        )
        inference_latency = time.perf_counter() - inference_start
        metrics.record(inference_latency)
        has_person = None
        if model_kind == "detector":
            has_person = any(
                item.get("label") == "person"
                and item.get("score", 0) >= settings.person_score_threshold
                for item in results
            )
        capture.maybe_capture(
            image_pil=image,
            metadata={
                "event": "predict",
                "request_id": request_id,
                "filename": file.filename,
                "model_name": settings.model_name,
                "device": settings.device,
                "predictions": results,
                "has_person": has_person,
            },
        )
        total_latency_ms = (time.perf_counter() - start_time) * 1000
        inference_latency_ms = inference_latency * 1000
        _log_request(
            request_id,
            "/predict",
            "POST",
            total_latency_ms,
            status_code=200,
            inference_latency_ms=round(inference_latency_ms, 2),
            filename=file.filename,
        )
        return {"predictions": results, "has_person": has_person}
    except Exception as e:
        total_latency_ms = (time.perf_counter() - start_time) * 1000
        _log_request(request_id, "/predict", "POST", total_latency_ms, status_code=500, error=str(e))
        raise


@app.get("/stream")
def stream(
    request: Request,
    rtsp_url: Optional[str] = None,
    max_frames: int = 0,
) -> StreamingResponse:
    request_id = str(uuid.uuid4())
    stream_start_time = time.perf_counter()
    stream_url = rtsp_url or settings.rtsp_url
    
    reader = RTSPFrameReader(
        stream_url,
        target_fps=settings.frame_sample_fps,
        width=settings.frame_width,
        height=settings.frame_height,
        camera_name=settings.camera_name,
        fallback_mp4_path=settings.fallback_mp4_path,
    ).start()
    
    _log_request(request_id, "/stream", "GET", 0, status_code=200, rtsp_url=stream_url, event="stream_started")

    def event_generator():
        count = 0
        try:
            while True:
                frame = reader.read()
                if frame is None:
                    time.sleep(0.1)
                    continue
                inference_start = time.perf_counter()
                preds = predict_bgr(
                    model,
                    preprocess,
                    categories,
                    device,
                    frame,
                    settings.class_topk,
                    model_kind=model_kind,
                    person_score_threshold=settings.person_score_threshold,
                )
                inference_latency = time.perf_counter() - inference_start
                metrics.record(inference_latency)
                has_person = None
                if model_kind == "detector":
                    has_person = any(
                        item.get("label") == "person"
                        and item.get("score", 0) >= settings.person_score_threshold
                        for item in preds
                    )
                payload = {
                    "timestamp": time.time(),
                    "predictions": preds,
                    "has_person": has_person,
                }
                capture.maybe_capture(
                    image_bgr=frame,
                    metadata={
                        "event": "stream",
                        "request_id": request_id,
                        "frame_index": count,
                        "rtsp_url": stream_url,
                        "model_name": settings.model_name,
                        "device": settings.device,
                        "predictions": preds,
                        "has_person": has_person,
                    },
                )
                yield f"data: {json.dumps(payload)}\n\n"
                count += 1
                if max_frames and count >= max_frames:
                    break
        finally:
            reader.stop()
            stream_latency_ms = (time.perf_counter() - stream_start_time) * 1000
            _log_request(request_id, "/stream", "GET", stream_latency_ms, status_code=200, rtsp_url=stream_url, event="stream_ended", frames_processed=count)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
