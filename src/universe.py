"""
Universe selector for the Forward Factor backtester.

Picks the top-N most liquid optionable names by 20-day average daily option
volume. This mirrors the author's criterion ("> 10K avg daily option volume")
and reduces our universe to names where:

  1. The bid-ask spread on calendars is narrow enough that the strategy works
     net of slippage.
  2. There's enough capacity that 5% of daily volume can absorb our trade size.
  3. The IV term structure is informed by enough order flow to be meaningful
     (low-volume names have noisy IVs that distort FF readings).

Survivorship bias note: we pick the universe AS OF a given date, not based on
current liquidity. This means a name that was liquid in 2022 but is now thin
will still appear in our 2022 universe slice. This is the correct approach.

Universe membership is refreshed every UNIVERSE_REFRESH_DAYS (default 30) so
that names entering/leaving the liquid set are properly handled across the
backtest window. We don't refresh daily because the cost is high and the
membership is stable enough at monthly cadence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from config import settings


log = logging.getLogger(__name__)


# Seed list of names that have historically had >10K daily option volume.
# Pulled from CBOE's most-active list and OCC volume reports (Mar 2026).
# This is a starter set — universe_selector pulls actual volumes from Polygon
# to filter and rank, but we need a candidate pool to query against.
#
# We deliberately include some names that may have dropped off (e.g. some
# 2022 high-vol names) so the universe captures historical liquidity.
SEED_TICKERS: list[str] = [
    # Mega-cap tech
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA", "AVGO",
    "ORCL", "ADBE", "CRM", "INTC", "AMD", "QCOM", "CSCO", "NFLX", "PYPL",
    # AI / Semis
    "MU", "ARM", "PLTR", "SNDK", "MRVL", "TSM", "ASML", "AMAT", "LRCX",
    "KLAC", "SMCI", "VRT", "CLS", "ALAB", "NBIS", "OKLO", "IREN", "ASTS",
    "CRWV",
    # Major financials
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "V", "MA",
    "COIN", "HOOD", "SOFI",
    # Major consumer & industrial
    "WMT", "HD", "LOW", "TGT", "COST", "MCD", "SBUX", "NKE", "DIS", "BA",
    "GE", "CAT", "DE", "FDX", "UPS", "F", "GM",
    # Healthcare & pharma
    "JNJ", "PFE", "MRK", "UNH", "ABBV", "LLY", "BMY", "TMO", "ABT", "DHR",
    "MRNA", "NVO",
    # Energy
    "XOM", "CVX", "COP", "OXY", "SLB", "EOG", "MPC",
    # Major ETFs (high option volume) — note: leveraged/inverse excluded via EXCLUDED_TICKERS
    "SPY", "QQQ", "IWM", "DIA", "EEM", "GLD", "SLV", "USO", "TLT", "HYG",
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLRE", "XLB",
    "XBI", "SMH", "ARKK",
    # Other high-volume
    "BABA", "NIO", "RIVN", "LCID", "DKNG", "SHOP", "UBER", "LYFT", "ABNB",
    "SNAP", "PINS", "SQ", "ROKU", "T", "VZ", "TMUS",
]


@dataclass(frozen=True)
class UniverseEntry:
    """A single name in the universe with its liquidity stats."""
    ticker: str
    avg_daily_option_volume: float  # 20-day avg
    last_close: float
    snapshot_date: date


@dataclass(frozen=True)
class Universe:
    """Universe membership snapshot for a given date."""
    snapshot_date: date
    entries: tuple[UniverseEntry, ...]

    @property
    def tickers(self) -> list[str]:
        return [e.ticker for e in self.entries]

    def __len__(self) -> int:
        return len(self.entries)


def compute_options_volume_universe(
    as_of: date,
    polygon_client,
    candidate_tickers: Optional[list[str]] = None,
    min_avg_volume: int = settings.UNIVERSE_MIN_DAILY_OPTION_VOLUME,
    max_tickers: int = settings.UNIVERSE_MAX_TICKERS,
    lookback_days: int = settings.UNIVERSE_VOLUME_LOOKBACK_DAYS,
    excluded: Optional[set[str]] = None,
) -> Universe:
    """
    Compute the top-N liquid optionable names as of `as_of`.

    Polygon does not expose a single "total options volume by underlying"
    endpoint, so we approximate it by:

      1. For each candidate ticker, list all options contracts active on `as_of`.
      2. For each contract, get its daily volume over `lookback_days`.
      3. Sum across contracts to get the underlying's total option volume.
      4. Average over the lookback period.
      5. Filter by min_avg_volume and rank.

    This is expensive (potentially 100s of contract-day queries per name)
    but it's the only way to get a faithful liquidity ranking. Results are
    cached aggressively via the data layer.

    For the initial backtest, we use SEED_TICKERS as the candidate pool.
    """
    if candidate_tickers is None:
        candidate_tickers = SEED_TICKERS
    if excluded is None:
        excluded = settings.EXCLUDED_TICKERS

    candidates = [t for t in candidate_tickers if t not in excluded]
    log.info("Computing universe for %s from %d candidates", as_of, len(candidates))

    lookback_start = as_of - timedelta(days=lookback_days * 2)  # extra buffer for non-trading days

    entries: list[UniverseEntry] = []
    for ticker in candidates:
        try:
            avg_vol = _compute_avg_option_volume(
                ticker, polygon_client, lookback_start, as_of, lookback_days
            )
            if avg_vol < min_avg_volume:
                continue

            # Last close for the underlying (used by ATM strike selection later)
            bars = polygon_client.get_daily_bars(ticker, lookback_start, as_of)
            if bars.empty:
                continue
            last_close = float(bars["close"].iloc[-1])

            entries.append(UniverseEntry(
                ticker=ticker,
                avg_daily_option_volume=avg_vol,
                last_close=last_close,
                snapshot_date=as_of,
            ))
        except Exception as e:
            log.warning("Failed to compute volume for %s: %s", ticker, e)
            continue

    # Rank by volume desc, take top N
    entries.sort(key=lambda e: e.avg_daily_option_volume, reverse=True)
    entries = entries[:max_tickers]

    log.info("Universe for %s: %d names selected", as_of, len(entries))
    return Universe(snapshot_date=as_of, entries=tuple(entries))


def _compute_avg_option_volume(
    ticker: str,
    polygon_client,
    start: date,
    end: date,
    target_days: int,
) -> float:
    """
    Estimate average daily option volume for a ticker over a window.

    Implementation strategy:
      - List all option contracts active on `end` for this underlying.
      - For each contract, fetch daily bars over the window.
      - Sum all volumes per day.
      - Average over the trading days observed.

    Returns 0.0 if no data is available.

    This is approximate — it counts only currently-active contracts, so
    contracts that expired during the lookback window are missed. For a
    20-day lookback this is a small fraction; for longer lookbacks the
    bias would matter more.
    """
    contracts = polygon_client.list_options_contracts(
        underlying=ticker,
        as_of=end,
        expiration_gt=end,
        limit=200,  # cap per name to control API cost
    )
    if contracts.empty or "ticker" not in contracts.columns:
        return 0.0

    # Take a sample to keep cost bounded: top 50 by ATM-ness or first 50
    contract_tickers = contracts["ticker"].head(50).tolist()

    daily_totals: dict[pd.Timestamp, float] = {}
    for ct in contract_tickers:
        try:
            bars = polygon_client.get_option_daily_bars(ct, start, end)
            if bars.empty:
                continue
            for ts, row in bars.iterrows():
                daily_totals[ts] = daily_totals.get(ts, 0.0) + float(row.get("volume", 0))
        except Exception:
            continue

    if not daily_totals:
        return 0.0

    # Average over actual trading days observed
    total = sum(daily_totals.values())
    n_days = max(1, len(daily_totals))
    return total / n_days


def build_universe_simple(
    as_of: date,
    candidate_tickers: Optional[list[str]] = None,
    excluded: Optional[set[str]] = None,
) -> list[str]:
    """
    Simple universe builder for offline testing. Returns the candidate
    pool minus exclusions, with no liquidity filtering. Used by unit tests
    where we don't want to call Polygon.
    """
    if candidate_tickers is None:
        candidate_tickers = SEED_TICKERS
    if excluded is None:
        excluded = settings.EXCLUDED_TICKERS
    return [t for t in candidate_tickers if t not in excluded]
