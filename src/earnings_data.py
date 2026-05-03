"""Hardcoded earnings calendar for the backtest universe.

VV's calculator.py does NOT handle earnings (verified 2026-05-02 via inspection
of the distributed script). The OQuants product structure (separate Ex-Earnings
IV and Forward Volatility calculators) confirms VV expects users to clean IV
inputs manually before computing FF. We implement the simpler "skip if earnings
in window" path (Option B) here, which is faithful to VV's free-script practice.

ETFs (SPY, QQQ, SMH, XBI, etc.) have no earnings — they're index funds.
Single-stock components do, and their earnings vol contaminates FF readings.

DATE QUALITY:
  - MSTR Q3 2024 (2024-10-30) is verified from the Oct 2024 drill data.
  - All other dates are approximate — based on typical quarterly cadence
    of each company. EXACT DATES MUST BE VERIFIED before any production
    allocation; the 4-day EARNINGS_BUFFER_DAYS in settings provides some
    forgiveness but not unlimited.
  - When Polygon publishes earnings on our tier, OR when AlphaVantage's
    free earnings calendar is wired up, this static file should be
    superseded by live data.

To use: EarningsFilter._fetch_events looks up here before falling back to
Polygon (which currently returns nothing on our tier).
"""
from __future__ import annotations

from datetime import date


# ETFs have no earnings — explicit empty lists make this intentional, not
# accidental. If a ticker is missing entirely, _fetch_events falls back to
# Polygon and may return [] silently — explicit is better.
ETF_TICKERS_NO_EARNINGS: set[str] = {
    "SPY", "QQQ", "IWM", "DIA", "SMH", "XBI", "KWEB", "TLT", "GLD", "SLV",
    "XLF", "XLE", "XLK", "XLY", "XLV", "XLP", "XLU", "XLB", "XLI",
    "KRE", "KBE", "IBB", "ARKK", "TQQQ", "SQQQ", "SOXL", "SOXS",
    "UVXY", "VXX", "SVXY", "BIL", "SGOV",
}


# Earnings dates for single-stock names in our universe. Approximate where
# noted — based on typical quarterly cadence. Q3 2024 MSTR is verified from
# the Oct 2024 drill output.
SINGLE_STOCK_EARNINGS: dict[str, list[date]] = {
    "MSTR": [
        # 2022
        date(2022, 2, 1), date(2022, 5, 3), date(2022, 8, 2), date(2022, 11, 1),
        # 2023
        date(2023, 2, 2), date(2023, 5, 1), date(2023, 8, 1), date(2023, 11, 1),
        # 2024 (Q3 verified from drill data: 2024-10-30)
        date(2024, 2, 15), date(2024, 4, 29), date(2024, 8, 1), date(2024, 10, 30),
        # 2025
        date(2025, 2, 5), date(2025, 5, 1), date(2025, 7, 31), date(2025, 10, 30),
        # 2026
        date(2026, 2, 5), date(2026, 5, 4),
    ],
    "META": [
        # Roughly: late Jan / late Apr / late Jul / late Oct
        date(2022, 2, 2), date(2022, 4, 27), date(2022, 7, 27), date(2022, 10, 26),
        date(2023, 2, 1), date(2023, 4, 26), date(2023, 7, 26), date(2023, 10, 25),
        date(2024, 1, 31), date(2024, 4, 24), date(2024, 7, 31), date(2024, 10, 30),
        date(2025, 1, 29), date(2025, 4, 30), date(2025, 7, 30), date(2025, 10, 29),
        date(2026, 1, 28), date(2026, 4, 29),
    ],
    "NVDA": [
        # NVDA fiscal year is offset — reports late Feb / late May / late Aug / late Nov
        date(2022, 2, 16), date(2022, 5, 25), date(2022, 8, 24), date(2022, 11, 16),
        date(2023, 2, 22), date(2023, 5, 24), date(2023, 8, 23), date(2023, 11, 21),
        date(2024, 2, 21), date(2024, 5, 22), date(2024, 8, 28), date(2024, 11, 20),
        date(2025, 2, 26), date(2025, 5, 28), date(2025, 8, 27), date(2025, 11, 19),
        date(2026, 2, 25), date(2026, 5, 27),
    ],
    "TSLA": [
        # Late Jan / late Apr / late Jul / late Oct
        date(2022, 1, 26), date(2022, 4, 20), date(2022, 7, 20), date(2022, 10, 19),
        date(2023, 1, 25), date(2023, 4, 19), date(2023, 7, 19), date(2023, 10, 18),
        date(2024, 1, 24), date(2024, 4, 23), date(2024, 7, 23), date(2024, 10, 23),
        date(2025, 1, 29), date(2025, 4, 22), date(2025, 7, 23), date(2025, 10, 22),
        date(2026, 1, 28), date(2026, 4, 22),
    ],
    "AMD": [
        # Late Jan / early May / early Aug / early Nov
        date(2022, 2, 1), date(2022, 5, 3), date(2022, 8, 2), date(2022, 11, 1),
        date(2023, 1, 31), date(2023, 5, 2), date(2023, 8, 1), date(2023, 10, 31),
        date(2024, 1, 30), date(2024, 4, 30), date(2024, 7, 30), date(2024, 10, 29),
        date(2025, 2, 4), date(2025, 5, 6), date(2025, 8, 5), date(2025, 11, 4),
        date(2026, 2, 3), date(2026, 5, 5),
    ],
    "COIN": [
        # Early Feb / early May / early Aug / early Nov
        date(2022, 2, 24), date(2022, 5, 10), date(2022, 8, 9), date(2022, 11, 3),
        date(2023, 2, 21), date(2023, 5, 4), date(2023, 8, 3), date(2023, 11, 2),
        date(2024, 2, 15), date(2024, 5, 2), date(2024, 8, 1), date(2024, 10, 31),
        date(2025, 2, 13), date(2025, 5, 8), date(2025, 8, 7), date(2025, 11, 6),
        date(2026, 2, 12), date(2026, 5, 7),
    ],
    "AAPL": [
        # Late Jan / early May / early Aug / late Oct - early Nov
        date(2022, 1, 27), date(2022, 4, 28), date(2022, 7, 28), date(2022, 10, 27),
        date(2023, 2, 2), date(2023, 5, 4), date(2023, 8, 3), date(2023, 11, 2),
        date(2024, 2, 1), date(2024, 5, 2), date(2024, 8, 1), date(2024, 10, 31),
        date(2025, 1, 30), date(2025, 5, 1), date(2025, 7, 31), date(2025, 10, 30),
        date(2026, 1, 29), date(2026, 4, 30),
    ],
    "SCHW": [
        # Mid Jan / mid Apr / mid Jul / mid Oct
        date(2022, 1, 18), date(2022, 4, 18), date(2022, 7, 18), date(2022, 10, 17),
        date(2023, 1, 18), date(2023, 4, 17), date(2023, 7, 18), date(2023, 10, 16),
        date(2024, 1, 17), date(2024, 4, 15), date(2024, 7, 16), date(2024, 10, 15),
        date(2025, 1, 21), date(2025, 4, 17), date(2025, 7, 18), date(2025, 10, 20),
        date(2026, 1, 20), date(2026, 4, 16),
    ],
    "GOOGL": [
        # Late Jan / late Apr / late Jul / late Oct
        date(2022, 2, 1), date(2022, 4, 26), date(2022, 7, 26), date(2022, 10, 25),
        date(2023, 1, 31), date(2023, 4, 25), date(2023, 7, 25), date(2023, 10, 24),
        date(2024, 1, 30), date(2024, 4, 25), date(2024, 7, 23), date(2024, 10, 29),
        date(2025, 2, 4), date(2025, 4, 29), date(2025, 7, 29), date(2025, 10, 28),
        date(2026, 2, 3), date(2026, 4, 28),
    ],
    "JPM": [
        # Mid Jan / mid Apr / mid Jul / mid Oct (typically BMO Friday)
        date(2022, 1, 14), date(2022, 4, 13), date(2022, 7, 14), date(2022, 10, 14),
        date(2023, 1, 13), date(2023, 4, 14), date(2023, 7, 14), date(2023, 10, 13),
        date(2024, 1, 12), date(2024, 4, 12), date(2024, 7, 12), date(2024, 10, 11),
        date(2025, 1, 15), date(2025, 4, 11), date(2025, 7, 15), date(2025, 10, 14),
        date(2026, 1, 14), date(2026, 4, 14),
    ],
}


def get_earnings_dates(ticker: str) -> list[date] | None:
    """Return earnings dates for a ticker, or None if we have no data.

    None vs []: None means "we don't know" (caller may want to fail loud
    or fall back to a different source). [] means "we explicitly know
    there are no earnings" (e.g. ETFs).
    """
    if ticker in ETF_TICKERS_NO_EARNINGS:
        return []
    return SINGLE_STOCK_EARNINGS.get(ticker)
