"""Phase 5 ORATS regime stress tests + final extended-history report.

Slices the 2008-2026 daily MTM equity series by regime window and computes
per-regime CAGR / MaxDD / Sharpe / # trades / trades-per-year for both:
  - ORATS Tier 1 unconstrained (output/orats_extended/sim_d075198d5e15/)
  - ORATS Stable with caps  (output/orats_extended_stable/sim_0b99f17e7a71/)

Includes:
  - Trades/year column per regime (Steven's locked decision #2)
  - Low-confidence flag if trades/year << 2022-2026 baseline
  - Universe disclosure: how many of 23 tickers were usable per regime
    (loaded from output/phase5_ticker_availability.csv)
  - Per-ticker P&L attribution across full extended history

Outputs:
  output/PHASE_5_REGIME_STRESS_TESTS.md
  output/PHASE_5_ORATS_BACKTEST_REPORT.md
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

TIER1_DIR = Path("output/orats_extended/sim_d075198d5e15")
STABLE_DIR = Path("output/orats_extended_stable/sim_0b99f17e7a71")
AVAILABILITY_CSV = Path("output/phase5_ticker_availability.csv")

REGIME_REPORT = Path("output/PHASE_5_REGIME_STRESS_TESTS.md")
BACKTEST_REPORT = Path("output/PHASE_5_ORATS_BACKTEST_REPORT.md")

REGIMES = [
    ("2008 H2 (GFC: Lehman → YE)",   date(2008, 7, 1),  date(2008, 12, 31)),
    ("2009 (recovery)",              date(2009, 1, 1),  date(2009, 12, 31)),
    ("2010-2014 (low-vol grind)",    date(2010, 1, 1),  date(2014, 12, 31)),
    ("2015 H2 (yuan deval)",         date(2015, 7, 1),  date(2015, 12, 31)),
    ("2016 H1 (Brexit)",             date(2016, 1, 1),  date(2016, 6, 30)),
    ("2018 Feb (Volmageddon)",       date(2018, 2, 1),  date(2018, 2, 28)),
    ("2020 Feb-Apr (COVID)",         date(2020, 2, 1),  date(2020, 4, 30)),
    ("2022-2026 (current era)",      date(2022, 1, 3),  date(2026, 4, 30)),
    ("FULL 2008-2026",               date(2008, 1, 2),  date(2026, 4, 30)),
]


# ============================================================================
# Helpers
# ============================================================================

def metrics_from_equity(eq: pd.Series, dates: pd.DatetimeIndex) -> dict:
    eq = pd.Series(eq.values, index=dates).sort_index()
    if len(eq) < 2: return {}
    start = float(eq.iloc[0]); end = float(eq.iloc[-1])
    cal_days = (eq.index[-1] - eq.index[0]).days
    cagr = ((end / start) ** (365 / max(cal_days, 1)) - 1) * 100 if start > 0 else 0
    rets = eq.pct_change().dropna()
    sharpe = (rets.mean() * 252) / (rets.std() * (252 ** 0.5)) if rets.std() > 0 else 0
    peak = eq.iloc[0]; max_dd = 0.0
    for v in eq:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd: max_dd = dd
    ann_vol = rets.std() * (252 ** 0.5) * 100 if len(rets) > 1 else 0
    return {"cagr": cagr, "max_dd_pct": max_dd, "sharpe": sharpe,
            "ann_vol": ann_vol, "n_days": len(eq),
            "start_val": start, "end_val": end}


def slice_regime(daily: pd.DataFrame, start_d: date, end_d: date) -> dict:
    sub = daily[(daily["date"] >= pd.Timestamp(start_d)) & (daily["date"] <= pd.Timestamp(end_d))]
    if sub.empty:
        return {"cagr": 0, "max_dd_pct": 0, "sharpe": 0, "ann_vol": 0,
                "n_days": 0, "start_val": np.nan, "end_val": np.nan}
    return metrics_from_equity(sub["combined"], pd.DatetimeIndex(sub["date"]))


def trades_in_window(trades: pd.DataFrame, start_d: date, end_d: date) -> int:
    return len(trades[(trades["entry_date"] >= pd.Timestamp(start_d))
                      & (trades["entry_date"] <= pd.Timestamp(end_d))])


def ticker_count_for_regime(avail: pd.DataFrame, label: str) -> int | None:
    """Return 'X/23' count from availability CSV for a regime label."""
    # availability CSV columns include the regime labels
    if label in avail.columns:
        ticker_col = avail.columns[0]
        # Each row is one ticker; presence is "✓"
        return int((avail[label] == "✓").sum())
    return None


# ============================================================================
# Main
# ============================================================================

def main():
    print("### Phase 5 ORATS regime stress + final report", flush=True)

    # Load both sim outputs
    t1_daily = pd.read_csv(TIER1_DIR / "daily_mtm_equity.csv", parse_dates=["date"])
    t1_trades = pd.read_csv(TIER1_DIR / "trade_log.csv", parse_dates=["entry_date", "exit_date"])
    st_daily = pd.read_csv(STABLE_DIR / "daily_mtm_equity.csv", parse_dates=["date"])
    st_trades = pd.read_csv(STABLE_DIR / "trade_log.csv", parse_dates=["entry_date", "exit_date"])

    print(f"  Tier 1: {len(t1_trades)} trades, {len(t1_daily)} daily rows", flush=True)
    print(f"  Stable: {len(st_trades)} trades, {len(st_daily)} daily rows", flush=True)

    # Load ticker availability
    avail = pd.read_csv(AVAILABILITY_CSV)

    # ---- Per-regime metrics ----
    print(f"\n  Per-regime breakdown:", flush=True)
    rows = []
    for label, start_d, end_d in REGIMES:
        m_t1 = slice_regime(t1_daily, start_d, end_d)
        m_st = slice_regime(st_daily, start_d, end_d)
        n_t1 = trades_in_window(t1_trades, start_d, end_d)
        n_st = trades_in_window(st_trades, start_d, end_d)
        years = max((end_d - start_d).days / 365.25, 0.01)
        tpy_t1 = n_t1 / years
        tpy_st = n_st / years
        n_tickers = ticker_count_for_regime(avail, label)
        rows.append({
            "regime": label,
            "start": start_d, "end": end_d, "years": years,
            "t1_cagr": m_t1["cagr"], "t1_dd": m_t1["max_dd_pct"], "t1_sh": m_t1["sharpe"], "t1_n": n_t1, "t1_tpy": tpy_t1,
            "st_cagr": m_st["cagr"], "st_dd": m_st["max_dd_pct"], "st_sh": m_st["sharpe"], "st_n": n_st, "st_tpy": tpy_st,
            "n_tickers": n_tickers,
        })
        print(f"    {label:38s}: T1 {m_t1['cagr']:+6.2f}% {n_t1:>4d}tr | ST {m_st['cagr']:+6.2f}% {n_st:>4d}tr | tickers {n_tickers}/23", flush=True)
    df = pd.DataFrame(rows)

    # 2022-2026 baseline trades/year (full era)
    baseline_tpy_t1 = df[df["regime"] == "2022-2026 (current era)"]["t1_tpy"].iloc[0]
    baseline_tpy_st = df[df["regime"] == "2022-2026 (current era)"]["st_tpy"].iloc[0]
    print(f"\n  Baseline trades/year (2022-2026): T1={baseline_tpy_t1:.1f}  ST={baseline_tpy_st:.1f}", flush=True)

    # ---- Per-year breakdown across full window ----
    print(f"\n  Per-year breakdown:", flush=True)
    yearly = []
    t1_daily["year"] = t1_daily["date"].dt.year
    st_daily["year"] = st_daily["date"].dt.year
    t1_trades["year"] = t1_trades["entry_date"].dt.year
    st_trades["year"] = st_trades["entry_date"].dt.year
    for year in sorted(set(t1_daily["year"].unique()) | set(st_daily["year"].unique())):
        t1_sub = t1_daily[t1_daily["year"] == year]
        st_sub = st_daily[st_daily["year"] == year]
        if len(t1_sub) < 2: continue
        m_t1 = metrics_from_equity(t1_sub["combined"], pd.DatetimeIndex(t1_sub["date"]))
        m_st = metrics_from_equity(st_sub["combined"], pd.DatetimeIndex(st_sub["date"]))
        n_t1_year = int((t1_trades["year"] == year).sum())
        n_st_year = int((st_trades["year"] == year).sum())
        yearly.append({
            "year": int(year),
            "t1_cagr": m_t1["cagr"], "t1_dd": m_t1["max_dd_pct"], "t1_sh": m_t1["sharpe"], "t1_n": n_t1_year,
            "st_cagr": m_st["cagr"], "st_dd": m_st["max_dd_pct"], "st_sh": m_st["sharpe"], "st_n": n_st_year,
        })
    yearly_df = pd.DataFrame(yearly)

    # ---- Per-ticker P&L attribution (Tier 1 across full history) ----
    t1_attr = t1_trades.groupby("ticker").agg(
        opens=("ticker", "size"),
        closed=("pnl_total", lambda s: s.notna().sum()),
        sum_pnl=("pnl_total", "sum"),
        max_single=("pnl_total", "max"),
        min_single=("pnl_total", "min"),
    ).sort_values("sum_pnl", ascending=False)
    total_pnl = t1_attr["sum_pnl"].sum()
    t1_attr["pct_of_total"] = 100 * t1_attr["sum_pnl"] / total_pnl if total_pnl != 0 else 0

    # ---- Markdown reports ----
    write_regime_report(df, baseline_tpy_t1, baseline_tpy_st, yearly_df)
    write_backtest_report(df, yearly_df, t1_attr, t1_trades, st_trades)
    print(f"\nWrote {REGIME_REPORT}", flush=True)
    print(f"Wrote {BACKTEST_REPORT}", flush=True)


def write_regime_report(df, baseline_tpy_t1, baseline_tpy_st, yearly_df):
    md = []
    md.append("# Phase 5 — ORATS Regime Stress Tests (2008-2026)")
    md.append("")
    md.append(f"_Generated {datetime.now().isoformat()}_")
    md.append("")
    md.append("## Setup")
    md.append("")
    md.append("- **Data source**: ORATS SMV Strikes daily ZIPs, validated as the clean source after Polygon Tier 1 was found to be data-noise-driven (see `PHASE_5_ORATS_ADAPTER_VALIDATION.md` and `Why the original Polygon backtest overstated returns` in `CLAUDE_CODE_HANDOFF.md`).")
    md.append("- **Methodology**: 3 cells (30-60, 30-90, 60-90 ATM call calendar) + extVol Path A (ex-earnings IV, no earnings filter) + era-adaptive dte_buffer (2007-2010=15, 2011-2015=12, 2016-2020=8, 2021-2026=5).")
    md.append("- **Universe**: 23 tickers (Tier 1). Aliasing FB→META, GOOG→GOOGL applied. Ticker availability per regime disclosed below.")
    md.append("- **Configs**: Tier 1 unconstrained (quarter-Kelly, no caps) AND Phase 5 stable (half-Kelly + debit-floor $0.15 + 12% per-ticker NAV cap + asset-class caps).")
    md.append("")
    md.append("## Per-regime breakdown")
    md.append("")
    md.append(f"Baseline trades/year (2022-2026): T1 {baseline_tpy_t1:.0f}, Stable {baseline_tpy_st:.0f}. Regimes with materially fewer trades/year flagged ⚠️ low-confidence.")
    md.append("")
    md.append("| Regime | Window | Years | Tickers | T1 CAGR | T1 DD | T1 Sh | T1 trades | T1 tr/yr | Conf | Stable CAGR | Stable DD | Stable Sh | Stable trades |")
    md.append("|---|---|---:|---:|---:|---:|---:|---:|---:|:-:|---:|---:|---:|---:|")
    for _, r in df.iterrows():
        conf_flag = ""
        if r["regime"] != "2022-2026 (current era)" and r["regime"] != "FULL 2008-2026":
            if r["t1_tpy"] < baseline_tpy_t1 * 0.5:
                conf_flag = "⚠️"
        nticker = f"{int(r['n_tickers'])}/23" if pd.notna(r["n_tickers"]) and r["n_tickers"] is not None else "—"
        md.append(f"| {r['regime']} | {r['start']} → {r['end']} | {r['years']:.1f} | {nticker} | "
                  f"{r['t1_cagr']:+.2f}% | {r['t1_dd']:.1f}% | {r['t1_sh']:+.2f} | {r['t1_n']} | {r['t1_tpy']:.0f} | {conf_flag} | "
                  f"{r['st_cagr']:+.2f}% | {r['st_dd']:.1f}% | {r['st_sh']:+.2f} | {r['st_n']} |")
    md.append("")
    md.append("**⚠️ flag**: trades/year < 50% of 2022-2026 baseline. Lower statistical confidence — sparse regimes have fewer sample events, so per-regime CAGR is noisier.")
    md.append("")
    md.append("## Per-year breakdown")
    md.append("")
    md.append("| Year | T1 CAGR | T1 DD | T1 Sh | T1 trades | Stable CAGR | Stable DD | Stable Sh | Stable trades |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for _, r in yearly_df.iterrows():
        md.append(f"| {r['year']} | {r['t1_cagr']:+.2f}% | {r['t1_dd']:.1f}% | {r['t1_sh']:+.2f} | {r['t1_n']} | "
                  f"{r['st_cagr']:+.2f}% | {r['st_dd']:.1f}% | {r['st_sh']:+.2f} | {r['st_n']} |")
    md.append("")
    md.append("## Reading the table")
    md.append("")
    md.append("- **2022-2026 era is anomalously good**, even on clean ORATS data. 2008-2021 produces near-zero CAGR with similar DDs.")
    md.append("- **Caps don't help; they hurt slightly**. Stable's CAGR is consistently below Tier 1's because the noise that caps suppress isn't actually noise on ORATS data — it's just normal trade variance. Caps shrink upside without removing meaningful downside.")
    md.append("- **Trade frequency varies dramatically** — 2008 H2 fired only ~10 trades on a 17-of-23 ticker universe; 2022-2026 fires ~300+/year on full 23. Sparse regimes have low statistical confidence; their CAGRs are noisy.")
    md.append("- **Universe disclosure matters**: the 2008 GFC test runs on 17 of 23 tickers (no ARKK/COIN/GLD/KWEB/SLV; META/GOOGL via alias). 2009 has 19/23. Apples-to-apples comparison only emerges from 2022 onward.")
    md.append("")
    REGIME_REPORT.parent.mkdir(parents=True, exist_ok=True)
    REGIME_REPORT.write_text("\n".join(md))


def write_backtest_report(df, yearly_df, t1_attr, t1_trades, st_trades):
    md = []
    md.append("# Phase 5 — ORATS Extended-History Backtest Report (2008-2026)")
    md.append("")
    md.append(f"_Generated {datetime.now().isoformat()}_")
    md.append("")
    md.append("## TL;DR")
    md.append("")
    full = df[df["regime"] == "FULL 2008-2026"].iloc[0]
    cur = df[df["regime"] == "2022-2026 (current era)"].iloc[0]
    md.append(f"Forward Factor strategy on clean ORATS data, 2008-2026, 3-cell + extVol Path A methodology, 23-ticker Tier 1 universe (with FB→META + GOOG→GOOGL aliasing):")
    md.append("")
    md.append(f"| Window | Tier 1 CAGR | Stable CAGR | Tier 1 DD | Stable DD | T1 Trades | ST Trades |")
    md.append(f"|---|---:|---:|---:|---:|---:|---:|")
    md.append(f"| **FULL 2008-2026** ({full['years']:.1f} yr) | **{full['t1_cagr']:+.2f}%** | **{full['st_cagr']:+.2f}%** | {full['t1_dd']:.1f}% | {full['st_dd']:.1f}% | {full['t1_n']} | {full['st_n']} |")
    md.append(f"| 2022-2026 era ({cur['years']:.1f} yr) | {cur['t1_cagr']:+.2f}% | {cur['st_cagr']:+.2f}% | {cur['t1_dd']:.1f}% | {cur['st_dd']:.1f}% | {cur['t1_n']} | {cur['st_n']} |")
    md.append("")
    md.append("**Conclusion**: Across 18+ years of clean data and methodology improvements (3 cells + extVol Path A), the strategy delivers near-zero CAGR. The 2022-2026 era was the best 4-year window in the entire 18-year history; extending the test window collapses the apparent edge.")
    md.append("")
    md.append("## Standalone metrics — full window")
    md.append("")
    md.append("| Metric | Tier 1 unconstrained | Phase 5 stable |")
    md.append("|---|---:|---:|")
    md.append(f"| MTM CAGR | {full['t1_cagr']:+.2f}% | {full['st_cagr']:+.2f}% |")
    md.append(f"| MaxDD% | {full['t1_dd']:.2f}% | {full['st_dd']:.2f}% |")
    md.append(f"| Sharpe | {full['t1_sh']:+.2f} | {full['st_sh']:+.2f} |")
    md.append(f"| Closed trades | {full['t1_n']} | {full['st_n']} |")
    md.append("")
    md.append("## Per-year P&L attribution (Tier 1)")
    md.append("")
    md.append("Top 15 tickers by P&L over the full 2008-2026 window:")
    md.append("")
    md.append("| Ticker | Opens | Closed | Sum P&L | Max single | Min single | % of total |")
    md.append("|---|---:|---:|---:|---:|---:|---:|")
    top = t1_attr.head(15)
    for ticker, r in top.iterrows():
        md.append(f"| {ticker} | {r['opens']} | {r['closed']} | "
                  f"${r['sum_pnl']:+,.0f} | ${r['max_single']:+,.0f} | ${r['min_single']:+,.0f} | "
                  f"{r['pct_of_total']:+.1f}% |")
    md.append("")
    md.append("## Why the result is so modest")
    md.append("")
    md.append("Three reasons that all stack:")
    md.append("")
    md.append("1. **Polygon's noise alpha doesn't exist on ORATS**: the apparent +32.78% CAGR on Polygon Tier 1 2022-2026 was driven by stale-close BS-IV inversion noise that ORATS' bid/ask quote pricing never sees. See PHASE_5_ORATS_ADAPTER_VALIDATION.md for the IWM Jul 18 2024 case study.")
    md.append("2. **2022-2026 was an anomalously favorable window even on clean data**: ORATS Tier 1 produced +3.09% CAGR over 2022-2026 but only +1.83% over 2008-2026. The 4-year window included sustained vol-term-structure backwardation; the longer history dilutes that.")
    md.append("3. **Methodology improvements (3-cell + extVol) didn't compensate**: adding the 30-60 cell boosts signal count by ~62% and extVol unblocks single-name trades, but the additional signals don't carry enough edge to materially lift CAGR. They just add similar-quality trades.")
    md.append("")
    md.append("## Implications for deployment")
    md.append("")
    md.append("- **Standalone strategy is not deployable as a primary alpha source.** ~+1-2% CAGR over 18+ years isn't worth the operational complexity (multi-leg orders, daily exit management, earnings tracking).")
    md.append("- **Diversification value is unchanged but at modest scale.** The −0.107 correlation with TQQQ-VT is real and structurally robust; combining FF with TQQQ-VT still improves portfolio Sharpe. But at +1-2% standalone CAGR, the size of the diversification benefit is small — likely a 5-15pp DD reduction in mixed portfolios with minimal CAGR uplift.")
    md.append("- **Phase A deployment recommendation (5% live STABLE + 10% paper STABLE + Tier 1 journal)** is now operationally questionable. The stable-version's 2022-2026 +6.48% standalone falls to +1.35% over 2008-2026 — even paper-trading isn't compelling at that level. Worth Steven's re-evaluation: is the diversification value worth the operational overhead, or is this strategy effectively shelved?")
    md.append("")
    md.append("## Files")
    md.append("")
    md.append(f"- ORATS Tier 1 sim: `{TIER1_DIR}/`")
    md.append(f"- ORATS Stable sim: `{STABLE_DIR}/`")
    md.append(f"- Discovery parquet: `output/phase5_orats_2008_2026_extVol.parquet`")
    md.append(f"- Regime stress detail: `{REGIME_REPORT.name}`")
    md.append("")
    BACKTEST_REPORT.parent.mkdir(parents=True, exist_ok=True)
    BACKTEST_REPORT.write_text("\n".join(md))


if __name__ == "__main__":
    main()
