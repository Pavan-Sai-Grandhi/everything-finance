#!/usr/bin/env python3
"""wealth-manager's deterministic engine — the net-worth spine + cross-domain math.

The orchestrating SKILL fetches (IndMoney net-worth payloads via MCP, the three leg
digests via forked leg-runners) and hands the whole picture here as ONE json file;
this module owns every number so none is eyeballed:

  - **spine**: total net worth, per-asset-class allocation across all IndMoney classes,
    equity share, liquid pool, per-holding XIRR summary — from `networth_snapshot` +
    `networth_allocation_breakdown` + the `lib/holdings.py` positions envelope.
  - **cross-domain** (the figures no single leg can produce): emergency-fund months of
    runway, protection-vs-net-worth read, risk posture.
  - **scorecard**: a status per domain (net worth & allocation, investments, protection,
    cashflow, emergency fund) with one line each, scored from the spine + leg digests.

Deterministic, offline, no MCP/network — same discipline as `lib/strategy.py`. Every
input is sourced upstream (IndMoney first-party state, spoke digests); this only weighs.
Absent legs/sources degrade to a labelled "not assessed", never a fabricated number.

Spine schema, scorecard shape, and the input envelope are in `lib/contracts.md`.

CLI:
  python3 wealth.py --input picture.json               # full-review: spine + cross-domain + scorecard
  python3 wealth.py --input picture.json --snapshot    # spine + emergency/protection flags only, no legs
"""
import argparse
import json
import sys


# --------------------------------------------------------------------------- #
# tolerant coercion (mirrors lib/holdings.py — fetched values arrive ₹/%-formatted)
# --------------------------------------------------------------------------- #
def _num(x):
    """Coerce to float, tolerating ₹/comma/%/Cr/L-formatted strings; None on failure."""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.replace(",", "").replace("₹", "").replace("%", "").strip()
        mult = 1.0
        low = s.lower()
        if low.endswith("cr"):
            mult, s = 1e7, s[:-2].strip()
        elif low.endswith("l") or low.endswith("lakh"):
            mult, s = 1e5, s.rstrip("Ll").replace("akh", "").strip()
        if s in ("", "-", "NA", "N/A", "null", "None"):
            return None
        try:
            return float(s) * mult
        except ValueError:
            return None
    return None


def _first(d, *keys):
    """First present, non-empty value among keys of a dict."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d:
            v = d[k]
            if v not in (None, "", [], {}):
                return v
    return None


# --------------------------------------------------------------------------- #
# asset-class canonicalisation — IndMoney's free-text classes → net-worth buckets
# --------------------------------------------------------------------------- #
# One bucket per row of the net-worth-level allocation. `market_linked` marks the
# growth/equity-risk sleeve (drives risk posture); `liquid` marks the emergency-fund
# eligible pool (cash + FD only — debt/funds may be long-duration, kept out on purpose).
_CLASSES = [
    ("us_equity",      ("us stock", "us equit", "foreign", "international")),
    ("equity",         ("indian stock", "stock", "equity", "share", "direct equit")),
    ("mutual_funds",   ("mutual fund", "mf", "sip", "elss")),
    ("debt",           ("debt", "bond", "fixed income", "ncd")),
    ("fd",             ("fixed deposit", "fd", "recurring deposit", "rd")),
    ("epf",            ("epf", "pf", "provident", "ppf", "nps")),
    ("real_estate",    ("real estate", "property", "reit")),
    ("gold",           ("gold", "sgb", "silver", "precious")),
    ("cash",           ("cash", "saving", "bank balance", "wallet", "liquid")),
    ("insurance",      ("insurance", "ulip", "endowment", "cash value")),
    ("crypto",         ("crypto", "bitcoin")),
]
_MARKET_LINKED = {"equity", "mutual_funds", "us_equity", "crypto"}
_LIQUID = {"cash", "fd"}
_LABEL = {
    "equity": "Indian equity", "mutual_funds": "Mutual funds", "us_equity": "US equity",
    "debt": "Debt", "fd": "Fixed deposits", "epf": "EPF/PF/NPS", "real_estate": "Real estate",
    "gold": "Gold", "cash": "Cash", "insurance": "Insurance value", "crypto": "Crypto",
    "other": "Other",
}


def canonical_class(raw):
    """Map an IndMoney asset-class label to a net-worth bucket; unknown → 'other'."""
    s = str(raw or "").lower()
    for bucket, needles in _CLASSES:
        if any(n in s for n in needles):
            return bucket
    return "other"


# --------------------------------------------------------------------------- #
# net-worth spine
# --------------------------------------------------------------------------- #
def _breakdown_rows(breakdown):
    """Dig the per-class [{class, value}] list out of a networth_allocation_breakdown
    payload — tolerant to a list, a wrapped list, or a flat {class: value} dict."""
    if breakdown is None:
        return []
    inner = breakdown
    if isinstance(breakdown, dict):
        wrapped = _first(breakdown, "allocation", "breakdown", "asset_allocation",
                         "networth_allocation_breakdown", "data", "result", "allocations")
        inner = wrapped if wrapped is not None else breakdown
    if isinstance(inner, dict):
        return [{"class": k, "value": v} for k, v in inner.items()]
    if isinstance(inner, list):
        return inner
    return []


def _position_value(p):
    """Market value of a canonical holdings.py position: invested+pnl, else ltp*qty."""
    inv, pnl, ltp, qty = p.get("invested"), p.get("pnl"), p.get("ltp"), p.get("qty")
    if inv is not None and pnl is not None:
        return inv + pnl
    if ltp is not None and qty is not None:
        return ltp * qty
    if inv is not None:
        return inv
    return None


def build_spine(snapshot=None, breakdown=None, positions_env=None):
    """Assemble the net-worth spine. Precedence for the allocation: IndMoney's
    `networth_allocation_breakdown` (authoritative, sees every class) → else aggregate
    the tradeable positions by asset_class (partial, labelled tradeable-only)."""
    gaps = []
    positions = ((positions_env or {}).get("data") or {}).get("positions") or []
    pos_source = (positions_env or {}).get("source")

    # allocation: prefer the official breakdown; fall back to positions
    alloc = {}
    coverage = "complete"
    rows = _breakdown_rows(breakdown)
    if rows:
        for r in rows:
            if not isinstance(r, dict):
                continue
            bucket = canonical_class(_first(r, "class", "asset_class", "category", "name", "label"))
            val = _num(_first(r, "value", "current_value", "amount", "total", "worth"))
            if val is None:
                continue
            alloc[bucket] = alloc.get(bucket, 0.0) + val
    else:
        coverage = "tradeable-only"
        gaps.append("no IndMoney net-worth breakdown — allocation built from tradeable "
                    "holdings only; real estate / EPF / FD / gold / cash not seen")
        for p in positions:
            bucket = canonical_class(p.get("asset_class"))
            val = _position_value(p)
            if val is not None:
                alloc[bucket] = alloc.get(bucket, 0.0) + val

    alloc_total = sum(alloc.values())

    # total net worth: snapshot is authoritative; else sum of allocation
    total = _num(_first(snapshot or {}, "total_net_worth", "net_worth", "networth",
                        "total", "total_value", "current_value"))
    if total is None:
        total = alloc_total if alloc_total else None
        if total is None:
            gaps.append("no net-worth total — neither snapshot nor allocation available")
        elif coverage == "complete":
            gaps.append("net-worth total inferred from allocation breakdown (no snapshot)")

    # percentages off the total we will report against
    denom = total if total else alloc_total
    allocation = {}
    for bucket, val in sorted(alloc.items(), key=lambda kv: -kv[1]):
        pct = round(val / denom * 100, 1) if denom else None
        allocation[bucket] = {"label": _LABEL.get(bucket, bucket.title()),
                              "value": round(val, 2), "pct": pct}

    liquid = round(sum(alloc.get(b, 0.0) for b in _LIQUID), 2)
    market_linked = sum(alloc.get(b, 0.0) for b in _MARKET_LINKED)
    equity_share_pct = round(market_linked / denom * 100, 1) if denom else None

    # per-holding XIRR summary from the tradeable positions
    xirrs = [(p.get("ticker"), p.get("xirr")) for p in positions if p.get("xirr") is not None]
    if xirrs:
        vals = [x for _, x in xirrs]
        best = max(xirrs, key=lambda t: t[1])
        worst = min(xirrs, key=lambda t: t[1])
        xirr_summary = {"count": len(xirrs), "avg": round(sum(vals) / len(vals), 1),
                        "best": {"ticker": best[0], "xirr": best[1]},
                        "worst": {"ticker": worst[0], "xirr": worst[1]}}
    else:
        xirr_summary = None
        if positions:
            gaps.append("no XIRR on holdings (broker/manual source) — return read unavailable")

    as_of = _first(snapshot or {}, "as_of", "as_on", "date") or (positions_env or {}).get("fetched_at")

    return {
        "total_networth": round(total, 2) if total is not None else None,
        "as_of": as_of,
        "allocation": allocation,
        "liquid": liquid,
        "equity_share_pct": equity_share_pct,
        "holdings_xirr": xirr_summary,
        "source": "indmoney" if rows else (pos_source or "none"),
        "coverage": coverage,
        "gaps": gaps + list((positions_env or {}).get("gaps") or []),
    }


# --------------------------------------------------------------------------- #
# cross-domain computation (what no single leg can produce)
# --------------------------------------------------------------------------- #
def _monthly_expenses(cashflow, profile):
    """Resolve monthly expenses for the emergency-fund runway, honestly labelled.
    profile.monthly_expenses (explicit) → cashflow monthly_outflow → recurring_monthly
    (a floor — actual spend is higher). None → caller marks the read not-assessed."""
    if profile.get("monthly_expenses") is not None:
        return _num(profile["monthly_expenses"]), "stated"
    if cashflow:
        out = _num(cashflow.get("monthly_outflow"))
        if out:
            return out, "cashflow-leg outflow"
        rec = _num(cashflow.get("recurring_monthly"))
        if rec:
            return rec, "committed recurring only (floor — actual spend higher)"
    return None, None


def emergency_fund(liquid, monthly_expenses):
    """Months of runway = liquid pool ÷ monthly expenses, vs a 3–6 month target."""
    if not monthly_expenses:
        return {"status": "not_assessed", "months": None,
                "line": "need monthly expenses (run /budget-tracker or state them)"}
    months = round(liquid / monthly_expenses, 1) if monthly_expenses else None
    if months is None:
        status = "not_assessed"
    elif months >= 6:
        status = "strong"
    elif months >= 3:
        status = "adequate"
    elif months >= 1:
        status = "thin"
    else:
        status = "critical"
    tgt = "meets" if months and months >= 3 else "below"
    return {"status": status, "months": months, "target": "3-6 months",
            "line": f"{months} months of runway — {tgt} the 3-6 month target"}


def protection_read(protection):
    """Weigh the protection-leg digest into a net-worth-level status. absent cover on a
    core line (term/health) is the worst; a short line is weak; all adequate is strong."""
    if not protection:
        return {"status": "not_assessed", "line": "protection not assessed — run /insurance-advisor"}
    lines_state = []
    worst = "strong"
    order = {"strong": 0, "adequate": 1, "weak": 2, "critical": 3}
    for kind in ("term", "health"):
        blk = protection.get(kind) or {}
        adq = str(blk.get("adequacy") or "").lower()
        if adq == "absent":
            st, note = "critical", f"{kind}: no cover"
        elif adq == "short":
            st, note = "weak", f"{kind}: short by {blk.get('gap', '?')}"
        elif adq == "adequate":
            st, note = "strong", f"{kind}: adequate"
        else:
            st, note = "not_assessed", f"{kind}: not assessed"
        if st != "not_assessed" and order.get(st, 0) > order.get(worst, 0):
            worst = st
        lines_state.append(note)
    flags = protection.get("red_flags") or []
    line = "; ".join(lines_state)
    if flags:
        line += f" · {len(flags)} policy red flag(s)"
    return {"status": worst, "line": line}


def risk_posture(equity_share_pct, ef_status, prot_status, age=None):
    """Gate 'take more/less risk' on the equity share vs an age-appropriate band, but
    only after the foundation (emergency fund + protection) is sound — a high equity
    share on a thin emergency fund or a protection gap is fragile, not aggressive."""
    if equity_share_pct is None:
        return {"stance": "unknown", "line": "net-worth equity share unknown — connect IndMoney for the full picture"}
    # age-appropriate equity ceiling: '100 - age' rule of thumb, wide band
    ceiling = (100 - age) if age else 70
    foundation_weak = ef_status in ("thin", "critical", "not_assessed") or \
        prot_status in ("weak", "critical")
    if equity_share_pct > ceiling + 10:
        stance = "reduce-risk"
        line = f"equity+MF {equity_share_pct}% is above the ~{ceiling}% ceiling for your profile — trim risk"
    elif foundation_weak:
        stance = "fix-foundation-first"
        line = ("foundation not yet sound (emergency fund / protection) — fix that before "
                "adding equity risk, whatever the equity share")
    elif equity_share_pct < ceiling - 20:
        stance = "can-add-risk"
        line = f"equity+MF {equity_share_pct}% is well below the ~{ceiling}% ceiling — room to add growth assets"
    else:
        stance = "balanced"
        line = f"equity+MF {equity_share_pct}% sits within an age-appropriate band (~{ceiling}% ceiling)"
    return {"stance": stance, "equity_share_pct": equity_share_pct, "line": line}


# --------------------------------------------------------------------------- #
# financial-health scorecard — a status per domain, one line each
# --------------------------------------------------------------------------- #
_RANK = {"strong": 0, "adequate": 1, "thin": 2, "weak": 2, "critical": 3,
         "not_assessed": 9, "unknown": 9}


def _score_networth(spine):
    total = spine.get("total_networth")
    if total is None:
        return {"status": "not_assessed", "line": "net worth unavailable — connect IndMoney"}
    alloc = spine.get("allocation") or {}
    top = next(iter(alloc.items()), None)
    if spine.get("coverage") == "tradeable-only":
        return {"status": "not_assessed",
                "line": "tradeable-only view — connect IndMoney for full net-worth allocation"}
    if top and top[1].get("pct") is not None and top[1]["pct"] > 60:
        return {"status": "weak",
                "line": f"{top[1]['label']} is {top[1]['pct']}% of net worth — heavily concentrated"}
    return {"status": "adequate",
            "line": f"net worth diversified across {len(alloc)} asset classes"}


def _score_investments(inv):
    if not inv:
        return {"status": "not_assessed", "line": "investment book not assessed — run /portfolio-review"}
    flags = inv.get("concentration_flags") or []
    exits = inv.get("top_exits") or []
    severe = [f for f in flags if str(f.get("severity", "")).lower() in ("high", "urgent", "severe")]
    hard_exits = [e for e in exits if str(e.get("verdict", "")).upper() == "EXIT"]
    if severe or hard_exits:
        bits = []
        if severe:
            bits.append(f"{len(severe)} severe concentration flag(s)")
        if hard_exits:
            bits.append(f"{len(hard_exits)} EXIT flag(s)")
        return {"status": "weak", "line": "; ".join(bits) + " — run /portfolio-review"}
    if flags or exits:
        return {"status": "adequate", "line": f"{len(flags)} concentration + {len(exits)} exit/trim flag(s) to review"}
    return {"status": "strong", "line": "no concentration or exit flags"}


def _score_cashflow(cf):
    if not cf:
        return {"status": "not_assessed", "line": "cashflow not assessed — run /budget-tracker"}
    sr = _num(cf.get("savings_rate"))
    if sr is None:
        return {"status": "not_assessed", "line": "savings rate unavailable"}
    leak = cf.get("biggest_leak")
    tail = f"; biggest leak {leak}" if leak else ""
    if sr >= 20:
        return {"status": "strong", "line": f"saving {sr}% of inflow{tail}"}
    if sr >= 10:
        return {"status": "adequate", "line": f"saving {sr}% of inflow — room to lift{tail}"}
    return {"status": "weak", "line": f"saving only {sr}% of inflow{tail}"}


def build_scorecard(spine, legs, cross):
    """One status per domain + the ranked cross-domain action plan (max 5)."""
    inv = (legs or {}).get("investments")
    prot = (legs or {}).get("protection")
    cf = (legs or {}).get("cashflow")

    domains = {
        "net_worth": _score_networth(spine),
        "investments": _score_investments(inv),
        "protection": {"status": cross["protection"]["status"], "line": cross["protection"]["line"]},
        "cashflow": _score_cashflow(cf),
        "emergency_fund": {"status": cross["emergency_fund"]["status"],
                           "line": cross["emergency_fund"]["line"]},
    }

    # overall = worst assessed domain
    assessed = [d["status"] for d in domains.values() if d["status"] != "not_assessed"]
    overall = max(assessed, key=lambda s: _RANK.get(s, 0)) if assessed else "not_assessed"

    actions = _prioritise(domains, spine, legs, cross)
    return {"domains": domains, "overall": overall, "actions": actions}


# priority: protection/emergency-fund gaps outrank fresh-equity moves — the cross-domain
# ordering that no single leg can make. Each action names the spoke to run for depth.
_PRIORITY = [
    ("emergency_fund", ("critical", "thin"), "Build the emergency fund first",
     "park 3-6 months of expenses in liquid FD/sweep before any fresh equity", "/budget-tracker"),
    ("protection", ("critical", "weak"), "Close the protection gap",
     "term + health cover must be sound before adding risk", "/insurance-advisor"),
    ("cashflow", ("weak",), "Lift the savings rate",
     "the biggest leak is the fastest win", "/budget-tracker"),
    ("investments", ("weak",), "Fix concentration / exit laggards",
     "act on the flagged names", "/portfolio-review"),
    ("net_worth", ("weak",), "Diversify the net-worth allocation",
     "the largest sleeve dominates — rebalance across asset classes", "/portfolio-review"),
]


def _prioritise(domains, spine, legs, cross):
    actions = []
    for domain, bad_states, text, step, run in _PRIORITY:
        st = domains.get(domain, {}).get("status")
        if st in bad_states:
            actions.append({"priority": len(actions) + 1, "domain": domain,
                            "status": st, "text": text, "next_step": step, "run": run})
        if len(actions) >= 5:
            break
    # if the foundation is sound and there is room, surface the risk-posture nudge
    if len(actions) < 5 and cross["risk_posture"]["stance"] == "can-add-risk":
        actions.append({"priority": len(actions) + 1, "domain": "risk_posture",
                        "status": "opportunity", "text": "Room to add growth assets",
                        "next_step": cross["risk_posture"]["line"], "run": "/portfolio-review"})
    return actions


# --------------------------------------------------------------------------- #
# top-level assembly
# --------------------------------------------------------------------------- #
def run(picture, snapshot_mode=False):
    """Full picture → {spine, cross_domain, scorecard}. snapshot_mode skips the legs:
    spine + emergency-fund/protection flags only, no scorecard fan-out."""
    spine = build_spine(picture.get("snapshot"), picture.get("breakdown"),
                        picture.get("positions"))
    legs = picture.get("legs") or {}
    profile = picture.get("profile") or {}
    cashflow = legs.get("cashflow")

    exp, exp_basis = _monthly_expenses(cashflow, profile)
    ef = emergency_fund(spine["liquid"], exp)
    ef["expense_basis"] = exp_basis
    prot = protection_read(legs.get("protection"))
    age = profile.get("age")
    risk = risk_posture(spine["equity_share_pct"], ef["status"], prot["status"], age)

    cross = {"emergency_fund": ef, "protection": prot, "risk_posture": risk}

    out = {"spine": spine, "cross_domain": cross, "mode": "snapshot" if snapshot_mode else "full-review"}
    if not snapshot_mode:
        out["scorecard"] = build_scorecard(spine, legs, cross)
    return out


def main():
    ap = argparse.ArgumentParser(description="wealth-manager spine + cross-domain + scorecard engine.")
    ap.add_argument("--input", required=True, help="path to the picture json (spine inputs + leg digests)")
    ap.add_argument("--snapshot", action="store_true", help="spine + emergency/protection flags only, no legs")
    args = ap.parse_args()
    with open(args.input) as f:
        picture = json.load(f)
    print(json.dumps(run(picture, snapshot_mode=args.snapshot), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
