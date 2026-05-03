"""Phase 4 Tier 1 — 2024 attribution analysis.

Five analyses on output/sim_4119dc073393/ artifacts:
  1. Per-year metrics (CAGR/MaxDD/Sharpe/Vol/closed/P&L) for 2022/2023/2024/2025/2026 YTD
     plus side-by-side comparison to Phase 3 baseline
  2. 2024 quarterly breakdown (Q1/Q2/Q3/Q4 P&L + #trades + top 3 tickers)
  3. 2024 per-ticker P&L attribution (full table sorted by P&L)
  4. Concentration test: total 2024 vs excl top 5 / top 10 trades
  5. Single-trade outlier identification (P&L>$20K, return>200%, debit<$0.10)

Output: output/PHASE_4_T1_2024_ATTRIBUTION.md
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

TIER1_TRADES = Path("output/sim_4119dc073393/trade_log.csv")
TIER1_EQUITY = Path("output/sim_4119dc073393/daily_mtm_equity.csv")
MD_OUT = Path("output/PHASE_4_T1_2024_ATTRIBUTION.md")
INITIAL = 400_000.0  # combined base

# Phase 3 baseline per-year reference (from output/PHASE_3_FULL_BACKTEST.md)
PHASE3_PER_YEAR = {
    2022: {"cagr": 31.06, "max_dd": 15.76, "sharpe": 0.84, "dd_days": 23},
    2023: {"cagr": -7.72, "max_dd": 19.47, "sharpe": -0.13, "dd_days": 36},
    2024: {"cagr": 87.52, "max_dd": 22.12, "sharpe": 1.15, "dd_days": 16},
    2025: {"cagr": 12.27, "max_dd": 12.62, "sharpe": 0.49, "dd_days": 73},
    2026: {"cagr": 2.82, "max_dd": 31.70, "sharpe": 0.47, "dd_days": 30},
}


def max_dd_pct(equity: pd.Series) -> tuple[float, int, int]:
    if equity.empty: return 0.0, 0, 0
    vals = equity.values
    peak = vals[0]; max_dd = 0.0; pi = 0; ti = 0; cur_pi = 0
    for i, v in enumerate(vals):
        if v > peak: peak = v; cur_pi = i
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd: max_dd = dd; pi = cur_pi; ti = i
    return max_dd, pi, ti


def metrics_for_slice(equity: pd.Series, base_for_cagr: float = None) -> dict:
    if equity.empty: return {}
    if base_for_cagr is None: base_for_cagr = float(equity.iloc[0])
    end_val = float(equity.iloc[-1])
    cal_days = (equity.index[-1] - equity.index[0]).days
    cagr = ((end_val / base_for_cagr) ** (365 / max(cal_days, 1)) - 1) * 100 if cal_days > 0 else 0
    rets = equity.pct_change().dropna()
    if len(rets) < 2: sd = 0; m = 0
    else: sd = float(rets.std()); m = float(rets.mean())
    ann_vol = sd * (252 ** 0.5) * 100
    sharpe = (m * 252) / (sd * (252 ** 0.5)) if sd > 0 else 0
    dd_pct, pi, ti = max_dd_pct(equity)
    return {
        "cagr": cagr, "max_dd": dd_pct, "ann_vol": ann_vol, "sharpe": sharpe,
        "dd_days": int(ti - pi), "n_days": len(equity),
        "start_eq": base_for_cagr, "end_eq": end_val, "delta_eq": end_val - base_for_cagr,
    }


def main():
    print("### Phase 4 Tier 1 — 2024 Attribution Analysis", flush=True)
    trades = pd.read_csv(TIER1_TRADES, parse_dates=["entry_date", "exit_date"])
    eq = pd.read_csv(TIER1_EQUITY, parse_dates=["date"])
    eq.set_index("date", inplace=True)
    combined = eq["combined"]
    print(f"  loaded {len(trades)} trades, {len(eq)} equity days", flush=True)

    # === Section 1: per-year metrics ===
    print("\n[1] Per-year metrics...", flush=True)
    per_year = {}
    for year in sorted(set(d.year for d in eq.index)):
        year_eq = combined[combined.index.year == year]
        if year_eq.empty: continue
        m = metrics_for_slice(year_eq)
        # P&L for closed trades in this year
        year_closed = trades[trades["pnl_total"].notna() &
                              (pd.to_datetime(trades["exit_date"]).dt.year == year)]
        m["n_closed"] = len(year_closed)
        m["sum_pnl"] = float(year_closed["pnl_total"].sum())
        m["winners"] = int((year_closed["pnl_total"] > 0).sum())
        m["losers"] = int((year_closed["pnl_total"] <= 0).sum())
        per_year[year] = m

    # === Section 2: 2024 quarterly ===
    print("\n[2] 2024 quarterly breakdown...", flush=True)
    quarters = {
        "Q1": (date(2024, 1, 1), date(2024, 3, 31)),
        "Q2": (date(2024, 4, 1), date(2024, 6, 30)),
        "Q3": (date(2024, 7, 1), date(2024, 9, 30)),
        "Q4": (date(2024, 10, 1), date(2024, 12, 31)),
    }
    quarterly = {}
    for q, (qs, qe) in quarters.items():
        # Closed in this quarter (by exit_date)
        sub = trades[trades["pnl_total"].notna()].copy()
        sub["exit_d"] = pd.to_datetime(sub["exit_date"]).dt.date
        sub = sub[(sub["exit_d"] >= qs) & (sub["exit_d"] <= qe)]
        # Top 3 contributing tickers
        ticker_pnl = sub.groupby("ticker")["pnl_total"].agg(["sum", "count"]).sort_values("sum", ascending=False)
        top3 = ticker_pnl.head(3)
        quarterly[q] = {
            "n_closed": len(sub),
            "sum_pnl": float(sub["pnl_total"].sum()),
            "winners": int((sub["pnl_total"] > 0).sum()),
            "top3": [(t, float(top3.loc[t, "sum"]), int(top3.loc[t, "count"])) for t in top3.index],
        }

    # === Section 3: 2024 per-ticker ===
    print("\n[3] 2024 per-ticker attribution...", flush=True)
    sub2024 = trades[trades["pnl_total"].notna()].copy()
    sub2024["exit_d"] = pd.to_datetime(sub2024["exit_date"]).dt.date
    sub2024 = sub2024[(sub2024["exit_d"] >= date(2024, 1, 1)) &
                       (sub2024["exit_d"] <= date(2024, 12, 31))].copy()
    sub2024["pnl_total"] = sub2024["pnl_total"].astype(float)
    per_ticker_2024 = sub2024.groupby("ticker").agg(
        n_closed=("pnl_total", "count"),
        sum_pnl=("pnl_total", "sum"),
        avg_pnl=("pnl_total", "mean"),
        max_pnl=("pnl_total", "max"),
        min_pnl=("pnl_total", "min"),
    ).sort_values("sum_pnl", ascending=False)

    # 2024 opens — count opens per ticker (not just closes)
    opens_2024 = trades.copy()
    opens_2024["entry_d"] = pd.to_datetime(opens_2024["entry_date"]).dt.date
    opens_2024 = opens_2024[(opens_2024["entry_d"] >= date(2024, 1, 1)) &
                             (opens_2024["entry_d"] <= date(2024, 12, 31))]
    opens_count = opens_2024.groupby("ticker").size().to_dict()

    # Compute pnl_pct early so both Section 4 and Section 5 see it
    sub2024["pnl_pct"] = sub2024.apply(
        lambda r: (r["pnl_total"] / (r["entry_debit"] * r["contracts"] * 100) * 100)
                   if r["entry_debit"] > 0 and r["contracts"] > 0 else 0, axis=1
    )

    # === Section 4: concentration test ===
    print("\n[4] Concentration test...", flush=True)
    sub2024_sorted = sub2024.sort_values("pnl_total", ascending=False)
    total_2024 = float(sub2024["pnl_total"].sum())
    top5_pnl = float(sub2024_sorted.head(5)["pnl_total"].sum())
    top10_pnl = float(sub2024_sorted.head(10)["pnl_total"].sum())
    excl_top5 = total_2024 - top5_pnl
    excl_top10 = total_2024 - top10_pnl
    pct_top5 = (top5_pnl / total_2024 * 100) if total_2024 != 0 else 0
    pct_top10 = (top10_pnl / total_2024 * 100) if total_2024 != 0 else 0

    # === Section 5: outlier identification ===
    print("\n[5] Outlier identification (2024 trades)...", flush=True)
    big_pnl = sub2024[sub2024["pnl_total"] > 20_000]
    big_return = sub2024[sub2024["pnl_pct"] > 200]
    near_zero_debit = sub2024[sub2024["entry_debit"] < 0.10]
    # Union, dedupe
    outlier_ids = set(big_pnl.index) | set(big_return.index) | set(near_zero_debit.index)
    outliers = sub2024.loc[sorted(outlier_ids)].copy()

    # ============== MARKDOWN ==============
    print(f"\nWriting {MD_OUT}...", flush=True)
    def fmt_dol(v): return f"${v:+,.0f}"
    def fmt_pct(v): return f"{v:+.2f}%"
    lines = []
    lines.append(f"# Phase 4 Tier 1 — 2024 Attribution Analysis")
    lines.append("")
    lines.append(f"**Source**: `output/sim_4119dc073393/` (Tier 1 canonical, 23-ticker universe).")
    lines.append(f"**Trades**: {len(trades)} total, {(trades['pnl_total'].notna()).sum()} closed.")
    lines.append("")

    # 1. Per-year
    lines.append(f"## 1. Per-year metrics (Tier 1 vs Phase 3 baseline)")
    lines.append("")
    lines.append(f"| Year | T1 CAGR | T1 MaxDD% | T1 Sharpe | T1 Closed | T1 P&L | P3 CAGR | Δ CAGR vs P3 |")
    lines.append(f"|---|---:|---:|---:|---:|---:|---:|---:|")
    for year in sorted(per_year.keys()):
        t1 = per_year[year]
        p3 = PHASE3_PER_YEAR.get(year, {})
        delta = t1["cagr"] - p3.get("cagr", 0) if p3 else 0
        lines.append(f"| {year} | {fmt_pct(t1['cagr'])} | {t1['max_dd']:.2f}% | {t1['sharpe']:.2f} | {t1['n_closed']} | {fmt_dol(t1['sum_pnl'])} | {fmt_pct(p3.get('cagr', 0))} | {delta:+.2f}pp |")
    lines.append("")
    lines.append(f"_T1 CAGR per year computed as (year_end_eq / year_start_eq)^(365/cal_days) − 1 on the combined daily MTM equity series. P3 baseline from `output/PHASE_3_FULL_BACKTEST.md`._")
    lines.append("")

    # 2. 2024 quarterly
    lines.append(f"## 2. 2024 quarterly breakdown")
    lines.append("")
    lines.append(f"| Quarter | Closed | Sum P&L | Win% | Top 3 tickers (P&L, # closed) |")
    lines.append(f"|---|---:|---:|---:|---|")
    for q in ["Q1", "Q2", "Q3", "Q4"]:
        m = quarterly[q]
        win_pct = (100 * m["winners"] / m["n_closed"]) if m["n_closed"] else 0
        top3_str = ", ".join(f"{t} ({fmt_dol(p)}, n={n})" for t, p, n in m["top3"])
        lines.append(f"| 2024-{q} | {m['n_closed']} | {fmt_dol(m['sum_pnl'])} | {win_pct:.0f}% | {top3_str} |")
    lines.append("")
    total_2024_check = sum(quarterly[q]["sum_pnl"] for q in ["Q1", "Q2", "Q3", "Q4"])
    lines.append(f"_Quarterly sum: {fmt_dol(total_2024_check)} (sanity check vs full-year 2024 P&L = {fmt_dol(total_2024)})._")
    lines.append("")

    # 3. 2024 per-ticker
    lines.append(f"## 3. 2024 per-ticker P&L attribution")
    lines.append("")
    lines.append(f"| Ticker | Opens | Closed | Sum P&L | Avg P&L | Max single | Min single | % of 2024 |")
    lines.append(f"|---|---:|---:|---:|---:|---:|---:|---:|")
    for t, row in per_ticker_2024.iterrows():
        opens_n = opens_count.get(t, 0)
        pct = (row["sum_pnl"] / total_2024 * 100) if total_2024 != 0 else 0
        lines.append(f"| {t} | {opens_n} | {int(row['n_closed'])} | {fmt_dol(row['sum_pnl'])} | {fmt_dol(row['avg_pnl'])} | {fmt_dol(row['max_pnl'])} | {fmt_dol(row['min_pnl'])} | {pct:+.1f}% |")
    lines.append(f"| **TOTAL** | — | **{len(sub2024)}** | **{fmt_dol(total_2024)}** | — | — | — | **100.0%** |")
    lines.append("")

    # 4. Concentration test
    lines.append(f"## 4. Concentration test for 2024")
    lines.append("")
    lines.append(f"| Scenario | P&L | Δ vs baseline | % of baseline |")
    lines.append(f"|---|---:|---:|---:|")
    lines.append(f"| Total 2024 (baseline) | {fmt_dol(total_2024)} | — | 100.0% |")
    lines.append(f"| Excluding top 5 trades | {fmt_dol(excl_top5)} | {fmt_dol(-top5_pnl)} | {(excl_top5/total_2024*100) if total_2024 else 0:.1f}% |")
    lines.append(f"| Excluding top 10 trades | {fmt_dol(excl_top10)} | {fmt_dol(-top10_pnl)} | {(excl_top10/total_2024*100) if total_2024 else 0:.1f}% |")
    lines.append("")
    lines.append(f"**Top 5 trades = {pct_top5:.1f}% of 2024 P&L. Top 10 trades = {pct_top10:.1f}%.**")
    lines.append("")

    # Top 10 trades themselves (transparency)
    lines.append(f"### Top 10 individual 2024 trades (the concentration drivers)")
    lines.append("")
    lines.append(f"| # | Ticker | Cell | Entry | Exit | Ctr | Entry$ | P&L | P&L % |")
    lines.append(f"|---|---|---|---|---|---:|---:|---:|---:|")
    for i, (idx, r) in enumerate(sub2024_sorted.head(10).iterrows(), 1):
        lines.append(f"| {i} | {r['ticker']} | {r['cell']} | {pd.to_datetime(r['entry_date']).date()} | {pd.to_datetime(r['exit_date']).date()} | {int(r['contracts'])} | ${r['entry_debit']:.2f} | {fmt_dol(r['pnl_total'])} | {r['pnl_pct']:+.1f}% |")
    lines.append("")

    # 5. Outliers
    lines.append(f"## 5. Single-trade outliers in 2024")
    lines.append("")
    lines.append(f"Criteria: (a) P&L > $20K, (b) return > 200%, (c) entry debit < $0.10. Union; dedupe.")
    lines.append("")
    if outliers.empty:
        lines.append(f"_No 2024 trades met any outlier criterion._")
    else:
        lines.append(f"**{len(outliers)} outlier trade(s) found:**")
        lines.append("")
        lines.append(f"| Ticker | Cell | Entry | Exit | Ctr | Entry$ | P&L | P&L % | FF@entry | Trigger |")
        lines.append(f"|---|---|---|---|---:|---:|---:|---:|---:|---|")
        for idx, r in outliers.iterrows():
            triggers = []
            if r["pnl_total"] > 20_000: triggers.append("P&L>$20K")
            if r["pnl_pct"] > 200: triggers.append("return>200%")
            if r["entry_debit"] < 0.10: triggers.append("debit<$0.10")
            ff = r.get("ff_at_entry", float("nan"))
            ff_str = f"{ff:.4f}" if pd.notna(ff) else "—"
            lines.append(f"| {r['ticker']} | {r['cell']} | {pd.to_datetime(r['entry_date']).date()} | {pd.to_datetime(r['exit_date']).date()} | {int(r['contracts'])} | ${r['entry_debit']:.2f} | {fmt_dol(r['pnl_total'])} | {r['pnl_pct']:+.1f}% | {ff_str} | {'+'.join(triggers)} |")
        lines.append("")
        # Aggregate outlier impact
        outlier_pnl = float(outliers["pnl_total"].sum())
        lines.append(f"**Combined outlier-trade P&L: {fmt_dol(outlier_pnl)} ({outlier_pnl/total_2024*100:.1f}% of 2024 P&L)**")
    lines.append("")

    # Decision rule
    lines.append(f"## Decision rule applied")
    lines.append("")
    excl_top5_pct_remaining = (excl_top5 / total_2024 * 100) if total_2024 else 0
    if excl_top5_pct_remaining >= 70:
        verdict = "**(A) BROAD-BASED** — excluding top 5 trades leaves ≥70% of 2024 P&L. Forward CAGR expectation stays high; allocation analysis stands as-is."
    elif pct_top5 >= 50:
        verdict = "**(B) OUTLIER-DRIVEN** — top 5 trades account for ≥50% of 2024 P&L. Forward CAGR expectation should be materially discounted; allocation sizing should be reduced from max-Sharpe 30%."
    else:
        verdict = "**(MIXED)** — between broad-based and outlier-driven. Top 5 trades = {pct_top5:.1f}% of P&L. Excluding top 5 leaves {excl_top5_pct_remaining:.1f}%. Allocation analysis warrants partial discount."
    lines.append(verdict)
    lines.append("")
    if not near_zero_debit.empty:
        nzd_sum = float(near_zero_debit["pnl_total"].sum())
        lines.append(f"**Near-zero-debit pattern check**: {len(near_zero_debit)} trade(s) with entry_debit < $0.10 in 2024, total P&L {fmt_dol(nzd_sum)} ({nzd_sum/total_2024*100:+.1f}% of year). " +
                      ("This is the same pattern that drove the KRE Apr 2026 catastrophe — recurrence in 2024 is meaningful." if nzd_sum != 0 else ""))

    MD_OUT.parent.mkdir(parents=True, exist_ok=True)
    MD_OUT.write_text("\n".join(lines))
    print(f"Wrote {MD_OUT}", flush=True)
    print(f"\n=== HEADLINE NUMBERS ===", flush=True)
    print(f"  T1 2024 CAGR: {fmt_pct(per_year[2024]['cagr'])} (vs P3 baseline {fmt_pct(PHASE3_PER_YEAR[2024]['cagr'])})", flush=True)
    print(f"  T1 2024 P&L: {fmt_dol(total_2024)}, n={len(sub2024)} closed", flush=True)
    print(f"  Top 5 = {pct_top5:.1f}% of 2024 P&L | Top 10 = {pct_top10:.1f}%", flush=True)
    print(f"  Excluding top 5 leaves {excl_top5_pct_remaining:.1f}% of baseline", flush=True)
    print(f"  Outlier trades: {len(outliers)}", flush=True)


if __name__ == "__main__":
    main()
