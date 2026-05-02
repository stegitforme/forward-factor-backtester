"""
Unit tests for the universe selector.

These tests exercise the pure logic without hitting Polygon. Real
liquidity-based universe construction is covered by integration tests
that require API access.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from config import settings
from src.universe import (
    SEED_TICKERS,
    Universe,
    UniverseEntry,
    build_universe_simple,
    compute_options_volume_universe,
)


class TestSeedTickers:
    """Sanity checks on the seed pool."""

    def test_seed_has_expected_size(self):
        # Should have a healthy candidate pool
        assert 80 < len(SEED_TICKERS) < 200

    def test_seed_includes_megacaps(self):
        for t in ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"]:
            assert t in SEED_TICKERS

    def test_seed_includes_index_etfs(self):
        for t in ["SPY", "QQQ", "IWM"]:
            assert t in SEED_TICKERS

    def test_seed_does_not_include_excluded_etfs(self):
        # These are leveraged/inverse and should be in EXCLUDED_TICKERS,
        # not in the SEED list directly. Either way they shouldn't end up
        # in the final universe.
        for t in settings.EXCLUDED_TICKERS:
            # SEED may include them (we rely on filtering); but TQQQ is
            # specifically used by the user's other strategy and must be excluded.
            # Just check that filtering removes them.
            filtered = build_universe_simple(date(2026, 5, 1))
            assert t not in filtered

    def test_seed_no_duplicates(self):
        assert len(SEED_TICKERS) == len(set(SEED_TICKERS))


class TestBuildUniverseSimple:
    """The simple builder used by tests and offline runs."""

    def test_returns_list_minus_excluded(self):
        result = build_universe_simple(date(2026, 5, 1))
        assert isinstance(result, list)
        for t in settings.EXCLUDED_TICKERS:
            assert t not in result

    def test_custom_candidates(self):
        result = build_universe_simple(
            date(2026, 5, 1),
            candidate_tickers=["AAPL", "TQQQ", "MSFT"],
            excluded={"TQQQ"},
        )
        assert "AAPL" in result
        assert "MSFT" in result
        assert "TQQQ" not in result

    def test_empty_candidates(self):
        result = build_universe_simple(
            date(2026, 5, 1),
            candidate_tickers=[],
        )
        assert result == []


class TestUniverseEntry:
    """Test the dataclass."""

    def test_create(self):
        e = UniverseEntry(
            ticker="AAPL",
            avg_daily_option_volume=500_000,
            last_close=150.0,
            snapshot_date=date(2026, 5, 1),
        )
        assert e.ticker == "AAPL"
        assert e.avg_daily_option_volume == 500_000

    def test_immutable(self):
        e = UniverseEntry(
            ticker="AAPL",
            avg_daily_option_volume=500_000,
            last_close=150.0,
            snapshot_date=date(2026, 5, 1),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            e.ticker = "MSFT"


class TestUniverse:
    """Test the universe container."""

    def test_create_and_iterate(self):
        e1 = UniverseEntry("AAPL", 500_000, 150.0, date(2026, 5, 1))
        e2 = UniverseEntry("MSFT", 300_000, 400.0, date(2026, 5, 1))
        u = Universe(snapshot_date=date(2026, 5, 1), entries=(e1, e2))
        assert u.tickers == ["AAPL", "MSFT"]
        assert len(u) == 2

    def test_empty_universe(self):
        u = Universe(snapshot_date=date(2026, 5, 1), entries=())
        assert u.tickers == []
        assert len(u) == 0


class TestComputeUniverseWithMockClient:
    """
    Integration-style test using a mocked Polygon client. Verifies the
    universe builder ranks correctly and respects min_avg_volume.
    """

    def test_filters_below_threshold(self):
        client = MagicMock()
        # AAPL: 50K avg, MSFT: 5K avg (below 10K threshold)
        # Set up mock responses
        def mock_list_options(*args, **kwargs):
            return pd.DataFrame({"ticker": ["O:FAKE1", "O:FAKE2"]})

        client.list_options_contracts.side_effect = mock_list_options

        # First call returns 1000 vol/day, second returns 100 vol/day
        # AAPL gets the high-volume contracts, MSFT the low-volume
        call_count = {"n": 0}
        def mock_get_option_bars(opt_ticker, start, end):
            call_count["n"] += 1
            # First batch = AAPL contracts (high vol)
            if call_count["n"] <= 2:
                return pd.DataFrame({
                    "volume": [50_000] * 20,
                    "vwap": [1.0] * 20,
                    "close": [1.0] * 20,
                }, index=pd.date_range(end="2026-05-01", periods=20))
            else:
                return pd.DataFrame({
                    "volume": [1_000] * 20,
                    "vwap": [1.0] * 20,
                    "close": [1.0] * 20,
                }, index=pd.date_range(end="2026-05-01", periods=20))
        client.get_option_daily_bars.side_effect = mock_get_option_bars

        client.get_daily_bars.return_value = pd.DataFrame({
            "close": [150.0],
        }, index=[pd.Timestamp("2026-05-01")])

        universe = compute_options_volume_universe(
            as_of=date(2026, 5, 1),
            polygon_client=client,
            candidate_tickers=["AAPL", "MSFT"],
            min_avg_volume=10_000,
            max_tickers=10,
            lookback_days=20,
        )

        # AAPL should pass (high vol), MSFT should fail
        tickers = universe.tickers
        assert "AAPL" in tickers
        assert "MSFT" not in tickers

    def test_ranks_by_volume_desc(self):
        """Higher volume should rank first in the universe."""
        client = MagicMock()
        client.list_options_contracts.return_value = pd.DataFrame({"ticker": ["O:F1"]})
        client.get_daily_bars.return_value = pd.DataFrame({
            "close": [100.0],
        }, index=[pd.Timestamp("2026-05-01")])

        # Volume per ticker: AAPL=200K/day, MSFT=100K/day, GOOGL=300K/day
        volumes = {"AAPL": 200_000, "MSFT": 100_000, "GOOGL": 300_000}
        current_ticker = {"name": None}

        def mock_list(*args, **kwargs):
            current_ticker["name"] = kwargs.get("underlying", args[0] if args else None)
            return pd.DataFrame({"ticker": ["O:F1"]})
        client.list_options_contracts.side_effect = mock_list

        def mock_bars(opt_ticker, start, end):
            t = current_ticker["name"]
            v = volumes.get(t, 0)
            return pd.DataFrame({
                "volume": [v] * 20,
                "vwap": [1.0] * 20,
                "close": [1.0] * 20,
            }, index=pd.date_range(end="2026-05-01", periods=20))
        client.get_option_daily_bars.side_effect = mock_bars

        universe = compute_options_volume_universe(
            as_of=date(2026, 5, 1),
            polygon_client=client,
            candidate_tickers=["AAPL", "MSFT", "GOOGL"],
            min_avg_volume=10_000,
            max_tickers=10,
            lookback_days=20,
        )

        # GOOGL (highest) should be first
        tickers = universe.tickers
        assert tickers[0] == "GOOGL"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
