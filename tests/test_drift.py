"""Tests for drift monitoring (PSI, KL divergence, DriftMonitor)."""

import numpy as np
import pytest

from src.monitoring.drift import (
    DriftMonitor,
    DriftResult,
    DriftThresholds,
    histogram_from_scores,
    kl_divergence,
    psi,
)


# ---------------------------------------------------------------------------
# PSI
# ---------------------------------------------------------------------------


class TestPSI:
    def test_identical_distributions(self):
        dist = np.array([0.2, 0.3, 0.5])
        assert psi(dist, dist) == pytest.approx(0.0, abs=1e-6)

    def test_similar_distributions(self):
        ref = np.array([0.2, 0.3, 0.5])
        cur = np.array([0.21, 0.29, 0.50])
        result = psi(ref, cur)
        assert result < 0.01  # very small drift

    def test_different_distributions(self):
        ref = np.array([0.5, 0.3, 0.2])
        cur = np.array([0.1, 0.1, 0.8])
        result = psi(ref, cur)
        assert result > 0.25  # significant drift

    def test_psi_non_negative(self):
        rng = np.random.default_rng(42)
        for _ in range(20):
            ref = rng.dirichlet(np.ones(5))
            cur = rng.dirichlet(np.ones(5))
            assert psi(ref, cur) >= 0.0

    def test_psi_handles_zeros(self):
        """PSI should handle zero bins gracefully (epsilon added)."""
        ref = np.array([0.0, 1.0, 0.0])
        cur = np.array([0.5, 0.0, 0.5])
        result = psi(ref, cur)
        assert np.isfinite(result)
        assert result > 0


# ---------------------------------------------------------------------------
# KL divergence
# ---------------------------------------------------------------------------


class TestKLDivergence:
    def test_identical_distributions(self):
        dist = np.array([0.25, 0.25, 0.25, 0.25])
        assert kl_divergence(dist, dist) == pytest.approx(0.0, abs=1e-6)

    def test_kl_non_negative(self):
        rng = np.random.default_rng(42)
        for _ in range(20):
            ref = rng.dirichlet(np.ones(5))
            cur = rng.dirichlet(np.ones(5))
            assert kl_divergence(ref, cur) >= -1e-10  # numerically >= 0

    def test_kl_asymmetric(self):
        ref = np.array([0.7, 0.2, 0.1])
        cur = np.array([0.1, 0.3, 0.6])
        kl_forward = kl_divergence(ref, cur)
        kl_backward = kl_divergence(cur, ref)
        # KL is asymmetric in general
        assert kl_forward != pytest.approx(kl_backward, abs=0.01)

    def test_kl_handles_zeros(self):
        ref = np.array([0.0, 1.0])
        cur = np.array([1.0, 0.0])
        result = kl_divergence(ref, cur)
        assert np.isfinite(result)


# ---------------------------------------------------------------------------
# histogram_from_scores
# ---------------------------------------------------------------------------


class TestHistogram:
    def test_uniform_scores(self):
        scores = list(np.linspace(0.0, 1.0, 100))
        hist = histogram_from_scores(scores, n_bins=10)
        assert hist.shape == (10,)
        assert hist.sum() == pytest.approx(1.0, abs=1e-6)

    def test_empty_scores(self):
        hist = histogram_from_scores([], n_bins=5)
        assert hist.shape == (5,)
        assert hist.sum() == pytest.approx(1.0, abs=1e-6)  # uniform fallback

    def test_single_score(self):
        hist = histogram_from_scores([0.5], n_bins=10)
        assert hist.sum() == pytest.approx(1.0, abs=1e-6)
        assert hist[5] > 0  # bin containing 0.5


# ---------------------------------------------------------------------------
# DriftThresholds
# ---------------------------------------------------------------------------


class TestDriftThresholds:
    def test_defaults(self):
        t = DriftThresholds()
        assert t.psi_warning == 0.10
        assert t.psi_critical == 0.25
        assert t.kl_warning == 0.10
        assert t.kl_critical == 0.50

    def test_custom(self):
        t = DriftThresholds(psi_warning=0.05, psi_critical=0.15)
        assert t.psi_warning == 0.05
        assert t.psi_critical == 0.15


# ---------------------------------------------------------------------------
# DriftResult
# ---------------------------------------------------------------------------


class TestDriftResult:
    def test_ok_result(self):
        r = DriftResult(
            psi_value=0.01, kl_value=0.02,
            psi_status="ok", kl_status="ok",
            timestamp="2026-01-01T00:00:00Z",
            window_size=100, reference_size=500,
        )
        assert not r.is_drifted
        assert not r.needs_investigation

    def test_warning_result(self):
        r = DriftResult(
            psi_value=0.15, kl_value=0.02,
            psi_status="warning", kl_status="ok",
            timestamp="2026-01-01T00:00:00Z",
            window_size=100, reference_size=500,
        )
        assert not r.is_drifted
        assert r.needs_investigation

    def test_critical_result(self):
        r = DriftResult(
            psi_value=0.30, kl_value=0.60,
            psi_status="critical", kl_status="critical",
            timestamp="2026-01-01T00:00:00Z",
            window_size=100, reference_size=500,
        )
        assert r.is_drifted
        assert r.needs_investigation

    def test_to_dict(self):
        r = DriftResult(
            psi_value=0.123456789, kl_value=0.987654321,
            psi_status="warning", kl_status="critical",
            timestamp="2026-01-01T00:00:00Z",
            window_size=100, reference_size=500,
        )
        d = r.to_dict()
        assert d["psi"] == 0.123457  # rounded to 6 decimals
        assert d["kl"] == 0.987654
        assert d["is_drifted"] is True
        assert d["needs_investigation"] is True


# ---------------------------------------------------------------------------
# DriftMonitor
# ---------------------------------------------------------------------------


class TestDriftMonitor:
    def _make_monitor(self, **kwargs):
        rng = np.random.default_rng(42)
        ref_scores = rng.uniform(0.3, 0.9, size=200).tolist()
        defaults = dict(
            reference_scores=ref_scores,
            window_size=100,
            n_bins=10,
            check_every=50,
        )
        defaults.update(kwargs)
        return DriftMonitor(**defaults)

    def test_no_check_before_threshold(self):
        mon = self._make_monitor(check_every=100)
        rng = np.random.default_rng(0)
        for _ in range(99):
            result = mon.record(rng.uniform(0.3, 0.9))
            assert result is None

    def test_check_triggers_at_interval(self):
        mon = self._make_monitor(check_every=50)
        rng = np.random.default_rng(0)
        results = []
        for _ in range(100):
            r = mon.record(rng.uniform(0.3, 0.9))
            if r is not None:
                results.append(r)
        assert len(results) == 2  # at 50 and 100

    def test_similar_distribution_ok(self):
        # Use a large reference and current window from the same distribution
        rng = np.random.default_rng(42)
        ref_scores = rng.uniform(0.3, 0.9, size=1000).tolist()
        mon = DriftMonitor(
            reference_scores=ref_scores,
            window_size=500,
            n_bins=10,
            check_every=50,
            thresholds=DriftThresholds(),
        )
        rng2 = np.random.default_rng(99)
        for _ in range(500):
            mon.record(rng2.uniform(0.3, 0.9))
        result = mon.check()
        assert result.psi_status == "ok"
        assert result.kl_status == "ok"
        assert not result.is_drifted

    def test_drifted_distribution_detected(self):
        mon = self._make_monitor(
            check_every=50,
            thresholds=DriftThresholds(psi_warning=0.05, psi_critical=0.15),
        )
        # Feed very different distribution (all near 0)
        for _ in range(100):
            mon.record(np.random.uniform(0.0, 0.05))
        result = mon.check()
        assert result.psi_value > 0.15
        assert result.psi_status == "critical"
        assert result.is_drifted

    def test_record_batch(self):
        mon = self._make_monitor(check_every=50)
        rng = np.random.default_rng(42)
        scores = rng.uniform(0.3, 0.9, size=100).tolist()
        result = mon.record_batch(scores)
        assert result is not None
        assert isinstance(result, DriftResult)

    def test_on_alert_callback(self):
        alerts = []
        mon = self._make_monitor(
            check_every=50,
            thresholds=DriftThresholds(psi_warning=0.01, psi_critical=0.02),
            on_alert=lambda r: alerts.append(r),
        )
        # Feed slightly different distribution to trigger warning
        rng = np.random.default_rng(99)
        for _ in range(100):
            mon.record(rng.uniform(0.0, 0.3))
        assert len(alerts) > 0
        assert all(isinstance(a, DriftResult) for a in alerts)

    def test_last_result(self):
        mon = self._make_monitor(check_every=10)
        assert mon.last_result is None
        rng = np.random.default_rng(42)
        for _ in range(10):
            mon.record(rng.uniform(0.3, 0.9))
        assert mon.last_result is not None
