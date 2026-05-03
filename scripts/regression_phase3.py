"""Regression test: new pipeline (baseline config, no caps) must match the
original Phase 3 trade log + equity curve within tolerance.

Tolerance per Steven:
  - Same trade set (sort-comparable on entry_date, ticker, cell, front_strike)
  - Total P&L within 0.01%
  - Daily equity curve point-wise within 0.01%
  - Metrics within rounding

Compares against:
  output/phase3_trade_log_30_90_atm.csv  + 60_90_atm
  output/phase3_daily_mtm_equity.csv

After the new baseline run, dumps a regression_report.txt.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

# Make repo root importable when running this script directly
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout)

from config.run_config import RunConfig
from src.discover_candidates import discover
from src.simulate_portfolio import simulate

CANDIDATES_PATH = Path("output/phase3_full_candidates.parquet")

ORIGINAL_TRADE_30 = Path("output/phase3_trade_log_30_90_atm.csv")
ORIGINAL_TRADE_60 = Path("output/phase3_trade_log_60_90_atm.csv")
ORIGINAL_EQUITY = Path("output/phase3_daily_mtm_equity.csv")


def main():
    print(f"### REGRESSION: new pipeline (baseline, no caps) vs original Phase 3", flush=True)

    BASE = RunConfig()
    cfg = replace(BASE,
                  position_cap_contracts=None,
                  position_cap_contracts_per_ticker_cell=None,
                  position_cap_nav_pct=None,
                  position_cap_strike_mtm=None)

    # Discovery
    if CANDIDATES_PATH.exists():
        print(f"  reusing {CANDIDATES_PATH}", flush=True)
        discovery_run_id = pd.read_parquet(CANDIDATES_PATH)["discovery_run_id"].iloc[0]
    else:
        print(f"  running discovery (will take many minutes)...", flush=True)
        discovery_run_id, _ = discover(
            start_date=date.fromisoformat(cfg.start_date),
            end_date=date.fromisoformat(cfg.end_date),
            universe=list(cfg.universe), cells=list(cfg.cells),
            output_path=CANDIDATES_PATH, max_workers=12,
        )

    print(f"  simulating with baseline config (config_hash={cfg.short_hash()})...", flush=True)
    simulate(CANDIDATES_PATH, cfg, "output", discovery_run_id=discovery_run_id)

    out_dir = Path("output") / f"sim_{cfg.short_hash()}"
    new_trades = pd.read_csv(out_dir / "trade_log.csv")
    new_eq = pd.read_csv(out_dir / "daily_mtm_equity.csv", parse_dates=["date"])
    new_eq.set_index("date", inplace=True)

    orig_30 = pd.read_csv(ORIGINAL_TRADE_30)
    orig_60 = pd.read_csv(ORIGINAL_TRADE_60)
    orig_30["cell"] = "30_90_atm"; orig_60["cell"] = "60_90_atm"
    orig_trades = pd.concat([orig_30, orig_60], ignore_index=True)

    orig_eq = pd.read_csv(ORIGINAL_EQUITY, parse_dates=["date"])
    orig_eq.set_index("date", inplace=True)

    print(f"\n=== TRADE LOG COMPARISON ===", flush=True)
    print(f"  new:      {len(new_trades)} rows", flush=True)
    print(f"  original: {len(orig_trades)} rows", flush=True)

    # Match on (entry_date, ticker, cell, front_strike, back_strike)
    keys = ["entry_date", "ticker", "cell", "front_strike", "back_strike"]
    new_trades["entry_date"] = pd.to_datetime(new_trades["entry_date"]).dt.date.astype(str)
    orig_trades["entry_date"] = pd.to_datetime(orig_trades["entry_date"]).dt.date.astype(str)

    new_set = set(map(tuple, new_trades[keys].values.tolist()))
    orig_set = set(map(tuple, orig_trades[keys].values.tolist()))
    common = new_set & orig_set
    only_new = new_set - orig_set
    only_orig = orig_set - new_set
    print(f"  common trades:    {len(common)}", flush=True)
    print(f"  only in new:      {len(only_new)}", flush=True)
    print(f"  only in original: {len(only_orig)}", flush=True)

    # P&L total comparison (closed only)
    new_closed_pnl = new_trades[new_trades["pnl_total"].notna()]["pnl_total"].astype(float).sum()
    orig_closed_pnl = orig_trades[orig_trades["pnl_total"].notna()]["pnl_total"].astype(float).sum()
    pnl_pct_diff = ((new_closed_pnl - orig_closed_pnl) / orig_closed_pnl * 100) if orig_closed_pnl != 0 else 0
    print(f"\n  total closed P&L new:      ${new_closed_pnl:+,.2f}", flush=True)
    print(f"  total closed P&L original: ${orig_closed_pnl:+,.2f}", flush=True)
    print(f"  delta:                     {pnl_pct_diff:+.4f}%  (tolerance: ±0.01%)", flush=True)

    print(f"\n=== EQUITY CURVE COMPARISON (combined daily MTM) ===", flush=True)
    common_dates = new_eq.index.intersection(orig_eq.index)
    diff = (new_eq.loc[common_dates, "combined"] - orig_eq.loc[common_dates, "combined"]) / orig_eq.loc[common_dates, "combined"] * 100
    max_pct_diff = diff.abs().max()
    print(f"  common days: {len(common_dates)}", flush=True)
    print(f"  max point-wise % difference: {max_pct_diff:.4f}%  (tolerance: ±0.01%)", flush=True)
    print(f"  end equity new:      ${new_eq['combined'].iloc[-1]:,.2f}", flush=True)
    print(f"  end equity original: ${orig_eq['combined'].iloc[-1]:,.2f}", flush=True)
    end_diff = (new_eq['combined'].iloc[-1] - orig_eq['combined'].iloc[-1]) / orig_eq['combined'].iloc[-1] * 100
    print(f"  end-equity diff:     {end_diff:+.4f}%", flush=True)

    print(f"\n=== VERDICT ===", flush=True)
    issues = []
    if abs(pnl_pct_diff) > 0.01: issues.append(f"P&L diff {pnl_pct_diff:.4f}% > 0.01% tolerance")
    if max_pct_diff > 0.01: issues.append(f"Equity diff {max_pct_diff:.4f}% > 0.01% tolerance")
    if len(only_new) + len(only_orig) > 0:
        issues.append(f"Trade set mismatch: {len(only_new)} only-new, {len(only_orig)} only-orig")

    if issues:
        print(f"⚠ REGRESSION FAILED — flag for review:", flush=True)
        for i in issues: print(f"  - {i}", flush=True)
    else:
        print(f"✓ Regression PASSED within tolerance.", flush=True)


if __name__ == "__main__":
    main()
