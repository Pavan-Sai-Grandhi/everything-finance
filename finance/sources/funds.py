#!/usr/bin/env python3
"""Mutual-fund fetch — identity, category screen, FULL holdings, NAV history.

Holdings come from Tickertape's public JSON API (free, no auth), which returns the
complete current allocation at 90-99% weight coverage. Never source them from a personal
MCP: that feed caps at 20 rows while funds hold 64-278 positions, so a look-through built
on it describes a different fund (CLAUDE.md rule 3). AMFI's NAVAll.txt is the authority for
scheme code + ISIN, and its half-yearly average-market-capitalisation workbook is the
authority for the SEBI cap rank; mfapi.in serves the daily NAV series the return math
runs on.

This module FETCHES ONLY — no grade, no verdict, no weighted aggregation. Turning holdings
into portfolio ratios is `finance/compute/lookthrough.py`'s job.

Returns the shared data-spine envelope (finance/contracts.md).

Reached through: resolve_fund, screen_funds, get_fund_holdings, get_nav_history,
get_stock_ratios.
"""
from __future__ import annotations

import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from finance import caps
from finance import deps
from finance import paths
from finance import transport
from finance.sources import tickertape
from finance.spine import (envelope as _envelope, f as _f, iso_date as _iso_date,
                           norm_symbol as _norm_symbol,
                           read_cache as _read_cache, write_cache as _write_cache)

_AMFI_NAV_ALL = "https://portal.amfiindia.com/spages/NAVAll.txt"
_AMFI_CAP_INDEX = "https://www.amfiindia.com/otherdata/categorisation-of-stocks"
_AMFI_HOST = "https://www.amfiindia.com"
_MFAPI = "https://api.mfapi.in/mf"

# AMFI republishes the classification half-yearly, so unlike the weekly NAVAll.txt this
# 582 KB workbook is stable for months. 30 days re-checks often enough to pick a new
# period up within a month of its publication without refetching it every week.
_CAP_LIST_MAX_AGE_DAYS = 30

# Both an <a href> and an escaped JSON blob on the index page carry the link; the class
# excludes the quote and backslash that delimit either form.
_CAP_XLSX_RE = re.compile(r"""[^\s"'<>\\()]*AverageMarketCapitalization[^\s"'<>\\()]*\.xlsx""",
                          re.I)
_CAP_PERIOD_RE = re.compile(r"(\d{1,2})([A-Za-z]{3,9})(\d{4})\.xlsx$", re.I)

# Header prefixes of the five columns worth keeping, matched case-folded so a reworded
# unit suffix ("in (Rs. Crs.)" vs "(Rs Crs.)") cannot shift a column.
_CAP_COLUMNS = {"rank": "sr. no", "name": "company name", "isin": "isin",
                "symbol": "nse symbol", "avg_mcap_cr": "average of all exchanges"}

# The screener fields that are free on the public endpoint. Tickertape 403s the whole
# request (not just the field) when a premium one is asked for, and names the offenders —
# so the restricted set is pinned here rather than rediscovered by a failed run.
SCREEN_FIELDS = [
    "aum", "subsector", "option", "expRatio", "navClose", "ageInMon",
    "ret1y", "ret3y", "ret5y", "ret6m", "ret3m",
    "sharpe", "sortino", "alpha", "stdDevAnn", "trackErr",
    "percSmallcap", "percMidcap", "percLargecap", "percEquityH",
    "pe", "catPe", "minSipAmount", "exitLoad",
]
PREMIUM_FIELDS = {"maxDrawdown", "avg3yRollingRet", "percTop10H", "percTop3H",
                  "percTop5H", "ret3yVsCat", "ret1yVsCat", "ret5yVsCat", "cashncasheq"}

def _cache_path(kind, key):
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(key))
    return os.path.join(paths.cache_dir(os.path.join("mf", kind)), f"{safe}.json")

def amfi_index(fresh=False):
    """The full AMFI scheme list — the authority for scheme code + ISIN + exact name.

    Name resolution goes through this file rather than mfapi's `/search` for two
    measured reasons (verified 2026-08-16): the search is a substring match on the
    registered name, so "TRUST Small Cap" returns **nothing** (AMFI registers it as
    "TRUSTMF"); and it **caps at 15 results with no pagination**, so the broad query you
    would fall back to ("Small Cap Fund") silently omits most of the category — the same
    truncation trap as the IndMoney holdings cap. This file is the complete registry.
    ~17.8k rows, cached for a week, so the cost is one fetch per week.
    Returns the envelope with `data.schemes = [{code, isin, name, nav, nav_date}]`, where
    `name` is the full registered scheme name — the file carries the fund name, the plan
    and the option in three separate columns, and it is the three together that identify
    a scheme. The fund name alone is shared by every plan/option variant of the fund, so
    matching on it would pick an IDCW or Regular series at random.
    """
    cache = _cache_path("meta", "amfi-navall")
    cached = _read_cache(cache, fresh, max_age_days=7)
    if cached is not None:
        return cached

    body, gap = transport.request(_AMFI_NAV_ALL, timeout=60,
                                  referer="https://www.amfiindia.com/")
    if gap:
        return _envelope(False, "AMFI", {"schemes": []}, [f"AMFI NAVAll: {gap}"])

    schemes = []
    for line in (body or "").splitlines():
        parts = line.split(";")
        if len(parts) < 8 or not parts[0].strip().isdigit():
            continue
        schemes.append({
            "code": parts[0].strip(),
            "isin": parts[1].strip() if parts[1].strip() != "-" else None,
            "name": " - ".join(p for p in (parts[3].strip(), parts[4].strip(),
                                           parts[5].strip()) if p),
            "nav": _f(parts[6]),
            "nav_date": parts[7].strip(),
        })
    gaps = [] if schemes else ["AMFI NAVAll returned no parseable scheme rows"]
    env = _envelope(bool(schemes), "AMFI", {"schemes": schemes, "count": len(schemes)}, gaps)
    if schemes:
        _write_cache(cache, env)
    return env


def _cap_xlsx_link(html):
    """Newest `AverageMarketCapitalization*.xlsx` link on the index page.

    Returns `(url, period, gap)`. The filename encodes the six months it covers, so the
    period is what orders the candidates — the page lists every past edition alongside
    the current one, in no dependable order.
    """
    best = None
    for hit in _CAP_XLSX_RE.findall(html or ""):
        m = _CAP_PERIOD_RE.search(hit)
        if not m:
            continue
        day, month, year = m.groups()
        period = _iso_date(f"{day}-{month}-{year}")
        if period and (best is None or period > best[1]):
            best = (hit, period)
    if not best:
        return None, None, ("AMFI categorisation page listed no dated "
                            "AverageMarketCapitalization .xlsx link")
    url = best[0]
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = _AMFI_HOST + url
    return url, best[1], None


def _parse_cap_xlsx(path):
    """The workbook -> `({key: {rank, name, isin, symbol, avg_mcap_cr}}, gap)`.

    Keyed on NSE Symbol, falling back to ISIN for the ~3.1k rows listed on BSE only, so a
    BSE-only holding is still rankable.
    """
    try:
        openpyxl = deps.need("openpyxl")
    except Exception as exc:  # noqa: BLE001 — a missing parser is a gap, not a crash
        return {}, f"openpyxl unavailable, AMFI cap list unparsed ({exc})"
    try:
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        rows = list(book[book.sheetnames[0]].iter_rows(values_only=True))
    except Exception as exc:  # noqa: BLE001
        return {}, f"AMFI cap workbook unreadable ({exc})"

    def cell(row, cols, key):
        """One column of one row, tolerating a short row and an absent column."""
        idx = cols[key]
        return row[idx] if idx is not None and idx < len(row) else None

    cols, stocks = None, {}
    for row in rows:
        cells = [str(c).strip().lower() if c is not None else "" for c in row]
        if cols is None:
            if any(c.startswith(_CAP_COLUMNS["rank"]) for c in cells):
                cols = {k: next((i for i, c in enumerate(cells) if c.startswith(v)), None)
                        for k, v in _CAP_COLUMNS.items()}
            continue
        rank = _f(cell(row, cols, "rank"))
        if rank is None:
            continue
        rec = {"rank": int(rank)}
        for field in ("name", "isin", "symbol"):
            raw = cell(row, cols, field)
            val = str(raw).strip() if raw is not None else ""
            rec[field] = val if val and val != "-" else None
        rec["symbol"] = _norm_symbol(rec["symbol"]) or None
        rec["avg_mcap_cr"] = _f(cell(row, cols, "avg_mcap_cr"))
        key = rec["symbol"] or rec["isin"]
        if key:
            stocks[key] = rec
    if cols is None:
        return {}, "AMFI cap workbook carried no recognisable header row"
    return stocks, None if stocks else "AMFI cap workbook carried no ranked rows"


def amfi_cap_list(fresh=False):
    """The SEBI market-cap classification straight from AMFI, the publisher of record.

    `data = {period, url, count, stocks:{<NSE symbol or ISIN>: {rank, name, isin, symbol,
    avg_mcap_cr}}}`, where `rank` is the `Sr. No.` column — SEBI's classification IS that
    rank. Link discovery is dynamic because the filename encodes the period; a failed
    resolution is a labelled gap.
    """
    cache = _cache_path("meta", "amfi-cap-list")
    cached = _read_cache(cache, fresh, max_age_days=_CAP_LIST_MAX_AGE_DAYS)
    if cached is not None:
        return cached

    empty = {"period": None, "url": None, "count": 0, "stocks": {}}
    html, gap = transport.request(_AMFI_CAP_INDEX, timeout=40, referer=_AMFI_HOST)
    if gap:
        return _envelope(False, "AMFI", empty, [f"AMFI cap-list index: {gap}"])
    url, period, gap = _cap_xlsx_link(html)
    if gap:
        return _envelope(False, "AMFI", empty, [gap])

    # pid-scoped: two sessions downloading the same period must not overwrite each
    # other's file mid-parse.
    dest = os.path.join(paths.tmp_dir("mf"), f"amfi-cap-list-{os.getpid()}.xlsx")
    saved, gap = transport.request(url, timeout=120, referer=_AMFI_CAP_INDEX,
                                   dest=dest)
    if gap:
        return _envelope(False, "AMFI", dict(empty, period=period, url=url),
                         [f"AMFI cap workbook: {gap}"])
    stocks, gap = _parse_cap_xlsx(saved)
    try:
        os.unlink(saved)
    except OSError:
        pass

    data = {"period": period, "url": url, "count": len(stocks), "stocks": stocks}
    env = _envelope(bool(stocks), "AMFI", data, [gap] if gap else [])
    if stocks:
        _write_cache(cache, env)
    return env


_cap_lock = threading.Lock()
_cap_index_memo = None


def _cap_index(fresh=False):
    """Process-wide `(by_key, by_isin, period, gaps)` view of the cap list.

    Memoised because `enrich` prices up to 278 holdings in a thread pool: without this
    every position would reload — and on a cold cache refetch — the same workbook.
    """
    global _cap_index_memo  # noqa: PLW0603 — one memo for the process, guarded by the lock
    with _cap_lock:
        if _cap_index_memo is None or fresh:
            env = amfi_cap_list(fresh=fresh)
            stocks = (env.get("data") or {}).get("stocks") or {}
            by_isin = {r["isin"]: r for r in stocks.values() if r.get("isin")}
            _cap_index_memo = (stocks, by_isin, (env.get("data") or {}).get("period"),
                               list(env.get("gaps") or []))
        return _cap_index_memo


def _cap_rank(ticker, isin=None):
    """`(rank, label, gaps)` for one listed company from the AMFI cap list.

    Deliberately blind to a caller's `fresh`: that means "today's quote", and the cap list
    is republished twice a year.
    """
    by_key, by_isin, period, gaps = _cap_index()
    rec = by_key.get(_norm_symbol(ticker)) or (by_isin.get(isin) if isin else None)
    if rec:
        return float(rec["rank"]), caps.cap_label(rec["rank"]), list(gaps)
    unranked = (f"{ticker or isin or 'holding'} is unranked in the AMFI cap list for "
                f"{period or 'the current period'} — cap falls back to the provider label")
    return None, None, list(gaps) + [unranked]


def _token_hit(token, name_lower, name_words):
    """Does `token` match this scheme name, allowing a word-prefix match?

    An AMC's registered AMFI name is often a longer word than the name people use:
    "TRUST Small Cap" is registered as "TRUSTMF SMALL CAP FUND". A plain substring test
    over the whole name would also let "iti" match inside "MULTI", so the prefix match is
    anchored to word boundaries."""
    return token in name_lower or any(w.startswith(token) for w in name_words)


def _score_name(query, name):
    """Token-overlap score of a query against an AMFI scheme name. Direct+Growth is
    preferred because that is the only plan this plugin ever recommends."""
    q = {t for t in query.lower().replace("-", " ").split() if t}
    n = name.lower()
    words = n.replace("-", " ").replace("(", " ").replace(")", " ").split()
    hits = sum(1 for t in q if _token_hit(t, n, words))
    if hits < len(q):
        return -1
    score = 100 - abs(len(n) - len(query))
    if "direct" in n:
        score += 50
    if "growth" in n:
        score += 30
    if any(w in n for w in ("idcw", "dividend", "payout", "bonus")):
        score -= 40
    return score


def resolve(name, fresh=False):
    """Fund name -> identity across all three systems, preferring Direct-Growth.

    Returns `data = {query, scheme_code, isin, amfi_name, plan, mf_id, tickertape_name}`.
    A missing `mf_id` (no Tickertape match) is a labelled gap, not a failure — NAV-based
    performance still works without it; only look-through does not.
    """
    out = {"query": name, "scheme_code": None, "isin": None, "amfi_name": None,
           "plan": None, "mf_id": None, "tickertape_name": None}
    gaps = []

    idx = amfi_index(fresh=fresh)
    best, best_score = None, 0
    for s in (idx.get("data") or {}).get("schemes", []):
        sc = _score_name(name, s["name"])
        if sc > best_score:
            best, best_score = s, sc
    if best:
        # The plan is read off the registered name, and several AMCs (SBI, HSBC, Motilal)
        # leave AMFI's plan column blank — that is an unknown plan, not a Regular one.
        lower = best["name"].lower()
        plan = "Direct" if "direct" in lower else ("Regular" if "regular" in lower else None)
        out.update(scheme_code=best["code"], isin=best["isin"], amfi_name=best["name"],
                   plan=plan)
        if plan == "Regular":
            gaps.append(f"only a Regular plan matched {name!r} — expense ratio will "
                        f"overstate a Direct-plan investor's cost")
        elif plan is None:
            gaps.append(f"AMFI names no plan for {name!r} — plan unverified; if it is a "
                        f"Regular plan its expense ratio overstates a Direct-plan cost")
    else:
        gaps.append(f"no AMFI scheme matched {name!r}")
    gaps += idx.get("gaps", [])

    hit, tt_gap = _tickertape_fund(name)
    if hit:
        out.update(mf_id=hit["mf_id"], tickertape_name=hit["name"])
    else:
        gaps.append(tt_gap or f"no Tickertape fund matched {name!r} — look-through "
                              f"holdings unavailable for it")
    return _envelope(bool(out["scheme_code"] or out["mf_id"]), "AMFI+Tickertape", out, gaps)


def _tickertape_fund(name):
    """Best Tickertape fund match for a name, via the screener's own listing."""
    env = screen(subsector=None, min_aum=0, limit_pages=12)
    rows = (env.get("data") or {}).get("funds") or []
    if not rows:
        return None, "Tickertape fund list unavailable"
    want = {t for t in name.lower().replace("-", " ").split() if t
            and t not in {"fund", "direct", "growth", "plan"}}
    best, best_hits = None, 0
    for r in rows:
        n = r["name"].lower()
        hits = sum(1 for t in want if t in n)
        if hits > best_hits or (hits == best_hits and best and hits > 0
                                and len(r["name"]) < len(best["name"])):
            best, best_hits = r, hits
    if not best or best_hits < max(1, len(want) - 1):
        return None, f"no confident Tickertape match for {name!r}"
    return best, None


def screen(subsector="Small Cap Fund", option="Growth", min_aum=100,
           fields=None, limit_pages=12, fresh=False):
    """Every fund in a SEBI sub-category, with the metrics a shortlist is built from.

    The endpoint ignores string filters in `match` (any non-numeric match silently returns
    an empty result), so the numeric AUM floor is pushed server-side and `subsector`/
    `option` are projected and filtered here — verified 2026-08-16.

    `subsector=None` returns the whole universe (used by name resolution).
    Returns `data.funds = [{mf_id, name, slug, <metric fields>}]`.
    """
    fields = list(fields or SCREEN_FIELDS)
    bad = sorted(set(fields) & PREMIUM_FIELDS)
    gaps = []
    if bad:
        fields = [f for f in fields if f not in PREMIUM_FIELDS]
        gaps.append(f"dropped premium-gated Tickertape fields {bad} (computed from NAV "
                    f"history instead where needed)")

    cache = _cache_path("screen", f"{subsector or 'ALL'}-{option}-{min_aum}")
    cached = _read_cache(cache, fresh)
    if cached is not None:
        return cached

    funds, page = [], 0
    while page < limit_pages:
        payload = {"match": {"aum": {"g": float(min_aum)}},
                   "sortBy": "aum", "sortOrder": -1,
                   "project": fields, "offset": page * 500, "count": 500}
        blob, gap = tickertape.get_json("/mf-screener/query", payload=payload, timeout=45)
        if gap:
            gaps.append(f"Tickertape screener page {page}: {gap}")
            break
        if isinstance(blob, dict) and blob.get("statusCode") == 403:
            gaps.append(f"Tickertape screener refused fields: {blob.get('message')}")
            break
        rows = ((blob or {}).get("data") or {}).get("result") or []
        if not rows:
            break
        for r in rows:
            rec = {"mf_id": r.get("mfId"), "name": r.get("name"),
                   "slug": r.get("slug"), "category": r.get("sector")}
            for v in r.get("values", []):
                rec[v.get("filter")] = v.get("doubleVal", v.get("strVal"))
            funds.append(rec)
        if len(rows) < 500:
            break
        page += 1

    if subsector:
        funds = [f for f in funds if f.get("subsector") == subsector]
    if option:
        funds = [f for f in funds if f.get("option") == option]
    funds.sort(key=lambda f: -(f.get("aum") or 0))

    if not funds and not gaps:
        gaps.append(f"no funds matched subsector={subsector!r} option={option!r}")
    env = _envelope(bool(funds), "Tickertape",
                    {"subsector": subsector, "option": option, "min_aum": min_aum,
                     "count": len(funds), "funds": funds}, gaps)
    if funds:
        _write_cache(cache, env)
    return env


def holdings(mf_id, fresh=False):
    """A fund's full current allocation — every position, not a top-20 slice.

    Returns `data = {mf_id, positions:[{sid, ticker, name, weight, change3m, type}],
    equity_weight, sector_weights, allocation_history, position_count}`.

    `sid` (not `ticker`) is the join key to `stock_ratios` — they genuinely differ
    (REC is ticker RECLTD, sid RECM), and guessing the sid 404s. Unlisted holdings appear
    with a weight but will carry no ratios; their weight must be counted as unpriced, never
    dropped, or coverage silently overstates itself.
    """
    cache = _cache_path("holdings", mf_id)
    cached = _read_cache(cache, fresh, max_age_days=7)
    if cached is not None:
        return cached

    blob, gap = tickertape.get_json(f"/mutualfunds/{mf_id}/holdings", timeout=40)
    if gap:
        return _envelope(False, "Tickertape", {"mf_id": mf_id, "positions": []},
                         [f"Tickertape holdings for {mf_id}: {gap}"])
    d = (blob or {}).get("data") or blob or {}
    alloc = d.get("currentAllocation") or []
    if not alloc:
        return _envelope(False, "Tickertape", {"mf_id": mf_id, "positions": []},
                         [f"Tickertape returned no currentAllocation for {mf_id}"])

    positions, equity_w = [], 0.0
    for row in alloc:
        w = _f(row.get("latest"))
        if w is None:
            continue
        rec = {"sid": row.get("sid"), "ticker": row.get("ticker"),
               "name": row.get("title"), "weight": w,
               "change3m": _f(row.get("change3m")), "type": row.get("type")}
        positions.append(rec)
        if str(row.get("type", "")).lower() == "equity":
            equity_w += w

    sector_w = {}
    for row in (d.get("sectorWeightage") or d.get("sectorDistribution") or []):
        if isinstance(row, dict):
            key = row.get("name") or row.get("title") or row.get("sector")
            val = _f(row.get("latest") if row.get("latest") is not None else row.get("value"))
            if key and val is not None:
                sector_w[key] = val

    data = {
        "mf_id": mf_id,
        "position_count": len(positions),
        "equity_weight": round(equity_w, 2),
        "positions": positions,
        "sector_weights": sector_w,
        "allocation_history": d.get("assetAllocationHistory") or [],
    }
    gaps = []
    if equity_w and equity_w < 60:
        gaps.append(f"equity weight only {equity_w:.1f}% — treat as a hybrid/cash-heavy book")
    env = _envelope(True, "Tickertape", data, gaps)
    _write_cache(cache, env)
    return env


def stock_ratios(sid, fresh=False):
    """One holding's ratios. Returns `data = {sid, ticker, name, sector, pe, ttm_pe, pb,
    roe, market_cap_cr, cap_rank, cap_label, div_yield, beta, industry_pe}`.

    `cap_rank` is AMFI's published market-cap RANK — the thing SEBI actually classifies
    caps by, so a downstream cap-tilt is a fact rather than an inference from ₹Cr bands.
    Everything else is Tickertape's sid-joined ratio feed.
    """
    cache = _cache_path("stocks", sid)
    cached = _read_cache(cache, fresh, max_age_days=5)
    if cached is not None:
        return cached

    blob, gap = tickertape.get_json(f"/stocks/info/{sid}", timeout=25)
    if gap:
        return _envelope(False, "Tickertape", {"sid": sid}, [f"ratios for {sid}: {gap}"])
    d = (blob or {}).get("data") or {}
    info, rat = d.get("info") or {}, d.get("ratios") or {}
    if not rat:
        return _envelope(False, "Tickertape", {"sid": sid},
                         [f"no ratios published for {sid} (unlisted or newly listed)"])
    rank, label, gaps = _cap_rank(info.get("ticker"), info.get("isin"))
    data = {
        "sid": sid,
        "ticker": info.get("ticker"),
        "name": info.get("name"),
        "sector": info.get("sector"),
        "pe": _f(rat.get("pe")),
        "ttm_pe": _f(rat.get("ttmPe")),
        "pb": _f(rat.get("pb")),
        "roe": _f(rat.get("roe")),
        "eps": _f(rat.get("eps")),
        "market_cap_cr": _f(rat.get("marketCap")),
        "cap_rank": rank,
        "cap_label": label or rat.get("marketCapLabel"),
        "div_yield": _f(rat.get("divYield")),
        "beta": _f(rat.get("beta")),
        "industry_pe": _f(rat.get("indpe")),
        "industry_pb": _f(rat.get("indpb")),
    }
    env = _envelope(True, "AMFI+Tickertape", data, gaps)
    _write_cache(cache, env)
    return env


def enrich(positions, workers=10, fresh=False):
    """Attach ratios to every equity position, in parallel and cached.

    Parallel and cached because serial enrichment of a 278-position book is slow enough to
    tempt a caller into hand-typing holdings JSON — the exact fabrication the plugin
    forbids. Keeping the real path fast keeps the honest path the easy one.
    Returns (enriched_positions, gaps).
    """
    equity = [p for p in positions if str(p.get("type", "")).lower() == "equity"]
    sids = [p["sid"] for p in equity if p.get("sid")]
    ratios, gaps, cap_period = {}, [], None
    if sids:
        # Prime the cap list before the pool: one workbook fetch for the whole book.
        _, _, cap_period, cap_gaps = _cap_index()
        gaps += cap_gaps
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for sid, env in zip(sids, pool.map(lambda s: stock_ratios(s, fresh=fresh), sids)):
                if env.get("ok"):
                    ratios[sid] = env["data"]
                else:
                    gaps += env.get("gaps", [])

    out = []
    for p in equity:
        rec = dict(p)
        rec.update(ratios.get(p.get("sid"), {}) or {})
        rec["priced"] = p.get("sid") in ratios
        out.append(rec)
    unpriced_w = round(sum(p["weight"] for p in out if not p["priced"]), 2)
    if unpriced_w:
        gaps.append(f"{unpriced_w}% of the book is unpriced (unlisted/newly-listed "
                    f"holdings) — excluded from ratios, never extrapolated")
    unranked_w = round(sum(p["weight"] for p in out
                           if p["priced"] and p.get("cap_rank") is None), 2)
    if unranked_w:
        gaps.append(f"{unranked_w}% of the book is unranked in the AMFI cap list for "
                    f"{cap_period or 'the current period'} — cap-tilt falls back to the "
                    f"provider label for that weight")
    return out, gaps


def nav_history(scheme_code, fresh=False):
    """Full daily NAV series for a scheme. `data = {code, meta, navs:[{date, nav}]}`
    with dates as ISO and OLDEST FIRST (mfapi serves newest-first)."""
    cache = _cache_path("nav", scheme_code)
    cached = _read_cache(cache, fresh)
    if cached is not None:
        return cached

    blob, gap = transport.json_request(f"{_MFAPI}/{scheme_code}", timeout=45)
    if gap:
        return _envelope(False, "mfapi.in", {"code": scheme_code, "navs": []},
                         [f"mfapi {scheme_code}: {gap}"])
    rows = (blob or {}).get("data") or []
    navs = []
    for r in rows:
        # strptime, not split("-"): "not-a-date" splits into three parts just as happily
        # as a real date does and would be silently reassembled into "date-a-not",
        # poisoning the series with a row that sorts to the end and looks like the latest
        # NAV. A NAV series feeds every return calculation — it has to be parsed strictly.
        try:
            iso = datetime.strptime(str(r.get("date", "")).strip(), "%d-%m-%Y").date()
            navs.append({"date": iso.isoformat(), "nav": float(r["nav"])})
        except (ValueError, TypeError, KeyError):  # a bad row never kills the series
            continue
    navs.sort(key=lambda x: x["date"])
    gaps = [] if navs else [f"mfapi returned no NAV rows for {scheme_code}"]
    env = _envelope(bool(navs), "mfapi.in",
                    {"code": scheme_code, "meta": (blob or {}).get("meta") or {},
                     "count": len(navs), "navs": navs}, gaps)
    if navs:
        _write_cache(cache, env)
    return env
