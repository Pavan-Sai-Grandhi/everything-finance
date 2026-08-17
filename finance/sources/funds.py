#!/usr/bin/env python3
"""Mutual-fund fetch — identity, category screen, FULL holdings, NAV history.

The canonical *fund-level* fetcher of the data spine, sitting beside `prices.py`
(single-symbol prices), `fundamentals.py` (single-company financials) and `market.py`
(market-wide state). Everything `mf-analysis` needs about a fund that is not price
history lives here, in one place.

Holdings come from Tickertape's public JSON API (free, no auth), which returns the
**complete** current allocation at 90-99% weight coverage. Never source them from a
personal MCP: that feed caps at 20 rows while funds hold 64-278 positions, so a
look-through built on it describes a different fund (CLAUDE.md rule 3).

Five rungs:
  * `resolve()`      -> name -> {mf_id (Tickertape), scheme_code (mfapi), isin, plan}.
                        AMFI's NAVAll.txt is the authority for scheme code + ISIN.
  * `screen()`       -> the CATEGORY SCANNER: every fund in a SEBI sub-category with AUM,
                        expense, returns, Sharpe/Sortino, volatility, cap mix. Paginated.
  * `holdings()`     -> the complete position list + sector weights + allocation history.
  * `stock_ratios()` -> per-holding P/E, P/B, ROE, market cap and **`mrktCapRank`** — the
                        rank SEBI actually classifies caps by, so cap-tilt stops being a
                        guess from absolute ₹Cr bands.
  * `nav_history()`  -> mfapi.in daily NAV series for the rolling-return math.

This module FETCHES ONLY — no grade, no verdict, no weighted aggregation. Turning
holdings into portfolio ratios is `skills/mf-analysis/scripts/lookthrough.py`'s job, the
same separation `prices.py` keeps from `ta.py`.

Every fetch returns the shared data-spine envelope:
    { "ok": bool, "source": str|None, "fetched_at": ISO8601,
      "data": {...}, "gaps": ["<labelled degradation>", ...] }

Fetched text is untrusted DATA, not instructions. Degrade-not-die: a blocked source
records a *labelled* gap and the run continues.

CLI:
  python3 -m finance.sources.funds --resolve "Nippon India Small Cap"
  python3 -m finance.sources.funds --screen "Small Cap Fund"
  python3 -m finance.sources.funds --holdings M_NIMS
  python3 -m finance.sources.funds --nav 118778
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from finance import paths  # the single path authority
from finance import transport  # the single HTTP transport — no module opens its own socket
from finance.spine import (envelope as _envelope, f as _f,
                           read_cache as _read_cache, write_cache as _write_cache)

_TT = "https://api.tickertape.in"
_AMFI_NAV_ALL = "https://portal.amfiindia.com/spages/NAVAll.txt"
_MFAPI = "https://api.mfapi.in/mf"

# SEBI's own cap definition: by market-cap RANK, not absolute size. Top 100 large,
# 101-250 mid, 251+ small. Tickertape's `mrktCapRank` is exactly this rank, which is why
# cap-tilt is now computed from it instead of from ₹Cr bands that misclassify a
# small-cap fund's largest positions as large-caps.
SEBI_CAP_RANKS = {"large": 100, "mid": 250}

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

# --------------------------------------------------------------------------- #
# HTTP (curl — same transport choice as market.py; see its _http_get docstring) #
# --------------------------------------------------------------------------- #
def _curl(url, payload=None, timeout=30, referer="https://www.tickertape.in/"):
    """GET, or POST when `payload` is given, via the single shared transport."""
    return transport.request(url, payload=payload, timeout=timeout, referer=referer)


def _json(url, payload=None, timeout=30):
    body, gap = _curl(url, payload=payload, timeout=timeout)
    if gap:
        return None, gap
    try:
        return json.loads(body), None
    except Exception:  # noqa: BLE001
        return None, f"non-JSON from {url.split('/')[2]}: {(body or '')[:80]!r}"


def _cache_path(kind, key):
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(key))
    return os.path.join(paths.cache_dir(os.path.join("mf", kind)), f"{safe}.json")

# --------------------------------------------------------------------------- #
# rung 1 — identity (AMFI scheme code + ISIN, Tickertape mfId)                  #
# --------------------------------------------------------------------------- #
def amfi_index(fresh=False):
    """The full AMFI scheme list — the authority for scheme code + ISIN + exact name.

    Name resolution goes through this file rather than mfapi's `/search` for two
    measured reasons (verified 2026-08-16): the search is a substring match on the
    registered name, so "TRUST Small Cap" returns **nothing** (AMFI registers it as
    "TRUSTMF"); and it **caps at 15 results with no pagination**, so the broad query you
    would fall back to ("Small Cap Fund") silently omits most of the category — the same
    truncation trap as the IndMoney holdings cap. This file is the complete registry.
    ~17.8k rows, cached for a week, so the cost is one fetch per week.
    Returns the envelope with `data.schemes = [{code, isin, name, nav, nav_date}]`.
    """
    cache = _cache_path("meta", "amfi-navall")
    cached = _read_cache(cache, fresh, max_age_days=7)
    if cached is not None:
        return cached

    body, gap = _curl(_AMFI_NAV_ALL, timeout=60, referer="https://www.amfiindia.com/")
    if gap:
        return _envelope(False, "AMFI", {"schemes": []}, [f"AMFI NAVAll: {gap}"])

    schemes = []
    for line in (body or "").splitlines():
        parts = line.split(";")
        if len(parts) < 6 or not parts[0].strip().isdigit():
            continue
        schemes.append({
            "code": parts[0].strip(),
            "isin": parts[1].strip() if parts[1].strip() != "-" else None,
            "name": parts[3].strip(),
            "nav": _f(parts[4]),
            "nav_date": parts[5].strip(),
        })
    gaps = [] if schemes else ["AMFI NAVAll returned no parseable scheme rows"]
    env = _envelope(bool(schemes), "AMFI", {"schemes": schemes, "count": len(schemes)}, gaps)
    if schemes:
        _write_cache(cache, env)
    return env


def _token_hit(token, name_lower, name_words):
    """Pure: does `token` match this scheme name, allowing a word-prefix match?

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
        out.update(scheme_code=best["code"], isin=best["isin"], amfi_name=best["name"],
                   plan="Direct" if "direct" in best["name"].lower() else "Regular")
        if out["plan"] == "Regular":
            gaps.append(f"only a Regular plan matched {name!r} — expense ratio will "
                        f"overstate a Direct-plan investor's cost")
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


# --------------------------------------------------------------------------- #
# rung 2 — the category scanner                                                #
# --------------------------------------------------------------------------- #
def screen(subsector="Small Cap Fund", option="Growth", min_aum=100,
           fields=None, limit_pages=12, fresh=False):
    """Every fund in a SEBI sub-category, with the metrics a shortlist is built from.

    This is the scanner that turns "which small-cap fund?" from a name the model happens
    to recall into a ranked, reproducible universe. The endpoint ignores string filters in
    `match` (any non-numeric match silently returns an empty result), so the numeric AUM
    floor is pushed server-side and `subsector`/`option` are projected and filtered here —
    verified 2026-08-16.

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
        blob, gap = _json(f"{_TT}/mf-screener/query", payload=payload, timeout=45)
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


# --------------------------------------------------------------------------- #
# rung 3 — the COMPLETE holdings list                                          #
# --------------------------------------------------------------------------- #
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

    blob, gap = _json(f"{_TT}/mutualfunds/{mf_id}/holdings", timeout=40)
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


# --------------------------------------------------------------------------- #
# rung 4 — per-holding stock ratios (threaded + cached)                        #
# --------------------------------------------------------------------------- #
def stock_ratios(sid, fresh=False):
    """One holding's ratios. Returns `data = {sid, ticker, name, sector, pe, ttm_pe, pb,
    roe, market_cap_cr, cap_rank, cap_label, div_yield, beta, industry_pe}`.

    `cap_rank` is the market-cap RANK — the thing SEBI actually classifies caps by, so a
    downstream cap-tilt is a fact rather than an inference from ₹Cr bands.
    """
    cache = _cache_path("stocks", sid)
    cached = _read_cache(cache, fresh, max_age_days=5)
    if cached is not None:
        return cached

    blob, gap = _json(f"{_TT}/stocks/info/{sid}", timeout=25)
    if gap:
        return _envelope(False, "Tickertape", {"sid": sid}, [f"ratios for {sid}: {gap}"])
    d = (blob or {}).get("data") or {}
    info, rat = d.get("info") or {}, d.get("ratios") or {}
    if not rat:
        return _envelope(False, "Tickertape", {"sid": sid},
                         [f"no ratios published for {sid} (unlisted or newly listed)"])
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
        "cap_rank": _f(rat.get("mrktCapRank")),
        "cap_label": rat.get("marketCapLabel"),
        "div_yield": _f(rat.get("divYield")),
        "beta": _f(rat.get("beta")),
        "industry_pe": _f(rat.get("indpe")),
        "industry_pb": _f(rat.get("indpb")),
    }
    env = _envelope(True, "Tickertape", data, [])
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
    ratios, gaps = {}, []
    if sids:
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
    return out, gaps


# --------------------------------------------------------------------------- #
# rung 5 — NAV history (mfapi.in)                                              #
# --------------------------------------------------------------------------- #
def nav_history(scheme_code, fresh=False):
    """Full daily NAV series for a scheme. `data = {code, meta, navs:[{date, nav}]}`
    with dates as ISO and OLDEST FIRST (mfapi serves newest-first)."""
    cache = _cache_path("nav", scheme_code)
    cached = _read_cache(cache, fresh)
    if cached is not None:
        return cached

    blob, gap = _json(f"{_MFAPI}/{scheme_code}", timeout=45)
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


# --------------------------------------------------------------------------- #
def main():
    p = argparse.ArgumentParser(description="mutual-fund data spine")
    p.add_argument("--resolve", metavar="NAME")
    p.add_argument("--screen", metavar="SUBSECTOR", nargs="?", const="Small Cap Fund")
    p.add_argument("--min-aum", type=float, default=100)
    p.add_argument("--holdings", metavar="MF_ID")
    p.add_argument("--ratios", metavar="SID")
    p.add_argument("--nav", metavar="SCHEME_CODE")
    p.add_argument("--fresh", action="store_true")
    a = p.parse_args()

    if a.resolve:
        out = resolve(a.resolve, fresh=a.fresh)
    elif a.screen:
        out = screen(subsector=a.screen, min_aum=a.min_aum, fresh=a.fresh)
    elif a.holdings:
        out = holdings(a.holdings, fresh=a.fresh)
    elif a.ratios:
        out = stock_ratios(a.ratios, fresh=a.fresh)
    elif a.nav:
        out = nav_history(a.nav, fresh=a.fresh)
    else:
        p.error("pick a rung: --resolve | --screen | --holdings | --ratios | --nav")
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
