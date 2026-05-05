# Phase 5 — ORATS Allocation Analysis vs TQQQ-VT

_Generated 2026-05-05T08:36:10.233042_

## Setup

- Window: 2022-01-03 → 2026-04-30 (1085 days)
- FF data source: ORATS extended-history backtest (3-cell + extVol Path A + era buffer)
- Sliced to 2022-2026 because TQQQ-VT data only spans that period
- Tier 1 hash: `d075198d5e15` — full 2008-2026 CAGR was +1.83%
- Stable hash: `0b99f17e7a71` — full 2008-2026 CAGR was +1.35%

## Correlations

| Strategy | Correlation vs TQQQ-VT |
|---|---:|
| FF Tier 1 (ORATS) | **+0.040** |
| FF Stable (ORATS) | **+0.030** |

Negative correlations confirm structural diversification, but at modest standalone CAGR the *magnitude* of diversification benefit is small.

## Standalone strategy metrics (overlapping window)

| Metric | FF Tier 1 ORATS | FF Stable ORATS | TQQQ-VT |
|---|---:|---:|---:|
| CAGR | +0.88% | +0.80% | +24.46% |
| MaxDD% | 7.59% | 4.36% | 31.43% |
| Ann Vol | 5.51% | 3.52% | 29.07% |
| Sharpe | 0.19 | 0.25 | 0.90 |
| Calmar | 0.12 | 0.18 | 0.78 |

## Allocation sweep — Tier 1 (no caps) vs TQQQ-VT

| Mix (TQ/FF) | CAGR | MaxDD% | Sharpe | Calmar | End $ |
|---|---:|---:|---:|---:|---:|
| 100/  0 | +24.46% | 31.43% | 0.90 | 0.78 | $25,752 |
|  90/ 10 | +22.35% | 28.66% | 0.91 | 0.78 | $23,917 |
|  85/ 15 | +21.27% | 27.24% | 0.91 | 0.78 | $23,017 |
|  80/ 20 | +20.17% | 25.80% | 0.91 | 0.78 | $22,130 |
|  75/ 25 | +19.06% | 24.33% | 0.91 | 0.78 | $21,257 |
|  70/ 30 | +17.93% | 22.85% | 0.91 | 0.78 | $20,399 |
|  60/ 40 | +15.63% | 19.82% | 0.91 | 0.79 | $18,733 |
|  50/ 50 ← max Sharpe | +13.27% | 16.70% | 0.92 | 0.79 | $17,139 |
|   0/100 | +0.88% | 7.59% | 0.19 | 0.12 | $10,388 |

## Allocation sweep — Stable (caps + half-Kelly) vs TQQQ-VT

| Mix (TQ/FF) | CAGR | MaxDD% | Sharpe | Calmar | End $ |
|---|---:|---:|---:|---:|---:|
| 100/  0 | +24.46% | 31.43% | 0.90 | 0.78 | $25,752 |
|  90/ 10 | +22.33% | 28.66% | 0.91 | 0.78 | $23,904 |
|  85/ 15 | +21.24% | 27.25% | 0.91 | 0.78 | $22,998 |
|  80/ 20 | +20.14% | 25.81% | 0.91 | 0.78 | $22,106 |
|  75/ 25 | +19.02% | 24.36% | 0.91 | 0.78 | $21,228 |
|  70/ 30 | +17.88% | 22.88% | 0.91 | 0.78 | $20,367 |
|  60/ 40 | +15.57% | 19.86% | 0.92 | 0.78 | $18,696 |
|  50/ 50 ← max Sharpe | +13.21% | 16.75% | 0.92 | 0.79 | $17,098 |
|   0/100 | +0.80% | 4.36% | 0.25 | 0.18 | $10,351 |

## Δ vs pure TQQQ-VT for each max-Sharpe mix

| Metric | Pure TQQQ-VT | T1 Max-Sh ( 50/ 50) | Δ T1 | ST Max-Sh ( 50/ 50) | Δ ST |
|---|---:|---:|---:|---:|---:|
| CAGR | +24.46% | +13.27% | -11.19pp | +13.21% | -11.25pp |
| MaxDD% | 31.43% | 16.70% | -14.73pp | 16.75% | -14.68pp |
| Sharpe | 0.90 | 0.92 | +0.01 | 0.92 | +0.02 |

## Verdict

- **Max-Sharpe Tier 1 mix**:  50/ 50 (50% FF) | Sharpe uplift +0.01 vs pure TQQQ-VT
- **Max-Sharpe Stable mix**:  50/ 50 (50% FF) | Sharpe uplift +0.02 vs pure TQQQ-VT

Compared to the prior (data-noise-driven) Polygon-based allocation analysis where the max-Sharpe mix was 30% FF with Sharpe uplift +0.36, the clean ORATS data shows materially smaller diversification benefit. The negative correlation is real, but at +1-3% standalone CAGR over the relevant window, the size of the Sharpe uplift shrinks substantially.

Combined with the regime stress finding that FF LOSES money in major vol events (Feb 2018 Volmageddon −6.5%, Feb-Apr 2020 COVID −13.5%), the deployment case for this strategy is now significantly weaker than any prior analysis suggested.

## Files

- FF Tier 1 daily MTM: `output/orats_extended/sim_d075198d5e15/daily_mtm_equity.csv`
- FF Stable daily MTM: `output/orats_extended_stable/sim_0b99f17e7a71/daily_mtm_equity.csv`
- TQQQ-VT daily equity: `output/tqqq_vt_daily_equity.csv`