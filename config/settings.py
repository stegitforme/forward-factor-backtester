"""
Centralized settings for the Forward Factor backtester.

Every magic number that affects results lives here. If you find yourself
wanting to tweak a number elsewhere in the codebase, move it here first.
This is the single source of truth for backtest parameters.
"""
from dataclasses import dataclass, field
from datetime import date


# ============================================================================
# DATE RANGES
# ============================================================================

# Polygon Options Advanced provides 5+ years history; we use 2022-05-02
# as start because that's what Developer ($79) would also support, ensuring
# the backtest is reproducible after we downgrade.
BACKTEST_START_DATE: date = date(2022, 5, 2)
BACKTEST_END_DATE: date = date(2026, 5, 1)

# Author's video claims 19 years of data. We'd need OptionMetrics IvyDB
# (institutional, ~$10K+/yr) to replicate that. The 2022-2026 window is
# the most demanding regime test (2022 bear + 2023 recovery + 2024 vol spike)
# and is what we actually need to make a capital allocation decision.


# ============================================================================
# CAPITAL & SIZING (per his video, quarter Kelly recommended)
# ============================================================================

INITIAL_CAPITAL: float = 200_000.0   # USD
RISK_PER_TRADE: float = 0.04         # 4% of equity as max debit per trade
MAX_CONCURRENT_POSITIONS: int = 12   # Per-name diversification cap
KELLY_FRACTION: float = 0.25         # Quarter Kelly per his recommendation


# ============================================================================
# FORWARD FACTOR PARAMETERS
# ============================================================================

# Per the video: "if FF >= 0.20 the setup is typically tradable"
# We test sensitivity at 0.15, 0.20, 0.25, 0.30 in the robustness sweep.
FF_THRESHOLD: float = 0.20

# DTE buffer: video allows ±5 day tolerance around target
DTE_BUFFER_DAYS: int = 5

# Simplified to single cell per user decision: 60-90 ATM call calendar only
DTE_PAIRS: list[tuple[int, int]] = [
    (60, 90),
]

STRUCTURES: list[str] = [
    "atm_call_calendar",      # Sell front ATM call, buy back ATM call
]


# ============================================================================
# UNIVERSE
# ============================================================================

# His criterion: 20-day average option volume > 10K contracts/day
UNIVERSE_MIN_DAILY_OPTION_VOLUME: int = 10_000
UNIVERSE_VOLUME_LOOKBACK_DAYS: int = 20
UNIVERSE_MAX_TICKERS: int = 100      # Top N by volume
UNIVERSE_REFRESH_DAYS: int = 30      # How often to recompute universe membership

# Excluded: leveraged ETFs, inverse ETFs, low-quality ADRs
EXCLUDED_TICKERS: set[str] = {
    "TQQQ", "SQQQ", "TNA", "TZA", "SOXL", "SOXS",  # Leveraged ETFs
    "UVXY", "VXX", "SVXY",                          # VIX products
}


# ============================================================================
# EXECUTION ASSUMPTIONS (realistic, conservative)
# ============================================================================

# Slippage on multi-leg spread fills (% of mid)
# Reference: ORATS uses 56% of bid-ask. We use 5% slippage on debit which is
# similar order of magnitude for liquid names.
SLIPPAGE_PCT: float = 0.05

# Per-contract commission both legs both sides
COMMISSION_PER_CONTRACT: float = 0.65   # Tradier rate

# Capacity cap: don't take more than X% of an option's daily volume
CAPACITY_PCT_OF_VOLUME: float = 0.05

# Exit timing: close T-N days before front expiry to avoid pin risk
EXIT_DAYS_BEFORE_FRONT_EXPIRY: int = 1


# ============================================================================
# EARNINGS FILTER (his "for simplicity, avoid earnings altogether")
# ============================================================================

# Skip if earnings event lies between today and the SECOND expiry
EARNINGS_LOOKAHEAD_DAYS: int = 95   # = max DTE2 + small buffer

# Minimum days between entry and earnings to allow trade
EARNINGS_BUFFER_DAYS: int = 4


# ============================================================================
# BENCHMARKS
# ============================================================================

@dataclass(frozen=True)
class TQQQConfig:
    """TQQQ/SGOV volatility-targeting benchmark (the user's existing strategy)."""
    vol_target: float = 0.35           # 35% annualized vol
    realized_vol_lookback: int = 20    # 20 trading days
    rebalance_weekday: int = 0         # 0=Monday (rebalance Monday on Friday signal)
    guard_ma_days: int = 200           # QQQ 200d MA guard
    cash_ticker: str = "BIL"           # SGOV before 2020 has limited data


TQQQ_CONFIG = TQQQConfig()


BENCHMARK_TICKERS: list[str] = ["SPY", "QQQ", "TQQQ", "BIL"]


# ============================================================================
# DATA SOURCE
# ============================================================================

POLYGON_BASE_URL: str = "https://api.polygon.io"

# Cache TTL for different endpoint types (seconds)
CACHE_TTL_REFERENCE: int = 86400 * 30   # Tickers list, contract specs (30 days)
CACHE_TTL_HISTORICAL: int = 86400 * 365 # Historical prices/IVs (1 year — they don't change)
CACHE_TTL_RECENT: int = 3600            # Within last week (1 hour)


# ============================================================================
# OUTPUT
# ============================================================================

OUTPUT_DIR: str = "output"
DASHBOARD_FILENAME: str = "comparison_dashboard.html"
EQUITY_CURVE_CSV: str = "equity_curves.csv"
TRADES_CSV: str = "trade_log.csv"
METRICS_CSV: str = "summary_metrics.csv"
