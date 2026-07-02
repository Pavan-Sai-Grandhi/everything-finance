#!/usr/bin/env python3
"""Offline tests for the wealth-manager engine. No network, no MCP.
Run: python3 skills/wealth-manager/scripts/test_wealth.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wealth  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


# --- captured sample payloads (shapes the SKILL hands off via a temp file) --- #

SNAPSHOT = {"total_net_worth": 12000000, "as_of": "2026-06-28"}

BREAKDOWN = {"allocation": [
    {"asset_class": "Indian Stocks", "value": 3600000},
    {"asset_class": "Mutual Funds", "value": 2400000},
    {"asset_class": "US Stocks", "value": 600000},
    {"asset_class": "Real Estate", "value": 3000000},
    {"asset_class": "EPF", "value": 900000},
    {"asset_class": "Fixed Deposit", "value": 600000},
    {"asset_class": "Gold", "value": 300000},
    {"asset_class": "Cash", "value": 600000},
]}

POSITIONS = {"ok": True, "source": "indmoney", "fetched_at": "2026-06-28",
             "data": {"positions": [
                 {"ticker": "RELIANCE", "qty": 50, "avg": 2400, "ltp": 2950, "pnl": 27500,
                  "invested": 120000, "xirr": 18.4, "asset_class": "indian stocks"},
                 {"ticker": "TCS", "qty": 20, "avg": 3200, "ltp": 3000, "pnl": -4000,
                  "invested": 64000, "xirr": -3.1, "asset_class": "indian stocks"},
             ]}, "gaps": []}

INVEST_LEG = {
    "book_xirr": 14.2,
    "allocation": {"asset_class": {"equity": 60, "debt": 30, "cash": 10}},
    "concentration_flags": [{"dimension": "sector", "category": "IT", "pct": 38, "severity": "high"}],
    "top_exits": [{"ticker": "XYZ", "verdict": "EXIT", "reason": "ROCE collapse"}],
    "laggard_funds": [], "value": 6600000, "coverage": {"sector": 90}, "gaps": [], "as_of": "2026-06-28",
}
PROT_LEG = {
    "term": {"have": 5000000, "need": 15000000, "gap": 10000000, "adequacy": "short"},
    "health": {"have": 1000000, "need": 1000000, "gap": 0, "adequacy": "adequate"},
    "vehicle": {"status": "ok"}, "red_flags": [{"policy": "ULIP-X", "flag": "high cost, low cover"}],
    "dependents": 2, "gaps": [], "as_of": "2026-06-28",
}
CASH_LEG = {
    "savings_rate": 28, "buckets": {}, "biggest_leak": "Dine & Entertainment ₹18,000",
    "recurring_monthly": 45000, "monthly_outflow": 90000, "target_source": "workbook",
    "gaps": [], "month": "2026-05",
}

FULL = {"snapshot": SNAPSHOT, "breakdown": BREAKDOWN, "positions": POSITIONS,
        "legs": {"investments": INVEST_LEG, "protection": PROT_LEG, "cashflow": CASH_LEG},
        "profile": {"age": 35, "dependents": 2}}


# --------------------------------------------------------------------------- #
# spine
# --------------------------------------------------------------------------- #
def test_spine_allocation():
    s = wealth.build_spine(SNAPSHOT, BREAKDOWN, POSITIONS)
    check("spine: total net worth from snapshot", s["total_networth"] == 12000000, s["total_networth"])
    check("spine: coverage complete", s["coverage"] == "complete", s["coverage"])
    check("spine: equity pct = 3.6M/12M = 30%", s["allocation"]["equity"]["pct"] == 30.0,
          s["allocation"]["equity"])
    check("spine: real estate bucketed", "real_estate" in s["allocation"])
    check("spine: gold bucketed", s["allocation"]["gold"]["value"] == 300000)
    # liquid = cash 600k + FD 600k
    check("spine: liquid = cash + FD", s["liquid"] == 1200000, s["liquid"])
    # equity share = (3.6 + 2.4 + 0.6)M / 12M = 55%
    check("spine: equity share = equity+MF+US", s["equity_share_pct"] == 55.0, s["equity_share_pct"])


def test_spine_xirr_summary():
    s = wealth.build_spine(SNAPSHOT, BREAKDOWN, POSITIONS)
    x = s["holdings_xirr"]
    check("spine: xirr count", x["count"] == 2, x)
    check("spine: xirr best is RELIANCE", x["best"]["ticker"] == "RELIANCE", x["best"])
    check("spine: xirr worst is TCS", x["worst"]["ticker"] == "TCS", x["worst"])


def test_spine_flat_breakdown_dict():
    s = wealth.build_spine(SNAPSHOT, {"Cash": 600000, "Gold": 300000}, None)
    check("spine: flat {class:value} breakdown parsed", s["allocation"]["cash"]["value"] == 600000, s["allocation"])


def test_spine_partial_tradeable_only():
    # no IndMoney breakdown/snapshot → tradeable-only spine from broker positions
    broker = {"ok": True, "source": "kite", "fetched_at": "2026-06-28",
              "data": {"positions": [
                  {"ticker": "INFY", "qty": 10, "avg": 1500, "ltp": 1600, "pnl": 1000,
                   "invested": 15000, "xirr": None, "asset_class": None}]}, "gaps": []}
    s = wealth.build_spine(None, None, broker)
    check("spine: tradeable-only coverage", s["coverage"] == "tradeable-only", s["coverage"])
    check("spine: total from positions when no snapshot", s["total_networth"] == 16000, s["total_networth"])
    check("spine: tradeable-only labelled a gap",
          any("tradeable holdings only" in g for g in s["gaps"]), s["gaps"])
    check("spine: no-xirr gap noted", any("XIRR" in g for g in s["gaps"]), s["gaps"])


def test_canonical_class():
    check("class: Indian Stocks → equity", wealth.canonical_class("Indian Stocks") == "equity")
    check("class: Mutual Funds → mutual_funds", wealth.canonical_class("Mutual Funds") == "mutual_funds")
    check("class: EPF → epf", wealth.canonical_class("EPF") == "epf")
    check("class: unknown → other", wealth.canonical_class("Angel Investments") == "other")


# --------------------------------------------------------------------------- #
# cross-domain
# --------------------------------------------------------------------------- #
def test_emergency_fund():
    # liquid 1.2M / 90k monthly = 13.3 months → strong
    ef = wealth.emergency_fund(1200000, 90000)
    check("ef: months", ef["months"] == 13.3, ef["months"])
    check("ef: strong ≥6 months", ef["status"] == "strong", ef["status"])
    # thin band
    check("ef: thin 1-3 months", wealth.emergency_fund(150000, 90000)["status"] == "thin")
    # critical <1 month
    check("ef: critical <1 month", wealth.emergency_fund(50000, 90000)["status"] == "critical")
    # no expenses → not assessed
    check("ef: not assessed without expenses", wealth.emergency_fund(1200000, None)["status"] == "not_assessed")


def test_monthly_expenses_precedence():
    check("exp: stated wins", wealth._monthly_expenses(CASH_LEG, {"monthly_expenses": 100000})[0] == 100000)
    check("exp: cashflow outflow next", wealth._monthly_expenses(CASH_LEG, {})[0] == 90000)
    rec_only = {"recurring_monthly": 45000}
    exp, basis = wealth._monthly_expenses(rec_only, {})
    check("exp: recurring floor fallback", exp == 45000 and "floor" in basis, (exp, basis))
    check("exp: none when nothing", wealth._monthly_expenses(None, {})[0] is None)


def test_protection_read():
    r = wealth.protection_read(PROT_LEG)
    check("protection: short term → weak", r["status"] == "weak", r["status"])
    check("protection: red flag counted", "red flag" in r["line"], r["line"])
    absent = wealth.protection_read({"term": {"adequacy": "absent"}, "health": {"adequacy": "adequate"}})
    check("protection: absent term → critical", absent["status"] == "critical", absent["status"])
    check("protection: not assessed when absent leg", wealth.protection_read(None)["status"] == "not_assessed")


def test_risk_posture():
    # equity share 55%, ceiling 100-35=65, foundation sound (strong ef, but weak protection)
    r = wealth.risk_posture(55, "strong", "weak", age=35)
    check("risk: weak protection → fix foundation first", r["stance"] == "fix-foundation-first", r["stance"])
    r2 = wealth.risk_posture(55, "strong", "strong", age=35)
    check("risk: 55% vs 65% ceiling, sound → balanced", r2["stance"] == "balanced", r2["stance"])
    r3 = wealth.risk_posture(90, "strong", "strong", age=35)
    check("risk: 90% over ceiling → reduce", r3["stance"] == "reduce-risk", r3["stance"])
    r4 = wealth.risk_posture(30, "strong", "strong", age=35)
    check("risk: 30% well below → can add", r4["stance"] == "can-add-risk", r4["stance"])
    check("risk: unknown share", wealth.risk_posture(None, "strong", "strong")["stance"] == "unknown")


# --------------------------------------------------------------------------- #
# scorecard + full run
# --------------------------------------------------------------------------- #
def test_full_run_scorecard():
    out = wealth.run(FULL)
    sc = out["scorecard"]
    d = sc["domains"]
    check("scorecard: 5 domains", len(d) == 5, list(d))
    check("scorecard: investments weak (EXIT + severe)", d["investments"]["status"] == "weak", d["investments"])
    check("scorecard: cashflow strong (28%)", d["cashflow"]["status"] == "strong", d["cashflow"])
    check("scorecard: protection weak (term short)", d["protection"]["status"] == "weak", d["protection"])
    check("scorecard: emergency fund strong", d["emergency_fund"]["status"] == "strong", d["emergency_fund"])
    check("scorecard: overall = worst assessed (weak)", sc["overall"] == "weak", sc["overall"])


def test_action_priority_protection_before_investments():
    out = wealth.run(FULL)
    actions = out["scorecard"]["actions"]
    domains_in_order = [a["domain"] for a in actions]
    check("actions: protection ranks before investments",
          domains_in_order.index("protection") < domains_in_order.index("investments"),
          domains_in_order)
    check("actions: capped at 5", len(actions) <= 5, len(actions))
    check("actions: each names a spoke to run", all(a["run"].startswith("/") for a in actions))


def test_full_run_missing_legs():
    # cashflow + protection legs absent → degrade to not_assessed, still verdict on the rest
    partial = {"snapshot": SNAPSHOT, "breakdown": BREAKDOWN, "positions": POSITIONS,
               "legs": {"investments": INVEST_LEG}, "profile": {"age": 35}}
    out = wealth.run(partial)
    d = out["scorecard"]["domains"]
    check("missing: cashflow not assessed", d["cashflow"]["status"] == "not_assessed", d["cashflow"])
    check("missing: protection not assessed", d["protection"]["status"] == "not_assessed", d["protection"])
    check("missing: emergency fund not assessed (no expenses)",
          d["emergency_fund"]["status"] == "not_assessed", d["emergency_fund"])
    check("missing: investments still scored", d["investments"]["status"] == "weak", d["investments"])
    check("missing: run does not crash and returns overall", "overall" in out["scorecard"])


def test_snapshot_mode():
    out = wealth.run(FULL, snapshot_mode=True)
    check("snapshot: no scorecard", "scorecard" not in out, list(out))
    check("snapshot: spine present", out["spine"]["total_networth"] == 12000000)
    check("snapshot: cross-domain flags present", "emergency_fund" in out["cross_domain"])
    check("snapshot: mode labelled", out["mode"] == "snapshot")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
