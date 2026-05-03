"""
Tests for the backtest orchestrator.

Tests the cell configuration and ensemble building logic. The full
backtest loop with mocked Polygon is deferred to integration tests.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.backtest import (
    BacktestResult,
    Cell,
    CellResult,
    _build_ensemble,
    _combine_trade_logs,
    all_cells,
)


class TestCells:
    def test_all_cells_count(self):
        """Phase 2a config: 2 DTE pairs × 1 structure = 2 cells."""
        cells = all_cells()
        assert len(cells) == 2

    def test_all_cells_unique_names(self):
        cells = all_cells()
        names = [c.name for c in cells]
        assert len(names) == len(set(names))

    def test_cells_cover_all_combinations(self):
        """Phase 2a config has 30-90 and 60-90 ATM call calendars."""
        cells = all_cells()
        dte_pairs = {(c.dte_front, c.dte_back) for c in cells}
        structures = {c.structure for c in cells}
        assert (30, 90) in dte_pairs
        assert (60, 90) in dte_pairs
        assert "atm_call_calendar" in structures


class TestEnsembleBuilder:
    def _make_cell_result(self, name, values, start="2022-05-02"):
        curve = pd.Series(
            values,
            index=pd.date_range(start, periods=len(values), freq="D"),
            name=name,
        )
        return CellResult(
            cell=Cell(name=name, dte_front=30, dte_back=60, structure="atm_call_calendar"),
            equity_curve=curve,
            trade_log=pd.DataFrame(),
            final_equity=float(curve.iloc[-1]),
        )

    def test_ensemble_averages_normalized_curves(self):
        """Two cells with different abs values should ensemble to the average growth."""
        # Cell A: 100 -> 200 (2x)
        # Cell B: 100 -> 150 (1.5x)
        # Equal-weighted ensemble final value = avg(2x, 1.5x) = 1.75x
        # Starting at $100k, ensemble ends at $175k
        a = self._make_cell_result("A", [100, 150, 200])
        b = self._make_cell_result("B", [100, 125, 150])
        ensemble = _build_ensemble({"A": a, "B": b}, initial_capital=100_000)
        # Final value: avg of (200/100, 150/100) * 100,000 = 1.75 * 100k
        assert abs(ensemble.iloc[-1] - 175_000) < 1e-6

    def test_ensemble_handles_empty(self):
        ensemble = _build_ensemble({}, initial_capital=100_000)
        assert len(ensemble) == 0

    def test_ensemble_skips_empty_curves(self):
        """Cells with empty equity curves are skipped."""
        a = self._make_cell_result("A", [100, 200])
        b_empty = CellResult(
            cell=Cell(name="B", dte_front=30, dte_back=60, structure="atm_call_calendar"),
            equity_curve=pd.Series(dtype=float),
            trade_log=pd.DataFrame(),
            final_equity=100_000,
        )
        ensemble = _build_ensemble({"A": a, "B": b_empty}, initial_capital=100_000)
        # Should ensemble only A (which doubled)
        assert ensemble.iloc[-1] == 200_000


class TestTradeLogCombiner:
    def _make_cell_result_with_trades(self, name, n_trades):
        return CellResult(
            cell=Cell(name=name, dte_front=30, dte_back=60, structure="atm_call_calendar"),
            equity_curve=pd.Series([100_000, 110_000],
                                    index=pd.to_datetime(["2022-05-02", "2022-06-02"])),
            trade_log=pd.DataFrame({
                "ticker": ["AAPL"] * n_trades,
                "pnl_total": [100.0] * n_trades,
            }),
            final_equity=110_000,
        )

    def test_combine_adds_cell_column(self):
        a = self._make_cell_result_with_trades("A", 3)
        b = self._make_cell_result_with_trades("B", 2)
        combined = _combine_trade_logs({"A": a, "B": b})
        assert len(combined) == 5
        assert set(combined["cell"].unique()) == {"A", "B"}

    def test_combine_handles_empty_trade_logs(self):
        a = CellResult(
            cell=Cell(name="A", dte_front=30, dte_back=60, structure="atm_call_calendar"),
            equity_curve=pd.Series(dtype=float),
            trade_log=pd.DataFrame(),
            final_equity=100_000,
        )
        combined = _combine_trade_logs({"A": a})
        assert combined.empty


class TestStepOneDayExitPricing:
    """Tests for the exit-pricing path in step_one_day().
    The candidate-discovery path is patched out (returns []) so we focus
    purely on the close branch."""

    def _setup(self, monkeypatch, exit_value, structure="atm_call_calendar"):
        """Build a portfolio with a single open position and patch out
        candidate discovery. Returns (portfolio, position, trade_log, today)."""
        from src import backtest as bt
        from src.portfolio import Portfolio, Position
        from src.universe import Universe

        # Patch candidate discovery to no-op (we're testing the close branch)
        monkeypatch.setattr(bt, "find_candidates_for_day", lambda *a, **k: [])

        # Patch compute_exit_value to return our scripted value
        monkeypatch.setattr(bt, "compute_exit_value", lambda *a, **k: exit_value)

        portfolio = Portfolio(cash=100_000)
        # Slipped entry: paid 1.00 * 1.05 = 1.05 per spread, 5 contracts
        position = Position(
            ticker="SPY",
            structure=structure,
            entry_date=date(2024, 9, 27),
            front_expiry=date(2024, 11, 15),
            back_expiry=date(2024, 12, 20),
            contracts=5,
            entry_debit=1.05,
            debit_total=525.0,
            forward_factor_at_entry=0.30,
            front_strike=571.0,
            back_strike=571.0,
        )
        portfolio.cash -= position.debit_total
        portfolio.positions.append(position)
        today = date(2024, 11, 14)  # T-1 of front_expiry triggers close
        cell = Cell(name="60_90_atm", dte_front=60, dte_back=90,
                    structure="atm_call_calendar")
        empty_universe = Universe(snapshot_date=today, entries=())
        trade_log: list[dict] = []
        return portfolio, position, trade_log, today, cell, empty_universe

    def test_real_exit_value_used_when_available(self, monkeypatch):
        """compute_exit_value returns 1.50/spread; close at that value, not entry_debit."""
        from src import backtest as bt
        portfolio, position, trade_log, today, cell, universe = self._setup(
            monkeypatch, exit_value=1.50,
        )
        # Entry: 1.05 * 5 * 100 = 525
        # Exit:  1.50 * 5 * 100 = 750
        # Commissions: 0.65 * 2 legs * 2 sides * 5 ctr = 13.00
        # P&L: 750 - 525 - 13 = 212.00
        bt.step_one_day(today, cell, portfolio, universe,
                        polygon_client=None, earnings_filter=None,
                        trade_log=trade_log)
        assert len(portfolio.positions) == 0
        assert abs(portfolio.realized_pnl - 212.0) < 1e-6

    def test_falls_back_to_entry_debit_when_exit_pricing_missing(self, monkeypatch, caplog):
        """If compute_exit_value returns None, use entry_debit + log warning.
        P&L = -commissions only (round-trip at parity)."""
        import logging
        from src import backtest as bt
        portfolio, position, trade_log, today, cell, universe = self._setup(
            monkeypatch, exit_value=None,
        )
        with caplog.at_level(logging.WARNING, logger="src.backtest"):
            bt.step_one_day(today, cell, portfolio, universe,
                            polygon_client=None, earnings_filter=None,
                            trade_log=trade_log)
        # Entry == Exit == 1.05 * 5 * 100 = 525
        # Commissions: 0.65 * 2 * 2 * 5 = 13.00
        # P&L: 525 - 525 - 13 = -13.00
        assert abs(portfolio.realized_pnl - (-13.0)) < 1e-6
        # Warning was logged
        assert any("Exit pricing unavailable" in r.message for r in caplog.records)

    def test_commission_count_atm_two_legs(self, monkeypatch):
        """ATM (2 legs) commission: 0.65 * 2 * 2 = 2.60 per contract round-trip.
        Old buggy code charged 0.65 * 4 * 2 = 5.20 per contract (double count)."""
        from src import backtest as bt
        portfolio, position, trade_log, today, cell, universe = self._setup(
            monkeypatch, exit_value=1.05,  # exit == entry mid (no underlying P&L)
        )
        # P&L should be -commissions only: 0.65 * 2 * 2 * 5 = 13.00
        bt.step_one_day(today, cell, portfolio, universe,
                        polygon_client=None, earnings_filter=None,
                        trade_log=trade_log)
        assert abs(portfolio.realized_pnl - (-13.0)) < 1e-6
        # Old bug would have given -26.00 (5.20 per contract)
        assert portfolio.realized_pnl != pytest.approx(-26.0)

    def test_commission_count_double_calendar_four_legs(self, monkeypatch):
        """Double calendar (4 legs): 0.65 * 4 * 2 * contracts."""
        from src import backtest as bt
        portfolio, position, trade_log, today, cell, universe = self._setup(
            monkeypatch, exit_value=1.05, structure="double_calendar_35d",
        )
        bt.step_one_day(today, cell, portfolio, universe,
                        polygon_client=None, earnings_filter=None,
                        trade_log=trade_log)
        # Commissions: 0.65 * 4 * 2 * 5 = 26.00
        # P&L: 0 - 26.00 = -26.00
        assert abs(portfolio.realized_pnl - (-26.0)) < 1e-6


class TestResolveFFThreshold:
    """Phase 2c: per-cell FF threshold resolution.
    settings.FF_THRESHOLD can be either a float (uniform) or a dict (per-cell)."""

    def test_uniform_float(self, monkeypatch):
        from src import backtest as bt
        from config import settings
        monkeypatch.setattr(settings, "FF_THRESHOLD", 0.20)
        assert bt.resolve_ff_threshold("30_90_atm") == 0.20
        assert bt.resolve_ff_threshold("60_90_atm") == 0.20
        assert bt.resolve_ff_threshold("anything_else") == 0.20

    def test_per_cell_dict_lookup_hit(self, monkeypatch):
        from src import backtest as bt
        from config import settings
        monkeypatch.setattr(settings, "FF_THRESHOLD",
                            {"30_90_atm": 0.30, "60_90_atm": 0.15})
        assert bt.resolve_ff_threshold("30_90_atm") == 0.30
        assert bt.resolve_ff_threshold("60_90_atm") == 0.15

    def test_per_cell_dict_lookup_miss_uses_default(self, monkeypatch):
        from src import backtest as bt
        from config import settings
        monkeypatch.setattr(settings, "FF_THRESHOLD", {"30_90_atm": 0.30})
        monkeypatch.setattr(settings, "FF_THRESHOLD_DEFAULT", 0.20)
        # Cell not in dict falls back to FF_THRESHOLD_DEFAULT
        assert bt.resolve_ff_threshold("60_90_atm") == 0.20
        assert bt.resolve_ff_threshold("30_90_atm") == 0.30


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
