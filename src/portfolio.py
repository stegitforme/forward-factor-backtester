"""
Portfolio sizing for the Forward Factor backtester.

Implements the author's quarter-Kelly approach with our hedge-fund-grade
risk overrides:

  1. Per-trade max debit:  RISK_PER_TRADE (4%) of current equity
  2. Kelly fraction:       KELLY_FRACTION (0.25 = quarter Kelly)
  3. Max concurrent:       MAX_CONCURRENT_POSITIONS (12)
  4. Allocation priority:  highest FF first when capacity is constrained

Why quarter Kelly:

  Full Kelly maximizes log-wealth growth but only at infinite trade count
  with no parameter uncertainty. Real-world strategies have estimated
  win rates and payoffs (not known), so betting full Kelly on those
  estimates is overbetting in expectation. Half/quarter Kelly is the
  industry-standard penalty.

  Additionally, the author's strategy can have ~6 wins per 10 trades.
  At full Kelly with these inputs, drawdowns can exceed 50% — way above
  our max DD criterion of 25%. Quarter Kelly brings worst-case DD into
  range.

The "Kelly fraction" applied to RISK_PER_TRADE acts as a global de-risk
multiplier. So effective per-trade risk = RISK_PER_TRADE * KELLY_FRACTION
= 4% * 0.25 = 1% of equity. That means even if all 12 concurrent positions
go to zero simultaneously, max loss = 12% of portfolio — within the
ensemble DD limit.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from config import settings


log = logging.getLogger(__name__)


@dataclass
class Position:
    """An open calendar trade in the portfolio."""
    ticker: str
    structure: str
    entry_date: date
    front_expiry: date
    back_expiry: date
    contracts: int
    entry_debit: float           # per spread
    debit_total: float           # entry_debit * contracts * 100
    forward_factor_at_entry: float


@dataclass
class TradeCandidate:
    """A potential trade ready for sizing."""
    ticker: str
    structure: str
    entry_date: date
    front_expiry: date
    back_expiry: date
    estimated_debit_per_spread: float  # mid debit, per spread
    forward_factor: float
    front_strike: float
    back_strike: float
    put_front_strike: Optional[float] = None
    put_back_strike: Optional[float] = None


@dataclass
class Portfolio:
    """Tracks portfolio state across the backtest."""
    cash: float
    positions: list[Position] = field(default_factory=list)
    realized_pnl: float = 0.0

    @property
    def equity(self) -> float:
        """
        Total equity = cash + capital deployed in open positions
        (unrealized P&L not marked here; we use entry debit as a proxy
        for capital tied up).
        """
        deployed = sum(p.debit_total for p in self.positions)
        return self.cash + deployed

    @property
    def deployed_capital(self) -> float:
        return sum(p.debit_total for p in self.positions)

    @property
    def n_concurrent(self) -> int:
        return len(self.positions)


def size_trade(
    candidate: TradeCandidate,
    portfolio: Portfolio,
    risk_per_trade: float = settings.RISK_PER_TRADE,
    kelly_fraction: float = settings.KELLY_FRACTION,
    max_concurrent: int = settings.MAX_CONCURRENT_POSITIONS,
    multiplier: float = 100.0,
) -> int:
    """
    Compute the number of contracts to allocate to a candidate trade.

    Returns 0 if the trade should be skipped (capacity full, debit too small,
    insufficient cash, etc.).

    Args:
        candidate: The proposed trade.
        portfolio: Current portfolio state.
        risk_per_trade: Fraction of equity allowed as max debit per trade.
        kelly_fraction: Global Kelly down-scaling.
        max_concurrent: Max open positions.
        multiplier: Options multiplier (always 100 in standard markets).
    """
    # Concurrency cap
    if portfolio.n_concurrent >= max_concurrent:
        log.debug("Concurrency cap reached (%d), skipping %s",
                  portfolio.n_concurrent, candidate.ticker)
        return 0

    # Effective per-trade dollar risk
    effective_risk = risk_per_trade * kelly_fraction
    target_dollar_debit = portfolio.equity * effective_risk

    # Per-spread cost
    per_spread_cost = candidate.estimated_debit_per_spread * multiplier
    if per_spread_cost <= 0:
        return 0

    # Max contracts the dollar budget allows
    max_contracts_by_budget = int(target_dollar_debit // per_spread_cost)

    # Floor at 1 to avoid zero-sizing legitimate trades; cap if cash insufficient
    max_contracts_by_cash = int(portfolio.cash // per_spread_cost)

    contracts = min(max_contracts_by_budget, max_contracts_by_cash)
    if contracts < 1:
        log.debug("Trade too small for %s: per_spread=$%.2f, budget=$%.2f, cash=$%.2f",
                  candidate.ticker, per_spread_cost, target_dollar_debit, portfolio.cash)
        return 0

    return contracts


def select_top_candidates(
    candidates: list[TradeCandidate],
    portfolio: Portfolio,
    max_concurrent: int = settings.MAX_CONCURRENT_POSITIONS,
) -> list[TradeCandidate]:
    """
    When more candidates qualify than we have capacity for, pick the
    highest-FF setups. This is the standard 'allocate to strongest signal
    first' rule.

    Returns up to (max_concurrent - n_open) candidates sorted by FF desc.
    """
    available_slots = max_concurrent - portfolio.n_concurrent
    if available_slots <= 0:
        return []

    sorted_candidates = sorted(
        candidates, key=lambda c: c.forward_factor, reverse=True
    )
    return sorted_candidates[:available_slots]


def open_position(
    portfolio: Portfolio,
    candidate: TradeCandidate,
    contracts: int,
    actual_debit_per_spread: float,
    multiplier: float = 100.0,
) -> Position:
    """
    Open a new position: deduct debit from cash, append to positions list,
    return the Position object.
    """
    debit_total = actual_debit_per_spread * contracts * multiplier
    if debit_total > portfolio.cash:
        raise ValueError(
            f"Insufficient cash: need ${debit_total:.2f}, have ${portfolio.cash:.2f}"
        )

    position = Position(
        ticker=candidate.ticker,
        structure=candidate.structure,
        entry_date=candidate.entry_date,
        front_expiry=candidate.front_expiry,
        back_expiry=candidate.back_expiry,
        contracts=contracts,
        entry_debit=actual_debit_per_spread,
        debit_total=debit_total,
        forward_factor_at_entry=candidate.forward_factor,
    )
    portfolio.cash -= debit_total
    portfolio.positions.append(position)
    return position


def close_position(
    portfolio: Portfolio,
    position: Position,
    exit_value_per_spread: float,
    commissions: float,
    multiplier: float = 100.0,
) -> float:
    """
    Close a position: return capital to cash, realize P&L, remove from
    open positions, return the realized P&L for this trade.
    """
    exit_proceeds = exit_value_per_spread * position.contracts * multiplier
    pnl = exit_proceeds - position.debit_total - commissions

    portfolio.cash += exit_proceeds - commissions
    portfolio.realized_pnl += pnl

    if position in portfolio.positions:
        portfolio.positions.remove(position)

    return pnl


def kelly_optimal_fraction(
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
) -> float:
    """
    Generalized Kelly fraction for asymmetric payoffs.

    f* = (p * b - q) / b  for symmetric payoffs (b = win/loss ratio)

    Generalized for asymmetric returns:
        f* = (p * W - q * L) / (W * L)   where W = avg_win, L = avg_loss
        but this can give f* > 1, in which case we cap at 1.

    Args:
        win_rate:     P(win), e.g. 0.6 for 60% wins.
        avg_win_pct:  Average winning trade return as a fraction (e.g. 0.40).
        avg_loss_pct: Average losing trade return as a positive fraction
                      representing magnitude (e.g. 0.25 means avg loss is -25%).

    Returns:
        Optimal Kelly fraction in [0, 1]. Apply the user's KELLY_FRACTION
        multiplier on top of this for quarter/half Kelly sizing.
    """
    if avg_loss_pct <= 0 or avg_win_pct <= 0:
        return 0.0
    if not (0 < win_rate < 1):
        return 0.0

    p = win_rate
    q = 1.0 - win_rate
    W = avg_win_pct
    L = avg_loss_pct

    f = (p * W - q * L) / (W * L)
    return max(0.0, min(1.0, f))
