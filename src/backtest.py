"""
Main backtest orchestrator for the Forward Factor strategy.

Walks the backtest window day by day, doing for each trading day:

  1. Maintain universe (refreshed every UNIVERSE_REFRESH_DAYS).
  2. Close any positions whose front expiry is within EXIT_DAYS_BEFORE.
  3. For each name in the universe:
       a. Pull near-the-money options chain at the configured DTE pairs.
       b. Compute Forward Factor.
       c. If FF >= threshold AND not blocked by earnings, queue a candidate.
  4. Rank candidates by FF, allocate capacity, size with quarter-Kelly.
  5. Open new positions, deduct cash.
  6. Mark to market, record equity for the day.

Outputs:
  - 6-cell results: per (DTE pair × structure) — separate equity curves
  - Equal-weighted ensemble across the 6 cells
  - Trade log per cell
  - Summary metrics table

This is the orchestration glue; the real work is delegated to the
existing modules (universe, ff_calculator, trade_simulator, portfolio).

Note: Production-grade implementation requires substantial Polygon
integration and ATM-strike resolution that depends on actual chain data.
This file provides the loop structure and high-level API; the per-day
trade discovery hook is a stub that you fill in once Polygon is wired up.
The Colab runner shows how to drive this end-to-end.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from config import settings
from src.earnings_filter import EarningsFilter
from src.ff_calculator import calculate_forward_factor
from src.portfolio import (
    Portfolio,
    TradeCandidate,
    close_position,
    open_position,
    select_top_candidates,
    size_trade,
)
from src.trade_simulator import CalendarSpec, simulate_calendar
from src.universe import Universe, compute_options_volume_universe


log = logging.getLogger(__name__)


# ============================================================================
# Cell configuration: each cell is one (DTE pair × structure) combination
# ============================================================================

@dataclass(frozen=True)
class Cell:
    """One backtest cell: a specific (DTE pair × structure) combination."""
    name: str
    dte_front: int
    dte_back: int
    structure: str  # "atm_call_calendar" or "double_calendar_35d"


def all_cells() -> list[Cell]:
    """Build all 6 cells of the parameter grid."""
    cells = []
    for (dte1, dte2) in settings.DTE_PAIRS:
        for structure in settings.STRUCTURES:
            short = "atm" if structure == "atm_call_calendar" else "dbl"
            cells.append(Cell(
                name=f"{dte1}_{dte2}_{short}",
                dte_front=dte1,
                dte_back=dte2,
                structure=structure,
            ))
    return cells


# ============================================================================
# Backtest result containers
# ============================================================================

@dataclass
class CellResult:
    """Output of running a single cell across the full backtest window."""
    cell: Cell
    equity_curve: pd.Series
    trade_log: pd.DataFrame
    final_equity: float


@dataclass
class BacktestResult:
    """Full output: one CellResult per cell, plus the equal-weighted ensemble."""
    cell_results: dict[str, CellResult]   # keyed by cell.name
    ensemble_curve: pd.Series
    ensemble_trade_log: pd.DataFrame


# ============================================================================
# Per-day candidate discovery (the hot loop)
# ============================================================================

def find_candidates_for_day(
    today: date,
    universe: Universe,
    cell: Cell,
    polygon_client,
    earnings_filter: EarningsFilter,
    ff_threshold: float = settings.FF_THRESHOLD,
    dte_buffer: int = settings.DTE_BUFFER_DAYS,
) -> list[TradeCandidate]:
    """
    For each name in the universe, check if there's a tradeable FF setup
    at the configured DTE pair. Returns a list of TradeCandidate.

    Real implementation: uses chain_resolver to find ATM/35-delta
    contracts at the front and back DTEs, computes IV from option close
    prices via Black-Scholes inversion, and computes Forward Factor.
    Earnings-blocked names are skipped before any Polygon calls to
    minimize API cost.
    """
    from src.chain_resolver import resolve_atm_option, resolve_delta_option
    from src.ff_calculator import calculate_forward_factor

    candidates: list[TradeCandidate] = []
    is_double = cell.structure == "double_calendar_35d"

    for entry in universe.entries:
        ticker = entry.ticker

        # Earnings filter first (cheap, no Polygon call)
        target_back_expiry = today + timedelta(days=cell.dte_back)
        if not earnings_filter.is_safe_window(ticker, today, target_back_expiry):
            continue

        try:
            # Resolve front and back legs (calls)
            front_call = resolve_atm_option(
                polygon_client, ticker, today, cell.dte_front,
                buffer_days=dte_buffer, contract_type="call",
            )
            if front_call is None or not (front_call.implied_volatility > 0):
                continue

            back_call = resolve_atm_option(
                polygon_client, ticker, today, cell.dte_back,
                buffer_days=dte_buffer, contract_type="call",
            )
            if back_call is None or not (back_call.implied_volatility > 0):
                continue

            # Compute Forward Factor from the call IVs
            # Note: iv_solver returns decimals (0.38), FF calculator
            # expects percentages (38.0)
            ff_result = calculate_forward_factor(
                dte_front=front_call.days_to_expiry,
                iv_front_pct=front_call.implied_volatility * 100.0,
                dte_back=back_call.days_to_expiry,
                iv_back_pct=back_call.implied_volatility * 100.0,
            )
            if not ff_result.is_valid:
                continue
            if ff_result.forward_factor < ff_threshold:
                continue

            # Estimated debit per spread (mid)
            estimated_debit = back_call.option_close - front_call.option_close
            if estimated_debit <= 0:
                continue

            # For double calendars, also resolve put legs at -35 delta
            put_front_strike: Optional[float] = None
            put_back_strike: Optional[float] = None
            if is_double:
                front_put = resolve_delta_option(
                    polygon_client, ticker, today, cell.dte_front,
                    target_delta=-0.35, contract_type="put",
                    buffer_days=dte_buffer,
                )
                back_put = resolve_delta_option(
                    polygon_client, ticker, today, cell.dte_back,
                    target_delta=-0.35, contract_type="put",
                    buffer_days=dte_buffer,
                )
                if front_put is None or back_put is None:
                    continue
                if not (front_put.option_close > 0 and back_put.option_close > 0):
                    continue
                put_debit = back_put.option_close - front_put.option_close
                if put_debit <= 0:
                    continue
                put_front_strike = front_put.strike
                put_back_strike = back_put.strike
                # Also recompute call leg at +35 delta to mirror the structure
                front_call_d = resolve_delta_option(
                    polygon_client, ticker, today, cell.dte_front,
                    target_delta=0.35, contract_type="call",
                    buffer_days=dte_buffer,
                )
                back_call_d = resolve_delta_option(
                    polygon_client, ticker, today, cell.dte_back,
                    target_delta=0.35, contract_type="call",
                    buffer_days=dte_buffer,
                )
                if front_call_d is None or back_call_d is None:
                    continue
                # Combined debit: call calendar + put calendar
                call_debit_d = back_call_d.option_close - front_call_d.option_close
                if call_debit_d <= 0:
                    continue
                estimated_debit = call_debit_d + put_debit
                # Use the 35-delta call strikes for the spec
                front_strike = front_call_d.strike
                back_strike = back_call_d.strike
            else:
                front_strike = front_call.strike
                back_strike = back_call.strike

            candidates.append(TradeCandidate(
                ticker=ticker,
                structure=cell.structure,
                entry_date=today,
                front_expiry=front_call.expiration,
                back_expiry=back_call.expiration,
                estimated_debit_per_spread=estimated_debit,
                forward_factor=ff_result.forward_factor,
                front_strike=front_strike,
                back_strike=back_strike,
                put_front_strike=put_front_strike,
                put_back_strike=put_back_strike,
            ))
        except Exception as e:
            # Log and skip — one bad ticker shouldn't kill the day
            log.debug("Candidate resolution failed for %s on %s: %s",
                      ticker, today, e)
            continue

    return candidates


# ============================================================================
# Position lifecycle for a single cell
# ============================================================================

def step_one_day(
    today: date,
    cell: Cell,
    portfolio: Portfolio,
    universe: Universe,
    polygon_client,
    earnings_filter: EarningsFilter,
    trade_log: list[dict],
) -> None:
    """
    Process one trading day for one cell:
      1. Close expiring positions
      2. Discover candidates
      3. Allocate capacity
      4. Open new positions
    """
    # Step 1: close positions whose front expiry is at T-EXIT
    exit_threshold_date = today + timedelta(days=settings.EXIT_DAYS_BEFORE_FRONT_EXPIRY)
    for position in list(portfolio.positions):
        if position.front_expiry <= exit_threshold_date:
            # Simulate the exit
            spec = CalendarSpec(
                ticker=position.ticker,
                entry_date=position.entry_date,
                structure=position.structure,
                front_expiry=position.front_expiry,
                back_expiry=position.back_expiry,
                front_strike=0.0,  # placeholder; real impl tracks strikes
                back_strike=0.0,
                contracts=position.contracts,
                forward_factor_at_entry=position.forward_factor_at_entry,
            )
            # In a full impl, we'd re-query exit prices here.
            # For now we approximate exit at parity (no P&L) — replace with
            # actual simulate_calendar() call once Polygon chain queries
            # are wired up.
            exit_value = position.entry_debit  # break-even placeholder
            commissions = settings.COMMISSION_PER_CONTRACT * 4 * position.contracts * 2
            pnl = close_position(portfolio, position, exit_value, commissions)
            # Find the matching open row (logged when position was opened)
            # and update it with exit info instead of duplicating.
            updated = False
            for row in trade_log:
                if (
                    row.get("ticker") == position.ticker
                    and row.get("entry_date") == position.entry_date
                    and row.get("structure") == position.structure
                    and row.get("exit_date") is None
                ):
                    row["exit_date"] = today
                    row["pnl_total"] = pnl
                    updated = True
                    break
            if not updated:
                # Defensive fallback (shouldn't happen but guards against
                # log/state mismatches)
                trade_log.append({
                    "ticker": position.ticker,
                    "structure": position.structure,
                    "entry_date": position.entry_date,
                    "exit_date": today,
                    "front_expiry": position.front_expiry,
                    "back_expiry": position.back_expiry,
                    "contracts": position.contracts,
                    "entry_debit": position.entry_debit,
                    "forward_factor_at_entry": position.forward_factor_at_entry,
                    "pnl_total": pnl,
                })

    # Step 2: find candidates for this cell
    candidates = find_candidates_for_day(
        today, universe, cell, polygon_client, earnings_filter
    )

    # Step 3: select top candidates by FF, respecting capacity
    selected = select_top_candidates(candidates, portfolio)

    # Step 4: open positions
    for candidate in selected:
        contracts = size_trade(candidate, portfolio)
        if contracts < 1:
            continue
        try:
            open_position(
                portfolio, candidate, contracts,
                actual_debit_per_spread=candidate.estimated_debit_per_spread
            )
            # Log the open immediately so smoke tests and short windows
            # see trades. pnl_total=NaN signals "still open"; will be
            # updated on close. compute_trade_stats() filters these out.
            trade_log.append({
                "ticker": candidate.ticker,
                "structure": candidate.structure,
                "entry_date": today,
                "exit_date": None,
                "front_expiry": candidate.front_expiry,
                "back_expiry": candidate.back_expiry,
                "contracts": contracts,
                "entry_debit": candidate.estimated_debit_per_spread,
                "forward_factor_at_entry": candidate.forward_factor,
                "pnl_total": float("nan"),
            })
        except ValueError as e:
            log.warning("Could not open %s: %s", candidate.ticker, e)


# ============================================================================
# Single-cell backtest
# ============================================================================

def run_cell_backtest(
    cell: Cell,
    polygon_client,
    earnings_filter: EarningsFilter,
    start_date: date = settings.BACKTEST_START_DATE,
    end_date: date = settings.BACKTEST_END_DATE,
    initial_capital: float = settings.INITIAL_CAPITAL,
    smoke_universe: Optional[list[str]] = None,
    show_progress: bool = True,
) -> CellResult:
    """
    Run the backtest for a single cell. Returns equity curve and trade log.

    Args:
        smoke_universe: If provided, override the universe with this static
            list of tickers (no liquidity filtering, no Polygon universe
            calls). Used by smoke-mode runs.
        show_progress: If True, display a tqdm progress bar over trading days.
    """
    log.info("Running cell %s from %s to %s", cell.name, start_date, end_date)

    portfolio = Portfolio(cash=initial_capital)
    trade_log: list[dict] = []
    equity_history: list[tuple[date, float]] = []

    # Universe: refresh on cadence
    universe: Optional[Universe] = None
    last_universe_date: Optional[date] = None

    # If smoke_universe provided, build a stub Universe and skip refresh
    if smoke_universe is not None:
        from src.universe import UniverseEntry
        # Build a stub universe with last_close=100 (placeholder; not used
        # by the strategy logic — only the FF math + chain resolver use the
        # actual underlying close which they fetch fresh from Polygon)
        universe = Universe(
            snapshot_date=start_date,
            entries=tuple(
                UniverseEntry(
                    ticker=t,
                    avg_daily_option_volume=100_000,
                    last_close=100.0,
                    snapshot_date=start_date,
                )
                for t in smoke_universe
            ),
        )
        last_universe_date = start_date

    # Build the list of trading days first so we can show a proper progress bar
    trading_days: list[date] = []
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5:
            trading_days.append(cursor)
        cursor += timedelta(days=1)

    iterator = trading_days
    if show_progress:
        try:
            from tqdm.auto import tqdm
            iterator = tqdm(
                trading_days,
                desc=f"Cell {cell.name}",
                unit="day",
                leave=True,
            )
        except ImportError:
            pass

    for today in iterator:
        # Refresh universe (skip if smoke_universe was provided)
        if smoke_universe is None and (
            universe is None
            or last_universe_date is None
            or (today - last_universe_date).days >= settings.UNIVERSE_REFRESH_DAYS
        ):
            try:
                universe = compute_options_volume_universe(
                    as_of=today, polygon_client=polygon_client
                )
                last_universe_date = today
            except Exception as e:
                log.warning("Universe refresh failed on %s: %s", today, e)
                if universe is None:
                    continue

        # Process the day
        step_one_day(today, cell, portfolio, universe, polygon_client,
                     earnings_filter, trade_log)

        # Mark equity
        equity_history.append((today, portfolio.equity))

    # Build outputs
    equity_curve = pd.Series(
        [e for (_, e) in equity_history],
        index=pd.to_datetime([t for (t, _) in equity_history]),
        name=cell.name,
    )
    trade_df = pd.DataFrame(trade_log)

    return CellResult(
        cell=cell,
        equity_curve=equity_curve,
        trade_log=trade_df,
        final_equity=float(equity_curve.iloc[-1]) if len(equity_curve) > 0 else initial_capital,
    )


# ============================================================================
# Multi-cell driver
# ============================================================================

def run_full_backtest(
    polygon_client,
    earnings_filter: Optional[EarningsFilter] = None,
    start_date: date = settings.BACKTEST_START_DATE,
    end_date: date = settings.BACKTEST_END_DATE,
    initial_capital: float = settings.INITIAL_CAPITAL,
    smoke_mode: bool = False,
    smoke_tickers: Optional[list[str]] = None,
    smoke_days: int = 30,
    show_progress: bool = True,
) -> BacktestResult:
    """
    Run all 6 cells + ensemble. Returns BacktestResult.

    Args:
        smoke_mode: If True, run a tiny version for sanity checking — only
            uses `smoke_tickers` and only over `smoke_days` calendar days
            starting from `start_date`. Bypasses universe selection.
        smoke_tickers: Optional override of smoke universe (default: 3 names).
        smoke_days: Number of calendar days to run in smoke mode (default 30).
        show_progress: Display tqdm progress bars during the run.
    """
    if earnings_filter is None:
        earnings_filter = EarningsFilter(polygon_client)

    cells = all_cells()
    cell_results: dict[str, CellResult] = {}

    if smoke_mode:
        if smoke_tickers is None:
            smoke_tickers = ["AAPL", "TSLA", "NVDA"]
        actual_end = start_date + timedelta(days=smoke_days)
        log.info(
            "SMOKE MODE: %d tickers (%s) over %d days (%s -> %s)",
            len(smoke_tickers), smoke_tickers, smoke_days,
            start_date, actual_end,
        )
        end_to_use = actual_end
    else:
        smoke_tickers = None
        end_to_use = end_date

    cell_iter = cells
    if show_progress:
        try:
            from tqdm.auto import tqdm
            cell_iter = tqdm(cells, desc="Cells", unit="cell", position=0)
        except ImportError:
            pass

    for cell in cell_iter:
        result = run_cell_backtest(
            cell, polygon_client, earnings_filter,
            start_date, end_to_use, initial_capital,
            smoke_universe=smoke_tickers,
            show_progress=show_progress,
        )
        cell_results[cell.name] = result

    # Build ensemble
    ensemble = _build_ensemble(cell_results, initial_capital)
    ensemble_log = _combine_trade_logs(cell_results)

    return BacktestResult(
        cell_results=cell_results,
        ensemble_curve=ensemble,
        ensemble_trade_log=ensemble_log,
    )


def _build_ensemble(
    cell_results: dict[str, CellResult],
    initial_capital: float,
) -> pd.Series:
    """
    Equal-weighted ensemble: at each date, average the normalized equity
    of all cells. Normalize so each cell starts at 1.0, then average,
    then scale by initial_capital.
    """
    if not cell_results:
        return pd.Series(dtype=float)

    normalized = []
    for name, res in cell_results.items():
        if len(res.equity_curve) == 0:
            continue
        norm = res.equity_curve / res.equity_curve.iloc[0]
        norm.name = name
        normalized.append(norm)

    if not normalized:
        return pd.Series(dtype=float)

    df = pd.concat(normalized, axis=1).ffill()
    avg = df.mean(axis=1) * initial_capital
    avg.name = "ensemble"
    return avg


def _combine_trade_logs(cell_results: dict[str, CellResult]) -> pd.DataFrame:
    """Concatenate all cell trade logs with a 'cell' column."""
    rows = []
    for name, res in cell_results.items():
        if res.trade_log.empty:
            continue
        df = res.trade_log.copy()
        df["cell"] = name
        rows.append(df)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)
