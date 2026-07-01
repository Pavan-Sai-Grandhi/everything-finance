#!/usr/bin/env python3
"""Decide whether `standard` mode runs a second debate round (spec §3).

`standard` runs one round (bull-r1, bear-r1) by default and escalates to round 2
only on *genuine divergence*, defined deterministically from the two round-1
digests each side emits:

  - both sides' top point addresses the **same verdict-relevant axis**, AND
  - each cites a distinct, evidence-tied claim (not a restatement, not a concession).

If the top points talk past each other (different axes), agree, one side conceded,
or a claim is empty → stop at round 1 and go to the PM. This inverts the old
always-two-rounds behaviour: one round is the baseline, a second is opt-in on
evidence. `deep` keeps its own up-to-3-rounds convergence loop and does not use this.

A digest is `{axis, claim, conceded}`. CLI:
  python3 escalation.py --bull bull-r1.json --bear bear-r1.json
  python3 escalation.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
import sys

# The verdict-relevant axes a top point may sit on. A clash only counts when both
# sides land on the *same* one of these — anything else is talking past each other.
VALID_AXES = {
    "valuation",
    "growth_durability",
    "balance_sheet_risk",
    "governance",
    "technical_structure",
}


def _norm(claim):
    """Lowercase, collapse whitespace, strip punctuation — so two phrasings of the
    *same* point read as identical and don't count as a genuine clash."""
    return re.sub(r"[^a-z0-9 ]", "", (claim or "").lower()).strip()


def should_escalate(bull, bear):
    """bull/bear are round-1 digests {axis, claim, conceded}. Returns
    {escalate: bool, reason}."""
    if bull.get("conceded") or bear.get("conceded"):
        return {"escalate": False, "reason": "a side conceded its top point — debate converged"}

    ba, ra = bull.get("axis"), bear.get("axis")
    if ba not in VALID_AXES or ra not in VALID_AXES:
        return {"escalate": False,
                "reason": f"top point on an unrecognised axis ({ba!r}/{ra!r}) — no verdict-relevant clash"}
    if ba != ra:
        return {"escalate": False,
                "reason": f"top points address different axes ({ba} vs {ra}) — talking past each other"}

    bc, rc = _norm(bull.get("claim")), _norm(bear.get("claim"))
    if not bc or not rc:
        return {"escalate": False, "reason": "a side gave no evidence-tied claim — nothing to clash on"}
    if bc == rc:
        return {"escalate": False, "reason": "both sides restate the same point — no genuine divergence"}

    return {"escalate": True,
            "reason": f"genuine divergence on {ba}: distinct evidence-tied claims, no concession"}


def _selftest():
    ok = should_escalate({"axis": "valuation", "claim": "cheap"},
                         {"axis": "valuation", "claim": "fairly priced"})["escalate"] is True
    ok &= should_escalate({"axis": "valuation", "claim": "cheap"},
                          {"axis": "governance", "claim": "pledging"})["escalate"] is False
    print("selftest", "ok" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bull", help="path to bull round-1 digest JSON")
    ap.add_argument("--bear", help="path to bear round-1 digest JSON")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    with open(a.bull) as f:
        bull = json.load(f)
    with open(a.bear) as f:
        bear = json.load(f)
    print(json.dumps(should_escalate(bull, bear)))


if __name__ == "__main__":
    main()
