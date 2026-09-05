#!/usr/bin/env python3
"""Offline tests for the DCF engine. No network, no yfinance — pure arithmetic checks."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance import paths  # noqa: E402
from finance.compute import dcf  # noqa: E402
from finance.tests.harness import check, rel_approx, summary  # noqa: E402


spec1 = {
    "years": 1, "base_revenue": 1000.0, "revenue_growth": 0.10, "operating_margin": 0.20,
    "tax_rate": 0.25, "sales_to_capital": 2.0, "wacc": 0.10,
    "terminal_growth": 0.04, "terminal_roic": 0.10, "terminal_margin": 0.20,
    "shares_outstanding": 10.0, "net_debt": 0.0,
}
r1 = dcf.value(spec1)
check("y1 fcff = 115", rel_approx(r1["yearly"][0]["fcff"], 115.0), r1["yearly"][0]["fcff"])
check("y1 pv_fcff = 104.5454", rel_approx(r1["pv_explicit_fcff"], 115.0 / 1.1, 1e-4), r1["pv_explicit_fcff"])
check("terminal value = 1716", rel_approx(r1["terminal_value"], 1716.0, 1e-4), r1["terminal_value"])
check("pv terminal = 1560", rel_approx(r1["pv_terminal_value"], 1560.0, 1e-4), r1["pv_terminal_value"])
check("EV = 1664.5454", rel_approx(r1["enterprise_value"], 115.0 / 1.1 + 1560.0, 1e-4), r1["enterprise_value"])
check("equity = EV (no debt)", rel_approx(r1["equity_value"], r1["enterprise_value"]), r1["equity_value"])
check("per share = EV/10", rel_approx(r1["intrinsic_value_per_share"], r1["enterprise_value"] / 10.0, 1e-4),
      r1["intrinsic_value_per_share"])

spec2 = dict(spec1, net_debt=200.0, non_operating_cash=50.0, minority_interest=30.0)
r2 = dcf.value(spec2)
check("equity bridge: EV-200+50-30", rel_approx(r2["equity_value"], r2["enterprise_value"] - 200.0 + 50.0 - 30.0),
      r2["equity_value"])

try:
    dcf.value(dict(spec1, terminal_wacc=0.03, terminal_growth=0.04))
    check("wacc<=g raises", False, "no exception")
except ValueError:
    check("wacc<=g raises", True)

r4 = dcf.value(dict(spec1, current_price=10.0))
check("MoS = intrinsic/price - 1",
      rel_approx(r4["margin_of_safety"], r4["intrinsic_value_per_share"] / 10.0 - 1.0, 1e-6),
      r4["margin_of_safety"])
check("undervalued -> MoS>0 when intrinsic>price",
      (r4["intrinsic_value_per_share"] > 10.0) == (r4["margin_of_safety"] > 0))

g = dcf.resolve_growth({"growth_glide": {"initial": 0.15, "fade_to": 0.04, "years_high": 3}}, 10)
check("glide len 10", len(g) == 10, len(g))
check("glide high years = 0.15", g[0] == 0.15 and g[1] == 0.15 and g[2] == 0.15, g[:3])
check("glide fades immediately after exactly years_high years", g[3] < 0.15, g[:5])
check("glide ends at 0.04", rel_approx(g[-1], 0.04), g[-1])
check("glide monotone non-increasing after high", all(g[i] >= g[i + 1] - 1e-9 for i in range(2, 9)), g)

m = dcf.resolve_margin({"margin_glide": {"start": 0.12, "target": 0.18, "year_target": 5}}, 10)
check("margin start 0.12", rel_approx(m[0], 0.12), m[0])
check("margin hits target by y5", rel_approx(m[4], 0.18), m[4])
check("margin holds target after y5", all(rel_approx(x, 0.18) for x in m[5:]), m[5:])

p = dcf._as_path([0.11, 0.10], 5, 0.11)
check("path carries last fwd", p == [0.11, 0.10, 0.10, 0.10, 0.10], p)
check("scalar path expands", dcf._as_path(0.09, 3, 0.11) == [0.09, 0.09, 0.09])

specw = dict(spec1, years=2, revenue_growth=[0.10, 0.10], operating_margin=0.20,
             wacc=[0.12, 0.10], sales_to_capital=2.0)
rw = dcf.value(specw)
check("cum discount y2 = 1.12*1.10", rel_approx(rw["yearly"][1]["discount_factor"], 1.12 * 1.10, 1e-9),
      rw["yearly"][1]["discount_factor"])

base = dcf.value(spec1)["intrinsic_value_per_share"]
hi_wacc = dcf.value(dict(spec1, wacc=0.13, terminal_wacc=0.13))["intrinsic_value_per_share"]
hi_g = dcf.value(dict(spec1, terminal_growth=0.05))["intrinsic_value_per_share"]
check("higher WACC -> lower value", hi_wacc < base, (hi_wacc, base))
check("higher terminal g -> higher value", hi_g > base, (hi_g, base))

fr_spec = {
    "years": 5, "base_revenue": 1000.0, "revenue_growth": 0.35, "operating_margin": 0.45,
    "tax_rate": 0.25, "sales_to_capital": 2.0, "wacc": 0.11,
    "terminal_growth": 0.08, "terminal_roic": 0.10, "risk_free": 0.07,
    "shares_outstanding": 10.0,
}
try:
    dcf.value(fr_spec)
    check("terminal growth > risk free raises", False)
except ValueError as e:
    check("terminal growth > risk free raises", "risk-free" in str(e).lower(), str(e))
fr = dcf.value(dict(fr_spec, terminal_growth=0.07))
flags = " ".join(fr["flags"])
check("flag: high margin", "HIGH_MARGIN_ASSUMPTION" in flags)
check("flag: high growth", "HIGH_GROWTH_ASSUMPTION" in flags)

heavy = dcf.value({
    "years": 10, "base_revenue": 1000.0, "growth_glide": {"initial": 0.08, "fade_to": 0.05, "years_high": 3},
    "margin_glide": {"start": 0.10, "target": 0.12, "year_target": 5},
    "tax_rate": 0.25, "sales_to_capital": 4.0, "wacc": 0.09,
    "terminal_growth": 0.07, "terminal_roic": 0.11, "terminal_wacc": 0.08, "shares_outstanding": 10.0,
})
check("flag: terminal value heavy", any("TERMINAL_VALUE_HEAVY" in f for f in heavy["flags"]), heavy["flags"])
check("terminal-heavy EV positive", heavy["enterprise_value"] > 0, heavy["enterprise_value"])

neg = dcf.value({
    "years": 10, "base_revenue": 1000.0, "growth_glide": {"initial": 0.20, "fade_to": 0.04, "years_high": 5},
    "margin_glide": {"start": 0.02, "target": 0.10, "year_target": 10},
    "tax_rate": 0.25, "sales_to_capital": 1.0, "wacc": 0.11,
    "terminal_growth": 0.05, "terminal_roic": 0.12, "shares_outstanding": 10.0,
})
check("flag: negative enterprise value", any("NEGATIVE_ENTERPRISE_VALUE" in f for f in neg["flags"]), neg["flags"])

ner = dcf.value(dict(spec1, terminal_roic=0.10, terminal_wacc=0.10, wacc=0.11))
check("flag: no terminal excess return", any("NO_TERMINAL_EXCESS_RETURN" in f for f in ner["flags"]), ner["flags"])

flat = dcf.value({"years": 1, "base_revenue": 1000.0, "revenue_growth": 0.0,
                  "operating_margin": 0.20, "tax_rate": 0.25, "sales_to_capital": 2.0,
                  "wacc": 0.10, "terminal_growth": 0.0, "terminal_roic": 0.10,
                  "shares_outstanding": 10.0})
check("flat year: reinvest 0", rel_approx(flat["yearly"][0]["reinvestment"], 0.0), flat["yearly"][0]["reinvestment"])
check("flat year: fcff == nopat", rel_approx(flat["yearly"][0]["fcff"], flat["yearly"][0]["nopat"]))

tvf = base
rfull = dcf.value(spec1)
check("tv fraction = pv_tv/EV",
      rel_approx(rfull["terminal_value_fraction"], rfull["pv_terminal_value"] / rfull["enterprise_value"], 1e-6),
      rfull["terminal_value_fraction"])

sens = dcf.sensitivity(spec1)
center = sens["cells"][2][2]
check("sensitivity center == base", rel_approx(center, round(base, 2), 1e-2), (center, base))
check("sensitivity grid 5x5", len(sens["cells"]) == 5 and all(len(r) == 5 for r in sens["cells"]))
check("sensitivity is explicitly labelled terminal-only",
      sens["scope"] == "terminal_only" and sens["wacc_axis_label"] == "terminal WACC", sens)

try:
    dcf.value(dict(spec1, shares_outstanding=0))
    check("zero shares raises", False)
except ValueError:
    check("zero shares raises", True)

for lever in ("tax_rate", "sales_to_capital", "terminal_growth"):
    bare = {k: v for k, v in spec1.items() if k != lever}
    try:
        dcf.value(bare)
        check(f"missing {lever} raises", False, "no exception")
    except ValueError as e:
        check(f"missing {lever} raises and names it", lever in str(e), str(e))

nowacc = {k: v for k, v in spec1.items() if k != "wacc"}
try:
    dcf.value(nowacc)
    check("missing wacc AND wacc_buildup raises", False, "no exception")
except ValueError as e:
    check("missing discount rate raises and names wacc", "wacc" in str(e).lower(), str(e))
check("wacc_buildup alone satisfies the discount-rate requirement",
      dcf.value(dict(nowacc, wacc_buildup={"risk_free": 0.07,
                                           "risk_free_is_default_free": True,
                                           "mature_erp": 0.05,
                                           "tax_rate": 0.25}))["intrinsic_value_per_share"] > 0)

india_buildup = {
    "government_bond_yield": 0.068,
    "sovereign_default_spread": 0.0195,
    "beta": 1.05,
    "mature_erp": 0.0508,
    "country_risk_premium": 0.0219,
    "cost_of_debt_pretax": 0.09,
    "equity_weight": 0.96,
    "tax_rate": 0.25,
}
india = dcf.value(dict(spec1, wacc=None, wacc_buildup=india_buildup,
                       lifecycle_stage="high_growth", years=5,
                       revenue_growth=[0.10] * 5, operating_margin=[0.20] * 5,
                       terminal_growth=0.04, terminal_wacc=0.105))
india_detail = india["assumptions"]["wacc_buildup"]
check("sovereign spread is removed from the local government yield",
      rel_approx(india_detail["default_free_risk_free"], 0.0485, 1e-9), india_detail)
check("country risk is then added exactly once in cost of equity",
      rel_approx(india_detail["cost_of_equity"], 0.0485 + 1.05 * 0.0508 + 0.0219, 1e-9),
      india_detail)
check("high-growth WACC converges toward the terminal discount rate",
      india["assumptions"]["wacc_path"][0] > india["assumptions"]["wacc_path"][-1] and
      rel_approx(india["assumptions"]["wacc_path"][-1], 0.105, 1e-9),
      india["assumptions"]["wacc_path"])

try:
    dcf.value(dict(spec1, wacc=None, wacc_buildup={
        "risk_free": 0.068, "mature_erp": 0.0508,
        "country_risk_premium": 0.0219, "tax_rate": 0.25,
    }))
    check("country-risk buildup rejects an unconfirmed risk-free basis", False)
except ValueError as e:
    check("country-risk buildup rejects an unconfirmed risk-free basis",
          "default-free" in str(e).lower(), str(e))

try:
    dcf.value(dict(spec1, wacc=None, wacc_buildup=india_buildup,
                   terminal_growth=0.05))
    check("terminal growth above default-free rupee rate is rejected", False)
except ValueError as e:
    check("terminal growth above default-free rupee rate is rejected",
          "terminal growth" in str(e).lower() and "risk-free" in str(e).lower(), str(e))

try:
    dcf.value(dict(nowacc, tax_rate=[0.25] * spec1["years"],
                   wacc_buildup={"risk_free": 0.07, "mature_erp": 0.05}))
    check("buildup with a per-year tax path and no scalar tax raises", False, "no exception")
except ValueError as e:
    check("buildup needs a scalar tax rate for the debt shield", "scalar" in str(e).lower(), str(e))

adig = dcf.run("INFY", spec1)["data"]["assumptions"]
check("run: assumptions carry the resolved wacc path", adig["wacc_path"][0] == 0.10, adig)
check("run: assumptions carry the resolved tax path", adig["tax_path"][0] == 0.25, adig)
check("run: assumptions carry sales-to-capital", adig["sales_to_capital_path"][0] == 2.0, adig)
check("run: assumptions carry terminal growth", adig["terminal_growth"] == 0.04, adig)

rspec = {
    "years": 10, "base_revenue": 1000.0,
    "growth_glide": {"initial": 0.12, "fade_to": 0.05, "years_high": 3},
    "margin_glide": {"start": 0.15, "target": 0.18, "year_target": 5},
    "tax_rate": 0.25, "sales_to_capital": 2.5, "wacc": 0.11,
    "terminal_growth": 0.05, "terminal_roic": 0.14, "shares_outstanding": 100.0, "net_debt": 0.0,
}
base_intrinsic = dcf.value(rspec)["intrinsic_value_per_share"]

rt = dcf.reverse_dcf(rspec, target_per_share=base_intrinsic, solve="growth")
check("reverse: target=base intrinsic -> ~0 shift", rt["solved"] and abs(rt["shift"]) < 1e-3,
      rt.get("shift", rt))

hi_target = base_intrinsic * 1.5
rh = dcf.reverse_dcf(rspec, target_per_share=hi_target, solve="growth")
check("reverse: higher price -> positive growth shift", rh["solved"] and rh["shift"] > 0, rh)
if rh["solved"]:
    repriced = dcf.value(dict(rspec, growth_glide=None, revenue_growth=rh["implied_path"]))["intrinsic_value_per_share"]
    check("reverse: solved growth reprices to target", rel_approx(repriced, hi_target, 1e-3), (repriced, hi_target))
    check("reverse: reports implied revenue CAGR", "implied_revenue_cagr" in rh, list(rh.keys()))

lo_target = base_intrinsic * 0.6
rl = dcf.reverse_dcf(rspec, target_per_share=lo_target, solve="growth")
check("reverse: lower price -> negative growth shift", rl["solved"] and rl["shift"] < 0, rl)

ru = dcf.reverse_dcf(rspec, target_per_share=base_intrinsic * 50, solve="growth")
check("reverse: unreachable target -> solved False with reason",
      (not ru["solved"]) and "reason" in ru, ru)

rp = dcf.reverse_dcf(dict(rspec, current_price=base_intrinsic), solve="growth")
check("reverse: defaults to current_price", rp["solved"] and abs(rp["shift"]) < 1e-3, rp.get("shift", rp))

try:
    dcf.reverse_dcf(rspec, solve="growth")
    check("reverse: no target raises", False)
except ValueError:
    check("reverse: no target raises", True)

rm = dcf.reverse_dcf(rspec, target_per_share=base_intrinsic * 1.3, solve="margin")
check("reverse: margin solve brackets", rm["solved"], rm)
if rm["solved"]:
    repm = dcf.value(dict(rspec, margin_glide=None, operating_margin=rm["implied_path"]))["intrinsic_value_per_share"]
    check("reverse: solved margin reprices to target", rel_approx(repm, base_intrinsic * 1.3, 1e-3), (repm,))

fp = dcf.value(dict(spec1, failure_probability=0.10))
check("failure haircut: equity = going_concern*(1-p)",
      rel_approx(fp["equity_value"], fp["equity_value_going_concern"] * 0.90, 1e-6),
      (fp["equity_value"], fp["equity_value_going_concern"]))
check("failure haircut: per-share below going concern",
      fp["intrinsic_value_per_share"] < dcf.value(spec1)["intrinsic_value_per_share"])
fpr = dcf.value(dict(spec1, failure_probability=0.20, failure_recovery=0.5))
check("failure recovery: equity = gc*((1-p)+rec*p)",
      rel_approx(fpr["equity_value"], fpr["equity_value_going_concern"] * (0.80 + 0.5 * 0.20), 1e-6),
      fpr["equity_value"])
try:
    dcf.value(dict(spec1, failure_probability=1.5))
    check("failure_probability>1 raises", False)
except ValueError:
    check("failure_probability>1 raises", True)

wb = {"risk_free": 0.07, "risk_free_is_default_free": True,
      "beta": 1.1, "mature_erp": 0.045, "country_risk_premium": 0.03,
      "cost_of_debt_pretax": 0.09, "equity_weight": 0.95, "tax_rate": 0.25}
rwb = dcf.value(dict(spec1, wacc=None, wacc_buildup=wb))
det = rwb["assumptions"]["wacc_buildup"]
coe_full = 0.07 + 1.1 * 0.045 + 1.0 * 0.03
check("wacc buildup: melded CoE = rf+beta*mature_erp+lambda*crp", rel_approx(det["cost_of_equity"], coe_full, 1e-9), det)
exp_wacc = 0.95 * coe_full + 0.05 * 0.09 * 0.75
check("wacc buildup: weighted wacc", rel_approx(det["wacc"], exp_wacc, 1e-9), (det["wacc"], exp_wacc))
check("wacc buildup: applied to discounting", rel_approx(rwb["assumptions"]["wacc_path"][0], exp_wacc, 1e-6))
check("explicit wacc overrides buildup",
      rel_approx(dcf.value(dict(spec1, wacc=0.12, wacc_buildup=wb))["assumptions"]["wacc_path"][0], 0.12, 1e-9))
exporter = dcf.value(dict(spec1, wacc=None, wacc_buildup=dict(wb, lambda_country=0.1)))
check("low lambda (exporter) lowers cost of equity",
      exporter["assumptions"]["wacc_buildup"]["cost_of_equity"] < det["cost_of_equity"],
      (exporter["assumptions"]["wacc_buildup"]["cost_of_equity"], det["cost_of_equity"]))
check("lambda reported", rel_approx(exporter["assumptions"]["wacc_buildup"]["lambda_country"], 0.1, 1e-9))

hibeta = dcf.value(dict(spec1, wacc=None, wacc_buildup=dict(wb, beta=1.5)))
check("beta reported in wacc detail", rel_approx(hibeta["assumptions"]["wacc_buildup"]["beta"], 1.5, 1e-9))
check("flag: high beta looks like regression",
      any("BETA_LOOKS_LIKE_REGRESSION" in f for f in hibeta["flags"]), hibeta["flags"])
check("no beta flag for a bottom-up-range beta (1.1)",
      not any("BETA_LOOKS_LIKE_REGRESSION" in f for f in rwb["flags"]))

noroic = dict(spec1)
noroic.pop("terminal_roic", None)
rnr = dcf.value(noroic)
check("terminal_roic defaults to terminal_wacc (convergence)",
      rel_approx(rnr["assumptions"]["terminal_roic"], rnr["assumptions"]["terminal_wacc"], 1e-9),
      (rnr["assumptions"]["terminal_roic"], rnr["assumptions"]["terminal_wacc"]))
check("terminal_excess_return = roic - wacc",
      rel_approx(rnr["assumptions"]["terminal_excess_return"],
             rnr["assumptions"]["terminal_roic"] - rnr["assumptions"]["terminal_wacc"], 1e-9))
check("convergence default -> NO_TERMINAL_EXCESS_RETURN",
      any("NO_TERMINAL_EXCESS_RETURN" in f for f in rnr["flags"]))

ss = dcf.story_sensitivity(rspec)
center_ss = ss["cells"][2][1]
check("story grid: center == base intrinsic", rel_approx(center_ss, round(base_intrinsic, 2), 1e-2),
      (center_ss, base_intrinsic))
check("story grid: higher growth -> higher value", ss["cells"][4][1] > ss["cells"][0][1],
      (ss["cells"][4][1], ss["cells"][0][1]))
check("story grid: higher margin -> higher value", ss["cells"][2][2] > ss["cells"][2][0])
check("story grid: duration read present for a glide spec", "duration" in ss and len(ss["duration"]) == 3)
check("story grid: more high-growth years -> higher value",
      ss["duration"][2]["per_share"] > ss["duration"][0]["per_share"], ss["duration"])
story_flat = [c for row in ss["cells"] for c in row if c is not None]
wacc_g = dcf.sensitivity(rspec)
wg_flat = [c for row in wacc_g["cells"] for c in row if c is not None]
check("story range wider than WACC×g range",
      (max(story_flat) - min(story_flat)) > (max(wg_flat) - min(wg_flat)),
      (max(story_flat) - min(story_flat), max(wg_flat) - min(wg_flat)))

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

cxr = dcf.value(dict(spec1, complexity_discount=0.20))
check("complexity discount: equity = going_concern*(1-cx)",
      rel_approx(cxr["equity_value"], cxr["equity_value_going_concern"] * 0.80, 1e-6),
      (cxr["equity_value"], cxr["equity_value_going_concern"]))
cxf = dcf.value(dict(spec1, failure_probability=0.10, complexity_discount=0.20))
check("failure and complexity compose multiplicatively",
      rel_approx(cxf["equity_value"], cxf["equity_value_going_concern"] * 0.90 * 0.80, 1e-6), cxf["equity_value"])
try:
    dcf.value(dict(spec1, complexity_discount=1.0))
    check("complexity_discount>=1 raises", False)
except ValueError:
    check("complexity_discount>=1 raises", True)

decl = dcf.value({
    "years": 5, "base_revenue": 1000.0, "lifecycle_stage": "decline",
    "growth_glide": {"initial": -0.05, "fade_to": -0.02, "years_high": 2},
    "margin_glide": {"start": 0.10, "target": 0.08, "year_target": 5},
    "tax_rate": 0.25, "sales_to_capital": 4.0, "wacc": 0.12,
    "terminal_growth": 0.03, "terminal_roic": 0.13, "terminal_wacc": 0.12, "shares_outstanding": 10.0,
})
check("decline + positive terminal growth flagged",
      any("DECLINE_POSITIVE_TERMINAL_GROWTH" in f for f in decl["flags"]), decl["flags"])

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

rs = dcf.value(dcf.SELFTEST_SPEC)
check("selftest EV = pv_fcff + pv_tv",
      rel_approx(rs["enterprise_value"], rs["pv_explicit_fcff"] + rs["pv_terminal_value"], 1e-4))
check("selftest equity = EV - netdebt + cash - minority",
      rel_approx(rs["equity_value"], rs["enterprise_value"] - 500.0 + 100.0 - 0.0, 1e-4))
check("selftest per-share positive", rs["intrinsic_value_per_share"] > 0)

os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = os.path.join(tempfile.mkdtemp(), "artifacts")
env = dcf.run("reliance", dcf.SELFTEST_SPEC, story=True,
              relative={"pe": 18.0, "peer_pe": [28, 24, 30, 22],
                        "own_pe_history": [20, 25, 28, 30, 32],
                        "growth": {"value": 22, "basis": "5y EPS CAGR"}})
d = env["data"]
check("run: envelope carries the contract keys",
      {"ok", "source", "fetched_at", "data", "gaps"} <= set(env), sorted(env))
check("run: source names the computation, not a website",
      env["source"] == "finance.compute.dcf", env["source"])
check("run: ok with no gaps", env["ok"] and env["gaps"] == [], env["gaps"])
check("run: ticker normalised to the NSE key", d["ticker"] == "RELIANCE", d["ticker"])
check("run: headline per-share is value()'s",
      d["intrinsic_value_per_share"] == rs["intrinsic_value_per_share"], d)
check("run: relative half rides along",
      d["relative"]["relative_stance"] == "undervalued", d["relative"])
check("run: peer median is the median, not the mean", d["relative"]["peer_median_pe"] == 26.0,
      d["relative"])
check("run: story range brackets the base value",
      d["story_range"][0] <= d["intrinsic_value_per_share"] <= d["story_range"][1],
      d["story_range"])
check("run: the year-by-year rows stay out of the response", "yearly" not in d, sorted(d))
check("run: dcf_path names dcf.json under the ticker",
      d["dcf_path"].endswith("dcf.json") and "RELIANCE" in d["dcf_path"], d["dcf_path"])
check("run: the spilled file is the complete result",
      json.load(open(d["dcf_path"]))["yearly"][0]["fcff"] == rs["yearly"][0]["fcff"])
check("run: the spill lands where latest_prior looks",
      os.path.dirname(d["dcf_path"]) == paths.stock_dir("RELIANCE"), d["dcf_path"])

solo = dcf.run("INFY", spec1)
check("run: no peer figures still values the stock",
      solo["ok"] and solo["data"]["relative"] is None, solo["data"])
check("run: a non-mapping `relative` degrades to a gap, keeping the DCF",
      dcf.run("INFY", spec1, relative=[1, 2])["gaps"] != [])

bad = dcf.run("INFY", {"base_revenue": 100.0})
check("run: an incomplete input set is ok:false", bad["ok"] is False, bad)
check("run: the rejection is labelled", any("rejected" in g for g in bad["gaps"]), bad["gaps"])
check("run: terminal wacc <= g is a gap, not a raise",
      dcf.run("INFY", dict(spec1, terminal_growth=0.5))["ok"] is False)
check("run: missing inputs are a gap, not a traceback",
      dcf.run("INFY", None)["ok"] is False and dcf.run("INFY", {})["ok"] is False)

def _codes(spec, **kw):
    kw.setdefault("margin", [1.0])
    kw.setdefault("growth", [0.10])
    return [f.split(":")[0] for f in dcf._sanity_flags(
        spec, 0.05, 0.12, 0.15, 100.0, 50.0, 50.0, 0.065, kw["growth"], kw["margin"])]

_fcff = _codes({})
check("fcff shape still runs the margin-basis check", "MARGIN_BASIS_UNCHECKED" in _fcff, _fcff)
check("fcff shape still flags a 100% margin", "HIGH_MARGIN_ASSUMPTION" in _fcff, _fcff)

_eq = _codes({"model_shape": "equity"})
check("equity shape declares itself", "EQUITY_MODEL_SHAPE" in _eq, _eq)
check("equity shape suppresses the margin-basis check",
      "MARGIN_BASIS_UNCHECKED" not in _eq, _eq)
check("equity shape suppresses the high-margin flag",
      "HIGH_MARGIN_ASSUMPTION" not in _eq, _eq)
check("equity shape keeps the checks that still apply",
      _codes({"model_shape": "equity"}, growth=[0.60]) and
      "HIGH_GROWTH_ASSUMPTION" in _codes({"model_shape": "equity"}, growth=[0.60]),
      _codes({"model_shape": "equity"}, growth=[0.60]))
check("an unknown model_shape falls back to fcff, never silently skips checks",
      "MARGIN_BASIS_UNCHECKED" in _codes({"model_shape": "nonsense"}), _codes({"model_shape": "nonsense"}))
check("model_shape is case- and space-insensitive",
      "EQUITY_MODEL_SHAPE" in _codes({"model_shape": " Equity "}), _codes({"model_shape": " Equity "}))

try:
    dcf.value(dict(spec1, model_shape="nonsense"))
    check("value rejects an unknown model shape", False)
except ValueError as e:
    check("value rejects an unknown model shape", "model_shape" in str(e), str(e))

try:
    dcf.value(dict(spec1, operating_margin=1.0, tax_rate=0.0))
    check("fcff run rejects inputs that are visibly equity-shaped", False)
except ValueError as e:
    check("fcff run rejects inputs that are visibly equity-shaped",
          "model_shape: equity" in str(e), str(e))

equity_spec = dict(spec1, model_shape="equity", operating_margin=1.0, tax_rate=0.0,
                   wacc=0.12, terminal_wacc=0.12, terminal_roic=0.14)
check("declared equity-shaped model remains valid",
      dcf.value(equity_spec)["assumptions"]["model_shape"] == "equity")

summary()
