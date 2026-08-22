#!/usr/bin/env python3
"""Offline tests for finance/sources/documents.py — the primary-document cache.

No network and no real poppler: the document index and the transport are swapped for
fakes (as in test_filings.py), and `pdftotext` is a stub script placed on PATH, so the
PDF branch is exercised deterministically on any box. Each run gets its own artifacts
root, so a cache hit is a real hit and never a leak from a previous run.

Run: python3 finance/tests/test_documents.py
"""
import json
import os
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance import transport
from finance.sources import documents as dz
from finance.sources import fundamentals
from finance.tests.harness import check, run


AR_URL = "https://www.bseindia.com/bseplus/AnnualReport/FY2025.pdf"
CC_URL = "https://www.example-ir.com/concall/may-2025-transcript.html"

INDEX = {
    "annual_reports": [{"label": "Financial Year 2025", "url": AR_URL},
                       {"label": "Financial Year 2024",
                        "url": "https://www.bseindia.com/bseplus/AnnualReport/FY2024.pdf"}],
    "concalls": [{"label": "May 2025 Transcript", "url": CC_URL}],
}

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
PDF_TEXT = "PAGE 1\nRevenue      1,00,000\nPAT            12,000\n"
HTML_BODY = ("<html><head><style>p{color:red}</style></head><body>"
             "<p>Moderator: Good evening.</p><p>CFO: Margins were 18.4%.</p>"
             "</body></html>")


def _index_of(docs, gaps=None):
    """Fake `fundamentals.fetch` serving just the documents section."""
    def fake(symbol, sections=None, fresh=False):
        return {"ok": True, "source": "screener.in", "fetched_at": "2026-08-21T09:00:00",
                "data": {"symbol": symbol, "documents": docs}, "gaps": list(gaps or [])}
    return fake


def _serve(bodies):
    """Fake `transport.request`: url -> bytes to write at `dest`, or a gap string.

    Returns (fake, calls) so a test can prove the second read never hit the network.
    """
    calls = []

    def fake(url, *, dest=None, **kw):
        calls.append(url)
        payload = bodies.get(url)
        if payload is None or isinstance(payload, str):
            return None, payload or f"{url}: no fixture"
        with open(dest, "wb") as fh:
            fh.write(payload)
        return dest, None
    return fake, calls


def _stub_pdftotext(directory, body=PDF_TEXT, exit_code=0):
    """Put a `pdftotext` on PATH that writes `body` (or fails), and return the new PATH."""
    os.makedirs(directory, exist_ok=True)
    script = os.path.join(directory, "pdftotext")
    with open(script, "w") as fh:
        fh.write("#!/bin/sh\n")
        if exit_code:
            fh.write(f'echo "Error: May not be a PDF file" >&2\nexit {exit_code}\n')
        else:
            # invoked as: pdftotext -layout <src> <txt>; %b so the fixture keeps its newlines
            fh.write(f'printf %b {json.dumps(body)} > "$3"\n')
    os.chmod(script, os.stat(script).st_mode | stat.S_IEXEC)
    return directory


def _harness(fn, docs=INDEX, bodies=None, index_gaps=None, pdftotext=PDF_TEXT,
             pdf_exit=0):
    """Run `fn(call, calls)` against a private artifacts root, fake index and fake wire.

    `call` invokes `documents.fetch`; `calls` accumulates every URL the transport saw.
    """
    bodies = {AR_URL: PDF_BYTES, CC_URL: HTML_BODY.encode()} if bodies is None else bodies
    fake_req, calls = _serve(bodies)
    saved = (fundamentals.fetch, transport.request, os.environ.get("PATH"),
             os.environ.get("EVERYTHING_FINANCE_ARTIFACTS"))
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = os.path.join(tmp, "artifacts")
        binroot = os.path.join(tmp, "bin")
        os.makedirs(binroot, exist_ok=True)
        if pdftotext is not None:
            _stub_pdftotext(binroot, pdftotext, pdf_exit)
        os.environ["PATH"] = binroot
        fundamentals.fetch = _index_of(docs, index_gaps)
        transport.request = fake_req
        try:
            return fn(lambda **kw: dz.fetch("RELIANCE", **kw), calls)
        finally:
            fundamentals.fetch, transport.request = saved[0], saved[1]
            for key, value in (("PATH", saved[2]),
                               ("EVERYTHING_FINANCE_ARTIFACTS", saved[3])):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


ROW_KEYS = {"kind", "label", "url", "publisher", "text_path", "text_chars",
            "text_lines", "extracted_by", "cached"}


# --- cache miss: the first read downloads, converts and writes ---------------- #
def test_cache_miss_downloads_and_converts():
    def body(call, calls):
        env = call()
        check("envelope is the data-spine shape",
              set(env) == {"ok", "source", "fetched_at", "data", "gaps"}, sorted(env))
        check("ok:true when both documents came back", env["ok"] is True, env["gaps"])
        check("no gaps on a clean run", env["gaps"] == [], env["gaps"])
        check("one annual report and one concall by default",
              env["data"]["documents_total"] == 2, env["data"])
        check("the index counts are reported",
              (env["data"]["annual_reports_available"],
               env["data"]["concalls_available"]) == (2, 1), env["data"])
        check("the transport was asked for exactly the two latest documents",
              calls == [AR_URL, CC_URL], calls)
        check("source names screener as the index and the publishers",
              env["source"].startswith("screener.in (document index) + ")
              and "www.bseindia.com" in env["source"], env["source"])
        for row in env["data"]["documents"]:
            check(f"{row['kind']} row carries exactly the contract keys",
                  set(row) == ROW_KEYS, sorted(row))
            check(f"{row['kind']} text_path exists on disk",
                  os.path.isfile(row["text_path"]), row["text_path"])
            check(f"{row['kind']} row is marked not-cached on the first read",
                  row["cached"] is False)
            check(f"{row['kind']} char and line counts match the file",
                  (row["text_chars"], row["text_lines"])
                  == dz._measure(row["text_path"]), row)
        ar = env["data"]["documents"][0]
        check("the annual report is tagged annual_report", ar["kind"] == "annual_report")
        check("the annual report kept its index label",
              ar["label"] == "Financial Year 2025", ar)
        check("the publisher is the document host, not screener",
              ar["publisher"] == "www.bseindia.com", ar)
        check("the concall HTML was stripped to text",
              "Margins were 18.4%" in open(env["data"]["documents"][1]["text_path"]).read())
        check("script/style never survive the strip",
              "color:red" not in open(env["data"]["documents"][1]["text_path"]).read())
    _harness(body)


# --- cache hit: the second read is served entirely from disk ------------------ #
def test_cache_hit_serves_from_disk():
    def body(call, calls):
        first = call()
        before = list(calls)
        second = call()
        check("a repeat read makes no further network call", calls == before, calls)
        check("a cache hit returns the same paths",
              [r["text_path"] for r in second["data"]["documents"]]
              == [r["text_path"] for r in first["data"]["documents"]])
        check("a cache hit is flagged as cached",
              all(r["cached"] is True for r in second["data"]["documents"]),
              second["data"]["documents"])
        check("a cache hit is still ok:true with no gap",
              second["ok"] is True and second["gaps"] == [], second["gaps"])
        check("a cache hit carries the same counts",
              [r["text_chars"] for r in second["data"]["documents"]]
              == [r["text_chars"] for r in first["data"]["documents"]])
        check("a cache hit row still carries exactly the contract keys",
              all(set(r) == ROW_KEYS for r in second["data"]["documents"]))
        third = call(fresh=True)
        check("fresh=True re-downloads", len(calls) == len(before) + 2, calls)
        check("a fresh read is flagged not-cached",
              all(r["cached"] is False for r in third["data"]["documents"]))
    _harness(body)


# --- pdftotext: the fallback for anything that is not already text ------------ #
def test_pdftotext_fallback():
    def body(call, calls):
        env = call(concalls=0)
        row = env["data"]["documents"][0]
        check("a PDF is converted by pdftotext", row["extracted_by"] == "pdftotext", row)
        check("the converted text lands on disk",
              open(row["text_path"]).read() == PDF_TEXT)
        check("concalls=0 pulls no concall", env["data"]["documents_total"] == 1, env["data"])
        check("an unread section is still counted in the index",
              env["data"]["concalls_available"] == 1, env["data"])
        check("HTML skips pdftotext entirely",
              call(annual_reports=0)["data"]["documents"][0]["extracted_by"] == "html")
    _harness(body)


def test_pdftotext_missing_is_a_labelled_gap():
    def body(call, calls):
        env = call(concalls=0)
        check("a PDF with no pdftotext yields no document",
              env["data"]["documents"] == [] and env["ok"] is False, env["data"])
        check("the gap names the document and the missing tool",
              any("Financial Year 2025" in g and "pdftotext" in g for g in env["gaps"]),
              env["gaps"])
        check("the gap says how to fix it",
              any("poppler" in g for g in env["gaps"]), env["gaps"])
    _harness(body, pdftotext=None)


def test_pdftotext_failure_does_not_abort_the_other_document():
    def body(call, calls):
        env = call()
        check("the failing PDF is a labelled gap naming its exit",
              any("Financial Year 2025" in g and "exit 1" in g for g in env["gaps"]),
              env["gaps"])
        check("the concall still came back",
              env["data"]["documents_total"] == 1
              and env["data"]["documents"][0]["kind"] == "concall", env["data"])
        check("a partial result is still ok:true", env["ok"] is True)
    _harness(body, pdf_exit=1)


# --- fetch failure: labelled gap, never an abort ------------------------------ #
def test_fetch_failure_is_a_labelled_gap():
    def body(call, calls):
        env = call()
        check("a blocked download yields no row for that document",
              env["data"]["documents_total"] == 1, env["data"])
        check("the gap names the document and the transport reason",
              any("Financial Year 2025" in g and "HTTP 403" in g for g in env["gaps"]),
              env["gaps"])
        check("the other document is unaffected",
              env["data"]["documents"][0]["kind"] == "concall", env["data"])
        check("a partial result is ok:true, not a failure", env["ok"] is True)
    _harness(body, bodies={AR_URL: "www.bseindia.com: HTTP 403",
                           CC_URL: HTML_BODY.encode()})


def test_every_document_failing_is_ok_false():
    def body(call, calls):
        env = call()
        check("nothing fetched is ok:false", env["ok"] is False)
        check("both failures are labelled", len(env["gaps"]) == 2, env["gaps"])
        check("no fabricated rows accompany a total failure",
              env["data"]["documents"] == [] and env["data"]["documents_total"] == 0)
    _harness(body, bodies={AR_URL: "www.bseindia.com: HTTP 403",
                           CC_URL: "www.example-ir.com: timed out after 120s"})


def test_empty_index_is_a_labelled_gap():
    def body(call, calls):
        env = call()
        check("an empty index is ok:false", env["ok"] is False)
        check("the missing sections are both named",
              any("annual reports" in g for g in env["gaps"])
              and any("concalls" in g for g in env["gaps"]), env["gaps"])
        check("nothing was fetched", calls == [], calls)
    _harness(body, docs={"annual_reports": [], "concalls": []})


def test_index_gaps_are_carried_through():
    def body(call, calls):
        env = call()
        check("a gap from the document index is prefixed and kept",
              "document index: consolidated page: HTTP 403" in env["gaps"], env["gaps"])
    _harness(body, index_gaps=["consolidated page: HTTP 403"])


def test_scanned_pdf_yielding_no_text_is_a_gap():
    def body(call, calls):
        env = call(concalls=0)
        check("an empty conversion is not passed off as a document",
              env["data"]["documents"] == [], env["data"])
        check("the gap says the PDF is an image, not text",
              any("scanned image" in g for g in env["gaps"]), env["gaps"])
    _harness(body, pdftotext="")


# --- R3: extraction only, and paths only -------------------------------------- #
def test_no_document_text_is_ever_returned_inline():
    def body(call, calls):
        env = call()
        blob = json.dumps(env, ensure_ascii=False)
        for fragment in ("Moderator: Good evening", "Margins were 18.4%",
                         "Revenue      1,00,000", "%PDF-"):
            check(f"the envelope carries no document text: {fragment[:24]!r}",
                  fragment not in blob, blob[:200])
        check("every row value is small — a label, a count or a path",
              all(len(str(v)) < 400 for r in env["data"]["documents"] for v in r.values()),
              env["data"]["documents"])
        check("no row carries a summary, score or verdict",
              not (ROW_KEYS & {"summary", "score", "verdict", "highlights", "text"}))
    _harness(body)


# --- the cache is content-addressed on the URL -------------------------------- #
def test_cache_key_is_the_url():
    check("the same URL keys the same cache entry",
          dz._key(AR_URL) == dz._key(AR_URL))
    check("a different URL keys a different entry", dz._key(AR_URL) != dz._key(CC_URL))
    check("the key is a filesystem-safe hex digest",
          dz._key(AR_URL).isalnum() and len(dz._key(AR_URL)) == 20, dz._key(AR_URL))

    def body(call, calls):
        env = call()
        for row in env["data"]["documents"]:
            check(f"{row['kind']} text is cached under the URL key, in the cache tier",
                  os.path.basename(row["text_path"]) == dz._key(row["url"]) + ".txt"
                  and os.sep + "cache" + os.sep in row["text_path"], row["text_path"])
    _harness(body)


# --- M5: the raw .src is dropped once its text is extracted ------------------- #
def test_raw_source_deleted_after_conversion():
    def body(call, calls):
        env = call()
        for row in env["data"]["documents"]:
            src, txt, meta = dz._cache_paths(row["url"])
            check(f"{row['kind']}: the extracted .txt is kept",
                  os.path.isfile(txt), txt)
            check(f"{row['kind']}: the raw .src download is deleted after conversion",
                  not os.path.isfile(src), src)
    _harness(body)


# --- M6: the latest is chosen by the year in the label, not by list position --- #
AR_OLD = "https://www.bseindia.com/bseplus/AnnualReport/FY2024.pdf"
AR_NEW = "https://www.bseindia.com/bseplus/AnnualReport/FY2026.pdf"


def test_label_recency_parses_year_and_quarter():
    check("a year is parsed from an annual-report label",
          dz._label_recency("Financial Year 2026 from bse") == (2026, 0))
    check("a quarter and year are parsed from a concall label",
          dz._label_recency("Q3 2025 Transcript") == (2025, 3))
    check("the latest year in the label wins",
          dz._label_recency("Annual Report 2023 (filed 2026)") == (2026, 0))
    check("a label with no year has no recency", dz._label_recency("Annual Report") is None)


def test_out_of_order_index_returns_the_true_latest():
    # index head is the OLDER report; the newest by label-year must still be chosen.
    docs = {"annual_reports": [{"label": "Financial Year 2024", "url": AR_OLD},
                               {"label": "Financial Year 2026", "url": AR_NEW}],
            "concalls": []}

    def body(call, calls):
        env = call(concalls=0)
        check("the newest annual report by label-year is picked, not the list head",
              env["data"]["documents"][0]["label"] == "Financial Year 2026",
              env["data"]["documents"])
        check("only the true-latest document was downloaded", calls == [AR_NEW], calls)
    _harness(body, docs=docs, bodies={AR_OLD: PDF_BYTES, AR_NEW: PDF_BYTES})


def test_undated_label_is_a_gap_not_a_silent_miscite():
    docs = {"annual_reports": [{"label": "Annual Report", "url": AR_URL}], "concalls": []}

    def body(call, calls):
        env = call(concalls=0)
        check("an undated cited document raises a labelled gap",
              any("no year" in g and "list position" in g for g in env["gaps"]), env["gaps"])
        check("the document still comes back on the DOM-order fallback",
              env["data"]["documents_total"] == 1, env["data"])
    _harness(body, docs=docs, bodies={AR_URL: PDF_BYTES})


if __name__ == "__main__":
    run(globals())
