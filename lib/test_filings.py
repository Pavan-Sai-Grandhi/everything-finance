#!/usr/bin/env python3
"""Offline tests for the filings classifier + parsing helpers. No network.
Run: python3 skills/filings-watch/scripts/test_filings.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import filings  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


def test_act_on():
    for text in ["Financial Results Q4", "Board Meeting Intimation",
                 "Resignation of Auditor", "Creation of Pledge on shares",
                 "Buyback of equity shares", "SEBI order against the company"]:
        tier, _, _ = filings.classify_materiality(text)
        check(f"act-on: {text[:34]}", tier == "act-on", tier)


def test_monitor():
    for text in ["Investor Meet schedule", "Capex update", "Rating affirmation"]:
        tier, _, _ = filings.classify_materiality(text)
        check(f"monitor: {text[:34]}", tier == "monitor", tier)


def test_routine():
    for text in ["Closure of Trading Window", "ESOP allotment intimation",
                 "Compliance Certificate under Regulation 74(5)"]:
        tier, _, _ = filings.classify_materiality(text)
        check(f"routine: {text[:34]}", tier == "routine", tier)


def test_suppressor_overrides_subject():
    # a newspaper copy of results is routine, not act-on
    tier, _, why = filings.classify_materiality("Newspaper publication of audited results")
    check("newspaper copy suppressed to routine", tier == "routine", f"{tier}/{why}")


def test_default_is_monitor_not_routine():
    tier, _, why = filings.classify_materiality("Wholly novel unmatched corporate event")
    check("unknown defaults to monitor", tier == "monitor", tier)
    check("default flagged for review", "review" in why.lower())


def test_empty_text():
    tier, _, _ = filings.classify_materiality("")
    check("empty -> monitor default (no crash)", tier == "monitor")
    tier, _, _ = filings.classify_materiality(None)
    check("None -> monitor default (no crash)", tier == "monitor")


def test_rows_defensive():
    check("rows reads Table", filings._rows({"Table": [{"a": 1}]}) == [{"a": 1}])
    check("rows reads Table1", filings._rows({"Table1": [{"b": 2}]}) == [{"b": 2}])
    check("rows on garbage -> []", filings._rows("nonsense") == [])
    check("rows on empty -> []", filings._rows({}) == [])


def test_first_picks_present_key():
    row = {"NEWSSUB": "", "HEADLINE": "Real headline", "X": None}
    check("_first skips empty/None, picks present",
          filings._first(row, "NEWSSUB", "HEADLINE") == "Real headline")
    check("_first all-missing -> ''", filings._first(row, "NOPE") == "")


def main():
    for fn in sorted(g for g in globals() if g.startswith("test_")):
        print(f"\n[{fn}]")
        globals()[fn]()
    print(f"\n{'='*48}\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
