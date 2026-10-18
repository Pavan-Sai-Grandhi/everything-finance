"""Deterministic insurance math for insurance-advisor.

Every figure the skill reports as "computed" comes through here rather than being
eyeballed in prose, so it is reproducible and unit-tested. The skill supplies the
inputs (interview answers + researched figures), calls a function, and surfaces the
assumptions that fed it in the report's Assumptions table.

Nothing here fetches data or invents a number: callers pass sourced/assumed inputs;
these functions only do the arithmetic. Currency is plain INR (rupees) throughout.

Reached through: run_insurance_math.
"""
from __future__ import annotations

import math
import json

from dataclasses import asdict, dataclass, field, is_dataclass

from finance import spine

_SOURCE = "finance.compute.insurance_math"


def _number(name, value, *, minimum=0, integer=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or (integer and not isinstance(value, int))):
        raise ValueError(f"{name} must be a finite {'integer' if integer else 'number'}")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")


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
    income_multiple: float,
    outstanding_loans: float,
    education_corpus: float,
    annual_expenses: float | None,
    years_to_independence: float,
    existing_corpus: float,
    existing_cover: float,
) -> TermNeed:
    """Term cover need = larger of income-replacement and liability+goals.

    - income replacement: explicitly chosen ``income_multiple`` x annual income.
      The caller must explain this scenario assumption, not treat it as a universal rule.
    - liability + goals: outstanding loans + children's education corpus +
      (annual family expenses x years to youngest dependent's independence) - existing
      liquid corpus. A positive expense runway requires explicit ``annual_expenses``;
      the caller must supply the household figure or a clearly labelled scenario.

    The *need* is the larger; the *gap* is need minus cover already held (never below 0).
    """
    for name, value in {"annual_income": annual_income, "income_multiple": income_multiple,
                        "outstanding_loans": outstanding_loans, "education_corpus": education_corpus,
                        "years_to_independence": years_to_independence, "existing_corpus": existing_corpus,
                        "existing_cover": existing_cover}.items():
        _number(name, value)
    if annual_expenses is not None:
        _number("annual_expenses", annual_expenses)
    if income_multiple <= 0:
        raise ValueError("income_multiple must be > 0")

    income_replacement = income_multiple * annual_income

    if annual_expenses is None and years_to_independence > 0:
        raise ValueError("annual_expenses is required when years_to_independence is positive")
    expense_runway = annual_expenses * years_to_independence if annual_expenses is not None else 0.0
    liability_goals = (
        outstanding_loans
        + education_corpus
        + expense_runway
        - existing_corpus
    )
    liability_goals = max(liability_goals, 0.0)

    need = max(income_replacement, liability_goals)
    method = "income_replacement" if income_replacement >= liability_goals else "liability_goals"
    gap = max(need - existing_cover, 0.0)

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
            "existing_cover": existing_cover,
        },
    )


@dataclass
class HealthNeed:
    base_target: float
    total_target: float
    deductible: float
    personal_cover: float
    employer_cover: float
    base_gap: float
    top_up_target: float
    deductible_gap: float
    planned_deductible_gap: float


def health_sum_insured(
    *,
    base_target: float,
    total_target: float,
    deductible: float,
    personal_cover: float,
    employer_cover: float,
) -> HealthNeed:
    """Arithmetic for an explicitly chosen personal-base + super-top-up scenario.

    Targets are caller-supplied assumptions, not inferred recommendations. The total
    target includes the deductible layer; the top-up sum insured is above it. Gaps
    compare nominal amounts only, not claim eligibility or reimbursement. Employer
    cover is reported separately, without discounting or adding it to personal cover.
    """
    for name, value in {"base_target": base_target, "total_target": total_target,
                        "deductible": deductible, "personal_cover": personal_cover,
                        "employer_cover": employer_cover}.items():
        _number(name, value)
    if base_target <= 0 or total_target < base_target:
        raise ValueError("targets must satisfy 0 < base_target <= total_target")
    if deductible > total_target:
        raise ValueError("deductible cannot exceed total_target")
    return HealthNeed(
        base_target=base_target, total_target=total_target, deductible=deductible,
        personal_cover=personal_cover, employer_cover=employer_cover,
        base_gap=max(base_target - personal_cover, 0.0),
        top_up_target=total_target - deductible,
        deductible_gap=max(deductible - personal_cover, 0.0),
        planned_deductible_gap=max(deductible - base_target, 0.0),
    )


# Age-based IDV schedule; policy source and scope are documented in
# skills/insurance-advisor/references/vehicle.md. Values are retained fractions.
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


def _idv_retention(age_years: float) -> float | None:
    for cap, frac in _IDV_RETENTION:
        if age_years <= cap:
            return frac
    return None  # Beyond five years the insurer and insured agree the IDV.


def expected_ncb(claim_free_years: int) -> float:
    """Entitled NCB fraction for a run of consecutive claim-free years (caps at 50%)."""
    _number("claim_free_years", claim_free_years, integer=True)
    if claim_free_years == 0:
        return 0.0
    frac = 0.0
    for years, f in _NCB_SLAB:
        if claim_free_years >= years:
            frac = f
    return frac


@dataclass
class VehicleSanity:
    expected_idv_low: float | None
    expected_idv_high: float | None
    idv_ok: bool | None
    expected_ncb: float | None         # fraction, e.g. 0.35; missing history is unknown
    ncb_ok: bool | None
    flags: list = field(default_factory=list)
    idv_gap: str | None = None
    ncb_gap: str | None = None


def idv_ncb_sanity(
    *,
    ex_showroom: float,
    age_years: float,
    quoted_idv: float,
    claim_free_years: int | None = None,
    quoted_ncb: float | None = None,
    idv_tolerance: float = 0.10,
    model_discontinued: bool = False,
) -> VehicleSanity:
    """Sanity-check a quoted IDV against the age-depreciated value, and NCB against slab.

    IDV should sit near ex-showroom x an age-based retention factor; a quote far below
    that band cuts the claim payout, one far above inflates premium. NCB should match the
    slab entitled by consecutive claim-free years — a higher quoted NCB is a red flag.
    Older/discontinued models have no age-based IDV check; NCB remains available.
    The tolerance band is a screening assumption, not a contractual entitlement.
    """
    for name, value in {"ex_showroom": ex_showroom, "age_years": age_years,
                        "quoted_idv": quoted_idv,
                        "idv_tolerance": idv_tolerance}.items():
        _number(name, value)
    if quoted_ncb is not None:
        _number("quoted_ncb", quoted_ncb)
    if (quoted_ncb is not None and quoted_ncb > 1) or idv_tolerance > 1:
        raise ValueError("quoted_ncb and idv_tolerance must be fractions between 0 and 1")
    if ex_showroom <= 0:
        raise ValueError("ex_showroom must be > 0")
    if not isinstance(model_discontinued, bool):
        raise ValueError("model_discontinued must be a boolean")
    retention = None if model_discontinued else _idv_retention(age_years)
    low = high = idv_ok = idv_gap = None
    if retention is None:
        idv_gap = "IDV requires insurer-insured agreement for vehicles over five years or discontinued models; age-based check unavailable"
    else:
        mid = ex_showroom * retention
        low = mid * (1 - idv_tolerance)
        high = mid * (1 + idv_tolerance)
        idv_ok = low <= quoted_idv <= high

    ncb = expected_ncb(claim_free_years) if claim_free_years is not None else None
    ncb_ok = ncb_gap = None
    if ncb is None or quoted_ncb is None:
        ncb_gap = "NCB check requires both claim_free_years and quoted_ncb; missing evidence is not zero"
    else:
        ncb_ok = abs(quoted_ncb - ncb) < 1e-9 or quoted_ncb <= ncb

    flags = []
    if low is not None and quoted_idv < low:
        flags.append("quoted IDV below age-depreciated band — under-insured, lower claim payout")
    elif high is not None and quoted_idv > high:
        flags.append("quoted IDV above age-depreciated band — inflated premium")
    if ncb is not None and quoted_ncb is not None and quoted_ncb > ncb + 1e-9:
        flags.append("quoted NCB exceeds slab entitlement — verify claim-free history")

    return VehicleSanity(
        expected_idv_low=low,
        expected_idv_high=high,
        idv_ok=idv_ok,
        expected_ncb=ncb,
        ncb_ok=ncb_ok,
        flags=flags,
        idv_gap=idv_gap,
        ncb_gap=ncb_gap,
    )


def _npv_sign_value(rate: float, cashflows: list) -> float:
    """NPV or a positive rescaling of it; only its sign is used by bisection.

    With negative rates multiply NPV by (1+rate)**(n-1) and use Horner's
    method. With nonnegative rates use discounted Horner evaluation. Both avoid
    raising discount factors to large powers and preserve the root.
    """
    value = 0.0
    factor = 1 + rate
    if rate < 0:
        for cf in cashflows:
            value = value * factor + cf
    else:
        for cf in reversed(cashflows):
            value = value / factor + cf
    return value


def irr(cashflows: list, *, lo: float = -0.99, hi: float = 1.0, tol: float = 1e-7) -> float | None:
    """Periodic IRR for cashflows with one sign change; None if unbracketed.

    Multiple sign changes are unsupported because they can have multiple IRRs.
    cashflows[0] is t0; tol is the absolute rate-interval tolerance, independent
    of the currency scale. No numpy dependency is needed.
    """
    if not isinstance(cashflows, (list, tuple)):
        raise ValueError("cashflows must be a numeric sequence")
    for value in (*cashflows, lo, hi, tol):
        _number("cashflow or IRR parameter", value, minimum=None)
    if not -1 < lo < hi:
        raise ValueError("IRR bounds must satisfy -1 < lo < hi")
    if tol <= 0:
        raise ValueError("IRR tolerance must be positive")
    nonzero = [cf for cf in cashflows if cf != 0]
    changes = sum((a < 0) != (b < 0) for a, b in zip(nonzero, nonzero[1:]))
    if changes != 1:
        return None
    # Removing endpoint zeros changes NPV by a positive factor, not its roots.
    start = next(i for i, cf in enumerate(cashflows) if cf != 0)
    end = len(cashflows) - next(i for i, cf in enumerate(reversed(cashflows)) if cf != 0)
    scale = max(abs(cf) for cf in cashflows)
    flows = [cf / scale for cf in cashflows[start:end]]
    f_lo, f_hi = _npv_sign_value(lo, flows), _npv_sign_value(hi, flows)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if (f_lo < 0) == (f_hi < 0):
        return None
    for _ in range(200):
        mid = lo / 2 + hi / 2
        f_mid = _npv_sign_value(mid, flows)
        if f_mid == 0 or hi - lo <= tol or mid in (lo, hi):
            return mid
        if (f_lo < 0) != (f_mid < 0):
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return None  # no converged solution within the iteration limit


@dataclass
class ContinueDecision:
    marginal_irr: float | None         # IRR of continuing; None if unsolvable
    cashflows: list
    beats_hurdle: bool | None          # None if IRR or benchmark unavailable
    hurdle_rate: float | None


def marginal_irr_continue(
    *,
    surrender_value: float,
    annual_premium: float,
    remaining_premiums: int,
    years_to_maturity: int,
    maturity_value: float,
    hurdle_rate: float | None = None,
) -> ContinueDecision:
    """Marginal IRR of *continuing* an in-force endowment/ULIP vs surrendering now.

    The decision-relevant series (not the whole-policy IRR): at t0 you forgo the surrender
    value you could have taken and invested (an outflow of that capital into the policy),
    you pay the remaining premiums, and at maturity you collect the maturity value.

        t0:                         -surrender_value
        t0 .. t_remaining_premiums-1: -annual_premium
        t_years_to_maturity:          +maturity_value

    Premiums are assumed paid at the start of each year, including the first payment
    now. The result compares this cash-flow IRR to the supplied hurdle; it does not
    decide whether to surrender coverage or account for taxes and policy guarantees.
    """
    for name, value in {"remaining_premiums": remaining_premiums,
                        "years_to_maturity": years_to_maturity}.items():
        _number(name, value, integer=True)
    for name, value in {"surrender_value": surrender_value, "annual_premium": annual_premium,
                        "maturity_value": maturity_value}.items():
        _number(name, value)
    if hurdle_rate is not None:
        _number("hurdle_rate", hurdle_rate, minimum=None)
        if hurdle_rate <= -1:
            raise ValueError("hurdle_rate must exceed -1")
    if remaining_premiums > years_to_maturity:
        raise ValueError("remaining_premiums cannot exceed years_to_maturity")

    cashflows = [0.0] * (years_to_maturity + 1)
    cashflows[0] = -surrender_value
    for t in range(remaining_premiums):
        cashflows[t] += -annual_premium
    cashflows[years_to_maturity] += maturity_value

    r = irr(cashflows)
    beats = None if r is None or hurdle_rate is None else (r >= hurdle_rate)
    return ContinueDecision(
        marginal_irr=r,
        cashflows=cashflows,
        beats_hurdle=beats,
        hurdle_rate=hurdle_rate,
    )


CALCULATIONS = {
    "term_cover_need": term_cover_need,
    "health_sum_insured": health_sum_insured,
    "idv_ncb_sanity": idv_ncb_sanity,
    "expected_ncb": expected_ncb,
    "irr": irr,
    "marginal_irr_continue": marginal_irr_continue,
}


def run(calculation, inputs=None):
    """One calculation from CALCULATIONS in the shared envelope.

    `inputs` is the keyword mapping that calculation takes. An unknown name, a missing
    keyword or a value the arithmetic rejects is a labelled gap, never an exception.
    """
    fn = CALCULATIONS.get(str(calculation))
    if fn is None:
        return spine.envelope(
            False, _SOURCE, {"calculation": calculation},
            [f"unknown calculation {calculation!r}; expected one of "
             f"{', '.join(sorted(CALCULATIONS))}"])
    try:
        result = fn(**(inputs or {}))
        output = asdict(result) if is_dataclass(result) else result
        json.dumps(output, allow_nan=False)
    except (TypeError, ValueError, ArithmeticError) as exc:
        return spine.envelope(False, _SOURCE, {"calculation": calculation},
                              [f"{calculation} rejected these inputs: {exc}"])
    solved = result is not None and (
        not isinstance(result, ContinueDecision) or result.marginal_irr is not None)
    gaps = [] if solved else [f"{calculation} had no supported solution for these inputs"]
    if isinstance(result, ContinueDecision) and result.hurdle_rate is None:
        gaps.append("hurdle_rate not supplied; IRR comparison is unavailable")
    if isinstance(result, VehicleSanity):
        gaps.extend(gap for gap in (result.idv_gap, result.ncb_gap) if gap)
    return spine.envelope(
        solved, _SOURCE,
        {"calculation": calculation,
         "result": output},
        gaps)
