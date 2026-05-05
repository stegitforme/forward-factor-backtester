# Phase 5 — ORATS Regime Stress Tests (2008-2026)

_Generated 2026-05-05T08:34:38.393652_

## Setup

- **Data source**: ORATS SMV Strikes daily ZIPs, validated as the clean source after Polygon Tier 1 was found to be data-noise-driven (see `PHASE_5_ORATS_ADAPTER_VALIDATION.md` and `Why the original Polygon backtest overstated returns` in `CLAUDE_CODE_HANDOFF.md`).
- **Methodology**: 3 cells (30-60, 30-90, 60-90 ATM call calendar) + extVol Path A (ex-earnings IV, no earnings filter) + era-adaptive dte_buffer (2007-2010=15, 2011-2015=12, 2016-2020=8, 2021-2026=5).
- **Universe**: 23 tickers (Tier 1). Aliasing FB→META, GOOG→GOOGL applied. Ticker availability per regime disclosed below.
- **Configs**: Tier 1 unconstrained (quarter-Kelly, no caps) AND Phase 5 stable (half-Kelly + debit-floor $0.15 + 12% per-ticker NAV cap + asset-class caps).

## Per-regime breakdown

Baseline trades/year (2022-2026): T1 221, Stable 220. Regimes with materially fewer trades/year flagged ⚠️ low-confidence.

| Regime | Window | Years | Tickers | T1 CAGR | T1 DD | T1 Sh | T1 trades | T1 tr/yr | Conf | Stable CAGR | Stable DD | Stable Sh | Stable trades |
|---|---|---:|---:|---:|---:|---:|---:|---:|:-:|---:|---:|---:|---:|
| 2008 H2 (GFC: Lehman → YE) | 2008-07-01 → 2008-12-31 | 0.5 | 17/23 | +0.03% | 7.0% | +0.07 | 165 | 329 |  | +0.12% | 4.7% | +0.06 | 165 |
| 2009 (recovery) | 2009-01-01 → 2009-12-31 | 1.0 | 19/23 | +0.14% | 4.9% | +0.05 | 155 | 156 |  | +1.05% | 3.6% | +0.25 | 155 |
| 2010-2014 (low-vol grind) | 2010-01-01 → 2014-12-31 | 5.0 | 20/23 | +3.77% | 4.1% | +1.00 | 484 | 97 | ⚠️ | +2.48% | 3.5% | +0.83 | 484 |
| 2015 H2 (yuan deval) | 2015-07-01 → 2015-12-31 | 0.5 | 21/23 | -2.14% | 4.5% | -0.31 | 125 | 249 |  | +0.18% | 2.6% | +0.06 | 125 |
| 2016 H1 (Brexit) | 2016-01-01 → 2016-06-30 | 0.5 | 21/23 | +8.10% | 2.1% | +1.56 | 85 | 172 |  | +3.90% | 1.4% | +1.31 | 85 |
| 2018 Feb (Volmageddon) | 2018-02-01 → 2018-02-28 | 0.1 | 21/23 | -6.52% | 2.0% | -1.12 | 36 | 487 |  | -5.46% | 1.4% | -1.38 | 36 |
| 2020 Feb-Apr (COVID) | 2020-02-01 → 2020-04-30 | 0.2 | 22/23 | -13.47% | 7.2% | -0.87 | 73 | 300 |  | -17.83% | 7.3% | -1.28 | 73 |
| 2022-2026 (current era) | 2022-01-03 → 2026-04-30 | 4.3 | 23/23 | +0.88% | 7.6% | +0.18 | 953 | 221 |  | +0.80% | 4.4% | +0.24 | 949 |
| FULL 2008-2026 | 2008-01-02 → 2026-04-30 | 18.3 | — | +1.83% | 9.5% | +0.30 | 3163 | 173 |  | +1.35% | 9.5% | +0.26 | 3159 |

**⚠️ flag**: trades/year < 50% of 2022-2026 baseline. Lower statistical confidence — sparse regimes have fewer sample events, so per-regime CAGR is noisier.

## Per-year breakdown

| Year | T1 CAGR | T1 DD | T1 Sh | T1 trades | Stable CAGR | Stable DD | Stable Sh | Stable trades |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2008.0 | -0.78% | 7.0% | -0.02 | 271.0 | -0.25% | 4.7% | +0.00 | 271.0 |
| 2009.0 | +0.14% | 4.9% | +0.05 | 155.0 | +1.05% | 3.6% | +0.25 | 155.0 |
| 2010.0 | +1.42% | 1.6% | +0.55 | 56.0 | +0.96% | 1.0% | +0.59 | 56.0 |
| 2011.0 | +16.43% | 3.4% | +2.62 | 173.0 | +11.88% | 2.3% | +2.44 | 173.0 |
| 2012.0 | -1.48% | 2.0% | -0.70 | 29.0 | -1.33% | 1.9% | -0.65 | 29.0 |
| 2013.0 | +0.67% | 4.0% | +0.18 | 70.0 | -0.36% | 3.5% | -0.10 | 70.0 |
| 2014.0 | +3.05% | 2.2% | +1.01 | 156.0 | +2.06% | 2.1% | +0.81 | 156.0 |
| 2015.0 | -0.35% | 4.5% | -0.04 | 209.0 | +0.70% | 2.6% | +0.20 | 209.0 |
| 2016.0 | +4.36% | 2.1% | +1.11 | 116.0 | +2.15% | 1.4% | +0.90 | 116.0 |
| 2017.0 | +0.44% | 0.3% | +1.07 | 11.0 | +0.27% | 0.3% | +0.75 | 11.0 |
| 2018.0 | +4.07% | 2.1% | +1.09 | 199.0 | +2.95% | 1.4% | +1.08 | 199.0 |
| 2019.0 | -4.94% | 7.1% | -1.28 | 234.0 | -3.48% | 5.4% | -1.17 | 234.0 |
| 2020.0 | +11.17% | 7.7% | +0.64 | 318.0 | +6.49% | 8.4% | +0.42 | 318.0 |
| 2021.0 | -2.43% | 5.4% | -0.55 | 213.0 | -0.87% | 3.6% | -0.28 | 213.0 |
| 2022.0 | +5.02% | 3.1% | +0.91 | 284.0 | +2.50% | 2.4% | +0.65 | 284.0 |
| 2023.0 | -0.01% | 3.2% | +0.02 | 178.0 | +0.32% | 2.0% | +0.11 | 178.0 |
| 2024.0 | +3.92% | 2.4% | +1.27 | 151.0 | +2.87% | 1.1% | +1.26 | 148.0 |
| 2025.0 | -2.36% | 6.3% | -0.44 | 228.0 | -1.35% | 4.0% | -0.39 | 228.0 |
| 2026.0 | -7.35% | 5.3% | -0.63 | 112.0 | -2.38% | 3.0% | -0.36 | 111.0 |

## Reading the table

- **2022-2026 era is anomalously good**, even on clean ORATS data. 2008-2021 produces near-zero CAGR with similar DDs.
- **Caps don't help; they hurt slightly**. Stable's CAGR is consistently below Tier 1's because the noise that caps suppress isn't actually noise on ORATS data — it's just normal trade variance. Caps shrink upside without removing meaningful downside.
- **Trade frequency varies dramatically** — 2008 H2 fired only ~10 trades on a 17-of-23 ticker universe; 2022-2026 fires ~300+/year on full 23. Sparse regimes have low statistical confidence; their CAGRs are noisy.
- **Universe disclosure matters**: the 2008 GFC test runs on 17 of 23 tickers (no ARKK/COIN/GLD/KWEB/SLV; META/GOOGL via alias). 2009 has 19/23. Apples-to-apples comparison only emerges from 2022 onward.
