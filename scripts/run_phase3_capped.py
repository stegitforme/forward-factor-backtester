"""5-config Phase 3 sweep with position caps.

Discovery runs ONCE; the resulting candidates.parquet feeds 5 simulations
with different cap configurations. This is the operational shape of the
new pipeline.

Configs:
  baseline      — no caps active (regression target vs prior Phase 3)
  cap1          — Cap 1 only (contract count + per-ticker-cell stack)
  cap2          — Cap 2 only (debit-floor NAV)
  cap1_cap2     — Cap 1 + Cap 2 combined (likely production config)
  all_three     — Cap 1 + Cap 2 + Cap 3 (most conservative)

Output: output/phase3_5config_sweep_summary.md + output/sim_<hash>/* per config
"""
from __future__ import annotations

import json
import logging
import math
import sys
import time
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
SUMMARY_PATH = Path("output/PHASE_3_5CONFIG_SWEEP.md")

# Base config — Phase 3 settings + caps as the disable-able knobs we sweep
BASE = RunConfig()  # all defaults from RunConfig (which match Phase 3 + new caps)

# 5 configs to run
CONFIGS = {
    "baseline":  replace(BASE,
                          position_cap_contracts=None,
                          position_cap_contracts_per_ticker_cell=None,
                          position_cap_nav_pct=None,
                          position_cap_strike_mtm=None),
    "cap1":      replace(BASE,
                          position_cap_contracts=500,
                          position_cap_contracts_per_ticker_cell=1000,
                          position_cap_nav_pct=None,
                          position_cap_strike_mtm=None),
    "cap2":      replace(BASE,
                          position_cap_contracts=None,
                          position_cap_contracts_per_ticker_cell=None,
                          position_cap_nav_pct=0.02,
                          position_cap_strike_mtm=None),
    "cap1_cap2": replace(BASE,
                          position_cap_contracts=500,
                          position_cap_contracts_per_ticker_cell=1000,
                          position_cap_nav_pct=0.02,
                          position_cap_strike_mtm=None),
    "all_three": replace(BASE,
                          position_cap_contracts=500,
                          position_cap_contracts_per_ticker_cell=1000,
                          position_cap_nav_pct=0.02,
                          position_cap_strike_mtm=0.02),
}


def _max_dd_stats(equity: pd.Series) -> dict:
    if equity.empty:
        return {"max_dd_pct": 0, "max_dd_dollar": 0, "dd_days": 0,
                "peak_date": None, "trough_date": None}
    vals = equity.values; dates = equity.index
    peak = vals[0]; pi = 0; max_dd = 0; pi_at = 0; ti = 0
    for i, v in enumerate(vals):
        if v > peak: peak = v; pi = i
        dd = peak - v
        if dd > max_dd: max_dd = dd; pi_at = pi; ti = i
    pv = vals[pi_at]
    pct = (max_dd / pv * 100) if pv > 0 else 0
    return {"max_dd_pct": pct, "max_dd_dollar": float(max_dd),
            "dd_days": int(ti - pi_at),
            "peak_date": str(pd.Timestamp(dates[pi_at]).date()),
            "trough_date": str(pd.Timestamp(dates[ti]).date())}


def _full_metrics(equity: pd.Series, base: float) -> dict:
    if equity.empty:
        return {"cagr_pct": 0, "ann_vol_pct": 0, "sharpe": 0, "calmar": 0}
    end_val = float(equity.iloc[-1])
    cal_days = (equity.index[-1] - equity.index[0]).days
    cagr = ((end_val / base) ** (365 / max(cal_days, 1)) - 1) * 100 if cal_days > 0 else 0
    rets = equity.pct_change().dropna()
    if rets.empty: return {"cagr_pct": cagr, "ann_vol_pct": 0, "sharpe": 0, "calmar": 0}
    sd = float(rets.std()); m = float(rets.mean())
    ann_vol = sd * (252 ** 0.5) * 100
    sharpe = (m * 252) / (sd * (252 ** 0.5)) if sd > 0 else 0
    dd = _max_dd_stats(equity)
    calmar = (cagr / dd["max_dd_pct"]) if dd["max_dd_pct"] > 0 else float("inf")
    return {"cagr_pct": float(cagr), "ann_vol_pct": float(ann_vol),
            "sharpe": float(sharpe), "calmar": float(calmar),
            "end_val": end_val, "net": end_val - base, **dd}


def main():
    print(f"### PHASE 3 5-CONFIG SWEEP", flush=True)
    print(f"Window: {BASE.start_date} -> {BASE.end_date}", flush=True)
    print(f"Universe: {len(BASE.universe)} tickers", flush=True)
    print(f"Cells: {[c[0] for c in BASE.cells]}", flush=True)
    print(f"Configs: {list(CONFIGS.keys())}", flush=True)
    print(flush=True)

    # === Discovery (one run feeds all 5 sims) ===
    if CANDIDATES_PATH.exists():
        print(f"[discovery] reusing existing {CANDIDATES_PATH} (delete to force re-discover)", flush=True)
        discovery_run_id = pd.read_parquet(CANDIDATES_PATH)["discovery_run_id"].iloc[0]
    else:
        print(f"[discovery] running fresh...", flush=True)
        discovery_run_id, _ = discover(
            start_date=date.fromisoformat(BASE.start_date),
            end_date=date.fromisoformat(BASE.end_date),
            universe=list(BASE.universe),
            cells=list(BASE.cells),
            output_path=CANDIDATES_PATH,
            max_workers=12,
            dte_buffer=BASE.dte_buffer_days,
        )
    print(f"discovery_run_id={discovery_run_id}", flush=True)

    # === Run each config ===
    results = {}
    for name, cfg in CONFIGS.items():
        print(f"\n{'='*80}\n[{name}] config_hash={cfg.short_hash()}\n{'='*80}", flush=True)
        t0 = time.time()
        metrics = simulate(CANDIDATES_PATH, cfg, "output", discovery_run_id=discovery_run_id)
        elapsed = time.time() - t0

        # Read back the daily MTM equity for full analytics
        out_dir = Path("output") / f"sim_{cfg.short_hash()}"
        eq = pd.read_csv(out_dir / "daily_mtm_equity.csv", parse_dates=["date"])
        eq.set_index("date", inplace=True)
        combined = eq["combined"]
        base = cfg.initial_capital_per_cell * len(cfg.cells)
        full = _full_metrics(combined, base)

        # Per-cell metrics
        per_cell = {}
        for cell_name, _, _ in cfg.cells:
            cell_eq = eq[cell_name]
            per_cell[cell_name] = _full_metrics(cell_eq, cfg.initial_capital_per_cell)

        # Cap-trigger detail
        trades = pd.read_csv(out_dir / "trade_log.csv")
        cap_trigger_counts = trades["binding_cap"].value_counts().to_dict() if not trades.empty else {}

        results[name] = {
            "config_hash": cfg.short_hash(),
            "metrics": metrics,
            "full": full,
            "per_cell": per_cell,
            "cap_trigger_counts": cap_trigger_counts,
            "n_opens": int(trades.shape[0]) if not trades.empty else 0,
            "n_closed": int(trades["pnl_total"].notna().sum()) if not trades.empty else 0,
            "elapsed": elapsed,
        }
        print(f"  CAGR={full['cagr_pct']:+.2f}%  MaxDD={full['max_dd_pct']:.2f}%  "
              f"Sharpe={full['sharpe']:.2f}  Calmar={full['calmar']:.2f}", flush=True)
        print(f"  opens={results[name]['n_opens']}  closed={results[name]['n_closed']}  "
              f"trigger counts: {cap_trigger_counts}", flush=True)

    # === Markdown summary ===
    print(f"\n\nWriting {SUMMARY_PATH}...", flush=True)
    lines = []
    lines.append(f"# Phase 3 5-Config Position-Cap Sweep")
    lines.append("")
    lines.append(f"**Window**: {BASE.start_date} → {BASE.end_date}  |  **Universe**: {len(BASE.universe)} tickers  |  **Cells**: {[c[0] for c in BASE.cells]}")
    lines.append(f"**Initial capital**: ${BASE.initial_capital_per_cell:,.0f} per cell  |  ${BASE.initial_capital_per_cell * len(BASE.cells):,.0f} combined base")
    lines.append(f"**discovery_run_id**: `{discovery_run_id}`")
    lines.append("")

    # Headline table
    lines.append(f"## Cross-config headline (combined MTM)")
    lines.append("")
    lines.append(f"| Config | CAGR | MaxDD% | MaxDD$ | DD days | Sharpe | Calmar | Ann Vol | Opens | Closed |")
    lines.append(f"|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name in CONFIGS:
        r = results[name]; f = r["full"]
        lines.append(f"| **{name}** | {f['cagr_pct']:+.2f}% | {f['max_dd_pct']:.2f}% | ${f['max_dd_dollar']:,.0f} | {f['dd_days']} | {f['sharpe']:.2f} | {f['calmar']:.2f} | {f['ann_vol_pct']:.2f}% | {r['n_opens']} | {r['n_closed']} |")
    lines.append("")

    # Cap trigger counts
    lines.append(f"## Cap-trigger frequency per config")
    lines.append("")
    lines.append(f"How many trades were sized DOWN by each cap (vs Kelly).")
    lines.append("")
    lines.append(f"| Config | kelly | cap1a | cap1b | cap2 | cap3 |")
    lines.append(f"|---|---:|---:|---:|---:|---:|")
    for name in CONFIGS:
        c = results[name]["cap_trigger_counts"]
        lines.append(f"| {name} | {c.get('kelly', 0)} | {c.get('cap1a', 0)} | {c.get('cap1b', 0)} | {c.get('cap2', 0)} | {c.get('cap3', 0)} |")
    lines.append("")

    # Per-cell breakdown
    lines.append(f"## Per-cell breakdown (each config)")
    lines.append("")
    for name in CONFIGS:
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"| Cell | CAGR | MaxDD% | DD days | Sharpe | Ann Vol | End val |")
        lines.append(f"|---|---:|---:|---:|---:|---:|---:|")
        for cn, m in results[name]["per_cell"].items():
            lines.append(f"| {cn} | {m['cagr_pct']:+.2f}% | {m['max_dd_pct']:.2f}% | {m['dd_days']} | {m['sharpe']:.2f} | {m['ann_vol_pct']:.2f}% | ${m.get('end_val', 0):,.0f} |")
        lines.append("")

    # Critical comparisons (per Steven's spec)
    lines.append(f"## Critical comparisons")
    lines.append("")
    base_cagr = results["baseline"]["full"]["cagr_pct"]
    base_dd = results["baseline"]["full"]["max_dd_pct"]
    for cmp_name in ["cap2", "cap1_cap2", "all_three"]:
        f = results[cmp_name]["full"]
        cagr_delta = f["cagr_pct"] - base_cagr
        dd_delta = f["max_dd_pct"] - base_dd
        lines.append(f"- **{cmp_name} vs baseline**: CAGR {f['cagr_pct']:+.2f}% (Δ {cagr_delta:+.2f}pp), MaxDD {f['max_dd_pct']:.2f}% (Δ {dd_delta:+.2f}pp)")
    lines.append("")

    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text("\n".join(lines))
    print(f"Wrote {SUMMARY_PATH}", flush=True)


if __name__ == "__main__":
    main()
