#!/usr/bin/env python3
"""Offline unit tests for insurance_math. No network — deterministic inputs.
Run: python3 skills/insurance-advisor/scripts/test_insurance_math.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import insurance_math as im  # noqa: E402

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


def approx(a, b, tol=1.0):
    return abs(a - b) <= tol


# --- term cover need ----------------------------------------------------------

def test_term_income_replacement_wins():
    # High income, no big liabilities -> income-replacement dominates.
    r = im.term_cover_need(20_00_000, income_multiple=12)
    check("income_replacement = 12x", approx(r.income_replacement, 2_40_00_000))
    check("need takes the larger", r.need == r.income_replacement)
    check("method is income_replacement", r.method == "income_replacement")


def test_term_liability_goals_wins():
    # Modest income but a big loan + education corpus -> liability+goals dominates.
    r = im.term_cover_need(
        10_00_000, income_multiple=10,
        outstanding_loans=80_00_000, education_corpus=1_00_00_000,
        annual_expenses=5_00_000, years_to_independence=15,
        existing_corpus=20_00_000,
    )
    # 80L + 1Cr + 5L*15 - 20L = 2.35Cr, vs income-replacement 1Cr
    check("liability_goals computed", approx(r.liability_goals, 2_35_00_000))
    check("need takes liability_goals", r.need == r.liability_goals)
    check("method is liability_goals", r.method == "liability_goals")


def test_term_gap_and_defaults():
    r = im.term_cover_need(10_00_000, income_multiple=15, existing_cover=50_00_000)
    check("need = 1.5Cr", approx(r.need, 1_50_00_000))
    check("gap nets existing cover", approx(r.gap, 1_00_00_000))
    r2 = im.term_cover_need(10_00_000, income_multiple=1, years_to_independence=10)
    # annual_expenses defaults to 45% of income = 4.5L, runway = 45L
    check("annual_expenses defaults to 45%", approx(r2.breakdown["annual_expenses"], 4_50_000))
    check("gap never negative", im.term_cover_need(0).gap == 0)


# --- health sum insured -------------------------------------------------------

def test_health_single_metro():
    r = im.health_sum_insured(adults=1, eldest_age=30, city_tier=1)
    check("single metro base = 10L", approx(r.base_recommended, 10_00_000))


def test_health_family_floater_and_employer_weight():
    r = im.health_sum_insured(
        adults=2, children=2, eldest_age=40, city_tier=1,
        personal_cover=5_00_000, employer_cover=10_00_000,
    )
    # 10L tier + 5L floater = 15L base; employer counts half: 5L + 0.5*10L = 10L
    check("floater base lifted", approx(r.base_recommended, 15_00_000))
    check("employer weighted at half", approx(r.effective_existing, 10_00_000))
    check("gap = base - effective", approx(r.gap, 5_00_000))


def test_health_older_and_seniors():
    r = im.health_sum_insured(adults=2, eldest_age=50, city_tier=1, has_senior_parents=True)
    # 10L + 5L floater + 5L age>=45 + 5L seniors = 25L
    check("older + seniors lift base to 25L", approx(r.base_recommended, 25_00_000))


# --- vehicle IDV / NCB --------------------------------------------------------

def test_idv_in_band():
    # 3-year car: retention 0.70 of 10L ex-showroom = 7L mid.
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


# --- marginal IRR of continuing -----------------------------------------------

def test_marginal_irr_known_series():
    # -100 at t0, +121 at t2 -> IRR = 10%.
    r = im.irr([-100, 0, 121])
    check("irr of simple series ~10%", approx(r, 0.10, tol=1e-4))


def test_marginal_irr_continue_poor_policy():
    # Forgo 5L SV, pay 1L/yr for 5 more yrs, get 12L at yr 10 -> low IRR, surrender.
    d = im.marginal_irr_continue(
        surrender_value=5_00_000, annual_premium=1_00_000,
        remaining_premiums=5, years_to_maturity=10, maturity_value=12_00_000,
        hurdle_rate=0.07,
    )
    check("marginal IRR solved", d.marginal_irr is not None)
    check("poor policy below 7% hurdle", d.beats_hurdle is False)
    # premiums are start-of-year: t0 carries surrender value + first premium
    check("t0 outflow is SV + first premium", d.cashflows[0] == -6_00_000)


def test_marginal_irr_continue_worth_keeping():
    # Small SV, cheap remaining premiums, big maturity -> high IRR, keep it.
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


def main():
    for fn in sorted(g for g in globals() if g.startswith("test_")):
        print(f"\n[{fn}]")
        globals()[fn]()
    print(f"\n{'='*48}\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
