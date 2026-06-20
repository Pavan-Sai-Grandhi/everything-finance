#!/usr/bin/env python3
"""Story-driven FCFF DCF valuation engine (everything-finance).

Faithful to Aswath Damodaran's free-cash-flow-to-firm model (The Little Book of
Valuation / Narrative and Numbers). The engine does ONLY arithmetic on inputs you
supply — it never invents a number. Every input must trace to a sourced figure
(screener.in financials, the annual report, an exchange filing) so the output is
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
worked check, or feed a YAML/JSON input file (see assets/dcf-inputs.example.yml).

Usage:
  python3 dcf.py --inputs dcf-inputs.yml --out artifacts/stocks/RELIANCE/2026-06-12/dcf.json
  python3 dcf.py --selftest
Exit: 0 = valued, 2 = input/usage error, 3 = model-invalid (e.g. wacc<=g).
"""
import argparse
import json
import os
import subprocess
import sys
from functools import reduce


def _need(mod, pip_name=None):
    try:
        return __import__(mod)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                               "--break-system-packages", pip_name or mod])
        return __import__(mod)


# ----------------------------------------------------------------------------- helpers

def _as_path(value, n, default):
    """Expand a scalar OR a list into an N-length list. Last value carries forward."""
    if value is None:
        value = default
    if isinstance(value, (int, float)):
        return [float(value)] * n
    seq = [float(x) for x in value]
    if len(seq) == 0:
        return [float(default)] * n
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
    if g:
        hi = float(g["initial"])
        lo = float(g.get("fade_to", hi))
        yh = int(g.get("years_high", 1))
        yh = max(0, min(yh, n))
        head = [hi] * yh
        tail = _ramp(hi, lo, n - yh) if n - yh > 0 else []
        return (head + tail)[:n]
    raise ValueError("inputs need either `revenue_growth` or `growth_glide`")


def resolve_margin(spec, n):
    """Operating-margin path. Either explicit `operating_margin` (scalar/list) or a glide
    {start, target, year_target}: ramp start->target by year_target, hold target after."""
    if "operating_margin" in spec and spec["operating_margin"] is not None:
        return _as_path(spec["operating_margin"], n, 0.0)
    m = spec.get("margin_glide")
    if m:
        start = float(m["start"])
        target = float(m["target"])
        yt = int(m.get("year_target", n))
        yt = max(1, min(yt, n))
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
        return _as_path(spec["wacc"], n, 0.11), None
    b = spec.get("wacc_buildup")
    if not b:
        return _as_path(0.11, n, 0.11), None
    rf = float(b["risk_free"])
    beta = float(b.get("beta", 1.0))
    mature_erp = float(b["mature_erp"])
    crp = float(b.get("country_risk_premium", 0.0))
    lam = float(b.get("lambda_country", 1.0))
    coe = rf + beta * mature_erp + lam * crp
    erp_total = mature_erp + lam * crp
    cod = float(b.get("cost_of_debt_pretax", coe))
    tax = float(b.get("tax_rate", spec.get("tax_rate", 0.25)) if not isinstance(
        spec.get("tax_rate"), (list, tuple)) else b.get("tax_rate", 0.25))
    we = float(b.get("equity_weight", 1.0))
    wd = float(b.get("debt_weight", 1.0 - we))
    wacc = we * coe + wd * cod * (1.0 - tax)
    detail = {"cost_of_equity": round(coe, 6), "after_tax_cost_of_debt": round(cod * (1 - tax), 6),
              "beta": round(beta, 6), "lambda_country": round(lam, 6),
              "country_risk_loaded": round(lam * crp, 6),
              "equity_risk_premium": round(erp_total, 6), "wacc": round(wacc, 6)}
    return _as_path(wacc, n, wacc), detail


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
        running *= (1.0 + w)
        factors.append(running)
    return factors


# ----------------------------------------------------------------------------- core

def value(spec):
    """Run the DCF. Returns a result dict. Raises ValueError on invalid input/model."""
    n = int(spec.get("years", 10))
    if n < 1:
        raise ValueError("years must be >= 1")

    base_rev = float(spec["base_revenue"])
    growth = resolve_growth(spec, n)
    margin = resolve_margin(spec, n)
    tax = _as_path(spec.get("tax_rate", 0.25), n, 0.25)
    s2c = _as_path(spec.get("sales_to_capital"), n, None) if spec.get("sales_to_capital") is not None \
        else _as_path(spec.get("sales_to_capital", 2.0), n, 2.0)
    wacc, wacc_detail = resolve_wacc(spec, n)

    # terminal assumptions
    g_T = float(spec.get("terminal_growth", 0.04))
    wacc_T = float(spec.get("terminal_wacc", wacc[-1]))
    margin_T = float(spec.get("terminal_margin", margin[-1]))
    tax_T = float(spec.get("terminal_tax_rate", tax[-1]))
    # Default: convergence — no perpetual excess return. Damodaran's base case for a going concern is
    # ROIC -> cost of capital (competition erodes excess returns); set terminal_roic > WACC only when a
    # durable moat earns it. The excess return (ROIC - WACC), not g_T, is what actually moves terminal value.
    roic_T = float(spec.get("terminal_roic", wacc_T))
    risk_free = spec.get("risk_free")  # optional, for the g<=rf sanity flag

    if wacc_T <= g_T:
        raise ValueError(f"terminal WACC ({wacc_T}) must exceed terminal growth ({g_T}) "
                         "— Gordon terminal value is undefined/negative otherwise")
    if roic_T <= 0:
        raise ValueError("terminal_roic must be > 0")

    df = _cum_discount(wacc)
    rows, pv_sum, prev_rev = [], 0.0, base_rev
    for t in range(n):
        rev = prev_rev * (1.0 + growth[t])
        ebit = rev * margin[t]
        nopat = ebit * (1.0 - tax[t])
        reinvest = (rev - prev_rev) / s2c[t] if s2c[t] else 0.0
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

    # terminal value
    rev_T1 = prev_rev * (1.0 + g_T)
    nopat_T1 = rev_T1 * margin_T * (1.0 - tax_T)
    reinvest_rate_T = g_T / roic_T
    fcff_T1 = nopat_T1 * (1.0 - reinvest_rate_T)
    tv = fcff_T1 / (wacc_T - g_T)
    pv_tv = tv / df[-1]

    ev = pv_sum + pv_tv
    net_debt = float(spec.get("net_debt", 0.0))
    non_op_cash = float(spec.get("non_operating_cash", 0.0))
    minority = float(spec.get("minority_interest", 0.0))
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
    p_fail = float(spec.get("failure_probability", 0.0))
    recovery = float(spec.get("failure_recovery", 0.0))  # fraction of going-concern equity in failure
    cx = float(spec.get("complexity_discount", 0.0))     # governance/cross-holding/control haircut
    if not 0.0 <= p_fail <= 1.0:
        raise ValueError("failure_probability must be between 0 and 1")
    if not 0.0 <= cx < 1.0:
        raise ValueError("complexity_discount must be between 0 and 1")
    equity_after_failure = equity_going_concern * ((1.0 - p_fail) + recovery * p_fail)
    equity = equity_after_failure * (1.0 - cx)

    shares = float(spec["shares_outstanding"])
    if shares <= 0:
        raise ValueError("shares_outstanding must be > 0")
    per_share = equity / shares

    price = spec.get("current_price")
    mos = None
    if price not in (None, 0):
        mos = per_share / float(price) - 1.0

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


def _sanity_flags(spec, g_T, wacc_T, roic_T, ev, pv_explicit, pv_tv, risk_free, growth, margin,
                  equity_going_concern=None, p_fail=0.0, cx=0.0, wacc_detail=None):
    """Damodaran's reality checks — surfaced, not silently swallowed. Several are
    stage-aware: the same fact (e.g. value concentrated in the terminal year) is the
    *expected* shape for a young company and a *red flag* for a mature or declining one, so a
    fixed threshold mislabels exactly the cases that most need judgement."""
    flags = []
    stage = lifecycle_stage(spec)
    young = stage in YOUNG_STAGES
    declining = "declin" in stage
    if risk_free is not None and g_T > float(risk_free) + 1e-9:
        flags.append(f"TERMINAL_GROWTH_ABOVE_RISKFREE: g_T={g_T:.3%} > risk_free={float(risk_free):.3%} "
                     "— no mature firm outgrows the economy forever; cap g_T at the risk-free rate. "
                     "(In a ₹ model the binding number is the ~6.5–7% rupee G-sec, not 4%.)")
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
    if wacc_detail and wacc_detail.get("beta", 0.0) > 1.3:
        flags.append(f"BETA_LOOKS_LIKE_REGRESSION: beta={wacc_detail['beta']:.2f} — a beta this high is usually a raw "
                     "regression beta that a volatile share price inflates, not the business's risk. Damodaran uses a "
                     "bottom-up/sector beta (unlevered industry beta, relevered for this firm's debt). Confirm that's "
                     "what this is; a regression beta over-discounts and depresses value for no business reason.")
    if max(margin) > 0.40:
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
    """Per-share intrinsic value across a WACC x terminal-growth grid (Damodaran's
    'show the range, not a false-precision point estimate')."""
    base_wacc_T = float(spec.get("terminal_wacc", _as_path(spec.get("wacc", 0.11),
                        int(spec.get("years", 10)), 0.11)[-1]))
    base_g_T = float(spec.get("terminal_growth", 0.04))
    grid = {"wacc_axis": [], "growth_axis": [round(base_g_T + d, 6) for d in g_deltas], "cells": []}
    grid["wacc_axis"] = [round(base_wacc_T + d, 6) for d in wacc_deltas]
    for wd in wacc_deltas:
        row = []
        for gd in g_deltas:
            trial = dict(spec)
            trial["terminal_wacc"] = base_wacc_T + wd
            trial["terminal_growth"] = base_g_T + gd
            # only the terminal discount rate shifts; explicit years keep their own path
            try:
                row.append(round(value(trial)["intrinsic_value_per_share"], 2))
            except ValueError:
                row.append(None)  # wacc<=g cell
        grid["cells"].append(row)
    return grid


def story_sensitivity(spec, growth_shifts=(-0.04, -0.02, 0.0, 0.02, 0.04),
                      margin_shifts=(-0.03, 0.0, 0.03)):
    """Per-share value across the levers that actually move a growth company: the whole
    revenue-growth path shifted by Δ (rate AND, because the shape is preserved, how long
    growth lasts) × the steady-state operating margin shifted by Δ.

    This is the headline range for a young/growth firm. The WACC×terminal-growth grid
    (`sensitivity`) perturbs the two LOWEST-leverage levers — in a rupee model a full ±1%
    on terminal growth barely moves value — so leading with it reports a falsely narrow band
    and hides that a premature growth fade is what's driving a low number. Damodaran's actual
    uncertainty tool for Zomato was a distribution over exactly these story drivers (market
    size/share → growth, and steady-state margin); this is the deterministic version of it.

    Also returns a `duration` read: holding the growth RATE, extend the high-growth phase —
    the single most common reason a quality Indian compounder prints far below price is that
    its demonstrated growth was faded to a mature rate years too early."""
    n = int(spec.get("years", 10))
    base_g = resolve_growth(spec, n)
    base_m = resolve_margin(spec, n)

    def trial(gd, md):
        s = dict(spec)
        s.pop("growth_glide", None)
        s.pop("margin_glide", None)
        s["revenue_growth"] = [g + gd for g in base_g]
        s["operating_margin"] = [max(0.0, m + md) for m in base_m]
        try:
            return round(value(s)["intrinsic_value_per_share"], 2)
        except ValueError:
            return None

    grid = {
        "growth_shift_axis": [round(g, 4) for g in growth_shifts],
        "margin_shift_axis": [round(m, 4) for m in margin_shifts],
        "cells": [[trial(gd, md) for md in margin_shifts] for gd in growth_shifts],
        "note": "rows = revenue-growth-path shift, cols = steady-state-margin shift; "
                "these are the levers a growth stock's value actually turns on.",
    }

    # Duration read: keep the rate, lengthen how long the high-growth phase lasts.
    g = spec.get("growth_glide")
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


# ----------------------------------------------------------------------------- reverse DCF

def reverse_dcf(spec, target_per_share=None, solve="growth", tol=1e-4, max_iter=200):
    """Solve the DCF backwards: hold every assumption fixed except ONE lever and find the
    value of that lever the market price already implies. Instead of "given my story, what
    is it worth?", it answers "given the price, what story must be true?" — Damodaran's
    favourite reality check. The whole chosen path is shifted by a constant Δ (so its shape /
    fade structure is preserved) until intrinsic value/share == target (default: current_price).

    solve = "growth"  -> implied revenue-growth path (and the implied N-year revenue CAGR)
    solve = "margin"  -> implied operating-margin path

    Returns {solved: True, lever, shift, implied_path, implied_year1, base_year1, ...} or
    {solved: False, lever, reason} when the target can't be bracketed (price below what even
    a conservative assumption supports, or beyond a credible range — which is itself the finding).
    """
    if target_per_share is None:
        target_per_share = spec.get("current_price")
    if target_per_share in (None, 0):
        raise ValueError("reverse_dcf needs a target — set current_price or pass target_per_share")
    target = float(target_per_share)
    n = int(spec.get("years", 10))

    if solve == "growth":
        base = resolve_growth(spec, n)

        def make(delta):
            s = dict(spec)
            s.pop("growth_glide", None)
            s["revenue_growth"] = [g + delta for g in base]
            return s
        lo, hi, label = -0.30, 0.60, "revenue growth"
    elif solve == "margin":
        base = resolve_margin(spec, n)

        def make(delta):
            s = dict(spec)
            s.pop("margin_glide", None)
            s["operating_margin"] = [max(0.0, m + delta) for m in base]
            return s
        lo, hi, label = -0.30, 0.40, "operating margin"
    else:
        raise ValueError("solve must be 'growth' or 'margin'")

    def f(delta):
        return value(make(delta))["intrinsic_value_per_share"] - target

    flo, fhi = f(lo), f(hi)
    # value rises with the lever (assuming terminal ROIC > WACC), so we expect flo < 0 < fhi.
    if flo >= 0:
        v = value(make(lo))["intrinsic_value_per_share"]
        return {"solved": False, "lever": label, "target_per_share": target,
                "reason": f"Even with {label} cut by {abs(lo):.0%} across the board, intrinsic value "
                          f"(₹{v:,.0f}/sh) still meets or exceeds the ₹{target:,.0f} target — the market "
                          f"is pricing in LESS than your already-conservative {label}; the stock looks cheap "
                          f"on this lever."}
    if fhi <= 0:
        v = value(make(hi))["intrinsic_value_per_share"]
        return {"solved": False, "lever": label, "target_per_share": target,
                "reason": f"Even with {label} raised by {hi:.0%} across the board, intrinsic value "
                          f"(₹{v:,.0f}/sh) stays below the ₹{target:,.0f} target — the price implies {label} "
                          f"beyond a credible/searchable range (or growth adds no value here because terminal "
                          f"ROIC ≤ WACC). Either way the price is very hard to justify on this lever alone."}

    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        fm = f(mid)
        if abs(fm) <= tol * max(1.0, target):
            lo = hi = mid
            break
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi, fhi = mid, fm
    delta = (lo + hi) / 2.0
    implied = [round(b + delta, 6) for b in base] if solve == "growth" \
        else [round(max(0.0, b + delta), 6) for b in base]
    out = {
        "solved": True,
        "lever": label,
        "target_per_share": target,
        "shift": round(delta, 6),
        "implied_path": implied,
        "implied_year1": implied[0],
        "base_year1": round(base[0], 6),
    }
    if solve == "growth":
        implied_cagr = reduce(lambda a, g: a * (1.0 + g), implied, 1.0) ** (1.0 / n) - 1.0
        base_cagr = reduce(lambda a, g: a * (1.0 + g), base, 1.0) ** (1.0 / n) - 1.0
        out["implied_revenue_cagr"] = round(implied_cagr, 6)
        out["base_revenue_cagr"] = round(base_cagr, 6)
    return out


# ----------------------------------------------------------------------------- io

def load_inputs(path):
    with open(path) as f:
        text = f.read()
    if path.endswith((".yml", ".yaml")):
        yaml = _need("yaml", "pyyaml")
        return yaml.safe_load(text)
    return json.loads(text)


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


def main():
    ap = argparse.ArgumentParser(description="Story-driven FCFF DCF (Damodaran).")
    ap.add_argument("--inputs", help="YAML/JSON input file (see assets/dcf-inputs.example.yml)")
    ap.add_argument("--out", help="write result JSON here")
    ap.add_argument("--sensitivity", action="store_true", help="also emit a WACC x g grid")
    ap.add_argument("--story", action="store_true",
                    help="also emit the story-driver grid (growth x steady-state margin) — the "
                         "headline range for a growth company; far higher leverage than WACC x g")
    ap.add_argument("--reverse", action="store_true",
                    help="also solve the DCF backwards: what assumption does current_price imply?")
    ap.add_argument("--reverse-solve", choices=["growth", "margin"], default="growth",
                    help="which lever the reverse DCF solves for (default growth)")
    ap.add_argument("--reverse-target", type=float,
                    help="target price/share for the reverse DCF (default: spec current_price)")
    ap.add_argument("--selftest", action="store_true", help="run the built-in worked example")
    args = ap.parse_args()

    if args.selftest:
        spec = SELFTEST_SPEC
    elif args.inputs:
        spec = load_inputs(args.inputs)
    else:
        ap.error("need --inputs <file> or --selftest")

    try:
        result = value(spec)
        if args.sensitivity or args.selftest:
            result["sensitivity"] = sensitivity(spec)
        if args.story or args.selftest:
            result["story_sensitivity"] = story_sensitivity(spec)
        if args.reverse or args.selftest:
            result["reverse_dcf"] = reverse_dcf(spec, target_per_share=args.reverse_target,
                                                solve=args.reverse_solve)
    except ValueError as e:
        print(f"MODEL-INVALID: {e}", file=sys.stderr)
        sys.exit(3)

    out = json.dumps(result, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w") as f:
            f.write(out + "\n")
        print(f"wrote {args.out}")
    else:
        print(out)

    ps = result["intrinsic_value_per_share"]
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
