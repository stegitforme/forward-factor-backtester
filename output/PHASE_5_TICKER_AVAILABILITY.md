# Phase 5 — Ticker Availability Across Regimes

Definitive table for the 23-ticker universe. Built before extended-history backtests so regime-test reports can honestly disclose which tickers existed and had ORATS coverage in each stress period.

**Key finding**: 2008 GFC stress test runs on a much smaller universe than the 23-ticker headline suggests. Several tickers either didn't exist (COIN, ARKK, KWEB) or had ORATS coverage gaps (GLD, SLV, ARKK, COIN, KWEB) extending years past their actual inception. Don't claim 'FF survived 2008 GFC across 23 tickers' — it ran on 13.

## Per-ticker inception + ORATS coverage gap

| Ticker | Inception | ORATS First Available | Gap (months) | Notes |
|---|---|---|---:|---|
| AMD | 1979-01-01 | 2007-01-03 | 336 | — |
| ARKK | 2014-10-31 | 2018-04-02 | 41 | **3.5-year ORATS gap** after Oct 2014 inception |
| COIN | 2021-04-14 | 2022-01-03 | 8 | 9-month ORATS gap after Apr 2021 inception |
| EEM | 2003-04-07 | 2007-01-03 | 44 | — |
| FXI | 2004-10-05 | 2007-01-03 | 26 | — |
| GLD | 2004-11-18 | 2009-01-02 | 49 | **4-year ORATS gap** after Nov 2004 inception |
| GOOGL | 2004-08-19 | 2007-01-03 | 28 | **Aliased**: GOOG 2007-01 → GOOGL 2014-04 (post-split Class A) |
| HYG | 2007-04-04 | 2008-01-02 | 8 | 9-month ORATS gap after Apr 2007 inception |
| IBB | 2001-02-05 | 2007-01-03 | 70 | — |
| IWM | 2000-05-22 | 2007-01-03 | 79 | — |
| JPM | 1969-01-01 | 2007-01-03 | 456 | — |
| KBE | 2005-11-08 | 2007-01-03 | 13 | — |
| KRE | 2006-06-19 | 2008-02-19 | 20 | Spotty Jan-Feb 2008 (9/41 days); continuous from 2008-02-19 |
| KWEB | 2013-07-31 | 2015-01-02 | 17 | 1.5-year ORATS gap after Jul 2013 inception |
| META | 2012-05-18 | 2013-01-02 | 7 | **Aliased**: FB 2013-01 → META 2022-07 (ticker rename Jun 9, 2022) |
| MSTR | 1998-06-11 | 2007-01-03 | 102 | — |
| SLV | 2006-04-21 | 2009-01-02 | 32 | **2.5-year ORATS gap** after Apr 2006 inception |
| SMH | 2000-05-05 | 2007-01-03 | 80 | — |
| SPY | 1993-01-22 | 2007-01-03 | 167 | Continuous from earliest data |
| TLT | 2002-07-22 | 2007-01-03 | 53 | — |
| USO | 2006-04-10 | 2008-01-02 | 20 | 21-month ORATS gap after Apr 2006 inception |
| XBI | 2006-01-31 | 2007-01-03 | 11 | — |
| XLF | 1998-12-16 | 2007-01-03 | 96 | — |

## Per-regime ticker counts

How many of the 23 universe tickers are usable in each regime (both inception ≤ regime end AND ORATS coverage starts ≤ regime end).

| Regime | Window | # Available | Missing |
|---|---|---:|---|
| 2008 H2 (GFC: Lehman → YE) | 2008-07-01 → 2008-12-31 | **17/23** | ARKK,COIN,GLD,KWEB,META,SLV |
| 2009 (recovery) | 2009-01-01 → 2009-12-31 | **19/23** | ARKK,COIN,KWEB,META |
| 2010-2014 (low-vol grind) | 2010-01-01 → 2014-12-31 | **20/23** | ARKK,COIN,KWEB |
| 2015 H2 (yuan deval) | 2015-07-01 → 2015-12-31 | **21/23** | ARKK,COIN |
| 2016 H1 (Brexit) | 2016-01-01 → 2016-06-30 | **21/23** | ARKK,COIN |
| 2018 Feb (Volmageddon) | 2018-02-01 → 2018-02-28 | **21/23** | ARKK,COIN |
| 2020 Feb-Apr (COVID) | 2020-02-01 → 2020-04-30 | **22/23** | COIN |
| 2022-2026 (current era) | 2022-01-03 → 2026-04-30 | **23/23** | (none) |

## Per-regime per-ticker matrix

✓ = ticker available in regime (existed AND in ORATS); ✗ = ticker not usable in this regime.

| Ticker | 2008 H2 (GFC: Lehman → YE) | 2009 (recovery) | 2010-2014 (low-vol grind) | 2015 H2 (yuan deval) | 2016 H1 (Brexit) | 2018 Feb (Volmageddon) | 2020 Feb-Apr (COVID) | 2022-2026 (current era) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| AMD | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| ARKK | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| COIN | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| EEM | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| FXI | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| GLD | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| GOOGL | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| HYG | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| IBB | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| IWM | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| JPM | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| KBE | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| KRE | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| KWEB | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ |
| META | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| MSTR | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| SLV | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| SMH | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| SPY | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| TLT | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| USO | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| XBI | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| XLF | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

## Ticker aliasing required for full coverage

Two tickers in the universe have predecessor symbols in ORATS that materially extend their backtest history. Discovery code should consult `TICKER_HISTORY` to pick the right ORATS symbol per date.

| Universe Ticker | Predecessor (ORATS) | Predecessor Window | Successor (ORATS) | Successor Window | Why |
|---|---|---|---|---|---|
| META | FB | 2013-01-02 → 2022-06-30 | META | 2022-07-01 → present | Ticker change Jun 9, 2022 (Facebook → Meta Platforms) |
| GOOGL | GOOG | 2007-01-03 → 2014-04-02 | GOOGL | 2014-04-03 → present | Apr 3, 2014 stock split (GOOG = Class C, GOOGL = Class A; pre-split = single GOOG class) |

**Without aliasing**: META has only ~4 years of ORATS data (2022+); GOOGL has only ~11 years (2015+). With aliasing: META gets ~13 years (2013+); GOOGL gets the full 19 years (2007+). The aliasing is essential to give pre-2022 single-name regimes a representative sample.

## Regime-test interpretation guidance

### 2008 H2 (GFC: Lehman → YE) (17/23 tickers)
**Missing**: ARKK,COIN,GLD,KWEB,META,SLV

Of the missing: 4 ETFs (sector/commodity diversifiers), 2 single names. Strategy diversification is materially weaker in this regime than in 2022-2026.

### 2009 (recovery) (19/23 tickers)
**Missing**: ARKK,COIN,KWEB,META

Of the missing: 2 ETFs (sector/commodity diversifiers), 2 single names. Strategy diversification is materially weaker in this regime than in 2022-2026.

### 2010-2014 (low-vol grind) (20/23 tickers)
**Missing**: ARKK,COIN,KWEB

Of the missing: 2 ETFs (sector/commodity diversifiers), 1 single names. Strategy diversification is materially weaker in this regime than in 2022-2026.

### 2015 H2 (yuan deval) (21/23 tickers)
**Missing**: ARKK,COIN

Of the missing: 1 ETFs (sector/commodity diversifiers), 1 single names. Strategy diversification is materially weaker in this regime than in 2022-2026.

### 2016 H1 (Brexit) (21/23 tickers)
**Missing**: ARKK,COIN

Of the missing: 1 ETFs (sector/commodity diversifiers), 1 single names. Strategy diversification is materially weaker in this regime than in 2022-2026.

### 2018 Feb (Volmageddon) (21/23 tickers)
**Missing**: ARKK,COIN

Of the missing: 1 ETFs (sector/commodity diversifiers), 1 single names. Strategy diversification is materially weaker in this regime than in 2022-2026.

### 2020 Feb-Apr (COVID) (22/23 tickers)
**Missing**: COIN

Of the missing: 0 ETFs (sector/commodity diversifiers), 1 single names. Strategy diversification is materially weaker in this regime than in 2022-2026.

### 2022-2026 (current era) (23/23 tickers)
Full universe available. No interpretation caveats.

## Files

- `output/phase5_ticker_availability.csv` — machine-readable per-ticker per-regime matrix
- `scripts/phase5_ticker_availability.py` — this script (re-runnable)

## Provenance

Inception dates verified 2026-05-04 from public sources (SEC filings, ETF issuer pages, Wikipedia for ticker changes). ORATS first-appearance probed empirically by reading 1st-of-year ZIP for 2007-2026 and drilling monthly/quarterly into the year of first appearance for a tighter date.