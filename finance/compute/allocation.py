"""Multi-dimensional allocation + concentration engine (portfolio-review).

Pure computation over the canonical positions `finance/compute/holdings.py` returns — no
fetch, no MCP. The skill enriches each position with the dimension tags it gathered and
hands the bundle here; this module decides breakdowns, drift-vs-target, and the
concentration breaches with concrete ₹ rebalancing moves. Keeping the arithmetic in one
tested place is why the skill's report and the `quick` digest cannot disagree.

Two provenance-honest input styles per dimension:
  * per-holding tag — `sector`, `amc`, single-stock, `asset_class` aggregate by
    summing each holding's market value; a missing tag lands in `unknown` and
    lowers that dimension's coverage.
  * pre-aggregated breakdown — `market_cap` and `style` arrive as category→₹ (or
    →pct) dicts from the mf-analysis look-through, because they are portfolio-level
    weights, not one tag per row. A cap tier is a classification, so it comes from
    `get_stock_ratios`' `cap_rank` via that look-through, never from a personal
    source's own breakdown field.

Reached through: skills/portfolio-review/scripts/allocation.py.
"""
import math

from finance import caps
from finance.compute.holdings import market_value


# Concentration thresholds (%). Grounded in references/reference.md; overridable
# per call so a stated plan can tighten them.
DEFAULTS = {
    "single_stock": 10.0,          # any one stock over this share of the book
    "single_sector": 25.0,         # any one sector
    "single_sector_urgent": 35.0,  # escalated wording above this
    "smallcap_microcap": 30.0,     # small+micro sleeve (liquidity risk)
    "single_amc": 40.0,            # exposure piled into one fund house
    "asset_drift_pp": 10.0,        # asset-class drift vs target, in pp
}



def _valued(holdings):
    """Split holdings into (valued rows [(h, value)], gaps for the unvaluable)."""
    rows, gaps = [], []
    for h in holdings:
        if not isinstance(h, dict):
            gaps.append("malformed holding — excluded from allocation")
            continue
        v = market_value(h)
        if v is None or not math.isfinite(v) or v < 0:
            gaps.append(f"{h.get('ticker', '?')}: no usable nonnegative current valuation — excluded from allocation")
        else:
            rows.append((h, v))
    return rows, gaps


def _pcts(value_map, total):
    """category→₹ into category→{value, pct} (pct of `total`; 0 when total 0)."""
    return {
        cat: {"value": round(v, 2), "pct": round(100.0 * v / total, 2) if total else 0.0}
        for cat, v in value_map.items()
    }


def aggregate(holdings, key, total=None):
    """Sum market value by `holding[key]`; a missing/None tag → 'unknown'.
    Returns {category: {value, pct}} plus the coverage (share priced to a real
    tag, 0..1). `total` defaults to the sum of valued holdings."""
    rows, _ = _valued(holdings)
    if total is None:
        total = sum(v for _, v in rows)
    buckets = {}
    for h, v in rows:
        cat = h.get(key)
        cat = _category(cat)
        buckets[cat] = buckets.get(cat, 0.0) + v
    known = total - buckets.get("unknown", 0.0)
    coverage = (known / total) if total else 0.0
    return {"breakdown": _pcts(buckets, total), "coverage": round(coverage, 4), "total": round(total, 2)}


def _amount(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite nonnegative number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{label} must be a finite nonnegative number") from None
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be a finite nonnegative number")
    return number


def _thresholds(overrides):
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError("thresholds must be a mapping")
    if set(overrides or {}) - set(DEFAULTS):
        raise ValueError("unknown concentration threshold")
    result = {**DEFAULTS, **(overrides or {})}
    for key, value in result.items():
        result[key] = _amount(value, key)
        if result[key] > 100:
            raise ValueError(f"{key} must be between 0 and 100")
    return result


def _category(value):
    return str(value).strip().lower() if value is not None and str(value).strip() else "unknown"


def from_breakdown(breakdown, total=None):
    """Normalize disjoint category amounts without renormalizing partial coverage."""
    if not isinstance(breakdown, dict):
        raise ValueError("breakdown must be a category mapping")
    if total is not None:
        total = _amount(total, "book total")
    flat = {}
    for cat, item in breakdown.items():
        if isinstance(item, dict):
            if item.get("value") is not None:
                value = _amount(item["value"], "category value")
                if item.get("pct") is not None:
                    pct = _amount(item["pct"], "category percentage")
                    if total is None or pct > 100 or not math.isclose(value, pct / 100 * total, abs_tol=0.01):
                        raise ValueError("category value and percentage disagree")
            elif item.get("pct") is not None and total is not None:
                pct = _amount(item["pct"], "category percentage")
                if pct > 100:
                    raise ValueError("category percentage exceeds 100")
                value = pct / 100 * total
            else:
                raise ValueError("a percentage breakdown requires a book total and valid weights")
        else:
            value = _amount(item, "category value")
        key = _category(cat)
        flat[key] = flat.get(key, 0.0) + value
    combined = _amount(sum(flat.values()), "combined allocation")
    if total is not None and combined > total and not math.isclose(combined, total, rel_tol=1e-12, abs_tol=1e-8):
        raise ValueError("category breakdown exceeds the valued book total")
    return _pcts(flat, combined if total is None else total)


def _flag(dimension, category, pct, value, threshold, total, severity, note):
    """One breach with the concrete ₹ trim back to the threshold."""
    trim = round(value - threshold / 100.0 * total, 2)
    return {
        "dimension": dimension, "category": category,
        "pct": round(pct, 2), "value": round(value, 2),
        "threshold": threshold, "severity": severity,
        "suggestion": f"TRIM ₹{trim:,.0f} of {category} to bring it from "
                      f"{pct:.1f}% to {threshold:.0f}% ({note})",
    }


def concentration_flags(holdings, breakdowns=None, thresholds=None):
    """Every breach across the dimensions, most-concentrated first. `breakdowns`
    carries the pre-aggregated dimensions (market_cap, style); per-holding tags
    cover single-stock, sector, amc."""
    t = _thresholds(thresholds)
    breakdowns = breakdowns or {}
    rows, valuation_gaps = _valued(holdings)
    total = sum(v for _, v in rows)
    flags = []
    if total <= 0:
        return flags

    # Combine the same listed name across accounts before applying a book limit.
    stocks = {}
    for h, v in rows:
        if str(h.get("kind", "stock")).lower() == "fund":
            continue
        ticker = str(h.get("ticker") or "").strip().upper()
        if not ticker or ticker == "?":
            continue
        stocks[ticker] = stocks.get(ticker, 0.0) + v
    for ticker, value in stocks.items():
        pct = 100.0 * value / total
        if pct > t["single_stock"]:
            flags.append(_flag("single_stock", ticker, pct, value,
                               t["single_stock"], total, "watch", "single-name risk"))

    sec = aggregate(holdings, "sector", total)["breakdown"]
    for cat, d in sec.items():
        if cat == "unknown":
            continue
        if d["pct"] > t["single_sector"]:
            urgent = d["pct"] > t["single_sector_urgent"]
            flags.append(_flag("sector", cat, d["pct"], d["value"], t["single_sector"],
                               total, "act" if urgent else "watch",
                               "sector concentration" + (" — urgent" if urgent else "")))

    fund_rows = [h for h, _ in rows if str(h.get("kind", "")).lower() == "fund"]
    fund_total = sum(v for h, v in rows if str(h.get("kind", "")).lower() == "fund")
    amc = aggregate(fund_rows, "amc", fund_total)["breakdown"]
    for cat, d in amc.items():
        if cat == "unknown":
            continue
        if d["pct"] > t["single_amc"]:
            flags.append(_flag("amc", cat, d["pct"], d["value"], t["single_amc"],
                               fund_total, "watch", "share of the fund sleeve"))
            flags[-1]["denominator"] = "fund_sleeve"

    cap = breakdowns.get("market_cap")
    if cap:
        capb = from_breakdown(cap, total)
        # caps.py owns label normalisation ("Small Cap", "smallcap", "micro" → small).
        small = sum(d["value"] for c, d in capb.items()
                    if caps.cap_bucket(cap_label=c)[0] == "small")
        pct = 100.0 * small / total
        if pct > t["smallcap_microcap"]:
            flags.append(_flag("smallcap_microcap", "small+micro", pct, small,
                               t["smallcap_microcap"], total, "watch",
                               "narrow exit doors in a correction"))

    if valuation_gaps:
        for flag in flags:
            flag["severity"] = "watch"
            flag["suggestion"] = "REVIEW: concentration is measured only within valued holdings; complete book valuation before sizing a trim"
    flags.sort(key=lambda f: f["pct"], reverse=True)
    return flags


def asset_drift(holdings, targets=None, thresholds=None):
    """Current equity:debt:cash vs the stated target. Returns per-class current
    pct, target pct, drift in pp, and the ₹ move to close it (+ add / − trim).
    With no target, reports the relative split and flags drift `relative`."""
    t = _thresholds(thresholds)
    if targets is not None:
        if not isinstance(targets, dict) or not targets:
            raise ValueError("targets must be a nonempty category mapping totaling 100%")
        normalized = {}
        for key, value in targets.items():
            key = _category(key)
            if key == "unknown" or key in normalized:
                raise ValueError("targets require unique named asset classes")
            normalized[key] = _amount(value, "target percentage")
        if not math.isclose(sum(normalized.values()), 100.0, rel_tol=0, abs_tol=1e-8):
            raise ValueError("target percentages must total 100")
        targets = normalized
    rows, valuation_gaps = _valued(holdings)
    cur = aggregate(holdings, "asset_class")
    total = sum(value for _, value in rows)
    amounts = {}
    for holding, value in rows:
        key = _category(holding.get("asset_class"))
        amounts[key] = amounts.get(key, 0.0) + value
    complete = not valuation_gaps and amounts.get("unknown", 0.0) == 0 and total > 0
    gaps = list(valuation_gaps)
    if targets is not None and not complete:
        gaps.append("rebalancing withheld: all holding values and asset classifications are required")
    out = {"relative": targets is None, "total": round(total, 2), "classes": {},
           "rebalance": [], "coverage_complete": complete, "gaps": gaps}
    classes = set(cur["breakdown"]) | set((targets or {}).keys())
    classes.discard("unknown")
    for c in sorted(classes):
        cur_pct = cur["breakdown"].get(c, {}).get("pct", 0.0)
        row = {"current_pct": cur_pct}
        if targets is not None:
            tgt = float(targets.get(c, 0.0))
            exact_pct = 100 * amounts.get(c, 0.0) / total if total else 0.0
            drift = round(exact_pct - tgt, 2)
            move = round(tgt / 100.0 * total - amounts.get(c, 0.0), 2) if complete else None
            row.update({"target_pct": tgt, "drift_pp": drift, "move_value": move})
            if complete and abs(exact_pct - tgt) > t["asset_drift_pp"]:
                verb = "ADD" if move > 0 else "TRIM"
                out["rebalance"].append(
                    f"{verb} ₹{abs(move):,.0f} {c}: {cur_pct:.0f}% vs {tgt:.0f}% target "
                    f"(drift {drift:+.0f}pp)")
        out["classes"][c] = row
    if "unknown" in cur["breakdown"]:
        out["classes"]["unknown"] = {"current_pct": cur["breakdown"]["unknown"]["pct"]}
    return out


def review(holdings, targets=None, breakdowns=None, thresholds=None):
    """The whole allocation read: per-dimension breakdowns, asset drift, and the
    ranked concentration flags — with coverage + gaps so partial data reads as
    partial, never as a confident zero."""
    breakdowns = breakdowns or {}
    rows, gaps = _valued(holdings)
    dims = {}
    total = sum(v for _, v in rows)
    for key in ("asset_class", "sector", "amc", "market_cap", "style"):
        if key in ("market_cap", "style") and key in breakdowns:
            supplied = from_breakdown(breakdowns[key], total)
            known = sum(d["value"] for cat, d in supplied.items() if cat != "unknown")
            coverage = min(1.0, max(0.0, known / total)) if total else 0.0
            dims[key] = {"breakdown": supplied, "coverage": round(coverage, 4),
                         "source": "supplied"}
            if coverage < 1:
                gaps.append(f"{key}: {(1 - coverage) * 100:.0f}% of book untagged")
        else:
            agg = aggregate(holdings, key)
            dims[key] = {"breakdown": agg["breakdown"], "coverage": agg["coverage"],
                         "source": "holdings"}
            if agg["coverage"] < 1.0:
                gaps.append(f"{key}: {(1 - agg['coverage']) * 100:.0f}% of book untagged")
    return {
        "total": round(sum(v for _, v in rows), 2),
        "dimensions": dims,
        "asset_drift": asset_drift(holdings, targets, thresholds),
        "concentration_flags": concentration_flags(holdings, breakdowns, thresholds),
        "gaps": gaps,
    }


def review_book(book):
    """`review` over one {holdings, targets?, breakdowns?, thresholds?} bundle."""
    return review(book.get("holdings", []), book.get("targets"),
                  book.get("breakdowns"), book.get("thresholds"))
