#!/usr/bin/env python3
"""Offline tests for the wealth-manager engine. No network, no MCP."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import wealth
from finance.tests.harness import check, run


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
        "profile": {"age": 35, "dependents": 2, "emergency_reserve": {"available_value": 1200000, "as_of": "2026-06-28", "source": "synthetic fixture: confirmed unencumbered balance"}}}


def test_spine_allocation():
    s = wealth.build_spine(SNAPSHOT, BREAKDOWN, POSITIONS)
    check("spine: total net worth from snapshot", s["total_networth"] == 12000000, s["total_networth"])
    check("spine: coverage complete", s["coverage"] == "complete", s["coverage"])
    check("spine: equity pct = 3.6M/12M = 30%", s["allocation"]["equity"]["pct"] == 30.0,
          s["allocation"]["equity"])
    check("spine: real estate bucketed", "real_estate" in s["allocation"])
    check("spine: gold bucketed", s["allocation"]["gold"]["value"] == 300000)
    check("spine: observed cash + FD is not certified liquidity", s["observed_liquid"] == 1200000 and s["liquid"] is None)
    check("spine: fund mix does not establish total equity share", s["equity_share_pct"] is None)
    check("spine: direct equity remains visible", s["known_equity_share_pct"] == 35.0)


def test_spine_xirr_summary():
    s = wealth.build_spine(SNAPSHOT, BREAKDOWN, POSITIONS)
    x = s["holdings_xirr"]
    check("spine: xirr count", x["count"] == 2, x)
    check("spine: xirr best is RELIANCE", x["best"]["ticker"] == "RELIANCE", x["best"])
    check("spine: xirr worst is TCS", x["worst"]["ticker"] == "TCS", x["worst"])
    check("spine: xirr avg is value-weighted", x["avg"] == 12.2, x["avg"])


def test_spine_flat_breakdown_dict():
    s = wealth.build_spine(SNAPSHOT, {"Cash": 600000, "Gold": 300000}, None)
    check("spine: flat {class:value} breakdown parsed", s["allocation"]["cash"]["value"] == 600000, s["allocation"])


def test_spine_partial_tradeable_only():
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


def test_emergency_fund():
    ef = wealth.emergency_fund(1200000, 90000)
    check("ef: months", ef["months"] == 13.3, ef["months"])
    check("ef: strong ≥6 months", ef["status"] == "strong", ef["status"])
    check("ef: thin 1-3 months", wealth.emergency_fund(150000, 90000)["status"] == "thin")
    check("ef: critical <1 month", wealth.emergency_fund(50000, 90000)["status"] == "critical")
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
    for partial in ({"gaps": ["no cover details"]}, {"health": {"adequacy": "adequate"}}):
        check("missing core cover cannot certify sound protection",
              wealth.protection_read(partial)["status"] == "not_assessed")


def test_risk_posture():
    r = wealth.risk_posture(55, "strong", "weak", age=35, equity_band={"min_pct": 45, "max_pct": 65})
    check("risk: weak protection → fix foundation first", r["stance"] == "fix-foundation-first", r["stance"])
    r2 = wealth.risk_posture(55, "strong", "strong", age=35, equity_band={"min_pct": 45, "max_pct": 65})
    check("risk: 55% vs 65% ceiling, sound → balanced", r2["stance"] == "within-target", r2["stance"])
    r3 = wealth.risk_posture(90, "strong", "strong", age=35, equity_band={"min_pct": 45, "max_pct": 65})
    check("risk: 90% over ceiling → reduce", r3["stance"] == "above-target", r3["stance"])
    r4 = wealth.risk_posture(30, "strong", "strong", age=35, equity_band={"min_pct": 45, "max_pct": 65})
    check("risk: 30% well below → can add", r4["stance"] == "below-target", r4["stance"])
    check("risk: unknown share", wealth.risk_posture(None, "strong", "strong")["stance"] == "unknown")
    check("unassessed protection cannot authorize more risk",
          wealth.risk_posture(10, "strong", "not_assessed")["stance"] == "fix-foundation-first")
    check("urgent allocation severity reaches wealth scorecard",
          wealth._score_investments({"concentration_flags": [{"severity": "act"}]})["status"] == "weak")


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


def test_num_scale_suffixes():
    """A spelled-out magnitude must parse. Silently reading "5 lakh" as missing turns a
    real figure into "not assessed" in the emergency-fund and risk-posture logic."""
    for text, want in (("5L", 5e5), ("5 lakh", 5e5), ("5 Lakh", 5e5), ("5 lakhs", 5e5),
                       ("5lakh", 5e5), ("12L", 12e5),
                       ("2.5 Cr", 2.5e7), ("2.5 crore", 2.5e7), ("3 crores", 3e7),
                       ("2.5cr", 2.5e7)):
        check(f"_num({text!r}) == {want:g}", wealth._num(text) == want, wealth._num(text))
    check("_num strips ₹ and Indian grouping", wealth._num("₹1,20,000") == 120000.0)
    check("_num keeps a plain percent number", wealth._num("45%") == 45.0)
    check("_num keeps a real zero", wealth._num(0) == 0.0)
    check("_num keeps a negative", wealth._num(-3.5) == -3.5)
    for blank in (None, "", "-", "NA", "N/A", "abc", True):
        check(f"_num({blank!r}) is None", wealth._num(blank) is None, wealth._num(blank))
    for bare in ("L", "cr", "lakh"):
        check(f"a bare suffix {bare!r} is None, not a multiplier",
              wealth._num(bare) is None, wealth._num(bare))


def test_incomplete_foundation_evidence():
    for value in (None, -10, float('inf')):
        try:
            result = wealth.emergency_fund(value, 100)
            safe = result['status'] == 'not_assessed'
        except (TypeError, ValueError):
            safe = False
        check('unusable liquid value cannot become runway', safe)
    check('negative monthly expenses cannot become runway', wealth.emergency_fund(100, -10)['status'] == 'not_assessed')
    picture = dict(FULL, legs={'cashflow': {'recurring_monthly': 100}, 'protection': PROT_LEG})
    result = wealth.run(picture)
    check('expense floor cannot certify strong emergency reserve', result['cross_domain']['emergency_fund']['status'] == 'not_assessed')
    check('gap-only investments cannot certify strong book', wealth._score_investments({'gaps': ['holdings unavailable']})['status'] == 'not_assessed')
    check('empty allocation cannot certify diversification', wealth._score_networth({'total_networth': 100, 'allocation': {}, 'coverage': 'complete'})['status'] == 'not_assessed')


def test_explicit_risk_targets():
    for age in (None, 25, 75, 'unknown'):
        result = wealth.risk_posture(10, 'strong', 'strong', age=age)
        check('age alone cannot authorize added risk', result['stance'] == 'unknown')
    for band in ({'min_pct': -1, 'max_pct': 80}, {'min_pct': 90, 'max_pct': 50}, {'min_pct': True, 'max_pct': 80}):
        check('invalid target range stays unknown', wealth.risk_posture(50, 'strong', 'strong', equity_band=band)['stance'] == 'unknown')
    check('weak foundation takes precedence over above-target allocation', wealth.risk_posture(99, 'thin', 'strong', equity_band={'min_pct': 40, 'max_pct': 60})['stance'] == 'fix-foundation-first')


def test_equity_classification_coverage():
    for label in ('Mutual Funds', 'Debt Mutual Funds', 'Equity Mutual Funds', 'International Mutual Funds'):
        result = wealth.build_spine({'total': 100}, {label: 100})
        check('unlooked-through fund does not become direct equity', result['equity_share_pct'] is None, label)
    result = wealth.build_spine({'total': 100}, {'Crypto': 100})
    check('crypto is not equity exposure', result['equity_share_pct'] == 0)
    check('short aliases do not match inside unrelated words', wealth.canonical_class('award assets') == 'other')
    result = wealth.build_spine({'total': 100}, {'Indian Stocks': 30, 'Mutual Funds': 70})
    check('known equity remains visible when total exposure is unknown', result.get('known_equity_share_pct') == 30)


def test_spine_reconciliation():
    partial = wealth.build_spine({'total': 1000}, {'Cash': 100})
    check('partial breakdown is not complete', partial['coverage'] != 'complete')
    check('unreconciled allocation is not rated diversified', wealth._score_networth(partial)['status'] == 'not_assessed')
    invalid = wealth.build_spine({'total': 1000}, {'Cash': 1000, 'Gold': 'unavailable'})
    check('discarded asset value lowers coverage', invalid['coverage'] != 'complete' and bool(invalid['gaps']))
    zero = wealth.build_spine({'total': 0}, {'Cash': 100})
    check('reported zero net worth is not replaced as percentage denominator', zero['allocation']['cash']['pct'] is None)
    negative = wealth.build_spine({'total': -100}, {'Cash': 100})
    check('nonpositive net worth cannot produce negative allocation percentages', negative['allocation']['cash']['pct'] is None)
    absent = wealth.run({'snapshot': {'total': 1000}, 'profile': {'monthly_expenses': 100}})
    check('unseen liquid holdings are not known zero', absent['cross_domain']['emergency_fund']['status'] == 'not_assessed')


def test_holding_return_summary_limits():
    positions = {'data': {'positions': [
        {'ticker': 'A', 'value': 100, 'xirr': '12.5%'},
        {'ticker': 'B', 'value': 200, 'xirr': 5},
        {'ticker': 'BAD', 'value': 300, 'xirr': float('nan')},
        {'ticker': 'BOOL', 'value': 300, 'xirr': True}]}}
    result = wealth.build_spine(SNAPSHOT, BREAKDOWN, positions)
    summary = result['holdings_xirr']
    check('mixed valid return formats are normalized', summary['best'] == {'ticker': 'A', 'xirr': 12.5})
    check('invalid return values are excluded with gaps', summary['count'] == 2 and any('invalid holding XIRR' in g for g in result['gaps']))
    check('holding mean is not represented as portfolio XIRR', summary['portfolio_xirr'] is None and 'not portfolio XIRR' in summary['method'])
    check('weighted summary declares its coverage', summary['weighted_count'] == 2 and summary['avg'] == 7.5)


def test_reserve_availability_evidence():
    for reserve in (None, {'available_value': 100},
                    {'available_value': 100, 'as_of': '2999-01-01', 'source': 'fixture'},
                    {'available_value': -1, 'as_of': '2026-06-28', 'source': 'fixture'}):
        picture = dict(FULL, profile={'monthly_expenses': 100, 'emergency_reserve': reserve})
        result = wealth.run(picture)
        check('asset labels cannot replace reserve evidence', result['cross_domain']['emergency_fund']['status'] == 'not_assessed')
    picture = {'profile': {'monthly_expenses': 100, 'emergency_reserve': {
        'available_value': 0, 'as_of': '2026-06-28', 'source': 'user-confirmed fixture'}}}
    result = wealth.run(picture)
    check('explicitly confirmed zero reserve is an assessed zero', result['cross_domain']['emergency_fund']['months'] == 0)
    check('reserve provenance reaches the report input', result['cross_domain']['emergency_fund']['reserve_evidence']['source'] == 'user-confirmed fixture')


def test_scorecard_precision_and_coverage():
    for reserve, status in ((596, 'adequate'), (296, 'thin'), (96, 'critical')):
        check('rounded runway does not cross status boundary', wealth.emergency_fund(reserve, 100)['status'] == status)
    check('impossible savings rate cannot score strong', wealth._score_cashflow({'savings_rate': 101})['status'] == 'not_assessed')
    check('cashflow gaps cannot certify strong savings', wealth._score_cashflow({'savings_rate': 50, 'gaps': ['statement missing']})['status'] == 'not_assessed')
    protection = {'term': {'adequacy': 'adequate'}, 'health': {'adequacy': 'adequate'}, 'red_flags': ['unresolved exclusion']}
    check('policy red flags prevent sound-protection certification', wealth.protection_read(protection)['status'] == 'not_assessed')
    result = wealth.run({})['scorecard']
    check('scorecard exposes unassessed domain count', result['assessed_domains'] == 0 and result['total_domains'] == 5 and not result['coverage_complete'])
    import json, subprocess, tempfile
    script = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'skills', 'wealth-manager', 'scripts', 'wealth.py')
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'picture.json')
        with open(path, 'w') as stream:
            json.dump({'profile': []}, stream)
        completed = subprocess.run([sys.executable, script, '--input', path], capture_output=True, text=True)
        check('CLI invalid shape yields no partial report', completed.returncode == 1 and not completed.stdout)
        check('CLI validation error is structured', json.loads(completed.stderr)['ok'] is False)


def test_explicit_liability_reconciliation():
    debt = {'total': 50, 'as_of': '2026-06-28', 'source': 'synthetic statement'}
    result = wealth.build_spine({'total': 100}, {'Cash': 150}, liabilities=debt)
    check('debt is reconciled exactly once against reported net worth', result['total_networth'] == 100 and result['coverage'] == 'complete')
    check('leveraged allocation uses gross assets', result['allocation']['cash']['pct'] == 100 and result['allocation_basis'] == 'gross_assets')
    result = wealth.build_spine(None, {'Cash': 150}, liabilities=debt)
    check('net worth can be computed from sourced assets and liabilities', result['total_networth'] == 100)
    result = wealth.build_spine({'total': 120}, {'Cash': 150}, liabilities=debt)
    check('inconsistent net worth remains a reconciliation gap', result['coverage'] == 'incomplete')
    result = wealth.build_spine(None, {'Cash': 150})
    check('asset subtotal alone does not prove complete net worth', result['coverage'] != 'complete')
    result = wealth.build_spine({'total': 100}, {'Cash': 100}, liabilities={'total': 0})
    check('unsourced liability amount cannot certify reconciliation', result['coverage'] == 'incomplete')


def test_tradeable_only_unvalued_position_is_not_silently_dropped():
    broker = {"ok": True, "source": "kite", "fetched_at": "2026-06-28",
              "data": {"positions": [
                  {"ticker": "INFY", "qty": 10, "avg": 1500, "ltp": 1600, "asset_class": None},
                  {"ticker": "UNPRICED", "qty": 5, "asset_class": None}]}, "gaps": []}
    s = wealth.build_spine(None, None, broker)
    check("spine: an unvalued holding is named as a gap",
          any("UNPRICED" in g for g in s["gaps"]), s["gaps"])
    check("spine: an unvalued holding makes coverage incomplete",
          s["coverage"] == "incomplete", s["coverage"])


def test_live_indmoney_snapshot_envelope_builds_the_spine():
    import json as _json
    inner = {"total_invested": 900, "total_current_value": 1000, "total_networth": 700,
             "investments": [{"asset_type": t, "invested_value": v, "current_value": v}
                             for t, v in (("MF", 500), ("US_STOCK", 200), ("FD", 100), ("STOCK", 100),
                                          ("EPF", 60), ("VEHICLE", 40), ("US_STOCK_WALLET", 0), ("CRYPTO", 0))],
             "assets": [{"assetclass_l2": "Equity", "current_value": 600}],
             "liabilities": {"total": 300, "loans": [{"lender": "X", "current_balance": 300}]}}
    snap = {"result": _json.dumps(inner)}
    s = wealth.build_spine(snapshot=snap, breakdown=snap,
                           liabilities={"total": 300, "as_of": "2026-10-11", "source": "IndMoney networth_snapshot"})
    check("spine: the JSON-string `result` snapshot yields the net-worth total", s["total_networth"] == 700, s)
    check("spine: per-class rows come from `investments[asset_type, current_value]`",
          s["allocation_total"] == 1000 and s["allocation"].get("mutual_funds", {}).get("value") == 500, s["allocation"])
    check("spine: assets minus the snapshot's liabilities reconcile with its net worth",
          not any("does not reconcile" in g for g in s["gaps"]), s["gaps"])
    check("spine: a US wallet balance is cash, not US equity", wealth.canonical_class("US_STOCK_WALLET") == "cash")


def test_liabilities_without_assets_do_not_invent_negative_net_worth():
    s = wealth.build_spine(snapshot=None, breakdown=None, positions_env=None,
                           liabilities={"total": 300, "as_of": "2026-10-11", "source": "statement"})
    check("spine: no observed assets means no computed net worth, not minus the loan",
          s["total_networth"] is None, s["total_networth"])


def test_broker_instrument_classes_map_to_their_exposure():
    check("wealth: a sovereign gold bond is gold exposure, not debt",
          wealth.canonical_class("sovereign gold bond") == "gold")
    check("wealth: a government security is debt", wealth.canonical_class("government security") == "debt")


if __name__ == "__main__":
    run(globals())
