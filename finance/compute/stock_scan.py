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
import math
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from finance import paths, spine
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
    if not isinstance(spec, dict):
        return {"ok": False, "checks": {}, "gaps": ["spec must be a mapping"]}
    for name in ("screening", "ranking", "universe"):
        if spec.get(name) is not None and not isinstance(spec[name], dict):
            return {"ok": False, "checks": {}, "gaps": [f"{name} must be a mapping"]}
    fundamental = (spec.get("screening") or {}).get("fundamental")
    if fundamental is not None and not isinstance(fundamental, dict):
        return {"ok": False, "checks": {}, "gaps": ["fundamental screen must be a mapping"]}
    scr = ((spec.get("screening") or {}).get("fundamental") or {})
    provider = str(scr.get("provider") or "tickertape").strip().lower()
    if provider != "tickertape":
        gaps.append(f"unapproved fundamental provider {provider!r}; use Tickertape or report a data gap")
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
    from finance.sources import prices
    return prices.close_history(sym, fresh=fresh)


def rank_value(metric, closes, benchmark):
    """The single scalar a symbol is ranked on for `metric`, or None."""
    if metric == "rs_vs_nifty":
        return rs.rs_vs_benchmark(closes, benchmark).get("3m")
    lb = _LOOKBACK.get(metric)
    return rs.pct_return(closes, lb) if lb else None


def _context_row(closes, benchmark, dates=None, benchmark_dates=None):
    """Each relative return must compare the same dated sessions."""
    relative = rs.rs_vs_benchmark(closes, benchmark)
    if dates:
        for key, window in rs.WINDOWS.items():
            if dates[-window-1:] != (benchmark_dates or [])[-window-1:]:
                relative[key] = None
    return {"returns": rs.window_returns(closes), "rs_vs_nifty": relative}


def scan(spec, top=None, fresh=False, market_context=None,
         screen_fn=None, closes_fn=None, workers=8):
    """universe ∩ fundamental quality gate → rank by ranking.metric → top N.

    The quality gate uses Tickertape's approved query fields. Unsupported
    providers fail validation before any screen, universe or price fetch."""
    from finance.sources import fundamentals, universe

    validation = completeness(spec)
    if not validation["ok"]:
        return _result({"name": spec.get("name") if isinstance(spec, dict) else None}, [],
                       {"screened": 0, "in_universe": 0, "ranked": 0}, None, None,
                       market_context, validation["gaps"])
    screen_fn = screen_fn or (lambda q, limit: fundamentals.screen(q, limit=limit, fresh=fresh))
    closes_fn = closes_fn or _spine_closes

    scr = (spec.get("screening") or {}).get("fundamental") or {}
    query = str(scr.get("query") or "").strip()
    max_survivors = scr.get("max_survivors", 60)
    metric = (spec.get("ranking") or {}).get("metric")
    n = top if top is not None else (spec.get("ranking") or {}).get("top_n", 5)
    source = (spec.get("universe") or {}).get("source")
    if any(type(value) is not int or value <= 0 for value in (max_survivors, n, workers)):
        return _result(spec, [], {"screened": 0, "in_universe": 0, "ranked": 0}, source,
                       metric, market_context, ["survivor, shortlist and worker limits must be positive integers"])
    limit = max(max_survivors, n) * 2

    gaps = []
    try:
        env = screen_fn(query, limit)
    except Exception as exc:
        env = _envelope(False, "fundamental gate", {}, [f"fundamental screen unavailable ({type(exc).__name__})"])
    if not isinstance(env, dict) or env.get("ok") is not True:
        return _result(spec, [], {"screened": 0, "in_universe": 0, "ranked": 0}, source,
                       metric, market_context, (env.get("gaps") or [] if isinstance(env, dict) else [])
                       + ["required fundamental gate did not succeed"])
    data = env.get("data")
    screened = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(screened, list) or any(not isinstance(symbol, str) or not symbol.strip() for symbol in screened):
        return _result(spec, [], {"screened": 0, "in_universe": 0, "ranked": 0}, source,
                       metric, market_context, ["fundamental screen returned malformed candidates"])
    screened = list(dict.fromkeys(screened))
    gaps += list(env.get("gaps") or [])

    pool = screened
    if source:
        try:
            uni, ugaps = universe.resolve_symbols(source, fresh=fresh)
        except Exception as exc:
            uni, ugaps = [], [f"universe unavailable ({type(exc).__name__})"]
        gaps += ugaps
        if uni:
            uni_set = set(uni)
            pool = [s for s in screened if s in uni_set]
        else:
            return _result(spec, [], {"screened": len(screened), "in_universe": 0, "ranked": 0},
                           source, metric, market_context,
                           gaps + [f"required universe {source!r} not resolved; no shortlist produced"])
    pool = pool[:max_survivors]

    if not pool:
        return _result(spec, [], {"screened": len(screened), "in_universe": 0, "ranked": 0},
                       source, metric, market_context,
                       gaps + ["no company passed the quality gate in this universe"])

    def load(symbol):
        return rs.load_history(closes_fn, symbol, fresh)
    bench = load(NIFTY) if metric == "rs_vs_nifty" else {"closes": [], "dates": [], "gaps": []}
    gaps.extend(f"{NIFTY}: {gap}" for gap in bench["gaps"])
    with ThreadPoolExecutor(max_workers=workers) as pool_ex:
        histories = list(pool_ex.map(load, pool))
    latest_day = max((h["dates"][-1] for h in histories if h["dates"]), default=None)
    anchor_dates = max((h["dates"] for h in histories if h["dates"] and h["dates"][-1] == latest_day), key=len, default=[])
    ranked = []
    for sym, history in zip(pool, histories):
        gaps.extend(f"{sym}: {gap}" for gap in history["gaps"])
        closes, dates = history["closes"], history["dates"]
        if dates and dates[-1] != latest_day:
            gaps.append(f"{sym}: last candle {dates[-1]} differs from scan date {latest_day}; not ranked")
            continue
        if metric == "rs_vs_nifty" and dates and dates[-64:] != bench["dates"][-64:]:
            gaps.append(f"{sym}: stock and benchmark sessions do not align; not ranked")
            continue
        lookback = _LOOKBACK.get(metric)
        if dates and lookback and dates[-lookback-1:] != anchor_dates[-lookback-1:]:
            gaps.append(f"{sym}: return window sessions differ from the scan reference; not ranked")
            continue
        val = rank_value(metric, closes, bench["closes"])
        if val is None or not math.isfinite(val):
            gaps.append(f"{sym}: no price history to rank on")
            continue
        ranked.append({"symbol": sym, "metric_value": val, "price_as_of": dates[-1] if dates else None,
                       "price_source": history.get("source"), "price_fetched_at": history.get("fetched_at"),
                       **_context_row(closes, bench["closes"], dates, bench["dates"])})
    ranked.sort(key=lambda r: r["metric_value"], reverse=True)

    shortlist = [{"rank": i + 1, **r} for i, r in enumerate(ranked[:n])]
    return _result(spec, shortlist,
                   {"screened": len(screened), "in_universe": len(pool),
                    "ranked": len(ranked)}, source, metric, market_context, gaps)


def _result(spec, shortlist, universe_counts, source, metric, market_context, gaps):
    price_dates = {row.get("price_as_of") for row in shortlist}
    return {
        "as_of": next(iter(price_dates)) if len(price_dates) == 1 else None,
        "generated_on": date.today().isoformat(),
        "purpose": "investment",
        "spec": spec.get("name"),
        "ranking_metric": metric,
        "universe": {"source": source, **universe_counts, "shortlisted": len(shortlist)},
        "gates": {"provider": (((spec.get("screening") or {}).get("fundamental") or {})
                               .get("provider") or "tickertape"),
                  "query": ((spec.get("screening") or {}).get("fundamental") or {}).get("query"),
                  "screen_url": ((spec.get("screening") or {}).get("fundamental")
                                 or {}).get("screen_url"),
                  "max_survivors": ((spec.get("screening") or {}).get("fundamental")
                                    or {}).get("max_survivors")},
        "market_context": market_context,
        "shortlist": shortlist,
        "gaps": gaps,
    }


def default_out_path():
    return os.path.join(paths.report_dir("discover"), "stock-scan.json")


def report(spec, top=None, fresh=False, market_context=None, out=None, **kw):
    """`scan()` in the spine envelope; `out` names a prefix for immutable JSON evidence."""
    result = scan(spec, top=top, fresh=fresh, market_context=market_context, **kw)
    gaps = list(result.get("gaps") or [])
    path = None
    try:
        target = os.fspath(out or default_out_path())
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        prefix = target[:-5] if target.endswith(".json") else target
        path = spine.publish_evidence(prefix, ".json", lambda fh:
            json.dump(result, fh, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False))
    except (OSError, ValueError, TypeError) as exc:
        gaps.append(f"could not persist shortlist evidence ({type(exc).__name__})")
    data = {k: v for k, v in result.items() if k != "gaps"}
    data["report_path"] = path
    return _envelope(bool(result["shortlist"]), "finance.compute.stock_scan", data, gaps)
