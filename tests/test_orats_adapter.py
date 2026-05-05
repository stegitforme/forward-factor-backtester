"""ORATS adapter tests.

These tests touch real ORATS files on /Users/sggmpb13/trading/. They are
gated by environment: if the data root or representative dates aren't present,
tests skip rather than fail.

Cache-related tests use a module-scoped tmp dir + a stubbed mini-cache
(2 days of one ticker, written directly) to avoid triggering full year-cache
builds (~6 min each) in unit-test runtime.

The one full-year-cache build test is marked `@pytest.mark.slow` and skipped
unless `RUN_SLOW_TESTS=1` is set.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.adapters import orats_adapter as orats


# ============================================================================
# Fixtures + helpers
# ============================================================================

REPRESENTATIVE_DAY = date(2024, 10, 29)  # MSTR earnings AMC tomorrow; AAPL 2 days
LEHMAN_DAY = date(2008, 9, 15)


def _data_present(d: date) -> bool:
    return orats.zip_path_for_date(d).exists()


pytestmark = pytest.mark.skipif(
    not _data_present(REPRESENTATIVE_DAY),
    reason=f"ORATS data root not present at {orats.ORATS_ROOT}",
)


@pytest.fixture(scope="module")
def isolated_cache():
    """One tmp cache dir shared across all tests in this module."""
    tmp = Path(tempfile.mkdtemp(prefix="orats_test_cache_"))
    orig = orats.CACHE_ROOT
    orats.CACHE_ROOT = tmp
    yield tmp
    orats.CACHE_ROOT = orig
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="module")
def mini_cache(isolated_cache):
    """Pre-seed a tiny SPY-2024 cache (2 trading days) via direct parquet write.

    Bypasses _build_year_cache (which would read all 252 ZIPs ~6 min). Tests
    that need the cache code path use this — they still exercise read-from-cache
    behavior, just not the full-year build.
    """
    days = [date(2024, 10, 28), date(2024, 10, 29)]
    chunks = []
    for d in days:
        zp = orats.zip_path_for_date(d)
        if not zp.exists():
            continue
        df = pd.read_csv(zp, compression="zip", usecols=orats.KEEP_COLUMNS)
        df = df[df["ticker"] == "SPY"]
        chunks.append(df)
    full = pd.concat(chunks, ignore_index=True)
    full["trade_date"] = pd.to_datetime(full["trade_date"]).dt.date
    full["expirDate"] = pd.to_datetime(full["expirDate"]).dt.date
    cp = orats.cache_path_for("SPY", 2024)
    cp.parent.mkdir(parents=True, exist_ok=True)
    full.to_parquet(cp, index=False)
    return cp


# ============================================================================
# Path / presence helpers (no I/O)
# ============================================================================

def test_zip_path_for_date_format():
    p = orats.zip_path_for_date(date(2024, 10, 29))
    assert p.name == "ORATS_SMV_Strikes_20241029.zip"
    assert p.parent.name == "2024"


def test_has_data_for_known_day():
    assert orats.has_data_for(REPRESENTATIVE_DAY)


def test_has_data_for_far_future():
    assert not orats.has_data_for(date(2099, 1, 1))


def test_cache_path_for_uppercases_ticker():
    p = orats.cache_path_for("spy", 2024)
    assert p.parent.name == "SPY"
    assert p.name == "2024.parquet"


# ============================================================================
# Raw day loads (one ZIP read each)
# ============================================================================

def test_load_orats_day_raw_returns_full_chain():
    df = orats.load_orats_day_raw(REPRESENTATIVE_DAY)
    assert not df.empty
    assert df["ticker"].nunique() > 1000
    assert len(df) > 100_000
    for col in ["ticker", "strike", "stkPx", "smoothSmvVol", "extVol",
                "trade_date", "expirDate"]:
        assert col in df.columns
    assert isinstance(df["trade_date"].iloc[0], date)
    assert isinstance(df["expirDate"].iloc[0], date)


def test_load_orats_day_raw_missing_returns_empty():
    df = orats.load_orats_day_raw(date(2099, 1, 1))
    assert df.empty
    for col in orats.KEEP_COLUMNS:
        assert col in df.columns


# ============================================================================
# Cache read path (uses pre-seeded mini cache; no year build)
# ============================================================================

def test_load_orats_day_filtered_reads_from_cache(isolated_cache, mini_cache):
    df = orats.load_orats_day_filtered(REPRESENTATIVE_DAY, ["SPY"])
    assert not df.empty
    assert set(df["ticker"].unique()) == {"SPY"}
    assert df["trade_date"].iloc[0] == REPRESENTATIVE_DAY


def test_load_orats_day_filtered_round_trip_consistent(isolated_cache, mini_cache):
    df1 = orats.load_orats_day_filtered(REPRESENTATIVE_DAY, ["SPY"])
    df2 = orats.load_orats_day_filtered(REPRESENTATIVE_DAY, ["SPY"])
    pd.testing.assert_frame_equal(
        df1.sort_values(["expirDate", "strike"]).reset_index(drop=True),
        df2.sort_values(["expirDate", "strike"]).reset_index(drop=True),
    )


def test_load_orats_range_uses_cache(isolated_cache, mini_cache):
    df = orats.load_orats_range(date(2024, 10, 28), date(2024, 10, 29), ["SPY"])
    assert not df.empty
    assert df["trade_date"].nunique() == 2
    assert set(df["ticker"].unique()) == {"SPY"}


def test_load_orats_range_empty_window(isolated_cache):
    df = orats.load_orats_range(date(2024, 10, 30), date(2024, 10, 28), ["SPY"])
    assert df.empty


# ============================================================================
# ATM finder helper
# ============================================================================

def test_find_atm_for_dte_picks_closest_expiry_and_strike(isolated_cache, mini_cache):
    df = orats.load_orats_day_filtered(REPRESENTATIVE_DAY, ["SPY"])
    row = orats.find_atm_for_dte(df, "SPY", target_dte=30, buffer_days=5)
    assert row is not None
    dte = (pd.Timestamp(row["expirDate"]) - pd.Timestamp(row["trade_date"])).days
    assert 25 <= dte <= 35
    assert abs(row["strike"] - row["stkPx"]) < 5.0


def test_find_atm_for_dte_returns_none_outside_buffer(isolated_cache, mini_cache):
    df = orats.load_orats_day_filtered(REPRESENTATIVE_DAY, ["SPY"])
    row = orats.find_atm_for_dte(df, "SPY", target_dte=5000, buffer_days=5)
    assert row is None


def test_find_atm_for_dte_returns_none_for_missing_ticker(isolated_cache, mini_cache):
    df = orats.load_orats_day_filtered(REPRESENTATIVE_DAY, ["SPY"])
    row = orats.find_atm_for_dte(df, "NOPE", target_dte=30, buffer_days=5)
    assert row is None


# ============================================================================
# Slow integration tests (full year-cache build) — gated by env var
# ============================================================================

slow = pytest.mark.skipif(
    os.environ.get("RUN_SLOW_TESTS") != "1",
    reason="set RUN_SLOW_TESTS=1 to enable slow integration tests",
)


@slow
def test_full_year_cache_build_2009_slv(isolated_cache):
    """SLV first appears 2009-01-02; full 2009 cache should have ~full coverage."""
    df = orats._build_year_cache("SLV", 2009)
    assert not df.empty
    assert df["trade_date"].nunique() > 240  # ~252 trading days in 2009
    assert set(df["ticker"].unique()) == {"SLV"}


@slow
def test_full_year_cache_build_2008_slv_empty(isolated_cache):
    """SLV missing from ORATS 2008 — cache build must produce empty frame."""
    df = orats._build_year_cache("SLV", 2008)
    assert df.empty
