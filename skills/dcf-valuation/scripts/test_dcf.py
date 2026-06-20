#!/usr/bin/env python3
"""Offline tests for the DCF engine. No network, no yfinance — pure arithmetic checks.

Run: python3 test_dcf.py    (exit 0 = all pass)
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dcf  # noqa: E402

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


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


# 1) A hand-computable single-year, no-terminal-distortion case.
#    base 1000, growth 10% -> rev 1100, margin 20% -> ebit 220, tax 25% -> nopat 165,
#    reinvest = (1100-1000)/2 = 50, fcff = 115, wacc 10% -> pv = 115/1.1 = 104.545...
#    terminal: g 4%, roic 10% -> reinv_rate 0.4; rev_T1=1100*1.04=1144; nopat_T1=1144*0.2*0.75=171.6
#    fcff_T1=171.6*0.6=102.96; TV=102.96/(0.10-0.04)=1716; pv_TV=1716/1.1=1560
#    EV = 104.545.. + 1560 = 1664.545..
spec1 = {
    "years": 1, "base_revenue": 1000.0, "revenue_growth": 0.10, "operating_margin": 0.20,
    "tax_rate": 0.25, "sales_to_capital": 2.0, "wacc": 0.10,
    "terminal_growth": 0.04, "terminal_roic": 0.10, "terminal_margin": 0.20,
    "shares_outstanding": 10.0, "net_debt": 0.0,
}
r1 = dcf.value(spec1)
check("y1 fcff = 115", approx(r1["yearly"][0]["fcff"], 115.0), r1["yearly"][0]["fcff"])
check("y1 pv_fcff = 104.5454", approx(r1["pv_explicit_fcff"], 115.0 / 1.1, 1e-4), r1["pv_explicit_fcff"])
check("terminal value = 1716", approx(r1["terminal_value"], 1716.0, 1e-4), r1["terminal_value"])
check("pv terminal = 1560", approx(r1["pv_terminal_value"], 1560.0, 1e-4), r1["pv_terminal_value"])
check("EV = 1664.5454", approx(r1["enterprise_value"], 115.0 / 1.1 + 1560.0, 1e-4), r1["enterprise_value"])
check("equity = EV (no debt)", approx(r1["equity_value"], r1["enterprise_value"]), r1["equity_value"])
check("per share = EV/10", approx(r1["intrinsic_value_per_share"], r1["enterprise_value"] / 10.0, 1e-4),
      r1["intrinsic_value_per_share"])

# 2) Net debt + non-operating cash + minority flow through the bridge correctly.
spec2 = dict(spec1, net_debt=200.0, non_operating_cash=50.0, minority_interest=30.0)
r2 = dcf.value(spec2)
check("equity bridge: EV-200+50-30", approx(r2["equity_value"], r2["enterprise_value"] - 200.0 + 50.0 - 30.0),
      r2["equity_value"])

# 3) wacc <= terminal growth is rejected (undefined Gordon TV).
try:
    dcf.value(dict(spec1, terminal_wacc=0.03, terminal_growth=0.04))
    check("wacc<=g raises", False, "no exception")
except ValueError:
    check("wacc<=g raises", True)

# 4) Margin of safety sign: intrinsic above price -> positive MoS.
r4 = dcf.value(dict(spec1, current_price=10.0))
check("MoS = intrinsic/price - 1",
      approx(r4["margin_of_safety"], r4["intrinsic_value_per_share"] / 10.0 - 1.0, 1e-6),
      r4["margin_of_safety"])
check("undervalued -> MoS>0 when intrinsic>price",
      (r4["intrinsic_value_per_share"] > 10.0) == (r4["margin_of_safety"] > 0))

# 5) Growth glide: 15% for 3 years then linear fade to 4% by year 10.
g = dcf.resolve_growth({"growth_glide": {"initial": 0.15, "fade_to": 0.04, "years_high": 3}}, 10)
check("glide len 10", len(g) == 10, len(g))
check("glide high years = 0.15", g[0] == 0.15 and g[1] == 0.15 and g[2] == 0.15, g[:3])
check("glide ends at 0.04", approx(g[-1], 0.04), g[-1])
check("glide monotone non-increasing after high", all(g[i] >= g[i + 1] - 1e-9 for i in range(2, 9)), g)

# 6) Margin glide: ramp 12% -> 18% by year 5, hold after.
m = dcf.resolve_margin({"margin_glide": {"start": 0.12, "target": 0.18, "year_target": 5}}, 10)
check("margin start 0.12", approx(m[0], 0.12), m[0])
check("margin hits target by y5", approx(m[4], 0.18), m[4])
check("margin holds target after y5", all(approx(x, 0.18) for x in m[5:]), m[5:])

# 7) Scalar vs list path expansion; short list carries last value forward.
p = dcf._as_path([0.11, 0.10], 5, 0.11)
check("path carries last fwd", p == [0.11, 0.10, 0.10, 0.10, 0.10], p)
check("scalar path expands", dcf._as_path(0.09, 3, 0.11) == [0.09, 0.09, 0.09])

# 8) Declining WACC path is applied year-by-year (cumulative discount).
specw = dict(spec1, years=2, revenue_growth=[0.10, 0.10], operating_margin=0.20,
             wacc=[0.12, 0.10], sales_to_capital=2.0)
rw = dcf.value(specw)
check("cum discount y2 = 1.12*1.10", approx(rw["yearly"][1]["discount_factor"], 1.12 * 1.10, 1e-9),
      rw["yearly"][1]["discount_factor"])

# 9) Higher WACC lowers value; higher terminal growth raises it (monotonicity).
base = dcf.value(spec1)["intrinsic_value_per_share"]
hi_wacc = dcf.value(dict(spec1, wacc=0.13, terminal_wacc=0.13))["intrinsic_value_per_share"]
hi_g = dcf.value(dict(spec1, terminal_growth=0.05))["intrinsic_value_per_share"]
check("higher WACC -> lower value", hi_wacc < base, (hi_wacc, base))
check("higher terminal g -> higher value", hi_g > base, (hi_g, base))

# 10) Sanity flags fire on the documented thresholds.
fr = dcf.value({
    "years": 5, "base_revenue": 1000.0, "revenue_growth": 0.35, "operating_margin": 0.45,
    "tax_rate": 0.25, "sales_to_capital": 2.0, "wacc": 0.11,
    "terminal_growth": 0.08, "terminal_roic": 0.10, "risk_free": 0.07,
    "shares_outstanding": 10.0,
})
flags = " ".join(fr["flags"])
check("flag: terminal growth > risk free", "TERMINAL_GROWTH_ABOVE_RISKFREE" in flags)
check("flag: high margin", "HIGH_MARGIN_ASSUMPTION" in flags)
check("flag: high growth", "HIGH_GROWTH_ASSUMPTION" in flags)

# 11) Terminal-value-heavy flag for a positive-EV but terminal-dominated case
#     (modest, light-reinvestment explicit period -> small positive FCFF, large terminal).
heavy = dcf.value({
    "years": 10, "base_revenue": 1000.0, "growth_glide": {"initial": 0.08, "fade_to": 0.05, "years_high": 3},
    "margin_glide": {"start": 0.10, "target": 0.12, "year_target": 5},
    "tax_rate": 0.25, "sales_to_capital": 4.0, "wacc": 0.09,
    "terminal_growth": 0.07, "terminal_roic": 0.11, "terminal_wacc": 0.08, "shares_outstanding": 10.0,
})
check("flag: terminal value heavy", any("TERMINAL_VALUE_HEAVY" in f for f in heavy["flags"]), heavy["flags"])
check("terminal-heavy EV positive", heavy["enterprise_value"] > 0, heavy["enterprise_value"])

# 11b) Negative-EV flag when reinvestment is implausibly heavy vs thin margins.
neg = dcf.value({
    "years": 10, "base_revenue": 1000.0, "growth_glide": {"initial": 0.20, "fade_to": 0.04, "years_high": 5},
    "margin_glide": {"start": 0.02, "target": 0.10, "year_target": 10},
    "tax_rate": 0.25, "sales_to_capital": 1.0, "wacc": 0.11,
    "terminal_growth": 0.05, "terminal_roic": 0.12, "shares_outstanding": 10.0,
})
check("flag: negative enterprise value", any("NEGATIVE_ENTERPRISE_VALUE" in f for f in neg["flags"]), neg["flags"])

# 12) No-excess-return flag when terminal ROIC == terminal WACC.
ner = dcf.value(dict(spec1, terminal_roic=0.10, terminal_wacc=0.10, wacc=0.11))
# terminal_wacc 0.10 > g 0.04 ok; roic==wacc -> flag
check("flag: no terminal excess return", any("NO_TERMINAL_EXCESS_RETURN" in f for f in ner["flags"]), ner["flags"])

# 13) Reinvestment is zero in a flat (no-growth) year -> fcff == nopat.
flat = dcf.value({"years": 1, "base_revenue": 1000.0, "revenue_growth": 0.0,
                  "operating_margin": 0.20, "tax_rate": 0.25, "sales_to_capital": 2.0,
                  "wacc": 0.10, "terminal_growth": 0.0, "terminal_roic": 0.10,
                  "shares_outstanding": 10.0})
check("flat year: reinvest 0", approx(flat["yearly"][0]["reinvestment"], 0.0), flat["yearly"][0]["reinvestment"])
check("flat year: fcff == nopat", approx(flat["yearly"][0]["fcff"], flat["yearly"][0]["nopat"]))

# 14) terminal value fraction is in (0,1) and consistent with components.
tvf = base
rfull = dcf.value(spec1)
check("tv fraction = pv_tv/EV",
      approx(rfull["terminal_value_fraction"], rfull["pv_terminal_value"] / rfull["enterprise_value"], 1e-6),
      rfull["terminal_value_fraction"])

# 15) Sensitivity grid: center cell equals the base intrinsic value; rejects wacc<=g cells as None.
sens = dcf.sensitivity(spec1)
center = sens["cells"][2][2]  # zero-delta on both axes
check("sensitivity center == base", approx(center, round(base, 2), 1e-2), (center, base))
check("sensitivity grid 5x5", len(sens["cells"]) == 5 and all(len(r) == 5 for r in sens["cells"]))

# 16) shares <= 0 rejected.
try:
    dcf.value(dict(spec1, shares_outstanding=0))
    check("zero shares raises", False)
except ValueError:
    check("zero shares raises", True)

# --- reverse DCF ---------------------------------------------------------------------
# Use a multi-year, value-creating spec (terminal ROIC 0.14 > WACC 0.11) so growth genuinely
# drives value — the only setting in which a reverse-DCF on growth is well-posed.
rspec = {
    "years": 10, "base_revenue": 1000.0,
    "growth_glide": {"initial": 0.12, "fade_to": 0.05, "years_high": 3},
    "margin_glide": {"start": 0.15, "target": 0.18, "year_target": 5},
    "tax_rate": 0.25, "sales_to_capital": 2.5, "wacc": 0.11,
    "terminal_growth": 0.05, "terminal_roic": 0.14, "shares_outstanding": 100.0, "net_debt": 0.0,
}
base_intrinsic = dcf.value(rspec)["intrinsic_value_per_share"]

# 16b) Round-trip: solving for the price that equals base intrinsic returns ~zero shift.
rt = dcf.reverse_dcf(rspec, target_per_share=base_intrinsic, solve="growth")
check("reverse: target=base intrinsic -> ~0 shift", rt["solved"] and abs(rt["shift"]) < 1e-3,
      rt.get("shift", rt))

# 16c) A higher target requires MORE growth (positive shift), and the solved spec reprices to target.
hi_target = base_intrinsic * 1.5
rh = dcf.reverse_dcf(rspec, target_per_share=hi_target, solve="growth")
check("reverse: higher price -> positive growth shift", rh["solved"] and rh["shift"] > 0, rh)
if rh["solved"]:
    repriced = dcf.value(dict(rspec, growth_glide=None, revenue_growth=rh["implied_path"]))["intrinsic_value_per_share"]
    check("reverse: solved growth reprices to target", approx(repriced, hi_target, 1e-3), (repriced, hi_target))
    check("reverse: reports implied revenue CAGR", "implied_revenue_cagr" in rh, list(rh.keys()))

# 16d) A lower target requires LESS growth (negative shift).
lo_target = base_intrinsic * 0.6
rl = dcf.reverse_dcf(rspec, target_per_share=lo_target, solve="growth")
check("reverse: lower price -> negative growth shift", rl["solved"] and rl["shift"] < 0, rl)

# 16e) Unreachably high target is reported as unsolved (not a bogus number).
ru = dcf.reverse_dcf(rspec, target_per_share=base_intrinsic * 50, solve="growth")
check("reverse: unreachable target -> solved False with reason",
      (not ru["solved"]) and "reason" in ru, ru)

# 16f) Default target falls back to current_price.
rp = dcf.reverse_dcf(dict(rspec, current_price=base_intrinsic), solve="growth")
check("reverse: defaults to current_price", rp["solved"] and abs(rp["shift"]) < 1e-3, rp.get("shift", rp))

# 16g) Missing target raises.
try:
    dcf.reverse_dcf(rspec, solve="growth")
    check("reverse: no target raises", False)
except ValueError:
    check("reverse: no target raises", True)

# 16h) Solving for margin works and reprices to target.
rm = dcf.reverse_dcf(rspec, target_per_share=base_intrinsic * 1.3, solve="margin")
check("reverse: margin solve brackets", rm["solved"], rm)
if rm["solved"]:
    repm = dcf.value(dict(rspec, margin_glide=None, operating_margin=rm["implied_path"]))["intrinsic_value_per_share"]
    check("reverse: solved margin reprices to target", approx(repm, base_intrinsic * 1.3, 1e-3), (repm,))

# 18) Failure-probability haircut: equity scales by (1-p_fail) when recovery=0; p>1 rejected.
fp = dcf.value(dict(spec1, failure_probability=0.10))
check("failure haircut: equity = going_concern*(1-p)",
      approx(fp["equity_value"], fp["equity_value_going_concern"] * 0.90, 1e-6),
      (fp["equity_value"], fp["equity_value_going_concern"]))
check("failure haircut: per-share below going concern",
      fp["intrinsic_value_per_share"] < dcf.value(spec1)["intrinsic_value_per_share"])
fpr = dcf.value(dict(spec1, failure_probability=0.20, failure_recovery=0.5))
check("failure recovery: equity = gc*((1-p)+rec*p)",
      approx(fpr["equity_value"], fpr["equity_value_going_concern"] * (0.80 + 0.5 * 0.20), 1e-6),
      fpr["equity_value"])
try:
    dcf.value(dict(spec1, failure_probability=1.5))
    check("failure_probability>1 raises", False)
except ValueError:
    check("failure_probability>1 raises", True)

# 19) WACC build-up (melded): CoE = rf + beta*mature_erp + lambda*crp; country risk scales with exposure.
wb = {"risk_free": 0.07, "beta": 1.1, "mature_erp": 0.045, "country_risk_premium": 0.03,
      "cost_of_debt_pretax": 0.09, "equity_weight": 0.95, "tax_rate": 0.25}
rwb = dcf.value(dict(spec1, wacc=None, wacc_buildup=wb))
det = rwb["assumptions"]["wacc_buildup"]
coe_full = 0.07 + 1.1 * 0.045 + 1.0 * 0.03  # lambda defaults to 1.0 (fully domestic)
check("wacc buildup: melded CoE = rf+beta*mature_erp+lambda*crp", approx(det["cost_of_equity"], coe_full, 1e-9), det)
exp_wacc = 0.95 * coe_full + 0.05 * 0.09 * 0.75
check("wacc buildup: weighted wacc", approx(det["wacc"], exp_wacc, 1e-9), (det["wacc"], exp_wacc))
check("wacc buildup: applied to discounting", approx(rwb["assumptions"]["wacc_path"][0], exp_wacc, 1e-6))
check("explicit wacc overrides buildup",
      approx(dcf.value(dict(spec1, wacc=0.12, wacc_buildup=wb))["assumptions"]["wacc_path"][0], 0.12, 1e-9))
# lambda scales the country premium with operating exposure: a low-lambda exporter pays less CRP.
exporter = dcf.value(dict(spec1, wacc=None, wacc_buildup=dict(wb, lambda_country=0.1)))
check("low lambda (exporter) lowers cost of equity",
      exporter["assumptions"]["wacc_buildup"]["cost_of_equity"] < det["cost_of_equity"],
      (exporter["assumptions"]["wacc_buildup"]["cost_of_equity"], det["cost_of_equity"]))
check("lambda reported", approx(exporter["assumptions"]["wacc_buildup"]["lambda_country"], 0.1, 1e-9))

# 19b) Bottom-up beta discipline: a high (regression-style) beta is flagged; beta is reported in the detail.
hibeta = dcf.value(dict(spec1, wacc=None, wacc_buildup=dict(wb, beta=1.5)))
check("beta reported in wacc detail", approx(hibeta["assumptions"]["wacc_buildup"]["beta"], 1.5, 1e-9))
check("flag: high beta looks like regression",
      any("BETA_LOOKS_LIKE_REGRESSION" in f for f in hibeta["flags"]), hibeta["flags"])
check("no beta flag for a bottom-up-range beta (1.1)",
      not any("BETA_LOOKS_LIKE_REGRESSION" in f for f in rwb["flags"]))

# 19c) Terminal ROIC defaults to convergence (= terminal WACC, no perpetual excess) when unspecified —
#      the Damodaran base case; excess return is surfaced separately and must be argued, not defaulted in.
noroic = dict(spec1)
noroic.pop("terminal_roic", None)
rnr = dcf.value(noroic)
check("terminal_roic defaults to terminal_wacc (convergence)",
      approx(rnr["assumptions"]["terminal_roic"], rnr["assumptions"]["terminal_wacc"], 1e-9),
      (rnr["assumptions"]["terminal_roic"], rnr["assumptions"]["terminal_wacc"]))
check("terminal_excess_return = roic - wacc",
      approx(rnr["assumptions"]["terminal_excess_return"],
             rnr["assumptions"]["terminal_roic"] - rnr["assumptions"]["terminal_wacc"], 1e-9))
check("convergence default -> NO_TERMINAL_EXCESS_RETURN",
      any("NO_TERMINAL_EXCESS_RETURN" in f for f in rnr["flags"]))

# 20) Story-driver sensitivity: center cell == base; value rises with growth and with margin.
ss = dcf.story_sensitivity(rspec)
center_ss = ss["cells"][2][1]  # zero growth-shift, zero margin-shift
check("story grid: center == base intrinsic", approx(center_ss, round(base_intrinsic, 2), 1e-2),
      (center_ss, base_intrinsic))
check("story grid: higher growth -> higher value", ss["cells"][4][1] > ss["cells"][0][1],
      (ss["cells"][4][1], ss["cells"][0][1]))
check("story grid: higher margin -> higher value", ss["cells"][2][2] > ss["cells"][2][0])
check("story grid: duration read present for a glide spec", "duration" in ss and len(ss["duration"]) == 3)
check("story grid: more high-growth years -> higher value",
      ss["duration"][2]["per_share"] > ss["duration"][0]["per_share"], ss["duration"])
# The point of the fix: the story range is WIDER than the WACC×g range (it moves the levers that matter).
story_flat = [c for row in ss["cells"] for c in row if c is not None]
wacc_g = dcf.sensitivity(rspec)
wg_flat = [c for row in wacc_g["cells"] for c in row if c is not None]
check("story range wider than WACC×g range",
      (max(story_flat) - min(story_flat)) > (max(wg_flat) - min(wg_flat)),
      (max(story_flat) - min(story_flat), max(wg_flat) - min(wg_flat)))

# 21) Young-stage flag: terminal-heavy is suppressed (expected) up to 90%, worded as expected.
young = dict(dcf.SELFTEST_SPEC, lifecycle_stage="high_growth",
             growth_glide={"initial": 0.30, "fade_to": 0.06, "years_high": 4},
             terminal_growth=0.06, terminal_roic=0.14, sales_to_capital=3.0)
ry = dcf.value(young)
tvheavy = [f for f in ry["flags"] if "TERMINAL_VALUE_HEAVY" in f]
if tvheavy:
    check("young-stage terminal-heavy worded as expected", "EXPECTED" in tvheavy[0], tvheavy)
else:
    check("young-stage terminal-heavy suppressed below 90%", ry["terminal_value_fraction"] <= 0.90,
          ry["terminal_value_fraction"])
check("lifecycle_stage reported", ry["assumptions"]["lifecycle_stage"] == "high_growth")

# 22) Complexity/governance discount: separate explicit haircut on equity, after the failure branch.
cxr = dcf.value(dict(spec1, complexity_discount=0.20))
check("complexity discount: equity = going_concern*(1-cx)",
      approx(cxr["equity_value"], cxr["equity_value_going_concern"] * 0.80, 1e-6),
      (cxr["equity_value"], cxr["equity_value_going_concern"]))
cxf = dcf.value(dict(spec1, failure_probability=0.10, complexity_discount=0.20))
check("failure and complexity compose multiplicatively",
      approx(cxf["equity_value"], cxf["equity_value_going_concern"] * 0.90 * 0.80, 1e-6), cxf["equity_value"])
try:
    dcf.value(dict(spec1, complexity_discount=1.0))
    check("complexity_discount>=1 raises", False)
except ValueError:
    check("complexity_discount>=1 raises", True)

# 23) Decline-stage flags: positive terminal growth flagged; terminal-heavy worded as a red flag.
decl = dcf.value({
    "years": 5, "base_revenue": 1000.0, "lifecycle_stage": "decline",
    "growth_glide": {"initial": -0.05, "fade_to": -0.02, "years_high": 2},
    "margin_glide": {"start": 0.10, "target": 0.08, "year_target": 5},
    "tax_rate": 0.25, "sales_to_capital": 4.0, "wacc": 0.12,
    "terminal_growth": 0.03, "terminal_roic": 0.13, "terminal_wacc": 0.12, "shares_outstanding": 10.0,
})
check("decline + positive terminal growth flagged",
      any("DECLINE_POSITIVE_TERMINAL_GROWTH" in f for f in decl["flags"]), decl["flags"])

# 24) Guard: discount applied to already-negative going-concern equity is flagged as meaningless.
negcx = dcf.value({
    "years": 10, "base_revenue": 90000.0, "revenue_growth": 0.25, "operating_margin": 0.06,
    "tax_rate": 0.25, "sales_to_capital": 0.9, "wacc": 0.13, "terminal_growth": 0.05,
    "terminal_roic": 0.04, "terminal_wacc": 0.13, "shares_outstanding": 110.0, "net_debt": 70000.0,
    "complexity_discount": 0.4, "failure_probability": 0.2,
})
check("guard: discount on non-positive equity flagged",
      any("DISCOUNT_ON_NONPOSITIVE_EQUITY" in f for f in negcx["flags"]), negcx["flags"])
check("guard: no false fire when going-concern equity positive",
      not any("DISCOUNT_ON_NONPOSITIVE_EQUITY" in f for f in dcf.value(dict(spec1, complexity_discount=0.2))["flags"]))

# 17) Selftest spec runs end-to-end and is internally consistent.
rs = dcf.value(dcf.SELFTEST_SPEC)
check("selftest EV = pv_fcff + pv_tv",
      approx(rs["enterprise_value"], rs["pv_explicit_fcff"] + rs["pv_terminal_value"], 1e-4))
check("selftest equity = EV - netdebt + cash - minority",
      approx(rs["equity_value"], rs["enterprise_value"] - 500.0 + 100.0 - 0.0, 1e-4))
check("selftest per-share positive", rs["intrinsic_value_per_share"] > 0)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
