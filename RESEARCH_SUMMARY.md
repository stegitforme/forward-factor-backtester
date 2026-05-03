# Forward Factor Backtester — Research Summary

> Self-contained snapshot of the project as of **2026-05-03** (updated post-2024-attribution + Path 1 sensitivity). If you've never seen this codebase before (including a future Steven who's lost the context), start here. For full state details see `CLAUDE_CODE_HANDOFF.md`.

> **Status**: research arc PROVISIONALLY complete. The core findings are stable, but the allocation answer is now bracketed (optimistic / realistic / forward-looking) pending two validations: (a) ORATS extended-history backtest covering 2008/2018/2020, and (b) debit-floor cap re-test on the 23-ticker universe. Initial deployment recommendation: **5-10% live + 15% paper trade as Phase A**, with full sizing decision deferred until ORATS lands (~10-14 days ETA).

## The strategy in one paragraph

The **Forward Factor (FF)** is a vol term-structure metric from the Volatility Vibes YouTube channel, validated against Campasano's 2018 SSRN paper "Term Structure Forecasts of Volatility." When front-month implied volatility is materially higher than the forward-implied vol between front and back month (FF ≥ 0.20), VV's thesis is that long-calendar spreads (sell front, buy back) capture systematic mispricing as the front leg's elevated IV decays faster than the back. We built an independent backtest of this on Polygon Options Advanced data covering 2022-01-03 → 2026-04-30 (~1,129 trading days). After 4+ phases of research (sparsity findings, single-cell rejection, exit-pricing fix, earnings disambiguation, multi-window stress tests, position-cap and vol-targeting experiments, universe expansion), the canonical configuration is a **2-cell ATM call calendar (30-90 + 60-90 DTE) on a 23-ticker multi-asset universe with hardcoded earnings filter active**. The strategy delivers a **+32.78% standalone CAGR** with **26.68% MaxDD** and **0.77 Sharpe** over the 4.3-year backtest, with **−0.107 daily-returns correlation to Steven's existing TQQQ Vol-Target system** — making it a genuine portfolio diversifier, not just expensive equity-vol exposure in a different costume.

## The headline result

### Standalone FF Tier 1

| Metric | Value |
|---|---:|
| MTM CAGR | **+32.78%** |
| MaxDD% (PCT-max) | **26.68%** (Nov 2023 → Feb 2024 episode, 88 days, recovered) |
| Annualized vol | 53.35% |
| Sharpe | 0.77 |
| Calmar | 1.23 |
| Closed trades | 643 |
| Still open at end | 24 |
| End equity | $1,362,520 (on $400K base) |

The 26.68% MaxDD is **above the README's ≤25% allocation criterion by 1.68pp**. As a standalone allocation, FF Tier 1 narrowly fails 2 of Steven's 5 stated criteria (worst-cell Sharpe and MaxDD). But standalone-only is the wrong test for THIS strategy — the right framing is the diversified mix, where the negative correlation does heavy lifting.

### Allocation answer vs Steven's TQQQ Vol-Target (BRACKETED)

Daily-returns correlation between FF Tier 1 and TQQQ-VT: **−0.107** (canonical) / **−0.115** (without IWM Jul 2024 outlier). Beta: −0.200 / −0.215. Their drawdowns happen at different times — diversification benefit is structural, not driven by any single trade.

**Optimistic case** (canonical, includes IWM Jul 2024 outlier worth +$304,868):

| Mix (TQQQ-VT/FF) | CAGR | MaxDD% | Sharpe | Calmar |
|---|---:|---:|---:|---:|
| 100/0 (Steven's current) | +24.46% | 31.43% | 0.90 | 0.78 |
| **70/30 — max-Sharpe** | **+32.31%** | **21.13%** | **1.26** | 1.53 |
| **50/50 — max-Calmar** | **+35.08%** | **16.40%** | 1.17 | **2.14** |
| 0/100 (pure FF) | +32.78% | 26.68% | 0.79 | 1.23 |

**Realistic case** (without IWM Jul 2024 — sensitivity per Path 1 analysis):

| Mix | CAGR | MaxDD% | Sharpe |
|---|---:|---:|---:|
| 100/0 (pure TQQQ-VT) | +24.46% | 31.43% | 0.90 |
| **70/30 — max-Sharpe (unchanged mix)** | **+30.19%** | **21.13%** | **1.20** |
| 0/100 (pure FF) | +25.22% | 31.95% | 0.69 |

**Forward-looking case**: TBD pending ORATS extended-history backtest.

**Key finding from Path 1 sensitivity**: max-Sharpe mix stays at 70/30 in BOTH optimistic and realistic cases — the strategy is structurally diversifying, the IWM trade was bonus not foundation. CAGR uplift vs pure TQQQ-VT shrinks from +7.85pp (optimistic) to +5.73pp (realistic); Sharpe uplift from +0.36 to +0.30. Both still meaningfully improve the portfolio over pure TQQQ-VT.

**Why the brackets**: 2024 attribution analysis revealed top 5 trades = 85.4% of 2024 P&L; the IWM Jul 2024 trade alone = 22.4% of the entire 4.3-year strategy P&L. The same near-zero-debit Kelly-overscale pattern produced both this winner AND the KRE Apr 2026 catastrophe (−$258K). Symmetric upside/downside; structural property of Kelly sizing on near-zero-debit calendars. Forward expected return depends critically on whether this pattern produces outliers consistently across regimes (ORATS extended history will tell us).

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

Steven's recommended phased approach to live capital — **NOT** immediate 30% deployment based on backtest alone.

**Phase A — Live + paper validation (months 1-6).** Allocate **5-10% of liquid NW** to live FF Tier 1 (small-stake, real fills) and run **25% of liquid NW as a paper-trade** of FF Tier 1 alongside (no capital at risk; just track live-execution behavior). Compare live + paper P&L to backtest expectations weekly. Watch fallback-warning frequency, fill quality vs slippage assumption, earnings-blocking accuracy on hardcoded calendar. If 6-month live + paper match backtest within ±5pp annualized, proceed to Phase B.

**Phase B — Scale to max-Sharpe allocation (months 7-12).** If Phase A clears, scale to the canonical **30% FF / 70% TQQQ-VT** max-Sharpe mix. Implement daily-rebalanced fixed-weight overlay (or quarterly rebalance if daily friction is too high — re-test backtest at quarterly to confirm degradation is small). Continue live monitoring; track Sharpe + MaxDD vs backtest expectations.

**Phase C — Re-evaluate (month 12+).** 12 months of live data is enough to start updating priors meaningfully. If live Sharpe ≥ backtest Sharpe − 0.20 AND MaxDD ≤ backtest MaxDD + 5pp, strategy is performing in expectation — consider 50/50 max-Calmar mix. If live drifts materially worse, reduce allocation but don't eliminate; the −0.107 correlation makes even reduced FF a net portfolio improver.

## Open follow-ups queued

Productive next steps if the strategy is deployed and Steven wants to refine. None block the allocation decision.

1. **Extend backtest to May 2021** — Polygon's 5-year cap allows ~7 more months of pre-2022 data. Adds the 2021 low-vol regime. ~1 hour compute.
2. **2024 per-quarter / per-ticker attribution** — was the +87% CAGR broad-based or concentrated? ~30 min analysis on existing trade log.
3. **OQuants ex-earnings IV implementation (Option A)** — would unlock single-name signal (META/AMD/GOOGL/JPM/COIN/MSTR currently produce zero opens). 6-10 hour build per OQuants methodology. Only worth doing if you specifically want single-name exposure.
4. **Live execution diary** — once Phase A starts, track every live trade vs backtest's predicted entry, fill price, exit pricing. Surfaces real-vs-backtest gaps that don't show up in pre-trade analysis.
5. **Verbatim VV transcript quotes** — Steven to paste into Spec Sources section of `CLAUDE_CODE_HANDOFF.md` when convenient. Doesn't block anything; makes the spec record auditable.

Items explicitly **NOT** to pursue without specific new evidence: Tier 2 (all 6 cells), Tier 3 (signal-quality weighted sizing — overfit risk on 4.3-year sample), more universe expansion (the 5-of-26 pre-flight pass rate showed marginal new tickers don't produce signal at this DTE pair).

## Where to find things

- **`CLAUDE_CODE_HANDOFF.md`** — full project state, all decisions, all caveats. The authoritative source if this RESEARCH_SUMMARY is ambiguous.
- **`scripts/`** — reproducible analysis: `phase4_t1_run.py` (canonical Tier 1), `tqqq_vt_allocation.py` (allocation sweep), `regression_phase3.py` (validates pipeline against Phase 3), pre-flight + sweep scripts for cap/vol-target negative results.
- **`src/`** — production code. `discover_candidates.py` + `simulate_portfolio.py` are the canonical pipeline (replaces older monolithic `backtest.py` flow). `earnings_data.py` holds the hardcoded earnings calendar. `run_config.py` is the hashable config dataclass.
- **`tests/`** — 174 unit tests. `pytest tests/` should pass cleanly.
- **`output/`** — per-config simulation artifacts (`sim_<config_hash>/` directories) + Phase reports (`PHASE_*.md`) + equity-curve PNGs. **Gitignored** (local artifacts; reproducible from `scripts/`).
- **`data_cache/`** — diskcache layered into `reference/`, `equity/`, `options/` (~924MB total, 244K Polygon API responses cached). Run `python -m src.data_layer cache_report` for breakdown.
- **GitHub canonical**: https://github.com/stegitforme/forward-factor-backtester (commit `676b387` is the research-arc-complete pin).

## TL;DR for someone reading in 6 months

> FF is a real, negatively-correlated diversifier vs Steven's TQQQ-VT. Standalone +32.78% CAGR with 26.68% DD on 4.3-year backtest; mixed 70/30 with TQQQ-VT delivers +32.31% CAGR with 21.13% DD and Sharpe 1.26 (optimistic case). BUT — the IWM Jul 2024 single trade is 22.4% of total P&L. Without it, FF standalone is +25.22% CAGR / 31.95% DD; the 70/30 mix still wins (Sharpe 1.20, CAGR +30.19%) — strategy is structurally diversifying, but the near-zero-debit Kelly-overscale pattern that produced this winner is the SAME pattern that caused the KRE Apr 2026 −$258K catastrophe. Forward expected returns are bracketed pending ORATS extended-history validation across 2008/2018/2020 regimes. Initial deployment is **5-10% live + 15% paper as Phase A**, full sizing decision deferred until ORATS lands. The structural lever that delivered the result was multi-asset universe expansion (not risk caps or vol-targeting, both tested and rejected). Don't run more cell expansion or signal-quality sizing — they'd overfit a 4.3-year sample.
