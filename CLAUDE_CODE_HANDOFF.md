# Claude Code Handoff: Forward Factor Backtester

## TL;DR — Strategy has no deployable edge (2026-05-05, post extended history)

> **FINAL STATUS (2026-05-05, post ORATS extended-history backtest)**: The Forward Factor strategy has no deployable edge after rigorous validation. Three findings stack:
>
> 1. **Polygon Tier 1's +32.78% CAGR was data-noise**: BS-IV inversion against stale/thin daily-bar closes produced phantom signals. The IWM Jul 18 2024 trade (formerly +$305K, 22.4% of Polygon P&L) was a $0.03 stale print on an $8.94-$8.99 ATM call — mathematically untradable.
>
> 2. **Clean ORATS data 2008-2026 produces +1.83% CAGR (Tier 1) / +1.35% (stable) over 18+ years.** That's 3,131 trades over 18 years yielding near-zero standalone return. The 2022-2026 era was the *favorable* sub-period; extending the test window collapses the apparent edge.
>
> 3. **Strategy LOSES money in major vol events** — exactly the regimes a vol-term-structure trade should profit from. Feb 2018 Volmageddon: −6.52%. Feb-Apr 2020 COVID: **−13.47%**. 2015 H2 yuan: −2.14%. The thesis "FF ≥ 0.20 captures vol-collapse mispricing" doesn't survive contact with real vol crashes — when underlying actually moves, the calendar gets crushed.
>
> **Diversification benefit also disappears on clean data**: correlation with TQQQ-VT is **+0.040** (clean ORATS) vs **−0.107** (noise-driven Polygon). Max-Sharpe mix 50/50 delivers Sharpe uplift of just +0.02 over pure TQQQ-VT. The negative correlation was an artifact of the noise pattern, not a structural property.
>
> **Recommendation: SHELVE the strategy.** Do not deploy live, do not paper-trade. Operational complexity (multi-leg orders on 23 underliers, daily exit management, earnings tracking) is not justified by ~+1-2% CAGR with negative-regime exposure and no diversification benefit. The research arc is closed; the answer is the strategy doesn't work as advertised, including against VV's published claims.

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

### Final framing (2026-05-05, post extended history): SHELVE

The 2026-05-03 "three interpretations" framing AND the morning-of-2026-05-05 "modest strategy with diversification value" framing are both **superseded** by the extended-history result. There is no deployable edge.

**Final summary across all configs:**

| Config | Window | CAGR | DD% | Sharpe | Trades | Read |
|---|---|---:|---:|---:|---:|---|
| Polygon Tier 1 unconstrained | 2022-2026 | +32.78% | 26.68% | 0.77 | 643 | RETIRED — data noise |
| Polygon Phase 5 stable | 2022-2026 | +6.48% | 8.66% | 0.61 | 643 | Caps suppressed noise; clean number is much lower |
| ORATS Tier 1 (2-cell smvVol) | 2022-2026 | +3.09% | 6.26% | 0.63 | 491 | Adapter validation result |
| **ORATS Tier 1 (3-cell extVol)** | **2008-2026** | **+1.83%** | — | — | 3,131 | **Definitive standalone CAGR** |
| **ORATS Stable (3-cell extVol + caps)** | **2008-2026** | **+1.35%** | — | — | 3,128 | **Caps don't help** |

**Per-regime Tier 1 CAGR (clean ORATS, 3-cell + extVol):**

| Regime | CAGR | Trades | Tickers | Reads |
|---|---:|---:|---:|---|
| 2008 H2 GFC | +0.03% | 165 | 17/23 | Near zero |
| 2009 recovery | +0.14% | 155 | 19/23 | Near zero |
| 2010-2014 grind | +3.77% | 484 | 20/23 | Best non-current period |
| 2015 H2 yuan deval | **−2.14%** | 125 | 21/23 | Negative |
| 2016 H1 Brexit | +8.10% | 85 | 21/23 | Best regime overall |
| **2018 Feb Volmageddon** | **−6.52%** | 36 | 21/23 | **Loses on vol crash** |
| **2020 Feb-Apr COVID** | **−13.47%** | 73 | 22/23 | **Loses badly on vol spike** |
| 2022-2026 current era | +0.88% | 953 | 23/23 | Flat |

**Allocation vs TQQQ-VT (clean ORATS, 2022-2026 overlapping window):**

| Mix (TQ/FF) | CAGR | DD% | Sharpe |
|---|---:|---:|---:|
| 100/0 (pure TQQQ-VT) | +24.46% | 31.43% | 0.90 |
| 50/50 max-Sharpe | +13.27% | 16.70% | **0.92** |
| 0/100 (pure FF Tier 1) | +0.88% | 7.59% | 0.19 |

Sharpe uplift at max-Sharpe mix: **+0.02** (vs +0.36 in the noise-driven Polygon analysis). Correlation: **+0.040** (vs −0.107 noisy). The negative correlation that anchored the diversification argument was an artifact.

**Why every previous interpretation is retired:**

- **"Aggressive 70/30 → +32.31% / Sharpe 1.26"**: data-noise math; the underlying CAGR was Polygon-noise.
- **"Conservative stable 50/50 → +16.66% / Sharpe 1.12"**: also data-noise downstream — caps suppressed the noise but the residual signal isn't enough to support that mix; on clean ORATS data, the equivalent is the +13.27% / Sharpe 0.92 row above (pure TQQQ-VT does almost as well).
- **"Modest strategy with diversification value"**: at +1-3% standalone CAGR with +0.04 correlation, "diversification value" is nominal. A 50/50 mix barely beats pure TQQQ-VT on Sharpe.

Reports for the full forensic trail: `output/PHASE_5_ORATS_ADAPTER_VALIDATION.md`, `output/PHASE_5_METHODOLOGY_DIAGNOSTICS.md`, `output/PHASE_5_REGIME_STRESS_TESTS.md`, `output/PHASE_5_ORATS_BACKTEST_REPORT.md`, `output/PHASE_5_ORATS_ALLOCATION.md`. Sim outputs: `output/orats_extended/sim_d075198d5e15/` (Tier 1) and `output/orats_extended_stable/sim_0b99f17e7a71/` (stable).

### Prior framing (preserved for context, but RETIRED 2026-05-05 evening)

The 2026-05-03 "three interpretations" framing (Conservative stable / Aggressive unconstrained / No-allocation-pending-validation) is **partially retired** by the 2022-2026 ORATS validation. The "Aggressive unconstrained" interpretation hinged on the +32.78% Polygon Tier 1 CAGR being a real-but-lottery-ticket-driven result. The validation showed something more fundamental: **the unconstrained engine's edge wasn't lottery-tickets-from-real-data — it was BS-IV inversion noise from stale/thin daily-bar closes that no actual fill could have captured.**

Three findings end the debate about whether Polygon's headline was real:

1. **IWM 2024-07-18 218C raw bid/ask in ORATS**: ATM call (spot $218.19, strike $218, 64 DTE) traded $8.94 / $8.99 bid/ask. Polygon recorded a $0.03 close — a stale print, mathematically incompatible with a 21% IV ATM option. The +$304,868 trade at 1,578 contracts × $0.0315 was Polygon-data fiction. ORATS captured the same date as a 16-contract × $0.42 trade returning +$1,779 — the realistic outcome.

2. **666 Polygon-fire dates checked against ORATS IV**: Median ORATS smoothSmvVol FF on those days = +0.046; median extVol FF = +0.082. Only 20-30% crossed the 0.20 threshold in either ORATS column. The other 70-80% were Polygon-only signals where quote-based IV showed no backwardation at all.

3. **Phase 5 stable + ORATS Tier 1 + ORATS Path-A all converge in a ~+3-7% band**: Three different mechanisms (caps suppress noise / different data source / different IV column) all collapse the result to roughly the same range. That's the real strategy CAGR; the +32.78% headline was the gap between real edge and added noise.

**Updated three viable interpretations**:

| Interpretation | Config | Mix vs TQQQ-VT | CAGR | Read |
|---|---|---|---:|---|
| **Conservative — deploy stable now** | half-Kelly + caps + 2 cells | 50/50 max-Sharpe | +16.66% combined | Validated by both Phase 5 stable (+6.48% standalone) and ORATS Tier 1 (+3.09% standalone). Deployable today as a portfolio diversifier. Standalone CAGR is modest; portfolio Sharpe uplift +0.22 vs pure TQQQ-VT. |
| **Optimistic — methodology improvements** | 3 cells + extVol (Path A) + caps | TBD | est. ~+8-12% standalone | Diagnostics suggest 3-cell + extVol could push CAGR to 8-12%. Pending: extended history validation across 2008-2026 to confirm the methodology improvements survive regime stress. |
| **Discard headline +32.78%** | — | — | — | The Polygon Tier 1 +32.78% / 70-30 mix +32.31% / Sharpe 1.26 numbers are **retired**. They were data artifacts, not research benchmarks. Anyone reading the project history needs this disclosure. |

**Deployment recommendation (unchanged)**: Phase A = 5% live STABLE + 10% paper STABLE + Tier 1 journal-only at 5% notional. The journal-only Tier 1 ledger now carries an additional purpose: live-test the IWM-style noise pattern. If real-world fills mirror ORATS bid/ask pricing rather than Polygon's stale-close pricing, the journal-only Tier 1 should produce results closer to ORATS's +3.09% than Polygon's +32.78%, confirming the diagnostic.

**Why the noise interpretation is more honest than "lottery-ticket pattern"**: A lottery-ticket pattern would still be a real strategy property — just a high-variance one. A data-noise-driven result isn't a property of the strategy at all; it's a property of which data source you used. The ORATS validation makes the latter the better explanation for the +32.78%.

Reports: `output/PHASE_5_STABLE_VERSION.md`, `output/PHASE_5_STABLE_ALLOCATION.md`, `output/sim_e3fa28f120d1/` (stable). `output/PHASE_5_ORATS_ADAPTER_VALIDATION.md`, `output/PHASE_5_METHODOLOGY_DIAGNOSTICS.md`, `output/orats_validation/sim_fb5fb0d6b38e/` (ORATS validation).

**Primary user**: Steven Goglanian, sgoglanian@gmail.com. Polygon Options Advanced paid through May 14, 2026 — downgrade May 30.

## Why the original Polygon backtest overstated returns (added 2026-05-05)

**This section is required reading before quoting any number from the Polygon Tier 1 result (`output/sim_4119dc073393/`)**. The 2022-2026 ORATS adapter validation surfaced a fundamental issue that wasn't visible during the Polygon-only research arc: the strategy's pipeline computes IVs by inverting Black-Scholes against Polygon's daily-bar closing price for ATM options. For thinly-traded strikes — including most of the strikes that produced the highest FF readings — the daily close is frequently a stale print far below the true bid/ask midpoint. Inverting BS against that stale price produces a fake-low IV, which produces a fake-high FF (front IV >> back IV when front IV is artificially deflated), which fires "signals" that no actual fill could ever capture.

### The IWM Jul 18 2024 case study

Single highest-impact trade in the Polygon Tier 1 result (`output/sim_4119dc073393/trade_log.csv`):

| Field | Polygon record | ORATS reality (same date, same strike) |
|---|---:|---:|
| Front strike (ATM call) | $218 | $218 |
| Spot price | ~$218 | $218.19 |
| Front leg DTE | ~64 | 64 (chain expiry 2024-09-20) |
| Front leg cBidPx | (not recorded; BS inverted) | **$8.94** |
| Front leg cAskPx | (not recorded; BS inverted) | **$8.99** |
| Front leg cMidPx | (not recorded; BS inverted) | **$8.965** |
| Front leg `cValue` (ORATS smooth-fair) | — | $8.96 |
| Front leg cMidIv | (BS-inverted from close) | **0.2122** |
| **Polygon's recorded entry_debit (calendar)** | **$0.0315** | impossible at this IV |
| ORATS' realistic calendar debit | — | ~$1.50-$2.00 |
| Polygon contracts (Kelly-sized off $0.0315) | **1,578** | — |
| ORATS contracts (Kelly-sized off ~$1.75) | — | 16 |
| Polygon recorded P&L | **+$304,868** | — |
| ORATS measured P&L | — | +$1,779 |
| Share of total Polygon strategy P&L | **22.4%** | — |

This single Polygon record represents 22.4% of total Polygon strategy P&L. It was previously framed as a "near-zero-debit Kelly-overscale lottery-ticket trade" — a real but high-variance phenomenon. The ORATS data shows the truth: the $0.0315 debit was a backtest artifact derived from a stale daily-bar print. Steven could not have entered this trade at $0.0315; the realistic fill price was ~$1.75. At that price, Kelly sizes ~16 contracts, not 1,578, and the realistic outcome is ~+$1,779.

### How systematic is the noise?

We checked all 666 (cell, ticker, date) signals from the Polygon Tier 1 trade log against ORATS' two IV columns on the same dates:

| ORATS IV column | Median FF on Polygon-fire days | % crossing 0.20 threshold |
|---|---:|---:|
| smoothSmvVol (smoothed surface) | +0.046 | **20.1%** |
| extVol (ex-earnings IV) | +0.082 | **29.3%** |

**70-80% of Polygon-fire days showed no FF backwardation at all in ORATS data**, regardless of IV column choice. Only the 20-30% that ORATS independently confirmed are real signals — and those produced the +3.09% standalone CAGR in the ORATS Tier 1 backtest, in the same band as Phase 5 stable's +6.48%.

### Three independent confirmations of the modest-CAGR finding

| Mechanism | CAGR | Why this kills the noise |
|---|---:|---|
| Polygon Tier 1 unconstrained | +32.78% | (the contaminated number) |
| Polygon Phase 5 stable (caps neutralize outliers) | +6.48% | Per-ticker NAV caps + debit-floor mechanically cap any single trade's contribution; the noise-driven 1,578-contract IWM trade gets trimmed to ~12 contracts |
| ORATS Tier 1 unconstrained smoothSmvVol | +3.09% | Bid/ask quote pricing rejects phantom fills; ORATS smoothing also dampens IV spikes that would have produced false-positive FF readings |

Three different fixes (cap-based / data-source-based / column-based) all collapse the result to the +3-7% band. That convergence makes the modest-CAGR conclusion robust.

### What this means for forward expectations

The deployable strategy is **fundamentally modest** with diversification value vs Steven's TQQQ-VT, not a +30% standalone CAGR alpha source. The 70/30 max-Sharpe answer (Sharpe 1.26, +32.31% combined CAGR) that anchored deployment recommendations through 2026-05-03 is **retired**. Pending extended-history work (2008-2026, methodology-improved with 3-cell + extVol Path A), realistic standalone CAGR is **+3% to +12%** range. Allocation analysis must be re-done on this scale.

### What this DOESN'T change

- Phase 5 stable's +6.48% standalone CAGR was derived from the same Polygon data but with caps that mechanically suppressed the noise-driven trades. It survives this finding cleanly.
- The −0.107 daily-returns correlation with TQQQ-VT is a structural property of FF (it's a vol term-structure strategy, TQQQ-VT is a vol-targeted equity strategy — they respond to different shocks at different times). Diversification benefit is real even if the standalone CAGR is modest.
- The ATM call calendar mechanics, FF computation, and earnings filter logic are all correct. The validation found a data-quality issue, not a strategy-logic bug.

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

### Recommended path (UPDATED 2026-05-03 post-Phase-5-stable)

**Phase A — Now, before ORATS (~10-14 days). Stable-version deployment + Tier 1 journal.**
- Allocate **5% of liquid NW live to STABLE-version config** (config_hash `e3fa28f120d1`: half-Kelly, debit-floor $0.15, 12% per-ticker NAV cap, asset-class caps). This is the deployable starting position — the stable version's caps neutralize the near-zero-debit Kelly-overscale pattern, so live execution risk is bounded even if the unconstrained pattern was 2022-2026-lucky.
- Run **10% of liquid NW as paper-trade of STABLE-version config** in parallel — track real-world execution gaps (slippage, fills, fallback-warning rate) on the deployable variant.
- Track **what unconstrained Tier 1 would have done at 5% notional as journal entries** (no real money) — pure-comparison ledger so we can adjudicate stable-vs-aggressive on live data, not just backtest. This costs nothing operationally; it's a spreadsheet of phantom trades sized as the unconstrained engine would have.
- Validates execution on the deployable version while preserving optionality on whether to scale up via stable or pivot to aggressive once ORATS lands.
- Watch for: (a) fallback-warning frequency vs 3.7% backtest rate, (b) actual fill quality vs 5% slippage assumption, (c) earnings-blocking accuracy, (d) any near-zero-debit (entry < $0.15) trade in the journal-only Tier 1 ledger — those are the structural alpha events; track outcomes.

**Phase B — After ORATS results land (decision tree below). Full sizing decision.**
ORATS extended-history backtest (2008 GFC, 2018 vol blowup, 2020 COVID) is the gating dataset. Decision tree:

| ORATS finding | Interpretation | Action |
|---|---|---|
| **Stable-version 2008-2021 CAGR > 8% consistently** | Caps preserve real edge across regimes | Scale STABLE to 15-20% live; keep journaling Tier 1 |
| **Stable-version 2008-2021 CAGR < 5%** | Strategy is too weak even with caps | Stay paper-only; close stable live position |
| **Unconstrained 2008-2021 reveals MORE IWM/KRE-style outliers** | Lottery-ticket pattern is structural across regimes — both upside and downside repeat | Fundamentally rethink — explore vega-targeted sizing variant before committing capital to unconstrained |
| **Unconstrained 2008-2021 CAGR > 25% with no major blowups** | The 4.3-year sample understated the strategy; near-zero-debit pattern is reliably one-sided in real history | Reconsider unconstrained at 15-20% live with active monitoring; keep stable as risk-control fallback |

**Phase C — Re-evaluate after Phase B has 12 months of live data.**
- If live Sharpe ≥ Phase-B-target Sharpe − 0.20 AND MaxDD ≤ Phase-B-target MaxDD + 5pp → strategy is performing in expectation; consider scaling within the chosen interpretation (stable→25%, aggressive→25-30%, etc.)
- If live drifts materially worse → reduce allocation but don't eliminate; the negative correlation makes even reduced FF a net portfolio improver
- Re-run Phase 5 stable-version + allocation sweep on the live + ORATS combined dataset to refresh the three-interpretation table

### Why the deployment changed from prior version (2026-05-02 → 2026-05-03 → 2026-05-03 evening)

**Morning (2026-05-03)**: Reduced Phase A from 30% canonical to 5-10% live + 15% paper after 2024-attribution revealed concentration risk. Still framed around the unconstrained Tier 1 70/30 mix as the ultimate target.

**Evening (2026-05-03)**: Phase 5 stable-version revealed that caps strip the strategy's edge to +6.48% CAGR — the unconstrained engine's alpha *is* the near-zero-debit Kelly-overscale pattern, not "the strategy plus an outlier." That changes the question from "how much of the canonical mix do we deploy?" to "which interpretation do we trust enough to size into?" Phase A now deploys the stable variant (deployable on its own merits as a portfolio diversifier even if standalone CAGR is modest) and journals the unconstrained variant for live-data comparison. Phase B is now a fork in the road, not a scale-up of the morning's path.

### Allocation criteria scorecard (vs Steven's README) — three-interpretation view

| Criterion | Threshold | Tier 1 unconstrained | Stable-version | Status |
|---|---|---:|---:|---|
| Ensemble CAGR ≥ 15% | yes | **+32.78%** standalone / **+32.31%** in 70/30 mix | **+6.48%** standalone / **+16.66%** in 50/50 mix | ✅ unconstrained / ✅ stable in mix only |
| 2022 standalone return ≥ 0% | yes | +44.70% (per Phase 5 attribution table) | +10.83% | ✅ both |
| Worst single cell Sharpe ≥ 1.0 | yes | 0.36 (30-90 individually) | 0.61 combined | ❌ both standalone / ✅ both in mix |
| Win rate 50-70% | yes | preliminary within band | (compute) | likely ✅ both |
| Max DD ≤ 25% | yes | **26.68%** standalone / **21.13%** in mix | **8.66%** standalone / **16.71%** in mix | ❌ unconstrained standalone / ✅ unconstrained in mix / ✅ stable both |

**Read**: criteria were written assuming a single canonical allocation, but Phase 5 produced two viable configs. Both pass in their respective max-Sharpe mixes. Stable wins on standalone DD but loses on standalone CAGR; unconstrained is the inverse. The choice between them is a judgment call about lottery-ticket pattern persistence — exactly the question ORATS is meant to answer.

## Research Arc — what's PARKED vs what's still OPEN

The research arc is **not** closed; it's bifurcated. Phase 5 stable revealed the strategy has two distinct modes (capped vs uncapped) with materially different alpha profiles, and ORATS is needed to adjudicate between them. Some experiments are fully parked, others are explicitly active but not blocking.

### Parked — do NOT run without strong new evidence

- **Tier 2 (all 6 cells)** — adding 30-60 ATM Call + 3 double-calendar cells. Won't change the allocation answer; the 2-cell config already captures the structural signal. Adding cells dilutes per-cell capital and adds complexity without commensurate Sharpe improvement.
- **Tier 3 (signal-quality weighted sizing per ticker per cell)** — would optimize on the 4.3-year history. Overfit risk is high; the data is one path through one set of regimes.
- **More universe expansion** — current 23-ticker set is decision-validated. The 5-of-26 pre-flight pass rate at 20% back-leg resolution showed the marginal new tickers (sector ETFs, currencies, leveraged ETFs) don't produce signal at this DTE pair.
- **Per-cell FF threshold calibration** — Phase 2c rejected (1.6pp Sharpe spread across configurations).
- **Per-trade position caps in isolation** — Phase 3.5 rejected for unconstrained engine (CAGR cost > DD benefit). Cross-cell caps in Phase 5 stable are a different experiment and produced a deployable variant.
- **Vol-targeting overlay** — Phase 3.5b rejected (couldn't react to bursty vol changes; Sharpe improvement +0.01).

### Open — explicitly active, gated on ORATS or live data

- **Stable-version vs unconstrained interpretation choice** — gated on ORATS extended-history results (~10-14 days ETA). See Phase B decision tree above.
- **Vega-targeted sizing variant** — queued for after ORATS. See Open Follow-ups section. Build cost ~3-5 hours; only justified if ORATS shows the lottery-ticket pattern repeats.
- **Debit-floor cap re-evaluation on 23-ticker universe** — gated on ORATS; quick (<30 min) once we know whether the pattern validates.

If any of the parked items are revisited, do it because of **specific new evidence** (e.g., live-trading data showing a regime not represented in backtest), not because of process inertia.

## Open Follow-ups (split: BLOCKING vs queued)

### BLOCKING the full-sizing allocation decision (Phase B gate)

These two items must land before the strategy graduates from Phase A (5% live STABLE + 10% paper STABLE + Tier 1 journal) to a Phase B sizing commitment:

1. **ORATS extended-history backtest** (~10-14 days ETA, data acquisition pending). Re-run BOTH the unconstrained Tier 1 config AND the Phase 5 stable config on ORATS data covering 2008 GFC, 2018 vol blowup, 2020 COVID. Two questions answered simultaneously: (a) does the unconstrained near-zero-debit Kelly-overscale pattern repeat outside 2022-2026, and (b) does the stable-version's +6.48% CAGR survive in older regimes or collapse further? Decision tree consumes both answers — see Phase B table above.

2. **Debit-floor cap re-evaluation on 23-ticker universe** (Path 2 from prior post-attribution recommendations, deferred until ORATS data lands). Cap 2 (debit-floor NAV cap) was rejected in Phase 3.5 on the 17-ticker universe because it cost 7.5pp CAGR. On the 23-ticker universe with the IWM Jul 2024 outlier dominating, the tradeoff math is different. Re-run with Cap 2 active; compare CAGR/MaxDD/Sharpe deltas. Quick (<30 min) once we know whether ORATS validates the pattern.

### Queued — for AFTER ORATS results land

3. **Vega-targeted sizing variant** — instead of contracts × debit Kelly sizing, size each trade so a 1× vol move produces max P&L change of 0.5% of NAV. Different lever for addressing the near-zero-debit pattern: caps the *risk* per trade rather than the *cost* per trade, which should be insensitive to debit collapse. Build cost: ~3-5 hours; runs on existing candidate data. **Don't run before ORATS** — its value depends on whether ORATS shows the lottery-ticket pattern repeats (in which case vega-sizing is the right next experiment) or doesn't (in which case stable-version is enough and vega-sizing is unnecessary complexity). Queued, not scheduled.

### Queued (productive when convenient, not blocking)

4. **Extend backtest to May 2021** — Polygon's 5-year cap allows ~7 more months of pre-2022 data. Adds the 2021 low-vol regime. Less informative than ORATS extended history but easier to obtain (already have Polygon access). ~1 hour compute.

5. **Live execution diary** — Steven proceeds with Phase A. Track every live trade vs backtest's predicted entry, fill price, exit pricing. Surfaces real-vs-backtest gaps that don't show up in pre-trade analysis. Track the journal-only Tier 1 ledger in the same spreadsheet so stable-vs-aggressive comparison is one click.

6. **Verbatim VV transcript quotes** — Steven to paste into Spec Sources section when convenient. Doesn't block anything; makes the spec record auditable.

7. **TQQQ benchmark drift fix** — `src/benchmark.py` shows 3-5pp CAGR drift vs Steven's reference numbers because Polygon's TQQQ history only goes back ~2022. Could supplement with yfinance for pre-2022 if anyone needs the older comparison. Low priority — TQQQ-VT (Steven's actual current strategy) is the relevant benchmark and we have its full daily curve.

8. **`compute_options_volume_universe`** stub — never implemented; current production uses static smoke universes. Only matters if you want dynamic universe refresh.

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
