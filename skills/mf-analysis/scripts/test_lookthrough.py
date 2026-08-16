#!/usr/bin/env python3
"""Offline tests for the look-through math. No network, no pytest. Run:
  python3 skills/mf-analysis/scripts/test_lookthrough.py

Covers the three corrections that flipped real verdicts — rank-based cap classification,
the coverage gate that withholds rather than annotates, and harmonic (not arithmetic)
multiple aggregation — plus every analytic added on top of them.
"""
import json
import os
import sys
import tempfile

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


# --- weighted harmonic: the correct P/E aggregation --------------------------
pe, w = L.weighted_harmonic([(50, 10), (50, 30)])
check("harmonic 50/50 of 10 & 30 = 15", approx(pe, 15.0) and w == 100)
check("harmonic differs materially from arithmetic (20 vs 15) — the old bug",
      approx(pe, 15.0) and abs(20.0 - pe) / pe > 0.20)
pe, w = L.weighted_harmonic([(40, 20), (60, None)])
check("harmonic ignores a None multiple and excludes its weight from coverage",
      approx(pe, 20.0) and w == 40)
pe, w = L.weighted_harmonic([(50, -5), (50, 0)])
check("harmonic drops non-positive multiples entirely", pe is None and w == 0.0)

# --- weighted mean (ROE / growth) --------------------------------------------
m, w = L.weighted_mean([(50, 20), (50, 10)])
check("weighted mean 50/50 of 20 & 10 = 15", approx(m, 15.0) and w == 100)
m, _ = L.weighted_mean([(50, 30), (50, -10)])
check("weighted mean carries a negative value", approx(m, 10.0))
m, w = L.weighted_mean([])
check("weighted mean of nothing → None, zero coverage", m is None and w == 0.0)

# --- earnings yield keeps loss-makers visible --------------------------------
EY = [{"weight": 50, "pe": 20}, {"weight": 50, "pe": -10}]
ey, ey_w = L.weighted_mean(L.earnings_yields(EY))
check("earnings yield averages +5% and -10% to -2.5%", approx(ey, -2.5) and ey_w == 100)
hpe, hw = L.weighted_harmonic((h["weight"], h["pe"]) for h in EY)
check("harmonic P/E hides the loss-maker (20 on half the book) — the yield does not",
      approx(hpe, 20.0) and hw == 50)

# --- CAGR --------------------------------------------------------------------
check("cagr one period 100→121 = 21%", approx(L.cagr([100, 121]), 21.0))
check("cagr two periods 100→110→121 = 10%", approx(L.cagr([100, 110, 121]), 10.0))
check("cagr <2 points → None", L.cagr([100]) is None)
check("cagr non-positive endpoint → None", L.cagr([-5, 121]) is None)

# --- cap classification: SEBI RANK, not ₹Cr ----------------------------------
check("rank 1 → large", L.cap_bucket(cap_rank=1) == ("large", "rank"))
check("rank 100 → large (boundary inclusive)", L.cap_bucket(cap_rank=100) == ("large", "rank"))
check("rank 101 → mid", L.cap_bucket(cap_rank=101) == ("mid", "rank"))
check("rank 250 → mid (boundary inclusive)", L.cap_bucket(cap_rank=250) == ("mid", "rank"))
check("rank 251 → small", L.cap_bucket(cap_rank=251) == ("small", "rank"))
check("rank wins over a contradicting label",
      L.cap_bucket(cap_rank=400, cap_label="Largecap") == ("small", "rank"))
check("label fallback when rank missing — and it is LABELLED as a fallback",
      L.cap_bucket(cap_rank=None, cap_label="Smallcap") == ("small", "label"))
check("label fallback tolerates spacing/case", L.cap_bucket(cap_label="Mid Cap") == ("mid", "label"))
check("micro-cap label folds into small", L.cap_bucket(cap_label="Microcap") == ("small", "label"))
check("no rank and no label → unclassified, never guessed",
      L.cap_bucket(None, None) == (None, None))
check("a ₹Cr market cap alone classifies nothing (the deleted bug)",
      L.cap_bucket(cap_rank=None, cap_label=None) == (None, None))

# The exact regression: a small-cap fund's biggest holdings are its largest names. Under
# absolute ₹Cr bands these read as large/mid-cap "drift"; under SEBI rank they are small.
SMALLCAP_BOOK = [
    {"weight": 5.0, "cap_rank": 260, "cap_label": "Smallcap", "market_cap_cr": 48000},
    {"weight": 4.0, "cap_rank": 310, "cap_label": "Smallcap", "market_cap_cr": 31000},
    {"weight": 3.0, "cap_rank": 180, "cap_label": "Midcap", "market_cap_cr": 62000},
]
ct = L.cap_tilt(SMALLCAP_BOOK)
check("rank-based tilt: 75% small, 25% mid, 0% large",
      approx(ct["small"], 0.75) and approx(ct["mid"], 0.25) and ct["large"] == 0.0)
check("cap-tilt records that 100% of it came from ranks", ct["by_rank"] == 1.0 and ct["by_label"] == 0.0)
ct2 = L.cap_tilt([{"weight": 60, "cap_label": "Smallcap"}, {"weight": 40, "cap_rank": 50}])
check("mixed rank/label tilt reports the fallback share", approx(ct2["by_label"], 0.6))
ct3 = L.cap_tilt([{"weight": 100}])
check("unclassifiable book → all None, zero coverage (not '0% small-cap')",
      ct3["small"] is None and ct3["coverage"] == 0.0)

# --- the coverage GATE -------------------------------------------------------
check("≥85% coverage is decision-grade", L.coverage_grade(0.85) == "decision-grade")
check("60-85% coverage is indicative", L.coverage_grade(0.65) == "indicative")
check("<60% coverage is unusable", L.coverage_grade(0.599) == "unusable")
g = L.gated(45.07, 65.0, 100.0)
check("indicative ratio is published but flagged",
      g["value"] == 45.07 and g["confidence"] == "indicative" and g["withheld"] is False)
g = L.gated(45.07, 20.0, 100.0)
check("unusable ratio is WITHHELD, not annotated — value is null",
      g["value"] is None and g["withheld"] is True and g["confidence"] == "unusable")
check("withheld ratio still reports its real coverage", approx(g["coverage"], 0.20))
g = L.gated(12.0, 0.0, 100.0)
check("no source at all grades 'unavailable', distinct from 'unusable'",
      g["confidence"] == "unavailable" and g["value"] is None)
g = L.gated(12.0, 50.0, 0.0)
check("zero total weight cannot divide-by-zero", g["value"] is None)

# --- P/B ÷ ROE ---------------------------------------------------------------
r = L.pb_over_roe(2.28, 12.89, 100.0, 100.0, 100.0)
check("pb_over_roe 2.28/12.89 = 0.1769 at 4dp", approx(r["value"], 0.1769, 0.0001))
r = L.pb_over_roe(3.06, 11.14, 100.0, 100.0, 100.0)
check("pb_over_roe ranks a demanding book higher", approx(r["value"], 0.2747, 0.0001))
r = L.pb_over_roe(3.0, -4.0, 100.0, 100.0, 100.0)
check("pb_over_roe undefined at non-positive ROE, and says so",
      r["value"] is None and r["withheld"] and "non-positive" in (r.get("note") or ""))
r = L.pb_over_roe(None, 12.0, 100.0, 100.0, 100.0)
check("pb_over_roe needs both inputs", r["value"] is None)
r = L.pb_over_roe(2.28, 12.89, 30.0, 100.0, 100.0)
check("pb_over_roe inherits the WORSE of the two coverages and is gated on it",
      r["value"] is None and r["confidence"] == "unusable")

# --- concentration -----------------------------------------------------------
c = L.concentration([{"weight": 40}, {"weight": 35}, {"weight": 15}, {"weight": 10}])
check("top5/top10 = whole book when ≤10 holdings", c["top5"] == 1.0 and c["top10"] == 1.0)
check("herfindahl of 40/35/15/10", approx(c["hhi"], 0.315) and c["n"] == 4)
c = L.concentration([{"weight": 1} for _ in range(100)])
check("100 equal positions → top10 = 10%, tiny HHI",
      approx(c["top10"], 0.10) and approx(c["hhi"], 0.01, 0.001))
check("empty book → None, never a fake zero",
      L.concentration([])["hhi"] is None)

# --- sector mix --------------------------------------------------------------
SECT = [
    {"weight": 30, "sector": "Industrial Machinery"},
    {"weight": 20, "sector": "Industrial Machinery"},
    {"weight": 25, "sector": "Private Banks"},
    {"weight": 15, "sector": "Pharma"},
    {"weight": 10},  # unclassified — excluded from the denominator, not assumed
]
s = L.sector_mix(SECT)
check("sector weights aggregate duplicates", approx(s["top_sectors"][0]["weight"], 50 / 90))
check("sector coverage excludes the unclassified tail", approx(s["coverage"], 90.0))
check("sector count", s["n_sectors"] == 3)
check("sector herfindahl", approx(s["hhi"], (50 / 90) ** 2 + (25 / 90) ** 2 + (15 / 90) ** 2, 0.001))
check("no sector data → zero coverage, empty list",
      L.sector_mix([{"weight": 10}])["top_sectors"] == [])

# --- earnings-distress dispersion --------------------------------------------
DIST = [
    {"weight": 20, "roe": 0.6, "pe": 122.1, "name": "Sudarshan", "sector": "Chemicals"},
    {"weight": 15, "roe": 5.1, "pe": 106.9, "name": "Carborundum", "sector": "Machinery"},
    {"weight": 25, "roe": 22.0, "pe": 18.0, "name": "Quality Co", "sector": "IT"},
    {"weight": 30, "roe": 12.0, "pe": 20.0, "name": "Middling", "sector": "Banks"},
    {"weight": 10},  # no ROE — excluded from the denominator
]
d = L.earnings_distress(DIST)
check("share of book at ROE<8% (35 of the 90 ROE-covered)", approx(d["pct_weight_roe_lt_8"], 38.89))
check("share of book at ROE>18%", approx(d["pct_weight_roe_gt_18"], 27.78))
check("distress coverage is the ROE-covered weight only", approx(d["coverage"], 90.0))
check("distressed names listed heaviest-first, with their multiples",
      d["distressed"][0]["name"] == "Sudarshan" and d["distressed"][0]["pe"] == 122.1)
check("a 12% ROE is neither distressed nor quality — no double counting",
      len(d["distressed"]) == 2)
d0 = L.earnings_distress([{"weight": 100}])
check("no ROE anywhere → None, not 0%", d0["pct_weight_roe_lt_8"] is None)

# --- full portfolio metrics, decision-grade ----------------------------------
BOOK = [
    {"weight": 40, "pe": 20, "pb": 3, "roe": 18, "growth": 15,
     "cap_rank": 40, "sector": "IT", "priced": True},
    {"weight": 35, "pe": 30, "pb": 5, "roe": 22, "growth": 25,
     "cap_rank": 150, "sector": "Banks", "priced": True},
    {"weight": 15, "pe": 10, "pb": 1.5, "roe": 12, "growth": 8,
     "cap_rank": 400, "sector": "Metals", "priced": True},
    {"weight": 10, "priced": False},  # unlisted — keeps its weight, lowers coverage
]
pm = L.portfolio_metrics(BOOK, equity_weight=100)
check("portfolio P/E harmonic over the priced 90%", approx(pm["portfolio_pe"]["value"], 19.29))
check("portfolio P/E coverage = 0.90 (the unlisted 10% counts against it)",
      pm["portfolio_pe"]["coverage"] == 0.9)
check("portfolio P/E is decision-grade at 90%", pm["portfolio_pe"]["confidence"] == "decision-grade")
check("portfolio P/B harmonic", approx(pm["portfolio_pb"]["value"], 2.97))
check("portfolio ROE weighted mean", approx(pm["portfolio_roe"]["value"], 18.56))
check("earnings growth weighted mean", approx(pm["earnings_growth"]["value"], 17.72))
check("pb_over_roe computed from the portfolio's own P/B and ROE",
      approx(pm["pb_over_roe"]["value"], 2.97 / 18.56, 0.001))
check("cap tilt from ranks: 44.4% large / 38.9% mid / 16.7% small",
      approx(pm["cap_tilt"]["large"], 0.4444) and approx(pm["cap_tilt"]["mid"], 0.3889)
      and approx(pm["cap_tilt"]["small"], 0.1667))
check("unpriced weight surfaced explicitly", pm["unpriced_weight_pct"] == 10.0)
check("overall confidence is decision-grade", pm["confidence"] == "decision-grade")

# --- the regression the gate exists for --------------------------------------
# A 20-row slice of a real book: the weights sum to a fifth of the fund, yet every ratio
# looks perfectly computable. Before the gate this printed "P/E 45.07" as fact.
TRUNCATED = [{"weight": 2.0, "pe": 45, "pb": 6, "roe": 14, "cap_rank": 300, "priced": True}
             for _ in range(10)]
pm_t = L.portfolio_metrics(TRUNCATED, equity_weight=97.0)
check("truncated feed: P/E withheld, not printed",
      pm_t["portfolio_pe"]["value"] is None and pm_t["portfolio_pe"]["withheld"])
check("truncated feed: overall confidence unusable", pm_t["confidence"] == "unusable")
check("truncated feed: the missing 77% shows up as unpriced weight",
      approx(pm_t["unpriced_weight_pct"], 77.0))
gaps_t = L.metric_gaps(pm_t)
check("truncated feed names the gate in its gaps",
      any("WITHHELD" in g for g in gaps_t) and any("unpriced" in g for g in gaps_t))

# --- indicative band ---------------------------------------------------------
INDICATIVE = [{"weight": 65.0, "pe": 20, "pb": 3, "roe": 15, "cap_rank": 300, "priced": True}]
pm_i = L.portfolio_metrics(INDICATIVE, equity_weight=100.0)
check("65% coverage publishes an indicative ratio",
      pm_i["portfolio_pe"]["value"] == 20.0 and pm_i["portfolio_pe"]["confidence"] == "indicative")
check("indicative ratio carries a 'do not cite' gap",
      any("indicative only" in g for g in L.metric_gaps(pm_i)))

# --- gaps for the label fallback ---------------------------------------------
LABELLED = [{"weight": 100, "cap_label": "Smallcap", "pe": 20, "pb": 3, "roe": 15,
             "priced": True}]
check("label-fallback share is reported as a gap",
      any("text label" in g for g in L.metric_gaps(L.portfolio_metrics(LABELLED, 100))))

# --- offline holdings-file hatch ---------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    p = os.path.join(tmp, "h.json")
    with open(p, "w") as f:
        json.dump({"holdings": [
            {"symbol": "ABC", "pct": 60, "pe": 15, "pb": 2, "roe": 20, "cap_rank": 300},
            {"name": "Unlisted Co", "weight": 40},
        ]}, f)
    with open(p) as f:
        rows = L.load_holdings_file(json.load(f))
    check("file hatch normalises pct→weight and symbol→ticker",
          rows[0]["weight"] == 60 and rows[0]["ticker"] == "ABC")
    check("file hatch marks a row with ratios as priced, one without as unpriced",
          rows[0]["priced"] is True and rows[1]["priced"] is False)
    rep = L.build_report(rows, 100.0, ["file gap"], {"source": "file:h.json"})
    check("build_report gates the file path too (60% = indicative)",
          rep["metrics"]["portfolio_pe"]["confidence"] == "indicative")
    check("build_report keeps the caller's gaps and appends its own",
          "file gap" in rep["gaps"] and len(rep["gaps"]) > 1)
    check("build_report reports publishability as a boolean the skill can branch on",
          rep["ratios_publishable"] is True)
    rep2 = L.build_report([{"weight": 20, "pe": 20, "pb": 3, "roe": 15, "priced": True}],
                          100.0, [], {})
    check("build_report says NOT publishable below the floor",
          rep2["ratios_publishable"] is False and rep2["confidence"] == "unusable")

# --- a bare list is accepted too ---------------------------------------------
check("file hatch accepts a bare list",
      len(L.load_holdings_file([{"weight": 1}, {"weight": 2}])) == 2)
check("file hatch skips non-dict rows", len(L.load_holdings_file([1, "x", {"weight": 1}])) == 1)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
