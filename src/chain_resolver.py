"""
Chain resolver: turns "I want a 30-DTE ATM call on AAPL on May 2, 2022"
into actual contract prices and implied volatilities ready for the FF
calculator.

This module is the bridge between the abstract strategy specification
(DTE pair, structure, FF threshold) and the concrete Polygon data we
need to backtest it.

The key challenge: Polygon Options Advanced does NOT return historical
implied volatility in its REST API. The /v3/snapshot/options/ endpoint
is live-only and on our tier returns empty 'day' fields for most
contracts. So we compute IV ourselves from the historical option close
price using Black-Scholes inversion.

Workflow per (ticker, date, target_DTE):

  1. List active contracts for that ticker as of `date`, filtered to
     expiration_date in [date + target_DTE - buffer, date + target_DTE + buffer].
  2. Get the underlying spot for that date.
  3. For ATM: pick the contract with strike closest to spot.
     For 35-delta: pick the strike whose delta (computed using a rough
     IV estimate first, then refined) is closest to 0.35.
  4. Get that contract's daily close on `date`.
  5. Solve for IV using BS inversion.

Every Polygon call goes through the cached PolygonClient, so a 4-year
backtest only pays the API cost once.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from config import settings
from src.iv_solver import (
    black_scholes_delta,
    implied_volatility_safe,
)


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedOption:
    """A specific option contract resolved at a specific date."""
    ticker: str           # Polygon option ticker e.g. "O:AAPL220617C00150000"
    underlying: str
    strike: float
    expiration: date
    contract_type: str    # "call" or "put"
    as_of_date: date
    days_to_expiry: int
    underlying_price: float
    option_close: float
    implied_volatility: float   # NaN if couldn't solve


def _open_close_get(
    polygon_client,
    option_ticker: str,
    on_date: date,
) -> Optional[dict]:
    """
    Use Polygon's /v1/open-close endpoint for a single (contract, date).

    Cheaper than /v2/aggs for one-day queries and returns OHLCV in one
    JSON. Returns None if not found / no data.
    """
    path = f"/v1/open-close/{option_ticker}/{on_date.isoformat()}"
    try:
        data = polygon_client._get(path, ttl_seconds=settings.CACHE_TTL_HISTORICAL)
    except Exception as e:
        log.debug("open-close failed for %s on %s: %s", option_ticker, on_date, e)
        return None
    if not isinstance(data, dict) or data.get("status") != "OK":
        return None
    return data


def _underlying_close(
    polygon_client,
    underlying: str,
    on_date: date,
) -> Optional[float]:
    """
    Get the underlying's close on `on_date`. Falls back to nearby
    trading days within 5 calendar days if `on_date` is not a trading
    day (weekend/holiday).
    """
    bars = polygon_client.get_daily_bars(
        underlying, on_date - timedelta(days=7), on_date + timedelta(days=1)
    )
    if bars.empty:
        return None
    target = pd.Timestamp(on_date)
    idx = bars.index.asof(target)
    if pd.isna(idx):
        return None
    return float(bars.loc[idx, "close"])


def _list_contracts_for_dte(
    polygon_client,
    underlying: str,
    as_of: date,
    target_dte: int,
    buffer_days: int = settings.DTE_BUFFER_DAYS,
    contract_type: str = "call",
) -> pd.DataFrame:
    """
    Find all contracts whose expiration is within target_dte ± buffer_days
    of `as_of`. Returns DataFrame with rows including ticker, strike,
    expiration_date, contract_type.
    """
    target_expiry = as_of + timedelta(days=target_dte)
    earliest = target_expiry - timedelta(days=buffer_days)
    latest = target_expiry + timedelta(days=buffer_days)

    df = polygon_client.list_options_contracts(
        underlying=underlying,
        as_of=as_of,
        expiration_gt=earliest,
        expiration_lt=latest,
        contract_type=contract_type,
        limit=1000,
    )
    return df


def resolve_atm_option(
    polygon_client,
    underlying: str,
    as_of: date,
    target_dte: int,
    buffer_days: int = settings.DTE_BUFFER_DAYS,
    contract_type: str = "call",
    risk_free_rate: float = 0.04,
) -> Optional[ResolvedOption]:
    """
    Resolve an ATM call (or put) closest to target_dte days out.

    Returns None if data is missing (no contracts in window, no underlying
    price, no option close, etc.).
    """
    contracts = _list_contracts_for_dte(
        polygon_client, underlying, as_of, target_dte, buffer_days, contract_type
    )
    if contracts.empty:
        return None

    spot = _underlying_close(polygon_client, underlying, as_of)
    if spot is None or spot <= 0:
        return None

    # Pick expiration closest to target DTE
    target_expiry = as_of + timedelta(days=target_dte)
    contracts = contracts.copy()
    contracts["expiry_diff"] = contracts["expiration_date"].apply(
        lambda d: abs((d - target_expiry).days)
    )
    chosen_expiry = contracts.sort_values("expiry_diff").iloc[0]["expiration_date"]
    same_expiry = contracts[contracts["expiration_date"] == chosen_expiry]

    # Within that expiry, pick strike closest to spot
    same_expiry = same_expiry.copy()
    same_expiry["strike_diff"] = (same_expiry["strike_price"] - spot).abs()
    chosen = same_expiry.sort_values("strike_diff").iloc[0]

    chosen_ticker = chosen["ticker"]
    chosen_strike = float(chosen["strike_price"])

    # Get the contract's price on as_of
    oc = _open_close_get(polygon_client, chosen_ticker, as_of)
    if oc is None:
        return None
    close = oc.get("close")
    if close is None or close <= 0:
        return None

    dte = (chosen_expiry - as_of).days
    iv = implied_volatility_safe(
        option_price=float(close),
        underlying=spot,
        strike=chosen_strike,
        days_to_expiry=dte,
        risk_free_rate=risk_free_rate,
        is_call=(contract_type == "call"),
    )

    return ResolvedOption(
        ticker=chosen_ticker,
        underlying=underlying,
        strike=chosen_strike,
        expiration=chosen_expiry,
        contract_type=contract_type,
        as_of_date=as_of,
        days_to_expiry=dte,
        underlying_price=spot,
        option_close=float(close),
        implied_volatility=iv,
    )


def resolve_delta_option(
    polygon_client,
    underlying: str,
    as_of: date,
    target_dte: int,
    target_delta: float,
    buffer_days: int = settings.DTE_BUFFER_DAYS,
    contract_type: str = "call",
    risk_free_rate: float = 0.04,
) -> Optional[ResolvedOption]:
    """
    Resolve a target-delta option (e.g. 0.35 for 35-delta call, -0.35 for
    35-delta put).

    Process:
      1. Find expiration closest to target_dte.
      2. Among strikes for that expiry, compute implied delta for each
         using their observed close prices and BS-inverted IV.
      3. Pick the strike whose delta is closest to target_delta.

    This is more expensive than ATM resolution because we need to query
    multiple contracts (5-15 strikes around the expected delta zone).
    Caching in the PolygonClient mitigates the repeat cost.
    """
    contracts = _list_contracts_for_dte(
        polygon_client, underlying, as_of, target_dte, buffer_days, contract_type
    )
    if contracts.empty:
        return None

    spot = _underlying_close(polygon_client, underlying, as_of)
    if spot is None or spot <= 0:
        return None

    target_expiry = as_of + timedelta(days=target_dte)
    contracts = contracts.copy()
    contracts["expiry_diff"] = contracts["expiration_date"].apply(
        lambda d: abs((d - target_expiry).days)
    )
    chosen_expiry = contracts.sort_values("expiry_diff").iloc[0]["expiration_date"]
    same_expiry = contracts[contracts["expiration_date"] == chosen_expiry].copy()

    if same_expiry.empty:
        return None

    dte = (chosen_expiry - as_of).days
    is_call = contract_type == "call"

    # Filter strikes to a reasonable band around expected delta zone:
    # 35-delta call is typically ~5-10% OTM; 35-delta put ~5-10% OTM (other side).
    # Cast a wide net: 0.5x to 1.5x of spot.
    same_expiry = same_expiry[
        (same_expiry["strike_price"] >= spot * 0.5) &
        (same_expiry["strike_price"] <= spot * 1.5)
    ]
    if same_expiry.empty:
        return None

    # Sort by strike to walk efficiently
    same_expiry = same_expiry.sort_values("strike_price").reset_index(drop=True)

    # For each candidate strike, fetch its price and compute IV+delta.
    # To keep API cost bounded, narrow to ~10 strikes nearest the
    # target-delta zone (heuristic: for 35-delta calls, pick strikes
    # 5-15% OTM as starting band).
    if is_call and target_delta > 0:
        # OTM calls are above spot
        candidates = same_expiry[same_expiry["strike_price"] > spot]
    elif not is_call and target_delta < 0:
        # OTM puts are below spot
        candidates = same_expiry[same_expiry["strike_price"] < spot]
    else:
        candidates = same_expiry

    if candidates.empty:
        candidates = same_expiry  # fall back to whole expiry

    # Evaluate up to 10 candidates closest to estimated delta zone
    candidates = candidates.head(15)

    best: Optional[tuple[float, ResolvedOption]] = None  # (delta_diff, resolved)

    for _, row in candidates.iterrows():
        ct = row["ticker"]
        strike = float(row["strike_price"])
        oc = _open_close_get(polygon_client, ct, as_of)
        if oc is None:
            continue
        close = oc.get("close")
        if close is None or close <= 0:
            continue
        iv = implied_volatility_safe(
            option_price=float(close),
            underlying=spot,
            strike=strike,
            days_to_expiry=dte,
            risk_free_rate=risk_free_rate,
            is_call=is_call,
        )
        if not (iv > 0):  # NaN or 0
            continue

        delta = black_scholes_delta(
            underlying=spot,
            strike=strike,
            time_to_expiry=dte / 365.0,
            risk_free_rate=risk_free_rate,
            volatility=iv,
            is_call=is_call,
        )
        delta_diff = abs(delta - target_delta)

        resolved = ResolvedOption(
            ticker=ct,
            underlying=underlying,
            strike=strike,
            expiration=chosen_expiry,
            contract_type=contract_type,
            as_of_date=as_of,
            days_to_expiry=dte,
            underlying_price=spot,
            option_close=float(close),
            implied_volatility=iv,
        )
        if best is None or delta_diff < best[0]:
            best = (delta_diff, resolved)

    return best[1] if best is not None else None
