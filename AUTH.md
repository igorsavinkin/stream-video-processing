# Authentication & Rate Limiting

## Overview

The API supports **API key authentication** and **per-endpoint rate limiting** via the `AuthRateLimitMiddleware` in [`src/api/auth.py`](src/api/auth.py).

**Key principle: Auth is disabled by default.** When `api_keys` is empty (the default), all requests pass through without authentication. Rate limiting is always active.

## Request Flow

```
Incoming request
  │
  ├─ api_keys configured?
  │   ├─ No (empty string) → Skip auth → Rate limit check → ✅ OK
  │   └─ Yes (keys set)
  │       ├─ Endpoint exempt? (/health, /health/stream, /docs, /openapi.json, /redoc)
  │       │   └─ Yes → Skip auth → Rate limit check → ✅ OK
  │       └─ No → Check X-API-Key header or api_key query param
  │           ├─ Valid key → Rate limit check → ✅ OK
  │           └─ Missing/invalid → ❌ 401 Unauthorized
  │
  └─ Rate limit check
      ├─ Within limit → ✅ OK (with X-RateLimit-* headers)
      └─ Exceeded → ❌ 429 Too Many Requests (with Retry-After header)
```

## Scenarios

| Scenario | `api_keys` setting | Effect |
|----------|-------------------|--------|
| **Local development** (default) | `""` (empty) | Auth **disabled**, everything works as before. Rate limits active with generous defaults |
| **Local dev with auth** | `"test-key-1"` in config.yaml or `APP_API_KEYS=test-key-1` | Must pass `X-API-Key: test-key-1` header |
| **Cloud (ECS/production)** | `APP_API_KEYS=key1,key2,key3` via env var | All `/predict` and `/stream` requests require a key. `/health` accessible without key (for ALB health checks) |

## What is NOT affected

1. **Local development** — without config changes, everything works as before (auth off)
2. **Health checks** — `/health` and `/health/stream` are always accessible without a key (exempt list)
3. **Swagger UI** — `/docs`, `/openapi.json`, `/redoc` are also in the exempt list
4. **Existing tests** — not affected since auth is disabled by default

## Configuration

### Via config.yaml

```yaml
# Comma-separated API keys; leave empty to disable auth
api_keys: "prod-key-abc-123,prod-key-def-456"

# Rate limits per endpoint (format: "<count>/<second|minute|hour>")
rate_limit_predict: "30/minute"
rate_limit_stream: "10/minute"
rate_limit_default: "60/minute"
```

### Via environment variables

```bash
APP_API_KEYS="prod-key-abc-123,prod-key-def-456"
APP_RATE_LIMIT_PREDICT="30/minute"
APP_RATE_LIMIT_STREAM="10/minute"
APP_RATE_LIMIT_DEFAULT="60/minute"
```

### Via ECS task definition

```json
{
  "environment": [
    { "name": "APP_API_KEYS", "value": "prod-key-abc-123,prod-key-def-456" },
    { "name": "APP_RATE_LIMIT_PREDICT", "value": "30/minute" },
    { "name": "APP_RATE_LIMIT_STREAM", "value": "10/minute" },
    { "name": "APP_RATE_LIMIT_DEFAULT", "value": "60/minute" }
  ]
}
```

## Rate Limits

Rate limiting works **independently of auth** (even when auth is disabled). Default limits:

| Endpoint | Default limit |
|----------|--------------|
| `/predict` | 30 requests/minute |
| `/stream` | 10 requests/minute |
| All others | 60 requests/minute |

Rate limit state is **in-memory per process** (sliding window counter). In a multi-instance deployment, each instance tracks limits independently.

### Response Headers

Every response includes rate limit headers:

```
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 29
```

When rate limit is exceeded (HTTP 429):

```
Retry-After: 60
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 0
```

## Usage Examples

### Without auth (default)

```bash
# Works out of the box
curl http://localhost:8000/predict -F file=@image.png
curl http://localhost:8000/stream
curl http://localhost:8000/health
```

### With auth enabled

```bash
# Via header
curl -H "X-API-Key: my-secret-key" http://localhost:8000/predict -F file=@image.png

# Via query parameter
curl "http://localhost:8000/stream?api_key=my-secret-key"

# Health endpoints — no key needed
curl http://localhost:8000/health
```

## Files

| File | Description |
|------|-------------|
| [`src/api/auth.py`](src/api/auth.py) | `AuthRateLimitMiddleware` implementation |
| [`src/api/app.py`](src/api/app.py) | Middleware registration |
| [`src/config.py`](src/config.py) | Settings: `api_keys`, `rate_limit_*` |
| [`config.example.yaml`](config.example.yaml) | Example configuration |
| [`tests/test_auth.py`](tests/test_auth.py) | 20 tests (auth + rate limiting) |
