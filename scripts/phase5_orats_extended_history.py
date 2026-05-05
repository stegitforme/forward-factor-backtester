"""ORATS extended-history backtest: 2008-2026 with the methodology-improved
config (3 cells + extVol Path A + era-adaptive dte_buffer).

Two simulations on a single discovery output:
  1. Tier 1 unconstrained — no caps, quarter-Kelly
  2. Phase 5 stable — half-Kelly + debit-floor 0.15 + 12% per-ticker NAV cap +
     asset-class caps

Era-adaptive dte_buffer (Steven's locked decision 2026-05-04):
  2007-2010: 15 (monthly expiries only)
  2011-2015: 12 (weeklies launching on indices)
  2016-2020: 8 (weekly availability spreading to single names)
  2021-2026: 5 (dense weekly chains)

Outputs:
  output/phase5_orats_2008_2026_extVol.parquet                     (discovery)
  output/orats_extended/sim_<HASH>/                                (Tier 1)
  output/orats_extended_stable/sim_<HASH>/                         (stable)
"""
from __future__ import annotations

import sys
import time
from datetime import date
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.run_config import RunConfig
from src.adapters.orats_adapter import OratsBarsClient
from src.discover_candidates_orats import discover_orats
from src.simulate_portfolio import simulate

# Phase 4 Tier 1 23-ticker universe (matches output/sim_4119dc073393/config.json)
TIER1_UNIVERSE = (
    "AMD", "ARKK", "COIN", "EEM", "FXI", "GLD", "GOOGL", "HYG", "IBB", "IWM",
    "JPM", "KBE", "KRE", "KWEB", "META", "MSTR", "SLV", "SMH", "SPY", "TLT",
    "USO", "XBI", "XLF",
)

CELLS_3 = (
    ("30_60_atm", 30, 60),
    ("30_90_atm", 30, 90),
    ("60_90_atm", 60, 90),
)

DTE_BUFFER_BY_YEAR = {
    **{y: 15 for y in range(2007, 2011)},
    **{y: 12 for y in range(2011, 2016)},
    **{y: 8 for y in range(2016, 2021)},
    **{y: 5 for y in range(2021, 2027)},
}

START = date(2008, 1, 2)
END = date(2026, 4, 30)

DISCOVERY_PARQUET = Path("output/phase5_orats_2008_2026_extVol.parquet")

# Phase 5 stable asset-class map (re-used from scripts/phase5_stable_run.py)
ASSET_CLASS_MAP = {
    "SPY": "equity_etf", "IWM": "equity_etf", "SMH": "equity_etf",
    "XBI": "equity_etf", "KRE": "equity_etf", "KBE": "equity_etf",
    "XLF": "equity_etf", "IBB": "equity_etf", "ARKK": "equity_etf",
    "MSTR": "single_name", "META": "single_name", "AMD": "single_name",
    "GOOGL": "single_name", "JPM": "single_name", "COIN": "single_name",
    "KWEB": "international", "EEM": "international", "FXI": "international",
    "TLT": "bond", "HYG": "bond",
    "GLD": "commodity", "SLV": "commodity", "USO": "commodity",
}
ASSET_CLASS_CAPS = {
    "equity_etf": 0.50, "single_name": 0.20, "commodity": 0.20,
    "bond": 0.15, "international": 0.15, "vol": 0.10,
}


def main():
    print("### Phase 5 ORATS Extended-History Backtest", flush=True)
    print(f"  Window: {START} -> {END}", flush=True)
    print(f"  Universe: {len(TIER1_UNIVERSE)} tickers", flush=True)
    print(f"  Cells: {[c[0] for c in CELLS_3]}", flush=True)
    print(f"  IV column: extVol (Path A — earnings filter OFF)", flush=True)
    print(f"  Era-adaptive dte_buffer: 2007-10=15, 2011-15=12, 2016-20=8, 2021+=5", flush=True)
    print()

    # Step 1: Discovery
    if DISCOVERY_PARQUET.exists():
        print(f"[1/3] Reusing discovery parquet: {DISCOVERY_PARQUET}", flush=True)
    else:
        print(f"[1/3] Running ORATS discovery 2008-2026...", flush=True)
        t0 = time.time()
        discover_orats(
            start_date=START,
            end_date=END,
            universe=list(TIER1_UNIVERSE),
            cells=list(CELLS_3),
            output_path=DISCOVERY_PARQUET,
            iv_column="extVol",
            earnings_filter_enabled=False,  # Path A: extVol strips earnings vol
            dte_buffer=5,  # fallback for years not in dte_buffer_by_year
            dte_buffer_by_year=DTE_BUFFER_BY_YEAR,
            use_cache=True,
        )
        print(f"      took {time.time()-t0:.0f}s", flush=True)

    # Step 2: Simulation — Tier 1 unconstrained
    cfg_tier1 = RunConfig(
        cells=CELLS_3,
        universe=TIER1_UNIVERSE,
        start_date=START.isoformat(),
        end_date=END.isoformat(),
        earnings_filter_enabled=False,  # Path A
    )
    tier1_dir = Path("output/orats_extended")
    tier1_sim = tier1_dir / f"sim_{cfg_tier1.short_hash()}"
    if (tier1_sim / "metrics.json").exists():
        print(f"\n[2/3] Reusing Tier 1 sim: {tier1_sim}", flush=True)
    else:
        print(f"\n[2/3] Running Tier 1 simulation (output: {tier1_sim})...", flush=True)
        t0 = time.time()
        simulate(
            candidates_path=DISCOVERY_PARQUET,
            cfg=cfg_tier1,
            output_dir=tier1_dir,
            client=OratsBarsClient(),
        )
        print(f"      took {time.time()-t0:.0f}s", flush=True)

    # Step 3: Simulation — Phase 5 stable (caps + half-Kelly)
    cfg_stable = replace(
        cfg_tier1,
        risk_per_trade=0.02,                       # half-Kelly
        debit_floor=0.15,                          # tighter
        position_cap_per_ticker_nav_pct=0.12,
        asset_class_caps=ASSET_CLASS_CAPS,
        asset_class_map=ASSET_CLASS_MAP,
    )
    stable_dir = Path("output/orats_extended_stable")
    stable_sim = stable_dir / f"sim_{cfg_stable.short_hash()}"
    if (stable_sim / "metrics.json").exists():
        print(f"\n[3/3] Reusing stable sim: {stable_sim}", flush=True)
    else:
        print(f"\n[3/3] Running stable simulation (output: {stable_sim})...", flush=True)
        t0 = time.time()
        simulate(
            candidates_path=DISCOVERY_PARQUET,
            cfg=cfg_stable,
            output_dir=stable_dir,
            client=OratsBarsClient(),
        )
        print(f"      took {time.time()-t0:.0f}s", flush=True)

    print(f"\n=== Done. Both backtests written. Now run regime stress + reports. ===", flush=True)
    print(f"  Tier 1 hash: {cfg_tier1.short_hash()}", flush=True)
    print(f"  Stable hash: {cfg_stable.short_hash()}", flush=True)


if __name__ == "__main__":
    main()
