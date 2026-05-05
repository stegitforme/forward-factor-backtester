# Forward Factor Backtester — Research Summary

> Self-contained snapshot of the project as of **2026-05-05 (FINAL, post ORATS extended-history backtest)**. If you've never seen this codebase before (including a future Steven who's lost the context), start here. For full forensic trail see `CLAUDE_CODE_HANDOFF.md`, especially "Why the original Polygon backtest overstated returns" and the per-regime tables.

> **FINAL STATUS**: The Forward Factor strategy has no deployable edge. Polygon's headline +32.78% CAGR was BS-IV inversion noise from stale daily-bar closes (single-trade case study: IWM Jul 18 2024 218C, Polygon recorded $0.03 close on an ATM call that ORATS shows trading $8.94-$8.99 bid/ask — mathematically untradable). On clean ORATS data 2008-2026 (18+ years, 3,131 trades, 3 cells, extVol Path A, era-adaptive dte_buffer), the strategy delivers **+1.83% CAGR** (Tier 1 unconstrained) / **+1.35% CAGR** (Phase 5 stable with caps). It LOSES money in major vol regimes: −13.47% in COVID Feb-Apr 2020, −6.52% in Feb 2018 Volmageddon, −2.14% in 2015 H2 yuan deval. Diversification benefit also vanishes on clean data: correlation with TQQQ-VT is **+0.040** (was −0.107 on noisy Polygon data); max-Sharpe mix delivers Sharpe uplift of just +0.02 over pure TQQQ-VT. **Recommendation: SHELVE.** Do not deploy live, do not paper-trade. Operational complexity (multi-leg orders on 23 underliers, daily exit management, earnings tracking) is not justified by ~+1% CAGR with negative-regime exposure.

## The strategy in one paragraph

The **Forward Factor (FF)** is a vol term-structure metric from the Volatility Vibes YouTube channel, validated against Campasano's 2018 SSRN paper "Term Structure Forecasts of Volatility." When front-month implied volatility is materially higher than the forward-implied vol between front and back month (FF ≥ 0.20), VV's thesis is that long-calendar spreads (sell front, buy back) capture systematic mispricing as the front leg's elevated IV decays faster than the back. We built an independent backtest covering 2022-01-03 → 2026-04-30 (~1,129 trading days) and found, after extensive validation, that **the strategy is real but modest** — standalone CAGR in the +3-7% range on clean data (ORATS bid/ask quotes) vs the +32.78% the original Polygon backtest reported (which was inflated by BS-IV inversion noise from stale daily-bar closes at thin strikes). The −0.107 daily-returns correlation with Steven's TQQQ-VT is structurally robust across data sources, making FF a genuine diversifier even at the realistic standalone CAGR.

## Final result — strategy has no deployable edge

The 18+-year ORATS backtest with methodology improvements (3 cells + extVol Path A) is the definitive finding. Earlier "modest strategy with diversification value" framing (morning of 2026-05-05) was based on the favorable 2022-2026 sub-period; extending to 2008-2026 reveals the strategy doesn't have edge in older regimes either.

### Standalone CAGR by config and window

| Config | Window | CAGR | Trades | Status |
|---|---|---:|---:|---|
| Polygon Tier 1 unconstrained | 2022-2026 | +32.78% | 643 | **RETIRED — data noise** |
| Polygon Phase 5 stable (caps) | 2022-2026 | +6.48% | 643 | Caps suppressed noise; clean number is much lower |
| ORATS Tier 1 (2-cell smvVol, earnings filter) | 2022-2026 | +3.09% | 491 | Adapter validation result |
| **ORATS Tier 1 (3-cell extVol Path A)** | **2008-2026** | **+1.83%** | **3,131** | **Definitive standalone** |
| **ORATS Stable (3-cell extVol + caps)** | **2008-2026** | **+1.35%** | **3,128** | **Caps don't help** |

### Per-regime Tier 1 CAGR (clean ORATS, full extended history)

| Regime | CAGR | Trades | Tickers | Reads |
|---|---:|---:|---:|---|
| 2008 H2 GFC | +0.03% | 165 | 17/23 | Near-zero |
| 2009 recovery | +0.14% | 155 | 19/23 | Near-zero |
| 2010-2014 grind | +3.77% | 484 | 20/23 | Best non-current period |
| 2015 H2 yuan deval | **−2.14%** | 125 | 21/23 | Negative |
| 2016 H1 Brexit | +8.10% | 85 | 21/23 | Best regime overall |
| **2018 Feb Volmageddon** | **−6.52%** | 36 | 21/23 | **Loses on vol crash** |
| **2020 Feb-Apr COVID** | **−13.47%** | 73 | 22/23 | **Loses badly on vol spike** |
| 2022-2026 current era | +0.88% | 953 | 23/23 | Flat |

The strategy LOSES money in the regimes where a vol-term-structure trade is supposed to perform best. When real vol crashes happen, the underlying moves more than the IV anticipates and the calendar gets crushed. The thesis "FF ≥ 0.20 captures vol-collapse mispricing" doesn't survive contact with actual vol crashes.

### Allocation analysis on clean data

Daily-returns correlation FF Tier 1 vs TQQQ-VT (2022-2026 overlap, the only window where TQQQ-VT data exists): **+0.040** — slightly positive, not negative. The −0.107 correlation that anchored the earlier diversification argument was noise-driven.

| Mix (TQQQ-VT/FF Tier 1) | CAGR | MaxDD% | Sharpe |
|---|---:|---:|---:|
| 100/0 (pure TQQQ-VT) | +24.46% | 31.43% | 0.90 |
| 90/10 | +22.35% | 28.66% | 0.91 |
| 70/30 (was max-Sharpe in noisy version) | +17.93% | 22.85% | 0.91 |
| **50/50 max-Sharpe (clean)** | **+13.27%** | **16.70%** | **0.92** |
| 0/100 (pure FF) | +0.88% | 7.59% | 0.19 |

Sharpe uplift at max-Sharpe mix: **+0.02** over pure TQQQ-VT. CAGR cost: −11.19pp. Translation: there's almost no mathematical reason to add FF — pure TQQQ-VT does almost as well risk-adjusted, with much higher CAGR.

### The IWM Jul 2024 disclosure (single most important data point)

The case study that ended the debate about whether Polygon's +32.78% was real:

| | Polygon record | ORATS bid/ask reality |
|---|---:|---:|
| ATM 218C entry price (front leg) | $0.03 (stale close) | $8.94 / $8.99 / $8.96 (mid) |
| Implied calendar debit | $0.0315 | ~$1.50-$2 |
| Kelly-sized contracts | 1,578 | 16 |
| Recorded P&L | +$304,868 | +$1,779 |
| % of total strategy P&L | 22.4% | 0.13% |

A 64-DTE ATM call at 21% IV cannot trade at $0.03. The Polygon entry was a stale daily-bar print, not a tradable price. This single trade carried 22.4% of total Polygon strategy P&L — and the corresponding ORATS trade carries 0.13%. The pattern is systematic: Polygon's BS-IV inversion against thin/stale closes produces phantom signals, the highest-FF ones get Kelly-overscaled into the trade log, and they dominate aggregate P&L.

## What this means

**The research arc is closed; the answer is the strategy doesn't work as advertised.** Volatility Vibes' published +27% CAGR claim isn't reproducible from clean data; our independent ORATS backtest produces +1-2% CAGR over 18+ years with negative exposure to major vol events. The diversification benefit that was the project's fallback case is also gone (correlation +0.04, not −0.11).

**Recommendation: SHELVE the strategy.** Do not deploy live, do not paper-trade. The original go/no-go criteria from the project README all fail on clean data:

- CAGR ≥ 15%: ❌ (+1.83% over 18 years)
- Worst-cell Sharpe ≥ 1.0: ❌
- 2022 standalone return ≥ 0%: ✓ but barely (+0.88%)
- Win rate 50-70%: TBD (likely below 50% given negative-regime exposure)
- Max DD ≤ 25%: ✓ (because trade size is small, not because strategy is robust)

**What was learned (positive):**
- ORATS adapter built; reusable for future options-strategy backtests
- IWM Jul 2024 case study is a clean teaching moment about the dangers of close-price BS-IV inversion at thin strikes
- Polygon's daily option bars are unreliable for backtest purposes at non-front-month / non-ATM contracts
- VV's published claims should be treated skeptically pending independent replication on bid/ask quote data

---

(The rest of this document preserves the prior narrative arc for forensic context. The "three confirmations of a modest strategy" section below was the morning-of-2026-05-05 framing; it has been superseded by the extended-history result above. Keeping for the audit trail.)

## The headline result — three confirmations of a modest strategy

Three independent treatments of the same Polygon backtest data converge on a CAGR in the +3-7% range, while the original Polygon Tier 1 unconstrained number was +32.78%. The 25+pp gap is **data noise, not strategy edge**.

### Standalone metrics: three configs over 2022-2026

| Config | Mechanism | Standalone CAGR | MaxDD% | Sharpe | Trades | What it tells us |
|---|---|---:|---:|---:|---:|---|
| Polygon Tier 1 unconstrained | (the contaminated number) | +32.78% | 26.68% | 0.77 | 643 | Inflated by BS-IV inversion noise on stale daily closes — see "Why Polygon overstated returns" in HANDOFF |
| Polygon Phase 5 stable | Caps mechanically suppress noise-driven trades | **+6.48%** | 8.66% | 0.61 | 643 | First independent confirmation: cap the size, the noise CAGR vanishes |
| **ORATS Tier 1 unconstrained** (smoothSmvVol) | Different data source rejects phantom fills | **+3.09%** | 6.26% | 0.63 | 491 | Second independent confirmation: bid/ask pricing won't fill at $0.03 phantom levels |
| ORATS Tier 1 with extVol (Path A) | Different IV column (ex-earnings) | (full sim TBD; diagnostic suggests similar range) | — | — | — | Third independent treatment available |

The convergence of stable (+6.48%) and ORATS Tier 1 (+3.09%) on a similar band is decisive. The strategy delivers ~+3-7% standalone CAGR; the +32.78% headline was Polygon-data artifacts.

### The IWM Jul 2024 disclosure

The single highest-impact Polygon trade — and the one that anchored the "lottery-ticket pattern" framing in the prior version of this summary — is now disclosed as a backtest artifact:

| | Polygon record | ORATS bid/ask reality |
|---|---:|---:|
| ATM 218C entry price | $0.03 (stale close) | $8.94 / $8.99 / $8.96 (mid) |
| Implied debit (calendar) | $0.0315 | ~$1.50-$2 |
| Kelly-sized contracts | 1,578 | 16 |
| Recorded P&L | +$304,868 | +$1,779 |
| % of total strategy P&L | 22.4% | 0.13% |

A 64-DTE ATM call at 21% IV cannot trade at $0.03 — bid was $8.94. The Polygon entry was mathematically impossible to fill. Steven could not have entered this trade at the recorded price; the strategy did not have +$305K of edge here.

### What replaces the prior "three viable interpretations"

The 2026-05-03 framing (Conservative stable / Aggressive unconstrained / No-allocation) is replaced. The "Aggressive unconstrained 70/30 mix → +32.31% CAGR / Sharpe 1.26" interpretation is **retired**: the standalone CAGR feeding it was data noise. New framing:

| Interpretation | Config | Standalone CAGR | Mix vs TQQQ-VT | Read |
|---|---|---:|---|---|
| **Conservative — deploy now** | Phase 5 stable (caps + half-Kelly) | +6.48% | 50/50 max-Sharpe → +16.66% combined CAGR, Sharpe 1.12, MaxDD 16.71% | Validated; deployable today as portfolio diversifier (not primary alpha source). |
| **Methodology-improved** (pending) | 3 cells + extVol Path A + caps | est. +8-12% | TBD | Phase 5 methodology diagnostics suggest 3-cell + extVol could push standalone CAGR to ~+8-12%. Pending: extended-history backtest 2008-2026 to validate across regimes. |
| **Reject all noise alpha** | (always) | — | — | The +32.78% Polygon Tier 1 / 70/30 mix +32.31% / Sharpe 1.26 numbers are **retired** as research benchmarks. Anyone reading older project history needs this disclosure. |

Daily-returns correlation: **−0.107** (Polygon Tier 1) / **−0.140** (Polygon stable). Negative correlation is structural and survives the noise correction — diversification benefit is real even at the modest standalone CAGR.

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
