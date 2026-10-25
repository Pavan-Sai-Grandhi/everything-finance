"""Rolling-return math for the past-performance pillar.

Point-to-point returns lie, because they hang on two endpoints (`methods/funds.md`). The
headline is **daily-rolled rolling returns** — roll a window across every NAV observation
and report mean/median/min over it — plus max drawdown. A window longer than the fund's
history yields nothing rather than a number computed off a partial series.

A lump sum is not how most holders invest, so the SIP view is computed too: every monthly
SIP the history holds, how often it ended below the money put in, and its XIRR spread. The
deepest drawdown is reported as an episode, with how long the holder sat below the peak.

Pure math over a NAV series already fetched; the math behind get_fund_scan.
"""
from __future__ import annotations

import bisect
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


def drawdown_episode(dates, navs):
    """The deepest decline as an episode a holder lived through: depth %, the peak, the
    trough, the date the NAV first regained the peak (None while still below it), and the
    days from peak to recovery or, unrecovered, to the last observation."""
    _check_series(dates, navs)
    if len(navs) < 2:
        return None
    peak_i, worst = 0, (0.0, 0, 0)
    for i, v in enumerate(navs):
        if v > navs[peak_i]:
            peak_i = i
        dd = v / navs[peak_i] - 1.0
        if dd < worst[0]:
            worst = (dd, peak_i, i)
    depth, p, t = worst
    if depth == 0.0:
        return {"depth_pct": 0.0, "peak": None, "trough": None, "recovered": None,
                "days_underwater": 0}
    r = next((i for i in range(t + 1, len(navs)) if navs[i] >= navs[p]), None)
    end = dates[r] if r is not None else dates[-1]
    return {"depth_pct": round(abs(depth) * 100.0, 2), "peak": dates[p].isoformat(),
            "trough": dates[t].isoformat(),
            "recovered": dates[r].isoformat() if r is not None else None,
            "days_underwater": (end - dates[p]).days}


def _check_series(dates, navs):
    if len(dates) != len(navs):
        raise ValueError("NAV dates and values must have equal lengths")
    if any(type(day) is not date for day in dates) or any(a >= b for a,b in zip(dates,dates[1:])):
        raise ValueError("NAV dates must be unique and strictly increasing calendar dates")
    _validate_navs(navs)


def _add_months(day, months):
    y, m = divmod(day.month - 1 + months, 12)
    year, month = day.year + y, m + 1
    last = (date(year + (month == 12), month % 12 + 1, 1) - date(year, month, 1)).days
    return date(year, month, min(day.day, last))


def _xirr(flows):
    """Annual rate r with sum(cf / (1+r)^(t/YEAR_DAYS)) = 0, for flows that are outflows
    followed by one inflow (one sign change, so the root is unique). Bisection."""
    t0 = flows[0][0]

    def npv(rate):
        return math.fsum(cf / (1.0 + rate) ** ((d - t0).days / YEAR_DAYS) for d, cf in flows)

    lo, hi = -0.9999, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(mid) > 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-9:
            break
    return (lo + hi) / 2


def sip_outcomes(dates, navs, years):
    """Every monthly SIP of `years` the history holds, one per calendar month of start.

    Equal instalments buy at the first NAV on or after each monthly anniversary of the
    start; the units are valued at the first NAV on or after the end. A start whose
    instalment or end NAV lands more than MAX_ENDPOINT_DELAY_DAYS late is skipped, never
    priced off a stale NAV. Returns {n, pct_negative, median_xirr, min_xirr}: the share of
    SIPs that ended below the money put in, and the distribution of their XIRR (%).
    None fields when no window fits."""
    _check_series(dates, navs)
    if isinstance(years, bool) or not isinstance(years, int) or years < 1:
        raise ValueError("SIP window must be a whole number of years")
    empty = {"n": 0, "pct_negative": None, "median_xirr": None, "min_xirr": None}
    if len(dates) < 2:
        return empty

    def at(target):
        i = bisect.bisect_left(dates, target)
        if i < len(dates) and (dates[i] - target).days <= MAX_ENDPOINT_DELAY_DAYS:
            return i
        return None

    starts, seen = [], set()
    for d in dates:
        if (d.year, d.month) not in seen:
            seen.add((d.year, d.month))
            starts.append(d)
    xirrs, negative = [], 0
    for s in starts:
        if _add_months(s, 12 * years) > dates[-1]:
            break
        buys = [at(_add_months(s, k)) for k in range(12 * years)]
        end = at(_add_months(s, 12 * years))
        if end is None or None in buys:
            continue
        units = math.fsum(1.0 / navs[i] for i in buys)
        value = units * navs[end]
        rate = _xirr([(dates[i], -1.0) for i in buys] + [(dates[end], value)])
        if rate is None:
            continue
        xirrs.append(rate * 100.0)
        negative += value < len(buys)
    if not xirrs:
        return empty
    return {"n": len(xirrs), "pct_negative": round(100.0 * negative / len(xirrs), 1),
            "median_xirr": round(statistics.median(xirrs), 2),
            "min_xirr": round(min(xirrs), 2)}

