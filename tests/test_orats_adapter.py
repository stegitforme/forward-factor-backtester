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
# Polygon-symbol parser
# ============================================================================

def test_parse_polygon_symbol_call():
    out = orats._parse_polygon_option_symbol("O:SPY241129C00580000")
    assert out is not None
    underlying, expiry, opt_type, strike = out
    assert underlying == "SPY"
    assert expiry == date(2024, 11, 29)
    assert opt_type == "C"
    assert strike == 580.0


def test_parse_polygon_symbol_put_with_decimal_strike():
    out = orats._parse_polygon_option_symbol("O:KRE250515P00056500")
    assert out is not None
    _, _, opt_type, strike = out
    assert opt_type == "P"
    assert strike == 56.5


def test_parse_polygon_symbol_invalid_returns_none():
    assert orats._parse_polygon_option_symbol("not a symbol") is None
    assert orats._parse_polygon_option_symbol("O:") is None


# ============================================================================
# Mid quote helper
# ============================================================================

def test_orats_mid_uses_bid_ask_when_present():
    row = pd.Series({"cBidPx": 1.00, "cAskPx": 1.20, "cValue": 0.50})
    assert orats._orats_mid(row, "C") == pytest.approx(1.10)


def test_orats_mid_falls_back_to_value_when_quotes_missing():
    row = pd.Series({"cBidPx": 0.0, "cAskPx": 0.0, "cValue": 1.05})
    assert orats._orats_mid(row, "C") == pytest.approx(1.05)


def test_orats_mid_returns_none_when_all_missing():
    row = pd.Series({"cBidPx": None, "cAskPx": None, "cValue": None})
    assert orats._orats_mid(row, "C") is None


def test_orats_mid_put_side():
    row = pd.Series({"pBidPx": 2.00, "pAskPx": 2.10, "pValue": 1.00})
    assert orats._orats_mid(row, "P") == pytest.approx(2.05)


# ============================================================================
# OratsBarsClient — quacks like PolygonClient
# ============================================================================

def test_orats_bars_client_returns_bars_for_real_contract(isolated_cache, mini_cache):
    """Synthesize a bar lookup for a SPY call near 2024-10-29."""
    client = orats.OratsBarsClient()
    # Pick a strike + expiry we know exists from the mini-cache (read it directly)
    spy_oct29 = orats.load_orats_day_filtered(date(2024, 10, 29), ["SPY"])
    # Pick first call with positive bid
    sample = spy_oct29[(spy_oct29["cBidPx"] > 0)].iloc[0]
    expiry = sample["expirDate"]
    strike = float(sample["strike"])
    sym = f"O:SPY{expiry:%y%m%d}C{int(round(strike*1000)):08d}"
    bars = client.get_option_daily_bars(sym, date(2024, 10, 28), date(2024, 10, 30))
    assert not bars.empty
    assert "close" in bars.columns
    assert "vwap" in bars.columns
    assert all(bars["close"] > 0)


def test_orats_bars_client_invalid_symbol_returns_empty(isolated_cache):
    client = orats.OratsBarsClient()
    bars = client.get_option_daily_bars("garbage", date(2024, 10, 28), date(2024, 10, 30))
    assert bars.empty


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
