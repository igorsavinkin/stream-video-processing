from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


logger = logging.getLogger("metrics")


@dataclass
class Metrics:
    log_every: int
    dimensions: dict[str, Any] = field(default_factory=dict)
    frame_count: int = 0
    error_count: int = 0
    total_latency: float = 0.0
    last_log_time: float = field(default_factory=time.time)

    def record(self, latency: float, error: bool = False) -> None:
        self.frame_count += 1
        self.total_latency += latency
        if error:
            self.error_count += 1
        if self.frame_count % self.log_every == 0:
            self._log_snapshot()

    def _log_snapshot(self) -> None:
        now = time.time()
        elapsed = max(now - self.last_log_time, 1e-6)
        avg_latency = self.total_latency / max(self.frame_count, 1)
        fps = self.log_every / elapsed
        payload = {
            "type": "metrics",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "frames": self.frame_count,
            "errors": self.error_count,
            "avg_latency_ms": round(avg_latency * 1000, 2),
            "fps": round(fps, 2),
            "log_every": self.log_every,
        }
        if self.dimensions:
            payload.update(self.dimensions)
        logger.info(json.dumps(payload))
        self.last_log_time = now
