"""Discover candidates: walk every (date, ticker, cell), record raw FF + chain
context, with NO threshold filter and NO sizing. Output: candidates.parquet.

This is the slow, API-bound stage. Parallelized via ThreadPoolExecutor with
retry-on-429 backoff. Once cached, re-running is fast.

Schema (one row per (date, ticker, cell), even when one or both legs missing):
  date            (date)        — trading day
  ticker          (str)
  cell            (str)         — "30_90_atm" or "60_90_atm"
  front_dte       (int|nan)
  back_dte        (int|nan)
  front_strike    (float|nan)
  back_strike     (float|nan)
  front_expiry    (date|None)
  back_expiry     (date|None)
  front_close     (float|nan)
  back_close      (float|nan)
  front_iv        (float|nan)
  back_iv         (float|nan)
  underlying_close (float|nan)
  ff              (float|nan)   — raw, NO threshold filter
  estimated_debit (float|nan)
  back_leg_resolved (bool)
  earnings_blocked  (bool)      — would the earnings filter block this candidate?
  discovery_run_id  (str UUID)  — provenance tag
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from src.chain_resolver import resolve_atm_option
from src.data_layer import get_client
from src.earnings_filter import EarningsFilter
from src.ff_calculator import calculate_forward_factor

log = logging.getLogger(__name__)


def _trading_days(start: date, end: date) -> list[date]:
    out = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def _resolve_one(client, ticker: str, on_date: date, dte_front: int, dte_back: int,
                 ef: EarningsFilter, dte_buffer: int) -> dict:
    """Resolve one (ticker, date, cell) and return the candidate row.

    Always returns a dict (even if missing data) so the parquet records
    resolution status uniformly. Exceptions are caught and recorded.
    """
    row: dict = {
        "ticker": ticker,
        "front_dte": None, "back_dte": None,
        "front_strike": None, "back_strike": None,
        "front_expiry": None, "back_expiry": None,
        "front_close": None, "back_close": None,
        "front_iv": None, "back_iv": None,
        "underlying_close": None,
        "ff": None, "estimated_debit": None,
        "back_leg_resolved": False,
        "earnings_blocked": False,
    }
    # Earnings filter check (uses target back expiry approximation)
    target_back = on_date + timedelta(days=dte_back)
    try:
        if not ef.is_safe_window(ticker, on_date, target_back):
            row["earnings_blocked"] = True
    except Exception as e:
        log.debug("earnings check failed %s %s: %s", ticker, on_date, e)

    try:
        front = resolve_atm_option(client, ticker, on_date, dte_front,
                                    buffer_days=dte_buffer, contract_type="call")
    except Exception as e:
        log.debug("front resolution failed %s %s: %s", ticker, on_date, e)
        return row
    if front is None:
        return row

    row["front_dte"] = front.days_to_expiry
    row["front_strike"] = float(front.strike)
    row["front_expiry"] = front.expiration
    row["front_close"] = float(front.option_close)
    row["front_iv"] = float(front.implied_volatility) if front.implied_volatility > 0 else None
    row["underlying_close"] = float(front.underlying_price)

    try:
        back = resolve_atm_option(client, ticker, on_date, dte_back,
                                   buffer_days=dte_buffer, contract_type="call")
    except Exception as e:
        log.debug("back resolution failed %s %s: %s", ticker, on_date, e)
        return row
    if back is None:
        return row

    row["back_dte"] = back.days_to_expiry
    row["back_strike"] = float(back.strike)
    row["back_expiry"] = back.expiration
    row["back_close"] = float(back.option_close)
    row["back_iv"] = float(back.implied_volatility) if back.implied_volatility > 0 else None
    row["back_leg_resolved"] = True

    # Compute FF if both IVs valid
    if row["front_iv"] is not None and row["back_iv"] is not None:
        ff = calculate_forward_factor(
            dte_front=front.days_to_expiry,
            iv_front_pct=front.implied_volatility * 100.0,
            dte_back=back.days_to_expiry,
            iv_back_pct=back.implied_volatility * 100.0,
        )
        if ff.is_valid:
            row["ff"] = float(ff.forward_factor)
            row["estimated_debit"] = float(back.option_close - front.option_close)
    return row


def discover(
    start_date: date,
    end_date: date,
    universe: list[str],
    cells: list[tuple[str, int, int]],
    output_path: str | Path,
    max_workers: int = 12,
    dte_buffer: int = 5,
    progress_every: int = 200,
) -> tuple[str, pd.DataFrame]:
    """Run candidate discovery. Returns (discovery_run_id, candidates_df).

    Writes parquet to output_path."""
    client = get_client()
    ef = EarningsFilter(client)
    days = _trading_days(start_date, end_date)
    n_total = len(days) * len(universe) * len(cells)
    discovery_run_id = str(uuid.uuid4())

    print(f"[discover_candidates] run_id={discovery_run_id}", flush=True)
    print(f"  window: {start_date} -> {end_date}  ({len(days)} trading days)", flush=True)
    print(f"  universe: {len(universe)} tickers  |  cells: {[c[0] for c in cells]}", flush=True)
    print(f"  total samples: {n_total:,}  |  parallel workers: {max_workers}", flush=True)

    # Build the work list
    tasks = []
    for d in days:
        for ticker in universe:
            for cell_name, dte_f, dte_b in cells:
                tasks.append((d, ticker, cell_name, dte_f, dte_b))

    rows: list[dict] = []
    t0 = time.time()
    n_done = 0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_resolve_one, client, ticker, d, dte_f, dte_b, ef, dte_buffer):
                (d, ticker, cell_name)
            for (d, ticker, cell_name, dte_f, dte_b) in tasks
        }
        for fut in as_completed(futures):
            d, ticker, cell_name = futures[fut]
            try:
                row = fut.result()
            except Exception as e:
                log.warning("worker error %s %s %s: %s", ticker, d, cell_name, e)
                row = {"ticker": ticker, "back_leg_resolved": False,
                       "earnings_blocked": False, "ff": None, "estimated_debit": None,
                       "front_dte": None, "back_dte": None, "front_strike": None,
                       "back_strike": None, "front_expiry": None, "back_expiry": None,
                       "front_close": None, "back_close": None, "front_iv": None,
                       "back_iv": None, "underlying_close": None}
            row["date"] = d
            row["cell"] = cell_name
            row["discovery_run_id"] = discovery_run_id
            rows.append(row)
            n_done += 1
            if n_done % progress_every == 0:
                elapsed = time.time() - t0
                rate = n_done / elapsed
                eta = (n_total - n_done) / rate if rate > 0 else 0
                print(f"  [{n_done}/{n_total}] elapsed={elapsed:.0f}s rate={rate:.1f}/s eta={eta:.0f}s", flush=True)

    elapsed = time.time() - t0
    print(f"  done in {elapsed:.0f}s ({n_done/elapsed:.1f}/s)", flush=True)

    # Build DataFrame with stable column order
    cols = ["date", "ticker", "cell", "front_dte", "back_dte",
            "front_strike", "back_strike", "front_expiry", "back_expiry",
            "front_close", "back_close", "front_iv", "back_iv",
            "underlying_close", "ff", "estimated_debit",
            "back_leg_resolved", "earnings_blocked", "discovery_run_id"]
    df = pd.DataFrame(rows)
    df = df[cols].sort_values(["date", "ticker", "cell"]).reset_index(drop=True)

    # Write parquet
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"  wrote {out}  ({len(df):,} rows)", flush=True)

    # Summary
    n_resolved = int(df["back_leg_resolved"].sum())
    n_blocked = int(df["earnings_blocked"].sum())
    n_ff_valid = int(df["ff"].notna().sum())
    print(f"\nSummary:", flush=True)
    print(f"  total candidate slots:       {len(df):,}", flush=True)
    print(f"  back leg resolved:           {n_resolved:,}  ({100*n_resolved/len(df):.1f}%)", flush=True)
    print(f"  FF computable:               {n_ff_valid:,}  ({100*n_ff_valid/len(df):.1f}%)", flush=True)
    print(f"  earnings-blocked:            {n_blocked:,}  ({100*n_blocked/len(df):.1f}%)", flush=True)

    return discovery_run_id, df


# ============================================================================
# CLI
# ============================================================================

def _parse_args():
    ap = argparse.ArgumentParser(description="Discover candidates and write parquet.")
    ap.add_argument("--start", required=True, help="ISO start date e.g. 2022-01-03")
    ap.add_argument("--end", required=True, help="ISO end date e.g. 2026-04-30")
    ap.add_argument("--universe", required=True,
                    help="Comma-separated tickers, e.g. SPY,QQQ,IWM")
    ap.add_argument("--cells", default="30_90_atm:30:90,60_90_atm:60:90",
                    help="Comma-separated cell specs name:dte_front:dte_back")
    ap.add_argument("--out", required=True, help="Output parquet path")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--dte-buffer", type=int, default=5)
    return ap.parse_args()


def _main():
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout)
    args = _parse_args()
    universe = [t.strip().upper() for t in args.universe.split(",") if t.strip()]
    cells = []
    for spec in args.cells.split(","):
        parts = spec.strip().split(":")
        if len(parts) != 3:
            raise ValueError(f"Bad cell spec: {spec} (expected name:dte_front:dte_back)")
        cells.append((parts[0], int(parts[1]), int(parts[2])))
    discover(
        start_date=date.fromisoformat(args.start),
        end_date=date.fromisoformat(args.end),
        universe=universe, cells=cells,
        output_path=args.out, max_workers=args.workers,
        dte_buffer=args.dte_buffer,
    )


if __name__ == "__main__":
    _main()
