"""ORATS SMV Strikes ZIP-archive adapter.

Reads ORATS' daily ZIP archives directly (no extraction) and exposes a
uniform DataFrame interface for discovery / simulation code. Builds a
ticker-year parquet cache lazily so repeat reads of the same ticker are
~100× faster than re-parsing ZIPs.

Data layout (Steven's local store):
  /Users/sggmpb13/trading/<YYYY>/ORATS_SMV_Strikes_<YYYYMMDD>.zip

Each ZIP contains a single CSV (ORATS_SMV_Strikes_<YYYYMMDD>.csv) with the
full options chain across all listed equities + ETFs for that day. ~70-230 MB
compressed, ~230 MB uncompressed, ~700K-1M rows × 39 columns.

Schema verified against ORATS docs + sample read of 2024-10-29 ZIP. Column
list captured in COLUMNS below.

Cache layout:
  ~/orats_data_cache/<TICKER>/<YEAR>.parquet

Each cached parquet is a year's worth of one ticker's chain (~5-50 MB depending
on ticker liquidity). Built lazily on first read of a ticker-year combo.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

log = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

ORATS_ROOT = Path("/Users/sggmpb13/trading")
CACHE_ROOT = Path.home() / "orats_data_cache"

# All 39 columns shipped in ORATS_SMV_Strikes (verified from 2024-10-29 ZIP).
COLUMNS = [
    "ticker", "cOpra", "pOpra", "stkPx", "expirDate", "yte", "strike",
    "cVolu", "cOi", "pVolu", "pOi",
    "cBidPx", "cValue", "cAskPx", "pBidPx", "pValue", "pAskPx",
    "cBidIv", "cMidIv", "cAskIv", "smoothSmvVol",
    "pBidIv", "pMidIv", "pAskIv",
    "iRate", "divRate", "residualRateData",
    "delta", "gamma", "theta", "vega", "rho", "phi", "driftlessTheta",
    "extVol", "extCTheo", "extPTheo",
    "spot_px", "trade_date",
]

# Subset we keep in cache. Drops cOpra/pOpra (~30% of file size) since we
# don't need the OPRA contract symbol for discovery / sim. Keeping them
# would let us cross-reference Polygon contract IDs but no current consumer.
KEEP_COLUMNS = [
    "ticker", "stkPx", "expirDate", "yte", "strike",
    "cVolu", "cOi", "pVolu", "pOi",
    "cBidPx", "cValue", "cAskPx", "pBidPx", "pValue", "pAskPx",
    "cBidIv", "cMidIv", "cAskIv", "smoothSmvVol",
    "pBidIv", "pMidIv", "pAskIv",
    "delta", "gamma", "theta", "vega",
    "extVol", "extCTheo", "extPTheo",
    "trade_date",
]


# ============================================================================
# Path helpers
# ============================================================================

def zip_path_for_date(d: date) -> Path:
    """Return the expected ZIP path for a given trade date."""
    return ORATS_ROOT / str(d.year) / f"ORATS_SMV_Strikes_{d:%Y%m%d}.zip"


def cache_path_for(ticker: str, year: int) -> Path:
    """Return the parquet cache path for a (ticker, year) combo."""
    return CACHE_ROOT / ticker.upper() / f"{year}.parquet"


def has_data_for(d: date) -> bool:
    """True if a ZIP exists for this trade date."""
    return zip_path_for_date(d).exists()


# ============================================================================
# Raw ZIP reads
# ============================================================================

def load_orats_day_raw(d: date) -> pd.DataFrame:
    """Read one full-chain ORATS day from ZIP. Returns empty DF if missing.

    All ~700K-1M rows × ~39 cols. Use sparingly — prefer load_orats_day with
    a ticker filter when discovery only needs a subset.
    """
    zp = zip_path_for_date(d)
    if not zp.exists():
        log.debug("ORATS ZIP missing for %s: %s", d, zp)
        return pd.DataFrame(columns=KEEP_COLUMNS)
    df = pd.read_csv(zp, compression="zip", usecols=KEEP_COLUMNS)
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["expirDate"] = pd.to_datetime(df["expirDate"]).dt.date
    return df


def load_orats_day_filtered(d: date, tickers: Iterable[str]) -> pd.DataFrame:
    """Read one ORATS day filtered to a ticker subset. Uses cache when available.

    Order of operations:
      1. For each ticker, check cache (~/orats_data_cache/<T>/<year>.parquet).
         If present, slice to the requested date and use that.
      2. For tickers missing from cache, build the year cache for that ticker
         (reads all ZIPs in the year, filters, writes parquet). This is the
         expensive first-pass; subsequent reads of any day in that year are
         instant.
      3. Concatenate per-ticker slices into one DataFrame.
    """
    tickers = sorted({t.upper() for t in tickers})
    if not tickers:
        return pd.DataFrame(columns=KEEP_COLUMNS)

    out_chunks = []
    for t in tickers:
        cached = _load_or_build_year_cache(t, d.year)
        if cached.empty:
            continue
        slice_ = cached[cached["trade_date"] == d]
        if not slice_.empty:
            out_chunks.append(slice_)

    if not out_chunks:
        return pd.DataFrame(columns=KEEP_COLUMNS)
    return pd.concat(out_chunks, ignore_index=True)


# ============================================================================
# Ticker-year cache
# ============================================================================

def _load_or_build_year_cache(ticker: str, year: int) -> pd.DataFrame:
    """Return the year cache for a ticker, building it if absent."""
    cp = cache_path_for(ticker, year)
    if cp.exists():
        try:
            return pd.read_parquet(cp)
        except Exception as e:
            log.warning("cache read failed %s: %s — rebuilding", cp, e)
            cp.unlink(missing_ok=True)
    return _build_year_cache(ticker, year)


def _build_year_cache(ticker: str, year: int) -> pd.DataFrame:
    """Read every ZIP in `year`, filter to `ticker`, write parquet cache."""
    yr_dir = ORATS_ROOT / str(year)
    if not yr_dir.exists():
        log.debug("ORATS year folder missing: %s", yr_dir)
        return pd.DataFrame(columns=KEEP_COLUMNS)
    zips = sorted(yr_dir.glob("ORATS_SMV_Strikes_*.zip"))
    if not zips:
        return pd.DataFrame(columns=KEEP_COLUMNS)

    log.info("Building ORATS cache: %s/%d (%d ZIPs)", ticker, year, len(zips))
    chunks = []
    for z in zips:
        try:
            df = pd.read_csv(z, compression="zip", usecols=KEEP_COLUMNS)
            df = df[df["ticker"] == ticker]
            if not df.empty:
                chunks.append(df)
        except Exception as e:
            log.warning("cache build: failed to read %s: %s", z.name, e)

    if not chunks:
        empty = pd.DataFrame(columns=KEEP_COLUMNS)
        return empty

    full = pd.concat(chunks, ignore_index=True)
    full["trade_date"] = pd.to_datetime(full["trade_date"]).dt.date
    full["expirDate"] = pd.to_datetime(full["expirDate"]).dt.date

    cp = cache_path_for(ticker, year)
    cp.parent.mkdir(parents=True, exist_ok=True)
    full.to_parquet(cp, index=False)
    return full


def warm_cache(tickers: Iterable[str], years: Iterable[int],
               max_workers: int = 4) -> None:
    """Pre-build ticker-year caches in parallel. Idempotent — skips existing.

    Useful before running discovery on a long date range to amortize the
    one-time ZIP-parsing cost.
    """
    tickers = sorted({t.upper() for t in tickers})
    years = sorted(set(years))
    work = [(t, y) for t in tickers for y in years
            if not cache_path_for(t, y).exists()]
    if not work:
        return
    log.info("Warming ORATS cache: %d (ticker, year) combos", len(work))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_build_year_cache, t, y): (t, y) for t, y in work}
        for fut in as_completed(futs):
            t, y = futs[fut]
            try:
                fut.result()
            except Exception as e:
                log.error("cache build failed %s/%d: %s", t, y, e)


# ============================================================================
# Range loading
# ============================================================================

def load_orats_range(start: date, end: date,
                     tickers: Iterable[str]) -> pd.DataFrame:
    """Load all ORATS rows for tickers between start and end (inclusive).

    Walks the underlying ticker-year caches; builds them on demand. Returns
    a single DataFrame keyed by (ticker, trade_date, expirDate, strike).
    """
    tickers = sorted({t.upper() for t in tickers})
    if start > end or not tickers:
        return pd.DataFrame(columns=KEEP_COLUMNS)
    chunks = []
    for t in tickers:
        for year in range(start.year, end.year + 1):
            yr_df = _load_or_build_year_cache(t, year)
            if yr_df.empty:
                continue
            mask = (yr_df["trade_date"] >= start) & (yr_df["trade_date"] <= end)
            sub = yr_df[mask]
            if not sub.empty:
                chunks.append(sub)
    if not chunks:
        return pd.DataFrame(columns=KEEP_COLUMNS)
    return pd.concat(chunks, ignore_index=True)


# ============================================================================
# Ticker availability (Q3 — answers "which tickers are present in which year")
# ============================================================================

@dataclass(frozen=True)
class TickerAvailabilityRow:
    ticker: str
    year: int
    days_present: int
    days_in_year: int

    @property
    def coverage_pct(self) -> float:
        return 100.0 * self.days_present / self.days_in_year if self.days_in_year else 0.0


def ticker_availability(start: date, end: date,
                        tickers: Iterable[str]) -> pd.DataFrame:
    """For each (ticker, year) in [start.year, end.year], count trading days
    where the ticker has at least one row in ORATS data.

    Returns DataFrame with columns: ticker, year, days_present, days_in_year,
    coverage_pct. Sorted by (ticker, year).

    Implementation reads each ticker-year cache once. Building the cache is
    a side effect; subsequent calls are fast.
    """
    tickers = sorted({t.upper() for t in tickers})
    rows = []
    for year in range(start.year, end.year + 1):
        yr_dir = ORATS_ROOT / str(year)
        if not yr_dir.exists():
            for t in tickers:
                rows.append(dict(ticker=t, year=year, days_present=0,
                                 days_in_year=0, coverage_pct=0.0))
            continue
        days_in_year = sum(1 for _ in yr_dir.glob("ORATS_SMV_Strikes_*.zip"))
        for t in tickers:
            yr_df = _load_or_build_year_cache(t, year)
            if yr_df.empty:
                cnt = 0
            else:
                # Filter to date window if year overlaps boundary
                lo = max(start, date(year, 1, 1))
                hi = min(end, date(year, 12, 31))
                mask = (yr_df["trade_date"] >= lo) & (yr_df["trade_date"] <= hi)
                cnt = int(yr_df.loc[mask, "trade_date"].nunique())
            rows.append(dict(ticker=t, year=year, days_present=cnt,
                             days_in_year=days_in_year,
                             coverage_pct=100.0 * cnt / days_in_year if days_in_year else 0.0))
    return pd.DataFrame(rows).sort_values(["ticker", "year"]).reset_index(drop=True)


# ============================================================================
# Helpers for discovery / simulation
# ============================================================================

def find_atm_for_dte(day_df: pd.DataFrame, ticker: str, target_dte: int,
                     buffer_days: int = 5) -> Optional[pd.Series]:
    """From a single-day chain (filtered or full), find the ATM call row at
    the closest expiry to target_dte (within ±buffer_days).

    Returns a single Series (one ORATS row) or None if no chain matches.

    "ATM" = strike closest to underlying spot. Uses absolute distance.
    """
    sub = day_df[day_df["ticker"] == ticker]
    if sub.empty:
        return None

    # Build DTE column from yte (ORATS already provides time-to-expiry in years)
    # but use expirDate - trade_date for integer day count to match Polygon code.
    trade_dates = sub["trade_date"].iloc[0]  # constant within day
    sub = sub.assign(dte=(pd.to_datetime(sub["expirDate"]) - pd.to_datetime(trade_dates)).dt.days)

    # Find expiry closest to target_dte within buffer
    expiries = sub.drop_duplicates("expirDate")[["expirDate", "dte"]]
    expiries = expiries.assign(dte_dist=(expiries["dte"] - target_dte).abs())
    expiries = expiries[expiries["dte_dist"] <= buffer_days]
    if expiries.empty:
        return None
    chosen = expiries.sort_values("dte_dist").iloc[0]
    chosen_expiry = chosen["expirDate"]

    # Within chosen expiry, ATM by absolute distance from spot
    chain = sub[sub["expirDate"] == chosen_expiry].copy()
    if chain.empty:
        return None
    spot = float(chain["stkPx"].iloc[0])
    chain["atm_dist"] = (chain["strike"] - spot).abs()
    return chain.sort_values("atm_dist").iloc[0]
