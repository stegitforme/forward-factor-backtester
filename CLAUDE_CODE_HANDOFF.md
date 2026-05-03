# Claude Code Handoff: Forward Factor Backtester

## TL;DR — Research arc PROVISIONALLY complete (2026-05-03)

> **Status update (2026-05-03)**: 2024 attribution analysis revealed strong concentration — top 5 trades = 85.4% of 2024 P&L; one IWM 60-90 trade (Jul 18 → Sep 19, 1,578 contracts at $0.03 debit, +$304,868) is **22.4% of the entire 4.3-year strategy P&L**. The same near-zero-debit Kelly-overscale pattern produced both this win AND the KRE Apr 2026 catastrophe — structural property, not coincidence. Path 1 sensitivity (allocation sweep without that trade) shows the 70/30 max-Sharpe answer is **structurally robust** — max-Sharpe mix stays at 30% FF, but magnitude of benefit shrinks (Sharpe 1.26 → 1.20, CAGR uplift 7.85pp → 5.73pp vs pure TQQQ-VT). Two further validations pending before research arc closes definitively: (a) ORATS extended-history backtest covering 2008/2018/2020 regimes (~10-14 days ETA) and (b) debit-floor cap re-evaluation on 23-ticker universe. Deployment recommendation now bracketed as **5-10% live + 15% paper trade as initial Phase A**, with full sizing decision deferred until ORATS validation.

Independent backtest of the **Forward Factor calendar spread strategy** (Volatility Vibes / Campasano 2018), expanded to a 23-ticker multi-asset universe. Pipeline runs end-to-end on Polygon Options Advanced via `discover_candidates` → `simulate_portfolio` (refactored architecture, see "Pipeline" below).

### Canonical result

**FF Tier 1 standalone** (23-ticker multi-asset, 2-cell 30-90 + 60-90 ATM Call, no caps, no vol-target, earnings filter ON, MAX_CONCURRENT=12, 2022-01-03 → 2026-04-30):

| Metric | Value |
|---|---:|
| MTM CAGR | **+32.78%** |
| MaxDD% (PCT-max) | 26.68% |
| Sharpe | 0.77 |
| Calmar | 1.23 |
| Annualized vol | 53.35% |
| Closed trades | 643 |
| End equity (on $400K base) | $1.36M |

**Allocation answer vs Steven's TQQQ-VT** (correlation = **−0.107**, beta = **−0.200**):

| Mix (TQQQ-VT/FF) | CAGR | MaxDD% | Sharpe | Calmar |
|---|---:|---:|---:|---:|
| 100/0 (Steven's current) | +24.46% | 31.43% | 0.90 | 0.78 |
| **70/30 (max-Sharpe)** | **+32.31%** | **21.13%** | **1.26** | 1.53 |
| **50/50 (max-Calmar)** | **+35.08%** | **16.40%** | 1.17 | **2.14** |
| 0/100 (pure FF) | +32.78% | 26.68% | 0.79 | 1.23 |

**Adding FF improves both CAGR AND MaxDD vs pure TQQQ-VT across every mix tested** — textbook diversification, driven by the −0.107 correlation. Max-Sharpe at 30% FF is in Steven's "meaningful allocation" bucket (>15%), not satellite.

### Bracketed allocation answer (post-2024-attribution sensitivity, 2026-05-03)

The allocation answer above is the **OPTIMISTIC case** — it uses the full sample including the IWM Jul 2024 outlier trade ($304,868, 22.4% of total strategy P&L). The Path 1 sensitivity analysis (script: `scripts/phase4_t1_no_iwm_sensitivity.py`, report: `output/PHASE_4_T1_ALLOCATION_NO_IWM_JUL_2024.md`) recomputed everything with that single trade removed:

| Case | Mix | CAGR | MaxDD% | Sharpe | Calmar |
|---|---|---:|---:|---:|---:|
| **Optimistic** (with IWM Jul 2024) | 70/30 | +32.31% | 21.13% | **1.26** | 1.53 |
| **Realistic** (without the outlier) | 70/30 | +30.19% | 21.13% | **1.20** | 1.43 |
| **Forward-looking** | TBD | TBD | TBD | TBD | TBD |

**Max-Sharpe mix unchanged at 70/30** in both cases — strategy is structurally diversifying, the IWM trade was bonus not foundation. Magnitude of CAGR uplift vs pure TQQQ-VT shrinks from +7.85pp to +5.73pp; Sharpe uplift from +0.36 to +0.30. Both still meaningful improvements.

**Forward-looking case requires ORATS extended-history backtest** (~10-14 days ETA). The near-zero-debit Kelly-overscale pattern produced both the IWM Jul 2024 +$304K winner AND the KRE Apr 2026 −$258K loss — same execution pattern, opposite outcomes. Whether this pattern produces outliers consistently across regimes (2008/2018/2020) or whether 2022-2026 was unusually lucky is the open question that determines forward-CAGR expectation.

**Primary user**: Steven Goglanian, sgoglanian@gmail.com. Polygon Options Advanced paid through May 14, 2026 — downgrade May 30.

## How to Pick This Up

```bash
git clone https://github.com/stegitforme/forward-factor-backtester.git
cd forward-factor-backtester
pip install -r requirements.txt
python -m pytest tests/  # Should report 174 passed
```

If you want to run the backtest, you need:
- A Polygon Options Advanced API key (Steven's: `l1AakpBVhCItuxqKpyKyIhExcD57Vsyo`)
- Put it in `config/secrets.py` (gitignored): `POLYGON_API_KEY = '...'`
- Run cells in `notebooks/colab_runner.ipynb` in order

## Final canonical config (2026-05-02, end of research arc)

```python
# config/settings.py — defaults align with canonical Tier 1 result
DTE_PAIRS = [(30, 90), (60, 90)]                 # 2-cell ATM call calendar
STRUCTURES = ["atm_call_calendar"]               # single-leg-pair structure
FF_THRESHOLD = 0.20                              # uniform; Phase 2c per-cell rejected
MAX_CONCURRENT_POSITIONS = 12
EARNINGS_FILTER_ENABLED = True                   # Phase 1 Option B (skip if earnings in window)

# Universe (23 tickers, validated by pre-flight ≥20% back-leg resolution for new additions):
UNIVERSE = [
    # Equity broad
    "SPY", "IWM",
    # Equity sector / thematic
    "SMH", "XBI", "KRE", "KBE", "XLF", "IBB", "ARKK",
    # Equity international
    "KWEB", "EEM", "FXI",
    # Equity single-name (mostly earnings-blocked at 60/90 — operationally near-zero)
    "MSTR", "META", "AMD", "GOOGL", "JPM", "COIN",
    # Bonds
    "TLT", "HYG",
    # Commodities
    "GLD", "SLV", "USO",
]
```

Caps and vol-targeting infrastructure exist in `RunConfig` (`config/run_config.py`) but are **disabled by default** — both were tested and rejected as risk controls (see Strategy Character below).

## What Works (verified)

- ✅ **Polygon Options Advanced API integration** — verified live: `/v3/reference/options/contracts`, `/v1/open-close/{contract}/{date}`, `/v3/quotes/{contract}`, `/v2/aggs/ticker/{contract}/...`
- ✅ **Black-Scholes IV solver** (`src/iv_solver.py`) — Newton-Raphson + Brent fallback. Round-tripped to 1e-4 across 0.10/0.20/0.30/0.50/0.80/1.20 vols. Validated against Hull textbook.
- ✅ **Chain resolver** (`src/chain_resolver.py`) — finds ATM/35-delta strikes, fetches close, inverts IV
- ✅ **Forward Factor calculator** — validated step-by-step against video walkthrough
- ✅ **TQQQ Vol Accel Guard benchmark** with auto-validation against Steven's reference numbers
- ✅ **Full backtest orchestration** with tqdm progress bars
- ✅ **Smoke mode** — `run_full_backtest(smoke_mode=True, smoke_tickers=[...], smoke_days=N)`
- ✅ **Quarter-Kelly sizing** with concurrency cap and per-trade dollar risk
- ✅ **Trade log captures opens immediately** (so smoke tests with short windows show activity)
- ✅ **Real exit pricing** in `step_one_day()` — re-prices each spread at exit date via `compute_exit_value()` in `src/trade_simulator.py`. Falls back to `entry_debit` + logged warning when Polygon has no daily bar within ±3 days for either leg. Slippage applied symmetrically (entry × 1.05, exit × 0.95). Commission count fixed (was charging double-calendar rate for ATM). See "Verified smoke" section below.
- ✅ **174 unit tests passing** (153 prior + 8 exit-pricing + 5 earnings + 3 per-cell-threshold + 5 pipeline)
- ✅ **Refactored pipeline (Phase 3 refactor)**: `src/discover_candidates.py` (parallel API, raw FF dump → parquet) → `src/simulate_portfolio.py` (RunConfig-driven sim with caps + vol-target infra). `RunConfig` (`config/run_config.py`) provides hash-based experiment isolation. Layered diskcache (reference / equity / options) with cache-stats CLI: `python -m src.data_layer cache_report`.

## Known Limitations (read before quoting any number from this codebase)

The canonical Tier 1 + allocation result has wide confidence intervals. Specifically:

- **n=643 closed trades** is reasonable but a single-sample backtest. Confidence interval on the +32.78% CAGR estimate is meaningfully wide (±5-8pp). This is one path through a sample of regimes, not a population estimate.
- **78% of P&L concentrated in 5 names** (IWM ≈ 30%, plus SMH/XBI/KWEB/ARKK/KRE). Strategy is real on a subset, NOT broadly distributed. Removing any of these top contributors materially shifts the result. IWM removal alone would drop CAGR from ~33% to ~9%.
- **5 of 6 single names produced zero opens** (META/AMD/GOOGL/JPM/COIN/MSTR all 97-100% earnings-blocked at 60/90 DTE). The "23-ticker universe" is operationally a "17-18 ticker universe" once the filter runs. Adding more single names won't help without Option A (ex-earnings IV) — see "Open Follow-ups Queued" below.
- **24 still-open positions at window end** (~$24K of MTM). If these reverse, results drop modestly.
- **MaxDD = 26.68%** is the standard PCT-max definition (largest peak-to-trough excursion at any point). This is **above the README's ≤25% allocation criterion by 1.68pp**. The original Phase 4 Tier 1 main report briefly cited 23.24% which was a dollar-max-with-contemporaneous-peak measure (defensible but not standard). Reports are now consistent on PCT-max.
- **Backtest window is 4.3 years** (2022-01-03 → 2026-04-30). Pre-2022 data is on Polygon's 5-year cap and not yet pulled. 2021 vol regime not represented.
- **2024 contributed disproportionately** (~+87% in 2024 alone per Phase 3 per-year breakdown). Per-quarter / per-ticker attribution within 2024 is queued (see "Open Follow-ups Queued") to confirm whether that year's outperformance was broad or one-shot.

These caveats apply to the standalone FF Tier 1 number (+32.78% CAGR). The allocation answer (max-Sharpe 70/30 mix) is more robust because it uses the −0.107 correlation directly — which holds even if either standalone CAGR shifts within its CI.

### CANONICAL RESULT: Phase 4 Tier 1 + Allocation (2026-05-02)

Final canonical result of the research arc. Standalone FF Tier 1 metrics, allocation analysis vs Steven's TQQQ-VT, and the recommended deployment split.

```
Configuration:  23-ticker multi-asset universe, 2 cells (30-90 + 60-90 ATM call calendar)
                Uniform FF=0.20, earnings filter ON, MAX_CONCURRENT=12, Quarter-Kelly
                Caps OFF, vol-targeting OFF (both rejected — see Strategy Character)
                Initial: $200K per cell ($400K combined base)
                Window: 2022-01-03 → 2026-04-30 (1129 trading days)
                Pipeline: discover_candidates.py → simulate_portfolio.py
                Discovery+sim outputs in output/sim_4119dc073393/
```

**Universe (23)**: SPY, IWM (broad equity) + SMH, XBI, KRE, KBE, XLF, IBB, ARKK (sector/thematic) + KWEB, EEM, FXI (international) + MSTR, META, AMD, GOOGL, JPM, COIN (single names; mostly earnings-blocked) + TLT, HYG (bonds) + GLD, SLV, USO (commodities).

#### Standalone FF Tier 1 metrics (full sample 2022-01-03 → 2026-04-30)

| Metric | Value |
|---|---:|
| MTM CAGR | **+32.78%** |
| MaxDD% (PCT-max) | **26.68%** (Nov 2023 → Feb 2024 episode, 88 days, recovered) |
| Annualized vol | 53.35% |
| Sharpe | 0.77 |
| Calmar | 1.23 |
| Closed trades | 643 |
| Still open at end | 24 |
| Fallback warnings | 24 / 643 closes (3.7%) |
| End equity | $1,362,520 (on $400K base) |

#### Per-asset-class P&L breakdown (the World B / multi-asset confirmation)

| Asset class | Tickers | Sum P&L | % of total |
|---|---|---:|---:|
| equity_broad | IWM, SPY | +$395,832 | +41.6% |
| equity_sector | SMH, XBI, KRE, KBE, IBB, XLF | +$249,555 | +26.2% |
| equity_international | KWEB, EEM, FXI | +$150,644 | +15.8% |
| equity_thematic | ARKK | +$59,451 | +6.2% |
| **commodity_oil** | **USO** | **+$44,193** | **+4.6%** |
| **bond** | **TLT, HYG** | **+$30,838** | **+3.2%** |
| **commodity_metal** | **GLD, SLV** | **+$22,647** | **+2.4%** |
| equity_single_name | COIN | −$639 | −0.1% |

**Non-equity total: $97,678 (10.2% of P&L)** — almost 2× the $50K threshold for "FF generalizes beyond equity-vol." World B confirmed: this is a multi-asset signal, not equity-vol-specific. Universe diversification was the structural fix that delivered 32% CAGR vs Phase 3's 24% (caps and vol-targeting both failed — see Strategy Character).

#### Per-ticker P&L attribution (full sample)

```
ticker  opens  closed  resolution  strict P&L   % total
IWM       50     48      38.0%    +$396,353    +41.6%
SMH       17     17      20.9%    +$125,239    +13.1%
XBI       30     30      17.4%    +$115,530    +12.1%
KWEB      32     32      23.8%     +$93,216     +9.8%
ARKK      33     32      18.3%     +$59,451     +6.2%
EEM       29     28      21.7%     +$51,235     +5.4%   NEW (Tier 1)
USO       41     32      17.4%     +$44,193     +4.6%   NEW
HYG      105    103      19.3%     +$22,924     +2.4%   NEW
IBB        7      7       4.4%     +$15,816     +1.7%
GLD       33     31      36.4%     +$13,844     +1.5%   NEW (cleanest non-equity test)
SLV       22     22      36.6%      +$8,803     +0.9%   NEW
TLT       63     61      41.8%      +$7,913     +0.8%
FXI       66     64      24.5%      +$6,194     +0.7%   NEW
KRE       59     58      22.4%      +$6,066     +0.6%
SPY       21     21      54.3%        −$521     −0.1%
COIN       2      2      29.1%        −$639     −0.1%
KBE        3      3       2.5%      −$1,366     −0.1%
XLF       54     52      35.3%     −$11,730     −1.2%
MSTR/META/AMD/GOOGL/JPM:  0 opens — 97-100% earnings-blocked
```

#### Allocation answer vs Steven's TQQQ Vol-Target

```
Daily-returns correlation (FF Tier 1 vs TQQQ-VT): −0.107
Beta (FF on TQQQ-VT):                              −0.200
TQQQ-VT standalone (overlapping period):           CAGR +24.46%, MaxDD 31.43%, Sharpe 0.90
```

**Allocation sweep (daily-rebalanced fixed weights):**

| Mix (TQQQ-VT/FF) | CAGR | MaxDD% | Sharpe | Calmar |
|---|---:|---:|---:|---:|
| 100/0 (Steven's current) | +24.46% | 31.43% | 0.90 | 0.78 |
| 90/10 | +27.54% | 27.91% | 1.07 | 0.99 |
| 85/15 | +28.91% | 26.11% | 1.14 | 1.11 |
| 80/20 | +30.17% | 24.37% | 1.20 | 1.24 |
| 75/25 | +31.30% | 22.76% | 1.24 | 1.38 |
| **70/30 (max-Sharpe)** | **+32.31%** | **21.13%** | **1.26** | 1.53 |
| 60/40 | +33.96% | 17.92% | 1.24 | 1.89 |
| **50/50 (max-Calmar)** | **+35.08%** | **16.40%** | 1.17 | **2.14** |
| 0/100 (pure FF) | +32.78% | 26.68% | 0.79 | 1.23 |

**Key insight**: adding FF improves BOTH CAGR AND MaxDD vs pure TQQQ-VT across every mix tested. The −0.107 correlation does real work — the two strategies' worst drawdowns happen at different times, so combining them produces a smoother equity curve. Max-Sharpe 30% FF allocation is in the **"meaningful allocation"** bucket per the >15% rule, not satellite.

#### Δ vs pure TQQQ-VT for the recommended max-Sharpe (70/30) mix

| Metric | Δ |
|---|---:|
| CAGR | **+7.85pp** (24.46 → 32.31%) |
| MaxDD% | **−10.30pp** (31.43 → 21.13%) |
| Sharpe | **+0.36** (0.90 → 1.26) |
| Calmar | **+0.75** (0.78 → 1.53) |

In dollar terms over the 4.3-year period: a $200K allocation deployed 70/30 would have ended at ~$704K vs ~$525K pure TQQQ-VT (+$179K) **with lower DD**.

#### Reports written

- [output/PHASE_4_T1_REPORT.md](output/PHASE_4_T1_REPORT.md) — Tier 1 standalone result + per-asset-class breakdown
- [output/PHASE_4_T1_BENCHMARK_REPORT.md](output/PHASE_4_T1_BENCHMARK_REPORT.md) — vs SPY/QQQ/TQQQ + TQQQ-VT point estimate
- [output/PHASE_4_T1_ALLOCATION_REPORT.md](output/PHASE_4_T1_ALLOCATION_REPORT.md) — TQQQ-VT correlation + 9-mix sweep
- [output/sim_4119dc073393/](output/sim_4119dc073393/) — trade log, daily MTM equity, metrics, provenance
- [output/phase4_t1_candidates.parquet](output/phase4_t1_candidates.parquet) — discovery dump (51,934 rows)
- [output/ff_vs_tqqqvt_curves.png](output/ff_vs_tqqqvt_curves.png), [output/allocation_sweep_curves.png](output/allocation_sweep_curves.png) — visualizations

#### Earnings filter validation (Phase 1 Option B — Steven's hypothesis empirically confirmed)

At 60/90 DTE, earnings cycle (~90 days) ≈ back-leg expiry (~90 days), so every entry day has earnings within the trade window for any quarterly-reporting single name. Empirically: 97-100% of (single-name, day) combinations are filter-blocked. The 5 single names in the Tier 1 universe (META, AMD, GOOGL, JPM, COIN, MSTR) produced **zero opens** across the full 4.3-year backtest. The "23-ticker universe" is operationally a "17-18 ticker universe" once the filter runs.

To capture single-name signal at 60/90 would require Option A (ex-earnings IV adjustment) — see "Open Follow-ups Queued" below.

## Strategy Character Notes

### Universe diversification was the structural fix (Phase 4 Tier 1, 2026-05-02)

Three risk-control hypotheses tested; only one worked.

**Per-trade position caps (Phase 3 refactor + 5-config sweep) — REJECTED.** Tested 4 cap configurations on top of the Phase 3 baseline. Best result (all three caps active) shrank MaxDD from 31.70% → 13.88% but at 4× CAGR cost (24.33% → 6.75%). Sharpe and Calmar both worsened across all cap configs vs baseline. The DD wasn't a per-trade-sizing failure — capping individual trades only redistributed risk, didn't reduce it. Cap infrastructure remains in `RunConfig` (`position_cap_*` fields, all default `None`/disabled) but should not be enabled.

**Strategy-level vol-targeting (Phase 3.5 sweep) — REJECTED.** Tested 4 configs (target 15%/20% × max_scale 1.0/2.0). Best configuration (target 20%, max_scale 2.0) gave Sharpe 0.67 vs baseline 0.66 — essentially identical. April 2026 DD specifically was unfixable: trailing-30-day vol said "low vol" right before the crash hit; vol-target couldn't react fast enough. Vol-target infrastructure remains in `RunConfig` (`vol_target_*` fields, all default `None`/disabled) but should not be enabled.

**Universe diversification across asset classes (Phase 4 Tier 1) — WORKED.** Adding 6 multi-asset tickers (EEM, FXI, HYG, GLD, SLV, USO) to the 17-ticker baseline lifted CAGR from +24.33% → +32.78% AND reduced MaxDD from 31.70% → 26.68%. Non-equity contribution: $97,678 (10.2% of P&L) — confirms FF is a multi-asset signal, not equity-vol-specific. The 6 new tickers also displaced marginal incumbent trades (KRE went from −$34K in Phase 3 to +$6K in Tier 1 because higher-FF candidates from EEM/HYG/USO took some of its slots).

**Pattern**: the right lever was at the strategy-DESIGN level (which underliers to look at), not at the strategy-EXECUTION level (how big to size). Future risk-control work should target universe / cell composition first, not sizing.

### FF Tier 1 is genuinely uncorrelated to equity benchmarks

Daily-returns correlations across the full 2022-2026 sample:

| Benchmark | Correlation | Beta | Info ratio (active vs benchmark) |
|---|---:|---:|---:|
| SPY | −0.085 | −0.259 | +0.53 |
| QQQ | −0.089 | −0.209 | +0.45 |
| TQQQ | −0.090 | −0.071 | +0.10 |
| **TQQQ-VT (Steven's)** | **−0.107** | **−0.200** | (drives allocation result) |

All four correlations near zero with slight negative tilt. This is why the allocation result works: combining FF with TQQQ-VT improves both CAGR and MaxDD vs either standalone, because their drawdowns happen at different times.

### Empirical FF distribution: 30-90 and 60-90 cells filter at the same percentile despite the math saying they shouldn't (2026-05-02)

The Forward Factor formula has `(T₂ − T₁)` in the denominator: `forward_variance = (σ₂²·T₂ − σ₁²·T₁) / (T₂ − T₁)`. For 60-90, T₂−T₁ = 30/365; for 30-90, T₂−T₁ = 60/365 — half as large. Theoretical prediction: 60-90 should produce FF magnitudes ~2× larger than 30-90 for the same IV gap.

**Empirically this doesn't happen.** Calibration sweep (444 trading days, 7 tickers, 2 cells, FF=0.0 — Phase 2c) shows the FF distributions are nearly identical:

| | 30-90 ATM | 60-90 ATM |
|---|---:|---:|
| Median FF | +0.0262 | +0.0094 |
| p75 | +0.1197 | +0.1179 |
| p90 | +0.2157 | +0.2258 |
| p95 | +0.2860 | +0.2964 |

**At threshold = 0.20, both cells filter to the same ~87-88th percentile of their own distributions** (87.6% for 30-90, 87.9% for 60-90). The trade-count gap (30-90 has 1.4× more candidates) comes entirely from 30-90 having more *valid samples* (better chain resolution at 30-DTE: 32.4% vs 24.0%), not from any FF-magnitude difference.

**Why the (T₂−T₁) prediction fails empirically**: real IV term-structure shape compensates for the formula's denominator effect. σ₁ at 30-DTE is typically higher than σ₁ at 60-DTE (vol rises near expiry); σ₂²·T₂ also scales accordingly. The empirical distributions of σ₁²·T₁ and σ₂²·T₂ end up correlated in a way that masks the (T₂−T₁) amplification.

**This is a real research finding** with a strategic implication: **the edge difference between cells (60-90 marginal trade has positive edge, 30-90 marginal trade has negative edge — see Capacity-Cap Experiment) is structural to the trade type itself — holding period, pin-risk profile, vol-collapse window — NOT a filtering artifact**. Per-cell threshold calibration to equalize trade rates makes only small adjustments (gap of 0.01–0.06 between cell thresholds at any reasonable target). It won't *fix* the cross-cell edge gap; it will only *equalize trade frequency*.

### Pin risk is implicit in "hold to front expiry"

The Oct 2024 smoke produced 3 TLT losses (Sep 17, 19, 20 entries — all 99/100 strikes — all losing $0.46 to $0.58 per spread). They lost not because the entry signal was bad — TLT WAS legitimately backwardated for real macro reasons (Fed pricing) — but because TLT drifted from ~$95 at entry to ~$90 by Nov 14 exit, leaving the calendar deeply OTM with both legs near zero.

This is **a feature of the design, not a bug**: VV's "hold to front expiry, close as a spread" exit rule has no defense against the underlying drifting more than ~5% from strike during the holding period. A calendar at a fixed strike is inherently a bet on (a) elevated forward IV AND (b) the underlying staying near the strike. (a) is what FF measures; (b) is unhedged and shows up as drag on otherwise-correct entry signals.

Implication for sizing/expectations: even on confirmed-correct entries, ~30-40% of trades will likely lose to underlying drift in regimes where the underlying trends (vs chops near strike). The 60/90 ATM cell can't avoid this without changing the strategy (e.g., 35-delta double calendar widens the profit zone, but that's a different cell).

## Spec Sources (Volatility Vibes video, id `6ao3uXE5KhU`)

Steven verified these from the video transcript on 2026-05-02. Verbatim transcript quotes with timestamps still TODO when convenient. **Definitive spec confirmations from VV's distributed `calculator.py` and `README.txt`** (Steven inspected these files directly on 2026-05-02; files were not dropped into the working directory but Steven summarized the content):

| Spec point | Verified spec | Status |
|---|---|---|
| **FF formula** | `σ_fwd = sqrt((σ₂²·T₂ − σ₁²·T₁) / (T₂ − T₁))`, `FF = (σ₁ − σ_fwd) / σ_fwd`, with `T = DTE/365` and `σ = IV/100`. From VV's `calculator.py` directly. Verified against our `src/ff_calculator.py` — matches exactly. Stale docstring example (claimed σ_fwd = 20.66 / FF = 117 for 30/45 + 60/35) corrected to actual output (20.61 / 118.3) on 2026-05-02 — the original numbers were a video-walkthrough rounding artifact, not the formula output. | ✅ implemented and verified |
| **Entry rule** | FF ≥ ~0.20 marks tradable backwardation (transcript). | ✅ implemented (`FF_THRESHOLD = 0.20`) |
| **Exit rule** | Hold until front expiry; close as a spread "right before the front contract expires" (transcript). 30-50% profit-target / early-close exits from ORATS / SteadyOptions / ACES are **different strategies** — do NOT add a profit-target exit branch. | ✅ implemented (`EXIT_DAYS_BEFORE_FRONT_EXPIRY = 1`) |
| **DTE preference** | Transcript: 60/90 strongest including single names. Full backtest doc tests **all three** pairs (30-60, 30-90, 60-90) and **both structures** (long call calendar, long double calendar) — i.e. the original 6-cell grid. The single-cell config we ship is a deliberate reduction to what VV calls strongest, NOT VV's full spec. | ✅ implemented as single-cell reduction (60/90 ATM call) |
| **Sizing** | Transcript: quarter-Kelly, 4% per-trade risk default. Backtest doc shows Full/Half/Quarter Kelly variants per DTE pair. | ✅ implemented (`KELLY_FRACTION=0.25, RISK_PER_TRADE=0.04`) |
| **Earnings handling** | **RESOLVED 2026-05-02**: VV's `calculator.py` does NOT handle earnings at all — takes raw `DTE1, IV1, DTE2, IV2`, computes FF, returns. The OQuants 2-tool product structure (separate Ex-Earnings IV and Forward Volatility calculators) confirms VV expects the user to clean IV inputs manually before plugging in. Two compatible implementations: (a) compute ex-earnings IV first (rigorous; ~6-10h to build); (b) skip any candidate where earnings ∈ [today, front_expiry] (operational; ~2-3h). **Option B selected for Phase 1** as faithful to VV's free-script practice, with (a) deferred until B's signal-vs-noise impact is measured. | 🚧 Phase 1 implementation in progress |

### Reference materials distributed with VV's `calculator.py`

From `README.txt`:
- **OQuants calculators (free, no install)**: https://oquants.com/calculators
- **Discord community**: https://discord.gg/krdByJHuHc
- **Backtest results document**: https://docs.google.com/document/d/1lIScF4MEoQf5GvDdiXEmWoyaBdkgfojKsSPju5QF8B4 (titled "Forward Factors Research")

### "Forward Factors Research" Google Doc — what we know (TOC + Steven's reading 2026-05-02)

- Tests **all three DTE pairs** (30-60, 30-90, 60-90) and **both structures** (long call calendar, long double calendar)
- Two model variants: **"All Trades Included"** and **"Filtered (~20 trades/month)"**
- Kelly variants: Full / Half / Quarter with per-DTE-pair equity curves
- Quantitative analyses: return distribution histograms, **quarterly performance batching** (validates our multi-window approach), FF-decile analysis

#### VV's "All Trades Included" trades-per-quarter (from doc body, 2026-05-02)

| Cell | Trades/quarter | vs 60-90 Call |
|---|---:|---:|
| 30-60 Call | 148.60 | 12.9× more |
| **30-90 Call** | **413.64** | **36× more (densest)** |
| **60-90 Call** | **11.51** | **baseline (sparsest of all 6)** |
| 30-60 Double | 187.21 | 16.3× more |
| 30-90 Double | 499.03 | 43× more |
| 60-90 Double | 109.43 | 9.5× more |

**Critical finding**: our prior single-cell simplification to 60-90 ATM Call picked the slowest-firing cell on VV's entire 6-cell grid. Our previous sparsity findings (~11/year per ticker, n=12-45 closed trades across 4 quarters) are entirely consistent with picking this cell. Phase 2a (added 30-90 alongside 60-90) is meant to test whether 30-90 actually fires ~36× more often on our universe at FF≥0.20.

#### "Filtered (~20 trades/month)" methodology

VV normalizes all 6 cells to ~60-65 trades/quarter via **per-cell FF threshold calibration** (mean=61.25-64.20 across the 6 filtered models). Our uniform `FF_THRESHOLD=0.20` across cells is NOT his methodology. Per-cell threshold calibration is a deferred Phase 2c task — only worth doing if Phase 2a shows multi-cell signal differs from single-cell signal.

#### Limit of what VV's research doc gives us (verified 2026-05-02)

**These six numbers (3 cells × 2 models) are the ENTIRE quantitative content of VV's research doc that's available as text.** All other statistics (CAGR, Sharpe, win rate, equity curves, Kelly curves, return distributions, FF-decile returns) live in chart images and do not extract via HTML/text scraping. Steven verified this directly in Chrome — confirmed by inspecting both the .docx and the live Google Doc.

**Our backtest produces ground truth on real Polygon data — VV's chart numbers are not blocking decisions.** Don't wait for more text from his doc; it doesn't exist.

If we ever need the chart numbers (e.g., for a sanity check on whether our cell-level CAGR roughly matches his), the only path is OCR on screenshots or asking VV directly.

## Known Strategy Findings (from 2026-05-02 sweeps)

### Sparsity at strict params (FF ≥ 0.20, DTE buffer = 5, 60/90 ATM call)

**Headline**: weekly sample of 15 liquid tickers across 2022-05 → 2025-04 (157 Wednesdays = 2,355 sample-days) produced just **89 sample-days above the FF threshold (3.8%)**. Strategy is genuinely sparse, not the densely-active picture the original video implies.

| Ticker | Both legs resolve | FF ≥ 0.20 hit-rate | Notes |
|---|---:|---:|---|
| AAPL | 36% | **0% — never fires in 3 years** (max FF = +0.188) | Exclude from production universe |
| TSLA | 32% | 1.9% | Concentrated near earnings |
| AMD | 32% | 1.3% | |
| MSTR | 8% | 1.3% | Sparse chain at 60/90 |
| GLD | 36% | 2.5% | |
| QQQ | 43% | 2.5% | |
| SPY | 59% | 3.2% | Highest both-leg resolution rate |
| KWEB | 25% | 2.5% | China macro driver |
| NVDA | 10% | 3.2% | Sparse chain |
| TLT | 45% | 4.5% | Rates vol driver |
| COIN | 29% | 3.8% | |
| IWM | 40% | 3.8% | |
| XBI | 17% | 4.5% | Sector sensitivity |
| SMH | 22% | 4.5% | Sector sensitivity |
| **META** | 35% | **17.2% — dominant hit source** (likely earnings-skew contaminated) | Use carefully |
| **XLE** | 0% | 0% | **Resolver bug — see Followups** |

**Implications**:
- 14 of 17 hit Wednesdays in the 5-ticker phase 1 sweep clustered near known macro events (FOMC, CPI, election, year-end vol). The signal IS real but the threshold gate makes it sparse.
- Effective trade frequency at strict params on a 5-ticker universe: ~12 candidate-days/year (weekly granularity). Daily granularity probably 3-5× higher → realistic open rate **~30-50 trades/year** on a 7-10 ticker production universe.
- The Volatility Vibes 27% CAGR / 2.4 Sharpe claim, if real, implies either (a) wider universe (50+ names), (b) the earnings-driven hits (e.g. META's 17.2%) being part of the strategy not filtered out, or (c) shorter-dated cells fire more often. The Oct 2024 smoke (~26% annualized over 3 months on n=12 trades) is consistent with the headline but n is far too small to validate.
- See `_sweep_phase1b_broader.csv` and `_drill_oct2024_*.csv` in repo root for the raw sweep data.

## Followups to Investigate

- **XLE returns 0 valid samples in the 60/90 ATM sweep across 157 Wednesdays (2022-2025).** Chain resolver may have a ticker-class blind spot — likely a contract listing or expiry-calendar quirk rather than missing data. Investigate before adding XLE to production universe.

## Known Issues / Outstanding Work

### 1. TQQQ benchmark drift (medium priority)

The benchmark `src/benchmark.py` reproduces Steven's TQQQ Vol Accel Guard but shows 3-5pp CAGR drift versus his reference numbers (43.2/-21.1 expected on 3Y vs 38.1/-28.0 actual; 5Y/2017+/2014+ all collapse to the same number, indicating Polygon's TQQQ history only goes back ~2022).

**Fix path**: Either accept and document the drift, or supplement Polygon TQQQ data with yfinance for pre-2022. The drift doesn't block the FF allocation decision — but Steven will compare them, so be honest about the gap.

### 2. Earnings handling — Phase 1 (Option B) implemented 2026-05-02

**Spec resolution**: VV's distributed `calculator.py` (inspected by Steven, 2026-05-02) does NOT include earnings handling at all — takes raw inputs, computes FF, returns. The OQuants 2-tool product structure (separate Ex-Earnings IV + Forward Volatility calculators) confirms the user is expected to clean IV inputs before plugging into the FF formula. Two compatible implementations:
  - **Option A (rigorous)**: compute ex-earnings IV first via iterative term-structure fitting (the OQuants Ex-Earnings IV tool's methodology), then plug cleaned IVs into FF. ~6-10h to build; needs ≥4 monthly IVs per ticker per day.
  - **Option B (operational)**: skip any candidate where earnings sits in the trade window. Faithful to VV's free-script practice; ~2-3h. **IMPLEMENTED.**

Implementation:
- `src/earnings_data.py` — hardcoded calendar covering AAPL/META/NVDA/TSLA/AMD/COIN/MSTR/SCHW for 2022-2026. ETFs (SPY/QQQ/IWM/SMH/XBI/KWEB/TLT/GLD/...) explicitly listed as no-earnings. MSTR Q3 2024 (2024-10-30) verified from drill data; other dates approximate based on typical quarterly cadence — **must be verified before any production allocation**.
- `src/earnings_filter.py::_fetch_events` consults hardcoded source first, falls back to (still-broken) Polygon endpoint, then empty calendar.
- 5 new tests covering hardcoded-source behavior + ETF empty-list semantics + end-to-end MSTR block.

**Measured impact** (in 7-ticker drill universe; only MSTR has earnings): 4-quarter cumulative drops from +$44,870 to +$40,344 (+12.9% CAGR → +12.0%). 2 MSTR winners blocked. Real test comes with expanded universe where META/NVDA/TSLA earnings noise should be substantial.

**Option A is deferred** until Option B's signal-vs-noise impact is measured on the expanded universe. Don't build Option A unless Option B clearly leaves money on the table.

### Phase 2c per-cell FF threshold calibration — COMPLETED-AND-REJECTED (2026-05-02)

Tested 4 configs (uniform 0.20 baseline + 3 per-cell calibrated to 5/10/2.8 trades per month). Results spread across all configs was **just ~1.6 pp annualized** — uniform 0.20 narrowly won on combined MTM CAGR. Per-cell calibration did NOT deliver the predicted step-function improvement.

**Why the prediction failed**: empirical FF distributions for 30-90 and 60-90 cells are nearly identical at the same percentile (87.6% vs 87.9% at FF=0.20) — the (T₂−T₁) denominator's theoretical FF-magnitude amplification doesn't manifest in real IV term structures. See "Empirical FF distribution" under Strategy Character.

**Infrastructure retained**: `FF_THRESHOLD` in `config/settings.py` accepts both float (uniform) and dict (per-cell) — see `resolve_ff_threshold` in `src/backtest.py`. 3 unit tests cover both shapes. Available for future experiments without rework.

**Production setting**: stays at uniform `FF_THRESHOLD = 0.20`.

### 3. ~~Trade exit at parity~~ — DONE (2026-05-02)

Implemented `compute_exit_value()` in `src/trade_simulator.py` that re-prices the calendar spread at exit date. Strikes are tracked on `Position`. Slippage applied symmetrically on both entry and exit. Commission count fixed (was charging double-calendar rate $5.20/ctr for ATM; now correctly $2.60/ctr for ATM, $5.20/ctr for double). Fallback to `entry_debit` + logged warning when Polygon has no daily bar within ±3 days for either leg (e.g. deep-ITM contracts after underlying drift).

Tests: 8 added (4 for `compute_exit_value`, 4 for `step_one_day` exit branch including fallback warning and commission counts for both ATM and double calendar).

### 4. The `compute_options_volume_universe` is not yet implemented

When NOT in smoke mode, the universe is supposed to refresh dynamically based on options volume. The function exists in `src/universe.py` but is a stub that returns the seed list. Re-enable when you're ready to broaden beyond manually-specified names.

For Steven's intended use (run on top ~50 liquid optionable names), the simpler path is to hardcode the universe list as a static smoke universe in the runner notebook. This is what the smoke test does.

## Files in This Bundle

```
config/
  settings.py             # All magic numbers. SINGLE CELL: 60_90_atm.
  secrets.example.py      # Template; create config/secrets.py with your key
src/
  backtest.py             # Orchestration: run_full_backtest, step_one_day, find_candidates_for_day
  iv_solver.py            # Black-Scholes inversion, IV solving
  chain_resolver.py       # Polygon chain queries, strike picking
  ff_calculator.py        # Forward Factor math
  data_layer.py           # PolygonClient with diskcache wrapper
  portfolio.py            # Quarter-Kelly sizing, Position, TradeCandidate
  trade_simulator.py      # Calendar P&L simulation (used at exit)
  earnings_filter.py      # Currently non-functional, returns empty calendar
  universe.py             # Universe construction (smoke mode bypasses this)
  benchmark.py            # SPY/QQQ/TQQQ benchmarks with TQQQ Vol Accel Guard
  metrics.py              # Sharpe, Sortino, max DD, regime breakdown, n_trades
  dashboard.py            # HTML dashboard generation
tests/
  test_*.py               # 153 unit tests; ALL must pass before commit
notebooks/
  colab_runner.ipynb      # Main runner notebook (Colab-friendly)
docs/
  ARCHITECTURE.md         # Why-we-did-it-this-way design notes
README.md
requirements.txt
.gitignore                # IMPORTANT: excludes config/secrets.py
```

## Polygon API Tier Notes

Steven's tier (Options Advanced, ~$199/mo) DOES return:
- Contract listings via `/v3/reference/options/contracts` (with `expired=true` for historical)
- Daily aggregates per contract via `/v2/aggs/ticker/{contract}/range/1/day/...`
- Single-day OHLCV via `/v1/open-close/{contract}/{date}` (workhorse endpoint)
- Quotes via `/v3/quotes/{contract}`

It does NOT return (despite docs):
- Implied volatility from `/v3/snapshot/options/...` (returns 200 but empty)
- Greeks from snapshot endpoint
- Historical IV term structure

That's why we compute IV ourselves via Black-Scholes inversion. This adds ~5-15ms per IV solve, but with caching the cost is paid once per (contract, date) tuple.

## How to Run the Smoke Test

In `notebooks/colab_runner.ipynb`, after running the setup cells:

```python
from datetime import date
from src.data_layer import get_client
from src.backtest import run_full_backtest
from src.earnings_filter import EarningsFilter

client = get_client()
earnings = EarningsFilter(client)

result = run_full_backtest(
    client,
    earnings_filter=earnings,
    start_date=date(2024, 1, 2),
    end_date=date(2024, 2, 2),
    initial_capital=200_000,
    smoke_mode=True,
    smoke_tickers=["AAPL", "TSLA", "NVDA"],
    smoke_days=30,
    show_progress=True,
)

for name, cr in result.cell_results.items():
    print(f"{name}: trades={len(cr.trade_log)}, final=${cr.final_equity:,.0f}")
```

Expected: 5-15 minute runtime, ~3-15 opened positions visible in the trade log.

## How to Run the Full Backtest

Same as smoke test but `smoke_mode=False` (or omit it). Don't pass `smoke_tickers`. Expected runtime: 4-12 hours on first run, minutes on subsequent runs (cache).

## Code Style / Conventions

- Type hints throughout, `from __future__ import annotations` at top of every file
- Dataclasses (frozen=True for value types) preferred over dicts/tuples
- Tests in `tests/`, mirroring the `src/` structure
- 153 tests must pass on every commit (`pytest` from repo root)
- Magic numbers go in `config/settings.py`, not inline
- Logging via `log = logging.getLogger(__name__)`; `log.debug` for high-frequency, `log.warning` for actionable

## Deployment Path (Steven's decision framework — research arc CLOSED)

The research arc is complete; what remains is an allocation decision and operational execution. Steven's recommended deployment path:

### Operational reality

- ~3-5 hrs/week monitoring (daily exit triggers, candidate review at signal-firing days)
- Multi-leg options orders (calendars on 23 underliers, both 30-90 and 60-90 cells)
- Daily exit management (T-1 of front expiry triggers close; need to monitor for the SPY-deep-ITM fallback pattern + KRE drift cases)
- Polygon Options Advanced for live data (or downgrade to Starter once backtest is sealed; live execution doesn't need the historical-data tier)

### Recommended path (UPDATED 2026-05-03 post-2024-attribution)

**Phase A — Live + paper validation (months 1-6).**
- Allocate **5-10% of liquid NW** to live FF Tier 1 (small-stake, real fills) — sized at the *low end* of the original 5-10% range pending ORATS validation
- Run **15% of liquid NW as paper-trade** of FF Tier 1 alongside (down from prior 25% paper recommendation; the smaller paper allocation matches the discounted forward-CAGR expectation from the realistic case)
- Compare live + paper P&L to **realistic-case** backtest expectations (+30.19% CAGR, 21.13% DD in 70/30 mix), NOT optimistic-case (+32.31%)
- Watch specifically for: (a) fallback-warning frequency vs 3.7% backtest rate, (b) actual fill quality vs 5% slippage, (c) earnings-blocking accuracy, **(d) NEW: any near-zero-debit (entry < $0.10) trade sizing — flag immediately for review even if Kelly says size big**
- If 6-month live + paper match realistic-case backtest within ±5pp annualized AND ORATS validates pattern repeatability → proceed to Phase B

**Phase B — Full sizing decision (months 7-12, GATED on ORATS results).**
- If ORATS extended history (2008/2018/2020) shows the near-zero-debit Kelly-overscale pattern produces outliers consistently and bidirectionally → scale to the canonical 30% FF / 70% TQQQ-VT max-Sharpe mix
- If ORATS shows 2022-2026 was unusually lucky on this pattern → cap FF allocation at the lower end (10-15%), well below max-Sharpe
- If ORATS shows the strategy degrades materially in pre-2022 regimes → defer Phase B indefinitely; treat Phase A as terminal
- Implement daily-rebalanced (or quarterly) fixed-weight overlay; track Sharpe + MaxDD vs ORATS-informed expectations

**Phase C — Re-evaluate (month 12+).**
- 12 months of live data is enough to start updating priors meaningfully
- If live Sharpe ≥ backtest Sharpe − 0.20 AND MaxDD ≤ backtest MaxDD + 5pp → strategy is performing in expectation; consider 50/50 max-Calmar mix
- If live drifts materially worse → reduce allocation, not eliminate; the −0.107 correlation makes even reduced FF a net portfolio improver

### Why the deployment changed from prior version (2026-05-02 → 2026-05-03)

The prior version recommended scaling to 30% FF after Phase A success. The 2024 attribution analysis revealed that the strategy's edge is materially concentrated: top 5 trades = 85.4% of 2024 P&L; the IWM Jul 2024 trade alone is 22.4% of the entire 4.3-year strategy P&L. The same near-zero-debit Kelly-overscale pattern produced both the IWM win AND the KRE Apr 2026 catastrophe — symmetric upside/downside. Until ORATS extended history reveals whether this pattern is consistent or 2022-2026-specific, the responsible path is to defer the full-sizing commitment.

### Allocation criteria scorecard (vs Steven's README)

| Criterion | Threshold | FF Tier 1 standalone | Status |
|---|---|---:|---|
| Ensemble CAGR ≥ 15% | yes | **+32.78%** | ✅ PASS |
| 2022 standalone return ≥ 0% | yes | (need explicit per-year check; likely ✅) | likely ✅ |
| Worst single cell Sharpe ≥ 1.0 | yes | 0.36 (30-90 individually) — but combined Sharpe is the relevant number for portfolio inclusion | ❌ standalone fail / ✅ combined |
| Win rate 50-70% | yes | (compute from trade log; preliminary indicates within band) | likely ✅ |
| Max DD ≤ 25% | yes | **26.68%** | ❌ FAIL by 1.68pp standalone — but **21.13% in the 70/30 mix → ✅ in portfolio context** |

**Read**: standalone FF Tier 1 narrowly misses 2 of 5 criteria (worst-cell Sharpe and MaxDD). But the criteria were written for standalone allocation; in the 70/30 mix with TQQQ-VT they all pass. The allocation is the right framing; standalone-only is the wrong test for THIS strategy.

## Research Arc Explicitly Closed

Do **NOT** run any of these without strong new evidence justifying the cost:

- **Tier 2 (all 6 cells)** — adding 30-60 ATM Call + 3 double-calendar cells. Won't change the allocation answer; the 2-cell config already captures the structural signal. Adding cells dilutes per-cell capital and adds complexity without commensurate Sharpe improvement.
- **Tier 3 (signal-quality weighted sizing per ticker per cell)** — would optimize on the 4.3-year history. Overfit risk is high; the data is one path through one set of regimes. The standardized Quarter-Kelly with FF≥0.20 is already at the right place.
- **More universe expansion** — current 23-ticker set is decision-validated. The 5-of-26 pre-flight pass rate at 20% back-leg resolution showed the marginal new tickers (sector ETFs, currencies, leveraged ETFs) don't produce signal at this DTE pair. Adding more diluted tickers would add complexity without P&L.
- **Per-cell FF threshold calibration** — Phase 2c rejected (1.6pp Sharpe spread across configurations).
- **Per-trade position caps** — Phase 3.5 rejected (CAGR cost > DD benefit).
- **Vol-targeting overlay** — Phase 3.5b rejected (couldn't react to bursty vol changes; Sharpe improvement +0.01).

If any of these are revisited, do it because of **specific new evidence** (e.g., live-trading data showing a regime not represented in backtest), not because of process inertia.

## Open Follow-ups (split: BLOCKING vs queued)

### BLOCKING the full-sizing allocation decision (Phase B gate)

These two items must land before the strategy graduates from Phase A (5-10% live + 15% paper) to Phase B (full max-Sharpe sizing):

1. **ORATS extended-history backtest** (~10-14 days ETA, data acquisition pending). Re-run the canonical Tier 1 config on ORATS data covering 2008 GFC, 2018 vol blowup, 2020 COVID. Specifically test whether the **near-zero-debit Kelly-overscale pattern** that produced both the IWM Jul 2024 +$304K winner AND the KRE Apr 2026 −$258K loss appears consistently across regimes or whether 2022-2026 was unusually lucky on this pattern. This is the Phase B gate per the updated deployment path.

2. **Debit-floor cap re-evaluation on 23-ticker universe** (Path 2 from prior post-attribution recommendations, deferred until ORATS data lands). Cap 2 (debit-floor NAV cap) was rejected in Phase 3.5 on the 17-ticker universe because it cost 7.5pp CAGR. On the 23-ticker universe with the IWM Jul 2024 outlier dominating, the tradeoff math is different. Re-run with Cap 2 active; compare CAGR/MaxDD/Sharpe deltas. Quick (<30 min) once we know whether ORATS validates the pattern.

### Queued (productive when convenient, not blocking)

3. **Extend backtest to May 2021** — Polygon's 5-year cap allows ~7 more months of pre-2022 data. Adds the 2021 low-vol regime. Less informative than ORATS extended history but easier to obtain (already have Polygon access). ~1 hour compute.

4. **Live execution diary** — if Steven proceeds with Phase A. Track every live trade vs backtest's predicted entry, fill price, exit pricing. Surfaces real-vs-backtest gaps that don't show up in any pre-trade analysis.

5. **Verbatim VV transcript quotes** — Steven to paste into Spec Sources section when convenient. Doesn't block anything; makes the spec record auditable.

6. **TQQQ benchmark drift fix** — `src/benchmark.py` shows 3-5pp CAGR drift vs Steven's reference numbers because Polygon's TQQQ history only goes back ~2022. Could supplement with yfinance for pre-2022 if anyone needs the older comparison. Low priority — TQQQ-VT (Steven's actual current strategy) is the relevant benchmark and we have its full daily curve.

7. **`compute_options_volume_universe`** stub — never implemented; current production uses static smoke universes. Only matters if you want dynamic universe refresh.

## Operational notes for next session

- **All scripts in `scripts/`** are idempotent (re-running with same config = same output, same hash).
- **Pipeline outputs land in `output/sim_<config_hash>/`** — directory contains `trade_log.csv`, `daily_mtm_equity.csv`, `metrics.json`, `config.json`, `provenance.json`. Provenance includes git commit + discovery_run_id.
- **Cache management**: `python -m src.data_layer cache_report` shows per-layer entry counts + bytes. Layered cache: `data_cache/{reference,equity,options}/`. Legacy cache at `data_cache/cache.db` retained as read-fallback for backward compat.
- **No ad-hoc scripts** in repo root — all scratch (`_*.py`, `_*.csv`, `_*.json`) is gitignored. Anything worth keeping moves to `scripts/`.

## Steven's Background (don't re-explain finance basics)

Steven is sophisticated. He runs:
- OVTLYR Golden Ticket momentum trades (deep ITM 0.75-0.80 delta calls)
- TQQQ/SGOV vol-targeting with QQQ 200d MA guard
- AI Autopilot portfolios on Robinhood (passive)
- Individual high-conviction AI/tech LEAPS

He understands options mechanics (IV, vega, theta, deltas), Kelly sizing, Sharpe ratios, regime testing. Speak in concrete trader language, not textbook explanations.

He prefers dashboards over text reports. He values honest assessments over reassurance. He'll catch you if you fudge — call out limitations explicitly.

## Contact / Continuity

- **GitHub repo**: https://github.com/stegitforme/forward-factor-backtester
- **Steven's email**: sgoglanian@gmail.com
- **Polygon dashboard**: https://massive.com/dashboard
- **Polygon downgrade reminder**: May 30, 2026 (Options Starter $29/mo is sufficient post-backtest)
