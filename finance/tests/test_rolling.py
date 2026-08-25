#!/usr/bin/env python3
"""Offline tests for the rolling-return math (spec §2, §8). No network."""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import rolling as R
from finance.tests.harness import approx, check, summary


def expo(rate, years, start=date(2016, 1, 1), nav0=100.0):
    """Daily NAV series growing at exactly `rate`/yr — the oracle."""
    dates, navs, d = [], [], start
    end = start + timedelta(days=int(years * R.YEAR_DAYS))
    while d <= end:
        dates.append(d)
        navs.append(nav0 * (1.0 + rate) ** ((d - start).days / R.YEAR_DAYS))
        d += timedelta(days=1)
    return dates, navs


d10, n10 = expo(0.10, 6)
for label, yrs in (("1y", 1), ("3y", 3), ("5y", 5)):
    s = R.rolling_stats(R.rolling_returns(d10, n10, yrs))
    check(f"{label} rolling mean = 10.0 on a 10%/yr series", approx(s["mean"], 10.0, tol=0.05), s)
    check(f"{label} rolling min = mean on a constant-rate series",
          approx(s["min"], 10.0, tol=0.05), s)

check("max drawdown 100→120→90→130 = 25%",
      approx(R.max_drawdown([100, 120, 90, 130]), 25.0, tol=0.05))
check("max drawdown monotonic-up series = 0", approx(R.max_drawdown(n10), 0.0, tol=0.05))
check("max drawdown <2 points → None", R.max_drawdown([100]) is None)

dy, ny = expo(0.10, 0.5)
y1 = R.rolling_stats(R.rolling_returns(dy, ny, 1))
y5 = R.rolling_stats(R.rolling_returns(dy, ny, 5))
check("young fund: 1Y rolling empty (n=0)", y1["n"] == 0)
check("young fund: 1Y mean is None, never 0.0", y1["mean"] is None)
check("young fund: 5Y rolling mean is None", y5["mean"] is None)
check("young fund: 5Y min is None, never fabricated", y5["min"] is None)
check("young fund: drawdown still computable from what exists",
      R.max_drawdown(ny) is not None)


summary()
