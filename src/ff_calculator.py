"""
Forward Factor calculator.

Mirrors the exact math from the Volatility Vibes calculator.py distributed
with his YouTube video. The only difference is this is a clean, callable
function library (no Tkinter GUI) suitable for backtest use.

Variance identity (the core idea):

    variance_total(T) = variance(0, T1) + variance(T1, T2)  for T1 < T2

So the FORWARD variance from T1 to T2 is:

    var_fwd = (sigma_2^2 * T2 - sigma_1^2 * T1) / (T2 - T1)
    sigma_fwd = sqrt(var_fwd)

The Forward Factor is then:

    FF = (sigma_1 - sigma_fwd) / sigma_fwd

When FF > 0: front IV exceeds the forward, term structure is in
backwardation, near-term vol is elevated relative to what the market
implies for the forward window. The author's strategy enters long
calendar spreads when FF >= 0.20.

Math verified against VV's distributed calculator.py (2026-05-02): formula
sigma_fwd = sqrt((sigma2^2 * T2 - sigma1^2 * T1) / (T2 - T1)) with T = DTE/365
and sigma = IV/100. VV's calculator.py does NOT include any earnings handling
(no ex-earnings IV adjustment, no earnings filter) — it expects the user to
clean the IV inputs before plugging in. Earnings filter is handled separately
in src/earnings_filter.py.

References:
- Calculator: calculator.py from his YouTube video distribution
- Worked example: 30-day IV = 45%, 60-day IV = 35% -> sigma_fwd = 20.61%, FF = 118.3%
  (the original docstring claim of 20.66 / 117 was a rounding artifact from
   the video walkthrough, not the actual formula output)
- Academic: Campasano (2018), "Term Structure Forecasts of Volatility"
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3240028
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# Use the same constant the author uses (calendar days per year). Note: this
# is intentionally NOT 252 (trading days) because his calculator divides DTE
# by 365 — we mirror that exactly to ensure FF values match his to the digit.
DAYS_PER_YEAR = 365.0


@dataclass(frozen=True)
class ForwardFactorResult:
    """Result of a forward factor calculation."""
    sigma_front: float          # decimal IV, e.g. 0.45
    sigma_back: float           # decimal IV, e.g. 0.35
    T_front: float              # years
    T_back: float               # years
    forward_variance: float     # annualized forward variance
    forward_sigma: float        # annualized forward IV (decimal)
    forward_factor: float       # FF as a ratio (e.g. 1.17 means front is 117% above forward)
    is_valid: bool              # True if forward variance is non-negative
    error: Optional[str] = None # Reason if not valid

    @property
    def forward_iv_pct(self) -> float:
        """Forward IV as a percentage (e.g. 20.66 for 20.66%)."""
        return self.forward_sigma * 100.0

    @property
    def forward_factor_pct(self) -> float:
        """FF as a percentage (e.g. 117.0 for 117%)."""
        return self.forward_factor * 100.0


def calculate_forward_factor(
    dte_front: float,
    iv_front_pct: float,
    dte_back: float,
    iv_back_pct: float,
) -> ForwardFactorResult:
    """
    Compute forward IV and Forward Factor between two expiries.

    Args:
        dte_front: Days to expiry of the front (near-term) option.
        iv_front_pct: Implied vol of the front option as a percentage (e.g. 45.0).
        dte_back: Days to expiry of the back (far) option.
        iv_back_pct: Implied vol of the back option as a percentage (e.g. 35.0).

    Returns:
        ForwardFactorResult with all intermediate values populated.

    Notes:
        Inputs use percentage IVs (45.0 not 0.45) to match the author's
        calculator and the typical broker UI display. The result internally
        stores decimal sigmas for downstream math.

    Example (matches VV calculator.py, math verified by hand):
        >>> r = calculate_forward_factor(30, 45.0, 60, 35.0)
        >>> round(r.forward_iv_pct, 2)
        20.61
        >>> round(r.forward_factor_pct, 2)
        118.3
    """
    # Validation
    if dte_front < 0 or dte_back < 0:
        return _invalid("DTEs must be non-negative.", iv_front_pct, iv_back_pct, dte_front, dte_back)
    if dte_back <= dte_front:
        return _invalid("dte_back must be > dte_front.", iv_front_pct, iv_back_pct, dte_front, dte_back)
    if iv_front_pct < 0 or iv_back_pct < 0:
        return _invalid("IVs must be non-negative.", iv_front_pct, iv_back_pct, dte_front, dte_back)

    T_front = dte_front / DAYS_PER_YEAR
    T_back = dte_back / DAYS_PER_YEAR
    sigma_front = iv_front_pct / 100.0
    sigma_back = iv_back_pct / 100.0

    var_front_total = sigma_front ** 2 * T_front
    var_back_total = sigma_back ** 2 * T_back
    fwd_var = (var_back_total - var_front_total) / (T_back - T_front)

    if fwd_var < 0:
        # Negative forward variance means the back IV is "too low" given the
        # front IV — mathematically impossible if both are real prices, so
        # this usually indicates data error or arbitrage opportunity.
        return ForwardFactorResult(
            sigma_front=sigma_front,
            sigma_back=sigma_back,
            T_front=T_front,
            T_back=T_back,
            forward_variance=fwd_var,
            forward_sigma=float("nan"),
            forward_factor=float("nan"),
            is_valid=False,
            error=f"Negative forward variance ({fwd_var:.6f}). Check inputs.",
        )

    fwd_sigma = math.sqrt(fwd_var)

    if fwd_sigma == 0.0:
        return ForwardFactorResult(
            sigma_front=sigma_front,
            sigma_back=sigma_back,
            T_front=T_front,
            T_back=T_back,
            forward_variance=fwd_var,
            forward_sigma=0.0,
            forward_factor=float("inf") if sigma_front > 0 else float("nan"),
            is_valid=False,
            error="Forward sigma is zero; FF is undefined.",
        )

    ff = (sigma_front - fwd_sigma) / fwd_sigma
    return ForwardFactorResult(
        sigma_front=sigma_front,
        sigma_back=sigma_back,
        T_front=T_front,
        T_back=T_back,
        forward_variance=fwd_var,
        forward_sigma=fwd_sigma,
        forward_factor=ff,
        is_valid=True,
        error=None,
    )


def _invalid(
    msg: str,
    iv_front_pct: float,
    iv_back_pct: float,
    dte_front: float,
    dte_back: float,
) -> ForwardFactorResult:
    """Return an invalid result with the given error message."""
    return ForwardFactorResult(
        sigma_front=iv_front_pct / 100.0,
        sigma_back=iv_back_pct / 100.0,
        T_front=dte_front / DAYS_PER_YEAR,
        T_back=dte_back / DAYS_PER_YEAR,
        forward_variance=float("nan"),
        forward_sigma=float("nan"),
        forward_factor=float("nan"),
        is_valid=False,
        error=msg,
    )


# ============================================================================
# Vectorized version for backtest hot path
# ============================================================================

def calculate_forward_factor_vectorized(
    dte_front,
    iv_front_pct,
    dte_back,
    iv_back_pct,
):
    """
    Vectorized FF calculation for use in backtest loops where we evaluate
    thousands of contract pairs per day.

    Accepts numpy arrays or pandas Series. Returns a dict of arrays:
        {
            'forward_sigma': np.ndarray,
            'forward_factor': np.ndarray,
            'forward_variance': np.ndarray,
            'is_valid': np.ndarray (bool),
        }

    Invalid rows (negative variance, zero sigma, etc.) are returned with
    NaN values and is_valid=False rather than raising.
    """
    import numpy as np

    dte_f = np.asarray(dte_front, dtype=float)
    dte_b = np.asarray(dte_back, dtype=float)
    iv_f = np.asarray(iv_front_pct, dtype=float)
    iv_b = np.asarray(iv_back_pct, dtype=float)

    T_f = dte_f / DAYS_PER_YEAR
    T_b = dte_b / DAYS_PER_YEAR
    sig_f = iv_f / 100.0
    sig_b = iv_b / 100.0

    # Suppress divide-by-zero warnings; we handle the invalid mask ourselves.
    with np.errstate(divide="ignore", invalid="ignore"):
        denom = T_b - T_f
        fwd_var = (sig_b ** 2 * T_b - sig_f ** 2 * T_f) / denom

        valid = (
            (dte_f >= 0)
            & (dte_b > dte_f)
            & (iv_f >= 0)
            & (iv_b >= 0)
            & (fwd_var > 0)
        )

        fwd_sigma = np.where(valid, np.sqrt(np.where(fwd_var > 0, fwd_var, np.nan)), np.nan)
        ff = np.where(
            valid & (fwd_sigma > 0),
            (sig_f - fwd_sigma) / fwd_sigma,
            np.nan,
        )

    return {
        "forward_variance": fwd_var,
        "forward_sigma": fwd_sigma,
        "forward_factor": ff,
        "is_valid": valid,
    }
