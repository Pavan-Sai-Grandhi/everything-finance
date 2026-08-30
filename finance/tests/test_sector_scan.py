#!/usr/bin/env python3
"""Offline tests for the sector screener. No network — the close series are synthetic."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = tempfile.mkdtemp(prefix="ef-sectorscan-")

from finance.compute import relative_strength as rs
from finance.compute import sector_scan
from finance.sources import market
from finance.tests.harness import check, run


def _series(r1, r3, r6=0.0, n=200):
    """A series whose 1M/3M/6M returns are exactly r1/r3/r6 (last close fixed at 100)."""
    closes = [100.0] * n
    closes[-1 - 21] = 100.0 / (1 + r1 / 100.0)
    closes[-1 - 63] = 100.0 / (1 + r3 / 100.0)
    closes[-1 - 126] = 100.0 / (1 + r6 / 100.0)
    return closes


# Bank → Improving, IT → Leading (1M 8), Pharma → Leading (1M 3), everything else → Lagging.
_PROFILES = {
    "^NSEBANK": (6.0, -2.0),
    "^CNXIT": (8.0, 10.0),
    "^CNXPHARMA": (3.0, 4.0),
}


def _closes_fn(ticker, fresh=False):
    if ticker == sector_scan.NIFTY:
        return [100.0] * 200
    r1, r3 = _PROFILES.get(ticker, (-10.0, -10.0))
    return _series(r1, r3)


def test_classify_parity():
    check("Leading", rs.classify(5, 8) == "Leading")
    check("Improving", rs.classify(5, -3) == "Improving")
    check("Weakening", rs.classify(-3, 5) == "Weakening")
    check("Lagging", rs.classify(-5, -8) == "Lagging")
    check("either window missing is unclassified", rs.classify(None, 5) == "unclassified")


def test_rs_ranking_order():
    res = sector_scan.scan(top=3, closes_fn=_closes_fn)
    order = [r["sector"] for r in res["shortlist"]]
    # Improving first (Bank), then Leading by higher 1M RS (IT before Pharma).
    check("Improving ranks first", res["shortlist"][0]["rs_class"] == "Improving", str(order))
    check("ranking order Bank, IT, Pharma", order == ["Bank", "IT", "Pharma"], str(order))


def test_classification_attached():
    res = sector_scan.scan(top=10, closes_fn=_closes_fn)
    bank = next(r for r in res["shortlist"] if r["sector"] == "Bank")
    check("Bank's 1M RS is +6 vs a flat Nifty", bank["rs_vs_nifty"]["1m"] == 6.0,
          str(bank["rs_vs_nifty"]))
    check("Bank classified Improving", bank["rs_class"] == "Improving")


def test_unknown_metric_is_a_gap():
    res = sector_scan.scan(spec={"screening": {"metric": "flow_bias"}}, closes_fn=_closes_fn)
    check("an unsupported metric yields no shortlist", res["shortlist"] == [])
    check("and a labelled gap", any("flow_bias" in g for g in res["gaps"]))


def test_default_spec_runs():
    res = sector_scan.scan(closes_fn=_closes_fn)
    check("the default spec uses rs_vs_nifty", res["metric"] == "rs_vs_nifty")
    check("default top_n is 3", len(res["shortlist"]) == 3)


def test_report_envelope_and_file():
    out = os.path.join(tempfile.mkdtemp(), "sector-scan.json")
    env = sector_scan.report(out=out, closes_fn=_closes_fn)
    check("report returns the spine envelope",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"}, sorted(env))
    check("report writes the shortlist to file", env["data"]["report_path"] == out)
    check("the file exists", os.path.exists(out))


def test_sector_universe_is_the_index_map():
    check("scan ranges over SECTOR_YF", len(market.SECTOR_YF) >= 8)


if __name__ == "__main__":
    run(globals())
