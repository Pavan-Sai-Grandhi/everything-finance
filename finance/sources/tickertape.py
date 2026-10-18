"""Tickertape client — the one door to api.tickertape.in.

Public JSON, no auth, but every path 403s without a `tickertape.in` Referer; that header
lives here so no caller can forget it.

Tickertape keys everything on its own security id (`sid`), which genuinely differs from the
NSE ticker — REC is ticker `RECLTD`, sid `RECM` — and a guessed sid 404s. `resolve_sid` is
the only way across.

Fetches only: no envelope, no judgement. `sources/fundamentals.py` and `sources/funds.py`
both sit on it.
"""
from __future__ import annotations

import os
import hashlib
import re
import urllib.parse

from finance import paths
from finance import transport
from finance.spine import (CACHE_STAMP, norm_symbol as _norm,
                           read_cache as _read_cache, write_cache as _write_cache)

BASE = "https://api.tickertape.in"
SITE = "https://www.tickertape.in/"

# A sid is an identity, not a quote: a listed company keeps it for its whole life.
_SID_MAX_AGE_DAYS = 90

# NSE symbols Tickertape's search will not resolve — typically a recent corporate rename its
# search index has not caught up to (querying the new ticker or name returns other companies,
# or nothing). Mapped straight to the sid, verified from the Tickertape stock URL whose slug
# ends in the sid (…/standard-glass-lining-technology-SGL). resolve_sid consults this before
# the search, so one line restores every symbol-keyed tool for a company search cannot reach.
_SID_ALIASES = {
    "SETL": "SGL",  # Standard Engineering Technology (ex Standard Glass Lining), renamed 2025-12
}


def get_json(path, payload=None, timeout=30):
    """`(parsed, gap)` for a Tickertape path. POSTs `payload` as JSON when given."""
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        return None, "Tickertape: an API-relative path is required"
    blob, gap = transport.json_request(BASE + path, payload=payload, timeout=timeout,
                                       referer=SITE)
    if gap:
        return None, gap
    if not isinstance(blob, dict) or blob.get("success") is False or blob.get("data") is None:
        return None, "Tickertape: failed or malformed API response"
    return blob, None


def cache_path(kind, key):
    """A stable cache-file path under the disposable tier (never hardcoded)."""
    safe = hashlib.sha256(str(key).encode()).hexdigest()
    return os.path.join(paths.cache_dir(os.path.join("tickertape", kind)), f"{safe}.json")


def resolve_sid(symbol, fresh=False):
    """NSE symbol -> `({sid, ticker, name, sector, slug}, gap)`.

    The search returns every partial match, so only an exact ticker equality is accepted:
    a "Reliance" query also offers RCOM and RPOWER, and a near-miss here would silently
    attribute one company's financials to another.
    """
    sym = _norm(symbol)
    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9&_.-]*", sym):
        return None, "no symbol given to resolve against Tickertape"

    alias = _SID_ALIASES.get(sym)
    if alias:
        return {"sid": alias, "ticker": sym, "name": None,
                "sector": None, "slug": None}, None

    cache, cached = None, None
    try:
        cache = cache_path("sid", sym)
        cached = _read_cache(cache, fresh, max_age_days=_SID_MAX_AGE_DAYS)
    except OSError:
        pass  # identity lookup still works when the disposable cache is unavailable
    if (cached is not None and cached["data"].get("ticker") == sym
            and isinstance(cached["data"].get("sid"), str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9&_.-]*", cached["data"]["sid"])):
        return {k: v for k, v in cached["data"].items() if k != CACHE_STAMP}, None

    url = "/search?" + urllib.parse.urlencode({"text": sym, "types": "stock"})
    blob, gap = get_json(url, timeout=25)
    if gap:
        return None, f"Tickertape sid for {sym}: {gap}"

    data = blob.get("data") if isinstance(blob, dict) else None
    stocks = data.get("stocks") if isinstance(data, dict) else None
    if not isinstance(stocks, list):
        return None, f"Tickertape sid for {sym}: malformed search results"
    stocks = [s for s in stocks if isinstance(s, dict)]
    hits = {s["sid"]: s for s in stocks
            if isinstance(s.get("ticker"), str) and _norm(s["ticker"]) == sym
            and isinstance(s.get("sid"), str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9&_.-]*", s["sid"])}
    if len(hits) > 1:
        return None, f"Tickertape sid for {sym}: conflicting exact-match security ids; identity unresolved"
    hit = next(iter(hits.values()), None)
    if not hit:
        offered = ", ".join(str(s.get("ticker")) for s in stocks[:5]) or "nothing"
        return None, (f"no Tickertape security id for NSE symbol {sym} — search offered "
                      f"{offered}. If the ticker was recently renamed, pass the sid directly "
                      f"(the tail of the Tickertape stock URL, …-SID) or add {sym} to "
                      f"_SID_ALIASES in sources/tickertape.py — do not substitute a "
                      f"near-match ticker's financials.")

    rec = {"sid": hit["sid"], "ticker": _norm(hit.get("ticker")), "name": hit.get("name"),
           "sector": hit.get("sector"), "slug": hit.get("slug")}
    if cache:
        _write_cache(cache, {"data": dict(rec)})
    return rec, None
