#!/usr/bin/env python3
"""Market-wide fetch — indices, valuation history, breadth, flows, macro.

Where `prices.py` answers "what is this stock doing", this module answers "what is the
MARKET doing" — and it is the only place those endpoints live, so the regime gate, the
fund scanner and the daily brief cannot drift to three different Nifty P/Es.

NSE `/api/allIndices` carries level AND P/E, P/B, dividend yield for all ~139 indices in one
call. The NSE archives serve the same fields for every index on any past trading day, so one
fetch per sampled DATE serves every index: the day snapshot is cached permanently and a
10-year percentile costs ~120 small fetches once, then nothing.

This module FETCHES ONLY. It classifies nothing: no regime label, no "expensive/cheap"
verdict, no score — turning these series into a market read is `finance/compute/context.py`'s
single job, so there is one market-of-record. The exceptions are `percentile()` and
`valuation_percentiles()`: ranking primitives with no verdict attached.

Returns the shared data-spine envelope (finance/contracts.md).

Reached through: get_indices, get_index_valuation_history, get_breadth, get_flows, get_macro.
"""
from __future__ import annotations

import csv
import io
import json
import math
import hashlib
from collections import Counter
import os
import statistics
import tempfile
from datetime import date, datetime, timedelta

from finance import paths
from finance import spine
from finance import transport
from finance.spine import envelope as _envelope, f as _f
from finance.sources import prices


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


def _http_get(url, timeout=25, referer=None, cookie_jar=None):
    """GET via the single shared transport. Returns (body, gap) — never raises."""
    return transport.request(url, timeout=timeout, referer=referer, cookie_jar=cookie_jar)


_nse_json = transport.nse_json


def indices(fresh=False, names=None):
    """Live level + **P/E, P/B, dividend yield** + 1-day/1-year change for NSE indices.

    One call covers all ~139 indices, so the broad-market read, the smallcap-vs-largecap
    comparison and the sector table all come from a single fetch of a single source —
    they cannot disagree. `names` narrows the returned map (matched case- and
    space-insensitively); `None` returns every index. Returns the envelope with
    `data.indices = {<CANONICAL NAME>: {last, pe, pb, dy, pct_change, pct_change_1y}}` and
    `data.available_total`, the number the fetch carried before any narrowing.
    """
    cache_file = os.path.join(paths.cache_dir("market"), "indices_validated.json")
    cached = _read_day_cache(cache_file, fresh)
    if cached is not None:
        return _select_indices(cached, names)

    payload, gap = _nse_json("https://www.nseindia.com/api/allIndices",
                             referer="https://www.nseindia.com/market-data/live-market-indices")
    if gap:
        return _select_indices(
            _envelope(False, "NSE", {"indices": {}}, [f"NSE allIndices: {gap}"]), names)

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return _envelope(False, "NSE", {"indices": {}}, ["NSE allIndices: invalid row list"])
    out, gaps = {}, []
    identities = Counter(_canon(r.get("index")) for r in payload["data"]
                         if isinstance(r, dict) and isinstance(r.get("index"), str))
    for row in payload["data"]:
        if not isinstance(row, dict):
            continue
        name = _canon(row.get("index")) if isinstance(row.get("index"), str) else ""
        if not name:
            gaps.append("NSE allIndices: unnamed index skipped")
            continue
        if identities[name] != 1:
            gaps.append(f"NSE allIndices: duplicate {name} withheld")
            continue
        out[name] = {
            "last": _f(row.get("last")),
            "pe": _f(row.get("pe")),
            "pb": _f(row.get("pb")),
            "dy": _f(row.get("dy")),
            "pct_change": _f(row.get("percentChange")),
            "pct_change_1y": _f(row.get("perChange365d")),
        }
        for field in ("last", "pe", "pb", "dy"):
            value = out[name][field]
            if value is not None and (value < 0 or (value == 0 and field != "dy")):
                out[name][field] = None
                gaps.append(f"NSE {name}: invalid {field} withheld")
    if not out:
        gaps.append("NSE allIndices returned no index rows")
    timestamp = payload.get("timestamp") if isinstance(payload.get("timestamp"), str) else None
    if timestamp is None:
        gaps.append("NSE index observation timestamp unavailable")
    env = _envelope(bool(out), "NSE", {"indices": out, "count": len(out),
                                      "source_timestamp": timestamp}, list(dict.fromkeys(gaps)))
    if out:
        _write_day_cache(cache_file, env)   # cache the full set; narrow only what is returned
    return _select_indices(env, names)


def _select_indices(env, names):
    """Narrow an indices envelope to `names` (None keeps all) and record the fetched total."""
    data = dict(env.get("data") or {})
    idx = data.get("indices") or {}
    result = dict(env, data=data, gaps=list(env.get("gaps") or []))
    data["available_total"] = len(idx)
    if names is not None:
        wanted = {_canon(n) for n in ([names] if isinstance(names, str) else names)}
        data["indices"] = {k: v for k, v in idx.items() if k in wanted}
        for name in sorted(wanted - set(idx)):
            result["gaps"].append(f"NSE index unavailable: {name}")
        data["count"] = len(data["indices"])
        result["ok"] = bool(data["indices"])
    return result


def index_levels(names=None, fresh=False):
    """`indices()` for a caller with a context budget: `names=None` means the broad set,
    because all ~139 indices are far too many to read inline."""
    return indices(fresh=fresh, names=names or BROAD_INDICES)


_ARCHIVE_CSV = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{d}.csv"


def _snapshot_cache_path(day):
    return os.path.join(paths.cache_dir(os.path.join("market", "ind_close")), f"{day}.json")


def _parse_ind_close_csv(text, expected_day=None):
    """The archive CSV -> {<CANONICAL INDEX>: {close, pe, pb, dy}}.

    Blank P/E cells are real in the archive (e.g. Smallcap 250 carried no P/E before ~2018);
    they become None, never 0 — a zero would silently poison a percentile.
    """
    out = {}
    for row in csv.DictReader(io.StringIO(text or "")):
        name = _canon(row.get("Index Name"))
        if not name:
            continue
        if expected_day is not None:
            raw_day = row.get("Index Date", "")
            parsed_day = spine.iso_date(raw_day)
            if parsed_day is None:
                try:
                    parsed_day = datetime.strptime(raw_day.strip(), "%d-%m-%Y").date().isoformat()
                except (TypeError, ValueError):
                    pass
            if parsed_day != expected_day:
                raise ValueError(f"archive date mismatch for {name}: expected {expected_day}")
        if name in out:
            raise ValueError(f"duplicate archive index: {name}")
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
    try:
        target = date.fromisoformat(str(day))
        if target > date.today() or type(walk_back) is not int or not 0 <= walk_back <= 31:
            raise ValueError("future day or invalid walk-back window")
    except (TypeError, ValueError):
        return {}, None, "archive requires a past/current ISO day and walk_back between 0 and 31"
    cache_file = _snapshot_cache_path(target.isoformat())
    if not fresh and os.path.exists(cache_file):
        try:
            with open(cache_file) as fh:
                blob = json.load(fh)
            actual = date.fromisoformat(blob["day"])
            cached = blob["indices"]
            if (blob.get("validated_version") == 1 and 0 <= (target - actual).days <= walk_back
                    and isinstance(cached, dict) and cached
                    and all(isinstance(k, str) and k and _canon(k) == k
                            and isinstance(v, dict) and set(v) == {"close", "pe", "pb", "dy"}
                            and all(x is None or (type(x) in (int, float) and math.isfinite(x))
                                    for x in v.values()) for k, v in cached.items())):
                return cached, actual.isoformat(), None
        except (OSError, ValueError, TypeError, KeyError):  # noqa: BLE001 — a bad cache file never blocks a fetch
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
        try:
            snap = _parse_ind_close_csv(text, expected_day=probe.isoformat())
        except (csv.Error, TypeError, ValueError) as exc:
            # Wrong-date or duplicate data is not evidence of a holiday.
            return {}, None, f"invalid NSE archive: {exc}"
        if not snap:  # holiday: the archive serves an empty body, not a 404
            continue
        pending = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False,
                                             dir=os.path.dirname(cache_file)) as fh:
                pending = fh.name
                json.dump({"validated_version": 1, "day": probe.isoformat(), "indices": snap},
                          fh, allow_nan=False)
            os.replace(pending, cache_file)
        except OSError:
            pass  # Source evidence remains usable even when disposable caching fails.
        finally:
            if pending and os.path.exists(pending):
                os.unlink(pending)
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
    if type(years) is not int or years <= 0 or type(max_fetches) is not int or max_fetches < 0:
        return _envelope(False, "NSE archives", {"index": key, "series": [], "samples": 0},
                         ["years must be a positive integer and max_fetches a nonnegative integer"])
    series, gaps, fetched = [], [], 0
    requested = _month_ends(years)
    seen = set()
    for day in requested:
        cached_exists = os.path.exists(_snapshot_cache_path(day.isoformat()))
        needs_fetch = fresh or not cached_exists
        if needs_fetch and fetched >= max_fetches:
            gaps.append(f"valuation history truncated at {max_fetches} snapshot requests")
            break
        if needs_fetch:
            fetched += 1
        snap, actual, gap = index_snapshot(day.isoformat(), fresh=fresh)
        if gap:
            gaps.append(f"{key} sample {day}: {gap}")
            continue
        try:
            stamp = date.fromisoformat(actual)
            if stamp > day or (day - stamp).days > 6:
                raise ValueError("outside snapshot window")
        except (TypeError, ValueError):
            gaps.append(f"{key} sample {day}: invalid archive observation date")
            continue
        row = snap.get(key) if isinstance(snap, dict) else None
        if not isinstance(row, dict) or not row:
            gaps.append(f"{key} sample {day}: index unavailable")
            continue
        if actual in seen:
            continue
        seen.add(actual)
        normalized = {}
        for field in ("close", "pe", "pb", "dy"):
            value = _f(row.get(field))
            if value is not None and (value < 0 or (field != "dy" and value == 0)):
                value = None
            normalized[field] = value
        series.append({"date": actual, **normalized})

    series.sort(key=lambda row: row["date"])
    if not series:
        gaps.append(f"no archive valuation history for {key}")
    for field in ("pe", "pb", "dy"):
        missing = sum(row[field] is None for row in series)
        if missing:
            label = {"pe": "P/E", "pb": "P/B", "dy": "dividend yield"}[field]
            gaps.append(f"{missing}/{len(series)} samples carry no {label} usable for ranking")
    return _envelope(bool(series), "NSE archives",
                     {"index": key, "years": years, "samples": len(series),
                      "requested_samples": len(requested),
                      "first_observation": series[0]["date"] if series else None,
                      "last_observation": series[-1]["date"] if series else None,
                      "series": series}, gaps)


def robust_pe_percentile(pe_series, current_pe):
    """Heuristic P/E percentile excluding positive samples at least 3x the median.

    An earnings trough can multiply an index P/E for a few months; ranking today against
    those samples understates how rich it is. This statistical filter cannot establish why
    an outlier occurred, so the included/excluded counts are returned with the percentile.
    Returns (percentile, included, excluded).
    """
    valid = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    pool = [p for p in (pe_series or []) if valid(p) and p > 0]
    if not pool or not valid(current_pe) or current_pe <= 0:
        return None, 0, 0
    med = statistics.median(pool)
    clean = [p for p in pool if p < 3 * med]
    return percentile(clean, current_pe), len(clean), len(pool) - len(clean)


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
        out[field] = {"current": now, "percentile": percentile(pool, now), "n": len(pool)}
    pe_pct, used, excluded = robust_pe_percentile(
        [row["pe"] for row in series if row.get("pe") is not None], cur.get("pe"))
    out["pe"].update({"percentile": pe_pct, "excluded": excluded})
    if excluded:
        env["gaps"].append(f"{excluded} of {used + excluded} P/E samples excluded as "
                           f"statistical outliers (P/E >= 3x median; heuristic, cause unverified)")
    env["data"] = out
    env["gaps"].extend(live.get("gaps") or [])
    env["ok"] = bool(series) and any(out[field]["percentile"] is not None for field in ("pe", "pb", "dy"))
    if not series:
        env.setdefault("gaps", []).append(
            f"no valuation history sampled for {index_name} over {years}y")
    return env


def percentile(values, value):
    """The percentile rank (0-100) of `value` within `values`, or None.

    Carries no opinion — whether the 92nd percentile means 'expensive' is the
    market-analysis skill's call, not the spine's. Ties count half, so a value sitting on a
    long flat stretch of its own history ranks mid-run rather than at either edge.
    """
    valid = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    pool = [v for v in (values or []) if valid(v)]
    if not pool or not valid(value):
        return None
    below = sum(1 for v in pool if v < value)
    ties = sum(1 for v in pool if v == value)
    return round(100.0 * (below + 0.5 * ties) / len(pool), 1)


BREADTH_COLUMNS = ["name", "close", "SMA50", "SMA200", "change",
                   "price_52_week_high", "price_52_week_low", "market_cap_basic"]


def breadth(universe=500, fresh=False):
    """Participation across the top-`universe` NSE stocks by market cap.

    Breadth separates a broad advance from an index carried by five heavyweights. Only
    counts and the universe size cross the return boundary, never the constituent list.
    Returns `data.counts` = above_sma50 / above_sma200 / advancing / near_52w_high /
    near_52w_low, plus the priced denominator for each.
    """
    if type(universe) is not int or not 1 <= universe <= 5000:
        return _envelope(False, "TradingView", {"counts": {}, "universe": 0},
                         ["breadth universe must be an integer between 1 and 5000"])
    cache_file = os.path.join(paths.cache_dir("market"), f"breadth_validated_{universe}.json")
    cached = _read_day_cache(cache_file, fresh)
    if cached is not None:
        return cached

    body = {
        "filter": [{"left": "exchange", "operation": "equal", "right": "NSE"},
                   {"left": "market_cap_basic", "operation": "greater", "right": 0}],
        "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"},
    }
    env = prices.screen(body, columns=BREADTH_COLUMNS, limit=int(universe))
    rows = (env.get("data") or {}).get("rows") or []
    if not rows:
        return _envelope(False, env.get("source"), {"counts": {}, "universe": 0},
                         env.get("gaps") or ["TradingView breadth screen returned no rows"])

    gaps = list(env.get("gaps") or [])
    names = Counter(r.get("name") for r in rows if isinstance(r, dict) and isinstance(r.get("name"), str))
    clean = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip() or names[row["name"]] != 1:
            gaps.append("breadth: missing or duplicate stock identity withheld")
            continue
        clean.append({k: (_f(row.get(k)) if k != "name" else row[k]) for k in BREADTH_COLUMNS})
    rows = clean
    if len(rows) < universe:
        gaps.append(f"breadth coverage: {len(rows)}/{universe} requested stocks available")

    def _count(pred, need):
        pool = [r for r in rows if all(r.get(k) is not None and (k == "change" or r[k] > 0) for k in need)]
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
    for metric, count in counts.items():
        if count["of"] < len(rows):
            gaps.append(f"breadth {metric}: {count['of']}/{len(rows)} stocks have usable inputs")
    out = _envelope(bool(rows), env.get("source") or "TradingView",
                    {"universe": len(rows), "requested_universe": universe, "counts": counts}, gaps)
    _write_day_cache(cache_file, out)
    return out


def flows(fresh=False):
    """Latest available session's FII/FPI and DII cash-market flows in ₹ Cr.

    Categories must share the reported session; missing categories stay explicit gaps.
    """
    cache_file = os.path.join(paths.cache_dir("market"), "flows_validated.json")
    cached = _read_day_cache(cache_file, fresh)
    if cached is not None:
        return cached

    payload, gap = _nse_json("https://www.nseindia.com/api/fiidiiTradeReact",
                             referer="https://www.nseindia.com/reports/fii-dii")
    if gap:
        return _envelope(False, "NSE", {"flows": {}}, [f"NSE FII/DII: {gap}"])

    if not isinstance(payload, list):
        return _envelope(False, "NSE", {"flows": {}}, ["NSE FII/DII: invalid row list"])
    candidates, gaps = {}, []
    for row in payload:
        if not isinstance(row, dict):
            gaps.append("NSE FII/DII: malformed row skipped")
            continue
        category = str(row.get("category", "")).strip().upper().rstrip(" *")
        cat = {"FII": "FII", "FII/FPI": "FII", "DII": "DII"}.get(category)
        if cat is None:
            gaps.append("NSE FII/DII: unrecognized category skipped")
            continue
        session = spine.iso_date(row.get("date"))
        if session is None or session > date.today().isoformat():
            gaps.append(f"NSE {cat}: invalid session date")
            continue
        values = {"buy_cr": _f(row.get("buyValue")),
                  "sell_cr": _f(row.get("sellValue")), "net_cr": _f(row.get("netValue"))}
        if (any(v is None for v in values.values()) or values["buy_cr"] < 0
                or values["sell_cr"] < 0
                or abs(values["buy_cr"] - values["sell_cr"] - values["net_cr"]) > 0.02):
            gaps.append(f"NSE {cat} {session}: incomplete or inconsistent buy/sell/net values")
            continue
        candidates.setdefault((session, cat), []).append(values)
    day = max((key[0] for key in candidates), default=None)
    out = {}
    for cat in ("FII", "DII"):
        rows = candidates.get((day, cat), [])
        if len(rows) == 1:
            out[cat] = rows[0]
        elif rows:
            gaps.append(f"NSE {cat} {day}: duplicate session rows withheld")
        elif day:
            gaps.append(f"NSE {cat}: unavailable for latest session {day}")
    if not out:
        gaps.append("NSE FII/DII returned no usable rows")
    env = _envelope(bool(out), "NSE", {"session": day, "flows": out}, gaps)
    if out:
        _write_day_cache(cache_file, env)
    return env


def macro(period="5y", fresh=False):
    """India VIX, USDINR, gold, Brent, US 10Y — level, 1M change, and own-history percentile.

    Each series is reduced to three numbers here on purpose: a caller reasoning about the
    market needs "VIX 11.3, 4th percentile of 5 years" — never 1250 daily closes.
    Returns `data.macro = {<key>: {last, chg_1m_pct, percentile_5y, as_of}}`.
    """
    if not isinstance(period, str) or not period:
        return _envelope(False, "yfinance", {"macro": {}}, ["macro period must be a nonempty string"])
    key_hash = hashlib.sha256(period.encode()).hexdigest()
    cache_file = os.path.join(paths.cache_dir("market"), f"macro_validated_{key_hash}.json")
    cached = _read_day_cache(cache_file, fresh)
    if cached is not None:
        return cached

    out, gaps = {}, []
    for key, ticker in _MACRO_TICKERS.items():
        env = prices.history(ticker, period=period, fresh=fresh)
        gaps.extend(env.get("gaps") or [])
        candles = (env.get("data") or {}).get("candles") or []
        settled = []
        dates = set()
        invalid = False
        for candle in candles:
            if not isinstance(candle, dict):
                invalid = True
                break
            stamp = spine.iso_date(candle.get("date"))
            value = _f(candle.get("close"))
            if stamp is None or stamp > date.today().isoformat() or stamp in dates or value is None:
                invalid = True
                break
            dates.add(stamp)
            settled.append({"date": stamp, "close": value})
        if invalid:
            gaps.append(f"{key} ({ticker}): invalid or duplicate dated history; series withheld")
            continue
        if not settled:
            gaps.append(f"{key} ({ticker}): no history")
            continue
        settled.sort(key=lambda c: c["date"])
        closes = [c["close"] for c in settled]
        last = closes[-1]
        # The established 1M proxy is 21 observation intervals, requiring 22 closes.
        month_ago = closes[-22] if len(closes) >= 22 else None
        if month_ago is None or month_ago <= 0:
            gaps.append(f"{key}: 1M change unavailable; needs 22 observations and positive base")
        rank = percentile(closes, last)
        out[key] = {
            "last": round(last, 2),
            "chg_1m_pct": round(100.0 * (last / month_ago - 1), 2) if month_ago is not None and month_ago > 0 else None,
            "percentile_5y": rank if period == "5y" else None,
            "percentile": rank,
            "history_period": period,
            "observations": len(closes),
            "first_observation": settled[0]["date"],
            "chg_1m_from": settled[-22]["date"] if len(settled) >= 22 else None,
            "as_of": settled[-1]["date"],
        }
    env = _envelope(bool(out), "yfinance", {"period": period, "macro": out}, gaps)
    if out:
        _write_day_cache(cache_file, env)
    return env


# Reuse the shared atomic, date-scoped envelope cache implementation.
def _read_day_cache(cache_file, fresh):
    return spine.read_cache(cache_file, fresh, stamp_key="date")


def _write_day_cache(cache_file, env):
    spine.write_cache(cache_file, env, stamp_key="date")
