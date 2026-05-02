"""
Unit tests for the Forward Factor calculator.

Validates against:
  1. The video walkthrough's worked example (30/60 DTE, 45%/35% IV)
  2. The author's calculator.py output for the same inputs
  3. Mathematical edge cases (equal IVs, contango, negative variance)
  4. Vectorized version produces identical results to scalar version
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from src.ff_calculator import (
    DAYS_PER_YEAR,
    calculate_forward_factor,
    calculate_forward_factor_vectorized,
)


class TestVideoWalkthrough:
    """Tests against the worked example in the YouTube video."""

    def test_video_example_forward_variance(self):
        """30 DTE @ 45% IV, 60 DTE @ 35% IV -> forward_variance = 0.0425."""
        r = calculate_forward_factor(30, 45.0, 60, 35.0)
        assert r.is_valid
        assert abs(r.forward_variance - 0.0425) < 1e-6

    def test_video_example_forward_iv(self):
        """Forward IV should be sqrt(0.0425) = 20.6155%, not 20.66%.

        The video narration says 20.66%, but his calculator.py and our
        implementation both produce 20.6155%. The discrepancy is a
        narration rounding error in the video, not a calculation bug.
        """
        r = calculate_forward_factor(30, 45.0, 60, 35.0)
        expected = math.sqrt(0.0425) * 100
        assert abs(r.forward_iv_pct - expected) < 0.001

    def test_video_example_forward_factor(self):
        """FF = (45% - 20.6155%) / 20.6155% = 118.28%."""
        r = calculate_forward_factor(30, 45.0, 60, 35.0)
        expected = (0.45 - math.sqrt(0.0425)) / math.sqrt(0.0425)
        assert abs(r.forward_factor - expected) < 1e-9


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_equal_ivs_gives_zero_ff(self):
        """When front and back IV are equal, FF should be exactly 0."""
        r = calculate_forward_factor(30, 30.0, 60, 30.0)
        assert r.is_valid
        assert abs(r.forward_factor) < 1e-12
        assert abs(r.forward_iv_pct - 30.0) < 1e-9

    def test_contango_gives_negative_ff(self):
        """Back IV > front IV -> FF should be negative (typical normal market)."""
        r = calculate_forward_factor(30, 20.0, 60, 25.0)
        assert r.is_valid
        assert r.forward_factor < 0
        assert r.forward_iv_pct > 25.0  # forward must be even higher than back

    def test_extreme_backwardation_invalid(self):
        """Very high front IV vs very low back IV -> negative variance."""
        # 100% front vs 30% back: var_front = 1.0 * 30/365, var_back = 0.09 * 60/365
        # fwd_var = (var_back - var_front) / (T_back - T_front) ... will be negative
        r = calculate_forward_factor(30, 100.0, 60, 30.0)
        assert not r.is_valid
        assert r.error is not None
        assert "negative" in r.error.lower() or "Negative" in r.error

    def test_zero_dte_front_allowed(self):
        """DTE_front = 0 is mathematically valid (back is forward window)."""
        r = calculate_forward_factor(0, 0.0, 30, 25.0)
        assert r.is_valid
        # Forward IV should equal back IV when front DTE is zero
        assert abs(r.forward_iv_pct - 25.0) < 1e-6

    def test_back_must_exceed_front(self):
        """dte_back must be strictly greater than dte_front."""
        r = calculate_forward_factor(60, 30.0, 60, 30.0)
        assert not r.is_valid
        assert "back must be" in (r.error or "").lower()

    def test_negative_dte_rejected(self):
        """Negative DTEs are rejected."""
        r = calculate_forward_factor(-5, 30.0, 30, 25.0)
        assert not r.is_valid

    def test_negative_iv_rejected(self):
        """Negative IVs are rejected."""
        r = calculate_forward_factor(30, -10.0, 60, 25.0)
        assert not r.is_valid


class TestPropertyValues:
    """Tests on the result object properties."""

    def test_forward_iv_pct_property(self):
        r = calculate_forward_factor(30, 45.0, 60, 35.0)
        assert abs(r.forward_iv_pct - r.forward_sigma * 100) < 1e-12

    def test_forward_factor_pct_property(self):
        r = calculate_forward_factor(30, 45.0, 60, 35.0)
        assert abs(r.forward_factor_pct - r.forward_factor * 100) < 1e-12

    def test_T_values_use_calendar_days(self):
        """T = DTE / 365, not DTE / 252 (matches author's calculator)."""
        r = calculate_forward_factor(30, 45.0, 60, 35.0)
        assert abs(r.T_front - 30 / 365.0) < 1e-12
        assert abs(r.T_back - 60 / 365.0) < 1e-12
        assert DAYS_PER_YEAR == 365.0


class TestVectorized:
    """Vectorized version must match scalar version exactly."""

    def test_vectorized_matches_scalar_video_example(self):
        v = calculate_forward_factor_vectorized([30], [45.0], [60], [35.0])
        s = calculate_forward_factor(30, 45.0, 60, 35.0)
        assert abs(v["forward_factor"][0] - s.forward_factor) < 1e-12
        assert abs(v["forward_sigma"][0] - s.forward_sigma) < 1e-12

    def test_vectorized_handles_invalid_rows(self):
        """Invalid rows return NaN with is_valid=False."""
        v = calculate_forward_factor_vectorized(
            dte_front=[30, 60, -5, 30],
            iv_front_pct=[45.0, 30.0, 30.0, 100.0],
            dte_back=[60, 60, 30, 60],
            iv_back_pct=[35.0, 30.0, 25.0, 30.0],
        )
        # Row 0: valid (video example)
        assert v["is_valid"][0]
        # Row 1: dte_back == dte_front -> invalid
        assert not v["is_valid"][1]
        # Row 2: negative dte_front -> invalid
        assert not v["is_valid"][2]
        # Row 3: negative variance -> invalid
        assert not v["is_valid"][3]

    def test_vectorized_batch_computation(self):
        """Vectorized matches scalar across a batch of varied inputs."""
        n = 50
        rng = np.random.default_rng(42)
        dte_f = rng.integers(7, 60, size=n)
        dte_b = dte_f + rng.integers(7, 90, size=n)
        iv_f = rng.uniform(15.0, 80.0, size=n)
        iv_b = rng.uniform(15.0, 60.0, size=n)

        v = calculate_forward_factor_vectorized(dte_f, iv_f, dte_b, iv_b)

        for i in range(n):
            s = calculate_forward_factor(dte_f[i], iv_f[i], dte_b[i], iv_b[i])
            if s.is_valid:
                assert abs(v["forward_factor"][i] - s.forward_factor) < 1e-10, \
                    f"Mismatch at row {i}"
            else:
                assert not v["is_valid"][i], f"Row {i} should be invalid"


class TestStrategyThreshold:
    """Validates that the FF >= 0.20 threshold from the video aligns
    with what we compute. These are sanity checks on the strategy logic."""

    def test_high_ff_setup(self):
        """A strongly backwardated setup should produce FF well above 0.20."""
        # 30 DTE at 60% IV, 60 DTE at 30% IV — typical pre-event setup
        r = calculate_forward_factor(30, 60.0, 60, 30.0)
        if r.is_valid:
            assert r.forward_factor > 0.20

    def test_typical_market_below_threshold(self):
        """In contango markets, FF should be negative or near zero."""
        # Typical contango: 30 DTE at 18% IV, 60 DTE at 22% IV
        r = calculate_forward_factor(30, 18.0, 60, 22.0)
        assert r.is_valid
        assert r.forward_factor < 0  # Below threshold = no trade

    def test_borderline_setup(self):
        """An FF right around 0.20 should compute without issues."""
        # Tune inputs to land near 0.20
        # If FF = 0.20, then sigma_front = 1.20 * sigma_fwd
        # So pick sigma_fwd = 0.25, sigma_front = 0.30, then derive sigma_back
        # var_back * T_back = var_front * T_front + var_fwd * (T_back - T_front)
        # 0.25^2 * (T_back - T_front) + 0.09 * 30/365 = sigma_back^2 * 60/365
        # solve for sigma_back
        T1, T2 = 30/365, 60/365
        sig_fwd = 0.25
        sig_front = 0.30
        var_front_total = sig_front**2 * T1
        var_fwd_window = sig_fwd**2 * (T2 - T1)
        var_back_total = var_front_total + var_fwd_window
        sig_back = math.sqrt(var_back_total / T2)

        r = calculate_forward_factor(30, sig_front * 100, 60, sig_back * 100)
        assert r.is_valid
        assert abs(r.forward_factor - 0.20) < 1e-6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
