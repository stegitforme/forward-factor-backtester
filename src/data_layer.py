"""
Polygon.io / Massive data layer.

Provides cached access to:
  - Equity OHLCV (for SPY/QQQ/TQQQ benchmarks)
  - Options contracts reference (for finding ATM strikes by DTE)
  - Options OHLCV (for historical option prices)
  - Daily implied volatility (Greeks/IV from Polygon)
  - Earnings calendar (for the earnings filter)

All Polygon responses are cached to disk via diskcache so repeated runs
don't burn API quota. Cache TTLs are tier-aware: historical data caches
for a year, recent data for an hour.

Polygon Options Advanced subscription is required for:
  - 5+ years of options history
  - Unlimited API calls
  - Real-time Greeks/IV
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
from diskcache import Cache

from config import settings


log = logging.getLogger(__name__)


class PolygonClient:
    """
    Thin wrapper around Polygon REST API with disk-backed caching and
    automatic retries on rate limits.
    """

    def __init__(
        self,
        api_key: str,
        cache_dir: str | Path = "data_cache",
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        if not api_key or api_key == "REPLACE_WITH_YOUR_POLYGON_API_KEY":
            raise ValueError(
                "Polygon API key is missing. Copy config/secrets.example.py to "
                "config/secrets.py and add your real key."
            )
        self.api_key = api_key
        self.base_url = settings.POLYGON_BASE_URL
        self.timeout = timeout
        self.max_retries = max_retries

        cache_path = Path(cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        self.cache = Cache(str(cache_path))

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "ff-backtester/0.1",
        })

    # ------------------------------------------------------------------
    # Low-level GET with caching
    # ------------------------------------------------------------------

    def _get(
        self,
        path: str,
        params: Optional[dict] = None,
        ttl_seconds: int = settings.CACHE_TTL_HISTORICAL,
    ) -> dict:
        """Cached GET request with retry on 429."""
        cache_key = f"{path}::{sorted((params or {}).items())}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        url = f"{self.base_url}{path}"
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.exceptions.RequestException as e:
                if attempt >= self.max_retries:
                    raise
                log.warning("Request failed (%s), retry %d/%d", e, attempt, self.max_retries)
                time.sleep(2 ** attempt)
                continue

            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", "5"))
                log.info("Rate limited, sleeping %.1fs", wait)
                time.sleep(wait)
                if attempt >= self.max_retries:
                    resp.raise_for_status()
                continue

            if resp.status_code >= 500 and attempt < self.max_retries:
                log.warning("Server error %s, retry %d/%d", resp.status_code, attempt, self.max_retries)
                time.sleep(2 ** attempt)
                continue

            resp.raise_for_status()
            data = resp.json()
            self.cache.set(cache_key, data, expire=ttl_seconds)
            return data

    # ------------------------------------------------------------------
    # Equity OHLCV
    # ------------------------------------------------------------------

    def get_daily_bars(
        self,
        ticker: str,
        start: date,
        end: date,
        adjusted: bool = True,
    ) -> pd.DataFrame:
        """
        Daily OHLCV for an equity ticker.

        Returns DataFrame indexed by date with columns: open, high, low,
        close, volume, vwap, transactions.
        """
        path = f"/v2/aggs/ticker/{ticker}/range/1/day/{start.isoformat()}/{end.isoformat()}"
        params = {"adjusted": str(adjusted).lower(), "sort": "asc", "limit": 50000}
        data = self._get(path, params, ttl_seconds=settings.CACHE_TTL_HISTORICAL)

        results = data.get("results", []) or []
        if not results:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "vwap", "transactions"])

        df = pd.DataFrame(results)
        df["date"] = pd.to_datetime(df["t"], unit="ms").dt.normalize()
        df = df.set_index("date")
        df = df.rename(columns={
            "o": "open", "h": "high", "l": "low", "c": "close",
            "v": "volume", "vw": "vwap", "n": "transactions",
        })
        cols = ["open", "high", "low", "close", "volume", "vwap", "transactions"]
        return df[[c for c in cols if c in df.columns]]

    # ------------------------------------------------------------------
    # Options contracts reference
    # ------------------------------------------------------------------

    def list_options_contracts(
        self,
        underlying: str,
        as_of: date,
        expiration_lt: Optional[date] = None,
        expiration_gt: Optional[date] = None,
        contract_type: Optional[str] = None,  # "call" or "put"
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        List options contracts for an underlying that were active on `as_of`.
        Filters by expiration window and contract type if specified.
        """
        path = "/v3/reference/options/contracts"
        params: dict[str, Any] = {
            "underlying_ticker": underlying,
            "as_of": as_of.isoformat(),
            "expired": "false",
            "limit": min(limit, 1000),
            "order": "asc",
            "sort": "expiration_date",
        }
        if expiration_lt:
            params["expiration_date.lte"] = expiration_lt.isoformat()
        if expiration_gt:
            params["expiration_date.gte"] = expiration_gt.isoformat()
        if contract_type:
            params["contract_type"] = contract_type

        all_results: list[dict] = []
        next_url: Optional[str] = None

        while True:
            if next_url:
                # next_url is fully qualified; need to handle differently
                resp = self.session.get(next_url, timeout=self.timeout, params={"apiKey": self.api_key})
                resp.raise_for_status()
                data = resp.json()
            else:
                data = self._get(path, params, ttl_seconds=settings.CACHE_TTL_HISTORICAL)

            results = data.get("results", []) or []
            all_results.extend(results)

            next_url = data.get("next_url")
            if not next_url or len(all_results) >= 5000:
                break

        if not all_results:
            return pd.DataFrame()

        df = pd.DataFrame(all_results)
        if "expiration_date" in df.columns:
            df["expiration_date"] = pd.to_datetime(df["expiration_date"]).dt.date
        return df

    # ------------------------------------------------------------------
    # Option daily bars
    # ------------------------------------------------------------------

    def get_option_daily_bars(
        self,
        option_ticker: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Daily OHLCV for an option contract (e.g. 'O:SPY230120C00400000')."""
        path = f"/v2/aggs/ticker/{option_ticker}/range/1/day/{start.isoformat()}/{end.isoformat()}"
        params = {"adjusted": "true", "sort": "asc", "limit": 50000}
        try:
            data = self._get(path, params, ttl_seconds=settings.CACHE_TTL_HISTORICAL)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return pd.DataFrame()
            raise

        results = data.get("results", []) or []
        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        df["date"] = pd.to_datetime(df["t"], unit="ms").dt.normalize()
        df = df.set_index("date")
        df = df.rename(columns={
            "o": "open", "h": "high", "l": "low", "c": "close",
            "v": "volume", "vw": "vwap", "n": "transactions",
        })
        return df

    # ------------------------------------------------------------------
    # Daily IV / Greeks snapshot
    # ------------------------------------------------------------------

    def get_option_snapshot(self, underlying: str, option_ticker: str) -> dict:
        """
        Real-time / latest snapshot for an option contract, including
        Greeks and implied volatility.

        Note: Polygon's HISTORICAL daily IV is delivered via a separate
        endpoint (`/v3/snapshot/options/{underlying}/{option}` is current,
        historical IV requires the flat files product or the contracts
        endpoint with 'as_of' specifier).
        """
        path = f"/v3/snapshot/options/{underlying}/{option_ticker}"
        return self._get(path, ttl_seconds=settings.CACHE_TTL_RECENT)

    # ------------------------------------------------------------------
    # Universe — most active options by daily volume
    # ------------------------------------------------------------------

    def get_options_volume_by_underlying(
        self,
        as_of: date,
    ) -> pd.DataFrame:
        """
        Get total options volume per underlying for a given date.

        Used by the universe selector to find the top N most active
        names (>10K avg daily option contracts).

        Note: This endpoint may require iterating through contract-level
        data and aggregating, depending on what Polygon exposes. The
        universe.py module handles the aggregation logic.
        """
        # Implementation note: Polygon does not expose a single "total
        # options volume by underlying" endpoint. The universe.py module
        # implements this by aggregating per-contract daily volumes.
        # Stubbed here for interface clarity.
        raise NotImplementedError(
            "Use universe.compute_options_volume_universe() which aggregates "
            "across contracts. This stub is here for API surface clarity."
        )


# ============================================================================
# Lazy singleton accessor
# ============================================================================

_client_instance: Optional[PolygonClient] = None


def get_client() -> PolygonClient:
    """
    Get the singleton PolygonClient. Loads the API key from config.secrets
    on first access. Importing this module does NOT require secrets.py to
    exist — only calling get_client() does.
    """
    global _client_instance
    if _client_instance is None:
        try:
            from config import secrets  # type: ignore
        except ImportError:
            raise RuntimeError(
                "config/secrets.py not found. Copy config/secrets.example.py "
                "to config/secrets.py and add your Polygon API key."
            )
        _client_instance = PolygonClient(api_key=secrets.POLYGON_API_KEY)
    return _client_instance
