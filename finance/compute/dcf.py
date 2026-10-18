"""Story-driven FCFF DCF valuation engine (everything-finance).

Faithful to Aswath Damodaran's free-cash-flow-to-firm model (The Little Book of
Valuation / Narrative and Numbers). The engine does ONLY arithmetic on inputs you
supply — it never invents a number. Every input must trace to a sourced figure
(`get_company_fundamentals`, the annual report, an exchange filing) so the output is
authentic and auditable. Garbage in, garbage out: the skill's job is to make the
story behind each input explicit and consistent before trusting the per-share value.

Model (per explicit-forecast year t = 1..N):
    revenue_t       = revenue_{t-1} * (1 + growth_t)
    ebit_t          = revenue_t * operating_margin_t          # pre-tax operating income
    nopat_t         = ebit_t * (1 - tax_rate_t)               # after-tax operating income
    reinvestment_t  = (revenue_t - revenue_{t-1}) / sales_to_capital_t
    fcff_t          = nopat_t - reinvestment_t                # free cash flow to the firm
    pv_t            = fcff_t / prod_{i<=t}(1 + wacc_i)         # cumulative discounting

Cash-flow timing (`timing: {base_period_end, valuation_date}`): a year's cash arrives through
the year, so each explicit flow is discounted from mid-year, and the whole value is rolled
forward from the base period's end to the valuation date:
    pv_t            *= (1 + wacc_t)**0.5 * (1 + wacc_1)**elapsed
    pv_TV           *= (1 + wacc_1)**elapsed      # the terminal value stays at year end
Without it every flow is discounted from the end of its year, counted from the base period's
end; the result carries TIMING_UNADJUSTED.

Terminal value (Gordon growth on a stable-growth firm, Damodaran's reinvestment tie):
    g_T             = terminal_growth          (must be <= risk_free; a mature firm
                                                cannot outgrow the economy forever)
    reinvest_rate_T = g_T / terminal_roic      (reinvestment consistent with growth+ROIC)
    nopat_{N+1}     = revenue_N*(1+g_T) * terminal_margin * (1 - tax_T)
    fcff_{N+1}      = nopat_{N+1} * (1 - reinvest_rate_T)
    TV_N            = fcff_{N+1} / (wacc_T - g_T)
    pv_TV           = TV_N / prod(1 + wacc_i over the N explicit years)

Value bridge:
    EV       = sum(pv_fcff) + pv_TV
    equity   = EV - net_debt + non_operating_cash - minority_interest
    per_share= equity / shares_outstanding
    MoS      = per_share / current_price - 1     (margin of safety, if a price is given)

All money inputs/outputs are in the SAME unit (use ₹ Crore consistently); shares in
the same count unit (Crore) so per_share comes out in ₹. The input file's shape is
skills/valuation-analysis/assets/dcf-inputs.example.yml. Reached through run_dcf, which
pairs this with the relative read from `relval.py`.
"""
import json
import math
import os
from datetime import date

from finance import paths, spine
from finance.compute import relval
from finance.sources import estimates as _estimates
from finance.sources import market as _market
from finance.sources import risk as _risk
from finance.deps import need as _need

_SOURCE = "finance.compute.dcf"

def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("model inputs must be finite numbers, not booleans or text")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError("model input exceeds the supported numeric range") from exc
    if not math.isfinite(number):
        raise ValueError("model inputs must be finite numbers, not booleans or text")
    return number


def _horizon(spec):
    if not isinstance(spec, dict):
        raise ValueError("model inputs must be a mapping")
    years = spec.get("years", 10)
    if type(years) is not int or years < 1:
        raise ValueError("years must be a positive integer")
    return years


def _as_path(value, n, default):
    """Expand a scalar OR a list into an N-length list. Last value carries forward."""
    if value is None:
        value = default
    if isinstance(value, (int, float)):
        return [_number(value)] * n
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("model paths must be a number or a nonempty list")
    seq = [_number(x) for x in value]
    if len(seq) < n:
        seq = seq + [seq[-1]] * (n - len(seq))
    return seq[:n]


def _ramp(start, end, n):
    """Linear glide from start to end across n years (inclusive of end at year n)."""
    if n == 1:
        return [float(end)]
    step = (end - start) / (n - 1)
    return [round(start + step * i, 10) for i in range(n)]


def resolve_growth(spec, n):
    """Revenue growth path. Either explicit `revenue_growth` (scalar/list) or a
    high->fade glide: {initial, fade_to, years_high} (high for years_high, then linear
    fade to fade_to by year N)."""
    if "revenue_growth" in spec and spec["revenue_growth"] is not None:
        return _as_path(spec["revenue_growth"], n, 0.0)
    g = spec.get("growth_glide")
    if g is not None and not isinstance(g, dict):
        raise ValueError("growth_glide must be a mapping")
    if g:
        hi = _number(g["initial"])
        lo = _number(g.get("fade_to", hi))
        yh = g.get("years_high", 1)
        if type(yh) is not int or not 0 <= yh <= n:
            raise ValueError("years_high must be an integer within the modeled horizon")
        head = [hi] * yh
        # `_ramp` includes its start.  Drop that duplicate after the explicit
        # high-growth block so `years_high: 3` means exactly three years, not four.
        if yh == 0:
            tail = _ramp(hi, lo, n)
        else:
            tail = _ramp(hi, lo, n - yh + 1)[1:] if n - yh > 0 else []
        return (head + tail)[:n]
    raise ValueError("inputs need either `revenue_growth` or `growth_glide`")


def resolve_margin(spec, n):
    """Operating-margin path. Either explicit `operating_margin` (scalar/list) or a glide
    {start, target, year_target}: ramp start->target by year_target, hold target after."""
    if "operating_margin" in spec and spec["operating_margin"] is not None:
        return _as_path(spec["operating_margin"], n, 0.0)
    m = spec.get("margin_glide")
    if m is not None and not isinstance(m, dict):
        raise ValueError("margin_glide must be a mapping")
    if m:
        start = _number(m["start"])
        target = _number(m["target"])
        yt = m.get("year_target", n)
        if type(yt) is not int or not 1 <= yt <= n:
            raise ValueError("year_target must be an integer within the modeled horizon")
        head = _ramp(start, target, yt)
        tail = [target] * (n - yt)
        return (head + tail)[:n]
    raise ValueError("inputs need either `operating_margin` or `margin_glide`")


def resolve_wacc(spec, n):
    """Discount-rate path. Either an explicit `wacc` (scalar/list) OR a `wacc_buildup` block
    that builds the cost of equity the way Damodaran does — and, crucially, lets the country
    risk attach to the company's *operating exposure*, not to where it is incorporated. His
    melded form:

        cost_of_equity = risk_free + beta*mature_erp + lambda_country*country_risk_premium
        wacc           = w_e*cost_of_equity + w_d*cost_of_debt_pretax*(1 - tax)

    `lambda_country` (λ) is the firm's exposure to the country's risk ≈ its share of revenue/
    operations there relative to the average firm. An Indian IT exporter earning abroad has a
    LOW λ (TCS ≈ 0.09) and should barely carry India's CRP; a purely domestic FMCG/lender has
    λ ≈ 1 and carries it fully. Defaulting λ to 1.0 keeps a domestic firm fully exposed; set it
    from the revenue mix rather than assuming every "Indian" company is equally India-risky.
    Building this up here (not hand-typing one wacc) also stops the double-count where risk is
    loaded into BOTH a high discount rate AND a deliberately timid growth path."""
    if spec.get("wacc") is not None:
        raw = spec["wacc"]
        path = _as_path(raw, n, 0.11)
        if isinstance(raw, (int, float)) and lifecycle_stage(spec) in YOUNG_STAGES \
                and spec.get("terminal_wacc") is not None:
            path = _ramp(path[0], _number(spec["terminal_wacc"]), n)
        return path, None
    b = spec.get("wacc_buildup")
    if b is not None and not isinstance(b, dict):
        raise ValueError("wacc_buildup must be a mapping")
    if not b:
        raise ValueError("inputs need a discount rate — either an explicit `wacc` (scalar/list) "
                         "or a `wacc_buildup` block; WACC must be sourced, never defaulted")
    beta = _number(b.get("beta", 1.0))
    mature_erp = _number(b["mature_erp"])
    crp = _number(b.get("country_risk_premium", 0.0))
    bond_yield = b.get("government_bond_yield")
    default_spread = b.get("sovereign_default_spread")
    if bond_yield is not None:
        if default_spread is None:
            raise ValueError("wacc_buildup with `government_bond_yield` also needs "
                             "`sovereign_default_spread` to derive a default-free risk-free rate")
        rf = _number(bond_yield) - _number(default_spread)
        if rf <= 0:
            raise ValueError("government_bond_yield minus sovereign_default_spread must be > 0")
    elif b.get("risk_free") is not None:
        rf = _number(b["risk_free"])
        if crp > 0 and b.get("risk_free_is_default_free") is not True:
            raise ValueError("country risk is being added, so `risk_free` must be explicitly confirmed "
                             "as default-free with `risk_free_is_default_free: true`, or derived from "
                             "`government_bond_yield - sovereign_default_spread`")
    else:
        raise ValueError("wacc_buildup needs either a default-free `risk_free` or "
                         "`government_bond_yield` plus `sovereign_default_spread`")
    lam = _number(b.get("lambda_country", 1.0))
    coe = rf + beta * mature_erp + lam * crp
    erp_total = mature_erp + lam * crp
    cod = _number(b.get("cost_of_debt_pretax", coe))
    # the buildup needs a SCALAR tax rate for the debt shield; a per-year spec `tax_rate` path
    # cannot stand in, so require an explicit scalar rather than defaulting one.
    tax_spec = b.get("tax_rate", spec.get("tax_rate"))
    if isinstance(tax_spec, (list, tuple)):
        raise ValueError("wacc_buildup needs a scalar `tax_rate` for the after-tax cost of debt "
                         "— a per-year tax path cannot supply it; set `tax_rate` in the "
                         "wacc_buildup block")
    if tax_spec is None:
        raise ValueError("wacc_buildup needs `tax_rate` for the after-tax cost of debt")
    tax = _number(tax_spec)
    we = _number(b.get("equity_weight", 1.0))
    wd = _number(b.get("debt_weight", 1.0 - we))
    if not 0 <= we <= 1 or not 0 <= wd <= 1 or not math.isclose(we + wd, 1.0, abs_tol=1e-9):
        raise ValueError("equity/debt weights must lie in [0,1] and sum to one")
    if str(spec.get("model_shape") or "fcff").strip().lower() == "equity" and (we != 1 or wd != 0):
        raise ValueError("equity model requires cost of equity: buildup weights must be equity=1, debt=0")
    wacc = we * coe + wd * cod * (1.0 - tax)
    detail = {"cost_of_equity": round(coe, 6), "after_tax_cost_of_debt": round(cod * (1 - tax), 6),
              # This rate is reused by validation and scenario calculations.
              # Keep its precision; presentation rounding belongs in reports.
              "default_free_risk_free": rf,
              "government_bond_yield": round(float(bond_yield), 6) if bond_yield is not None else None,
              "sovereign_default_spread": round(float(default_spread), 6) if default_spread is not None else None,
              "beta": round(beta, 6), "lambda_country": round(lam, 6),
              "country_risk_loaded": round(lam * crp, 6),
              "equity_risk_premium": round(erp_total, 6), "wacc": round(wacc, 6)}
    path = _as_path(wacc, n, wacc)
    if lifecycle_stage(spec) in YOUNG_STAGES and spec.get("terminal_wacc") is not None:
        path = _ramp(wacc, _number(spec["terminal_wacc"]), n)
    return path, detail


YOUNG_STAGES = {"idea", "start_up", "startup", "young", "young_growth", "high_growth"}


def lifecycle_stage(spec):
    """Where on the corporate life cycle this company sits — the master diagnosis that decides
    which inputs are hard, where value should sit, and which adjustments are warranted (the
    6-stage Damodaran framing: start_up / young_growth / high_growth / mature_growth /
    mature_stable / decline). Defaults to mature when unspecified."""
    return str(spec.get("lifecycle_stage") or "mature").lower()


def _cum_discount(wacc_path):
    """Cumulative discount factors: df[t] = prod_{i<=t}(1+wacc_i)."""
    factors, running = [], 1.0
    for w in wacc_path:
        if not math.isfinite(w) or w <= -1:
            raise ValueError("discount rates must be finite and greater than -1")
        running *= (1.0 + w)
        if not math.isfinite(running) or running <= 0:
            raise ValueError("discount factors are outside the finite numeric range")
        factors.append(running)
    return factors


def _iso(value, name):
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError(f"timing.{name} must be an ISO date (YYYY-MM-DD)")


def resolve_timing(spec):
    """`timing` → (base_period_end, valuation_date, years_elapsed), or None when absent.

    The base period is the one `base_revenue` covers (the fiscal year or TTM window it ends
    on); the valuation date is the date of `current_price`. Year 1 is the twelve months after
    the base period, so the valuation date must fall inside it."""
    raw = spec.get("timing")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("timing must be a mapping of base_period_end and valuation_date")
    if raw.get("base_period_end") is None or raw.get("valuation_date") is None:
        raise ValueError("timing needs both base_period_end and valuation_date")
    base_end = _iso(raw["base_period_end"], "base_period_end")
    valued = _iso(raw["valuation_date"], "valuation_date")
    elapsed = (valued - base_end).days / 365.25
    if elapsed < 0:
        raise ValueError("timing.valuation_date precedes base_period_end")
    if elapsed >= 1:
        raise ValueError("the base period ended a year or more before the valuation date — "
                         "roll base_revenue forward to the latest TTM or fiscal year")
    return base_end, valued, elapsed


def value(spec):
    """Run the DCF. Returns a result dict. Raises ValueError on invalid input/model."""
    n = _horizon(spec)
    if n < 1:
        raise ValueError("years must be >= 1")

    base_rev = _number(spec["base_revenue"])
    growth = resolve_growth(spec, n)
    margin = resolve_margin(spec, n)
    if any(g < -1 for g in growth):
        raise ValueError("revenue growth cannot be below -100%")
    if spec.get("tax_rate") is None:
        raise ValueError("inputs need `tax_rate` — the effective tax rate must be sourced "
                         "(annual-report tax note), never defaulted")
    tax = _as_path(spec["tax_rate"], n, 0.0)
    shape = str(spec.get("model_shape") or "fcff").strip().lower()
    if shape not in _MODEL_SHAPES:
        raise ValueError(f"model_shape must be one of {', '.join(_MODEL_SHAPES)}")
    if shape == "fcff" and margin and min(margin) >= 0.95 and max(abs(x) for x in tax) <= 1e-12:
        raise ValueError("inputs look like an equity-shaped bank/NBFC/insurer model "
                         "(after-tax earnings stream with 100% margin); set `model_shape: equity` "
                         "and use cost of equity, not WACC")
    if spec.get("sales_to_capital") is None:
        raise ValueError("inputs need `sales_to_capital` — the reinvestment efficiency ratio "
                         "must be sourced (historical ΔRevenue ÷ reinvestment, or peer benchmark), "
                         "never defaulted")
    s2c = _as_path(spec["sales_to_capital"], n, 0.0)
    if any(not math.isfinite(ratio) or ratio <= 0 for ratio in s2c):
        raise ValueError("sales_to_capital must be finite and positive in every year")
    wacc, wacc_detail = resolve_wacc(spec, n)

    if spec.get("terminal_growth") is None:
        raise ValueError("inputs need `terminal_growth` — the perpetuity growth rate must be "
                         "sourced (capped at the risk-free rate), never defaulted")
    g_T = _number(spec["terminal_growth"])
    wacc_T = _number(spec.get("terminal_wacc", wacc[-1]))
    margin_T = _number(spec.get("terminal_margin", margin[-1]))
    tax_T = _number(spec.get("terminal_tax_rate", tax[-1]))
    if shape == "equity":
        if any(m != 1 for m in margin) or margin_T != 1:
            raise ValueError("equity model uses after-tax earnings: explicit and terminal margins must be 1")
        if any(t != 0 for t in tax) or tax_T != 0:
            raise ValueError("equity model uses after-tax earnings: explicit and terminal tax rates must be 0")
        if _number(spec.get("net_debt", 0.0)) != 0:
            raise ValueError("equity model already values equity cash flows: net_debt must be 0")
    # Default: convergence — no perpetual excess return. Damodaran's base case for a going concern is
    # ROIC -> cost of capital (competition erodes excess returns); set terminal_roic > WACC only when a
    # durable moat earns it. The excess return (ROIC - WACC), not g_T, is what actually moves terminal value.
    roic_T = _number(spec.get("terminal_roic", wacc_T))
    risk_free = spec.get("risk_free")
    if risk_free is not None:
        risk_free = _number(risk_free)
    if wacc_detail:
        derived_rf = wacc_detail["default_free_risk_free"]
        if risk_free is not None and abs(float(risk_free) - derived_rf) > 1e-9:
            raise ValueError("top-level `risk_free` disagrees with the default-free rate derived "
                             "inside `wacc_buildup`; use one consistent rate")
        risk_free = derived_rf

    if wacc_T <= g_T:
        raise ValueError(f"terminal WACC ({wacc_T}) must exceed terminal growth ({g_T}) "
                         "— Gordon terminal value is undefined/negative otherwise")
    if risk_free is not None and g_T > float(risk_free) + 1e-9:
        raise ValueError(f"terminal growth ({g_T}) must not exceed the default-free risk-free "
                         f"rate ({float(risk_free)}) in the cash-flow currency")
    if g_T < -1:
        raise ValueError("terminal growth cannot be below -100%")
    if roic_T <= 0:
        raise ValueError("terminal_roic must be > 0")

    df = _cum_discount(wacc)
    timing = resolve_timing(spec)
    roll = (1.0 + wacc[0]) ** timing[2] if timing else 1.0
    rows, pv_sum, prev_rev = [], 0.0, base_rev
    for t in range(n):
        rev = prev_rev * (1.0 + growth[t])
        ebit = rev * margin[t]
        nopat = ebit * (1.0 - tax[t])
        reinvest = (rev - prev_rev) / s2c[t]
        fcff = nopat - reinvest
        factor = df[t] / (roll * ((1.0 + wacc[t]) ** 0.5 if timing else 1.0))
        pv = fcff / factor
        pv_sum += pv
        rows.append({
            "year": t + 1,
            "growth": round(growth[t], 6),
            "revenue": round(rev, 4),
            "operating_margin": round(margin[t], 6),
            "ebit": round(ebit, 4),
            "tax_rate": round(tax[t], 6),
            "nopat": round(nopat, 4),
            "sales_to_capital": round(s2c[t], 6),
            "reinvestment": round(reinvest, 4),
            "fcff": round(fcff, 4),
            "discount_factor": round(factor, 6),
            "pv_fcff": round(pv, 4),
        })
        prev_rev = rev

    rev_T1 = prev_rev * (1.0 + g_T)
    nopat_T1 = rev_T1 * margin_T * (1.0 - tax_T)
    reinvest_rate_T = g_T / roic_T
    fcff_T1 = nopat_T1 * (1.0 - reinvest_rate_T)
    tv = fcff_T1 / (wacc_T - g_T)
    pv_tv = tv / df[-1] * roll

    ev = pv_sum + pv_tv
    net_debt = _number(spec.get("net_debt", 0.0))
    non_op_cash = _number(spec.get("non_operating_cash", 0.0))
    minority = _number(spec.get("minority_interest", 0.0))
    equity_going_concern = ev - net_debt + non_op_cash - minority

    # Two adjustments Damodaran keeps SEPARATE from the operating story, each applied only when
    # the diagnosis calls for it — never as a default knob:
    #   (1) failure/distress haircut — value the going concern, then accept it is worth only a
    #       recovery fraction (usually ~0) in the branch where the firm doesn't survive. Warranted
    #       when distress signals are present (negative earnings + heavy debt + reliance on external
    #       capital early in the life cycle, or a decline-phase firm). ~0 for a mature, cash-generative
    #       firm — leave failure_probability unset there.
    #   (2) complexity/governance discount — value operations cleanly, THEN haircut for things a DCF
    #       can't see: opaque cross-holdings, family-control wealth-transfer risk, pledging, political
    #       dependence (Adani: clean operating value first, then "a significant discount on intrinsic
    #       value"). Kept separate so the operating story is never quietly poisoned to express it.
    p_fail = _number(spec.get("failure_probability", 0.0))
    recovery = _number(spec.get("failure_recovery", 0.0))  # fraction of going-concern equity in failure
    cx = _number(spec.get("complexity_discount", 0.0))     # governance/cross-holding/control haircut
    if not 0.0 <= recovery <= 1.0:
        raise ValueError("failure_recovery must be between 0 and 1")
    if not 0.0 <= p_fail <= 1.0:
        raise ValueError("failure_probability must be between 0 and 1")
    if not 0.0 <= cx < 1.0:
        raise ValueError("complexity_discount must be between 0 and 1")
    equity_after_failure = equity_going_concern * ((1.0 - p_fail) + recovery * p_fail)
    equity = equity_after_failure * (1.0 - cx)

    shares = _number(spec["shares_outstanding"])
    if shares <= 0:
        raise ValueError("shares_outstanding must be > 0")
    per_share = equity / shares

    price = spec.get("current_price")
    mos = None
    if price is not None:
        price = _number(price)
        if price <= 0:
            raise ValueError("current_price must be positive when supplied")
        mos = per_share / price - 1.0
    computed = (pv_sum, pv_tv, ev, equity_going_concern, equity, per_share)
    if not all(math.isfinite(v) for v in computed) or (mos is not None and not math.isfinite(mos)):
        raise ValueError("valuation exceeds supported finite numeric range")

    tv_fraction = pv_tv / ev if ev else None

    return {
        "currency_unit": spec.get("currency_unit", "INR Crore"),
        "explicit_years": n,
        "assumptions": {
            "growth_path": [round(x, 6) for x in growth],
            "margin_path": [round(x, 6) for x in margin],
            "tax_path": [round(x, 6) for x in tax],
            "sales_to_capital_path": [round(x, 6) for x in s2c],
            "wacc_path": [round(x, 6) for x in wacc],
            "terminal_growth": g_T,
            "terminal_wacc": wacc_T,
            "terminal_margin": margin_T,
            "terminal_roic": roic_T,
            "terminal_excess_return": round(roic_T - wacc_T, 6),
            "terminal_reinvestment_rate": round(reinvest_rate_T, 6),
            "risk_free": risk_free,
            "wacc_buildup": wacc_detail,
            "lifecycle_stage": lifecycle_stage(spec),
            "model_shape": shape,
            "timing": ({"base_period_end": timing[0].isoformat(),
                        "valuation_date": timing[1].isoformat(),
                        "years_elapsed": round(timing[2], 6),
                        "convention": "mid-year flows, rolled forward to the valuation date"}
                       if timing else None),
        },
        "yearly": rows,
        "terminal_value": round(tv, 4),
        "pv_explicit_fcff": round(pv_sum, 4),
        "pv_terminal_value": round(pv_tv, 4),
        "enterprise_value": round(ev, 4),
        "net_debt": net_debt,
        "non_operating_cash": non_op_cash,
        "minority_interest": minority,
        "equity_value_going_concern": round(equity_going_concern, 4),
        "failure_probability": p_fail,
        "failure_recovery": recovery,
        "complexity_discount": cx,
        "equity_value": round(equity, 4),
        "shares_outstanding": shares,
        "intrinsic_value_per_share": round(per_share, 4),
        "current_price": price,
        "margin_of_safety": round(mos, 6) if mos is not None else None,
        "terminal_value_fraction": round(tv_fraction, 6) if tv_fraction is not None else None,
        "flags": _sanity_flags(spec, g_T, wacc_T, roic_T, ev, pv_sum, pv_tv,
                               risk_free, growth, margin, equity_going_concern, p_fail, cx,
                               wacc_detail) + ([] if timing else [_TIMING_UNADJUSTED]),
    }


_TIMING_UNADJUSTED = ("TIMING_UNADJUSTED: no `timing` block, so every cash flow is discounted from the "
                      "end of its year counted from the base period's end. Value is understated by "
                      "about (1+WACC)^(years since the base period + 0.5) — supply base_period_end and "
                      "valuation_date.")


_MODEL_SHAPES = ("fcff", "equity")


def _sanity_flags(spec, g_T, wacc_T, roic_T, ev, pv_explicit, pv_tv, risk_free, growth, margin,
                  equity_going_concern=None, p_fail=0.0, cx=0.0, wacc_detail=None):
    """Damodaran's reality checks — surfaced, not silently swallowed. Several are
    stage-aware: the same fact (e.g. value concentrated in the terminal year) is the
    *expected* shape for a young company and a *red flag* for a mature or declining one, so a
    fixed threshold mislabels exactly the cases that most need judgement.

    `model_shape` selects which questions apply. `fcff` (the default) is the firm-side model
    these checks were written for. `equity` is the standard adaptation for banks, NBFCs and
    insurers, where FCFF is ill-defined: capex and working capital bear no relation to what
    funds growth, so the run feeds an after-tax earnings stream and lets regulatory capital
    be the reinvestment. Margin has no meaning under that shape."""
    shape = str(spec.get("model_shape") or "fcff").strip().lower()
    if shape not in _MODEL_SHAPES:
        shape = "fcff"
    flags = []
    stage = lifecycle_stage(spec)
    young = stage in YOUNG_STAGES
    declining = "declin" in stage
    if risk_free is not None and g_T > float(risk_free) + 1e-9:
        flags.append(f"TERMINAL_GROWTH_ABOVE_RISKFREE: g_T={g_T:.3%} > risk_free={float(risk_free):.3%} "
                     "— no mature firm outgrows the economy forever; cap g_T at the default-free "
                     "rate in the cash-flow currency.")
    if ev <= 0:
        flags.append(f"NEGATIVE_ENTERPRISE_VALUE: EV={ev:.1f} — the explicit-period cash flows are deeply "
                     "negative (reinvestment too heavy / margins too thin for the growth assumed). The model "
                     "is not usable as-is; revisit sales-to-capital and the margin path before trusting any price.")
    else:
        frac = pv_tv / ev
        thresh = 0.90 if young else 0.75
        if pv_explicit < 0 or frac > thresh:
            if young:
                flags.append(f"TERMINAL_VALUE_HEAVY: {frac:.0%} of EV is terminal value — for a young company "
                             "this is EXPECTED (the cash flows live in the future, not today), not a defect; the "
                             "thing to stress-test is the growth duration and steady-state margin that build that "
                             "terminal, which the story-driver sensitivity does — not the WACC×g grid.")
            elif declining:
                flags.append(f"TERMINAL_VALUE_HEAVY: {frac:.0%} of EV is terminal value — for a DECLINING firm this "
                             "is a red flag: a declining business should derive value from near-term cash extraction "
                             "and asset/liquidation value, not a rich perpetuity. Re-check that terminal growth isn't "
                             "positive for a shrinking firm, and consider a liquidation/break-up cross-check.")
            else:
                flags.append(f"TERMINAL_VALUE_HEAVY: {frac:.0%} of EV is terminal value — for a going concern "
                             "this is normal, not a defect (most equity value is future cash flow). It means look "
                             "HARDER at the assumptions that BUILD the terminal: the high-growth path leading into "
                             "it and the terminal excess return (ROIC−WACC — the real driver; g_T barely moves it). "
                             "Stress-test those, don't distrust the model.")
    if declining and g_T > 0:
        flags.append(f"DECLINE_POSITIVE_TERMINAL_GROWTH: terminal growth {g_T:.1%} > 0 for a firm you classified as "
                     "declining — a shrinking business usually warrants g_T ≤ 0 and a liquidation cross-check.")
    if roic_T <= wacc_T + 1e-9:
        flags.append(f"NO_TERMINAL_EXCESS_RETURN: terminal_roic={roic_T:.2%} <= terminal_wacc={wacc_T:.2%} "
                     "— the firm creates no value in perpetuity (fine for a no-moat business; flag if you assumed a moat).")
    # `operating_margin` is an EBIT margin, and India's published feeds hand out an
    # "OPM %" struck at EBITDA — one keystroke apart, and the substitution overstates
    # every year's cash flow. A year-1 margin well above the current EBIT margin is
    # that signature; a real expansion story starts at today's margin and glides.
    cur_ebit = spec.get("current_ebit_margin")
    if shape == "equity":
        # An equity-shaped run feeds Net Income as "revenue", so margin is 1.0 by
        # construction and tax is already paid. The margin checks below read that as an
        # impossible business; they are the wrong questions for this shape, not answers.
        flags.append("EQUITY_MODEL_SHAPE: levers read as FCFE — `base_revenue` is an "
                     "after-tax earnings stream, `sales_to_capital` is marginal return on "
                     "reinvested equity, and `terminal_roic` is the sustainable return "
                     "whose spread over the cost of equity carries the value. Margin checks "
                     "are suppressed; confirm the discount rate is a cost of EQUITY, not WACC.")
    elif cur_ebit is None:
        flags.append("MARGIN_BASIS_UNCHECKED: no `current_ebit_margin` supplied, so the "
                     "EBITDA-in-an-EBIT-slot check did not run — pass the company's current "
                     "EBIT (PBIT / revenue) margin to enable it.")
    elif margin:
        cur_ebit = float(cur_ebit)
        excess = margin[0] - cur_ebit
        rel = excess / abs(cur_ebit) if cur_ebit else 0.0
        if excess > 0.0025 and rel > 0.20:
            flags.append(
                f"MARGIN_BASIS_SUSPECT: year-1 operating margin {margin[0]:.2%} is "
                f"{rel:+.0%} above the current EBIT margin {cur_ebit:.2%}. Check you have "
                f"not fed a published \"OPM %\", which is struck at EBITDA (pre-depreciation). "
                f"If the step-up is a real forecast, start the path at the current margin "
                f"and glide to the target.")

    if wacc_detail and wacc_detail.get("beta", 0.0) > 1.3:
        flags.append(f"BETA_LOOKS_LIKE_REGRESSION: beta={wacc_detail['beta']:.2f} — a beta this high is usually a raw "
                     "regression beta that a volatile share price inflates, not the business's risk. Damodaran uses a "
                     "bottom-up/sector beta (unlevered industry beta, relevered for this firm's debt). Confirm that's "
                     "what this is; a regression beta over-discounts and depresses value for no business reason.")
    if shape != "equity" and max(margin) > 0.40:
        flags.append(f"HIGH_MARGIN_ASSUMPTION: peak operating margin {max(margin):.0%} "
                     "— confirm a real peer has sustained this; few do. And remember a bigger target market "
                     "usually comes WITH lower margins + heavier reinvestment, not higher margins (SpaceX).")
    if max(growth) > 0.30:
        flags.append(f"HIGH_GROWTH_ASSUMPTION: peak revenue growth {max(growth):.0%} "
                     "— check it against TAM×share (not just history), and that reinvestment funds it. Don't add "
                     "a separate premium 'because India is a big market' — that belongs in growth, and is already here.")
    if equity_going_concern is not None and equity_going_concern <= 0 and (p_fail > 0 or cx > 0):
        flags.append("DISCOUNT_ON_NONPOSITIVE_EQUITY: a failure probability or complexity discount was applied "
                     "to a going-concern equity that is already ≤ 0 — multiplying a negative value makes it look "
                     "'less bad', which is meaningless. When operating value is negative the story itself is the "
                     "verdict (growth is destroying value / debt swamps thin operations); drop the haircuts and "
                     "cross-check against asset/liquidation or sum-of-parts value instead.")
    return flags


def sensitivity(spec, wacc_deltas=(-0.01, -0.005, 0.0, 0.005, 0.01),
                g_deltas=(-0.01, -0.005, 0.0, 0.005, 0.01)):
    """Per-share value across a *terminal* WACC x terminal-growth grid.

    This is a mechanical terminal-value check, not a coherent whole-company risk
    scenario: explicit-period discount rates and operating assumptions stay fixed.
    """
    explicit_wacc, buildup = resolve_wacc(spec, _horizon(spec))
    base_wacc_T = _number(spec.get("terminal_wacc", explicit_wacc[-1]))
    base_g_T = _number(spec["terminal_growth"])
    grid = {"wacc_axis": [round(base_wacc_T + d, 6) for d in wacc_deltas],
            "growth_axis": [round(base_g_T + d, 6) for d in g_deltas],
            "wacc_axis_label": "terminal WACC",
            "scope": "terminal_only",
            "note": "Mechanical terminal-value check; explicit WACC and operating paths are unchanged.",
            "cells": []}
    for wd in wacc_deltas:
        row = []
        for gd in g_deltas:
            # only the terminal discount rate shifts; explicit years keep their own path
            trial = dict(spec)
            trial["wacc"] = explicit_wacc
            if buildup:
                trial["risk_free"] = buildup["default_free_risk_free"]
            trial["terminal_wacc"] = base_wacc_T + wd
            trial["terminal_growth"] = base_g_T + gd
            try:
                row.append(round(value(trial)["intrinsic_value_per_share"], 2))
            except ValueError:
                row.append(None)  # wacc<=g cell
        grid["cells"].append(row)
    return grid


def story_sensitivity(spec, growth_shifts=(-0.04, -0.02, 0.0, 0.02, 0.04),
                      margin_shifts=(-0.03, 0.0, 0.03)):
    """Per-share values for specified operating scenarios: the whole
    revenue-growth path shifted by Δ (the rate path; duration is tested separately below)
    × the explicit operating-margin path and terminal margin shifted by Δ.
    Negative margins remain negative; a zero shift reproduces the base model.

    This is a conditional scenario grid, not a probability interval or proof that
    these inputs dominate every valuation. Compare it with discount-rate and terminal
    sensitivities. The duration cases extend the high-growth phase at the same rate;
    they do not establish which duration is supported by business evidence."""
    n = _horizon(spec)
    base_g = resolve_growth(spec, n)
    base_m = resolve_margin(spec, n)

    def trial(gd, md):
        s = dict(spec)
        s.pop("growth_glide", None)
        s.pop("margin_glide", None)
        s["revenue_growth"] = [g + gd for g in base_g]
        s["operating_margin"] = [m + md for m in base_m]
        s["terminal_margin"] = _number(spec.get("terminal_margin", base_m[-1])) + md
        try:
            return round(value(s)["intrinsic_value_per_share"], 2)
        except ValueError:
            return None

    grid = {
        "growth_shift_axis": [round(g, 4) for g in growth_shifts],
        "margin_shift_axis": [round(m, 4) for m in margin_shifts],
        "cells": [[trial(gd, md) for md in margin_shifts] for gd in growth_shifts],
        "note": "rows = revenue-growth-path shift, cols = explicit and terminal margin shift; "
                "conditional scenarios with other assumptions fixed, not a probability interval.",
    }

    g = spec.get("growth_glide")
    if g is not None and not isinstance(g, dict):
        raise ValueError("growth_glide must be a mapping")
    if g:
        dur = []
        base_yh = int(g.get("years_high", 1))
        for extra in (0, 2, 4):
            s = dict(spec)
            s["growth_glide"] = dict(g, years_high=min(n, base_yh + extra))
            try:
                dur.append({"extra_high_growth_years": extra,
                            "per_share": round(value(s)["intrinsic_value_per_share"], 2)})
            except ValueError:
                dur.append({"extra_high_growth_years": extra, "per_share": None})
        grid["duration"] = dur
    return grid


def reverse_dcf(spec, target_per_share=None, solve="growth", tol=1e-4, max_iter=200):
    """Solve the DCF backwards: hold every assumption fixed except ONE lever and find the
    value of that lever the market price already implies. Instead of "given my story, what
    is it worth?", it answers "given the price, what story must be true?" — Damodaran's
    favourite reality check. The whole chosen path is shifted by a constant Δ (so its shape /
    fade structure is preserved) until intrinsic value/share == target (default: current_price).

    solve = "growth"  -> implied revenue-growth path (and the implied N-year revenue CAGR)
    solve = "margin"  -> implied operating-margin path

    Returns {solved: True, lever, shift, implied_path, implied_year1, base_year1, ...} or
    {solved: False, lever, reason} when the target is not bracketed or convergence fails.
    A bracketed root need not be unique; an unbracketed search makes no valuation judgment.
    """
    if target_per_share is None:
        target_per_share = spec.get("current_price")
    if target_per_share in (None, 0):
        raise ValueError("reverse_dcf needs a target — set current_price or pass target_per_share")
    target = _number(target_per_share)
    tol = _number(tol)
    if target <= 0 or tol <= 0 or type(max_iter) is not int or max_iter < 1:
        raise ValueError("reverse target and tolerance must be positive; max_iter must be a positive integer")
    n = _horizon(spec)

    if solve == "growth":
        base = resolve_growth(spec, n)

        def make(delta):
            s = dict(spec)
            s.pop("growth_glide", None)
            s["revenue_growth"] = [g + delta for g in base]
            return s
        lo, hi, label = max(-0.30, -1.0 - min(base)), 0.60, "revenue growth"
    elif solve == "margin":
        base = resolve_margin(spec, n)

        def make(delta):
            s = dict(spec)
            s.pop("margin_glide", None)
            s["operating_margin"] = [m + delta for m in base]
            s["terminal_margin"] = _number(spec.get("terminal_margin", base[-1])) + delta
            return s
        lo, hi, label = -0.30, 0.40, "operating margin"
    else:
        raise ValueError("solve must be 'growth' or 'margin'")

    def f(delta):
        return _number(value(make(delta))["intrinsic_value_per_share"]) - target

    def unsolved(reason):
        return {"solved": False, "lever": label, "target_per_share": target,
                "reason": reason, "search_shift_bounds": [lo, hi]}

    flo, fhi = f(lo), f(hi)
    tolerance = tol * max(1.0, target)
    if abs(flo) <= tolerance:
        delta = lo
    elif abs(fhi) <= tolerance:
        delta = hi
    elif (flo > 0) == (fhi > 0):
        return unsolved("Target is not bracketed within the searched shift bounds. Endpoint values "
                        "lie on the same side of the target; interior or multiple roots remain possible.")
    else:
        for _ in range(max_iter):
            delta = (lo + hi) / 2.0
            residual = f(delta)
            if abs(residual) <= tolerance:
                break
            if (residual > 0) == (flo > 0):
                lo, flo = delta, residual
            else:
                hi, fhi = delta, residual
        else:
            return unsolved("Iteration limit reached before the valuation matched the target tolerance.")
    # Retain machine precision: rounding the solved input can undo convergence.
    implied = [b + delta for b in base]
    out = {
        "solved": True,
        "lever": label,
        "target_per_share": target,
        "shift": delta,
        "implied_path": implied,
        "implied_year1": implied[0],
        "base_year1": base[0],
    }
    if solve == "growth":
        def cagr(growth):
            return -1.0 if -1.0 in growth else math.expm1(sum(math.log1p(g) for g in growth) / n)
        implied_cagr = cagr(implied)
        base_cagr = cagr(base)
        out["implied_revenue_cagr"] = round(implied_cagr, 6)
        out["base_revenue_cagr"] = round(base_cagr, 6)
    return out


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if not isinstance(key, str):
            raise ValueError("model field names must be strings")
        if key in result:
            raise ValueError(f"duplicate model field: {key}")
        result[key] = value
    return result


def load_inputs(path):
    with open(path) as f:
        text = f.read()
    if path.endswith((".yml", ".yaml")):
        yaml = _need("yaml", "pyyaml")

        class ModelLoader(yaml.SafeLoader):
            pass

        def mapping(loader, node):
            # Flatten merges before validation so an inherited assumption cannot
            # silently be replaced by a second value in the same model mapping.
            loader.flatten_mapping(node)
            return _unique_fields((loader.construct_object(key, deep=True),
                                   loader.construct_object(value, deep=True))
                                  for key, value in node.value)

        ModelLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
        try:
            return yaml.load(text, Loader=ModelLoader)
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid YAML input: {exc}") from exc
    return json.loads(text, object_pairs_hook=_unique_fields)


def compute(spec, sensitivity_grid=False, story=False, reverse=False,
            reverse_solve="growth", reverse_target=None):
    """The DCF result plus whichever optional grids were asked for."""
    result = value(spec)
    result["gaps"] = []
    for requested, key, calculate, options in (
        (sensitivity_grid, "sensitivity", sensitivity, {}),
        (story, "story_sensitivity", story_sensitivity, {}),
        (reverse, "reverse_dcf", reverse_dcf,
         {"target_per_share": reverse_target, "solve": reverse_solve}),
    ):
        if not requested:
            continue
        try:
            result[key] = calculate(spec, **options)
        except (ValueError, ArithmeticError) as exc:
            result["gaps"].append(f"{key} unavailable: {exc}")
            result[key] = {"solved": False, "reason": str(exc)} if key == "reverse_dcf" else None
    return result


def _grid_range(grid):
    """(low, high) across a sensitivity grid's cells, or None when nothing solved."""
    cells = [c for row in (grid or {}).get("cells", []) for c in row if c is not None]
    return [min(cells), max(cells)] if cells else None


def _inr(v):
    """Indian-grouped integer rupees, or an em dash for an unsolved cell."""
    return "—" if v is None else spine.inr_group(v)


def grid_markdown(grid, row_axis, col_axis, corner, axis_kind="shift"):
    """Render a sensitivity grid as a GFM table, base cell bolded.

    The report pastes this verbatim. Engine output is never retyped into a template.
    `axis_kind` is "shift" for a delta axis (signed, zero labelled `base`) or "level"
    for an absolute-rate axis.
    """
    if not grid or not grid.get("cells"):
        return None
    rows, cols = grid.get(row_axis) or [], grid.get(col_axis) or []
    cells = grid["cells"]
    if axis_kind == "shift":
        # a delta axis: signed, and the zero point is the story as written
        fmt = lambda v: "base" if abs(v) < 1e-9 else f"{v:+.0%}"
    else:
        # a level axis: the absolute rate, to one decimal (0.5% steps are common)
        fmt = lambda v: f"{v * 100:.1f}%"
    # the base row/col is the zero-shift one for a shift axis, else the middle
    def base_i(axis):
        if axis_kind == "shift" and 0.0 in axis:
            return axis.index(0.0)
        return len(axis) // 2
    br, bc = base_i(rows), base_i(cols)
    head = [corner] + [f"**{fmt(c)}**" if i == bc else fmt(c) for i, c in enumerate(cols)]
    out = ["| " + " | ".join(head) + " |",
           "|" + "---|" * len(head)]
    for i, r in enumerate(rows):
        label = f"**{fmt(r)}**" if i == br else fmt(r)
        vals = []
        for j, v in enumerate(cells[i] if i < len(cells) else []):
            t = _inr(v)
            vals.append(f"**{t}**" if (i == br and j == bc) else t)
        out.append("| " + " | ".join([label] + vals) + " |")
    return "\n".join(out)


MARKET_INDEX = "NIFTY 500"
_NO_BUILDUP = "inputs use an explicit `wacc`; the market view needs `wacc_buildup`"
# The buildup fields get_risk_inputs serves, with how far a run may sit from today's figure.
# The Damodaran fields are one dated vintage and must match it; the yield moves daily.
_RISK_FIELDS = (("government_bond_yield", ("india_10y", "value"), 0.0025),
                ("sovereign_default_spread", ("country_risk", "default_spread"), 1e-6),
                ("mature_erp", ("country_risk", "mature_erp"), 1e-6),
                ("country_risk_premium", ("country_risk", "country_risk_premium"), 1e-6))


def market_growth_path(pe, pb, dy_pct, risk_free, consensus=None, years_high=5, years=10):
    """The index's earnings growth, year by year. With `consensus` (analysts' expected growth
    for the next fiscal years), those years come first and their compound rate runs on to
    `years_high`; without it, the sustainable ROE x (1 - payout) runs for `years_high`. Either
    way growth then fades linearly to the default-free `risk_free` by `years`."""
    if consensus:
        compound = math.prod(1.0 + g for g in consensus) ** (1.0 / len(consensus)) - 1.0
        high = list(consensus) + [compound] * max(0, years_high - len(consensus))
    else:
        high = [pb / pe * (1.0 - dy_pct / 100.0 * pe)] * years_high
    last = high[-1]
    return high + [last + (risk_free - last) * (i + 1) / (years - len(high))
                   for i in range(years - len(high))]


def _index_worth(pe, pb, dy_pct, rf, r, consensus=None):
    """Value per unit of index price at discount rate `r` (see implied_market_return)."""
    roe = pb / pe
    earn, pv, disc = 1.0 / pe, 0.0, 1.0
    for g in market_growth_path(pe, pb, dy_pct, rf, consensus):
        earn *= 1.0 + g
        disc *= 1.0 + r
        pv += earn * (1.0 - g / roe) / disc
    return pv + earn * (1.0 + rf) * (1.0 - rf / roe) / (r - rf) / disc


def implied_market_return(pe, pb, dy_pct, risk_free, consensus=None):
    """The annual return today's index level implies — Damodaran's implied-ERP solve.

    Per unit of index price: earnings 1/PE and ROE = PB/PE; growth follows
    `market_growth_path` (analysts' consensus when supplied, else the index's sustainable
    growth). Each year's cash to equity is earnings x (1 - g/ROE); after year ten it grows at
    `risk_free` forever with ROE held. Returns the rate that equates those cash flows to the
    price, or None when the inputs cannot support one."""
    if not all(spine.is_finite(v) for v in (pe, pb, dy_pct, risk_free)):
        return None
    if pe <= 0 or pb <= 0 or dy_pct < 0:
        return None
    worth = lambda r: _index_worth(pe, pb, dy_pct, risk_free, r, consensus)  # noqa: E731
    lo, hi = risk_free + 1e-4, 0.5
    if worth(lo) < 1.0 or worth(hi) > 1.0:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2.0
        lo, hi = (mid, hi) if worth(mid) > 1.0 else (lo, mid)
    return round((lo + hi) / 2.0, 6)


def _risk_provenance(buildup, risk_env):
    """Gaps for every market input in `wacc_buildup` that does not match `get_risk_inputs`."""
    if not risk_env.get("ok"):
        return ["discount-rate inputs not verified: get_risk_inputs unavailable "
                f"({'; '.join(risk_env.get('gaps') or ['no data'])})"]
    data, gaps = risk_env.get("data") or {}, []
    for field, (block, key), tol in _RISK_FIELDS:
        if field not in buildup:
            continue
        sourced = (data.get(block) or {}).get(key)
        given = buildup[field]
        if not spine.is_finite(sourced):
            gaps.append(f"wacc_buildup.{field} not verified: get_risk_inputs has no {block}.{key}")
        elif not spine.is_finite(given) or abs(given - sourced) > tol:
            gaps.append(f"wacc_buildup.{field}={given} is not get_risk_inputs' {sourced} — "
                        "an unsourced discount-rate input")
    return gaps


def market_view(inputs, result, risk_env, index_env, consensus_env):
    """The same company valued at the return the Indian market itself implies today.

    The buildup's total equity premium (mature ERP + country premium) is a view on what
    Indian equities should earn; the index price implies its own. Rescaling both premium
    parts to the market-implied total (so `lambda_country` still applies) and shifting the
    terminal rate by the same change separates "is this stock dear against the market" from
    "is the market dear". The market's growth is analysts' consensus (`consensus_env`, from
    `estimates.market`) and falls back to the index's own sustainable growth when that is
    unavailable. Returns (block, gaps)."""
    buildup = inputs.get("wacc_buildup")
    if not isinstance(buildup, dict):
        return {"skipped": _NO_BUILDUP}, []
    row = ((index_env.get("data") or {}).get("indices") or {}).get(MARKET_INDEX) or {}
    rf = result["assumptions"]["risk_free"]
    gaps = []
    consensus = (consensus_env.get("data") or {}).get("growth") if consensus_env.get("ok") else None
    if consensus is None:
        gaps.append("market growth from the index's own fundamentals: analyst consensus "
                    f"unavailable ({'; '.join(consensus_env.get('gaps') or ['no data'])})")
    coe_mkt = implied_market_return(row.get("pe"), row.get("pb"), row.get("dy"), rf, consensus)
    country = (risk_env.get("data") or {}).get("country_risk") or {}
    mature, crp = country.get("mature_erp"), country.get("country_risk_premium")
    if coe_mkt is None or not spine.is_finite(mature) or not spine.is_finite(crp):
        reason = (f"{MARKET_INDEX} P/E, P/B and dividend yield did not yield an implied return"
                  if coe_mkt is None else "sourced mature ERP and country premium unavailable")
        return {"skipped": reason}, gaps + [f"market view not computed: {reason}"]
    implied_erp = coe_mkt - rf
    scale = implied_erp / (mature + crp)
    trial = dict(inputs, wacc_buildup=dict(buildup, mature_erp=mature * scale,
                                           country_risk_premium=crp * scale))
    if inputs.get("terminal_wacc") is not None:
        shift = (resolve_wacc(trial, 1)[1]["wacc"]
                 - result["assumptions"]["wacc_buildup"]["wacc"])
        trial["terminal_wacc"] = _number(inputs["terminal_wacc"]) + shift
    try:
        rebased = value(trial)
    except ValueError as exc:
        return {"skipped": str(exc)}, gaps + [f"market view not computed: {exc}"]
    method_coe = result["assumptions"]["wacc_buildup"]["cost_of_equity"]
    beta_one = rf + mature + crp
    return {
        "index": MARKET_INDEX,
        "index_pe": row.get("pe"), "index_pb": row.get("pb"), "index_dy_pct": row.get("dy"),
        "index_source": index_env.get("source"), "index_fetched_at": index_env.get("fetched_at"),
        "market_growth_basis": "analyst consensus" if consensus else "index fundamentals",
        "market_growth_path": [round(g, 6) for g in market_growth_path(
            row["pe"], row["pb"], row["dy"], rf, consensus)],
        "consensus_coverage": (consensus_env.get("data") or {}).get("coverage") if consensus else None,
        "market_implied_return": coe_mkt,
        "market_implied_erp": round(implied_erp, 6),
        "method_erp": round(mature + crp, 6),
        "method_cost_of_equity": method_coe,
        "cost_of_equity": rebased["assumptions"]["wacc_buildup"]["cost_of_equity"],
        "terminal_wacc": rebased["assumptions"]["terminal_wacc"],
        "intrinsic_value_per_share": rebased["intrinsic_value_per_share"],
        "margin_of_safety": rebased["margin_of_safety"],
        "index_value_to_price_at_method_rate": round(
            _index_worth(row["pe"], row["pb"], row["dy"], rf, beta_one, consensus), 4),
    }, gaps


def run(ticker, inputs, relative=None, sensitivity=False, story=False, reverse=False,
        reverse_solve="growth", reverse_target=None, date=None):
    """Intrinsic value and relative value as one envelope.

    The full result JSON is bulk: it is written to `dcf-<hash>.json` in the ticker's run-day
    folder and `data` carries the headline numbers plus `dcf_path`. `relative` is the
    optional figures mapping `relval.relative_read` reads — omit it and only the DCF
    comes back. `inputs` is the mapping or the path to its YAML/JSON file. Inputs the model
    rejects are a labelled gap, never an exception.
    """
    if isinstance(inputs, str):
        try:
            inputs = load_inputs(inputs)
        except (OSError, ValueError) as exc:
            return spine.envelope(False, _SOURCE, {"ticker": ticker},
                                  [f"dcf inputs file unreadable: {exc}"])
    if not isinstance(inputs, dict) or not inputs:
        return spine.envelope(False, _SOURCE, {"ticker": ticker},
                              ["dcf inputs missing or not a mapping"])
    try:
        result = compute(inputs, sensitivity_grid=sensitivity, story=story,
                         reverse=reverse, reverse_solve=reverse_solve,
                         reverse_target=reverse_target)
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        return spine.envelope(False, _SOURCE, {"ticker": ticker},
                              [f"dcf inputs rejected: {exc}"])

    gaps = list(result.get("gaps", []))
    if result["assumptions"]["timing"] is None:
        gaps.append("cash-flow timing not supplied: values discounted from the base period's end, "
                    "not the valuation date (TIMING_UNADJUSTED)")
    view = {"skipped": _NO_BUILDUP}
    if isinstance(inputs.get("wacc_buildup"), dict):
        risk_env = _risk.fetch()
        gaps.extend(_risk_provenance(inputs["wacc_buildup"], risk_env))
        view, view_gaps = market_view(inputs, result, risk_env,
                                      _market.indices(names=[MARKET_INDEX]), _estimates.market())
        gaps.extend(view_gaps)
    result["market_view"] = view
    read = None
    if relative is not None:
        if isinstance(relative, dict):
            read = relval.relative_read(relative)
        else:
            gaps.append("relative valuation skipped: `relative` is not a mapping")

    result["inputs"] = inputs
    result["relative"] = read
    path = None
    try:
        prefix = os.path.join(paths.stock_dir(ticker, date), "dcf")
        path = spine.publish_evidence(prefix, ".json",
            lambda fh: json.dump(result, fh, indent=2, sort_keys=True, allow_nan=False))
    except (OSError, ValueError, TypeError) as exc:
        gaps.append(f"could not persist DCF evidence: {type(exc).__name__}")

    data = {k: result[k] for k in (
        "currency_unit", "explicit_years", "enterprise_value", "equity_value",
        "shares_outstanding", "intrinsic_value_per_share", "current_price",
        "margin_of_safety", "terminal_value_fraction", "flags")}
    # The resolved levers travel in the digest, not only into dcf.json, so a reader can see
    # which discount rate, tax, reinvestment and terminal growth actually built this value.
    a = result["assumptions"]
    data["assumptions"] = {k: a[k] for k in (
        "wacc_path", "wacc_buildup", "tax_path", "sales_to_capital_path",
        "terminal_growth", "terminal_wacc", "terminal_roic", "timing")}
    try:
        data["ticker"] = paths.ticker_key(ticker)
    except ValueError:
        data["ticker"] = None
    data["relative"] = read
    data["market_view"] = view
    data["dcf_path"] = path
    if sensitivity:
        g = result.get("sensitivity")
        data["sensitivity_range"] = _grid_range(g)
        data["sensitivity_md"] = grid_markdown(
            g, "wacc_axis", "growth_axis", "terminal WACC ↓ / terminal g →",
            axis_kind="level")
    if story:
        g = result.get("story_sensitivity")
        data["story_range"] = _grid_range(g)
        data["story_sensitivity_md"] = grid_markdown(
            g, "growth_shift_axis", "margin_shift_axis",
            "growth shift ↓ / margin shift →")
    if reverse:
        data["reverse_dcf"] = result.get("reverse_dcf")
    return spine.envelope(True, _SOURCE, data, gaps)
