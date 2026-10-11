#!/usr/bin/env python3
"""Offline tests for the market-of-record's pure logic. No network."""
import os
import shutil
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import context as mc
from finance.tests.harness import check, summary


check("trend up needs both EMAs and a rising slope",
      mc.classify_trend(True, True, True) == "up")
check("trend down needs both below and a falling slope",
      mc.classify_trend(False, False, False) == "down")
check("above both but slope falling is range",
      mc.classify_trend(True, True, False) == "range")
check("below both but slope rising is range",
      mc.classify_trend(False, False, True) == "range")
check("mixed EMAs is range", mc.classify_trend(True, False, True) == "range")

check("VIX 11.3 is low", mc.classify_vol_band(11.31) == "low")
check("VIX 13 is normal (boundary is exclusive below)",
      mc.classify_vol_band(13) == "normal")
check("VIX 20 is normal (boundary is exclusive above)",
      mc.classify_vol_band(20) == "normal")
check("VIX 24 is high", mc.classify_vol_band(24) == "high")
check("missing VIX is unknown, never a silent default",
      mc.classify_vol_band(None) == "unknown")

hist = [20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 4000, 9000, 44692]
pct_raw = mc.market.percentile(hist, 30)
pct_robust, used, dropped = mc.robust_pe_percentile(hist, 30)
check("earnings-collapse samples are excluded", dropped == 3, f"dropped={dropped}")
check("the surviving sample count is reported", used == 10, f"used={used}")
check("excluding distortions raises the percentile (today looks less cheap)",
      pct_robust > pct_raw, f"raw={pct_raw} robust={pct_robust}")
check("distorted samples are counted, not silently filtered",
      used + dropped == len(hist))
check("robust percentile is None when there is no current value",
      mc.robust_pe_percentile(hist, None)[0] is None)
check("robust percentile is None on an empty history",
      mc.robust_pe_percentile([], 30)[0] is None)
check("a clean history drops nothing", mc.robust_pe_percentile([20, 22, 24], 22)[2] == 0)

check("low percentiles across the board read cheap",
      mc.classify_stance(5, 5, 95)[0] == "cheap")
check("high P/E and P/B with a poor yield reads expensive",
      mc.classify_stance(90, 92, 5)[0] == "expensive")
check("a low dividend yield pushes toward expensive (yield is inverted)",
      mc.classify_stance(50, 50, 5)[1] > mc.classify_stance(50, 50, 95)[1])
check("stance works from P/B alone when P/E is unusable",
      mc.classify_stance(None, 80, None)[0] in ("rich", "expensive"))
check("no inputs at all is unknown, never a fabricated stance",
      mc.classify_stance(None, None, None) == ("unknown", None))
_stance, blended = mc.classify_stance(60, 80, 10)
check("blended percentile averages only the available parts",
      blended == round((60 + 80 + 90) / 3, 1), blended)

check("uptrend + calm + participation is risk_on",
      mc.classify_posture("up", "normal", 70)[0] == "risk_on")
check("high volatility forces risk_off even in an uptrend",
      mc.classify_posture("up", "high", 70)[0] == "risk_off")
check("narrow breadth forces risk_off even in an uptrend",
      mc.classify_posture("up", "normal", 25)[0] == "risk_off")
check("downtrend is risk_off", mc.classify_posture("down", "normal", 55)[0] == "risk_off")
check("range with mixed breadth is neutral",
      mc.classify_posture("range", "normal", 55)[0] == "neutral")
check("posture always carries a rationale",
      all(mc.classify_posture(t, "normal", 55)[1]
          for t in ("up", "down", "range", "unknown")))

check("_pct computes against the priced denominator, not the universe",
      mc._pct({"count": 300, "of": 492}) == 61.0)
check("_pct is None when nothing was priced (never 0%, which reads as a real finding)",
      mc._pct({"count": 0, "of": 0}) is None)
check("_pct is None on a missing block", mc._pct(None) is None)

ctx = {
    "as_of": "2026-08-14", "generated": str(date.today()), "history_years": 10,
    "context_version": mc._CONTEXT_VERSION, "mode": "standard",
    "market_trend": "range", "market_posture": "neutral", "rationale": "why",
    "trend_detail": {"close": 24366.0, "above_ema50": True, "above_ema200": False,
                     "pct_from_52w_high": -7.5},
    "volatility": {"vix": 11.31, "band": "low", "percentile_1y": 23.6},
    "breadth": {"universe": 500, "pct_above_sma50": 61.0, "pct_above_sma200": 64.9,
                "pct_sectors_above_ema50": 60.0, "pct_near_52w_high": 18.4,
                "pct_near_52w_low": 4.8},
    "valuation": {"NIFTY 50": {"pe": 20.56, "pe_pctile": 7.8, "pb": 2.97, "pb_pctile": 3.7,
                               "dy": 1.17, "dy_pctile": 20.1, "stance": "below average",
                               "blended_pctile": 30.5, "history_years": 10}},
    "relative": {"smallcap_vs_largecap_pb_ratio": 1.21, "percentile_spread": 45.3,
                 "read": "smallcaps expensive"},
    "flows": {"FII": {"net_cr": 508.12}, "DII": {"net_cr": 356.4}},
    "flows_session": "14-Aug-2026",
    "macro": {"usdinr": {"last": 95.43, "chg_1m_pct": -1.26, "percentile_5y": 97.2}},
    "sectors": {"leaders": [{"index": "NIFTY METAL", "chg_1y_pct": 40.42}],
                "laggards": [{"index": "NIFTY FMCG", "chg_1y_pct": -11.05}]},
    "gaps": [],
}
text = mc.digest(ctx)
check("digest reports as_of, not the generation date",
      "2026-08-14" in text and "as_of: 2026-08-14" in text)
check("digest carries the valuation percentiles", "7.8p" in text and "3.7p" in text)
check("digest carries the relative read", "1.21" in text and "45.3" in text)
check("digest carries flows", "508.12" in text)
check("digest always states gaps", "gaps:" in text)
check("digest stays narrow (a context budget, not a data dump)",
      len(text.splitlines()) < 40, f"{len(text.splitlines())} lines")

ctx_gappy = dict(ctx, gaps=["India VIX unavailable"], valuation={
    "NIFTY SMALLCAP 250": dict(ctx["valuation"]["NIFTY 50"],
                               pe_pctile_note="8 of 114 samples excluded")})
check("a gap is surfaced in the digest, never swallowed",
      "India VIX unavailable" in mc.digest(ctx_gappy))
check("the excluded-sample note reaches the digest",
      "8 of 114 samples excluded" in mc.digest(ctx_gappy))

with tempfile.TemporaryDirectory() as tmp:
    os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = tmp
    check("no artifact yet means quick mode must compute", mc.load_today() is None)
    p = mc.artifact_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    import json
    with open(p, "w") as fh:
        json.dump(ctx, fh)
    loaded = mc.load_today()
    check("quick mode reuses today's artifact (N callers, one computation)",
          loaded is not None and loaded["as_of"] == "2026-08-14")
    check("artifact lands under the market-analysis report dir",
          "market-analysis" in p and p.endswith(".json"), p)
    with open(p, "w") as fh:
        fh.write("{not json")
    check("a corrupt artifact forces a recompute instead of raising",
          mc.load_today() is None)
    os.environ.pop("EVERYTHING_FINANCE_ARTIFACTS", None)

_orig_compute = mc.compute
_orig_artifact_path = mc.artifact_path
_report_tmp = tempfile.mkdtemp()
mc.artifact_path = lambda day=None: os.path.join(_report_tmp, "market.json")
mc.compute = lambda mode="standard", years=10: dict(ctx, mode=mode)
try:
    env = mc.report(mode="quick", years=5, fresh=True)
finally:
    mc.compute = _orig_compute
check("report returns the data-spine envelope",
      set(env) == {"ok", "source", "fetched_at", "data", "gaps"}, sorted(env))
check("report dates itself by the context's as_of, not by now",
      env["fetched_at"] == "2026-08-14", env["fetched_at"])
check("report carries the digest", "as_of: 2026-08-14" in env["data"]["digest"])
check("report carries the structured fields a caller branches on without parsing prose",
      (env["data"]["market_trend"], env["data"]["market_posture"],
       env["data"]["rationale"]) == ("range", "neutral", "why"), env["data"])
check("report stays narrow — digest plus the branch fields, no raw blocks",
      set(env["data"]) == {"digest", "as_of", "market_trend", "market_posture",
                           "rationale"}, sorted(env["data"]))

mc.compute = lambda mode="standard", years=10: dict(ctx, gaps=["India VIX unavailable"])
try:
    env_gappy = mc.report(fresh=True)
finally:
    mc.compute = _orig_compute
    mc.artifact_path = _orig_artifact_path
    shutil.rmtree(_report_tmp, ignore_errors=True)
check("report surfaces the context's gaps as the envelope's gaps",
      env_gappy["gaps"] == ["India VIX unavailable"], env_gappy["gaps"])

for key in ("market_trend", "trend_detail", "volatility", "breadth"):
    check(f"frozen: top-level {key!r} present", key in ctx)
check("frozen: trend_detail.above_ema200", "above_ema200" in ctx["trend_detail"])
check("frozen: volatility.vix", "vix" in ctx["volatility"])
check("frozen: breadth.pct_sectors_above_ema50",
      "pct_sectors_above_ema50" in ctx["breadth"])
check("posture key is market_posture (wealth owns risk_posture)",
      "market_posture" in ctx and "risk_posture" not in ctx)


import json  # noqa: E402

tmp = tempfile.mkdtemp()
calls = []

fixture_context = ctx.copy()

def fake_compute(mode="standard", years=10):
    calls.append(mode)
    return dict(fixture_context, as_of="2026-08-18", mode=mode, history_years=years, gaps=[])

orig_compute = mc.compute
orig_path = mc.artifact_path
mc.compute = fake_compute
mc.artifact_path = lambda day=None: os.path.join(tmp, "market.json")
try:
    ctx = mc.resolve(mode="quick")
    check("quick computes when no artifact exists", len(calls) == 1)
    check("the artifact is written", os.path.exists(mc.artifact_path()))
    with open(mc.artifact_path()) as fh:
        check("what is written is what is returned", json.load(fh) == ctx)

    ctx2 = mc.resolve(mode="quick")
    check("quick reuses the day's artifact", len(calls) == 1, f"computed {len(calls)}x")
    check("the reused context is the same", ctx2 == ctx)

    mc.resolve(mode="quick", fresh=True)
    check("fresh bypasses the artifact", len(calls) == 2)

    mc.resolve(mode="deep")
    check("deep always recomputes", len(calls) == 3)
    check("deep mode reaches compute", calls[-1] == "deep")

    before = len(calls)
    env = mc.report(mode="quick")
    check("report reuses too", len(calls) == before, "report recomputed")
    for k in ("ok", "source", "fetched_at", "data", "gaps"):
        check(f"report envelope has {k}", k in env)
    check("fetched_at is the context's as-of, not now",
          env["fetched_at"] == "2026-08-18")
    check("report exposes fresh", mc.report(mode="quick", fresh=True) is not None)
    check("report's fresh recomputed", len(calls) == before + 1)
finally:
    mc.compute = orig_compute
    mc.artifact_path = orig_path
    shutil.rmtree(tmp, ignore_errors=True)

# Missing evidence must not turn into a favourable trading gate.
from unittest.mock import patch
import pandas as pd

check("missing trend comparisons stay unknown", mc.classify_trend(None, None, None) == "unknown")
check("invalid VIX stays unknown", all(mc.classify_vol_band(v) == "unknown"
      for v in (float('nan'), float('inf'), -1, True)))
check("missing VIX cannot authorize risk-on", mc.classify_posture("up", "unknown", 70)[0] == "neutral")
check("missing breadth cannot authorize risk-on", mc.classify_posture("up", "normal", None)[0] == "neutral")
check("invalid breadth cannot authorize risk-on", mc.classify_posture("up", "normal", 101)[0] == "neutral")
check("impossible participation counts are unavailable", mc._pct({'count': 11, 'of': 10}) is None)
with patch.object(mc.prices, 'history_df', return_value=(None, ['upstream unavailable'])):
    gaps = []
    vol = mc._volatility(gaps)
    check("missing volatility remains unknown in fetched context", vol['band'] == 'unknown')
    check("volatility preserves source gaps", 'upstream unavailable' in gaps)
frame = pd.DataFrame({'Close': [100.] * 199 + [float('nan')]},
                     index=pd.date_range('2025-01-01', periods=200))
with patch.object(mc.prices, 'history_df', return_value=(frame, [])):
    check("EMA warmup counts usable observations", mc._trend([])[0] == 'unknown')
sector_frame = pd.DataFrame({'Close': range(1, 61)}, index=pd.date_range('2025-01-01', periods=60))
with patch.object(mc.market, 'SECTOR_YF', {'A': 'A', 'B': 'B'}), \
     patch.object(mc.market, 'breadth', return_value={'data': {}, 'gaps': []}), \
     patch.object(mc.prices, 'history_df', side_effect=[(sector_frame, []), (None, ['B unavailable'])]):
    gaps = []
    breadth = mc._breadth(gaps)
    check("partial sector coverage cannot pass a full-universe gate", breadth['pct_sectors_above_ema50'] is None)
    check("sector source gaps survive", 'B unavailable' in gaps)
check("relative history unavailable is not similar valuation", 'unavailable' in mc._relative({
    'NIFTY 50': {'pb': 3}, 'NIFTY SMALLCAP 250': {'pb': 4}})['read'])

# Cache correctness, interrupted publication, and simultaneous consumers.
from concurrent.futures import ThreadPoolExecutor
with tempfile.TemporaryDirectory() as tmp:
    target = os.path.join(tmp, 'market.json')
    with patch.object(mc, 'artifact_path', return_value=target):
        valid = dict(fixture_context, gaps=[])
        for bad in ([], dict(valid, history_years=5), dict(valid, generated='2000-01-01'),
                    dict(valid, context_version=0), dict(valid, volatility=[]),
                    dict(valid, as_of='2999-01-01'), dict(valid, breadth={'value': float('nan')})):
            with open(target, 'w') as stream:
                json.dump(bad, stream)
            check('incompatible or invalid context is not reused', mc.load_today() is None)
        mc.persist(valid)
        original = open(target).read()
        with patch.object(mc.os, 'replace', side_effect=OSError('simulated interrupted replacement')):
            try:
                mc.persist(dict(valid, rationale='replacement'))
            except OSError:
                pass
        check('failed replacement preserves complete prior snapshot', open(target).read() == original)
        check('failed replacement cleans its temporary file', os.listdir(tmp) == ['market.json'])
        try:
            mc.persist(dict(valid, volatility={'vix': float('nan')}))
        except ValueError:
            pass
        check('nonfinite publication cannot overwrite prior snapshot', open(target).read() == original)
        os.unlink(target)
        def compute_fixture(mode='standard', years=10):
            return dict(valid, mode=mode, history_years=years, gaps=[])
        with patch.object(mc, 'compute', side_effect=compute_fixture) as compute_mock:
            with ThreadPoolExecutor(max_workers=4) as pool:
                contexts = list(pool.map(lambda _: mc.resolve(mode='quick'), range(4)))
            check('concurrent quick consumers compute once', compute_mock.call_count == 1)
            check('concurrent consumers share the same snapshot', all(c == contexts[0] for c in contexts))
            mc.resolve(mode='quick', years=5)
            check('changed history window triggers recomputation', compute_mock.call_count == 2)
            custom = os.path.join(tmp, 'copy.json')
            mc.resolve(mode='quick', years=5, out=custom)
            check('cached result still honors requested output', json.load(open(custom)) == json.load(open(target)))
        with patch.object(mc, 'compute', side_effect=compute_fixture), \
             patch.object(mc, 'persist', side_effect=OSError('read-only directory')):
            degraded = mc.resolve(fresh=True)
            check('persistence failure returns computed evidence with a gap',
                  degraded['market_trend'] == valid['market_trend'] and
                  any('persistence unavailable' in g for g in degraded['gaps']))

check("invalid percentiles do not create valuation stances",
      mc.classify_stance(float('nan'), 101, True) == ('unknown', None))
check("nonpositive and nonfinite PE observations cannot skew ranking",
      mc.robust_pe_percentile([20, 22, 24, -10, float('nan'), True], 22) ==
      mc.robust_pe_percentile([20, 22, 24], 22))
with tempfile.TemporaryDirectory() as tmp:
    with patch.object(mc.paths, 'report_dir', return_value=tmp):
        for name, value in [('2020-01-01.json', dict(fixture_context, as_of='2020-01-01')),
                            ('2020-01-02.json', []),
                            (str(date.today()) + '.json', fixture_context)]:
            with open(os.path.join(tmp, name), 'w') as stream:
                json.dump(value, stream)
        for suffix in ('md', 'html', 'lock'):
            open(os.path.join(tmp, '2999-01-01.' + suffix), 'w').close()
        check("history filters current, malformed and non-JSON files before limiting",
              mc._transitions(limit=1) == [{'date': '2020-01-01', 'trend': 'range', 'posture': 'neutral'}])

with patch.object(mc.prices, 'history_df', return_value=(sector_frame, [])):
    gaps = []
    vol = mc._volatility(gaps, expected_as_of='2026-09-01')
    check("stale VIX cannot satisfy current-session risk gate", vol['vix'] is None and vol['band'] == 'unknown' and bool(gaps))
with patch.object(mc.market, 'SECTOR_YF', {'A': 'A'}), \
     patch.object(mc.market, 'breadth', return_value={'data': {}, 'gaps': []}), \
     patch.object(mc.prices, 'history_df', return_value=(sector_frame, [])):
    gaps = []
    br = mc._breadth(gaps, expected_as_of='2026-09-01')
    check("stale sector history cannot satisfy current-session breadth gate", br['pct_sectors_above_ema50'] is None and br['sectors_available'] == 0 and bool(gaps))

summary()
