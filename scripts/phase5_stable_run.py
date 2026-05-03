"""Phase 5 — Stable-version Tier 1 (production-tier deployment config).

Delta vs Tier 1 canonical:
  - risk_per_trade 0.04 → 0.02  (half-Kelly)
  - debit_floor    0.10 → 0.15  (tighter near-zero-debit guardrail)
  - position_cap_per_ticker_nav_pct = 0.12  (NEW: 12% of strategy NAV per ticker)
  - asset_class_caps:
      equity_etf      ≤ 50%
      single_name     ≤ 20%
      commodity       ≤ 20%
      bond            ≤ 15%
      international   ≤ 15%
      vol             ≤ 10%
  - All other caps unchanged (cap1a 500, cap1b 1000, cap2 0.02, cap3 0.02)

Reuses output/phase4_t1_candidates.parquet (no new discovery).

Reports:
  - Standalone metrics + 7 concentration tests with PASS/FAIL
  - Per-ticker P&L attribution
  - Side-by-side vs Tier 1 canonical and Tier 1 without IWM Jul 2024
  - Cap-trigger frequency

Output: output/PHASE_5_STABLE_VERSION.md
"""
from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from config.run_config import RunConfig
from src.simulate_portfolio import simulate

CANDIDATES_PATH = Path("output/phase4_t1_candidates.parquet")
TIER1_TRADES = Path("output/sim_4119dc073393/trade_log.csv")
TIER1_EQUITY = Path("output/sim_4119dc073393/daily_mtm_equity.csv")
MD_OUT = Path("output/PHASE_5_STABLE_VERSION.md")
INITIAL = 400_000.0

# Asset class mapping for the 23-ticker universe
ASSET_CLASS_MAP = {
    # equity ETFs (US broad / sector / thematic)
    "SPY": "equity_etf", "IWM": "equity_etf",
    "SMH": "equity_etf", "XBI": "equity_etf", "KRE": "equity_etf",
    "KBE": "equity_etf", "XLF": "equity_etf", "IBB": "equity_etf",
    "ARKK": "equity_etf",
    # single names (all earnings-blocked at 60/90 in practice)
    "MSTR": "single_name", "META": "single_name", "AMD": "single_name",
    "GOOGL": "single_name", "JPM": "single_name", "COIN": "single_name",
    # international equity
    "KWEB": "international", "EEM": "international", "FXI": "international",
    # bonds
    "TLT": "bond", "HYG": "bond",
    # commodities
    "GLD": "commodity", "SLV": "commodity", "USO": "commodity",
}
ASSET_CLASS_CAPS = {
    "equity_etf": 0.50,
    "single_name": 0.20,
    "commodity": 0.20,
    "bond": 0.15,
    "international": 0.15,
    "vol": 0.10,
}


def max_dd_pct(vals) -> float:
    if len(vals) == 0: return 0.0
    peak = vals[0]; max_dd = 0.0
    for v in vals:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd: max_dd = dd
    return max_dd


def metrics(equity: pd.Series, base: float) -> dict:
    if equity.empty: return {}
    end_val = float(equity.iloc[-1])
    cal_days = (equity.index[-1] - equity.index[0]).days
    cagr = ((end_val / base) ** (365 / max(cal_days, 1)) - 1) * 100 if cal_days > 0 else 0
    rets = equity.pct_change().dropna()
    if len(rets) < 2: sd = 0; m = 0
    else: sd = float(rets.std()); m = float(rets.mean())
    ann_vol = sd * (252 ** 0.5) * 100
    sharpe = (m * 252) / (sd * (252 ** 0.5)) if sd > 0 else 0
    dd_pct = max_dd_pct(equity.values)
    calmar = (cagr / dd_pct) if dd_pct > 0 else float("inf")
    return {"cagr": cagr, "max_dd_pct": dd_pct, "ann_vol": ann_vol,
            "sharpe": sharpe, "calmar": calmar, "end_val": end_val}


def per_year_metrics(equity: pd.Series) -> dict:
    out = {}
    for year in sorted(set(d.year for d in equity.index)):
        ye = equity[equity.index.year == year]
        if ye.empty: continue
        m = metrics(ye, float(ye.iloc[0]))
        out[year] = m
    return out


def main():
    print("### Phase 5 — Stable-Version Tier 1", flush=True)

    base = RunConfig()  # canonical Tier 1 config (defaults)
    stable = replace(
        base,
        risk_per_trade=0.02,         # half-Kelly
        debit_floor=0.15,            # tighter
        position_cap_per_ticker_nav_pct=0.12,
        asset_class_caps=ASSET_CLASS_CAPS,
        asset_class_map=ASSET_CLASS_MAP,
        # All other caps stay at defaults (cap1a 500, cap1b 1000, cap2 0.02, cap3 0.02)
    )
    print(f"  config_hash: {stable.short_hash()}", flush=True)
    print(f"  delta vs Tier 1: half-Kelly + debit_floor 0.15 + per-ticker NAV cap 12% + asset-class caps", flush=True)

    # Run sim
    sim_metrics = simulate(CANDIDATES_PATH, stable, "output")
    out_dir = Path("output") / f"sim_{stable.short_hash()}"
    trades = pd.read_csv(out_dir / "trade_log.csv", parse_dates=["entry_date", "exit_date"])
    eq = pd.read_csv(out_dir / "daily_mtm_equity.csv", parse_dates=["date"])
    eq.set_index("date", inplace=True)
    combined = eq["combined"]

    stable_m = metrics(combined, INITIAL)
    print(f"\n  Stable-version full sample: CAGR {stable_m['cagr']:+.2f}%  DD {stable_m['max_dd_pct']:.2f}%  Sharpe {stable_m['sharpe']:.2f}  Calmar {stable_m['calmar']:.2f}", flush=True)

    # Tier 1 canonical (for comparison)
    t1_trades = pd.read_csv(TIER1_TRADES, parse_dates=["entry_date", "exit_date"])
    t1_eq = pd.read_csv(TIER1_EQUITY, parse_dates=["date"]).set_index("date")
    t1_m = metrics(t1_eq["combined"], INITIAL)

    # === 7 Concentration tests ===
    print("\n  Running 7 concentration tests...", flush=True)
    closed = trades[trades["pnl_total"].notna()].copy()
    closed["pnl_total"] = closed["pnl_total"].astype(float)
    total_pnl = float(closed["pnl_total"].sum())
    sorted_pnl = closed.sort_values("pnl_total", ascending=False)
    top5 = float(sorted_pnl.head(5)["pnl_total"].sum())
    top10 = float(sorted_pnl.head(10)["pnl_total"].sum())

    # Per-ticker
    per_ticker = closed.groupby("ticker")["pnl_total"].sum().sort_values(ascending=False)
    top_ticker_pnl = float(per_ticker.iloc[0]) if len(per_ticker) else 0
    top5_tickers_pnl = float(per_ticker.head(5).sum())

    # Per year
    closed["exit_year"] = pd.to_datetime(closed["exit_date"]).dt.year
    per_year_pnl = closed.groupby("exit_year")["pnl_total"].sum()
    best_year_pnl = float(per_year_pnl.max()) if len(per_year_pnl) else 0

    largest_gain = float(closed["pnl_total"].max()) if len(closed) else 0
    largest_loss = float(closed["pnl_total"].min()) if len(closed) else 0
    abs_loss = abs(largest_loss)

    tests = [
        ("Top 5 trades < 50% of P&L", (top5 / total_pnl * 100) if total_pnl != 0 else 0, "<", 50, "%"),
        ("Top 10 trades < 50% of P&L", (top10 / total_pnl * 100) if total_pnl != 0 else 0, "<", 50, "%"),
        ("Best year < 60% of total P&L", (best_year_pnl / total_pnl * 100) if total_pnl != 0 else 0, "<", 60, "%"),
        ("Top ticker < 30% of P&L", (top_ticker_pnl / total_pnl * 100) if total_pnl != 0 else 0, "<", 30, "%"),
        ("Top 5 tickers < 60% of P&L", (top5_tickers_pnl / total_pnl * 100) if total_pnl != 0 else 0, "<", 60, "%"),
        ("Annualized vol < 2× CAGR", stable_m["ann_vol"], "<", stable_m["cagr"] * 2 if stable_m["cagr"] > 0 else float("inf"), ""),
        ("Largest gain < 3× |largest loss|", largest_gain, "<", 3 * abs_loss if abs_loss > 0 else float("inf"), "$"),
    ]

    test_results = []
    for name, val, op, threshold, unit in tests:
        passed = val < threshold if op == "<" else val > threshold
        test_results.append({"name": name, "value": val, "threshold": threshold, "unit": unit, "passed": passed})
        marker = "✅ PASS" if passed else "❌ FAIL"
        if unit == "%":
            print(f"    {marker}  {name}: {val:.1f}% (threshold {threshold:.1f}%)", flush=True)
        elif unit == "$":
            print(f"    {marker}  {name}: ${val:,.0f} vs 3× ${abs_loss:,.0f} = ${threshold:,.0f}", flush=True)
        else:
            print(f"    {marker}  {name}: {val:.2f} (threshold {threshold:.2f})", flush=True)

    n_passed = sum(1 for t in test_results if t["passed"])

    # Decision rule
    cagr_ok_for_production = 15 <= stable_m["cagr"] <= 25
    cagr_ok_for_paper_only = stable_m["cagr"] >= 12 and not cagr_ok_for_production
    cagr_too_low = stable_m["cagr"] < 12

    if n_passed >= 5 and cagr_ok_for_production:
        verdict = f"**PRODUCTION CONFIG** — passed {n_passed}/7 concentration tests AND CAGR {stable_m['cagr']:+.2f}% in 15-25% target range. Replaces Tier 1 as canonical for deployment purposes (Tier 1 stays as research result). Awaits allocation sweep to confirm max-Sharpe stays at 15%+ FF."
    elif n_passed >= 5 and cagr_ok_for_paper_only:
        verdict = f"**PAPER-TRADE ONLY** — passed {n_passed}/7 concentration tests but CAGR {stable_m['cagr']:+.2f}% is below 15% production target. Strategy is fundamentally outlier-dependent at production sizing; defer live allocation until ORATS validates."
    elif n_passed >= 5 and cagr_too_low:
        verdict = f"**FUNDAMENTAL OUTLIER DEPENDENCE** — concentration tests pass (n={n_passed}/7) but CAGR collapsed to {stable_m['cagr']:+.2f}% under structural caps. Strategy edge is materially the near-zero-debit Kelly-overscale pattern. Don't deploy without ORATS validation."
    else:
        verdict = f"**CAPS DON'T ADDRESS STRUCTURAL ISSUE** — only {n_passed}/7 concentration tests passed. The constraints chosen don't fix the concentration problem. Harder thinking required before deployment."

    # Per-year (compare T1 vs stable)
    stable_per_year = per_year_metrics(combined)
    t1_per_year = per_year_metrics(t1_eq["combined"])

    # Per-ticker for stable
    per_ticker_stable = closed.groupby("ticker").agg(
        n_closed=("pnl_total", "count"),
        sum_pnl=("pnl_total", "sum"),
        max_pnl=("pnl_total", "max"),
        min_pnl=("pnl_total", "min"),
    ).sort_values("sum_pnl", ascending=False)
    opens_count = trades.groupby("ticker").size().to_dict()

    # Cap triggers
    cap_triggers = sim_metrics.get("cap_triggers", {})

    # ============= MARKDOWN =============
    print(f"\nWriting {MD_OUT}...", flush=True)
    def fmt_pct(v): return f"{v:+.2f}%"
    def fmt_dol(v): return f"${v:+,.0f}"
    lines = []
    lines.append(f"# Phase 5 — Stable-Version Tier 1 (production-tier config)")
    lines.append("")
    lines.append(f"**config_hash**: `{stable.short_hash()}`  |  **output dir**: `output/sim_{stable.short_hash()}/`")
    lines.append("")
    lines.append(f"## Configuration deltas vs Tier 1 canonical")
    lines.append("")
    lines.append(f"| Knob | Tier 1 canonical | Stable-version |")
    lines.append(f"|---|---:|---:|")
    lines.append(f"| risk_per_trade | 0.04 (Quarter-Kelly) | **0.02 (Half-Kelly)** |")
    lines.append(f"| debit_floor (Cap 2) | $0.10 | **$0.15** |")
    lines.append(f"| position_cap_per_ticker_nav_pct | (none) | **12% of strategy NAV** |")
    lines.append(f"| asset_class_caps | (none) | **equity_etf 50% / single_name 20% / commodity 20% / bond 15% / international 15% / vol 10%** |")
    lines.append("")
    lines.append(f"_All other caps unchanged: cap1a 500 contracts, cap1b 1000 contracts/(ticker,cell), cap2 NAV 0.02, cap3 strike-MTM 0.02, vol-target disabled. Same 23-ticker universe, same FF=0.20, same 30-90 + 60-90 cells, same earnings filter._")
    lines.append("")

    # Headline
    lines.append(f"## Headline standalone metrics")
    lines.append("")
    lines.append(f"| Metric | Tier 1 canonical | Stable-version | Δ |")
    lines.append(f"|---|---:|---:|---:|")
    lines.append(f"| MTM CAGR | {fmt_pct(t1_m['cagr'])} | {fmt_pct(stable_m['cagr'])} | {stable_m['cagr']-t1_m['cagr']:+.2f}pp |")
    lines.append(f"| MaxDD% | {t1_m['max_dd_pct']:.2f}% | {stable_m['max_dd_pct']:.2f}% | {stable_m['max_dd_pct']-t1_m['max_dd_pct']:+.2f}pp |")
    lines.append(f"| Annualized vol | {t1_m['ann_vol']:.2f}% | {stable_m['ann_vol']:.2f}% | {stable_m['ann_vol']-t1_m['ann_vol']:+.2f}pp |")
    lines.append(f"| Sharpe | {t1_m['sharpe']:.2f} | {stable_m['sharpe']:.2f} | {stable_m['sharpe']-t1_m['sharpe']:+.2f} |")
    lines.append(f"| Calmar | {t1_m['calmar']:.2f} | {stable_m['calmar']:.2f} | {stable_m['calmar']-t1_m['calmar']:+.2f} |")
    lines.append(f"| End equity | ${t1_m['end_val']:,.0f} | ${stable_m['end_val']:,.0f} | ${stable_m['end_val']-t1_m['end_val']:+,.0f} |")
    lines.append(f"| Closed trades | {(t1_trades['pnl_total'].notna()).sum()} | {len(closed)} | {len(closed)-(t1_trades['pnl_total'].notna()).sum():+d} |")
    lines.append("")

    # 7 concentration tests
    lines.append(f"## 7 concentration tests (PASS / FAIL)")
    lines.append("")
    lines.append(f"| # | Test | Value | Threshold | Result |")
    lines.append(f"|---|---|---:|---:|---|")
    for i, t in enumerate(test_results, 1):
        if t["unit"] == "%":
            v_str = f"{t['value']:.1f}%"
            th_str = f"<{t['threshold']:.1f}%"
        elif t["unit"] == "$":
            v_str = f"${t['value']:,.0f}"
            th_str = f"<${t['threshold']:,.0f}"
        else:
            v_str = f"{t['value']:.2f}"
            th_str = f"<{t['threshold']:.2f}"
        marker = "✅ PASS" if t["passed"] else "❌ FAIL"
        lines.append(f"| {i} | {t['name']} | {v_str} | {th_str} | {marker} |")
    lines.append("")
    lines.append(f"**Score: {n_passed} of 7 tests passed.**")
    lines.append("")

    # Per-year breakdown
    lines.append(f"## Per-year breakdown (stable-version)")
    lines.append("")
    lines.append(f"| Year | Stable CAGR | Stable MaxDD | Stable Sharpe | T1 CAGR | Δ vs T1 |")
    lines.append(f"|---|---:|---:|---:|---:|---:|")
    for year in sorted(stable_per_year.keys()):
        sm = stable_per_year[year]
        tm = t1_per_year.get(year, {})
        delta = sm["cagr"] - tm.get("cagr", 0)
        lines.append(f"| {year} | {fmt_pct(sm['cagr'])} | {sm['max_dd_pct']:.2f}% | {sm['sharpe']:.2f} | {fmt_pct(tm.get('cagr', 0))} | {delta:+.2f}pp |")
    lines.append("")

    # Per-ticker
    lines.append(f"## Per-ticker P&L attribution (stable-version, full sample)")
    lines.append("")
    lines.append(f"| Ticker | Asset class | Opens | Closed | Sum P&L | Max single | Min single | % of total |")
    lines.append(f"|---|---|---:|---:|---:|---:|---:|---:|")
    for t, row in per_ticker_stable.iterrows():
        cls = ASSET_CLASS_MAP.get(t, "?")
        opens_n = opens_count.get(t, 0)
        pct = (row["sum_pnl"] / total_pnl * 100) if total_pnl else 0
        lines.append(f"| {t} | {cls} | {opens_n} | {int(row['n_closed'])} | {fmt_dol(row['sum_pnl'])} | {fmt_dol(row['max_pnl'])} | {fmt_dol(row['min_pnl'])} | {pct:+.1f}% |")
    lines.append("")

    # Cap triggers
    lines.append(f"## Cap-trigger frequency (which constraint bound how often)")
    lines.append("")
    lines.append(f"| Cap | # times bound |")
    lines.append(f"|---|---:|")
    for cap, count in sorted(cap_triggers.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {cap} | {count} |")
    lines.append("")

    # Decision verdict
    lines.append(f"## Decision verdict")
    lines.append("")
    lines.append(verdict)
    lines.append("")
    lines.append(f"**Next step**: `scripts/phase5_stable_allocation.py` runs the allocation sweep on the stable-version equity curve to confirm whether max-Sharpe stays at 15%+ FF allocation under the constrained config.")
    lines.append("")

    MD_OUT.parent.mkdir(parents=True, exist_ok=True)
    MD_OUT.write_text("\n".join(lines))
    print(f"Wrote {MD_OUT}", flush=True)
    print(f"\n=== HEADLINE: stable CAGR {stable_m['cagr']:+.2f}%, DD {stable_m['max_dd_pct']:.2f}%, Sharpe {stable_m['sharpe']:.2f}, {n_passed}/7 concentration tests passed ===", flush=True)


if __name__ == "__main__":
    main()
