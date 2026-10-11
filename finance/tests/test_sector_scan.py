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
    check("report writes the shortlist to file", env["data"]["report_path"].startswith(out[:-5]+"-"))
    check("the file exists", os.path.exists(env["data"]["report_path"]))


def test_sector_universe_is_the_index_map():
    check("scan ranges over SECTOR_YF", len(market.SECTOR_YF) >= 8)


def test_invalid_prices_are_not_market_classifications():
    for bad in (float('nan'),float('inf'),True):
        check('invalid RS is unclassified',rs.classify(bad,5)=='unclassified',bad)
        check('invalid price cannot produce a return',rs.pct_return([100,bad],1) is None,bad)
    check('negative price cannot produce a return',rs.pct_return([-100,100],1) is None)


def test_sector_failure_is_isolated():
    def loader(ticker,fresh=False):
        if ticker=='^NSEBANK': raise OSError('fixture price outage')
        return _closes_fn(ticker,fresh)
    try:
        result=sector_scan.scan(closes_fn=loader)
        check('one sector failure preserves other sectors',bool(result['shortlist']) and any('Bank' in gap for gap in result['gaps']),result)
    except Exception as exc:
        check('one sector failure preserves other sectors',False,type(exc).__name__)


def test_invalid_limit_refuses_before_fetching():
    from unittest.mock import Mock
    loader=Mock(side_effect=_closes_fn)
    result=sector_scan.scan(top=0,closes_fn=loader)
    check('zero limit is not silently replaced by the default',not loader.called and not result['shortlist'] and bool(result['gaps']))


def test_sector_dated_windows_must_match():
    from datetime import date,timedelta
    dates=[(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(200)]
    def loader(ticker,fresh=False):
        ds=dates.copy()
        if ticker=='^NSEBANK': ds[-20]='2025-01-01'
        return {'closes':_closes_fn(ticker),'dates':ds,'gaps':['fixture source gap']}
    result=sector_scan.scan(closes_fn=loader)
    check('sector with mismatched benchmark sessions is excluded','Bank' not in [r['sector'] for r in result['shortlist']])
    check('sector source gaps survive ranking',any('fixture source gap' in g for g in result['gaps']))

def test_valuation_gate_rejects_failed_and_invalid_provider_rows():
    from unittest.mock import patch
    from finance.spine import envelope
    def valuation(name,**kw):
        if name=='ERROR': raise RuntimeError('fixture unavailable')
        if name=='FAILED': return envelope(False,'fixture',{'pe':{'current':20,'percentile':10}},['fixture failed'])
        if name=='INVALID': return envelope(True,'fixture',{'pe':{'current':20,'percentile':float('nan')}},[])
        return envelope(True,'fixture',{'pe':{'current':20,'percentile':40}},['fixture partial'])
    with patch.object(market,'SECTOR_INDICES',['ERROR','FAILED','INVALID','GOOD']), patch.object(market,'valuation_percentiles',side_effect=valuation):
        result=sector_scan.scan({'screening':{'metric':'index_valuation_percentile'}})
    check('only valid successful valuation rows rank',[r['sector'] for r in result['shortlist']]==['GOOD'],result)
    check('valuation source gaps survive',any('fixture partial' in g for g in result['gaps']),result)

if __name__ == "__main__":
    run(globals())
