#!/usr/bin/env python3
"""Deterministic insurance math for insurance-advisor.

Every figure the skill reports as "computed" comes through here rather than being
eyeballed in prose, so it is reproducible and unit-tested. The skill supplies the
inputs (interview answers + researched figures), calls a function, and surfaces the
assumptions that fed it in the report's Assumptions table.

Nothing here fetches data or invents a number: callers pass sourced/assumed inputs;
these functions only do the arithmetic. Currency is plain INR (rupees) throughout.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# --- term life: how much cover -------------------------------------------------

@dataclass
class TermNeed:
    income_replacement: float          # multiple x annual income
    liability_goals: float             # loans + goals + expense-runway - corpus
    need: float                        # the larger of the two (never negative)
    gap: float                         # need - existing cover (floored at 0)
    method: str                        # which method set the need
    breakdown: dict = field(default_factory=dict)


def term_cover_need(
    annual_income: float,
    *,
    income_multiple: float = 12.0,
    outstanding_loans: float = 0.0,
    education_corpus: float = 0.0,
    annual_expenses: float | None = None,
    years_to_independence: float = 0.0,
    existing_corpus: float = 0.0,
    existing_cover: float = 0.0,
) -> TermNeed:
    """Term cover need = larger of income-replacement and liability+goals.

    - income replacement: ``income_multiple`` x annual income (10-15x rule; 15x when
      dependents are young).
    - liability + goals: outstanding loans + children's education corpus +
      (annual family expenses x years to youngest dependent's independence) - existing
      liquid corpus. ``annual_expenses`` defaults to 45% of income when unstated.

    The *need* is the larger; the *gap* is need minus cover already held (never below 0).
    """
    if annual_income < 0:
        raise ValueError("annual_income must be >= 0")
    if income_multiple <= 0:
        raise ValueError("income_multiple must be > 0")

    income_replacement = income_multiple * annual_income

    if annual_expenses is None:
        annual_expenses = 0.45 * annual_income
    expense_runway = annual_expenses * max(years_to_independence, 0.0)
    liability_goals = (
        max(outstanding_loans, 0.0)
        + max(education_corpus, 0.0)
        + expense_runway
        - max(existing_corpus, 0.0)
    )
    liability_goals = max(liability_goals, 0.0)

    need = max(income_replacement, liability_goals)
    method = "income_replacement" if income_replacement >= liability_goals else "liability_goals"
    gap = max(need - max(existing_cover, 0.0), 0.0)

    return TermNeed(
        income_replacement=income_replacement,
        liability_goals=liability_goals,
        need=need,
        gap=gap,
        method=method,
        breakdown={
            "income_multiple": income_multiple,
            "annual_expenses": annual_expenses,
            "expense_runway": expense_runway,
            "existing_cover": max(existing_cover, 0.0),
        },
    )


# --- health: how much sum insured ---------------------------------------------

# Base individual sum-insured floor by city tier (2026 metro context, INR).
_HEALTH_TIER_BASE = {1: 10_00_000, 2: 7_50_000, 3: 5_00_000}


@dataclass
class HealthNeed:
    base_recommended: float            # base policy sum insured to hold
    effective_existing: float          # existing cover, employer weighted at half
    top_up_recommended: float          # super top-up to cover the tail
    gap: float                         # base_recommended - effective_existing (>= 0)
    structure: str
    breakdown: dict = field(default_factory=dict)


def health_sum_insured(
    *,
    adults: int = 1,
    children: int = 0,
    eldest_age: int = 30,
    city_tier: int = 1,
    personal_cover: float = 0.0,
    employer_cover: float = 0.0,
    has_senior_parents: bool = False,
) -> HealthNeed:
    """Recommend a base sum insured + super top-up, and the gap vs existing cover.

    Family floaters need more than a single life; older members and senior parents push
    the base up. Employer cover is real but vanishes with the job, so it counts at half
    weight toward the effective existing cover. The resilient structure is a personal
    base policy plus a super top-up above a deductible.
    """
    if adults < 0 or children < 0:
        raise ValueError("adults and children must be >= 0")
    if city_tier not in _HEALTH_TIER_BASE:
        raise ValueError("city_tier must be 1, 2 or 3")

    base = float(_HEALTH_TIER_BASE[city_tier])
    lives = adults + children
    if lives > 1:                       # floater: lift the base for a family
        base += 5_00_000
    if eldest_age >= 45:                # older lives claim more, cost more
        base += 5_00_000
    if has_senior_parents:              # separate senior policy, not on the floater
        base += 5_00_000

    effective_existing = max(personal_cover, 0.0) + 0.5 * max(employer_cover, 0.0)
    gap = max(base - effective_existing, 0.0)
    # Super top-up sizes the catastrophic tail above the base (medical inflation 12-14%).
    top_up = max(50_00_000 - base, 0.0) + 50_00_000

    return HealthNeed(
        base_recommended=base,
        effective_existing=effective_existing,
        top_up_recommended=top_up,
        gap=gap,
        structure="personal base + super top-up above deductible",
        breakdown={
            "tier_base": float(_HEALTH_TIER_BASE[city_tier]),
            "lives": lives,
            "employer_weight": 0.5,
        },
    )


# --- vehicle: IDV / NCB sanity -------------------------------------------------

# IRDAI depreciation grid for IDV by vehicle age (fraction retained of ex-showroom).
_IDV_RETENTION = [
    (0.5, 0.95),   # <= 6 months
    (1.0, 0.85),   # 6 months - 1 year
    (2.0, 0.80),   # 1 - 2 years
    (3.0, 0.70),   # 2 - 3 years
    (4.0, 0.60),   # 3 - 4 years
    (5.0, 0.50),   # 4 - 5 years
]

# NCB slab: consecutive claim-free years -> entitled discount fraction.
_NCB_SLAB = [(1, 0.20), (2, 0.25), (3, 0.35), (4, 0.45), (5, 0.50)]


def _idv_retention(age_years: float) -> float:
    for cap, frac in _IDV_RETENTION:
        if age_years <= cap:
            return frac
    return 0.50  # >5y: IDV is mutually agreed, but ~50% is the practical floor


def expected_ncb(claim_free_years: int) -> float:
    """Entitled NCB fraction for a run of consecutive claim-free years (caps at 50%)."""
    if claim_free_years <= 0:
        return 0.0
    frac = 0.0
    for years, f in _NCB_SLAB:
        if claim_free_years >= years:
            frac = f
    return frac


@dataclass
class VehicleSanity:
    expected_idv_low: float
    expected_idv_high: float
    idv_ok: bool
    expected_ncb: float                # fraction, e.g. 0.35
    ncb_ok: bool
    flags: list = field(default_factory=list)


def idv_ncb_sanity(
    *,
    ex_showroom: float,
    age_years: float,
    quoted_idv: float,
    claim_free_years: int = 0,
    quoted_ncb: float = 0.0,
    idv_tolerance: float = 0.10,
) -> VehicleSanity:
    """Sanity-check a quoted IDV against the age-depreciated value, and NCB against slab.

    IDV should sit near ex-showroom x an age-based retention factor; a quote far below
    that band cuts the claim payout, one far above inflates premium. NCB should match the
    slab entitled by consecutive claim-free years — a higher quoted NCB is a red flag.
    """
    if ex_showroom <= 0:
        raise ValueError("ex_showroom must be > 0")
    retention = _idv_retention(max(age_years, 0.0))
    mid = ex_showroom * retention
    low = mid * (1 - idv_tolerance)
    high = mid * (1 + idv_tolerance)
    idv_ok = low <= quoted_idv <= high

    ncb = expected_ncb(claim_free_years)
    ncb_ok = abs(quoted_ncb - ncb) < 1e-9 or quoted_ncb <= ncb

    flags = []
    if quoted_idv < low:
        flags.append("quoted IDV below age-depreciated band — under-insured, lower claim payout")
    elif quoted_idv > high:
        flags.append("quoted IDV above age-depreciated band — inflated premium")
    if quoted_ncb > ncb + 1e-9:
        flags.append("quoted NCB exceeds slab entitlement — verify claim-free history")

    return VehicleSanity(
        expected_idv_low=low,
        expected_idv_high=high,
        idv_ok=idv_ok,
        expected_ncb=ncb,
        ncb_ok=ncb_ok,
        flags=flags,
    )


# --- endowment / ULIP: marginal IRR of continuing ------------------------------

def _npv(rate: float, cashflows: list) -> float:
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))


def irr(cashflows: list, *, lo: float = -0.99, hi: float = 1.0, tol: float = 1e-7) -> float | None:
    """Internal rate of return by bisection on NPV; None if no sign change in range.

    No numpy dependency — the series here are short. cashflows[0] is t0.
    """
    f_lo, f_hi = _npv(lo, cashflows), _npv(hi, cashflows)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if f_lo * f_hi > 0:
        return None  # no root bracketed — caller treats as unsolvable
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = _npv(mid, cashflows)
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


@dataclass
class ContinueDecision:
    marginal_irr: float | None         # IRR of continuing; None if unsolvable
    cashflows: list
    beats_hurdle: bool | None          # marginal_irr >= hurdle_rate (None if unsolvable)
    hurdle_rate: float


def marginal_irr_continue(
    *,
    surrender_value: float,
    annual_premium: float,
    remaining_premiums: int,
    years_to_maturity: int,
    maturity_value: float,
    hurdle_rate: float = 0.07,
) -> ContinueDecision:
    """Marginal IRR of *continuing* an in-force endowment/ULIP vs surrendering now.

    The decision-relevant series (not the whole-policy IRR): at t0 you forgo the surrender
    value you could have taken and invested (an outflow of that capital into the policy),
    you pay the remaining premiums, and at maturity you collect the maturity value.

        t0:                 -surrender_value
        t1 .. t_prem:       -annual_premium   (remaining_premiums years)
        t_maturity:         +maturity_value

    If the marginal IRR is below a safe hurdle (a comparable FD / debt fund), surrender and
    invest the proceeds instead. Premiums are assumed paid at the start of each year.
    """
    if remaining_premiums < 0 or years_to_maturity < 0:
        raise ValueError("remaining_premiums and years_to_maturity must be >= 0")
    if remaining_premiums > years_to_maturity:
        raise ValueError("remaining_premiums cannot exceed years_to_maturity")

    cashflows = [0.0] * (years_to_maturity + 1)
    cashflows[0] = -max(surrender_value, 0.0)
    for t in range(remaining_premiums):
        cashflows[t] += -max(annual_premium, 0.0)
    cashflows[years_to_maturity] += max(maturity_value, 0.0)

    r = irr(cashflows)
    beats = None if r is None else (r >= hurdle_rate)
    return ContinueDecision(
        marginal_irr=r,
        cashflows=cashflows,
        beats_hurdle=beats,
        hurdle_rate=hurdle_rate,
    )
