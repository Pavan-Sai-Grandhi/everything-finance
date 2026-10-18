"""Analyst consensus — Yahoo Finance's EPS and revenue consensus for NSE stocks, and the
NIFTY 500's expected earnings growth built from it.

Yahoo, read through yfinance (the approved Yahoo client), publishes per stock the mean, low
and high analyst estimate of EPS and revenue for the current and next fiscal year, the
analyst count, and the year-ago EPS the growth is measured from. For an Indian company with
a March year-end, `current` is the year ending the coming March. Yahoo's `indexTrend` column
is the S&P 500, not an Indian index, and is never read.

The market figure sums net income. Each covered constituent's latest fiscal-year net income
(Tickertape screener) is grown by its own consensus EPS ratios, and the sums give the index's
expected earnings growth for the next two fiscal years. A stock enters only with at least
`MIN_ANALYSTS` analysts and a Yahoo year-ago EPS within `BASIS_TOLERANCE` of Tickertape's
published EPS for the same year: a demerger, a one-off gain or a standalone/consolidated
mismatch puts the two apart, and one such stock would otherwise swamp the sum. Coverage is the
covered share of the index's positive net income; below `MIN_COVERAGE` the figure is withheld.

Analyst forecasts lean optimistic. Consumers read them as what the market expects, not as a
forecast of what will happen.

Reached through: get_analyst_estimates, and run_dcf's market view.
"""
from __future__ import annotations

import os

from finance import deps, paths, spine
from finance.sources import tickertape, universe
from finance.sources.prices import yf_ticker

_SOURCE = "Yahoo Finance consensus (yfinance)"
_PERIODS = (("0y", "current_fy"), ("+1y", "next_fy"))
MIN_ANALYSTS = 3
BASIS_TOLERANCE = 0.20
MIN_COVERAGE = 0.70
MARKET_UNIVERSE = "nifty500"
_MARKET_CACHE_DAYS = 7


def _cache(kind, key):
    return os.path.join(paths.cache_dir(os.path.join("estimates", kind)), f"{key}.json")


def _rows(frame, fields):
    """{current_fy|next_fy: {field: float|None}} from a yfinance estimate frame."""
    out = {}
    for code, name in _PERIODS:
        row = frame.loc[code] if frame is not None and code in frame.index else None
        out[name] = {f: (spine.f(row.get(src)) if row is not None else None)
                     for f, src in fields.items()}
    return out


def _consensus(symbol):
    """(record, gap): one stock's EPS and revenue consensus straight from Yahoo."""
    try:
        ticker = deps.need("yfinance").Ticker(yf_ticker(symbol))
        eps, revenue = ticker.earnings_estimate, ticker.revenue_estimate
    except Exception as exc:  # noqa: BLE001 — any provider failure is a labelled gap
        return None, f"Yahoo consensus for {symbol}: {type(exc).__name__}"
    record = {
        "eps": _rows(eps, {"avg": "avg", "low": "low", "high": "high",
                           "year_ago": "yearAgoEps", "analysts": "numberOfAnalysts"}),
        "revenue": _rows(revenue, {"avg": "avg", "low": "low", "high": "high",
                                   "year_ago": "yearAgoRevenue", "analysts": "numberOfAnalysts"}),
    }
    if record["eps"]["current_fy"]["avg"] is None and record["revenue"]["current_fy"]["avg"] is None:
        return None, f"Yahoo has no analyst consensus for {symbol}"
    return record, None


def company(symbol, fresh=False):
    """One stock's consensus: EPS and revenue (mean, low, high, analysts, year-ago) for the
    current and next fiscal year, cached for the day. EPS growth is struck against Yahoo's own
    year-ago EPS, whose basis can differ from the annual report — the consumer checks it."""
    sym = spine.norm_symbol(symbol)
    if not sym:
        return spine.envelope(False, _SOURCE, {"symbol": symbol}, ["no symbol given"])
    path = _cache("company", sym)
    cached = spine.read_cache(path, fresh)
    if cached is not None:
        return cached
    record, gap = _consensus(sym)
    if gap:
        return spine.envelope(False, _SOURCE, {"symbol": sym}, [gap])
    for block in record["revenue"].values():  # Yahoo reports rupees; the plugin's unit is ₹ Crore
        for key in ("avg", "low", "high", "year_ago"):
            block[key] = round(block[key] / 1e7, 2) if block[key] is not None else None
    for block in record["eps"].values():
        avg, base = block["avg"], block["year_ago"]
        block["growth"] = round(avg / base - 1, 6) if avg is not None and base and base > 0 else None
    gaps = []
    if (record["eps"]["current_fy"]["analysts"] or 0) < MIN_ANALYSTS:
        gaps.append(f"fewer than {MIN_ANALYSTS} analysts cover {sym}'s EPS — a thin consensus")
    env = spine.envelope(True, _SOURCE, {"symbol": sym, "revenue_unit": "INR Crore", **record}, gaps)
    spine.write_cache(path, env)
    return env


def _bases():
    """(ticker → {eps, net_income}, gap): latest fiscal-year EPS and net income for every
    listed stock above ₹500 Cr, one Tickertape screener page."""
    blob, gap = tickertape.get_json(
        "/screener/query", timeout=45,
        payload={"match": {"mrktCapf": {"g": 500}}, "sortBy": "mrktCapf", "sortOrder": -1,
                 "project": ["mrktCapf", "incEps", "incNinc"], "offset": 0, "count": 2000})
    if gap:
        return None, f"Tickertape net-income base: {gap}"
    rows = ((blob or {}).get("data") or {}).get("results")
    if not isinstance(rows, list):
        return None, "Tickertape net-income base: no results list"
    out = {}
    for row in rows:
        stock = row.get("stock") if isinstance(row, dict) else None
        info, ratios = (stock or {}).get("info") or {}, (stock or {}).get("advancedRatios") or {}
        if isinstance(info.get("ticker"), str):
            out[spine.norm_symbol(info["ticker"])] = {"eps": spine.f(ratios.get("incEps")),
                                                      "net_income": spine.f(ratios.get("incNinc"))}
    return out, None


def aggregate(constituents, bases, consensus):
    """The index's expected earnings growth from per-stock consensus — pure arithmetic.

    `bases` maps symbol → {eps, net_income} (latest fiscal year); `consensus` maps symbol →
    the `eps` block of `company`. Returns {growth: [current_fy, next_fy] | None, coverage,
    covered, constituents, excluded_basis}."""
    positive = {s: bases[s] for s in constituents
                if s in bases and (bases[s]["net_income"] or 0) > 0}
    total = sum(b["net_income"] for b in positive.values())
    base_ni = cur_ni = next_ni = 0.0
    covered, excluded = [], []
    for sym, b in positive.items():
        eps = consensus.get(sym) or {}
        cur, nxt = eps.get("current_fy") or {}, eps.get("next_fy") or {}
        year_ago, avg0, avg1 = cur.get("year_ago"), cur.get("avg"), nxt.get("avg")
        if (cur.get("analysts") or 0) < MIN_ANALYSTS or None in (year_ago, avg0, avg1) \
                or year_ago <= 0 or not b["eps"] or b["eps"] <= 0:
            continue
        if abs(year_ago / b["eps"] - 1) > BASIS_TOLERANCE:
            excluded.append({"symbol": sym, "yahoo_year_ago_eps": year_ago,
                             "published_eps": b["eps"], "net_income": b["net_income"]})
            continue
        covered.append(sym)
        base_ni += b["net_income"]
        cur_ni += b["net_income"] * avg0 / year_ago
        next_ni += b["net_income"] * avg1 / year_ago
    coverage = base_ni / total if total else 0.0
    growth = ([round(cur_ni / base_ni - 1, 6), round(next_ni / cur_ni - 1, 6)]
              if base_ni > 0 and cur_ni > 0 and coverage >= MIN_COVERAGE else None)
    excluded.sort(key=lambda r: -r["net_income"])
    return {"growth": growth, "coverage": round(coverage, 4), "covered": len(covered),
            "constituents": len(constituents), "excluded_basis": excluded[:10]}


def market(fresh=False):
    """The NIFTY 500's earnings-weighted consensus growth for the current and next fiscal
    year, cached for a week (consensus moves slowly; the build reads ~500 stocks)."""
    path = _cache("market", MARKET_UNIVERSE)
    cached = spine.read_cache(path, fresh, max_age_days=_MARKET_CACHE_DAYS)
    if cached is not None:
        return cached
    source = f"{_SOURCE} + Tickertape + NSE"
    symbols, gaps = universe.resolve_symbols(MARKET_UNIVERSE, fresh=fresh)
    bases, gap = _bases()
    if gap or not symbols:
        return spine.envelope(False, source, {"index": "NIFTY 500", "growth": None},
                              gaps + ([gap] if gap else []))
    consensus = {}
    for sym in symbols:
        record, _ = _consensus(sym)
        if record:
            consensus[sym] = record["eps"]
    data = {"index": "NIFTY 500", "min_analysts": MIN_ANALYSTS,
            "basis_tolerance": BASIS_TOLERANCE, **aggregate(symbols, bases, consensus)}
    if data["growth"] is None:
        gaps.append(f"consensus covers {data['coverage']:.0%} of NIFTY 500 net income, under "
                    f"the {MIN_COVERAGE:.0%} needed — market growth withheld")
    env = spine.envelope(data["growth"] is not None, source, data, gaps)
    if data["growth"] is not None:
        spine.write_cache(path, env)
    return env
