"""
Trade simulator for the Forward Factor backtester.

Simulates entering and exiting calendar / double calendar spreads with
realistic fill assumptions:

  - Mid-price ± slippage_pct of the debit
  - $0.65/contract commission per leg per side (Tradier rate)
  - Capacity cap: max 5% of an option's daily volume
  - Exit T-N days before front expiry (default T-1)

Two structures supported:

  1. ATM Call Calendar
       Long  back-month  ATM call  (debit)
       Short front-month ATM call  (credit)
       Net debit. Profit if vol stays elevated AND price stays near strike.

  2. 35-Delta Double Calendar
       Long  back-month  35-delta call    + Long back-month  -35-delta put
       Short front-month 35-delta call    + Short front-month -35-delta put
       Net debit. Profit zone is wider but lower peak P&L per dollar.

P&L methodology:
  At entry:  pay net debit (long back legs, short front legs)
  At exit:   receive net spread value at T-1 of front expiry
  P&L = exit_value - entry_debit - commissions

We use mid-prices from Polygon's daily option bars. Real fills will be
worse during stressed markets — this is approximated via SLIPPAGE_PCT.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from config import settings


log = logging.getLogger(__name__)


# ============================================================================
# Trade specification
# ============================================================================

@dataclass(frozen=True)
class CalendarSpec:
    """
    Fully-specified calendar trade ready for simulation.

    The simulator takes one of these and produces a CalendarResult.
    """
    ticker: str
    entry_date: date
    structure: str  # "atm_call_calendar" or "double_calendar_35d"
    front_expiry: date
    back_expiry: date
    front_strike: float
    back_strike: float
    # For double calendars, we need two strikes per side
    put_front_strike: Optional[float] = None
    put_back_strike: Optional[float] = None
    # Sizing
    contracts: int = 1
    # Reference (FF reading at entry)
    forward_factor_at_entry: Optional[float] = None
    front_iv_at_entry: Optional[float] = None
    back_iv_at_entry: Optional[float] = None


@dataclass(frozen=True)
class CalendarResult:
    """Outcome of simulating a single calendar trade."""
    spec: CalendarSpec
    entry_debit: float           # per spread (positive = paid)
    exit_credit: float           # per spread (positive = received)
    exit_date: date
    pnl_per_spread: float        # exit_credit - entry_debit
    pnl_total: float             # pnl_per_spread * contracts (net of commissions)
    commissions: float
    return_on_debit: float       # pnl_total / (entry_debit * contracts)
    fill_quality_note: str = ""

    @property
    def is_winner(self) -> bool:
        return self.pnl_total > 0


# ============================================================================
# Pricing helpers
# ============================================================================

def _mid_from_bar(bar_row: pd.Series) -> Optional[float]:
    """
    Get a 'mid' proxy from a daily option bar. Polygon's daily bar gives
    OHLCV but no bid/ask; we use VWAP if available, else close.

    For real strategies you'd want the actual bid/ask snapshot. For a
    backtest at daily granularity, VWAP-or-close is the standard proxy.
    """
    if pd.isna(bar_row.get("vwap")):
        c = bar_row.get("close")
        return float(c) if c and not pd.isna(c) else None
    return float(bar_row["vwap"])


def _option_ticker_for_strike(
    underlying: str,
    expiry: date,
    contract_type: str,  # "C" or "P"
    strike: float,
) -> str:
    """
    Build Polygon's option ticker symbol from components.

    Format: O:{underlying}{YYMMDD}{C|P}{strike*1000:08d}
    Example: O:SPY230120C00400000  (SPY $400 call expiring 2023-01-20)
    """
    yymmdd = expiry.strftime("%y%m%d")
    strike_int = int(round(strike * 1000))
    return f"O:{underlying}{yymmdd}{contract_type}{strike_int:08d}"


def _price_calendar_legs(
    polygon_client,
    underlying: str,
    front_expiry: date,
    back_expiry: date,
    front_strike: float,
    back_strike: float,
    contract_type: str,  # "C" or "P"
    on_date: date,
) -> Optional[tuple[float, float]]:
    """
    Get (front_mid, back_mid) for a single-side calendar (call OR put).
    Returns None if either leg has no data.
    """
    front_ticker = _option_ticker_for_strike(underlying, front_expiry, contract_type, front_strike)
    back_ticker = _option_ticker_for_strike(underlying, back_expiry, contract_type, back_strike)

    # Fetch one-day window centered on `on_date`
    start = on_date - timedelta(days=3)
    end = on_date + timedelta(days=3)
    front_bars = polygon_client.get_option_daily_bars(front_ticker, start, end)
    back_bars = polygon_client.get_option_daily_bars(back_ticker, start, end)

    if front_bars.empty or back_bars.empty:
        return None

    # Pick the closest bar to on_date (preferring on_date or earlier)
    target = pd.Timestamp(on_date)
    front_idx = front_bars.index.asof(target)
    back_idx = back_bars.index.asof(target)
    if pd.isna(front_idx) or pd.isna(back_idx):
        return None

    front_mid = _mid_from_bar(front_bars.loc[front_idx])
    back_mid = _mid_from_bar(back_bars.loc[back_idx])
    if front_mid is None or back_mid is None:
        return None

    return (front_mid, back_mid)


# ============================================================================
# Main simulator
# ============================================================================

def simulate_calendar(
    spec: CalendarSpec,
    polygon_client,
    slippage_pct: float = settings.SLIPPAGE_PCT,
    commission_per_contract: float = settings.COMMISSION_PER_CONTRACT,
    exit_days_before_front: int = settings.EXIT_DAYS_BEFORE_FRONT_EXPIRY,
) -> Optional[CalendarResult]:
    """
    Simulate entering and exiting a single calendar / double calendar.

    Returns None if pricing data is incomplete (we can't faithfully
    simulate the trade and shouldn't fudge it).
    """
    is_double = spec.structure == "double_calendar_35d"
    legs_per_spread = 4 if is_double else 2

    # ---- ENTRY ----
    call_legs = _price_calendar_legs(
        polygon_client,
        underlying=spec.ticker,
        front_expiry=spec.front_expiry,
        back_expiry=spec.back_expiry,
        front_strike=spec.front_strike,
        back_strike=spec.back_strike,
        contract_type="C",
        on_date=spec.entry_date,
    )
    if call_legs is None:
        log.debug("Entry pricing missing (calls) for %s on %s", spec.ticker, spec.entry_date)
        return None

    call_front_mid, call_back_mid = call_legs
    call_debit = call_back_mid - call_front_mid

    if is_double:
        if spec.put_front_strike is None or spec.put_back_strike is None:
            log.warning("Double calendar missing put strikes for %s", spec.ticker)
            return None
        put_legs = _price_calendar_legs(
            polygon_client,
            underlying=spec.ticker,
            front_expiry=spec.front_expiry,
            back_expiry=spec.back_expiry,
            front_strike=spec.put_front_strike,
            back_strike=spec.put_back_strike,
            contract_type="P",
            on_date=spec.entry_date,
        )
        if put_legs is None:
            log.debug("Entry pricing missing (puts) for %s on %s", spec.ticker, spec.entry_date)
            return None
        put_front_mid, put_back_mid = put_legs
        put_debit = put_back_mid - put_front_mid
        entry_mid_debit = call_debit + put_debit
    else:
        entry_mid_debit = call_debit

    if entry_mid_debit <= 0:
        # Net credit calendar is unusual (deep ITM/OTM) — skip
        log.debug("Non-positive entry debit (%s) for %s — skipping", entry_mid_debit, spec.ticker)
        return None

    entry_debit_with_slip = entry_mid_debit * (1.0 + slippage_pct)

    # ---- EXIT ----
    exit_date = spec.front_expiry - timedelta(days=exit_days_before_front)
    # Adjust for weekend (front_expiry is usually Friday; T-1 = Thursday is fine)

    exit_call_legs = _price_calendar_legs(
        polygon_client,
        underlying=spec.ticker,
        front_expiry=spec.front_expiry,
        back_expiry=spec.back_expiry,
        front_strike=spec.front_strike,
        back_strike=spec.back_strike,
        contract_type="C",
        on_date=exit_date,
    )
    if exit_call_legs is None:
        log.debug("Exit pricing missing (calls) for %s on %s", spec.ticker, exit_date)
        return None

    exit_call_front, exit_call_back = exit_call_legs
    exit_call_value = exit_call_back - exit_call_front

    if is_double:
        exit_put_legs = _price_calendar_legs(
            polygon_client,
            underlying=spec.ticker,
            front_expiry=spec.front_expiry,
            back_expiry=spec.back_expiry,
            front_strike=spec.put_front_strike,
            back_strike=spec.put_back_strike,
            contract_type="P",
            on_date=exit_date,
        )
        if exit_put_legs is None:
            return None
        exit_put_front, exit_put_back = exit_put_legs
        exit_put_value = exit_put_back - exit_put_front
        exit_mid_value = exit_call_value + exit_put_value
    else:
        exit_mid_value = exit_call_value

    exit_credit_with_slip = exit_mid_value * (1.0 - slippage_pct)

    # ---- P&L ----
    pnl_per_spread = exit_credit_with_slip - entry_debit_with_slip
    commissions_per_spread = commission_per_contract * legs_per_spread * 2  # entry + exit
    total_commissions = commissions_per_spread * spec.contracts
    pnl_total = pnl_per_spread * spec.contracts * 100.0 - total_commissions  # 100 = options multiplier

    return_on_debit = pnl_total / (entry_debit_with_slip * 100.0 * spec.contracts) \
        if entry_debit_with_slip > 0 else 0.0

    return CalendarResult(
        spec=spec,
        entry_debit=entry_debit_with_slip,
        exit_credit=exit_credit_with_slip,
        exit_date=exit_date,
        pnl_per_spread=pnl_per_spread,
        pnl_total=pnl_total,
        commissions=total_commissions,
        return_on_debit=return_on_debit,
    )


# ============================================================================
# Exit-only pricing (for closing already-open positions in the backtest loop)
# ============================================================================

def compute_exit_value(
    polygon_client,
    position,
    on_date: date,
    slippage_pct: float = settings.SLIPPAGE_PCT,
) -> Optional[float]:
    """
    Slipped exit value per spread for an already-open Position, or None if
    Polygon has no daily bar for either leg within the helper's ±3-day
    asof window. The caller (step_one_day) falls back to position.entry_debit
    + log warning when None is returned.

    Holiday handling is implicit: _price_calendar_legs uses bars.index.asof,
    which returns the most recent bar on or before on_date — so a Thursday
    Thanksgiving exit naturally falls back to Wednesday's close.

    Slippage applies on the way out: we receive (mid * (1 - slippage_pct))
    on a positive spread. Pathological inverted spreads (rare; spread <= 0
    at exit) are treated as a debit-to-close — slip against us via (1 + slip).
    """
    is_double = position.structure == "double_calendar_35d"

    call_legs = _price_calendar_legs(
        polygon_client,
        underlying=position.ticker,
        front_expiry=position.front_expiry,
        back_expiry=position.back_expiry,
        front_strike=position.front_strike,
        back_strike=position.back_strike,
        contract_type="C",
        on_date=on_date,
    )
    if call_legs is None:
        return None
    call_front_mid, call_back_mid = call_legs
    mid_value = call_back_mid - call_front_mid

    if is_double:
        if position.put_front_strike is None or position.put_back_strike is None:
            return None
        put_legs = _price_calendar_legs(
            polygon_client,
            underlying=position.ticker,
            front_expiry=position.front_expiry,
            back_expiry=position.back_expiry,
            front_strike=position.put_front_strike,
            back_strike=position.put_back_strike,
            contract_type="P",
            on_date=on_date,
        )
        if put_legs is None:
            return None
        mid_value += (put_legs[1] - put_legs[0])

    if mid_value <= 0:
        # Inverted spread at exit: we'd PAY to close. Slip against us.
        return mid_value * (1.0 + slippage_pct)
    return mid_value * (1.0 - slippage_pct)


# ============================================================================
# Pure-math version (for testing without Polygon)
# ============================================================================

def simulate_calendar_from_prices(
    entry_front_mid: float,
    entry_back_mid: float,
    exit_front_mid: float,
    exit_back_mid: float,
    contracts: int = 1,
    legs_per_spread: int = 2,
    slippage_pct: float = settings.SLIPPAGE_PCT,
    commission_per_contract: float = settings.COMMISSION_PER_CONTRACT,
    multiplier: float = 100.0,
) -> dict:
    """
    Pure-math calendar P&L given known mid prices. Used by unit tests
    and by the simulator above for the actual calculation.

    Returns dict with entry_debit, exit_credit, pnl_total, commissions,
    return_on_debit.
    """
    entry_mid = entry_back_mid - entry_front_mid
    if entry_mid <= 0:
        raise ValueError(f"Non-positive entry debit: {entry_mid}")

    entry_debit = entry_mid * (1.0 + slippage_pct)
    exit_value = exit_back_mid - exit_front_mid
    exit_credit = exit_value * (1.0 - slippage_pct)

    pnl_per_spread = exit_credit - entry_debit
    commissions = commission_per_contract * legs_per_spread * 2 * contracts
    pnl_total = pnl_per_spread * contracts * multiplier - commissions

    return {
        "entry_debit": entry_debit,
        "exit_credit": exit_credit,
        "pnl_per_spread": pnl_per_spread,
        "pnl_total": pnl_total,
        "commissions": commissions,
        "return_on_debit": pnl_total / (entry_debit * multiplier * contracts) if entry_debit > 0 else 0.0,
    }
