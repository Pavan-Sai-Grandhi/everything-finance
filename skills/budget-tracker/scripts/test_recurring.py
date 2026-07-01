#!/usr/bin/env python3
"""Offline tests for recurring.py — cadence detection, new/creep/dormant flags,
single-period low-confidence path. No network.
Run: python3 skills/budget-tracker/scripts/test_recurring.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import recurring as R  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


def txn(date, desc, amount):
    return {"date": date, "description": desc, "amount": amount,
            "direction": "debit", "account": "HDFC"}


def sub(res, merchant):
    for s in res["subscriptions"]:
        if s["merchant"] == merchant:
            return s
    return None


# --- monthly cadence, stable amount: high-confidence recurring ---------------
netflix = [txn(f"2026-{m:02d}-05", "UPI/NETFLIX/ybl", 649) for m in (2, 3, 4, 5, 6)]
res = R.detect(netflix, as_of="2026-06-30")
s = sub(res, "NETFLIX")
check("monthly cadence detected", s and s["cadence"] == "monthly", s)
check("high confidence at 5 occurrences", s and s["confidence"] == "high", s)
check("monthly_equivalent == amount for monthly", s and s["monthly_equivalent"] == 649, s)
check("stable monthly sub has no creep flag", s and "price_creep" not in s["flags"], s)

# --- quarterly and annual cadence -> monthly_equivalent divides --------------
quarterly = [txn(d, "UPI/SOMECLUB MEMBERSHIP/ybl", 3000)
             for d in ("2026-01-10", "2026-04-10", "2026-07-10")]
res = R.detect(quarterly, as_of="2026-07-31")
s = sub(res, "SOMECLUB")
check("quarterly cadence detected", s and s["cadence"] == "quarterly", s)
check("quarterly monthly_equivalent = amount/3", s and s["monthly_equivalent"] == 1000, s)

annual = [txn("2025-08-01", "UPI/AMAZONPRIME MEMBERSHIP/ybl", 1499),
          txn("2026-08-01", "UPI/AMAZONPRIME MEMBERSHIP/ybl", 1499)]
res = R.detect(annual, as_of="2026-08-15")
s = sub(res, "AMAZONPRIME")
check("annual cadence detected", s and s["cadence"] == "annual", s)
check("annual monthly_equivalent ~ amount/12",
      s and abs(s["monthly_equivalent"] - 1499 / 12) < 0.01, s)

# --- new flag: first appearance is the current month -------------------------
newsub = [txn("2026-06-03", "UPI/HOTSTAR/ybl", 299),
          txn("2026-07-03", "UPI/HOTSTAR/ybl", 299)]
res = R.detect(newsub, as_of="2026-06-30")  # anchored at the first month
s = sub(res, "HOTSTAR")
check("new flag when first month == current month", s and "new" in s["flags"], s)

# --- price creep: amount rose vs the prior cadence ---------------------------
creep = [txn("2026-03-01", "UPI/SPOTIFY/ybl", 119),
         txn("2026-04-01", "UPI/SPOTIFY/ybl", 119),
         txn("2026-05-01", "UPI/SPOTIFY/ybl", 149)]
res = R.detect(creep, as_of="2026-05-31")
s = sub(res, "SPOTIFY")
check("price_creep flagged when latest > prior", s and "price_creep" in s["flags"], s)
check("prior_amount reported for creep", s and s["prior_amount"] == 119, s)

# --- dormant: established cadence that lapsed (charge overdue) ----------------
dormant = [txn("2026-01-08", "UPI/GYMPASS/ybl", 1500),
           txn("2026-02-08", "UPI/GYMPASS/ybl", 1500),
           txn("2026-03-08", "UPI/GYMPASS/ybl", 1500)]
res = R.detect(dormant, as_of="2026-06-30")  # ~114 days after last charge, monthly cadence
s = sub(res, "GYMPASS")
check("dormant flagged when charge overdue", s and "dormant" in s["flags"], s)
check("dormant excluded from committed monthly total",
      res["total_committed_monthly"] == 0.0, res["total_committed_monthly"])

# --- single-period low-confidence: one sighting of a known subscription ------
single = [txn("2026-06-15", "UPI/NETFLIX/ybl", 649)]
res = R.detect(single, as_of="2026-06-30")
s = sub(res, "NETFLIX")
check("single sighting of known sub surfaced", s is not None, res["subscriptions"])
check("single sighting is low confidence", s and s["confidence"] == "low", s)
check("single sighting cadence inferred monthly", s and s["cadence"] == "monthly", s)

# --- non-recurring variable spend is NOT surfaced ----------------------------
groceries = [txn("2026-05-02", "UPI/BIGBASKET/ybl", 2100),
             txn("2026-05-11", "UPI/BIGBASKET/ybl", 640),
             txn("2026-05-23", "UPI/BIGBASKET/ybl", 3300)]
res = R.detect(groceries, as_of="2026-05-31")
check("irregular variable spend not called recurring", sub(res, "BIGBASKET") is None,
      res["subscriptions"])

# --- committed total sums monthly-equivalents of active subs -----------------
# anchor within a monthly cadence of Netflix's last charge so neither goes dormant
mix = netflix + quarterly
res = R.detect(mix, as_of="2026-07-15")
check("committed monthly total = 649 + 1000",
      res["total_committed_monthly"] == 1649, res["total_committed_monthly"])

# --- no debits -> empty, no crash --------------------------------------------
credits = [{"date": "2026-05-01", "description": "SALARY", "amount": 100000,
            "direction": "credit", "account": "HDFC"}]
res = R.detect(credits, as_of="2026-05-31")
check("all-credit input yields no subscriptions", res["subscriptions"] == [], res)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
