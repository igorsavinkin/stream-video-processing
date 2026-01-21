import json
import os
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.ingest.rtsp_reader import RTSPFrameReader

TEST_RTSP_URL = os.getenv("APP_TEST_RTSP_URL")


@pytest.mark.integration
@pytest.mark.skipif(
    not TEST_RTSP_URL,
    reason="APP_TEST_RTSP_URL not set; skipping RTSP integration test",
)
def test_rtsp_reader_reads_frames():
    reader = RTSPFrameReader(
        TEST_RTSP_URL,
        target_fps=2,
        width=320,
        height=240,
    ).start()
    try:
        deadline = time.time() + 5
        frame = None
        while time.time() < deadline and frame is None:
            frame = reader.read()
            time.sleep(0.1)
        assert frame is not None
        assert isinstance(frame, np.ndarray)
        assert frame.ndim == 3
        assert frame.shape[2] == 3
    finally:
        reader.stop()


@pytest.mark.integration
@pytest.mark.skipif(
    not TEST_RTSP_URL,
    reason="APP_TEST_RTSP_URL not set; skipping SSE integration test",
)
def test_stream_endpoint_with_live_source(monkeypatch):
    import src.api.app as app_module

    def _dummy_load_model(_settings):
        return object(), object(), ["class_a"], "cpu", "classifier"

    def _dummy_predict_bgr(*_args, **_kwargs):
        return [{"label": "class_a", "score": 0.5}]

    monkeypatch.setattr(app_module, "load_model", _dummy_load_model)
    monkeypatch.setattr(app_module, "predict_bgr", _dummy_predict_bgr)

    with TestClient(app_module.app) as client:
        events = []
        with client.stream(
            "GET", f"/stream?max_frames=1&rtsp_url={TEST_RTSP_URL}"
        ) as response:
            for line in response.iter_lines():
                if not line:
                    continue
                text = line.decode("utf-8") if isinstance(line, bytes) else line
                if text.startswith("data: "):
                    events.append(json.loads(text.replace("data: ", "", 1)))
                    break

    assert len(events) == 1
    payload = events[0]
    assert "timestamp" in payload
    assert "predictions" in payload
    assert "has_person" in payload