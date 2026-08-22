#!/usr/bin/env python3
"""Offline tests for the relative-valuation math (spec §5). No network. Run:
  python3 finance/tests/test_relval.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import relval  # noqa: E402
from finance.tests.harness import approx, check, summary  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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

# --- I3: a negative/zero peer P/E is not a multiple → excluded from the median ---------
# Raw median of [-14, 9, 11, 13, 18] is 11 (negatives drag the centre down); pricing only the
# positives gives median([9,11,13,18]) = 12, and the count of loss-makers is reported.
r = relval.relative_read({"pe": 20.0, "peer_pe": [-14, 9, 11, 13, 18],
                          "own_pe_history": [15, 18, 20, 22, 24]})
check("negative peer P/E excluded from the median", r["peer_median_pe"] == 12.0, r)
check("priced-peer count excludes the loss-maker", r["peers_priced"] == 4, r)
check("excluded loss-makers are reported", r["peers_excluded_nonpositive"] == 1, r)
# A zero P/E is equally not a multiple.
r = relval.relative_read({"pe": 20.0, "peer_pe": [0, 22, 24, 26]})
check("zero peer P/E excluded too",
      r["peers_priced"] == 3 and r["peers_excluded_nonpositive"] == 1, r)
# All peers loss-making → no median, no false stance from an empty set.
r = relval.relative_read({"pe": 20.0, "peer_pe": [-5, -8]})
check("all-negative peer set → no peer median", r["peer_median_pe"] is None
      and r["peers_priced"] == 0 and r["peers_excluded_nonpositive"] == 2, r)

# --- I2: the leg must feed peers on the same TTM basis as the company's Stock P/E ------
with open(os.path.join(_ROOT, "skills/valuation-analysis/SKILL.md"), encoding="utf-8") as fh:
    _skill = fh.read()
check("valuation SKILL names the trailing peer field (ttm_pe), not the annualised one",
      "ttm_pe" in _skill and "annualised" in _skill, "step 6 must pin the TTM basis")

summary()
