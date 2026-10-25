"""Category scanner — turns "which small-cap fund?" into a deterministic shortlist.

Takes the WHOLE SEBI sub-category from `funds.screen()`, applies the selection checklist in
`methods/funds.md` as HARD gates, scores the survivors on a fixed published weight table, and
emits the top N. Same inputs, same answer, every run, and auditable because the weights and
the per-component scores are in the output.

Rolling returns and max drawdown are computed here from AMFI NAV history rather than read
off Tickertape: it gates `maxDrawdown` and `avg3yRollingRet` behind a paywall, and a
NAV-derived figure is reproducible from a primary source where a paywalled field is not.
Nothing is estimated — a fund missing an input is scored on the rest with the weight
redistributed, and if too little is left it is gated out rather than guessed at.

The hard gates, applied before any scoring:

1. Direct-Growth plan only, with the expense ratio under a Direct-plan ceiling. A
   Regular-plan TER served on a Direct-plan page is the most common identity error in fund
   research, and it is ~1.1%/yr of guaranteed drag.
2. AUM viability floor: below it an equity scheme has liquidity and viability questions,
   and its expense ratio has nowhere to fall.
3. Fund age >= the window being credited. A 3-year record cannot be credited to a
   2-year-old fund; this is a gate, not a penalty.
4. NAV independently resolvable. No AMFI Direct-Growth scheme match means rolling returns
   and drawdown cannot be recomputed from a primary source, so the fund is listed as gated
   rather than silently scored on vendor numbers.
5. Fund-manager tenure is a pending MANUAL gate: no free API publishes it, so it is checked
   by hand for the shortlist only, never for the whole universe.

Reached through get_fund_scan.
"""
from __future__ import annotations

import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from finance import spine
from finance.compute import rolling as R
from finance.spine import envelope as _envelope, f as _f

# Weights sum to 1.00. Two thirds sit on risk-adjusted behaviour and downside, one third
# on the structural drags that persist regardless of what the market does next (cost,
# size, mandate purity). Trailing point-to-point returns are deliberately NOT scored —
# Point-to-point returns hang on two endpoints; the rolling equivalents do not.
WEIGHTS = {
    "roll_mean":   0.20,   # mean rolling return over the credited window (NAV-derived)
    "roll_min":    0.12,   # WORST rolling window — what a badly-timed investor got
    "sharpe":      0.12,   # return per unit of total risk
    "sortino":     0.10,   # return per unit of DOWNSIDE risk
    "alpha":       0.10,   # excess over benchmark
    "max_dd":      0.10,   # deepest peak-to-trough (NAV-derived; lower is better)
    "std_dev":     0.06,   # annualised volatility (lower is better)
    "exp_ratio":   0.10,   # the only input guaranteed to happen (lower is better)
    "aum_agility": 0.06,   # absolute score — can this size still move in this category?
    "cap_purity":  0.04,   # absolute score — is it actually running its mandate?
}

# Direction of each RELATIVE component. Relative components are percentile-ranked WITHIN
# the gated survivor set (outlier-proof, and "best in this category today" is the only
# meaningful reading anyway). `aum_agility` and `cap_purity` are absolute 0-1 scores
# instead, because they mean something on their own scale: a bloated small-cap fund is
# bloated even if every peer is worse.
HIGHER_IS_BETTER = {
    "roll_mean": True, "roll_min": True, "sharpe": True, "sortino": True,
    "alpha": True, "max_dd": False, "std_dev": False, "exp_ratio": False,
}
ABSOLUTE = {"aum_agility", "cap_purity"}

# A fund scored on less than this share of the weight table is not comparable.
MIN_SCORE_COVERAGE = 0.60

# Defaults per SEBI sub-category. `purity_field` is the cap bucket the mandate requires
# (SEBI: >=65% of a small-cap scheme in small caps, >=65% mid, >=80% large).
CATEGORY_DEFAULTS = {
    "small cap fund":  {"purity_field": "percSmallcap", "agility_ceiling_cr": 25000,
                        "cap_tier": "NIFTY SMALLCAP 250"},
    "mid cap fund":    {"purity_field": "percMidcap", "agility_ceiling_cr": 40000,
                        "cap_tier": "NIFTY MIDCAP 150"},
    "large cap fund":  {"purity_field": "percLargecap", "agility_ceiling_cr": 200000,
                        "cap_tier": "NIFTY 50"},
    "elss":            {"purity_field": None, "agility_ceiling_cr": 60000,
                        "cap_tier": "NIFTY 50"},
    "flexi cap fund":  {"purity_field": None, "agility_ceiling_cr": 80000,
                        "cap_tier": "NIFTY 50"},
    "multi cap fund":  {"purity_field": None, "agility_ceiling_cr": 60000,
                        "cap_tier": "NIFTY 50"},
    "large & mid cap fund": {"purity_field": None, "agility_ceiling_cr": 60000,
                             "cap_tier": "NIFTY MIDCAP 150"},
}
DEFAULT_CATEGORY = {"purity_field": None, "agility_ceiling_cr": 60000, "cap_tier": None}

WINDOW_YEARS = {"1y": 1, "3y": 3, "5y": 5}

# A Direct-plan equity TER above this is almost certainly a Regular-plan figure served on
# a Direct-plan page. Index funds sit near 0.2%, active equity Direct near 0.5-1.0%.
DIRECT_TER_CEILING = 1.25

# Tokens that mark an AMFI scheme name as the wrong variant of the right fund.
_BAD_PLAN_TOKENS = {"idcw", "dividend", "payout", "bonus", "reinvestment", "reinvest",
                    "regular", "daily", "weekly", "fortnightly", "quarterly", "annual"}
_NOISE_TOKENS = {"fund", "plan", "direct", "growth", "option", "scheme", "the", "of"}


def percentile_ranks(values, higher_is_better=True):
    """[v|None] -> [0..1|None], the fund's rank among the peers that HAVE the metric.

    Rank rather than min-max because one outlier fund must not compress everyone else
    into a corner of the scale, and rank is invariant to the units of whatever is being
    ranked. Ties share the average rank; a single-valued set scores 0.5 (no information).
    """
    idx = [i for i, v in enumerate(values) if _f(v) is not None]
    if not idx:
        return [None] * len(values)
    if len(idx) == 1:
        out = [None] * len(values)
        out[idx[0]] = 0.5
        return out
    pairs = sorted(idx, key=lambda i: _f(values[i]), reverse=not higher_is_better)
    ranks = {}
    i = 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and _f(values[pairs[j + 1]]) == _f(values[pairs[i]]):
            j += 1
        avg = (i + j) / 2.0 / (len(pairs) - 1)
        for k in range(i, j + 1):
            ranks[pairs[k]] = avg
        i = j + 1
    return [ranks.get(i) for i in range(len(values))]


def aum_agility(aum_cr, floor_cr, ceiling_cr):
    """0-1: can a fund this size still act on its mandate?

    Full marks between the viability floor and the agility ceiling. Above the ceiling the
    score decays as ceiling/AUM — a small-cap fund at twice the ceiling scores 0.5, not 0,
    because size is a headwind, not a disqualification. Below the floor it is 0 (and the
    hard gate will already have removed it).
    """
    a = _f(aum_cr)
    if a is None or a <= 0:
        return None
    if a < floor_cr:
        return 0.0
    if a <= ceiling_cr:
        return 1.0
    return max(0.0, min(1.0, ceiling_cr / a))


def cap_purity(pct_in_mandate_cap):
    """0-1: the share of the book actually inside the cap tier the fund's name promises.

    A "small-cap" fund parking a third of its book in mid-caps is selling mid-cap beta
    under a small-cap label, and its headline return is partly another tier's.
    """
    p = _f(pct_in_mandate_cap)
    if p is None or not 0 <= p <= 100:
        return None
    return p / 100.0


def composite(components, weights=None):
    """{component: 0-1|None} -> (score 0-1, coverage 0-1, scored_on list).

    Missing components are dropped and their weight redistributed over the ones present,
    so a fund is never penalised for a vendor's silence — but `coverage` records how much
    of the table actually applied, and the caller gates on it.
    """
    weights = weights or WEIGHTS
    used = {k: v for k, v in components.items()
            if k in weights and _f(v) is not None}
    wsum = sum(weights[k] for k in used)
    if wsum <= 0:
        return None, 0.0, []
    score = sum(weights[k] * _f(v) for k, v in used.items()) / wsum
    return round(score, 4), round(wsum / sum(weights.values()), 4), sorted(used)


def gate(row, min_aum_cr, min_age_months, ter_ceiling=DIRECT_TER_CEILING):
    """-> (passed: bool, reasons: [str]). Every hard gate, in one pure function.

    Reasons are phrased as what is WRONG so the rejection tally reads as a diagnosis of
    the category, not as a list of names.
    """
    reasons = []
    if (row.get("option") or "").strip().lower() != "growth":
        reasons.append("not a Growth option (IDCW/dividend plans compound worse)")
    ter = _f(row.get("expRatio"))
    if ter is None:
        reasons.append("expense ratio not published — Direct plan unverifiable")
    elif ter > ter_ceiling:
        reasons.append(f"TER {ter:.2f}% exceeds the {ter_ceiling:.2f}% Direct-plan ceiling "
                       f"— likely a Regular-plan figure")
    aum = _f(row.get("aum"))
    if aum is None:
        reasons.append("AUM not published")
    elif aum < min_aum_cr:
        reasons.append(f"AUM ₹{aum:,.0f} Cr below the ₹{min_aum_cr:,.0f} Cr viability floor")
    age = _f(row.get("ageInMon"))
    if age is None:
        reasons.append("fund age not published")
    elif age < min_age_months:
        reasons.append(f"fund is {age:.0f} months old — younger than the "
                       f"{min_age_months}-month window being credited")
    return (not reasons), reasons


def span_confidence(years):
    """A record shorter than one full market cycle describes a regime, not a manager."""
    y = _f(years)
    if y is None:
        return "unknown"
    if y < 3:
        return "low"
    if y < 7:
        return "ok"
    return "full-cycle"


def _tokens(s):
    out, cur = [], []
    for ch in str(s).lower():
        if ch.isalnum():
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def match_amfi_scheme(fund_name, schemes):
    """Tickertape fund name + AMFI scheme list -> the Direct-Growth scheme, or None.

    Token-set matching, never substring: "ITI" must not match inside "MULTI", and
    "Small Cap" must not match "Large Cap". Every identifying token of the fund name has
    to match exactly after plan/noise tokens, the scheme has to be Direct + Growth, and any IDCW/bonus/reinvestment
    variant is rejected outright — those share the fund's name but not its NAV series,
    and scoring a growth mandate on a dividend-stripped NAV would understate it every time.
    Exactly one distinct AMFI code must match; ambiguity never picks an arbitrary NAV.
    """
    want = {t for t in _tokens(fund_name) if t not in _NOISE_TOKENS}
    if not want:
        return None
    matches = {}
    for s in schemes or []:
        if not isinstance(s,dict) or not isinstance(s.get("name"),str) or not s.get("code"):
            continue
        toks = set(_tokens(s["name"]))
        if want != toks - _NOISE_TOKENS:
            continue
        if toks & _BAD_PLAN_TOKENS:
            continue
        if "direct" not in toks or "growth" not in toks:
            continue
        matches[str(s["code"])] = s
    return next(iter(matches.values())) if len(matches) == 1 else None


def nav_metrics(navs, window_years):
    """[{date, nav}] (ISO, oldest first) -> the metrics Tickertape puts behind a paywall.

    Rolling mean/median/min over the window, max drawdown and its episode, the monthly-SIP
    outcomes over the same window, span in years and the confidence that span earns. The
    caller does the fetching.
    """
    dates, values = [], []
    for r in navs or []:
        try:
            day = date.fromisoformat(r["date"])
            raw = r["nav"]
            if isinstance(raw, bool):
                raise ValueError("boolean NAV")
            value = float(raw)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("invalid dated NAV observation") from exc
        dates.append(day)
        values.append(value)
    returns = R.rolling_returns(dates, values, window_years)
    if len(values) < 2:
        return {"roll_mean": None, "roll_min": None, "roll_median": None, "n_windows": 0,
                "max_drawdown_pct": None, "drawdown": None,
                "sip": R.sip_outcomes(dates, values, window_years), "span_years": None,
                "confidence": "unknown", "nav_as_of": None}
    span = (dates[-1] - dates[0]).days / R.YEAR_DAYS
    stats = R.rolling_stats(returns)
    return {
        "roll_mean": stats["mean"],
        "roll_median": stats["median"],
        "roll_min": stats["min"],
        "n_windows": stats["n"],
        "max_drawdown_pct": R.max_drawdown(values),
        "drawdown": R.drawdown_episode(dates, values),
        "sip": R.sip_outcomes(dates, values, window_years),
        "span_years": round(span, 2),
        "confidence": span_confidence(span) if stats["n"] else "unknown",
        "nav_as_of": dates[-1].isoformat(),
    }


def category_config(category):
    return dict(CATEGORY_DEFAULTS.get(str(category).strip().lower(), DEFAULT_CATEGORY))


def _resolve_and_nav(row, schemes, window_years, fresh):
    """One fund: AMFI identity + NAV history + the NAV-derived metrics."""
    from finance.sources import funds  # inside the worker; the module import is already cached
    hit = match_amfi_scheme(row.get("name") or "", schemes)
    if not hit:
        return None, None, ["no unique exact AMFI Direct-Growth scheme matched this name"]
    env = funds.nav_history(hit["code"], fresh=fresh)
    if not env.get("ok"):
        return hit, None, list(env.get("gaps") or ["NAV history unavailable"])
    try:
        metrics = nav_metrics((env.get("data") or {}).get("navs") or [], window_years)
    except ValueError as exc:
        return hit, None, list(env.get("gaps") or []) + [f"invalid NAV history: {exc}"]
    return hit, metrics, list(env.get("gaps") or [])


def scan(category="Small Cap Fund", top=5, window="3y", min_aum_cr=500,
         min_age_months=None, agility_ceiling_cr=None, ter_ceiling=DIRECT_TER_CEILING,
         workers=8, fresh=False, market_context=None):
    """The whole pipeline: universe -> hard gates -> NAV compute -> composite -> top N."""
    from finance.sources import funds

    if not isinstance(category,str) or not category.strip():
        raise ValueError("category must be a nonempty name")
    if not isinstance(window,str) or window not in WINDOW_YEARS:
        raise ValueError("window must be 1y, 3y or 5y")
    for label,value in (("top",top),("workers",workers)):
        if type(value) is not int or value <= 0:
            raise ValueError(f"{label} must be a positive integer")
    for label,value in (("min_aum_cr",min_aum_cr),("ter_ceiling",ter_ceiling),
                        ("min_age_months",min_age_months),("agility_ceiling_cr",agility_ceiling_cr)):
        if value is None and label in ("min_age_months","agility_ceiling_cr"):
            continue
        try:
            valid = (not isinstance(value,bool) and isinstance(value,(int,float))
                     and math.isfinite(value) and value >= 0
                     and (label != "agility_ceiling_cr" or value > 0))
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(f"{label} must be finite and nonnegative (agility ceiling strictly positive)")
    cfg = category_config(category)
    if agility_ceiling_cr is not None:
        cfg["agility_ceiling_cr"] = agility_ceiling_cr
    years = WINDOW_YEARS[window]
    min_age_months = min_age_months if min_age_months is not None else years * 12

    env = funds.screen(subsector=category, option="Growth", min_aum=min(min_aum_cr, 100),
                       fresh=fresh)
    universe = (env.get("data") or {}).get("funds") or []
    gaps = list(env.get("gaps") or [])
    if not universe:
        gaps.append(f"no funds returned for category {category!r} — check the SEBI "
                    f"sub-category spelling against screen_funds")

    survivors, rejected = [], {}
    for row in universe:
        ok, reasons = gate(row, min_aum_cr, min_age_months, ter_ceiling)
        if ok:
            survivors.append(row)
        else:
            rejected[reasons[0]] = rejected.get(reasons[0], 0) + 1

    schemes = (funds.amfi_index(fresh=fresh).get("data") or {}).get("schemes") or []
    if not schemes:
        gaps.append("AMFI scheme list unavailable — rolling returns and drawdown could "
                    "not be computed for any fund")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        resolved = list(pool.map(
            lambda r: _resolve_and_nav(r, schemes, years, fresh), survivors))

    scored, nav_failed = [], {}
    for row, (hit, nav, row_gaps) in zip(survivors, resolved):
        gaps.extend(f"{row.get('name') or 'fund'}: {gap}" for gap in row_gaps)
        if nav is None:
            reason = row_gaps[0] if row_gaps else "NAV history unavailable"
            nav_failed[reason] = nav_failed.get(reason, 0) + 1
            continue
        if not nav["n_windows"]:
            reason = f"no eligible rolling {years}y windows in NAV history"
            nav_failed[reason] = nav_failed.get(reason, 0) + 1
            gaps.append(f"{row.get('name') or 'fund'}: {reason}")
            continue
        scored.append({"row": row, "amfi": hit, "nav": nav})
    for reason, n in nav_failed.items():
        rejected[reason] = rejected.get(reason, 0) + n

    if not scored:
        return _empty(category, window, cfg, universe, rejected, gaps, market_context,
                      passed_gates=len(survivors))

    raw = {
        "roll_mean":  [s["nav"]["roll_mean"] for s in scored],
        "roll_min":   [s["nav"]["roll_min"] for s in scored],
        "max_dd":     [s["nav"]["max_drawdown_pct"] for s in scored],
        "sharpe":     [s["row"].get("sharpe") for s in scored],
        "sortino":    [s["row"].get("sortino") for s in scored],
        "alpha":      [s["row"].get("alpha") for s in scored],
        "std_dev":    [s["row"].get("stdDevAnn") for s in scored],
        "exp_ratio":  [s["row"].get("expRatio") for s in scored],
    }
    ranked = {k: percentile_ranks(v, HIGHER_IS_BETTER[k]) for k, v in raw.items()}

    purity_field = cfg["purity_field"]
    for i, s in enumerate(scored):
        comp = {k: ranked[k][i] for k in ranked}
        comp["aum_agility"] = aum_agility(s["row"].get("aum"), min_aum_cr,
                                          cfg["agility_ceiling_cr"])
        comp["cap_purity"] = cap_purity(s["row"].get(purity_field)) if purity_field else None
        if purity_field and s["row"].get(purity_field) is not None and comp["cap_purity"] is None:
            gaps.append(f"{s['row'].get('name') or 'fund'}: invalid {purity_field}; cap-purity score unavailable")
        score, cov, used = composite(comp)
        s["components"] = {k: (round(v, 4) if isinstance(v, float) else v)
                           for k, v in comp.items()}
        s["score"], s["score_coverage"], s["scored_on"] = score, cov, used

    dropped = [s for s in scored if (s["score"] is None or s["score_coverage"] < MIN_SCORE_COVERAGE)]
    for s in dropped:
        rejected["too few scoring inputs published to compare fairly"] = \
            rejected.get("too few scoring inputs published to compare fairly", 0) + 1
    scored = [s for s in scored if s not in dropped]
    scored.sort(key=lambda s: -s["score"])

    shortlist = [_shortlist_row(i + 1, s, purity_field, years)
                 for i, s in enumerate(scored[:top])]

    # An advisory, not a data gap: `gaps` means a figure is missing or degraded, and
    # diluting it with commentary trains a caller to skim past the entries that matter.
    advisories = ["one or more shortlisted funds carry a flag — read the `flags` field "
                  "before treating a rank as a recommendation"] \
        if any(r["flags"] for r in shortlist) else []

    return {
        "as_of": date.today().isoformat(),
        "advisories": advisories,
        "category": category,
        "window_credited": window,
        "universe": {"screened": len(universe), "passed_gates": len(survivors),
                     "scored": len(scored), "shortlisted": len(shortlist)},
        "gates": {
            "min_aum_cr": min_aum_cr,
            "min_age_months": min_age_months,
            "direct_ter_ceiling_pct": ter_ceiling,
            "plan": "Direct-Growth only",
            "rejected_tally": dict(sorted(rejected.items(), key=lambda kv: -kv[1])),
        },
        "scoring": {
            "weights": WEIGHTS,
            "method": ("relative components are percentile-ranked WITHIN the gated "
                       "survivor set; aum_agility and cap_purity are absolute 0-1 scores; "
                       "a missing component's weight is redistributed and the remaining "
                       f"coverage must reach {MIN_SCORE_COVERAGE:.0%}"),
            "rolling_and_drawdown": ("computed from AMFI NAV history via rolling.py — not "
                                     "taken from any vendor's premium field"),
            "trailing_returns": "reported as context, deliberately unscored (endpoint-dependent)",
        },
        "category_context": market_context,
        "pending_manual_gates": [
            "fund-manager tenure >= the credited window — no free API publishes it; "
            "verify by hand for the shortlist only, and discount a record earned by a "
            "predecessor",
            "benchmark identity — confirm each shortlisted fund's stated benchmark before "
            "comparing beat-rates across funds",
        ],
        "shortlist": shortlist,
        "gaps": gaps,
    }


def _empty(category, window, cfg, universe, rejected, gaps, market_context, passed_gates=0):
    return {
        "as_of": date.today().isoformat(),
        "category": category,
        "window_credited": window,
        "universe": {"screened": len(universe), "passed_gates": passed_gates, "scored": 0,
                     "shortlisted": 0},
        "gates": {"rejected_tally": dict(sorted(rejected.items(), key=lambda kv: -kv[1]))},
        "scoring": {"weights": WEIGHTS},
        "category_context": market_context,
        "pending_manual_gates": [],
        "shortlist": [],
        "gaps": gaps + ["no fund has both eligible screening inputs and usable NAV coverage; "
                        "see rejection counts and source gaps"],
    }


def _shortlist_row(rank, s, purity_field, years):
    row, nav = s["row"], s["nav"]
    flags = []
    if nav["confidence"] == "low":
        flags.append(f"only {nav['span_years']}y of NAV history — one regime; risk metrics "
                     f"are descriptive, not predictive")
    if not nav["n_windows"]:
        flags.append(f"no eligible rolling {years}y windows — return coverage unavailable")
    elif nav["n_windows"] < 60:
        flags.append(f"{nav['n_windows']} rolling {years}y windows — thin sample")
    if s["components"].get("aum_agility") is not None and s["components"]["aum_agility"] < 0.6:
        flags.append(f"AUM ₹{_f(row.get('aum')) or 0:,.0f} Cr is past the agility ceiling "
                     f"for this category")
    purity_score = cap_purity(row.get(purity_field)) if purity_field else None
    purity = purity_score * 100 if purity_score is not None else None
    if purity is not None and purity < 65:
        flags.append(f"only {purity:.1f}% of the book sits in the cap tier its mandate "
                     f"names — part of the record may be another cap tier's beta")
    return {
        "rank": rank,
        "mf_id": row.get("mf_id"),
        "name": row.get("name"),
        "scheme_code": (s["amfi"] or {}).get("code"),
        "isin": (s["amfi"] or {}).get("isin"),
        "amfi_name": (s["amfi"] or {}).get("name"),
        "score": s["score"],
        "score_coverage": s["score_coverage"],
        "scored_on": s["scored_on"],
        "components": s["components"],
        "metrics": {
            "aum_cr": _f(row.get("aum")),
            "expense_ratio_pct": _f(row.get("expRatio")),
            "sharpe": _f(row.get("sharpe")),
            "sortino": _f(row.get("sortino")),
            "alpha": _f(row.get("alpha")),
            "std_dev_ann": _f(row.get("stdDevAnn")),
            "tracking_error": _f(row.get("trackErr")),
            "age_months": _f(row.get("ageInMon")),
            "cap_mix": {"large": _f(row.get("percLargecap")), "mid": _f(row.get("percMidcap")),
                        "small": _f(row.get("percSmallcap")), "equity": _f(row.get("percEquityH"))},
            "vendor_pe": _f(row.get("pe")),
            "category_pe": _f(row.get("catPe")),
            "trailing_unscored": {"1y": _f(row.get("ret1y")), "3y": _f(row.get("ret3y")),
                                  "5y": _f(row.get("ret5y"))},
            "rolling": {"window": f"{years}y", "mean": nav["roll_mean"],
                        "median": nav["roll_median"], "min": nav["roll_min"],
                        "n_windows": nav["n_windows"]},
            "max_drawdown_pct": nav["max_drawdown_pct"],
            "drawdown": nav["drawdown"],
            "sip": dict(nav["sip"], window=f"{years}y"),
            "span_years": nav["span_years"],
            "history_confidence": nav["confidence"],
            "nav_as_of": nav["nav_as_of"],
        },
        "flags": flags,
    }


def load_market_context(path, category):
    """Pull the cap tier's valuation stance out of a market-analysis digest.

    Passed through VERBATIM — this script does not judge the market, it only carries the
    market skill's own reading alongside the shortlist so the fund choice and the
    "is this category a good place to add money right now" question stay separable.
    """
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            blob = json.load(f)
    except (OSError, ValueError):
        return None
    tier = category_config(category)["cap_tier"]
    val = ((blob.get("valuation") or {}).get(tier) or {}) if tier else {}
    return {
        "source": os.path.basename(path),
        "as_of": blob.get("as_of"),
        "cap_tier": tier,
        "market_trend": blob.get("market_trend"),
        "market_posture": blob.get("market_posture"),
        "tier_valuation": val or None,
        "relative": blob.get("relative"),
        "volatility_band": (blob.get("volatility") or {}).get("band"),
    }


def render_table(result):
    """The compact ranked table. The universe is summarised, never listed."""
    u, g = result["universe"], result["gates"]
    lines = [
        f"{result['category']} — top {u['shortlisted']} of {u['screened']} funds "
        f"({result['as_of']}, crediting the {result['window_credited']} window)",
        f"gates: Direct-Growth · AUM >= ₹{g.get('min_aum_cr', 0):,.0f} Cr · age >= "
        f"{g.get('min_age_months', 0)} months  ->  {u['passed_gates']} passed, "
        f"{u['scored']} scored",
        "",
    ]
    hdr = (f"{'#':>2} {'fund':<38} {'score':>6} {'roll':>7} {'worst':>7} {'maxDD':>7} "
           f"{'TER':>5} {'AUM ₹Cr':>10} {'Shrp':>6} {'purity':>7}")
    lines += [hdr, "-" * len(hdr)]
    purity_key = {"percSmallcap":"small", "percMidcap":"mid", "percLargecap":"large"}.get(
        category_config(result["category"])["purity_field"])
    for r in result["shortlist"]:
        m = r["metrics"]
        purity = m["cap_mix"].get(purity_key) if purity_key else None
        lines.append(
            f"{r['rank']:>2} {(r['name'] or '')[:38]:<38} {r['score']:>6.3f} "
            f"{_cell(m['rolling']['mean'], '%')  :>7} {_cell(m['rolling']['min'], '%'):>7} "
            f"{_cell(m['max_drawdown_pct'], '%'):>7} {_cell(m['expense_ratio_pct'], '%'):>5} "
            f"{_cell(m['aum_cr'], '', 0):>10} {_cell(m['sharpe'], '', 2):>6} "
            f"{_cell(purity, '%', 0):>7}")
        for flag in r["flags"]:
            lines.append(f"   ! {flag}")
    if result["gates"].get("rejected_tally"):
        lines += ["", "gated out (tally, not names):"]
        for reason, n in result["gates"]["rejected_tally"].items():
            lines.append(f"   {n:>3}  {reason}")
    ctx = result.get("category_context")
    if ctx and ctx.get("tier_valuation"):
        v = ctx["tier_valuation"]
        lines += ["", f"category context ({ctx['cap_tier']}, {ctx['as_of']}): "
                      f"P/E {v.get('pe')} ({v.get('pe_pctile')}th pctile) · "
                      f"P/B {v.get('pb')} ({v.get('pb_pctile')}th) · stance {v.get('stance')} · "
                      f"market {ctx.get('market_trend')}/{ctx.get('market_posture')}"]
    if result["gaps"]:
        lines += ["", "data gaps:"] + [f"   - {g}" for g in result["gaps"]]
    lines += ["", "Rankings describe the past and the present book, not the future. "
                  "Not investment advice — personal research tool."]
    return "\n".join(lines)


def _cell(v, suffix="", nd=1):
    x = _f(v)
    if x is None:
        return "—"
    return f"{x:,.{nd}f}{suffix}"


def default_out_path(category):
    from finance import paths
    return os.path.join(paths.fund_dir(f"{category} scan"), "fund-scan.json")


def report(category="Small Cap Fund", top=5, window="3y", min_aum_cr=500,
           min_age_months=None, agility_ceiling_cr=None, ter_ceiling=DIRECT_TER_CEILING,
           workers=8, fresh=False, market_context=None, out=None):
    """`scan()` in the shared data-spine envelope, with the shortlist persisted as JSON.

    `market_context` is the path to a market-analysis artifact whose cap-tier reading is
    carried through verbatim, so "which fund" and "is this category worth adding to now"
    stay separable questions.
    """
    try:
        result = scan(category=category, top=top, window=window, min_aum_cr=min_aum_cr,
                      min_age_months=min_age_months, agility_ceiling_cr=agility_ceiling_cr,
                      ter_ceiling=ter_ceiling, workers=workers, fresh=fresh,
                      market_context=load_market_context(market_context, category))
    except (ValueError, TypeError) as exc:
        return _envelope(False, "finance.compute.fund_scan", {"shortlist":[],"report_path":None},
                         [f"invalid fund scan inputs: {exc}"])
    gaps = list(result.get("gaps") or [])
    path = None
    try:
        target = os.fspath(out or default_out_path(category))
        prefix = os.path.splitext(target)[0]
        os.makedirs(os.path.dirname(os.path.abspath(prefix)), exist_ok=True)
        path = spine.publish_evidence(prefix, ".json", lambda stream:
            json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError, TypeError) as exc:
        gaps.append(f"could not write the shortlist: {exc}")
    data = {k: v for k, v in result.items() if k != "gaps"}
    data["report_path"] = path
    return _envelope(bool(result["shortlist"]), "finance.compute.fund_scan", data, gaps)
