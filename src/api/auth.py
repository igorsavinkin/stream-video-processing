"""API key authentication and per-endpoint rate limiting middleware.

Auth:
  - When ``api_keys`` setting is non-empty, every request must carry a valid
    key via ``X-API-Key`` header or ``api_key`` query parameter.
  - ``/health`` is always exempt from auth so load-balancers can probe.

Rate limiting:
  - Uses a simple in-memory sliding-window counter (no external store).
  - Limits are configured per-endpoint group via settings:
    ``rate_limit_predict``, ``rate_limit_stream``, ``rate_limit_default``.
  - Format: ``"<count>/<period>"`` where period is ``second|minute|hour``.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("api.auth")

# ---------------------------------------------------------------------------
# Rate-limit helpers
# ---------------------------------------------------------------------------

_PERIOD_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
}


@dataclass
class _RateLimit:
    max_requests: int
    window_seconds: float


def parse_rate_limit(spec: str) -> _RateLimit:
    """Parse ``'30/minute'`` into a :class:`_RateLimit`."""
    parts = spec.strip().split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid rate-limit spec: {spec!r}")
    count = int(parts[0])
    period = parts[1].lower()
    if period not in _PERIOD_SECONDS:
        raise ValueError(f"Unknown period {period!r} in rate-limit spec")
    return _RateLimit(max_requests=count, window_seconds=_PERIOD_SECONDS[period])


@dataclass
class _SlidingWindowCounter:
    """Per-key sliding-window rate limiter (in-memory)."""

    limit: _RateLimit
    # key -> list of timestamps
    _hits: Dict[str, List[float]] = field(default_factory=lambda: defaultdict(list))

    def is_allowed(self, key: str) -> Tuple[bool, int]:
        """Return ``(allowed, remaining)``."""
        now = time.monotonic()
        cutoff = now - self.limit.window_seconds
        # Prune old entries
        self._hits[key] = [t for t in self._hits[key] if t > cutoff]
        current = len(self._hits[key])
        if current >= self.limit.max_requests:
            return False, 0
        self._hits[key].append(now)
        return True, self.limit.max_requests - current - 1


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

# Endpoints exempt from authentication (health probes)
_AUTH_EXEMPT: Set[str] = {"/health", "/health/stream", "/docs", "/openapi.json", "/redoc"}


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    """Combined API-key auth + per-endpoint rate-limiting middleware."""

    def __init__(
        self,
        app: FastAPI,
        *,
        api_keys: Optional[Set[str]] = None,
        rate_limit_predict: str = "30/minute",
        rate_limit_stream: str = "10/minute",
        rate_limit_default: str = "60/minute",
    ) -> None:
        super().__init__(app)
        self.api_keys: Optional[Set[str]] = api_keys  # None = auth disabled
        self._limiters: Dict[str, _SlidingWindowCounter] = {
            "/predict": _SlidingWindowCounter(limit=parse_rate_limit(rate_limit_predict)),
            "/stream": _SlidingWindowCounter(limit=parse_rate_limit(rate_limit_stream)),
            "_default": _SlidingWindowCounter(limit=parse_rate_limit(rate_limit_default)),
        }

    # ------------------------------------------------------------------
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path.rstrip("/") or "/"

        # --- Auth ---
        if self.api_keys and path not in _AUTH_EXEMPT:
            key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
            if not key or key not in self.api_keys:
                logger.warning("auth_rejected path=%s remote=%s", path, request.client.host if request.client else "?")
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key"},
                )

        # --- Rate limiting ---
        client_ip = request.client.host if request.client else "unknown"
        limiter = self._limiters.get(path, self._limiters["_default"])
        allowed, remaining = limiter.is_allowed(client_ip)
        if not allowed:
            logger.warning("rate_limited path=%s remote=%s", path, client_ip)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={
                    "Retry-After": str(int(limiter.limit.window_seconds)),
                    "X-RateLimit-Limit": str(limiter.limit.max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limiter.limit.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
