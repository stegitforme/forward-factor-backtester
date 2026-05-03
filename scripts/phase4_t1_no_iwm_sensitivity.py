"""Path 1 sensitivity: FF Tier 1 + allocation answer WITHOUT the single
IWM Jul 18 → Sep 19 2024 trade.

Method:
  1. Load Tier 1 combined daily MTM equity.
  2. Re-compute the IWM trade's daily MTM contribution using cached option bars
     (same logic as the simulator's inline MTM tracker).
  3. Subtract that daily contribution from the equity curve during the holding
     period; subtract the trade's realized P&L from all post-exit days.
  4. Recompute FF standalone metrics + correlation vs TQQQ-VT + 9-mix
     allocation sweep on the adjusted curve.
  5. Side-by-side comparison vs canonical (with-trade) numbers.

Output: output/PHASE_4_T1_ALLOCATION_NO_IWM_JUL_2024.md
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from src.data_layer import get_client
from src.trade_simulator import _option_ticker_for_strike, _mid_from_bar
from config import settings

TIER1_TRADES = Path("output/sim_4119dc073393/trade_log.csv")
TIER1_EQUITY = Path("output/sim_4119dc073393/daily_mtm_equity.csv")
TQQQVT_EQUITY = Path("output/tqqq_vt_daily_equity.csv")
MD_OUT = Path("output/PHASE_4_T1_ALLOCATION_NO_IWM_JUL_2024.md")

# The trade to remove
TRADE = {
    "ticker": "IWM", "cell": "60_90_atm",
    "entry_date": date(2024, 7, 18), "exit_date": date(2024, 9, 19),
    "front_expiry": date(2024, 9, 20), "back_expiry": date(2024, 10, 18),
    "front_strike": 218.0, "back_strike": 220.0,
    "contracts": 1578,
    "entry_debit": 0.0315,                # slipped, per spread
    "exit_value_per_spread": 1.98949,     # slipped, per spread
    "pnl_total": 304868.022,
}
SLIP = settings.SLIPPAGE_PCT
COMM = settings.COMMISSION_PER_CONTRACT * 2 * 2 * TRADE["contracts"]  # ATM (2 legs) × 2 sides × ctr
INITIAL = 400_000.0  # combined base
MIXES = [
    (1.00, 0.00), (0.90, 0.10), (0.85, 0.15), (0.80, 0.20),
    (0.75, 0.25), (0.70, 0.30), (0.60, 0.40), (0.50, 0.50),
    (0.00, 1.00),
]

# Canonical (with-trade) numbers from PHASE_4_T1_ALLOCATION_REPORT.md
CANONICAL = {
    "ff_cagr": 32.78, "ff_max_dd": 26.68, "ff_sharpe": 0.77, "ff_calmar": 1.23,
    "correlation": -0.107, "beta": -0.200,
    "tqqqvt_cagr": 24.46, "tqqqvt_max_dd": 31.43, "tqqqvt_sharpe": 0.90,
    "max_sharpe_mix": "70/30", "max_sharpe_cagr": 32.31, "max_sharpe_dd": 21.13,
    "max_sharpe_sharpe": 1.26, "max_sharpe_calmar": 1.53,
    "max_calmar_mix": "50/50", "max_calmar_cagr": 35.08, "max_calmar_dd": 16.40,
    "max_calmar_sharpe": 1.17, "max_calmar_calmar": 2.14,
}


def max_dd_pct(equity_vals) -> tuple[float, int, int]:
    if len(equity_vals) == 0: return 0.0, 0, 0
    peak = equity_vals[0]; max_dd = 0.0; pi = 0; ti = 0; cur_pi = 0
    for i, v in enumerate(equity_vals):
        if v > peak: peak = v; cur_pi = i
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd: max_dd = dd; pi = cur_pi; ti = i
    return max_dd, pi, ti


def metrics(equity: pd.Series, base: float = None) -> dict:
    if equity.empty: return {}
    if base is None: base = float(equity.iloc[0])
    end_val = float(equity.iloc[-1])
    cal_days = (equity.index[-1] - equity.index[0]).days
    cagr = ((end_val / base) ** (365 / max(cal_days, 1)) - 1) * 100 if cal_days > 0 else 0
    rets = equity.pct_change().dropna()
    if len(rets) < 2: sd = 0; m = 0
    else: sd = float(rets.std()); m = float(rets.mean())
    ann_vol = sd * (252 ** 0.5) * 100
    sharpe = (m * 252) / (sd * (252 ** 0.5)) if sd > 0 else 0
    dd_pct, pi, ti = max_dd_pct(equity.values)
    calmar = (cagr / dd_pct) if dd_pct > 0 else float("inf")
    return {"cagr": cagr, "max_dd_pct": dd_pct, "ann_vol": ann_vol, "sharpe": sharpe,
            "calmar": calmar, "end_val": end_val}


def main():
    print("### Path 1 — Allocation sensitivity WITHOUT IWM Jul 2024 trade", flush=True)
    client = get_client()

    # Load Tier 1 equity
    eq_df = pd.read_csv(TIER1_EQUITY, parse_dates=["date"])
    eq_df.set_index("date", inplace=True)
    ff_with = eq_df["combined"].copy()
    print(f"  Tier 1 equity: {len(ff_with)} days, ${float(ff_with.iloc[0]):,.0f} → ${float(ff_with.iloc[-1]):,.0f}", flush=True)

    # ---- Compute the trade's daily MTM contribution ----
    print(f"\n  Computing IWM Jul 2024 trade's daily MTM contribution...", flush=True)
    f_ticker = _option_ticker_for_strike(TRADE["ticker"], TRADE["front_expiry"], "C", TRADE["front_strike"])
    b_ticker = _option_ticker_for_strike(TRADE["ticker"], TRADE["back_expiry"], "C", TRADE["back_strike"])
    print(f"    front contract: {f_ticker}", flush=True)
    print(f"    back contract:  {b_ticker}", flush=True)
    f_bars = client.get_option_daily_bars(f_ticker, TRADE["entry_date"] - timedelta(days=5),
                                            TRADE["front_expiry"] + timedelta(days=5))
    b_bars = client.get_option_daily_bars(b_ticker, TRADE["entry_date"] - timedelta(days=5),
                                            TRADE["back_expiry"] + timedelta(days=5))
    if f_bars.empty or b_bars.empty:
        raise RuntimeError("Trade bars not in cache — re-run discovery to populate")

    # For each trading day in the holding period, compute MTM contribution
    # (per the simulator's _eod_cell_mtm: cell_eq adds mid * contracts * 100 - comm
    #  for open positions, vs strict adds debit_total)
    # The Tier 1 equity curve already includes this trade's MTM.
    # To remove: subtract the MTM-mid component AND the implicit "as-if-held" cash
    # delta, leaving only the rest of the portfolio.
    #
    # Simpler view: build the trade's standalone P&L contribution to combined equity:
    #   For dates < entry: 0
    #   For dates >= entry, < exit: the trade contributed (mid * ctr * 100 - comm)
    #     into the cell's MTM equity (replaces the entry_debit deployment)
    #     i.e. unrealized contribution to equity = (mid - entry_debit) * ctr * 100 - comm
    #   For dates >= exit: realized contribution = pnl_total (constant)
    print(f"    walking days from {TRADE['entry_date']} to last day...", flush=True)
    trade_contrib = pd.Series(0.0, index=ff_with.index)
    for d in ff_with.index:
        d_date = d.date() if hasattr(d, "date") else d
        if d_date < TRADE["entry_date"]:
            continue
        if d_date >= TRADE["exit_date"]:
            # Post-exit: realized P&L is permanently in equity
            trade_contrib.loc[d] = TRADE["pnl_total"]
            continue
        # Holding period: compute that day's MTM
        target = pd.Timestamp(d_date)
        fi = f_bars.index.asof(target); bi = b_bars.index.asof(target)
        if pd.isna(fi) or pd.isna(bi):
            # No bar — fall back to entry_debit (zero unrealized; commission only)
            trade_contrib.loc[d] = -COMM
            continue
        fm = _mid_from_bar(f_bars.loc[fi]); bm = _mid_from_bar(b_bars.loc[bi])
        if fm is None or bm is None:
            trade_contrib.loc[d] = -COMM
            continue
        spread = bm - fm
        slipped_mid = spread * (1.0 - SLIP) if spread > 0 else spread * (1.0 + SLIP)
        unrealized = (slipped_mid - TRADE["entry_debit"]) * TRADE["contracts"] * 100 - COMM
        trade_contrib.loc[d] = unrealized

    # FF without the trade
    ff_without = ff_with - trade_contrib
    print(f"    trade contribution at entry day: ${float(trade_contrib.loc[pd.Timestamp(TRADE['entry_date'])]):,.0f}", flush=True)
    print(f"    trade contribution at exit day:  ${float(trade_contrib.loc[pd.Timestamp(TRADE['exit_date'])]):,.0f}", flush=True)
    print(f"    trade contribution at end:       ${float(trade_contrib.iloc[-1]):,.0f}  (should ≈ ${TRADE['pnl_total']:,.0f})", flush=True)
    print(f"  FF without IWM trade: ${float(ff_without.iloc[0]):,.0f} → ${float(ff_without.iloc[-1]):,.0f}", flush=True)

    # Tier 1 standalone metrics — both versions
    ff_with_m = metrics(ff_with, INITIAL)
    ff_without_m = metrics(ff_without, INITIAL)
    print(f"\n  FF with trade:    CAGR {ff_with_m['cagr']:+.2f}%  DD {ff_with_m['max_dd_pct']:.2f}%  Sharpe {ff_with_m['sharpe']:.2f}", flush=True)
    print(f"  FF without trade: CAGR {ff_without_m['cagr']:+.2f}%  DD {ff_without_m['max_dd_pct']:.2f}%  Sharpe {ff_without_m['sharpe']:.2f}", flush=True)

    # ---- TQQQ-VT + correlation + allocation ----
    tq = pd.read_csv(TQQQVT_EQUITY, parse_dates=["date"]).set_index("date")
    tq_eq = tq[tq.columns[0]] if "portfolio_value" not in tq.columns else tq["portfolio_value"]
    common = ff_without.index.intersection(tq_eq.index)
    ff_w = ff_with.loc[common]; ff_wo = ff_without.loc[common]; tqe = tq_eq.loc[common]

    ff_rets_w = ff_w.pct_change().dropna()
    ff_rets_wo = ff_wo.pct_change().dropna()
    tq_rets = tqe.pct_change().dropna()
    idx_w = ff_rets_w.index.intersection(tq_rets.index)
    idx_wo = ff_rets_wo.index.intersection(tq_rets.index)
    corr_with = float(ff_rets_w.loc[idx_w].corr(tq_rets.loc[idx_w]))
    corr_without = float(ff_rets_wo.loc[idx_wo].corr(tq_rets.loc[idx_wo]))
    cov_wo = float(ff_rets_wo.loc[idx_wo].cov(tq_rets.loc[idx_wo]))
    var_tq = float(tq_rets.loc[idx_wo].var())
    beta_wo = cov_wo / var_tq if var_tq > 0 else 0
    print(f"\n  Correlation with trade: {corr_with:+.3f}  | without: {corr_without:+.3f}", flush=True)
    print(f"  Beta without trade: {beta_wo:+.3f}", flush=True)

    # Allocation sweep on FF without trade
    print(f"\n  Allocation sweep (without IWM Jul 2024)...", flush=True)
    base_for_sweep = 10_000.0
    sweep = []
    for w_tq, w_ff in MIXES:
        port_rets = w_tq * tq_rets.loc[idx_wo] + w_ff * ff_rets_wo.loc[idx_wo]
        eq = (1.0 + port_rets).cumprod() * base_for_sweep
        eq = pd.concat([pd.Series([base_for_sweep], index=[port_rets.index[0] - pd.Timedelta(days=1)]), eq])
        m = metrics(eq, base_for_sweep)
        sweep.append({"label": f"{int(w_tq*100):3d}/{int(w_ff*100):3d}", "w_tq": w_tq, "w_ff": w_ff, **m})
        print(f"    {int(w_tq*100):3d}% TQQQ-VT / {int(w_ff*100):3d}% FF:  CAGR {m['cagr']:+.2f}%  DD {m['max_dd_pct']:.2f}%  Sharpe {m['sharpe']:.2f}  Calmar {m['calmar']:.2f}", flush=True)

    max_sh_idx = max(range(len(sweep)), key=lambda i: sweep[i]["sharpe"])
    max_cal_idx = max(range(len(sweep)), key=lambda i: sweep[i]["calmar"] if sweep[i]["calmar"] != float("inf") else 0)
    pure_tq = sweep[0]
    max_sh = sweep[max_sh_idx]
    max_cal = sweep[max_cal_idx]
    print(f"\n  Max-Sharpe (without trade): {max_sh['label']}  Sharpe {max_sh['sharpe']:.3f}", flush=True)
    print(f"  Max-Calmar (without trade): {max_cal['label']}  Calmar {max_cal['calmar']:.3f}", flush=True)

    # Decision rule
    ff_pct_in_max_sh = int(max_sh["w_ff"] * 100)
    if ff_pct_in_max_sh < 10:
        verdict = "**(COLLAPSE)** Max-Sharpe drops to <10% FF without the IWM trade. Strategy is highly outlier-dependent. Recommend defer all live allocation until ORATS extended-history validation."
        bucket = "<10%"
    elif ff_pct_in_max_sh <= 15:
        verdict = f"**(STRONG OUTLIER DEPENDENCE)** Max-Sharpe drops to {ff_pct_in_max_sh}% FF (vs canonical 30%). Strategy's diversification benefit is materially smaller without the outlier. Recommend 5-10% live + 15% paper as initial deployment, full sizing decision after ORATS."
        bucket = "10-15%"
    elif ff_pct_in_max_sh <= 25:
        verdict = f"**(PARTIAL OUTLIER DEPENDENCE)** Max-Sharpe lands at {ff_pct_in_max_sh}% FF (vs canonical 30%). The IWM trade was a bonus but not the foundation; strategy still genuinely diversifies. Recommend 5-10% live + 15% paper as initial deployment per Steven's bracketed framing."
        bucket = "15-25%"
    else:
        verdict = f"**(HOLDS)** Max-Sharpe stays at {ff_pct_in_max_sh}% FF, basically unchanged from canonical 30%. The IWM trade was a one-off bonus on top of a genuinely diversifying strategy. Allocation answer is robust."
        bucket = "25%+"

    # ---- Markdown ----
    print(f"\nWriting {MD_OUT}...", flush=True)
    def fmt_pct(v): return f"{v:+.2f}%"
    lines = []
    lines.append(f"# Phase 4 Tier 1 — Allocation Sensitivity (without IWM Jul 2024 trade)")
    lines.append("")
    lines.append(f"**Method**: removed the single IWM 60-90 trade (entry 2024-07-18, exit 2024-09-19, 1,578 contracts at $0.03 debit, P&L +$304,868) from FF Tier 1's daily MTM equity curve, then recomputed metrics + correlation + allocation sweep.")
    lines.append("")
    lines.append(f"**Trade contribution removed daily**: walked the 2024-07-18 → 2024-09-19 holding period, computed MTM unrealized P&L using cached option bars (front O:IWM240920C00218000, back O:IWM241018C00220000), subtracted from combined equity. Post-exit days had the realized $+304,868 subtracted as a constant.")
    lines.append("")

    lines.append(f"## Side-by-side comparison")
    lines.append("")
    lines.append(f"| Metric | With IWM Jul 2024 (canonical) | Without IWM Jul 2024 (sensitivity) | Δ |")
    lines.append(f"|---|---:|---:|---:|")
    lines.append(f"| FF standalone CAGR | {fmt_pct(ff_with_m['cagr'])} | {fmt_pct(ff_without_m['cagr'])} | {ff_without_m['cagr']-ff_with_m['cagr']:+.2f}pp |")
    lines.append(f"| FF standalone MaxDD | {ff_with_m['max_dd_pct']:.2f}% | {ff_without_m['max_dd_pct']:.2f}% | {ff_without_m['max_dd_pct']-ff_with_m['max_dd_pct']:+.2f}pp |")
    lines.append(f"| FF standalone Sharpe | {ff_with_m['sharpe']:.2f} | {ff_without_m['sharpe']:.2f} | {ff_without_m['sharpe']-ff_with_m['sharpe']:+.2f} |")
    lines.append(f"| FF standalone Calmar | {ff_with_m['calmar']:.2f} | {ff_without_m['calmar']:.2f} | {ff_without_m['calmar']-ff_with_m['calmar']:+.2f} |")
    lines.append(f"| FF end equity (on $400K base) | ${ff_with_m['end_val']:,.0f} | ${ff_without_m['end_val']:,.0f} | ${ff_without_m['end_val']-ff_with_m['end_val']:+,.0f} |")
    lines.append(f"| Correlation to TQQQ-VT | {corr_with:+.3f} | {corr_without:+.3f} | {corr_without-corr_with:+.3f} |")
    lines.append(f"| Max-Sharpe mix | 70/30 | **{max_sh['label']}** | (see below) |")
    lines.append(f"| Max-Sharpe portfolio CAGR | +32.31% | {fmt_pct(max_sh['cagr'])} | {max_sh['cagr']-32.31:+.2f}pp |")
    lines.append(f"| Max-Sharpe portfolio MaxDD | 21.13% | {max_sh['max_dd_pct']:.2f}% | {max_sh['max_dd_pct']-21.13:+.2f}pp |")
    lines.append(f"| Max-Sharpe portfolio Sharpe | 1.26 | {max_sh['sharpe']:.2f} | {max_sh['sharpe']-1.26:+.2f} |")
    lines.append("")

    lines.append(f"## Allocation sweep — full table (without IWM Jul 2024)")
    lines.append("")
    lines.append(f"| Mix (TQQQ-VT/FF) | CAGR | MaxDD% | Ann Vol | Sharpe | Calmar |")
    lines.append(f"|---|---:|---:|---:|---:|---:|")
    for r in sweep:
        marker = ""
        if r is max_sh: marker = " ← max Sharpe"
        if r is max_cal and r is not max_sh: marker = " ← max Calmar"
        lines.append(f"| {r['label']}{marker} | {fmt_pct(r['cagr'])} | {r['max_dd_pct']:.2f}% | {r['ann_vol']:.2f}% | {r['sharpe']:.2f} | {r['calmar']:.2f} |")
    lines.append("")

    lines.append(f"## Critical comparison: pure TQQQ-VT vs Max-Sharpe vs Max-Calmar (sensitivity)")
    lines.append("")
    lines.append(f"| Metric | Pure TQQQ-VT | Max-Sharpe ({max_sh['label']}) | Max-Calmar ({max_cal['label']}) |")
    lines.append(f"|---|---:|---:|---:|")
    for k, label in [("cagr", "CAGR"), ("max_dd_pct", "MaxDD%"), ("ann_vol", "Ann Vol"), ("sharpe", "Sharpe"), ("calmar", "Calmar")]:
        v1 = pure_tq[k]; v2 = max_sh[k]; v3 = max_cal[k]
        if k in ("cagr", "max_dd_pct", "ann_vol"):
            lines.append(f"| {label} | {fmt_pct(v1)} | {fmt_pct(v2)} | {fmt_pct(v3)} |")
        else:
            lines.append(f"| {label} | {v1:.2f} | {v2:.2f} | {v3:.2f} |")
    lines.append("")

    lines.append(f"## Decision rule applied (bucket: {bucket} FF allocation)")
    lines.append("")
    lines.append(verdict)
    lines.append("")

    lines.append(f"## Bracketed allocation framing")
    lines.append("")
    lines.append(f"- **Optimistic case (with IWM Jul 2024 in sample)**: 30% FF / 70% TQQQ-VT, portfolio Sharpe 1.26, MaxDD 21.13%, CAGR +32.31%")
    lines.append(f"- **Realistic case (without the outlier)**: {max_sh['label']}, portfolio Sharpe {max_sh['sharpe']:.2f}, MaxDD {max_sh['max_dd_pct']:.2f}%, CAGR {fmt_pct(max_sh['cagr'])}")
    lines.append(f"- **Forward-looking case**: TBD pending ORATS extended-history backtest (will reveal whether near-zero-debit Kelly-overscale pattern produces outliers consistently across regimes)")
    lines.append("")

    MD_OUT.parent.mkdir(parents=True, exist_ok=True)
    MD_OUT.write_text("\n".join(lines))
    print(f"Wrote {MD_OUT}", flush=True)


if __name__ == "__main__":
    main()
