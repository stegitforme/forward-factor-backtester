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

# ============================================================================
# Ticker rename history (Phase 5)
#
# Two universe tickers have predecessor symbols in ORATS that materially extend
# their backtest history. Rather than rewrite cached parquet files (which would
# couple cache to alias logic), we resolve at lookup time: discovery + bars
# clients consult resolve_ticker(canonical, date) to pick the right ORATS
# symbol per trade date.
#
# Verified empirically by probing each universe ticker's first appearance in
# ORATS, plus checking known predecessor candidates (e.g. ARKW for ARKK,
# IAU/PHYS for GLD, MCHI for KWEB). No other 23-universe ticker has a rename;
# all other coverage gaps (ARKK, KWEB, GLD, SLV, USO, HYG, COIN) are genuine
# ORATS-side coverage gaps without a predecessor symbol.
#
# Rename windows (verified 2026-05-04):
#   FB     -> META on 2022-06-09 (Facebook -> Meta Platforms ticker change)
#   GOOG   -> GOOGL on 2015-01-02 (when ORATS first carries GOOGL data —
#            note this is 9 months AFTER the actual stock split on 2014-04-03;
#            during 2014-04-03 → 2014-12-31 we use GOOG as Class A proxy
#            because ORATS lacks GOOGL coverage in that window)
#
# GOOGL caveat: post-split GOOG (Class C, no voting) and GOOGL (Class A, voting)
# trade at near-identical prices and IVs (typically <1% spread). Pre-split
# (2007-2014-04-02), GOOG is the only Google share class. The 9-month
# "GOOGL exists but ORATS doesn't have it" window is bridged using GOOG —
# acceptable noise vs the alternative of having a backtest gap. Documented
# in PHASE_5_TICKER_AVAILABILITY.md.
# ============================================================================

TICKER_HISTORY: dict[str, list[tuple[str, date, Optional[date]]]] = {
    "META":  [("FB",    date(2013, 1, 2),  date(2022, 6, 8)),
              ("META",  date(2022, 6, 9),  None)],
    "GOOGL": [("GOOG",  date(2007, 1, 3),  date(2015, 1, 1)),
              ("GOOGL", date(2015, 1, 2),  None)],
}


def resolve_ticker(target_ticker: str, trade_date: date) -> str:
    """Return the ORATS symbol to use for `target_ticker` on `trade_date`.

    For tickers without a rename history, returns target_ticker unchanged.
    For aliased tickers, picks the predecessor or canonical symbol that
    covered `trade_date`. If the date is outside all known windows for an
    aliased ticker, returns the target_ticker unchanged (caller will get
    empty data — correct behavior for dates pre-inception).
    """
    history = TICKER_HISTORY.get(target_ticker)
    if history is None:
        return target_ticker
    for orats_sym, start, end in history:
        if trade_date >= start and (end is None or trade_date <= end):
            return orats_sym
    return target_ticker


def expand_universe_for_lookup(universe: Iterable[str]) -> list[str]:
    """Return the union of all ORATS symbols needed to cover `universe`
    across history (canonical + all predecessors). Use when warming caches
    or loading day chains so the data needed by the alias resolver is present.
    """
    expanded = set()
    for t in universe:
        expanded.add(t)
        if t in TICKER_HISTORY:
            for orats_sym, _, _ in TICKER_HISTORY[t]:
                expanded.add(orats_sym)
    return sorted(expanded)


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

    NOTE: For short date windows (a few days), prefer load_orats_day_direct —
    it skips the full year cache build entirely and reads only the needed ZIPs.
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


def load_orats_day_direct(d: date, tickers: Iterable[str]) -> pd.DataFrame:
    """Read one ORATS day directly from ZIP, filtered to ticker subset.

    Bypasses the year cache entirely. Use for short windows (a few days) or
    when you don't want to incur the full-year cache build. Cost: ~1.5s per
    day (one full ZIP parse).
    """
    tickers_set = {t.upper() for t in tickers}
    if not tickers_set:
        return pd.DataFrame(columns=KEEP_COLUMNS)
    raw = load_orats_day_raw(d)
    if raw.empty:
        return raw
    return raw[raw["ticker"].isin(tickers_set)].reset_index(drop=True)


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


def warm_year_for_universe(year: int, tickers: Iterable[str]) -> None:
    """Read each ZIP in `year` ONCE, filter to all `tickers` in one pass, write
    per-ticker parquet caches.

    Vastly faster than calling _build_year_cache(ticker, year) per ticker
    (which would re-read every ZIP for each ticker). For a 23-ticker universe
    this is ~23× faster than the per-ticker approach.

    Idempotent — skips tickers whose cache already exists for the year.
    """
    tickers = sorted({t.upper() for t in tickers})
    if not tickers:
        return
    # Skip tickers already cached for this year
    pending = [t for t in tickers if not cache_path_for(t, year).exists()]
    if not pending:
        return
    yr_dir = ORATS_ROOT / str(year)
    if not yr_dir.exists():
        return
    zips = sorted(yr_dir.glob("ORATS_SMV_Strikes_*.zip"))
    if not zips:
        return

    log.info("Warming ORATS year cache: %d/%d (%d tickers, %d ZIPs)",
             year, year, len(pending), len(zips))
    pending_set = set(pending)
    # ticker -> list of per-day chunks
    chunks: dict[str, list[pd.DataFrame]] = {t: [] for t in pending_set}
    for z in zips:
        try:
            df = pd.read_csv(z, compression="zip", usecols=KEEP_COLUMNS)
            df = df[df["ticker"].isin(pending_set)]
            if df.empty:
                continue
            for t, sub in df.groupby("ticker"):
                if t in pending_set:
                    chunks[t].append(sub)
        except Exception as e:
            log.warning("warm_year: failed to read %s: %s", z.name, e)

    for t, parts in chunks.items():
        cp = cache_path_for(t, year)
        cp.parent.mkdir(parents=True, exist_ok=True)
        if not parts:
            # Write empty parquet so subsequent reads short-circuit instead of
            # re-running this expensive scan.
            pd.DataFrame(columns=KEEP_COLUMNS).to_parquet(cp, index=False)
            continue
        full = pd.concat(parts, ignore_index=True)
        full["trade_date"] = pd.to_datetime(full["trade_date"]).dt.date
        full["expirDate"] = pd.to_datetime(full["expirDate"]).dt.date
        full.to_parquet(cp, index=False)


def warm_cache(tickers: Iterable[str], years: Iterable[int],
               max_workers: int = 1) -> None:
    """Pre-build ticker-year caches. Calls warm_year_for_universe per year.

    With the batched warm_year_for_universe, threading across years gives a
    modest additional speedup (years are independent) but is bounded by
    disk I/O. Default max_workers=1 since each year is already an
    expensive single-pass read.
    """
    tickers = sorted({t.upper() for t in tickers})
    years = sorted(set(years))
    if not tickers or not years:
        return
    if max_workers <= 1:
        for y in years:
            warm_year_for_universe(y, tickers)
        return
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(warm_year_for_universe, y, tickers): y for y in years}
        for fut in as_completed(futs):
            y = futs[fut]
            try:
                fut.result()
            except Exception as e:
                log.error("warm_year failed %d: %s", y, e)


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


# ============================================================================
# OratsBarsClient — quacks like PolygonClient.get_option_daily_bars
#
# The existing simulator (src/simulate_portfolio.py + src/trade_simulator.py)
# uses Polygon-style option tickers ("O:SPY241129C00580000") and looks up
# daily OHLCV bars via client.get_option_daily_bars(symbol, start, end).
#
# This client lets the simulator run unchanged on ORATS data: it parses the
# Polygon symbol back to (ticker, expiry, type, strike) and synthesizes a
# bar-shaped DataFrame from ORATS quote midpoints.
# ============================================================================

OPTION_SYMBOL_RE = None  # built lazily


def _parse_polygon_option_symbol(symbol: str) -> Optional[tuple[str, date, str, float]]:
    """Parse 'O:SPY241129C00580000' -> ('SPY', date(2024,11,29), 'C', 580.0).

    Returns None if symbol doesn't match the expected format.
    """
    import re
    global OPTION_SYMBOL_RE
    if OPTION_SYMBOL_RE is None:
        OPTION_SYMBOL_RE = re.compile(
            r"^O:([A-Z\.]+?)(\d{6})([CP])(\d{8})$"
        )
    m = OPTION_SYMBOL_RE.match(symbol)
    if m is None:
        return None
    underlying, yymmdd, opt_type, strike_str = m.groups()
    try:
        year = 2000 + int(yymmdd[:2])
        month = int(yymmdd[2:4])
        day = int(yymmdd[4:6])
        expiry = date(year, month, day)
    except ValueError:
        return None
    strike = int(strike_str) / 1000.0
    return underlying, expiry, opt_type, strike


def _orats_mid(row: pd.Series, opt_type: str) -> Optional[float]:
    """Mid quote from one ORATS row for the requested side. Falls back to
    cValue / pValue (ORATS' smooth-surface fair price) if bid/ask quotes are
    zero or missing — matches what a real fill would look like for thin chains.
    """
    if opt_type == "C":
        bid = row.get("cBidPx")
        ask = row.get("cAskPx")
        val = row.get("cValue")
    else:
        bid = row.get("pBidPx")
        ask = row.get("pAskPx")
        val = row.get("pValue")
    try:
        if bid is not None and ask is not None and not pd.isna(bid) and not pd.isna(ask):
            b = float(bid); a = float(ask)
            if b > 0 and a > 0 and a >= b:
                return (b + a) / 2.0
    except (TypeError, ValueError):
        pass
    if val is not None and not pd.isna(val):
        try:
            v = float(val)
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None
    return None


class OratsBarsClient:
    """Adapter that exposes get_option_daily_bars(symbol, start, end) backed
    by the ORATS ticker-year cache. Drop-in replacement for PolygonClient
    in the simulator's MTM + exit-pricing call sites.

    The synthesized bar DataFrame has columns: open, high, low, close, vwap,
    volume — all set to the ORATS mid (or cValue/pValue fallback). Index is
    pd.DatetimeIndex of trade_dates. This shape matches what
    `_mid_from_bar()` and `bars.index.asof()` expect.

    Cache: instance maintains a per-(ticker, expiry, strike, type) cache so
    repeated lookups within a sim run are O(1).
    """

    def __init__(self):
        self._cache: dict[tuple[str, date, str, float], pd.DataFrame] = {}

    def get_option_daily_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        parsed = _parse_polygon_option_symbol(symbol)
        if parsed is None:
            return pd.DataFrame()
        underlying, expiry, opt_type, strike = parsed
        key = (underlying, expiry, opt_type, strike)
        if key in self._cache:
            df = self._cache[key]
        else:
            df = self._build_bars_for_contract(underlying, expiry, opt_type, strike)
            self._cache[key] = df
        if df.empty:
            return df
        # Slice to requested window (caller passes ±3 day window typically)
        return df.loc[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]

    def _build_bars_for_contract(self, underlying: str, expiry: date,
                                  opt_type: str, strike: float) -> pd.DataFrame:
        """Look up ORATS rows for this contract across its lifetime, build
        a bar-shaped DataFrame indexed by trade_date.

        Aliasing: if `underlying` has a TICKER_HISTORY entry (e.g. META, GOOGL),
        load data under ALL aliases (FB+META, GOOG+GOOGL) and concatenate.
        For an option whose lifetime spans a rename date, both predecessor and
        successor symbols carry data for the same physical contract — we want
        both halves so the bars timeseries is continuous.
        """
        # Decide which ORATS symbols to query. For aliased tickers, expand
        # to the full set; for the rest, query the canonical name only.
        symbols_to_query: list[str]
        if underlying in TICKER_HISTORY:
            symbols_to_query = sorted({sym for sym, _, _ in TICKER_HISTORY[underlying]})
        else:
            symbols_to_query = [underlying]

        # ORATS rows for this ticker exist in (year of expiry) and possibly
        # the year before. Fetch from start-of-expiry-year-minus-1 through
        # expiry, slice to dates with this exact (expiry, strike, type).
        start_year = expiry.year - 1 if expiry.month <= 3 else expiry.year
        start_date = date(start_year, 1, 1)

        all_chunks = []
        for sym in symbols_to_query:
            rng = load_orats_range(start_date, expiry, [sym])
            if rng.empty:
                continue
            sub = rng[(rng["expirDate"] == expiry) & (rng["strike"] == strike)]
            if not sub.empty:
                all_chunks.append(sub)

        if not all_chunks:
            return pd.DataFrame()
        full_sub = pd.concat(all_chunks, ignore_index=True)

        mids = full_sub.apply(lambda r: _orats_mid(r, opt_type), axis=1)
        out = pd.DataFrame({
            "open": mids.values, "high": mids.values, "low": mids.values,
            "close": mids.values, "vwap": mids.values, "volume": 0,
        }, index=pd.DatetimeIndex([pd.Timestamp(d) for d in full_sub["trade_date"]], name="date"))
        out = out.dropna(subset=["close"])
        out = out[~out.index.duplicated(keep="first")].sort_index()
        return out
