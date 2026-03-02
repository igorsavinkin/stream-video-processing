"""Tests for API key authentication and rate limiting middleware."""

import time

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.api.auth import AuthRateLimitMiddleware, parse_rate_limit


# ---------------------------------------------------------------------------
# parse_rate_limit
# ---------------------------------------------------------------------------


def test_parse_rate_limit_minute():
    rl = parse_rate_limit("30/minute")
    assert rl.max_requests == 30
    assert rl.window_seconds == 60


def test_parse_rate_limit_second():
    rl = parse_rate_limit("5/second")
    assert rl.max_requests == 5
    assert rl.window_seconds == 1


def test_parse_rate_limit_hour():
    rl = parse_rate_limit("1000/hour")
    assert rl.max_requests == 1000
    assert rl.window_seconds == 3600


def test_parse_rate_limit_invalid():
    with pytest.raises(ValueError):
        parse_rate_limit("bad")
    with pytest.raises(ValueError):
        parse_rate_limit("10/year")


# ---------------------------------------------------------------------------
# Helper: minimal FastAPI app with middleware
# ---------------------------------------------------------------------------


def _make_app(
    api_keys=None,
    rate_limit_predict="30/minute",
    rate_limit_stream="10/minute",
    rate_limit_default="60/minute",
) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        AuthRateLimitMiddleware,
        api_keys=api_keys,
        rate_limit_predict=rate_limit_predict,
        rate_limit_stream=rate_limit_stream,
        rate_limit_default=rate_limit_default,
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/health/stream")
    def health_stream():
        return {"status": "ok"}

    @app.post("/predict")
    def predict():
        return {"predictions": []}

    @app.get("/stream")
    def stream():
        return {"data": "ok"}

    @app.get("/other")
    def other():
        return {"ok": True}

    return app


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


class TestAuth:
    def test_no_auth_when_keys_empty(self):
        """When api_keys is None, all requests pass without key."""
        client = TestClient(_make_app(api_keys=None))
        resp = client.get("/other")
        assert resp.status_code == 200

    def test_auth_rejects_missing_key(self):
        """When api_keys is set, requests without key get 401."""
        client = TestClient(_make_app(api_keys={"secret-key-1"}))
        resp = client.get("/other")
        assert resp.status_code == 401
        assert "API key" in resp.json()["detail"]

    def test_auth_rejects_wrong_key(self):
        client = TestClient(_make_app(api_keys={"secret-key-1"}))
        resp = client.get("/other", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_auth_accepts_valid_header_key(self):
        client = TestClient(_make_app(api_keys={"secret-key-1"}))
        resp = client.get("/other", headers={"X-API-Key": "secret-key-1"})
        assert resp.status_code == 200

    def test_auth_accepts_valid_query_key(self):
        client = TestClient(_make_app(api_keys={"secret-key-1"}))
        resp = client.get("/other?api_key=secret-key-1")
        assert resp.status_code == 200

    def test_health_exempt_from_auth(self):
        """Health endpoints should be accessible without API key."""
        client = TestClient(_make_app(api_keys={"secret-key-1"}))
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_stream_exempt_from_auth(self):
        client = TestClient(_make_app(api_keys={"secret-key-1"}))
        resp = client.get("/health/stream")
        assert resp.status_code == 200

    def test_predict_requires_auth(self):
        client = TestClient(_make_app(api_keys={"key-abc"}))
        resp = client.post("/predict")
        assert resp.status_code == 401

    def test_predict_with_valid_key(self):
        client = TestClient(_make_app(api_keys={"key-abc"}))
        resp = client.post("/predict", headers={"X-API-Key": "key-abc"})
        assert resp.status_code == 200

    def test_multiple_api_keys(self):
        client = TestClient(_make_app(api_keys={"key-1", "key-2"}))
        assert client.get("/other", headers={"X-API-Key": "key-1"}).status_code == 200
        assert client.get("/other", headers={"X-API-Key": "key-2"}).status_code == 200
        assert client.get("/other", headers={"X-API-Key": "key-3"}).status_code == 401


# ---------------------------------------------------------------------------
# Rate-limit tests
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_rate_limit_headers_present(self):
        client = TestClient(_make_app(rate_limit_default="100/minute"))
        resp = client.get("/other")
        assert "X-RateLimit-Limit" in resp.headers
        assert "X-RateLimit-Remaining" in resp.headers

    def test_rate_limit_blocks_after_exceeded(self):
        """After exceeding the limit, requests get 429."""
        client = TestClient(_make_app(rate_limit_default="3/minute"))
        for _ in range(3):
            resp = client.get("/other")
            assert resp.status_code == 200
        # 4th request should be blocked
        resp = client.get("/other")
        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["detail"]
        assert "Retry-After" in resp.headers

    def test_predict_has_own_limit(self):
        """Predict endpoint uses its own rate limit."""
        client = TestClient(
            _make_app(rate_limit_predict="2/minute", rate_limit_default="100/minute")
        )
        for _ in range(2):
            resp = client.post("/predict")
            assert resp.status_code == 200
        resp = client.post("/predict")
        assert resp.status_code == 429

    def test_stream_has_own_limit(self):
        """Stream endpoint uses its own rate limit."""
        client = TestClient(
            _make_app(rate_limit_stream="2/minute", rate_limit_default="100/minute")
        )
        for _ in range(2):
            resp = client.get("/stream")
            assert resp.status_code == 200
        resp = client.get("/stream")
        assert resp.status_code == 429

    def test_different_endpoints_independent_limits(self):
        """Rate limits for different endpoints are independent."""
        client = TestClient(
            _make_app(
                rate_limit_predict="2/minute",
                rate_limit_stream="2/minute",
                rate_limit_default="2/minute",
            )
        )
        # Exhaust /predict limit
        for _ in range(2):
            client.post("/predict")
        assert client.post("/predict").status_code == 429
        # /stream should still work
        assert client.get("/stream").status_code == 200

    def test_health_still_rate_limited(self):
        """Health endpoints are auth-exempt but still rate-limited."""
        client = TestClient(_make_app(rate_limit_default="2/minute"))
        for _ in range(2):
            resp = client.get("/health")
            assert resp.status_code == 200
        resp = client.get("/health")
        assert resp.status_code == 429
