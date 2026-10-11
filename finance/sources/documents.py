#!/usr/bin/env python3
"""Document fetch — a company's annual report and concall as cached local text.

screener.in's `#documents` section is the index; the documents themselves are published by
BSE, NSE and the company's own investor-relations host. Each document is downloaded once,
converted to text and kept under a URL-addressed cache key, so every leg that cites a
filing reads the same primary text off disk.

Extraction only: nothing here summarises, scores or judges — that is the reading leg's job.
The envelope carries **paths**, never document body text.

Returns the shared data-spine envelope (finance/contracts.md). Reached through get_documents.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import tempfile
from html import unescape
from urllib.parse import urlsplit

from finance import spine
from finance import paths
from finance import transport
from finance.sources import fundamentals
from finance.spine import envelope as _envelope, norm_symbol as _norm


# An annual report runs to hundreds of pages; a slow BSE host must not be mistaken for a
# dead one, and pdftotext on a 40 MB scan is not quick either.
_DOWNLOAD_TIMEOUT = 120
_CONVERT_TIMEOUT = 180

# index section -> the `kind` a row is tagged with.
_KINDS = {"annual_reports": "annual_report", "concalls": "concall"}

_DROP_RE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.I | re.S)
_BLOCK_RE = re.compile(r"</(p|div|tr|li|h[1-6]|table|section|br)\s*/?>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")

_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_QUARTER_RE = re.compile(r"\bQ([1-4])\b", re.I)
_REPORT_YEAR_RE = re.compile(
    r"\b(?:annual\s+report|financial\s+year|FY)\s*(?:for\s+)?"
    r"((?:19|20)\d{2})(?:\s*[-/–]\s*((?:19|20)\d{2}|\d{2}))?\b", re.I)


def _label_recency(label):
    """(year, quarter) parsed from a document label, for a newest-first sort; None when the
    label carries no 4-digit year. Annual reports name a year ("Financial Year 2026");
    concalls add a quarter ("Q1 2026 Transcript"). A stated annual period takes
    precedence over incidental filing dates; otherwise multiple years are ambiguous."""
    label = label or ""
    period = _REPORT_YEAR_RE.search(label)
    if period:
        year = int(period.group(1))
        if period.group(2):
            end = period.group(2)
            end_year = int(end) if len(end) == 4 else year // 100 * 100 + int(end)
            if len(end) == 2 and end_year < year:
                end_year += 100
            if end_year not in (year, year + 1):
                return None
            year = end_year
        return year, 0
    years = set(_YEAR_RE.findall(label))
    if len(years) != 1:
        return None
    q = _QUARTER_RE.search(label)
    return int(next(iter(years))), (int(q.group(1)) if q else 0)


def _order_newest_first(found, section, wanted, gaps):
    """Order a section's index entries newest-first by the year+quarter in each label,
    not by DOM position — screener's list order is not a guaranteed date order. Entries
    with no parseable year keep DOM order behind the dated ones; if such an entry lands in
    the cited head, raise a gap saying its recency is a list-position guess, not a date."""
    dated, undated = [], []
    for i, link in enumerate(found):
        rec = _label_recency(link.get("label"))
        (undated if rec is None else dated).append((rec, i, link))
    dated.sort(key=lambda t: (-t[0][0], -t[0][1], t[1]))
    ordered = [t[2] for t in dated] + [t[2] for t in undated]
    undated_ids = {id(t[2]) for t in undated}
    for link in ordered[:max(0, int(wanted or 0))]:
        if id(link) in undated_ids:
            label = (link.get("label") or "").strip() or section
            gaps.append(f"{label}: no year or ambiguous reporting period in the label — ordered by list position, not date")
    return ordered


def _key(url):
    """URL identity for the current snapshot pointer; content may change on refresh."""
    return hashlib.sha256(str(url).encode("utf-8")).hexdigest()[:20]


def _cache_paths(url):
    """(downloaded source, extracted text, row metadata) for one document URL."""
    base = os.path.join(paths.cache_dir("documents"), _key(url))
    return base + ".src", base + ".txt", base + ".json"


def _html_to_text(raw):
    """HTML to plain text with block breaks kept — a document's line structure carries
    meaning that a whitespace-collapsing strip would flatten away."""
    text = _TAG_RE.sub("", _BLOCK_RE.sub("\n", _DROP_RE.sub(" ", raw)))
    text = re.sub(r"[ \t\u00a0]+", " ", unescape(text))
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()


def _to_text(src_path, txt_path, expected_pdf=False):
    """Convert a downloaded document to text at `txt_path`. Returns `(method, gap)`.

    Text and HTML are stripped in process; anything else goes to `pdftotext -layout`,
    whose layout mode keeps the column alignment that annual-report tables depend on.
    """
    try:
        with open(src_path, "rb") as fh:
            head = fh.read(5)
    except OSError as exc:
        return None, f"could not read the download ({exc})"

    if head != b"%PDF-":
        if expected_pdf:
            return None, "expected a PDF but received a different format (possibly an access or error page)"
        try:
            with open(src_path, encoding="utf-8-sig") as fh:
                raw = fh.read()
            if any(ord(char) < 32 and char not in "\t\n\r\f" for char in raw):
                return None, "download contains binary/control bytes, not readable document text"
            title = re.search(r"<title\b[^>]*>(.*?)</title\s*>",raw,re.I|re.S)
            if title:
                heading = _html_to_text(title.group(1)).strip().lower().rstrip(".! ")
                if heading in {"access denied", "forbidden", "just a moment", "attention required", "service unavailable", "404 not found", "sign in", "login"}:
                    return None, "download is an access, login or error page, not the requested document"
            text, method = ((_html_to_text(raw), "html") if "<" in raw[:4096]
                            else (raw.strip(), "text"))
            with open(txt_path, "w", encoding="utf-8") as fh:
                fh.write(text)
        except (OSError, UnicodeError) as exc:
            return None, f"could not extract text ({exc})"
        return method, None

    exe = shutil.which("pdftotext")
    if not exe:
        return None, "pdftotext is not installed (brew install poppler) — PDF not converted"
    try:
        proc = subprocess.run([exe, "-layout", src_path, txt_path],
                              capture_output=True, text=True, timeout=_CONVERT_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"pdftotext failed ({exc})"
    if proc.returncode != 0 or not os.path.isfile(txt_path):
        detail = (proc.stderr or "").strip().splitlines()
        return None, (f"pdftotext exit {proc.returncode}"
                      + (f" ({detail[-1][:100]})" if detail else ""))
    return "pdftotext", None


def _content_digest(path):
    """Verify snapshot bytes, including same-length edits that counts cannot detect."""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _measure(path):
    """(chars, lines) of the extracted text, read streaming so a 300-page report never
    lands in memory just to be counted."""
    chars = lines = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            lines += 1
            chars += len(line)
    return chars, lines


# The notes a leg must reach in an Indian annual report or concall, and the headings
# they appear under. Keys are what a skill asks for; the regexes run over the extracted
# text once, at conversion time, and the result is cached with the document.
_SECTIONS = {
    "auditors_report": r"independent auditor'?s?'? report",
    "emphasis_of_matter": r"emphasis of matter",
    "auditor_remuneration": r"(payment(s)? to auditor|auditor'?s?'? remuneration)",
    "mdna": r"management discussion and analysis",
    "directors_report": r"(board'?s? report|directors'? report)",
    "corporate_governance": r"(corporate governance report|board of directors)",
    "related_party": r"related part(y|ies) (disclosure|transaction)",
    "contingent_liabilities": r"contingent liabilit",
    "remuneration": r"(managerial remuneration|remuneration (of|to) (directors|key manageri)|section 197)",
    "tax_note": r"(income tax expense|tax expense|current and deferred tax)",
    "segment": r"(segment information|operating segments|segment reporting)",
    "cash_flow": r"statement of cash flows?",
    "esop": r"(employee stock option|esop scheme)",
    "shareholding": r"(shareholding pattern|pattern of shareholding)",
    "qna": r"(question[- ]and[- ]answer session|we will now begin the question)",
}

# A heading line is short and carries no page number; a contents-page entry is the
# opposite. Ranking on that separates the real section from the table of contents,
# which is otherwise the first hit for every pattern in the file.
_PAGE_NUM = re.compile(r"(?<!\d)\d{1,4}(?!\d)")
_MAX_HITS = 4


def _rank(text, line_no, total_lines):
    """Higher is more likely to be the section itself rather than a contents entry."""
    stripped = " ".join(text.split())
    score = 0.0
    if len(stripped) <= 80:
        score += 2.0
    elif len(stripped) <= 160:
        score += 1.0
    if not _PAGE_NUM.search(stripped):
        score += 1.5
    if total_lines and line_no > total_lines * 0.08:
        score += 1.0
    return score


def _outline(path, total_lines):
    """Where each known section starts in the extracted text: {key: [{line, text}]}.

    A leg needs four notes out of a 27,000-line annual report. Without this every leg
    greps for them independently and the ones it cannot find become data gaps in a
    report. Candidates are ranked best-first and capped, so the payload stays a few
    hundred bytes and the leg reads the lines it needs instead of hunting.
    """
    pats = {k: re.compile(v, re.I) for k, v in _SECTIONS.items()}
    hits = {k: [] for k in _SECTIONS}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                for key, pat in pats.items():
                    if pat.search(line):
                        hits[key].append((_rank(line, n, total_lines), n,
                                          " ".join(line.split())[:120]))
    except OSError:
        return {}
    out = {}
    for key, found in hits.items():
        if not found:
            continue
        found.sort(key=lambda h: (-h[0], h[1]))
        out[key] = [{"line": n, "text": t} for _, n, t in found[:_MAX_HITS]]
    return out


def _public_web_url(url):
    """A named public HTTP(S) host. Index links are untrusted data: an IP literal,
    loopback or local-network name is refused rather than fetched from this machine."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or "." not in host:
        return False
    if host.endswith((".localhost", ".local", ".internal", ".lan", ".home.arpa")):
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        return True


def _document(link, kind, fresh, gaps):
    """One index entry → its `data.documents` row, or None having appended a gap."""
    label = (link.get("label") or "").strip() or kind
    url = (link.get("url") or "").strip()
    if not url:
        gaps.append(f"{label}: the document index carries no link")
        return None
    if not _public_web_url(url):
        gaps.append(f"{label}: refused a link that is not a named public web host ({url[:80]})")
        return None

    _, legacy_txt, meta = _cache_paths(url)
    directory = os.path.dirname(meta)
    if not fresh and os.path.isfile(meta):
        try:
            with open(meta, encoding="utf-8") as fh:
                row = json.load(fh)
            format_checked = row.pop("_format_validation", None) == 1
            txt = row["text_path"]
            # Metadata cannot redirect a reader outside this URL's snapshot namespace.
            valid_path = (os.path.dirname(os.path.realpath(txt)) == os.path.realpath(directory)
                          and re.fullmatch(re.escape(_key(url)) + r"-[0-9a-f]{64}\.txt", os.path.basename(txt)))
            if (format_checked and row.get("url") == url and row.get("kind") == kind and valid_path
                    and os.path.isfile(txt) and _measure(txt) == (row.get("text_chars"),row.get("text_lines"))):
                expected = os.path.basename(txt)[len(_key(url)) + 1:-4]
                if _content_digest(txt) == expected:
                    row["cached"] = True
                    row["label"] = label
                    row["publisher"] = transport._host(url)
                    return row
                gaps.append(f"{label}: cached text failed its content hash; attempting a fresh download")
        except (OSError, ValueError, TypeError, KeyError):
            pass  # Invalid or legacy metadata triggers a fresh isolated extraction.

    try:
        with tempfile.TemporaryDirectory(prefix="document-", dir=directory) as work:
            src, extracted = os.path.join(work,"download.src"), os.path.join(work,"extracted.txt")
            got, gap = transport.request(url, dest=src, timeout=_DOWNLOAD_TIMEOUT,
                                         referer=fundamentals.SCREENER + "/")
            if gap or not got:
                gaps.append(f"{label}: download failed ({gap or 'empty response'})")
                return None
            method, gap = _to_text(src, extracted, expected_pdf=urlsplit(url).path.lower().endswith(".pdf"))
            if gap:
                gaps.append(f"{label}: {gap}")
                return None
            chars, lines = _measure(extracted)
            if not chars:
                gaps.append(f"{label}: converted to an empty file — no readable text")
                return None
            outline = _outline(extracted, lines)
            def write(stream):
                with open(extracted, encoding="utf-8") as source:
                    shutil.copyfileobj(source, stream)
            txt = spine.publish_evidence(os.path.splitext(legacy_txt)[0], ".txt", write)
        row = {"kind": kind, "label": label, "url": url, "publisher": transport._host(url),
               "text_path": txt, "text_chars": chars, "text_lines": lines,
               "extracted_by": method, "outline": outline}
        pending = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=directory, encoding="utf-8", delete=False) as stream:
                pending = stream.name
                json.dump({**row, "_format_validation": 1}, stream, ensure_ascii=False)
            os.replace(pending, meta)
        except OSError as exc:
            gaps.append(f"{label}: text saved but metadata not cached ({exc})")
        finally:
            if pending and os.path.exists(pending):
                os.unlink(pending)
        row["cached"] = False
        return row
    except (OSError, ValueError, TypeError) as exc:
        gaps.append(f"{label}: document extraction failed ({exc})")
        return None


def fetch(symbol, annual_reports=1, concalls=1, fresh=False):
    """Download the newest `annual_reports` and `concalls` for `symbol` as cached text.

    Returns paths, never content. A document that will not download or convert is a
    labelled gap; every other document still comes back.
    """
    sym = _norm(symbol)
    source = "screener.in (document index)"
    wanted = {"annual_reports": annual_reports, "concalls": concalls}
    empty = {"symbol":sym, "documents":[], "documents_total":0}
    if any(type(count) is not int or count < 0 for count in wanted.values()):
        return _envelope(False, source, empty, ["document counts must be nonnegative integers"])
    if not any(wanted.values()):
        return _envelope(True, source, empty, [])
    try:
        index = fundamentals.fetch(sym, sections=["documents"], fresh=fresh)
        links = index.get("data", {}).get("documents", {})
        if not isinstance(links, dict):
            raise ValueError("documents index must be a mapping")
        gaps = [f"document index: {g}" for g in (index.get("gaps") or [])]
        if index.get("ok") is not True and not gaps:
            gaps.append("document index: source did not succeed")
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        return _envelope(False, source, empty, [f"document index unavailable: {exc}"])

    rows, available = [], {}
    for section, kind in _KINDS.items():
        want_n = wanted[section]
        found = links.get(section) or []
        if not isinstance(found, list):
            if want_n:
                gaps.append(f"document index: malformed {section} list")
            found = []
        valid, seen = [], set()
        for link in found:
            if (not isinstance(link,dict) or not isinstance(link.get("label",""),str)
                    or not isinstance(link.get("url"),str) or not link["url"].strip()):
                if want_n:
                    gaps.append(f"document index: malformed {section} entry excluded")
                continue
            url = link["url"].strip()
            if url not in seen:
                seen.add(url)
                valid.append(link)
        available[f"{section}_available"] = len(valid)
        if not want_n:
            continue
        if not valid:
            gaps.append(f"screener.in lists no usable {section.replace('_', ' ')} for {sym}")
            continue
        ordered = _order_newest_first(valid, section, want_n, gaps)
        for link in ordered[:want_n]:
            try:
                row = _document(link, kind, fresh, gaps)
                if row:
                    rows.append(row)
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                gaps.append(f"{link.get('label') or kind}: document unavailable ({exc})")

    source = "screener.in (document index)"
    publishers = sorted({r["publisher"] for r in rows})
    if publishers:
        source += " + " + ", ".join(publishers)
    data = {"symbol": sym, "documents": rows, "documents_total": len(rows), **available}
    return _envelope(bool(rows), source, data, gaps)
