"""
Performance metrics for the Forward Factor backtester.

Computes the standard hedge-fund performance statistics from an equity curve:

  - CAGR (compound annual growth rate)
  - Volatility (annualized)
  - Sharpe ratio (rf=0 for simplicity; can pass rf if needed)
  - Sortino ratio (downside-only volatility denominator)
  - Calmar ratio (CAGR / Max DD)
  - Max drawdown
  - Win rate (from trade log)
  - Average win / average loss

Also provides regime-segmented metrics: 2022 bear, 2023 recovery,
2024 vol spike, etc., so we can verify the strategy's diversification
claims.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class PerformanceMetrics:
    """All-in-one performance summary for a strategy or benchmark."""
    cagr: float
    volatility: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float           # negative number, e.g. -0.18 for -18%
    max_drawdown_duration_days: int
    total_return: float           # ending equity / starting equity - 1
    n_trades: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    payoff_ratio: float           # avg_win / avg_loss
    start_date: date
    end_date: date

    def to_dict(self) -> dict:
        return asdict(self)


def compute_returns(equity_curve: pd.Series) -> pd.Series:
    """
    Compute daily simple returns from an equity curve.
    Filters out the first NaN to keep the series clean.
    """
    return equity_curve.pct_change().dropna()


def compute_cagr(equity_curve: pd.Series) -> float:
    """
    Compound annual growth rate. Uses the calendar duration between
    first and last data points, not trading days.
    """
    if len(equity_curve) < 2:
        return 0.0
    start_val = equity_curve.iloc[0]
    end_val = equity_curve.iloc[-1]
    if start_val <= 0:
        return 0.0

    days = (equity_curve.index[-1] - equity_curve.index[0]).days
    if days <= 0:
        return 0.0
    years = days / 365.25
    return (end_val / start_val) ** (1 / years) - 1


def compute_volatility(returns: pd.Series, annualize: bool = True) -> float:
    """Annualized standard deviation of daily returns."""
    if len(returns) < 2:
        return 0.0
    daily_std = returns.std()
    if annualize:
        return daily_std * np.sqrt(TRADING_DAYS_PER_YEAR)
    return daily_std


def compute_sharpe(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """
    Annualized Sharpe ratio.

    risk_free_rate is the daily risk-free rate (e.g. 0.0001 for ~2.5%/yr).
    Default 0 for simplicity since we're comparing strategies, not absolute.
    """
    if len(returns) < 2:
        return 0.0
    excess = returns - risk_free_rate
    if excess.std() == 0:
        return 0.0
    return (excess.mean() / excess.std()) * np.sqrt(TRADING_DAYS_PER_YEAR)


def compute_sortino(returns: pd.Series, mar: float = 0.0) -> float:
    """
    Sortino ratio: like Sharpe but only penalizes downside volatility.
    mar = minimum acceptable return (default 0, meaning negative returns count).
    """
    if len(returns) < 2:
        return 0.0
    excess = returns - mar
    downside = excess[excess < 0]
    if len(downside) == 0 or downside.std() == 0:
        return 0.0
    return (excess.mean() / downside.std()) * np.sqrt(TRADING_DAYS_PER_YEAR)


def compute_max_drawdown(equity_curve: pd.Series) -> tuple[float, int]:
    """
    Maximum drawdown as a fraction (returned as a NEGATIVE number),
    plus the longest drawdown duration in days.

    Returns (max_dd, max_dd_duration_days).
    """
    if len(equity_curve) < 2:
        return (0.0, 0)

    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    max_dd = drawdown.min()

    # Compute longest underwater duration
    underwater = drawdown < 0
    if not underwater.any():
        return (float(max_dd), 0)

    # Find consecutive runs of underwater days
    longest_run = 0
    current_run = 0
    for is_underwater in underwater:
        if is_underwater:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0

    return (float(max_dd), longest_run)


def compute_calmar(equity_curve: pd.Series) -> float:
    """Calmar ratio = CAGR / |Max DD|."""
    cagr = compute_cagr(equity_curve)
    max_dd, _ = compute_max_drawdown(equity_curve)
    if max_dd == 0:
        return 0.0
    return cagr / abs(max_dd)


def compute_trade_stats(trade_log: pd.DataFrame, pnl_col: str = "pnl_total") -> dict:
    """
    Compute win rate, avg win, avg loss, payoff ratio from a trade log.

    Args:
        trade_log: DataFrame with one row per trade. Open trades have
            pnl_col = NaN (they're filtered out here so only closed
            round-trips are counted).
        pnl_col: Column containing per-trade P&L.
    """
    if trade_log.empty or pnl_col not in trade_log.columns:
        return {
            "n_trades": 0,
            "win_rate": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "payoff_ratio": 0.0,
        }

    # Filter to only closed trades (pnl is set, not NaN)
    closed = trade_log[trade_log[pnl_col].notna()]
    if closed.empty:
        return {
            "n_trades": 0,
            "win_rate": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "payoff_ratio": 0.0,
        }

    pnls = closed[pnl_col].astype(float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    win_rate = len(wins) / len(pnls) if len(pnls) > 0 else 0.0
    avg_win = wins.mean() if len(wins) > 0 else 0.0
    avg_loss = abs(losses.mean()) if len(losses) > 0 else 0.0

    # If P&L is in dollars, convert to fraction using debit if available
    if "entry_debit" in closed.columns and "contracts" in closed.columns:
        debit_dollars = closed["entry_debit"] * closed["contracts"] * 100
        pct_returns = pnls / debit_dollars
        avg_win_pct = pct_returns[pct_returns > 0].mean() if (pct_returns > 0).any() else 0.0
        avg_loss_pct = abs(pct_returns[pct_returns < 0].mean()) if (pct_returns < 0).any() else 0.0
    else:
        avg_win_pct = avg_win
        avg_loss_pct = avg_loss

    payoff_ratio = avg_win_pct / avg_loss_pct if avg_loss_pct > 0 else 0.0

    return {
        "n_trades": len(pnls),
        "win_rate": float(win_rate),
        "avg_win_pct": float(avg_win_pct),
        "avg_loss_pct": float(avg_loss_pct),
        "payoff_ratio": float(payoff_ratio),
    }


def compute_metrics(
    equity_curve: pd.Series,
    trade_log: Optional[pd.DataFrame] = None,
) -> PerformanceMetrics:
    """
    Compute the full performance metrics suite from an equity curve and
    optional trade log.
    """
    if len(equity_curve) < 2:
        return PerformanceMetrics(
            cagr=0.0, volatility=0.0, sharpe=0.0, sortino=0.0, calmar=0.0,
            max_drawdown=0.0, max_drawdown_duration_days=0,
            total_return=0.0, n_trades=0, win_rate=0.0,
            avg_win_pct=0.0, avg_loss_pct=0.0, payoff_ratio=0.0,
            start_date=date.today(), end_date=date.today(),
        )

    returns = compute_returns(equity_curve)
    cagr = compute_cagr(equity_curve)
    vol = compute_volatility(returns)
    sharpe = compute_sharpe(returns)
    sortino = compute_sortino(returns)
    max_dd, max_dd_dur = compute_max_drawdown(equity_curve)
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0.0

    total_return = float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1)

    if trade_log is not None and not trade_log.empty:
        trade_stats = compute_trade_stats(trade_log)
    else:
        trade_stats = {
            "n_trades": 0, "win_rate": 0.0,
            "avg_win_pct": 0.0, "avg_loss_pct": 0.0, "payoff_ratio": 0.0,
        }

    start = equity_curve.index[0]
    end = equity_curve.index[-1]

    return PerformanceMetrics(
        cagr=cagr,
        volatility=vol,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        max_drawdown=max_dd,
        max_drawdown_duration_days=max_dd_dur,
        total_return=total_return,
        n_trades=trade_stats["n_trades"],
        win_rate=trade_stats["win_rate"],
        avg_win_pct=trade_stats["avg_win_pct"],
        avg_loss_pct=trade_stats["avg_loss_pct"],
        payoff_ratio=trade_stats["payoff_ratio"],
        start_date=start.date() if isinstance(start, pd.Timestamp) else start,
        end_date=end.date() if isinstance(end, pd.Timestamp) else end,
    )


# ============================================================================
# Regime breakdown
# ============================================================================

# Defined regimes for 2022-2026 backtest window
REGIMES: dict[str, tuple[date, date]] = {
    "2022_bear":          (date(2022, 5, 2),  date(2022, 12, 31)),
    "2023_recovery":      (date(2023, 1, 1),  date(2023, 12, 31)),
    "2024_full_year":     (date(2024, 1, 1),  date(2024, 12, 31)),
    "2025_full_year":     (date(2025, 1, 1),  date(2025, 12, 31)),
    "2026_ytd":           (date(2026, 1, 1),  date(2026, 5, 1)),
}


def compute_regime_metrics(
    equity_curve: pd.Series,
    regimes: Optional[dict[str, tuple[date, date]]] = None,
) -> dict[str, PerformanceMetrics]:
    """
    Compute metrics for each regime separately.

    Returns dict of regime_name -> PerformanceMetrics.
    """
    if regimes is None:
        regimes = REGIMES

    out = {}
    for name, (start, end) in regimes.items():
        mask = (equity_curve.index >= pd.Timestamp(start)) & (equity_curve.index <= pd.Timestamp(end))
        regime_curve = equity_curve[mask]
        if len(regime_curve) >= 2:
            out[name] = compute_metrics(regime_curve)
    return out


def compare_strategies(
    strategy_curves: dict[str, pd.Series],
    trade_logs: Optional[dict[str, pd.DataFrame]] = None,
) -> pd.DataFrame:
    """
    Build a side-by-side comparison table of multiple strategies.

    Args:
        strategy_curves: dict of strategy_name -> equity_curve Series.
        trade_logs:      dict of strategy_name -> trade_log DataFrame (optional).

    Returns DataFrame indexed by strategy with metric columns.
    """
    rows = []
    for name, curve in strategy_curves.items():
        log = (trade_logs or {}).get(name)
        m = compute_metrics(curve, log)
        d = m.to_dict()
        d["strategy"] = name
        rows.append(d)
    df = pd.DataFrame(rows).set_index("strategy")

    # Friendly column ordering
    col_order = [
        "cagr", "total_return", "volatility", "sharpe", "sortino", "calmar",
        "max_drawdown", "max_drawdown_duration_days",
        "n_trades", "win_rate", "avg_win_pct", "avg_loss_pct", "payoff_ratio",
        "start_date", "end_date",
    ]
    return df[[c for c in col_order if c in df.columns]]


def correlation_matrix(strategy_returns: dict[str, pd.Series]) -> pd.DataFrame:
    """
    Compute the correlation matrix of daily returns across strategies.

    Useful for verifying that the FF cells diversify against each other
    (target: 0.4-0.85 cross-correlation per our criteria).
    """
    df = pd.DataFrame(strategy_returns)
    return df.corr()
