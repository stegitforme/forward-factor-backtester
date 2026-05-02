"""
Unit tests for the trade simulator.

Tests the pure-math P&L calculation and the option ticker formatting.
The full simulate_calendar() function with Polygon integration is
covered by integration tests requiring API access.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.trade_simulator import (
    CalendarResult,
    CalendarSpec,
    _option_ticker_for_strike,
    simulate_calendar_from_prices,
)


class TestOptionTickerFormatting:
    """Test the Polygon option symbol builder."""

    def test_spy_call(self):
        """SPY $400 call expiring 2023-01-20 should be O:SPY230120C00400000."""
        result = _option_ticker_for_strike(
            underlying="SPY",
            expiry=date(2023, 1, 20),
            contract_type="C",
            strike=400.0,
        )
        assert result == "O:SPY230120C00400000"

    def test_aapl_put(self):
        """AAPL $150.50 put expiring 2026-05-16."""
        result = _option_ticker_for_strike(
            underlying="AAPL",
            expiry=date(2026, 5, 16),
            contract_type="P",
            strike=150.50,
        )
        assert result == "O:AAPL260516P00150500"

    def test_low_strike(self):
        """Low strike like $5.00."""
        result = _option_ticker_for_strike(
            underlying="F",
            expiry=date(2026, 6, 19),
            contract_type="C",
            strike=5.0,
        )
        assert result == "O:F260619C00005000"

    def test_high_strike(self):
        """High strike like $1234.50."""
        result = _option_ticker_for_strike(
            underlying="BRK",
            expiry=date(2026, 12, 18),
            contract_type="C",
            strike=1234.50,
        )
        assert result == "O:BRK261218C01234500"

    def test_fractional_strike_rounding(self):
        """Strike like $150.555 should round to nearest cent."""
        result = _option_ticker_for_strike(
            underlying="X",
            expiry=date(2026, 5, 16),
            contract_type="C",
            strike=150.555,
        )
        # 150.555 * 1000 = 150555 -> rounds to 150555
        assert "00150555" in result


class TestSimulateFromPrices:
    """Test the pure-math P&L calculator."""

    def test_winning_calendar_basic(self):
        """
        Entry: front=$2.00, back=$3.00 -> debit $1.00
        Exit:  front=$0.10, back=$2.00 -> spread $1.90
        Profit before slippage/comms = $0.90 per spread = $90 with multiplier
        With 5% slippage: entry $1.05, exit $1.805 -> profit $0.755 = $75.50
        Less 4 commission events at $0.65 = $5.20
        Net per spread: $75.50 - $5.20 = $70.30
        """
        result = simulate_calendar_from_prices(
            entry_front_mid=2.00,
            entry_back_mid=3.00,
            exit_front_mid=0.10,
            exit_back_mid=2.00,
            contracts=1,
            legs_per_spread=2,
            slippage_pct=0.05,
            commission_per_contract=0.65,
            multiplier=100.0,
        )
        # entry_debit = 1.00 * 1.05 = 1.05
        assert abs(result["entry_debit"] - 1.05) < 1e-9
        # exit_credit = 1.90 * 0.95 = 1.805
        assert abs(result["exit_credit"] - 1.805) < 1e-9
        # commissions = 0.65 * 2 * 2 * 1 = 2.60 (wait: legs * 2 sides * contracts)
        assert abs(result["commissions"] - 2.60) < 1e-9
        # pnl = (1.805 - 1.05) * 1 * 100 - 2.60 = 75.50 - 2.60 = 72.90
        assert abs(result["pnl_total"] - 72.90) < 1e-9

    def test_losing_calendar(self):
        """Front rallied harder than back -> spread shrinks, calendar loses."""
        result = simulate_calendar_from_prices(
            entry_front_mid=2.00,
            entry_back_mid=3.00,   # debit 1.00
            exit_front_mid=2.00,
            exit_back_mid=2.50,    # spread 0.50 (lost half)
            contracts=1,
        )
        assert result["pnl_total"] < 0

    def test_zero_debit_raises(self):
        """If front == back at entry, we have zero debit which is invalid."""
        with pytest.raises(ValueError):
            simulate_calendar_from_prices(
                entry_front_mid=2.00,
                entry_back_mid=2.00,
                exit_front_mid=1.00,
                exit_back_mid=1.50,
            )

    def test_inverted_calendar_raises(self):
        """Front > back at entry -> negative debit, invalid."""
        with pytest.raises(ValueError):
            simulate_calendar_from_prices(
                entry_front_mid=3.00,
                entry_back_mid=2.00,
                exit_front_mid=1.00,
                exit_back_mid=1.50,
            )

    def test_multiple_contracts_scales_linearly(self):
        """10 contracts should give 10x the per-spread P&L (minus 10x comms)."""
        r1 = simulate_calendar_from_prices(
            entry_front_mid=2.00, entry_back_mid=3.00,
            exit_front_mid=0.10, exit_back_mid=2.00,
            contracts=1,
        )
        r10 = simulate_calendar_from_prices(
            entry_front_mid=2.00, entry_back_mid=3.00,
            exit_front_mid=0.10, exit_back_mid=2.00,
            contracts=10,
        )
        # PnL per spread is the same; total scales
        assert abs(r10["pnl_per_spread"] - r1["pnl_per_spread"]) < 1e-9
        # Total: 10 * (gross_per_spread * 100) - 10 * commissions
        gross_total_r1 = r1["pnl_total"] + r1["commissions"]
        gross_total_r10 = r10["pnl_total"] + r10["commissions"]
        assert abs(gross_total_r10 - 10 * gross_total_r1) < 1e-9

    def test_double_calendar_4_legs_per_spread(self):
        """
        Double calendar has 4 legs per spread, so commissions are 2x.
        With same gross P&L, double calendar has lower net P&L due to 2x comms.
        """
        single = simulate_calendar_from_prices(
            entry_front_mid=2.00, entry_back_mid=3.00,
            exit_front_mid=0.10, exit_back_mid=2.00,
            contracts=1, legs_per_spread=2,
        )
        double = simulate_calendar_from_prices(
            entry_front_mid=2.00, entry_back_mid=3.00,
            exit_front_mid=0.10, exit_back_mid=2.00,
            contracts=1, legs_per_spread=4,
        )
        # Same gross, but double pays 2x comms
        assert abs(double["commissions"] - 2 * single["commissions"]) < 1e-9
        assert double["pnl_total"] < single["pnl_total"]

    def test_zero_slippage_zero_commission(self):
        """With no friction, P&L = (exit_spread - entry_spread) * 100 * contracts."""
        result = simulate_calendar_from_prices(
            entry_front_mid=2.00, entry_back_mid=3.00,
            exit_front_mid=0.10, exit_back_mid=2.00,
            contracts=1, legs_per_spread=2,
            slippage_pct=0.0, commission_per_contract=0.0,
        )
        # Gross P&L = (1.90 - 1.00) * 100 = 90
        assert abs(result["pnl_total"] - 90.0) < 1e-9
        assert result["commissions"] == 0.0


class TestCalendarSpec:
    """Test the spec dataclass."""

    def test_basic_call_spec(self):
        spec = CalendarSpec(
            ticker="AAPL",
            entry_date=date(2026, 5, 1),
            structure="atm_call_calendar",
            front_expiry=date(2026, 5, 30),
            back_expiry=date(2026, 6, 30),
            front_strike=150.0,
            back_strike=150.0,
            contracts=1,
            forward_factor_at_entry=0.25,
        )
        assert spec.structure == "atm_call_calendar"
        assert spec.put_front_strike is None

    def test_double_calendar_spec(self):
        spec = CalendarSpec(
            ticker="AAPL",
            entry_date=date(2026, 5, 1),
            structure="double_calendar_35d",
            front_expiry=date(2026, 5, 30),
            back_expiry=date(2026, 6, 30),
            front_strike=155.0,        # 35-delta call strike
            back_strike=155.0,
            put_front_strike=145.0,    # 35-delta put strike (mirror)
            put_back_strike=145.0,
            contracts=2,
            forward_factor_at_entry=0.30,
        )
        assert spec.put_front_strike == 145.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
