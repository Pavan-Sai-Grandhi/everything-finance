#!/usr/bin/env python3
"""Offline tests for the relative-valuation math (spec §5). No network."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import relval  # noqa: E402
from finance.tests.harness import approx, check, summary  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


check("median odd count", relval.median([12, 15, 20, 25, 30]) == 20)
check("median even count", relval.median([22, 24, 28, 30]) == 26)
check("median ignores ordering", relval.median([30, 12, 20]) == 20)
check("median empty → None", relval.median([]) is None)
check("median is not the mean on a skewed set",
      relval.median([10, 11, 12, 13, 80]) == 12)

check("peg basic", approx(relval.peg(18.0, 22.0), 0.82))
check("peg zero growth → None", relval.peg(18.0, 0) is None)
check("peg negative growth → None", relval.peg(18.0, -5) is None)

check("band percentile", relval.band_percentile(18.0, [12, 15, 20, 25, 30]) == 40.0)
check("band percentile at bottom", relval.band_percentile(5.0, [12, 15, 20]) == 0.0)
check("band percentile empty → None", relval.band_percentile(18.0, []) is None)

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

r = relval.relative_read({
    "pe": 40.0,
    "peer_pe": [20, 22, 24],
    "own_pe_history": [15, 18, 22, 30, 38],
    "growth": {"value": 10.0, "basis": "analyst", "estimated": True},
})
check("premium to peers → overvalued", r["relative_stance"] == "overvalued", r)

r = relval.relative_read({
    "pe": 30.0,
    "peer_pe": [34, 36, 40],
    "own_pe_history": [12, 16, 20, 24, 28],
    "growth": {"value": 15.0, "basis": "5y EPS CAGR", "estimated": False},
})
check("opposing signals cancel → fair", r["relative_stance"] == "fair", r)

r = relval.relative_read({"pe": 18.0, "peer_pe": [24, 26, 28], "own_pe_history": [20, 22, 24]})
check("missing growth → peg None, stance present", r["peg"] is None and "relative_stance" in r, r)

r = relval.relative_read({"pe": 20.0, "peer_pe": [-14, 9, 11, 13, 18],
                          "own_pe_history": [15, 18, 20, 22, 24]})
check("negative peer P/E excluded from the median", r["peer_median_pe"] == 12.0, r)
check("priced-peer count excludes the loss-maker", r["peers_priced"] == 4, r)
check("excluded loss-makers are reported", r["peers_excluded_nonpositive"] == 1, r)
r = relval.relative_read({"pe": 20.0, "peer_pe": [0, 22, 24, 26]})
check("zero peer P/E excluded too",
      r["peers_priced"] == 3 and r["peers_excluded_nonpositive"] == 1, r)
r = relval.relative_read({"pe": 20.0, "peer_pe": [-5, -8]})
check("all-negative peer set → no peer median", r["peer_median_pe"] is None
      and r["peers_priced"] == 0 and r["peers_excluded_nonpositive"] == 2, r)

with open(os.path.join(_ROOT, "skills/valuation-analysis/SKILL.md"), encoding="utf-8") as fh:
    _skill = fh.read()
check("valuation SKILL names the trailing peer field (ttm_pe), not the annualised one",
      "ttm_pe" in _skill and "annualised" in _skill, "step 6 must pin the TTM basis")


r = relval.relative_read({"pe": 122.0, "peer_pe": [], "own_pe_history": [],
                          "growth": {"value": 15.2, "basis": "10y EPS CAGR",
                                     "estimated": True}})
check("no peers, no own band → not computable",
      r["relative_stance"] == "not computable", r)
check("no peers → peer read does not count", r["peer_read_counts"] is False, r)
check("no peers → peer label says so", r["pe_vs_peer_median"] == "not comparable", r)
check("no peers raises two gaps", len(r["gaps"]) == 2, r)
check("a gap names the thin peer set", any("too thin" in g for g in r["gaps"]), r)

r = relval.relative_read({"pe": 40.0, "peer_pe": [20.0, 22.0],
                          "own_pe_history": [30, 35, 40, 45, 50]})
check("2 peers → peer read void", r["peer_read_counts"] is False, r)
check("2 peers → median still reported for context", r["peer_median_pe"] == 21.0, r)
check("2 peers → stance falls back to the own band alone",
      r["relative_stance"] == "fair", r)
check("MIN_PEERS is three", relval.MIN_PEERS == 3, relval.MIN_PEERS)

r = relval.relative_read({"pe": 40.0, "peer_pe": [20.0, 22.0, 21.0],
                          "own_pe_history": [30, 35, 40, 45, 50]})
check("3 peers → peer read counts", r["peer_read_counts"] is True, r)
check("3 peers → premium is read", r["pe_vs_peer_median"] == "premium", r)
check("3 peers → stance moves to overvalued", r["relative_stance"] == "overvalued", r)
check("a sufficient peer set raises no gap", r["gaps"] == [], r)

same = {"pe": 89.8, "peer_pe": [123.0, 80.0, 70.0, 86.0],
        "own_pe_history": [40, 50, 60, 70, 80]}
r = relval.relative_read(same)
check("default basis is reported on both sides",
      (r["pe_basis"], r["peer_pe_basis"]) == ("reported", "reported"), r)
check("matched basis → peer read counts", r["peer_read_counts"] is True, r)

r = relval.relative_read(dict(same, pe_basis="adjusted"))
check("adjusted company P/E vs reported peers → peer read void",
      r["peer_read_counts"] is False, r)
check("basis mismatch is a gap", any("basis mismatch" in g for g in r["gaps"]), r)
check("basis mismatch keeps the median visible", r["peer_median_pe"] == 83.0, r)
check("basis mismatch still reads the own band",
      r["relative_stance"] == "overvalued", r)

r = relval.relative_read(dict(same, pe_basis="adjusted", peer_pe_basis="adjusted"))
check("both sides adjusted → peer read counts again",
      r["peer_read_counts"] is True, r)
check("both-adjusted raises no gap", r["gaps"] == [], r)

r = relval.relative_read(dict(same, pe_basis="clean"))
check("an unknown basis name is a gap",
      any("not one of" in g for g in r["gaps"]), r)

for figs in ({"pe": 20.0, "peer_pe": [18.0, 19.0, 21.0]}, {"pe": None, "peer_pe": []}):
    r = relval.relative_read(figs)
    check("read carries gaps + basis + peer_read_counts",
          {"gaps", "pe_basis", "peer_pe_basis", "peer_read_counts"} <= set(r), r)

_MALFORMED = {
    "own_pe_history as a sentence":
        {"pe": 83.31, "peer_pe": [48.5, 166.5, 24.0],
         "own_pe_history": "not available - no per-stock historical P/E series"},
    "peer_pe as symbol rows":
        {"pe": 83.31, "peer_pe": [{"symbol": "VMART", "pe": 48.5},
                                  {"symbol": "STANLEY", "pe": 166.5}]},
    "peer_pe as a symbol map":
        {"pe": 83.31, "peer_pe": {"VMART": 48.5, "STANLEY": 166.5, "TRENT": 24.0}},
    "peer_pe as a scalar":
        {"pe": 20.0, "peer_pe": 25.0, "growth": 7.5},
    "growth as a bare number":
        {"pe": 83.31, "peer_pe": [48.5, 166.5, 24.0], "growth": 7.5},
    "pe as a formatted string":
        {"pe": "83.31x", "peer_pe": [48.5, 166.5, 24.0]},
}
for name, figs in _MALFORMED.items():
    try:
        r = relval.relative_read(figs)
        raised = None
    except Exception as exc:                                  # noqa: BLE001
        r, raised = None, exc
    check(f"{name} does not raise", raised is None, raised)
    if r is not None:
        check(f"{name} still returns a stance", bool(r.get("relative_stance")), r)

r = relval.relative_read({"pe": 83.31, "peer_pe": [{"symbol": "VMART", "pe": 48.5}]})
check("non-numeric peers are counted in a gap",
      any("not a number" in g for g in r["gaps"]), r)

r = relval.relative_read({"pe": 83.31, "peer_pe": [48.5, 166.5, 24.0],
                          "own_pe_history": "unavailable"})
check("a prose own_pe_history voids the own-band read",
      r["own_band_percentile"] is None
      and any("own_pe_history" in g for g in r["gaps"]), r)

r = relval.relative_read({"pe": 83.31, "peer_pe": [48.5, 166.5, 24.0],
                          "growth": {"value": 0.075, "basis": "3Y EPS CAGR"}})
check("a growth fraction withholds PEG rather than printing 1110",
      r["peg"] is None and any("fraction, not a percent" in g for g in r["gaps"]), r)

r = relval.relative_read({"pe": 83.31, "peer_pe": [48.5, 166.5, 24.0], "growth": 7.5})
check("a bare growth percent is read as the value", r["peg"] == 11.11, r)

for pe in (None, 0, -5, float("nan"), float("inf")):
    r = relval.relative_read({"pe": pe, "peer_pe": [10, 20, 30],
                              "own_pe_history": [10, 20, 30], "growth": 5})
    check("unusable company earnings cannot imply cheapness or fair value",
          r["relative_stance"] == "not computable", r)
    check("unusable earnings cannot yield PEG", r["peg"] is None, r)
r = relval.relative_read({"pe": 20, "peer_pe": [10, 20, 30],
                          "pe_basis": "unchecked", "peer_pe_basis": "unchecked"})
check("two matching invalid P/E bases do not validate a comparison",
      not r["peer_read_counts"], r)

summary()
