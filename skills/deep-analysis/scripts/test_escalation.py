#!/usr/bin/env python3
"""Offline tests for the bull/bear round-escalation rule, both modes. No network.
Run: python3 skills/deep-analysis/scripts/test_escalation.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
import escalation  # noqa: E402
from finance.tests.harness import check, summary  # noqa: E402


def dig(axis, claim, conceded=False, new_evidence=True):
    return {"axis": axis, "claim": claim, "conceded": conceded,
            "new_evidence": new_evidence}


# --- the engagement rule ------------------------------------------------------
# same axis, distinct evidence-tied claims, neither conceded → escalate to rebut
r = escalation.should_escalate(
    dig("valuation", "trades at 18x vs peer median 28x — cheap"),
    dig("valuation", "18x is fair given decelerating EPS growth"))
check("same-axis clash → escalate", r["escalate"] is True, r)
check("same-axis directive is rebut", r["directive"] == escalation.REBUT, r)

# different axes → escalate to cross-examine: neither side has tested the other
r = escalation.should_escalate(
    dig("technical_structure", "reclaimed the 200-DMA on rising volume"),
    dig("valuation", "reverse-DCF implies 28% CAGR vs a 3-year stagnation"))
check("different axes → ESCALATE", r["escalate"] is True, r)
check("different-axes directive is cross-examine",
      r["directive"] == escalation.CROSS_EXAMINE, r)
check("different-axes reason names non-engagement",
      "tested the other" in r["reason"], r)
check("different axes is not a gap", r["gaps"] == [], r)

r = escalation.should_escalate(
    dig("valuation", "cheap vs peers"),
    dig("balance_sheet_risk", "D/E 1.8, interest cover 2.1"))
check("different axes (second pair) → escalate", r["escalate"] is True, r)

# --- what actually ends a debate ---------------------------------------------
r = escalation.should_escalate(
    dig("growth_durability", "order book covers 3 years"),
    dig("growth_durability", "agreed, growth visibility is real", conceded=True))
check("a concession → stop", r["escalate"] is False, r)
check("concession reason names the side", "bear conceded" in r["reason"], r)

r = escalation.should_escalate(
    dig("valuation", "cheap", conceded=True),
    dig("governance", "pledging", conceded=True))
check("both conceded → stop", r["escalate"] is False, r)
check("both-conceded reason", "both sides conceded" in r["reason"], r)

# a concession outranks non-engagement — differing axes do not resurrect a
# debate one side has already given up
r = escalation.should_escalate(
    dig("technical_structure", "uptrend intact", conceded=True),
    dig("valuation", "no margin of safety"))
check("concession beats the differing-axes escalation", r["escalate"] is False, r)

r = escalation.should_escalate(
    dig("governance", "promoter pledging at 40%"),
    dig("governance", "Promoter pledging at 40%!"))
check("restated identical claim → stop", r["escalate"] is False, r)
check("restatement reason", "restate" in r["reason"], r)

r = escalation.should_escalate(
    dig("technical_structure", "broke 200-DMA on volume"),
    dig("technical_structure", ""))
check("empty claim → stop", r["escalate"] is False, r)
check("empty claim is reported as a gap", any("bear" in g for g in r["gaps"]), r)

# --- a malformed digest is a contract bug, reported as such -------------------
r = escalation.should_escalate(dig("vibes", "feels expensive"),
                               dig("vibes", "feels cheap"))
check("unrecognised axis → stop", r["escalate"] is False, r)
check("unrecognised axis is reported as a gap", len(r["gaps"]) == 2, r)
check("the gap names the offending value", "'vibes'" in r["gaps"][0], r)
check("unrecognised-axis reason does not claim convergence",
      "converged" not in r["reason"], r)

# --- round caps ---------------------------------------------------------------
clash = (dig("valuation", "cheap"), dig("valuation", "dear"))
check("standard: round 1 escalates",
      escalation.should_escalate(*clash, mode="standard", round_no=1)["escalate"] is True)
check("standard: round 2 is the cap",
      escalation.should_escalate(*clash, mode="standard", round_no=2)["escalate"] is False)
check("deep: round 2 still escalates",
      escalation.should_escalate(*clash, mode="deep", round_no=2)["escalate"] is True)
check("deep: round 3 is the cap",
      escalation.should_escalate(*clash, mode="deep", round_no=3)["escalate"] is False)
r = escalation.should_escalate(*clash, mode="deep", round_no=3)
check("cap reason names the mode", "deep mode" in r["reason"], r)
check("MAX_ROUNDS is declared per mode",
      escalation.MAX_ROUNDS == {"standard": 2, "deep": 3}, escalation.MAX_ROUNDS)

# --- exhaustion: new_evidence false on both sides ends deep mode --------------
stale = (dig("valuation", "cheap", new_evidence=False),
         dig("valuation", "dear", new_evidence=False))
r = escalation.should_escalate(*stale, mode="deep", round_no=2)
check("deep r2, neither side new → stop", r["escalate"] is False, r)
check("exhaustion reason", "new evidence" in r["reason"], r)

# one side still bringing evidence keeps it alive
r = escalation.should_escalate(dig("valuation", "cheap", new_evidence=True),
                               dig("valuation", "dear", new_evidence=False),
                               mode="deep", round_no=2)
check("deep r2, one side still new → escalate", r["escalate"] is True, r)

# exhaustion is not consulted in round 1 — every side is new there by definition
r = escalation.should_escalate(*stale, mode="standard", round_no=1)
check("round 1 ignores new_evidence", r["escalate"] is True, r)

# --- shape --------------------------------------------------------------------
for r in (escalation.should_escalate(*clash),
          escalation.should_escalate(*stale, mode="deep", round_no=2)):
    check("every result carries the four keys",
          set(r) == {"escalate", "reason", "directive", "gaps"}, r)
check("no directive when not escalating",
      escalation.should_escalate(*clash, mode="standard", round_no=2)["directive"] is None)

check("selftest passes", escalation._selftest() == 0)

summary()
