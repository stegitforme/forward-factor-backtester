"""
Tests for the metrics module.

Validates CAGR, Sharpe, Sortino, Calmar, max drawdown calculations
against known values constructed by hand.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.metrics import (
    compute_cagr,
    compute_max_drawdown,
    compute_metrics,
    compute_returns,
    compute_sharpe,
    compute_sortino,
    compute_trade_stats,
    compute_volatility,
    correlation_matrix,
)


def _make_curve(values: list[float], start_date: str = "2022-05-02") -> pd.Series:
    """Build a daily equity curve from a list of values."""
    dates = pd.date_range(start=start_date, periods=len(values), freq="D")
    return pd.Series(values, index=dates)


class TestCAGR:
    def test_doubling_in_one_year(self):
        """100 -> 200 over 365 days = 100% CAGR."""
        curve = pd.Series(
            [100.0, 200.0],
            index=pd.to_datetime(["2022-05-02", "2023-05-02"]),
        )
        cagr = compute_cagr(curve)
        assert abs(cagr - 1.0) < 0.001  # 100% within rounding

    def test_no_growth_zero_cagr(self):
        curve = _make_curve([100.0] * 100)
        assert abs(compute_cagr(curve)) < 1e-9

    def test_loss_negative_cagr(self):
        """100 -> 50 over 365 days = -50% CAGR."""
        curve = pd.Series(
            [100.0, 50.0],
            index=pd.to_datetime(["2022-05-02", "2023-05-02"]),
        )
        cagr = compute_cagr(curve)
        assert abs(cagr - (-0.5)) < 0.001

    def test_short_curve_returns_zero(self):
        curve = _make_curve([100.0])
        assert compute_cagr(curve) == 0.0


class TestVolatility:
    def test_zero_vol_constant_returns(self):
        """Constant returns should give zero std."""
        curve = pd.Series([100, 102, 104.04, 106.12, 108.24],
                          index=pd.date_range("2022-05-02", periods=5, freq="D"))
        returns = compute_returns(curve)
        # Returns are all ~0.02 — std should be near zero
        vol = compute_volatility(returns)
        assert vol < 0.01

    def test_known_volatility(self):
        """Returns of [+1%, -1%, +1%, -1%, ...] should give vol = 1% * sqrt(252)."""
        n = 250
        returns = pd.Series(
            [0.01 if i % 2 == 0 else -0.01 for i in range(n)],
            index=pd.date_range("2022-05-02", periods=n, freq="D"),
        )
        vol = compute_volatility(returns)
        expected = 0.01 * np.sqrt(252)
        # Tolerance because std uses N-1, not N
        assert abs(vol - expected) < 0.01


class TestSharpe:
    def test_sharpe_zero_for_zero_excess(self):
        """All zero returns -> Sharpe = 0."""
        returns = pd.Series([0.0] * 100,
                            index=pd.date_range("2022-05-02", periods=100, freq="D"))
        # Sharpe should handle zero-volatility gracefully
        s = compute_sharpe(returns)
        assert s == 0.0

    def test_sharpe_positive_for_consistent_gains(self):
        """Steady positive returns -> high positive Sharpe."""
        n = 200
        returns = pd.Series(
            [0.001] * n + [0.001 + 0.0001 * (i % 7 - 3) for i in range(n)],
            index=pd.date_range("2022-05-02", periods=2 * n, freq="D"),
        )
        s = compute_sharpe(returns)
        assert s > 0


class TestSortino:
    def test_sortino_higher_than_sharpe_for_positive_skew(self):
        """For a positively-skewed return series (rare large gains),
        Sortino should be >= Sharpe because downside std < total std."""
        # Mostly small losses, occasional large gain
        returns_list = [-0.001] * 100 + [0.05] * 5 + [0.0] * 100
        returns = pd.Series(
            returns_list,
            index=pd.date_range("2022-05-02", periods=len(returns_list), freq="D"),
        )
        sharpe = compute_sharpe(returns)
        sortino = compute_sortino(returns)
        # Both should be defined
        assert isinstance(sortino, float)
        # If mean is positive, sortino should be at least sharpe
        if returns.mean() > 0:
            assert sortino >= sharpe - 0.01


class TestMaxDrawdown:
    def test_no_drawdown_monotonic(self):
        """Monotonically increasing -> 0 drawdown."""
        curve = _make_curve([100, 110, 120, 130, 140])
        dd, dur = compute_max_drawdown(curve)
        assert dd == 0.0
        assert dur == 0

    def test_known_drawdown(self):
        """Curve: 100 -> 200 -> 150 -> 220.
        DD from 200 to 150 = -25%."""
        curve = _make_curve([100, 200, 150, 220])
        dd, _ = compute_max_drawdown(curve)
        assert abs(dd - (-0.25)) < 1e-9

    def test_drawdown_duration(self):
        """Underwater for 3 days then recovered."""
        curve = _make_curve([100, 90, 85, 80, 100, 110])
        dd, dur = compute_max_drawdown(curve)
        assert dd < 0
        # 4 days underwater (90, 85, 80, then recovered at 100)
        # Days 1, 2, 3 are underwater; day 4 returns to peak
        assert dur >= 3


class TestComputeMetrics:
    """Integration test: full metrics computation on synthetic curve."""

    def test_basic_metrics_complete(self):
        """Build a 1-year curve and verify all fields are populated."""
        n = 252
        np.random.seed(42)
        returns = np.random.normal(0.0008, 0.012, n)
        equity = 100_000 * np.cumprod(1 + returns)
        curve = pd.Series(
            equity,
            index=pd.date_range("2022-05-02", periods=n, freq="B"),
        )
        m = compute_metrics(curve)

        # All numeric fields populated
        assert isinstance(m.cagr, float)
        assert isinstance(m.volatility, float)
        assert isinstance(m.sharpe, float)
        assert isinstance(m.sortino, float)
        assert m.start_date is not None
        assert m.end_date is not None

    def test_with_trade_log(self):
        """Compute metrics with a trade log and verify trade stats."""
        n = 100
        curve = _make_curve(list(np.linspace(100_000, 130_000, n)))
        # Build a simple trade log
        trades = pd.DataFrame({
            "ticker": ["AAPL"] * 10,
            "pnl_total": [100, 200, -50, 150, -100, 300, -75, 250, -125, 175],
            "entry_debit": [1.0] * 10,
            "contracts": [1] * 10,
        })
        m = compute_metrics(curve, trades)
        assert m.n_trades == 10
        assert 0.0 < m.win_rate < 1.0


class TestTradeStats:
    def test_empty_trades(self):
        stats = compute_trade_stats(pd.DataFrame())
        assert stats["n_trades"] == 0
        assert stats["win_rate"] == 0.0

    def test_all_wins(self):
        trades = pd.DataFrame({"pnl_total": [100, 200, 300]})
        stats = compute_trade_stats(trades)
        assert stats["win_rate"] == 1.0
        assert stats["n_trades"] == 3

    def test_mixed_outcomes(self):
        trades = pd.DataFrame({"pnl_total": [100, -50, 200, -100, 150]})
        stats = compute_trade_stats(trades)
        assert stats["n_trades"] == 5
        assert abs(stats["win_rate"] - 0.6) < 1e-9


class TestCorrelationMatrix:
    def test_correlation_with_self_is_one(self):
        n = 50
        np.random.seed(0)
        returns = pd.Series(np.random.normal(0, 0.01, n),
                            index=pd.date_range("2022-05-02", periods=n))
        corr = correlation_matrix({"strat_a": returns, "strat_b": returns})
        # Self-correlation = 1
        assert abs(corr.loc["strat_a", "strat_a"] - 1.0) < 1e-9
        # Identical series -> correlation 1
        assert abs(corr.loc["strat_a", "strat_b"] - 1.0) < 1e-9

    def test_uncorrelated_returns(self):
        n = 500
        np.random.seed(123)
        a = pd.Series(np.random.normal(0, 0.01, n),
                      index=pd.date_range("2022-05-02", periods=n))
        b = pd.Series(np.random.normal(0, 0.01, n),
                      index=pd.date_range("2022-05-02", periods=n))
        corr = correlation_matrix({"a": a, "b": b})
        # Should be close to zero with this many samples
        assert abs(corr.loc["a", "b"]) < 0.15


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
