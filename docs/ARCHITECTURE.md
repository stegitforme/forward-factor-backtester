# Architecture & Design Decisions

## Goal

Build a backtester that gives us an honest, capital-allocation-grade answer
to one question: **does Forward Factor produce real, uncorrelated alpha
worth allocating to alongside an existing TQQQ/SGOV vol-targeting strategy?**

## Why Modular Files Instead of One Notebook

Three reasons, each of which would force this on its own at any meaningful AUM:

1. **Reproducibility under audit.** When the strategy has a bad month and
   we need to show "exactly what code ran in May 2026," we need git-versioned
   modular files with commit hashes. A 2,000-line notebook full of mutable
   cell state is a compliance disaster.

2. **Component testability.** Calendar spread strategies fail in subtle ways
   — bad fills, mis-stripped earnings, IV interpolation bugs. We need to
   unit-test each component against known values, which requires modular
   files with public interfaces.

3. **Live/paper/prod parity.** When the backtest works, we want to run the
   same code on live data without rewriting anything. Modular code lets us
   swap `data_layer.py` from "Polygon historical" to "Polygon live" with
   zero changes to the trade simulator.

The marginal cost is ~15% extra coding time. The downside protection is
catastrophic: the moment real money is at stake, a notebook becomes a
liability. We do this right from the start.

## Why All 6 Cells Plus Ensemble

The author's video reports best-case results from the **60/90 DTE double
calendar at quarter Kelly** (27% CAGR, 2.42 Sharpe). A hedge fund would
never accept that single number as proof of alpha. We test all 6 cells
because:

1. **Parameter sensitivity is the strategy.** If FF works at 30/60 ATM but
   fails at 60/90 double, that's not "different parameter choices" — it's
   a fragility signal. A genuine signal should show edge across the whole
   grid with smooth gradients.

2. **The ensemble has a free Sharpe boost.** Real vol funds run
   equal-weighted ensembles across the parameter surface, not the
   historical best cell. Cross-cell noise diversifies away while the
   signal compounds. Typical improvement: +0.3 to +0.5 Sharpe vs any
   single cell.

3. **The marginal cost is essentially zero.** Same options data, same
   fills, same earnings filter. Calculating all 6 cells is a couple
   extra lines of logic per day per name.

## Data Source: Polygon Options Advanced

We chose Polygon at the **Advanced tier ($199/m for one month)** over:

- **oQuants ($99/m)**: His own platform. Conflict of interest — we'd be
  asking him to validate his own strategy via his own infrastructure.
  Doesn't give us code we own. $99/m forever vs $58/m forever (Stocks +
  Options Starter post-test).
- **Polygon Developer ($79/m)**: 4 years of history. Gets us most of 2022
  bear market, but starts mid-cycle. We picked Advanced because it covers
  the full 2022 drawdown plus 2024 vol spike with margin to spare.
- **OptionMetrics IvyDB**: The institutional gold standard, ~$10K+/yr.
  Overkill for a personal allocation decision.

We will **downgrade back to Starter ($29/m) immediately after the
backtest is complete** to maintain ongoing live signal access without
the high-tier subscription cost.

## Test Window: 2022-05-02 to today

Why this specific window:

- **Captures most of the 2022 bear market** (peak Jan 2022, troughs in
  June/Sept/Oct — all within window). This is the single most important
  stress test for a vol arbitrage strategy.
- **Out-of-sample for the author**. His backtest runs through 2025;
  recent months are out-of-sample for him.
- **Reproducible at Developer tier** in the future if we want to re-run
  cheaply.

We do not attempt to reproduce his 19-year backtest because:
1. We'd need IvyDB for that, which is $10K+/yr.
2. The recent regime-rich period is what we actually need to make a
   capital allocation decision.
3. Re-proving 2007-2021 doesn't change the answer to "should I allocate
   today."

## Capital Allocation Decision Criteria

The strategy clears all of these on out-of-sample data, OR it doesn't
get capital:

| Test                        | Threshold                                  | Why                                                                |
|-----------------------------|--------------------------------------------|--------------------------------------------------------------------|
| Ensemble CAGR (net of cost) | ≥ 15%                                      | Below this, TQQQ/SGOV at 24% wins outright                         |
| Worst single cell Sharpe    | ≥ 1.0                                      | Robustness — best cell at 2.4 means nothing if worst is 0.2        |
| 2022 standalone return      | ≥ 0%                                       | Strategy must demonstrate the diversification it claims            |
| Cross-cell correlation      | 0.4–0.85                                   | High enough to confirm same signal, low enough to ensemble usefully|
| Win rate (any cell)         | 50–70%                                     | Above 75% suggests model bug; below 45% means edge is fragile      |
| Max DD (ensemble)           | ≤ 25%                                      | Hedge fund standard for vol-arb sleeves                            |

**If all pass: 10–15% of liquid net worth at quarter Kelly.**
**If any fail: shelve the strategy, document the reason, move on.**

We size at 10–15%, not 50%, because:
- TQQQ/SGOV is the equity engine; it should remain dominant.
- Forward Factor's value is uncorrelated returns, not absolute returns.
- A new strategy gets a probationary allocation regardless of backtest
  strength — live execution always reveals issues backtests miss.

## Execution Realism Assumptions

| Parameter           | Value     | Rationale                                                  |
|---------------------|-----------|------------------------------------------------------------|
| Slippage            | 5% of debit | Conservative; ORATS uses 56% of bid-ask which is similar order |
| Commission          | $0.65/contract | Tradier rate                                                |
| Capacity cap        | 5% of daily option volume | Avoids unrealistic fills on thin contracts |
| Exit timing         | T-1 day before front expiry | Avoids pin risk and assignment             |
| Earnings filter     | No earnings between entry and back expiry | Author's "for simplicity" approach |

These are intentionally conservative. If the strategy works under these
assumptions, real-world execution should be equal or better. If it
doesn't, we've correctly avoided a bad bet.

## What We're NOT Testing (Yet)

- **Live execution drift.** Backtest assumes mid-prices with slippage.
  Real fills, especially during vol spikes, can be worse.
- **Capacity at scale.** $200K is well within liquidity bounds. Anything
  approaching $1M+ would need separate analysis.
- **Survivorship bias in universe selection.** We pick top-100 by current
  volume; some past names may have had high FF readings that look
  exploitable but are actually dead names.
- **Earnings IV stripping.** Author uses ex-earnings IV. We use the
  simpler approach of skipping earnings windows entirely. This may
  under-represent the strategy's potential by 5-15% but is far less
  error-prone.

## Module Responsibilities

| Module               | Purpose                                                       |
|----------------------|---------------------------------------------------------------|
| `config/settings.py` | All magic numbers and parameters                              |
| `config/secrets.py`  | API keys (gitignored)                                          |
| `src/data_layer.py`  | Polygon REST/Flat Files wrapper with disk caching              |
| `src/ff_calculator.py` | Forward Factor math, validated against author's calculator.py |
| `src/universe.py`    | Top-N liquid optionable name selector (Chunk 2)                |
| `src/earnings_filter.py` | Earnings calendar + window overlap check (Chunk 2)         |
| `src/trade_simulator.py` | Calendar/double calendar P&L with realistic fills (Chunk 2) |
| `src/portfolio.py`   | Quarter-Kelly sizing, max concurrent, allocation logic (Chunk 2) |
| `src/backtest.py`    | Main loop orchestrator (Chunk 3)                               |
| `src/benchmark.py`   | TQQQ/SGOV, SPY, QQQ comparison strategies (Chunk 3)            |
| `src/metrics.py`     | CAGR, DD, Sharpe, Sortino, regime breakdown (Chunk 3)          |
| `src/dashboard.py`   | Interactive HTML output (Chunk 3)                              |

## Development Chunks

- **Chunk 1 (this commit)**: Project skeleton, FF calculator, data layer,
  unit tests. Validates we can compute FF correctly and pull data from Polygon.
- **Chunk 2 (next)**: Universe selector, earnings filter, trade simulator,
  portfolio sizing. Validates we can simulate a single trade end-to-end.
- **Chunk 3 (final)**: Full backtest orchestrator, benchmarks, metrics,
  dashboard. Produces the capital allocation decision.

After Chunk 3 we have everything needed to answer the question.
