#!/usr/bin/env python3
"""Decide whether the bull/bear debate runs another round. One function, both modes.

A debate round costs two agents. This decides, deterministically and identically in
`standard` and `deep`, whether the next one buys anything — from the `debate-block`
digest each side emits, never from the orchestrator's impression of the argument.

## The axis rule

Each side names the **axis** its top point sits on, and both cases escalate:

  - **different axes** — neither side has tested the other, so the round is a
    **cross-examination**: each answers the opponent's axis before restating its own;
  - **same axis, distinct claims** — a real clash; one more round decides which
    claim survives.

## What ends a debate

Concession, repetition, or exhaustion — never non-engagement:

  - a side **conceded** its top point → converged, stop;
  - both sides' claims normalise to the **same string** → restatement, stop;
  - (deep, round > 1) **neither side brought new evidence** → converged, stop;
  - the round cap for the mode is reached → stop.

`new_evidence: false` is a legitimate, debate-ending turn. A side with nothing new
says so; it does not manufacture a point to satisfy the loop.

A digest is `{axis, claim, conceded, new_evidence}`. CLI:
  python3 escalation.py --bull bull-r1.json --bear bear-r1.json [--mode deep --round 2]
  python3 escalation.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
import sys

# The verdict-relevant axes a top point may sit on. Both engagement checks read
# these; an axis outside the set means the digest did not honour its contract.
VALID_AXES = {
    "valuation",
    "growth_durability",
    "balance_sheet_risk",
    "governance",
    "technical_structure",
}

# Rounds a mode will run in total, including round 1.
MAX_ROUNDS = {"standard": 2, "deep": 3}

# What the next round is for. The orchestrator puts this in the round prompt.
CROSS_EXAMINE = ("cross-examine: each side must answer the OPPONENT's axis directly "
                 "before restating its own")
REBUT = "rebut: both sides are on the same axis — attack the opposing claim's evidence"


def _norm(claim):
    """Lowercase, collapse whitespace, strip punctuation — so two phrasings of the
    *same* point read as identical and don't count as a genuine clash."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (claim or "").lower())).strip()


def should_escalate(bull, bear, mode="standard", round_no=1):
    """bull/bear are the round-`round_no` digests {axis, claim, conceded, new_evidence}.

    Returns {escalate, reason, directive, gaps}. `directive` is what the next round is
    for (None when not escalating); `gaps` names any contract violation in the digests.
    """
    cap = MAX_ROUNDS.get(mode, MAX_ROUNDS["standard"])
    stop = lambda reason, gaps=(): {"escalate": False, "reason": reason,
                                    "directive": None, "gaps": list(gaps)}

    if round_no >= cap:
        return stop(f"round {round_no} is the cap for {mode} mode")

    # A side that gave up its top point has nothing left to test, whatever the axes.
    if bull.get("conceded") and bear.get("conceded"):
        return stop("both sides conceded their top point — debate converged")
    if bull.get("conceded"):
        return stop("the bull conceded its top point — debate converged")
    if bear.get("conceded"):
        return stop("the bear conceded its top point — debate converged")

    # Exhaustion. Meaningless in round 1, where both sides are new by definition.
    if round_no > 1:
        bn, rn = bull.get("new_evidence"), bear.get("new_evidence")
        if bn is False and rn is False:
            return stop(f"neither side brought new evidence in round {round_no} — converged")

    ba, ra = bull.get("axis"), bear.get("axis")
    bad = [f"{side} axis {a!r} is not one of {sorted(VALID_AXES)}"
           for side, a in (("bull", ba), ("bear", ra)) if a not in VALID_AXES]
    if bad:
        # Engagement is not assessable, so stop — but as a broken contract, not a
        # converged debate.
        return stop("a digest did not name a valid axis — engagement not assessable", bad)

    bc, rc = _norm(bull.get("claim")), _norm(bear.get("claim"))
    if not bc or not rc:
        missing = [f"{s} gave no evidence-tied claim"
                   for s, c in (("bull", bc), ("bear", rc)) if not c]
        return stop("a side gave no evidence-tied claim — nothing to clash on", missing)

    # Non-engagement — the case that needs the extra round most.
    if ba != ra:
        return {"escalate": True,
                "reason": (f"sides argued different axes ({ba} vs {ra}) — neither has "
                           f"tested the other's case"),
                "directive": CROSS_EXAMINE, "gaps": []}

    # Same axis: distinct claims are a real clash, identical ones a restatement.
    if bc == rc:
        return stop("both sides restate the same point — no genuine divergence")

    return {"escalate": True,
            "reason": f"genuine divergence on {ba}: distinct evidence-tied claims, no concession",
            "directive": REBUT, "gaps": []}


def _selftest():
    # same axis, distinct claims → escalate to rebut
    r = should_escalate({"axis": "valuation", "claim": "cheap"},
                        {"axis": "valuation", "claim": "fairly priced"})
    ok = r["escalate"] is True and r["directive"] == REBUT
    # different axes → escalate to cross-examine (this is the inverted rule)
    r = should_escalate({"axis": "valuation", "claim": "cheap"},
                        {"axis": "governance", "claim": "pledging"})
    ok &= r["escalate"] is True and r["directive"] == CROSS_EXAMINE
    # concession stops it
    ok &= should_escalate({"axis": "valuation", "claim": "cheap", "conceded": True},
                          {"axis": "valuation", "claim": "dear"})["escalate"] is False
    # the cap stops it
    ok &= should_escalate({"axis": "valuation", "claim": "a"},
                          {"axis": "governance", "claim": "b"},
                          mode="deep", round_no=3)["escalate"] is False
    # no new evidence on either side, after round 1, stops it
    ok &= should_escalate({"axis": "valuation", "claim": "a", "new_evidence": False},
                          {"axis": "governance", "claim": "b", "new_evidence": False},
                          mode="deep", round_no=2)["escalate"] is False
    print("selftest", "ok" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bull", help="path to the bull digest JSON for this round")
    ap.add_argument("--bear", help="path to the bear digest JSON for this round")
    ap.add_argument("--mode", default="standard", choices=sorted(MAX_ROUNDS),
                    help="debate mode — sets the round cap (standard 2, deep 3)")
    ap.add_argument("--round", type=int, default=1, dest="round_no",
                    help="the round that just finished")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    with open(a.bull) as f:
        bull = json.load(f)
    with open(a.bear) as f:
        bear = json.load(f)
    print(json.dumps(should_escalate(bull, bear, mode=a.mode, round_no=a.round_no)))


if __name__ == "__main__":
    main()
