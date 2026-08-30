#!/usr/bin/env python3
"""Sector screener — the single definition of sector relative strength.

The invest·sectors screener: rank the NSE sectoral indices by the sector spec's metric
(RS-vs-Nifty windowed + classified by default) and take the top N, over the one
sectoral-index ticker map (`sources/market.py::SECTOR_YF`). The code definition of sector
relative strength, on the shared primitive in `compute/relative_strength.py`, so a
sector's RS and a stock's RS agree.

The shortlist is written to file; the response carries the spine envelope.

Reached through: run_sector_screen.
"""
from __future__ import annotations

import json
import os
from datetime import date

from finance import paths
from finance.compute import relative_strength as rs
from finance.spine import envelope as _envelope

NIFTY = "^NSEI"

# Default sector spec — makes `discover sectors` work out of the box.
DEFAULT_SPEC = {
    "name": "sector-rs-rotation",
    "purpose": "investment",
    "asset": "sectors",
    "screening": {"metric": "rs_vs_nifty"},
    "ranking": {"top_n": 3},
}

KNOWN_METRICS = ("rs_vs_nifty", "index_valuation_percentile")

# Ranking order for the RS classes — Improving (early rotation) is the actionable class,
# then Leading; Weakening and Lagging trail. Within a class, higher 1M then 3M RS wins.
_CLASS_ORDER = {"Improving": 0, "Leading": 1, "Weakening": 2, "Lagging": 3,
                "unclassified": 4}


def _spine_closes(ticker, fresh=False):
    from finance.sources import prices
    env = prices.history(ticker, period="1y", adjusted=True, fresh=fresh)
    return [c["close"] for c in (env.get("data") or {}).get("candles") or []
            if c.get("close") is not None]


def _rs_scan(n, fresh, closes_fn):
    from finance.sources import market
    bench = closes_fn(NIFTY, fresh)
    rows, gaps = [], []
    if len(bench) < 126:
        gaps.append("Nifty history too short to compute sector RS")
        return [], gaps
    for name, ticker in market.SECTOR_YF.items():
        closes = closes_fn(ticker, fresh)
        if len(closes) < 126:
            gaps.append(f"{name} ({ticker}): <6M history, excluded")
            continue
        windows = rs.rs_vs_benchmark(closes, bench)
        rows.append({
            "sector": name, "ticker": ticker,
            "rs_vs_nifty": windows,
            "rs_class": rs.classify(windows["1m"], windows["3m"]),
            "returns": rs.window_returns(closes),
        })
    rows.sort(key=lambda r: (_CLASS_ORDER[r["rs_class"]],
                             -(r["rs_vs_nifty"]["1m"] if r["rs_vs_nifty"]["1m"] is not None else -1e9),
                             -(r["rs_vs_nifty"]["3m"] if r["rs_vs_nifty"]["3m"] is not None else -1e9)))
    return [{"rank": i + 1, **r} for i, r in enumerate(rows[:n])], gaps


def _valuation_scan(n, fresh):
    """Rank the sectoral indices by cheapness — the lower the P/E percentile, the better."""
    from finance.sources import market
    rows, gaps = [], []
    for name in market.SECTOR_INDICES:
        env = market.valuation_percentiles(name, fresh=fresh)
        pe = (env.get("data") or {}).get("pe") or {}
        if pe.get("percentile") is None:
            gaps.append(f"{name}: no valuation percentile")
            continue
        rows.append({"sector": name, "pe": pe.get("current"),
                     "pe_percentile": pe.get("percentile")})
    rows.sort(key=lambda r: r["pe_percentile"])
    return [{"rank": i + 1, **r} for i, r in enumerate(rows[:n])], gaps


def scan(spec=None, top=None, fresh=False, closes_fn=None):
    """The sectoral-index universe → the spec's screening metric → ranked top N."""
    spec = spec or DEFAULT_SPEC
    metric = (spec.get("screening") or {}).get("metric") or "rs_vs_nifty"
    n = top or (spec.get("ranking") or {}).get("top_n") or 3
    closes_fn = closes_fn or _spine_closes

    if metric == "rs_vs_nifty":
        shortlist, gaps = _rs_scan(n, fresh, closes_fn)
    elif metric == "index_valuation_percentile":
        shortlist, gaps = _valuation_scan(n, fresh)
    else:
        shortlist, gaps = [], [f"sector metric {metric!r} not one of {KNOWN_METRICS}"]

    return {
        "as_of": date.today().isoformat(),
        "purpose": "investment",
        "spec": spec.get("name"),
        "metric": metric,
        "ranking_rule": ("Improving > Leading > Weakening > Lagging, then higher 1M then "
                         "3M RS" if metric == "rs_vs_nifty" else "cheapest P/E percentile first"),
        "shortlist": shortlist,
        "gaps": gaps,
    }


def default_out_path():
    return os.path.join(paths.report_dir("discover"), "sector-scan.json")


def report(spec=None, top=None, fresh=False, out=None, **kw):
    """`scan()` in the spine envelope, shortlist persisted as JSON."""
    result = scan(spec, top=top, fresh=fresh, **kw)
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
    return _envelope(bool(result["shortlist"]), "finance.compute.sector_scan", data, gaps)
