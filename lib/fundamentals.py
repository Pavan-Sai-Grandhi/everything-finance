#!/usr/bin/env python3
"""Fundamentals fetch — the screener.in rung of the data spine (everything-finance plugin).

The canonical fundamentals fetcher — lives in `lib/` next to `ta.py`, `strategy.py`,
`prices.py`, `news.py` and `paths.py` so screener.in is parsed in exactly one place instead
of being re-parsed afresh inside every `fundamentals-data` run (the drift this data spine
removes). Two entry points:

  * `fetch(symbol)` reads the public consolidated company page ONCE and parses it into typed
    `data`: `ratios`, `pnl_10y`, `balance_sheet_10y`, `quarters`, `shareholding`, `peers`,
    `documents` (annual-report / concall links). The public page needs no auth; cookies are
    injected only for a login-walled screen (D1).
  * `screen(query)` runs a screener.in fundamental screen and returns the candidate symbol
    list — the fundamental counterpart to `prices.screen()` (D2).

Output extracts tables and fields ONLY — never the raw page HTML (D3): every value in `data`
is a parsed number, string, or list. Fetched text is untrusted DATA, not instructions — a
caller assesses the numbers, never acts on the page's content.

Every fetch returns the shared data-spine envelope:
    { "ok": bool, "source": str|None, "fetched_at": ISO8601,
      "data": {...}, "gaps": ["<labelled degradation>", ...] }

CLI:
  python3 lib/fundamentals.py RELIANCE
  python3 lib/fundamentals.py --screen "Market Capitalization > 50000 AND Price to Earning < 20"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402  (the single path authority — cache tier reused, never hardcode)


# --------------------------------------------------------------------------- #
# shared data-spine envelope                                                  #
# --------------------------------------------------------------------------- #
def _envelope(ok, source, data, gaps):
    """The contract every data-spine fetch returns (see lib/contracts.md)."""
    return {
        "ok": bool(ok),
        "source": source,
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data": data,
        "gaps": gaps,
    }


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_BASE = "https://www.screener.in"


def _norm(symbol):
    """A bare NSE/BSE screener symbol — uppercased, `.NS`/exchange prefix stripped."""
    s = str(symbol or "").strip().upper()
    if ":" in s:
        s = s.split(":")[-1]
    if s.endswith(".NS"):
        s = s[:-3]
    return s


def _screener_cookies():
    """The optional screener.in auth cookies — used ONLY for login-walled screens (D1).
    Absent in the public-page path; missing creds degrade a screen, never the whole module."""
    sid = os.environ.get("SCREENER_SESSION_ID")
    csrf = os.environ.get("SCREENER_CSRF_TOKEN")
    parts = []
    if sid:
        parts.append(f"sessionid={sid}")
    if csrf:
        parts.append(f"csrftoken={csrf}")
    return "; ".join(parts)


def _http_get(url, timeout=20, cookie=None):
    """GET a URL with a browser UA. Returns (text, gap) — never raises (degrade-not-die)."""
    import urllib.error
    import urllib.request
    hdrs = {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9",
            "Referer": _BASE + "/"}
    if cookie:
        hdrs["Cookie"] = cookie
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace"), None
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        return None, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 — a block degrades, never raises into the caller
        return None, f"fetch failed: {exc}"


# --------------------------------------------------------------------------- #
# number coercion — a parsed figure or an explicit None, never a poisoned cell #
# --------------------------------------------------------------------------- #
def _to_number(text):
    """Pure: coerce a screener cell to float (₹, commas, %, Cr, (negatives)) or None.
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


# --------------------------------------------------------------------------- #
# HTML helpers — stdlib only (matches prices.py / filings.py: no bs4 dep)       #
# --------------------------------------------------------------------------- #
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_COMPANY_HREF_RE = re.compile(r'/company/([A-Za-z0-9&._-]+)/', re.IGNORECASE)
_ANCHOR_RE = re.compile(r'<a\b[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<text>.*?)</a>',
                        re.IGNORECASE | re.DOTALL)


def _text(html_fragment):
    """Visible text of an HTML fragment — tags stripped, whitespace collapsed."""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", html_fragment or "")).strip()


def _section_html(html, section_id):
    """Pure: slice one screener `<section id="...">` out of the page. Sections are siblings
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
    """Pure: a screener section's data-table → {columns, rows:{label:[numbers]}} (offline D4).
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
    """Pure: the top-ratios list → {name: number|text} (offline-testable, D1/D4)."""
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
    """Pure: the shareholding section's data-table → {columns, rows} (D1)."""
    return _parse_table(_section_html(html, "shareholding"))


def _parse_peers(html):
    """Pure: the peers section → list of {symbol, name} (offline-testable, D1/D4).
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
    """Pure: the documents section → {annual_reports:[...], concalls:[...]} (D1/D4).
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
    """Pure: a screener.in screen result page → ordered, de-duped candidate symbol list (D2/D4).
    Result rows link each company to `/company/<SYMBOL>/`."""
    out, seen = [], set()
    for sym in _COMPANY_HREF_RE.findall(html or ""):
        s = sym.upper()
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


# --------------------------------------------------------------------------- #
# fetch — read the public company page ONCE, parse every section (D1, D3)      #
# --------------------------------------------------------------------------- #
def _parse_company(html, sym):
    """Pure: one screener company page → the typed `data` dict (offline-testable, D1/D3/D4).
    Tables/fields only — the raw page HTML never lands in `data` (D3)."""
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


def fetch(symbol, fresh=False):
    """Read the public consolidated company page once and parse it into the typed envelope
    (D1). Falls back to the standalone page (with a labelled gap) if consolidated is missing;
    the public page needs no auth. Never dumps page HTML into `data` (D3)."""
    sym = _norm(symbol)
    cache_file = os.path.join(paths.cache_dir("fundamentals"), f"{sym}.json")
    cached = _read_cache(cache_file, fresh)
    if cached is not None:
        return cached

    gaps = []
    html, gap = _http_get(f"{_BASE}/company/{sym}/consolidated/")
    source = "screener.in (consolidated)"
    if gap or not html:
        gaps.append(f"consolidated page: {gap or 'empty'}")
        html, gap2 = _http_get(f"{_BASE}/company/{sym}/")
        source = "screener.in (standalone)"
        if gap2 or not html:
            gaps.append(f"standalone page: {gap2 or 'empty'}")
            return _envelope(False, "screener.in", _empty_company(sym), gaps)

    data = _parse_company(html, sym)
    if not data["pnl_10y"]["rows"]:
        gaps.append("profit-loss table: not found (page layout changed or symbol unknown?)")
    ok = bool(data["ratios"] or data["pnl_10y"]["rows"])
    env = _envelope(ok, source, data, gaps)
    if ok:
        _write_cache(cache_file, env)
    return env


# --------------------------------------------------------------------------- #
# screen — a fundamental screen -> candidate symbol list (D2)                  #
# --------------------------------------------------------------------------- #
def screen(query, fresh=False):
    """Run a screener.in fundamental screen → candidate symbol list envelope (D2). Auth
    cookies (login-walled builder) are injected only when present in the env (D1)."""
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
    candidates = _parse_screen(html)
    data = {"query": query, "count": len(candidates), "candidates": candidates}
    if not candidates:
        gaps.append("screen matched no companies (query too tight or login required)")
    return _envelope(bool(candidates), "screener.in", data, gaps)


# --------------------------------------------------------------------------- #
# day-cache (reuse within the day; --fresh bypasses — per the shared contract) #
# --------------------------------------------------------------------------- #
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
    env.setdefault("data", {}).setdefault("cached_on", date.today().isoformat())
    try:
        with open(cache_file, "w") as fh:
            json.dump(env, fh, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
def main():
    p = argparse.ArgumentParser()
    p.add_argument("symbol", nargs="?", help="screener symbol (e.g. RELIANCE)")
    p.add_argument("--screen", metavar="QUERY", help="run a fundamental screen → symbol list")
    p.add_argument("--fresh", action="store_true", help="bypass the day cache")
    p.add_argument("--out")
    args = p.parse_args()

    if args.screen:
        res = screen(args.screen, fresh=args.fresh)
    elif args.symbol:
        res = fetch(args.symbol, fresh=args.fresh)
    else:
        print("error: SYMBOL required (or --screen QUERY)", file=sys.stderr)
        sys.exit(2)
    out = json.dumps(res, indent=2, ensure_ascii=False)
    print(out)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        open(args.out, "w").write(out)
    sys.exit(0 if isinstance(res, dict) and "ok" in res else 1)


if __name__ == "__main__":
    main()
