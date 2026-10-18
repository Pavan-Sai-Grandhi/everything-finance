"""wealth-manager's deterministic engine — the net-worth spine + cross-domain math.

The orchestrating SKILL fetches (IndMoney net-worth payloads via MCP, the three leg
digests via forked leg-runners) and hands the whole picture here as ONE json file;
this module owns every number so none is eyeballed:

  - spine: total net worth, per-asset-class allocation across all IndMoney classes, equity
    share, liquid pool, per-holding XIRR summary.
  - cross-domain, the figures no single leg can produce: emergency-fund months of runway,
    protection-vs-net-worth read, risk posture.
  - scorecard: a status per domain with one line each, from the spine + leg digests.

Deterministic and offline: every input is sourced upstream (IndMoney first-party state,
spoke digests) and this only weighs them. Absent legs or sources degrade to a labelled
"not assessed", never a fabricated number.

Spine schema, scorecard shape, and the input envelope are in `finance/contracts.md`.
"""
import json
import re
import math
from datetime import date

from finance import spine
from finance.spine import first as _first, f
from finance.compute.holdings import market_value as _position_value


_SCALE_SUFFIXES = (
    ("crores", 1e7), ("crore", 1e7), ("cr", 1e7),
    ("lakhs", 1e5), ("lakh", 1e5), ("l", 1e5),
)


def _num(x):
    """Coerce to float, tolerating ₹/comma/%/Cr/L-formatted strings; None on failure.
    Wider than `spine.f`, which does not carry the Cr/L multipliers."""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return f(x)
    if isinstance(x, str):
        s = x.replace(",", "").replace("₹", "").replace("%", "").strip()
        mult = 1.0
        low = s.lower()
        for suffix, factor in _SCALE_SUFFIXES:
            if low.endswith(suffix):
                mult, s = factor, s[:-len(suffix)].strip()
                break
        if s in ("", "-", "NA", "N/A", "null", "None"):
            return None
        try:
            return f(float(s) * mult)
        except ValueError:
            return None
    return None


# IndMoney's free-text asset classes map to one bucket per row of the net-worth-level allocation. `market_linked` marks the
# growth/equity-risk sleeve (drives risk posture); `liquid` marks the emergency-fund
# eligible pool (cash + FD only — debt/funds may be long-duration, kept out on purpose).
_CLASSES = [
    # A broker wallet is uninvested cash, even inside a US-stock account.
    ("cash",           ("wallet",)),
    # A sovereign gold bond tracks the gold price; classify it before the "bond" needle.
    ("gold",           ("sovereign gold", "sgb")),
    ("us_equity",      ("us stock", "us equit", "foreign", "international")),
    ("equity",         ("indian stock", "stock", "equity", "share", "direct equit")),
    ("mutual_funds",   ("mutual fund", "mf", "sip", "elss")),
    ("debt",           ("debt", "bond", "fixed income", "ncd", "government security", "g-sec")),
    ("fd",             ("fixed deposit", "fd", "recurring deposit", "rd")),
    ("epf",            ("epf", "pf", "provident", "ppf", "nps")),
    ("real_estate",    ("real estate", "property", "reit")),
    ("gold",           ("gold", "sgb", "silver", "precious")),
    ("cash",           ("cash", "saving", "bank balance", "wallet", "liquid")),
    ("insurance",      ("insurance", "ulip", "endowment", "cash value")),
    ("crypto",         ("crypto", "bitcoin")),
]
_DIRECT_EQUITY = {"equity", "us_equity"}
_LIQUID = {"cash", "fd"}
_LABEL = {
    "equity": "Indian equity", "mutual_funds": "Mutual funds", "us_equity": "US equity",
    "debt": "Debt", "fd": "Fixed deposits", "epf": "EPF/PF/NPS", "real_estate": "Real estate",
    "gold": "Gold", "cash": "Cash", "insurance": "Insurance value", "crypto": "Crypto",
    "other": "Other",
}


def canonical_class(raw):
    """Map an IndMoney asset-class label to a net-worth bucket; unknown → 'other'."""
    s = " ".join(str(raw or "").lower().replace("_", " ").split())
    # Fund wrappers do not reveal portfolio equity exposure, even when their
    # labels contain 'equity', 'international' or 'debt'.
    if re.search(r"\b(?:mutual funds?|mf|elss|sip)\b", s):
        return "mutual_funds"
    for bucket, needles in _CLASSES:
        if any(re.search(r"\b" + re.escape(n) + (r"\w*\b" if n.endswith("equit") else r"s?\b"), s)
               for n in needles):
            return bucket
    return "other"


def _unwrap(payload):
    """MCP tools can return the payload as a JSON string under `result` (IndMoney
    does); decode it once — never evaluate it — and return the inner mapping."""
    if isinstance(payload, dict) and set(payload) == {"result"} and isinstance(payload["result"], str):
        try:
            inner = json.loads(payload["result"])
        except ValueError:
            return payload
        return inner if isinstance(inner, dict) else payload
    return payload


def _breakdown_rows(breakdown):
    """Dig the per-class [{class, value}] list out of a networth_allocation_breakdown
    payload — tolerant to a list, a wrapped list, or a flat {class: value} dict."""
    breakdown = _unwrap(breakdown)
    if breakdown is None:
        return []
    inner = breakdown
    if isinstance(breakdown, dict):
        wrapped = _first(breakdown, "allocation", "breakdown", "asset_allocation",
                         "networth_allocation_breakdown", "investments", "data", "result",
                         "allocations")
        inner = wrapped if wrapped is not None else breakdown
    if isinstance(inner, dict):
        return [{"class": k, "value": v} for k, v in inner.items()]
    if isinstance(inner, list):
        return inner
    return []


_RESERVE_UNVERIFIED = ("emergency-reserve availability unverified: cash/FD labels alone do not "
                       "establish accessible funds")


def build_spine(snapshot=None, breakdown=None, positions_env=None, liabilities=None):
    """Assemble the net-worth spine. Precedence for the allocation: IndMoney's
    `networth_allocation_breakdown` (authoritative, sees every class) → else aggregate
    the tradeable positions by asset_class (partial, labelled tradeable-only)."""
    gaps = []
    positions = ((positions_env or {}).get("data") or {}).get("positions") or []
    if not isinstance(positions, list):
        gaps.append("invalid positions collection — holdings unavailable")
        positions = []
    if any(not isinstance(p, dict) for p in positions):
        gaps.append("malformed position rows excluded")
        positions = [p for p in positions if isinstance(p, dict)]
    pos_source = (positions_env or {}).get("source")

    alloc = {}
    coverage = "complete"
    rows = _breakdown_rows(breakdown)
    if rows:
        for r in rows:
            if not isinstance(r, dict):
                coverage = "incomplete"
                gaps.append("malformed asset breakdown row excluded")
                continue
            bucket = canonical_class(_first(r, "class", "asset_class", "asset_type", "category",
                                            "name", "label"))
            val = _num(_first(r, "value", "current_value", "amount", "total", "worth"))
            if val is None or val < 0:
                coverage = "incomplete"
                gaps.append(f"{bucket}: missing or unsupported negative asset value")
                continue
            alloc[bucket] = alloc.get(bucket, 0.0) + val
    else:
        coverage = "tradeable-only"
        gaps.append("no IndMoney net-worth breakdown — allocation built from tradeable "
                    "holdings only; real estate / EPF / FD / gold / cash not seen")
        for p in positions:
            bucket = canonical_class(p.get("asset_class"))
            val = _position_value(p)
            if val is None:
                coverage = "incomplete"
                gaps.append(f"{p.get('ticker', '?')}: no current value — holding excluded from the subtotal")
                continue
            alloc[bucket] = alloc.get(bucket, 0.0) + val

    alloc_total = sum(alloc.values())

    # Optional canonical liability evidence is supplied by the orchestrator, not
    # guessed from an undocumented broker payload field or a balancing difference.
    liability_total, liability_evidence = None, None
    if liabilities is not None:
        liability_total, liability_evidence, liability_gap = _dated_amount(liabilities, "total", "liabilities")
        if liability_gap:
            gaps.append(liability_gap)
            coverage = "incomplete"

    snapshot = _unwrap(snapshot) or {}
    total = _num(_first(snapshot, "total_net_worth", "total_networth", "net_worth", "networth",
                        "total", "total_value", "current_value"))
    # With no observed assets there is nothing to net a liability against.
    calculated_net = alloc_total - liability_total if liability_total is not None and alloc else None
    if total is None:
        total = calculated_net if calculated_net is not None else (alloc_total if alloc else None)
        if total is None:
            gaps.append("no net-worth total — neither snapshot nor allocation available")
        elif liability_total is None:
            coverage = "incomplete" if rows else coverage
            gaps.append("asset subtotal only: no reported net worth or verified liability total")
        else:
            gaps.append("net worth calculated from supplied assets minus sourced liabilities")

    comparable = calculated_net if liability_total is not None else alloc_total
    if rows and total is not None and not math.isclose(comparable, total, rel_tol=1e-8, abs_tol=0.01):
        coverage = "incomplete"
        gaps.append("asset/liability breakdown does not reconcile with reported net worth; reconcile missing rows or valuation dates")
    # Asset allocation describes the gross asset mix. Dividing it by leveraged
    # net worth would produce percentages above 100% unrelated to composition.
    denom = alloc_total if liability_total is not None else total
    denom = denom if denom is not None and denom > 0 else None
    allocation = {}
    for bucket, val in sorted(alloc.items(), key=lambda kv: -kv[1]):
        pct = round(val / denom * 100, 1) if denom else None
        allocation[bucket] = {"label": _LABEL.get(bucket, bucket.title()),
                              "value": round(val, 2), "pct": pct}

    observed_liquid = round(sum(alloc.get(b, 0.0) for b in _LIQUID), 2)
    liquid = None
    gaps.append(_RESERVE_UNVERIFIED)
    direct_equity = sum(alloc.get(b, 0.0) for b in _DIRECT_EQUITY)
    known_equity_share_pct = round(direct_equity / denom * 100, 1) if denom and denom > 0 else None
    unknown_equity_value = sum(alloc.get(b, 0.0) for b in ("mutual_funds", "other", "epf", "insurance"))
    equity_share_pct = known_equity_share_pct if unknown_equity_value == 0 and coverage == "complete" else None
    if equity_share_pct is None:
        gaps.append("total equity exposure unavailable: unresolved fund/other asset composition or incomplete book; direct equity shown separately")

    xirrs, weighted = [], []
    for position in positions:
        raw = position.get("xirr")
        rate = f(raw) if not isinstance(raw, bool) else None
        if rate is None:
            if raw is not None:
                gaps.append(f"{position.get('ticker', '?')}: invalid holding XIRR omitted")
            continue
        xirrs.append((position.get("ticker"), rate))
        value = _position_value(position)
        if value is not None and value > 0:
            weighted.append((value, rate))
    if xirrs:
        best = max(xirrs, key=lambda t: t[1])
        worst = min(xirrs, key=lambda t: t[1])
        # Normalize before multiplying so finite large position values do not overflow.
        scale = max((value for value, _ in weighted), default=1)
        weights = [(value / scale, rate) for value, rate in weighted]
        weight_sum = sum(weight for weight, _ in weights)
        mean = f(sum(weight / weight_sum * rate for weight, rate in weights)) if weight_sum else None
        xirr_summary = {"count": len(xirrs), "avg": round(mean, 1) if mean is not None else None,
                        "weighted_count": len(weighted),
                        "method": "current-value-weighted mean of holding XIRRs; not portfolio XIRR",
                        "portfolio_xirr": None,
                        "best": {"ticker": best[0], "xirr": best[1]},
                        "worst": {"ticker": worst[0], "xirr": worst[1]}}
        gaps.append("portfolio XIRR is not computed from holding XIRRs; dated aggregate cash flows are required")
    else:
        xirr_summary = None
        if positions:
            gaps.append("no XIRR on holdings (broker/manual source) — return read unavailable")

    as_of = _first(snapshot, "as_of", "as_on", "date") or (positions_env or {}).get("fetched_at")

    return {
        "total_networth": round(total, 2) if total is not None else None,
        "as_of": as_of,
        "allocation": allocation,
        "liquid": liquid,
        "observed_liquid": observed_liquid,
        "allocation_total": round(alloc_total, 2),
        "liabilities_total": liability_total,
        "liabilities_evidence": liability_evidence,
        "allocation_basis": "gross_assets" if liability_total is not None else "reported_total",
        "equity_share_pct": equity_share_pct,
        "known_equity_share_pct": known_equity_share_pct,
        "unclassified_equity_value": unknown_equity_value,
        "holdings_xirr": xirr_summary,
        "source": "indmoney" if rows else (pos_source or "none"),
        "coverage": coverage,
        "gaps": gaps + list((positions_env or {}).get("gaps") or []),
    }


def _dated_amount(block, value_key, label):
    """Validate an explicitly sourced balance supplied by the orchestrator."""
    if not isinstance(block, dict):
        return None, None, f"need a sourced, dated {label} balance"
    value = _num(block.get(value_key))
    source = block.get("source")
    try:
        stamp = date.fromisoformat(block.get("as_of"))
    except (ValueError, TypeError):
        stamp = None
    if (value is None or value < 0 or stamp is None or stamp > date.today()
            or not isinstance(source, str) or not source.strip()):
        return None, None, f"{label} requires nonnegative {value_key}, past/current ISO as_of and source"
    return value, {"as_of": stamp.isoformat(), "source": source.strip()}, None


def _reserve(profile):
    return _dated_amount(profile.get("emergency_reserve"), "available_value", "emergency reserve")


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
    liquid, monthly_expenses = _num(liquid), _num(monthly_expenses)
    if liquid is None or liquid < 0 or monthly_expenses is None or monthly_expenses <= 0:
        return {"status": "not_assessed", "months": None,
                "line": "need a nonnegative liquid balance and positive monthly expenses"}
    exact_months = f(liquid / monthly_expenses)
    months = round(exact_months, 1) if exact_months is not None else None
    if months is None:
        status = "not_assessed"
    elif exact_months >= 6:
        status = "strong"
    elif exact_months >= 3:
        status = "adequate"
    elif exact_months >= 1:
        status = "thin"
    else:
        status = "critical"
    tgt = "meets" if exact_months is not None and exact_months >= 3 else "below"
    return {"status": status, "months": months, "target": "3-6 months",
            "line": f"{months} months of runway — {tgt} the 3-6 month target"}


def protection_read(protection):
    """Weigh the protection-leg digest into a net-worth-level status. absent cover on a
    core line (term/health) is the worst; a short line is weak; all adequate is strong."""
    if not protection:
        return {"status": "not_assessed", "line": "protection not assessed — run /insurance-advisor"}
    lines_state = []
    worst = "strong"
    missing = False
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
            missing = True
        if st != "not_assessed" and order.get(st, 0) > order.get(worst, 0):
            worst = st
        lines_state.append(note)
    flags = protection.get("red_flags") or []
    line = "; ".join(lines_state)
    if flags:
        line += f" · {len(flags)} policy red flag(s)"
    return {"status": "not_assessed" if (missing or flags) and worst == "strong" else worst, "line": line}


def risk_posture(equity_share_pct, ef_status, prot_status, equity_band=None):
    """Compare exposure with the user's stated range; there is no age-based default.

    A range comparison is a review finding, not authorization to transact.
    """
    share = _num(equity_share_pct)
    if share is None or not 0 <= share <= 100:
        return {"stance": "unknown", "line": "net-worth equity share unavailable or invalid"}
    if ef_status not in ("strong", "adequate") or prot_status not in ("strong", "adequate"):
        return {"stance": "fix-foundation-first", "equity_share_pct": share,
                "line": "emergency-fund or protection evidence is weak/incomplete — resolve it before considering more equity risk"}
    if not isinstance(equity_band, dict):
        return {"stance": "unknown", "equity_share_pct": share,
                "line": "no stated equity target range; age alone does not establish suitable exposure"}
    low, high = _num(equity_band.get("min_pct")), _num(equity_band.get("max_pct"))
    if low is None or high is None or not 0 <= low <= high <= 100:
        return {"stance": "unknown", "equity_share_pct": share,
                "line": "equity target range must satisfy 0 <= min_pct <= max_pct <= 100"}
    if share > high:
        stance, comparison = "above-target", "above"
    elif share < low:
        stance, comparison = "below-target", "below"
    else:
        stance, comparison = "within-target", "within"
    return {"stance": stance, "equity_share_pct": share,
            "equity_band": {"min_pct": low, "max_pct": high},
            "line": f"equity exposure {share}% is {comparison} the stated {low}–{high}% range; review goals, liquidity and costs before changing allocation"}


_RANK = {"strong": 0, "adequate": 1, "thin": 2, "weak": 2, "critical": 3,
         "not_assessed": 9, "unknown": 9}


def _score_networth(spine):
    total = spine.get("total_networth")
    if total is None:
        return {"status": "not_assessed", "line": "net worth unavailable — connect IndMoney"}
    alloc = spine.get("allocation") or {}
    if not alloc:
        return {"status": "not_assessed", "line": "asset allocation unavailable"}
    top = next(iter(alloc.items()), None)
    if spine.get("coverage") != "complete":
        return {"status": "not_assessed",
                "line": "incomplete or unreconciled allocation — complete the asset/liability picture"}
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
    severe = [f for f in flags if str(f.get("severity", "")).lower() in ("act", "high", "urgent", "severe")]
    hard_exits = [e for e in exits if str(e.get("verdict", "")).upper() == "EXIT"]
    if severe or hard_exits:
        bits = []
        if severe:
            bits.append(f"{len(severe)} severe concentration flag(s)")
        if hard_exits:
            bits.append(f"{len(hard_exits)} EXIT flag(s)")
        return {"status": "weak", "line": "; ".join(bits) + " — run /portfolio-review"}
    if (inv.get("gaps") or "concentration_flags" not in inv or "top_exits" not in inv):
        return {"status": "not_assessed", "line": "investment evidence incomplete — review data gaps"}
    if flags or exits:
        return {"status": "adequate", "line": f"{len(flags)} concentration + {len(exits)} exit/trim flag(s) to review"}
    return {"status": "strong", "line": "no concentration or exit flags"}


def _score_cashflow(cf):
    if not cf:
        return {"status": "not_assessed", "line": "cashflow not assessed — run /budget-tracker"}
    sr = _num(cf.get("savings_rate"))
    if sr is None or sr > 100:
        return {"status": "not_assessed", "line": "savings rate unavailable or invalid"}
    if cf.get("gaps"):
        return {"status": "not_assessed", "line": "cashflow evidence incomplete — review source gaps"}
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
    return {"domains": domains, "overall": overall, "actions": actions,
            "assessed_domains": len(assessed), "total_domains": len(domains),
            "coverage_complete": len(assessed) == len(domains)}


# priority: protection/emergency-fund gaps outrank fresh-equity moves — the cross-domain
# ordering that no single leg can make. Each action names the spoke to run for depth.
_PRIORITY = [
    ("emergency_fund", ("critical", "thin"), "Build the emergency fund first",
     "confirm accessible reserve needs against complete expenses and near-term commitments", "/budget-tracker"),
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
    if len(actions) < 5 and cross["risk_posture"]["stance"] in ("below-target", "above-target"):
        actions.append({"priority": len(actions) + 1, "domain": "risk_posture",
                        "status": "review", "text": "Review allocation against the stated target",
                        "next_step": cross["risk_posture"]["line"], "run": "/portfolio-review"})
    return actions


def run(picture, snapshot_mode=False):
    """Full picture → {spine, cross_domain, scorecard}. snapshot_mode skips the legs:
    spine + emergency-fund/protection flags only, no scorecard fan-out."""
    if not isinstance(picture, dict):
        raise ValueError("wealth picture must be an object")
    for key in ("snapshot", "positions", "profile", "legs"):
        if picture.get(key) is not None and not isinstance(picture[key], dict):
            raise ValueError(f"{key} must be an object")
    for key, value in (picture.get("legs") or {}).items():
        if value is not None and not isinstance(value, dict):
            raise ValueError(f"{key} leg must be an object")
    spine = build_spine(picture.get("snapshot"), picture.get("breakdown"),
                        picture.get("positions"), picture.get("liabilities"))
    legs = picture.get("legs") or {}
    profile = picture.get("profile") or {}
    cashflow = legs.get("cashflow")
    reserve, reserve_evidence, reserve_gap = _reserve(profile)
    if reserve_gap:
        spine["gaps"].append(reserve_gap)
    else:
        spine["liquid"] = reserve
        spine["reserve_evidence"] = reserve_evidence
        spine["gaps"].remove(_RESERVE_UNVERIFIED)

    exp, exp_basis = _monthly_expenses(cashflow, profile)
    ef = emergency_fund(spine["liquid"], exp)
    if exp_basis and "floor" in exp_basis:
        ef = {"status": "not_assessed", "months": None,
              "months_upper_bound": ef.get("months"),
              "line": "recurring expenses are only a floor; complete monthly spending is needed to assess runway"}
    ef["expense_basis"] = exp_basis
    ef["reserve_evidence"] = reserve_evidence
    prot = protection_read(legs.get("protection"))
    risk = risk_posture(spine["equity_share_pct"], ef["status"], prot["status"],
                        equity_band=profile.get("equity_band"))

    cross = {"emergency_fund": ef, "protection": prot, "risk_posture": risk}

    out = {"spine": spine, "cross_domain": cross, "mode": "snapshot" if snapshot_mode else "full-review"}
    if not snapshot_mode:
        out["scorecard"] = build_scorecard(spine, legs, cross)
    return out


@spine.guarded("finance.compute.wealth")
def report(picture, snapshot=False):
    """`run` over the picture JSON file the orchestrator assembled."""
    result = run(spine.read_json(picture), snapshot_mode=snapshot)
    return spine.envelope(True, "finance.compute.wealth", result, list(result["spine"].get("gaps", [])))
