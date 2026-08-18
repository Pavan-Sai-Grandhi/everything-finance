#!/usr/bin/env python3
"""Fundamentals fetch — the screener.in rung of the data spine.

`fetch(symbol)` reads the public consolidated company page ONCE and parses every section;
the public page needs no auth, and cookies are injected only for the login-walled screen
that `screen(query)` runs.

Output extracts tables and fields ONLY — never the raw page HTML: every value in `data` is
a parsed number, string, or list.

Returns the shared data-spine envelope (finance/contracts.md).

Reached through: get_company_fundamentals, run_fundamental_screen.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from html.parser import HTMLParser

from finance import paths
from finance import transport
from finance.spine import envelope as _envelope, norm_symbol as _norm


_BASE = "https://www.screener.in"

def _screener_cookies():
    """The optional screener.in auth cookies — used ONLY for login-walled screens.
    Missing creds degrade a screen, never the whole module."""
    sid = os.environ.get("SCREENER_SESSION_ID")
    csrf = os.environ.get("SCREENER_CSRF_TOKEN")
    parts = []
    if sid:
        parts.append(f"sessionid={sid}")
    if csrf:
        parts.append(f"csrftoken={csrf}")
    return "; ".join(parts)


_LOGGED_OUT_TITLES = ("register", "login", "sign in", "sign up")


def is_logged_out(html):
    """Did screener.in serve its anonymous page instead of the requested one?

    When a `sessionid` expires — Django rotates them, so this happens routinely — screener
    does NOT return 401 or redirect visibly: it answers 200 with its Register page. The
    screen parser finds no company rows in that page and reports "no companies matched",
    which reads exactly like a filter that was too tight, and a `find-trade` run then
    proceeds as though no stock passed the fundamental cut.

    Detected on the page title (screener titles its anonymous pages "Register - Screener"
    / "Login - Screener"), with a login-form fallback. A real screen result is titled
    after the query, so this cannot fire on a legitimately empty result.
    """
    text = html or ""
    m = re.search(r"<title>(.*?)</title>", text, re.S | re.IGNORECASE)
    if m:
        title = _WS_RE.sub(" ", m.group(1)).strip().lower()
        if any(title.startswith(t) for t in _LOGGED_OUT_TITLES):
            return True
    # Fallback: an anonymous page carries a login form; a signed-in one carries a logout link.
    return bool(re.search(r'action=["\'][^"\']*/login/?["\']', text, re.IGNORECASE))


def _http_get(url, timeout=20, cookie=None):
    """GET via the single shared transport. Returns (text, gap) — never raises."""
    headers = {"Cookie": cookie} if cookie else None
    return transport.request(url, timeout=timeout, referer=_BASE + "/", headers=headers)


def _to_number(text):
    """Coerce a screener cell to float (₹, commas, %, Cr, (negatives)) or None.
    A blank/dash cell is None — a labelled missing beats a fabricated zero in the math."""
    if text is None:
        return None
    s = str(text).strip()
    if not s or s in {"-", "—", "–"}:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    for junk in ("₹", ",", "%", "Cr.", "Cr", "days", "x"):
        s = s.replace(junk, "")
    s = s.strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


# HTML parsing is stdlib-only here, as in prices.py and filings.py: no bs4 dependency.
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_COMPANY_HREF_RE = re.compile(r'/company/([A-Za-z0-9&._-]+)/', re.IGNORECASE)
_ANCHOR_RE = re.compile(r'<a\b[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<text>.*?)</a>',
                        re.IGNORECASE | re.DOTALL)


def _text(html_fragment):
    """Visible text of an HTML fragment — tags stripped, whitespace collapsed."""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", html_fragment or "")).strip()


def _section_html(html, section_id):
    """Slice one screener `<section id="...">` out of the page. Sections are siblings
    (not nested), so the slice runs to the next `<section` or the page end."""
    m = re.search(rf'<section\b[^>]*\bid=["\']{re.escape(section_id)}["\']', html or "", re.I)
    if not m:
        return ""
    nxt = re.search(r'<section\b', html[m.end():], re.I)
    end = m.end() + nxt.start() if nxt else len(html)
    return html[m.start():end]


class _FirstTable(HTMLParser):
    """Pull the first <table>'s header row + body rows out of an HTML fragment.

    screener.in lays a financial section out as one `data-table`: a header row of period
    labels (Mar 2015 … TTM) and one body row per line-item whose first cell is the label."""

    def __init__(self):
        super().__init__()
        self._in_table = self._done = False
        self._in_cell = False
        self._row, self._cell, self._row_has_th = [], [], False
        self.header, self.rows = [], []

    def handle_starttag(self, tag, attrs):
        if self._done:
            return
        if tag == "table" and not self._in_table:
            self._in_table = True
        elif self._in_table and tag == "tr":
            self._row, self._row_has_th = [], False
        elif self._in_table and tag in ("th", "td"):
            self._in_cell, self._cell = True, []
            if tag == "th":
                self._row_has_th = True

    def handle_endtag(self, tag):
        if self._done or not self._in_table:
            return
        if tag == "table":
            self._in_table, self._done = False, True
        elif tag in ("th", "td") and self._in_cell:
            self._row.append(_WS_RE.sub(" ", "".join(self._cell)).strip())
            self._in_cell = False
        elif tag == "tr":
            if not self.header and self._row_has_th:
                self.header = self._row
            elif self._row:
                self.rows.append(self._row)

    def handle_data(self, data):
        if self._in_cell:
            self._cell.append(data)


def _parse_table(section_html):
    """A screener section's data-table → {columns, rows:{label:[numbers]}}.
    The leading label column is dropped from `columns`; row values are coerced to number."""
    p = _FirstTable()
    p.feed(section_html or "")
    columns = p.header[1:] if p.header else []
    rows = {}
    for r in p.rows:
        if not r:
            continue
        label = re.sub(r"[+\-]?$", "", r[0]).strip()  # drop screener's expand "+"/"-" affordance
        if not label:
            continue
        rows[label] = [_to_number(c) for c in r[1:]]
    return {"columns": columns, "rows": rows}


def _parse_ratios(html):
    """The top-ratios list → {name: number|text}."""
    block = re.search(r'<ul[^>]*id=["\']top-ratios["\'][^>]*>(.*?)</ul>', html or "", re.S | re.I)
    if not block:
        return {}
    out = {}
    for li in re.findall(r"<li\b.*?</li>", block.group(1), re.S | re.I):
        name_m = re.search(r'class=["\'][^"\']*\bname\b[^"\']*["\']>(.*?)</span>', li, re.S | re.I)
        if not name_m:
            continue
        name = _text(name_m.group(0).split(">", 1)[1])
        # everything after the name span is the value (may hold one or more numbers)
        rest = li[name_m.end():]
        nums = re.findall(r'class=["\'][^"\']*\bnumber\b[^"\']*["\']>(.*?)</span>', rest, re.S | re.I)
        if len(nums) == 1:
            out[name] = _to_number(nums[0])
        elif nums:
            out[name] = " / ".join(_text(n) for n in nums)
        else:
            out[name] = _to_number(_text(rest)) if _to_number(_text(rest)) is not None else _text(rest)
    return out


def _parse_shareholding(html):
    """The shareholding section's data-table → {columns, rows}."""
    return _parse_table(_section_html(html, "shareholding"))


def _parse_peers(html):
    """The peers section → list of {symbol, name}.
    Each peer row links to `/company/<SYMBOL>/`; the link text is the company name."""
    sect = _section_html(html, "peers")
    out, seen = [], set()
    for m in _ANCHOR_RE.finditer(sect):
        href = m.group("href")
        sm = _COMPANY_HREF_RE.search(href)
        if not sm:
            continue
        sym = sm.group(1).upper()
        if sym in seen:
            continue
        seen.add(sym)
        out.append({"symbol": sym, "name": _text(m.group("text"))})
    return out


def _parse_documents(html):
    """The documents section → {annual_reports:[...], concalls:[...]}.
    Links are classified by their text: annual-report PDFs vs concall transcripts/notes/PPTs."""
    sect = _section_html(html, "documents")
    annual, concalls = [], []
    for m in _ANCHOR_RE.finditer(sect):
        href, text = m.group("href").strip(), _text(m.group("text"))
        if not href.startswith("http") and href.startswith("/"):
            href = _BASE + href
        low = text.lower()
        link = {"label": text, "url": href}
        if "annual report" in low or "from bse" in low or "from nse" in low:
            annual.append(link)
        elif any(k in low for k in ("transcript", "concall", "ppt", "notes", "presentation")):
            concalls.append(link)
    return {"annual_reports": annual, "concalls": concalls}


def _parse_screen(html):
    """A screener.in screen result page → ordered, de-duped candidate symbol list.
    Result rows link each company to `/company/<SYMBOL>/`."""
    out, seen = [], set()
    for sym in _COMPANY_HREF_RE.findall(html or ""):
        s = sym.upper()
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _parse_company(html, sym):
    """One screener company page → the typed `data` dict.
    Tables/fields only — the raw page HTML never lands in `data`."""
    return {
        "symbol": sym,
        "ratios": _parse_ratios(html),
        "pnl_10y": _parse_table(_section_html(html, "profit-loss")),
        "balance_sheet_10y": _parse_table(_section_html(html, "balance-sheet")),
        "quarters": _parse_table(_section_html(html, "quarters")),
        "shareholding": _parse_shareholding(html),
        "peers": _parse_peers(html),
        "documents": _parse_documents(html),
    }


def _empty_company(sym):
    return {"symbol": sym, "ratios": {}, "pnl_10y": {"columns": [], "rows": {}},
            "balance_sheet_10y": {"columns": [], "rows": {}}, "quarters": {"columns": [], "rows": {}},
            "shareholding": {"columns": [], "rows": {}}, "peers": [],
            "documents": {"annual_reports": [], "concalls": []}}


def _select_sections(env, sections):
    """Narrow a company envelope to `sections` (None keeps all), always keeping the
    identity fields and listing every section the page actually yielded."""
    if not sections:
        return env
    data = env.get("data") or {}
    keep = set(sections) | {"symbol", "name", "url"}
    env["data"] = {k: v for k, v in data.items() if k in keep}
    env["data"]["sections_available"] = sorted(data)
    return env


_MIN_RATIOS = 6   # a complete screener page carries ~9 headline ratios


def fetch(symbol, sections=None, fresh=False):
    """Read the public consolidated company page once and parse it into the typed envelope.

    Falls back to the standalone page (with a labelled gap) if consolidated is missing.
    `sections` narrows the returned data to the parts asked for (the whole page is large);
    the cache always holds the complete parse, so a narrowed read costs no extra fetch."""
    sym = _norm(symbol)
    cache_file = os.path.join(paths.cache_dir("fundamentals"), f"{sym}.json")
    cached = _read_cache(cache_file, fresh)
    if cached is not None:
        return _select_sections(cached, sections)

    gaps = []
    html, gap = _http_get(f"{_BASE}/company/{sym}/consolidated/")
    source = "screener.in (consolidated)"
    if gap or not html:
        gaps.append(f"consolidated page: {gap or 'empty'}")
        html, gap2 = _http_get(f"{_BASE}/company/{sym}/")
        source = "screener.in (standalone)"
        if gap2 or not html:
            gaps.append(f"standalone page: {gap2 or 'empty'}")
            return _select_sections(
                _envelope(False, "screener.in", _empty_company(sym), gaps), sections)

    data = _parse_company(html, sym)
    if not data["pnl_10y"]["rows"]:
        gaps.append("profit-loss table: not found (page layout changed or symbol unknown?)")
    # A real company page publishes ~9 headline ratios. A handful means a partial or
    # substituted page, which parses cleanly and reads as authoritative — the failure
    # mode that put a stale price into a valuation.
    if 0 < len(data["ratios"]) < _MIN_RATIOS:
        gaps.append(f"only {len(data['ratios'])} headline ratios parsed "
                    f"(expected >= {_MIN_RATIOS}) — partial page, treat figures as unverified")
    ok = bool(data["ratios"] or data["pnl_10y"]["rows"])
    env = _envelope(ok, source, data, gaps)
    if ok:
        _write_cache(cache_file, env)
    return _select_sections(env, sections)


def screen(query, fresh=False):
    """Run a screener.in fundamental screen → candidate symbol list envelope. Auth cookies
    (the builder is login-walled) are injected only when present in the env."""
    import urllib.parse
    url = f"{_BASE}/screen/raw/?" + urllib.parse.urlencode({"query": query, "source": ""})
    cookie = _screener_cookies()
    gaps = []
    if not cookie:
        gaps.append("no screener auth cookies — screen builder is login-walled; results may be empty")
    html, gap = _http_get(url, cookie=cookie or None)
    if gap or not html:
        return _envelope(False, "screener.in", {"query": query, "count": 0, "candidates": []},
                         gaps + [f"screen fetch: {gap or 'empty'}"])
    # Check auth BEFORE parsing: an expired session yields a parseable page with no
    # company rows, which is indistinguishable from an empty result unless asked directly.
    if is_logged_out(html):
        gaps.append(
            "screener.in session expired or not logged in — this is NOT an empty result. "
            "Re-copy `sessionid` and `csrftoken` from a logged-in browser "
            "(DevTools -> Application -> Cookies -> screener.in) into the plugin's .env as "
            "SCREENER_SESSION_ID / SCREENER_CSRF_TOKEN.")
        return _envelope(False, "screener.in",
                         {"query": query, "count": 0, "candidates": []}, gaps)

    candidates = _parse_screen(html)
    data = {"query": query, "count": len(candidates), "candidates": candidates}
    if not candidates:
        gaps.append("screen matched no companies — the session is valid, so this is a "
                    "genuinely empty result (query too tight)")
    return _envelope(bool(candidates), "screener.in", data, gaps)


# Day-cache: reuse within the day, --fresh bypasses.
def _read_cache(cache_file, fresh):
    if fresh or not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file) as fh:
            cached = json.load(fh)
        if cached.get("data", {}).get("cached_on") == date.today().isoformat():
            return cached
    except Exception:  # noqa: BLE001 — a bad cache file never blocks a fetch
        pass
    return None


def _write_cache(cache_file, env):
    # The stamp records when WE cached, so it is assigned, never setdefault:
    # upstream payloads carry their own "cached_on" and an inherited one would let
    # the freshness check read a source's date as our fetch time.
    env.setdefault("data", {})["cached_on"] = date.today().isoformat()
    try:
        with open(cache_file, "w") as fh:
            json.dump(env, fh, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass
