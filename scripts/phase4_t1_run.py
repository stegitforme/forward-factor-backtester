"""Phase 4 Tier 1: discovery + simulation + per-asset-class report.

Universe (23): 17 incumbent + 6 passers from pre-flight (EEM, FXI, HYG, GLD, SLV, USO).
Config: Phase 3 baseline (no caps, no vol-target).
Hypothesis: does FF generalize beyond equity-vol?

Reporting:
  - Headline metrics
  - Per-asset-class breakdown (equity / bond / commodity / international)
  - Per-ticker P&L attribution with GLD isolated
  - Concentration: top-5 ticker % of P&L (vs Phase 3 78%)
  - Correlation to baseline Phase 3 equity curve
  - Per-ticker resolution rate
  - Decision gate: $50K threshold for non-equity P&L

Output: output/PHASE_4_T1_REPORT.md
"""
from __future__ import annotations

import json
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

# Universe
INCUMBENT = ["SPY", "IWM", "SMH", "XBI", "KWEB", "TLT", "MSTR",
             "KRE", "KBE", "XLF", "IBB", "ARKK", "COIN", "AMD", "META", "GOOGL", "JPM"]
NEW_PASSERS = ["EEM", "FXI", "HYG", "GLD", "SLV", "USO"]
UNIVERSE = sorted(set(INCUMBENT + NEW_PASSERS))

# Asset class mapping
ASSET_CLASS = {
    # Equity broad/sector
    "SPY": "equity_broad", "IWM": "equity_broad", "QQQ": "equity_broad",
    "SMH": "equity_sector", "XBI": "equity_sector", "XLF": "equity_sector",
    "KRE": "equity_sector", "KBE": "equity_sector", "IBB": "equity_sector",
    "ARKK": "equity_thematic",
    # Equity single names
    "MSTR": "equity_single_name", "META": "equity_single_name", "AMD": "equity_single_name",
    "GOOGL": "equity_single_name", "JPM": "equity_single_name", "COIN": "equity_single_name",
    # Bonds
    "TLT": "bond", "HYG": "bond",
    # Commodity
    "GLD": "commodity_metal", "SLV": "commodity_metal", "USO": "commodity_oil",
    # International
    "EEM": "equity_international", "FXI": "equity_international", "KWEB": "equity_international",
}

CANDIDATES_PATH = Path("output/phase4_t1_candidates.parquet")
PHASE3_EQUITY = Path("output/sim_b31247ce13e0/daily_mtm_equity.csv")  # baseline regression hash
SUMMARY_PATH = Path("output/PHASE_4_T1_REPORT.md")

# Use Phase 3 baseline config — caps + vol-target both disabled
BASE = RunConfig()
CFG = replace(
    BASE,
    universe=tuple(UNIVERSE),
    position_cap_contracts=None,
    position_cap_contracts_per_ticker_cell=None,
    position_cap_nav_pct=None,
    position_cap_strike_mtm=None,
    vol_target_annualized=None,
)

print(f"### PHASE 4 TIER 1", flush=True)
print(f"Universe ({len(UNIVERSE)}): {UNIVERSE}", flush=True)
print(f"  Incumbents (17): {INCUMBENT}", flush=True)
print(f"  New (6): {NEW_PASSERS}", flush=True)
print(f"Window: {CFG.start_date} → {CFG.end_date}", flush=True)
print(f"Cells: {[c[0] for c in CFG.cells]}", flush=True)
print()

# --- Discovery ---
if CANDIDATES_PATH.exists():
    print(f"[discovery] reusing {CANDIDATES_PATH}", flush=True)
else:
    print(f"[discovery] running fresh on 23-ticker universe...", flush=True)
    t0 = time.time()
    discover(
        start_date=date.fromisoformat(CFG.start_date),
        end_date=date.fromisoformat(CFG.end_date),
        universe=list(UNIVERSE),
        cells=list(CFG.cells),
        output_path=CANDIDATES_PATH,
        max_workers=12,
    )
    print(f"  discovery done in {time.time()-t0:.0f}s", flush=True)

# Load candidates (always — for resolution stats in the report)
cands = pd.read_parquet(CANDIDATES_PATH)
discovery_run_id = str(cands["discovery_run_id"].iloc[0])

# --- Simulation ---
print(f"\n[simulate] config_hash={CFG.short_hash()}", flush=True)
t0 = time.time()
metrics = simulate(CANDIDATES_PATH, CFG, "output", discovery_run_id=discovery_run_id)
print(f"  simulation done in {time.time()-t0:.0f}s", flush=True)

# --- Load outputs ---
out_dir = Path("output") / f"sim_{CFG.short_hash()}"
trades = pd.read_csv(out_dir / "trade_log.csv")
eq = pd.read_csv(out_dir / "daily_mtm_equity.csv", parse_dates=["date"])
eq.set_index("date", inplace=True)


# --- Metrics helpers ---
def _max_dd(equity: pd.Series) -> dict:
    """Standard MaxDD: largest peak-to-trough percentage decline at any point.
    Tracks by PCT (not dollar) so multiple drawdowns at different equity scales
    are compared correctly. PCT-max is the canonical risk metric."""
    if equity.empty: return {"max_dd_pct": 0, "max_dd_dollar": 0, "dd_days": 0}
    vals = equity.values; dates = equity.index
    peak = vals[0]; cur_pi = 0
    max_dd_pct = 0.0; max_dd_dollar = 0.0
    pi_at = 0; ti = 0
    for i, v in enumerate(vals):
        if v > peak: peak = v; cur_pi = i
        dd_pct = (peak - v) / peak * 100 if peak > 0 else 0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd_dollar = peak - v
            pi_at = cur_pi; ti = i
    return {"max_dd_pct": max_dd_pct, "max_dd_dollar": float(max_dd_dollar),
            "dd_days": int(ti - pi_at),
            "peak_date": str(dates[pi_at].date()) if hasattr(dates[pi_at], "date") else str(dates[pi_at]),
            "trough_date": str(dates[ti].date()) if hasattr(dates[ti], "date") else str(dates[ti])}


def _full_metrics(equity: pd.Series, base: float) -> dict:
    if equity.empty: return {}
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
    return {"cagr_pct": cagr, "ann_vol_pct": ann_vol, "sharpe": sharpe, "calmar": calmar,
            "end_val": end_val, **dd}


combined = eq["combined"]
base_combined = CFG.initial_capital_per_cell * len(CFG.cells)
full = _full_metrics(combined, base_combined)


# --- Per-ticker P&L ---
ticker_pnl = {}
for _, row in trades.iterrows():
    t = row["ticker"]
    ticker_pnl.setdefault(t, {"opens": 0, "closed": 0, "pnl": 0.0})
    ticker_pnl[t]["opens"] += 1
    if pd.notna(row["pnl_total"]):
        ticker_pnl[t]["closed"] += 1
        ticker_pnl[t]["pnl"] += float(row["pnl_total"])

# --- Per-asset-class aggregate ---
class_pnl = {}
for t, m in ticker_pnl.items():
    cls = ASSET_CLASS.get(t, "unknown")
    class_pnl.setdefault(cls, {"opens": 0, "closed": 0, "pnl": 0.0, "tickers": []})
    class_pnl[cls]["opens"] += m["opens"]
    class_pnl[cls]["closed"] += m["closed"]
    class_pnl[cls]["pnl"] += m["pnl"]
    if t not in class_pnl[cls]["tickers"]:
        class_pnl[cls]["tickers"].append(t)

# --- Concentration ---
sorted_pnl = sorted(ticker_pnl.items(), key=lambda kv: -kv[1]["pnl"])
top5_pnl = sum(m["pnl"] for _, m in sorted_pnl[:5])
total_pnl = sum(m["pnl"] for _, m in sorted_pnl)
top5_concentration = (top5_pnl / total_pnl * 100) if total_pnl != 0 else 0

# --- Correlation to baseline Phase 3 ---
correlation_to_phase3 = None
if PHASE3_EQUITY.exists():
    p3 = pd.read_csv(PHASE3_EQUITY, parse_dates=["date"]).set_index("date")
    common = combined.index.intersection(p3.index)
    if len(common) > 30:
        new_rets = combined.loc[common].pct_change().dropna()
        p3_rets = p3.loc[common, "combined"].pct_change().dropna()
        idx = new_rets.index.intersection(p3_rets.index)
        if len(idx) > 30:
            correlation_to_phase3 = float(new_rets.loc[idx].corr(p3_rets.loc[idx]))

# --- Per-ticker resolution + candidate stats from parquet ---
tk_resolved = {}
for t in UNIVERSE:
    sub = cands[cands["ticker"] == t]
    n = len(sub)
    n_resolved = int(sub["back_leg_resolved"].sum())
    n_ff_above = int((sub["ff"] >= CFG.ff_threshold).sum())
    tk_resolved[t] = {"n": n, "resolved": n_resolved, "ff_above": n_ff_above,
                       "resolved_pct": (100*n_resolved/n) if n else 0}

# --- Decision gate ---
non_equity_classes = ["bond", "commodity_metal", "commodity_oil"]  # excludes equity_international
non_equity_pnl = sum(class_pnl.get(c, {"pnl": 0})["pnl"] for c in non_equity_classes)
gld_pnl = ticker_pnl.get("GLD", {"pnl": 0})["pnl"]

# === Markdown report ===
print(f"\n\nWriting {SUMMARY_PATH}...", flush=True)
def fmt_pct(v): return f"{v:+.2f}%"

lines = []
lines.append(f"# Phase 4 Tier 1 — Universe Expansion to Multi-Asset")
lines.append("")
lines.append(f"**Window**: {CFG.start_date} → {CFG.end_date}  |  **Universe**: {len(UNIVERSE)} tickers (17 incumbent + 6 new)")
lines.append(f"**Config**: Phase 3 baseline — no caps, no vol-target, uniform FF=0.20, earnings ON, MAX_CONCURRENT=12")
lines.append(f"**Hypothesis**: does the FF signal generalize beyond equity-vol?")
lines.append(f"**discovery_run_id**: `{discovery_run_id}`")
lines.append("")

# Headline
lines.append(f"## Headline metrics (combined MTM, $400K base)")
lines.append("")
lines.append(f"| Metric | Tier 1 (23 tickers) | Phase 3 baseline (17 tickers) | Δ |")
lines.append(f"|---|---:|---:|---:|")
phase3_baseline = {"cagr_pct": 24.33, "max_dd_pct": 31.70, "sharpe": 0.66, "calmar": 0.77,
                    "ann_vol_pct": 52.43, "n_closed": 490, "end_val": 1025381}
lines.append(f"| MTM CAGR | {fmt_pct(full['cagr_pct'])} | +24.33% | {full['cagr_pct']-24.33:+.2f}pp |")
lines.append(f"| MaxDD% | {full['max_dd_pct']:.2f}% | 31.70% | {full['max_dd_pct']-31.70:+.2f}pp |")
lines.append(f"| Sharpe | {full['sharpe']:.2f} | 0.66 | {full['sharpe']-0.66:+.2f} |")
lines.append(f"| Calmar | {full['calmar']:.2f} | 0.77 | {full['calmar']-0.77:+.2f} |")
lines.append(f"| Ann Vol | {full['ann_vol_pct']:.2f}% | 52.43% | {full['ann_vol_pct']-52.43:+.2f}pp |")
lines.append(f"| Closed trades | {sum(t['closed'] for t in ticker_pnl.values())} | 490 | {sum(t['closed'] for t in ticker_pnl.values())-490:+d} |")
lines.append(f"| End equity | ${full['end_val']:,.0f} | $1,025,381 | ${full['end_val']-1025381:+,.0f} |")
lines.append("")

# Correlation
if correlation_to_phase3 is not None:
    lines.append(f"**Daily-returns correlation to Phase 3 baseline equity curve: {correlation_to_phase3:+.3f}**")
    if correlation_to_phase3 > 0.95:
        lines.append(f"_Curves are nearly identical — adding 6 new tickers barely shifted the strategy character._")
    elif correlation_to_phase3 > 0.80:
        lines.append(f"_Curves are highly correlated — new tickers contributed but didn't fundamentally diversify._")
    else:
        lines.append(f"_Curves diverge meaningfully — new tickers materially shifted the strategy character._")
    lines.append("")

# Per-asset-class
lines.append(f"## Per-asset-class P&L breakdown")
lines.append("")
lines.append(f"| Asset class | Tickers | Opens | Closed | Sum P&L | % of total |")
lines.append(f"|---|---|---:|---:|---:|---:|")
for cls in sorted(class_pnl.keys()):
    m = class_pnl[cls]
    pct = (100 * m["pnl"] / total_pnl) if total_pnl != 0 else 0
    lines.append(f"| {cls} | {', '.join(sorted(m['tickers']))} | {m['opens']} | {m['closed']} | ${m['pnl']:+,.0f} | {pct:+.1f}% |")
lines.append("")

# Per-ticker (full table, sorted by P&L)
lines.append(f"## Per-ticker P&L attribution (full table, sorted by P&L)")
lines.append("")
lines.append(f"| Ticker | Asset class | Opens | Closed | Resolution% | FF≥0.20 candidates | Strict P&L | % total |")
lines.append(f"|---|---|---:|---:|---:|---:|---:|---:|")
for t, m in sorted_pnl:
    cls = ASSET_CLASS.get(t, "?")
    res = tk_resolved.get(t, {})
    is_new = " (NEW)" if t in NEW_PASSERS else ""
    pct = (100 * m["pnl"] / total_pnl) if total_pnl != 0 else 0
    is_gld = " ⭐" if t == "GLD" else ""
    lines.append(f"| {t}{is_new}{is_gld} | {cls} | {m['opens']} | {m['closed']} | {res.get('resolved_pct', 0):.1f}% | {res.get('ff_above', 0)} | ${m['pnl']:+,.0f} | {pct:+.1f}% |")
lines.append("")

# Concentration
lines.append(f"## Concentration check")
lines.append("")
lines.append(f"| Metric | Tier 1 | Phase 3 baseline |")
lines.append(f"|---|---:|---:|")
lines.append(f"| Top-5 ticker % of P&L | **{top5_concentration:.1f}%** | **78%** |")
lines.append(f"")
lines.append(f"Top 5 contributors:")
for i, (t, m) in enumerate(sorted_pnl[:5], 1):
    cls = ASSET_CLASS.get(t, "?")
    pct = (100 * m["pnl"] / total_pnl) if total_pnl != 0 else 0
    lines.append(f"{i}. **{t}** ({cls}): ${m['pnl']:+,.0f}  ({pct:+.1f}% of total)")
lines.append("")

# Decision gate
lines.append(f"## Decision gate — does FF generalize beyond equity-vol?")
lines.append("")
lines.append(f"| Threshold | Result | Verdict |")
lines.append(f"|---|---|---|")
non_eq_status = "✓ World B (multi-asset)" if non_equity_pnl >= 50_000 else "✗ World A (equity-vol-only)"
lines.append(f"| Non-equity ETFs (bond + commodity) total P&L >= $50K? | ${non_equity_pnl:+,.0f} | {non_eq_status} |")
gld_status = "STRONG generalization signal" if gld_pnl >= 25_000 else ("WEAK signal" if gld_pnl >= 5_000 else "NO signal — equity-vol-specific")
lines.append(f"| GLD specifically (43% resolution, cleanest non-equity test): | ${gld_pnl:+,.0f} | {gld_status} |")
lines.append("")

# Verdict summary
lines.append(f"## Verdict summary")
lines.append("")
if non_equity_pnl >= 50_000:
    lines.append(f"**WORLD B**: FF generalizes to non-equity asset classes. Non-equity P&L = ${non_equity_pnl:+,.0f}.")
    lines.append(f"")
    lines.append(f"Recommendations:")
    lines.append(f"- Strategy is a genuine multi-asset diversifier, not equity-vol-specific")
    lines.append(f"- Larger allocation defensible (vs equity-vol-only framing)")
    lines.append(f"- Tiers 2-3 (more cells, signal-quality sizing) become productive next steps")
else:
    lines.append(f"**WORLD A**: FF is fundamentally an equity-vol trade. Non-equity P&L = ${non_equity_pnl:+,.0f} (below $50K threshold).")
    lines.append(f"")
    lines.append(f"Recommendations:")
    lines.append(f"- Strategy is real but specifically captures equity-vol regimes")
    lines.append(f"- Concentration in IWM/sector-equity is structural to what the strategy IS")
    lines.append(f"- Tiers 2-3 unlikely to fundamentally change this — not worth pursuing")
    lines.append(f"- Move to allocation framings: small satellite (5-7%) vs watch-list state vs decline")

SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
SUMMARY_PATH.write_text("\n".join(lines))
print(f"Wrote {SUMMARY_PATH}", flush=True)
print(f"\nNon-equity P&L: ${non_equity_pnl:+,.0f}  |  GLD P&L: ${gld_pnl:+,.0f}", flush=True)
print(f"Verdict: {'WORLD B (multi-asset)' if non_equity_pnl >= 50_000 else 'WORLD A (equity-vol-only)'}", flush=True)
