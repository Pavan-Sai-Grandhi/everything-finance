#!/usr/bin/env python3
"""Offline tests for the rolling-return math (spec §2, §8). No network. Run:
  python3 skills/mf-analysis/scripts/test_rolling.py

Validated against a *known* NAV series: exact exponential growth at rate r makes every
daily-rolled annualised return equal r, so mean = median = min = r — a clean oracle.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rolling as R  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


def approx(a, b, tol=0.05):
    return a is not None and abs(a - b) <= tol


def expo(rate, years, start=date(2016, 1, 1), nav0=100.0):
    """Daily NAV series growing at exactly `rate`/yr — the oracle."""
    dates, navs, d = [], [], start
    end = start + timedelta(days=int(years * R.YEAR_DAYS))
    while d <= end:
        dates.append(d)
        navs.append(nav0 * (1.0 + rate) ** ((d - start).days / R.YEAR_DAYS))
        d += timedelta(days=1)
    return dates, navs


# --- known-series rolling returns: every window equals the growth rate --------
d10, n10 = expo(0.10, 6)
for label, yrs in (("1y", 1), ("3y", 3), ("5y", 5)):
    s = R.rolling_stats(R.rolling_returns(d10, n10, yrs))
    check(f"{label} rolling mean = 10.0 on a 10%/yr series", approx(s["mean"], 10.0), s)
    check(f"{label} rolling min = mean on a constant-rate series", approx(s["min"], 10.0), s)

# --- point-to-point CAGR matches the known rate ------------------------------
check("point-to-point 5Y CAGR = 10.0", approx(R.trailing_cagr(d10, n10, 5), 10.0))
check("point-to-point 1Y CAGR = 10.0", approx(R.trailing_cagr(d10, n10, 1), 10.0))

# --- max drawdown on a hand series -------------------------------------------
check("max drawdown 100→120→90→130 = 25%", approx(R.max_drawdown([100, 120, 90, 130]), 25.0))
check("max drawdown monotonic-up series = 0", approx(R.max_drawdown(n10), 0.0))
check("max drawdown <2 points → None", R.max_drawdown([100]) is None)

# --- Sharpe on a hand series (rf 6%) -----------------------------------------
# rets [0.1, -0.1]: mean 0, sample sd 0.141421 → sharpe = (0 - 0.06)/(0.141421*√252)
check("sharpe of [100,110,99] ≈ -0.03", approx(R.sharpe([100, 110, 99]), -0.03, tol=0.005))
check("sharpe of a zero-vol series → None", R.sharpe([100, 100, 100]) is None)

# --- window alignment across funds (% beating benchmark) ---------------------
d12, n12 = expo(0.12, 6)
fund = R.rolling_returns(d12, n12, 1)
bench = R.rolling_returns(d10, n10, 1)
check("12% fund beats 10% benchmark in 100% of aligned windows",
      approx(R.pct_beating(fund, bench), 100.0))
check("10% fund beats 12% benchmark in 0% of aligned windows",
      approx(R.pct_beating(bench, fund), 0.0))
check("pct_beating None when windows don't align",
      R.pct_beating({"2020-01-01": 12.0}, {"2021-01-01": 10.0}) is None)

# --- young fund: history shorter than the window -----------------------------
dy, ny = expo(0.10, 0.5)  # 6 months
rep = R.analyze(dy, ny)
check("young fund: 1Y rolling empty (n=0)", rep["rolling_returns"]["1y"]["n"] == 0)
check("young fund: 5Y rolling mean is None", rep["rolling_returns"]["5y"]["mean"] is None)
check("young fund: gap labelled, no crash",
      any("history shorter" in g for g in rep["gaps"]))
check("young fund: 1Y point-to-point None", rep["point_to_point_cagr"]["1y"] is None)

# --- parse_mfapi: newest-first DD-MM-YYYY → ascending floats ------------------
payload = {"data": [{"date": "03-01-2016", "nav": "102.0"},
                    {"date": "02-01-2016", "nav": "101.0"},
                    {"date": "01-01-2016", "nav": "100.0"},
                    {"date": "bad", "nav": "x"}]}
pd, pn = R.parse_mfapi(payload)
check("parse_mfapi sorts ascending and drops bad rows",
      pd[0] == date(2016, 1, 1) and pn == [100.0, 101.0, 102.0], (pd, pn))

# --- analyze integrates benchmark alignment ----------------------------------
rep2 = R.analyze(d12, n12, bench=(d10, n10))
check("analyze reports pct_beating_benchmark on 1Y",
      approx(rep2["rolling_returns"]["1y"]["pct_beating_benchmark"], 100.0))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
