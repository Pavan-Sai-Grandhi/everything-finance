#!/usr/bin/env python3
"""Investment stock scorer — the scored shortlist tier stocks were missing.

The invest·stocks counterpart to `compute/fund_scan.py`: take a business-quality query,
run it through the same Tickertape screener `run_fundamental_screen` uses, intersect the
survivors with the spec's named universe, rank them by a momentum metric, and cap to the
top N. **No entry / stop / target / size, no RRR, no signal, no backtest** — this chooses
*what to deep-dive*, not *when to enter*. The per-item LLM pass (`deep-analysis quick`)
applies the elimination criteria to the survivors.

The universe/shortlist is written to file; the response carries the spine envelope.

Reached through: run_stock_scan.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from finance import paths
from finance.compute import relative_strength as rs
from finance.spine import envelope as _envelope

# The ranking metrics an investment spec may name — the set the completeness gate checks.
KNOWN_METRICS = ("return_12m", "return_6m", "rs_vs_nifty")
_LOOKBACK = {"return_12m": 252, "return_6m": 126}
NIFTY = "^NSEI"


def completeness(spec):
    """The investment-spec completeness gate (pure): the fields must be present and the
    ranking metric known. Live resolvability — universe fetch, query-field resolution — is
    the skill's job via `get_universe` / `run_fundamental_screen`. Returns
    {ok, checks, gaps}."""
    checks, gaps = {}, []
    scr = ((spec.get("screening") or {}).get("fundamental") or {})
    checks["has_query"] = bool(str(scr.get("query") or "").strip())
    if not checks["has_query"]:
        gaps.append("screening.fundamental.query is missing or empty")

    metric = ((spec.get("ranking") or {}).get("metric"))
    checks["metric_known"] = metric in KNOWN_METRICS
    if not checks["metric_known"]:
        gaps.append(f"ranking.metric {metric!r} is not one of {KNOWN_METRICS}")

    checks["has_universe"] = bool((spec.get("universe") or {}).get("source"))
    if not checks["has_universe"]:
        gaps.append("universe.source is missing")

    checks["purpose_investment"] = spec.get("purpose") == "investment"
    if not checks["purpose_investment"]:
        gaps.append("purpose is not 'investment'")

    return {"ok": not gaps, "checks": checks, "gaps": gaps}


def _spine_closes(sym, fresh=False):
    """Default close-series loader — 2y adjusted EOD via the data spine, enough for a
    12-month lookback. Returns [] on any gap."""
    from finance.sources import prices
    env = prices.history(sym, period="2y", adjusted=True, fresh=fresh)
    return [c["close"] for c in (env.get("data") or {}).get("candles") or []
            if c.get("close") is not None]


def rank_value(metric, closes, benchmark):
    """The single scalar a symbol is ranked on for `metric`, or None."""
    if metric == "rs_vs_nifty":
        return rs.rs_vs_benchmark(closes, benchmark).get("3m")
    lb = _LOOKBACK.get(metric)
    return rs.pct_return(closes, lb) if lb else None


def _context_row(closes, benchmark):
    """The window returns + RS carried alongside each shortlist row for context."""
    return {"returns": rs.window_returns(closes),
            "rs_vs_nifty": rs.rs_vs_benchmark(closes, benchmark)}


def scan(spec, top=None, fresh=False, market_context=None,
         screen_fn=None, closes_fn=None, workers=8):
    """universe ∩ fundamental quality gate → rank by ranking.metric → top N."""
    from finance.sources import fundamentals, universe

    screen_fn = screen_fn or (lambda q, limit: fundamentals.screen(q, limit=limit))
    closes_fn = closes_fn or _spine_closes

    scr = (spec.get("screening") or {}).get("fundamental") or {}
    query = str(scr.get("query") or "").strip()
    max_survivors = int(scr.get("max_survivors") or 60)
    metric = (spec.get("ranking") or {}).get("metric")
    n = top or (spec.get("ranking") or {}).get("top_n") or 5
    source = (spec.get("universe") or {}).get("source")

    gaps = []
    if not query:
        return _result(spec, [], {"screened": 0, "in_universe": 0, "ranked": 0}, source,
                       metric, market_context, ["no fundamental query in the spec"])

    env = screen_fn(query, max(max_survivors, n) * 2)
    screened = list((env.get("data") or {}).get("candidates") or [])
    gaps += list(env.get("gaps") or [])

    pool = screened
    if source:
        uni, ugaps = universe.resolve_symbols(source, fresh=fresh)
        if uni:
            uni_set = set(uni)
            pool = [s for s in screened if s in uni_set]
        else:
            gaps += ugaps + [f"universe {source!r} not resolved — ranking the full "
                             f"screen instead of its {source} members"]
    pool = pool[:max_survivors]

    if not pool:
        return _result(spec, [], {"screened": len(screened), "in_universe": 0, "ranked": 0},
                       source, metric, market_context,
                       gaps + ["no company passed the quality gate in this universe"])

    if metric not in KNOWN_METRICS:
        gaps.append(f"ranking.metric {metric!r} unknown — kept market-cap order")
        rows = [{"symbol": s, "metric_value": None, "returns": {}, "rs_vs_nifty": {}}
                for s in pool]
        return _result(spec, rows[:n],
                       {"screened": len(screened), "in_universe": len(pool),
                        "ranked": len(rows)}, source, metric, market_context, gaps)

    bench = closes_fn(NIFTY, fresh) if metric == "rs_vs_nifty" else []
    with ThreadPoolExecutor(max_workers=workers) as pool_ex:
        all_closes = list(pool_ex.map(lambda s: closes_fn(s, fresh), pool))

    ranked = []
    for sym, closes in zip(pool, all_closes):
        val = rank_value(metric, closes, bench)
        if val is None:
            gaps.append(f"{sym}: no price history to rank on")
            continue
        ranked.append({"symbol": sym, "metric_value": val, **_context_row(closes, bench)})
    ranked.sort(key=lambda r: r["metric_value"], reverse=True)

    shortlist = [{"rank": i + 1, **r} for i, r in enumerate(ranked[:n])]
    return _result(spec, shortlist,
                   {"screened": len(screened), "in_universe": len(pool),
                    "ranked": len(ranked)}, source, metric, market_context, gaps)


def _result(spec, shortlist, universe_counts, source, metric, market_context, gaps):
    return {
        "as_of": date.today().isoformat(),
        "purpose": "investment",
        "spec": spec.get("name"),
        "ranking_metric": metric,
        "universe": {"source": source, **universe_counts, "shortlisted": len(shortlist)},
        "gates": {"query": ((spec.get("screening") or {}).get("fundamental") or {}).get("query"),
                  "max_survivors": ((spec.get("screening") or {}).get("fundamental")
                                    or {}).get("max_survivors")},
        "market_context": market_context,
        "shortlist": shortlist,
        "gaps": gaps,
    }


def default_out_path():
    return os.path.join(paths.report_dir("discover"), "stock-scan.json")


def report(spec, top=None, fresh=False, market_context=None, out=None, **kw):
    """`scan()` in the spine envelope, shortlist persisted as JSON."""
    result = scan(spec, top=top, fresh=fresh, market_context=market_context, **kw)
    gaps = list(result.get("gaps") or [])
    path = out or default_out_path()
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    except OSError as exc:
        gaps.append(f"could not write the shortlist to {path}: {exc}")
        path = None
    data = {k: v for k, v in result.items() if k != "gaps"}
    data["report_path"] = path
    return _envelope(bool(result["shortlist"]), "finance.compute.stock_scan", data, gaps)
