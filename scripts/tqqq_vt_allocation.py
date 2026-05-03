"""Step 3 allocation analysis — FF Tier 1 vs Steven's TQQQ Vol-Target.

Reads:
  output/sim_4119dc073393/daily_mtm_equity.csv  (FF Tier 1 daily MTM curve)
  output/tqqq_vt_daily_equity.csv               (Steven's TQQQ-VT, columns: date, portfolio_value)

Computes:
  - Daily-returns correlation, beta of FF on TQQQ-VT
  - Allocation sweep across 9 mixes (100/0 ... 0/100), daily-rebalanced
  - Identifies max-Sharpe and max-Calmar mixes
  - Equity-curve overlay PNG (FF + TQQQ-VT normalized to $100)
  - Decision rule: 0-5% / 5-15% / 15%+ FF allocation buckets

Output: output/PHASE_4_T1_ALLOCATION_REPORT.md + output/ff_vs_tqqqvt_curves.png
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make repo root importable (no internal imports needed but keeps pattern consistent)
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FF_EQUITY = Path("output/sim_4119dc073393/daily_mtm_equity.csv")
TQQQVT_EQUITY = Path("output/tqqq_vt_daily_equity.csv")
PNG_OUT = Path("output/ff_vs_tqqqvt_curves.png")
ALLOC_PNG = Path("output/allocation_sweep_curves.png")
MD_OUT = Path("output/PHASE_4_T1_ALLOCATION_REPORT.md")

# Allocation mixes per Steven's spec
MIXES = [
    (1.00, 0.00), (0.90, 0.10), (0.85, 0.15), (0.80, 0.20),
    (0.75, 0.25), (0.70, 0.30), (0.60, 0.40), (0.50, 0.50),
    (0.00, 1.00),
]


def max_dd_pct(equity: np.ndarray) -> tuple[float, int, int]:
    """Standard MaxDD: largest peak-to-trough percentage decline."""
    if len(equity) == 0: return 0.0, 0, 0
    peak = equity[0]; max_dd = 0.0; pi = 0; ti = 0; cur_pi = 0
    for i, v in enumerate(equity):
        if v > peak: peak = v; cur_pi = i
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd: max_dd = dd; pi = cur_pi; ti = i
    return max_dd, pi, ti


def metrics_from_equity(equity: np.ndarray, dates: pd.DatetimeIndex, base: float = None) -> dict:
    if len(equity) == 0: return {}
    if base is None: base = float(equity[0])
    end_val = float(equity[-1])
    cal_days = (dates[-1] - dates[0]).days
    cagr = ((end_val / base) ** (365 / max(cal_days, 1)) - 1) * 100 if cal_days > 0 else 0
    rets = pd.Series(equity).pct_change().dropna()
    if len(rets) < 2: sd = 0.0; m = 0.0
    else: sd = float(rets.std()); m = float(rets.mean())
    ann_vol = sd * (252 ** 0.5) * 100
    sharpe = (m * 252) / (sd * (252 ** 0.5)) if sd > 0 else 0
    dd_pct, pi, ti = max_dd_pct(equity)
    calmar = (cagr / dd_pct) if dd_pct > 0 else float("inf")
    return {"cagr": cagr, "max_dd_pct": dd_pct, "ann_vol": ann_vol, "sharpe": sharpe,
            "calmar": calmar, "end_val": end_val,
            "dd_peak_date": str(dates[pi].date()), "dd_trough_date": str(dates[ti].date())}


def main():
    print(f"### Step 3 — TQQQ-VT Allocation Analysis", flush=True)

    # Load FF
    ff = pd.read_csv(FF_EQUITY, parse_dates=["date"])
    ff = ff[["date", "combined"]].rename(columns={"combined": "ff_equity"})
    ff.set_index("date", inplace=True)
    print(f"  FF Tier 1: {len(ff)} days, ${float(ff['ff_equity'].iloc[0]):,.0f} → ${float(ff['ff_equity'].iloc[-1]):,.0f}", flush=True)

    # Load TQQQ-VT
    if not TQQQVT_EQUITY.exists():
        print(f"\nERROR: {TQQQVT_EQUITY} not found.", flush=True)
        print(f"Steven needs to provide his TQQQ-VT daily equity curve as CSV at this path.", flush=True)
        print(f"Columns: date, portfolio_value. Date format: ISO (2022-01-03).", flush=True)
        return

    tq = pd.read_csv(TQQQVT_EQUITY, parse_dates=["date"])
    # Tolerant of column naming
    val_col = None
    for c in tq.columns:
        if c.lower() in ("portfolio_value", "value", "equity", "nav", "balance"):
            val_col = c; break
    if val_col is None and len(tq.columns) == 2:
        val_col = [c for c in tq.columns if c.lower() != "date"][0]
    if val_col is None:
        raise ValueError(f"Couldn't find equity column in {TQQQVT_EQUITY}; columns: {list(tq.columns)}")
    tq = tq[["date", val_col]].rename(columns={val_col: "tqqqvt_equity"})
    tq.set_index("date", inplace=True)
    print(f"  TQQQ-VT:   {len(tq)} days, ${float(tq['tqqqvt_equity'].iloc[0]):,.2f} → ${float(tq['tqqqvt_equity'].iloc[-1]):,.2f}", flush=True)

    # Align on common dates
    merged = ff.join(tq, how="inner")
    print(f"  Common days: {len(merged)} ({merged.index[0].date()} → {merged.index[-1].date()})", flush=True)
    if len(merged) < 100:
        print(f"WARNING: only {len(merged)} common days — alignment likely off.", flush=True)

    # Daily returns
    ff_rets = merged["ff_equity"].pct_change().dropna()
    tq_rets = merged["tqqqvt_equity"].pct_change().dropna()
    common_idx = ff_rets.index.intersection(tq_rets.index)
    ff_rets = ff_rets.loc[common_idx]; tq_rets = tq_rets.loc[common_idx]

    # Correlation, beta
    correlation = float(ff_rets.corr(tq_rets))
    cov = float(ff_rets.cov(tq_rets))
    var_tq = float(tq_rets.var())
    beta = cov / var_tq if var_tq > 0 else 0
    print(f"\n  Correlation (FF vs TQQQ-VT, daily returns): {correlation:+.3f}", flush=True)
    print(f"  Beta (FF on TQQQ-VT):                       {beta:+.3f}", flush=True)

    # Per-strategy metrics over the OVERLAPPING period
    aligned_dates = pd.DatetimeIndex(merged.index)
    ff_metrics = metrics_from_equity(merged["ff_equity"].values, aligned_dates)
    tq_metrics = metrics_from_equity(merged["tqqqvt_equity"].values, aligned_dates)
    print(f"\n  FF Tier 1 (overlapping period):  CAGR {ff_metrics['cagr']:+.2f}%  MaxDD {ff_metrics['max_dd_pct']:.2f}%  Sharpe {ff_metrics['sharpe']:.2f}", flush=True)
    print(f"  TQQQ-VT  (overlapping period):  CAGR {tq_metrics['cagr']:+.2f}%  MaxDD {tq_metrics['max_dd_pct']:.2f}%  Sharpe {tq_metrics['sharpe']:.2f}", flush=True)

    # Equity-curve overlay PNG (just FF + TQQQ-VT)
    print(f"\nGenerating overlay PNG: {PNG_OUT}", flush=True)
    fig, ax = plt.subplots(figsize=(14, 7))
    ff_norm = merged["ff_equity"] / float(merged["ff_equity"].iloc[0]) * 100
    tq_norm = merged["tqqqvt_equity"] / float(merged["tqqqvt_equity"].iloc[0]) * 100
    ax.plot(ff_norm.index, ff_norm.values, label=f"FF Tier 1 (CAGR {ff_metrics['cagr']:+.1f}%, DD {ff_metrics['max_dd_pct']:.1f}%, Sh {ff_metrics['sharpe']:.2f})", linewidth=2.5, color="black")
    ax.plot(tq_norm.index, tq_norm.values, label=f"TQQQ-VT (CAGR {tq_metrics['cagr']:+.1f}%, DD {tq_metrics['max_dd_pct']:.1f}%, Sh {tq_metrics['sharpe']:.2f})", linewidth=2.5, color="tab:blue", alpha=0.8)
    ax.axhline(100, color="gray", linestyle="--", linewidth=0.5)
    ax.set_title(f"FF Tier 1 vs TQQQ Vol-Target (overlapping period, normalized to $100)")
    ax.set_xlabel("Date"); ax.set_ylabel("Normalized equity ($)"); ax.legend(loc="best"); ax.grid(True, alpha=0.3)
    plt.tight_layout(); plt.savefig(PNG_OUT, dpi=120); plt.close()

    # === Allocation sweep ===
    print(f"\n  Running allocation sweep ({len(MIXES)} mixes, daily-rebalanced)...", flush=True)
    base = 10_000.0  # arbitrary; doesn't affect Sharpe/CAGR/MaxDD
    sweep_results = []
    sweep_curves = {}
    for w_tq, w_ff in MIXES:
        # Combined daily returns
        port_rets = w_tq * tq_rets + w_ff * ff_rets
        # Reconstruct equity from returns starting at $base
        eq = (1.0 + port_rets).cumprod() * base
        eq = pd.concat([pd.Series([base], index=[port_rets.index[0] - pd.Timedelta(days=1)]), eq])
        m = metrics_from_equity(eq.values, pd.DatetimeIndex(eq.index), base=base)
        sweep_results.append({
            "mix_label": f"{int(w_tq*100):3d}/{int(w_ff*100):3d}",
            "w_tqqqvt": w_tq, "w_ff": w_ff, **m,
        })
        sweep_curves[(w_tq, w_ff)] = eq
        print(f"    {int(w_tq*100):3d}% TQQQ-VT / {int(w_ff*100):3d}% FF:  CAGR {m['cagr']:+.2f}%  MaxDD {m['max_dd_pct']:.2f}%  Sharpe {m['sharpe']:.2f}  Calmar {m['calmar']:.2f}", flush=True)

    # Identify max-Sharpe + max-Calmar mixes
    max_sharpe_idx = max(range(len(sweep_results)), key=lambda i: sweep_results[i]["sharpe"])
    max_calmar_idx = max(range(len(sweep_results)), key=lambda i: sweep_results[i]["calmar"] if sweep_results[i]["calmar"] != float("inf") else 0)
    pure_tq = sweep_results[0]
    max_sh = sweep_results[max_sharpe_idx]
    max_cal = sweep_results[max_calmar_idx]
    print(f"\n  Max-Sharpe mix: {max_sh['mix_label']}  (Sharpe {max_sh['sharpe']:.3f})", flush=True)
    print(f"  Max-Calmar mix: {max_cal['mix_label']}  (Calmar {max_cal['calmar']:.3f})", flush=True)

    # Allocation-sweep PNG (selected mixes overlaid)
    print(f"\nGenerating allocation sweep PNG: {ALLOC_PNG}", flush=True)
    fig, ax = plt.subplots(figsize=(14, 8))
    selected = [(1.0, 0.0), (max_sh["w_tqqqvt"], max_sh["w_ff"]), (0.0, 1.0)]
    if (max_cal["w_tqqqvt"], max_cal["w_ff"]) not in selected:
        selected.insert(2, (max_cal["w_tqqqvt"], max_cal["w_ff"]))
    for i, key in enumerate(selected):
        eq = sweep_curves[key]
        eq_100 = eq / float(eq.iloc[0]) * 100
        w_tq, w_ff = key
        label = f"{int(w_tq*100)}% TQQQ-VT / {int(w_ff*100)}% FF"
        if (w_tq, w_ff) == (1.0, 0.0): label += " (pure TQQQ-VT)"
        if (w_tq, w_ff) == (0.0, 1.0): label += " (pure FF)"
        if (w_tq, w_ff) == (max_sh["w_tqqqvt"], max_sh["w_ff"]): label += " ← MAX SHARPE"
        if (w_tq, w_ff) == (max_cal["w_tqqqvt"], max_cal["w_ff"]) and key != (max_sh["w_tqqqvt"], max_sh["w_ff"]): label += " ← MAX CALMAR"
        ax.plot(eq_100.index, eq_100.values, label=label, linewidth=2 if "MAX" in label else 1.5)
    ax.axhline(100, color="gray", linestyle="--", linewidth=0.5)
    ax.set_title("Allocation sweep — selected mixes (normalized to $100)")
    ax.set_xlabel("Date"); ax.set_ylabel("Normalized equity ($)"); ax.legend(loc="best"); ax.grid(True, alpha=0.3)
    plt.tight_layout(); plt.savefig(ALLOC_PNG, dpi=120); plt.close()

    # Decision bucket
    ff_alloc_pct = int(max_sh["w_ff"] * 100)
    if ff_alloc_pct <= 5:
        decision = "**FF DOES NOT EARN ALLOCATION.** Strategy is interesting research but doesn't improve Steven's existing portfolio meaningfully."
        bucket = "0-5%"
    elif ff_alloc_pct <= 15:
        decision = f"**CLEAN SATELLITE ALLOCATION ANSWER: ~{ff_alloc_pct}% FF / {100-ff_alloc_pct}% TQQQ-VT.** Recommended mix."
        bucket = "5-15%"
    else:
        decision = f"**MEANINGFUL ALLOCATION: {ff_alloc_pct}% FF / {100-ff_alloc_pct}% TQQQ-VT.** Strategy is a real piece of the portfolio, not a satellite."
        bucket = "15%+"

    # === Markdown ===
    print(f"\nWriting {MD_OUT}...", flush=True)
    def fmt(v): return f"{v:+.2f}%"
    lines = []
    lines.append(f"# Phase 4 Tier 1 — Allocation Analysis vs TQQQ Vol-Target")
    lines.append("")
    lines.append(f"**Overlapping period**: {merged.index[0].date()} → {merged.index[-1].date()} ({len(merged)} days)")
    lines.append(f"**Method**: daily-rebalanced fixed-weight portfolio. Returns combined as `w_tq × tq_rets + w_ff × ff_rets`.")
    lines.append("")

    lines.append(f"## Daily-returns correlation + beta")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---:|")
    lines.append(f"| Correlation (FF Tier 1 vs TQQQ-VT) | **{correlation:+.3f}** |")
    lines.append(f"| Beta (FF on TQQQ-VT) | **{beta:+.3f}** |")
    lines.append("")

    lines.append(f"## Standalone strategy metrics (overlapping period)")
    lines.append("")
    lines.append(f"| Metric | FF Tier 1 | TQQQ-VT |")
    lines.append(f"|---|---:|---:|")
    lines.append(f"| CAGR | {fmt(ff_metrics['cagr'])} | {fmt(tq_metrics['cagr'])} |")
    lines.append(f"| MaxDD% | {ff_metrics['max_dd_pct']:.2f}% | {tq_metrics['max_dd_pct']:.2f}% |")
    lines.append(f"| Ann Vol | {ff_metrics['ann_vol']:.2f}% | {tq_metrics['ann_vol']:.2f}% |")
    lines.append(f"| Sharpe | {ff_metrics['sharpe']:.2f} | {tq_metrics['sharpe']:.2f} |")
    lines.append(f"| Calmar | {ff_metrics['calmar']:.2f} | {tq_metrics['calmar']:.2f} |")
    lines.append("")

    lines.append(f"## Allocation sweep — full table")
    lines.append("")
    lines.append(f"| Mix (TQQQ-VT/FF) | CAGR | MaxDD% | Ann Vol | Sharpe | Calmar | End $ |")
    lines.append(f"|---|---:|---:|---:|---:|---:|---:|")
    for r in sweep_results:
        marker = ""
        if r is max_sh: marker += " ← max Sharpe"
        if r is max_cal and r is not max_sh: marker += " ← max Calmar"
        lines.append(f"| {r['mix_label']}{marker} | {fmt(r['cagr'])} | {r['max_dd_pct']:.2f}% | {r['ann_vol']:.2f}% | {r['sharpe']:.2f} | {r['calmar']:.2f} | ${r['end_val']:,.0f} |")
    lines.append("")

    lines.append(f"## Critical comparison: pure TQQQ-VT vs Max-Sharpe vs Max-Calmar")
    lines.append("")
    lines.append(f"| Metric | Pure TQQQ-VT (current) | Max-Sharpe Mix ({max_sh['mix_label']}) | Max-Calmar Mix ({max_cal['mix_label']}) |")
    lines.append(f"|---|---:|---:|---:|")
    for k, label in [("cagr", "CAGR"), ("max_dd_pct", "MaxDD%"), ("ann_vol", "Ann Vol"), ("sharpe", "Sharpe"), ("calmar", "Calmar")]:
        v_pure = pure_tq[k]; v_sh = max_sh[k]; v_cal = max_cal[k]
        if k in ("cagr", "max_dd_pct", "ann_vol"):
            lines.append(f"| {label} | {fmt(v_pure)} | {fmt(v_sh)} | {fmt(v_cal)} |")
        else:
            lines.append(f"| {label} | {v_pure:.2f} | {v_sh:.2f} | {v_cal:.2f} |")
    lines.append("")

    lines.append(f"## Decision (bucket: {bucket} FF allocation)")
    lines.append("")
    lines.append(decision)
    lines.append("")
    lines.append(f"### Δ vs pure TQQQ-VT for the recommended mix")
    lines.append("")
    lines.append(f"| Metric | Δ |")
    lines.append(f"|---|---:|")
    lines.append(f"| CAGR | {max_sh['cagr']-pure_tq['cagr']:+.2f}pp |")
    lines.append(f"| MaxDD% | {max_sh['max_dd_pct']-pure_tq['max_dd_pct']:+.2f}pp |")
    lines.append(f"| Sharpe | {max_sh['sharpe']-pure_tq['sharpe']:+.3f} |")
    lines.append(f"| Calmar | {max_sh['calmar']-pure_tq['calmar']:+.3f} |")
    lines.append(f"| Ann Vol | {max_sh['ann_vol']-pure_tq['ann_vol']:+.2f}pp |")
    lines.append("")

    lines.append(f"## Equity curves")
    lines.append("")
    lines.append(f"### FF Tier 1 vs TQQQ-VT (standalone)")
    lines.append("")
    lines.append(f"![FF vs TQQQ-VT]({PNG_OUT.name})")
    lines.append("")
    lines.append(f"### Allocation sweep — pure TQQQ-VT, max-Sharpe mix, max-Calmar mix, pure FF")
    lines.append("")
    lines.append(f"![Allocation sweep]({ALLOC_PNG.name})")

    MD_OUT.parent.mkdir(parents=True, exist_ok=True)
    MD_OUT.write_text("\n".join(lines))
    print(f"Wrote {MD_OUT}", flush=True)
    print(f"\n=== ALLOCATION DECISION: {bucket} FF — {decision[:120]}... ===", flush=True)


if __name__ == "__main__":
    main()
