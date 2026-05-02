"""
Unit tests for the earnings filter.

Tests the pure overlap logic and the EarningsCalendar dataclass without
requiring Polygon access. The EarningsFilter class itself is tested
through its public interface using a mock polygon client.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.earnings_filter import (
    EarningsCalendar,
    EarningsEvent,
    EarningsFilter,
    overlap_check,
)


class TestOverlapCheck:
    """Pure function tests."""

    def test_event_before_window_no_overlap(self):
        """Earnings 5 days before window start, with 0 buffer -> no overlap."""
        events = [date(2026, 4, 25)]
        result = overlap_check(events, date(2026, 5, 1), date(2026, 6, 1), buffer_days=0)
        assert result is False

    def test_event_inside_window_overlap(self):
        events = [date(2026, 5, 15)]
        result = overlap_check(events, date(2026, 5, 1), date(2026, 6, 1), buffer_days=0)
        assert result is True

    def test_event_after_window_no_overlap(self):
        events = [date(2026, 6, 15)]
        result = overlap_check(events, date(2026, 5, 1), date(2026, 6, 1), buffer_days=0)
        assert result is False

    def test_event_at_start_with_buffer_overlap(self):
        """Event 3 days before window start, buffer 4 days -> overlap."""
        events = [date(2026, 4, 28)]
        result = overlap_check(events, date(2026, 5, 1), date(2026, 6, 1), buffer_days=4)
        assert result is True

    def test_event_far_before_with_buffer_no_overlap(self):
        events = [date(2026, 4, 20)]
        result = overlap_check(events, date(2026, 5, 1), date(2026, 6, 1), buffer_days=4)
        assert result is False

    def test_no_events(self):
        result = overlap_check([], date(2026, 5, 1), date(2026, 6, 1), buffer_days=0)
        assert result is False

    def test_multiple_events_one_overlaps(self):
        events = [date(2026, 4, 1), date(2026, 5, 15), date(2026, 7, 1)]
        result = overlap_check(events, date(2026, 5, 1), date(2026, 6, 1), buffer_days=0)
        assert result is True

    def test_event_exactly_at_boundary(self):
        events = [date(2026, 5, 1)]
        result = overlap_check(events, date(2026, 5, 1), date(2026, 6, 1), buffer_days=0)
        assert result is True

    def test_event_exactly_at_end_boundary(self):
        events = [date(2026, 6, 1)]
        result = overlap_check(events, date(2026, 5, 1), date(2026, 6, 1), buffer_days=0)
        assert result is True


class TestEarningsCalendar:
    """Test the EarningsCalendar dataclass."""

    def test_has_event_in_window(self):
        cal = EarningsCalendar(
            ticker="AAPL",
            events=(
                EarningsEvent("AAPL", date(2026, 5, 4), "amc"),
                EarningsEvent("AAPL", date(2026, 8, 1), "amc"),
            ),
        )
        assert cal.has_event_in_window(date(2026, 5, 1), date(2026, 6, 1)) is True
        assert cal.has_event_in_window(date(2026, 6, 2), date(2026, 7, 31)) is False

    def test_next_event_after(self):
        cal = EarningsCalendar(
            ticker="AAPL",
            events=(
                EarningsEvent("AAPL", date(2026, 5, 4), "amc"),
                EarningsEvent("AAPL", date(2026, 8, 1), "amc"),
                EarningsEvent("AAPL", date(2026, 11, 1), "amc"),
            ),
        )
        next_event = cal.next_event_after(date(2026, 6, 1))
        assert next_event is not None
        assert next_event.event_date == date(2026, 8, 1)

    def test_next_event_after_empty(self):
        cal = EarningsCalendar(ticker="AAPL", events=())
        assert cal.next_event_after(date(2026, 5, 1)) is None

    def test_next_event_after_all_past(self):
        cal = EarningsCalendar(
            ticker="AAPL",
            events=(EarningsEvent("AAPL", date(2026, 1, 1), "amc"),),
        )
        assert cal.next_event_after(date(2026, 5, 1)) is None


class TestEarningsFilter:
    """Test the filter class with a mock polygon client."""

    def _make_client_with_events(self, events_data):
        """events_data: list of {date, timing} dicts."""
        client = MagicMock()
        client._get.return_value = {
            "results": {
                "events": [
                    {"type": "earnings", "date": d["date"], "timing": d.get("timing", "amc")}
                    for d in events_data
                ]
            }
        }
        return client

    def test_safe_window_with_no_earnings(self):
        client = self._make_client_with_events([])
        f = EarningsFilter(client, buffer_days=4)
        assert f.is_safe_window("AAPL", date(2026, 5, 1), date(2026, 6, 1)) is True

    def test_unsafe_window_with_earnings_inside(self):
        client = self._make_client_with_events([{"date": "2026-05-15"}])
        f = EarningsFilter(client, buffer_days=4)
        assert f.is_safe_window("AAPL", date(2026, 5, 1), date(2026, 6, 1)) is False

    def test_safe_window_with_earnings_well_outside(self):
        client = self._make_client_with_events([{"date": "2026-09-01"}])
        f = EarningsFilter(client, buffer_days=4)
        assert f.is_safe_window("AAPL", date(2026, 5, 1), date(2026, 6, 1)) is True

    def test_buffer_catches_near_misses(self):
        # Earnings 3 days before window start, buffer = 4 days -> should catch
        client = self._make_client_with_events([{"date": "2026-04-28"}])
        f = EarningsFilter(client, buffer_days=4)
        assert f.is_safe_window("AAPL", date(2026, 5, 1), date(2026, 6, 1)) is False

    def test_calendar_is_cached(self):
        """Calendar fetched once, served from cache thereafter."""
        client = self._make_client_with_events([{"date": "2026-05-15"}])
        f = EarningsFilter(client, buffer_days=4)
        f.is_safe_window("AAPL", date(2026, 5, 1), date(2026, 6, 1))
        f.is_safe_window("AAPL", date(2026, 7, 1), date(2026, 8, 1))
        # Only one fetch should have happened (the second uses the cache)
        assert client._get.call_count == 1

    def test_empty_calendar_on_fetch_failure(self):
        """If polygon fetch fails, return empty calendar (no filtering)."""
        client = MagicMock()
        client._get.side_effect = Exception("API down")
        f = EarningsFilter(client, buffer_days=4)
        # Should not raise; should treat as safe (no events known)
        result = f.is_safe_window("AAPL", date(2026, 5, 1), date(2026, 6, 1))
        assert result is True

    def test_filter_trades_dataframe(self):
        """The filter_trades vectorized helper."""
        client = self._make_client_with_events([{"date": "2026-05-15"}])
        f = EarningsFilter(client, buffer_days=4)

        trades = pd.DataFrame({
            "ticker": ["AAPL", "AAPL", "AAPL"],
            "entry_date": [date(2026, 5, 1), date(2026, 6, 5), date(2026, 7, 1)],
            "back_expiry": [date(2026, 6, 1), date(2026, 7, 5), date(2026, 8, 1)],
        })
        result = f.filter_trades(trades)

        # First trade overlaps May 15 earnings -> filtered out
        # Second trade is after earnings + buffer -> kept
        # Third trade is well after -> kept
        assert len(result) == 2
        assert result.iloc[0]["entry_date"] == date(2026, 6, 5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
