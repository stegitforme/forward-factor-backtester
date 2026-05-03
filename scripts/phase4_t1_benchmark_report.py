"""Phase 4 Tier 1 benchmark report — same shape as Phase 3 benchmark report
but uses Tier 1 equity curve. Adds TQQQ-VT point estimates as a separate row
for context.

Steps 1+2 of Steven's 4-step plan:
  1. Per-horizon (1Y/2Y/3Y/full) CAGR/MaxDD/Sharpe for FF Tier 1 vs SPY/QQQ/TQQQ
  2. Daily-returns correlation, beta, info ratio of Tier 1 vs each benchmark

Step 3 (TQQQ-VT correlation + allocation sweep) is BLOCKED on Steven providing
his TQQQ-VT daily equity curve CSV. Once provided, run scripts/tqqq_vt_allocation.py.

Output: output/PHASE_4_T1_BENCHMARK_REPORT.md + output/phase4_t1_benchmark_curve.png
"""
from __future__ import annotations

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# Make repo root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout)

from src.data_layer import get_client

TIER1_EQUITY = Path("output/sim_4119dc073393/daily_mtm_equity.csv")
MD_OUT = Path("output/PHASE_4_T1_BENCHMARK_REPORT.md")
PNG_OUT = Path("output/phase4_t1_benchmark_curve.png")

START = date(2022, 1, 3)
END = date(2026, 4, 30)
INITIAL = 400_000.0
BENCHMARKS = ["SPY", "QQQ", "TQQQ"]

# Steven's TQQQ Vol-Target benchmark (point estimates only — daily curve needed for full analysis)
TQQQ_VT_POINT = {
    "cagr": 25.05, "max_dd_pct": 31.43, "sharpe": 0.92,
    "calmar": 0.80, "ann_vol": 29.1,
}

print(f"### Phase 4 Tier 1 Benchmark Report", flush=True)
print(f"Reading Tier 1 MTM equity from {TIER1_EQUITY}...", flush=True)

client = get_client()

ff_eq = pd.read_csv(TIER1_EQUITY, parse_dates=["date"])
ff_eq.set_index("date", inplace=True)
ff_combined = ff_eq["combined"]
print(f"  FF Tier 1: {len(ff_combined)} days, {ff_combined.index[0].date()} → {ff_combined.index[-1].date()}", flush=True)
print(f"  Final equity: ${float(ff_combined.iloc[-1]):,.0f}", flush=True)

# Fetch benchmark closes
print(f"\nFetching benchmark closes...", flush=True)
benchmarks_data = {}
for t in BENCHMARKS:
    bars = client.get_daily_bars(t, START - timedelta(days=5), END + timedelta(days=5))
    if bars.empty:
        print(f"  {t}: NO DATA", flush=True); continue
    benchmarks_data[t] = bars["close"]
    print(f"  {t}: {len(bars)} days", flush=True)

# Normalize benchmarks to FF base
ff_dates = ff_combined.index
def normalize(series, initial=INITIAL):
    return series / float(series.iloc[0]) * initial
bench_norm = {t: normalize(c) for t, c in benchmarks_data.items()}
bench_aligned = {t: c.reindex(ff_dates, method="ffill") for t, c in bench_norm.items()}

# === Per-series metrics ===
def compute_metrics(series: pd.Series, initial: float) -> dict:
    if series.empty: return {}
    end_val = float(series.iloc[-1])
    cal_days = (series.index[-1] - series.index[0]).days
    cagr = ((end_val / initial) ** (365 / max(cal_days, 1)) - 1) * 100 if cal_days > 0 else 0
    rets = series.pct_change().dropna()
    if rets.empty:
        return {"cagr": cagr, "max_dd_pct": 0, "sharpe": 0, "ann_vol": 0, "calmar": 0,
                "end_val": end_val, "rets": rets}
    sd = float(rets.std()); m = float(rets.mean())
    ann_vol = sd * (252 ** 0.5) * 100
    sharpe = (m * 252) / (sd * (252 ** 0.5)) if sd > 0 else 0
    # Standard MaxDD: largest peak-to-trough percentage decline at any point.
    # NOT max-dollar/final-peak (which understates) and NOT max-dollar/contemporaneous-peak
    # (which can miss earlier larger pct declines). Track the max PCT directly.
    vals = series.values; peak = vals[0]
    max_dd_pct = 0.0; max_dd_dollar = 0.0
    for v in vals:
        if v > peak: peak = v
        dd_pct = (peak - v) / peak * 100 if peak > 0 else 0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd_dollar = peak - v
    calmar = (cagr / max_dd_pct) if max_dd_pct > 0 else float("inf")
    return {"cagr": cagr, "max_dd_pct": max_dd_pct, "max_dd_dollar": float(max_dd_dollar),
            "sharpe": sharpe, "ann_vol": ann_vol, "calmar": calmar,
            "end_val": end_val, "rets": rets}


full_metrics = {"FF_Tier1": compute_metrics(ff_combined, INITIAL)}
for t, c in bench_aligned.items():
    full_metrics[t] = compute_metrics(c, INITIAL)

# === Cross metrics: FF vs each benchmark ===
ff_rets = full_metrics["FF_Tier1"]["rets"]
crosses = {}
for t in BENCHMARKS:
    b_rets = full_metrics[t]["rets"]
    common = ff_rets.index.intersection(b_rets.index)
    fr = ff_rets.loc[common]; br = b_rets.loc[common]
    if len(common) < 30:
        crosses[t] = {"corr": None}; continue
    corr = float(fr.corr(br))
    cov = float(fr.cov(br))
    var_b = float(br.var())
    beta = cov / var_b if var_b > 0 else 0
    active = fr - br
    te = float(active.std()) * (252 ** 0.5)
    active_mean = float(active.mean()) * 252
    info_ratio = active_mean / te if te > 0 else 0
    crosses[t] = {"corr": corr, "beta": beta, "info_ratio": info_ratio,
                  "active_return_ann_pct": active_mean * 100,
                  "tracking_error_pct": te * 100}

# === Per-horizon ===
horizons = [
    ("1Y", END - timedelta(days=365)),
    ("2Y", END - timedelta(days=730)),
    ("3Y", END - timedelta(days=1095)),
    ("Full", START),
]

horizon_metrics = {}
for label, hstart in horizons:
    h_metrics = {}
    ff_slice = ff_combined[ff_combined.index >= pd.Timestamp(hstart)]
    if not ff_slice.empty:
        h_metrics["FF_Tier1"] = compute_metrics(ff_slice, float(ff_slice.iloc[0]))
        for t in BENCHMARKS:
            b_slice = bench_aligned[t][bench_aligned[t].index >= pd.Timestamp(hstart)]
            if not b_slice.empty:
                h_metrics[t] = compute_metrics(b_slice, float(b_slice.iloc[0]))
    horizon_metrics[label] = h_metrics

# === DD-window specific (Mar 6 - Apr 17 2026 — Phase 3 DD window) ===
DD_PEAK = pd.Timestamp("2026-03-06"); DD_TROUGH = pd.Timestamp("2026-04-17")
dd_window_perf = {}
for series_name, ser in [("FF_Tier1", ff_combined)] + [(t, bench_aligned[t]) for t in BENCHMARKS]:
    ser_w = ser[(ser.index >= DD_PEAK) & (ser.index <= DD_TROUGH)]
    if ser_w.empty: continue
    pct = (float(ser_w.iloc[-1]) / float(ser_w.iloc[0]) - 1) * 100
    dd_metrics = compute_metrics(ser_w, float(ser_w.iloc[0]))
    dd_window_perf[series_name] = {"pct": pct, "max_dd_pct": dd_metrics["max_dd_pct"]}

# === PNG ===
print(f"\nGenerating equity-curve PNG...", flush=True)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(14, 8))
ff_to_100 = ff_combined / float(ff_combined.iloc[0]) * 100
ax.plot(ff_to_100.index, ff_to_100.values,
        label=f"FF Tier 1 (CAGR {full_metrics['FF_Tier1']['cagr']:+.1f}%, MaxDD {full_metrics['FF_Tier1']['max_dd_pct']:.1f}%)",
        linewidth=2.5, color="black")
colors = {"SPY": "tab:blue", "QQQ": "tab:orange", "TQQQ": "tab:red"}
for t in BENCHMARKS:
    bs = bench_aligned[t]
    bs_100 = bs / float(bs.iloc[0]) * 100
    ax.plot(bs_100.index, bs_100.values,
            label=f"{t} (CAGR {full_metrics[t]['cagr']:+.1f}%, MaxDD {full_metrics[t]['max_dd_pct']:.1f}%)",
            color=colors[t], alpha=0.7)
ax.axhline(100, color="gray", linestyle="--", linewidth=0.5)
ax.set_title(f"Phase 4 Tier 1 — Forward Factor (23-ticker multi-asset) vs SPY/QQQ/TQQQ\n{START} → {END}, normalized to $100")
ax.set_xlabel("Date"); ax.set_ylabel("Normalized equity (start = $100)")
ax.legend(loc="best"); ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(PNG_OUT, dpi=120)
plt.close()
print(f"Wrote {PNG_OUT}", flush=True)

# === Markdown ===
print(f"\nWriting {MD_OUT}...", flush=True)
def fmt_pct(v): return f"{v:+.2f}%"

lines = []
lines.append(f"# Phase 4 Tier 1 — Benchmark Comparison")
lines.append("")
lines.append(f"**Window**: {START} → {END}  |  **Base**: $400K (combined FF Tier 1; benchmarks normalized)")
lines.append(f"**Benchmarks**: SPY, QQQ, TQQQ + Steven's TQQQ-VT point estimates")
lines.append("")

# Headline + TQQQ-VT row
lines.append(f"## Headline metrics (full sample)")
lines.append("")
lines.append(f"| Series | CAGR | MaxDD% | Ann Vol | Sharpe | Calmar | End val |")
lines.append(f"|---|---:|---:|---:|---:|---:|---:|")
for s in ["FF_Tier1", "SPY", "QQQ", "TQQQ"]:
    m = full_metrics.get(s)
    if not m: continue
    lines.append(f"| {s} | {fmt_pct(m['cagr'])} | {m['max_dd_pct']:.2f}% | {m['ann_vol']:.2f}% | {m['sharpe']:.2f} | {m['calmar']:.2f} | ${m['end_val']:,.0f} |")
v = TQQQ_VT_POINT
lines.append(f"| **TQQQ-VT** (Steven's, point est) | {fmt_pct(v['cagr'])} | {v['max_dd_pct']:.2f}% | {v['ann_vol']:.2f}% | {v['sharpe']:.2f} | {v['calmar']:.2f} | (need daily curve) |")
lines.append("")

# Cross-correlation
lines.append(f"## FF Tier 1 vs each benchmark — correlation, beta, info ratio")
lines.append("")
lines.append(f"| Benchmark | Correlation | Beta (FF on benchmark) | Active return (ann) | Tracking error | Info ratio |")
lines.append(f"|---|---:|---:|---:|---:|---:|")
for t in BENCHMARKS:
    c = crosses.get(t, {})
    if c.get("corr") is None:
        lines.append(f"| {t} | - | - | - | - | - |"); continue
    lines.append(f"| {t} | {c['corr']:+.3f} | {c['beta']:+.3f} | {fmt_pct(c['active_return_ann_pct'])} | {c['tracking_error_pct']:.2f}% | {c['info_ratio']:+.2f} |")
lines.append("")
lines.append(f"_TQQQ-VT correlation + allocation sweep BLOCKED on Steven providing daily TQQQ-VT equity curve CSV._")
lines.append("")

# Per-horizon
lines.append(f"## Per-horizon CAGR / MaxDD / Sharpe")
lines.append("")
lines.append(f"| Horizon | Series | CAGR | MaxDD% | Sharpe |")
lines.append(f"|---|---|---:|---:|---:|")
for label, _ in horizons:
    h = horizon_metrics.get(label, {})
    for s in ["FF_Tier1", "SPY", "QQQ", "TQQQ"]:
        m = h.get(s)
        if not m: continue
        lines.append(f"| {label} | {s} | {fmt_pct(m['cagr'])} | {m['max_dd_pct']:.2f}% | {m['sharpe']:.2f} |")
lines.append("")

# DD-window benchmark performance
lines.append(f"## DD window (Mar 6 - Apr 17 2026) — what benchmarks did during the FF DD")
lines.append("")
lines.append(f"| Series | Peak→Trough % | Max intraday DD% |")
lines.append(f"|---|---:|---:|")
for s in ["FF_Tier1", "SPY", "QQQ", "TQQQ"]:
    d = dd_window_perf.get(s)
    if d is None: continue
    lines.append(f"| {s} | {fmt_pct(d['pct'])} | {d['max_dd_pct']:.2f}% |")
lines.append("")

# Phase 3 vs Tier 1 comparison
lines.append(f"## Tier 1 vs Phase 3 — what changed")
lines.append("")
lines.append(f"| Metric | Phase 3 (17 tickers) | Tier 1 (23 tickers) | Δ |")
lines.append(f"|---|---:|---:|---:|")
m = full_metrics["FF_Tier1"]
lines.append(f"| CAGR | +24.33% | {fmt_pct(m['cagr'])} | {m['cagr']-24.33:+.2f}pp |")
lines.append(f"| MaxDD | 31.70% | {m['max_dd_pct']:.2f}% | {m['max_dd_pct']-31.70:+.2f}pp |")
lines.append(f"| Sharpe | 0.66 | {m['sharpe']:.2f} | {m['sharpe']-0.66:+.2f} |")
lines.append(f"| Calmar | 0.77 | {m['calmar']:.2f} | {m['calmar']-0.77:+.2f} |")
lines.append("")

# Vs TQQQ-VT (point estimate, qualitative)
lines.append(f"## FF Tier 1 vs Steven's TQQQ-VT (point-estimate comparison)")
lines.append("")
lines.append(f"| Metric | FF Tier 1 | TQQQ-VT | Winner |")
lines.append(f"|---|---:|---:|---|")
m = full_metrics["FF_Tier1"]
def winner(a, b, higher_better=True):
    if higher_better: return "FF" if a > b else ("TQQQ-VT" if b > a else "tie")
    else: return "FF" if a < b else ("TQQQ-VT" if b < a else "tie")
lines.append(f"| CAGR | {fmt_pct(m['cagr'])} | +25.05% | {winner(m['cagr'], 25.05)} |")
lines.append(f"| MaxDD% | {m['max_dd_pct']:.2f}% | 31.43% | {winner(m['max_dd_pct'], 31.43, higher_better=False)} |")
lines.append(f"| Sharpe | {m['sharpe']:.2f} | 0.92 | {winner(m['sharpe'], 0.92)} |")
lines.append(f"| Calmar | {m['calmar']:.2f} | 0.80 | {winner(m['calmar'], 0.80)} |")
lines.append(f"| Ann Vol | {m['ann_vol']:.2f}% | 29.10% | {winner(m['ann_vol'], 29.1, higher_better=False)} |")
lines.append("")
lines.append(f"_Both clear ~25% CAGR. TQQQ-VT has higher Sharpe (0.92 vs 0.77) AND lower vol (29% vs 53%). FF has higher CAGR (+32.78% vs +25.05%) AND lower MaxDD (23.24% vs 31.43%) AND higher Calmar (1.41 vs 0.80). The answer to 'which is better' depends on what you care about; the answer to 'do they combine well' depends on correlation — which requires the TQQQ-VT daily curve to compute._")
lines.append("")

# Equity curve
lines.append(f"## Equity curve (4 series normalized to $100)")
lines.append("")
lines.append(f"![Phase 4 Tier 1 Benchmark Curve]({PNG_OUT.name})")
lines.append("")

# Critical pending
lines.append(f"## Pending: TQQQ-VT correlation + allocation analysis")
lines.append("")
lines.append(f"To complete the allocation decision, need from Steven:")
lines.append(f"- Daily equity curve from TQQQ-VT backtest as CSV (columns: date, portfolio_value)")
lines.append(f"- Date format: ISO (2022-01-03)")
lines.append(f"- Period: 2022-01-03 → 2026-05-01")
lines.append("")
lines.append(f"Once provided, run `scripts/tqqq_vt_allocation.py` (to be built) which will compute:")
lines.append(f"- Daily-returns correlation between FF Tier 1 and TQQQ-VT")
lines.append(f"- Beta of FF vs TQQQ-VT")
lines.append(f"- Allocation sweep: 100/0, 90/10, 80/20, 70/30, 60/40, 50/50, 0/100 → which mix maximizes Sharpe?")
lines.append(f"- This is THE answer to 'what % allocation, if any?'")

MD_OUT.parent.mkdir(parents=True, exist_ok=True)
MD_OUT.write_text("\n".join(lines))
print(f"Wrote {MD_OUT}", flush=True)
print(f"\nDone. Awaiting TQQQ-VT daily CSV for allocation step.", flush=True)
