#!/usr/bin/env python3
"""Look-through portfolio metrics — the forward-looking pillar of mf-analysis.

A fund does not publish its own P/E, P/B or ROE, but it does publish what it owns.
This script aggregates the underlying stocks' ratios into the portfolio's ratios, so a
verdict can rest on *what the fund holds today* rather than on what it returned last year.

Holdings and per-stock ratios both come from `finance/sources/funds.py`, the
one sanctioned path — it fetches the COMPLETE position list (64-278 names at 90-99% weight
coverage), threaded and disk-cached. A holdings file is an offline/testing hatch only.

Three rules are baked into the math, each of which can flip a verdict:

1. **Cap-tilt is RANK-based, not ₹Cr-band-based** — `finance/caps.py` owns the tiers and
   the refusal of ₹Cr bands. `cap_tilt` adds only the weighting, and reports `by_rank` vs
   `by_label` so a reader sees whether the split is a fact or a fallback.

2. **Coverage is a GATE, not a footnote.** Below `MIN_PUBLISHABLE_COVERAGE` the ratio is
   withheld (`value: null`, `confidence: "unusable"`), not annotated — the same book
   priced at 20% and at 95% coverage yields wildly different multiples, so a blank beats
   a confident wrong number.

3. **A multiple aggregates by the weighted HARMONIC mean.** A portfolio P/E is total
   price / total earnings = 1 / Sum(w_i / PE_i); weighted-arithmetic averaging inflates
   every multiple and mis-ranks a peer comparison.

Only `load_fund()` touches the network; the math core is pure. Uncovered weight is
reported, never extrapolated.

Reached through: get_fund_lookthrough.
"""
from __future__ import annotations

import math


from finance.caps import cap_bucket
from finance.spine import envelope as _envelope, f as _num, first as _first

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


def weighted_harmonic(pairs):
    """(weight, multiple) -> (portfolio multiple, covered weight).

    Yield-weighted: 1 / Sum(w/v). The ONLY correct way to aggregate a P/E- or P/B-type
    multiple — you sum earnings and book yields, not the multiples. Non-positive
    multiples (loss-makers) are dropped, because a negative P/E is not a cheaper P/E;
    their weight is excluded from coverage so the omission is visible.
    """
    usable = []
    for w, v in pairs:
        w, v = _num(w), _num(v)
        if w is None or w <= 0 or v is None or v <= 0:
            continue
        usable.append((w, v))
    if not usable:
        return None, 0.0
    cov = math.fsum(w for w, _ in usable)
    scale = min(v for _, v in usable)
    denominator = math.fsum((w / cov) * (scale / v) for w, v in usable)
    if denominator <= 0:
        return None, cov
    return _num(scale / denominator), cov


def weighted_mean(pairs):
    """(weight, value) -> (weighted arithmetic mean, covered weight). For ROE, growth
    and earnings yield, which are additive and may legitimately be negative."""
    usable = []
    for w, v in pairs:
        w, v = _num(w), _num(v)
        if w is None or w <= 0 or v is None:
            continue
        usable.append((w, v))
    if not usable:
        return None, 0.0
    cov = math.fsum(w for w, _ in usable)
    scale = max(abs(v) for _, v in usable)
    if not scale:
        return 0.0, cov
    normalized = math.fsum((w / cov) * (v / scale) for w, v in usable)
    # The convex mean is bounded by the inputs, including at the float limit.
    return min(1.0, max(-1.0, normalized)) * scale, cov


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
    if covered_weight > 0 and _num(value) is None:
        return {"value": None, "coverage": round(frac, 4), "confidence": "unusable",
                "withheld": True, "note": "calculated metric is missing or nonfinite"}
    ok = grade in ("decision-grade", "indicative")
    return {
        "value": _round(value, ndigits) if ok else None,
        "coverage": round(frac, 4),
        "confidence": grade,
        "withheld": not ok,
    }


def portfolio_metrics(holdings, equity_weight=None):
    """Every look-through metric for one fund, from enriched holdings.

    Each holding carries `weight` and, when priced, `pe`/`pb`/`roe`/`cap_rank`/
    `cap_label`/`sector`/`market_cap_cr`. `equity_weight` is the
    fund's total equity allocation (%) — the honest denominator for coverage, because
    positions the provider never listed must count against coverage, not vanish from it.
    """
    if not isinstance(holdings, list) or any(not isinstance(h,dict) for h in holdings):
        raise ValueError("holdings must be a list of mappings")
    weights = [_num(h.get("weight")) for h in holdings]
    if any(weight is None or not 0 <= weight <= 100 for weight in weights):
        raise ValueError("holding weights must be finite percentages between 0 and 100")
    listed = math.fsum(weights)
    if listed > 100 and not math.isclose(listed,100,rel_tol=0,abs_tol=1e-8):
        raise ValueError("holding weights exceed 100%; check duplicate or inconsistent positions")
    if holdings and equity_weight is None:
        raise ValueError("total equity allocation is missing; coverage cannot be established from listed holdings alone")
    total = _num(equity_weight) if equity_weight is not None else 0.0
    if total is None or not 0 <= total <= 100:
        raise ValueError("equity weight must be a finite percentage between 0 and 100")
    if listed > total and not math.isclose(listed,total,rel_tol=0,abs_tol=1e-8):
        raise ValueError("listed holdings exceed the supplied equity allocation")
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
        "pb_over_roe": pb_over_roe(holdings, total),
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


def pb_over_roe(holdings, total):
    """P/B divided by weighted ROE on exactly the same covered holdings.

    Independent P/B and ROE coverage does not establish their overlap. Compute both
    inputs again on the intersection, then gate on that joint covered weight.
    This is a descriptive ratio, not proof of cheapness or resilience to bad data.
    """
    shared = [h for h in holdings if (_num(h.get("pb")) is not None
              and _num(h.get("pb")) > 0 and _num(h.get("roe")) is not None)]
    pb, pb_w = weighted_harmonic((h.get("weight"),h.get("pb")) for h in shared)
    roe, roe_w = weighted_mean((h.get("weight"),h.get("roe")) for h in shared)
    p, r = _num(pb), _num(roe)
    joint_weight = min(pb_w, roe_w)
    if p is None or r is None:
        return gated(None, 0, total, ndigits=4)
    if r <= 0:
        return {"value": None, "coverage": round(joint_weight / total,4) if total else 0.0,
                "confidence": "unusable", "withheld": True,
                "note": "undefined at non-positive ROE on the jointly covered holdings"}
    return gated(p / r, joint_weight, total, ndigits=4)


def metric_gaps(metrics):
    """The labelled degradations implied by a metrics block — the "Data gaps" line."""
    gaps = []
    for key in ("portfolio_pe", "portfolio_pb", "portfolio_roe", "pb_over_roe",
                "earnings_yield_pct"):
        m = metrics.get(key) or {}
        if m.get("confidence") == "unavailable":
            gaps.append(f"{key}: unavailable — the supplied holdings contain no usable "
                        f"inputs for this metric; missing data is not zero")
        elif m.get("withheld") and m.get("note"):
            gaps.append(f"{key}: WITHHELD — {m['note']}")
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
        gaps.append(f"{up:.2f}% of the book is unpriced (ratio data unconfirmed); "
                    f"each metric reports its own usable coverage, without extrapolation")
    ct = metrics.get("cap_tilt") or {}
    if ct.get("by_label"):
        gaps.append(f"cap-tilt: {100 * ct['by_label']:.1f}% of classified weight fell back to "
                    f"the provider's text label because no usable market-cap rank was returned")
    ed = metrics.get("earnings_distress") or {}
    if ed.get("coverage") and metrics.get("equity_weight_pct"):
        frac = ed["coverage"] / metrics["equity_weight_pct"]
        if frac < DECISION_GRADE_COVERAGE:
            gaps.append(f"earnings-distress dispersion covers {100 * frac:.1f}% of the book")
    return gaps


def load_fund(mf_id, fresh=False, workers=10):
    """The default path: full holdings + threaded, cached per-stock ratios.

    Returns (holdings, equity_weight, gaps, meta). The ONLY network code in the file;
    everything above it is pure.
    """
    from finance.sources import funds  # deferred: the pure math core must not need the fetchers

    env = funds.holdings(mf_id, fresh=fresh)
    gaps = list(env.get("gaps") or [])
    data = env.get("data") or {}
    positions = data.get("positions") or []
    if not env.get("ok") or not positions:
        return [], 0.0, gaps or [f"no holdings returned for {mf_id}"], {"mf_id": mf_id}

    equity_weight = _num(data.get("equity_weight"))
    if equity_weight is None:
        # Coverage is already unusable; fetching every stock cannot repair it.
        enriched = [dict(p) for p in positions if str(p.get("type", "")).lower() == "equity"]
    else:
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
    return enriched, equity_weight, gaps, meta


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
    if type(workers) is not int or workers <= 0:
        return _envelope(False, "finance.compute.lookthrough",
                         {"meta": {"mf_id": mf_id}, "metrics": {}, "n_holdings": 0,
                          "ratios_publishable": False, "confidence": "unusable"},
                         ["invalid look-through inputs: workers must be a positive integer"])
    holdings, equity_weight, gaps, meta = load_fund(mf_id, fresh=fresh, workers=workers)
    try:
        rep = build_report(holdings, equity_weight, gaps, meta)
    except ValueError as exc:
        return _envelope(False, "finance.compute.lookthrough",
                         {"meta":meta, "metrics":{}, "n_holdings":len(holdings) if isinstance(holdings,list) else 0,
                          "ratios_publishable":False, "confidence":"unusable"},
                         list(gaps) + [f"invalid holdings coverage: {exc}"])
    data = {k: v for k, v in rep.items() if k != "gaps"}
    return _envelope(bool(holdings) and rep["ratios_publishable"],
                     "finance.compute.lookthrough", data, rep["gaps"])
