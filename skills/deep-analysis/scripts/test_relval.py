#!/usr/bin/env python3
"""Offline tests for the relative-valuation math (spec §5). No network. Run:
  python3 skills/deep-analysis/scripts/test_relval.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import relval  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


def approx(a, b, tol=0.01):
    return a is not None and abs(a - b) <= tol


# --- median (not mean — multiples are skewed) --------------------------------
check("median odd count", relval.median([12, 15, 20, 25, 30]) == 20)
check("median even count", relval.median([22, 24, 28, 30]) == 26)
check("median ignores ordering", relval.median([30, 12, 20]) == 20)
check("median empty → None", relval.median([]) is None)
# mean would be 24.6 on the skewed set; median must not be the mean
check("median is not the mean on a skewed set",
      relval.median([10, 11, 12, 13, 80]) == 12)

# --- PEG = P/E ÷ expected EPS growth (%) -------------------------------------
check("peg basic", approx(relval.peg(18.0, 22.0), 0.82))
check("peg zero growth → None", relval.peg(18.0, 0) is None)
check("peg negative growth → None", relval.peg(18.0, -5) is None)

# --- own-historical-band percentile ------------------------------------------
# 18 sits above 12 and 15 (2 of 5) → 40th percentile of its own band
check("band percentile", relval.band_percentile(18.0, [12, 15, 20, 25, 30]) == 40.0)
check("band percentile at bottom", relval.band_percentile(5.0, [12, 15, 20]) == 0.0)
check("band percentile empty → None", relval.band_percentile(18.0, []) is None)

# --- relative read: combined relative-only stance -----------------------------
r = relval.relative_read({
    "pe": 18.0,
    "peer_pe": [28, 24, 30, 22],
    "own_pe_history": [20, 25, 28, 30, 32],
    "growth": {"value": 22.0, "basis": "5y EPS CAGR", "estimated": True},
})
check("peer_median_pe computed (median not mean)", r["peer_median_pe"] == 26.0, r)
check("discount to peers flagged", r["pe_vs_peer_median"] == "discount", r)
check("relative stance undervalued", r["relative_stance"] == "undervalued", r)
check("peg surfaced in read", approx(r["peg"], 0.82), r)
check("estimated growth labelled", "estimate" in r["growth_basis"].lower(), r)

# premium + top-of-band → overvalued
r = relval.relative_read({
    "pe": 40.0,
    "peer_pe": [20, 22, 24],
    "own_pe_history": [15, 18, 22, 30, 38],
    "growth": {"value": 10.0, "basis": "analyst", "estimated": True},
})
check("premium to peers → overvalued", r["relative_stance"] == "overvalued", r)

# discount to peers but high in own band → the two signals cancel → fair
r = relval.relative_read({
    "pe": 30.0,
    "peer_pe": [34, 36, 40],
    "own_pe_history": [12, 16, 20, 24, 28],
    "growth": {"value": 15.0, "basis": "5y EPS CAGR", "estimated": False},
})
check("opposing signals cancel → fair", r["relative_stance"] == "fair", r)

# missing growth → PEG is None, read still returns a stance
r = relval.relative_read({"pe": 18.0, "peer_pe": [24, 26, 28], "own_pe_history": [20, 22, 24]})
check("missing growth → peg None, stance present", r["peg"] is None and "relative_stance" in r, r)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
