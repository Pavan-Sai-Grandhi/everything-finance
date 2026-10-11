#!/usr/bin/env python3
"""Offline unit tests for the insurance math. No network — deterministic inputs."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import insurance_math as im  # noqa: E402
from finance.tests.harness import approx, check, run  # noqa: E402


def term_inputs(**overrides):
    """Complete synthetic household; explicit zeros mean confirmed absence in this fixture."""
    return dict(dict(annual_income=100, income_multiple=12, outstanding_loans=0,
                     education_corpus=0, annual_expenses=0, years_to_independence=0,
                     existing_corpus=0, existing_cover=0), **overrides)


def test_term_income_replacement_wins():
    r = im.term_cover_need(**term_inputs(annual_income=20_00_000, income_multiple=12))
    check("income_replacement = 12x", approx(r.income_replacement, 2_40_00_000, tol=1.0))
    check("need takes the larger", r.need == r.income_replacement)
    check("method is income_replacement", r.method == "income_replacement")


def test_term_liability_goals_wins():
    r = im.term_cover_need(
        10_00_000, income_multiple=10,
        outstanding_loans=80_00_000, education_corpus=1_00_00_000,
        annual_expenses=5_00_000, years_to_independence=15,
        existing_corpus=20_00_000, existing_cover=0,
    )
    check("liability_goals computed", approx(r.liability_goals, 2_35_00_000, tol=1.0))
    check("need takes liability_goals", r.need == r.liability_goals)
    check("method is liability_goals", r.method == "liability_goals")


def test_term_gap_and_explicit_amounts():
    r = im.term_cover_need(**term_inputs(annual_income=10_00_000, income_multiple=15, existing_cover=50_00_000))
    check("need = 1.5Cr", approx(r.need, 1_50_00_000, tol=1.0))
    check("gap nets existing cover", approx(r.gap, 1_00_00_000, tol=1.0))
    r2 = im.term_cover_need(**term_inputs(annual_income=10_00_000, income_multiple=1, years_to_independence=10,
                            annual_expenses=4_50_000))
    check("annual_expenses preserves the supplied figure",
          approx(r2.breakdown["annual_expenses"], 4_50_000, tol=1.0))
    check("gap never negative", im.term_cover_need(**term_inputs(annual_income=0)).gap == 0)


def test_health_gaps_floor_at_zero():
    r = im.health_sum_insured(base_target=1000000, total_target=5000000,
                             deductible=1000000, personal_cover=1500000, employer_cover=0)
    check("excess personal cover cannot produce negative gaps",
          r.base_gap == r.deductible_gap == r.planned_deductible_gap == 0)
    check("personal and employer amounts remain separate", r.personal_cover == 1500000 and r.employer_cover == 0)


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
    env = im.run("term_cover_need", term_inputs(annual_income=20_00_000, income_multiple=12))
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
    tier = im.run("health_sum_insured", {"base_target": -1, "total_target": 100,
                  "deductible": 10, "personal_cover": 0, "employer_cover": 0})
    check("a rejected value is not ok", tier["ok"] is False)
    check("a rejected value is labelled", any("base_target" in g for g in tier["gaps"]),
          tier["gaps"])
    missing = im.run("idv_ncb_sanity", {"ex_showroom": 10_00_000})
    check("a missing keyword is a gap, not a TypeError", missing["ok"] is False, missing)


def test_health_sum_insured_requires_explicit_scenario():
    env = im.run("health_sum_insured", {})
    check("health sizing without targets is a labelled gap", not env["ok"] and bool(env["gaps"]), env)
    for invalid in ({"total_target": 1}, {"deductible": 6000000}, {"personal_cover": None},
                    {"base_target": True}, {"employer_cover": float("inf")}):
        inputs = dict(base_target=1000000, total_target=5000000, deductible=1000000,
                      personal_cover=0, employer_cover=0)
        env = im.run("health_sum_insured", dict(inputs, **invalid))
        check("invalid or unknown health scenario inputs cannot produce a result",
              not env["ok"] and bool(env["gaps"]), env)


def test_run_unsolvable_result_is_not_ok():
    env = im.run("irr", {"cashflows": [100, 100, 100]})
    check("an unbracketed IRR returns no result", env["data"]["result"] is None, env["data"])
    check("no result is ok:false with a gap", env["ok"] is False and bool(env["gaps"]),
          env["gaps"])



def test_irr_requires_meaningful_finite_cashflows():
    for cashflows in ([], [0], [0, 0], [100], [-100]):
        env = im.run("irr", {"cashflows": cashflows})
        check("degenerate cashflows cannot produce an IRR", not env["ok"] and bool(env["gaps"]), env)
    for inputs in ({"cashflows": [-100, float("nan")]},
                   {"cashflows": [-100, float("inf")]},
                   {"cashflows": [False, 100]},
                   {"cashflows": [-100, 110], "lo": -1},
                   {"cashflows": [-100, 110], "lo": 1, "hi": 0},
                   {"cashflows": [-100, 110], "tol": 0}):
        try:
            env = im.run("irr", inputs)
            check("invalid IRR inputs return a labelled gap", not env["ok"] and bool(env["gaps"]), env)
        except Exception as exc:
            check("invalid IRR inputs return a labelled gap", False, str(exc))



def test_irr_is_stable_across_scale_and_long_horizons():
    for flows, expected in (([0, -100, 90, 0], -0.1),
                            ([100, -110], 0.1),
                            ([-1e-15, 1.1e-15], 0.1),
                            ([-1e300, 1.1e300], 0.1),
                            ([-100] + [0] * 399 + [200], 2 ** (1 / 400) - 1)):
        env = im.run("irr", {"cashflows": flows})
        actual = env.get("data", {}).get("result")
        check("IRR is independent of currency scale and survives long horizons",
              env["ok"] and approx(actual, expected, tol=1e-6), env)


def test_irr_does_not_choose_between_multiple_roots():
    # This polynomial has IRRs at 10% and 20%; a narrow bracket must not conceal that.
    result = im.run("irr", {"cashflows": [-100, 230, -132], "lo": 0.09, "hi": 0.15})
    check("nonconventional cashflows cannot yield an arbitrary single IRR",
          not result["ok"] and bool(result["gaps"]), result)



def test_insurance_inputs_cannot_be_silently_repaired():
    cases = [
        ("term_cover_need", term_inputs(), {"existing_cover": -1}),
        ("term_cover_need", term_inputs(), {"annual_expenses": float("nan")}),
        ("term_cover_need", term_inputs(), {"years_to_independence": True}),
        ("idv_ncb_sanity", {"ex_showroom": 100, "age_years": 1, "quoted_idv": 85}, {"quoted_ncb": -0.1}),
        ("idv_ncb_sanity", {"ex_showroom": 100, "age_years": 1, "quoted_idv": 85}, {"age_years": -1}),
        ("idv_ncb_sanity", {"ex_showroom": 100, "age_years": 1, "quoted_idv": 85}, {"idv_tolerance": 2}),
        ("expected_ncb", {}, {"claim_free_years": 1.5}),
        ("expected_ncb", {}, {"claim_free_years": True}),
        ("marginal_irr_continue", {"surrender_value": 100, "annual_premium": 10,
          "remaining_premiums": 1, "years_to_maturity": 2, "maturity_value": 121}, {"surrender_value": -1}),
        ("marginal_irr_continue", {"surrender_value": 100, "annual_premium": 10,
          "remaining_premiums": 1, "years_to_maturity": 2, "maturity_value": 121}, {"hurdle_rate": float("nan")}),
    ]
    for name, base, invalid in cases:
        env = im.run(name, dict(base, **invalid))
        check("invalid insurance input produces a gap instead of a recommendation",
              not env["ok"] and bool(env["gaps"]), (name, invalid, env))


def test_insurance_output_must_be_finite():
    env = im.run("term_cover_need", term_inputs(annual_income=1e308))
    check("overflow cannot publish an infinite cover recommendation",
          not env["ok"] and bool(env["gaps"]), env)



def test_continuation_without_irr_reports_gap():
    env = im.run("marginal_irr_continue", {"surrender_value": 0, "annual_premium": 0,
                  "remaining_premiums": 0, "years_to_maturity": 0, "maturity_value": 0})
    check("unsolved continuation calculation is not reported as successful",
          not env["ok"] and env["data"]["result"]["marginal_irr"] is None and bool(env["gaps"]), env)



def test_term_runway_requires_explicit_expenses():
    env = im.run("term_cover_need", term_inputs(years_to_independence=10, annual_expenses=None))
    check("missing family expenses cannot become an invented runway",
          not env["ok"] and any("annual_expenses" in gap for gap in env["gaps"]), env)
    zero = im.run("term_cover_need", term_inputs(years_to_independence=10, annual_expenses=0))
    check("explicit zero expenses remain a valid input", zero["ok"]
          and zero["data"]["result"]["breakdown"]["expense_runway"] == 0, zero)



def test_vehicle_idv_beyond_schedule_is_unknown():
    for extra in ({"age_years": 6}, {"age_years": 3, "model_discontinued": True}):
        env = im.run("idv_ncb_sanity", dict(ex_showroom=1000000, quoted_idv=500000,
                         claim_free_years=3, quoted_ncb=0.35, **extra))
        result = env["data"].get("result", {})
        check("out-of-schedule IDV is unknown while NCB remains available",
              env["ok"] and result.get("idv_ok") is None
              and result.get("expected_idv_low") is None and result.get("expected_idv_high") is None
              and result.get("ncb_ok") is True and bool(env["gaps"]), env)
    edge = im.idv_ncb_sanity(ex_showroom=1000000, age_years=5, quoted_idv=500000)
    check("exactly five years remains inside published age schedule", edge.idv_ok is True)



def test_health_uses_explicit_targets_and_deductible():
    inputs = dict(base_target=1000000, total_target=5000000, deductible=1500000,
                  personal_cover=500000, employer_cover=2000000)
    env = im.run("health_sum_insured", inputs)
    r = env["data"].get("result", {})
    check("health sizing uses explicit targets, not demographics", env["ok"] and r.get("base_target") == 1000000, env)
    check("employer cover cannot silently close the personal base gap", r.get("base_gap") == 500000, r)
    check("top-up target starts above the policy deductible", r.get("top_up_target") == 3500000, r)
    check("deductible gaps distinguish existing cover from proposed base",
          r.get("deductible_gap") == 1000000 and r.get("planned_deductible_gap") == 500000, r)
    legacy = im.run("health_sum_insured", {"adults": 2, "eldest_age": 40, "city_tier": 1})
    check("legacy demographics alone cannot manufacture a health target", not legacy["ok"], legacy)



def test_term_requires_all_household_and_scenario_inputs():
    for key in term_inputs():
        inputs = term_inputs()
        del inputs[key]
        env = im.run("term_cover_need", inputs)
        check("missing term input cannot become an implicit assumption",
              not env["ok"] and any(key in gap for gap in env["gaps"]), (key, env))



def test_insurance_cli_rejects_malformed_or_ambiguous_json():
    import subprocess
    from pathlib import Path
    cli = Path(__file__).resolve().parents[2] / "skills/insurance-advisor/scripts/insurance_math.py"
    for payload in ('{"claim_free_years":', '[]', 'null',
                    '{"claim_free_years": 1, "claim_free_years": 5}',
                    '{"claim_free_years": NaN}', '{"claim_free_years": 1e999}'):
        result = subprocess.run([sys.executable, str(cli), "expected_ncb", payload],
                                capture_output=True, text=True, timeout=10)
        check("bad CLI input reports usage error without traceback or result",
              result.returncode == 2 and "error:" in result.stderr
              and "Traceback" not in result.stderr and not result.stdout, result)
    result = subprocess.run([sys.executable, str(cli), "expected_ncb", '{"claim_free_years": 3}'],
                            capture_output=True, text=True, timeout=10)
    import json
    check("valid CLI input still delegates to the shared calculator",
          result.returncode == 0 and json.loads(result.stdout)["data"]["result"] == 0.35, result)



def test_continuation_without_hurdle_keeps_irr_without_verdict():
    env = im.run("marginal_irr_continue", dict(surrender_value=100, annual_premium=0,
                 remaining_premiums=0, years_to_maturity=2, maturity_value=121))
    result = env["data"].get("result", {})
    check("missing hurdle preserves computed IRR without inventing a benchmark",
          env["ok"] and approx(result.get("marginal_irr"), 0.1, tol=1e-6)
          and result.get("hurdle_rate") is None and result.get("beats_hurdle") is None
          and any("hurdle" in gap for gap in env["gaps"]), env)



def test_missing_ncb_inputs_remain_unknown():
    for inputs in ({}, {"claim_free_years": 3}, {"quoted_ncb": 0}):
        env = im.run("idv_ncb_sanity", dict(ex_showroom=1000000, age_years=3,
                    quoted_idv=700000, **inputs))
        result = env["data"].get("result", {})
        check("missing NCB evidence cannot become a passing check",
              env["ok"] and result.get("idv_ok") is True and result.get("ncb_ok") is None
              and any("NCB" in gap for gap in env["gaps"]), env)
    explicit = im.idv_ncb_sanity(ex_showroom=1000000, age_years=3, quoted_idv=700000,
                                claim_free_years=0, quoted_ncb=0)
    check("explicit zero NCB and history remain checkable", explicit.ncb_ok is True)


if __name__ == "__main__":
    run(globals())
