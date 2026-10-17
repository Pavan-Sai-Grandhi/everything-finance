#!/usr/bin/env python3
"""Offline tests for finance/sources/estimates.py (analyst consensus). No network."""
import atexit
import contextlib
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

_TMP_ROOT = tempfile.mkdtemp(prefix="ef-test-estimates-")
os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = os.path.join(_TMP_ROOT, "artifacts")
atexit.register(shutil.rmtree, _TMP_ROOT, True)

import pandas as pd  # noqa: E402

from finance import deps  # noqa: E402
from finance.sources import estimates  # noqa: E402
from finance.tests.harness import check, rel_approx, summary  # noqa: E402


@contextlib.contextmanager
def swap(module, attr, fake):
    orig = getattr(module, attr)
    setattr(module, attr, fake)
    try:
        yield
    finally:
        setattr(module, attr, orig)


def _frame(rows, cols):
    return pd.DataFrame(rows, index=["0q", "+1q", "0y", "+1y"][-len(rows):], columns=cols)


EPS_COLS = ["avg", "low", "high", "yearAgoEps", "numberOfAnalysts", "growth", "currency"]
REV_COLS = ["avg", "low", "high", "numberOfAnalysts", "yearAgoRevenue", "growth", "currency"]


class FakeYF:
    """Stands in for the yfinance module: `Ticker(sym)` with estimate frames."""
    def __init__(self, eps=None, revenue=None, fail=False):
        self.eps, self.revenue, self.fail, self.asked = eps, revenue, fail, []

    def Ticker(self, sym):  # noqa: N802 — mirrors yfinance
        self.asked.append(sym)
        if self.fail:
            raise ConnectionError("down")
        return type("T", (), {"earnings_estimate": self.eps, "revenue_estimate": self.revenue})()


cams_eps = _frame([[22.0, 20.6, 23.3, 19.13, 18, 0.15, "INR"], [25.9, 24.0, 28.3, 22.0, 18, 0.18, "INR"]],
                  EPS_COLS)
cams_rev = _frame([[1.69e10, 1.64e10, 1.73e10, 18, 1.516e10, 0.11, "INR"],
                   [1.92e10, 1.86e10, 1.98e10, 18, 1.69e10, 0.14, "INR"]], REV_COLS)
fake = FakeYF(cams_eps, cams_rev)
with swap(deps, "need", lambda mod, pip_name=None: fake):
    env = estimates.company("cams", fresh=True)
d = env["data"]
check("company: asks Yahoo for the NSE listing", fake.asked == ["CAMS.NS"], fake.asked)
check("company: current-year EPS consensus carried", d["eps"]["current_fy"]["avg"] == 22.0, d)
check("company: growth struck against Yahoo's year-ago EPS",
      rel_approx(d["eps"]["current_fy"]["growth"], 22.0 / 19.13 - 1, 1e-6), d["eps"]["current_fy"])
check("company: revenue converted to ₹ Crore",
      d["revenue"]["current_fy"]["avg"] == 1690.0 and d["revenue_unit"] == "INR Crore", d["revenue"])
check("company: well-covered stock carries no gap", env["ok"] and env["gaps"] == [], env["gaps"])

thin = _frame([[19.9, 19.9, 19.9, 13.35, 1, 0.49, "INR"], [24.4, 18.4, 28.5, 19.9, 4, 0.23, "INR"]], EPS_COLS)
with swap(deps, "need", lambda mod, pip_name=None: FakeYF(thin, None)):
    thin_env = estimates.company("WONDERLA", fresh=True)
check("company: a thin consensus is named", thin_env["ok"] and any("fewer than" in g for g in thin_env["gaps"]),
      thin_env["gaps"])
with swap(deps, "need", lambda mod, pip_name=None: FakeYF(fail=True)):
    down = estimates.company("CAMS", fresh=True)
check("company: a provider failure is a labelled gap", down["ok"] is False and down["gaps"], down)
with swap(deps, "need", lambda mod, pip_name=None: FakeYF(None, None)):
    none = estimates.company("XYZ", fresh=True)
check("company: no consensus is a labelled gap, not zeros", none["ok"] is False and none["gaps"], none)


def eps(year_ago, cur, nxt, analysts=10):
    return {"current_fy": {"avg": cur, "year_ago": year_ago, "analysts": analysts},
            "next_fy": {"avg": nxt, "year_ago": cur, "analysts": analysts}}


bases = {"A": {"eps": 10.0, "net_income": 600.0}, "B": {"eps": 20.0, "net_income": 300.0},
         "C": {"eps": 5.0, "net_income": 100.0}, "L": {"eps": -1.0, "net_income": -50.0}}
agg = estimates.aggregate(["A", "B", "C", "L"], bases,
                          {"A": eps(10.0, 11.0, 12.1), "B": eps(20.0, 22.0, 26.4), "C": eps(5.0, 6.0, 6.6)})
check("aggregate: net-income-weighted growth",
      rel_approx(agg["growth"][0], (600 * 1.1 + 300 * 1.1 + 100 * 1.2) / 1000 - 1, 1e-9), agg)
check("aggregate: next year from the same weights",
      rel_approx(agg["growth"][1], (600 * 1.21 + 300 * 1.32 + 100 * 1.32) / (600 * 1.1 + 300 * 1.1 + 100 * 1.2) - 1,
                 1e-5), agg)
check("aggregate: loss-makers sit outside the base", agg["coverage"] == 1.0 and agg["covered"] == 3, agg)
mismatch = estimates.aggregate(["A", "B", "C"], bases,
                               {"A": eps(2.0, 11.0, 12.1), "B": eps(20.0, 22.0, 26.4), "C": eps(5.0, 6.0, 6.6)})
check("aggregate: a year-ago EPS off the published basis is excluded, and named",
      [r["symbol"] for r in mismatch["excluded_basis"]] == ["A"] and mismatch["growth"] is None, mismatch)
check("aggregate: coverage below the floor withholds the growth",
      rel_approx(mismatch["coverage"], 0.4, 1e-9), mismatch)
thin_agg = estimates.aggregate(["A", "B", "C"], bases,
                               {"A": eps(10.0, 11.0, 12.1, analysts=2), "B": eps(20.0, 22.0, 26.4),
                                "C": eps(5.0, 6.0, 6.6)})
check("aggregate: stocks under the analyst floor do not count", thin_agg["covered"] == 2, thin_agg)

with swap(estimates.universe, "resolve_symbols", lambda name, fresh=False: (["A", "B", "C"], [])), \
        swap(estimates, "_bases", lambda: (bases, None)), \
        swap(estimates, "_consensus", lambda s: ({"eps": {"A": eps(10.0, 11.0, 12.1), "B": eps(20.0, 22.0, 26.4),
                                                          "C": eps(5.0, 6.0, 6.6)}[s]}, None)):
    mkt = estimates.market(fresh=True)
check("market: envelope carries the aggregated growth", mkt["ok"] and mkt["data"]["growth"] == agg["growth"],
      mkt)
with swap(estimates.universe, "resolve_symbols", lambda name, fresh=False: (["A"], [])), \
        swap(estimates, "_bases", lambda: (None, "Tickertape net-income base: HTTP 503")):
    mkt_down = estimates.market(fresh=True)
check("market: a failed base fetch is a labelled gap", mkt_down["ok"] is False and mkt_down["gaps"], mkt_down)

summary()
