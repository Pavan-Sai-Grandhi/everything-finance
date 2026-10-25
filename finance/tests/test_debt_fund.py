#!/usr/bin/env python3
"""Offline tests for the debt-fund rate scenarios. No network."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import debt_fund as D
from finance.tests.harness import approx, check, summary


def by_shift(env):
    return {r["yield_change_pp"]: r["return_pct"] for r in env["data"]["scenarios"]}


# The worked example in methods/funds.md: YTM 8.26%, duration 4.17, before expenses.
env = D.scenarios(8.26, 4.17, 0)
rows = by_shift(env)
check("a one-point fall adds the duration", env["ok"] and approx(rows[-1.0], 12.43), rows)
check("a one-point rise takes the duration away", approx(rows[1.0], 4.09), rows)
check("no change earns the yield", approx(rows[0.0], 8.26), rows)
check("the expense ratio comes off every scenario",
      approx(by_shift(D.scenarios(8.26, 4.17, 0.5))[0.0], 7.76))

extra = by_shift(D.scenarios(7.0, 2.0, 0.3, [0.5]))
check("both directions are shown even when only one shift is asked for",
      set(extra) == {-1.0, 0.0, 0.5, 1.0}, extra)
check("a zero-duration fund is unmoved by rates",
      len(set(by_shift(D.scenarios(6.5, 0, 0.2)).values())) == 1)

for bad in ((float("nan"), 2, 0.3), (7, -1, 0.3), (7, 2, 5), (True, 2, 0.3), ("7", 2, 0.3)):
    env = D.scenarios(*bad)
    check(f"invalid input {bad!r} is a labelled ok:false", env["ok"] is False and env["gaps"], env)
check("an out-of-range shift is rejected", D.scenarios(7, 2, 0.3, [9])["ok"] is False)
check("too many shifts are rejected", D.scenarios(7, 2, 0.3, [0.1] * 9)["ok"] is False)

summary()
