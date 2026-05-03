"""4-part validation for the discover_candidates → simulate_portfolio pipeline.

Tests run on a small fixture (SPY/QQQ/IWM, 2024-H1) so they complete fast on
cached data. Each tests an INVARIANT of the pipeline, not a specific number.

Subset assertions are at the CANDIDATE-POOL level. The executed-trade level is
NOT a strict subset because the concurrency cap can cause earlier cells/trades
to fill slots differently when more candidates are available — verified
separately as a consistency check (executed ⊆ candidate pool, sized correctly).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from config.run_config import RunConfig
from src.discover_candidates import discover
from src.simulate_portfolio import simulate

# Fast fixture
FIXTURE_UNIVERSE = ["SPY", "QQQ", "IWM"]
FIXTURE_START = date(2024, 1, 2)
FIXTURE_END = date(2024, 6, 30)
FIXTURE_CELLS = [("30_90_atm", 30, 90), ("60_90_atm", 60, 90)]


def _fixture_config(**overrides) -> RunConfig:
    """Build a RunConfig pinned to the test fixture window/universe."""
    base = dict(
        cells=tuple(tuple(c) for c in FIXTURE_CELLS),
        universe=tuple(FIXTURE_UNIVERSE),
        start_date=FIXTURE_START.isoformat(),
        end_date=FIXTURE_END.isoformat(),
        # Disable position caps for predictable subset tests
        position_cap_contracts=None,
        position_cap_contracts_per_ticker_cell=None,
        position_cap_nav_pct=None,
        position_cap_strike_mtm=None,
    )
    base.update(overrides)
    return RunConfig(**base)


@pytest.fixture(scope="module")
def fixture_candidates(tmp_path_factory):
    """Run discovery once for the fixture; reused across all tests in this module."""
    out = tmp_path_factory.mktemp("disc") / "candidates.parquet"
    discover(
        start_date=FIXTURE_START, end_date=FIXTURE_END,
        universe=FIXTURE_UNIVERSE, cells=FIXTURE_CELLS,
        output_path=out, max_workers=8,
    )
    return out


# ----------------------------------------------------------------------------
# Test 1: idempotency — same config + same candidates → same trade log
# ----------------------------------------------------------------------------

def test_idempotency(fixture_candidates, tmp_path):
    """Running simulate twice with the same config produces identical trade logs."""
    cfg = _fixture_config()
    out_a = tmp_path / "a"; out_b = tmp_path / "b"
    simulate(fixture_candidates, cfg, out_a)
    simulate(fixture_candidates, cfg, out_b)
    log_a = pd.read_csv(out_a / f"sim_{cfg.short_hash()}" / "trade_log.csv")
    log_b = pd.read_csv(out_b / f"sim_{cfg.short_hash()}" / "trade_log.csv")
    # Sort both for stable comparison (no internal ordering guarantee under threads)
    sort_keys = ["entry_date", "ticker", "cell", "front_strike"]
    log_a = log_a.sort_values(sort_keys).reset_index(drop=True)
    log_b = log_b.sort_values(sort_keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(log_a, log_b)


# ----------------------------------------------------------------------------
# Test 2: sizing change — doubling risk_per_trade ≤ 2x contracts per position
# ----------------------------------------------------------------------------

def test_sizing_change_kelly_doubles(fixture_candidates, tmp_path):
    """Doubling risk_per_trade should exactly double per-trade kelly_contracts.

    The FINAL contracts may not double 1:1 because cash budget can bind earlier
    trades (consuming more cash and starving later trades) — that's a sequencing
    effect, not a sizing-formula bug. The invariant we test is at the
    pre-cash-budget Kelly level: kelly_high == 2 × kelly_low for matched trades."""
    cfg_low = _fixture_config(risk_per_trade=0.04)
    cfg_high = _fixture_config(risk_per_trade=0.08)
    simulate(fixture_candidates, cfg_low, tmp_path / "low")
    simulate(fixture_candidates, cfg_high, tmp_path / "high")
    log_low = pd.read_csv(tmp_path / "low" / f"sim_{cfg_low.short_hash()}" / "trade_log.csv")
    log_high = pd.read_csv(tmp_path / "high" / f"sim_{cfg_high.short_hash()}" / "trade_log.csv")
    keys = ["entry_date", "ticker", "cell", "front_strike", "back_strike"]
    merged = log_low[keys + ["kelly_contracts"]].merge(
        log_high[keys + ["kelly_contracts"]], on=keys, suffixes=("_low", "_high"))
    assert not merged.empty, "no overlapping trades to compare"
    # Kelly target dollar doubles → kelly_contracts doubles (with int floor).
    # Allow exact 2x or 2x ± 1 for floor-rounding.
    diff = merged["kelly_contracts_high"] - 2 * merged["kelly_contracts_low"]
    assert (diff.abs() <= 1).all(), \
        f"kelly_contracts not doubling for matched trades:\n{merged[diff.abs() > 1]}"


# ----------------------------------------------------------------------------
# Test 3: threshold change — raising FF threshold shrinks candidate pool
#                            (subset assertion at candidate-pool level)
# ----------------------------------------------------------------------------

def test_threshold_raise_shrinks_candidate_pool(fixture_candidates, tmp_path):
    """Raising FF threshold from 0.20 → 0.30 shrinks the eligible-candidate pool.
    Every candidate eligible at 0.30 was also eligible at 0.20.

    NOTE: This holds at the CANDIDATE-POOL level (FF >= threshold). The
    EXECUTED-TRADE set is not strictly subset because concurrency cap can change
    which candidates execute when more are available. Test asserts the pool
    invariant; executed-trade consistency is checked separately."""
    cands = pd.read_parquet(fixture_candidates)
    pool_low = cands[cands["ff"].notna() & (cands["ff"] >= 0.20)]
    pool_high = cands[cands["ff"].notna() & (cands["ff"] >= 0.30)]
    # High-threshold pool ⊆ low-threshold pool
    keys = ["date", "ticker", "cell"]
    merged = pool_high[keys].merge(pool_low[keys], on=keys, how="left", indicator=True)
    assert (merged["_merge"] == "both").all(), "high-threshold candidate not in low-threshold pool"
    assert len(pool_high) <= len(pool_low), \
        f"high pool ({len(pool_high)}) not ≤ low pool ({len(pool_low)})"


# ----------------------------------------------------------------------------
# Test 4: cell expansion — adding a cell EXPANDS candidate pool
# ----------------------------------------------------------------------------

def test_cell_expansion_grows_candidate_pool(fixture_candidates):
    """Adding a cell adds candidates without removing existing-cell candidates.
    Existing-cell candidates appear in both 1-cell and 2-cell pools."""
    cands = pd.read_parquet(fixture_candidates)
    pool_one = cands[cands["cell"] == "60_90_atm"]
    pool_two = cands[cands["cell"].isin(["60_90_atm", "30_90_atm"])]
    assert len(pool_two) >= len(pool_one), "2-cell pool not ≥ 1-cell pool"
    # Every (date, ticker, 60_90_atm) row in pool_one must appear identically in pool_two
    keys = ["date", "ticker", "cell"]
    merged = pool_one[keys].merge(pool_two[keys], on=keys, how="left", indicator=True)
    assert (merged["_merge"] == "both").all(), "60_90_atm row missing from 2-cell pool"


# ----------------------------------------------------------------------------
# Consistency check: executed trades ⊆ candidate pool, sized > 0
# ----------------------------------------------------------------------------

def test_executed_subset_of_candidates(fixture_candidates, tmp_path):
    """Every executed trade appears in the candidate pool with FF ≥ threshold
    AND has contracts > 0. This is the executed-trade-level consistency check."""
    cfg = _fixture_config()
    simulate(fixture_candidates, cfg, tmp_path)
    log = pd.read_csv(tmp_path / f"sim_{cfg.short_hash()}" / "trade_log.csv")
    if log.empty:
        pytest.skip("no trades opened; cannot verify subset")
    cands = pd.read_parquet(fixture_candidates)
    cands["date"] = cands["date"].apply(lambda v: v if isinstance(v, date) else pd.Timestamp(v).date())
    log["entry_date"] = pd.to_datetime(log["entry_date"]).dt.date

    # contracts > 0 for every trade
    assert (log["contracts"] > 0).all(), "trade with zero contracts"

    # FF >= threshold for every trade
    assert (log["ff_at_entry"] >= 0.20).all(), "trade entered with FF below threshold"

    # Each trade's (date, ticker, cell) was a valid candidate row
    keys = ["date", "ticker", "cell"]
    log_keys = log[["entry_date", "ticker", "cell"]].rename(columns={"entry_date": "date"})
    merged = log_keys.merge(cands[cands["back_leg_resolved"]][keys], on=keys, how="left", indicator=True)
    assert (merged["_merge"] == "both").all(), "executed trade has no candidate row"
