# Phase 5 — Methodology Diagnostics: 30-60 Cell + extVol

_Generated 2026-05-05T07:24:04.419777_

## Purpose

Two methodology variants VV uses but we didn't test, run quickly to explain the gap between our 2022-2026 ORATS result (+3.09% CAGR) and VV's published +27% claim. Combined with the IWM Jul 18 2024 raw-data diagnostic, this should explain most of the gap.

**Window**: 2022-01-03 → 2026-04-30  |  **Universe**: 23 tickers (Tier 1)  |  **Threshold**: FF ≥ 0.20

## Per-cell × per-config signal stats

| Config | Cell | Total | Resolved | FF valid | **FF≥0.20** | Earn-blocked | Median FF | P90 FF |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2cells_smvVol_baseline | 30_90_atm | 24,955 | 9,986 | 9,980 | **857** | 6,479 | -0.0148 | +0.1799 |
| 2cells_smvVol_baseline | 60_90_atm | 24,955 | 6,597 | 6,582 | **727** | 6,479 | -0.0060 | +0.2137 |
| 3cells_smvVol(earn_filter=ON) | 30_60_atm | 24,955 | 10,223 | 10,212 | **977** | 4,960 | -0.0009 | +0.1943 |
| 3cells_smvVol(earn_filter=ON) | 30_90_atm | 24,955 | 9,986 | 9,980 | **857** | 6,479 | -0.0148 | +0.1799 |
| 3cells_smvVol(earn_filter=ON) | 60_90_atm | 24,955 | 6,597 | 6,582 | **727** | 6,479 | -0.0060 | +0.2137 |
| 2cells_extVol(earn_filter=OFF) | 30_90_atm | 24,955 | 9,986 | 9,981 | **1,281** | 0 | +0.0104 | +0.2295 |
| 2cells_extVol(earn_filter=OFF) | 60_90_atm | 24,955 | 6,597 | 6,582 | **366** | 0 | +0.0035 | +0.1437 |

## Q1: Does the 30-60 cell add signal?

FF ≥ 0.20 hits across the 3 cells:

| Cell | Hits | Share |
|---|---:|---:|
| 30_60_atm | 977 | 38% |
| 30_90_atm | 857 | 33% |
| 60_90_atm | 727 | 28% |
| **Total** | **2561** | **100%** |

**VV's published spec**: 30-60 fires 13× more trades/quarter than 60-90, 30-90 fires 36× more (densest cell).

**Our finding**: 30-60 produces 1.3× the FF≥0.20 hits of 60-90. Adds materially to total signal count.

## Q2: Does extVol (ex-earnings IV) change the signal?

Comparing extVol-based FF to smoothSmvVol-based FF on the same 49,910 (date, ticker, cell) rows where both compute valid FF:

| Statistic | Value |
|---|---:|
| Mean Δ (extVol - smvVol) | +0.0277 |
| Median Δ | +0.0244 |
| Std Δ | 0.1990 |
| P10 / P90 Δ | -0.1560 / +0.2089 |

**FF ≥ 0.20 cross-classification** (per row):

| | extVol ≥ 0.20 | extVol < 0.20 |
|---|---:|---:|
| **smvVol ≥ 0.20** | 496 | 1085 |
| **smvVol < 0.20** | 1151 | 13,825 |

**extVol picks up 1151 signals smvVol misses, while smvVol picks up only 1085 that extVol misses.** Net: extVol fires more often.

## Q3: On Polygon-fire dates, do ORATS IVs say the signal was real?

Polygon Tier 1 fired 667 (cell, ticker, date) signals. For each, we look up ORATS' FF on the same date:

| IV column | Median FF on Polygon-fire days | % crossing 0.20 |
|---|---:|---:|
| smoothSmvVol | +0.0462 | 20.1% |
| extVol | +0.0816 | 29.3% |

If both ORATS columns say FF was nowhere near 0.20 on Polygon-fire days, that's strong evidence those signals were Polygon-data-noise (BS-IV inverted off thin/stale close prices), not real backwardation.

## Combined diagnostic verdict

Three diagnostics together:

1. **IWM 2024-07-18 218C** (raw bid/ask): ATM call traded $8.94-$8.99 — Polygon's $0.03 close was a stale print, not a tradable price. The +$305K trade is fake.
2. **30-60 cell** (this report Q1): see table above.
3. **extVol** (this report Q2 + Q3): see table above.

## Files

- `output/phase5_orats_2022_2026_3cells_smvVol.parquet` — 3-cell smvVol discovery output
- `output/phase5_orats_2022_2026_extVol.parquet` — 2-cell extVol discovery output
- `output/phase5_orats_2022_2026_smvVol.parquet` — original 2-cell smvVol baseline