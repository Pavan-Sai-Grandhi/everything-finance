#!/usr/bin/env python3
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
import urllib.parse

from finance import paths
from finance import transport
from finance.spine import (CACHE_STAMP, norm_symbol as _norm,
                           read_cache as _read_cache, write_cache as _write_cache)

BASE = "https://api.tickertape.in"
SITE = "https://www.tickertape.in/"

# A sid is an identity, not a quote: a listed company keeps it for its whole life.
_SID_MAX_AGE_DAYS = 90


def get_json(path, payload=None, timeout=30):
    """`(parsed, gap)` for a Tickertape path. POSTs `payload` as JSON when given."""
    return transport.json_request(BASE + path, payload=payload, timeout=timeout,
                                  referer=SITE)


def cache_path(kind, key):
    """A stable cache-file path under the disposable tier (never hardcoded)."""
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(key))
    return os.path.join(paths.cache_dir(os.path.join("tickertape", kind)), f"{safe}.json")


def resolve_sid(symbol, fresh=False):
    """NSE symbol -> `({sid, ticker, name, sector, slug}, gap)`.

    The search returns every partial match, so only an exact ticker equality is accepted:
    a "Reliance" query also offers RCOM and RPOWER, and a near-miss here would silently
    attribute one company's financials to another.
    """
    sym = _norm(symbol)
    if not sym:
        return None, "no symbol given to resolve against Tickertape"

    cache = cache_path("sid", sym)
    cached = _read_cache(cache, fresh, max_age_days=_SID_MAX_AGE_DAYS)
    if cached is not None:
        return {k: v for k, v in cached["data"].items() if k != CACHE_STAMP}, None

    url = "/search?" + urllib.parse.urlencode({"text": sym, "types": "stock"})
    blob, gap = get_json(url, timeout=25)
    if gap:
        return None, f"Tickertape sid for {sym}: {gap}"

    stocks = ((blob or {}).get("data") or {}).get("stocks") or []
    hit = next((s for s in stocks if _norm(s.get("ticker")) == sym and s.get("sid")), None)
    if not hit:
        offered = ", ".join(str(s.get("ticker")) for s in stocks[:5]) or "nothing"
        return None, (f"no Tickertape security id for NSE symbol {sym} "
                      f"(search offered {offered})")

    rec = {"sid": hit["sid"], "ticker": _norm(hit.get("ticker")), "name": hit.get("name"),
           "sector": hit.get("sector"), "slug": hit.get("slug")}
    _write_cache(cache, {"data": dict(rec)})
    return rec, None
