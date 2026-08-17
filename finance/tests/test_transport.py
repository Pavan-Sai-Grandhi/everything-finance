#!/usr/bin/env python3
"""Offline tests for finance/transport.py — the single HTTP transport.

The contract that matters here is **degrade, never die**: every failure mode must come
back as `(None, "<labelled gap>")` rather than an exception, because every caller in the
plugin treats a gap as data to report and an exception as a crashed skill. These tests
drive the failure modes directly (a curl that cannot run, a non-2xx status, a body that
isn't JSON) rather than mocking around them.

Run: python3 finance/tests/test_transport.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance import transport

_passed = 0
_failed = 0


def check(name, cond, extra=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name} {extra}")


# --- host labelling: gaps must name where the failure happened -------------- #
def test_host_extraction():
    check("host pulled from a normal url",
          transport._host("https://www.nseindia.com/api/allIndices") == "www.nseindia.com")
    check("host pulled with a port",
          transport._host("http://localhost:8080/x") == "localhost:8080")
    check("a garbage url still yields a label, never an exception",
          isinstance(transport._host("not-a-url"), str))
    check("None is handled", isinstance(transport._host(None), str))


# --- retry classification: only transient conditions are retried ------------ #
def test_retry_classification():
    check("a DNS failure is transient", 6 in transport._TRANSIENT_EXITS)
    check("a connect failure is transient", 7 in transport._TRANSIENT_EXITS)
    check("a timeout is transient", 28 in transport._TRANSIENT_EXITS)
    check("rate-limit is a transient status", 429 in transport._TRANSIENT_STATUS)
    check("a gateway error is a transient status", 502 in transport._TRANSIENT_STATUS)
    check("403 is NOT retried — retrying a refusal just gets a slower refusal",
          403 not in transport._TRANSIENT_STATUS)
    check("404 is NOT retried", 404 not in transport._TRANSIENT_STATUS)


# --- degrade-not-die: every failure is a labelled gap, never a raise -------- #
def test_unresolvable_host_returns_gap():
    body, gap = transport.request(
        "https://nonexistent-host-for-tests.invalid/x", timeout=5, retries=0)
    check("a dead host returns no body", body is None)
    check("a dead host returns a labelled gap", isinstance(gap, str) and bool(gap), gap)
    check("the gap names the host", "nonexistent-host-for-tests.invalid" in (gap or ""), gap)


def test_request_never_raises_on_bad_input():
    for bad in (None, "", "::::", "gopher://x"):
        try:
            body, gap = transport.request(bad, timeout=5, retries=0)
            ok = body is None and isinstance(gap, str)
        except Exception as exc:  # noqa: BLE001
            ok = False
            gap = f"raised {exc!r}"
        check(f"malformed url {bad!r} degrades instead of raising", ok, gap)


def test_json_request_labels_non_json():
    """The realistic failure: a site swaps its JSON payload for an HTML block page."""
    orig = transport.request
    transport.request = lambda url, **kw: ("<html>Access Denied</html>", None)
    try:
        parsed, gap = transport.json_request("https://example.com/api")
    finally:
        transport.request = orig
    check("non-JSON body yields no parse", parsed is None)
    check("non-JSON body yields a labelled gap", isinstance(gap, str))
    check("the gap says it was non-JSON", "non-JSON" in (gap or ""), gap)
    check("the gap carries a snippet so you can tell a block page from a bug",
          "Access Denied" in (gap or ""), gap)


def test_json_request_passes_through_upstream_gap():
    orig = transport.request
    transport.request = lambda url, **kw: (None, "example.com: HTTP 403")
    try:
        parsed, gap = transport.json_request("https://example.com/api")
    finally:
        transport.request = orig
    check("an upstream gap is passed through unchanged", gap == "example.com: HTTP 403")
    check("no fabricated payload accompanies a gap", parsed is None)


def test_json_request_parses_good_json():
    orig = transport.request
    transport.request = lambda url, **kw: ('{"a": [1, 2]}', None)
    try:
        parsed, gap = transport.json_request("https://example.com/api")
    finally:
        transport.request = orig
    check("valid JSON parses", parsed == {"a": [1, 2]})
    check("a successful parse carries no gap", gap is None)


# --- cookie jars live in the disposable tier, never hardcoded --------------- #
def test_jar_path_uses_the_path_authority():
    p = transport.jar_path("nse")
    check("jar path is absolute", os.path.isabs(p), p)
    check("jar path is under the tmp tier", "tmp" in p, p)
    check("jar name is sanitised", transport.jar_path("a/b c").endswith("a_b_c-cookies.txt"),
          transport.jar_path("a/b c"))


# --- one UA for the whole plugin ------------------------------------------- #
def test_single_user_agent():
    check("a browser UA is defined once here", "Mozilla/5.0" in transport.DEFAULT_UA)
    sources = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "sources")
    for mod in ("market", "prices", "funds", "fundamentals", "news", "filings"):
        src = open(os.path.join(sources, f"{mod}.py")).read()
        check(f"{mod}.py declares no UA of its own", "_UA = (" not in src)


def main():
    for fn in (test_host_extraction, test_retry_classification,
               test_unresolvable_host_returns_gap, test_request_never_raises_on_bad_input,
               test_json_request_labels_non_json,
               test_json_request_passes_through_upstream_gap,
               test_json_request_parses_good_json, test_jar_path_uses_the_path_authority,
               test_single_user_agent):
        fn()
    print(f"\n{'=' * 48}\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
