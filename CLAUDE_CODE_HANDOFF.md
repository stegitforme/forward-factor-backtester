# Claude Code Handoff: Forward Factor Backtester

## TL;DR

Independent backtest of the **Forward Factor calendar spread strategy** (Volatility Vibes YouTube channel, validated against Campasano 2018 SSRN paper). The codebase has been **simplified to a single cell: 60-DTE front / 90-DTE back, ATM call calendar.** It runs end-to-end via `notebooks/colab_runner.ipynb` against Polygon Options Advanced (~$199/mo).

The smoke test runs in 5-15 minutes and confirms the pipeline works. The full 4-year backtest will take 4-12 hours on first run (Polygon API latency dominated; subsequent runs use disk cache).

**Primary user**: Steven Goglanian, sgoglanian@gmail.com. Already paid for Polygon Options Advanced through May 14, 2026 — should downgrade May 30.

## How to Pick This Up

```bash
git clone https://github.com/stegitforme/forward-factor-backtester.git
cd forward-factor-backtester
pip install -r requirements.txt
python -m pytest tests/  # Should report 153 passed
```

If you want to run the backtest, you need:
- A Polygon Options Advanced API key (Steven's: `l1AakpBVhCItuxqKpyKyIhExcD57Vsyo`)
- Put it in `config/secrets.py` (gitignored): `POLYGON_API_KEY = '...'`
- Run cells in `notebooks/colab_runner.ipynb` in order

## Decision: Simplified to Single Cell (2026-05-02)

The original design had a 6-cell parameter grid (3 DTE pairs × 2 structures). Steven decided to keep ONLY 60-DTE front / 90-DTE back ATM calls. The codebase still *supports* multi-cell setups — the `Cell` dataclass and `all_cells()` builder are intact — we just configured a 1-cell grid in `config/settings.py`:

```python
DTE_PAIRS: list[tuple[int, int]] = [(60, 90)]
STRUCTURES: list[str] = ["atm_call_calendar"]
```

Re-enabling the full grid is a one-line edit if you ever want to compare.

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
- ✅ **153 unit tests passing**

The smoke test (3 tickers × 30 days, 60_90_atm cell) ran successfully and **opened 3 positions** for AAPL on Jan 11, 12, and 19 of 2024.

## Known Issues / Outstanding Work

### 1. TQQQ benchmark drift (medium priority)

The benchmark `src/benchmark.py` reproduces Steven's TQQQ Vol Accel Guard but shows 3-5pp CAGR drift versus his reference numbers (43.2/-21.1 expected on 3Y vs 38.1/-28.0 actual; 5Y/2017+/2014+ all collapse to the same number, indicating Polygon's TQQQ history only goes back ~2022).

**Fix path**: Either accept and document the drift, or supplement Polygon TQQQ data with yfinance for pre-2022. The drift doesn't block the FF allocation decision — but Steven will compare them, so be honest about the gap.

### 2. Earnings filter is non-functional but silent

The Polygon endpoint `/v1/reference/tickers/{ticker}` returns 404. `/v3/reference/tickers/{ticker}` returns ticker metadata (no earnings). `/vX/reference/tickers/{ticker}/events` returns ticker_change events only.

**Current state**: Filter returns empty calendar (no earnings to block any trades). Warning logs were downgraded from `warning` to `debug` to silence spam.

**Recommendation**: Use AlphaVantage's free earnings calendar OR a hardcoded earnings list for the major tickers (~30 names) covering 2022-2026. Both are tractable.

### 3. Trade exit at parity (placeholder P&L)

`src/backtest.py` `step_one_day()` exits positions at `entry_debit` (no P&L). The placeholder is clearly comment-marked. Replace with `simulate_calendar()` calls that re-query the option chain at exit date, similar to `find_candidates_for_day()`.

This is the **single most important remaining piece**. Without it, the backtest produces flat equity curves regardless of strategy quality. The data layer and chain resolver already exist; you just need to:

1. Track strikes on the `Position` (currently set to 0.0 placeholder)
2. At exit date, fetch the front and back close prices via `_open_close_get`
3. Compute exit value = back_close - front_close (per spread)
4. Plug that into `close_position()`

Estimated effort: 2-4 hours including tests.

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

## What I'd Do First If I Were You

1. **Run the smoke test** to confirm the environment works and pipeline produces opens
2. **Implement real exit pricing** in `step_one_day()` — this is the highest-leverage fix; without it, all backtest results are meaningless flat lines
3. **Add a hardcoded earnings calendar** for the top ~30 names (or wire AlphaVantage). Sample format: `{ticker: [date, date, ...]}`
4. **Re-run the smoke test** with real exits to see win rate / payoff ratio
5. **Run the full backtest** once everything looks reasonable
6. **Compare Forward Factor strategy vs Steven's TQQQ Vol Accel Guard benchmark** for the capital allocation decision

## Decision Criteria for Allocation

Steven's bar (per his criteria):
- ✅ Ensemble CAGR ≥ 15%
- ✅ Worst single cell Sharpe ≥ 1.0  
- ✅ Win rate 50–70%
- ✅ Max DD ≤ 25%

If all four pass, allocate 10–15% of liquid net worth at quarter Kelly. If any fail, document the failure mode and stand pat.

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
