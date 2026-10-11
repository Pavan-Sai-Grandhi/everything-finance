#!/usr/bin/env python3
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
the same count unit (Crore) so per_share comes out in ₹. Run with --selftest for a
worked check, or feed a YAML/JSON input file (see
skills/valuation-analysis/assets/dcf-inputs.example.yml).

Usage:
  PYTHONPATH=<plugin> python3 -m finance.compute.dcf --inputs dcf-inputs.yml \
      --out artifacts/stocks/RELIANCE/2026-06-12/dcf.json
  PYTHONPATH=<plugin> python3 -m finance.compute.dcf --selftest
Exit: 0 = valued, 2 = input/usage error, 3 = model-invalid (e.g. wacc<=g).

Reached through: run_dcf, which pairs this with the relative read from `relval.py`.
"""
import argparse
import json
import math
import os
import sys
import tempfile

from finance import paths, spine
from finance.compute import relval
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
    rows, pv_sum, prev_rev = [], 0.0, base_rev
    for t in range(n):
        rev = prev_rev * (1.0 + growth[t])
        ebit = rev * margin[t]
        nopat = ebit * (1.0 - tax[t])
        reinvest = (rev - prev_rev) / s2c[t]
        fcff = nopat - reinvest
        pv = fcff / df[t]
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
            "discount_factor": round(df[t], 6),
            "pv_fcff": round(pv, 4),
        })
        prev_rev = rev

    rev_T1 = prev_rev * (1.0 + g_T)
    nopat_T1 = rev_T1 * margin_T * (1.0 - tax_T)
    reinvest_rate_T = g_T / roic_T
    fcff_T1 = nopat_T1 * (1.0 - reinvest_rate_T)
    tv = fcff_T1 / (wacc_T - g_T)
    pv_tv = tv / df[-1]

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
                               wacc_detail),
    }


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


SELFTEST_SPEC = {
    "currency_unit": "INR Crore",
    "years": 10,
    "base_revenue": 1000.0,
    "growth_glide": {"initial": 0.15, "fade_to": 0.04, "years_high": 3},
    "margin_glide": {"start": 0.12, "target": 0.18, "year_target": 5},
    "tax_rate": 0.25,
    "sales_to_capital": 2.0,
    "wacc": 0.11,
    "terminal_growth": 0.04,
    "terminal_roic": 0.13,
    "risk_free": 0.07,
    "net_debt": 500.0,
    "non_operating_cash": 100.0,
    "shares_outstanding": 100.0,
    "current_price": 60.0,
}


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
    if v is None:
        return "—"
    n = int(round(v))
    sign, n = ("-", -n) if n < 0 else ("", n)
    s = str(n)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join(([head] if head else []) + parts + [tail])
    return sign + s


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


def run(ticker, inputs, relative=None, sensitivity=False, story=False, reverse=False,
        reverse_solve="growth", reverse_target=None, date=None):
    """Intrinsic value and relative value as one envelope.

    The full result JSON is bulk: it is written to `dcf-<hash>.json` in the ticker's run-day
    folder and `data` carries the headline numbers plus `dcf_path`. `relative` is the
    optional figures mapping `relval.relative_read` reads — omit it and only the DCF
    comes back. Inputs the model rejects are a labelled gap, never an exception.
    """
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
    read = None
    if relative is not None:
        if isinstance(relative, dict):
            read = relval.relative_read(relative)
        else:
            gaps.append("relative valuation skipped: `relative` is not a mapping")

    # A same-day call from another session is not a revision of this valuation.
    # Preserve each exact input/result pair; the author cites any intentional revisions.
    result["revisions"] = []  # compatibility field; never infer lineage by filename
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
        "terminal_growth", "terminal_wacc", "terminal_roic")}
    try:
        data["ticker"] = paths.ticker_key(ticker)
    except ValueError:
        data["ticker"] = None
    data["relative"] = read
    data["dcf_path"] = path
    data["revisions"] = result["revisions"]
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


def main():
    ap = argparse.ArgumentParser(description="Story-driven FCFF DCF (Damodaran).")
    ap.add_argument("--inputs",
                    help="YAML/JSON input file "
                         "(see skills/valuation-analysis/assets/dcf-inputs.example.yml)")
    ap.add_argument("--out", help="write result JSON here")
    ap.add_argument("--sensitivity", action="store_true",
                    help="also emit a terminal-WACC x terminal-growth check")
    ap.add_argument("--story", action="store_true",
                    help="also emit the story-driver grid (growth x steady-state margin) — the "
                         "headline range for a growth company; far higher leverage than the terminal check")
    ap.add_argument("--reverse", action="store_true",
                    help="also solve the DCF backwards: what assumption does current_price imply?")
    ap.add_argument("--reverse-solve", choices=["growth", "margin"], default="growth",
                    help="which lever the reverse DCF solves for (default growth)")
    ap.add_argument("--reverse-target", type=float,
                    help="target price/share for the reverse DCF (default: spec current_price)")
    ap.add_argument("--selftest", action="store_true", help="run the built-in worked example")
    args = ap.parse_args()

    if args.inputs and args.out:
        same_path = os.path.realpath(args.inputs) == os.path.realpath(args.out)
        if os.path.exists(args.inputs) and os.path.exists(args.out):
            same_path = same_path or os.path.samefile(args.inputs, args.out)
        if same_path:
            ap.error("--out must not overwrite the input file")
    if args.selftest:
        spec = SELFTEST_SPEC
    elif args.inputs:
        try:
            spec = load_inputs(args.inputs)
        except (OSError, ValueError) as exc:
            ap.error(f"could not read inputs: {exc}")
    else:
        ap.error("need --inputs <file> or --selftest")

    try:
        result = compute(spec,
                         sensitivity_grid=args.sensitivity or args.selftest,
                         story=args.story or args.selftest,
                         reverse=args.reverse or args.selftest,
                         reverse_solve=args.reverse_solve,
                         reverse_target=args.reverse_target)
    except (ValueError, KeyError, TypeError, ZeroDivisionError, OverflowError) as e:
        print(f"MODEL-INVALID: {e}", file=sys.stderr)
        sys.exit(3)

    pending = None
    try:
        out = json.dumps(result, indent=2, allow_nan=False)
        if args.out:
            directory = os.path.dirname(os.path.abspath(args.out))
            os.makedirs(directory, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", dir=directory, encoding="utf-8",
                                             delete=False) as stream:
                pending = stream.name
                stream.write(out + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(pending, args.out)
            pending = None
            print(f"wrote {args.out}")
        else:
            print(out)
    except (OSError, ValueError, TypeError) as exc:
        ap.error(f"could not publish result: {exc}")
    finally:
        if pending and os.path.exists(pending):
            os.unlink(pending)

    ps = result["intrinsic_value_per_share"]
    for gap in result.get("gaps", []):
        print(f"Data gap: {gap}", file=sys.stderr)
    cu = result["currency_unit"].split()[0]
    print(f"\nIntrinsic value/share: {cu} {ps:,.2f}", file=sys.stderr)
    if result.get("failure_probability") or result.get("complexity_discount"):
        gc = result["equity_value_going_concern"] / result["shares_outstanding"]
        bits = []
        if result.get("failure_probability"):
            bits.append(f"{result['failure_probability']:.0%} failure prob")
        if result.get("complexity_discount"):
            bits.append(f"{result['complexity_discount']:.0%} complexity/governance discount")
        print(f"  (going concern {cu} {gc:,.2f}/sh, haircut for {', '.join(bits)})", file=sys.stderr)
    if result["margin_of_safety"] is not None:
        print(f"Margin of safety vs price: {result['margin_of_safety']:+.1%}", file=sys.stderr)
    if result["terminal_value_fraction"] is not None:
        print(f"Terminal value = {result['terminal_value_fraction']:.0%} of EV", file=sys.stderr)
    st = result.get("story_sensitivity")
    if st and st["cells"]:
        flat = [c for row in st["cells"] for c in row if c is not None]
        if flat:
            print(f"Story-driver range (growth×margin): {cu} {min(flat):,.0f} – {cu} {max(flat):,.0f} "
                  "(the levers that actually move a growth stock)", file=sys.stderr)
    rev = result.get("reverse_dcf")
    if rev:
        if rev.get("solved"):
            if rev["lever"] == "revenue growth":
                print(f"Reverse DCF: price ₹{rev['target_per_share']:,.0f} implies "
                      f"{rev['implied_year1']:.1%} year-1 growth (~{rev['implied_revenue_cagr']:.1%} "
                      f"{result['explicit_years']}y revenue CAGR) vs your {rev['base_year1']:.1%} "
                      f"base — a {rev['shift']:+.1%} shift.", file=sys.stderr)
            else:
                print(f"Reverse DCF: price ₹{rev['target_per_share']:,.0f} implies a {rev['shift']:+.1%} "
                      f"shift in operating margin (year-1 {rev['implied_year1']:.1%} vs base "
                      f"{rev['base_year1']:.1%}).", file=sys.stderr)
        else:
            print(f"Reverse DCF: {rev['reason']}", file=sys.stderr)


if __name__ == "__main__":
    main()
