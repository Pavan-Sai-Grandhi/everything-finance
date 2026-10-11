#!/usr/bin/env python3
"""Fundamentals fetch — Tickertape for the numbers, screener.in for the document index.

`fetch(symbol)` resolves the NSE symbol to a Tickertape `sid` and reads the ratio, annual
P&L, balance-sheet and cash-flow, interim financial, shareholding and peer endpoints. Annual-report and concall links
come from screener.in's public company page: no other approved source indexes them.

Line-item labels are Tickertape's own published vocabulary (`GET /screener/filters` names
every field), so a row means what the source says it means. Two of those meanings bite if
assumed away: **`Taxes & Other Items` lumps tax with the non-controlling interest**, so it
is not an effective tax rate; and **`EBITDA` is struck after other income**, so an
operating-only margin is not separable from it.

`screen(query)` runs the Tickertape stock screener. `query` is `FIELD OP VALUE` clauses
joined by `AND`, over the field names that endpoint publishes; an unresolvable name is
refused with the near-misses named, never dropped — a dropped clause loosens a quality gate
without saying so.

Output extracts tables and fields ONLY — never the raw page HTML: every value in `data` is
a parsed number, string, or list.

Returns the shared data-spine envelope (finance/contracts.md).

Reached through: get_company_fundamentals, run_fundamental_screen.
"""
from __future__ import annotations

import copy
import hashlib
import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from finance import paths
from finance import transport
from finance.sources import tickertape
from finance.spine import (CACHE_STAMP, envelope as _envelope, f as _f,
                           iso_date as _iso_date, norm_symbol as _norm, pct as _pct,
                           read_cache as _read_cache, write_cache as _write_cache)

SCREENER = "https://www.screener.in"

_SECTIONS = ("ratios", "pnl_10y", "balance_sheet_10y", "cash_flow_10y", "quarters",
             "shareholding", "peers", "documents")

# Identity travels with every narrowed read, so an extracted section stays attributable.
_IDENTITY = ("symbol", "name", "sid")


# --- screener.in: the document index ---------------------------------------- #

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_ANCHOR_RE = re.compile(r'<a\b[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<text>.*?)</a>',
                        re.IGNORECASE | re.DOTALL)

_LOGGED_OUT_TITLES = ("register", "login", "sign in", "sign up")


def is_logged_out(html):
    """Did screener.in serve its anonymous page instead of the requested one?

    screener answers a rate-limited or gated request with HTTP 200 and its Register page,
    not a 401. That page parses cleanly and yields no document links, which reads exactly
    like a company that has filed nothing — so the caller would report "no annual reports"
    for a company that has ten.

    Detected on the page title (screener titles its anonymous pages "Register - Screener" /
    "Login - Screener"), with a login-form fallback. A real company page is titled after
    the company, so this cannot fire on a legitimate one.
    """
    text = html or ""
    m = re.search(r"<title>(.*?)</title>", text, re.S | re.IGNORECASE)
    if m:
        title = _WS_RE.sub(" ", m.group(1)).strip().lower()
        if any(title.startswith(t) for t in _LOGGED_OUT_TITLES):
            return True
    return bool(re.search(r'action=["\'][^"\']*/login/?["\']', text, re.IGNORECASE))


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


def _parse_documents(html):
    """The documents section → {annual_reports:[...], concalls:[...]}.
    Links are classified by their text: annual-report PDFs vs concall transcripts/notes/PPTs."""
    sect = _section_html(html, "documents")
    annual, concalls = [], []
    for m in _ANCHOR_RE.finditer(sect):
        href, text = m.group("href").strip(), _text(m.group("text"))
        if not href.startswith("http") and href.startswith("/"):
            href = SCREENER + href
        low = text.lower()
        link = {"label": text, "url": href}
        if "annual report" in low or "from bse" in low or "from nse" in low:
            annual.append(link)
        elif any(k in low for k in ("transcript", "concall", "ppt", "notes", "presentation")):
            concalls.append(link)
    return {"annual_reports": annual, "concalls": concalls}


def _documents(sym):
    """`({annual_reports, concalls}, gaps)` from screener's public company page."""
    empty = {"annual_reports": [], "concalls": []}
    encoded = quote(sym, safe="")
    html, gap = transport.request(f"{SCREENER}/company/{encoded}/consolidated/",
                                  timeout=25, referer=SCREENER + "/")
    if gap or not html:
        html, gap2 = transport.request(f"{SCREENER}/company/{encoded}/", timeout=25,
                                       referer=SCREENER + "/")
        if gap2 or not html:
            return empty, [f"screener.in document index for {sym}: {gap or gap2 or 'empty'}"]
    if is_logged_out(html):
        return empty, [f"screener.in served its anonymous page for {sym} instead of the "
                       f"company page — this is NOT a company that has filed nothing"]
    docs = _parse_documents(html)
    if not (docs["annual_reports"] or docs["concalls"]):
        return docs, [f"screener.in lists no documents for {sym} "
                      f"(page layout changed or symbol unknown?)"]
    return docs, []


# --- Tickertape: the numbers ------------------------------------------------ #

# ratio name -> `/stocks/info` ratios key. `Stock P/E` is the trailing-twelve-month PE,
# which is the multiple an Indian screen quotes; `pe` on the same payload is annualised.
_INFO_RATIOS = {"Market Cap": "marketCap", "Current Price": "lastPrice",
                "Stock P/E": "ttmPe", "Book Value": "bps", "Dividend Yield": "divYield",
                "ROE": "roe", "No. of Shareholders": "nShareholders"}

# ratio name -> screener-query field; `/stocks/info` publishes neither.
_QUERY_RATIOS = {"ROCE": "roce", "Face Value": "faceValue"}

# A complete ratio block carries all ten; a handful means a partial or substituted payload,
# which parses cleanly and reads as authoritative.
_MIN_RATIOS = 6

# Annual P&L, in statement order. The interim endpoint publishes the same fields under a
# `q`-prefixed name, so one map drives both.
_PNL_ROWS = [
    ("Total Revenue", "incTrev"),
    ("Raw Materials", "incRaw"),
    ("Power & Fuel Cost", "incPfc"),
    ("Employee Cost", "incEpc"),
    ("Selling & Administrative Expenses", "incSga"),
    ("Operating & Other expenses", "incOpe"),
    ("EBITDA", "incEbi"),
    ("Depreciation & Amortization", "incDep"),
    ("PBIT", "incPbi"),
    ("Interest & Other Items", "incIoi"),
    ("PBT", "incPbt"),
    ("Taxes & Other Items", "incToi"),
    ("Net Income", "incNinc"),
    ("Earnings Per Share", "incEps"),
    ("Dividend Per Share", "incDps"),
]

_BS_ROWS = [
    ("Cash and Equivalent", "balCsti"),
    ("Total Receivables", "balTrec"),
    ("Total Inventory", "balTinv"),
    ("Other Current Assets", "balOca"),
    ("Total Current Assets", "balTca"),
    ("Loans & Advances", "balNetl"),
    ("Net Property, Plant & Equipment", "balNppe"),
    ("Goodwill & Intangibles", "balGint"),
    ("Long Term Investments", "balLti"),
    ("Other Assets", "balOtha"),
    ("Non Current Assets", "balNca"),
    ("Total Assets", "balTota"),
    ("Accounts Payable", "balAccp"),
    ("Total Deposits - Banks", "balTdep"),
    ("Other Current Liabilities", "balOcl"),
    ("Total Current Liabilities", "balTcl"),
    ("Long Term Debt", "balTltd"),
    ("Total Debt", "balTdeb"),
    ("Deferred Tax Liabilities (Net)", "balDit"),
    ("Deferred Tax Assets (Net)", "balDta"),
    ("Minority Interest", "balMint"),
    ("Other Liabilities", "balOthl"),
    ("Non Current Liabilities", "balNcl"),
    ("Total Liabilities", "balTotl"),
    ("Share Capital", "balComs"),
    ("Additional Paid-in Capital", "balApic"),
    ("Reserves & Surplus", "balRtne"),
    ("Other Equity", "balOeq"),
    ("Total Equity", "balTeq"),
    ("Total Liabilities & Shareholders Equity", "balTlse"),
    ("Common Shares Outstanding", "balTcso"),
]

# Annual cash flow, in the order the source's own statement renders it. `Free Cash Flow`
# is published, not derived: `cafCfoa - cafCexp` reproduces it exactly.
# `cafFee` is dropped — the source publishes no name for it, renders no row for it, and
# returns null for it on every company checked; naming it ourselves would be a guess.
_CF_ROWS = [
    ("Cash from Operating Activities", "cafCfoa"),
    ("Cash from Investing Activities", "cafCfia"),
    ("Cash from Financing Activities", "cafCffa"),
    ("Net Change in Cash", "cafNcic"),
    ("Changes in Working Capital", "cafCiwc"),
    ("Capital Expenditures", "cafCexp"),
    ("Total Cash Dividends Paid", "cafTcdp"),
    ("Free Cash Flow", "cafFcf"),
]

_HOLDING_ROWS = [
    ("Promoters", "pmPctT"),
    # The denominator is the promoter stake, not the share capital: Vedanta reads 99.99.
    ("Promoter Pledge (% of promoter holding)", "pmPctP"),
    ("FIIs", "fiPctT"),
    ("DIIs", "diPctT"),
    ("Mutual Funds", "mfPctT"),
    ("Insurance", "isPctT"),
    ("Retail", "rhPctT"),
    ("Others", "othPctT"),
]

_EMPTY_TABLE = {"columns": [], "rows": {}}


def _q_key(key):
    """The interim endpoint's name for an annual field: `incTrev` -> `qIncTrev`."""
    return "q" + key[0].upper() + key[1:]



def _periods(sid, statement, span, count):
    """`(rows, gap)` for one financial statement — one dict per reporting period."""
    blob, gap = tickertape.get_json(
        f"/stocks/financials/{statement}/{sid}/{span}/normal?count={count}", timeout=30)
    if gap:
        return [], f"Tickertape {statement} ({span}) for {sid}: {gap}"
    rows = (blob or {}).get("data") or []
    if not rows:
        return [], f"Tickertape published no {span} {statement} for {sid}"
    return rows, None


def _period_kind(label):
    """Classify a column's reporting period. The annual income statement appends a
    trailing-twelve-month column the balance sheet and cash flow do NOT, so pairing the
    three by index silently mixes a TTM value with a fiscal-year one — a consumer must
    pair by kind/label, never by position."""
    s = str(label or "").strip().upper()
    if s == "TTM":
        return "TTM"
    if s.startswith("FY"):
        return "FY"
    return "interim"


def _table(rows, labels, derived=None):
    """Period dicts + a (label, key) map → the shared `{columns, period_kinds, rows}` table."""
    columns = [str(r.get("displayPeriod") or "") for r in rows]
    period_kinds = [_period_kind(c) for c in columns]
    out = {}
    for label, key in labels:
        series = [_f(r.get(key)) for r in rows]
        if any(v is not None for v in series):
            out[label] = series
    for label, fn in (derived or {}).items():
        series = [fn(r) for r in rows]
        if any(v is not None for v in series):
            out[label] = series
    return {"columns": columns, "period_kinds": period_kinds, "rows": out}


# EBITDA is struck after other income, so this is not an operating-only margin.
_PNL_DERIVED = {
    "EBITDA Margin %": lambda r: _pct(r.get("incEbi"), r.get("incTrev")),
    "Payout Ratio %": lambda r: (None if _f(r.get("incPyr")) is None
                                 else round(100.0 * _f(r.get("incPyr")), 2)),
}

_Q_DERIVED = {
    "EBITDA Margin %": lambda r: _pct(r.get("qIncEbi"), r.get("qIncTrev")),
}


def _ratios(sid):
    """The headline ratio block, joined across the two endpoints that carry it."""
    out, gaps = {}, []
    blob, gap = tickertape.get_json(f"/stocks/info/{sid}", timeout=25)
    if gap:
        gaps.append(f"Tickertape ratios for {sid}: {gap}")
    else:
        rat = ((blob or {}).get("data") or {}).get("ratios") or {}
        for name, key in _INFO_RATIOS.items():
            out[name] = _f(rat.get(key))
        hi, lo = _f(rat.get("52wHigh")), _f(rat.get("52wLow"))
        if hi is not None and lo is not None:
            out["High / Low"] = f"{hi} / {lo}"

    blob, gap = tickertape.get_json(
        "/screener/query", timeout=30,
        payload={"match": {}, "sortBy": "mrktCapf", "sortOrder": -1,
                 "project": sorted(_QUERY_RATIOS.values()) + ["mrktCapf"],
                 "offset": 0, "count": 1, "sids": [sid]})
    if gap:
        gaps.append(f"Tickertape screener ratios for {sid}: {gap}")
    else:
        results = ((blob or {}).get("data") or {}).get("results") or []
        adv = (results[0].get("stock") or {}).get("advancedRatios") or {} if results else {}
        for name, key in _QUERY_RATIOS.items():
            out[name] = _f(adv.get(key))

    live = {k: v for k, v in out.items() if v is not None}
    if 0 < len(live) < _MIN_RATIOS:
        gaps.append(f"only {len(live)} of {len(_INFO_RATIOS) + len(_QUERY_RATIOS) + 1} "
                    f"headline ratios came back for {sid} — treat figures as unverified")
    return live, gaps


def _pnl_10y(sid):
    rows, gap = _periods(sid, "income", "annual", 10)
    return _table(rows, _PNL_ROWS, _PNL_DERIVED), ([gap] if gap else [])


def _balance_sheet_10y(sid):
    rows, gap = _periods(sid, "balancesheet", "annual", 10)
    return _table(rows, _BS_ROWS), ([gap] if gap else [])


def _cash_flow_10y(sid):
    rows, gap = _periods(sid, "cashflow", "annual", 10)
    return _table(rows, _CF_ROWS), ([gap] if gap else [])


def _quarters(sid):
    rows, gap = _periods(sid, "income", "interim", 13)
    labels = [(label, _q_key(key)) for label, key in _PNL_ROWS]
    return _table(rows, labels, _Q_DERIVED), ([gap] if gap else [])


def _shareholding(sid):
    """The quarterly ownership split. Tickertape publishes six quarters, no more."""
    blob, gap = tickertape.get_json(f"/stocks/holdings/{sid}", timeout=25)
    if gap:
        return _blank("shareholding"), [f"Tickertape shareholding for {sid}: {gap}"]
    quarters = (blob or {}).get("data") or []
    if not quarters:
        return _blank("shareholding"), [f"Tickertape published no shareholding for {sid}"]
    columns = [_iso_date(q.get("date")) for q in quarters]
    cells = [q.get("data") or {} for q in quarters]
    rows = {}
    for label, key in _HOLDING_ROWS:
        series = [_f(c.get(key)) for c in cells]
        if any(v is not None for v in series):
            rows[label] = series
    return {"columns": columns, "rows": rows}, []


def _peers(sid):
    """Sub-sector peers, self excluded, each with the multiples the valuation tab returns.

    `ttm_pe` and `pb` arrive in this one response, so the relative read needs no
    per-peer call and every peer is struck on the same trailing basis. `sid` travels
    for the ratios a peer row does not carry.
    """
    blob, gap = tickertape.get_json(f"/stocks/peers/{sid}?tab=valuation", timeout=25)
    if gap:
        return [], [f"Tickertape peers for {sid}: {gap}"]
    out = []
    for r in ((blob or {}).get("data") or []):
        if r.get("sid") == sid:
            continue
        ratios = r.get("ratios") or {}
        out.append({"symbol": _norm(r.get("ticker")), "name": r.get("name"),
                    "sid": r.get("sid"), "ttm_pe": _f(ratios.get("ttmPe")),
                    "pb": _f(ratios.get("pbr"))})
    return out, ([] if out else [f"Tickertape lists no peers for {sid}"])


_TT_SECTIONS = {"ratios": _ratios, "pnl_10y": _pnl_10y,
                "balance_sheet_10y": _balance_sheet_10y, "cash_flow_10y": _cash_flow_10y,
                "quarters": _quarters, "shareholding": _shareholding, "peers": _peers}

_EMPTY = {"ratios": {}, "pnl_10y": _EMPTY_TABLE, "balance_sheet_10y": _EMPTY_TABLE,
          "cash_flow_10y": _EMPTY_TABLE, "quarters": _EMPTY_TABLE,
          "shareholding": _EMPTY_TABLE, "peers": [],
          "documents": {"annual_reports": [], "concalls": []}}


def _blank(section):
    """A fresh empty value for a section — never a shared mutable default."""
    return copy.deepcopy(_EMPTY[section])


def _has_data(section, value):
    if section == "documents":
        return isinstance(value, dict) and any(value.get(k) for k in ("annual_reports", "concalls"))
    if section in {"pnl_10y", "balance_sheet_10y", "cash_flow_10y", "quarters", "shareholding"}:
        return (isinstance(value, dict) and bool(value.get("columns"))
                and isinstance(value.get("rows"), dict)
                and any(isinstance(series, list) and any(v is not None for v in series)
                        for series in value["rows"].values()))
    return bool(value)


def _fetch_section(section, identity):
    """Isolate a malformed provider response to its own typed section."""
    try:
        value, gaps = (_documents(identity) if section == "documents"
                       else _TT_SECTIONS[section](identity))
        if not _has_data(section, value):
            return _blank(section), gaps or [f"{section}: no usable data returned for {identity}"]
        return value, gaps
    except Exception as exc:
        return _blank(section), [f"{section} for {identity}: response could not be read ({type(exc).__name__})"]


def _select(env, sections):
    """Narrow a company envelope to `sections` (None keeps all), always keeping the
    identity fields and listing which sections this narrowed response carries. That set is
    what was fetched, not the company's full section set — a narrowed read never queries the
    others, so it cannot report them."""
    (env.get("data") or {}).pop(CACHE_STAMP, None)  # our bookkeeping, not the contract
    if not sections:
        return env
    data = env.get("data") or {}
    keep = set(sections) | set(_IDENTITY)
    env["data"] = {k: v for k, v in data.items() if k in keep}
    env["data"]["sections_returned"] = sorted(k for k in env["data"] if k in _SECTIONS)
    env["ok"] = any(_has_data(k, env["data"].get(k)) for k in sections)
    return env


def fetch(symbol, sections=None, fresh=False, sid=None):
    """Read one company's fundamentals into the typed envelope.

    `sections` narrows both the answer and the work: only the endpoints behind the sections
    asked for are called, which is what keeps `get_documents` to a single screener fetch.
    A narrowed read therefore does not populate the day cache — only a full one does.

    `sid` is the escape hatch for when ticker->sid resolution is broken (a rename Tickertape
    search cannot reach): pass the known Tickertape sid and the symbol->sid hop is skipped, so
    the full Tickertape path — 10y statements, peers, shareholding — still works instead of
    degrading to a hand-built read. The caller owns the sid's correctness.
    """
    sym = _norm(symbol)
    identity = {"symbol": sym, "name": None, "sid": None}
    if (not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9&_.-]*", sym)
            or sid is not None and (not isinstance(sid, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9&_.-]*", sid.strip()))):
        return _envelope(False, None, identity, ["invalid NSE symbol or Tickertape security id"])
    if sections is not None and (not isinstance(sections, (list, tuple))
            or any(not isinstance(s, str) or s not in _SECTIONS for s in sections)):
        return _envelope(False, None, identity, [f"sections must be a list drawn from {', '.join(_SECTIONS)}"])
    want = set(sections or _SECTIONS)
    sid = sid.strip() if sid is not None else None
    cache_file, cached, gaps = None, None, []
    try:
        key = hashlib.sha256(repr((sym, sid)).encode()).hexdigest()
        cache_file = os.path.join(paths.cache_dir("fundamentals"), f"company-v2-{key}.json")
        cached = _read_cache(cache_file, fresh)
    except OSError:
        gaps.append("fundamentals cache unavailable; fetched without cache")
    if (cached is not None and cached["data"].get("symbol") == sym
            and (sid is None or cached["data"].get("sid") == sid)
            and want <= set(cached["data"])):
        return _select(cached, sections)

    data = identity
    data.update({k: _blank(k) for k in want})
    sources = []

    tt_want = sorted(want - {"documents"})
    if tt_want:
        if sid:
            rec, gap = {"sid": str(sid).strip(), "name": None}, None
        else:
            rec, gap = tickertape.resolve_sid(sym, fresh=fresh)
        if gap:
            gaps.append(gap)
        else:
            data["sid"], data["name"] = rec["sid"], rec.get("name")
            sources.append("Tickertape")
            with ThreadPoolExecutor(max_workers=len(tt_want)) as pool:
                results = pool.map(lambda s: _fetch_section(s, rec["sid"]), tt_want)
                for section, (value, section_gaps) in zip(tt_want, results):
                    data[section] = value
                    gaps += section_gaps

    if "documents" in want:
        data["documents"], doc_gaps = _fetch_section("documents", sym)
        gaps += doc_gaps
        sources.append("screener.in (document index)")

    ok = any(_has_data(s, data[s]) for s in want)
    env = _envelope(ok, " + ".join(sources) or "Tickertape + screener.in", data, gaps)
    if ok and want == set(_SECTIONS) and cache_file:
        _write_cache(cache_file, {**env, "data": dict(env["data"])})
    return _select(env, sections)


# --- the fundamental screen ------------------------------------------------- #

# Only `g` and `l` are real operators: the endpoint answers an unrecognised one with an
# empty result rather than an error, so an inclusive comparison must be refused, never
# approximated to a strict one.
_OPS = {">": "g", "<": "l"}

# Quoted back at a caller whose field name did not resolve, so a query can be corrected
# without pulling the 179 KB filter catalogue to find out what exists.
COMMON_FIELDS = ("Market Cap", "PE Ratio", "TTM PE Ratio", "PB Ratio", "ROCE",
                 "Return on Equity", "Debt to Equity", "Interest Coverage Ratio",
                 "Net Profit Margin", "1Y Historical Revenue Growth",
                 "5Y Historical Revenue Growth", "1Y Historical EPS Growth",
                 "Promoter Holding", "Dividend Yield")

_CLAUSE_RE = re.compile(r"^\s*(?P<field>.+?)\s*(?P<op>>=|<=|>|<|=)\s*(?P<value>-?[\d.]+)\s*$")
_FILTER_MAX_AGE_DAYS = 7


def _norm_name(text):
    """A field name reduced to comparable form: case, punctuation and spacing folded."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).split())


def _catalogue(fresh=False):
    """`({normalised name: field label}, premium_labels, gap)` from the screener's own
    published filter list — the authority on which names exist and which are paywalled."""
    cache = tickertape.cache_path("meta", "screener-filters")
    cached = _read_cache(cache, fresh, max_age_days=_FILTER_MAX_AGE_DAYS)
    if cached is None:
        blob, gap = tickertape.get_json("/screener/filters", timeout=45)
        if gap:
            return {}, set(), f"Tickertape filter catalogue: {gap}"
        names, premium = {}, []
        for group in ((blob or {}).get("data") or {}).values():
            for item in group or []:
                label = item.get("label")
                if not label:
                    continue
                if item.get("premium"):
                    premium.append(label)
                for alias in (label, item.get("display"), item.get("short")):
                    # An absent alias folds to "", which every field name starts with —
                    # it would make the prefix match resolve anything to this one field.
                    if _norm_name(alias):
                        names.setdefault(_norm_name(alias), label)
        if not names:
            return {}, set(), "Tickertape filter catalogue carried no fields"
        cached = {"data": {"names": names, "premium": premium}}
        _write_cache(cache, cached)
    return cached["data"]["names"], set(cached["data"]["premium"]), None


def _resolve_field(name, names):
    """`(label, gap)` for one query field name, matched against the published catalogue.

    Only published aliases and the documented Market Capitalization spelling resolve.
    Prefixes suggest corrections; they cannot turn an unknown period/metric into another.
    """
    key = _norm_name(name)
    if key == "market capitalization" and key not in names:
        key = "market cap"
    if key in names:
        return names[key], None
    hits = sorted({label for alias, label in names.items()
                   if alias.startswith(key) or key.startswith(alias)})
    if hits:
        return None, f"{name!r} is not a published field alias — possible fields: {', '.join(hits[:6])}"
    return None, (f"{name!r} is not a Tickertape screener field. The names a quality cut "
                  f"usually wants: {', '.join(COMMON_FIELDS)}. "
                  f"GET {tickertape.BASE}/screener/filters lists every one.")


def _parse_query(query, names, premium):
    """`(match, gaps)` for a whole query string. `match` is None when anything is refused."""
    clauses = re.split(r"\s+AND\s+", str(query or ""), flags=re.I)
    if not any(c.strip() for c in clauses):
        return None, ["empty screen query"]

    match, gaps = {}, []
    for clause in clauses:
        m = _CLAUSE_RE.match(clause)
        if not m:
            gaps.append(f"cannot parse {clause.strip()!r} — expected FIELD > VALUE "
                        f"or FIELD < VALUE, joined by AND")
            continue
        op = _OPS.get(m.group("op"))
        if not op:
            gaps.append(f"{clause.strip()!r} uses {m.group('op')!r}; the Tickertape "
                        f"screener supports only > and <")
            continue
        label, gap = _resolve_field(m.group("field"), names)
        if gap:
            gaps.append(gap)
            continue
        if label in premium:
            gaps.append(f"{m.group('field').strip()!r} ({label}) is a paywalled Tickertape "
                        f"field — the endpoint refuses the whole query for it")
            continue
        value = _f(m.group("value"))
        if value is None:
            gaps.append(f"{clause.strip()!r} requires a finite numeric threshold")
            continue
        bounds = match.setdefault(label, {})
        bounds[op] = (max if op == "g" else min)(bounds.get(op, value), value)
    for label, bounds in match.items():
        if "g" in bounds and "l" in bounds and bounds["g"] >= bounds["l"]:
            gaps.append(f"{label}: contradictory strict lower and upper bounds")
    return (None if gaps else match), gaps


def screen(query, limit=1000, fresh=False):
    """Run a fundamental screen on Tickertape → candidate symbol list envelope.

    Every clause must resolve: a query that half-resolves would return a superset of what
    was asked for, and a candidate that never passed the quality cut looks identical to one
    that did.
    """
    empty = {"query": query, "count": 0, "candidates": []}
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        return _envelope(False, "Tickertape", empty, ["screen limit must be a positive integer"])
    # Old caches contain candidates accepted without validating the returned projection.
    key = hashlib.sha256(f"validated-v2|{query}|{limit}".encode("utf-8")).hexdigest()[:20]
    cache = tickertape.cache_path("screen", key)
    cached = _read_cache(cache, fresh)
    if cached is not None:
        cached["data"].pop(CACHE_STAMP, None)
        return cached

    names, premium, gap = _catalogue(fresh=fresh)
    if gap:
        return _envelope(False, "Tickertape", empty, [gap])

    match, gaps = _parse_query(query, names, premium)
    if match is None:
        return _envelope(False, "Tickertape", empty, gaps)

    blob, gap = tickertape.get_json(
        "/screener/query", timeout=45,
        payload={"match": match, "sortBy": "mrktCapf", "sortOrder": -1,
                 "project": sorted(set(match) | {"mrktCapf"}),
                 "offset": 0, "count": int(limit)})
    if gap:
        return _envelope(False, "Tickertape", empty, [f"screen fetch: {gap}"])

    response = blob.get("data") if isinstance(blob, dict) else None
    rows = response.get("results") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        return _envelope(False, "Tickertape", empty, ["screen response has no valid results list"])
    candidates, seen, rejected = [], set(), 0
    for row in rows:
        stock = row.get("stock") if isinstance(row, dict) else None
        info = stock.get("info") if isinstance(stock, dict) else None
        projected = stock.get("advancedRatios") if isinstance(stock, dict) else None
        ticker = info.get("ticker") if isinstance(info, dict) else None
        sym = _norm(ticker) if isinstance(ticker, str) else ""
        valid = bool(sym) and isinstance(projected, dict)
        if valid:
            for field, bounds in match.items():
                value = _f(projected.get(field))
                if (value is None or ("g" in bounds and value <= bounds["g"])
                        or ("l" in bounds and value >= bounds["l"])):
                    valid = False
                    break
        if not valid:
            rejected += 1
            continue
        if sym and sym not in seen:
            seen.add(sym)
            candidates.append(sym)

    candidates = candidates[:limit]
    if rejected:
        gaps.append(f"screen: excluded {rejected} rows with missing identity, unavailable "
                    "projected values or values that fail the requested bounds")
    stats = response.get("stats")
    total = _f(stats.get("count")) if isinstance(stats, dict) else None
    data = {"query": query, "count": len(candidates), "candidates": candidates}
    if total is not None and total > len(rows):
        gaps.append(f"source reports {total:g} matches; only {len(rows)} rows were supplied "
                    "for verification (raise `limit` for broader coverage)")
    if len(seen) > limit:
        gaps.append(f"screen: returned the first {limit} verified candidates in source order")
    if not candidates:
        gaps.append("screen returned no verifiable candidates")
    env = _envelope(bool(candidates), "Tickertape", data, gaps)
    if candidates:
        _write_cache(cache, {**env, "data": dict(data)})
    return env
