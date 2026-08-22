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
import json
import os
import re
import shutil
import subprocess
from html import unescape

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


def _label_recency(label):
    """(year, quarter) parsed from a document label, for a newest-first sort; None when the
    label carries no 4-digit year. Annual reports name a year ("Financial Year 2026");
    concalls add a quarter ("Q1 2026 Transcript"). The latest year in the label wins."""
    years = _YEAR_RE.findall(label or "")
    if not years:
        return None
    q = _QUARTER_RE.search(label or "")
    return max(int(y) for y in years), (int(q.group(1)) if q else 0)


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
            gaps.append(f"{label}: no year in the label — ordered by list position, not date")
    return ordered


def _key(url):
    """Content address for a document.

    A published annual report or transcript never changes at its URL, so the URL is the
    whole key and the cache has no expiry — `fresh=True` is the only re-download.
    """
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


def _to_text(src_path, txt_path):
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
        try:
            with open(src_path, encoding="utf-8", errors="replace") as fh:
                raw = fh.read()
            text, method = ((_html_to_text(raw), "html") if "<" in raw[:4096]
                            else (raw.strip(), "text"))
            with open(txt_path, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
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


def _measure(path):
    """(chars, lines) of the extracted text, read streaming so a 300-page report never
    lands in memory just to be counted."""
    chars = lines = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            lines += 1
            chars += len(line)
    return chars, lines


def _document(link, kind, fresh, gaps):
    """One index entry → its `data.documents` row, or None having appended a gap."""
    label = (link.get("label") or "").strip() or kind
    url = (link.get("url") or "").strip()
    if not url:
        gaps.append(f"{label}: the document index carries no link")
        return None

    src, txt, meta = _cache_paths(url)
    if not fresh and os.path.isfile(txt) and os.path.isfile(meta):
        try:
            with open(meta, encoding="utf-8") as fh:
                row = json.load(fh)
            row["cached"] = True
            return row
        except (OSError, ValueError):
            pass  # a damaged cache entry re-downloads rather than blocking the read

    got, gap = transport.request(url, dest=src, timeout=_DOWNLOAD_TIMEOUT,
                                 referer=fundamentals.SCREENER + "/")
    if gap or not got:
        gaps.append(f"{label}: download failed ({gap or 'empty response'})")
        return None

    method, gap = _to_text(src, txt)
    if gap:
        gaps.append(f"{label}: {gap}")
        return None
    try:
        os.remove(src)  # the raw download is never re-read; the .txt is the cached primary
    except OSError:
        pass

    chars, lines = _measure(txt)
    if not chars:
        gaps.append(f"{label}: converted to an empty file — a scanned image, not text")
        return None

    row = {"kind": kind, "label": label, "url": url, "publisher": transport._host(url),
           "text_path": txt, "text_chars": chars, "text_lines": lines,
           "extracted_by": method}
    try:
        with open(meta, "w", encoding="utf-8") as fh:
            json.dump(row, fh, ensure_ascii=False)
    except OSError as exc:
        gaps.append(f"{label}: cached the text but not its metadata ({exc}) — "
                    "the next call re-downloads it")
    row["cached"] = False
    return row


def fetch(symbol, annual_reports=1, concalls=1, fresh=False):
    """Download the newest `annual_reports` and `concalls` for `symbol` as cached text.

    Returns paths, never content. A document that will not download or convert is a
    labelled gap; every other document still comes back.
    """
    sym = _norm(symbol)
    index = fundamentals.fetch(sym, sections=["documents"], fresh=fresh)
    links = ((index.get("data") or {}).get("documents") or {})
    gaps = [f"document index: {g}" for g in (index.get("gaps") or [])]

    wanted = {"annual_reports": annual_reports, "concalls": concalls}
    rows, available = [], {}
    for section, kind in _KINDS.items():
        found = links.get(section) or []
        available[f"{section}_available"] = len(found)
        if not found:
            gaps.append(f"screener.in lists no {section.replace('_', ' ')} for {sym}")
            continue
        want_n = max(0, int(wanted[section] or 0))
        ordered = _order_newest_first(found, section, want_n, gaps)
        for link in ordered[:want_n]:
            row = _document(link, kind, fresh, gaps)
            if row:
                rows.append(row)

    source = "screener.in (document index)"
    publishers = sorted({r["publisher"] for r in rows})
    if publishers:
        source += " + " + ", ".join(publishers)
    data = {"symbol": sym, "documents": rows, "documents_total": len(rows), **available}
    return _envelope(bool(rows), source, data, gaps)
