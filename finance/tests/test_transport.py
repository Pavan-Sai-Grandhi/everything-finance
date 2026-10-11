#!/usr/bin/env python3
"""Offline tests for finance/transport.py — the single HTTP transport."""
import os
import sys
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance import transport
from finance.tests.harness import check, run


def test_host_extraction():
    check("host pulled from a normal url",
          transport._host("https://www.nseindia.com/api/allIndices") == "www.nseindia.com")
    check("host pulled with a port",
          transport._host("http://localhost:8080/x") == "localhost:8080")
    check("a garbage url still yields a label, never an exception",
          isinstance(transport._host("not-a-url"), str))
    check("None is handled", isinstance(transport._host(None), str))


def test_retry_classification():
    check("a DNS failure is transient", 6 in transport._TRANSIENT_EXITS)
    check("a connect failure is transient", 7 in transport._TRANSIENT_EXITS)
    check("a timeout is transient", 28 in transport._TRANSIENT_EXITS)
    check("rate-limit is a transient status", 429 in transport._TRANSIENT_STATUS)
    check("a gateway error is a transient status", 502 in transport._TRANSIENT_STATUS)
    check("403 is NOT retried — retrying a refusal just gets a slower refusal",
          403 not in transport._TRANSIENT_STATUS)
    check("404 is NOT retried", 404 not in transport._TRANSIENT_STATUS)


def test_unresolvable_host_returns_gap():
    with patch.object(transport.subprocess, "run", return_value=SimpleNamespace(
            returncode=6, stdout="000", stderr="fixture DNS failure")):
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


def test_dest_writes_nothing_when_the_fetch_fails():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "annual-report.src")
        with patch.object(transport.subprocess, "run", return_value=SimpleNamespace(
                returncode=6, stdout="000", stderr="fixture DNS failure")):
            body, gap = transport.request("https://nonexistent-host-for-tests.invalid/x",
                                          timeout=5, retries=0, dest=target)
        check("a failed download returns a gap, not the path", body is None and bool(gap),
              gap)
        check("a failed download leaves no file where a caller expects a document",
              not os.path.exists(target), target)


def test_jar_path_uses_the_path_authority():
    p = transport.jar_path("nse")
    check("jar path is absolute", os.path.isabs(p), p)
    check("jar path is under the tmp tier", "tmp" in p, p)
    check("jar name is sanitised", transport.jar_path("a/b c").endswith("a_b_c-cookies.txt"),
          transport.jar_path("a/b c"))


def test_single_user_agent():
    check("a browser UA is defined once here", "Mozilla/5.0" in transport.DEFAULT_UA)
    sources = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "sources")
    for mod in ("market", "prices", "funds", "fundamentals", "news", "filings",
                "documents"):
        src = open(os.path.join(sources, f"{mod}.py")).read()
        check(f"{mod}.py declares no UA of its own", "_UA = (" not in src)



def test_transport_boundary_failures():
    def attempt(**kw):
        try:
            body, gap = transport.request("https://example.com/data", **kw)
            return body is None and bool(gap)
        except Exception:
            return False
    with patch.object(transport.subprocess, "run") as invoke:
        for kw in ({"timeout": None}, {"timeout": float("nan")}, {"timeout": 0},
                   {"retries": -1}, {"retries": 1.5}, {"payload": {1, 2}},
                   {"payload": {"x": float("nan")}}, {"headers": ["bad"]},
                   {"headers": {"X-Test": "bad\r\nInjected: yes"}}):
            check(f"invalid request options degrade: {kw!r}", attempt(**kw))
        check("invalid options never dispatch curl", invoke.call_count == 0)
    with patch.object(transport.tempfile, "mkstemp", side_effect=OSError("fixture disk full")):
        check("temporary-file setup failure becomes a gap", attempt())


def test_http_status_protocol_and_retry():
    calls = []
    statuses = []
    def fake(cmd, **kw):
        calls.append(cmd)
        with open(cmd[cmd.index("-o") + 1], "wb") as out:
            out.write(b"fixture body")
        status = statuses.pop(0)
        return SimpleNamespace(returncode=0, stdout=status, stderr="")
    with patch.object(transport.subprocess, "run", side_effect=fake), \
            patch.object(transport.time, "sleep"):
        for status in ("", "000", "garbage", "junk200", "600"):
            statuses[:] = [status]
            body, gap = transport.request("https://example.com/data", retries=0)
            check(f"invalid HTTP status {status!r} is a gap", body is None and bool(gap))
        statuses[:] = ["503", "200"]
        calls.clear()
        body, gap = transport.request("https://example.com/data", retries=1)
        check("transient HTTP failure retries and returns the successful body",
              body == "fixture body" and gap is None and len(calls) == 2)
        cmd = calls[-1]
        check("curl restricts initial and redirected protocols to HTTP(S)",
              "--proto" in cmd and cmd[cmd.index("--proto") + 1] == "=http,https"
              and "--proto-redir" in cmd
              and cmd[cmd.index("--proto-redir") + 1] == "=http,https")
        statuses[:] = ["403"]
        calls.clear()
        body, gap = transport.request("https://example.com/data", retries=2)
        check("HTTP refusal is not retried", body is None and "403" in gap and len(calls) == 1)
        for url in ("file:///etc/hosts", "https://user:secret@example.com/data"):
            calls.clear()
            try:
                body, gap = transport.request(url, retries=0)
                valid = body is None and bool(gap) and not calls and "secret" not in gap
            except Exception:
                valid = False
            check("unsafe URL is rejected before dispatch without echoing credentials", valid)


def test_binary_publication_preserves_previous_evidence():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        dest = os.path.join(tmp, "report.pdf")
        with open(dest, "wb") as out:
            out.write(b"old report")
        def fake(cmd, **kw):
            with open(cmd[cmd.index("-o") + 1], "wb") as out:
                out.write(b"new report\x00\xff")
            return SimpleNamespace(returncode=0, stdout="200", stderr="")
        with patch.object(transport.subprocess, "run", side_effect=fake):
            with patch.object(transport.os, "replace", side_effect=OSError("fixture write failure")):
                body, gap = transport.request("https://example.com/report", dest=dest)
            check("failed publication returns a gap", body is None and bool(gap))
            with open(dest, "rb") as inp:
                check("failed publication preserves previous complete document", inp.read() == b"old report")
            body, gap = transport.request("https://example.com/report", dest=dest)
            with open(dest, "rb") as inp:
                check("successful publication preserves exact binary bytes",
                      body == dest and gap is None and inp.read() == b"new report\x00\xff")
            check("publication leaves no temporary fragments", os.listdir(tmp) == ["report.pdf"])


def test_redirects_can_be_refused_at_source_boundary():
    with patch.object(transport.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stdout="302", stderr="")) as run_curl:
        body, gap = transport.request("https://www.amfiindia.com/data", follow_redirects=False)
    check("source can refuse unchecked redirects", "-L" not in run_curl.call_args.args[0])
    check("refused redirect is a labelled gap", body is None and "302" in gap, gap)


if __name__ == "__main__":
    run((test_redirects_can_be_refused_at_source_boundary, test_transport_boundary_failures, test_http_status_protocol_and_retry,
         test_binary_publication_preserves_previous_evidence, test_host_extraction, test_retry_classification,
            test_unresolvable_host_returns_gap, test_request_never_raises_on_bad_input,
            test_json_request_labels_non_json,
            test_json_request_passes_through_upstream_gap,
            test_json_request_parses_good_json,
            test_dest_writes_nothing_when_the_fetch_fails,
            test_jar_path_uses_the_path_authority, test_single_user_agent))
