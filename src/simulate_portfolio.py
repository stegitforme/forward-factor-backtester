"""Simulate portfolio: read candidates.parquet, apply RunConfig, produce
trade log + daily MTM equity + metrics + provenance.

Pure mechanics. No Polygon API calls except for exit pricing (re-uses
PolygonClient for re-pricing open positions at exit_date and for daily MTM).

Application order in size_trade:
  1. FF threshold filter (per-cell or uniform)
  2. Earnings-blocked filter
  3. Quarter-Kelly target dollar sizing → kelly_contracts
  4. Position caps:
       cap1a: max contracts per single position
       cap1b: max stacked contracts per (ticker, cell)
       cap2:  debit-floor NAV cap
       cap3:  strike-width MTM cap
  5. contracts = max(0, min(kelly, cap1a, cap1b, cap2, cap3))

NAV scope for caps 2 and 3: per-cell INITIAL capital (FIXED).

Output directory: output/sim_<config_hash>/
  trade_log.csv
  daily_mtm_equity.csv  (date, <cell>, combined)
  metrics.json
  config.json
  provenance.json
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from config.run_config import RunConfig, cap_disabled
from src.data_layer import get_client
from src.trade_simulator import _option_ticker_for_strike, _mid_from_bar, _price_calendar_legs

log = logging.getLogger(__name__)


# ============================================================================
# Position + Portfolio state (lightweight, internal to this module)
# ============================================================================

@dataclass
class _Pos:
    ticker: str; cell: str
    entry_date: date; front_expiry: date; back_expiry: date
    front_strike: float; back_strike: float
    contracts: int
    entry_debit: float          # slipped, per spread
    debit_total: float          # entry_debit * contracts * 100
    ff_at_entry: float


# ============================================================================
# Cap math
# ============================================================================

def _kelly_contracts(equity: float, debit: float, cfg: RunConfig) -> int:
    """Quarter-Kelly contract count (existing logic from src/portfolio.py)."""
    effective_risk = cfg.risk_per_trade * cfg.kelly_fraction
    target_dollar = equity * effective_risk
    per_spread_cost = debit * 100.0
    if per_spread_cost <= 0:
        return 0
    return int(target_dollar // per_spread_cost)


def _cap_debit_floor_nav(nav_per_cell: float, debit: float, cfg: RunConfig) -> Optional[int]:
    """Cap 2: contracts ≤ NAV * pct / (max(debit, floor) * 100)."""
    if cap_disabled(cfg.position_cap_nav_pct):
        return None
    floored_debit = max(debit, cfg.debit_floor)
    return int((nav_per_cell * cfg.position_cap_nav_pct) // (floored_debit * 100.0))


def _cap_strike_mtm(nav_per_cell: float, front_strike: float, back_strike: float, cfg: RunConfig) -> Optional[int]:
    """Cap 3: contracts ≤ NAV * pct / (max(|fK-bK|, floor) * 100)."""
    if cap_disabled(cfg.position_cap_strike_mtm):
        return None
    sw = abs(back_strike - front_strike)
    sw_floored = max(sw, cfg.strike_width_floor)
    return int((nav_per_cell * cfg.position_cap_strike_mtm) // (sw_floored * 100.0))


def _cap_per_ticker_cell(open_positions: list[_Pos], ticker: str, cell: str, cfg: RunConfig) -> Optional[int]:
    """Cap 1b: max stacked contracts per (ticker, cell)."""
    if cap_disabled(cfg.position_cap_contracts_per_ticker_cell):
        return None
    open_contracts = sum(p.contracts for p in open_positions if p.ticker == ticker and p.cell == cell)
    return max(0, cfg.position_cap_contracts_per_ticker_cell - open_contracts)


def _resolve_ff_threshold(cell_name: str, cfg: RunConfig) -> float:
    if isinstance(cfg.ff_threshold, dict):
        return float(cfg.ff_threshold.get(cell_name, 0.20))
    return float(cfg.ff_threshold)


def _vol_target_scale(equity_history: list[float], cfg: RunConfig) -> float:
    """Compute the position-size scale factor based on trailing realized vol of
    the combined MTM equity curve. Returns 1.0 if vol-targeting disabled or
    insufficient history.

    Workflow:
      - Take last vol_target_lookback_days values of equity_history
      - Daily returns = pct_change
      - Realized vol = std(returns) × √252
      - Scale = vol_target_annualized / realized_vol
      - Clip to [vol_target_min_scale, vol_target_max_scale]
    """
    if cap_disabled(cfg.vol_target_annualized):
        return 1.0
    if len(equity_history) < cfg.vol_target_lookback_days + 1:
        return 1.0  # warmup period
    window = equity_history[-(cfg.vol_target_lookback_days + 1):]
    # pct change
    rets = []
    for i in range(1, len(window)):
        prev = window[i - 1]
        if prev > 0:
            rets.append((window[i] - prev) / prev)
    if not rets:
        return 1.0
    n = len(rets)
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / max(n - 1, 1)
    sd = var ** 0.5
    if sd <= 0:
        return cfg.vol_target_max_scale
    realized_ann_vol = sd * (252 ** 0.5)
    raw_scale = cfg.vol_target_annualized / realized_ann_vol
    return max(cfg.vol_target_min_scale, min(cfg.vol_target_max_scale, raw_scale))


def _size(candidate_row: dict, cell_name: str, current_equity: float, nav_per_cell: float,
          open_positions: list[_Pos], cfg: RunConfig, vol_scale: float = 1.0) -> tuple[int, dict]:
    """Apply Kelly × vol_scale + all caps. Returns (contracts, breakdown_dict).

    Uses MID debit (not slipped) for Kelly + caps — matches original
    step_one_day semantics: sizing computed against quoted mid, slippage
    applied only at cash deduction. Steven's KRE example used $0.02 mid,
    confirming caps reference MID debit too.

    Vol-targeting (Phase 3.5): kelly is multiplied by vol_scale BEFORE caps.
    vol_scale = 1.0 disables vol-targeting (default).
    """
    debit_mid = float(candidate_row["estimated_debit"])
    kelly = _kelly_contracts(current_equity, debit_mid, cfg)
    scaled_kelly = int(kelly * vol_scale)
    caps = {"kelly": kelly, "vol_scale": vol_scale, "scaled_kelly": scaled_kelly}

    cap1a = cfg.position_cap_contracts if not cap_disabled(cfg.position_cap_contracts) else None
    cap1b = _cap_per_ticker_cell(open_positions, candidate_row["ticker"], cell_name, cfg)
    cap2 = _cap_debit_floor_nav(nav_per_cell, debit_mid, cfg)
    cap3 = _cap_strike_mtm(nav_per_cell, float(candidate_row["front_strike"]),
                           float(candidate_row["back_strike"]), cfg)

    caps["cap1a_per_position"] = cap1a
    caps["cap1b_per_ticker_cell"] = cap1b
    caps["cap2_debit_floor_nav"] = cap2
    caps["cap3_strike_mtm"] = cap3

    active = [c for c in [scaled_kelly, cap1a, cap1b, cap2, cap3] if c is not None]
    final = max(0, min(active)) if active else 0

    # Identify which constraint bound, in order of application
    binding = "kelly" if vol_scale >= 1.0 else "vol_scale"
    cur = scaled_kelly
    for name, val in [("cap1a", cap1a), ("cap1b", cap1b), ("cap2", cap2), ("cap3", cap3)]:
        if val is not None and val < cur:
            cur = val; binding = name

    caps["final_contracts"] = final
    caps["binding_cap"] = binding
    return final, caps


# ============================================================================
# Exit pricing — re-uses src.trade_simulator helpers
# ============================================================================

def _exit_value_per_spread(client, pos: _Pos, on_date: date, slippage_pct: float) -> Optional[float]:
    legs = _price_calendar_legs(
        client, pos.ticker, pos.front_expiry, pos.back_expiry,
        pos.front_strike, pos.back_strike, "C", on_date,
    )
    if legs is None:
        return None
    fm, bm = legs
    spread = bm - fm
    return spread * (1.0 - slippage_pct) if spread > 0 else spread * (1.0 + slippage_pct)


# ============================================================================
# Main simulation
# ============================================================================

def simulate(candidates_path: str | Path, cfg: RunConfig, output_dir: str | Path,
             discovery_run_id: Optional[str] = None,
             client=None) -> dict:
    """Run the simulation. Writes trade log, daily equity, metrics, provenance.
    Returns the metrics dict.

    `client` parameter (added 2026-05-04 for ORATS work): if None, uses the
    default Polygon client. Pass an OratsBarsClient instance (or any object
    implementing get_option_daily_bars(symbol, start, end)) to run the
    simulator on ORATS data without touching Polygon.
    """
    if client is None:
        client = get_client()
    cands = pd.read_parquet(candidates_path)
    # Date column: may come back as object; normalize to date
    cands["date"] = cands["date"].apply(lambda v: v if isinstance(v, date) else pd.Timestamp(v).date())
    cands["front_expiry"] = cands["front_expiry"].apply(
        lambda v: v if v is None or isinstance(v, date) else pd.Timestamp(v).date()
    )
    cands["back_expiry"] = cands["back_expiry"].apply(
        lambda v: v if v is None or isinstance(v, date) else pd.Timestamp(v).date()
    )

    if discovery_run_id is None and "discovery_run_id" in cands.columns:
        discovery_run_id = str(cands["discovery_run_id"].iloc[0]) if len(cands) > 0 else None

    print(f"[simulate_portfolio] config_hash={cfg.short_hash()}  candidates={len(cands):,}", flush=True)
    print(f"  cells: {[c[0] for c in cfg.cells]}  | initial_capital_per_cell=${cfg.initial_capital_per_cell:,.0f}", flush=True)
    print(f"  caps: cap1a={cfg.position_cap_contracts} cap1b={cfg.position_cap_contracts_per_ticker_cell} "
          f"cap2_pct={cfg.position_cap_nav_pct} cap3_pct={cfg.position_cap_strike_mtm}", flush=True)

    # Date range
    start_d = date.fromisoformat(cfg.start_date)
    end_d = date.fromisoformat(cfg.end_date)
    days = []
    cur = start_d
    while cur <= end_d:
        if cur.weekday() < 5: days.append(cur)
        cur += timedelta(days=1)

    cell_names = [c[0] for c in cfg.cells]
    cell_dte = {c[0]: (c[1], c[2]) for c in cfg.cells}

    # Per-cell portfolio state
    cell_state = {cn: {"cash": cfg.initial_capital_per_cell, "positions": [],
                       "trade_log": [], "realized_pnl": 0.0,
                       "cap_triggers": {"cap1a": 0, "cap1b": 0, "cap2": 0, "cap3": 0, "kelly": 0,
                                         "vol_scale": 0}}
                  for cn in cell_names}

    # Daily equity record (strict — kept for backwards compat)
    daily_equity = {cn: [] for cn in cell_names}
    # Inline daily MTM equity, used for vol-target scale + final reporting
    daily_mtm_per_cell = {cn: [] for cn in cell_names}
    combined_mtm_history: list[float] = []
    daily_dates = []
    daily_vol_scales: list[float] = []  # diagnostic

    # Bars cache for inline MTM (filled lazily on each open)
    bars_cache: dict[str, pd.DataFrame] = {}

    def _ensure_bars(pos: _Pos):
        f = _option_ticker_for_strike(pos.ticker, pos.front_expiry, "C", pos.front_strike)
        b = _option_ticker_for_strike(pos.ticker, pos.back_expiry, "C", pos.back_strike)
        if f not in bars_cache:
            bars_cache[f] = client.get_option_daily_bars(
                f, start_d - timedelta(days=5), pos.front_expiry + timedelta(days=5))
        if b not in bars_cache:
            bars_cache[b] = client.get_option_daily_bars(
                b, start_d - timedelta(days=5), pos.back_expiry + timedelta(days=5))

    def _mtm_per_spread_inline(pos: _Pos, on_day: date) -> Optional[float]:
        f = _option_ticker_for_strike(pos.ticker, pos.front_expiry, "C", pos.front_strike)
        b = _option_ticker_for_strike(pos.ticker, pos.back_expiry, "C", pos.back_strike)
        fb = bars_cache.get(f); bb = bars_cache.get(b)
        if fb is None or bb is None or fb.empty or bb.empty: return None
        target = pd.Timestamp(on_day)
        fi = fb.index.asof(target); bi = bb.index.asof(target)
        if pd.isna(fi) or pd.isna(bi): return None
        fm = _mid_from_bar(fb.loc[fi]); bm = _mid_from_bar(bb.loc[bi])
        if fm is None or bm is None: return None
        spread = bm - fm
        return spread * (1.0 - cfg.slippage_pct) if spread > 0 else spread * (1.0 + cfg.slippage_pct)

    def _eod_cell_mtm(cn: str, d: date) -> float:
        """Compute end-of-day liquidation value for one cell."""
        state = cell_state[cn]
        cell_eq = state["cash"]  # cash already net of entry debits paid
        legs_per_spread = 4 if cfg.structure == "double_calendar_35d" else 2
        for p in state["positions"]:
            comm = cfg.commission_per_contract * legs_per_spread * 2 * p.contracts
            mid = _mtm_per_spread_inline(p, d)
            if mid is None:
                # No bar — use entry_debit as MTM (no unrealized P&L beyond commission drag)
                cell_eq += p.debit_total - comm
            else:
                cell_eq += mid * p.contracts * 100 - comm
        return cell_eq

    t0 = time.time()
    for d in days:
        # Step 1: close positions whose front_expiry <= today + EXIT_DAYS_BEFORE
        exit_threshold = d + timedelta(days=cfg.exit_days_before_front_expiry)
        for cn in cell_names:
            state = cell_state[cn]
            for pos in list(state["positions"]):
                if pos.front_expiry > exit_threshold:
                    continue
                # Re-price at exit
                exit_value = _exit_value_per_spread(client, pos, d, cfg.slippage_pct)
                fallback_used = False
                if exit_value is None:
                    exit_value = pos.entry_debit
                    fallback_used = True
                    log.warning(
                        "Exit pricing unavailable for %s entry=%s strikes=%s/%s exit=%s; "
                        "falling back to entry_debit",
                        pos.ticker, pos.entry_date, pos.front_strike, pos.back_strike, d,
                    )
                legs_per_spread = 4 if cfg.structure == "double_calendar_35d" else 2
                comm = cfg.commission_per_contract * legs_per_spread * 2 * pos.contracts
                exit_proceeds = exit_value * pos.contracts * 100
                pnl = exit_proceeds - pos.debit_total - comm
                state["cash"] += exit_proceeds - comm
                state["realized_pnl"] += pnl
                state["positions"].remove(pos)
                # Update trade log row
                for row in state["trade_log"]:
                    if (row["ticker"] == pos.ticker and row["entry_date"] == pos.entry_date
                            and row["front_strike"] == pos.front_strike
                            and row["exit_date"] is None):
                        row["exit_date"] = d
                        row["exit_value_per_spread"] = exit_value
                        row["pnl_total"] = pnl
                        row["fallback_used"] = fallback_used
                        break

        # Step 1.5: compute vol-target scale based on history through PREVIOUS day.
        # Default 1.0 if disabled or insufficient history.
        vol_scale = _vol_target_scale(combined_mtm_history, cfg)
        daily_vol_scales.append(vol_scale)

        # Step 2: discover this day's candidates (filter from parquet)
        day_rows = cands[cands["date"] == d]
        for cn in cell_names:
            state = cell_state[cn]
            if len(state["positions"]) >= cfg.max_concurrent_positions:
                continue
            cell_rows = day_rows[day_rows["cell"] == cn]
            cell_rows = cell_rows[cell_rows["ff"].notna()]
            if cfg.earnings_filter_enabled:
                cell_rows = cell_rows[~cell_rows["earnings_blocked"]]
            ff_thr = _resolve_ff_threshold(cn, cfg)
            cell_rows = cell_rows[cell_rows["ff"] >= ff_thr]
            cell_rows = cell_rows[cell_rows["estimated_debit"] > 0]
            if cell_rows.empty:
                continue
            # Sort by FF desc; allocate top by capacity
            cell_rows = cell_rows.sort_values("ff", ascending=False)
            for _, candidate in cell_rows.iterrows():
                if len(state["positions"]) >= cfg.max_concurrent_positions:
                    break
                current_equity = state["cash"] + sum(p.debit_total for p in state["positions"])
                contracts, breakdown = _size(candidate, cn, current_equity,
                                              cfg.initial_capital_per_cell,
                                              state["positions"], cfg, vol_scale)
                state["cap_triggers"][breakdown["binding_cap"]] = \
                    state["cap_triggers"].get(breakdown["binding_cap"], 0) + 1
                if contracts < 1:
                    continue

                # ===== Cross-cell caps (Phase 5 stable-version) =====
                # Per-ticker NAV cap: sum of debit_total across all open positions
                # for this ticker (across all cells), capped at strategy NAV * pct.
                # NAV scope = combined initial (FIXED), matching per-cell-initial choice.
                debit_mid = float(candidate["estimated_debit"])
                strategy_nav_initial = cfg.initial_capital_per_cell * len(cell_names)
                per_spread_cost = debit_mid * 100.0
                cross_cap_binding = None

                if not cap_disabled(cfg.position_cap_per_ticker_nav_pct) and per_spread_cost > 0:
                    ticker_open_debit = sum(
                        p.debit_total
                        for cn2 in cell_names for p in cell_state[cn2]["positions"]
                        if p.ticker == candidate["ticker"]
                    )
                    cap_dollars = strategy_nav_initial * cfg.position_cap_per_ticker_nav_pct
                    remaining = cap_dollars - ticker_open_debit
                    cap_ticker = max(0, int(remaining // per_spread_cost))
                    if cap_ticker < contracts:
                        contracts = cap_ticker
                        cross_cap_binding = "cap_per_ticker_nav"

                if cfg.asset_class_caps and cfg.asset_class_map and per_spread_cost > 0:
                    cls = cfg.asset_class_map.get(candidate["ticker"])
                    cap_pct = cfg.asset_class_caps.get(cls) if cls else None
                    if cap_pct is not None:
                        cls_open_debit = sum(
                            p.debit_total
                            for cn2 in cell_names for p in cell_state[cn2]["positions"]
                            if cfg.asset_class_map.get(p.ticker) == cls
                        )
                        cap_dollars = strategy_nav_initial * cap_pct
                        remaining = cap_dollars - cls_open_debit
                        cap_class = max(0, int(remaining // per_spread_cost))
                        if cap_class < contracts:
                            contracts = cap_class
                            cross_cap_binding = "cap_asset_class"

                if cross_cap_binding is not None:
                    # Update binding_cap if a cross-cell cap won
                    breakdown["binding_cap"] = cross_cap_binding
                    state["cap_triggers"][cross_cap_binding] = \
                        state["cap_triggers"].get(cross_cap_binding, 0) + 1

                if contracts < 1:
                    continue

                # Open: slipped debit
                debit_slipped = float(candidate["estimated_debit"]) * (1.0 + cfg.slippage_pct)
                debit_total = debit_slipped * contracts * 100
                if debit_total > state["cash"]:
                    continue  # insufficient cash
                pos = _Pos(
                    ticker=candidate["ticker"], cell=cn,
                    entry_date=d,
                    front_expiry=candidate["front_expiry"],
                    back_expiry=candidate["back_expiry"],
                    front_strike=float(candidate["front_strike"]),
                    back_strike=float(candidate["back_strike"]),
                    contracts=contracts,
                    entry_debit=debit_slipped,
                    debit_total=debit_total,
                    ff_at_entry=float(candidate["ff"]),
                )
                state["cash"] -= debit_total
                state["positions"].append(pos)
                _ensure_bars(pos)  # pre-fetch for inline MTM
                state["trade_log"].append({
                    "cell": cn, "ticker": pos.ticker,
                    "entry_date": d, "exit_date": None,
                    "front_expiry": pos.front_expiry, "back_expiry": pos.back_expiry,
                    "front_strike": pos.front_strike, "back_strike": pos.back_strike,
                    "contracts": pos.contracts, "entry_debit": pos.entry_debit,
                    "debit_total": pos.debit_total, "ff_at_entry": pos.ff_at_entry,
                    "exit_value_per_spread": None, "pnl_total": None,
                    "fallback_used": False,
                    "binding_cap": breakdown["binding_cap"],
                    "kelly_contracts": breakdown["kelly"],
                    "vol_scale_at_entry": vol_scale,
                })

        # Step 3: record daily strict + MTM equity
        daily_dates.append(d)
        combined_eod = 0.0
        for cn in cell_names:
            state = cell_state[cn]
            strict_eq = state["cash"] + sum(p.debit_total for p in state["positions"])
            daily_equity[cn].append(strict_eq)
            cell_mtm = _eod_cell_mtm(cn, d)
            daily_mtm_per_cell[cn].append(cell_mtm)
            combined_eod += cell_mtm
        combined_mtm_history.append(combined_eod)

    elapsed = time.time() - t0
    print(f"  simulation loop done in {elapsed:.0f}s  (inline MTM tracked; bars cached for {len(bars_cache)} contracts)", flush=True)

    # Inline MTM is the daily equity series (already computed during the loop)
    daily_mtm = daily_mtm_per_cell

    # -------- Output artifacts --------
    out_dir = Path(output_dir) / f"sim_{cfg.short_hash()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"  writing artifacts to {out_dir}/", flush=True)

    # Trade log
    all_trades = []
    for cn in cell_names:
        for row in cell_state[cn]["trade_log"]:
            all_trades.append(row)
    trade_df = pd.DataFrame(all_trades)
    trade_df.to_csv(out_dir / "trade_log.csv", index=False)

    # Daily MTM equity (+ vol-target scale used that day for diagnostics)
    eq_df_data = {"date": [d.isoformat() for d in days]}
    for cn in cell_names:
        eq_df_data[cn] = daily_mtm[cn]
    eq_df_data["combined"] = [sum(daily_mtm[cn][i] for cn in cell_names) for i in range(len(days))]
    eq_df_data["vol_scale"] = daily_vol_scales
    eq_df = pd.DataFrame(eq_df_data)
    eq_df.to_csv(out_dir / "daily_mtm_equity.csv", index=False)

    # Metrics (basic; full analytics live in scripts/)
    n_closed = sum(1 for r in all_trades if r["pnl_total"] is not None)
    n_open = len(all_trades) - n_closed
    realized_pnl = sum(cell_state[cn]["realized_pnl"] for cn in cell_names)
    final_combined_mtm = eq_df["combined"].iloc[-1] if len(eq_df) else cfg.initial_capital_per_cell * len(cell_names)
    base_combined = cfg.initial_capital_per_cell * len(cell_names)
    cal_days = (days[-1] - days[0]).days if len(days) > 1 else 1
    cagr = ((final_combined_mtm / base_combined) ** (365 / max(cal_days, 1)) - 1) * 100

    # Aggregate cap-trigger counts across cells
    cap_triggers_total = {}
    for cn in cell_names:
        for k, v in cell_state[cn]["cap_triggers"].items():
            cap_triggers_total[k] = cap_triggers_total.get(k, 0) + v

    # Vol-scale diagnostics
    n_days_total = len(daily_vol_scales) if daily_vol_scales else 1
    avg_scale = sum(daily_vol_scales) / n_days_total if daily_vol_scales else 1.0
    pct_downscaled = 100.0 * sum(1 for s in daily_vol_scales if s < 1.0) / n_days_total
    pct_upscaled = 100.0 * sum(1 for s in daily_vol_scales if s > 1.0) / n_days_total

    metrics = {
        "config_hash": cfg.hash(),
        "n_total_opens": len(all_trades),
        "n_closed": n_closed, "n_open": n_open,
        "realized_pnl": realized_pnl,
        "final_combined_mtm_equity": float(final_combined_mtm),
        "combined_mtm_cagr_pct": float(cagr),
        "fallback_count": sum(1 for r in all_trades if r.get("fallback_used")),
        "cap_triggers": cap_triggers_total,
        "vol_scale_avg": float(avg_scale),
        "vol_scale_min": float(min(daily_vol_scales)) if daily_vol_scales else 1.0,
        "vol_scale_max": float(max(daily_vol_scales)) if daily_vol_scales else 1.0,
        "pct_days_downscaled": float(pct_downscaled),
        "pct_days_upscaled": float(pct_upscaled),
    }
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))

    # Config snapshot
    (out_dir / "config.json").write_text(json.dumps(cfg.to_dict(), indent=2, default=str))

    # Provenance
    git_commit = "unknown"
    try:
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        pass
    (out_dir / "provenance.json").write_text(json.dumps({
        "discovery_run_id": discovery_run_id,
        "config_hash": cfg.hash(),
        "git_commit": git_commit,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "candidates_path": str(candidates_path),
    }, indent=2))

    print(f"  done. CAGR={cagr:+.2f}%  closes={n_closed}  opens-still={n_open}  fallbacks={metrics['fallback_count']}", flush=True)
    return metrics


# ============================================================================
# CLI
# ============================================================================

def _parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True, help="Path to candidates.parquet")
    ap.add_argument("--config", required=True, help="Path to RunConfig JSON")
    ap.add_argument("--out", default="output", help="Output base dir (subdir per config_hash created automatically)")
    return ap.parse_args()


def _main():
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout)
    args = _parse_args()
    cfg = RunConfig.from_json(Path(args.config).read_text())
    simulate(args.candidates, cfg, args.out)


if __name__ == "__main__":
    _main()
