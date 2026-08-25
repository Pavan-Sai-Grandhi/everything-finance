#!/usr/bin/env python3
"""Offline tests for the market-of-record's pure logic. No network."""
import os
import shutil
import sys
import tempfile

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
    "as_of": "2026-08-14", "generated": "2026-08-16",
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

def fake_compute(mode="standard", years=10):
    calls.append(mode)
    return {"as_of": "2026-08-18", "mode": mode, "market_trend": "uptrend",
            "market_posture": "risk-on", "rationale": "synthetic", "gaps": []}

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

summary()
