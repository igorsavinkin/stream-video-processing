"""Data / prediction drift detection using PSI and KL divergence.

Usage
-----
1. Collect a *reference* distribution from a baseline dataset (e.g. first
   hour of production traffic or a validation set).
2. Periodically compute PSI / KL between the reference and the latest
   *current* window of predictions.
3. If the metric exceeds the configured threshold, emit an alert.

Both metrics operate on **binned probability distributions** so they work
equally well on raw logits, softmax outputs, or embedding norms.
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Deque, Dict, List, Optional, Sequence

import numpy as np

logger = logging.getLogger("monitoring.drift")

# Small constant to avoid log(0) / division-by-zero
_EPS = 1e-10


# ---------------------------------------------------------------------------
# Core statistical functions
# ---------------------------------------------------------------------------


def psi(reference: np.ndarray, current: np.ndarray) -> float:
    """Population Stability Index between two probability distributions.

    Both arrays must be 1-D and sum to ~1 (i.e. they are histograms /
    probability vectors).  A small epsilon is added to avoid log(0).

    Interpretation (rule of thumb):
      * PSI < 0.10  — no significant change
      * 0.10 ≤ PSI < 0.25 — moderate change, investigate
      * PSI ≥ 0.25 — significant change, action required
    """
    ref = np.asarray(reference, dtype=np.float64) + _EPS
    cur = np.asarray(current, dtype=np.float64) + _EPS
    # Normalise to ensure they are proper distributions
    ref = ref / ref.sum()
    cur = cur / cur.sum()
    return float(np.sum((cur - ref) * np.log(cur / ref)))


def kl_divergence(reference: np.ndarray, current: np.ndarray) -> float:
    """KL divergence  D_KL(current || reference).

    Both arrays must be 1-D probability distributions.
    """
    ref = np.asarray(reference, dtype=np.float64) + _EPS
    cur = np.asarray(current, dtype=np.float64) + _EPS
    ref = ref / ref.sum()
    cur = cur / cur.sum()
    return float(np.sum(cur * np.log(cur / ref)))


def histogram_from_scores(
    scores: Sequence[float],
    n_bins: int = 10,
    range_min: float = 0.0,
    range_max: float = 1.0,
) -> np.ndarray:
    """Bin a list of scalar scores into a normalised histogram."""
    counts, _ = np.histogram(scores, bins=n_bins, range=(range_min, range_max))
    total = counts.sum()
    if total == 0:
        return np.ones(n_bins, dtype=np.float64) / n_bins
    return counts.astype(np.float64) / total


# ---------------------------------------------------------------------------
# Alert thresholds
# ---------------------------------------------------------------------------


@dataclass
class DriftThresholds:
    """Configurable thresholds for drift alerts."""

    psi_warning: float = 0.10
    psi_critical: float = 0.25
    kl_warning: float = 0.10
    kl_critical: float = 0.50


@dataclass
class DriftResult:
    """Result of a single drift check."""

    psi_value: float
    kl_value: float
    psi_status: str  # "ok" | "warning" | "critical"
    kl_status: str   # "ok" | "warning" | "critical"
    timestamp: str
    window_size: int
    reference_size: int

    @property
    def is_drifted(self) -> bool:
        return self.psi_status == "critical" or self.kl_status == "critical"

    @property
    def needs_investigation(self) -> bool:
        return self.psi_status in ("warning", "critical") or self.kl_status in ("warning", "critical")

    def to_dict(self) -> dict:
        return {
            "psi": round(self.psi_value, 6),
            "kl": round(self.kl_value, 6),
            "psi_status": self.psi_status,
            "kl_status": self.kl_status,
            "is_drifted": self.is_drifted,
            "needs_investigation": self.needs_investigation,
            "timestamp": self.timestamp,
            "window_size": self.window_size,
            "reference_size": self.reference_size,
        }


def _classify(value: float, warning: float, critical: float) -> str:
    if value >= critical:
        return "critical"
    if value >= warning:
        return "warning"
    return "ok"


# ---------------------------------------------------------------------------
# DriftMonitor — stateful monitor
# ---------------------------------------------------------------------------


@dataclass
class DriftMonitor:
    """Sliding-window drift monitor for model predictions.

    Parameters
    ----------
    reference_scores : list[float]
        Baseline score distribution (e.g. top-1 confidence from validation).
    window_size : int
        Number of recent scores to keep for the *current* distribution.
    n_bins : int
        Number of histogram bins.
    thresholds : DriftThresholds
        Alert thresholds.
    on_alert : callable, optional
        Callback ``fn(DriftResult)`` invoked when drift is detected.
    check_every : int
        Run the drift check every N recorded scores.
    """

    reference_scores: List[float]
    window_size: int = 500
    n_bins: int = 10
    thresholds: DriftThresholds = field(default_factory=DriftThresholds)
    on_alert: Optional[Callable[["DriftResult"], None]] = None
    check_every: int = 100

    # internal state
    _current_scores: Deque[float] = field(default_factory=deque, init=False)
    _record_count: int = field(default=0, init=False)
    _reference_hist: Optional[np.ndarray] = field(default=None, init=False)
    _last_result: Optional[DriftResult] = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._current_scores = deque(maxlen=self.window_size)
        self._reference_hist = histogram_from_scores(
            self.reference_scores, n_bins=self.n_bins
        )

    def record(self, score: float) -> Optional[DriftResult]:
        """Record a new prediction score and optionally run a drift check.

        Returns a :class:`DriftResult` when a check is performed, else ``None``.
        """
        self._current_scores.append(score)
        self._record_count += 1
        if self._record_count % self.check_every == 0 and len(self._current_scores) >= self.n_bins:
            return self.check()
        return None

    def record_batch(self, scores: Sequence[float]) -> Optional[DriftResult]:
        """Record a batch of scores. Returns the last check result if any."""
        result = None
        for s in scores:
            r = self.record(s)
            if r is not None:
                result = r
        return result

    def check(self) -> DriftResult:
        """Force a drift check with the current window."""
        current_hist = histogram_from_scores(
            list(self._current_scores), n_bins=self.n_bins
        )
        psi_val = psi(self._reference_hist, current_hist)
        kl_val = kl_divergence(self._reference_hist, current_hist)

        result = DriftResult(
            psi_value=psi_val,
            kl_value=kl_val,
            psi_status=_classify(psi_val, self.thresholds.psi_warning, self.thresholds.psi_critical),
            kl_status=_classify(kl_val, self.thresholds.kl_warning, self.thresholds.kl_critical),
            timestamp=datetime.now(timezone.utc).isoformat(),
            window_size=len(self._current_scores),
            reference_size=len(self.reference_scores),
        )
        self._last_result = result

        # Structured log
        log_payload = {
            "type": "drift_check",
            **result.to_dict(),
        }
        if result.is_drifted:
            logger.warning(json.dumps(log_payload))
        elif result.needs_investigation:
            logger.info(json.dumps(log_payload))
        else:
            logger.debug(json.dumps(log_payload))

        # Alert callback
        if result.needs_investigation and self.on_alert:
            try:
                self.on_alert(result)
            except Exception:
                logger.exception("Drift alert callback failed")

        return result

    @property
    def last_result(self) -> Optional[DriftResult]:
        return self._last_result
