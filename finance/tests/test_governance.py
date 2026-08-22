#!/usr/bin/env python3
"""Offline tests for the integrity-gate arithmetic. No network.
Run: python3 finance/tests/test_governance.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from finance.compute import governance as g  # noqa: E402
from finance.tests.harness import check, summary  # noqa: E402

# --- remuneration vs profit ---------------------------------------------------
r = g.remuneration_check(30.0, 1000.0)
check("3% of profit passes", r["verdict"] == "PASS", r)
check("the ratio is reported", r["ratio_pct"] == 3.0, r)
check("the reason carries the number", "3.00%" in r["reason"], r)

r = g.remuneration_check(80.0, 1000.0)
check("8% of profit flags — inside the cap, above the norm", r["verdict"] == "FLAG", r)
check("the flag names both thresholds",
      "11%" in r["reason"] and "5%" in r["reason"], r)

r = g.remuneration_check(130.0, 1000.0)
check("13% of profit fails the s.197 ceiling", r["verdict"] == "FAIL", r)
check("the fail names the ceiling", "ceiling of 11%" in r["reason"], r)

check("exactly at the 5% norm still passes",
      g.remuneration_check(50.0, 1000.0)["verdict"] == "PASS")
check("exactly at the 11% ceiling is a flag, not a fail",
      g.remuneration_check(110.0, 1000.0)["verdict"] == "FLAG")

# the tighter per-MD ceilings
r = g.remuneration_check(60.0, 1000.0, managing_directors=1)
check("6% with one MD breaches the 5% single-MD ceiling", r["verdict"] == "FAIL", r)
check("the single-MD cap is reported", r["cap_pct"] == 5.0, r)
r = g.remuneration_check(60.0, 1000.0, managing_directors=2)
check("6% with two MDs is inside the 10% ceiling", r["verdict"] == "FLAG", r)
check("the multiple-MD cap is reported", r["cap_pct"] == 10.0, r)
check("no MD count falls back to the 11% total cap",
      g.remuneration_check(60.0, 1000.0)["cap_pct"] == 11.0)

# a loss year is not a pass
r = g.remuneration_check(30.0, -50.0)
check("pay against a loss is a flag, not a division", r["verdict"] == "FLAG", r)
check("the loss-year reason names Schedule V", "Schedule V" in r["reason"], r)
check("zero profit is handled the same way",
      g.remuneration_check(30.0, 0.0)["verdict"] == "FLAG")

# a missing input never becomes a benign reading
for args in ((None, 1000.0), (30.0, None), (None, None)):
    r = g.remuneration_check(*args)
    check(f"missing input {args} → NOT-CHECKED", r["verdict"] == "NOT-CHECKED", r)
check("NOT-CHECKED is distinct from PASS",
      g.remuneration_check(None, None)["verdict"] != "PASS")

# --- auditor fee trend --------------------------------------------------------
r = g.auditor_fee_check([2.0, 2.1], revenues=[100.0, 108.0])
check("a fee growing slower than revenue passes", r["verdict"] == "PASS", r)
check("the YoY is reported", r["fee_yoy_pct"] == 5.0, r)

r = g.auditor_fee_check([2.0, 2.6], revenues=[100.0, 102.0])
check("a fee outrunning revenue by >15pp flags", r["verdict"] == "FLAG", r)
check("the flag quantifies the excess", "pp" in r["reason"], r)

r = g.auditor_fee_check([2.0, 2.54], revenues=[100.0, 105.0], profits=[100.0, 11.0])
check("a fee rising into a profit collapse flags", r["verdict"] == "FLAG", r)
check("the profit-collapse note is separate",
      "profit fell" in r["reason"], r)
check("the profit YoY is reported", r["profit_yoy_pct"] == -89.0, r)

r = g.auditor_fee_check([2.0, 2.1], revenues=[100.0, 108.0], profits=[100.0, 120.0])
check("a rising fee in a rising-profit year is not flagged", r["verdict"] == "PASS", r)

check("one year of fee is NOT-CHECKED",
      g.auditor_fee_check([2.0])["verdict"] == "NOT-CHECKED")
check("no fees at all is NOT-CHECKED",
      g.auditor_fee_check(None)["verdict"] == "NOT-CHECKED")
check("a zero prior-year fee is NOT-CHECKED, not a division by zero",
      g.auditor_fee_check([0.0, 2.0])["verdict"] == "NOT-CHECKED")

r = g.auditor_fee_check([2.0, 2.6])
check("no revenue series still reads the raw trend", r["verdict"] == "PASS", r)
check("the reason states the YoY when there is nothing to compare against",
      "+30.0%" in r["reason"], r)

# --- shape --------------------------------------------------------------------
for r in (g.remuneration_check(30.0, 1000.0), g.remuneration_check(None, None)):
    check("every remuneration result carries verdict + reason",
          {"verdict", "reason", "ratio_pct", "cap_pct"} == set(r), sorted(r))
for r in (g.auditor_fee_check([2.0, 2.1]), g.auditor_fee_check([2.0])):
    check("every fee result carries verdict + reason",
          {"verdict", "reason"} <= set(r), sorted(r))
check("verdicts come from the fixed vocabulary",
      all(x["verdict"] in ("PASS", "FLAG", "FAIL", "NOT-CHECKED")
          for x in (g.remuneration_check(130.0, 1000.0), g.auditor_fee_check([2.0]))))

check("selftest passes", g._selftest() == 0)

# --- the gate vocabulary is one word across the four files that speak it -------------
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _read(rel):
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as fh:
        return fh.read()

_ref = _read("skills/management-analysis/references/reference.md")
check("the gate aggregation names an outcome for a FLAGged sub-check",
      "else **`FLAG`** if any check flagged" in _ref,
      "a flagged check with no aggregate outcome forces the leg to improvise one")
check("the aggregation still puts FAIL first", _ref.index("**`FAIL`** if any check failed")
      < _ref.index("else **`FLAG`**"), "FAIL must outrank FLAG")

_pm = _read("agents/portfolio-manager.md")
check("verdict-block can express a FLAGged gate", "integrity_gate: PASS | FLAG | FAIL" in _pm, _pm[:0])
check("the k-of-7 count is its own field, not smuggled into the verdict",
      "integrity_partial:" in _pm and "PASS (partial" not in _pm,
      "a partial count inside integrity_gate reads as PASS to every consumer")
check("the PM is told to carry the gate through, not re-grade it",
      "never `PASS` on a leg that reported `FLAG`" in _pm, "")
check("the PM must verify a metric before calling it corroborated",
      "Confluence means the same quantity, sourced independently" in _pm, "")

_con = _read("finance/contracts.md")
check("contracts forbids FLAG or partial reaching the verdict as PASS",
      "neither may reach `verdict-block` as `PASS`" in _con, "")

summary()
