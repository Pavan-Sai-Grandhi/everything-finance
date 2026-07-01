#!/usr/bin/env python3
"""Offline tests for the standard-mode round-1 → round-2 escalation rule. No
network. Run: python3 skills/deep-analysis/scripts/test_escalation.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import escalation  # noqa: E402

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


def dig(axis, claim, conceded=False):
    return {"axis": axis, "claim": claim, "conceded": conceded}


# same axis, distinct evidence-tied claims, neither conceded → escalate
r = escalation.should_escalate(
    dig("valuation", "trades at 18x vs peer median 28x — cheap"),
    dig("valuation", "18x is fair given decelerating EPS growth"))
check("same-axis clash → escalate", r["escalate"] is True, r)

# top points address different axes (talk past each other) → stop
r = escalation.should_escalate(
    dig("valuation", "cheap vs peers"),
    dig("balance_sheet_risk", "D/E 1.8, interest cover 2.1"))
check("different axes → stop", r["escalate"] is False, r)
check("different-axes reason", "different axes" in r["reason"].lower(), r)

# one side conceded → stop
r = escalation.should_escalate(
    dig("growth_durability", "order book covers 3 years"),
    dig("growth_durability", "agreed, growth visibility is real", conceded=True))
check("a concession → stop", r["escalate"] is False, r)
check("concession reason", "conced" in r["reason"].lower(), r)

# same axis but the claims are the same point restated → stop (no genuine clash)
r = escalation.should_escalate(
    dig("governance", "promoter pledging at 40%"),
    dig("governance", "promoter pledging at 40%"))
check("restated identical claim → stop", r["escalate"] is False, r)

# an unrecognised axis can't establish a verdict-relevant clash → stop
r = escalation.should_escalate(
    dig("vibes", "feels expensive"),
    dig("vibes", "feels cheap"))
check("unrecognised axis → stop", r["escalate"] is False, r)

# an empty claim on one side → stop (nothing to clash on)
r = escalation.should_escalate(
    dig("technical_structure", "broke 200-DMA on volume"),
    dig("technical_structure", ""))
check("empty claim → stop", r["escalate"] is False, r)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
