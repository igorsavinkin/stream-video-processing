# Testing Guide

This document describes the testing strategy for the app, including test kinds,
types, and how to run them locally.

## Kinds of tests
- Unit tests: fast, isolated tests for pure functions and small modules.
- API tests: FastAPI endpoint tests using the in-process TestClient.
- Integration tests: tests that touch multiple modules or external services.
- Stream tests: RTSP/SSE behavior validation (often needs a live or mock stream).
- Manual tests: quick smoke checks via the running API and UI tools.

## Types of tests in this repo
- Preprocess unit tests: `tests/test_transforms.py`
  - Color conversion and round-trip checks
  - Resize and file-write behavior
- API tests: `tests/test_api.py`
  - `/health` and `/predict` using stubbed model inference
- Integration tests: `tests/test_stream_integration.py`
  - RTSP reader smoke test against a live source
  - SSE `/stream` test using a live source with stubbed inference

## Running tests
Install dev dependencies and run the full suite:
```bash
pip install -r requirements-dev.txt
pytest
```

Run a single file or test:
```bash
pytest tests/test_api.py
pytest tests/test_transforms.py::test_resize_frame_shape
```

Optional PYTHONPATH workaround (use if you don't want editable installs):
```bash
# PowerShell
$env:PYTHONPATH = (Get-Location).Path
pytest
```

## Integration/stream tests
These tests require an RTSP source and are skipped unless you provide a URL.

Run with a real stream:
```bash
# PowerShell
$env:APP_TEST_RTSP_URL = "rtsp://your-stream"
pytest -m integration
```

## When to add each test type
- Add unit tests when you change utility functions (preprocess, metrics, config).
- Add API tests when you change request/response payloads or error handling.
- Add integration/stream tests when RTSP ingestion, SSE, or model loading changes.

## Manual test ideas
- Start the API and hit `/health` and `/predict` from `http://localhost:8000/docs`.
- Use `tools/sse_viewer.html` to verify the `/stream` SSE output.
- Run `python -m src.ingest.capture --output data/raw --max-frames 10` to verify
  ingestion and file writes.

## Notes
- API tests stub model loading to avoid heavy model downloads.
- Stream integration tests require a working RTSP or local video source.
