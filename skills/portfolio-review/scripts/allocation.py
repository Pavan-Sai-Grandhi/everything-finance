#!/usr/bin/env python3
"""Multi-dimensional allocation + concentration engine (portfolio-review).

Pure computation over the canonical positions the shared `lib/holdings.py`
resolver returns — no fetch, no MCP. The skill enriches each position with the
dimension tags it gathered (sector, market-cap, AMC, style, asset-class) and the
pre-aggregated breakdowns IndMoney / mf-analysis look-through supply, then hands
the bundle here; this module decides breakdowns, drift-vs-target, and the
concentration breaches with concrete ₹ rebalancing moves. Keeping the arithmetic
in one tested place is why the skill's report and the `quick` digest can't disagree.

Two provenance-honest input styles per dimension:
  * per-holding tag — `sector`, `amc`, single-stock, `asset_class` aggregate by
    summing each holding's market value; a missing tag lands in `unknown` and
    lowers that dimension's coverage.
  * pre-aggregated breakdown — `market_cap` and `style` arrive as category→₹ (or
    →pct) dicts from IndMoney `networth_allocation_breakdown` / mf-analysis
    look-through, because they are portfolio-level weights, not one tag per row.

Market value precedence per holding: explicit `value` → `qty*ltp` → `invested`
→ `qty*avg`. A holding that yields no value is dropped with a labelled gap
rather than counted as zero.

CLI:
  python3 allocation.py --book book.json      # {holdings, targets?, breakdowns?, thresholds?}
"""
import argparse
import json
import sys

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

_SMALL_CAPS = ("small", "micro")


# --------------------------------------------------------------------------- #
# market value                                                                #
# --------------------------------------------------------------------------- #
def market_value(h):
    """Current ₹ value of a holding, by precedence. None when nothing resolves."""
    v = h.get("value")
    if v is not None:
        return float(v)
    qty = h.get("qty")
    ltp = h.get("ltp")
    if qty is not None and ltp is not None:
        return float(qty) * float(ltp)
    inv = h.get("invested")
    if inv is not None:
        return float(inv)
    avg = h.get("avg")
    if qty is not None and avg is not None:
        return float(qty) * float(avg)
    return None


def _valued(holdings):
    """Split holdings into (valued rows [(h, value)], gaps for the unvaluable)."""
    rows, gaps = [], []
    for h in holdings:
        v = market_value(h)
        if v is None:
            gaps.append(f"{h.get('ticker', '?')}: no price/cost — excluded from allocation")
        else:
            rows.append((h, v))
    return rows, gaps


# --------------------------------------------------------------------------- #
# breakdowns                                                                   #
# --------------------------------------------------------------------------- #
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
        cat = str(cat).lower() if cat not in (None, "") else "unknown"
        buckets[cat] = buckets.get(cat, 0.0) + v
    known = total - buckets.get("unknown", 0.0)
    coverage = (known / total) if total else 0.0
    return {"breakdown": _pcts(buckets, total), "coverage": round(coverage, 4), "total": round(total, 2)}


def from_breakdown(breakdown, total=None):
    """Normalize a caller-supplied category→(₹ or {value}/{pct}) dict to the same
    {category: {value, pct}} shape. When values look like percentages (sum ≈ 100
    and no `total`), they are treated as pct and value left as the pct number."""
    flat = {}
    for cat, v in breakdown.items():
        if isinstance(v, dict):
            flat[str(cat).lower()] = float(v.get("value", v.get("pct", 0.0)))
        else:
            flat[str(cat).lower()] = float(v)
    s = sum(flat.values())
    if total is None:
        total = s
    return _pcts(flat, total)


# --------------------------------------------------------------------------- #
# concentration flags                                                         #
# --------------------------------------------------------------------------- #
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
    t = {**DEFAULTS, **(thresholds or {})}
    breakdowns = breakdowns or {}
    rows, _ = _valued(holdings)
    total = sum(v for _, v in rows)
    flags = []
    if total <= 0:
        return flags

    # single stock — per holding, stocks only (funds are diversified by design)
    for h, v in rows:
        if str(h.get("kind", "stock")).lower() == "fund":
            continue
        pct = 100.0 * v / total
        if pct > t["single_stock"]:
            flags.append(_flag("single_stock", h.get("ticker", "?"), pct, v,
                               t["single_stock"], total, "watch", "single-name risk"))

    # sector — per holding tag
    sec = aggregate(holdings, "sector", total)["breakdown"]
    for cat, d in sec.items():
        if cat == "unknown":
            continue
        if d["pct"] > t["single_sector"]:
            urgent = d["pct"] > t["single_sector_urgent"]
            flags.append(_flag("sector", cat, d["pct"], d["value"], t["single_sector"],
                               total, "act" if urgent else "watch",
                               "sector concentration" + (" — urgent" if urgent else "")))

    # AMC — per fund tag
    amc = aggregate(holdings, "amc", total)["breakdown"]
    for cat, d in amc.items():
        if cat == "unknown":
            continue
        if d["pct"] > t["single_amc"]:
            flags.append(_flag("amc", cat, d["pct"], d["value"], t["single_amc"],
                               total, "watch", "one fund house"))

    # market cap — small+micro sleeve, from the supplied breakdown
    cap = breakdowns.get("market_cap")
    if cap:
        capb = from_breakdown(cap, total)
        small = sum(d["value"] for c, d in capb.items()
                    if any(s in c for s in _SMALL_CAPS))
        pct = 100.0 * small / total
        if pct > t["smallcap_microcap"]:
            flags.append(_flag("smallcap_microcap", "small+micro", pct, small,
                               t["smallcap_microcap"], total, "watch",
                               "narrow exit doors in a correction"))

    flags.sort(key=lambda f: f["pct"], reverse=True)
    return flags


# --------------------------------------------------------------------------- #
# asset-class drift vs target                                                 #
# --------------------------------------------------------------------------- #
def asset_drift(holdings, targets=None, thresholds=None):
    """Current equity:debt:cash vs the stated target. Returns per-class current
    pct, target pct, drift in pp, and the ₹ move to close it (+ add / − trim).
    With no target, reports the relative split and flags drift `relative`."""
    t = {**DEFAULTS, **(thresholds or {})}
    cur = aggregate(holdings, "asset_class")
    total = cur["total"]
    out = {"relative": targets is None, "total": total, "classes": {}, "rebalance": []}
    classes = set(cur["breakdown"]) | set((targets or {}).keys())
    classes.discard("unknown")
    for c in sorted(classes):
        cur_pct = cur["breakdown"].get(c, {}).get("pct", 0.0)
        row = {"current_pct": cur_pct}
        if targets is not None:
            tgt = float(targets.get(c, 0.0))
            drift = round(cur_pct - tgt, 2)
            move = round((tgt - cur_pct) / 100.0 * total, 2)
            row.update({"target_pct": tgt, "drift_pp": drift, "move_value": move})
            if abs(drift) > t["asset_drift_pp"]:
                verb = "ADD" if move > 0 else "TRIM"
                out["rebalance"].append(
                    f"{verb} ₹{abs(move):,.0f} {c}: {cur_pct:.0f}% vs {tgt:.0f}% target "
                    f"(drift {drift:+.0f}pp)")
        out["classes"][c] = row
    if "unknown" in cur["breakdown"]:
        out["classes"]["unknown"] = {"current_pct": cur["breakdown"]["unknown"]["pct"]}
    return out


# --------------------------------------------------------------------------- #
# top-level review                                                            #
# --------------------------------------------------------------------------- #
def review(holdings, targets=None, breakdowns=None, thresholds=None):
    """The whole allocation read: per-dimension breakdowns, asset drift, and the
    ranked concentration flags — with coverage + gaps so partial data reads as
    partial, never as a confident zero."""
    breakdowns = breakdowns or {}
    _, gaps = _valued(holdings)
    dims = {}
    for key in ("asset_class", "sector", "amc", "market_cap", "style"):
        if key in ("market_cap", "style") and key in breakdowns:
            dims[key] = {"breakdown": from_breakdown(breakdowns[key]), "coverage": 1.0,
                         "source": "supplied"}
        else:
            agg = aggregate(holdings, key)
            dims[key] = {"breakdown": agg["breakdown"], "coverage": agg["coverage"],
                         "source": "holdings"}
            if agg["coverage"] < 1.0:
                gaps.append(f"{key}: {(1 - agg['coverage']) * 100:.0f}% of book untagged")
    return {
        "total": round(sum(v for _, v in _valued(holdings)[0]), 2),
        "dimensions": dims,
        "asset_drift": asset_drift(holdings, targets, thresholds),
        "concentration_flags": concentration_flags(holdings, breakdowns, thresholds),
        "gaps": gaps,
    }


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Multi-dimensional allocation + concentration.")
    ap.add_argument("--book", required=True,
                    help="JSON: {holdings:[...], targets?:{}, breakdowns?:{}, thresholds?:{}}")
    args = ap.parse_args()
    with open(args.book) as f:
        book = json.load(f)
    out = review(book.get("holdings", []), book.get("targets"),
                 book.get("breakdowns"), book.get("thresholds"))
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
