"""Phase 4 Tier 1 pre-flight: back-leg resolution check on 26 new tickers.

Drops any new ticker with <20% back-leg resolution rate (matching incumbent
threshold). Outputs the filtered universe ready for discovery.

Sample: weekly Wednesdays across the full Phase 3 window.
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

# Make repo root importable
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout)

from src.data_layer import get_client
from src.chain_resolver import resolve_atm_option

# 26 new tickers per Steven's spec
NEW_TICKERS = [
    # Equity additions
    "XLK", "XLE", "XLV", "XLI", "XLP", "XLU", "XLRE", "XLY",
    "EFA", "EEM", "FXI", "GDXJ", "SOXL",
    # Bond/credit
    "HYG", "LQD", "IEF", "EMB",
    # Commodity
    "GLD", "SLV", "USO",
    # Currency
    "FXE", "UUP", "FXY",
    # Vol
    "VXX",
]
WINDOW_START = date(2022, 1, 3)
WINDOW_END = date(2026, 4, 30)
CELLS = [("30_90_atm", 30, 90), ("60_90_atm", 60, 90)]
RESOLUTION_THRESHOLD = 0.20  # 20% back-leg resolution

client = get_client()

# Sample dates: Wednesdays in window
sample_dates = []
cur = WINDOW_START
while cur <= WINDOW_END:
    if cur.weekday() == 2:
        sample_dates.append(cur)
    cur += timedelta(days=1)

print(f"### Phase 4 Tier 1 PRE-FLIGHT", flush=True)
print(f"  {len(NEW_TICKERS)} new tickers x {len(sample_dates)} sample dates x {len(CELLS)} cells = "
      f"{len(NEW_TICKERS)*len(sample_dates)*len(CELLS):,} samples", flush=True)
print(f"  Pass threshold: back-leg resolution >= {RESOLUTION_THRESHOLD*100:.0f}%", flush=True)
print()

# Per-ticker back-leg resolution rate (across both cells, conservative: AVG)
results = {t: {cn: {"front_ok": 0, "back_ok": 0, "n": 0} for cn, _, _ in CELLS}
           for t in NEW_TICKERS}

t0 = time.time()
n_done = 0
n_total = len(NEW_TICKERS) * len(sample_dates) * len(CELLS)

for ticker in NEW_TICKERS:
    for d in sample_dates:
        for cell_name, dte_f, dte_b in CELLS:
            results[ticker][cell_name]["n"] += 1
            try:
                front = resolve_atm_option(client, ticker, d, dte_f, contract_type="call")
            except Exception:
                front = None
            if front is None:
                n_done += 1; continue
            results[ticker][cell_name]["front_ok"] += 1
            try:
                back = resolve_atm_option(client, ticker, d, dte_b, contract_type="call")
            except Exception:
                back = None
            if back is not None:
                results[ticker][cell_name]["back_ok"] += 1
            n_done += 1
            if n_done % 200 == 0:
                elapsed = time.time() - t0
                rate = n_done / elapsed if elapsed > 0 else 0
                eta = (n_total - n_done) / rate if rate > 0 else 0
                print(f"  [{n_done}/{n_total}] elapsed={elapsed:.0f}s rate={rate:.1f}/s eta={eta:.0f}s", flush=True)

print(f"\n  Done in {time.time()-t0:.0f}s", flush=True)

# Report per-ticker (averaged across cells)
print(f"\n{'='*80}\nPRE-FLIGHT RESOLUTION RATES (averaged across both cells)\n{'='*80}", flush=True)
print(f"{'ticker':<8} {'30-90 back%':>12} {'60-90 back%':>12} {'avg back%':>11} verdict", flush=True)
keep, exclude = [], []
for ticker in NEW_TICKERS:
    rates = {}
    for cn, _, _ in CELLS:
        r = results[ticker][cn]
        rates[cn] = (r["back_ok"] / r["n"]) if r["n"] > 0 else 0
    avg = sum(rates.values()) / len(rates)
    verdict = "KEEP" if avg >= RESOLUTION_THRESHOLD else "EXCLUDE"
    if avg >= RESOLUTION_THRESHOLD: keep.append(ticker)
    else: exclude.append(ticker)
    print(f"{ticker:<8} {rates['30_90_atm']*100:>11.1f}% {rates['60_90_atm']*100:>11.1f}% {avg*100:>10.1f}%  {verdict}", flush=True)

print(f"\n{'='*80}\nVERDICT\n{'='*80}", flush=True)
print(f"KEEP    ({len(keep)}): {keep}", flush=True)
print(f"EXCLUDE ({len(exclude)}): {exclude}", flush=True)

# Existing 17 from Phase 3 + new passers = full Tier 1 universe
EXISTING = ["SPY", "IWM", "SMH", "XBI", "KWEB", "TLT", "MSTR",
            "KRE", "KBE", "XLF", "IBB", "ARKK", "COIN", "AMD", "META", "GOOGL", "JPM"]
union = sorted(set(EXISTING + keep))
print(f"\nFinal Tier 1 universe ({len(union)}): {union}", flush=True)

# Save the universe to a file the discovery script can read
out = Path("output/phase4_t1_universe.txt")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(",".join(union))
print(f"Wrote {out}", flush=True)
