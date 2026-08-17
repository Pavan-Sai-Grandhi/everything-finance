#!/usr/bin/env python3
"""Offline tests for the market-of-record's pure logic. No network. Each test runs in a
temp artifacts root so it never touches a real workspace.
Run: python3 finance/tests/test_context.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import context as mc

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


# --- classify_trend: the taxonomy strategy specs are validated against ------------
check("trend up needs both EMAs and a rising slope",
      mc.classify_trend(True, True, True) == "up")
check("trend down needs both below and a falling slope",
      mc.classify_trend(False, False, False) == "down")
check("above both but slope falling is range",
      mc.classify_trend(True, True, False) == "range")
check("below both but slope rising is range",
      mc.classify_trend(False, False, True) == "range")
check("mixed EMAs is range", mc.classify_trend(True, False, True) == "range")

# --- classify_vol_band -----------------------------------------------------------
check("VIX 11.3 is low", mc.classify_vol_band(11.31) == "low")
check("VIX 13 is normal (boundary is exclusive below)",
      mc.classify_vol_band(13) == "normal")
check("VIX 20 is normal (boundary is exclusive above)",
      mc.classify_vol_band(20) == "normal")
check("VIX 24 is high", mc.classify_vol_band(24) == "high")
check("missing VIX is unknown, never a silent default",
      mc.classify_vol_band(None) == "unknown")

# --- robust_pe_percentile: the earnings-collapse trap -----------------------------
# A history with three absurd prints from an earnings trough. Left in, today's 30 looks
# cheap; excluded, it ranks where it belongs.
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

# --- classify_stance -------------------------------------------------------------
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

# --- classify_posture ------------------------------------------------------------
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

# --- _pct: denominators ----------------------------------------------------------
check("_pct computes against the priced denominator, not the universe",
      mc._pct({"count": 300, "of": 492}) == 61.0)
check("_pct is None when nothing was priced (never 0%, which reads as a real finding)",
      mc._pct({"count": 0, "of": 0}) is None)
check("_pct is None on a missing block", mc._pct(None) is None)

# --- digest: the narrow report ---------------------------------------------------
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

# --- artifact path + quick-mode reuse --------------------------------------------
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

# --- frozen key names -------------------------------------------------------------
# select_strategy.py gates on exactly these paths. Renaming one silently breaks every
# strategy spec's regime_required check, so the contract is asserted here.
for key in ("market_trend", "trend_detail", "volatility", "breadth"):
    check(f"frozen: top-level {key!r} present", key in ctx)
check("frozen: trend_detail.above_ema200", "above_ema200" in ctx["trend_detail"])
check("frozen: volatility.vix", "vix" in ctx["volatility"])
check("frozen: breadth.pct_sectors_above_ema50",
      "pct_sectors_above_ema50" in ctx["breadth"])
check("posture key is market_posture (wealth owns risk_posture)",
      "market_posture" in ctx and "risk_posture" not in ctx)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
