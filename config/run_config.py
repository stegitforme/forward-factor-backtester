"""RunConfig — canonical, hashable configuration for a simulation run.

Every parameter that affects the trade log lives here. Two simulations with
the same RunConfig hash produce byte-identical (modulo non-determinism)
trade logs. This is the foundation of experiment isolation.

The hash deterministically maps RunConfig -> output directory:
  output/sim_<config_hash>/
    config.json           # the RunConfig used (round-trips)
    trade_log.csv         # produced trades
    daily_mtm_equity.csv  # daily MTM curve per cell + combined
    metrics.json          # summary stats
    provenance.json       # discovery_run_id, git commit, timestamps
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, fields
from typing import Optional, Union


@dataclass(frozen=True)
class RunConfig:
    """All knobs that affect a simulation outcome.

    Position caps:
      Each cap_* parameter can be None to disable that cap. All active caps
      are enforced simultaneously: contracts = min(kelly, *active_caps).
    """
    # === Strategy parameters ===
    cells: tuple[tuple[str, int, int], ...] = (
        ("30_90_atm", 30, 90),
        ("60_90_atm", 60, 90),
    )  # (cell_name, dte_front, dte_back)
    structure: str = "atm_call_calendar"
    ff_threshold: Union[float, dict[str, float]] = 0.20
    dte_buffer_days: int = 5

    # === Sizing ===
    initial_capital_per_cell: float = 200_000.0
    risk_per_trade: float = 0.04
    kelly_fraction: float = 0.25
    max_concurrent_positions: int = 12

    # === Position caps (Phase 3 refactor; per-cell-initial NAV scope) ===
    # NAV used in caps 2 and 3 = initial_capital_per_cell (FIXED; does not grow)
    position_cap_contracts: Optional[int] = 500
    position_cap_contracts_per_ticker_cell: Optional[int] = 1000
    position_cap_nav_pct: Optional[float] = 0.02
    debit_floor: float = 0.10
    position_cap_strike_mtm: Optional[float] = 0.02
    strike_width_floor: float = 2.50

    # === Cross-cell caps (Phase 5 stable-version; combined-strategy NAV scope) ===
    # NAV used in these caps = initial_capital_per_cell × len(cells), FIXED.
    # Position cap per ticker = sum of debit_total across ALL open positions
    # (across all cells) for that ticker, capped at this fraction of strategy NAV.
    # Asset-class caps work the same way but aggregate by class via asset_class_map.
    # Both default to None (disabled); stable-version config sets them.
    position_cap_per_ticker_nav_pct: Optional[float] = None
    asset_class_caps: Optional[dict] = None       # {class_name: pct_of_NAV}
    asset_class_map: Optional[dict] = None        # {ticker: class_name}

    # === Execution ===
    slippage_pct: float = 0.05
    commission_per_contract: float = 0.65
    exit_days_before_front_expiry: int = 1

    # === Vol-targeting (Phase 3.5) ===
    # If vol_target_annualized is None, vol-targeting is disabled (scale = 1.0 always).
    # Otherwise: scale = vol_target_annualized / realized_vol(trailing N days),
    # clipped to [vol_target_min_scale, vol_target_max_scale].
    # Applied to Kelly contracts BEFORE per-trade caps. Existing positions
    # are not resized; new-entry scaling only.
    vol_target_annualized: Optional[float] = None
    vol_target_lookback_days: int = 30
    vol_target_min_scale: float = 0.25
    vol_target_max_scale: float = 1.0

    # === Earnings filter policy ===
    earnings_filter_enabled: bool = True
    earnings_buffer_days: int = 4

    # === Run window ===
    start_date: str = "2022-01-03"   # ISO
    end_date: str = "2026-04-30"

    # === Universe (sorted tuple for hash stability) ===
    universe: tuple[str, ...] = (
        "SPY", "IWM", "SMH", "XBI", "KWEB", "TLT", "MSTR",
        "KRE", "KBE", "XLF", "IBB", "ARKK", "COIN", "AMD",
        "META", "GOOGL", "JPM",
    )

    def to_dict(self) -> dict:
        """Canonical dict representation. Tuples → lists, dicts sorted."""
        d = asdict(self)
        # Normalize cells (tuple of tuples → list of lists)
        d["cells"] = [list(c) for c in self.cells]
        d["universe"] = sorted(self.universe)
        if isinstance(self.ff_threshold, dict):
            d["ff_threshold"] = dict(sorted(self.ff_threshold.items()))
        # Sort the new optional dicts so hashing is stable
        if isinstance(self.asset_class_caps, dict):
            d["asset_class_caps"] = dict(sorted(self.asset_class_caps.items()))
        if isinstance(self.asset_class_map, dict):
            d["asset_class_map"] = dict(sorted(self.asset_class_map.items()))
        return d

    def to_json(self) -> str:
        """Canonical JSON: sorted keys, no whitespace ambiguity."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def hash(self) -> str:
        """SHA256 of canonical JSON. Stable across runs and machines."""
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    def short_hash(self, n: int = 12) -> str:
        return self.hash()[:n]

    @classmethod
    def from_dict(cls, d: dict) -> "RunConfig":
        """Round-trip from to_dict / JSON. Re-tuples lists where needed."""
        d = dict(d)  # copy
        d["cells"] = tuple(tuple(c) for c in d.get("cells", []))
        d["universe"] = tuple(d.get("universe", []))
        return cls(**d)

    @classmethod
    def from_json(cls, s: str) -> "RunConfig":
        return cls.from_dict(json.loads(s))


def cap_disabled(value) -> bool:
    """A cap is disabled if it's None, math.inf, or sentinel."""
    return value is None or (isinstance(value, float) and math.isinf(value))
