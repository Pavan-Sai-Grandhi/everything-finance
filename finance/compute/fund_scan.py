#!/usr/bin/env python3
"""Category scanner — turns "which small-cap fund?" into a deterministic shortlist.

Takes the WHOLE SEBI sub-category from `finance.sources.funds.screen()`, applies the Varsity
checklist as HARD gates, scores the survivors on a fixed published weight table, and
emits the top N. Same inputs, same answer, every run, and auditable because the weights
and the per-component scores are in the output. The universe is never printed — only the
decision-grade rows reach stdout.

WHERE THE NUMBERS COME FROM
---------------------------
* AUM, expense ratio, Sharpe, Sortino, alpha, annualised volatility, trailing returns,
  fund age and cap mix -> `funds.screen()` (Tickertape, free, unauthenticated).
* Rolling returns and max drawdown -> **computed here from AMFI NAV history**
  (`funds.nav_history()` + `rolling.py`'s tested math). Tickertape gates `maxDrawdown` and
  `avg3yRollingRet` behind a paywall, and a NAV-derived version is reproducible from a
  primary source — which the paywalled field would not be.
* Nothing is estimated. A fund missing an input is scored on the rest with the weight
  redistributed, and if too little is left it is gated out rather than guessed at.

THE GATES (hard, applied before any scoring — Varsity ch. 24-26)
---------------------------------------------------------------
1. **Direct-Growth plan only.** `option == Growth`, and the expense ratio must sit under
   a Direct-plan ceiling — a Regular-plan TER served on a Direct-plan page is the most
   common identity error in fund research, and it is ~1.1%/yr of guaranteed drag.
2. **AUM viability floor.** Below it, an equity scheme has liquidity and viability
   questions (and its expense ratio has nowhere to fall).
3. **Fund age >= the window being credited.** You cannot credit a 3-year record to a
   2-year-old fund. This is a gate, not a penalty.
4. **NAV independently resolvable.** No AMFI Direct-Growth scheme match means rolling
   returns and drawdown cannot be recomputed from a primary source, so the fund cannot
   be verified — it is listed as gated, never silently scored on vendor numbers.
5. **Fund-manager tenure** is a pending MANUAL gate: no free API publishes it, so it is
   checked by hand for the shortlist only (never for the whole universe).

CLI:
  python3 -m finance.compute.fund_scan --category "Small Cap Fund" --top 5
  python3 -m finance.compute.fund_scan --category "Mid Cap Fund" --window 5y --min-aum 1000 --json
  python3 -m finance.compute.fund_scan --category "Small Cap Fund" --market-context artifacts/market-analysis/2026-08-16.json
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from finance.compute import rolling as R  # the tested rolling-return math, shared with pillar 1
from finance.spine import f as _f         # the one scraped-cell -> float coercion

# --------------------------------------------------------------------------- #
# the published scoring contract                                              #
# --------------------------------------------------------------------------- #

# Weights sum to 1.00. Two thirds sit on risk-adjusted behaviour and downside, one third
# on the structural drags that persist regardless of what the market does next (cost,
# size, mandate purity). Trailing point-to-point returns are deliberately NOT scored —
# Varsity's whole point is that they hang on two endpoints; the rolling equivalents are.
WEIGHTS = {
    "roll_mean":   0.20,   # mean rolling return over the credited window (NAV-derived)
    "roll_min":    0.12,   # WORST rolling window — what a badly-timed investor got
    "sharpe":      0.12,   # return per unit of total risk
    "sortino":     0.10,   # return per unit of DOWNSIDE risk (Varsity's refinement)
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


# --------------------------------------------------------------------------- #
# pure scoring primitives                                                      #
# --------------------------------------------------------------------------- #
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
    if p is None:
        return None
    return max(0.0, min(1.0, p / 100.0))


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


# --------------------------------------------------------------------------- #
# pure gating                                                                  #
# --------------------------------------------------------------------------- #
def gate(row, min_aum_cr, min_age_months, ter_ceiling=DIRECT_TER_CEILING):
    """-> (passed: bool, reasons: [str]). Every Varsity hard gate, in one pure function.

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


# --------------------------------------------------------------------------- #
# pure AMFI name matching                                                      #
# --------------------------------------------------------------------------- #
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
    to be present, the scheme has to be Direct + Growth, and any IDCW/bonus/reinvestment
    variant is rejected outright — those share the fund's name but not its NAV series,
    and scoring a growth mandate on a dividend-stripped NAV would understate it every time.
    Among survivors the shortest name wins (the plain Growth option, not a sub-variant).
    """
    want = {t for t in _tokens(fund_name) if t not in _NOISE_TOKENS}
    if not want:
        return None
    best = None
    for s in schemes or []:
        toks = set(_tokens(s.get("name", "")))
        if not want <= toks:
            continue
        if toks & _BAD_PLAN_TOKENS:
            continue
        if "direct" not in toks or "growth" not in toks:
            continue
        if best is None or len(s["name"]) < len(best["name"]):
            best = s
    return best


# --------------------------------------------------------------------------- #
# NAV-derived metrics (rolling + drawdown), computed not bought                #
# --------------------------------------------------------------------------- #
def nav_metrics(navs, window_years):
    """[{date, nav}] (ISO, oldest first) -> the metrics Tickertape puts behind a paywall.

    Returns rolling mean/median/min over the window, max drawdown, span in years and the
    confidence that span earns. Pure — the caller does the fetching.
    """
    dates, values = [], []
    for r in navs or []:
        try:
            dates.append(date.fromisoformat(r["date"]))
            values.append(float(r["nav"]))
        except (KeyError, TypeError, ValueError):
            continue
    if len(values) < 2:
        return {"roll_mean": None, "roll_min": None, "roll_median": None, "n_windows": 0,
                "max_drawdown_pct": None, "span_years": None, "confidence": "unknown",
                "nav_as_of": None}
    span = (dates[-1] - dates[0]).days / R.YEAR_DAYS
    stats = R.rolling_stats(R.rolling_returns(dates, values, window_years))
    return {
        "roll_mean": stats["mean"],
        "roll_median": stats["median"],
        "roll_min": stats["min"],
        "n_windows": stats["n"],
        "max_drawdown_pct": R.max_drawdown(values),
        "span_years": round(span, 2),
        "confidence": span_confidence(span),
        "nav_as_of": dates[-1].isoformat(),
    }


# --------------------------------------------------------------------------- #
# assembly (network)                                                           #
# --------------------------------------------------------------------------- #
def category_config(category):
    return dict(CATEGORY_DEFAULTS.get(str(category).strip().lower(), DEFAULT_CATEGORY))


def _resolve_and_nav(row, schemes, window_years, fresh):
    """One fund: AMFI identity + NAV history + the NAV-derived metrics."""
    from finance.sources import funds  # imported inside the worker; module-level import is cached
    hit = match_amfi_scheme(row.get("name") or "", schemes)
    if not hit:
        return None, None, ["no AMFI Direct-Growth scheme matched this name"]
    env = funds.nav_history(hit["code"], fresh=fresh)
    if not env.get("ok"):
        return hit, None, list(env.get("gaps") or ["NAV history unavailable"])
    return hit, nav_metrics((env.get("data") or {}).get("navs") or [], window_years), []


def scan(category="Small Cap Fund", top=5, window="3y", min_aum_cr=500,
         min_age_months=None, agility_ceiling_cr=None, ter_ceiling=DIRECT_TER_CEILING,
         workers=8, fresh=False, market_context=None):
    """The whole pipeline: universe -> hard gates -> NAV compute -> composite -> top N."""
    from finance.sources import funds

    cfg = category_config(category)
    if agility_ceiling_cr:
        cfg["agility_ceiling_cr"] = agility_ceiling_cr
    years = WINDOW_YEARS.get(window, 3)
    min_age_months = min_age_months if min_age_months is not None else years * 12

    env = funds.screen(subsector=category, option="Growth", min_aum=min(min_aum_cr, 100),
                       fresh=fresh)
    universe = (env.get("data") or {}).get("funds") or []
    gaps = list(env.get("gaps") or [])
    if not universe:
        gaps.append(f"no funds returned for category {category!r} — check the SEBI "
                    f"sub-category spelling against `python3 -m finance.sources.funds --screen`")

    # --- hard gates ---------------------------------------------------------
    survivors, rejected = [], {}
    for row in universe:
        ok, reasons = gate(row, min_aum_cr, min_age_months, ter_ceiling)
        if ok:
            survivors.append(row)
        else:
            rejected[reasons[0]] = rejected.get(reasons[0], 0) + 1

    # --- NAV-derived metrics for the survivors only -------------------------
    schemes = (funds.amfi_index(fresh=fresh).get("data") or {}).get("schemes") or []
    if not schemes:
        gaps.append("AMFI scheme list unavailable — rolling returns and drawdown could "
                    "not be computed for any fund")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        resolved = list(pool.map(
            lambda r: _resolve_and_nav(r, schemes, years, fresh), survivors))

    scored, nav_failed = [], {}
    for row, (hit, nav, row_gaps) in zip(survivors, resolved):
        if nav is None:
            reason = row_gaps[0] if row_gaps else "NAV history unavailable"
            nav_failed[reason] = nav_failed.get(reason, 0) + 1
            continue
        scored.append({"row": row, "amfi": hit, "nav": nav})
    for reason, n in nav_failed.items():
        rejected[reason] = rejected.get(reason, 0) + n

    if not scored:
        return _empty(category, window, cfg, universe, rejected, gaps, market_context)

    # --- relative components: percentile-rank within the survivor set --------
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

    # --- absolute components ------------------------------------------------
    purity_field = cfg["purity_field"]
    for i, s in enumerate(scored):
        comp = {k: ranked[k][i] for k in ranked}
        comp["aum_agility"] = aum_agility(s["row"].get("aum"), min_aum_cr,
                                          cfg["agility_ceiling_cr"])
        comp["cap_purity"] = cap_purity(s["row"].get(purity_field)) if purity_field else None
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
                 for i, s in enumerate(scored[:max(1, top)])]

    if any(r["flags"] for r in shortlist):
        gaps.append("one or more shortlisted funds carry a flag — read the `flags` field "
                    "before treating a rank as a recommendation")

    return {
        "as_of": date.today().isoformat(),
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


def _empty(category, window, cfg, universe, rejected, gaps, market_context):
    return {
        "as_of": date.today().isoformat(),
        "category": category,
        "window_credited": window,
        "universe": {"screened": len(universe), "passed_gates": 0, "scored": 0,
                     "shortlisted": 0},
        "gates": {"rejected_tally": dict(sorted(rejected.items(), key=lambda kv: -kv[1]))},
        "scoring": {"weights": WEIGHTS},
        "category_context": market_context,
        "pending_manual_gates": [],
        "shortlist": [],
        "gaps": gaps + ["no fund cleared the hard gates — loosen --min-aum or --window "
                        "explicitly rather than shortlisting a fund that failed one"],
    }


def _shortlist_row(rank, s, purity_field, years):
    row, nav = s["row"], s["nav"]
    flags = []
    if nav["confidence"] == "low":
        flags.append(f"only {nav['span_years']}y of NAV history — one regime; risk metrics "
                     f"are descriptive, not predictive")
    if nav["n_windows"] and nav["n_windows"] < 60:
        flags.append(f"{nav['n_windows']} rolling {years}y windows — thin sample")
    if s["components"].get("aum_agility") is not None and s["components"]["aum_agility"] < 0.6:
        flags.append(f"AUM ₹{_f(row.get('aum')) or 0:,.0f} Cr is past the agility ceiling "
                     f"for this category")
    purity = _f(row.get(purity_field)) if purity_field else None
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
            "span_years": nav["span_years"],
            "history_confidence": nav["confidence"],
            "nav_as_of": nav["nav_as_of"],
        },
        "flags": flags,
    }


# --------------------------------------------------------------------------- #
# market context (read-only pass-through)                                      #
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# output — only decision-grade rows ever reach stdout                          #
# --------------------------------------------------------------------------- #
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
    for r in result["shortlist"]:
        m = r["metrics"]
        purity = m["cap_mix"].get("small") or m["cap_mix"].get("mid") or m["cap_mix"].get("large")
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
    from finance import paths  # the single path authority
    return os.path.join(paths.fund_dir(f"{category} scan"), "scanner.json")


def main():
    ap = argparse.ArgumentParser(description="Rank a SEBI fund sub-category deterministically.")
    ap.add_argument("--category", default="Small Cap Fund",
                    help='SEBI sub-category, e.g. "Small Cap Fund", "Flexi Cap Fund"')
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--window", default="3y", choices=sorted(WINDOW_YEARS),
                    help="the return window being credited; also the minimum fund age")
    ap.add_argument("--min-aum", type=float, default=500, metavar="CR",
                    help="AUM viability floor in ₹Cr (Varsity: <500 = viability questions)")
    ap.add_argument("--min-age-months", type=int, default=None,
                    help="override the age gate (default: the credited window)")
    ap.add_argument("--agility-ceiling", type=float, default=None, metavar="CR",
                    help="AUM above which size starts costing agility in this category")
    ap.add_argument("--ter-ceiling", type=float, default=DIRECT_TER_CEILING,
                    help="Direct-plan TER ceiling; above it the plan label is suspect")
    ap.add_argument("--market-context", metavar="FILE",
                    help="artifacts/market-analysis/<date>.json — carried through verbatim")
    ap.add_argument("--out", metavar="FILE", help="shortlist JSON destination")
    ap.add_argument("--json", action="store_true",
                    help="print the shortlist JSON to stdout instead of the table")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()

    result = scan(category=a.category, top=a.top, window=a.window, min_aum_cr=a.min_aum,
                  min_age_months=a.min_age_months, agility_ceiling_cr=a.agility_ceiling,
                  ter_ceiling=a.ter_ceiling, workers=a.workers, fresh=a.fresh,
                  market_context=load_market_context(a.market_context, a.category))

    out = a.out or default_out_path(a.category)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")

    if a.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render_table(result))
        print(f"\nshortlist JSON: {out}")


if __name__ == "__main__":
    main()
