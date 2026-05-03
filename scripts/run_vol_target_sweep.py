"""Phase 3.5 vol-target sweep.

Five configs designed to isolate two distinct hypotheses:
  - Does scaling DOWN during high-vol regimes improve risk-adjusted return?  (max_scale=1.0)
  - Does additionally scaling UP during low-vol regimes capture more edge?    (max_scale=2.0)

Configs:
  baseline           — no vol target (regression target = $24.33% Phase 3)
  target20_max1.0    — target 20% ann vol, downscale only
  target15_max1.0    — target 15% ann vol, downscale only (more aggressive target)
  target20_max2.0    — target 20% ann vol, downscale + upscale to 2x
  target15_max2.0    — target 15% ann vol, downscale + upscale to 2x

NO position caps — vol-target tested in isolation. (Caps + vol-target combined
is a separate experiment if vol-target shows promise.)

Discovery shared across all 5 sims (same parquet).
"""
from __future__ import annotations

import logging
import sys
import time
from dataclasses import replace
from datetime import date
from pathlib import Path

# Make repo root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout)

from config.run_config import RunConfig
from src.discover_candidates import discover
from src.simulate_portfolio import simulate

CANDIDATES_PATH = Path("output/phase3_full_candidates.parquet")
SUMMARY_PATH = Path("output/PHASE_3_5_VOL_TARGET_SWEEP.md")

# Base: Phase 3 settings, NO caps active (isolate vol-target effect)
BASE = replace(
    RunConfig(),
    position_cap_contracts=None,
    position_cap_contracts_per_ticker_cell=None,
    position_cap_nav_pct=None,
    position_cap_strike_mtm=None,
)

CONFIGS = {
    "baseline":         replace(BASE, vol_target_annualized=None),
    "target20_max1.0":  replace(BASE, vol_target_annualized=0.20, vol_target_max_scale=1.0),
    "target15_max1.0":  replace(BASE, vol_target_annualized=0.15, vol_target_max_scale=1.0),
    "target20_max2.0":  replace(BASE, vol_target_annualized=0.20, vol_target_max_scale=2.0),
    "target15_max2.0":  replace(BASE, vol_target_annualized=0.15, vol_target_max_scale=2.0),
}

DD_WINDOW_PEAK = pd.Timestamp("2026-03-06")
DD_WINDOW_TROUGH = pd.Timestamp("2026-04-17")


def _max_dd(equity: pd.Series) -> dict:
    if equity.empty: return {"max_dd_pct": 0, "max_dd_dollar": 0, "dd_days": 0}
    vals = equity.values; dates = equity.index
    peak = vals[0]; pi = 0; max_dd = 0; pi_at = 0; ti = 0
    for i, v in enumerate(vals):
        if v > peak: peak = v; pi = i
        dd = peak - v
        if dd > max_dd: max_dd = dd; pi_at = pi; ti = i
    pv = vals[pi_at]
    return {"max_dd_pct": (max_dd / pv * 100) if pv > 0 else 0,
            "max_dd_dollar": float(max_dd), "dd_days": int(ti - pi_at)}


def _full_metrics(equity: pd.Series, base: float) -> dict:
    if equity.empty:
        return {"cagr_pct": 0, "ann_vol_pct": 0, "sharpe": 0, "calmar": 0,
                "end_val": base, "max_dd_pct": 0, "max_dd_dollar": 0, "dd_days": 0}
    end_val = float(equity.iloc[-1])
    cal_days = (equity.index[-1] - equity.index[0]).days
    cagr = ((end_val / base) ** (365 / max(cal_days, 1)) - 1) * 100 if cal_days > 0 else 0
    rets = equity.pct_change().dropna()
    if rets.empty: return {"cagr_pct": cagr, "ann_vol_pct": 0, "sharpe": 0, "calmar": 0,
                            "end_val": end_val, "max_dd_pct": 0, "max_dd_dollar": 0, "dd_days": 0}
    sd = float(rets.std()); m = float(rets.mean())
    ann_vol = sd * (252 ** 0.5) * 100
    sharpe = (m * 252) / (sd * (252 ** 0.5)) if sd > 0 else 0
    dd = _max_dd(equity)
    calmar = (cagr / dd["max_dd_pct"]) if dd["max_dd_pct"] > 0 else float("inf")
    return {"cagr_pct": float(cagr), "ann_vol_pct": float(ann_vol), "sharpe": float(sharpe),
            "calmar": float(calmar), "end_val": end_val, **dd}


def _april_dd(equity: pd.Series) -> dict:
    """Peak→trough during March-April 2026 DD window."""
    sub = equity[(equity.index >= DD_WINDOW_PEAK) & (equity.index <= DD_WINDOW_TROUGH)]
    if sub.empty: return {"april_pct": 0, "april_max_dd_pct": 0}
    pct_change = (float(sub.iloc[-1]) / float(sub.iloc[0]) - 1) * 100
    dd = _max_dd(sub)
    return {"april_pct": pct_change, "april_max_dd_pct": dd["max_dd_pct"]}


def main():
    print(f"### PHASE 3.5 VOL-TARGET SWEEP", flush=True)
    print(f"Window: {BASE.start_date} → {BASE.end_date}", flush=True)
    print(f"Universe: {len(BASE.universe)} tickers", flush=True)
    print(f"Cells: {[c[0] for c in BASE.cells]}", flush=True)
    print(f"Configs: {list(CONFIGS.keys())}", flush=True)
    print()

    # Discovery (reuse if exists)
    if CANDIDATES_PATH.exists():
        print(f"[discovery] reusing {CANDIDATES_PATH}", flush=True)
        discovery_run_id = pd.read_parquet(CANDIDATES_PATH)["discovery_run_id"].iloc[0]
    else:
        print(f"[discovery] running fresh...", flush=True)
        discovery_run_id, _ = discover(
            start_date=date.fromisoformat(BASE.start_date),
            end_date=date.fromisoformat(BASE.end_date),
            universe=list(BASE.universe), cells=list(BASE.cells),
            output_path=CANDIDATES_PATH, max_workers=12,
        )

    results = {}
    for name, cfg in CONFIGS.items():
        print(f"\n{'='*80}\n[{name}] config_hash={cfg.short_hash()}\n{'='*80}", flush=True)
        print(f"  vol_target={cfg.vol_target_annualized}  max_scale={cfg.vol_target_max_scale}  "
              f"min_scale={cfg.vol_target_min_scale}  lookback={cfg.vol_target_lookback_days}d", flush=True)
        t0 = time.time()
        metrics = simulate(CANDIDATES_PATH, cfg, "output", discovery_run_id=discovery_run_id)
        elapsed = time.time() - t0

        out_dir = Path("output") / f"sim_{cfg.short_hash()}"
        eq = pd.read_csv(out_dir / "daily_mtm_equity.csv", parse_dates=["date"])
        eq.set_index("date", inplace=True)
        combined = eq["combined"]
        base_combined = cfg.initial_capital_per_cell * len(cfg.cells)
        full = _full_metrics(combined, base_combined)
        april = _april_dd(combined)

        per_cell = {}
        for cn, _, _ in cfg.cells:
            per_cell[cn] = _full_metrics(eq[cn], cfg.initial_capital_per_cell)

        trades = pd.read_csv(out_dir / "trade_log.csv")

        results[name] = {
            "config_hash": cfg.short_hash(),
            "metrics": metrics, "full": full, "april": april, "per_cell": per_cell,
            "n_opens": int(trades.shape[0]) if not trades.empty else 0,
            "n_closed": int(trades["pnl_total"].notna().sum()) if not trades.empty else 0,
            "elapsed": elapsed,
        }
        print(f"  CAGR={full['cagr_pct']:+.2f}%  MaxDD={full['max_dd_pct']:.2f}%  Sharpe={full['sharpe']:.2f}  Calmar={full['calmar']:.2f}", flush=True)
        print(f"  Apr DD: {april['april_pct']:+.2f}% (intra max DD: {april['april_max_dd_pct']:.2f}%)", flush=True)
        print(f"  vol_scale: avg={metrics['vol_scale_avg']:.3f}  min={metrics['vol_scale_min']:.3f}  max={metrics['vol_scale_max']:.3f}  "
              f"down%={metrics['pct_days_downscaled']:.1f}  up%={metrics['pct_days_upscaled']:.1f}", flush=True)

    # ---- Markdown summary ----
    print(f"\n\nWriting {SUMMARY_PATH}...", flush=True)
    lines = []
    lines.append(f"# Phase 3.5 Vol-Target Sweep")
    lines.append("")
    lines.append(f"**Window**: {BASE.start_date} → {BASE.end_date}  |  **Universe**: {len(BASE.universe)} tickers  |  **Cells**: {[c[0] for c in BASE.cells]}")
    lines.append(f"**Initial capital**: ${BASE.initial_capital_per_cell:,.0f} per cell, ${BASE.initial_capital_per_cell*len(BASE.cells):,.0f} combined base")
    lines.append(f"**Caps**: ALL DISABLED (vol-target tested in isolation)")
    lines.append(f"**discovery_run_id**: `{discovery_run_id}`")
    lines.append("")

    # Cross-config headline
    lines.append(f"## Cross-config headline (combined MTM)")
    lines.append("")
    lines.append(f"| Config | CAGR | MaxDD% | DD$ | DD days | Sharpe | Calmar | Ann Vol | Opens | Closed |")
    lines.append(f"|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name in CONFIGS:
        r = results[name]; f = r["full"]
        lines.append(f"| **{name}** | {f['cagr_pct']:+.2f}% | {f['max_dd_pct']:.2f}% | ${f['max_dd_dollar']:,.0f} | {f['dd_days']} | {f['sharpe']:.2f} | {f['calmar']:.2f} | {f['ann_vol_pct']:.2f}% | {r['n_opens']} | {r['n_closed']} |")
    lines.append("")

    # Vol-scale activity
    lines.append(f"## Vol-scale activity per config")
    lines.append("")
    lines.append(f"| Config | avg | min | max | %days <1.0 | %days >1.0 |")
    lines.append(f"|---|---:|---:|---:|---:|---:|")
    for name in CONFIGS:
        m = results[name]["metrics"]
        lines.append(f"| {name} | {m['vol_scale_avg']:.3f} | {m['vol_scale_min']:.3f} | {m['vol_scale_max']:.3f} | {m['pct_days_downscaled']:.1f}% | {m['pct_days_upscaled']:.1f}% |")
    lines.append("")

    # April 2026 DD impact
    lines.append(f"## April 2026 DD impact (was 31.70% baseline at Phase 3)")
    lines.append("")
    lines.append(f"| Config | Mar 6 → Apr 17 % | Intra-window MaxDD% |")
    lines.append(f"|---|---:|---:|")
    for name in CONFIGS:
        a = results[name]["april"]
        lines.append(f"| {name} | {a['april_pct']:+.2f}% | {a['april_max_dd_pct']:.2f}% |")
    lines.append("")

    # Per-cell breakdown
    lines.append(f"## Per-cell metrics")
    lines.append("")
    for name in CONFIGS:
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"| Cell | CAGR | MaxDD% | DD days | Sharpe | Ann Vol |")
        lines.append(f"|---|---:|---:|---:|---:|---:|")
        for cn, m in results[name]["per_cell"].items():
            lines.append(f"| {cn} | {m['cagr_pct']:+.2f}% | {m['max_dd_pct']:.2f}% | {m['dd_days']} | {m['sharpe']:.2f} | {m['ann_vol_pct']:.2f}% |")
        lines.append("")

    # Critical comparisons (per Steven's spec)
    lines.append(f"## Critical comparisons")
    lines.append("")
    lines.append(f"### Hypothesis 1: does downscaling improve risk-adjusted return? (max_scale=1.0 vs baseline)")
    base_sh = results["baseline"]["full"]["sharpe"]; base_cagr = results["baseline"]["full"]["cagr_pct"]; base_dd = results["baseline"]["full"]["max_dd_pct"]
    for n in ["target20_max1.0", "target15_max1.0"]:
        f = results[n]["full"]
        lines.append(f"- **{n}**: Sharpe {f['sharpe']:.2f} (Δ {f['sharpe']-base_sh:+.2f}), CAGR {f['cagr_pct']:+.2f}% (Δ {f['cagr_pct']-base_cagr:+.2f}pp), MaxDD {f['max_dd_pct']:.2f}% (Δ {f['max_dd_pct']-base_dd:+.2f}pp)")
    lines.append("")
    lines.append(f"### Hypothesis 2: does upscaling capture more edge? (max_scale=2.0 vs max_scale=1.0)")
    for tgt in ["target20", "target15"]:
        f1 = results[f"{tgt}_max1.0"]["full"]; f2 = results[f"{tgt}_max2.0"]["full"]
        lines.append(f"- **{tgt}**: Sharpe {f1['sharpe']:.2f} (max1.0) vs {f2['sharpe']:.2f} (max2.0) → Δ {f2['sharpe']-f1['sharpe']:+.2f}; CAGR {f1['cagr_pct']:+.2f}% vs {f2['cagr_pct']:+.2f}% → Δ {f2['cagr_pct']-f1['cagr_pct']:+.2f}pp; MaxDD {f1['max_dd_pct']:.2f}% vs {f2['max_dd_pct']:.2f}% → Δ {f2['max_dd_pct']-f1['max_dd_pct']:+.2f}pp")
    lines.append("")

    # Success criterion
    lines.append(f"## Success criterion check")
    lines.append("")
    lines.append(f"_Steven's bar: Sharpe > baseline 0.66 AND MaxDD < 25%. Ideal: DD < 20% with CAGR > 15%._")
    lines.append("")
    lines.append(f"| Config | Sharpe > 0.66? | MaxDD < 25%? | DD < 20% AND CAGR > 15%? |")
    lines.append(f"|---|---|---|---|")
    for name in CONFIGS:
        f = results[name]["full"]
        sh_ok = "✓" if f["sharpe"] > 0.66 else "✗"
        dd_ok = "✓" if f["max_dd_pct"] < 25 else "✗"
        ideal_ok = "✓" if (f["max_dd_pct"] < 20 and f["cagr_pct"] > 15) else "✗"
        lines.append(f"| {name} | {sh_ok} ({f['sharpe']:.2f}) | {dd_ok} ({f['max_dd_pct']:.2f}%) | {ideal_ok} |")
    lines.append("")

    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text("\n".join(lines))
    print(f"Wrote {SUMMARY_PATH}", flush=True)


if __name__ == "__main__":
    main()
