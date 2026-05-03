# Forward Factor Backtester — Research Summary

> Self-contained snapshot of the project as of **2026-05-03 (end of day, post Phase 5 stable-version)**. If you've never seen this codebase before (including a future Steven who's lost the context), start here. For full state details see `CLAUDE_CODE_HANDOFF.md`.

> **Status**: NOT decision-ready, NOT research-arc-closed. Phase 5 stable-version revealed the strategy has two distinct alpha modes — unconstrained Tier 1 (+32.78% CAGR, edge driven by near-zero-debit Kelly-overscale lottery-ticket trades) and stable-with-caps (+6.48% CAGR, lottery-ticket pattern neutralized). Three viable interpretations now exist (conservative, aggressive, no-allocation-pending-validation); none is "the canonical answer." **Deployment via Phase A: 5% live STABLE + 10% paper STABLE + Tier 1 journal-only at 5% notional.** Full sizing decision gated on ORATS extended-history results (~10-14 days ETA) per the Phase B decision tree in `CLAUDE_CODE_HANDOFF.md`.

## The strategy in one paragraph

The **Forward Factor (FF)** is a vol term-structure metric from the Volatility Vibes YouTube channel, validated against Campasano's 2018 SSRN paper "Term Structure Forecasts of Volatility." When front-month implied volatility is materially higher than the forward-implied vol between front and back month (FF ≥ 0.20), VV's thesis is that long-calendar spreads (sell front, buy back) capture systematic mispricing as the front leg's elevated IV decays faster than the back. We built an independent backtest of this on Polygon Options Advanced data covering 2022-01-03 → 2026-04-30 (~1,129 trading days). After 4+ phases of research (sparsity findings, single-cell rejection, exit-pricing fix, earnings disambiguation, multi-window stress tests, position-cap and vol-targeting experiments, universe expansion), the canonical configuration is a **2-cell ATM call calendar (30-90 + 60-90 DTE) on a 23-ticker multi-asset universe with hardcoded earnings filter active**. The strategy delivers a **+32.78% standalone CAGR** with **26.68% MaxDD** and **0.77 Sharpe** over the 4.3-year backtest, with **−0.107 daily-returns correlation to Steven's existing TQQQ Vol-Target system** — making it a genuine portfolio diversifier, not just expensive equity-vol exposure in a different costume.

## The headline result — two configs, three interpretations

The strategy has **two distinct alpha modes** depending on how it's sized. Phase 5 (2026-05-03) added structural caps to the canonical config and revealed that the unconstrained engine's edge IS the near-zero-debit Kelly-overscale lottery-ticket pattern — strip that pattern via caps and the strategy yields +6.48% CAGR. That's not "the strategy plus an outlier"; the lottery-ticket pattern is the primary alpha generator.

### Standalone metrics (both configs, full sample 2022-01-03 → 2026-04-30)

| Metric | Tier 1 unconstrained | Stable-version (capped) |
|---|---:|---:|
| MTM CAGR | **+32.78%** | **+6.48%** |
| MaxDD% (PCT-max) | 26.68% | **8.66%** |
| Annualized vol | 53.35% | **11.10%** |
| Sharpe | 0.77 | 0.61 |
| Calmar | 1.23 | 0.75 |
| Closed trades | 643 | 643 |
| End equity | $1,362,520 | $524,653 (on $400K base) |
| Concentration tests passed | (failed top-5 ticker, top-5 trades) | **6 of 7** |

Stable config (`e3fa28f120d1`): half-Kelly (2% per-trade) + debit-floor $0.15 + 12% per-ticker NAV cap + asset-class caps (equity_etf 50% / single_name 20% / commodity 20% / bond 15% / international 15% / vol 10%). All other parameters identical to Tier 1.

### Three viable interpretations vs Steven's TQQQ Vol-Target

Daily-returns correlation: **−0.107** (Tier 1) / **−0.140** (stable). Both negative — diversification benefit is structural across both configs.

| Interpretation | Config | Mix | CAGR | MaxDD% | Sharpe | Read |
|---|---|---|---:|---:|---:|---|
| **Conservative** | stable-version | 50/50 max-Sharpe | **+16.66%** | **16.71%** | **1.12** | Improves portfolio Sharpe (+0.22 vs pure TQQQ-VT) and halves DD; lower CAGR. Deployable today. |
| **Aggressive** | Tier 1 unconstrained | 70/30 max-Sharpe | **+32.31%** | **21.13%** | **1.26** | Best Sharpe AND CAGR uplift, but accepts that the strategy's edge depends on a pattern that produced both biggest win (IWM Jul 2024 +$305K) AND biggest loss (KRE Apr 2026 −$258K). Symmetric lottery-ticket on both sides. |
| **No allocation pending validation** | — | (paper-trade only) | — | — | — | Defer until ORATS extended history (2008/2018/2020) confirms whether the lottery-ticket pattern persists across regimes. |

All three are honest reads of the same data. The "70/30 max-Sharpe is canonical" framing from earlier in the day was incomplete — it didn't account for the fact that the unconstrained engine's edge is structurally lottery-ticket-shaped on both sides. Phase 5 made that visible by stripping the pattern out and showing what's left.

**Why no single canonical answer**: pre-Phase 5, the question was "how big do we deploy the canonical mix?" Post-Phase 5, the question is "which configuration do we trust enough to size into?" That's a fork in the road, not a magnitude calibration. ORATS extended history is the only data that can adjudicate.

## What we tried that didn't work

Three risk-control hypotheses tested rigorously and rejected. All infrastructure remains in `RunConfig` for future re-experimentation but is **disabled by default** in production config.

- **Per-cell FF threshold calibration (Phase 2c).** Hypothesis: 30-90 and 60-90 cells filter unevenly at uniform FF=0.20, so per-cell thresholds calibrated to ~20 trades/month each would equalize edge. Reality: empirically the cells filter to the same ~87-88th percentile at FF=0.20 (the (T₂−T₁) denominator's theoretical FF-magnitude amplification doesn't manifest in real IV term structures). 4 calibrated configs produced just 1.6pp Sharpe spread — uniform 0.20 won narrowly. Per-cell calibration was a no-op.

- **Per-trade position caps (Phase 3.5).** Hypothesis: capping single-trade contracts (especially near-zero-debit calendars that Kelly sizes into massively) would shrink the worst drawdown. Reality: the 5-config sweep showed best DD reduction came at 4× CAGR cost (24.33% → 6.75%). Sharpe and Calmar both worsened across all cap configs vs baseline. The DD wasn't a per-trade-sizing failure — capping individual trades only redistributed risk, didn't reduce it.

- **Strategy-level vol-targeting (Phase 3.5b).** Hypothesis: scaling positions inversely to trailing-30-day realized vol would reduce DD by sizing down before crashes. Reality: 5-config sweep produced Sharpe +0.01 over baseline at best. The April 2026 crash specifically was unfixable: trailing vol said "low vol" right before the crash, so vol-target couldn't react in time. Vol-targeting can't outrun bursty regime changes.

## What we tried that DID work

**Universe diversification across asset classes (Phase 4 Tier 1).** Adding 6 multi-asset tickers (EEM, FXI, HYG, GLD, SLV, USO) to the 17-ticker baseline lifted CAGR from +24.33% → +32.78% AND reduced MaxDD from 31.70% → 26.68% simultaneously — the only intervention that improved both axes at once. Non-equity contribution was $97,678 (10.2% of total P&L), well over the $50K threshold for "FF generalizes beyond equity-vol." Bonds (HYG +$22.9K, TLT +$7.9K), gold (GLD +$13.8K), silver (SLV +$8.8K), oil (USO +$44.2K), and international equity (EEM +$51.2K, FXI +$6.2K) all contributed meaningfully. The signal works on any underlying with a vol term structure — not just equity-vol-specific. Side benefit: the new tickers also displaced marginal incumbent trades (KRE went from −$34K in Phase 3 to +$6K in Tier 1 because higher-FF candidates from new tickers took some slots that previously went to weaker KRE setups). The lesson: the right risk-control lever for THIS strategy is at the strategy-DESIGN level (which underliers to look at), not at the strategy-EXECUTION level (how big to size).

## What's still unknown

- **Forward edge persistence.** 4.3 years of data is the entire backtest window (2022-01-03 to 2026-04-30, capped by Polygon Options Advanced 5-year history). One sample path through one set of regimes. Confidence interval on the +32.78% CAGR is meaningfully wide (±5-8pp). Whether the next 4 years produce similar character is the central unknown — only live deployment will reveal it.

- **Live execution costs.** Backtest assumes 5% slippage on multi-leg fills and $0.65/contract commissions. Real fills on a 23-ticker universe with daily exit management may be worse. The 3.7% fallback-warning rate in the backtest (Polygon data gaps for deep-ITM contracts) is approximated with entry-debit fallback, which produces zero P&L; live equivalents would cost spread.

- **Ex-earnings IV adjustment for single names.** The 5 single names in the universe (META, AMD, GOOGL, JPM, COIN, MSTR) produce **zero opens** because the earnings filter blocks 97-100% of trading days at 60/90 DTE — earnings cycle ≈ back-leg expiry, mathematically. To capture single-name signal at 60/90 would require Option A (subtract earnings vol contribution from front IV before computing FF), an estimated 6-10 hour build that wasn't pursued because Option B + ETF universe proved sufficient.

- **2024-specific contribution.** 2024 contributed +87% CAGR (per Phase 3 per-year breakdown). Whether that year was broad-based or concentrated in 1-2 quarters / 1-2 tickers isn't yet decomposed. If concentrated, the +32.78% full-sample CAGR may overstate steady-state expectation. Queued as a follow-up.

- **Pre-2022 regime data.** Polygon's 5-year cap means 2021 (low-vol) isn't in the backtest. The 2021 regime was structurally different from 2022-2025 and could be a different stress case.

## Deployment path

Three-phase plan that deploys via the stable-version while preserving optionality on the aggressive interpretation.

**Phase A — Now, before ORATS (~10-14 days). Stable deployment + Tier 1 journal.**
- **5% of liquid NW live to STABLE-version config** (`e3fa28f120d1`). Caps neutralize the lottery-ticket pattern, so live execution risk is bounded even if the unconstrained pattern was 2022-2026-lucky.
- **10% of liquid NW as paper-trade of STABLE-version config** in parallel. Tracks real-world execution gaps (slippage, fills, fallback-warning rate) on the deployable variant.
- **Tier 1 unconstrained tracked at 5% notional as journal-only entries** (no real money). Pure-comparison ledger so we can adjudicate stable-vs-aggressive on live data, not just backtest.

This validates execution on the deployable version while preserving optionality. Watch for: fallback-warning frequency vs 3.7% backtest rate; actual fill quality vs 5% slippage; earnings-blocking accuracy; any near-zero-debit (entry < $0.15) trade in the journal-only Tier 1 ledger — those are the structural alpha events; track outcomes.

**Phase B — After ORATS lands (decision tree). Full sizing decision.**

| ORATS finding | Action |
|---|---|
| Stable-version 2008-2021 CAGR > 8% consistently | Caps preserve real edge across regimes — scale STABLE to 15-20% live |
| Stable-version 2008-2021 CAGR < 5% | Strategy is too weak even with caps — paper-only |
| Unconstrained 2008-2021 reveals more IWM/KRE-style outliers | Lottery-ticket pattern is structural — fundamentally rethink; explore vega-targeted sizing variant |
| Unconstrained 2008-2021 CAGR > 25% with no major blowups | The 4.3-year sample understated the strategy — reconsider unconstrained at 15-20% with active monitoring |

**Phase C — Re-evaluate after Phase B has 12 months of live data.** If live performance is in expectation (Sharpe ≥ Phase-B-target − 0.20, MaxDD ≤ Phase-B-target + 5pp), consider scaling within the chosen interpretation. If live drifts worse, reduce but don't eliminate — the negative correlation makes even reduced FF a net portfolio improver.

## Open follow-ups

### BLOCKING the Phase B sizing decision

1. **ORATS extended-history backtest** (~10-14 days ETA, data acquisition pending). Re-run BOTH Tier 1 unconstrained AND Phase 5 stable on 2008/2018/2020 ORATS data. Two questions: does the unconstrained near-zero-debit pattern repeat outside 2022-2026, and does stable-version's +6.48% CAGR survive in older regimes? Both answers feed the Phase B decision tree.
2. **Debit-floor cap re-evaluation on 23-ticker universe** — Cap 2 was rejected on 17-ticker universe; 23-ticker math may differ. ~30 min once ORATS lands.

### Queued — for AFTER ORATS

3. **Vega-targeted sizing variant** — instead of contracts × debit Kelly, size each trade so a 1× vol move produces max P&L change of 0.5% of NAV. Different lever for the near-zero-debit pattern: caps risk per trade (insensitive to debit collapse) rather than cost per trade. Build cost ~3-5 hours; runs on existing candidate data. Don't run before ORATS — its value depends on whether the lottery-ticket pattern repeats. If yes, vega-sizing is the natural next experiment; if no, stable-version is sufficient.

### Productive when convenient (not blocking)

4. **Extend backtest to May 2021** — Polygon's 5-year cap allows ~7 more months of pre-2022 data. ~1 hour compute.
5. **OQuants ex-earnings IV implementation (Option A)** — unlocks single-name signal (5 single names in universe currently produce ~zero opens because earnings filter blocks 97-100% of their days at 60/90 DTE). 6-10 hour build. Only worth doing if Steven wants single-name exposure specifically.
6. **Live execution diary** — once Phase A starts, track every live trade and journal entry vs backtest's predicted entry, fill price, exit pricing. Stable-vs-aggressive comparison lives in the same spreadsheet.
7. **Verbatim VV transcript quotes** — Steven to paste into Spec Sources section of `CLAUDE_CODE_HANDOFF.md` when convenient.

### Items explicitly parked (do NOT pursue without new evidence)

Tier 2 (all 6 cells), Tier 3 (signal-quality weighted sizing — overfit risk on 4.3-year sample), more universe expansion, per-cell FF threshold calibration, per-trade caps in isolation, vol-targeting overlay. All tested or evaluated and either rejected or shown to add complexity without commensurate edge.

## Where to find things

- **`CLAUDE_CODE_HANDOFF.md`** — full project state, all decisions, all caveats. The authoritative source if this RESEARCH_SUMMARY is ambiguous.
- **`scripts/`** — reproducible analysis: `phase4_t1_run.py` (canonical Tier 1), `tqqq_vt_allocation.py` (allocation sweep), `regression_phase3.py` (validates pipeline against Phase 3), pre-flight + sweep scripts for cap/vol-target negative results.
- **`src/`** — production code. `discover_candidates.py` + `simulate_portfolio.py` are the canonical pipeline (replaces older monolithic `backtest.py` flow). `earnings_data.py` holds the hardcoded earnings calendar. `run_config.py` is the hashable config dataclass.
- **`tests/`** — 174 unit tests. `pytest tests/` should pass cleanly.
- **`output/`** — per-config simulation artifacts (`sim_<config_hash>/` directories) + Phase reports (`PHASE_*.md`) + equity-curve PNGs. **Gitignored** (local artifacts; reproducible from `scripts/`).
- **`data_cache/`** — diskcache layered into `reference/`, `equity/`, `options/` (~924MB total, 244K Polygon API responses cached). Run `python -m src.data_layer cache_report` for breakdown.
- **GitHub canonical**: https://github.com/stegitforme/forward-factor-backtester (commit `676b387` is the research-arc-complete pin).

## TL;DR for someone reading in 6 months

> FF has two distinct alpha modes. **Unconstrained Tier 1**: +32.78% CAGR / 26.68% DD standalone, +32.31% / 21.13% / Sharpe 1.26 in 70/30 mix with TQQQ-VT. The edge comes from a near-zero-debit Kelly-overscale lottery-ticket pattern that produced both biggest win (IWM Jul 2024 +$305K, 22.4% of total P&L) AND biggest loss (KRE Apr 2026 −$258K). **Stable-version with structural caps**: +6.48% CAGR / 8.66% DD standalone, +16.66% / 16.71% / Sharpe 1.12 in 50/50 mix. Caps strip the lottery-ticket pattern and reveal what's left underneath. Three viable interpretations now exist (conservative stable, aggressive unconstrained, no-allocation-pending-validation); none is "the canonical answer." Deployment via Phase A: **5% live STABLE + 10% paper STABLE + Tier 1 journal-only at 5% notional**. Full sizing decision gated on ORATS extended-history results (~10-14 days) per Phase B decision tree. Multi-asset universe expansion (Phase 4) was the structural lever that delivered the result; risk caps and vol-targeting in isolation were tested and rejected. Vega-targeted sizing is queued for after ORATS as the next experiment IF the lottery-ticket pattern is shown to repeat. Do not treat this as decision-ready or research-arc-closed — it's a deployable starting position with a clear gate to the full-sizing decision.
