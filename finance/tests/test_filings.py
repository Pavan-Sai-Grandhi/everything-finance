#!/usr/bin/env python3
"""Offline tests for the filings classifier + parsing helpers. No network.
Run: python3 finance/tests/test_filings.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.sources import filings
from finance.tests.harness import check, run


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


def _serve(payloads):
    """Fake `_nse_json`: url substring -> (rows, gap). Anything unmatched serves nothing."""
    def fake(url, referer):
        for key, result in payloads.items():
            if key in url:
                return result
        return [], None
    return fake


def _swapped(fake, fn):
    orig = filings._nse_json
    filings._nse_json = fake
    try:
        return fn()
    finally:
        filings._nse_json = orig


SHP_ROWS = [{"date": "30-Jun-2026", "pr_and_prgrp": "50.5", "public_val": "49.5",
             "employeeTrusts": "0.0", "submissionDate": "15-Jul-2026", "xbrl": "u"}]
CA_ROWS = [{"symbol": "RELIANCE", "subject": "Dividend - Rs 10 per share",
            "exDate": "10-Aug-2026", "recDate": "11-Aug-2026", "series": "EQ",
            "isin": "INE002A01018"}]


def test_shareholding_envelope():
    env = _swapped(_serve({"share-holdings-master": (SHP_ROWS, None),
                           "pledgedata": ([{"x": 1}], None)}),
                   lambda: filings.shareholding("reliance", quarters=4))
    check("shareholding returns the data-spine envelope",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"}, sorted(env))
    check("shareholding ok:true with quarters", env["ok"] is True)
    check("shareholding source is NSE", env["source"] == "NSE")
    check("shareholding echoes the symbol as given", env["data"]["symbol"] == "reliance")
    check("shareholding carries the parsed quarters",
          env["data"]["quarters"][0]["promoter_pct"] == 50.5, env["data"]["quarters"])
    check("shareholding carries the pledge rows", env["data"]["pledge"] == [{"x": 1}])
    check("shareholding with pledge rows reports no gap", env["gaps"] == [], env["gaps"])


def test_shareholding_empty_pledge_is_unknown_not_nil():
    env = _swapped(_serve({"share-holdings-master": (SHP_ROWS, None),
                           "pledgedata": ([], None)}),
                   lambda: filings.shareholding("VEDL"))
    check("an empty pledge list is a labelled gap, never 'no pledge'",
          any("UNKNOWN" in g for g in env["gaps"]), env["gaps"])
    check("an empty pledge list still returns the quarters", env["ok"] is True)


def test_shareholding_blocked_degrades():
    env = _swapped(_serve({"share-holdings-master": ([], "HTTP 403")}),
                   lambda: filings.shareholding("RELIANCE"))
    check("shareholding blocked is ok:false", env["ok"] is False)
    check("shareholding blocked names the gap",
          any("NSE shareholding" in g for g in env["gaps"]), env["gaps"])
    check("shareholding blocked returns no quarters, never a partial lie",
          env["data"]["quarters"] == [] and env["data"]["pledge"] == [], env["data"])


def test_corporate_actions_envelope():
    env = _swapped(_serve({"corporateActions": (CA_ROWS, None)}),
                   lambda: filings.corporate_actions("RELIANCE"))
    check("corporate_actions returns the data-spine envelope",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"}, sorted(env))
    check("corporate_actions ok:true with rows", env["ok"] is True)
    # NSE serves DD-Mon-YYYY; everything this plugin emits is ISO, so filings, news and
    # candles can be compared and sorted against each other.
    row = env["data"]["corporate_actions"][0]
    check("corporate_actions normalises ex/record dates to ISO",
          (row["ex_date"], row["record_date"]) == ("2026-08-10", "2026-08-11"), row)
    check("corporate_actions reports no gap when rows came back", env["gaps"] == [])


def test_corporate_actions_none_is_a_labelled_gap():
    env = _swapped(_serve({"corporateActions": ([], None)}),
                   lambda: filings.corporate_actions("RELIANCE"))
    check("no corporate actions is ok:false with a gap",
          env["ok"] is False and env["gaps"] == ["no forthcoming corporate actions"],
          env["gaps"])


if __name__ == "__main__":
    run(globals())
