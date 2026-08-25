#!/usr/bin/env python3
"""Offline unit tests for the insurance math. No network — deterministic inputs."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import insurance_math as im  # noqa: E402
from finance.tests.harness import approx, check, run  # noqa: E402


def test_term_income_replacement_wins():
    r = im.term_cover_need(20_00_000, income_multiple=12)
    check("income_replacement = 12x", approx(r.income_replacement, 2_40_00_000, tol=1.0))
    check("need takes the larger", r.need == r.income_replacement)
    check("method is income_replacement", r.method == "income_replacement")


def test_term_liability_goals_wins():
    r = im.term_cover_need(
        10_00_000, income_multiple=10,
        outstanding_loans=80_00_000, education_corpus=1_00_00_000,
        annual_expenses=5_00_000, years_to_independence=15,
        existing_corpus=20_00_000,
    )
    check("liability_goals computed", approx(r.liability_goals, 2_35_00_000, tol=1.0))
    check("need takes liability_goals", r.need == r.liability_goals)
    check("method is liability_goals", r.method == "liability_goals")


def test_term_gap_and_defaults():
    r = im.term_cover_need(10_00_000, income_multiple=15, existing_cover=50_00_000)
    check("need = 1.5Cr", approx(r.need, 1_50_00_000, tol=1.0))
    check("gap nets existing cover", approx(r.gap, 1_00_00_000, tol=1.0))
    r2 = im.term_cover_need(10_00_000, income_multiple=1, years_to_independence=10)
    check("annual_expenses defaults to 45%",
          approx(r2.breakdown["annual_expenses"], 4_50_000, tol=1.0))
    check("gap never negative", im.term_cover_need(0).gap == 0)


def test_health_single_metro():
    r = im.health_sum_insured(adults=1, eldest_age=30, city_tier=1)
    check("single metro base = 10L", approx(r.base_recommended, 10_00_000, tol=1.0))


def test_health_family_floater_and_employer_weight():
    r = im.health_sum_insured(
        adults=2, children=2, eldest_age=40, city_tier=1,
        personal_cover=5_00_000, employer_cover=10_00_000,
    )
    check("floater base lifted", approx(r.base_recommended, 15_00_000, tol=1.0))
    check("employer weighted at half", approx(r.effective_existing, 10_00_000, tol=1.0))
    check("gap = base - effective", approx(r.gap, 5_00_000, tol=1.0))


def test_health_older_and_seniors():
    r = im.health_sum_insured(adults=2, eldest_age=50, city_tier=1, has_senior_parents=True)
    check("older + seniors lift base to 25L", approx(r.base_recommended, 25_00_000, tol=1.0))


def test_idv_in_band():
    r = im.idv_ncb_sanity(ex_showroom=10_00_000, age_years=3, quoted_idv=7_00_000, claim_free_years=3, quoted_ncb=0.35)
    check("mid-band IDV ok", r.idv_ok)
    check("expected NCB 35% for 3 claim-free yrs", approx(r.expected_ncb, 0.35, tol=1e-6))
    check("no flags on clean quote", r.flags == [])


def test_idv_below_band_flags():
    r = im.idv_ncb_sanity(ex_showroom=10_00_000, age_years=3, quoted_idv=4_00_000)
    check("low IDV not ok", not r.idv_ok)
    check("under-insured flag raised", any("below" in f for f in r.flags))


def test_ncb_overstated_flags():
    r = im.idv_ncb_sanity(ex_showroom=10_00_000, age_years=1, quoted_idv=8_50_000, claim_free_years=1, quoted_ncb=0.50)
    check("expected NCB 20% for 1 yr", approx(r.expected_ncb, 0.20, tol=1e-6))
    check("overstated NCB flagged", any("NCB" in f for f in r.flags))


def test_expected_ncb_slab():
    check("0 yrs -> 0%", im.expected_ncb(0) == 0.0)
    check("2 yrs -> 25%", approx(im.expected_ncb(2), 0.25, tol=1e-6))
    check("6 yrs caps at 50%", approx(im.expected_ncb(6), 0.50, tol=1e-6))


def test_marginal_irr_known_series():
    r = im.irr([-100, 0, 121])
    check("irr of simple series ~10%", approx(r, 0.10, tol=1e-4))


def test_marginal_irr_continue_poor_policy():
    d = im.marginal_irr_continue(
        surrender_value=5_00_000, annual_premium=1_00_000,
        remaining_premiums=5, years_to_maturity=10, maturity_value=12_00_000,
        hurdle_rate=0.07,
    )
    check("marginal IRR solved", d.marginal_irr is not None)
    check("poor policy below 7% hurdle", d.beats_hurdle is False)
    check("t0 outflow is SV + first premium", d.cashflows[0] == -6_00_000)


def test_marginal_irr_continue_worth_keeping():
    d = im.marginal_irr_continue(
        surrender_value=1_00_000, annual_premium=50_000,
        remaining_premiums=2, years_to_maturity=5, maturity_value=6_00_000,
        hurdle_rate=0.07,
    )
    check("worth-keeping policy beats hurdle", d.beats_hurdle is True)


def test_marginal_irr_validates_inputs():
    try:
        im.marginal_irr_continue(
            surrender_value=1, annual_premium=1,
            remaining_premiums=10, years_to_maturity=5, maturity_value=1,
        )
        check("rejects remaining > maturity", False)
    except ValueError:
        check("rejects remaining > maturity", True)


def test_run_envelope_shape():
    env = im.run("term_cover_need", {"annual_income": 20_00_000, "income_multiple": 12})
    check("envelope carries the contract keys",
          {"ok", "source", "fetched_at", "data", "gaps"} <= set(env), sorted(env))
    check("run reports ok with no gaps", env["ok"] and env["gaps"] == [], env["gaps"])
    check("source names the computation",
          env["source"] == "finance.compute.insurance_math", env["source"])
    check("a dataclass result comes back as a mapping",
          approx(env["data"]["result"]["need"], 2_40_00_000, tol=1.0), env["data"])


def test_run_scalar_result_passes_through():
    env = im.run("expected_ncb", {"claim_free_years": 3})
    check("scalar result is the value itself",
          approx(env["data"]["result"], 0.35, tol=1e-6), env["data"])


def test_run_unknown_calculation_is_a_gap():
    env = im.run("guess_the_premium", {})
    check("unknown calculation is not ok", env["ok"] is False)
    check("unknown calculation is labelled",
          any("unknown calculation" in g for g in env["gaps"]), env["gaps"])


def test_run_bad_inputs_are_a_gap_not_an_exception():
    tier = im.run("health_sum_insured", {"adults": 1, "eldest_age": 30, "city_tier": 9})
    check("a rejected value is not ok", tier["ok"] is False)
    check("a rejected value is labelled", any("city_tier" in g for g in tier["gaps"]),
          tier["gaps"])
    missing = im.run("idv_ncb_sanity", {"ex_showroom": 10_00_000})
    check("a missing keyword is a gap, not a TypeError", missing["ok"] is False, missing)


def test_health_sum_insured_needs_the_household_inputs():
    env = im.run("health_sum_insured", {})
    check("all-defaults health call is not ok", env["ok"] is False, env)
    check("the gap names a missing required input",
          any("adults" in g or "city_tier" in g or "eldest_age" in g for g in env["gaps"]),
          env["gaps"])
    check("no result is fabricated from defaults", env["data"].get("result") is None, env["data"])
    ok = im.run("health_sum_insured", {"adults": 1, "eldest_age": 30, "city_tier": 1})
    check("supplying the household inputs solves it", ok["ok"] is True, ok["gaps"])


def test_run_unsolvable_result_is_not_ok():
    env = im.run("irr", {"cashflows": [100, 100, 100]})
    check("an unbracketed IRR returns no result", env["data"]["result"] is None, env["data"])
    check("no result is ok:false with a gap", env["ok"] is False and bool(env["gaps"]),
          env["gaps"])


if __name__ == "__main__":
    run(globals())
