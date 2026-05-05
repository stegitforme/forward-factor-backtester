"""Three-way methodology diagnostics on 2022-2026 ORATS data.

Purpose: explain (or eliminate) the gap between our +3-7% backtest CAGR and
VV's published +27% claim by varying two methodology choices VV uses but we
didn't test:

  1. **30-60 cell** — VV's published research backtests 3 cells (30-60, 30-90,
     60-90) and 2 structures. We only test the 2 longer cells. 30-60 has the
     densest signal calendar — VV reports 148.6 trades/quarter for 30-60 vs
     11.5 for 60-90 (13x denser). Even if 30-60's per-trade edge is smaller,
     the signal count alone could materially boost CAGR.

  2. **extVol** — ORATS' ex-earnings IV. The Path A adjustment we deferred in
     Phase 1. If smoothSmvVol smoothing dampens the FF signal, extVol's
     earnings-stripped IV might either reveal a different signal pattern or
     produce the same modest result (confirming the strategy is fundamentally
     modest).

Combined with the IWM Jul 18 2024 raw-data diagnostic, this should explain
most of the gap.

Outputs:
  output/phase5_orats_2022_2026_3cells_smvVol.parquet
  output/phase5_orats_2022_2026_extVol.parquet
  output/PHASE_5_METHODOLOGY_DIAGNOSTICS.md
"""
from __future__ import annotations

import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from src.discover_candidates_orats import discover_orats

# Phase 4 Tier 1 23-ticker universe
TIER1_UNIVERSE = [
    "AMD", "ARKK", "COIN", "EEM", "FXI", "GLD", "GOOGL", "HYG", "IBB", "IWM",
    "JPM", "KBE", "KRE", "KWEB", "META", "MSTR", "SLV", "SMH", "SPY", "TLT",
    "USO", "XBI", "XLF",
]

START = date(2022, 1, 3)
END = date(2026, 4, 30)

PARQ_3CELL = Path("output/phase5_orats_2022_2026_3cells_smvVol.parquet")
PARQ_EXTVOL = Path("output/phase5_orats_2022_2026_extVol.parquet")
EXISTING_2CELL = Path("output/phase5_orats_2022_2026_smvVol.parquet")

REPORT_PATH = Path("output/PHASE_5_METHODOLOGY_DIAGNOSTICS.md")


def main():
    print("### Phase 5 Methodology Diagnostics", flush=True)
    print(f"  Window: {START} -> {END}", flush=True)
    print(f"  Universe: {len(TIER1_UNIVERSE)} tickers", flush=True)
    print()

    # ----- Discovery 1: 3 cells (add 30-60) with smoothSmvVol -----
    if PARQ_3CELL.exists():
        print(f"[1/2] Reusing 3-cell parquet: {PARQ_3CELL}", flush=True)
    else:
        print(f"[1/2] Discovery: 3 cells × smoothSmvVol...", flush=True)
        t0 = time.time()
        discover_orats(
            start_date=START, end_date=END,
            universe=TIER1_UNIVERSE,
            cells=[("30_60_atm", 30, 60), ("30_90_atm", 30, 90), ("60_90_atm", 60, 90)],
            output_path=PARQ_3CELL,
            iv_column="smoothSmvVol",
            earnings_filter_enabled=True,
            use_cache=True,
        )
        print(f"      took {time.time()-t0:.0f}s", flush=True)

    # ----- Discovery 2: 2 cells with extVol -----
    if PARQ_EXTVOL.exists():
        print(f"[2/2] Reusing extVol parquet: {PARQ_EXTVOL}", flush=True)
    else:
        print(f"[2/2] Discovery: 2 cells × extVol (Path A)...", flush=True)
        t0 = time.time()
        discover_orats(
            start_date=START, end_date=END,
            universe=TIER1_UNIVERSE,
            cells=[("30_90_atm", 30, 90), ("60_90_atm", 60, 90)],
            output_path=PARQ_EXTVOL,
            iv_column="extVol",
            earnings_filter_enabled=False,  # Path A: extVol already strips earnings vol
            use_cache=True,
        )
        print(f"      took {time.time()-t0:.0f}s", flush=True)

    # ----- Analyze -----
    print("\n=== Analysis ===", flush=True)
    df_3cell = pd.read_parquet(PARQ_3CELL)
    df_extvol = pd.read_parquet(PARQ_EXTVOL)
    df_baseline = pd.read_parquet(EXISTING_2CELL)  # original 2-cell smvVol for cross-ref

    # Per-cell summary stats
    def summarize(df: pd.DataFrame, label: str) -> pd.DataFrame:
        rows = []
        for cell in sorted(df["cell"].unique()):
            sub = df[df["cell"] == cell]
            rows.append({
                "config": label,
                "cell": cell,
                "n_total": len(sub),
                "n_resolved": int(sub["back_leg_resolved"].sum()),
                "n_ff_valid": int(sub["ff"].notna().sum()),
                "n_ff_strong": int((sub["ff"].fillna(-1) >= 0.20).sum()),
                "n_earnings_blocked": int(sub["earnings_blocked"].sum()),
                "median_ff_resolved": float(sub.loc[sub["back_leg_resolved"], "ff"].median()) if int(sub["back_leg_resolved"].sum()) > 0 else float("nan"),
                "p90_ff_resolved": float(sub.loc[sub["back_leg_resolved"], "ff"].quantile(0.90)) if int(sub["back_leg_resolved"].sum()) > 0 else float("nan"),
            })
        return pd.DataFrame(rows)

    s_3cell = summarize(df_3cell, "3cells_smvVol(earn_filter=ON)")
    s_extvol = summarize(df_extvol, "2cells_extVol(earn_filter=OFF)")
    s_baseline = summarize(df_baseline, "2cells_smvVol_baseline")
    print()
    print("PER-CELL SUMMARY:", flush=True)
    print(pd.concat([s_baseline, s_3cell, s_extvol], ignore_index=True).to_string(index=False), flush=True)

    # ----- Q1: Does 30-60 cell add a lot of signal? -----
    print("\n=== Q1: Does adding 30-60 boost the strategy? ===")
    n3 = s_3cell.set_index("cell")
    if "30_60_atm" in n3.index:
        c30_60 = int(n3.loc["30_60_atm", "n_ff_strong"])
        c30_90 = int(n3.loc["30_90_atm", "n_ff_strong"])
        c60_90 = int(n3.loc["60_90_atm", "n_ff_strong"])
        total = c30_60 + c30_90 + c60_90
        print(f"  FF >= 0.20 hits per cell:")
        print(f"    30-60: {c30_60} ({100*c30_60/total:.0f}%)")
        print(f"    30-90: {c30_90} ({100*c30_90/total:.0f}%)")
        print(f"    60-90: {c60_90} ({100*c60_90/total:.0f}%)")
        if c30_60 > c30_90 and c30_60 > c60_90:
            print(f"  -> 30-60 IS the densest cell (matches VV's published 36x trade frequency)")

    # ----- Q2: Does extVol change the signal? -----
    print("\n=== Q2: Does extVol change the signal vs smoothSmvVol? ===")
    # Per cell, compare ff_strong counts: extVol vs smoothSmvVol baseline
    se = s_extvol.set_index("cell")
    sb = s_baseline.set_index("cell")
    for cell in ["30_90_atm", "60_90_atm"]:
        if cell not in se.index or cell not in sb.index: continue
        ext = int(se.loc[cell, "n_ff_strong"])
        smv = int(sb.loc[cell, "n_ff_strong"])
        delta = ext - smv
        print(f"  {cell}: extVol={ext} hits | smoothSmvVol={smv} hits | delta={delta:+d}")

    # Per-row FF correlation: where both have ff_valid, how do they compare?
    # Match on (date, ticker, cell) — both parquets have the same rows for 2-cell × 23 ticker × 1085 days.
    df_baseline_idx = df_baseline.set_index(["date", "ticker", "cell"])
    df_extvol_idx = df_extvol.set_index(["date", "ticker", "cell"])
    common_idx = df_baseline_idx.index.intersection(df_extvol_idx.index)
    print(f"\n  Common (date,ticker,cell): {len(common_idx):,}")
    bff = df_baseline_idx.loc[common_idx, "ff"]
    eff = df_extvol_idx.loc[common_idx, "ff"]
    both_valid = bff.notna() & eff.notna()
    print(f"  Rows with both FFs valid: {int(both_valid.sum()):,}")
    diff = (eff - bff)[both_valid]
    print(f"  FF(extVol) - FF(smoothSmvVol):")
    print(f"    mean   = {diff.mean():+.4f}")
    print(f"    median = {diff.median():+.4f}")
    print(f"    std    = {diff.std():.4f}")
    print(f"    p90    = {diff.quantile(0.90):+.4f}")
    print(f"    p10    = {diff.quantile(0.10):+.4f}")

    # Of the rows where smoothSmvVol gave FF >= 0.20, what % does extVol also give FF >= 0.20?
    smv_strong = bff[both_valid] >= 0.20
    ext_strong = eff[both_valid] >= 0.20
    n_both = int((smv_strong & ext_strong).sum())
    n_smv_only = int((smv_strong & ~ext_strong).sum())
    n_ext_only = int((~smv_strong & ext_strong).sum())
    n_neither = int((~smv_strong & ~ext_strong).sum())
    print(f"\n  FF >= 0.20 cross-classification:")
    print(f"    Both >= 0.20:     {n_both}")
    print(f"    smvVol-only:      {n_smv_only}")
    print(f"    extVol-only:      {n_ext_only}")
    print(f"    Neither:          {n_neither}")

    # ----- Q3: Polygon-only signals — does extVol pick them up? -----
    poly = pd.read_csv("output/sim_4119dc073393/trade_log.csv")
    poly["entry_date"] = pd.to_datetime(poly["entry_date"]).dt.date
    poly_keys = set(zip(poly["cell"], poly["ticker"], poly["entry_date"]))

    # Attach extVol FF for each Polygon trade
    df_extvol["date"] = pd.to_datetime(df_extvol["date"]).dt.date
    extvol_lookup = df_extvol.set_index(["cell", "ticker", "date"])
    df_baseline["date"] = pd.to_datetime(df_baseline["date"]).dt.date
    baseline_lookup = df_baseline.set_index(["cell", "ticker", "date"])

    poly_extvol_ff = []
    poly_smv_ff = []
    for cell, ticker, ed in poly_keys:
        try:
            ext_ff = extvol_lookup.loc[(cell, ticker, ed), "ff"]
            if hasattr(ext_ff, "iloc"): ext_ff = ext_ff.iloc[0]
            if pd.notna(ext_ff): poly_extvol_ff.append(ext_ff)
        except Exception: pass
        try:
            smv_ff = baseline_lookup.loc[(cell, ticker, ed), "ff"]
            if hasattr(smv_ff, "iloc"): smv_ff = smv_ff.iloc[0]
            if pd.notna(smv_ff): poly_smv_ff.append(smv_ff)
        except Exception: pass

    poly_extvol_ff = pd.Series(poly_extvol_ff)
    poly_smv_ff = pd.Series(poly_smv_ff)
    print(f"\n=== Q3: On {len(poly_keys)} Polygon-fire dates, what do ORATS FFs say? ===")
    print(f"  smoothSmvVol FF on Polygon-fire days (n={len(poly_smv_ff)}):")
    print(f"    median = {poly_smv_ff.median():+.4f}, mean = {poly_smv_ff.mean():+.4f}")
    print(f"    >= 0.20: {int((poly_smv_ff >= 0.20).sum())} ({100*(poly_smv_ff >= 0.20).mean():.1f}%)")
    print(f"  extVol FF on Polygon-fire days (n={len(poly_extvol_ff)}):")
    print(f"    median = {poly_extvol_ff.median():+.4f}, mean = {poly_extvol_ff.mean():+.4f}")
    print(f"    >= 0.20: {int((poly_extvol_ff >= 0.20).sum())} ({100*(poly_extvol_ff >= 0.20).mean():.1f}%)")

    # ----- Markdown report -----
    md = []
    md.append("# Phase 5 — Methodology Diagnostics: 30-60 Cell + extVol")
    md.append("")
    md.append(f"_Generated {datetime.now().isoformat()}_")
    md.append("")
    md.append("## Purpose")
    md.append("")
    md.append("Two methodology variants VV uses but we didn't test, run quickly to "
              "explain the gap between our 2022-2026 ORATS result (+3.09% CAGR) and "
              "VV's published +27% claim. Combined with the IWM Jul 18 2024 raw-data "
              "diagnostic, this should explain most of the gap.")
    md.append("")
    md.append(f"**Window**: {START} → {END}  |  **Universe**: 23 tickers (Tier 1)  |  **Threshold**: FF ≥ 0.20")
    md.append("")

    md.append("## Per-cell × per-config signal stats")
    md.append("")
    md.append("| Config | Cell | Total | Resolved | FF valid | **FF≥0.20** | Earn-blocked | Median FF | P90 FF |")
    md.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for s_df in [s_baseline, s_3cell, s_extvol]:
        for _, r in s_df.iterrows():
            md.append(f"| {r['config']} | {r['cell']} | {r['n_total']:,} | {r['n_resolved']:,} | "
                      f"{r['n_ff_valid']:,} | **{r['n_ff_strong']:,}** | {r['n_earnings_blocked']:,} | "
                      f"{r['median_ff_resolved']:+.4f} | {r['p90_ff_resolved']:+.4f} |")
    md.append("")

    md.append("## Q1: Does the 30-60 cell add signal?")
    md.append("")
    if "30_60_atm" in n3.index:
        md.append(f"FF ≥ 0.20 hits across the 3 cells:")
        md.append("")
        md.append(f"| Cell | Hits | Share |")
        md.append(f"|---|---:|---:|")
        c30_60 = int(n3.loc["30_60_atm", "n_ff_strong"])
        c30_90 = int(n3.loc["30_90_atm", "n_ff_strong"])
        c60_90 = int(n3.loc["60_90_atm", "n_ff_strong"])
        total_hits = c30_60 + c30_90 + c60_90
        for cell, hits in [("30_60_atm", c30_60), ("30_90_atm", c30_90), ("60_90_atm", c60_90)]:
            pct = 100 * hits / max(total_hits, 1)
            md.append(f"| {cell} | {hits} | {pct:.0f}% |")
        md.append(f"| **Total** | **{total_hits}** | **100%** |")
        md.append("")
        md.append(f"**VV's published spec**: 30-60 fires 13× more trades/quarter than 60-90, "
                  f"30-90 fires 36× more (densest cell).")
        md.append("")
        if c30_60 > c60_90:
            md.append(f"**Our finding**: 30-60 produces {c30_60/c60_90:.1f}× the FF≥0.20 hits "
                      f"of 60-90. Adds materially to total signal count.")
        else:
            md.append(f"**Our finding**: 30-60 does NOT produce more hits than 60-90 in our data "
                      f"({c30_60} vs {c60_90}). Inconsistent with VV — possibly the FF "
                      f"distribution differs by cell more than VV's spec suggests.")
    md.append("")

    md.append("## Q2: Does extVol (ex-earnings IV) change the signal?")
    md.append("")
    md.append(f"Comparing extVol-based FF to smoothSmvVol-based FF on the same {len(common_idx):,} "
              f"(date, ticker, cell) rows where both compute valid FF:")
    md.append("")
    md.append(f"| Statistic | Value |")
    md.append(f"|---|---:|")
    md.append(f"| Mean Δ (extVol - smvVol) | {diff.mean():+.4f} |")
    md.append(f"| Median Δ | {diff.median():+.4f} |")
    md.append(f"| Std Δ | {diff.std():.4f} |")
    md.append(f"| P10 / P90 Δ | {diff.quantile(0.10):+.4f} / {diff.quantile(0.90):+.4f} |")
    md.append("")
    md.append(f"**FF ≥ 0.20 cross-classification** (per row):")
    md.append("")
    md.append(f"| | extVol ≥ 0.20 | extVol < 0.20 |")
    md.append(f"|---|---:|---:|")
    md.append(f"| **smvVol ≥ 0.20** | {n_both} | {n_smv_only} |")
    md.append(f"| **smvVol < 0.20** | {n_ext_only} | {n_neither:,} |")
    md.append("")
    if n_ext_only > n_smv_only:
        md.append(f"**extVol picks up {n_ext_only} signals smvVol misses, while smvVol picks up "
                  f"only {n_smv_only} that extVol misses.** Net: extVol fires more often.")
    elif n_smv_only > n_ext_only:
        md.append(f"**smvVol picks up {n_smv_only} signals extVol misses, while extVol picks up "
                  f"only {n_ext_only} that smvVol misses.** Net: smvVol fires more often.")
    else:
        md.append(f"Roughly symmetric — extVol and smvVol cross threshold at similar rates.")
    md.append("")

    md.append("## Q3: On Polygon-fire dates, do ORATS IVs say the signal was real?")
    md.append("")
    md.append(f"Polygon Tier 1 fired {len(poly_keys):,} (cell, ticker, date) signals. "
              f"For each, we look up ORATS' FF on the same date:")
    md.append("")
    md.append(f"| IV column | Median FF on Polygon-fire days | % crossing 0.20 |")
    md.append(f"|---|---:|---:|")
    md.append(f"| smoothSmvVol | {poly_smv_ff.median():+.4f} | {100*(poly_smv_ff >= 0.20).mean():.1f}% |")
    md.append(f"| extVol | {poly_extvol_ff.median():+.4f} | {100*(poly_extvol_ff >= 0.20).mean():.1f}% |")
    md.append("")
    md.append(f"If both ORATS columns say FF was nowhere near 0.20 on Polygon-fire days, that's "
              f"strong evidence those signals were Polygon-data-noise (BS-IV inverted off thin/stale "
              f"close prices), not real backwardation.")
    md.append("")

    md.append("## Combined diagnostic verdict")
    md.append("")
    md.append("Three diagnostics together:")
    md.append("")
    md.append("1. **IWM 2024-07-18 218C** (raw bid/ask): ATM call traded $8.94-$8.99 — Polygon's "
              "$0.03 close was a stale print, not a tradable price. The +$305K trade is fake.")
    md.append("2. **30-60 cell** (this report Q1): see table above.")
    md.append("3. **extVol** (this report Q2 + Q3): see table above.")
    md.append("")

    md.append("## Files")
    md.append("")
    md.append(f"- `{PARQ_3CELL}` — 3-cell smvVol discovery output")
    md.append(f"- `{PARQ_EXTVOL}` — 2-cell extVol discovery output")
    md.append(f"- `{EXISTING_2CELL}` — original 2-cell smvVol baseline")

    REPORT_PATH.write_text("\n".join(md))
    print(f"\nWrote {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
