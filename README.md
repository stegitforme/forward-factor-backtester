# Forward Factor Backtester

Independent validation of the Forward Factor calendar spread strategy
([Volatility Vibes](https://www.youtube.com/watch?v=6ao3uXE5KhU))
against the academic foundation
([Campasano 2018, "Term Structure Forecasts of Volatility"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3240028)),
with head-to-head comparison against a TQQQ/SGOV volatility-targeting baseline.

## Why This Exists

A YouTube creator claims a calendar spread strategy delivers ~27% CAGR
with 2.4 Sharpe over 19 years. The math is real, the academic paper is real,
and the methodology is plausible — but no independent verification exists.
The author markets a SaaS platform (oQuants) as the implementation channel,
which is a structural conflict. We're building this to answer one question
with our own data, our own code, and our own benchmarks:

**Does Forward Factor deliver real, uncorrelated alpha that justifies
allocation alongside an existing TQQQ/SGOV volatility-targeting strategy?**

## What "Real" Looks Like (Decision Criteria)

Capital allocation requires the strategy to clear all of these on
out-of-sample data (2022-05-02 to today):

| Test                        | Threshold                                  |
|-----------------------------|--------------------------------------------|
| Ensemble CAGR (net of cost) | ≥ 15%                                      |
| Worst single cell Sharpe    | ≥ 1.0                                      |
| 2022 standalone return      | ≥ 0% (proves diversification thesis)       |
| Cross-cell correlation      | 0.4–0.85 (same signal, ensembleable)       |
| Win rate                    | 50–70% (above 75% suggests bug; below 45% fragile) |
| Max DD (ensemble)           | ≤ 25%                                      |

If all pass: 10–15% of liquid net worth at quarter Kelly.
If any fail: strategy is shelved, and we know exactly why.

## What This Project Tests

A 6-cell parameter grid plus an equal-weighted ensemble:

|              | 30/60 DTE | 30/90 DTE | 60/90 DTE |
|--------------|-----------|-----------|-----------|
| ATM Calendar | Cell 1    | Cell 2    | Cell 3    |
| 35Δ Double   | Cell 4    | Cell 5    | Cell 6    |

Plus benchmarks: SPY buy-and-hold, QQQ buy-and-hold, TQQQ/SGOV 35-vol-target
with 200-day MA guard.

## Architecture

```
forward-factor-backtester/
├── config/                 # Settings, secrets template
├── src/                    # Core modules (data, FF math, simulator, etc.)
├── tests/                  # Unit tests (FF math validation, edge cases)
├── docs/                   # Architecture decisions, capital allocation criteria
├── notebooks/              # Colab runner for end-to-end execution
└── data_cache/             # Local cache for Polygon responses (gitignored)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for design decisions.

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/stegitforme/forward-factor-backtester.git
cd forward-factor-backtester

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy secrets template and add your Polygon API key
cp config/secrets.example.py config/secrets.py
# Edit config/secrets.py with your POLYGON_API_KEY

# 4. Run tests to verify FF math against the author's calculator
pytest tests/

# 5. (Coming in Chunk 2/3) Run the full backtest
python -m src.backtest
```

## Data Source

Polygon.io **Options Advanced** tier ($199/m, downgrade to Starter
post-validation). Provides 5+ years history, real-time Greeks/IV,
unlimited API calls. Required for the historical depth needed to test
through 2022 bear, 2024 vol spike, and full 2022–2026 cycle.

## Development Status

- [x] **Chunk 1**: Project skeleton, data layer, FF calculator, validation tests
- [ ] **Chunk 2**: Universe selector, earnings filter, trade simulator, portfolio sizing
- [ ] **Chunk 3**: Backtest orchestrator, benchmarks, metrics, interactive dashboard

## License

Private. All rights reserved.
