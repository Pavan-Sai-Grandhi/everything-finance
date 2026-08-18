#!/usr/bin/env python3
"""Rolling-return math for the past-performance pillar.

Varsity's hierarchy: point-to-point returns lie, because they hang on two endpoints. The
headline is **daily-rolled rolling returns** — roll a window across every NAV observation
and report mean/median/min over it — plus max drawdown. A window longer than the fund's
history yields nothing rather than a number computed off a partial series.

Pure math over a NAV series already fetched; nothing here reaches the network.
Library only: the math behind get_fund_scan.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta

YEAR_DAYS = 365.25


def rolling_returns(dates, navs, years):
    """Daily-rolled annualised return (%) for each start that has an observation ~`years`
    later. Returns {start_date_iso: annualised_return_pct} — the map lets two funds align
    on identical start dates. Empty when history is shorter than the window."""
    target = years * YEAR_DAYS
    out, j, n = {}, 0, len(dates)
    for i in range(n):
        if j <= i:
            j = i + 1
        while j < n and (dates[j] - dates[i]).days < target:
            j += 1
        if j >= n:
            break
        elapsed = (dates[j] - dates[i]).days / YEAR_DAYS
        out[dates[i].isoformat()] = ((navs[j] / navs[i]) ** (1.0 / elapsed) - 1.0) * 100.0
    return out


def rolling_stats(returns_map):
    """mean/median/min/n over a rolling-return map. None fields when empty (young fund)."""
    vals = list(returns_map.values())
    if not vals:
        return {"mean": None, "median": None, "min": None, "n": 0}
    return {"mean": round(statistics.fmean(vals), 2),
            "median": round(statistics.median(vals), 2),
            "min": round(min(vals), 2),
            "n": len(vals)}


def max_drawdown(navs):
    """Deepest peak-to-trough decline over the full series, as a positive %."""
    if len(navs) < 2:
        return None
    peak, mdd = navs[0], 0.0
    for v in navs:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return round(abs(mdd) * 100.0, 2)


