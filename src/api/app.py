from __future__ import annotations

import io
import json
import logging
import time
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from src.config import load_settings
from src.ingest.rtsp_reader import RTSPFrameReader
from src.metrics import Metrics
from src.model.infer import load_model, predict_bgr, predict_pil


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

app = FastAPI(title="Stream Video ML Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
settings = load_settings()
metrics = Metrics(log_every=settings.metrics_log_every)

model = None
preprocess = None
categories = None
device = None


@app.on_event("startup")
def startup_event() -> None:
    global model, preprocess, categories, device
    model, preprocess, categories, device = load_model(settings)
    logger.info("model_loaded=%s", settings.model_name)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/predict")
async def predict(file: UploadFile = File(...)) -> dict:
    payload = await file.read()
    image = Image.open(io.BytesIO(payload)).convert("RGB")
    start = time.perf_counter()
    results = predict_pil(model, preprocess, categories, device, image, settings.class_topk)
    metrics.record(time.perf_counter() - start)
    return {"predictions": results}


@app.get("/stream")
def stream(
    rtsp_url: Optional[str] = None,
    max_frames: int = 0,
) -> StreamingResponse:
    reader = RTSPFrameReader(
        rtsp_url or settings.rtsp_url,
        target_fps=settings.frame_sample_fps,
        width=settings.frame_width,
        height=settings.frame_height,
    ).start()

    def event_generator():
        count = 0
        try:
            while True:
                frame = reader.read()
                if frame is None:
                    time.sleep(0.1)
                    continue
                start = time.perf_counter()
                preds = predict_bgr(
                    model, preprocess, categories, device, frame, settings.class_topk
                )
                metrics.record(time.perf_counter() - start)
                payload = {
                    "timestamp": time.time(),
                    "predictions": preds,
                }
                yield f"data: {json.dumps(payload)}\n\n"
                count += 1
                if max_frames and count >= max_frames:
                    break
        finally:
            reader.stop()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
