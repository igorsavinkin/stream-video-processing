import io
import json

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image


def _dummy_load_model(_settings):
    return object(), object(), ["class_a"], "cpu", "classifier"


def _dummy_predict_pil(
    _model,
    _preprocess,
    _categories,
    _device,
    _image,
    _topk,
    model_kind="classifier",
    person_score_threshold=0.6,
):
    return [{"label": "class_a", "score": 0.99}]


def _make_png_bytes() -> bytes:
    image = Image.new("RGB", (8, 8), color=(255, 0, 0))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_health_endpoint(monkeypatch):
    import src.api.app as app_module

    monkeypatch.setattr(app_module, "load_model", _dummy_load_model)
    with TestClient(app_module.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_predict_endpoint(monkeypatch):
    import src.api.app as app_module

    monkeypatch.setattr(app_module, "load_model", _dummy_load_model)
    monkeypatch.setattr(app_module, "predict_pil", _dummy_predict_pil)
    with TestClient(app_module.app) as client:
        files = {"file": ("sample.png", _make_png_bytes(), "image/png")}
        response = client.post("/predict", files=files)
    assert response.status_code == 200
    payload = response.json()
    assert payload["has_person"] is None
    assert payload["predictions"] == [{"label": "class_a", "score": 0.99}]


def test_stream_endpoint_sse(monkeypatch):
    import src.api.app as app_module

    class DummyReader:
        def __init__(self, frames):
            self._frames = frames
            self._idx = 0

        def start(self):
            return self

        def read(self):
            if self._idx >= len(self._frames):
                return None
            frame = self._frames[self._idx]
            self._idx += 1
            return frame

        def stop(self):
            return None

    def _dummy_rtsp_reader(*_args, **_kwargs):
        frames = [
            np.zeros((4, 4, 3), dtype=np.uint8),
            np.ones((4, 4, 3), dtype=np.uint8) * 127,
        ]
        return DummyReader(frames)

    def _dummy_predict_bgr(*_args, **_kwargs):
        return [{"label": "class_a", "score": 0.5}]

    monkeypatch.setattr(app_module, "load_model", _dummy_load_model)
    monkeypatch.setattr(app_module, "RTSPFrameReader", _dummy_rtsp_reader)
    monkeypatch.setattr(app_module, "predict_bgr", _dummy_predict_bgr)

    with TestClient(app_module.app) as client:
        response = client.get("/stream?max_frames=2", stream=True)
        events = []
        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8")
            if text.startswith("data: "):
                events.append(json.loads(text.replace("data: ", "", 1)))
            if len(events) >= 2:
                break

    assert len(events) == 2
    assert all("predictions" in event for event in events)
