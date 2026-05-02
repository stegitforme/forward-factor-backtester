"""
Black-Scholes implied volatility solver.

Polygon Options Advanced doesn't return historical IV in its REST API
(snapshot is live-only, and the day field on the snapshot endpoint comes
back empty for our tier on most contracts). So we compute IV ourselves
from the option's mid price using Black-Scholes inversion.

Standard approach: Newton-Raphson with vega for fast convergence, with
Brent's method as a fallback for edge cases. About 8-15 iterations
usually nails IV to 1e-6 accuracy.

Inputs we need:
  - option_price:  the contract's mid price (or close)
  - underlying:    the stock's spot price
  - strike:        the option's strike
  - time_to_expiry: in YEARS (calendar days / 365)
  - risk_free_rate: annualized, decimal (e.g. 0.04 for 4%)
  - is_call:       True for calls, False for puts
  - dividend_yield: optional, default 0

Returns NaN for unsolvable inputs:
  - Price below intrinsic (arb)
  - Price above max possible (call cannot exceed spot)
  - Time-to-expiry too short or zero
  - Newton/Brent fails to converge

Tested against published values from CBOE white papers and Hull textbook
problems.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq


SQRT_2PI = math.sqrt(2 * math.pi)


def black_scholes_price(
    underlying: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    is_call: bool = True,
    dividend_yield: float = 0.0,
) -> float:
    """
    Black-Scholes price of a European option (used for both pricing and as
    the inner function for IV inversion).

    Returns the theoretical fair-value price.
    """
    if time_to_expiry <= 0 or volatility <= 0:
        # At-expiry intrinsic
        if is_call:
            return max(underlying - strike, 0.0)
        return max(strike - underlying, 0.0)

    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(underlying / strike) + (risk_free_rate - dividend_yield + 0.5 * volatility ** 2) * time_to_expiry) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t

    discount = math.exp(-risk_free_rate * time_to_expiry)
    div_discount = math.exp(-dividend_yield * time_to_expiry)

    if is_call:
        return underlying * div_discount * norm.cdf(d1) - strike * discount * norm.cdf(d2)
    return strike * discount * norm.cdf(-d2) - underlying * div_discount * norm.cdf(-d1)


def black_scholes_vega(
    underlying: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    dividend_yield: float = 0.0,
) -> float:
    """
    Vega: dPrice/dVolatility. Used by Newton-Raphson for fast IV inversion.
    """
    if time_to_expiry <= 0 or volatility <= 0:
        return 0.0
    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(underlying / strike) + (risk_free_rate - dividend_yield + 0.5 * volatility ** 2) * time_to_expiry) / (volatility * sqrt_t)
    div_discount = math.exp(-dividend_yield * time_to_expiry)
    return underlying * div_discount * sqrt_t * norm.pdf(d1)


def black_scholes_delta(
    underlying: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    volatility: float,
    is_call: bool = True,
    dividend_yield: float = 0.0,
) -> float:
    """Delta: dPrice/dUnderlying. Used to find 35-delta strikes."""
    if time_to_expiry <= 0 or volatility <= 0:
        if is_call:
            return 1.0 if underlying > strike else 0.0
        return -1.0 if underlying < strike else 0.0

    sqrt_t = math.sqrt(time_to_expiry)
    d1 = (math.log(underlying / strike) + (risk_free_rate - dividend_yield + 0.5 * volatility ** 2) * time_to_expiry) / (volatility * sqrt_t)
    div_discount = math.exp(-dividend_yield * time_to_expiry)
    if is_call:
        return div_discount * norm.cdf(d1)
    return div_discount * (norm.cdf(d1) - 1.0)


def implied_volatility(
    option_price: float,
    underlying: float,
    strike: float,
    time_to_expiry: float,
    risk_free_rate: float,
    is_call: bool = True,
    dividend_yield: float = 0.0,
    initial_guess: float = 0.3,
    max_iter: int = 50,
    tolerance: float = 1e-6,
) -> float:
    """
    Solve for implied volatility given an observed option price.

    Returns NaN if:
      - inputs are degenerate (negative price, zero time, etc.)
      - price is below intrinsic value (arb)
      - price is above the no-arb upper bound
      - solver fails to converge
    """
    # Degenerate input checks
    if option_price <= 0 or underlying <= 0 or strike <= 0:
        return float("nan")
    if time_to_expiry <= 1.0 / 365.0:  # less than 1 day
        return float("nan")

    # Check arb bounds
    intrinsic = max(underlying - strike, 0.0) if is_call else max(strike - underlying, 0.0)
    if option_price < intrinsic - 0.01:  # small tolerance for rounding
        return float("nan")

    # Upper bound: call <= spot, put <= strike (under no-div assumption)
    if is_call and option_price > underlying:
        return float("nan")
    if not is_call and option_price > strike:
        return float("nan")

    # Newton-Raphson
    sigma = initial_guess
    for _ in range(max_iter):
        try:
            price = black_scholes_price(
                underlying, strike, time_to_expiry, risk_free_rate,
                sigma, is_call, dividend_yield,
            )
            diff = price - option_price
            if abs(diff) < tolerance:
                return sigma
            vega = black_scholes_vega(
                underlying, strike, time_to_expiry, risk_free_rate,
                sigma, dividend_yield,
            )
            if vega < 1e-10:
                # Vega too small — fall back to brent
                break
            sigma_new = sigma - diff / vega
            # Safeguards: keep sigma in (0.001, 5.0)
            if sigma_new < 0.001:
                sigma_new = 0.001
            if sigma_new > 5.0:
                sigma_new = 5.0
            if abs(sigma_new - sigma) < tolerance:
                return sigma_new
            sigma = sigma_new
        except (ValueError, ZeroDivisionError, OverflowError):
            break

    # Fall back to Brent's method on a wide bracket
    def f(sig):
        return black_scholes_price(
            underlying, strike, time_to_expiry, risk_free_rate,
            sig, is_call, dividend_yield,
        ) - option_price

    try:
        # Need f(low) and f(high) to have opposite signs
        f_low = f(0.001)
        f_high = f(5.0)
        if f_low * f_high > 0:
            return float("nan")
        return brentq(f, 0.001, 5.0, xtol=tolerance, maxiter=100)
    except (ValueError, RuntimeError):
        return float("nan")


def implied_volatility_safe(
    option_price: float,
    underlying: float,
    strike: float,
    days_to_expiry: int,
    risk_free_rate: float = 0.04,
    is_call: bool = True,
    dividend_yield: float = 0.0,
) -> float:
    """
    Wrapper that takes days-to-expiry instead of years and never raises.

    Returns NaN on any failure. Use this in batch computations where
    individual contract failures shouldn't stop the loop.
    """
    if days_to_expiry <= 0:
        return float("nan")
    try:
        tte_years = days_to_expiry / 365.0
        return implied_volatility(
            option_price, underlying, strike, tte_years,
            risk_free_rate, is_call, dividend_yield,
        )
    except Exception:
        return float("nan")
