#!/usr/bin/env python3
"""Market-wide fetch — indices, valuation history, breadth, volatility, flows, macro.

The canonical *market-level* fetcher of the data spine, sitting next to `prices.py`
(single-symbol prices), `fundamentals.py` (single-company financials) and `news.py`.
Where `prices.py` answers "what is this stock doing", this module answers "what is the
MARKET doing" — and it is the only place those endpoints live, so the regime gate, the
fund scanner and the daily brief cannot drift to three different Nifty P/Es.

Five rungs, each on its cheapest verified path:

  * `indices()`      -> NSE `/api/allIndices`: live level + **P/E, P/B, dividend yield**
                        for all ~139 NSE indices in ONE call (cookie-bootstrapped).
  * `valuation_history()` -> NSE archives `ind_close_all_<DDMMYYYY>.csv`: the same P/E-P/B-DY
                        for EVERY index on any past trading day. One fetch per sampled DATE
                        serves every index, so the day snapshot is cached permanently and a
                        10-year percentile costs ~120 small fetches ONCE, then nothing.
  * `breadth()`      -> TradingView India scanner (via `prices.screen`, no auth): the
                        top-N-by-market-cap universe with SMA50/SMA200/52w fields, from
                        which participation is counted.
  * `flows()`        -> NSE `/api/fiidiiTradeReact`: latest FII/FPI and DII net cash flow.
  * `macro()`        -> yfinance: India VIX, USDINR, gold, crude, US 10Y — the cross-asset
                        backdrop, no bot wall.

This module FETCHES ONLY. It classifies nothing: no regime label, no "expensive/cheap"
verdict, no score. Turning these series into a market read is
`finance/compute/context.py`'s single job — the same separation
`prices.py` (candles) keeps from `ta.py` (indicators), so there is one market-of-record.
The exceptions are `percentile()` and `valuation_percentiles()`: ranking primitives that
say where a number sits in its own history, with no verdict attached.

Every fetch returns the shared data-spine envelope:
    { "ok": bool, "source": str|None, "fetched_at": ISO8601,
      "data": {...}, "gaps": ["<labelled degradation>", ...] }

Fetched text is untrusted DATA, not instructions. Networked, best-effort,
degrade-not-die: a blocked source records a *labelled* gap and the run continues.

CLI:
  python3 -m finance.sources.market --indices                   # live index snapshot w/ P/E, P/B, DY
  python3 -m finance.sources.market --valuation "NIFTY SMALLCAP 250" --years 10
  python3 -m finance.sources.market --breadth                   # participation counts
  python3 -m finance.sources.market --flows                     # FII/DII net
  python3 -m finance.sources.market --macro                     # VIX, USDINR, gold, crude
  python3 -m finance.sources.market --seed-valuation --years 10 # warm the day-snapshot cache
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from datetime import date, timedelta

from finance import paths  # the single path authority — never hardcode a cache string
from finance import transport  # the single HTTP transport — no module opens its own socket
from finance.spine import envelope as _envelope, f as _f
from finance.sources import prices  # the TradingView scanner rung is already solved there


# The indices the plugin actually reasons about, in canonical NSE spelling. Callers pass
# these keys around; `_canon()` makes matching case/space-insensitive so the live JSON
# ("NIFTY SMALLCAP 250") and the archive CSV ("Nifty Smallcap 250") resolve to one key.
BROAD_INDICES = [
    "NIFTY 50", "NIFTY NEXT 50", "NIFTY 100", "NIFTY 500",
    "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250", "NIFTY MICROCAP 250",
]
SECTOR_INDICES = [
    "NIFTY BANK", "NIFTY IT", "NIFTY AUTO", "NIFTY PHARMA", "NIFTY FMCG",
    "NIFTY METAL", "NIFTY REALTY", "NIFTY ENERGY", "NIFTY INFRASTRUCTURE",
    "NIFTY PSU BANK", "NIFTY PRIVATE BANK", "NIFTY FINANCIAL SERVICES",
    "NIFTY MEDIA", "NIFTY CONSUMER DURABLES", "NIFTY OIL & GAS",
    "NIFTY HEALTHCARE INDEX", "NIFTY COMMODITIES",
]

# The verified yfinance tickers for the NSE sectoral indices — **the one copy**. Anything
# needing sector price history reads it from here, so no two skills can disagree about
# which sectors exist.
SECTOR_YF = {
    "Bank": "^NSEBANK", "FinServ": "NIFTY_FIN_SERVICE.NS", "IT": "^CNXIT",
    "Pharma": "^CNXPHARMA", "Auto": "^CNXAUTO", "FMCG": "^CNXFMCG",
    "Metal": "^CNXMETAL", "Realty": "^CNXREALTY", "Energy": "^CNXENERGY",
    "PSUBank": "^CNXPSUBANK",
}

# The cap tiers a cap-tier valuation read is built on, in ascending size order.
CAP_TIER_INDICES = ["NIFTY SMALLCAP 250", "NIFTY MIDCAP 150", "NIFTY 50"]

# yfinance tickers for the cross-asset backdrop. Kept here (not in prices.py) because
# these are market-level series, not tradeable NSE symbols.
_MACRO_TICKERS = {
    "india_vix": "^INDIAVIX",
    "usdinr": "INR=X",
    "gold_usd": "GC=F",
    "crude_brent": "BZ=F",
    "us_10y": "^TNX",
}

def _canon(name):
    """Canonical index key: upper-cased, whitespace-collapsed. Makes the live JSON's
    'NIFTY SMALLCAP 250' and the archive CSV's 'Nifty Smallcap 250' the same key."""
    return " ".join(str(name or "").upper().split())


# --------------------------------------------------------------------------- #
# HTTP                                                                         #
# --------------------------------------------------------------------------- #
def _http_get(url, timeout=25, referer=None, cookie_jar=None):
    """GET via the single shared transport. Returns (body, gap) — never raises."""
    return transport.request(url, timeout=timeout, referer=referer, cookie_jar=cookie_jar)


_nse_json = transport.nse_json


# --------------------------------------------------------------------------- #
# rung 1 — live index snapshot with valuation (NSE allIndices)                  #
# --------------------------------------------------------------------------- #
def indices(fresh=False, names=None):
    """Live level + **P/E, P/B, dividend yield** + 1-day/1-year change for NSE indices.

    One call covers all ~139 indices, so the broad-market read, the smallcap-vs-largecap
    comparison and the sector table all come from a single fetch of a single source —
    they cannot disagree. `names` narrows the returned map (matched case- and
    space-insensitively); `None` returns every index. Returns the envelope with
    `data.indices = {<CANONICAL NAME>: {last, pe, pb, dy, pct_change, pct_change_1y}}` and
    `data.available_total`, the number the fetch carried before any narrowing.
    """
    cache_file = os.path.join(paths.cache_dir("market"), "indices.json")
    cached = _read_day_cache(cache_file, fresh)
    if cached is not None:
        return _select_indices(cached, names)

    payload, gap = _nse_json("https://www.nseindia.com/api/allIndices",
                             referer="https://www.nseindia.com/market-data/live-market-indices")
    if gap:
        return _select_indices(
            _envelope(False, "NSE", {"indices": {}}, [f"NSE allIndices: {gap}"]), names)

    out = {}
    for row in (payload or {}).get("data", []):
        if not isinstance(row, dict):
            continue
        name = _canon(row.get("index"))
        if not name:
            continue
        out[name] = {
            "last": _f(row.get("last")),
            "pe": _f(row.get("pe")),
            "pb": _f(row.get("pb")),
            "dy": _f(row.get("dy")),
            "pct_change": _f(row.get("percentChange")),
            "pct_change_1y": _f(row.get("perChange365d")),
        }
    gaps = [] if out else ["NSE allIndices returned no index rows"]
    env = _envelope(bool(out), "NSE", {"indices": out, "count": len(out)}, gaps)
    if out:
        _write_day_cache(cache_file, env)   # cache the full set; narrow only what is returned
    return _select_indices(env, names)


def _select_indices(env, names):
    """Narrow an indices envelope to `names` (None keeps all) and record the fetched total."""
    idx = (env.get("data") or {}).get("indices") or {}
    env.setdefault("data", {})["available_total"] = len(idx)
    if names is not None:
        wanted = {_canon(n) for n in names}
        env["data"]["indices"] = {k: v for k, v in idx.items() if _canon(k) in wanted}
    return env


def index_levels(names=None, fresh=False):
    """`indices()` for a caller with a context budget: `names=None` means the broad set,
    because all ~139 indices are far too many to read inline."""
    return indices(fresh=fresh, names=names or BROAD_INDICES)


# --------------------------------------------------------------------------- #
# rung 2 — historical index valuation (NSE archives daily CSV)                  #
# --------------------------------------------------------------------------- #
_ARCHIVE_CSV = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{d}.csv"


def _snapshot_cache_path(day):
    return os.path.join(paths.cache_dir(os.path.join("market", "ind_close")), f"{day}.json")


def _parse_ind_close_csv(text):
    """Pure: the archive CSV -> {<CANONICAL INDEX>: {close, pe, pb, dy}} (offline-testable).

    Blank P/E cells are real in the archive (e.g. Smallcap 250 carried no P/E before ~2018);
    they become None, never 0 — a zero would silently poison a percentile.
    """
    out = {}
    for row in csv.DictReader(io.StringIO(text or "")):
        name = _canon(row.get("Index Name"))
        if not name:
            continue
        out[name] = {
            "close": _f(row.get("Closing Index Value")),
            "pe": _f(row.get("P/E")),
            "pb": _f(row.get("P/B")),
            "dy": _f(row.get("Div Yield")),
        }
    return out


def index_snapshot(day, fresh=False, walk_back=6):
    """Every index's close/P/E/P/B/DY on one past trading day, cached **permanently**.

    `day` is an ISO date; weekends and holidays walk back up to `walk_back` days to the
    previous trading session. One fetch serves all ~139 indices, which is what makes a
    multi-index, multi-year percentile affordable. Returns (snapshot_dict, actual_day, gap).
    """
    target = date.fromisoformat(str(day))
    cache_file = _snapshot_cache_path(target.isoformat())
    if not fresh and os.path.exists(cache_file):
        try:
            with open(cache_file) as fh:
                blob = json.load(fh)
            return blob.get("indices", {}), blob.get("day"), None
        except Exception:  # noqa: BLE001 — a bad cache file never blocks a fetch
            pass

    last_gap = None
    for back in range(walk_back + 1):
        probe = target - timedelta(days=back)
        if probe.weekday() >= 5:  # NSE is shut Sat/Sun — don't spend a fetch on it
            continue
        text, gap = _http_get(_ARCHIVE_CSV.format(d=probe.strftime("%d%m%Y")),
                              referer="https://www.nseindia.com/")
        if gap:
            last_gap = gap
            continue
        snap = _parse_ind_close_csv(text)
        if not snap:  # holiday: the archive serves an empty body, not a 404
            continue
        try:
            with open(cache_file, "w") as fh:
                json.dump({"day": probe.isoformat(), "indices": snap}, fh)
        except Exception:  # noqa: BLE001
            pass
        return snap, probe.isoformat(), None
    return {}, None, (last_gap or f"no NSE archive snapshot within {walk_back}d of {day}")


def _month_ends(years, today=None):
    """Month-end sample dates covering the last `years` years, oldest first.

    Monthly sampling (not daily) is deliberate: a valuation percentile is a slow-moving
    statistic, and 120 points describe the distribution as well as 2500 do at 5% of the
    fetches. `today` is the final, un-rounded sample so the current level is included.
    """
    end = today or date.today()
    out, cursor = [], date(end.year, end.month, 1)
    for _ in range(int(years * 12) + 1):
        out.append(cursor - timedelta(days=1))  # last day of the previous month
        cursor = date(cursor.year - 1, 12, 1) if cursor.month == 1 \
            else date(cursor.year, cursor.month - 1, 1)
    out = sorted(d for d in out if d < end)
    return out + [end]


def valuation_history(index_name, years=10, fresh=False, max_fetches=200):
    """Month-end P/E, P/B, DY series for one index over `years`, from the cached snapshots.

    The first run costs ~`years*12` small fetches; every later run — and every OTHER index,
    since a snapshot holds all of them — is served from cache. Returns the envelope with
    `data.series = [{date, close, pe, pb, dy}, ...]` oldest first.
    """
    key = _canon(index_name)
    series, gaps, fetched = [], [], 0
    for day in _month_ends(years):
        cached_exists = os.path.exists(_snapshot_cache_path(day.isoformat()))
        if not cached_exists and fetched >= max_fetches:
            gaps.append(f"valuation history truncated at {max_fetches} fetches")
            break
        if not cached_exists:
            fetched += 1
        snap, actual, gap = index_snapshot(day.isoformat(), fresh=fresh)
        if gap:
            continue
        row = snap.get(key)
        if not row:
            continue
        series.append({"date": actual, **row})

    if not series:
        gaps.append(f"no archive valuation history for {key}")
    priced = [s for s in series if s.get("pe") is not None]
    if series and len(priced) < len(series):
        gaps.append(f"{len(series) - len(priced)}/{len(series)} samples carry no P/E "
                    f"(NSE published none for {key} then)")
    return _envelope(bool(series), "NSE archives",
                     {"index": key, "years": years, "samples": len(series),
                      "series": series}, gaps)


def valuation_percentiles(index_name, years=10, fresh=False):
    """Where an index's valuation sits against its own history: the current P/E, P/B and
    dividend yield each ranked against the month-end series over `years`.

    Returns the envelope with `data = {index, years, samples, pe|pb|dy: {current,
    percentile, n}}` — the ranks, not the series, because "where does today sit" is the
    decision and the series is a few hundred rows of context nobody reads.
    """
    env = valuation_history(index_name, years=years, fresh=fresh)
    series = (env.get("data") or {}).get("series") or []
    live = indices(fresh=fresh)
    cur = ((live.get("data") or {}).get("indices") or {}).get(_canon(index_name)) or {}

    out = {"index": index_name, "years": years, "samples": len(series)}
    for field in ("pe", "pb", "dy"):
        pool = [row[field] for row in series if row.get(field) is not None]
        now = cur.get(field)
        out[field] = {
            "current": now,
            "percentile": (round(percentile(pool, now), 1)
                           if pool and now is not None else None),
            "n": len(pool),
        }
    env["data"] = out
    if not series:
        env.setdefault("gaps", []).append(
            f"no valuation history sampled for {index_name} over {years}y")
    return env


def percentile(values, value):
    """Pure: the percentile rank (0-100) of `value` within `values`, or None.

    The one piece of math in this module, and it carries no opinion — whether the 92nd
    percentile means 'expensive' is the market-analysis skill's call, not the spine's.
    """
    pool = [v for v in (values or []) if v is not None]
    if not pool or value is None:
        return None
    below = sum(1 for v in pool if v < value)
    ties = sum(1 for v in pool if v == value)
    return round(100.0 * (below + 0.5 * ties) / len(pool), 1)


# --------------------------------------------------------------------------- #
# rung 3 — market breadth (TradingView scanner, via prices.screen)              #
# --------------------------------------------------------------------------- #
BREADTH_COLUMNS = ["name", "close", "SMA50", "SMA200", "change",
                   "price_52_week_high", "price_52_week_low", "market_cap_basic"]


def breadth(universe=500, fresh=False):
    """Participation across the top-`universe` NSE stocks by market cap.

    Breadth is what separates a broad advance from an index carried by five heavyweights —
    the single most useful check the plugin was missing. Counts (not the constituent list)
    are what callers need, so only counts and the universe size cross the return boundary.
    Returns `data.counts` = above_sma50 / above_sma200 / advancing / near_52w_high /
    near_52w_low, plus the priced denominator for each.
    """
    cache_file = os.path.join(paths.cache_dir("market"), f"breadth_{universe}.json")
    cached = _read_day_cache(cache_file, fresh)
    if cached is not None:
        return cached

    body = {
        "filter": [{"left": "exchange", "operation": "equal", "right": "NSE"},
                   {"left": "market_cap_basic", "operation": "greater", "right": 5_000_000_000}],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
    }
    env = prices.screen(body, columns=BREADTH_COLUMNS, limit=int(universe))
    rows = (env.get("data") or {}).get("rows") or []
    if not rows:
        return _envelope(False, env.get("source"), {"counts": {}, "universe": 0},
                         env.get("gaps") or ["TradingView breadth screen returned no rows"])

    def _count(pred, need):
        pool = [r for r in rows if all(r.get(k) is not None for k in need)]
        return {"count": sum(1 for r in pool if pred(r)), "of": len(pool)}

    counts = {
        "above_sma50": _count(lambda r: r["close"] > r["SMA50"], ("close", "SMA50")),
        "above_sma200": _count(lambda r: r["close"] > r["SMA200"], ("close", "SMA200")),
        "advancing": _count(lambda r: r["change"] > 0, ("change",)),
        "near_52w_high": _count(
            lambda r: r["close"] >= 0.95 * r["price_52_week_high"],
            ("close", "price_52_week_high")),
        "near_52w_low": _count(
            lambda r: r["close"] <= 1.05 * r["price_52_week_low"],
            ("close", "price_52_week_low")),
    }
    out = _envelope(True, env.get("source") or "TradingView",
                    {"universe": len(rows), "counts": counts}, env.get("gaps") or [])
    _write_day_cache(cache_file, out)
    return out


# --------------------------------------------------------------------------- #
# rung 4 — institutional flows (NSE FII/DII)                                    #
# --------------------------------------------------------------------------- #
def flows(fresh=False):
    """Latest session's FII/FPI and DII net cash-market flow, in ₹ Cr.

    Domestic (DII/SIP) money absorbing foreign selling is the structural fact behind the
    last several years of Indian small/midcap behaviour — the flow rung exists so that
    claim is sourced, never assumed. Returns `data.flows = {FII: {...}, DII: {...}}`.
    """
    cache_file = os.path.join(paths.cache_dir("market"), "flows.json")
    cached = _read_day_cache(cache_file, fresh)
    if cached is not None:
        return cached

    payload, gap = _nse_json("https://www.nseindia.com/api/fiidiiTradeReact",
                             referer="https://www.nseindia.com/reports/fii-dii")
    if gap:
        return _envelope(False, "NSE", {"flows": {}}, [f"NSE FII/DII: {gap}"])

    out, day = {}, None
    for row in payload or []:
        if not isinstance(row, dict):
            continue
        cat = "FII" if "FII" in str(row.get("category", "")).upper() else "DII"
        out[cat] = {"buy_cr": _f(row.get("buyValue")),
                    "sell_cr": _f(row.get("sellValue")),
                    "net_cr": _f(row.get("netValue"))}
        day = row.get("date") or day
    gaps = [] if out else ["NSE FII/DII returned no rows"]
    env = _envelope(bool(out), "NSE", {"session": day, "flows": out}, gaps)
    if out:
        _write_day_cache(cache_file, env)
    return env


# --------------------------------------------------------------------------- #
# rung 5 — cross-asset macro backdrop (yfinance)                                #
# --------------------------------------------------------------------------- #
def macro(period="5y", fresh=False):
    """India VIX, USDINR, gold, Brent, US 10Y — level, 1M change, and own-history percentile.

    Each series is reduced to three numbers here on purpose: a caller reasoning about the
    market needs "VIX 11.3, 4th percentile of 5 years" — never 1250 daily closes.
    Returns `data.macro = {<key>: {last, chg_1m_pct, percentile_5y, as_of}}`.
    """
    cache_file = os.path.join(paths.cache_dir("market"), f"macro_{period}.json")
    cached = _read_day_cache(cache_file, fresh)
    if cached is not None:
        return cached

    out, gaps = {}, []
    for key, ticker in _MACRO_TICKERS.items():
        env = prices.history(ticker, period=period, fresh=fresh)
        candles = (env.get("data") or {}).get("candles") or []
        closes = [c.get("close") for c in candles if c.get("close") is not None]
        if not closes:
            gaps.append(f"{key} ({ticker}): no history")
            continue
        last = closes[-1]
        month_ago = closes[-22] if len(closes) > 22 else closes[0]
        out[key] = {
            "last": round(last, 2),
            "chg_1m_pct": round(100.0 * (last - month_ago) / month_ago, 2) if month_ago else None,
            "percentile_5y": percentile(closes, last),
            "as_of": candles[-1].get("date"),
        }
    env = _envelope(bool(out), "yfinance", {"period": period, "macro": out}, gaps)
    if out:
        _write_day_cache(cache_file, env)
    return env


# --------------------------------------------------------------------------- #
# day-scoped cache (same contract as prices.py: today's file, else refetch)     #
# --------------------------------------------------------------------------- #
def _read_day_cache(cache_file, fresh):
    if fresh or not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file) as fh:
            cached = json.load(fh)
        if cached.get("data", {}).get("date") == date.today().isoformat():
            return cached
    except Exception:  # noqa: BLE001 — a bad cache file never blocks a fetch
        pass
    return None


def _write_day_cache(cache_file, env):
    env.setdefault("data", {}).setdefault("date", date.today().isoformat())
    try:
        with open(cache_file, "w") as fh:
            json.dump(env, fh, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
def main():
    p = argparse.ArgumentParser(description="market-wide data spine")
    p.add_argument("--indices", action="store_true", help="live index snapshot w/ P/E,P/B,DY")
    p.add_argument("--valuation", metavar="INDEX", help="month-end valuation history")
    p.add_argument("--years", type=int, default=10)
    p.add_argument("--breadth", action="store_true")
    p.add_argument("--universe", type=int, default=500)
    p.add_argument("--flows", action="store_true")
    p.add_argument("--macro", action="store_true")
    p.add_argument("--seed-valuation", action="store_true",
                   help="warm the day-snapshot cache (one fetch per month-end, then free)")
    p.add_argument("--fresh", action="store_true")
    a = p.parse_args()

    if a.indices:
        out = indices(fresh=a.fresh)
    elif a.valuation:
        out = valuation_history(a.valuation, years=a.years, fresh=a.fresh)
    elif a.breadth:
        out = breadth(universe=a.universe, fresh=a.fresh)
    elif a.flows:
        out = flows(fresh=a.fresh)
    elif a.macro:
        out = macro(fresh=a.fresh)
    elif a.seed_valuation:
        got = 0
        for day in _month_ends(a.years):
            snap, actual, _gap = index_snapshot(day.isoformat())
            got += 1 if snap else 0
        out = _envelope(bool(got), "NSE archives",
                        {"seeded": got, "requested": len(_month_ends(a.years))}, [])
    else:
        p.error("pick a rung: --indices | --valuation | --breadth | --flows | --macro")
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
