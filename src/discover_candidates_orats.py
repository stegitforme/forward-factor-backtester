"""ORATS-backed candidate discovery.

Mirror of src/discover_candidates.py but reads from ORATS daily ZIPs
(via src.adapters.orats_adapter) instead of Polygon API. Output parquet
schema is identical so src/simulate_portfolio.py consumes either one.

Two discovery variants, parameterized by `iv_column`:
  - "smoothSmvVol" — VV-faithful: uses ORATS' smoothed surface IV (closest
    analog to Polygon BS-inverted IV). Use earnings filter on top.
  - "extVol"      — Path A: uses ORATS' ex-earnings IV (earnings event vol
    contribution stripped out). Earnings filter optional / off.

Provenance: each candidate row carries `iv_source` so simulate / reporting
can tell which IV variant produced the row.
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

from src.adapters import orats_adapter as orats
from src.earnings_filter import EarningsFilter
from src.ff_calculator import calculate_forward_factor

log = logging.getLogger(__name__)


SUPPORTED_IV_COLUMNS = ("smoothSmvVol", "extVol")


# ============================================================================
# Helpers
# ============================================================================

def _trading_days_with_data(start: date, end: date) -> list[date]:
    """Trading days in [start, end] that have an ORATS ZIP present."""
    out = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5 and orats.has_data_for(cur):
            out.append(cur)
        cur += timedelta(days=1)
    return out


def _resolve_one(day_chain: pd.DataFrame, ticker: str, on_date: date,
                 dte_front: int, dte_back: int, dte_buffer: int,
                 iv_column: str, ef: Optional[EarningsFilter]) -> dict:
    """Resolve one (ticker, date, cell) using a pre-loaded day chain.

    `ticker` is the CANONICAL universe symbol (e.g. "META"). Internally we
    resolve to the ORATS symbol active on `on_date` (e.g. "FB" pre-2022-06-09)
    via orats.resolve_ticker. Output row always carries the canonical name
    so downstream simulation/reporting see one consistent identifier.

    Returns the candidate row dict (always — schema-uniform even on miss).
    """
    orats_symbol = orats.resolve_ticker(ticker, on_date)
    row: dict = {
        "ticker": ticker,
        "orats_symbol_used": orats_symbol if orats_symbol != ticker else None,
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

    # Earnings check (uses target back expiry approximation as in Polygon path)
    target_back = on_date + timedelta(days=dte_back)
    if ef is not None:
        try:
            if not ef.is_safe_window(ticker, on_date, target_back):
                row["earnings_blocked"] = True
        except Exception as e:
            log.debug("earnings check failed %s %s: %s", ticker, on_date, e)

    # ATM-ish strike at front DTE (call leg). Look up using the resolved
    # ORATS symbol (e.g. "FB" for "META" pre-2022-06-09).
    front = orats.find_atm_for_dte(day_chain, orats_symbol, dte_front, dte_buffer)
    if front is None:
        return row
    front_iv = front.get(iv_column)
    front_mid = orats._orats_mid(front, "C")
    if front_iv is None or pd.isna(front_iv) or front_iv <= 0:
        return row
    if front_mid is None:
        return row

    front_dte = (pd.Timestamp(front["expirDate"]) - pd.Timestamp(on_date)).days
    row["front_dte"] = int(front_dte)
    row["front_strike"] = float(front["strike"])
    row["front_expiry"] = front["expirDate"]
    row["front_close"] = float(front_mid)
    row["front_iv"] = float(front_iv)
    row["underlying_close"] = float(front["stkPx"])

    # ATM-ish strike at back DTE (call leg) — same resolved symbol as front
    back = orats.find_atm_for_dte(day_chain, orats_symbol, dte_back, dte_buffer)
    if back is None:
        return row
    back_iv = back.get(iv_column)
    back_mid = orats._orats_mid(back, "C")
    if back_iv is None or pd.isna(back_iv) or back_iv <= 0:
        return row
    if back_mid is None:
        return row

    back_dte = (pd.Timestamp(back["expirDate"]) - pd.Timestamp(on_date)).days
    row["back_dte"] = int(back_dte)
    row["back_strike"] = float(back["strike"])
    row["back_expiry"] = back["expirDate"]
    row["back_close"] = float(back_mid)
    row["back_iv"] = float(back_iv)
    row["back_leg_resolved"] = True

    # Compute FF
    ff = calculate_forward_factor(
        dte_front=row["front_dte"],
        iv_front_pct=row["front_iv"] * 100.0,
        dte_back=row["back_dte"],
        iv_back_pct=row["back_iv"] * 100.0,
    )
    if ff.is_valid:
        row["ff"] = float(ff.forward_factor)
        row["estimated_debit"] = float(row["back_close"] - row["front_close"])
    return row


# ============================================================================
# Main entry point
# ============================================================================

def discover_orats(
    start_date: date,
    end_date: date,
    universe: list[str],
    cells: list[tuple[str, int, int]],
    output_path: str | Path,
    iv_column: str = "smoothSmvVol",
    earnings_filter_enabled: bool = True,
    dte_buffer: int = 5,
    progress_every: int = 200,
    use_cache: Optional[bool] = None,
) -> tuple[str, pd.DataFrame]:
    """Discover candidates using ORATS data.

    Args:
      iv_column: "smoothSmvVol" (VV-faithful) or "extVol" (Path A ex-earnings).
      earnings_filter_enabled: if False, all candidates pass earnings check.
        Recommended True for VV-faithful, False for Path A (extVol already
        strips earnings vol from front IV).

    Returns (discovery_run_id, candidates_df). Writes parquet to output_path.
    """
    if iv_column not in SUPPORTED_IV_COLUMNS:
        raise ValueError(f"Unsupported iv_column={iv_column!r}; "
                         f"choose from {SUPPORTED_IV_COLUMNS}")

    days = _trading_days_with_data(start_date, end_date)
    n_total = len(days) * len(universe) * len(cells)
    discovery_run_id = str(uuid.uuid4())

    # Auto-pick cache strategy: build year cache only when window is large
    # enough that the build cost amortizes (>30 days as a heuristic).
    if use_cache is None:
        use_cache = len(days) > 30

    print(f"[discover_candidates_orats] run_id={discovery_run_id}", flush=True)
    print(f"  iv_column={iv_column}  earnings_filter={earnings_filter_enabled}", flush=True)
    print(f"  window: {start_date} -> {end_date}  ({len(days)} trading days with data)", flush=True)
    print(f"  universe: {len(universe)} tickers  |  cells: {[c[0] for c in cells]}", flush=True)
    print(f"  total samples: {n_total:,}  |  use_cache={use_cache}", flush=True)

    # Earnings filter (uses hardcoded calendar; data-source-agnostic)
    ef: Optional[EarningsFilter] = None
    if earnings_filter_enabled:
        # EarningsFilter takes a Polygon client for fallback fetch; the hardcoded
        # source short-circuits before the API call, so we can pass None safely
        # provided every universe ticker has a hardcoded entry (verified for
        # all 23 tickers including ETF additions in earnings_data.py).
        ef = EarningsFilter(polygon_client=None)

    # Expand universe to include all rename predecessors so the loaded chain
    # contains data under whichever ORATS symbol was active per date.
    universe_expanded = orats.expand_universe_for_lookup(universe)
    aliased = sorted(set(universe_expanded) - set(universe))
    if aliased:
        print(f"  ticker aliases active: {aliased} -> "
              f"{[t for t in universe if t in orats.TICKER_HISTORY]}", flush=True)

    if use_cache:
        years = sorted({d.year for d in days})
        print(f"  warming ORATS caches for {len(universe_expanded)} symbols × {len(years)} years...", flush=True)
        t_warm = time.time()
        orats.warm_cache(universe_expanded, years, max_workers=1)
        print(f"  cache warm done in {time.time()-t_warm:.0f}s", flush=True)
        load_fn = lambda d, u: orats.load_orats_day_filtered(d, u)
    else:
        # Direct ZIP read per day, no cache build
        load_fn = lambda d, u: orats.load_orats_day_direct(d, u)

    # Process day-by-day. For each day, load full ticker subset once then
    # walk (ticker, cell) within that day. This reuses one DataFrame across
    # ticker × cell loops.
    rows: list[dict] = []
    t0 = time.time()
    n_done = 0

    for d in days:
        day_chain = load_fn(d, universe_expanded)
        for ticker in universe:
            for cell_name, dte_f, dte_b in cells:
                row = _resolve_one(day_chain, ticker, d, dte_f, dte_b,
                                   dte_buffer, iv_column, ef)
                row["date"] = d
                row["cell"] = cell_name
                row["discovery_run_id"] = discovery_run_id
                row["iv_source"] = iv_column
                rows.append(row)
                n_done += 1
                if n_done % progress_every == 0:
                    elapsed = time.time() - t0
                    rate = n_done / elapsed if elapsed > 0 else 0
                    eta = (n_total - n_done) / rate if rate > 0 else 0
                    print(f"  [{n_done}/{n_total}] elapsed={elapsed:.0f}s "
                          f"rate={rate:.1f}/s eta={eta:.0f}s", flush=True)

    elapsed = time.time() - t0
    print(f"  discovery loop done in {elapsed:.0f}s ({n_done/elapsed:.1f}/s)", flush=True)

    cols = ["date", "ticker", "cell", "front_dte", "back_dte",
            "front_strike", "back_strike", "front_expiry", "back_expiry",
            "front_close", "back_close", "front_iv", "back_iv",
            "underlying_close", "ff", "estimated_debit",
            "back_leg_resolved", "earnings_blocked",
            "discovery_run_id", "iv_source", "orats_symbol_used"]
    df = pd.DataFrame(rows)
    df = df[cols].sort_values(["date", "ticker", "cell"]).reset_index(drop=True)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"  wrote {out}  ({len(df):,} rows)", flush=True)

    n_resolved = int(df["back_leg_resolved"].sum())
    n_blocked = int(df["earnings_blocked"].sum())
    n_ff_valid = int(df["ff"].notna().sum())
    n_ff_strong = int((df["ff"] >= 0.20).sum())
    print(f"\nSummary:", flush=True)
    print(f"  total candidate slots:  {len(df):,}", flush=True)
    print(f"  back leg resolved:      {n_resolved:,}  ({100*n_resolved/len(df):.1f}%)", flush=True)
    print(f"  FF computable:          {n_ff_valid:,}  ({100*n_ff_valid/len(df):.1f}%)", flush=True)
    print(f"  FF >= 0.20:             {n_ff_strong:,}  ({100*n_ff_strong/len(df):.1f}%)", flush=True)
    print(f"  earnings-blocked:       {n_blocked:,}  ({100*n_blocked/len(df):.1f}%)", flush=True)

    return discovery_run_id, df


# ============================================================================
# CLI
# ============================================================================

def _parse_args():
    ap = argparse.ArgumentParser(description="ORATS candidate discovery.")
    ap.add_argument("--start", required=True, help="ISO start date e.g. 2008-01-02")
    ap.add_argument("--end", required=True, help="ISO end date e.g. 2026-04-30")
    ap.add_argument("--universe", required=True,
                    help="Comma-separated tickers, e.g. SPY,IWM")
    ap.add_argument("--cells", default="30_90_atm:30:90,60_90_atm:60:90",
                    help="Comma-separated cell specs name:dte_front:dte_back")
    ap.add_argument("--out", required=True, help="Output parquet path")
    ap.add_argument("--iv-column", default="smoothSmvVol",
                    choices=list(SUPPORTED_IV_COLUMNS))
    ap.add_argument("--no-earnings-filter", action="store_true",
                    help="Disable Option-B earnings filter (recommended for Path A)")
    ap.add_argument("--dte-buffer", type=int, default=5)
    return ap.parse_args()


def _main():
    logging.basicConfig(level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        stream=sys.stdout)
    args = _parse_args()
    universe = [t.strip().upper() for t in args.universe.split(",") if t.strip()]
    cells = []
    for spec in args.cells.split(","):
        parts = spec.strip().split(":")
        if len(parts) != 3:
            raise ValueError(f"Bad cell spec: {spec} (expected name:dte_front:dte_back)")
        cells.append((parts[0], int(parts[1]), int(parts[2])))
    discover_orats(
        start_date=date.fromisoformat(args.start),
        end_date=date.fromisoformat(args.end),
        universe=universe, cells=cells,
        output_path=args.out, iv_column=args.iv_column,
        earnings_filter_enabled=not args.no_earnings_filter,
        dte_buffer=args.dte_buffer,
    )


if __name__ == "__main__":
    _main()
