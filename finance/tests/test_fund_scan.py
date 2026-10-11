#!/usr/bin/env python3
"""Offline tests for the category scanner's pure logic. No network."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import fund_scan as S
from finance.tests.harness import check, summary


r = S.percentile_ranks([1, 2, 3, 4, 5])
check("best value ranks 1.0 when higher is better", r[4] == 1.0, r)
check("worst value ranks 0.0", r[0] == 0.0, r)
check("ranks are monotonic", r == sorted(r), r)
r_low = S.percentile_ranks([1, 2, 3, 4, 5], higher_is_better=False)
check("lower-is-better inverts the ranking", r_low[0] == 1.0 and r_low[4] == 0.0, r_low)
r_none = S.percentile_ranks([1, None, 3])
check("a missing metric stays None rather than scoring 0",
      r_none[1] is None and r_none[0] == 0.0 and r_none[2] == 1.0, r_none)
check("an all-missing column yields all None",
      S.percentile_ranks([None, None]) == [None, None])
check("a single valued peer scores 0.5 (rank carries no information)",
      S.percentile_ranks([None, 7, None])[1] == 0.5)
ties = S.percentile_ranks([5, 5, 1])
check("ties share the average rank", ties[0] == ties[1], ties)
check("an outlier does not compress the rest (rank, not min-max)",
      S.percentile_ranks([1, 2, 1000])[1] == 0.5, S.percentile_ranks([1, 2, 1000]))

check("inside the band scores full marks", S.aum_agility(5000, 500, 20000) == 1.0)
check("below the viability floor scores 0", S.aum_agility(200, 500, 20000) == 0.0)
check("twice the ceiling decays to 0.5, not 0 (size is a headwind, not a veto)",
      S.aum_agility(40000, 500, 20000) == 0.5)
check("exactly at the ceiling still scores 1.0", S.aum_agility(20000, 500, 20000) == 1.0)
check("missing AUM is None, never 0", S.aum_agility(None, 500, 20000) is None)
check("a nonsensical AUM is None", S.aum_agility(0, 500, 20000) is None)
check("agility decays monotonically past the ceiling",
      S.aum_agility(30000, 500, 20000) > S.aum_agility(60000, 500, 20000))

check("85% in-mandate maps to 0.85", abs(S.cap_purity(85) - 0.85) < 1e-9)
check("purity over 100 is unknown, not a perfect score", S.cap_purity(120) is None)
check("negative purity is unknown, not a zero allocation", S.cap_purity(-5) is None)
check("missing purity is None", S.cap_purity(None) is None)

score, cov, used = S.composite({k: 1.0 for k in S.WEIGHTS})
check("all components present scores 1.0 at full coverage", score == 1.0 and cov == 1.0)
check("every weighted component is reported as used", len(used) == len(S.WEIGHTS))
k0 = sorted(S.WEIGHTS)[0]
partial = {k: (None if k == k0 else 1.0) for k in S.WEIGHTS}
score_p, cov_p, used_p = S.composite(partial)
check("a missing component redistributes weight instead of penalising",
      score_p == 1.0, score_p)
check("coverage records what actually applied", cov_p < 1.0, cov_p)
check("the dropped component is absent from scored_on", k0 not in used_p)
check("no usable component yields a None score, not 0",
      S.composite({k: None for k in S.WEIGHTS}) == (None, 0.0, []))

good = {"option": "Growth", "expRatio": 0.7, "aum": 5000, "ageInMon": 60}
ok, reasons = S.gate(good, 500, 36)
check("a compliant fund passes every gate", ok and reasons == [], reasons)
ok, reasons = S.gate(dict(good, option="IDCW"), 500, 36)
check("an IDCW plan is gated out", not ok and any("Growth" in r for r in reasons))
ok, reasons = S.gate(dict(good, expRatio=1.9), 500, 36)
check("a Regular-plan TER masquerading as Direct is caught",
      not ok and any("ceiling" in r for r in reasons), reasons)
ok, reasons = S.gate(dict(good, aum=100), 500, 36)
check("sub-floor AUM is gated out", not ok and any("viability" in r for r in reasons))
ok, reasons = S.gate(dict(good, ageInMon=12), 500, 36)
check("a fund younger than the credited window is gated out",
      not ok and any("younger" in r for r in reasons), reasons)
ok, reasons = S.gate({"option": "Growth"}, 500, 36)
check("unpublished fields are gated as unverifiable, never assumed good",
      not ok and len(reasons) == 3, reasons)
check("gate reasons diagnose the fund, never name it",
      all("Growth" in r or "TER" in r or "AUM" in r or "age" in r or "expense" in r
          or "months" in r for r in reasons), reasons)

check("under 3 years is low confidence", S.span_confidence(2.0) == "low")
check("3-7 years is ok", S.span_confidence(5.0) == "ok")
check("7+ years earns full-cycle", S.span_confidence(8.0) == "full-cycle")
check("unknown span is 'unknown', not a guess", S.span_confidence(None) == "unknown")

schemes = [
    {"code": "1", "name": "ITI Small Cap Fund - Direct Plan - Growth"},
    {"code": "2", "name": "ITI Small Cap Fund - Direct Plan - IDCW"},
    {"code": "3", "name": "ITI Small Cap Fund - Regular Plan - Growth"},
    {"code": "4", "name": "ITI Multi Cap Fund - Direct Plan - Growth"},
    {"code": "5", "name": "ITI Large Cap Fund - Direct Plan - Growth"},
]
m = S.match_amfi_scheme("ITI Small Cap Fund", schemes)
check("the Direct-Growth scheme is chosen", m and m["code"] == "1", m)
check("the IDCW variant is rejected (different NAV series, same name)",
      m and "IDCW" not in m["name"])
check("the Regular plan is rejected", m and "Regular" not in m["name"])
check("'Small Cap' does not match 'Large Cap'",
      S.match_amfi_scheme("ITI Large Cap Fund", schemes)["code"] == "5")
check("token-set matching: 'ITI' must not match inside 'MULTI'",
      S.match_amfi_scheme("ITI Multi Cap Fund", schemes)["code"] == "4")
check("an unmatched fund returns None, never a near-miss",
      S.match_amfi_scheme("Nonexistent Zzz Fund", schemes) is None)
check("an empty scheme list returns None",
      S.match_amfi_scheme("ITI Small Cap Fund", []) is None)

navs = [{"date": f"2020-01-{d:02d}", "nav": v}
        for d, v in zip(range(1, 11), [100, 110, 120, 90, 95, 130, 140, 120, 150, 160])]
m = S.nav_metrics(navs, 1)
check("max drawdown is computed from the NAV series, not bought from a vendor",
      m["max_drawdown_pct"] is not None and m["max_drawdown_pct"] > 0, m["max_drawdown_pct"])
check("the worst peak-to-trough is found (120 -> 90 = 25%)",
      abs(m["max_drawdown_pct"] - 25.0) < 0.01, m["max_drawdown_pct"])
check("the NAV as-of date is the newest bar", m["nav_as_of"] == "2020-01-10", m)
check("ten days cannot establish confidence in one-year rolling returns", m["confidence"] == "unknown")
empty = S.nav_metrics([], 1)
check("an empty NAV series degrades to None, never raises",
      empty["max_drawdown_pct"] is None and empty["n_windows"] == 0)
check("a one-point series is still safe", S.nav_metrics([navs[0]], 1)["confidence"] == "unknown")
for bad in ({"date":"bad","nav":"x"}, {"date":"2010-01-01","nav":"bad"}, {"date":"2010-01-01","nav":True}):
    try:
        S.nav_metrics([bad] + navs, 1)
        check("malformed NAV cannot misalign dates and values",False)
    except ValueError:
        check("malformed NAV cannot misalign dates and values",True)

check("a missing market-context path is None, not a fabricated market read",
      S.load_market_context("/nonexistent/path.json", "Small Cap Fund") is None)
with tempfile.TemporaryDirectory() as tmp:
    p = os.path.join(tmp, "mc.json")
    with open(p, "w") as fh:
        json.dump({"as_of": "2026-08-14", "market_trend": "range",
                   "market_posture": "neutral",
                   "volatility": {"band": "low"},
                   "relative": {"percentile_spread": 45.3},
                   "valuation": {"NIFTY SMALLCAP 250": {"pb_pctile": 77.0,
                                                        "stance": "rich"}}}, fh)
    mc = S.load_market_context(p, "Small Cap Fund")
    check("the small-cap tier's valuation is selected for a small-cap scan",
          mc["cap_tier"] == "NIFTY SMALLCAP 250", mc)
    check("the tier stance is carried through VERBATIM (the scanner does not judge it)",
          mc["tier_valuation"]["stance"] == "rich", mc)
    check("posture and volatility band travel with it",
          mc["market_posture"] == "neutral" and mc["volatility_band"] == "low")
    check("the relative read is carried too",
          mc["relative"]["percentile_spread"] == 45.3)
    check("as_of comes from the market artifact, not from today",
          mc["as_of"] == "2026-08-14")
    with open(p, "w") as fh:
        fh.write("{corrupt")
    check("a corrupt market context degrades to None rather than raising",
          S.load_market_context(p, "Small Cap Fund") is None)

SCAN_RESULT = {
    "as_of": "2026-08-17", "category": "Small Cap Fund", "window_credited": "3y",
    "universe": {"screened": 20, "passed_gates": 6, "scored": 5, "shortlisted": 2},
    "gates": {"rejected_tally": {"AUM below the floor": 14}},
    "scoring": {"weights": S.WEIGHTS},
    "category_context": None, "pending_manual_gates": [],
    "shortlist": [{"rank": 1, "name": "Fund A", "flags": []}],
    "gaps": ["AMFI scheme list unavailable"],
}

_orig_scan = S.scan
with tempfile.TemporaryDirectory() as tmp:
    out = os.path.join(tmp, "fund-scan.json")
    try:
        S.scan = lambda **kw: dict(SCAN_RESULT)
        env = S.report(category="Small Cap Fund", top=2, out=out)
    finally:
        S.scan = _orig_scan
    check("report returns the data-spine envelope",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"}, sorted(env))
    check("report is ok when something was shortlisted", env["ok"] is True)
    check("report carries the shortlist inline",
          env["data"]["shortlist"][0]["name"] == "Fund A", env["data"]["shortlist"])
    check("report carries the universe funnel so a rank is auditable",
          env["data"]["universe"]["screened"] == 20, env["data"]["universe"])
    check("report keeps the rejection tally rather than hiding the failures",
          env["data"]["gates"]["rejected_tally"]["AUM below the floor"] == 14)
    check("report lifts the scan's gaps to the envelope, not into data",
          env["gaps"] == ["AMFI scheme list unavailable"] and "gaps" not in env["data"],
          env["gaps"])
    check("report writes the shortlist JSON and names the path",
          env["data"]["report_path"] != out and os.path.isfile(env["data"]["report_path"]))
    with open(env["data"]["report_path"]) as fh:
        check("the written shortlist keeps its own gaps list",
              json.load(fh)["gaps"] == ["AMFI scheme list unavailable"])

    try:
        S.scan = lambda **kw: dict(SCAN_RESULT, shortlist=[], gaps=["no fund cleared"])
        env_empty = S.report(category="Small Cap Fund", out=out)
    finally:
        S.scan = _orig_scan
    check("report with an empty shortlist is ok:false", env_empty["ok"] is False)
    check("report with an empty shortlist carries the reason",
          env_empty["gaps"] == ["no fund cleared"], env_empty["gaps"])

from unittest import mock
from finance.sources import funds as fund_source
with mock.patch.object(S,"match_amfi_scheme",return_value={"code":"fixture"}), mock.patch.object(fund_source,"nav_history",return_value={"ok":True,"data":{"navs":[{"date":"2020-01-01","nav":0}]},"gaps":[]}):
    hit, metrics, errors = S._resolve_and_nav({"name":"fixture"},[],1,False)
check("invalid NAV excludes only affected fund with a gap",metrics is None and any("invalid NAV" in gap for gap in errors))

for invalid in ({"window":"4y"},{"top":0},{"top":True},{"workers":0},
                {"min_aum_cr":float("nan")},{"ter_ceiling":-1},
                {"agility_ceiling_cr":0},{"min_age_months":-1},{"category":""}):
    with mock.patch.object(fund_source,"screen") as fetch, mock.patch.object(fund_source,"amfi_index",return_value={"data":{"schemes":[]}}):
        try:
            S.scan(**invalid)
            check("invalid fund scan rejected before fetching",False,invalid)
        except ValueError:
            check("invalid fund scan rejected before fetching",not fetch.called,invalid)
    with mock.patch.object(fund_source,"screen") as fetch, mock.patch.object(fund_source,"amfi_index",return_value={"data":{"schemes":[]}}):
        env=S.report(**invalid)
    check("invalid public scan returns a gap envelope",not fetch.called and not env["ok"] and bool(env["gaps"]),invalid)

ambiguous=[{"code":"10","name":"Fixture Equity Fund Direct Growth"},
           {"code":"20","name":"Fixture Equity Fund Direct Plan Growth"}]
check("two matching AMFI identities are not resolved by shortest name",S.match_amfi_scheme("Fixture Equity Fund",ambiguous) is None)
check("partial name cannot pick a more specific scheme",S.match_amfi_scheme("Fixture Equity Fund",[{"code":"10","name":"Fixture Equity Opportunities Fund Direct Growth"}]) is None)
check("duplicate rows for one scheme do not create ambiguity",S.match_amfi_scheme("Fixture Equity Fund",[ambiguous[0],dict(ambiguous[0])])["code"]=="10")
check("malformed registry neighbors do not block valid identity",S.match_amfi_scheme("Fixture Equity Fund",[None,{"name":5},ambiguous[0]])["code"]=="10")

with tempfile.TemporaryDirectory() as directory:
    hint=os.path.join(directory,"scan.json")
    with mock.patch.object(S,"scan",return_value=dict(SCAN_RESULT)):
        first=S.report(out=hint)
        identical=S.report(out=hint)
    with mock.patch.object(S,"scan",return_value=dict(SCAN_RESULT,shortlist=[])):
        second=S.report(out=hint)
    check("changed fund scan gets distinct evidence path",first["data"]["report_path"] != second["data"]["report_path"])
    check("identical fund scan reuses content address",first["data"]["report_path"] == identical["data"]["report_path"])
    with open(first["data"]["report_path"]) as stream:
        check("earlier shortlist survives later empty scan",bool(json.load(stream)["shortlist"]))

with tempfile.TemporaryDirectory() as directory, mock.patch.object(S,"scan",return_value=dict(SCAN_RESULT)), mock.patch.object(S.spine,"publish_evidence",side_effect=OSError("fixture unavailable")):
    failed=S.report(out=os.path.join(directory,"scan.json"))
check("snapshot failure preserves computed shortlist with gap",failed["ok"] and failed["data"]["report_path"] is None and bool(failed["data"]["shortlist"]) and any("could not write" in gap for gap in failed["gaps"]))

for category, expected in (("Large Cap Fund","80%"),("Mid Cap Fund","15%"),("Small Cap Fund","0%"),("Flexi Cap Fund","—")):
    metrics={"cap_mix":{"small":0,"mid":15,"large":80},"rolling":{"mean":10,"min":5},
             "max_drawdown_pct":20,"expense_ratio_pct":0.5,"aum_cr":1000,"sharpe":1}
    fixture=dict(SCAN_RESULT,category=category,shortlist=[{"rank":1,"name":"PurityFixture","score":0.5,"flags":[],"metrics":metrics}])
    line=next(line for line in S.render_table(fixture).splitlines() if "PurityFixture" in line)
    check("table purity corresponds to the category mandate including zero",line.split()[-1]==expected,(category,line))

fixture_row={"name":"Fixture","option":"Growth","expRatio":0.5,"aum":1000,"ageInMon":60,
             "sharpe":1,"sortino":1,"alpha":1,"stdDevAnn":10,"percSmallcap":120}
fixture_nav={"roll_mean":10,"roll_min":5,"roll_median":8,"n_windows":100,"max_drawdown_pct":20,
             "span_years":5,"confidence":"ok","nav_as_of":"2020-01-01"}
with mock.patch.object(fund_source,"screen",return_value={"data":{"funds":[fixture_row]},"gaps":[]}), mock.patch.object(fund_source,"amfi_index",return_value={"data":{"schemes":[{"code":"fixture"}]}}), mock.patch.object(S,"_resolve_and_nav",return_value=({"code":"fixture"},fixture_nav,[])):
    result=S.scan()
check("invalid provider purity reaches the report gaps",any("invalid percSmallcap" in gap for gap in result["gaps"]))
check("invalid purity contributes no score or coverage",result["shortlist"] and "cap_purity" not in result["shortlist"][0]["scored_on"] and result["shortlist"][0]["components"]["cap_purity"] is None)

# Age metadata cannot substitute for usable returns over the requested window.
missing_windows = dict(fixture_nav, roll_mean=None, roll_min=None, roll_median=None,
                       n_windows=0, confidence='unknown')
with mock.patch.object(fund_source, 'screen', return_value={'data': {'funds': [dict(fixture_row, percSmallcap=80)]}, 'gaps': []}), mock.patch.object(fund_source, 'amfi_index', return_value={'data': {'schemes': [{'code': 'fixture'}]}}), mock.patch.object(S, '_resolve_and_nav', return_value=({'code': 'fixture'}, missing_windows, [])):
    missing_result = S.scan()
check('fund with no requested rolling windows cannot enter ranking', not missing_result['shortlist'])
check('NAV-stage rejection preserves the earlier funnel count',
      missing_result['universe']['passed_gates'] == 1 and missing_result['universe']['scored'] == 0)
check('missing rolling coverage explains rejection without recommending weaker gates',
      any('rolling' in gap for gap in missing_result['gaps'])
      and not any('loosen' in gap for gap in missing_result['gaps']))
summary()
