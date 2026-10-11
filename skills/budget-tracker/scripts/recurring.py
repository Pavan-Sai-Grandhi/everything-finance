#!/usr/bin/env python3
"""Detect committed recurring spend — subscriptions, EMIs, memberships.

Deterministic and reproducible from the artifacts: groups debits by the SAME merchant
token categorize.py uses, finds a stable cadence (monthly / quarterly / annual) and a
roughly stable amount, and surfaces:

  * total committed recurring ₹/month (dormant charges excluded),
  * the list of detected subscriptions/EMIs/memberships with the months each was seen in,
  * flags: `new` (first appearance is the current month), `price_creep` (amount rose vs the
    prior cadence), `dormant` (an established recurring charge that lapsed — maybe fine,
    maybe a missed cancellation worth confirming).

With no prior months the run sees only the current statements: a single occurrence of a
known-subscription merchant is still surfaced, at **low** confidence with the cadence
unconfirmed and excluded from the monthly total.

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
# surfaced as low-confidence candidates; one charge cannot establish a cadence.
SUBSCRIPTION_HINTS = {"NETFLIX", "SPOTIFY", "HOTSTAR", "PRIME", "YOUTUBE", "APPLE",
                      "GOOGLE", "ADOBE", "AUDIBLE", "LINKEDIN", "ICLOUD", "GYM",
                      "CULT", "CULTFIT", "SWIGGY ONE", "ZOMATO GOLD"}

AMOUNT_SPREAD_TOL = 0.30   # rel. spread allowed and still called "roughly stable"
CREEP_THRESHOLD = 0.05     # latest > prior * (1+this) -> price creep
DORMANT_FACTOR = 1.6       # last seen older than this * cadence -> dormant


def _d(s):
    if not isinstance(s, str) or len(s) != 10:
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(s)


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
    transactions, gaps = categorize.validate_transactions(transactions)
    anchor = _d(as_of) if as_of is not None else None
    debits = []
    for row in transactions:
        if row["direction"] != "debit" or row["amount"] == 0:
            continue
        if anchor is not None and _d(row["date"]) > anchor:
            gaps.append("Transaction after as-of date; excluded from recurrence")
            continue
        debits.append(row)
    if not debits:
        return {"as_of": anchor.isoformat() if anchor else None,
                "current_month": _month(anchor) if anchor else None,
                "total_committed_monthly": 0.0, "subscriptions": [],
                "flagged": {"new": [], "price_creep": [], "dormant": []}, "gaps": gaps}

    as_of = anchor or max(_d(t["date"]) for t in debits)
    current_month = as_of.isoformat()[:7]

    groups = {}
    for t in debits:
        tok = categorize.normalize_token(t.get("description", ""))
        category, bucket, _ = categorize.categorize_one(t["description"], {})
        if bucket in ("Excluded", "Income", "Investments") or category == "ATM/Cash":
            continue
        groups.setdefault((tok, t.get("account", "")), []).append(t)

    subs = []
    for (token, account), rows in groups.items():
        rows = sorted(rows, key=lambda r: _d(r["date"]))
        dates = [_d(r["date"]) for r in rows]
        amounts = [abs(float(r.get("amount", 0) or 0)) for r in rows]
        months = sorted({_month(r["date"]) for r in rows})
        n = len(rows)
        desc = rows[-1].get("description", "")
        cat, _bucket, _src = categorize.categorize_one(desc, {})

        cadence, months_per_charge, cadence_days, confidence = None, None, None, None
        if n >= 2:
            intervals = [(dates[i] - dates[i - 1]).days for i in range(1, n)]
            cadence_days = statistics.median(intervals)
            cadence, months_per_charge = _months_between(cadence_days)
            spread = (max(amounts) - min(amounts)) / statistics.median(amounts) \
                if statistics.median(amounts) else 0
            regular = cadence and all(_months_between(gap)[0] == cadence for gap in intervals)
            if regular and spread <= AMOUNT_SPREAD_TOL + CREEP_THRESHOLD:
                confidence = "high" if n >= 3 else "medium"
        if confidence is None:
            # A familiar merchant is only a candidate, never proof of cadence.
            up = desc.upper()
            if n == 1 and (token in SUBSCRIPTION_HINTS
                           or any(categorize.matches_token(up, h) for h in SUBSCRIPTION_HINTS)):
                cadence, months_per_charge, confidence = None, None, "low"
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
            "account": account,
            "description": desc,
            "category": cat,
            "cadence": cadence,
            "amount": round(latest_amount, 2),
            "monthly_equivalent": (round(_monthly_equiv(latest_amount, months_per_charge), 2)
                                   if months_per_charge is not None else None),
            "occurrences": n,
            "months_observed": months,
            "last_seen": dates[-1].isoformat(),
            "confidence": confidence,
            "prior_amount": round(statistics.median(amounts[:-1]), 2) if n >= 2 else None,
            "flags": flags,
        })

    subs.sort(key=lambda s: s["monthly_equivalent"] or 0, reverse=True)
    committed = sum(s["monthly_equivalent"] for s in subs
                    if "dormant" not in s["flags"] and s["monthly_equivalent"] is not None)
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
        "gaps": gaps,
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
    payload = json.dumps(result, indent=2, allow_nan=False)
    if args.out:
        if os.path.realpath(args.out) == os.path.realpath(args.txns):
            raise ValueError("output cannot overwrite transactions")
        categorize.write_json(result, args.out)
        print(json.dumps({"out": args.out, "count": len(result["subscriptions"]),
                          "committed_monthly": result["total_committed_monthly"]}))
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(_main())
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "gaps": [str(exc)]}), file=sys.stderr)
        sys.exit(1)
