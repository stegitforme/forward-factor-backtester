"""Phase 5 ORATS final allocation analysis: 2022-2026 (TQQQ-VT period only)
on the clean ORATS extended-history backtest (Tier 1 d075198d5e15 / stable
0b99f17e7a71). Shows what the diversification benefit looks like when we
use the realistic CAGR numbers instead of the noise-driven Polygon ones.

Output: output/PHASE_5_ORATS_ALLOCATION.md
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

T1_HASH = "d075198d5e15"
ST_HASH = "0b99f17e7a71"

T1_EQUITY = Path(f"output/orats_extended/sim_{T1_HASH}/daily_mtm_equity.csv")
ST_EQUITY = Path(f"output/orats_extended_stable/sim_{ST_HASH}/daily_mtm_equity.csv")
TQ_EQUITY = Path("output/tqqq_vt_daily_equity.csv")

REPORT = Path("output/PHASE_5_ORATS_ALLOCATION.md")

MIXES = [(1.00, 0.00), (0.90, 0.10), (0.85, 0.15), (0.80, 0.20),
         (0.75, 0.25), (0.70, 0.30), (0.60, 0.40), (0.50, 0.50), (0.00, 1.00)]


def metrics(eq: np.ndarray, dates: pd.DatetimeIndex, base: float = None) -> dict:
    if len(eq) < 2: return {}
    base = base if base is not None else float(eq[0])
    end = float(eq[-1])
    cal_days = (dates[-1] - dates[0]).days
    cagr = ((end / base) ** (365 / max(cal_days, 1)) - 1) * 100
    rets = pd.Series(eq).pct_change().dropna()
    sharpe = (rets.mean() * 252) / (rets.std() * (252 ** 0.5)) if rets.std() > 0 else 0
    peak = eq[0]; max_dd = 0.0
    for v in eq:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd: max_dd = dd
    ann_vol = rets.std() * (252 ** 0.5) * 100
    calmar = cagr / max_dd if max_dd > 0 else float("inf")
    return {"cagr": cagr, "max_dd_pct": max_dd, "ann_vol": ann_vol,
            "sharpe": sharpe, "calmar": calmar, "end_val": end}


def main():
    print("### Phase 5 ORATS Allocation Analysis", flush=True)

    # Load
    t1 = pd.read_csv(T1_EQUITY, parse_dates=["date"])[["date", "combined"]].rename(columns={"combined": "ff_t1"})
    st = pd.read_csv(ST_EQUITY, parse_dates=["date"])[["date", "combined"]].rename(columns={"combined": "ff_st"})
    tq = pd.read_csv(TQ_EQUITY, parse_dates=["date"])
    val_col = next((c for c in tq.columns if c.lower() in ("portfolio_value", "value", "equity", "nav", "balance")), None)
    if val_col is None and len(tq.columns) == 2:
        val_col = [c for c in tq.columns if c.lower() != "date"][0]
    tq = tq[["date", val_col]].rename(columns={val_col: "tqvt"})

    # Align on common dates (TQQQ-VT only goes back to 2022 → that defines the window)
    t1.set_index("date", inplace=True)
    st.set_index("date", inplace=True)
    tq.set_index("date", inplace=True)
    merged = t1.join(st, how="inner").join(tq, how="inner")
    print(f"  Common days: {len(merged)} ({merged.index[0].date()} → {merged.index[-1].date()})", flush=True)

    # Daily returns
    t1_rets = merged["ff_t1"].pct_change().dropna()
    st_rets = merged["ff_st"].pct_change().dropna()
    tq_rets = merged["tqvt"].pct_change().dropna()
    common_idx = t1_rets.index.intersection(tq_rets.index)
    t1_rets = t1_rets.loc[common_idx]
    st_rets = st_rets.loc[common_idx]
    tq_rets = tq_rets.loc[common_idx]

    # Correlations
    corr_t1 = float(t1_rets.corr(tq_rets))
    corr_st = float(st_rets.corr(tq_rets))
    print(f"  Correlations: T1 vs TQQQ-VT = {corr_t1:+.3f}  ST vs TQQQ-VT = {corr_st:+.3f}", flush=True)

    # Standalone metrics on overlapping window
    aligned = pd.DatetimeIndex(merged.index)
    m_t1 = metrics(merged["ff_t1"].values, aligned)
    m_st = metrics(merged["ff_st"].values, aligned)
    m_tq = metrics(merged["tqvt"].values, aligned)
    print(f"\n  Standalone (overlap):", flush=True)
    print(f"    FF Tier 1 ORATS: CAGR {m_t1['cagr']:+.2f}% DD {m_t1['max_dd_pct']:.2f}% Sh {m_t1['sharpe']:.2f}", flush=True)
    print(f"    FF Stable ORATS: CAGR {m_st['cagr']:+.2f}% DD {m_st['max_dd_pct']:.2f}% Sh {m_st['sharpe']:.2f}", flush=True)
    print(f"    TQQQ-VT:         CAGR {m_tq['cagr']:+.2f}% DD {m_tq['max_dd_pct']:.2f}% Sh {m_tq['sharpe']:.2f}", flush=True)

    # Allocation sweep: Tier 1 vs TQQQ-VT and Stable vs TQQQ-VT
    def sweep(ff_rets, label):
        rows = []
        base = 10_000.0
        for w_tq, w_ff in MIXES:
            port_rets = w_tq * tq_rets + w_ff * ff_rets
            eq = (1.0 + port_rets).cumprod() * base
            eq = pd.concat([pd.Series([base], index=[port_rets.index[0] - pd.Timedelta(days=1)]), eq])
            m = metrics(eq.values, pd.DatetimeIndex(eq.index), base=base)
            rows.append({"mix": f"{int(w_tq*100):3d}/{int(w_ff*100):3d}", "w_tq": w_tq, "w_ff": w_ff, **m})
        return pd.DataFrame(rows)

    sw_t1 = sweep(t1_rets, "Tier 1")
    sw_st = sweep(st_rets, "Stable")

    # Identify max-Sharpe and max-Calmar
    def best(df, key):
        return df.iloc[df[key].idxmax()]
    msh_t1 = best(sw_t1, "sharpe")
    mcal_t1 = best(sw_t1, "calmar")
    msh_st = best(sw_st, "sharpe")
    mcal_st = best(sw_st, "calmar")

    print(f"\n  Allocation sweep (Tier 1):", flush=True)
    for _, r in sw_t1.iterrows():
        print(f"    {r['mix']}: CAGR {r['cagr']:+.2f}% DD {r['max_dd_pct']:.2f}% Sh {r['sharpe']:.2f}", flush=True)
    print(f"  Max-Sharpe: {msh_t1['mix']} (Sh {msh_t1['sharpe']:.2f})", flush=True)
    print(f"  Max-Calmar: {mcal_t1['mix']} (Cal {mcal_t1['calmar']:.2f})", flush=True)

    # ---- Markdown ----
    md = []
    md.append("# Phase 5 — ORATS Allocation Analysis vs TQQQ-VT")
    md.append("")
    md.append(f"_Generated {datetime.now().isoformat()}_")
    md.append("")
    md.append("## Setup")
    md.append("")
    md.append(f"- Window: {merged.index[0].date()} → {merged.index[-1].date()} ({len(merged)} days)")
    md.append(f"- FF data source: ORATS extended-history backtest (3-cell + extVol Path A + era buffer)")
    md.append(f"- Sliced to 2022-2026 because TQQQ-VT data only spans that period")
    md.append(f"- Tier 1 hash: `{T1_HASH}` — full 2008-2026 CAGR was +1.83%")
    md.append(f"- Stable hash: `{ST_HASH}` — full 2008-2026 CAGR was +1.35%")
    md.append("")

    md.append("## Correlations")
    md.append("")
    md.append("| Strategy | Correlation vs TQQQ-VT |")
    md.append("|---|---:|")
    md.append(f"| FF Tier 1 (ORATS) | **{corr_t1:+.3f}** |")
    md.append(f"| FF Stable (ORATS) | **{corr_st:+.3f}** |")
    md.append("")
    md.append(f"Negative correlations confirm structural diversification, but at modest standalone CAGR the *magnitude* of diversification benefit is small.")
    md.append("")

    md.append("## Standalone strategy metrics (overlapping window)")
    md.append("")
    md.append("| Metric | FF Tier 1 ORATS | FF Stable ORATS | TQQQ-VT |")
    md.append("|---|---:|---:|---:|")
    md.append(f"| CAGR | {m_t1['cagr']:+.2f}% | {m_st['cagr']:+.2f}% | {m_tq['cagr']:+.2f}% |")
    md.append(f"| MaxDD% | {m_t1['max_dd_pct']:.2f}% | {m_st['max_dd_pct']:.2f}% | {m_tq['max_dd_pct']:.2f}% |")
    md.append(f"| Ann Vol | {m_t1['ann_vol']:.2f}% | {m_st['ann_vol']:.2f}% | {m_tq['ann_vol']:.2f}% |")
    md.append(f"| Sharpe | {m_t1['sharpe']:.2f} | {m_st['sharpe']:.2f} | {m_tq['sharpe']:.2f} |")
    md.append(f"| Calmar | {m_t1['calmar']:.2f} | {m_st['calmar']:.2f} | {m_tq['calmar']:.2f} |")
    md.append("")

    md.append("## Allocation sweep — Tier 1 (no caps) vs TQQQ-VT")
    md.append("")
    md.append("| Mix (TQ/FF) | CAGR | MaxDD% | Sharpe | Calmar | End $ |")
    md.append("|---|---:|---:|---:|---:|---:|")
    for _, r in sw_t1.iterrows():
        marker = ""
        if r["mix"] == msh_t1["mix"]: marker += " ← max Sharpe"
        if r["mix"] == mcal_t1["mix"] and r["mix"] != msh_t1["mix"]: marker += " ← max Calmar"
        md.append(f"| {r['mix']}{marker} | {r['cagr']:+.2f}% | {r['max_dd_pct']:.2f}% | {r['sharpe']:.2f} | {r['calmar']:.2f} | ${r['end_val']:,.0f} |")
    md.append("")

    md.append("## Allocation sweep — Stable (caps + half-Kelly) vs TQQQ-VT")
    md.append("")
    md.append("| Mix (TQ/FF) | CAGR | MaxDD% | Sharpe | Calmar | End $ |")
    md.append("|---|---:|---:|---:|---:|---:|")
    for _, r in sw_st.iterrows():
        marker = ""
        if r["mix"] == msh_st["mix"]: marker += " ← max Sharpe"
        if r["mix"] == mcal_st["mix"] and r["mix"] != msh_st["mix"]: marker += " ← max Calmar"
        md.append(f"| {r['mix']}{marker} | {r['cagr']:+.2f}% | {r['max_dd_pct']:.2f}% | {r['sharpe']:.2f} | {r['calmar']:.2f} | ${r['end_val']:,.0f} |")
    md.append("")

    md.append("## Δ vs pure TQQQ-VT for each max-Sharpe mix")
    md.append("")
    pure_tq = sw_t1.iloc[0]
    md.append(f"| Metric | Pure TQQQ-VT | T1 Max-Sh ({msh_t1['mix']}) | Δ T1 | ST Max-Sh ({msh_st['mix']}) | Δ ST |")
    md.append("|---|---:|---:|---:|---:|---:|")
    md.append(f"| CAGR | {pure_tq['cagr']:+.2f}% | {msh_t1['cagr']:+.2f}% | {msh_t1['cagr']-pure_tq['cagr']:+.2f}pp | {msh_st['cagr']:+.2f}% | {msh_st['cagr']-pure_tq['cagr']:+.2f}pp |")
    md.append(f"| MaxDD% | {pure_tq['max_dd_pct']:.2f}% | {msh_t1['max_dd_pct']:.2f}% | {msh_t1['max_dd_pct']-pure_tq['max_dd_pct']:+.2f}pp | {msh_st['max_dd_pct']:.2f}% | {msh_st['max_dd_pct']-pure_tq['max_dd_pct']:+.2f}pp |")
    md.append(f"| Sharpe | {pure_tq['sharpe']:.2f} | {msh_t1['sharpe']:.2f} | {msh_t1['sharpe']-pure_tq['sharpe']:+.2f} | {msh_st['sharpe']:.2f} | {msh_st['sharpe']-pure_tq['sharpe']:+.2f} |")
    md.append("")

    md.append("## Verdict")
    md.append("")
    msh_t1_alloc = int(msh_t1["w_ff"] * 100)
    msh_st_alloc = int(msh_st["w_ff"] * 100)
    md.append(f"- **Max-Sharpe Tier 1 mix**: {msh_t1['mix']} ({msh_t1_alloc}% FF) | Sharpe uplift {msh_t1['sharpe']-pure_tq['sharpe']:+.2f} vs pure TQQQ-VT")
    md.append(f"- **Max-Sharpe Stable mix**: {msh_st['mix']} ({msh_st_alloc}% FF) | Sharpe uplift {msh_st['sharpe']-pure_tq['sharpe']:+.2f} vs pure TQQQ-VT")
    md.append("")
    md.append("Compared to the prior (data-noise-driven) Polygon-based allocation analysis where the max-Sharpe mix was 30% FF with Sharpe uplift +0.36, the clean ORATS data shows materially smaller diversification benefit. The negative correlation is real, but at +1-3% standalone CAGR over the relevant window, the size of the Sharpe uplift shrinks substantially.")
    md.append("")
    md.append("Combined with the regime stress finding that FF LOSES money in major vol events (Feb 2018 Volmageddon −6.5%, Feb-Apr 2020 COVID −13.5%), the deployment case for this strategy is now significantly weaker than any prior analysis suggested.")
    md.append("")
    md.append("## Files")
    md.append("")
    md.append(f"- FF Tier 1 daily MTM: `{T1_EQUITY}`")
    md.append(f"- FF Stable daily MTM: `{ST_EQUITY}`")
    md.append(f"- TQQQ-VT daily equity: `{TQ_EQUITY}`")

    REPORT.write_text("\n".join(md))
    print(f"\nWrote {REPORT}", flush=True)


if __name__ == "__main__":
    main()
