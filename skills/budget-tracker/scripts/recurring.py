#!/usr/bin/env python3
"""Detect committed recurring spend — subscriptions, EMIs, memberships (design Section 2).

Deterministic and reproducible from the artifacts: groups debits by the SAME merchant
token categorize.py uses, finds a stable cadence (monthly / quarterly / annual) and a
roughly stable amount, and surfaces:

  * total committed **recurring ₹/month** (dormant charges excluded),
  * the list of detected subscriptions/EMIs/memberships with the months each was seen in,
  * flags: **new** (first appearance is the current month), **price_creep** (amount rose
    vs the prior cadence), **dormant** (an established recurring charge that lapsed —
    maybe fine, maybe a missed cancellation worth confirming).

With no prior months the run sees only the current statements: a single occurrence of a
known-subscription merchant is still surfaced, at **low** confidence with the cadence
*inferred* rather than observed.

CLI:  recurring.py --txns txns.json [--as-of YYYY-MM-DD] [--out out.json]
"""
import argparse
import json
import os
import statistics
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import categorize  # noqa: E402  (shares the one merchant tokenizer)

# cadence label -> (min_days, max_days, months_per_charge) for the median inter-charge gap
CADENCE_BANDS = [
    ("monthly", 24, 38, 1),
    ("quarterly", 80, 100, 3),
    ("annual", 350, 400, 12),
]
# merchants that are recurring by nature — lets a single sighting (no prior months) be
# surfaced low-confidence with an inferred monthly cadence.
SUBSCRIPTION_HINTS = {"NETFLIX", "SPOTIFY", "HOTSTAR", "PRIME", "YOUTUBE", "APPLE",
                      "GOOGLE", "ADOBE", "AUDIBLE", "LINKEDIN", "ICLOUD", "GYM",
                      "CULT", "CULTFIT", "SWIGGY ONE", "ZOMATO GOLD"}

AMOUNT_SPREAD_TOL = 0.30   # rel. spread allowed and still called "roughly stable"
CREEP_THRESHOLD = 0.05     # latest > prior * (1+this) -> price creep
DORMANT_FACTOR = 1.6       # last seen older than this * cadence -> dormant


def _d(s):
    return date.fromisoformat(str(s)[:10])


def _month(s):
    return str(s)[:7]


def _months_between(cadence_days):
    for label, lo, hi, mpc in CADENCE_BANDS:
        if lo <= cadence_days <= hi:
            return label, mpc
    return None, None


def _monthly_equiv(amount, months_per_charge):
    return amount / months_per_charge if months_per_charge else amount


def detect(transactions, as_of=None):
    """-> {as_of, current_month, total_committed_monthly, subscriptions:[...], flagged:{...}}.

    Only debits participate. ``as_of`` (default: latest txn date) anchors "current month"
    and the dormancy check."""
    debits = [t for t in transactions
              if str(t.get("direction", "")).lower() in ("debit", "dr", "d")
              and t.get("date")]
    if not debits:
        return {"as_of": as_of, "current_month": _month(as_of) if as_of else None,
                "total_committed_monthly": 0.0, "subscriptions": [], "flagged": {}}

    as_of = _d(as_of) if as_of else max(_d(t["date"]) for t in debits)
    current_month = as_of.isoformat()[:7]

    groups = {}
    for t in debits:
        tok = categorize.normalize_token(t.get("description", ""))
        groups.setdefault(tok, []).append(t)

    subs = []
    for token, rows in groups.items():
        rows = sorted(rows, key=lambda r: _d(r["date"]))
        dates = [_d(r["date"]) for r in rows]
        amounts = [abs(float(r.get("amount", 0) or 0)) for r in rows]
        months = sorted({_month(r["date"]) for r in rows})
        n = len(rows)
        desc = rows[-1].get("description", "")
        cat, _bucket, _src = categorize.categorize_one(desc, {})

        cadence, months_per_charge, cadence_days, confidence = None, None, None, None
        if n >= 2:
            gaps = [(dates[i] - dates[i - 1]).days for i in range(1, n)]
            cadence_days = statistics.median(gaps)
            cadence, months_per_charge = _months_between(cadence_days)
            spread = (max(amounts) - min(amounts)) / statistics.median(amounts) \
                if statistics.median(amounts) else 0
            if cadence and spread <= AMOUNT_SPREAD_TOL + CREEP_THRESHOLD:
                confidence = "high" if n >= 3 else "medium"
        if confidence is None:
            # single sighting (or no clean cadence): infer only for known subscriptions
            up = desc.upper()
            if n == 1 and (token in SUBSCRIPTION_HINTS
                           or any(h in up for h in SUBSCRIPTION_HINTS)):
                cadence, months_per_charge, confidence = "monthly", 1, "low"
            else:
                continue  # not recurring

        latest_amount = amounts[-1]
        flags = []
        if months[0] == current_month:
            flags.append("new")
        if n >= 2:
            prior = statistics.median(amounts[:-1])
            if latest_amount > prior * (1 + CREEP_THRESHOLD):
                flags.append("price_creep")
            # dormant: an established cadence whose next charge is overdue
            if confidence in ("high", "medium") and cadence_days:
                overdue = (as_of - dates[-1]).days
                if overdue > cadence_days * DORMANT_FACTOR:
                    flags.append("dormant")

        subs.append({
            "merchant": token,
            "description": desc,
            "category": cat,
            "cadence": cadence,
            "amount": round(latest_amount, 2),
            "monthly_equivalent": round(_monthly_equiv(latest_amount, months_per_charge), 2),
            "occurrences": n,
            "months_observed": months,
            "last_seen": dates[-1].isoformat(),
            "confidence": confidence,
            "prior_amount": round(statistics.median(amounts[:-1]), 2) if n >= 2 else None,
            "flags": flags,
        })

    subs.sort(key=lambda s: s["monthly_equivalent"], reverse=True)
    committed = sum(s["monthly_equivalent"] for s in subs if "dormant" not in s["flags"])
    flagged = {
        "new": [s["merchant"] for s in subs if "new" in s["flags"]],
        "price_creep": [s["merchant"] for s in subs if "price_creep" in s["flags"]],
        "dormant": [s["merchant"] for s in subs if "dormant" in s["flags"]],
    }
    return {
        "as_of": as_of.isoformat(),
        "current_month": current_month,
        "total_committed_monthly": round(committed, 2),
        "subscriptions": subs,
        "flagged": flagged,
    }


def _main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--txns", required=True, help="JSON file: normalized transactions "
                    "across the current + prior months")
    ap.add_argument("--as-of", dest="as_of", help="anchor date YYYY-MM-DD (default: latest txn)")
    ap.add_argument("--out", help="write result JSON here")
    args = ap.parse_args(argv)

    with open(args.txns) as f:
        transactions = json.load(f)
    result = detect(transactions, as_of=args.as_of)
    payload = json.dumps(result, indent=2, default=str)
    if args.out:
        with open(args.out, "w") as f:
            f.write(payload)
        print(json.dumps({"out": args.out, "count": len(result["subscriptions"]),
                          "committed_monthly": result["total_committed_monthly"]}))
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
