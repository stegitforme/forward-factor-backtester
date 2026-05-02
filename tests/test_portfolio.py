"""
Unit tests for the portfolio sizing module.

Verifies:
  - size_trade respects all caps (concurrency, dollar budget, cash)
  - select_top_candidates picks highest FF first
  - open/close_position correctly tracks cash and positions
  - kelly_optimal_fraction matches known Kelly outputs
"""
from __future__ import annotations

import math
from datetime import date

import pytest

from src.portfolio import (
    Portfolio,
    Position,
    TradeCandidate,
    close_position,
    kelly_optimal_fraction,
    open_position,
    select_top_candidates,
    size_trade,
)


# ============================================================================
# Helpers
# ============================================================================

def _make_candidate(
    ticker="AAPL",
    debit=1.00,
    ff=0.25,
    structure="atm_call_calendar",
):
    return TradeCandidate(
        ticker=ticker,
        structure=structure,
        entry_date=date(2026, 5, 1),
        front_expiry=date(2026, 5, 30),
        back_expiry=date(2026, 6, 30),
        estimated_debit_per_spread=debit,
        forward_factor=ff,
        front_strike=150.0,
        back_strike=150.0,
    )


def _make_position(ticker="AAPL", debit_total=10_000):
    return Position(
        ticker=ticker,
        structure="atm_call_calendar",
        entry_date=date(2026, 5, 1),
        front_expiry=date(2026, 5, 30),
        back_expiry=date(2026, 6, 30),
        contracts=1,
        entry_debit=100.0,
        debit_total=debit_total,
        forward_factor_at_entry=0.25,
    )


# ============================================================================
# size_trade tests
# ============================================================================

class TestSizeTrade:
    """Tests for the per-trade sizing function."""

    def test_basic_sizing_at_quarter_kelly(self):
        """
        $200K equity, 4% risk, 25% Kelly = 1% effective per trade = $2000.
        Per-spread cost = $1.00 * 100 = $100.
        Max contracts = $2000 / $100 = 20.
        """
        portfolio = Portfolio(cash=200_000)
        candidate = _make_candidate(debit=1.00)
        contracts = size_trade(
            candidate, portfolio,
            risk_per_trade=0.04, kelly_fraction=0.25,
        )
        assert contracts == 20

    def test_zero_when_concurrency_full(self):
        """
        At max_concurrent positions, size returns 0.
        """
        portfolio = Portfolio(cash=200_000)
        # Fill up to 12 positions
        portfolio.positions = [_make_position(f"T{i}") for i in range(12)]

        candidate = _make_candidate()
        contracts = size_trade(candidate, portfolio, max_concurrent=12)
        assert contracts == 0

    def test_zero_when_debit_too_large(self):
        """
        Per-spread debit exceeds budget -> 0 contracts.
        Equity $10K, 4% * 25% Kelly = 0.1% = $10 budget.
        Per-spread cost = $5 * 100 = $500. Can't afford even 1.
        """
        portfolio = Portfolio(cash=10_000)
        candidate = _make_candidate(debit=5.00)
        contracts = size_trade(candidate, portfolio)
        assert contracts == 0

    def test_capped_by_cash(self):
        """
        If budget allows 20 contracts but cash only allows 5, size at 5.
        """
        # Equity = cash + deployed = 10,000 + 200,000 = 210,000
        # 4% * 25% = 1% = $2,100 budget
        # Per-spread cost = $1.00 * 100 = $100
        # Budget allows 21 contracts; cash allows 100; so 21 is the cap
        # But what we want to test: cash < budget allowance
        portfolio = Portfolio(cash=500)
        portfolio.positions = [_make_position("OTHER", debit_total=200_000)]
        # Equity = 500 + 200_000 = 200_500
        # Budget = 200_500 * 0.01 = 2,005
        # Per-spread = 100
        # By budget: 20 contracts
        # By cash: $500 / $100 = 5 contracts
        candidate = _make_candidate(debit=1.00)
        contracts = size_trade(candidate, portfolio)
        assert contracts == 5

    def test_quarter_kelly_uses_25pct_of_4pct(self):
        """
        Kelly fraction should multiplicatively scale the risk_per_trade.
        Equity $100K, 4% risk, 25% Kelly = $1000 budget.
        Per-spread $1 = $100. Max = 10 contracts.
        """
        portfolio = Portfolio(cash=100_000)
        candidate = _make_candidate(debit=1.00)
        contracts = size_trade(
            candidate, portfolio,
            risk_per_trade=0.04, kelly_fraction=0.25,
        )
        assert contracts == 10

    def test_full_kelly_quadruples_quarter(self):
        """Full Kelly should give 4x the contracts of quarter Kelly."""
        portfolio = Portfolio(cash=100_000)
        candidate = _make_candidate(debit=1.00)

        full_kelly = size_trade(
            candidate, portfolio,
            risk_per_trade=0.04, kelly_fraction=1.0,
        )
        quarter_kelly = size_trade(
            candidate, portfolio,
            risk_per_trade=0.04, kelly_fraction=0.25,
        )
        assert full_kelly == 4 * quarter_kelly


# ============================================================================
# select_top_candidates tests
# ============================================================================

class TestSelectTopCandidates:
    """Tests for FF-prioritized candidate selection."""

    def test_picks_highest_ff_first(self):
        portfolio = Portfolio(cash=100_000)
        candidates = [
            _make_candidate("LOW", ff=0.21),
            _make_candidate("HIGH", ff=0.45),
            _make_candidate("MID", ff=0.30),
        ]
        selected = select_top_candidates(candidates, portfolio, max_concurrent=12)
        assert selected[0].ticker == "HIGH"
        assert selected[1].ticker == "MID"
        assert selected[2].ticker == "LOW"

    def test_respects_remaining_capacity(self):
        portfolio = Portfolio(cash=100_000)
        portfolio.positions = [_make_position(f"T{i}") for i in range(10)]
        # 10 of 12 slots taken; 2 remaining
        candidates = [
            _make_candidate(f"NEW{i}", ff=0.20 + i * 0.01) for i in range(5)
        ]
        selected = select_top_candidates(candidates, portfolio, max_concurrent=12)
        assert len(selected) == 2
        # Should be the two highest FF
        assert selected[0].forward_factor > selected[1].forward_factor

    def test_returns_empty_when_full(self):
        portfolio = Portfolio(cash=100_000)
        portfolio.positions = [_make_position(f"T{i}") for i in range(12)]
        candidates = [_make_candidate(f"NEW{i}") for i in range(5)]
        selected = select_top_candidates(candidates, portfolio, max_concurrent=12)
        assert selected == []

    def test_empty_candidate_list(self):
        portfolio = Portfolio(cash=100_000)
        selected = select_top_candidates([], portfolio, max_concurrent=12)
        assert selected == []


# ============================================================================
# open / close position tests
# ============================================================================

class TestOpenClosePosition:
    """Position lifecycle tests."""

    def test_open_position_deducts_cash(self):
        portfolio = Portfolio(cash=100_000)
        candidate = _make_candidate(debit=2.00)
        position = open_position(portfolio, candidate, contracts=5, actual_debit_per_spread=2.10)

        # Total debit = 2.10 * 5 * 100 = 1050
        assert position.debit_total == 1050.0
        assert portfolio.cash == 100_000 - 1050.0
        assert len(portfolio.positions) == 1
        assert position in portfolio.positions

    def test_open_position_insufficient_cash_raises(self):
        portfolio = Portfolio(cash=100)
        candidate = _make_candidate(debit=2.00)
        with pytest.raises(ValueError, match="Insufficient cash"):
            open_position(portfolio, candidate, contracts=5, actual_debit_per_spread=2.00)

    def test_close_position_returns_capital(self):
        portfolio = Portfolio(cash=100_000)
        candidate = _make_candidate(debit=2.00)
        position = open_position(portfolio, candidate, contracts=5, actual_debit_per_spread=2.00)
        # Cash now: 100,000 - 1,000 = 99,000

        # Close at 2.50 per spread
        # Exit proceeds = 2.50 * 5 * 100 = 1,250
        # Less commissions = 1,250 - 13 = 1,237
        # PnL = 1,237 - 1,000 = 237
        pnl = close_position(portfolio, position, exit_value_per_spread=2.50, commissions=13.0)

        assert abs(pnl - 237.0) < 1e-9
        assert abs(portfolio.realized_pnl - 237.0) < 1e-9
        # Cash: 99,000 + 1,250 - 13 = 100,237
        assert abs(portfolio.cash - 100_237.0) < 1e-9
        assert len(portfolio.positions) == 0

    def test_equity_includes_deployed_capital(self):
        portfolio = Portfolio(cash=50_000)
        candidate = _make_candidate(debit=2.00)
        open_position(portfolio, candidate, contracts=5, actual_debit_per_spread=2.00)
        # Cash: 50,000 - 1,000 = 49,000
        # Deployed: 1,000
        # Equity should be 50,000
        assert portfolio.cash == 49_000.0
        assert portfolio.deployed_capital == 1_000.0
        assert portfolio.equity == 50_000.0


# ============================================================================
# Kelly fraction tests
# ============================================================================

class TestKellyFormula:
    """Verify Kelly fraction matches textbook values."""

    def test_symmetric_60pct_winrate_even_money(self):
        """
        Classic example: 60% win rate, 1:1 payoffs.
        f* = (p*W - q*L) / (W*L) = (0.6*1 - 0.4*1) / (1*1) = 0.20
        """
        f = kelly_optimal_fraction(win_rate=0.6, avg_win_pct=1.0, avg_loss_pct=1.0)
        assert abs(f - 0.20) < 1e-9

    def test_asymmetric_payoffs(self):
        """
        60% wins of 30%, 40% losses of 20%.
        f* = (0.6 * 0.3 - 0.4 * 0.2) / (0.3 * 0.2) = (0.18 - 0.08) / 0.06 = 1.667
        Capped at 1.0.
        """
        f = kelly_optimal_fraction(win_rate=0.6, avg_win_pct=0.30, avg_loss_pct=0.20)
        assert f == 1.0  # capped

    def test_realistic_calendar_strategy(self):
        """
        Author's claim: 60% wins of ~40% return, 40% losses of ~25% loss.
        f* = (0.6 * 0.4 - 0.4 * 0.25) / (0.4 * 0.25)
            = (0.24 - 0.10) / 0.10
            = 1.4
        Capped at 1.0. We multiply by KELLY_FRACTION (0.25) to get 0.25 effective.
        """
        f = kelly_optimal_fraction(win_rate=0.6, avg_win_pct=0.4, avg_loss_pct=0.25)
        assert f == 1.0  # full Kelly capped

    def test_negative_edge_returns_zero(self):
        """Losing strategy: 30% wins of 10%, 70% losses of 20%."""
        f = kelly_optimal_fraction(win_rate=0.3, avg_win_pct=0.10, avg_loss_pct=0.20)
        assert f == 0.0

    def test_invalid_inputs_return_zero(self):
        assert kelly_optimal_fraction(0.5, 0.0, 0.20) == 0.0  # zero avg_win
        assert kelly_optimal_fraction(0.5, 0.30, 0.0) == 0.0  # zero avg_loss
        assert kelly_optimal_fraction(0.0, 0.30, 0.20) == 0.0  # 0% win rate
        assert kelly_optimal_fraction(1.0, 0.30, 0.20) == 0.0  # 100% win rate (degenerate)

    def test_50pct_winrate_no_edge(self):
        """50% wins, equal payoffs = no edge -> Kelly = 0."""
        f = kelly_optimal_fraction(win_rate=0.5, avg_win_pct=0.20, avg_loss_pct=0.20)
        assert abs(f) < 1e-9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
