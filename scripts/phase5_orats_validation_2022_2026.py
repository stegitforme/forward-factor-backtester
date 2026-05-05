"""ORATS adapter validation: run 2022-2026 backtest on ORATS using the
canonical Tier 1 RunConfig, then reconcile vs the Polygon Tier 1 result
(output/sim_4119dc073393/).

Pass criterion (per Steven's spec):
  - Per-year CAGR delta vs Polygon within ±2pp
  - Per-trade signal alignment: trades that fired in Polygon but not in ORATS
    (or vice versa) should be small in count and explainable

Output: output/PHASE_5_ORATS_ADAPTER_VALIDATION.md
"""
from __future__ import annotations

import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

from config.run_config import RunConfig
from src.adapters.orats_adapter import OratsBarsClient
from src.discover_candidates_orats import discover_orats
from src.simulate_portfolio import simulate


# ============================================================================
# Inputs
# ============================================================================

POLYGON_HASH = "4119dc073393"
POLYGON_DIR = Path(f"output/sim_{POLYGON_HASH}")
POLYGON_TRADES_CSV = POLYGON_DIR / "trade_log.csv"
POLYGON_DAILY_CSV = POLYGON_DIR / "daily_mtm_equity.csv"

# Discovery output for ORATS path
ORATS_CAND_PARQUET = Path("output/phase5_orats_2022_2026_smvVol.parquet")

REPORT_PATH = Path("output/PHASE_5_ORATS_ADAPTER_VALIDATION.md")

# Phase 4 Tier 1 23-ticker universe (matches output/sim_4119dc073393/config.json).
# RunConfig()'s default `universe` is the OLD 17-ticker Phase 3 baseline; the
# Tier 1 Polygon result was produced with this expanded list. Pass explicitly
# so validation compares apples-to-apples.
TIER1_UNIVERSE = (
    "AMD", "ARKK", "COIN", "EEM", "FXI", "GLD", "GOOGL", "HYG", "IBB", "IWM",
    "JPM", "KBE", "KRE", "KWEB", "META", "MSTR", "SLV", "SMH", "SPY", "TLT",
    "USO", "XBI", "XLF",
)


# ============================================================================
# Helpers
# ============================================================================

def cagr_per_year(daily: pd.DataFrame) -> dict[int, dict]:
    """Per-year CAGR / MaxDD / Sharpe from a daily MTM equity series.

    daily must have columns date, combined.
    """
    out = {}
    daily = daily.sort_values("date").copy()
    for year, sub in daily.groupby(daily["date"].dt.year):
        if len(sub) < 2:
            continue
        start = float(sub["combined"].iloc[0])
        end = float(sub["combined"].iloc[-1])
        cal_days = (sub["date"].iloc[-1] - sub["date"].iloc[0]).days
        cagr = ((end / start) ** (365 / max(cal_days, 1)) - 1) * 100 if start > 0 else 0
        rets = sub["combined"].pct_change().dropna()
        sharpe = (rets.mean() * 252) / (rets.std() * (252 ** 0.5)) if rets.std() > 0 else 0
        # MaxDD (PCT-max)
        peak = sub["combined"].iloc[0]
        max_dd = 0.0
        for v in sub["combined"]:
            if v > peak: peak = v
            dd = (peak - v) / peak * 100 if peak > 0 else 0
            if dd > max_dd: max_dd = dd
        out[int(year)] = {
            "cagr": float(cagr),
            "max_dd_pct": float(max_dd),
            "sharpe": float(sharpe),
            "n_days": len(sub),
            "start_val": start,
            "end_val": end,
        }
    return out


def overall_metrics(daily: pd.DataFrame) -> dict:
    daily = daily.sort_values("date")
    start = float(daily["combined"].iloc[0])
    end = float(daily["combined"].iloc[-1])
    cal_days = (daily["date"].iloc[-1] - daily["date"].iloc[0]).days
    cagr = ((end / start) ** (365 / max(cal_days, 1)) - 1) * 100
    rets = daily["combined"].pct_change().dropna()
    sharpe = (rets.mean() * 252) / (rets.std() * (252 ** 0.5)) if rets.std() > 0 else 0
    peak = daily["combined"].iloc[0]
    max_dd = 0.0
    for v in daily["combined"]:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd: max_dd = dd
    return {"cagr": cagr, "max_dd_pct": max_dd, "sharpe": sharpe,
            "start_val": start, "end_val": end}


def main():
    cfg = RunConfig(universe=TIER1_UNIVERSE)
    print(f"### Phase 5 ORATS validation — 2022-2026 vs Polygon Tier 1", flush=True)
    print(f"  RunConfig hash: {cfg.short_hash()}", flush=True)
    print(f"  Polygon canonical hash: {POLYGON_HASH}", flush=True)
    print(f"  Universe: {len(cfg.universe)} tickers", flush=True)
    if cfg.short_hash() != POLYGON_HASH:
        print(f"  WARNING: config hash mismatch — expected {POLYGON_HASH}, got {cfg.short_hash()}", flush=True)
        print(f"  This means the canonical RunConfig changed since Polygon Tier 1 was run.", flush=True)
        print(f"  Validation will compare ORATS@new-hash vs Polygon@old-hash; differences may include config drift.", flush=True)

    # Step 1: ORATS discovery (VV-faithful: smoothSmvVol + earnings filter ON)
    if ORATS_CAND_PARQUET.exists():
        print(f"\n  Reusing existing ORATS candidates parquet: {ORATS_CAND_PARQUET}", flush=True)
    else:
        print(f"\n  Running ORATS discovery (smoothSmvVol, earnings filter ON)...", flush=True)
        t0 = time.time()
        discover_orats(
            start_date=date.fromisoformat(cfg.start_date),
            end_date=date.fromisoformat(cfg.end_date),
            universe=list(cfg.universe),
            cells=[(c[0], c[1], c[2]) for c in cfg.cells],
            output_path=ORATS_CAND_PARQUET,
            iv_column="smoothSmvVol",
            earnings_filter_enabled=True,
            dte_buffer=cfg.dte_buffer_days,
            use_cache=True,
        )
        print(f"  discovery took {time.time()-t0:.0f}s", flush=True)

    # Step 2: Simulation with ORATS bar client
    # NOTE: simulate() writes to {output_dir}/sim_{hash}/ — pass parent
    # `output/orats_validation` so artifacts land at
    # output/orats_validation/sim_{hash}/
    orats_sim_parent = Path("output/orats_validation")
    orats_sim_dir = orats_sim_parent / f"sim_{cfg.short_hash()}"
    if (orats_sim_dir / "metrics.json").exists():
        print(f"\n  Reusing existing ORATS sim output: {orats_sim_dir}", flush=True)
    else:
        print(f"\n  Running ORATS simulation (output: {orats_sim_dir})...", flush=True)
        t0 = time.time()
        client = OratsBarsClient()
        simulate(
            candidates_path=ORATS_CAND_PARQUET,
            cfg=cfg,
            output_dir=orats_sim_parent,
            client=client,
        )
        print(f"  simulation took {time.time()-t0:.0f}s", flush=True)

    # Step 3: Load both result sets
    print(f"\n  Loading both result sets for reconciliation...", flush=True)
    poly_trades = pd.read_csv(POLYGON_TRADES_CSV)
    poly_trades["entry_date"] = pd.to_datetime(poly_trades["entry_date"])
    poly_trades["exit_date"] = pd.to_datetime(poly_trades["exit_date"])
    poly_daily = pd.read_csv(POLYGON_DAILY_CSV, parse_dates=["date"])

    orats_trades = pd.read_csv(orats_sim_dir / "trade_log.csv")
    orats_trades["entry_date"] = pd.to_datetime(orats_trades["entry_date"])
    orats_trades["exit_date"] = pd.to_datetime(orats_trades["exit_date"])
    orats_daily = pd.read_csv(orats_sim_dir / "daily_mtm_equity.csv", parse_dates=["date"])

    # Step 4: Per-year metrics
    print(f"\n  Computing per-year metrics...", flush=True)
    poly_yearly = cagr_per_year(poly_daily)
    orats_yearly = cagr_per_year(orats_daily)
    poly_overall = overall_metrics(poly_daily)
    orats_overall = overall_metrics(orats_daily)

    # Step 5: Per-trade signal reconciliation
    # Match by (cell, ticker, entry_date) — closest analog to "did the same signal fire?"
    print(f"  Reconciling per-trade signals...", flush=True)
    poly_keys = set(zip(poly_trades["cell"], poly_trades["ticker"], poly_trades["entry_date"].dt.date))
    orats_keys = set(zip(orats_trades["cell"], orats_trades["ticker"], orats_trades["entry_date"].dt.date))
    common = poly_keys & orats_keys
    polygon_only = poly_keys - orats_keys
    orats_only = orats_keys - poly_keys

    # Per-cell breakdown
    cells = sorted(set(c for c, _, _ in poly_keys | orats_keys))
    cell_breakdown = []
    for cell in cells:
        p_cell = {(c, t, d) for c, t, d in poly_keys if c == cell}
        o_cell = {(c, t, d) for c, t, d in orats_keys if c == cell}
        cell_breakdown.append({
            "cell": cell,
            "polygon_n": len(p_cell), "orats_n": len(o_cell),
            "common": len(p_cell & o_cell),
            "polygon_only": len(p_cell - o_cell),
            "orats_only": len(o_cell - p_cell),
        })

    # P&L delta on common trades
    poly_idx = poly_trades.set_index(["cell", "ticker", poly_trades["entry_date"].dt.date])
    orats_idx = orats_trades.set_index(["cell", "ticker", orats_trades["entry_date"].dt.date])
    pnl_diffs = []
    for k in common:
        try:
            p_pnl = poly_idx.loc[k, "pnl_total"]
            o_pnl = orats_idx.loc[k, "pnl_total"]
            # If indexed multiple times (rare), take first
            if hasattr(p_pnl, "iloc"): p_pnl = p_pnl.iloc[0]
            if hasattr(o_pnl, "iloc"): o_pnl = o_pnl.iloc[0]
            pnl_diffs.append({
                "cell": k[0], "ticker": k[1], "entry_date": k[2],
                "polygon_pnl": float(p_pnl) if pd.notna(p_pnl) else None,
                "orats_pnl": float(o_pnl) if pd.notna(o_pnl) else None,
            })
        except Exception as e:
            pnl_diffs.append({"cell": k[0], "ticker": k[1], "entry_date": k[2],
                              "polygon_pnl": None, "orats_pnl": None})
    pnl_df = pd.DataFrame(pnl_diffs)
    pnl_df["pnl_diff"] = pnl_df["orats_pnl"] - pnl_df["polygon_pnl"]
    pnl_df["pnl_diff_abs"] = pnl_df["pnl_diff"].abs()

    # Step 6: Markdown report
    print(f"\n  Writing {REPORT_PATH}...", flush=True)
    md = []
    md.append("# Phase 5 — ORATS Adapter Validation (2022-2026)")
    md.append("")
    md.append(f"_Generated {datetime.now().isoformat()}_")
    md.append("")
    md.append("## Purpose")
    md.append("")
    md.append("Validate the ORATS adapter end-to-end by running an apples-to-apples "
              "Tier 1 backtest on ORATS data over the same 2022-2026 window where we "
              "have a canonical Polygon-based result (`output/sim_4119dc073393/`). "
              "If results match within Steven's tolerance "
              "(±2pp per-year CAGR, signal alignment > 90%), the adapter is "
              "trustworthy for extended-history work (2008-2021).")
    md.append("")

    md.append("## Configuration")
    md.append("")
    md.append(f"- **RunConfig hash**: `{cfg.short_hash()}`")
    md.append(f"- **Polygon comparison hash**: `{POLYGON_HASH}`")
    md.append(f"- **Cells**: {[c[0] for c in cfg.cells]}")
    md.append(f"- **FF threshold**: {cfg.ff_threshold}")
    md.append(f"- **Universe size**: {len(cfg.universe)} tickers")
    md.append(f"- **DTE buffer**: ±{cfg.dte_buffer_days} days")
    md.append(f"- **Earnings filter**: {'ON' if cfg.earnings_filter_enabled else 'OFF'}")
    md.append(f"- **IV column**: smoothSmvVol (VV-faithful)")
    md.append(f"- **Window**: {cfg.start_date} → {cfg.end_date}")
    md.append("")

    md.append("## Headline metrics — overall (full window)")
    md.append("")
    md.append("| Metric | Polygon | ORATS | Δ |")
    md.append("|---|---:|---:|---:|")
    md.append(f"| CAGR | {poly_overall['cagr']:+.2f}% | {orats_overall['cagr']:+.2f}% | "
              f"{orats_overall['cagr']-poly_overall['cagr']:+.2f}pp |")
    md.append(f"| MaxDD% | {poly_overall['max_dd_pct']:.2f}% | {orats_overall['max_dd_pct']:.2f}% | "
              f"{orats_overall['max_dd_pct']-poly_overall['max_dd_pct']:+.2f}pp |")
    md.append(f"| Sharpe | {poly_overall['sharpe']:.2f} | {orats_overall['sharpe']:.2f} | "
              f"{orats_overall['sharpe']-poly_overall['sharpe']:+.2f} |")
    md.append(f"| End equity | ${poly_overall['end_val']:,.0f} | ${orats_overall['end_val']:,.0f} | "
              f"${orats_overall['end_val']-poly_overall['end_val']:+,.0f} |")
    md.append(f"| # Trades | {len(poly_trades)} | {len(orats_trades)} | "
              f"{len(orats_trades)-len(poly_trades):+d} |")
    md.append("")

    md.append("## Per-year breakdown")
    md.append("")
    md.append("| Year | Poly CAGR | ORATS CAGR | Δ CAGR | Poly DD | ORATS DD | Poly Sh | ORATS Sh |")
    md.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    years = sorted(set(poly_yearly.keys()) | set(orats_yearly.keys()))
    for y in years:
        p = poly_yearly.get(y, {"cagr": 0, "max_dd_pct": 0, "sharpe": 0})
        o = orats_yearly.get(y, {"cagr": 0, "max_dd_pct": 0, "sharpe": 0})
        delta = o["cagr"] - p["cagr"]
        flag = " ⚠️" if abs(delta) > 2.0 else ""
        md.append(f"| {y}{flag} | {p['cagr']:+.2f}% | {o['cagr']:+.2f}% | {delta:+.2f}pp | "
                  f"{p['max_dd_pct']:.2f}% | {o['max_dd_pct']:.2f}% | "
                  f"{p['sharpe']:.2f} | {o['sharpe']:.2f} |")
    md.append("")
    md.append("⚠️ flag: per-year CAGR delta > 2pp (Steven's tolerance threshold).")
    md.append("")

    md.append("## Per-trade signal alignment")
    md.append("")
    md.append(f"- **Common (fired in both)**: {len(common):,}")
    md.append(f"- **Polygon-only (fired in Polygon, not ORATS)**: {len(polygon_only):,}")
    md.append(f"- **ORATS-only (fired in ORATS, not Polygon)**: {len(orats_only):,}")
    overlap_pct = 100.0 * len(common) / max(len(poly_keys | orats_keys), 1)
    md.append(f"- **Overlap (Jaccard)**: {overlap_pct:.1f}%")
    md.append("")

    md.append("### Per-cell signal counts")
    md.append("")
    md.append("| Cell | Polygon | ORATS | Common | Poly-only | ORATS-only |")
    md.append("|---|---:|---:|---:|---:|---:|")
    for r in cell_breakdown:
        md.append(f"| {r['cell']} | {r['polygon_n']} | {r['orats_n']} | "
                  f"{r['common']} | {r['polygon_only']} | {r['orats_only']} |")
    md.append("")

    if polygon_only:
        md.append("### First 20 Polygon-only signals (fired in Polygon, NOT in ORATS)")
        md.append("")
        md.append("These are signals that ORATS data missed. Most likely causes: "
                  "(1) ORATS strike-rounding differs from Polygon BS-inverted IV, "
                  "(2) FF computation rounding, (3) earnings-filter borderline cases. "
                  "Counts > 20 may indicate a systematic issue.")
        md.append("")
        md.append("| Cell | Ticker | Entry Date |")
        md.append("|---|---|---|")
        for k in sorted(polygon_only)[:20]:
            md.append(f"| {k[0]} | {k[1]} | {k[2]} |")
        md.append("")

    if orats_only:
        md.append("### First 20 ORATS-only signals (fired in ORATS, NOT in Polygon)")
        md.append("")
        md.append("ORATS picked up signals Polygon missed. Likely causes: "
                  "ORATS' smoothSmvVol differs slightly from Polygon BS-inverted IV at "
                  "the threshold boundary; ORATS tickers covered that Polygon couldn't "
                  "resolve.")
        md.append("")
        md.append("| Cell | Ticker | Entry Date |")
        md.append("|---|---|---|")
        for k in sorted(orats_only)[:20]:
            md.append(f"| {k[0]} | {k[1]} | {k[2]} |")
        md.append("")

    md.append("### P&L delta on common trades")
    md.append("")
    if not pnl_df.empty and pnl_df["pnl_diff"].notna().any():
        valid = pnl_df.dropna(subset=["pnl_diff"])
        mean_diff = valid["pnl_diff"].mean()
        median_diff = valid["pnl_diff"].median()
        median_abs = valid["pnl_diff_abs"].median()
        max_abs = valid["pnl_diff_abs"].max()
        md.append(f"| Statistic | Value |")
        md.append(f"|---|---:|")
        md.append(f"| Mean Δ (orats - poly) | ${mean_diff:+,.0f} |")
        md.append(f"| Median Δ | ${median_diff:+,.0f} |")
        md.append(f"| Median |Δ| | ${median_abs:,.0f} |")
        md.append(f"| Max |Δ| | ${max_abs:,.0f} |")
        md.append("")
        md.append("### Top 10 largest |P&L deltas|")
        md.append("")
        top = valid.nlargest(10, "pnl_diff_abs")[["cell", "ticker", "entry_date",
                                                  "polygon_pnl", "orats_pnl", "pnl_diff"]]
        md.append("| Cell | Ticker | Entry | Polygon P&L | ORATS P&L | Δ |")
        md.append("|---|---|---|---:|---:|---:|")
        for _, row in top.iterrows():
            md.append(f"| {row['cell']} | {row['ticker']} | {row['entry_date']} | "
                      f"${row['polygon_pnl']:+,.0f} | ${row['orats_pnl']:+,.0f} | "
                      f"${row['pnl_diff']:+,.0f} |")
        md.append("")
    else:
        md.append("(No common trades or P&L data available for delta computation.)")
        md.append("")

    md.append("## Verdict")
    md.append("")
    over_2pp_years = [y for y in years if abs(orats_yearly.get(y, {"cagr": 0})["cagr"] - poly_yearly.get(y, {"cagr": 0})["cagr"]) > 2.0]
    overall_cagr_delta = abs(orats_overall["cagr"] - poly_overall["cagr"])
    sig_overlap_ok = overlap_pct >= 90.0
    cagr_yearly_ok = len(over_2pp_years) == 0
    cagr_overall_ok = overall_cagr_delta <= 2.0
    md.append(f"- **Overall CAGR delta**: {orats_overall['cagr']-poly_overall['cagr']:+.2f}pp ({'✅ within ±2pp' if cagr_overall_ok else '❌ exceeds ±2pp'})")
    md.append(f"- **Per-year CAGR within ±2pp**: {'✅ all years' if cagr_yearly_ok else f'❌ years exceeding: {over_2pp_years}'}")
    md.append(f"- **Signal overlap**: {overlap_pct:.1f}% ({'✅ ≥90%' if sig_overlap_ok else '❌ <90%'})")
    md.append("")
    if cagr_yearly_ok and cagr_overall_ok and sig_overlap_ok:
        md.append("**ADAPTER VALIDATED.** Proceed with extended-history work.")
    else:
        md.append("**ADAPTER NEEDS DESIGN REVIEW.** Investigate divergences before extending history.")
    md.append("")

    md.append("## Files")
    md.append("")
    md.append(f"- ORATS candidate parquet: `{ORATS_CAND_PARQUET}`")
    md.append(f"- ORATS sim output: `{orats_sim_dir}/`")
    md.append(f"- Polygon canonical: `{POLYGON_DIR}/`")
    md.append("")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(md))
    print(f"  wrote {REPORT_PATH}", flush=True)

    print(f"\n=== HEADLINE: Polygon CAGR {poly_overall['cagr']:+.2f}% vs ORATS {orats_overall['cagr']:+.2f}% "
          f"(Δ {orats_overall['cagr']-poly_overall['cagr']:+.2f}pp); "
          f"signal overlap {overlap_pct:.1f}% ===", flush=True)


if __name__ == "__main__":
    main()
