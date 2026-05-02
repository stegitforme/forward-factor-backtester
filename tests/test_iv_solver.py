"""
Tests for the Black-Scholes IV solver.

Validates against:
  - Hull textbook problems (chapter 15 examples)
  - Known sanity checks (ATM 30-DTE call at 20% IV must round-trip)
  - Edge cases (deep ITM, deep OTM, expired)
"""
from __future__ import annotations

import math

import pytest

from src.iv_solver import (
    black_scholes_delta,
    black_scholes_price,
    black_scholes_vega,
    implied_volatility,
    implied_volatility_safe,
)


class TestBlackScholesPricing:
    """Verify the BS pricing formula against textbook values."""

    def test_hull_example_atm_call(self):
        """
        Hull 9th ed Example 15.6: stock=$42, strike=$40, T=0.5, r=0.10,
        sigma=0.20. Expected call price ≈ $4.76.
        """
        price = black_scholes_price(
            underlying=42, strike=40, time_to_expiry=0.5,
            risk_free_rate=0.10, volatility=0.20, is_call=True,
        )
        assert abs(price - 4.76) < 0.05

    def test_hull_example_atm_put(self):
        """Same parameters as above for put. Expected ≈ $0.81."""
        price = black_scholes_price(
            underlying=42, strike=40, time_to_expiry=0.5,
            risk_free_rate=0.10, volatility=0.20, is_call=False,
        )
        assert abs(price - 0.81) < 0.05

    def test_put_call_parity(self):
        """C - P = S - K*exp(-rT) must hold."""
        S, K, T, r, sigma = 100, 100, 0.25, 0.05, 0.30
        c = black_scholes_price(S, K, T, r, sigma, is_call=True)
        p = black_scholes_price(S, K, T, r, sigma, is_call=False)
        rhs = S - K * math.exp(-r * T)
        assert abs((c - p) - rhs) < 1e-6

    def test_zero_volatility(self):
        """At zero vol, call price = max(S-K, 0)."""
        # ITM call
        price_itm = black_scholes_price(110, 100, 0.5, 0.05, 0.0, is_call=True)
        assert price_itm == 10.0  # intrinsic
        # OTM call
        price_otm = black_scholes_price(90, 100, 0.5, 0.05, 0.0, is_call=True)
        assert price_otm == 0.0


class TestBlackScholesDelta:
    """Delta sanity checks."""

    def test_atm_call_delta_near_half(self):
        """ATM call delta should be near 0.5 (slightly above)."""
        d = black_scholes_delta(100, 100, 0.25, 0.05, 0.30, is_call=True)
        assert 0.5 < d < 0.7

    def test_deep_itm_call_delta(self):
        """Deep ITM call delta approaches 1."""
        d = black_scholes_delta(150, 100, 0.25, 0.05, 0.30, is_call=True)
        assert d > 0.95

    def test_deep_otm_call_delta(self):
        """Deep OTM call delta approaches 0."""
        d = black_scholes_delta(50, 100, 0.25, 0.05, 0.30, is_call=True)
        assert d < 0.05

    def test_atm_put_delta_near_neg_half(self):
        """ATM put delta should be near -0.5."""
        d = black_scholes_delta(100, 100, 0.25, 0.05, 0.30, is_call=False)
        assert -0.7 < d < -0.3


class TestImpliedVolatilityRoundTrip:
    """Inversion: price -> IV -> price should round-trip."""

    @pytest.mark.parametrize("sigma", [0.10, 0.20, 0.30, 0.50, 0.80, 1.20])
    def test_atm_call_round_trip(self, sigma):
        """
        For ATM 30-DTE calls at various vols, generate the price then
        invert it. Should recover sigma to 1e-4.
        """
        S, K, T, r = 100, 100, 30 / 365.0, 0.04
        price = black_scholes_price(S, K, T, r, sigma, is_call=True)
        iv = implied_volatility(price, S, K, T, r, is_call=True)
        assert abs(iv - sigma) < 1e-4

    @pytest.mark.parametrize("strike_offset", [-20, -10, -5, 0, 5, 10, 20])
    def test_various_strikes_round_trip(self, strike_offset):
        """Round-trip for ITM, ATM, OTM at sigma=0.30."""
        S, T, r, sigma = 100, 60 / 365.0, 0.04, 0.30
        K = S + strike_offset
        price = black_scholes_price(S, K, T, r, sigma, is_call=True)
        if price <= 0.01:  # too cheap to invert reliably
            return
        iv = implied_volatility(price, S, K, T, r, is_call=True)
        assert abs(iv - sigma) < 1e-3

    def test_put_round_trip(self):
        """Put round-trip at 35-delta-ish strike."""
        S, K, T, r, sigma = 100, 95, 30 / 365.0, 0.04, 0.25
        price = black_scholes_price(S, K, T, r, sigma, is_call=False)
        iv = implied_volatility(price, S, K, T, r, is_call=False)
        assert abs(iv - sigma) < 1e-4


class TestImpliedVolatilityEdgeCases:
    """Bad inputs should return NaN, not crash."""

    def test_negative_price_returns_nan(self):
        iv = implied_volatility(-1.0, 100, 100, 0.25, 0.04)
        assert math.isnan(iv)

    def test_zero_time_returns_nan(self):
        iv = implied_volatility(5.0, 100, 100, 0.0, 0.04)
        assert math.isnan(iv)

    def test_below_intrinsic_returns_nan(self):
        """ITM call priced below intrinsic = arb, no valid IV."""
        # spot=110, strike=100, intrinsic=10. Price=5 is below.
        iv = implied_volatility(5.0, 110, 100, 0.25, 0.04, is_call=True)
        assert math.isnan(iv)

    def test_call_above_spot_returns_nan(self):
        """Call above spot = arb."""
        iv = implied_volatility(110.0, 100, 100, 0.25, 0.04, is_call=True)
        assert math.isnan(iv)


class TestImpliedVolatilitySafe:
    """The 'safe' wrapper should never raise."""

    def test_returns_nan_on_bad_input(self):
        iv = implied_volatility_safe(-5, 100, 100, 30)
        assert math.isnan(iv)

    def test_returns_nan_on_zero_dte(self):
        iv = implied_volatility_safe(5, 100, 100, 0)
        assert math.isnan(iv)

    def test_round_trip_valid_input(self):
        S, K, dte, r, sigma = 100, 100, 30, 0.04, 0.25
        T = dte / 365.0
        price = black_scholes_price(S, K, T, r, sigma, is_call=True)
        iv = implied_volatility_safe(price, S, K, dte, r, is_call=True)
        assert abs(iv - sigma) < 1e-4


class TestVega:
    """Vega sanity checks."""

    def test_atm_vega_positive(self):
        v = black_scholes_vega(100, 100, 0.25, 0.04, 0.20)
        assert v > 0

    def test_zero_time_zero_vega(self):
        v = black_scholes_vega(100, 100, 0.0, 0.04, 0.20)
        assert v == 0.0

    def test_atm_vega_peaks_near_money(self):
        """Vega should be max near ATM, lower for deep OTM/ITM."""
        v_atm = black_scholes_vega(100, 100, 0.25, 0.04, 0.20)
        v_otm = black_scholes_vega(100, 150, 0.25, 0.04, 0.20)
        v_itm = black_scholes_vega(100, 50, 0.25, 0.04, 0.20)
        assert v_atm > v_otm
        assert v_atm > v_itm


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
