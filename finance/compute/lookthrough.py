#!/usr/bin/env python3
"""Look-through portfolio metrics — the forward-looking pillar of mf-analysis.

A fund does not publish its own P/E, P/B or ROE, but it does publish what it owns.
This script aggregates the underlying stocks' ratios into the portfolio's ratios, so a
verdict can rest on *what the fund holds today* rather than on what it returned last year.

Holdings and per-stock ratios both come from `finance/sources/funds.py` (Tickertape), the one
sanctioned path — `--fund <MF_ID>` fetches the COMPLETE position list (64-278 names at
90-99% weight coverage), threaded and disk-cached. `--holdings FILE` is an
offline/testing hatch only.

Three rules are baked into the math, each of which can flip a verdict:

1. **Cap-tilt is RANK-based, not ₹Cr-band-based.** SEBI classifies by market-cap rank
   (top 100 large, 101-250 mid, 251+ small) and Tickertape publishes that rank.
   Absolute-₹Cr bands fabricate style drift, because a small-cap fund's biggest holdings
   are, by construction, its largest names.

2. **Coverage is a GATE, not a footnote.** Below `MIN_PUBLISHABLE_COVERAGE` the ratio is
   withheld (`value: null`, `confidence: "unusable"`), not annotated — the same book
   priced at 20% and at 95% coverage yields wildly different multiples, so a blank beats
   a confident wrong number.

3. **A multiple aggregates by the weighted HARMONIC mean.** A portfolio P/E is total
   price / total earnings = 1 / Sum(w_i / PE_i); weighted-arithmetic averaging inflates
   every multiple and mis-ranks a peer comparison.

Beyond the ratios it emits `pb_over_roe` (the valuation cut most stable under data
revision), earnings-distress dispersion (share of book at ROE < 8% — "cheap" means
nothing if the earnings are at a trough), weighted ROE, weighted earnings yield (which,
unlike P/E, can carry loss-makers), sector concentration + Herfindahl, top-5/top-10
concentration, and the unpriced/unlisted weight that every ratio silently excludes.

The math core is pure and offline-tested (`test_lookthrough.py`); only `load_fund()`
touches the network. Uncovered weight is reported, never extrapolated.

Reached through: get_fund_lookthrough (finance-funds)
"""
from __future__ import annotations


from finance.spine import envelope as _envelope, f as _num, first as _first  # shared spine

# --------------------------------------------------------------------------- #
# gates and thresholds — the tuned constants, in one place                     #
# --------------------------------------------------------------------------- #

# SEBI's own definition: caps are RANKS, not sizes. Top 100 large, 101-250 mid, 251+
# small. Mirrors `finance.sources.funds.SEBI_CAP_RANKS`; restated here so the pure math core stays
# importable with no dependency on the network module.
SEBI_CAP_RANKS = {"large": 100, "mid": 250}

# Coverage bands over the fund's EQUITY weight. A ratio graded `unusable` is withheld.
DECISION_GRADE_COVERAGE = 0.85
MIN_PUBLISHABLE_COVERAGE = 0.60

# Earnings-distress bands. 8% ROE is roughly the cost of equity for an Indian mid/small
# cap — below it a company is not earning its keep, so its P/E denominator is depressed
# and the multiple built on it is not a valuation, it is an artefact.
ROE_DISTRESS = 8.0
ROE_QUALITY = 18.0

# Unlisted/unpriced weight above this is a named risk, not a footnote (SEBI caps a
# scheme's unlisted exposure at 10%; a single unlisted top holding has been seen at 2.5%).
UNPRICED_RISK_PCT = 2.0


def _round(v, n=2):
    return round(v, n) if isinstance(v, (int, float)) else None


# --------------------------------------------------------------------------- #
# pure aggregation                                                             #
# --------------------------------------------------------------------------- #
def weighted_harmonic(pairs):
    """(weight, multiple) -> (portfolio multiple, covered weight).

    Yield-weighted: 1 / Sum(w/v). The ONLY correct way to aggregate a P/E- or P/B-type
    multiple — you sum earnings and book yields, not the multiples. Non-positive
    multiples (loss-makers) are dropped, because a negative P/E is not a cheaper P/E;
    their weight is excluded from coverage so the omission is visible.
    """
    num = cov = 0.0
    for w, v in pairs:
        w, v = _num(w), _num(v)
        if w is None or w <= 0 or v is None or v <= 0:
            continue
        num += w / v
        cov += w
    if num <= 0:
        return None, 0.0
    return cov / num, cov


def weighted_mean(pairs):
    """(weight, value) -> (weighted arithmetic mean, covered weight). For ROE, growth
    and earnings yield, which are additive and may legitimately be negative."""
    num = cov = 0.0
    for w, v in pairs:
        w, v = _num(w), _num(v)
        if w is None or w <= 0 or v is None:
            continue
        num += w * v
        cov += w
    if cov <= 0:
        return None, 0.0
    return num / cov, cov


def earnings_yields(holdings):
    """(weight, earnings yield %) per holding — 100/PE, keeping loss-makers NEGATIVE.

    The counterpart the harmonic P/E cannot express: harmonic P/E must drop negative
    earnings, so a book stuffed with loss-makers looks *cheaper* than it is. Aggregating
    the yields instead keeps that drag visible.
    """
    for h in holdings:
        pe = _num(_first(h, "pe", "ttm_pe"))
        if pe is None or pe == 0:
            continue
        yield (h.get("weight"), 100.0 / pe)


def cagr(series):
    """First->last CAGR (%) over len-1 periods. None if <2 usable points or a
    non-positive endpoint (a sign change makes CAGR meaningless)."""
    xs = [_num(x) for x in (series or []) if _num(x) is not None]
    if len(xs) < 2 or xs[0] <= 0 or xs[-1] <= 0:
        return None
    return ((xs[-1] / xs[0]) ** (1.0 / (len(xs) - 1)) - 1.0) * 100.0


# --------------------------------------------------------------------------- #
# cap classification — rank first, provider label second                       #
# --------------------------------------------------------------------------- #
def cap_bucket(cap_rank=None, cap_label=None):
    """-> ("large"|"mid"|"small"|None, source).

    Rank is the fact (SEBI classifies by market-cap rank); the provider's own text label
    is the labelled fallback when a rank is missing; absolute ₹Cr is not used at all,
    because a band that calls a small-cap fund's top holdings "large-cap" fabricates
    style drift out of nothing.
    """
    r = _num(cap_rank)
    if r is not None and r > 0:
        if r <= SEBI_CAP_RANKS["large"]:
            return "large", "rank"
        if r <= SEBI_CAP_RANKS["mid"]:
            return "mid", "rank"
        return "small", "rank"
    lab = str(cap_label or "").strip().lower().replace(" ", "").replace("-", "")
    if lab.startswith("large"):
        return "large", "label"
    if lab.startswith("mid"):
        return "mid", "label"
    if lab.startswith("small") or lab.startswith("micro"):
        return "small", "label"
    return None, None


def cap_tilt(holdings):
    """Weight fraction in large/mid/small over the cap-classified weight only.

    Reports how each rupee was classified (`by_rank` / `by_label`) so a reader can see
    whether the split is a fact or a fallback, and `coverage` so an uncovered tail can
    never masquerade as a zero bucket.
    """
    buckets = {"large": 0.0, "mid": 0.0, "small": 0.0}
    cov = by_rank = by_label = 0.0
    for h in holdings:
        w = _num(h.get("weight"))
        b, src = cap_bucket(h.get("cap_rank"), h.get("cap_label"))
        if w is None or w <= 0 or b is None:
            continue
        buckets[b] += w
        cov += w
        if src == "rank":
            by_rank += w
        else:
            by_label += w
    if cov <= 0:
        return {"large": None, "mid": None, "small": None, "coverage": 0.0,
                "by_rank": 0.0, "by_label": 0.0, "basis": "none"}
    out = {k: round(v / cov, 4) for k, v in buckets.items()}
    out["coverage"] = round(cov, 2)
    out["by_rank"] = round(by_rank / cov, 4)
    out["by_label"] = round(by_label / cov, 4)
    out["basis"] = "SEBI market-cap rank (top 100 large / 101-250 mid / 251+ small)"
    return out


# --------------------------------------------------------------------------- #
# concentration, sectors, distress                                             #
# --------------------------------------------------------------------------- #
def concentration(holdings):
    """Top-5 / top-10 weight share and the Herfindahl index of position weights."""
    ws = sorted((_num(h.get("weight")) or 0.0 for h in holdings), reverse=True)
    total = sum(ws)
    if total <= 0:
        return {"n": len(ws), "top5": None, "top10": None, "hhi": None}
    return {
        "n": len(ws),
        "top5": round(sum(ws[:5]) / total, 4),
        "top10": round(sum(ws[:10]) / total, 4),
        "hhi": round(sum((w / total) ** 2 for w in ws), 4),
    }


def sector_mix(holdings, top=8):
    """Sector weights (share of sector-classified weight), Herfindahl, and the top bets.

    Sector concentration is what turns a "diversified" 278-name book into a single macro
    bet — a fund can hold hundreds of stocks and still be one call on industrials.
    """
    tot = {}
    cov = 0.0
    for h in holdings:
        w = _num(h.get("weight"))
        s = (h.get("sector") or "").strip()
        if w is None or w <= 0 or not s:
            continue
        tot[s] = tot.get(s, 0.0) + w
        cov += w
    if cov <= 0:
        return {"coverage": 0.0, "hhi": None, "top_sectors": [], "n_sectors": 0}
    shares = sorted(((s, w / cov) for s, w in tot.items()), key=lambda x: -x[1])
    return {
        "coverage": round(cov, 2),
        "n_sectors": len(shares),
        "hhi": round(sum(v ** 2 for _, v in shares), 4),
        "top_sectors": [{"sector": s, "weight": round(v, 4)} for s, v in shares[:top]],
    }


def earnings_distress(holdings, top=10):
    """Dispersion of return-on-equity across the book — the "is this cheap or broken?" cut.

    A low portfolio P/E on collapsed earnings is a trap, not a bargain; a high one on
    trough earnings can be a bargain. Neither is visible in the aggregate multiple, so
    the share of book below `ROE_DISTRESS` and above `ROE_QUALITY` is reported directly,
    with the distressed names listed so the reader can classify each as **cyclical**
    (mean-reverting: steel, chemicals, capital goods in a downcycle) or **idiosyncratic**
    (may never revert: a company earning 4% ROE in a healthy sector). Fractions are of
    the ROE-covered weight, and that coverage is stated.
    """
    cov = lo = hi = 0.0
    names = []
    for h in holdings:
        w = _num(h.get("weight"))
        roe = _num(h.get("roe"))
        if w is None or w <= 0 or roe is None:
            continue
        cov += w
        if roe < ROE_DISTRESS:
            lo += w
            names.append({
                "name": h.get("name") or h.get("ticker") or h.get("sid"),
                "ticker": h.get("ticker"),
                "sector": h.get("sector"),
                "weight": round(w, 3),
                "pe": _round(_num(h.get("pe"))),
                "pb": _round(_num(h.get("pb"))),
                "roe": _round(roe),
            })
        elif roe > ROE_QUALITY:
            hi += w
    if cov <= 0:
        return {"coverage": 0.0, "pct_weight_roe_lt_8": None,
                "pct_weight_roe_gt_18": None, "distressed": []}
    names.sort(key=lambda r: -r["weight"])
    return {
        "coverage": round(cov, 2),
        "roe_distress_threshold": ROE_DISTRESS,
        "roe_quality_threshold": ROE_QUALITY,
        "pct_weight_roe_lt_8": round(100.0 * lo / cov, 2),
        "pct_weight_roe_gt_18": round(100.0 * hi / cov, 2),
        "distressed": names[:top],
    }


# --------------------------------------------------------------------------- #
# the coverage gate                                                            #
# --------------------------------------------------------------------------- #
def coverage_grade(fraction):
    """Coverage fraction (0-1) -> "decision-grade" | "indicative" | "unusable"."""
    f = _num(fraction) or 0.0
    if f >= DECISION_GRADE_COVERAGE:
        return "decision-grade"
    if f >= MIN_PUBLISHABLE_COVERAGE:
        return "indicative"
    return "unusable"


def gated(value, covered_weight, total_weight, ndigits=2):
    """Wrap a ratio in its coverage grade and WITHHOLD it when unusable.

    This is the gate itself: an `unusable` ratio comes back `{"value": null}`. It is not
    a display convention — a number that survives into a table gets cited, and a ratio
    computed on a fifth of a portfolio is a different portfolio's ratio.

    A metric with literally no source at all is graded `unavailable` rather than
    `unusable`, so "nobody publishes this" reads differently from "we only priced a
    fifth of the book" — the first is a missing input, the second is a warning.
    """
    frac = (covered_weight / total_weight) if (total_weight and total_weight > 0) else 0.0
    grade = "unavailable" if covered_weight <= 0 else coverage_grade(frac)
    ok = grade in ("decision-grade", "indicative")
    return {
        "value": _round(value, ndigits) if ok else None,
        "coverage": round(frac, 4),
        "confidence": grade,
        "withheld": not ok,
    }


# --------------------------------------------------------------------------- #
# the portfolio read                                                           #
# --------------------------------------------------------------------------- #
def portfolio_metrics(holdings, equity_weight=None):
    """Every look-through metric for one fund, from enriched holdings.

    Each holding carries `weight` and, when priced, `pe`/`pb`/`roe`/`cap_rank`/
    `cap_label`/`sector`/`market_cap_cr`. `equity_weight` is the
    fund's total equity allocation (%) — the honest denominator for coverage, because
    positions the provider never listed must count against coverage, not vanish from it.
    """
    listed = sum(_num(h.get("weight")) or 0.0 for h in holdings)
    total = _num(equity_weight) or listed
    total = max(total, listed)

    pe, pe_w = weighted_harmonic((h.get("weight"), _first(h, "pe", "ttm_pe"))
                                 for h in holdings)
    pb, pb_w = weighted_harmonic((h.get("weight"), h.get("pb")) for h in holdings)
    roe, roe_w = weighted_mean((h.get("weight"), h.get("roe")) for h in holdings)
    ey, ey_w = weighted_mean(earnings_yields(holdings))

    priced_w = sum(_num(h.get("weight")) or 0.0 for h in holdings if h.get("priced"))
    unpriced_w = round(max(0.0, total - priced_w), 2)

    m = {
        "portfolio_pe": gated(pe, pe_w, total),
        "portfolio_pb": gated(pb, pb_w, total),
        "portfolio_roe": gated(roe, roe_w, total),
        "earnings_yield_pct": gated(ey, ey_w, total),
        "pb_over_roe": pb_over_roe(pb, roe, pb_w, roe_w, total),
        "cap_tilt": cap_tilt(holdings),
        "concentration": concentration(holdings),
        "sectors": sector_mix(holdings),
        "earnings_distress": earnings_distress(holdings),
        "unpriced_weight_pct": unpriced_w,
        "equity_weight_pct": round(total, 2),
        "listed_weight_pct": round(listed, 2),
    }
    m["confidence"] = coverage_grade(min(
        (pe_w / total) if total else 0.0, (pb_w / total) if total else 0.0))
    return m


def pb_over_roe(pb, roe, pb_w, roe_w, total):
    """Price-to-book per unit of return on equity — price paid for each point of
    profitability.

    The quality-adjusted valuation cut, and the one most stable under data revision:
    P/E collapses whenever the earnings denominator does, so it flip-flops; book value
    does not collapse, and dividing by ROE asks whether you are paying up for a business
    that earns. Lower is cheaper. Undefined for a non-positive ROE (paying anything for
    no return on equity is not a ratio, it is a red flag).
    """
    p, r = _num(pb), _num(roe)
    if p is None or r is None or r <= 0:
        return {"value": None, "coverage": 0.0, "confidence": "unusable",
                "withheld": True,
                "note": "undefined at non-positive portfolio ROE" if p is not None else None}
    return gated(p / r, min(pb_w, roe_w), total, ndigits=4)


def metric_gaps(metrics):
    """The labelled degradations implied by a metrics block — the "Data gaps" line."""
    gaps = []
    for key in ("portfolio_pe", "portfolio_pb", "portfolio_roe", "pb_over_roe",
                "earnings_yield_pct"):
        m = metrics.get(key) or {}
        if m.get("confidence") == "unavailable":
            gaps.append(f"{key}: no source — nothing in the sanctioned data path publishes "
                        f"it for these holdings; it is absent, not zero")
        elif m.get("withheld"):
            gaps.append(f"{key}: WITHHELD — priced weight {100 * m.get('coverage', 0):.1f}% "
                        f"of the book is below the {100 * MIN_PUBLISHABLE_COVERAGE:.0f}% "
                        f"publishable floor; the ratio would describe a different portfolio")
        elif m.get("confidence") == "indicative":
            gaps.append(f"{key}: indicative only — {100 * m.get('coverage', 0):.1f}% coverage "
                        f"(decision-grade needs {100 * DECISION_GRADE_COVERAGE:.0f}%); "
                        f"do not cite it as a deciding factor")
    up = metrics.get("unpriced_weight_pct") or 0.0
    if up > UNPRICED_RISK_PCT:
        gaps.append(f"{up:.2f}% of the book is unlisted or unpriced — excluded from every "
                    f"ratio above, never extrapolated; treat as opacity risk")
    ct = metrics.get("cap_tilt") or {}
    if ct.get("by_label"):
        gaps.append(f"cap-tilt: {100 * ct['by_label']:.1f}% of classified weight fell back to "
                    f"the provider's text label because no market-cap rank was published")
    ed = metrics.get("earnings_distress") or {}
    if ed.get("coverage") and metrics.get("equity_weight_pct"):
        frac = ed["coverage"] / metrics["equity_weight_pct"]
        if frac < DECISION_GRADE_COVERAGE:
            gaps.append(f"earnings-distress dispersion covers {100 * frac:.1f}% of the book")
    return gaps


# --------------------------------------------------------------------------- #
# holdings input                                                               #
# --------------------------------------------------------------------------- #
def load_fund(mf_id, fresh=False, workers=10):
    """The default path: full holdings + threaded, cached per-stock ratios via finance.sources.funds.

    Returns (holdings, equity_weight, gaps, meta). This is the ONLY network code in the
    file; everything above it is pure and offline-tested.
    """
    from finance.sources import funds  # deferred: the pure math core must not need the fetchers

    env = funds.holdings(mf_id, fresh=fresh)
    gaps = list(env.get("gaps") or [])
    data = env.get("data") or {}
    positions = data.get("positions") or []
    if not env.get("ok") or not positions:
        return [], 0.0, gaps or [f"no holdings returned for {mf_id}"], {"mf_id": mf_id}

    enriched, enrich_gaps = funds.enrich(positions, workers=workers, fresh=fresh)
    gaps += enrich_gaps
    meta = {
        "mf_id": mf_id,
        "source": env.get("source"),
        "fetched_at": env.get("fetched_at"),
        "position_count": data.get("position_count"),
        "equity_positions": len(enriched),
        "provider_sector_weights": data.get("sector_weights") or {},
    }
    return enriched, _num(data.get("equity_weight")) or 0.0, gaps, meta


def load_holdings_file(payload):
    """Offline hatch: a bare list, or a wrapper carrying holdings/positions/data.

    Kept for tests and for the rare audit against an AMC's own disclosure — NOT the
    normal path. A row that carries no ratios of its own and no `sid` stays unpriced and
    drags coverage down, exactly as it should; nothing is inferred from a name.
    """
    rows = payload if isinstance(payload, list) else _first(
        payload, "holdings", "positions", "data", "portfolio") or []
    out = []
    for it in rows:
        if not isinstance(it, dict):
            continue
        rec = dict(it)
        rec["weight"] = _num(_first(it, "weight", "percentage", "holding_pct",
                                    "corpus_percentage", "pct", "latest"))
        rec.setdefault("ticker", _first(it, "ticker", "symbol", "nse_code", "code"))
        rec.setdefault("name", _first(it, "name", "title", "company", "instrument"))
        rec["priced"] = it.get("priced") if "priced" in it else (
            _num(_first(it, "pe", "ttm_pe")) is not None or _num(it.get("pb")) is not None)
        out.append(rec)
    return out


def enrich_file_rows(rows, fresh=False, workers=10):
    """Fill ratios for file rows that carry a Tickertape `sid` (same source as the fund
    path, so a mixed-provider aggregate can never happen). Rows without a `sid` keep
    whatever ratios they were given and stay unpriced otherwise."""
    if not any(r.get("sid") for r in rows):
        return rows, []
    from finance.sources import funds

    for r in rows:
        r.setdefault("type", "Equity")
    enriched, gaps = funds.enrich(rows, workers=workers, fresh=fresh)
    return enriched, gaps


# --------------------------------------------------------------------------- #
def build_report(holdings, equity_weight, gaps, meta):
    """Assemble the artifact the skill and the HTML template consume."""
    metrics = portfolio_metrics(holdings, equity_weight)
    all_gaps = list(gaps) + metric_gaps(metrics)
    return {
        "meta": meta,
        "n_holdings": len(holdings),
        "metrics": metrics,
        "confidence": metrics["confidence"],
        "ratios_publishable": metrics["confidence"] != "unusable",
        "gaps": all_gaps,
    }


def report(mf_id, fresh=False, workers=10):
    """The look-through report for one fund in the shared data-spine envelope.

    `ok` is false when the holdings could not be read, or when coverage leaves the ratios
    unpublishable — a look-through built on a third of the book is a labelled gap, not a
    valuation.
    """
    holdings, equity_weight, gaps, meta = load_fund(mf_id, fresh=fresh, workers=workers)
    rep = build_report(holdings, equity_weight, gaps, meta)
    data = {k: v for k, v in rep.items() if k != "gaps"}
    return _envelope(bool(holdings) and rep["ratios_publishable"],
                     "finance.compute.lookthrough", data, rep["gaps"])
