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
    check("report writes the shortlist to file", env["data"]["report_path"].startswith(out[:-5]+"-"))
    check("the file holds the shortlist", os.path.exists(env["data"]["report_path"]))


def test_required_gates_cannot_be_bypassed():
    from unittest import mock
    from finance.sources import universe
    with mock.patch.object(universe,'resolve_symbols',return_value=([],['fixture universe unavailable'])):
        res = _scan()
    check('missing named universe cannot widen to the full screen',not res['shortlist'] and any('universe' in g for g in res['gaps']),res)
    res = stock_scan.scan(_SPEC,screen_fn=lambda *a:_envelope(False,'stub',{'candidates':['AAA']},['fixture rejected gate']),closes_fn=_closes_fn)
    check('failed quality gate cannot use residual candidates',not res['shortlist'],res)
    loader = mock.Mock(side_effect=_closes_fn)
    screen = mock.Mock(side_effect=_screen_fn)
    res = stock_scan.scan({**_SPEC,'ranking':{'metric':'typo'}},screen_fn=screen,closes_fn=loader)
    check('invalid ranking refuses before fetching',not screen.called and not loader.called and not res['shortlist'],res)
    res=stock_scan.scan(_SPEC,screen_fn=mock.Mock(side_effect=OSError('fixture outage')),closes_fn=_closes_fn)
    check('gate exception degrades without a shortlist',not res['shortlist'] and bool(res['gaps']),res)
    with mock.patch.object(universe,'resolve_symbols',return_value=(['AAA'],['fixture stale universe'])):
        res=_scan()
    check('usable degraded universe retains its source gap','fixture stale universe' in res['gaps'])


def test_price_failure_does_not_abort_other_candidates():
    def loader(symbol,fresh=False):
        if symbol=='AAA': raise OSError('fixture history unavailable')
        return _closes_fn(symbol,fresh)
    try:
        res=stock_scan.scan(_SPEC,screen_fn=_screen_fn,closes_fn=loader)
        check('one history failure leaves other candidates usable',[r['symbol'] for r in res['shortlist']]==['BBB','CCC'] and any('AAA' in g for g in res['gaps']),res)
    except Exception as exc:
        check('one history failure leaves other candidates usable',False,type(exc).__name__)

def test_dated_sources_preserve_gaps_and_refuse_misalignment():
    from unittest import mock
    from finance.sources import prices
    from datetime import date,timedelta
    days=[(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(300)]
    def history(symbol,**kwargs):
        selected=days[:-1] if symbol=='AAA' else days
        return _envelope(True,'fixture',{'candles':[{'date':d,'close':100+i} for i,d in enumerate(selected)]},['fixture partial source'])
    with mock.patch.object(prices,'history',side_effect=history):
        res=stock_scan.scan(_SPEC,screen_fn=_screen_fn)
    check('price source gaps survive scanning',any('fixture partial source' in gap for gap in res['gaps']),res)
    check('stale stock endpoint cannot mix with later stock endpoints','AAA' not in [r['symbol'] for r in res['shortlist']])
    check('shortlist carries actual price date',all(r['price_as_of']==days[-1] for r in res['shortlist']))


def test_report_rerun_preserves_prior_evidence():
    with tempfile.TemporaryDirectory() as work:
        target=os.path.join(work,'scan.json')
        first=stock_scan.report(_SPEC,top=1,out=target,screen_fn=_screen_fn,closes_fn=_closes_fn)
        path=first['data']['report_path']
        content=open(path,'rb').read()
        second=stock_scan.report(_SPEC,top=2,out=target,screen_fn=_screen_fn,closes_fn=_closes_fn)
        check('changed rerun cannot overwrite an earlier shortlist',second['data']['report_path']!=path and open(path,'rb').read()==content)

def test_relative_windows_align_without_requiring_identical_history_lengths():
    days=[str(i) for i in range(400)]
    short, long = _series(20,300), _series(5,400)
    context=stock_scan._context_row(short,long,days[-300:],days)
    check('matching recent windows permit different total history lengths',context['rs_vs_nifty']['3m']==15,context)
    mismatched=days[-300:].copy()
    mismatched[-20]='different-session'
    context=stock_scan._context_row(short,long,mismatched,days)
    check('context cannot subtract returns over different sessions',context['rs_vs_nifty']['3m'] is None,context)


def test_nonfinite_injected_prices_cannot_rank():
    res=stock_scan.scan(_SPEC,screen_fn=_screen_fn,closes_fn=lambda *a:[float('nan')]*300)
    check('invalid price series cannot produce a shortlist',res['shortlist']==[] and bool(res['gaps']),res)

def test_unapproved_provider_is_rejected_before_fetch():
    from unittest.mock import Mock
    gate = Mock(side_effect=AssertionError('unapproved screen fetched'))
    spec = dict(_SPEC, screening={'fundamental': {'provider': 'screener_in',
                'screen_url': 'https://www.screener.in/screens/999/example/'}})
    result = stock_scan.scan(spec, screen_fn=gate)
    check('a non-Tickertape provider fails before any fetching', not gate.called and not result['shortlist'])
    check('source-policy gap is explicit', any('unapproved' in gap for gap in result['gaps']))


if __name__ == "__main__":
    run(globals())
