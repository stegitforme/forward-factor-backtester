# Phase 5 — ORATS Adapter Validation (2022-2026)

_Generated 2026-05-04T23:14:24.554692_

## Purpose

Validate the ORATS adapter end-to-end by running an apples-to-apples Tier 1 backtest on ORATS data over the same 2022-2026 window where we have a canonical Polygon-based result (`output/sim_4119dc073393/`). If results match within Steven's tolerance (±2pp per-year CAGR, signal alignment > 90%), the adapter is trustworthy for extended-history work (2008-2021).

## Configuration

- **RunConfig hash**: `fb5fb0d6b38e`
- **Polygon comparison hash**: `4119dc073393`
- **Cells**: ['30_90_atm', '60_90_atm']
- **FF threshold**: 0.2
- **Universe size**: 23 tickers
- **DTE buffer**: ±5 days
- **Earnings filter**: ON
- **IV column**: smoothSmvVol (VV-faithful)
- **Window**: 2022-01-03 → 2026-04-30

## Headline metrics — overall (full window)

| Metric | Polygon | ORATS | Δ |
|---|---:|---:|---:|
| CAGR | +32.78% | +3.09% | -29.69pp |
| MaxDD% | 26.68% | 6.26% | -20.42pp |
| Sharpe | 0.77 | 0.63 | -0.14 |
| End equity | $1,362,520 | $456,214 | $-906,306 |
| # Trades | 667 | 491 | -176 |

## Per-year breakdown

| Year | Poly CAGR | ORATS CAGR | Δ CAGR | Poly DD | ORATS DD | Poly Sh | ORATS Sh |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 ⚠️ | +44.70% | +1.55% | -43.15pp | 18.07% | 4.84% | 1.00 | 0.31 |
| 2023 ⚠️ | +8.15% | +1.53% | -6.62pp | 17.58% | 3.03% | 0.39 | 0.70 |
| 2024 ⚠️ | +77.10% | +4.61% | -72.49pp | 23.24% | 1.41% | 1.06 | 1.15 |
| 2025 ⚠️ | +19.78% | -0.79% | -20.57pp | 15.11% | 6.04% | 0.63 | -0.11 |
| 2026 ⚠️ | +10.02% | +21.71% | +11.69pp | 10.91% | 2.05% | 0.43 | 2.21 |

⚠️ flag: per-year CAGR delta > 2pp (Steven's tolerance threshold).

## Per-trade signal alignment

- **Common (fired in both)**: 114
- **Polygon-only (fired in Polygon, not ORATS)**: 553
- **ORATS-only (fired in ORATS, not Polygon)**: 377
- **Overlap (Jaccard)**: 10.9%

### Per-cell signal counts

| Cell | Polygon | ORATS | Common | Poly-only | ORATS-only |
|---|---:|---:|---:|---:|---:|
| 30_90_atm | 414 | 253 | 90 | 324 | 163 |
| 60_90_atm | 253 | 238 | 24 | 229 | 214 |

### First 20 Polygon-only signals (fired in Polygon, NOT in ORATS)

These are signals that ORATS data missed. Most likely causes: (1) ORATS strike-rounding differs from Polygon BS-inverted IV, (2) FF computation rounding, (3) earnings-filter borderline cases. Counts > 20 may indicate a systematic issue.

| Cell | Ticker | Entry Date |
|---|---|---|
| 30_90_atm | ARKK | 2022-01-14 |
| 30_90_atm | ARKK | 2022-03-17 |
| 30_90_atm | ARKK | 2022-04-18 |
| 30_90_atm | ARKK | 2022-04-20 |
| 30_90_atm | ARKK | 2022-06-22 |
| 30_90_atm | ARKK | 2022-07-26 |
| 30_90_atm | ARKK | 2023-02-14 |
| 30_90_atm | ARKK | 2023-02-17 |
| 30_90_atm | ARKK | 2023-03-13 |
| 30_90_atm | ARKK | 2023-06-20 |
| 30_90_atm | ARKK | 2024-02-14 |
| 30_90_atm | ARKK | 2025-03-17 |
| 30_90_atm | ARKK | 2025-03-19 |
| 30_90_atm | ARKK | 2025-03-25 |
| 30_90_atm | ARKK | 2025-04-16 |
| 30_90_atm | ARKK | 2025-08-19 |
| 30_90_atm | COIN | 2022-11-17 |
| 30_90_atm | COIN | 2022-11-18 |
| 30_90_atm | EEM | 2022-06-23 |
| 30_90_atm | EEM | 2022-10-21 |

### First 20 ORATS-only signals (fired in ORATS, NOT in Polygon)

ORATS picked up signals Polygon missed. Likely causes: ORATS' smoothSmvVol differs slightly from Polygon BS-inverted IV at the threshold boundary; ORATS tickers covered that Polygon couldn't resolve.

| Cell | Ticker | Entry Date |
|---|---|---|
| 30_90_atm | ARKK | 2022-01-10 |
| 30_90_atm | ARKK | 2022-01-19 |
| 30_90_atm | ARKK | 2022-02-22 |
| 30_90_atm | ARKK | 2022-02-23 |
| 30_90_atm | ARKK | 2025-10-13 |
| 30_90_atm | ARKK | 2025-10-14 |
| 30_90_atm | EEM | 2022-03-18 |
| 30_90_atm | EEM | 2022-04-21 |
| 30_90_atm | EEM | 2022-10-17 |
| 30_90_atm | EEM | 2022-10-25 |
| 30_90_atm | EEM | 2022-11-23 |
| 30_90_atm | EEM | 2023-11-21 |
| 30_90_atm | EEM | 2024-01-02 |
| 30_90_atm | EEM | 2024-09-30 |
| 30_90_atm | EEM | 2024-11-20 |
| 30_90_atm | EEM | 2024-11-21 |
| 30_90_atm | EEM | 2025-04-04 |
| 30_90_atm | EEM | 2025-06-04 |
| 30_90_atm | EEM | 2025-11-17 |
| 30_90_atm | EEM | 2026-03-03 |

### P&L delta on common trades

| Statistic | Value |
|---|---:|
| Mean Δ (orats - poly) | $-3,260 |
| Median Δ | $-101 |
| Median |Δ| | $536 |
| Max |Δ| | $303,089 |

### Top 10 largest |P&L deltas|

| Cell | Ticker | Entry | Polygon P&L | ORATS P&L | Δ |
|---|---|---|---:|---:|---:|
| 60_90_atm | IWM | 2024-07-18 | $+304,868 | $+1,779 | $-303,089 |
| 60_90_atm | EEM | 2026-01-20 | $+28,558 | $+1,300 | $-27,258 |
| 30_90_atm | USO | 2026-01-14 | $+15,241 | $+852 | $-14,389 |
| 60_90_atm | SMH | 2025-09-25 | $+12,667 | $+3,453 | $-9,215 |
| 60_90_atm | TLT | 2024-09-19 | $-7,463 | $-42 | $+7,422 |
| 30_90_atm | HYG | 2023-02-23 | $+7,102 | $+658 | $-6,444 |
| 60_90_atm | SLV | 2026-01-15 | $-7,315 | $-1,365 | $+5,950 |
| 60_90_atm | SLV | 2026-01-16 | $-6,976 | $-1,244 | $+5,732 |
| 60_90_atm | USO | 2025-06-20 | $-6,346 | $-1,111 | $+5,236 |
| 30_90_atm | HYG | 2023-11-14 | $-4,691 | $+274 | $+4,965 |

## Verdict

- **Overall CAGR delta**: -29.69pp (❌ exceeds ±2pp)
- **Per-year CAGR within ±2pp**: ❌ years exceeding: [2022, 2023, 2024, 2025, 2026]
- **Signal overlap**: 10.9% (❌ <90%)

**ADAPTER NEEDS DESIGN REVIEW.** Investigate divergences before extending history.

## Files

- ORATS candidate parquet: `output/phase5_orats_2022_2026_smvVol.parquet`
- ORATS sim output: `output/orats_validation/sim_fb5fb0d6b38e/`
- Polygon canonical: `output/sim_4119dc073393/`
