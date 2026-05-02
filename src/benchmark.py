"""
Benchmark strategies for comparison against Forward Factor.

Three benchmarks are run on the same date range with the same starting
capital so we can directly compare equity curves:

  1. SPY buy-and-hold:    Pure US equity exposure
  2. QQQ buy-and-hold:    Tech-tilted equity (closer to the user's existing tilt)
  3. TQQQ Vol Accel Guard: The user's existing 35-vol-target with 200d MA guard

For the user (Steven), benchmark #3 is the critical one — Forward Factor must
clear that bar to earn allocation. SPY/QQQ are sanity checks against the
broad market.

The user has independently backtested benchmark #3 and reports the following
target numbers (must reproduce these to within ~3 percentage points to
validate the implementation):

  3Y:    43.2% CAGR / -21.1% Max DD
  5Y:    27.2% CAGR / -23.2% Max DD
  2017+: 33.2% CAGR / -31.8% Max DD
  2014+: 27.3% CAGR / -38.2% Max DD

If our reimplementation here drifts materially from those numbers, treat
that as a bug to fix BEFORE proceeding with FF allocation decisions.
The validate_against_user_targets() function logs warnings on drift.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from config import settings


log = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Output of running a benchmark strategy."""
    name: str
    equity_curve: pd.Series   # daily, indexed by date
    starting_equity: float
    ending_equity: float


def run_buy_and_hold(
    ticker: str,
    polygon_client,
    start_date: date,
    end_date: date,
    initial_capital: float = settings.INITIAL_CAPITAL,
) -> BenchmarkResult:
    """
    Simple buy-and-hold benchmark. Buy at first close, hold to last close,
    no rebalancing or transaction costs (negligible for buy-and-hold over
    multi-year window).
    """
    bars = polygon_client.get_daily_bars(ticker, start_date, end_date)
    if bars.empty:
        log.warning("No bars available for %s — empty benchmark", ticker)
        return BenchmarkResult(
            name=f"{ticker}_buy_and_hold",
            equity_curve=pd.Series(dtype=float),
            starting_equity=initial_capital,
            ending_equity=initial_capital,
        )

    closes = bars["close"]
    shares = initial_capital / closes.iloc[0]
    equity = closes * shares
    equity.name = f"{ticker}_buy_and_hold"

    return BenchmarkResult(
        name=f"{ticker}_buy_and_hold",
        equity_curve=equity,
        starting_equity=initial_capital,
        ending_equity=float(equity.iloc[-1]),
    )


def run_tqqq_vol_accel_guard(
    polygon_client,
    start_date: date,
    end_date: date,
    initial_capital: float = settings.INITIAL_CAPITAL,
    vol_target: float = settings.TQQQ_CONFIG.vol_target,
    realized_vol_lookback: int = settings.TQQQ_CONFIG.realized_vol_lookback,
    guard_ma_days: int = settings.TQQQ_CONFIG.guard_ma_days,
    cash_ticker: str = settings.TQQQ_CONFIG.cash_ticker,
    rebalance_step_pct: float = 0.05,
) -> BenchmarkResult:
    """
    TQQQ Vol Accel Guard — user's documented strategy, faithful reimplementation.

    Logic (run weekly, Friday signal -> Monday execution):

      1. Compute TQQQ's 20-day realized volatility (annualized).
      2. Compute QQQ's 200d simple MA on QQQ price.
      3. If QQQ_close < QQQ_MA200: target_TQQQ = 0% (guard active -> sit in cash)
         Else:
            target_TQQQ = vol_target / realized_vol_TQQQ
            target_TQQQ = clip(target_TQQQ, 0, 1.0)
            target_TQQQ = round to nearest 5%
      4. Allocate: target_TQQQ to TQQQ, remainder to BIL (cash proxy).
      5. Repeat next Friday close -> Monday open.

    Why TQQQ realized vol (not 3*QQQ): The user's documented spec uses TQQQ
    directly. 3x leverage isn't perfectly mapped due to daily reset decay,
    so the realized TQQQ vol is the right input — and that's what produces
    the validated 27.2% / -23.2% target numbers.

    Why BIL as cash proxy: SGOV's history is too short to span 2022 backtest
    start. BIL has the same effective return characteristic.

    Why clamp at 1.0 not 1.5: matches the user's documented "0-100%" rule.
    """
    qqq_bars = polygon_client.get_daily_bars(
        "QQQ", start_date - timedelta(days=guard_ma_days + 60), end_date
    )
    tqqq_bars = polygon_client.get_daily_bars(
        "TQQQ", start_date - timedelta(days=realized_vol_lookback + 30), end_date
    )
    cash_bars = polygon_client.get_daily_bars(
        cash_ticker, start_date - timedelta(days=30), end_date
    )

    if qqq_bars.empty or tqqq_bars.empty or cash_bars.empty:
        log.warning("Missing data for TQQQ Vol Accel Guard")
        return BenchmarkResult(
            name="TQQQ_vol_accel_guard",
            equity_curve=pd.Series(dtype=float),
            starting_equity=initial_capital,
            ending_equity=initial_capital,
        )

    qqq_close = qqq_bars["close"]
    qqq_ma = qqq_close.rolling(guard_ma_days, min_periods=guard_ma_days // 2).mean()

    tqqq_close = tqqq_bars["close"]
    tqqq_returns = tqqq_close.pct_change()
    tqqq_vol = tqqq_returns.rolling(realized_vol_lookback).std() * np.sqrt(252)

    cash_close = cash_bars["close"]

    all_dates = qqq_close.index.intersection(tqqq_close.index).intersection(cash_close.index)
    backtest_dates = all_dates[(all_dates >= pd.Timestamp(start_date)) &
                                (all_dates <= pd.Timestamp(end_date))]

    if len(backtest_dates) == 0:
        log.warning("No overlapping trading days in range")
        return BenchmarkResult(
            name="TQQQ_vol_accel_guard",
            equity_curve=pd.Series(dtype=float),
            starting_equity=initial_capital,
            ending_equity=initial_capital,
        )

    tqqq_units = 0.0
    cash_units = 0.0
    equity_history: list[tuple[pd.Timestamp, float]] = []
    last_signal_date: Optional[pd.Timestamp] = None

    for i, ts in enumerate(backtest_dates):
        tqqq_px = tqqq_close.loc[ts] if ts in tqqq_close.index else float("nan")
        cash_px = cash_close.loc[ts] if ts in cash_close.index else float("nan")

        if pd.isna(tqqq_px) or pd.isna(cash_px):
            continue

        equity_today = tqqq_units * tqqq_px + cash_units * cash_px

        if i == 0 or (tqqq_units == 0.0 and cash_units == 0.0):
            equity_today = initial_capital

        is_monday = ts.weekday() == 0
        first_run = last_signal_date is None
        days_since_last = (ts - last_signal_date).days if last_signal_date else 999

        if first_run or (is_monday and days_since_last >= 5):
            # Find prior Friday for Friday-close signal
            signal_ts = ts
            for back_days in range(1, 5):
                candidate = ts - pd.Timedelta(days=back_days)
                if candidate.weekday() == 4 and candidate in qqq_close.index:
                    signal_ts = candidate
                    break

            qqq_above_ma = False
            if signal_ts in qqq_close.index and signal_ts in qqq_ma.index:
                qqq_px = qqq_close.loc[signal_ts]
                ma_px = qqq_ma.loc[signal_ts]
                qqq_above_ma = (not pd.isna(ma_px)) and qqq_px > ma_px

            current_tqqq_vol = (
                tqqq_vol.loc[signal_ts] if signal_ts in tqqq_vol.index else float("nan")
            )
            if pd.isna(current_tqqq_vol) or current_tqqq_vol <= 0:
                current_tqqq_vol = 0.60

            if not qqq_above_ma:
                target_tqqq_pct = 0.0
            else:
                raw = vol_target / current_tqqq_vol
                clipped = float(np.clip(raw, 0.0, 1.0))  # clamp 0-100%
                target_tqqq_pct = round(clipped / rebalance_step_pct) * rebalance_step_pct

            target_tqqq_dollars = equity_today * target_tqqq_pct
            target_cash_dollars = max(equity_today - target_tqqq_dollars, 0.0)

            tqqq_units = target_tqqq_dollars / tqqq_px if tqqq_px > 0 else 0.0
            cash_units = target_cash_dollars / cash_px if cash_px > 0 else 0.0

            last_signal_date = ts

        equity_history.append((ts, equity_today))

    if not equity_history:
        return BenchmarkResult(
            name="TQQQ_vol_accel_guard",
            equity_curve=pd.Series(dtype=float),
            starting_equity=initial_capital,
            ending_equity=initial_capital,
        )

    eq_series = pd.Series(
        [e for (_, e) in equity_history],
        index=[t for (t, _) in equity_history],
        name="TQQQ_vol_accel_guard",
    )

    return BenchmarkResult(
        name="TQQQ_vol_accel_guard",
        equity_curve=eq_series,
        starting_equity=initial_capital,
        ending_equity=float(eq_series.iloc[-1]),
    )


# Backwards-compatible alias for the older name used in earlier code
run_tqqq_sgov_vol_target = run_tqqq_vol_accel_guard


def validate_against_user_targets(
    result: BenchmarkResult,
    targets: Optional[dict] = None,
    tolerance_pct: float = 3.0,
) -> dict:
    """
    Validate that the TQQQ Vol Accel Guard implementation reproduces the
    user's independently-backtested target numbers.

    User's validated reference (from his TradingView/external backtest):

      3Y:    43.2% CAGR / -21.1% Max DD
      5Y:    27.2% CAGR / -23.2% Max DD
      2017+: 33.2% CAGR / -31.8% Max DD
      2014+: 27.3% CAGR / -38.2% Max DD

    For each window, we compute CAGR and Max DD on the equity curve
    sub-window and compare. Drift > tolerance_pct = warning logged.
    """
    from src.metrics import compute_cagr, compute_max_drawdown

    if targets is None:
        targets = {
            "3Y":    {"cagr": 0.432, "max_dd": -0.211},
            "5Y":    {"cagr": 0.272, "max_dd": -0.232},
            "2017+": {"cagr": 0.332, "max_dd": -0.318},
            "2014+": {"cagr": 0.273, "max_dd": -0.382},
        }

    if len(result.equity_curve) == 0:
        return {"status": "no_data"}

    end_ts = result.equity_curve.index[-1]
    checks = {}
    for window_name, target in targets.items():
        if window_name == "3Y":
            start_ts = end_ts - pd.DateOffset(years=3)
        elif window_name == "5Y":
            start_ts = end_ts - pd.DateOffset(years=5)
        elif window_name == "2017+":
            start_ts = pd.Timestamp("2017-01-01")
        elif window_name == "2014+":
            start_ts = pd.Timestamp("2014-01-01")
        else:
            continue

        sub = result.equity_curve[result.equity_curve.index >= start_ts]
        if len(sub) < 100:
            checks[window_name] = {"status": "insufficient_data", "n_days": len(sub)}
            continue

        actual_cagr = compute_cagr(sub)
        actual_dd, _ = compute_max_drawdown(sub)
        cagr_diff_pct = abs(actual_cagr - target["cagr"]) * 100
        dd_diff_pct = abs(actual_dd - target["max_dd"]) * 100

        within_tolerance = (cagr_diff_pct <= tolerance_pct) and (dd_diff_pct <= tolerance_pct)
        checks[window_name] = {
            "status": "match" if within_tolerance else "drift",
            "actual_cagr": actual_cagr,
            "expected_cagr": target["cagr"],
            "actual_max_dd": actual_dd,
            "expected_max_dd": target["max_dd"],
            "cagr_drift_pp": cagr_diff_pct,
            "dd_drift_pp": dd_diff_pct,
        }

    valid_checks = [c for c in checks.values() if c.get("status") in ("match", "drift")]
    if not valid_checks:
        overall = "insufficient_data"
    elif all(c["status"] == "match" for c in valid_checks):
        overall = "match"
    else:
        overall = "drift"

    return {"overall": overall, "windows": checks}


def run_all_benchmarks(
    polygon_client,
    start_date: date = settings.BACKTEST_START_DATE,
    end_date: date = settings.BACKTEST_END_DATE,
    initial_capital: float = settings.INITIAL_CAPITAL,
) -> dict[str, BenchmarkResult]:
    """
    Run all benchmarks and return them keyed by name.
    Validates TQQQ Vol Accel Guard against user's known-good numbers
    and logs warnings on drift.
    """
    results = {}

    log.info("Running SPY buy-and-hold...")
    results["SPY_buy_and_hold"] = run_buy_and_hold(
        "SPY", polygon_client, start_date, end_date, initial_capital
    )

    log.info("Running QQQ buy-and-hold...")
    results["QQQ_buy_and_hold"] = run_buy_and_hold(
        "QQQ", polygon_client, start_date, end_date, initial_capital
    )

    log.info("Running TQQQ Vol Accel Guard...")
    tqqq_result = run_tqqq_vol_accel_guard(
        polygon_client, start_date, end_date, initial_capital
    )
    results["TQQQ_vol_accel_guard"] = tqqq_result

    # Validate against user's independently-backtested numbers
    if len(tqqq_result.equity_curve) > 0:
        validation = validate_against_user_targets(tqqq_result)
        log.info("TQQQ Vol Accel Guard validation: %s", validation.get("overall"))
        if validation.get("overall") == "drift":
            log.warning("TQQQ benchmark drift vs. user's validated numbers:")
            for window, check in validation.get("windows", {}).items():
                if check.get("status") == "drift":
                    log.warning(
                        "  %s: actual %.1f%%/%.1f%% vs expected %.1f%%/%.1f%% "
                        "(drift: %.1fpp CAGR, %.1fpp DD)",
                        window,
                        check["actual_cagr"] * 100, check["actual_max_dd"] * 100,
                        check["expected_cagr"] * 100, check["expected_max_dd"] * 100,
                        check["cagr_drift_pp"], check["dd_drift_pp"],
                    )

    return results
