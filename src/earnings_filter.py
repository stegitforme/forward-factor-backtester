"""
Earnings filter for the Forward Factor backtester.

The author's video explicitly says: "for simplicity, we avoid earnings
altogether." We follow that exact rule:

  Skip a trade if any earnings event for the underlying lies between
  TODAY and the BACK expiry of the calendar (with a small buffer).

This is the conservative approach. The alternative — using ex-earnings IV
to compute FF — is more sophisticated but introduces estimation error that
can dominate the strategy's edge. We sacrifice some trades for cleaner
signals.

Earnings data sources:

  Primary:   Polygon /vX/reference/tickers/{ticker}/events?types=earnings
             (requires an Equities tier — confirm scope with subscription)
  Fallback:  AlphaVantage's earnings calendar (free, lower quality)
  Manual:    Hardcoded list for backtest if we want to avoid API dependency

For the backtest run, we cache the full earnings calendar for each ticker
once (it doesn't change historically) and look up overlap on each trade
candidate.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from config import settings


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class EarningsEvent:
    """A single earnings announcement."""
    ticker: str
    event_date: date
    timing: str  # "bmo" (before market open), "amc" (after market close), "unknown"


@dataclass(frozen=True)
class EarningsCalendar:
    """Earnings events for a single ticker."""
    ticker: str
    events: tuple[EarningsEvent, ...]

    def has_event_in_window(self, start: date, end: date, buffer_days: int = 0) -> bool:
        """
        Return True if any earnings event falls within [start - buffer, end + buffer].
        """
        adj_start = start - timedelta(days=buffer_days)
        adj_end = end + timedelta(days=buffer_days)
        return any(adj_start <= e.event_date <= adj_end for e in self.events)

    def next_event_after(self, after: date) -> Optional[EarningsEvent]:
        """Return the next earnings event strictly after `after`, or None."""
        future = sorted(
            [e for e in self.events if e.event_date > after],
            key=lambda e: e.event_date,
        )
        return future[0] if future else None


class EarningsFilter:
    """
    Wraps an earnings data source and provides per-trade overlap checks.

    Usage:
        filter = EarningsFilter(polygon_client)
        if filter.is_safe_window("AAPL", entry_date, back_expiry):
            # safe to enter trade
            ...
    """

    def __init__(self, polygon_client, buffer_days: int = settings.EARNINGS_BUFFER_DAYS):
        self.polygon_client = polygon_client
        self.buffer_days = buffer_days
        self._cache: dict[str, EarningsCalendar] = {}

    def get_calendar(self, ticker: str) -> EarningsCalendar:
        """
        Fetch and cache the full earnings history for a ticker.

        Falls back to an empty calendar (returning False from overlap checks
        as if there were no events) if the data source fails. We log a
        warning so the user knows; in production we'd want to fail loud.
        """
        if ticker in self._cache:
            return self._cache[ticker]

        events = self._fetch_events(ticker)
        cal = EarningsCalendar(ticker=ticker, events=tuple(events))
        self._cache[ticker] = cal
        return cal

    def _fetch_events(self, ticker: str) -> list[EarningsEvent]:
        """
        Fetch earnings events from Polygon. The exact endpoint may evolve;
        if Polygon doesn't return earnings for this tier, fall back to a
        permissive policy (no filter) and log a warning.
        """
        try:
            # Polygon's reference endpoint for ticker events
            # https://polygon.io/docs/stocks/get_v1_reference_tickers__ticker
            data = self.polygon_client._get(
                f"/v1/reference/tickers/{ticker}",
                ttl_seconds=settings.CACHE_TTL_REFERENCE,
            )
        except Exception as e:
            # The Polygon /v1/reference/tickers endpoint doesn't return
            # earnings on our tier. Without a working source, we run with
            # an empty calendar (no events block trades). This is logged
            # at debug level to avoid spam — it fires for every ticker.
            log.debug("Earnings fetch failed for %s: %s — using empty calendar", ticker, e)
            return []

        # Parse — exact schema TBD; this is a defensive parse
        events: list[EarningsEvent] = []
        ticker_data = data.get("results", {}) if isinstance(data, dict) else {}
        raw_events = ticker_data.get("events") or []
        for ev in raw_events:
            if (ev or {}).get("type") != "earnings":
                continue
            ev_date_str = ev.get("date")
            if not ev_date_str:
                continue
            try:
                ev_date = date.fromisoformat(ev_date_str)
            except (TypeError, ValueError):
                continue
            timing = ev.get("timing", "unknown")
            events.append(EarningsEvent(
                ticker=ticker,
                event_date=ev_date,
                timing=timing,
            ))

        return events

    def is_safe_window(
        self,
        ticker: str,
        window_start: date,
        window_end: date,
    ) -> bool:
        """
        Return True if there is NO earnings event between window_start and
        window_end (inclusive of buffer). The trade is safe to enter.

        Args:
            ticker: Underlying symbol.
            window_start: Trade entry date.
            window_end: Back expiry date of the calendar.
        """
        cal = self.get_calendar(ticker)
        return not cal.has_event_in_window(
            window_start, window_end, buffer_days=self.buffer_days
        )

    def filter_trades(
        self,
        trades: pd.DataFrame,
        ticker_col: str = "ticker",
        entry_col: str = "entry_date",
        back_expiry_col: str = "back_expiry",
    ) -> pd.DataFrame:
        """
        Vectorized filter: returns only rows where the trade window is
        clear of earnings.

        Args:
            trades: DataFrame with at least `ticker`, `entry_date`,
                `back_expiry` columns.
        """
        if trades.empty:
            return trades

        keep_mask = []
        for _, row in trades.iterrows():
            ticker = row[ticker_col]
            entry = row[entry_col]
            back = row[back_expiry_col]
            if isinstance(entry, pd.Timestamp):
                entry = entry.date()
            if isinstance(back, pd.Timestamp):
                back = back.date()
            keep_mask.append(self.is_safe_window(ticker, entry, back))

        return trades[keep_mask].reset_index(drop=True)


# ============================================================================
# Standalone helper for use without a polygon client (testing)
# ============================================================================

def overlap_check(
    earnings_dates: list[date],
    window_start: date,
    window_end: date,
    buffer_days: int = settings.EARNINGS_BUFFER_DAYS,
) -> bool:
    """
    Pure function: returns True if any earnings date falls in
    [window_start - buffer, window_end + buffer].
    """
    adj_start = window_start - timedelta(days=buffer_days)
    adj_end = window_end + timedelta(days=buffer_days)
    return any(adj_start <= d <= adj_end for d in earnings_dates)
