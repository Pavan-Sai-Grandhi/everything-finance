"""Rolling-return math for the past-performance pillar.

Point-to-point returns lie, because they hang on two endpoints (`methods/funds.md`). The
headline is **daily-rolled rolling returns** — roll a window across every NAV observation
and report mean/median/min over it — plus max drawdown. A window longer than the fund's
history yields nothing rather than a number computed off a partial series.

Pure math over a NAV series already fetched; the math behind get_fund_scan.
"""
from __future__ import annotations

import statistics
import math
from datetime import date

YEAR_DAYS = 365.25
# Calendar-day tolerance for weekends/holidays, not an exchange-calendar guarantee.
# A later observation outside this bound is missing coverage, not the requested window.
MAX_ENDPOINT_DELAY_DAYS = 7


def _positive(value):
    try:
        return not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value) and value > 0
    except OverflowError:
        return False


def _validate_navs(navs):
    if any(not _positive(value) for value in navs):
        raise ValueError("NAV observations must be finite positive numbers")


def rolling_returns(dates, navs, years):
    """Daily-rolled annualised return (%) for each start that has an observation ~`years`
    later. Returns {start_date_iso: annualised_return_pct} — the map lets two funds align
    on identical start dates. Endpoints may be at most seven calendar days late.
    Empty when history is shorter than the window or has no eligible endpoints.
    Comparisons must also align observation calendars; matching starts alone does not
    guarantee identical end dates."""
    if not _positive(years):
        raise ValueError("rolling window must be finite and positive")
    if len(dates) != len(navs):
        raise ValueError("NAV dates and values must have equal lengths")
    if any(type(day) is not date for day in dates) or any(a >= b for a,b in zip(dates,dates[1:])):
        raise ValueError("NAV dates must be unique and strictly increasing calendar dates")
    _validate_navs(navs)
    target = years * YEAR_DAYS
    if not math.isfinite(target):
        raise ValueError("rolling window is too large")
    out, j, n = {}, 0, len(dates)
    for i in range(n):
        if j <= i:
            j = i + 1
        while j < n and (dates[j] - dates[i]).days < target:
            j += 1
        if j >= n:
            break
        if (dates[j] - dates[i]).days - target > MAX_ENDPOINT_DELAY_DAYS:
            continue
        elapsed = (dates[j] - dates[i]).days / YEAR_DAYS
        # Log-space avoids overflowing the endpoint ratio before annualisation.
        try:
            value = math.expm1((math.log(navs[j]) - math.log(navs[i])) / elapsed) * 100.0
        except OverflowError as exc:
            raise ValueError("annualised return exceeds finite numeric range") from exc
        if not math.isfinite(value):
            raise ValueError("annualised return exceeds finite numeric range")
        out[dates[i].isoformat()] = value
    return out


def rolling_stats(returns_map):
    """mean/median/min/n over a rolling-return map. None fields when empty (young fund)."""
    vals = list(returns_map.values())
    try:
        valid = all(not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value) for value in vals)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("rolling statistics require finite numeric returns")
    if not vals:
        return {"mean": None, "median": None, "min": None, "n": 0}
    try:
        mean = math.fsum(value / len(vals) for value in vals)
        median = statistics.median_low(vals) / 2 + statistics.median_high(vals) / 2
    except OverflowError as exc:
        raise ValueError("rolling summary exceeds finite numeric range") from exc
    if not all(math.isfinite(value) for value in (mean, median)):
        raise ValueError("rolling summary exceeds finite numeric range")
    return {"mean": round(mean, 2), "median": round(median, 2),
            "min": round(min(vals), 2), "n": len(vals)}


def max_drawdown(navs):
    """Deepest peak-to-trough decline over the full series, as a positive %."""
    _validate_navs(navs)
    if len(navs) < 2:
        return None
    peak, mdd = navs[0], 0.0
    for v in navs:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return round(abs(mdd) * 100.0, 2)

