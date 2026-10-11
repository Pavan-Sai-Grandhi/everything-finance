#!/usr/bin/env python3
"""Offline tests for the look-through math. No network."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance import caps
from finance.compute import lookthrough as L
from finance.tests.harness import approx, check, summary


pe, w = L.weighted_harmonic([(50, 10), (50, 30)])
check("harmonic 50/50 of 10 & 30 = 15", approx(pe, 15.0) and w == 100)
check("harmonic differs materially from arithmetic (20 vs 15)",
      approx(pe, 15.0) and abs(20.0 - pe) / pe > 0.20)
pe, w = L.weighted_harmonic([(40, 20), (60, None)])
check("harmonic ignores a None multiple and excludes its weight from coverage",
      approx(pe, 20.0) and w == 40)
pe, w = L.weighted_harmonic([(50, -5), (50, 0)])
check("harmonic drops non-positive multiples entirely", pe is None and w == 0.0)

m, w = L.weighted_mean([(50, 20), (50, 10)])
check("weighted mean 50/50 of 20 & 10 = 15", approx(m, 15.0) and w == 100)
m, _ = L.weighted_mean([(50, 30), (50, -10)])
check("weighted mean carries a negative value", approx(m, 10.0))
m, w = L.weighted_mean([])
check("weighted mean of nothing → None, zero coverage", m is None and w == 0.0)

EY = [{"weight": 50, "pe": 20}, {"weight": 50, "pe": -10}]
ey, ey_w = L.weighted_mean(L.earnings_yields(EY))
check("earnings yield averages +5% and -10% to -2.5%", approx(ey, -2.5) and ey_w == 100)
hpe, hw = L.weighted_harmonic((h["weight"], h["pe"]) for h in EY)
check("harmonic P/E hides the loss-maker (20 on half the book) — the yield does not",
      approx(hpe, 20.0) and hw == 50)

check("rank 1 → large", caps.cap_bucket(cap_rank=1) == ("large", "rank"))
check("rank 100 → large (boundary inclusive)", caps.cap_bucket(cap_rank=100) == ("large", "rank"))
check("rank 101 → mid", caps.cap_bucket(cap_rank=101) == ("mid", "rank"))
check("rank 250 → mid (boundary inclusive)", caps.cap_bucket(cap_rank=250) == ("mid", "rank"))
check("rank 251 → small", caps.cap_bucket(cap_rank=251) == ("small", "rank"))
check("rank wins over a contradicting label",
      caps.cap_bucket(cap_rank=400, cap_label="Largecap") == ("small", "rank"))
check("label fallback when rank missing — and it is LABELLED as a fallback",
      caps.cap_bucket(cap_rank=None, cap_label="Smallcap") == ("small", "label"))
check("label fallback tolerates spacing/case", caps.cap_bucket(cap_label="Mid Cap") == ("mid", "label"))
check("micro-cap label folds into small", caps.cap_bucket(cap_label="Microcap") == ("small", "label"))
check("no rank and no label → unclassified, never guessed",
      caps.cap_bucket(None, None) == (None, None))
check("a ₹Cr market cap alone classifies nothing",
      caps.cap_bucket(cap_rank=None, cap_label=None) == (None, None))

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

r = L.pb_over_roe([{"weight":100,"pb":2.28,"roe":12.89}],100)
check("pb_over_roe 2.28/12.89 = 0.1769 at 4dp", approx(r["value"], 0.1769, 0.0001))
r = L.pb_over_roe([{"weight":100,"pb":3.06,"roe":11.14}],100)
check("pb_over_roe ranks a demanding book higher", approx(r["value"], 0.2747, 0.0001))
r = L.pb_over_roe([{"weight":100,"pb":3,"roe":-4}],100)
check("pb_over_roe undefined at non-positive ROE, and says so",
      r["value"] is None and r["withheld"] and "non-positive" in (r.get("note") or ""))
r = L.pb_over_roe([{"weight":100,"pb":None,"roe":12}],100)
check("pb_over_roe needs both inputs", r["value"] is None)
r = L.pb_over_roe([{"weight":30,"pb":2.28,"roe":12.89},{"weight":70,"roe":12.89}],100)
check("pb_over_roe uses the jointly covered holdings and gates on their weight",
      r["value"] is None and r["confidence"] == "unusable")

c = L.concentration([{"weight": 40}, {"weight": 35}, {"weight": 15}, {"weight": 10}])
check("top5/top10 = whole book when ≤10 holdings", c["top5"] == 1.0 and c["top10"] == 1.0)
check("herfindahl of 40/35/15/10", approx(c["hhi"], 0.315) and c["n"] == 4)
c = L.concentration([{"weight": 1} for _ in range(100)])
check("100 equal positions → top10 = 10%, tiny HHI",
      approx(c["top10"], 0.10) and approx(c["hhi"], 0.01, 0.001))
check("empty book → None, never a fake zero",
      L.concentration([])["hhi"] is None)

SECT = [
    {"weight": 30, "sector": "Industrial Machinery"},
    {"weight": 20, "sector": "Industrial Machinery"},
    {"weight": 25, "sector": "Private Banks"},
    {"weight": 15, "sector": "Pharma"},
    {"weight": 10},
]
s = L.sector_mix(SECT)
check("sector weights aggregate duplicates", approx(s["top_sectors"][0]["weight"], 50 / 90))
check("sector coverage excludes the unclassified tail", approx(s["coverage"], 90.0))
check("sector count", s["n_sectors"] == 3)
check("sector herfindahl", approx(s["hhi"], (50 / 90) ** 2 + (25 / 90) ** 2 + (15 / 90) ** 2, 0.001))
check("no sector data → zero coverage, empty list",
      L.sector_mix([{"weight": 10}])["top_sectors"] == [])

DIST = [
    {"weight": 20, "roe": 0.6, "pe": 122.1, "name": "Sudarshan", "sector": "Chemicals"},
    {"weight": 15, "roe": 5.1, "pe": 106.9, "name": "Carborundum", "sector": "Machinery"},
    {"weight": 25, "roe": 22.0, "pe": 18.0, "name": "Quality Co", "sector": "IT"},
    {"weight": 30, "roe": 12.0, "pe": 20.0, "name": "Middling", "sector": "Banks"},
    {"weight": 10},
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

BOOK = [
    {"weight": 40, "pe": 20, "pb": 3, "roe": 18, "growth": 15,
     "cap_rank": 40, "sector": "IT", "priced": True},
    {"weight": 35, "pe": 30, "pb": 5, "roe": 22, "growth": 25,
     "cap_rank": 150, "sector": "Banks", "priced": True},
    {"weight": 15, "pe": 10, "pb": 1.5, "roe": 12, "growth": 8,
     "cap_rank": 400, "sector": "Metals", "priced": True},
    {"weight": 10, "priced": False},
]
pm = L.portfolio_metrics(BOOK, equity_weight=100)
check("portfolio P/E harmonic over the priced 90%", approx(pm["portfolio_pe"]["value"], 19.29))
check("portfolio P/E coverage = 0.90 (the unlisted 10% counts against it)",
      pm["portfolio_pe"]["coverage"] == 0.9)
check("portfolio P/E is decision-grade at 90%", pm["portfolio_pe"]["confidence"] == "decision-grade")
check("portfolio P/B harmonic", approx(pm["portfolio_pb"]["value"], 2.97))
check("portfolio ROE weighted mean", approx(pm["portfolio_roe"]["value"], 18.56))
check("no earnings-growth metric: no sanctioned source publishes it per holding, and a\n"
      "      permanently-unavailable metric is a permanent gap",
      "earnings_growth" not in pm, sorted(pm))
check("pb_over_roe computed from the portfolio's own P/B and ROE",
      approx(pm["pb_over_roe"]["value"], 2.97 / 18.56, 0.001))
check("cap tilt from ranks: 44.4% large / 38.9% mid / 16.7% small",
      approx(pm["cap_tilt"]["large"], 0.4444) and approx(pm["cap_tilt"]["mid"], 0.3889)
      and approx(pm["cap_tilt"]["small"], 0.1667))
check("unpriced weight surfaced explicitly", pm["unpriced_weight_pct"] == 10.0)
check("overall confidence is decision-grade", pm["confidence"] == "decision-grade")

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

INDICATIVE = [{"weight": 65.0, "pe": 20, "pb": 3, "roe": 15, "cap_rank": 300, "priced": True}]
pm_i = L.portfolio_metrics(INDICATIVE, equity_weight=100.0)
check("65% coverage publishes an indicative ratio",
      pm_i["portfolio_pe"]["value"] == 20.0 and pm_i["portfolio_pe"]["confidence"] == "indicative")
check("indicative ratio carries a 'do not cite' gap",
      any("indicative only" in g for g in L.metric_gaps(pm_i)))

LABELLED = [{"weight": 100, "cap_label": "Smallcap", "pe": 20, "pb": 3, "roe": 15,
             "priced": True}]
check("label-fallback share is reported as a gap",
      any("text label" in g for g in L.metric_gaps(L.portfolio_metrics(LABELLED, 100))))

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

check("file hatch accepts a bare list",
      len(L.load_holdings_file([{"weight": 1}, {"weight": 2}])) == 2)
check("file hatch skips non-dict rows", len(L.load_holdings_file([1, "x", {"weight": 1}])) == 1)

_orig_load_fund = L.load_fund
PRICED_BOOK = [{"weight": 95.0, "pe": 25.0, "pb": 4.0, "roe": 18.0, "cap_rank": 50,
                "priced": True, "name": "A", "sector": "IT"}]
try:
    L.load_fund = lambda mf_id, fresh=False, workers=10: (
        PRICED_BOOK, 95.0, ["one holding unpriced"], {"mf_id": mf_id, "source": "Tickertape"})
    env = L.report("M_TEST")
finally:
    L.load_fund = _orig_load_fund
check("report returns the data-spine envelope",
      set(env) == {"ok", "source", "fetched_at", "data", "gaps"}, sorted(env))
check("report is ok when the book is priced well enough to publish", env["ok"] is True)
check("report carries the look-through metrics", "metrics" in env["data"], sorted(env["data"]))
check("report carries the coverage confidence grade",
      env["data"]["confidence"] == env["data"]["metrics"]["confidence"])
check("report keeps the fund identity in meta",
      env["data"]["meta"]["mf_id"] == "M_TEST", env["data"]["meta"])
check("report lifts the gaps to the envelope, not into data",
      "one holding unpriced" in env["gaps"] and "gaps" not in env["data"], env["gaps"])

try:
    L.load_fund = lambda mf_id, fresh=False, workers=10: (
        [], 0.0, ["no holdings returned for M_TEST"], {"mf_id": mf_id})
    env_empty = L.report("M_TEST")
finally:
    L.load_fund = _orig_load_fund
check("report with no holdings is ok:false", env_empty["ok"] is False)
check("report with no holdings names the gap",
      any("no holdings" in g for g in env_empty["gaps"]), env_empty["gaps"])

try:
    L.load_fund = lambda mf_id, fresh=False, workers=10: (
        [{"weight": 20.0, "pe": 25.0, "pb": 4.0, "roe": 18.0, "priced": True}],
        100.0, [], {"mf_id": mf_id})
    env_thin = L.report("M_TEST")
finally:
    L.load_fund = _orig_load_fund
check("report below the publishable coverage floor is ok:false — a gap, not a valuation",
      env_thin["ok"] is False and env_thin["data"]["confidence"] == "unusable",
      env_thin["data"]["confidence"])

for invalid_rank in (0.5, 100.5, 250.5, "100%", True, float("inf")):
    check("invalid ordinal rank remains unclassified", caps.cap_bucket(cap_rank=invalid_rank)==(None,None), invalid_rank)
for ambiguous in ("large and mid cap", "midcap fund", "smallish", "microfinance", "large-cap blend"):
    check("ambiguous cap label remains unclassified", caps.cap_bucket(cap_label=ambiguous)==(None,None), ambiguous)
check("integer-valued provider rank accepted", caps.cap_bucket(cap_rank="101.0")==("mid","rank"))

for weight in (-10,True,float("nan"),101,None):
    try:
        L.portfolio_metrics([{"weight":weight,"pe":10,"pb":2}],equity_weight=100)
        check("invalid holding weight rejects portfolio metrics",False,weight)
    except ValueError:
        check("invalid holding weight rejects portfolio metrics",True)
try:
    L.portfolio_metrics([{"weight":60},{"weight":60}],equity_weight=100)
    check("overfull holdings cannot inflate coverage",False)
except ValueError:
    check("overfull holdings cannot inflate coverage",True)

from unittest import mock
for allocation in (0,50,101,float("nan"),True):
    with mock.patch.object(L,"load_fund",return_value=([{"weight":60,"pe":10,"pb":2}],allocation,["fixture source gap"],{"mf_id":"fixture"})):
        invalid=L.report("fixture")
    check("inconsistent equity allocation returns unusable report",not invalid["ok"] and invalid["data"]["ratios_publishable"] is False and invalid["data"]["metrics"]=={},allocation)
    check("invalid allocation report preserves source and validation gaps", "fixture source gap" in invalid["gaps"] and any("invalid holdings coverage" in gap for gap in invalid["gaps"]),invalid)

split_book=[{"weight":40,"pb":2},{"weight":40,"roe":10},{"weight":20,"pb":4,"roe":20}]
combined=L.portfolio_metrics(split_book,100)["pb_over_roe"]
check("combined valuation coverage is the shared holding set",combined["coverage"]==0.2,combined)
check("separate 60-percent ratios cannot publish a 20-percent joint ratio",combined["withheld"] and combined["value"] is None,combined)
shared_book=[{"weight":60,"pb":2,"roe":10},{"weight":20,"pb":20},{"weight":20,"roe":40}]
combined=L.portfolio_metrics(shared_book,100)["pb_over_roe"]
check("joint metric excludes unmatched ratios from its value",approx(combined["value"],0.2) and combined["coverage"]==0.6,combined)

negative=L.portfolio_metrics([{"weight":100,"pb":2,"roe":-5}],100)
check("undefined joint ratio retains actual coverage",negative["pb_over_roe"]["coverage"]==1)
check("undefined ratio gap explains profitability rather than missing coverage",any("pb_over_roe" in gap and "non-positive ROE" in gap for gap in L.metric_gaps(negative)))

with mock.patch.object(L,"load_fund",return_value=([{"weight":20,"pe":10,"pb":2}],None,[],{})):
    missing=L.report("fixture")
check("missing equity allocation cannot make a partial book fully covered",not missing["ok"] and not missing["data"]["ratios_publishable"] and any("equity" in gap for gap in missing["gaps"]),missing)

from finance.sources import funds as source_funds
with mock.patch.object(source_funds, "holdings", return_value={
    "ok": True, "data": {"positions": [{"sid": "FIX", "type": "equity", "weight": 20}],
                          "equity_weight": None}, "gaps": ["incomplete allocation"]
}), mock.patch.object(source_funds, "enrich", return_value=([], [])) as enrich_call:
    invalid = L.report("fixture")
check("unknown coverage skips per-stock enrichment", enrich_call.call_count == 0, enrich_call.call_count)
check("unknown coverage retains position count and source gap",
      not invalid["ok"] and invalid["data"]["n_holdings"] == 1
      and "incomplete allocation" in invalid["gaps"], invalid)

# Finite inputs must not publish nonfinite aggregates through intermediate overflow.
large_mean, covered = L.weighted_mean([(50, 1e308), (50, 1e308)])
check('large finite weighted mean remains representable', large_mean == 1e308 and covered == 100)
tiny_harmonic, covered = L.weighted_harmonic([(50, 1e-308), (50, 1e-308)])
check('tiny positive multiples do not collapse to zero through yield overflow',
      tiny_harmonic == 1e-308 and covered == 100)
for invalid in (None, float('nan'), float('inf')):
    invalid_metric = L.gated(invalid, 100, 100)
    check('coverage cannot make an invalid calculated metric publishable',
          invalid_metric['value'] is None and invalid_metric['withheld'], invalid)
_calls = []
try:
    L.load_fund = lambda mf_id, fresh=False, workers=10: _calls.append(workers) or ([], 0.0, [], {})
    for bad in (0, -1, 2.5, True, "4", None):
        env_bad = L.report("M_TEST", workers=bad)
        check(f"invalid workers {bad!r} is a labelled gap, not an exception",
              env_bad["ok"] is False and any("workers" in g for g in env_bad["gaps"]), env_bad)
finally:
    L.load_fund = _orig_load_fund
check("invalid workers never reach the fetch path", _calls == [], _calls)
summary()
