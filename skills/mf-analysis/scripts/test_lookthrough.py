#!/usr/bin/env python3
"""Offline tests for the look-through math (spec §2, §8). No network. Run:
  python3 skills/mf-analysis/scripts/test_lookthrough.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lookthrough as L  # noqa: E402

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


def approx(a, b, tol=0.01):
    return a is not None and abs(a - b) <= tol


# --- weighted harmonic (correct P/E aggregation) -----------------------------
pe, w = L.weighted_harmonic([(50, 10), (50, 30)])
check("harmonic 50/50 of 10 & 30 = 15", approx(pe, 15.0) and w == 100)
pe, w = L.weighted_harmonic([(40, 20), (60, None)])
check("harmonic ignores None value, covered weight excludes it", approx(pe, 20.0) and w == 40)
pe, w = L.weighted_harmonic([(50, -5), (50, 0)])
check("harmonic drops non-positive multiples → None", pe is None and w == 0.0)

# --- weighted mean (ROE / growth) --------------------------------------------
m, w = L.weighted_mean([(50, 20), (50, 10)])
check("mean 50/50 of 20 & 10 = 15", approx(m, 15.0) and w == 100)
m, _ = L.weighted_mean([(50, 30), (50, -10)])
check("mean handles negative growth", approx(m, 10.0))

# --- CAGR --------------------------------------------------------------------
check("cagr one period 100→121 = 21%", approx(L.cagr([100, 121]), 21.0))
check("cagr two periods 100→110→121 = 10%", approx(L.cagr([100, 110, 121]), 10.0))
check("cagr <2 points → None", L.cagr([100]) is None)
check("cagr non-positive endpoint → None", L.cagr([-5, 121]) is None)

# --- cap-tilt classification -------------------------------------------------
check("cap_bucket large", L.cap_bucket(80000) == "large")
check("cap_bucket mid", L.cap_bucket(20000) == "mid")
check("cap_bucket small", L.cap_bucket(8000) == "small")
check("cap_bucket unknown → None", L.cap_bucket(None) is None)

# --- concentration -----------------------------------------------------------
c = L.concentration([{"weight": 40}, {"weight": 35}, {"weight": 15}, {"weight": 10}])
check("concentration top5/top10 = full when <=10 holdings", c["top5"] == 1.0 and c["top10"] == 1.0)
check("concentration hhi", approx(c["hhi"], 0.315) and c["n"] == 4)

# --- full portfolio metrics with partial coverage ----------------------------
HOLD = [
    {"weight": 40, "pe": 20, "pb": 3, "roe": 18, "growth": 15, "mcap": 80000},
    {"weight": 35, "pe": 30, "pb": 5, "roe": 22, "growth": 25, "mcap": 20000},
    {"weight": 15, "pe": 10, "pb": 1.5, "roe": 12, "growth": 8, "mcap": 8000},
    {"weight": 10},  # unpriced holding — keeps its weight, lowers coverage
]
pm = L.portfolio_metrics(HOLD)
check("portfolio P/E harmonic", approx(pm["portfolio_pe"]["value"], 19.29))
check("portfolio P/E coverage = 0.9 (unpriced 10% excluded)", pm["portfolio_pe"]["coverage"] == 0.9)
check("portfolio P/B harmonic", approx(pm["portfolio_pb"]["value"], 2.97))
check("portfolio ROE weighted mean", approx(pm["portfolio_roe"]["value"], 18.56))
check("earnings growth weighted mean", approx(pm["earnings_growth"]["value"], 17.72))
check("cap-tilt large fraction", approx(pm["cap_tilt"]["large"], 0.4444))
check("cap-tilt mid fraction", approx(pm["cap_tilt"]["mid"], 0.3889))
check("cap-tilt small fraction", approx(pm["cap_tilt"]["small"], 0.1667))

# --- missing-holding handling: no priced rows at all -------------------------
pm0 = L.portfolio_metrics([{"weight": 100}])
check("all-unpriced → None value, zero coverage",
      pm0["portfolio_pe"]["value"] is None and pm0["portfolio_pe"]["coverage"] == 0.0)

# --- extraction from a screener.in data-pack ---------------------------------
DATA = {
    "ratios": {"Stock P/E": 24.3, "Market Cap": 1989000.0, "ROE": 9.5,
               "Current Price": 2951.0, "Book Value": 1200.0},
    "pnl_10y": {"columns": ["Mar22", "Mar23", "Mar24", "TTM"],
                "rows": {"Sales": [7, 8, 9, 9], "EPS in Rs": [89.78, 98.62, 102.94, 116.84]}},
}
f = L.stock_fields(DATA)
check("stock_fields pe", f["pe"] == 24.3)
check("stock_fields mcap", f["mcap"] == 1989000.0)
check("stock_fields roe", f["roe"] == 9.5)
check("stock_fields P/B derived from price/book", approx(f["pb"], 2.46))
check("stock_fields growth = EPS CAGR", approx(f["growth"], 9.18))
check("stock_fields empty data → all None",
      all(v is None for v in L.stock_fields({}).values()))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
