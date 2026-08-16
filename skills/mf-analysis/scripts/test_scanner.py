#!/usr/bin/env python3
"""Offline tests for the category scanner's pure logic. No network.
Run: python3 skills/mf-analysis/scripts/test_scanner.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanner as S  # noqa: E402

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


# --- percentile_ranks --------------------------------------------------------
r = S.percentile_ranks([1, 2, 3, 4, 5])
check("best value ranks 1.0 when higher is better", r[4] == 1.0, r)
check("worst value ranks 0.0", r[0] == 0.0, r)
check("ranks are monotonic", r == sorted(r), r)
r_low = S.percentile_ranks([1, 2, 3, 4, 5], higher_is_better=False)
check("lower-is-better inverts the ranking", r_low[0] == 1.0 and r_low[4] == 0.0, r_low)
r_none = S.percentile_ranks([1, None, 3])
check("a missing metric stays None rather than scoring 0",
      r_none[1] is None and r_none[0] == 0.0 and r_none[2] == 1.0, r_none)
check("an all-missing column yields all None",
      S.percentile_ranks([None, None]) == [None, None])
check("a single valued peer scores 0.5 (rank carries no information)",
      S.percentile_ranks([None, 7, None])[1] == 0.5)
ties = S.percentile_ranks([5, 5, 1])
check("ties share the average rank", ties[0] == ties[1], ties)
check("an outlier does not compress the rest (rank, not min-max)",
      S.percentile_ranks([1, 2, 1000])[1] == 0.5, S.percentile_ranks([1, 2, 1000]))

# --- aum_agility -------------------------------------------------------------
check("inside the band scores full marks", S.aum_agility(5000, 500, 20000) == 1.0)
check("below the viability floor scores 0", S.aum_agility(200, 500, 20000) == 0.0)
check("twice the ceiling decays to 0.5, not 0 (size is a headwind, not a veto)",
      S.aum_agility(40000, 500, 20000) == 0.5)
check("exactly at the ceiling still scores 1.0", S.aum_agility(20000, 500, 20000) == 1.0)
check("missing AUM is None, never 0", S.aum_agility(None, 500, 20000) is None)
check("a nonsensical AUM is None", S.aum_agility(0, 500, 20000) is None)
check("agility decays monotonically past the ceiling",
      S.aum_agility(30000, 500, 20000) > S.aum_agility(60000, 500, 20000))

# --- cap_purity --------------------------------------------------------------
check("85% in-mandate maps to 0.85", abs(S.cap_purity(85) - 0.85) < 1e-9)
check("purity is clamped to 1.0", S.cap_purity(120) == 1.0)
check("negative purity clamps to 0", S.cap_purity(-5) == 0.0)
check("missing purity is None", S.cap_purity(None) is None)

# --- composite ---------------------------------------------------------------
score, cov, used = S.composite({k: 1.0 for k in S.WEIGHTS})
check("all components present scores 1.0 at full coverage", score == 1.0 and cov == 1.0)
check("every weighted component is reported as used", len(used) == len(S.WEIGHTS))
k0 = sorted(S.WEIGHTS)[0]
partial = {k: (None if k == k0 else 1.0) for k in S.WEIGHTS}
score_p, cov_p, used_p = S.composite(partial)
check("a missing component redistributes weight instead of penalising",
      score_p == 1.0, score_p)
check("coverage records what actually applied", cov_p < 1.0, cov_p)
check("the dropped component is absent from scored_on", k0 not in used_p)
check("no usable component yields a None score, not 0",
      S.composite({k: None for k in S.WEIGHTS}) == (None, 0.0, []))

# --- gate --------------------------------------------------------------------
good = {"option": "Growth", "expRatio": 0.7, "aum": 5000, "ageInMon": 60}
ok, reasons = S.gate(good, 500, 36)
check("a compliant fund passes every gate", ok and reasons == [], reasons)
ok, reasons = S.gate(dict(good, option="IDCW"), 500, 36)
check("an IDCW plan is gated out", not ok and any("Growth" in r for r in reasons))
ok, reasons = S.gate(dict(good, expRatio=1.9), 500, 36)
check("a Regular-plan TER masquerading as Direct is caught",
      not ok and any("ceiling" in r for r in reasons), reasons)
ok, reasons = S.gate(dict(good, aum=100), 500, 36)
check("sub-floor AUM is gated out", not ok and any("viability" in r for r in reasons))
ok, reasons = S.gate(dict(good, ageInMon=12), 500, 36)
check("a fund younger than the credited window is gated out",
      not ok and any("younger" in r for r in reasons), reasons)
ok, reasons = S.gate({"option": "Growth"}, 500, 36)
check("unpublished fields are gated as unverifiable, never assumed good",
      not ok and len(reasons) == 3, reasons)
check("gate reasons diagnose the fund, never name it",
      all("Growth" in r or "TER" in r or "AUM" in r or "age" in r or "expense" in r
          or "months" in r for r in reasons), reasons)

# --- span_confidence ---------------------------------------------------------
check("under 3 years is low confidence", S.span_confidence(2.0) == "low")
check("3-7 years is ok", S.span_confidence(5.0) == "ok")
check("7+ years earns full-cycle", S.span_confidence(8.0) == "full-cycle")
check("unknown span is 'unknown', not a guess", S.span_confidence(None) == "unknown")

# --- match_amfi_scheme -------------------------------------------------------
schemes = [
    {"code": "1", "name": "ITI Small Cap Fund - Direct Plan - Growth"},
    {"code": "2", "name": "ITI Small Cap Fund - Direct Plan - IDCW"},
    {"code": "3", "name": "ITI Small Cap Fund - Regular Plan - Growth"},
    {"code": "4", "name": "ITI Multi Cap Fund - Direct Plan - Growth"},
    {"code": "5", "name": "ITI Large Cap Fund - Direct Plan - Growth"},
]
m = S.match_amfi_scheme("ITI Small Cap Fund", schemes)
check("the Direct-Growth scheme is chosen", m and m["code"] == "1", m)
check("the IDCW variant is rejected (different NAV series, same name)",
      m and "IDCW" not in m["name"])
check("the Regular plan is rejected", m and "Regular" not in m["name"])
check("'Small Cap' does not match 'Large Cap'",
      S.match_amfi_scheme("ITI Large Cap Fund", schemes)["code"] == "5")
check("token-set matching: 'ITI' must not match inside 'MULTI'",
      S.match_amfi_scheme("ITI Multi Cap Fund", schemes)["code"] == "4")
check("an unmatched fund returns None, never a near-miss",
      S.match_amfi_scheme("Nonexistent Zzz Fund", schemes) is None)
check("an empty scheme list returns None",
      S.match_amfi_scheme("ITI Small Cap Fund", []) is None)

# --- nav_metrics -------------------------------------------------------------
navs = [{"date": f"2020-01-{d:02d}", "nav": v}
        for d, v in zip(range(1, 11), [100, 110, 120, 90, 95, 130, 140, 120, 150, 160])]
m = S.nav_metrics(navs, 1)
check("max drawdown is computed from the NAV series, not bought from a vendor",
      m["max_drawdown_pct"] is not None and m["max_drawdown_pct"] > 0, m["max_drawdown_pct"])
check("the worst peak-to-trough is found (120 -> 90 = 25%)",
      abs(m["max_drawdown_pct"] - 25.0) < 0.01, m["max_drawdown_pct"])
check("the NAV as-of date is the newest bar", m["nav_as_of"] == "2020-01-10", m)
check("a span under 3 years is flagged low confidence", m["confidence"] == "low")
empty = S.nav_metrics([], 1)
check("an empty NAV series degrades to None, never raises",
      empty["max_drawdown_pct"] is None and empty["n_windows"] == 0)
check("a one-point series is still safe", S.nav_metrics([navs[0]], 1)["confidence"] == "unknown")
check("unparseable rows are skipped, not crashed on",
      S.nav_metrics([{"date": "bad", "nav": "x"}] + navs, 1)["nav_as_of"] == "2020-01-10")

# --- load_market_context -----------------------------------------------------
check("a missing market-context path is None, not a fabricated market read",
      S.load_market_context("/nonexistent/path.json", "Small Cap Fund") is None)
with tempfile.TemporaryDirectory() as tmp:
    p = os.path.join(tmp, "mc.json")
    with open(p, "w") as fh:
        json.dump({"as_of": "2026-08-14", "market_trend": "range",
                   "market_posture": "neutral",
                   "volatility": {"band": "low"},
                   "relative": {"percentile_spread": 45.3},
                   "valuation": {"NIFTY SMALLCAP 250": {"pb_pctile": 77.0,
                                                        "stance": "rich"}}}, fh)
    mc = S.load_market_context(p, "Small Cap Fund")
    check("the small-cap tier's valuation is selected for a small-cap scan",
          mc["cap_tier"] == "NIFTY SMALLCAP 250", mc)
    check("the tier stance is carried through VERBATIM (the scanner does not judge it)",
          mc["tier_valuation"]["stance"] == "rich", mc)
    check("posture and volatility band travel with it",
          mc["market_posture"] == "neutral" and mc["volatility_band"] == "low")
    check("the relative read is carried too",
          mc["relative"]["percentile_spread"] == 45.3)
    check("as_of comes from the market artifact, not from today",
          mc["as_of"] == "2026-08-14")
    with open(p, "w") as fh:
        fh.write("{corrupt")
    check("a corrupt market context degrades to None rather than raising",
          S.load_market_context(p, "Small Cap Fund") is None)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
