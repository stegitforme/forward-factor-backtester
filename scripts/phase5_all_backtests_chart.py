"""Per-year CAGR + MaxDD comparison chart across all 5 main backtests.

Renders a two-panel grouped bar chart so Steven can see the full story
at a glance: which config + which year, CAGR (top) and MaxDD (bottom).

Output: output/PHASE_5_ALL_BACKTESTS_COMPARISON.png
       output/phase5_all_backtests_yearly.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PNG_OUT = Path("output/PHASE_5_ALL_BACKTESTS_COMPARISON.png")
CSV_OUT = Path("output/phase5_all_backtests_yearly.csv")

# The 5 backtests that tell the story. Order matters for the chart legend.
BACKTESTS = [
    {
        "name": "Polygon Tier 1 (data-noise driven)",
        "path": "output/sim_4119dc073393/daily_mtm_equity.csv",
        "color": "#cc0000",
        "cagr_full": 32.78,
        "config": "2-cell, 23 ticker, no caps",
    },
    {
        "name": "Polygon Phase 5 stable (caps)",
        "path": "output/sim_e3fa28f120d1/daily_mtm_equity.csv",
        "color": "#ff8800",
        "cagr_full": 6.48,
        "config": "2-cell, 17 ticker, half-Kelly + caps",
    },
    {
        "name": "ORATS Tier 1 2022-2026 (validation)",
        "path": "output/orats_validation/sim_fb5fb0d6b38e/daily_mtm_equity.csv",
        "color": "#0088cc",
        "cagr_full": 3.09,
        "config": "2-cell smvVol, 23 ticker",
    },
    {
        "name": "ORATS Tier 1 2008-2026 (3-cell + extVol)",
        "path": "output/orats_extended/sim_d075198d5e15/daily_mtm_equity.csv",
        "color": "#005599",
        "cagr_full": 1.83,
        "config": "3-cell extVol Path A, 23 ticker, era-buffer",
    },
    {
        "name": "ORATS Stable 2008-2026 (3-cell + extVol + caps)",
        "path": "output/orats_extended_stable/sim_0b99f17e7a71/daily_mtm_equity.csv",
        "color": "#00cc66",
        "cagr_full": 1.35,
        "config": "3-cell extVol + half-Kelly + caps, 23 ticker",
    },
]


def per_year_metrics(eq_csv: str | Path) -> pd.DataFrame:
    """Return DataFrame with columns: year, cagr_pct, max_dd_pct, sharpe, n_days."""
    df = pd.read_csv(eq_csv, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df["year"] = df["date"].dt.year
    out = []
    for year, sub in df.groupby("year"):
        if len(sub) < 2:
            continue
        eq = sub["combined"].values
        dates = sub["date"]
        start = float(eq[0]); end = float(eq[-1])
        cal_days = (dates.iloc[-1] - dates.iloc[0]).days
        cagr = ((end / start) ** (365 / max(cal_days, 1)) - 1) * 100 if start > 0 else 0
        rets = pd.Series(eq).pct_change().dropna()
        sh = (rets.mean() * 252) / (rets.std() * (252 ** 0.5)) if rets.std() > 0 else 0
        peak = eq[0]; max_dd = 0.0
        for v in eq:
            if v > peak: peak = v
            dd = (peak - v) / peak * 100 if peak > 0 else 0
            if dd > max_dd: max_dd = dd
        out.append({"year": int(year), "cagr": float(cagr), "max_dd": float(max_dd),
                    "sharpe": float(sh), "n_days": len(sub)})
    return pd.DataFrame(out)


def main():
    # Compute per-year metrics for every config
    all_data = {}
    for bt in BACKTESTS:
        df = per_year_metrics(bt["path"])
        df["config"] = bt["name"]
        all_data[bt["name"]] = df
        print(f"  {bt['name']}: years {df['year'].min()}-{df['year'].max()}, full-window CAGR {bt['cagr_full']}%", flush=True)

    # Flat table for CSV
    flat = pd.concat(all_data.values(), ignore_index=True)
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    flat.to_csv(CSV_OUT, index=False)
    print(f"Wrote {CSV_OUT}")

    # Pivot for plotting: rows = year, cols = config name, values = cagr / max_dd
    cagr_pivot = flat.pivot(index="year", columns="config", values="cagr")
    dd_pivot = flat.pivot(index="year", columns="config", values="max_dd")

    # Re-order columns to match BACKTESTS order
    ordered_names = [bt["name"] for bt in BACKTESTS]
    cagr_pivot = cagr_pivot[ordered_names]
    dd_pivot = dd_pivot[ordered_names]

    years = list(cagr_pivot.index)
    n_configs = len(ordered_names)
    bar_width = 0.85 / n_configs

    fig, (ax_cagr, ax_dd) = plt.subplots(2, 1, figsize=(18, 10), sharex=True)

    # --- Top: per-year CAGR ---
    for i, bt in enumerate(BACKTESTS):
        positions = np.arange(len(years)) + (i - (n_configs - 1) / 2) * bar_width
        vals = cagr_pivot[bt["name"]].values
        ax_cagr.bar(positions, vals, bar_width, label=f"{bt['name']} (full: {bt['cagr_full']:+.2f}%)",
                    color=bt["color"], alpha=0.85)
    ax_cagr.axhline(0, color="black", linewidth=0.5)
    ax_cagr.set_ylabel("Per-year CAGR (%)", fontsize=12)
    ax_cagr.set_title("Forward Factor — per-year CAGR across all 5 main backtests",
                      fontsize=13, fontweight="bold")
    ax_cagr.legend(loc="upper left", fontsize=9)
    ax_cagr.grid(True, alpha=0.3, axis="y")

    # Annotate regime stress periods on top axis
    regime_annotations = [
        (2008.5, "GFC", "red"),
        (2018.0, "Volm.", "red"),
        (2020.2, "COVID", "red"),
        (2024.5, "IWM\noutlier", "purple"),
    ]
    ymin, ymax = ax_cagr.get_ylim()
    for x_year, label, color in regime_annotations:
        if min(years) <= x_year <= max(years):
            x_pos = years.index(int(x_year)) + (x_year - int(x_year)) - 0.5
            ax_cagr.annotate(label, xy=(x_pos, ymax * 0.95), xytext=(x_pos, ymax * 0.95),
                            ha="center", fontsize=9, color=color, fontweight="bold",
                            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=color, alpha=0.7))

    # --- Bottom: per-year MaxDD ---
    for i, bt in enumerate(BACKTESTS):
        positions = np.arange(len(years)) + (i - (n_configs - 1) / 2) * bar_width
        vals = dd_pivot[bt["name"]].values
        ax_dd.bar(positions, vals, bar_width, label=bt["name"], color=bt["color"], alpha=0.85)
    ax_dd.axhline(0, color="black", linewidth=0.5)
    ax_dd.set_ylabel("Per-year MaxDD (%)", fontsize=12)
    ax_dd.set_xlabel("Year", fontsize=12)
    ax_dd.set_title("Per-year MaxDD (within-year peak-to-trough)", fontsize=13, fontweight="bold")
    ax_dd.grid(True, alpha=0.3, axis="y")
    ax_dd.invert_yaxis()  # show DD descending so deeper = lower

    ax_dd.set_xticks(np.arange(len(years)))
    ax_dd.set_xticklabels(years)

    plt.suptitle("Phase 5 — All 5 main backtests, per-year breakdown\n"
                 "Polygon Tier 1's +32.78% headline was data-noise; clean ORATS data shows ~+1-3% real edge across regimes",
                 fontsize=13, y=0.995)
    plt.tight_layout(rect=(0, 0, 1, 0.97))
    PNG_OUT.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(PNG_OUT, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"Wrote {PNG_OUT}")

    # ---- Also: normalized equity curves ----
    png_curves = Path("output/PHASE_5_ALL_BACKTESTS_CURVES.png")
    fig, ax = plt.subplots(figsize=(16, 8))
    for bt in BACKTESTS:
        df = pd.read_csv(bt["path"], parse_dates=["date"])
        df = df.sort_values("date")
        norm = df["combined"] / df["combined"].iloc[0] * 100
        ax.plot(df["date"], norm, label=f"{bt['name']} ({bt['cagr_full']:+.2f}%)",
                color=bt["color"], linewidth=1.8, alpha=0.85)
    ax.axhline(100, color="gray", linestyle="--", linewidth=0.5)
    ax.set_ylabel("Normalized equity ($100 = start)", fontsize=12)
    ax.set_xlabel("Date", fontsize=12)
    ax.set_title("FF backtests — normalized equity curves (all 5 main configs)",
                 fontsize=13, fontweight="bold")
    ax.legend(loc="upper left", fontsize=10)
    ax.grid(True, alpha=0.3)
    # Mark stress periods
    for date_str, label in [("2018-02-05", "Volmageddon"), ("2020-03-15", "COVID"),
                             ("2024-07-18", "IWM phantom trade")]:
        d = pd.Timestamp(date_str)
        ax.axvline(d, color="red", linestyle=":", linewidth=0.8, alpha=0.5)
        ax.text(d, ax.get_ylim()[1] * 0.95, label, rotation=90, fontsize=9, color="red",
                ha="right", va="top", alpha=0.8)
    plt.tight_layout()
    plt.savefig(png_curves, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"Wrote {png_curves}")


if __name__ == "__main__":
    main()
