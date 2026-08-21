#!/usr/bin/env python3
"""Offline tests for the allocation engine. No network, no MCP.
Run: python3 finance/tests/test_allocation.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import allocation
from finance.tests.harness import check, run


# A ₹10,00,000 mixed book: a 15% single stock, an over-weight sector, a fund. --- #
BOOK = [
    {"ticker": "TCS", "value": 150000, "kind": "stock", "sector": "IT",
     "asset_class": "equity"},                                    # 15% single-stock breach
    {"ticker": "INFY", "value": 120000, "kind": "stock", "sector": "IT",
     "asset_class": "equity"},                                    # IT sector = 27% → breach
    {"ticker": "HDFCBANK", "qty": 100, "ltp": 1500, "kind": "stock", "sector": "Banking",
     "asset_class": "equity"},                                    # value via qty*ltp = 150000
    {"ticker": "ITC", "invested": 80000, "kind": "stock", "sector": "FMCG",
     "asset_class": "equity"},                                    # value via invested
    {"ticker": "PPFAS", "value": 300000, "kind": "fund", "amc": "PPFAS",
     "asset_class": "equity", "style": "value"},
    {"ticker": "LIQUIDBEES", "value": 100000, "kind": "fund", "asset_class": "cash"},
    {"ticker": "GILT", "value": 100000, "kind": "fund", "asset_class": "debt"},
]
TOTAL = 150000 + 120000 + 150000 + 80000 + 300000 + 100000 + 100000  # 1,000,000


def test_market_value_precedence():
    check("value: explicit wins", allocation.market_value({"value": 5, "qty": 9, "ltp": 9}) == 5.0)
    check("value: qty*ltp", allocation.market_value({"qty": 10, "ltp": 20}) == 200.0)
    check("value: invested fallback", allocation.market_value({"invested": 4200}) == 4200.0)
    check("value: qty*avg last", allocation.market_value({"qty": 10, "avg": 30}) == 300.0)
    check("value: unvaluable -> None", allocation.market_value({"ticker": "X"}) is None)


def test_aggregate_and_coverage():
    sec = allocation.aggregate(BOOK, "sector")
    check("aggregate sector IT = 27%", abs(sec["breakdown"]["it"]["pct"] - 27.0) < 0.01,
          sec["breakdown"].get("it"))
    check("aggregate sector unknown from funds",
          abs(sec["breakdown"]["unknown"]["pct"] - 50.0) < 0.01, sec["breakdown"].get("unknown"))
    check("aggregate coverage excludes unknown", abs(sec["coverage"] - 0.5) < 0.001, sec["coverage"])

    ac = allocation.aggregate(BOOK, "asset_class")
    check("aggregate asset equity 80%", abs(ac["breakdown"]["equity"]["pct"] - 80.0) < 0.01,
          ac["breakdown"].get("equity"))
    check("aggregate asset cash 10%", abs(ac["breakdown"]["cash"]["pct"] - 10.0) < 0.01)


def test_concentration_flags():
    flags = allocation.concentration_flags(BOOK)
    dims = {f["dimension"] for f in flags}
    check("flag: single-stock TCS present",
          any(f["dimension"] == "single_stock" and f["category"] == "TCS" for f in flags))
    check("flag: no single-stock for the 30% fund (funds exempt)",
          not any(f["dimension"] == "single_stock" and f["category"] == "PPFAS" for f in flags))
    check("flag: IT sector present", "sector" in dims)
    it_flag = next(f for f in flags if f["dimension"] == "sector")
    check("flag: sector ₹ trim = value - 25% of total",
          abs(it_flag["value"] - (150000 + 120000)) < 1 and "TRIM ₹" in it_flag["suggestion"],
          it_flag["suggestion"])
    check("flags sorted by pct desc", flags == sorted(flags, key=lambda f: f["pct"], reverse=True))


def test_concentration_amc_breach():
    amc_book = [
        {"ticker": "A", "value": 500000, "kind": "fund", "amc": "HDFC AMC"},
        {"ticker": "B", "value": 500000, "kind": "fund", "amc": "HDFC AMC"},
    ]
    amc_flags = allocation.concentration_flags(amc_book)
    check("flag: single AMC 100% breach",
          any(f["dimension"] == "amc" and f["pct"] == 100.0 for f in amc_flags), amc_flags)


def test_concentration_smallcap_sleeve():
    """The cap sleeve comes from a supplied breakdown, not a per-holding tag."""
    cap_flags = allocation.concentration_flags(
        [{"ticker": "X", "value": 1000000, "kind": "stock"}],
        breakdowns={"market_cap": {"large": 600000, "mid": 40000, "small": 300000, "micro": 60000}})
    check("flag: small+micro sleeve 36% breach",
          any(f["dimension"] == "smallcap_microcap" and abs(f["pct"] - 36.0) < 0.01 for f in cap_flags),
          cap_flags)
    check("flag: no sleeve breach when under 30%",
          not any(f["dimension"] == "smallcap_microcap" for f in allocation.concentration_flags(
              [{"ticker": "X", "value": 1000000, "kind": "stock"}],
              breakdowns={"market_cap": {"large": 800000, "small": 200000}})))


def test_asset_drift_vs_target():
    drift = allocation.asset_drift(BOOK, {"equity": 60, "debt": 30, "cash": 10})
    check("drift: equity +20pp over target",
          abs(drift["classes"]["equity"]["drift_pp"] - 20.0) < 0.01, drift["classes"]["equity"])
    check("drift: equity rebalance TRIM present",
          any("TRIM" in r and "equity" in r for r in drift["rebalance"]), drift["rebalance"])
    check("drift: debt under target → ADD",
          any("ADD" in r and "debt" in r for r in drift["rebalance"]), drift["rebalance"])
    check("drift: cash on target → no rebalance line",
          not any("cash" in r for r in drift["rebalance"]))
    check("drift: move_value equity = (60-80)% of total = -200000",
          abs(drift["classes"]["equity"]["move_value"] + 200000) < 1)


def test_asset_drift_relative():
    rel = allocation.asset_drift(BOOK)
    check("drift: relative flag when no target", rel["relative"] is True)
    check("drift: relative has no rebalance lines", rel["rebalance"] == [])
    check("drift: relative still reports current pct",
          abs(rel["classes"]["equity"]["current_pct"] - 80.0) < 0.01)


def test_review_partial_data():
    """An unvaluable holding surfaces as a gap, not a silent zero."""
    partial = allocation.review([
        {"ticker": "OK", "value": 100000, "kind": "stock", "sector": "IT", "asset_class": "equity"},
        {"ticker": "NOPRICE", "kind": "stock"},
    ])
    check("review: unvaluable holding produces a gap",
          any("NOPRICE" in g for g in partial["gaps"]), partial["gaps"])
    check("review: total excludes the unvaluable row", partial["total"] == 100000.0)
    check("review: untagged dimension lowers coverage & notes a gap",
          any("amc:" in g for g in partial["gaps"]) and partial["dimensions"]["amc"]["coverage"] < 1.0)


def test_review_dimension_provenance():
    rev = allocation.review(BOOK, {"equity": 60, "debt": 30, "cash": 10},
                            breakdowns={"market_cap": {"large": 700000, "small": 300000}})
    check("review: market_cap source=supplied", rev["dimensions"]["market_cap"]["source"] == "supplied")
    check("review: sector source=holdings", rev["dimensions"]["sector"]["source"] == "holdings")
    check("review: concentration flags carried through", len(rev["concentration_flags"]) > 0)
    check("review: total is ₹10L", rev["total"] == float(TOTAL))


def test_review_book_routes_every_bundle_key():
    """`review`'s four arguments are positional, so a bundle key landing on the wrong one
    would still return a plausible-looking review. Each key is pinned by its own effect."""
    bundle = {"holdings": BOOK, "targets": {"equity": 30, "debt": 35, "cash": 35},
              "breakdowns": {"market_cap": {"large": 900000, "small": 100000}},
              "thresholds": {"single_stock": 99.0, "single_sector": 99.0}}
    rev = allocation.review_book(bundle)
    check("review_book equals the explicit review call",
          rev == allocation.review(BOOK, bundle["targets"], bundle["breakdowns"],
                                   bundle["thresholds"]))
    check("review_book routes holdings", rev["total"] == float(TOTAL), rev["total"])
    check("review_book routes targets — the 30% equity target drifts against an 80% book",
          rev["asset_drift"]["classes"]["equity"]["target_pct"] == 30.0
          and rev["asset_drift"]["classes"]["equity"]["drift_pp"] > 0,
          rev["asset_drift"]["classes"]["equity"])
    check("review_book routes breakdowns", rev["dimensions"]["market_cap"]["source"] == "supplied")
    check("review_book routes thresholds — 99% ceilings silence the stock/sector flags",
          not [f for f in rev["concentration_flags"]
               if f.get("dimension") in ("single_stock", "single_sector")],
          rev["concentration_flags"])


def test_review_empty_book():
    empty = allocation.review([])
    check("review: empty book ok", empty["total"] == 0.0 and empty["concentration_flags"] == [])


if __name__ == "__main__":
    run(globals())
