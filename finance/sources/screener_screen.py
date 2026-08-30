"""Saved-screen fetch — run a public screener.in screen and return its matched NSE symbols.

screener.in's saved public screens (`/screens/<id>/<slug>/`) are readable ANONYMOUSLY and carry
both the query text and the matched-company table, so a spec can lean on the full screener.in
query language — cross-period comparisons (`ROCE > ROCE preceding year`), PEG, promoter-holding
change, pledged % — that the Tickertape screener (`fundamentals.screen`) cannot express. No login.

The custom-query endpoint (`/screen/raw/`) is login-walled and deliberately NOT used: a saved
public screen already carries whatever query its author wrote, and the user can author any custom
screen on screener.in's own site (free), save it, and paste the URL here.

Two markup facts this parser depends on (verified against a live screen 2026-08-30):
  - the query lives in `<textarea name="query">…</textarea>`, HTML-entity encoded;
  - each result row carries one `/company/<SYMBOL>/` link inside a `class="data-table"` table,
    and screener paginates 25 rows/page with a "Showing page X of Y" marker.
A purely-numeric `/company/<code>/` is a BSE-only scrip code with no NSE symbol — skipped and
counted as a gap, never emitted as a candidate. Returns the shared envelope (finance/contracts.md).
"""
from __future__ import annotations

import html as _html
import os
import re

from finance import paths, transport
from finance.spine import (CACHE_STAMP, envelope as _envelope, norm_symbol as _norm,
                           read_cache as _read_cache, write_cache as _write_cache)

BASE = "https://www.screener.in"

_SCREEN_URL_RE = re.compile(r"^https?://(?:www\.)?screener\.in/screens/(\d+)(/[^?\s#]*?)?/?(?:[?#].*)?$", re.I)
_QUERY_RE = re.compile(r'<textarea[^>]*name="query"[^>]*>(.*?)</textarea>', re.S | re.I)
_TABLE_RE = re.compile(r'<table[^>]*class="[^"]*data-table[^"]*"[^>]*>(.*?)</table>', re.S | re.I)
_COMPANY_RE = re.compile(r'/company/([A-Za-z0-9&._%-]+)/')
_PAGES_RE = re.compile(r'Showing\s+page\s+(\d+)\s+of\s+(\d+)', re.I)
_LOGINWALL_RE = re.compile(r'name="password"', re.I)

_MAX_PAGES = 20            # 25 rows/page -> a 500-name hard ceiling, whatever max_survivors asks
_CACHE_MAX_AGE_DAYS = 1


def _cache_path(key):
    """A stable cache-file path under the disposable tier (mirrors tickertape.cache_path)."""
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(key))
    return os.path.join(paths.cache_dir("screener_screen"), f"{safe}.json")


def _parse(body):
    """`(query|None, [nse_symbols], [bse_codes], pages_total|None, login_walled)` for one page."""
    body = body or ""
    query = None
    m = _QUERY_RE.search(body)
    if m:
        query = _html.unescape(re.sub(r"\s+", " ", m.group(1)).strip()) or None

    region = body
    t = _TABLE_RE.search(body)
    if t:
        region = t.group(1)

    syms, bse, seen = [], [], set()
    for raw in _COMPANY_RE.findall(region):
        token = _html.unescape(raw)
        if token in seen:
            continue
        seen.add(token)
        (bse if token.isdigit() else syms).append(token if token.isdigit() else _norm(token))

    pages = None
    p = _PAGES_RE.search(body)
    if p:
        pages = int(p.group(2))
    return query, syms, bse, pages, bool(_LOGINWALL_RE.search(body))


def screen(screen_url, max_survivors=200, fresh=False):
    """Fetch a screener.in saved public screen → candidate NSE-symbol list envelope.

    `screen_url` must be a `screener.in/screens/<id>/<slug>/` URL (the bare `/<id>/` 404s to a
    non-browser client, so the slug is required and the user should paste the full URL). Pages are
    walked until the screen is exhausted, `max_survivors` is reached, or the page ceiling hits.
    """
    empty = {"query": None, "screen_url": screen_url, "count": 0, "candidates": []}
    m = _SCREEN_URL_RE.match((screen_url or "").strip())
    if not m:
        return _envelope(False, "screener.in", empty,
                         ["not a screener.in saved-screen URL — expected "
                          "https://www.screener.in/screens/<id>/<slug>/ (with the slug; the bare "
                          "/screens/<id>/ 404s)"])
    screen_id, slug = m.group(1), (m.group(2) or "")
    base = f"{BASE}/screens/{screen_id}{slug.rstrip('/')}/" if slug else f"{BASE}/screens/{screen_id}/"

    key = f"{screen_id}|{max_survivors}"
    cache = _cache_path(key)
    cached = _read_cache(cache, fresh, max_age_days=_CACHE_MAX_AGE_DAYS)
    if cached is not None:
        cached["data"].pop(CACHE_STAMP, None)
        return cached

    candidates, seen = [], set()
    bse_skipped, gaps = [], []
    query, pages_total, walled = None, None, False
    page = 1
    while page <= _MAX_PAGES:
        url = base + (f"?page={page}" if page > 1 else "")
        body, gap = transport.request(url, timeout=30)
        if gap:
            gaps.append(f"screen page {page} fetch: {gap}")
            break
        q, syms, bse, pages, walled = _parse(body)
        if page == 1:
            query, pages_total = q, pages
        for s in syms:
            if s not in seen:
                seen.add(s)
                candidates.append(s)
        bse_skipped += [b for b in bse if b not in bse_skipped]
        if len(candidates) >= max_survivors:
            candidates = candidates[:max_survivors]
            break
        if not syms or (pages_total and page >= pages_total):
            break
        page += 1

    data = {"query": query, "screen_url": screen_url,
            "count": len(candidates), "candidates": candidates}
    if bse_skipped:
        shown = ", ".join(bse_skipped[:6]) + ("…" if len(bse_skipped) > 6 else "")
        gaps.append(f"{len(bse_skipped)} BSE-only row(s) skipped — numeric scrip codes with no "
                    f"NSE symbol ({shown})")
    if pages_total and pages_total > page and len(candidates) >= max_survivors:
        gaps.append(f"stopped at {len(candidates)} of the screen's results across {pages_total} "
                    f"pages — raise max_survivors for the rest")
    if not candidates and not gaps:
        if walled:
            gaps.append("screen is private / login-walled — only public saved screens are "
                        "readable; make it public on screener.in or paste a public one")
        else:
            gaps.append("screen matched no NSE companies — check the URL is the /<id>/<slug>/ "
                        "form, or the screen genuinely returned nothing")

    env = _envelope(bool(candidates), "screener.in", data, gaps)
    if candidates:
        _write_cache(cache, {**env, "data": dict(data)})
    return env
