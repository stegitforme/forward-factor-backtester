"""Phase 5 stable-version allocation analysis — FF Stable vs Steven's TQQQ-VT.

Same methodology as Step 3 (scripts/tqqq_vt_allocation.py) but reads the
stable-version daily MTM curve instead of Tier 1 canonical.

Reads:
  output/sim_e3fa28f120d1/daily_mtm_equity.csv  (FF stable daily MTM curve)
  output/tqqq_vt_daily_equity.csv               (Steven's TQQQ-VT)

Output: output/PHASE_5_STABLE_ALLOCATION.md
        output/ff_stable_vs_tqqqvt_curves.png
        output/stable_allocation_sweep_curves.png
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FF_STABLE_HASH = "e3fa28f120d1"
FF_TIER1_HASH = "4119dc073393"

FF_STABLE_EQUITY = Path(f"output/sim_{FF_STABLE_HASH}/daily_mtm_equity.csv")
FF_TIER1_EQUITY = Path(f"output/sim_{FF_TIER1_HASH}/daily_mtm_equity.csv")
TQQQVT_EQUITY = Path("output/tqqq_vt_daily_equity.csv")

PNG_OUT = Path("output/ff_stable_vs_tqqqvt_curves.png")
ALLOC_PNG = Path("output/stable_allocation_sweep_curves.png")
MD_OUT = Path("output/PHASE_5_STABLE_ALLOCATION.md")

MIXES = [
    (1.00, 0.00), (0.90, 0.10), (0.85, 0.15), (0.80, 0.20),
    (0.75, 0.25), (0.70, 0.30), (0.60, 0.40), (0.50, 0.50),
    (0.00, 1.00),
]


def max_dd_pct(equity: np.ndarray) -> tuple[float, int, int]:
    if len(equity) == 0:
        return 0.0, 0, 0
    peak = equity[0]; max_dd = 0.0; pi = 0; ti = 0; cur_pi = 0
    for i, v in enumerate(equity):
        if v > peak:
            peak = v; cur_pi = i
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd; pi = cur_pi; ti = i
    return max_dd, pi, ti


def metrics_from_equity(equity: np.ndarray, dates: pd.DatetimeIndex, base: float = None) -> dict:
    if len(equity) == 0:
        return {}
    if base is None:
        base = float(equity[0])
    end_val = float(equity[-1])
    cal_days = (dates[-1] - dates[0]).days
    cagr = ((end_val / base) ** (365 / max(cal_days, 1)) - 1) * 100 if cal_days > 0 else 0
    rets = pd.Series(equity).pct_change().dropna()
    if len(rets) < 2:
        sd = 0.0; m = 0.0
    else:
        sd = float(rets.std()); m = float(rets.mean())
    ann_vol = sd * (252 ** 0.5) * 100
    sharpe = (m * 252) / (sd * (252 ** 0.5)) if sd > 0 else 0
    dd_pct, pi, ti = max_dd_pct(equity)
    calmar = (cagr / dd_pct) if dd_pct > 0 else float("inf")
    return {"cagr": cagr, "max_dd_pct": dd_pct, "ann_vol": ann_vol, "sharpe": sharpe,
            "calmar": calmar, "end_val": end_val,
            "dd_peak_date": str(dates[pi].date()), "dd_trough_date": str(dates[ti].date())}


def main():
    print(f"### Phase 5 Stable — Allocation Analysis vs TQQQ-VT", flush=True)

    ff = pd.read_csv(FF_STABLE_EQUITY, parse_dates=["date"])
    ff = ff[["date", "combined"]].rename(columns={"combined": "ff_equity"})
    ff.set_index("date", inplace=True)
    print(f"  FF Stable: {len(ff)} days, ${float(ff['ff_equity'].iloc[0]):,.0f} → ${float(ff['ff_equity'].iloc[-1]):,.0f}", flush=True)

    if not TQQQVT_EQUITY.exists():
        print(f"\nERROR: {TQQQVT_EQUITY} not found.", flush=True)
        return

    tq = pd.read_csv(TQQQVT_EQUITY, parse_dates=["date"])
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

    merged = ff.join(tq, how="inner")
    print(f"  Common days: {len(merged)} ({merged.index[0].date()} → {merged.index[-1].date()})", flush=True)

    ff_rets = merged["ff_equity"].pct_change().dropna()
    tq_rets = merged["tqqqvt_equity"].pct_change().dropna()
    common_idx = ff_rets.index.intersection(tq_rets.index)
    ff_rets = ff_rets.loc[common_idx]; tq_rets = tq_rets.loc[common_idx]

    correlation = float(ff_rets.corr(tq_rets))
    cov = float(ff_rets.cov(tq_rets))
    var_tq = float(tq_rets.var())
    beta = cov / var_tq if var_tq > 0 else 0
    print(f"\n  Correlation (FF stable vs TQQQ-VT): {correlation:+.3f}", flush=True)
    print(f"  Beta (FF stable on TQQQ-VT):        {beta:+.3f}", flush=True)

    aligned_dates = pd.DatetimeIndex(merged.index)
    ff_metrics = metrics_from_equity(merged["ff_equity"].values, aligned_dates)
    tq_metrics = metrics_from_equity(merged["tqqqvt_equity"].values, aligned_dates)
    print(f"\n  FF Stable (overlap): CAGR {ff_metrics['cagr']:+.2f}%  DD {ff_metrics['max_dd_pct']:.2f}%  Sh {ff_metrics['sharpe']:.2f}", flush=True)
    print(f"  TQQQ-VT  (overlap): CAGR {tq_metrics['cagr']:+.2f}%  DD {tq_metrics['max_dd_pct']:.2f}%  Sh {tq_metrics['sharpe']:.2f}", flush=True)

    # Side-by-side: also load Tier 1 over same overlapping window
    tier1_metrics = None
    if FF_TIER1_EQUITY.exists():
        t1 = pd.read_csv(FF_TIER1_EQUITY, parse_dates=["date"])
        t1 = t1[["date", "combined"]].rename(columns={"combined": "t1_equity"}).set_index("date")
        t1_aligned = t1.loc[t1.index.isin(aligned_dates)]
        if len(t1_aligned) >= 100:
            tier1_metrics = metrics_from_equity(
                t1_aligned["t1_equity"].values,
                pd.DatetimeIndex(t1_aligned.index),
            )
            print(f"  FF Tier 1 (overlap): CAGR {tier1_metrics['cagr']:+.2f}%  DD {tier1_metrics['max_dd_pct']:.2f}%  Sh {tier1_metrics['sharpe']:.2f}", flush=True)

    # Overlay PNG
    print(f"\nGenerating overlay PNG: {PNG_OUT}", flush=True)
    fig, ax = plt.subplots(figsize=(14, 7))
    ff_norm = merged["ff_equity"] / float(merged["ff_equity"].iloc[0]) * 100
    tq_norm = merged["tqqqvt_equity"] / float(merged["tqqqvt_equity"].iloc[0]) * 100
    ax.plot(ff_norm.index, ff_norm.values,
            label=f"FF Stable (CAGR {ff_metrics['cagr']:+.1f}%, DD {ff_metrics['max_dd_pct']:.1f}%, Sh {ff_metrics['sharpe']:.2f})",
            linewidth=2.5, color="black")
    ax.plot(tq_norm.index, tq_norm.values,
            label=f"TQQQ-VT (CAGR {tq_metrics['cagr']:+.1f}%, DD {tq_metrics['max_dd_pct']:.1f}%, Sh {tq_metrics['sharpe']:.2f})",
            linewidth=2.5, color="tab:blue", alpha=0.8)
    ax.axhline(100, color="gray", linestyle="--", linewidth=0.5)
    ax.set_title("FF Stable vs TQQQ-VT (overlapping period, normalized to $100)")
    ax.set_xlabel("Date"); ax.set_ylabel("Normalized equity ($)"); ax.legend(loc="best"); ax.grid(True, alpha=0.3)
    plt.tight_layout(); plt.savefig(PNG_OUT, dpi=120); plt.close()

    # Allocation sweep
    print(f"\n  Running allocation sweep ({len(MIXES)} mixes, daily-rebalanced)...", flush=True)
    base = 10_000.0
    sweep_results = []
    sweep_curves = {}
    for w_tq, w_ff in MIXES:
        port_rets = w_tq * tq_rets + w_ff * ff_rets
        eq = (1.0 + port_rets).cumprod() * base
        eq = pd.concat([pd.Series([base], index=[port_rets.index[0] - pd.Timedelta(days=1)]), eq])
        m = metrics_from_equity(eq.values, pd.DatetimeIndex(eq.index), base=base)
        sweep_results.append({
            "mix_label": f"{int(w_tq*100):3d}/{int(w_ff*100):3d}",
            "w_tqqqvt": w_tq, "w_ff": w_ff, **m,
        })
        sweep_curves[(w_tq, w_ff)] = eq
        print(f"    {int(w_tq*100):3d}% TQQQ-VT / {int(w_ff*100):3d}% FF:  "
              f"CAGR {m['cagr']:+.2f}%  DD {m['max_dd_pct']:.2f}%  Sh {m['sharpe']:.2f}  Cal {m['calmar']:.2f}", flush=True)

    max_sharpe_idx = max(range(len(sweep_results)), key=lambda i: sweep_results[i]["sharpe"])
    max_calmar_idx = max(range(len(sweep_results)),
                        key=lambda i: sweep_results[i]["calmar"] if sweep_results[i]["calmar"] != float("inf") else 0)
    pure_tq = sweep_results[0]
    max_sh = sweep_results[max_sharpe_idx]
    max_cal = sweep_results[max_calmar_idx]
    print(f"\n  Max-Sharpe mix: {max_sh['mix_label']}  (Sharpe {max_sh['sharpe']:.3f})", flush=True)
    print(f"  Max-Calmar mix: {max_cal['mix_label']}  (Calmar {max_cal['calmar']:.3f})", flush=True)

    # Allocation sweep PNG
    print(f"\nGenerating allocation sweep PNG: {ALLOC_PNG}", flush=True)
    fig, ax = plt.subplots(figsize=(14, 8))
    selected = [(1.0, 0.0), (max_sh["w_tqqqvt"], max_sh["w_ff"]), (0.0, 1.0)]
    if (max_cal["w_tqqqvt"], max_cal["w_ff"]) not in selected:
        selected.insert(2, (max_cal["w_tqqqvt"], max_cal["w_ff"]))
    for key in selected:
        eq = sweep_curves[key]
        eq_100 = eq / float(eq.iloc[0]) * 100
        w_tq, w_ff = key
        label = f"{int(w_tq*100)}% TQQQ-VT / {int(w_ff*100)}% FF"
        if (w_tq, w_ff) == (1.0, 0.0): label += " (pure TQQQ-VT)"
        if (w_tq, w_ff) == (0.0, 1.0): label += " (pure FF Stable)"
        if (w_tq, w_ff) == (max_sh["w_tqqqvt"], max_sh["w_ff"]): label += " ← MAX SHARPE"
        if (w_tq, w_ff) == (max_cal["w_tqqqvt"], max_cal["w_ff"]) and key != (max_sh["w_tqqqvt"], max_sh["w_ff"]):
            label += " ← MAX CALMAR"
        ax.plot(eq_100.index, eq_100.values, label=label, linewidth=2 if "MAX" in label else 1.5)
    ax.axhline(100, color="gray", linestyle="--", linewidth=0.5)
    ax.set_title("Stable-Version Allocation sweep — selected mixes (normalized to $100)")
    ax.set_xlabel("Date"); ax.set_ylabel("Normalized equity ($)"); ax.legend(loc="best"); ax.grid(True, alpha=0.3)
    plt.tight_layout(); plt.savefig(ALLOC_PNG, dpi=120); plt.close()

    ff_alloc_pct = int(max_sh["w_ff"] * 100)
    if ff_alloc_pct <= 5:
        decision = "**FF STABLE DOES NOT EARN ALLOCATION.** Caps neutralized concentration but stripped the strategy of its alpha — it doesn't improve TQQQ-VT meaningfully."
        bucket = "0-5%"
    elif ff_alloc_pct <= 15:
        decision = f"**SATELLITE ALLOCATION: ~{ff_alloc_pct}% FF Stable / {100-ff_alloc_pct}% TQQQ-VT.** Recommended mix at the modest end."
        bucket = "5-15%"
    else:
        decision = f"**MEANINGFUL ALLOCATION: {ff_alloc_pct}% FF Stable / {100-ff_alloc_pct}% TQQQ-VT.** Stable still earns a real seat."
        bucket = "15%+"

    print(f"\nWriting {MD_OUT}...", flush=True)
    def fmt(v): return f"{v:+.2f}%"
    lines = []
    lines.append(f"# Phase 5 Stable-Version — Allocation Analysis vs TQQQ Vol-Target")
    lines.append("")
    lines.append(f"**Stable config hash**: `{FF_STABLE_HASH}`")
    lines.append(f"**Overlapping period**: {merged.index[0].date()} → {merged.index[-1].date()} ({len(merged)} days)")
    lines.append(f"**Method**: daily-rebalanced fixed-weight portfolio. Returns combined as `w_tq × tq_rets + w_ff × ff_rets`.")
    lines.append("")

    lines.append(f"## Daily-returns correlation + beta")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---:|")
    lines.append(f"| Correlation (FF Stable vs TQQQ-VT) | **{correlation:+.3f}** |")
    lines.append(f"| Beta (FF Stable on TQQQ-VT) | **{beta:+.3f}** |")
    lines.append("")

    lines.append(f"## Standalone strategy metrics (overlapping period)")
    lines.append("")
    if tier1_metrics is not None:
        lines.append(f"| Metric | FF Stable | FF Tier 1 (canonical) | TQQQ-VT |")
        lines.append(f"|---|---:|---:|---:|")
        lines.append(f"| CAGR | {fmt(ff_metrics['cagr'])} | {fmt(tier1_metrics['cagr'])} | {fmt(tq_metrics['cagr'])} |")
        lines.append(f"| MaxDD% | {ff_metrics['max_dd_pct']:.2f}% | {tier1_metrics['max_dd_pct']:.2f}% | {tq_metrics['max_dd_pct']:.2f}% |")
        lines.append(f"| Ann Vol | {ff_metrics['ann_vol']:.2f}% | {tier1_metrics['ann_vol']:.2f}% | {tq_metrics['ann_vol']:.2f}% |")
        lines.append(f"| Sharpe | {ff_metrics['sharpe']:.2f} | {tier1_metrics['sharpe']:.2f} | {tq_metrics['sharpe']:.2f} |")
        lines.append(f"| Calmar | {ff_metrics['calmar']:.2f} | {tier1_metrics['calmar']:.2f} | {tq_metrics['calmar']:.2f} |")
    else:
        lines.append(f"| Metric | FF Stable | TQQQ-VT |")
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
    lines.append(f"| Metric | Pure TQQQ-VT | Max-Sharpe Mix ({max_sh['mix_label']}) | Max-Calmar Mix ({max_cal['mix_label']}) |")
    lines.append(f"|---|---:|---:|---:|")
    for k, label in [("cagr", "CAGR"), ("max_dd_pct", "MaxDD%"), ("ann_vol", "Ann Vol"), ("sharpe", "Sharpe"), ("calmar", "Calmar")]:
        v_pure = pure_tq[k]; v_sh = max_sh[k]; v_cal = max_cal[k]
        if k in ("cagr", "max_dd_pct", "ann_vol"):
            lines.append(f"| {label} | {fmt(v_pure)} | {fmt(v_sh)} | {fmt(v_cal)} |")
        else:
            lines.append(f"| {label} | {v_pure:.2f} | {v_sh:.2f} | {v_cal:.2f} |")
    lines.append("")

    lines.append(f"## Decision (bucket: {bucket} FF Stable allocation)")
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
    lines.append(f"### FF Stable vs TQQQ-VT (standalone)")
    lines.append("")
    lines.append(f"![FF Stable vs TQQQ-VT]({PNG_OUT.name})")
    lines.append("")
    lines.append(f"### Allocation sweep — pure TQQQ-VT, max-Sharpe mix, max-Calmar mix, pure FF Stable")
    lines.append("")
    lines.append(f"![Allocation sweep]({ALLOC_PNG.name})")

    MD_OUT.parent.mkdir(parents=True, exist_ok=True)
    MD_OUT.write_text("\n".join(lines))
    print(f"Wrote {MD_OUT}", flush=True)
    print(f"\n=== STABLE ALLOCATION DECISION: {bucket} FF — max-Sharpe at {max_sh['mix_label']} (Sh {max_sh['sharpe']:.3f}) ===", flush=True)


if __name__ == "__main__":
    main()
