#!/usr/bin/env python3
"""Offline tests for the filings classifier + parsing helpers. No network."""
import os
import sys
from unittest.mock import patch

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


SHP_ROWS = [{"symbol": "RELIANCE", "date": "30-Jun-2026", "pr_and_prgrp": "50.5", "public_val": "49.5",
             "employeeTrusts": "0.0", "submissionDate": "15-Jul-2026", "xbrl": "u"}]
CA_ROWS = [{"symbol": "RELIANCE", "subject": "Dividend - Rs 10 per share",
            "exDate": "10-Aug-2026", "recDate": "11-Aug-2026", "series": "EQ",
            "isin": "INE002A01018"}]


def test_shareholding_envelope():
    env = _swapped(_serve({"share-holdings-master": (SHP_ROWS, None),
                           "pledgedata": ([{"symbol": "RELIANCE", "x": 1}], None)}),
                   lambda: filings.shareholding("reliance", quarters=4))
    check("shareholding returns the data-spine envelope",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"}, sorted(env))
    check("shareholding ok:true with quarters", env["ok"] is True)
    check("shareholding source is NSE", env["source"] == "NSE")
    check("shareholding echoes the symbol as given", env["data"]["symbol"] == "reliance")
    check("shareholding carries the parsed quarters",
          env["data"]["quarters"][0]["promoter_pct"] == 50.5, env["data"]["quarters"])
    check("shareholding carries the pledge rows", env["data"]["pledge"] == [{"symbol": "RELIANCE", "x": 1}])
    check("shareholding with pledge rows reports no gap", env["gaps"] == [], env["gaps"])


def test_shareholding_empty_pledge_is_unknown_not_nil():
    env = _swapped(_serve({"share-holdings-master": (SHP_ROWS, None),
                           "pledgedata": ([], None)}),
                   lambda: filings.shareholding("RELIANCE"))
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



def _pledge_xml(flag=None, fields=None):
    tags = []
    if flag is not None:
        tags.append(f"<p:{filings._PLEDGE_FLAG}>{flag}</p:{filings._PLEDGE_FLAG}>")
    for key, value in (fields or {}).items():
        tag = filings._PLEDGE_TAGS[key]
        tags.append(f"<p:{tag}>{value}</p:{tag}>")
    return '<xbrl xmlns:p="urn:fixture">' + ''.join(tags) + '</xbrl>'


def test_pledge_unknown_never_becomes_zero():
    url = "https://nsearchives.nseindia.com/fixture.xml"
    for value in ("unknown", "", "N/A"):
        with patch.object(filings.transport, "request", return_value=(_pledge_xml(value), None)):
            result = filings.pledge_from_xbrl(url)
        check("unrecognized boolean cannot mean no pledge",
              result is None or (result["declared"] is None and result["pledged_pct"] is None), result)
    for value in ("false", "0"):
        with patch.object(filings.transport, "request", return_value=(_pledge_xml(value), None)):
            result = filings.pledge_from_xbrl(url)
        check("explicit XML false confirms no pledged shares",
              result["declared"] is False and result["pledged_pct"] == 0)
        check("no pledge does not prove absence of other encumbrances",
              result["encumbered_pct"] is None and result["encumbered_shares"] is None, result)
    with patch.object(filings.transport, "request", return_value=(_pledge_xml("1", {"pledged_pct": .25}), None)):
        result = filings.pledge_from_xbrl(url)
    check("XML numeric true and filed fraction are parsed", result["declared"] is True and result["pledged_pct"] == 25)
    for body in ("<html>Access denied</html>", "<broken", '<xbrl xmlns:p="urn:fixture"/>'):
        with patch.object(filings.transport, "request", return_value=(body, None)):
            result = filings.pledge_from_xbrl(url)
        check("unreadable or unrelated document provides no pledge summary", result is None, result)


def test_pledge_invalid_and_conflicting_facts():
    url = "https://nsearchives.nseindia.com/fixture.xml"
    for value in (-.1, 1.5, "NaN"):
        with patch.object(filings.transport, "request", return_value=(_pledge_xml("true", {"pledged_pct": value}), None)):
            result = filings.pledge_from_xbrl(url)
        check("invalid fraction stays unknown with a gap",
              result["pledged_pct"] is None and bool(result.get("gaps")), result)
    with patch.object(filings.transport, "request", return_value=(_pledge_xml("false", {"pledged_pct": .25}), None)):
        result = filings.pledge_from_xbrl(url)
    check("contradictory declaration cannot certify no pledge", result["declared"] is None and bool(result.get("gaps")), result)
    xml = _pledge_xml("true", {"pledged_pct": .25})
    tag = filings._PLEDGE_TAGS["pledged_pct"]
    xml = xml.replace('</xbrl>', f'<p:{tag} contextRef="other">0.5</p:{tag}></xbrl>')
    with patch.object(filings.transport, "request", return_value=(xml, None)):
        result = filings.pledge_from_xbrl(url)
    check("conflicting XBRL contexts are not selected by document order",
          result["pledged_pct"] is None and bool(result.get("gaps")), result)



def test_every_exchange_endpoint_scopes_rows_before_selection():
    target = "M&M"
    foreign = dict(SHP_ROWS[0], symbol="FOREIGN", xbrl="https://nsearchives.nseindia.com/foreign.xml")
    wanted = dict(SHP_ROWS[0], symbol=target, xbrl="https://nsearchives.nseindia.com/wanted.xml")
    missing = dict(SHP_ROWS[0]); missing.pop("symbol")
    rows = [foreign, missing, wanted]
    with patch.object(filings, "_nse_json", return_value=(rows, None)), \
            patch.object(filings, "pledge_from_xbrl", return_value=None) as xbrl:
        result = filings.fetch_nse_shareholding(target, quarters=1)
    check("shareholding filters identity before limiting quarters",
          len(result["items"]) == 1 and result["items"][0]["xbrl"] == wanted["xbrl"], result)
    check("only the requested company's XBRL is read", xbrl.call_args.args == (wanted["xbrl"],))
    check("pledge rows also require the requested symbol",
          len(result["pledge"]) == 1 and result["pledge"][0]["symbol"] == target, result)
    check("discarded or unidentified exchange rows are visible as gaps", bool(result["gap"]))
    for endpoint, row in ((filings.fetch_nse_announcements, {"attchmntText": "Results", "an_dt": "01-Sep-2026"}),
                          (filings.fetch_nse_corp_actions, {"subject": "Dividend"})):
        with patch.object(filings, "_nse_json", return_value=([row, dict(row, symbol="FOREIGN"), dict(row, symbol=target)], None)) as request:
            result = endpoint(target)
        check("exchange rows with unknown or foreign identity are excluded", len(result["items"]) == 1, result)
        check("dropped rows are labelled even when some data survives", bool(result["gap"]))
        check("NSE symbols containing ampersands are encoded in the request", "symbol=M%26M" in request.call_args.args[0])


def test_distinct_same_day_filings_keep_separate_identities():
    common = {'date': '2026-09-01', 'headline': 'Results announcement ' + 'x' * 90}
    first = dict(common, attachment='https://nsearchives.nseindia.com/first.pdf')
    second = dict(common, attachment='https://nsearchives.nseindia.com/second.pdf')
    items = filings._dedupe([first, second, dict(first)])
    check('separate attachments survive identical headline prefixes', len(items) == 2)
    identifiers = [item.get('filing_id') for item in items]
    check('distinct filings carry distinct stable IDs',
          len(identifiers) == 2 and all(identifiers) and len(set(identifiers)) == 2)
    again = filings._dedupe([dict(first)])
    check('repeat filing keeps its alert identity', bool(again[0].get('filing_id'))
          and again[0].get('filing_id') == items[0].get('filing_id'))
    check('deduplication does not mutate source rows', 'filing_id' not in first)
    third = dict(common, headline=common['headline'] + ' correction', attachment='')
    fourth = dict(common, headline=common['headline'] + ' original', attachment='')
    check('full headlines distinguish filings without attachments', len(filings._dedupe([third, fourth])) == 2)


def test_long_headlines_preserve_distinct_filing_evidence():
    prefix = 'Results ' + 'x' * 250
    rows = [{'symbol': 'TEST', 'attchmntText': prefix + suffix,
             'an_dt': '01-Sep-2026'} for suffix in (' original', ' correction')]
    with patch.object(filings, '_nse_json', return_value=(rows, None)):
        result = filings.fetch_nse_announcements('TEST')
    check('announcement parser preserves complete disclosure text',
          result['items'][0]['headline'] == prefix + ' original')
    check('headlines differing after display length retain separate identities',
          len(filings._dedupe(result['items'])) == 2)


def test_invalid_summary_request_refuses_before_cache_or_network():
    for symbol, days in (('../escape', 30), ('', 30), (None, 30), ('TEST', -1),
                         ('TEST', True), ('TEST', 1.5), ('TEST', '30'), ('TEST', 10**20)):
        with patch.object(filings.paths, 'cache_dir') as cache, patch.object(filings, 'fetch_nse_announcements') as fetch, patch.object(filings, 'fetch_nse_corp_actions', return_value={'items': [], 'gap': None}):
            try:
                result = filings.summarize(symbol, days=days)
                rejected = not result['ok'] and bool(result['gaps'])
            except Exception:
                rejected = False
        check('invalid filing request has no cache or network side effects',
              rejected and not cache.called and not fetch.called, (symbol, days))


def test_summary_cache_reuse_and_failed_refresh_preserves_snapshot():
    import tempfile
    from pathlib import Path
    item = {'date': '2026-09-01', 'headline': 'Results', 'attachment': 'fixture', 'tier': 'act-on'}
    with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'EVERYTHING_FINANCE_ARTIFACTS': root}), patch.object(filings, 'fetch_nse_announcements', return_value={'items': [item], 'gap': None}) as fetch, patch.object(filings, 'fetch_nse_corp_actions', return_value={'items': [], 'gap': None}):
        first = filings.summarize('TEST')
        again = filings.summarize('TEST')
        check('same-day cache reuses complete filing evidence', fetch.call_count == 1 and first == again)
        cache = next(Path(root).rglob('v3_TEST_30.json'))
        original = cache.read_bytes()
        with patch.object(filings.spine.os, 'replace', side_effect=OSError('fixture failure')):
            refreshed = filings.summarize('TEST', fresh=True)
        check('cache publication failure preserves prior snapshot and usable result',
              refreshed['ok'] and cache.read_bytes() == original)
        check('cache publication failure leaves no pending file',
              list(cache.parent.iterdir()) == [cache])


def test_shareholding_orders_quarters_and_bounds_xbrl_fetch():
    old = dict(SHP_ROWS[0], date="31-Dec-2025", pr_and_prgrp="55.0",
               xbrl="https://nsearchives.nseindia.com/old.xml")
    new = dict(SHP_ROWS[0], date="30-Jun-2026", pr_and_prgrp="50.5",
               xbrl="https://nsearchives.nseindia.com/new.xml")
    mid = dict(SHP_ROWS[0], date="31-Mar-2026", pr_and_prgrp="52.0",
               xbrl="https://nsearchives.nseindia.com/mid.xml")
    with patch.object(filings, "_nse_json", return_value=([old, new, mid], None)), \
            patch.object(filings, "pledge_from_xbrl", return_value=None) as xbrl:
        result = filings.fetch_nse_shareholding("RELIANCE", quarters=2)
    check("quarters are newest first regardless of payload order",
          [q["quarter"] for q in result["items"]] == ["2026-06-30", "2026-03-31"], result["items"])
    check("the pledge is read from the latest quarter's filing",
          xbrl.call_args.args == (new["xbrl"],), xbrl.call_args)
    calls = []
    with patch.object(filings.transport, "request",
                      side_effect=lambda *a, **k: calls.append(a[0]) or ("", "x")):
        for url in ("https://evil.example/x.xml", "http://nsearchives.nseindia.com/x.xml",
                    "https://nseindia.com.evil.example/x.xml", "file:///etc/passwd", "u"):
            check(f"XBRL outside NSE is not fetched: {url}", filings.pledge_from_xbrl(url) is None)
    check("no off-source XBRL reached transport", calls == [], calls)
    with patch.object(filings, "_nse_json", side_effect=AssertionError("network")) as net:
        for bad in (0, -1, 1.5, True, "4"):
            try:
                env = filings.shareholding("RELIANCE", quarters=bad)
            except AssertionError:
                env = {"ok": None, "gaps": []}
            check(f"invalid quarters {bad!r} is a labelled gap",
                  env["ok"] is False and any("quarters" in g for g in env["gaps"]), env)
    check("invalid quarters never reach NSE", not net.called)


if __name__ == "__main__":
    run(globals())
