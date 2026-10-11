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


for dates,values,years in ((d10[:2],[100],1),(d10[:2],[100,0],1),
                           (d10[:2],[100,float("nan")],1),(list(reversed(d10[:2])),[100,101],1),
                           ([d10[0],d10[0]],[100,101],1),(d10[:2],[100,101],0)):
    try:
        R.rolling_returns(dates,values,years)
        check("invalid rolling input rejected",False)
    except ValueError:
        check("invalid rolling input rejected",True)

# A huge endpoint ratio can overflow even though its long-window CAGR is finite.
long_dates=[date(1900,1,1),date(1900,1,1) + timedelta(days=int(100 * R.YEAR_DAYS))]
result=R.rolling_returns(long_dates,[1e-200,1e200],100)
check("finite long-window CAGR survives endpoint-ratio overflow",len(result) == 1 and all(__import__('math').isfinite(value) for value in result.values()))
for value in (float("nan"),float("inf"),True):
    try:
        R.rolling_stats({"fixture":value})
        check("nonfinite or boolean return cannot become statistics",False)
    except ValueError:
        check("nonfinite or boolean return cannot become statistics",True)
try:
    R.rolling_returns([date(2020,1,1),date(2020,1,2)],[1,1e300],0.001)
    check("unrepresentable CAGR rejected",False)
except ValueError:
    check("unrepresentable CAGR rejected",True)
except OverflowError:
    check("unrepresentable CAGR rejected",False,"raw overflow escaped")

large=R.rolling_stats({"first":1e308,"second":1e308})
check("large finite return mean does not overflow intermediate sum",large["mean"]==1e308)
check("large finite return median does not overflow midpoint sum",large["median"]==1e308)

check('century gap cannot supply a one-year rolling observation',
      R.rolling_returns(long_dates, [100, 110], 1) == {})
start = date(2020, 1, 1)
check('weekend-like endpoint delay remains usable',
      len(R.rolling_returns([start, start + timedelta(days=368)], [100, 110], 1)) == 1)
check('endpoint delayed beyond a week is excluded',
      R.rolling_returns([start, start + timedelta(days=374)], [100, 110], 1) == {})
from finance.compute.fund_scan import nav_metrics
sparse = nav_metrics([{'date': day.isoformat(), 'nav': value}
                     for day, value in zip(long_dates, [100, 110])], 1)
check('no eligible rolling windows cannot be high confidence',
      sparse['n_windows'] == 0 and sparse['confidence'] == 'unknown')
summary()
