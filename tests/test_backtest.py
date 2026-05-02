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
        """Simplified config: 1 DTE pair × 1 structure = 1 cell (60-90 ATM)."""
        cells = all_cells()
        assert len(cells) == 1

    def test_all_cells_unique_names(self):
        cells = all_cells()
        names = [c.name for c in cells]
        assert len(names) == len(set(names))

    def test_cells_cover_all_combinations(self):
        """The simplified config keeps only the 60-90 ATM call calendar."""
        cells = all_cells()
        dte_pairs = {(c.dte_front, c.dte_back) for c in cells}
        structures = {c.structure for c in cells}
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
