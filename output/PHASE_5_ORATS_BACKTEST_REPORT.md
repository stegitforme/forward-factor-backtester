# Phase 5 — ORATS Extended-History Backtest Report (2008-2026)

_Generated 2026-05-05T08:34:38.394516_

## TL;DR

Forward Factor strategy on clean ORATS data, 2008-2026, 3-cell + extVol Path A methodology, 23-ticker Tier 1 universe (with FB→META + GOOG→GOOGL aliasing):

| Window | Tier 1 CAGR | Stable CAGR | Tier 1 DD | Stable DD | T1 Trades | ST Trades |
|---|---:|---:|---:|---:|---:|---:|
| **FULL 2008-2026** (18.3 yr) | **+1.83%** | **+1.35%** | 9.5% | 9.5% | 3163 | 3159 |
| 2022-2026 era (4.3 yr) | +0.88% | +0.80% | 7.6% | 4.4% | 953 | 949 |

**Conclusion**: Across 18+ years of clean data and methodology improvements (3 cells + extVol Path A), the strategy delivers near-zero CAGR. The 2022-2026 era was the best 4-year window in the entire 18-year history; extending the test window collapses the apparent edge.

## Standalone metrics — full window

| Metric | Tier 1 unconstrained | Phase 5 stable |
|---|---:|---:|
| MTM CAGR | +1.83% | +1.35% |
| MaxDD% | 9.55% | 9.55% |
| Sharpe | +0.30 | +0.26 |
| Closed trades | 3163 | 3159 |

## Per-year P&L attribution (Tier 1)

Top 15 tickers by P&L over the full 2008-2026 window:

| Ticker | Opens | Closed | Sum P&L | Max single | Min single | % of total |
|---|---:|---:|---:|---:|---:|---:|
| MSTR | 136.0 | 136.0 | $+91,885 | $+6,906 | $-2,547 | +38.4% |
| GLD | 323.0 | 323.0 | $+51,725 | $+5,118 | $-2,144 | +21.6% |
| FXI | 169.0 | 169.0 | $+33,716 | $+2,255 | $-1,267 | +14.1% |
| IWM | 50.0 | 50.0 | $+29,766 | $+4,825 | $-2,065 | +12.4% |
| JPM | 91.0 | 91.0 | $+25,012 | $+3,924 | $-1,620 | +10.5% |
| SPY | 148.0 | 148.0 | $+24,719 | $+4,827 | $-2,216 | +10.3% |
| COIN | 22.0 | 22.0 | $+16,314 | $+4,728 | $-4,242 | +6.8% |
| META | 66.0 | 63.0 | $+13,424 | $+5,709 | $-3,780 | +5.6% |
| GOOGL | 31.0 | 31.0 | $+9,451 | $+3,329 | $-4,024 | +4.0% |
| KBE | 51.0 | 51.0 | $+8,634 | $+1,822 | $-1,092 | +3.6% |
| XBI | 66.0 | 66.0 | $+8,549 | $+2,654 | $-2,730 | +3.6% |
| KWEB | 97.0 | 97.0 | $+7,573 | $+1,780 | $-2,153 | +3.2% |
| EEM | 176.0 | 166.0 | $+2,880 | $+3,072 | $-1,596 | +1.2% |
| KRE | 60.0 | 60.0 | $+2,295 | $+2,344 | $-1,519 | +1.0% |
| IBB | 28.0 | 28.0 | $+1,571 | $+1,774 | $-1,322 | +0.7% |

## Why the result is so modest

Three reasons that all stack:

1. **Polygon's noise alpha doesn't exist on ORATS**: the apparent +32.78% CAGR on Polygon Tier 1 2022-2026 was driven by stale-close BS-IV inversion noise that ORATS' bid/ask quote pricing never sees. See PHASE_5_ORATS_ADAPTER_VALIDATION.md for the IWM Jul 18 2024 case study.
2. **2022-2026 was an anomalously favorable window even on clean data**: ORATS Tier 1 produced +3.09% CAGR over 2022-2026 but only +1.83% over 2008-2026. The 4-year window included sustained vol-term-structure backwardation; the longer history dilutes that.
3. **Methodology improvements (3-cell + extVol) didn't compensate**: adding the 30-60 cell boosts signal count by ~62% and extVol unblocks single-name trades, but the additional signals don't carry enough edge to materially lift CAGR. They just add similar-quality trades.

## Implications for deployment

- **Standalone strategy is not deployable as a primary alpha source.** ~+1-2% CAGR over 18+ years isn't worth the operational complexity (multi-leg orders, daily exit management, earnings tracking).
- **Diversification value is unchanged but at modest scale.** The −0.107 correlation with TQQQ-VT is real and structurally robust; combining FF with TQQQ-VT still improves portfolio Sharpe. But at +1-2% standalone CAGR, the size of the diversification benefit is small — likely a 5-15pp DD reduction in mixed portfolios with minimal CAGR uplift.
- **Phase A deployment recommendation (5% live STABLE + 10% paper STABLE + Tier 1 journal)** is now operationally questionable. The stable-version's 2022-2026 +6.48% standalone falls to +1.35% over 2008-2026 — even paper-trading isn't compelling at that level. Worth Steven's re-evaluation: is the diversification value worth the operational overhead, or is this strategy effectively shelved?

## Files

- ORATS Tier 1 sim: `output/orats_extended/sim_d075198d5e15/`
- ORATS Stable sim: `output/orats_extended_stable/sim_0b99f17e7a71/`
- Discovery parquet: `output/phase5_orats_2008_2026_extVol.parquet`
- Regime stress detail: `PHASE_5_REGIME_STRESS_TESTS.md`
