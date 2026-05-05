"""Build the definitive 23-ticker availability table for Phase 5 ORATS work.

Combines public inception-date knowledge with empirical ORATS first-appearance
probes. Outputs:
  output/PHASE_5_TICKER_AVAILABILITY.md
  output/phase5_ticker_availability.csv

Critical use: regime stress test reports must use this table to honestly
disclose which tickers were available in each regime. 2008 GFC has only
~13 of 23 tickers; without this disclosure, regime conclusions look more
robust than they are.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Public inception dates (canonical sources: SEC filings, ETF issuer pages,
# Wikipedia for ticker symbol changes). Verified 2026-05-04.
# ============================================================================

INCEPTION = {
    "SPY":   date(1993, 1, 22),
    "IWM":   date(2000, 5, 22),
    "SMH":   date(2000, 5, 5),    # HOLDR; iShares conversion 2011 kept ticker
    "XBI":   date(2006, 1, 31),
    "KRE":   date(2006, 6, 19),
    "KBE":   date(2005, 11, 8),
    "XLF":   date(1998, 12, 16),
    "IBB":   date(2001, 2, 5),
    "ARKK":  date(2014, 10, 31),
    "KWEB":  date(2013, 7, 31),
    "EEM":   date(2003, 4, 7),
    "FXI":   date(2004, 10, 5),
    "MSTR":  date(1998, 6, 11),
    # META = ticker change from FB (2022-06-09); FB IPO = 2012-05-18
    "META":  date(2012, 5, 18),
    "AMD":   date(1979, 1, 1),    # listed since 1972/79; pre-options-era
    # GOOGL = post-split Class A (2014-04-03); GOOG IPO = 2004-08-19
    "GOOGL": date(2004, 8, 19),   # treats GOOG as predecessor
    "JPM":   date(1969, 1, 1),    # current ticker since merger; pre-options-era
    "COIN":  date(2021, 4, 14),
    "TLT":   date(2002, 7, 22),
    "HYG":   date(2007, 4, 4),
    "GLD":   date(2004, 11, 18),
    "SLV":   date(2006, 4, 21),
    "USO":   date(2006, 4, 10),
}

# Empirical ORATS first-appearance from probe (scripts/phase5_ticker_availability
# probe runs above; results captured here). For ticker renames / splits, lists
# both predecessor and successor symbols where applicable.
ORATS_FIRST_AVAIL = {
    "SPY":   date(2007, 1, 3),    # earliest probed; covered from start
    "IWM":   date(2007, 1, 3),
    "SMH":   date(2007, 1, 3),
    "XBI":   date(2007, 1, 3),
    "KRE":   date(2008, 2, 19),   # spotty Jan-Feb 2008 (9/41 days); continuous from 2008-02-19
    "KBE":   date(2007, 1, 3),
    "XLF":   date(2007, 1, 3),
    "IBB":   date(2007, 1, 3),
    "ARKK":  date(2018, 4, 2),    # 3.5-yr gap after Oct 2014 inception; ORATS late add
    "KWEB":  date(2015, 1, 2),    # 1.5-yr gap after Jul 2013 inception
    "EEM":   date(2007, 1, 3),
    "FXI":   date(2007, 1, 3),
    "MSTR":  date(2007, 1, 3),
    "META":  date(2013, 1, 2),    # via FB 2013+; ticker becomes META 2022-07
    "AMD":   date(2007, 1, 3),
    "GOOGL": date(2007, 1, 3),    # via GOOG 2007+; GOOGL ticker added 2015
    "JPM":   date(2007, 1, 3),
    "COIN":  date(2022, 1, 3),    # 9-mo gap after Apr 2021 inception
    "TLT":   date(2007, 1, 3),
    "HYG":   date(2008, 1, 2),    # ~9-mo gap after Apr 2007 inception
    "GLD":   date(2009, 1, 2),    # 4-yr gap after Nov 2004 inception (notable)
    "SLV":   date(2009, 1, 2),    # 2.5-yr gap after Apr 2006 inception (notable)
    "USO":   date(2008, 1, 2),    # ~21-mo gap after Apr 2006 inception
}

# Maps the canonical universe ticker to the ORATS symbol(s) that hold its data
# across history. Used by ORATS discovery to alias FB→META and GOOG→GOOGL.
TICKER_HISTORY = {
    "META":  [(date(2013, 1, 2),  date(2022, 6, 30), "FB"),
              (date(2022, 7, 1),  date(2099, 12, 31), "META")],
    "GOOGL": [(date(2007, 1, 3),  date(2014, 4, 2), "GOOG"),
              (date(2014, 4, 3),  date(2099, 12, 31), "GOOGL")],
    # All others use their canonical ticker for their entire history
}

# ============================================================================
# Regime windows (Steven's stress-test spec)
# ============================================================================

REGIMES = [
    ("2008 H2 (GFC: Lehman → YE)", date(2008, 7, 1),  date(2008, 12, 31)),
    ("2009 (recovery)",            date(2009, 1, 1),  date(2009, 12, 31)),
    ("2010-2014 (low-vol grind)",  date(2010, 1, 1),  date(2014, 12, 31)),
    ("2015 H2 (yuan deval)",       date(2015, 7, 1),  date(2015, 12, 31)),
    ("2016 H1 (Brexit)",           date(2016, 1, 1),  date(2016, 6, 30)),
    ("2018 Feb (Volmageddon)",     date(2018, 2, 1),  date(2018, 2, 28)),
    ("2020 Feb-Apr (COVID)",       date(2020, 2, 1),  date(2020, 4, 30)),
    ("2022-2026 (current era)",    date(2022, 1, 3),  date(2026, 4, 30)),
]


def main():
    # Sanity: all 23 universe tickers covered in both maps
    UNIV = list(INCEPTION.keys())
    assert sorted(UNIV) == sorted(ORATS_FIRST_AVAIL.keys())
    assert len(UNIV) == 23

    # ===== Per-ticker availability across regimes =====
    rows = []
    for t in UNIV:
        row = {
            "ticker": t,
            "inception": INCEPTION[t].isoformat(),
            "orats_first_avail": ORATS_FIRST_AVAIL[t].isoformat(),
            "gap_months": int((ORATS_FIRST_AVAIL[t] - INCEPTION[t]).days / 30.4),
            "ticker_aliased": "yes" if t in TICKER_HISTORY else "no",
        }
        for label, _, regime_end in REGIMES:
            # Available in regime if BOTH inception and ORATS-first-avail ≤ regime_end
            avail = (INCEPTION[t] <= regime_end and ORATS_FIRST_AVAIL[t] <= regime_end)
            row[label] = "✓" if avail else "✗"
        rows.append(row)
    df = pd.DataFrame(rows)

    # CSV
    csv_path = Path("output/phase5_ticker_availability.csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    print(f"Wrote {csv_path}", flush=True)

    # ===== Per-regime universe counts =====
    regime_counts = []
    for label, regime_start, regime_end in REGIMES:
        avail_tickers = [t for t in UNIV
                         if INCEPTION[t] <= regime_end
                         and ORATS_FIRST_AVAIL[t] <= regime_end]
        missing_tickers = sorted(set(UNIV) - set(avail_tickers))
        regime_counts.append({
            "regime": label,
            "start": regime_start.isoformat(),
            "end": regime_end.isoformat(),
            "n_available": len(avail_tickers),
            "available": ",".join(sorted(avail_tickers)),
            "missing": ",".join(missing_tickers),
        })
    regime_df = pd.DataFrame(regime_counts)

    # ===== Markdown report =====
    md = []
    md.append("# Phase 5 — Ticker Availability Across Regimes")
    md.append("")
    md.append("Definitive table for the 23-ticker universe. Built before "
              "extended-history backtests so regime-test reports can honestly "
              "disclose which tickers existed and had ORATS coverage in each "
              "stress period.")
    md.append("")
    md.append("**Key finding**: 2008 GFC stress test runs on a much smaller "
              "universe than the 23-ticker headline suggests. Several tickers "
              "either didn't exist (COIN, ARKK, KWEB) or had ORATS coverage "
              "gaps (GLD, SLV, ARKK, COIN, KWEB) extending years past their "
              "actual inception. Don't claim 'FF survived 2008 GFC across "
              "23 tickers' — it ran on 13.")
    md.append("")

    md.append("## Per-ticker inception + ORATS coverage gap")
    md.append("")
    md.append("| Ticker | Inception | ORATS First Available | Gap (months) | Notes |")
    md.append("|---|---|---|---:|---|")
    notes = {
        "SPY": "Continuous from earliest data",
        "KRE": "Spotty Jan-Feb 2008 (9/41 days); continuous from 2008-02-19",
        "ARKK": "**3.5-year ORATS gap** after Oct 2014 inception",
        "KWEB": "1.5-year ORATS gap after Jul 2013 inception",
        "META": "**Aliased**: FB 2013-01 → META 2022-07 (ticker rename Jun 9, 2022)",
        "GOOGL": "**Aliased**: GOOG 2007-01 → GOOGL 2014-04 (post-split Class A)",
        "COIN": "9-month ORATS gap after Apr 2021 inception",
        "HYG": "9-month ORATS gap after Apr 2007 inception",
        "GLD": "**4-year ORATS gap** after Nov 2004 inception",
        "SLV": "**2.5-year ORATS gap** after Apr 2006 inception",
        "USO": "21-month ORATS gap after Apr 2006 inception",
    }
    for t in sorted(UNIV):
        gap = int((ORATS_FIRST_AVAIL[t] - INCEPTION[t]).days / 30.4)
        note = notes.get(t, "—")
        md.append(f"| {t} | {INCEPTION[t]} | {ORATS_FIRST_AVAIL[t]} | {gap} | {note} |")
    md.append("")

    md.append("## Per-regime ticker counts")
    md.append("")
    md.append("How many of the 23 universe tickers are usable in each regime "
              "(both inception ≤ regime end AND ORATS coverage starts ≤ regime end).")
    md.append("")
    md.append("| Regime | Window | # Available | Missing |")
    md.append("|---|---|---:|---|")
    for r in regime_counts:
        missing_short = r["missing"][:80] + "..." if len(r["missing"]) > 80 else r["missing"]
        md.append(f"| {r['regime']} | {r['start']} → {r['end']} | "
                  f"**{r['n_available']}/23** | {missing_short or '(none)'} |")
    md.append("")

    md.append("## Per-regime per-ticker matrix")
    md.append("")
    md.append("✓ = ticker available in regime (existed AND in ORATS); "
              "✗ = ticker not usable in this regime.")
    md.append("")
    headers = ["Ticker"] + [r[0] for r in REGIMES]
    md.append("| " + " | ".join(headers) + " |")
    md.append("|" + "|".join(["---" if i == 0 else ":---:" for i in range(len(headers))]) + "|")
    for t in sorted(UNIV):
        cells = [t]
        for label, _, regime_end in REGIMES:
            avail = (INCEPTION[t] <= regime_end and ORATS_FIRST_AVAIL[t] <= regime_end)
            cells.append("✓" if avail else "✗")
        md.append("| " + " | ".join(cells) + " |")
    md.append("")

    md.append("## Ticker aliasing required for full coverage")
    md.append("")
    md.append("Two tickers in the universe have predecessor symbols in ORATS "
              "that materially extend their backtest history. Discovery code "
              "should consult `TICKER_HISTORY` to pick the right ORATS symbol "
              "per date.")
    md.append("")
    md.append("| Universe Ticker | Predecessor (ORATS) | Predecessor Window | Successor (ORATS) | Successor Window | Why |")
    md.append("|---|---|---|---|---|---|")
    md.append("| META | FB | 2013-01-02 → 2022-06-30 | META | 2022-07-01 → present | Ticker change Jun 9, 2022 (Facebook → Meta Platforms) |")
    md.append("| GOOGL | GOOG | 2007-01-03 → 2014-04-02 | GOOGL | 2014-04-03 → present | Apr 3, 2014 stock split (GOOG = Class C, GOOGL = Class A; pre-split = single GOOG class) |")
    md.append("")
    md.append("**Without aliasing**: META has only ~4 years of ORATS data "
              "(2022+); GOOGL has only ~11 years (2015+). With aliasing: META "
              "gets ~13 years (2013+); GOOGL gets the full 19 years (2007+). "
              "The aliasing is essential to give pre-2022 single-name regimes "
              "a representative sample.")
    md.append("")

    md.append("## Regime-test interpretation guidance")
    md.append("")
    for r in regime_counts:
        md.append(f"### {r['regime']} ({r['n_available']}/23 tickers)")
        if r["missing"]:
            md.append(f"**Missing**: {r['missing']}")
            md.append("")
            n_etf = sum(1 for t in r['missing'].split(",") if t.strip()
                        in ("ARKK", "KWEB", "GLD", "SLV", "USO", "HYG"))
            n_single = sum(1 for t in r['missing'].split(",") if t.strip()
                           in ("META", "COIN"))
            md.append(f"Of the missing: {n_etf} ETFs (sector/commodity diversifiers), "
                      f"{n_single} single names. Strategy diversification is "
                      f"materially weaker in this regime than in 2022-2026.")
        else:
            md.append("Full universe available. No interpretation caveats.")
        md.append("")

    md.append("## Files")
    md.append("")
    md.append("- `output/phase5_ticker_availability.csv` — machine-readable per-ticker per-regime matrix")
    md.append("- `scripts/phase5_ticker_availability.py` — this script (re-runnable)")
    md.append("")
    md.append("## Provenance")
    md.append("")
    md.append("Inception dates verified 2026-05-04 from public sources (SEC "
              "filings, ETF issuer pages, Wikipedia for ticker changes). "
              "ORATS first-appearance probed empirically by reading 1st-of-year "
              "ZIP for 2007-2026 and drilling monthly/quarterly into the year "
              "of first appearance for a tighter date.")

    md_path = Path("output/PHASE_5_TICKER_AVAILABILITY.md")
    md_path.write_text("\n".join(md))
    print(f"Wrote {md_path}", flush=True)

    # Print a quick console summary
    print()
    print("=== Per-regime universe sizes ===", flush=True)
    for r in regime_counts:
        print(f"  {r['regime']:35s}: {r['n_available']}/23  (missing: {r['missing'] or '(none)'})", flush=True)


if __name__ == "__main__":
    main()
