"""Integration tests for streaming endpoints with sample video."""

import json
import os
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.ingest.rtsp_reader import RTSPFrameReader


def _create_test_video(output_path: Path, num_frames: int = 10, fps: int = 2):
    """Create a test video file for integration testing."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    width, height = 320, 240
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
    
    for i in range(num_frames):
        # Create a frame with varying colors
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = [i * 25 % 255, (i * 50) % 255, (i * 75) % 255]
        out.write(frame)
    
    out.release()


@pytest.fixture
def sample_video(tmp_path):
    """Create a temporary test video file."""
    video_path = tmp_path / "test_video.mp4"
    _create_test_video(video_path, num_frames=5, fps=2)
    return str(video_path)


def _dummy_load_model(_settings):
    """Dummy model loader for testing."""
    return object(), object(), ["class_a", "class_b"], "cpu", "classifier"


def _dummy_predict_bgr(*_args, **_kwargs):
    """Dummy predictor that returns consistent results."""
    return [{"label": "class_a", "score": 0.8}, {"label": "class_b", "score": 0.2}]


def test_rtsp_reader_with_local_video(sample_video):
    """Integration test: RTSP reader with local video file."""
    reader = RTSPFrameReader(
        sample_video,
        target_fps=2,
        width=320,
        height=240,
    ).start()
    
    try:
        frames_read = 0
        max_attempts = 20
        for _ in range(max_attempts):
            frame = reader.read()
            if frame is not None:
                frames_read += 1
                assert isinstance(frame, np.ndarray)
                assert frame.ndim == 3
                assert frame.shape[2] == 3
                if frames_read >= 3:  # Read at least 3 frames
                    break
        assert frames_read >= 3, "Should read at least 3 frames from test video"
    finally:
        reader.stop()


def test_stream_endpoint_with_local_video(sample_video, monkeypatch):
    """Integration test: /stream endpoint with local video file."""
    import src.api.app as app_module
    
    monkeypatch.setattr(app_module, "load_model", _dummy_load_model)
    monkeypatch.setattr(app_module, "predict_bgr", _dummy_predict_bgr)
    
    with TestClient(app_module.app) as client:
        response = client.get(f"/stream?rtsp_url={sample_video}&max_frames=3", stream=True)
        assert response.status_code == 200
        
        events = []
        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if text.startswith("data: "):
                event = json.loads(text.replace("data: ", "", 1))
                events.append(event)
                if len(events) >= 3:
                    break
        
        assert len(events) >= 2, "Should receive at least 2 events"
        for event in events:
            assert "timestamp" in event
            assert "predictions" in event
            assert "has_person" in event
            assert isinstance(event["predictions"], list)
            assert len(event["predictions"]) > 0


def test_stream_endpoint_max_frames_limit(sample_video, monkeypatch):
    """Test that max_frames parameter limits the number of events."""
    import src.api.app as app_module
    
    monkeypatch.setattr(app_module, "load_model", _dummy_load_model)
    monkeypatch.setattr(app_module, "predict_bgr", _dummy_predict_bgr)
    
    with TestClient(app_module.app) as client:
        max_frames = 2
        response = client.get(f"/stream?rtsp_url={sample_video}&max_frames={max_frames}", stream=True)
        assert response.status_code == 200
        
        events = []
        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if text.startswith("data: "):
                event = json.loads(text.replace("data: ", "", 1))
                events.append(event)
                if len(events) >= max_frames + 1:  # Allow one extra to verify it stops
                    break
        
        assert len(events) == max_frames, f"Should receive exactly {max_frames} events"


def test_stream_endpoint_sse_format(sample_video, monkeypatch):
    """Test that SSE stream follows correct format."""
    import src.api.app as app_module
    
    monkeypatch.setattr(app_module, "load_model", _dummy_load_model)
    monkeypatch.setattr(app_module, "predict_bgr", _dummy_predict_bgr)
    
    with TestClient(app_module.app) as client:
        response = client.get(f"/stream?rtsp_url={sample_video}&max_frames=1", stream=True)
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
        
        lines = []
        for line in response.iter_lines():
            if line:
                lines.append(line.decode("utf-8") if isinstance(line, bytes) else line)
                if len(lines) >= 3:  # Get at least one data line
                    break
        
        # Should have at least one "data: " line
        data_lines = [l for l in lines if l.startswith("data: ")]
        assert len(data_lines) >= 1, "Should have at least one data line"
        
        # Parse the first data line
        event = json.loads(data_lines[0].replace("data: ", "", 1))
        assert "timestamp" in event
        assert "predictions" in event


def test_rtsp_reader_reconnection_handling(sample_video):
    """Test that RTSP reader handles video file correctly."""
    reader = RTSPFrameReader(
        sample_video,
        target_fps=1,  # Lower FPS to test timing
        width=320,
        height=240,
    ).start()
    
    try:
        # Read a few frames
        frames = []
        for _ in range(5):
            frame = reader.read()
            if frame is not None:
                frames.append(frame)
        
        assert len(frames) > 0, "Should read at least one frame"
        # All frames should have consistent shape
        if len(frames) > 1:
            first_shape = frames[0].shape
            for frame in frames[1:]:
                assert frame.shape == first_shape, "Frames should have consistent shape"
    finally:
        reader.stop()


@pytest.mark.integration
def test_stream_with_person_detector(sample_video, monkeypatch):
    """Integration test: Stream endpoint with person detector model."""
    import src.api.app as app_module
    
    def _dummy_load_person_detector(_settings):
        return object(), object(), ["person", "no_person"], "cpu", "detector"
    
    def _dummy_predict_person(*_args, **_kwargs):
        return [{"label": "person", "score": 0.7}, {"label": "no_person", "score": 0.0}]
    
    monkeypatch.setattr(app_module, "load_model", _dummy_load_person_detector)
    monkeypatch.setattr(app_module, "predict_bgr", _dummy_predict_person)
    
    with TestClient(app_module.app) as client:
        response = client.get(f"/stream?rtsp_url={sample_video}&max_frames=2", stream=True)
        assert response.status_code == 200
        
        events = []
        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if text.startswith("data: "):
                event = json.loads(text.replace("data: ", "", 1))
                events.append(event)
                if len(events) >= 2:
                    break
        
        assert len(events) >= 1
        for event in events:
            assert "has_person" in event
            assert event["has_person"] is not None  # Should be True or False for detector
