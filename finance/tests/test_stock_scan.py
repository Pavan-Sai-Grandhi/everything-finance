#!/usr/bin/env python3
"""Offline tests for the investment stock scorer. No network — screen/closes injected."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = tempfile.mkdtemp(prefix="ef-stockscan-")

from finance.compute import stock_scan
from finance.spine import envelope as _envelope
from finance.tests.harness import check, run

_SPEC = {
    "name": "quality-momentum",
    "purpose": "investment",
    "universe": {"source": ["AAA", "BBB", "CCC", "DDD"]},
    "screening": {"fundamental": {"query": "ROCE > 15", "max_survivors": 3}},
    "ranking": {"metric": "return_12m", "top_n": 2},
}


def _series(ret_pct, n=300):
    """A flat series whose 252/63-bar lookback return is exactly `ret_pct`%."""
    closes = [100.0] * n
    closes[-1] = 100.0 * (1 + ret_pct / 100.0)
    return closes


# AAA best, CCC worst; ZZZ passes the screen but is outside the universe.
_RETURNS = {"AAA": 40.0, "BBB": 20.0, "CCC": 5.0, "DDD": -10.0, "ZZZ": 99.0}


def _screen_fn(query, limit):
    return _envelope(True, "stub", {"candidates": ["ZZZ", "AAA", "BBB", "CCC", "DDD"]}, [])


def _closes_fn(sym, fresh=False):
    return _series(_RETURNS.get(sym, 0.0))


def _scan(spec=None, top=None):
    return stock_scan.scan(spec or _SPEC, top=top, screen_fn=_screen_fn, closes_fn=_closes_fn)


def test_completeness_gate():
    good = stock_scan.completeness(_SPEC)
    check("a complete investment spec passes", good["ok"], str(good["gaps"]))
    bad = stock_scan.completeness({**_SPEC, "ranking": {"metric": "sharpe"}})
    check("an unknown ranking metric fails", not bad["ok"])
    check("the failure names the metric", any("sharpe" in g for g in bad["gaps"]))


def test_intersects_with_universe():
    res = _scan()
    syms = [r["symbol"] for r in res["shortlist"]]
    check("ZZZ passed the screen but is outside the universe — dropped", "ZZZ" not in syms)
    check("screened count is the full screen", res["universe"]["screened"] == 5)
    check("in_universe is the intersection", res["universe"]["in_universe"] == 3,
          str(res["universe"]))


def test_ranks_and_caps():
    res = _scan()
    check("top_n caps the shortlist at 2", len(res["shortlist"]) == 2)
    check("ranked by return_12m descending",
          [r["symbol"] for r in res["shortlist"]] == ["AAA", "BBB"],
          str([r["symbol"] for r in res["shortlist"]]))
    check("rank 1 carries its metric value",
          res["shortlist"][0]["metric_value"] == 40.0, str(res["shortlist"][0]))


def test_max_survivors_caps_the_pool():
    # max_survivors=3, so only the top 3 in-universe by screen order are ranked.
    res = _scan()
    check("pool capped at max_survivors", res["universe"]["in_universe"] == 3)


def test_rs_vs_nifty_metric():
    spec = {**_SPEC, "ranking": {"metric": "rs_vs_nifty", "top_n": 3}}
    res = stock_scan.scan(spec, screen_fn=_screen_fn, closes_fn=_closes_fn)
    check("rs_vs_nifty ranks by 3M outperformance",
          [r["symbol"] for r in res["shortlist"]] == ["AAA", "BBB", "CCC"],
          str([r["symbol"] for r in res["shortlist"]]))


def test_top_arg_overrides_spec_top_n():
    res = _scan(top=1)
    check("the top argument wins over ranking.top_n", len(res["shortlist"]) == 1)


def test_no_entry_exit_required():
    # The spec carries no entry/exit/sizing — the scorer must not need them.
    check("scan runs on a spec with no trading half", _scan()["shortlist"], "empty shortlist")


def test_report_envelope_and_file():
    out = os.path.join(tempfile.mkdtemp(), "stock-scan.json")
    env = stock_scan.report(_SPEC, out=out, screen_fn=_screen_fn, closes_fn=_closes_fn)
    check("report returns the spine envelope",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"}, sorted(env))
    check("report writes the shortlist to file", env["data"]["report_path"] == out)
    check("the file holds the shortlist", os.path.exists(out))


if __name__ == "__main__":
    run(globals())
