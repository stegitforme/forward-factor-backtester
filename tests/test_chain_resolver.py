"""
Tests for the chain resolver.

Uses a mocked Polygon client so we can verify the logic of:
  - DTE matching with buffer
  - ATM strike selection
  - 35-delta strike selection (via IV inversion)
  - Failure handling when data is missing
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.chain_resolver import (
    ResolvedOption,
    resolve_atm_option,
    resolve_delta_option,
)
from src.iv_solver import black_scholes_price


def _build_mock_client_for_chain(
    underlying: str,
    spot: float,
    strikes: list[float],
    expiry: date,
    sigma: float = 0.30,
    risk_free_rate: float = 0.04,
    dte: int = 30,
):
    """
    Build a mock Polygon client that returns:
      - A list of contracts at given strikes for the expiry
      - Black-Scholes-priced closes for each contract on a given date
      - Underlying price = spot
    """
    client = MagicMock()

    # list_options_contracts -> DataFrame with the strikes
    contracts = pd.DataFrame({
        "ticker": [f"O:{underlying}{expiry.strftime('%y%m%d')}C{int(s*1000):08d}"
                   for s in strikes],
        "strike_price": strikes,
        "expiration_date": [expiry] * len(strikes),
        "contract_type": ["call"] * len(strikes),
        "underlying_ticker": [underlying] * len(strikes),
    })
    client.list_options_contracts.return_value = contracts

    # get_daily_bars for underlying -> single-row df with close=spot
    def daily_bars(ticker, start, end):
        if ticker == underlying:
            return pd.DataFrame({
                "close": [spot, spot, spot],
            }, index=pd.date_range(end=date.today(), periods=3))
        return pd.DataFrame()
    client.get_daily_bars.side_effect = daily_bars

    # _get for /v1/open-close -> BS price
    def _get(path, ttl_seconds=None):
        # path looks like /v1/open-close/O:AAPL.../2022-05-02
        if "/open-close/" not in path:
            return {}
        parts = path.split("/")
        ct = parts[3]
        # Find the strike from the ticker
        # Ticker format: O:AAPL220617C00150000 -> last 8 chars * .001
        strike_str = ct[-8:]
        strike = int(strike_str) / 1000.0

        T = dte / 365.0
        price = black_scholes_price(
            underlying=spot, strike=strike, time_to_expiry=T,
            risk_free_rate=risk_free_rate, volatility=sigma, is_call=True,
        )
        return {"status": "OK", "close": price, "open": price, "high": price, "low": price}

    client._get = MagicMock(side_effect=_get)
    return client


class TestResolveATMOption:
    def test_picks_strike_closest_to_spot(self):
        """Among strikes 95, 100, 105 with spot=101, must pick 100."""
        as_of = date(2026, 5, 1)
        expiry = as_of + timedelta(days=30)
        client = _build_mock_client_for_chain(
            "AAPL", spot=101.0, strikes=[95, 100, 105],
            expiry=expiry, sigma=0.30, dte=30,
        )

        result = resolve_atm_option(
            client, "AAPL", as_of, target_dte=30, contract_type="call",
        )
        assert result is not None
        assert result.strike == 100.0
        assert result.underlying_price == 101.0
        # IV should round-trip near 0.30 (allow some Newton-Raphson tolerance)
        assert abs(result.implied_volatility - 0.30) < 0.01

    def test_returns_none_when_no_contracts(self):
        client = MagicMock()
        client.list_options_contracts.return_value = pd.DataFrame()
        client.get_daily_bars.return_value = pd.DataFrame()
        result = resolve_atm_option(client, "AAPL", date(2026, 5, 1), 30)
        assert result is None

    def test_returns_none_when_no_underlying_price(self):
        as_of = date(2026, 5, 1)
        expiry = as_of + timedelta(days=30)
        client = _build_mock_client_for_chain("AAPL", 100, [95, 100, 105], expiry)
        # Override daily_bars to return empty
        client.get_daily_bars.side_effect = lambda *a, **k: pd.DataFrame()
        result = resolve_atm_option(client, "AAPL", as_of, 30)
        assert result is None

    def test_iv_matches_round_trip(self):
        """The whole point: feed BS-priced contracts in, get the same IV out."""
        as_of = date(2026, 5, 1)
        expiry = as_of + timedelta(days=45)
        sigma = 0.42
        client = _build_mock_client_for_chain(
            "TSLA", spot=200.0, strikes=[180, 190, 200, 210, 220],
            expiry=expiry, sigma=sigma, dte=45,
        )
        result = resolve_atm_option(client, "TSLA", as_of, target_dte=45)
        assert result is not None
        assert abs(result.implied_volatility - sigma) < 0.01

    def test_dte_buffer_widens_search(self):
        """If exact target DTE is not available, picks within buffer."""
        as_of = date(2026, 5, 1)
        # Expiry 32 days out; target=30, buffer=5 -> should match
        expiry = as_of + timedelta(days=32)
        client = _build_mock_client_for_chain(
            "AAPL", 100, [100], expiry=expiry, sigma=0.30, dte=32,
        )
        result = resolve_atm_option(
            client, "AAPL", as_of, target_dte=30, buffer_days=5,
        )
        assert result is not None
        assert result.days_to_expiry == 32


class TestResolveDeltaOption:
    def test_picks_strike_closest_to_target_delta(self):
        """For target_delta=0.35 call, expects an OTM strike."""
        as_of = date(2026, 5, 1)
        expiry = as_of + timedelta(days=30)
        sigma = 0.30
        # Strikes: 100 (ATM, ~50d), 105 (~30d), 110 (~10d)
        client = _build_mock_client_for_chain(
            "AAPL", spot=100, strikes=[95, 100, 105, 110],
            expiry=expiry, sigma=sigma, dte=30,
        )
        result = resolve_delta_option(
            client, "AAPL", as_of, target_dte=30,
            target_delta=0.35, contract_type="call",
        )
        assert result is not None
        # Picked strike should give delta closest to 0.35
        # For the synthetic data, 105 should have delta ~0.35
        assert result.strike in [100.0, 105.0]


class TestResolveOptionFailureModes:
    def test_zero_close_returns_none(self):
        """If contract close is 0 (or missing), skip."""
        client = MagicMock()
        client.list_options_contracts.return_value = pd.DataFrame({
            "ticker": ["O:AAPL260601C00100000"],
            "strike_price": [100.0],
            "expiration_date": [date(2026, 6, 1)],
            "contract_type": ["call"],
        })
        client.get_daily_bars.return_value = pd.DataFrame({
            "close": [100.0],
        }, index=pd.date_range(end=date(2026, 5, 1), periods=1))
        client._get.return_value = {"status": "OK", "close": 0}

        result = resolve_atm_option(client, "AAPL", date(2026, 5, 1), 30)
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
