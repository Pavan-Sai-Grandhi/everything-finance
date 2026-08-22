#!/usr/bin/env python3
"""The integrity-gate checks that are arithmetic, not judgement.

`management-analysis` grades seven integrity sub-checks. Two of them are a division
over figures the annual report publishes, and a gate that returns PASS on a check
nobody performed is worse than no gate — so they are computed here, deterministically
and unit-tested, rather than eyeballed.

  - **Managerial remuneration vs profit.** Companies Act s.197 caps total managerial
    remuneration at 11% of net profits computed under s.198 (5% for a single MD/WTD,
    10% for more than one). Well below the cap, the working norm is ~5% of net profit;
    above it, the promoter is paying themselves ahead of the shareholder.
  - **Auditor fee trend.** The fee itself means little; the fee accelerating away from
    the business — and especially rising into a profit collapse — is the signal.

Both return a PASS / FLAG / FAIL verdict with the number that decided it, and both
return `NOT-CHECKED` when an input is missing rather than assuming the benign reading.

CLI:
  PYTHONPATH=<plugin> python3 -m finance.compute.governance --selftest
"""
from __future__ import annotations

import argparse
import json
import sys

from finance import spine

# Companies Act s.197 ceilings, as a percentage of net profit computed under s.198.
CAP_TOTAL_PCT = 11.0
CAP_SINGLE_MD_PCT = 5.0
CAP_MULTIPLE_MD_PCT = 10.0

# Below this share of net profit, pay is not competing with the shareholder.
NORM_PCT = 5.0

# An audit fee outrunning revenue by this much is worth naming.
FEE_EXCESS_PP = 15.0


def remuneration_check(total_remuneration, net_profit, managing_directors=None):
    """Total KMP/managerial remuneration against net profit and the s.197 ceiling.

    `total_remuneration` and `net_profit` are the same currency unit (both ₹ Cr, or
    both ₹ Lakh). `managing_directors` — the count of MD/WTDs — selects the tighter
    single/multiple ceiling; omit it and only the 11% total cap is applied.
    """
    if total_remuneration is None or net_profit is None:
        return {"verdict": "NOT-CHECKED", "ratio_pct": None, "cap_pct": None,
                "reason": "remuneration or net profit not disclosed at the granularity needed"}
    if net_profit <= 0:
        return {"verdict": "FLAG", "ratio_pct": None, "cap_pct": CAP_TOTAL_PCT,
                "reason": f"pay of {total_remuneration:,.2f} drawn against a non-positive "
                          f"net profit ({net_profit:,.2f}) — s.197 requires central-government "
                          f"approval or Schedule V compliance in a loss year"}

    ratio = spine.pct(total_remuneration, net_profit)
    cap = CAP_TOTAL_PCT
    if managing_directors == 1:
        cap = CAP_SINGLE_MD_PCT
    elif managing_directors and managing_directors > 1:
        cap = CAP_MULTIPLE_MD_PCT

    if ratio > cap:
        verdict, reason = "FAIL", (f"{ratio:.2f}% of net profit exceeds the s.197 ceiling "
                                   f"of {cap:.0f}%")
    elif ratio > NORM_PCT:
        verdict, reason = "FLAG", (f"{ratio:.2f}% of net profit is inside the s.197 ceiling "
                                   f"of {cap:.0f}% but above the ~{NORM_PCT:.0f}% norm")
    else:
        verdict, reason = "PASS", (f"{ratio:.2f}% of net profit, against a ~{NORM_PCT:.0f}% "
                                   f"norm and a {cap:.0f}% ceiling")
    return {"verdict": verdict, "ratio_pct": ratio, "cap_pct": cap, "reason": reason}


def auditor_fee_check(fees, revenues=None, profits=None):
    """Audit-fee trend against the business it audits.

    `fees` is oldest-first, at least two years, same unit throughout. `revenues` and
    `profits` are the matching series where available — the fee is read against
    revenue growth, and a fee rising into a profit collapse is called out separately.
    """
    fees = [f for f in (fees or []) if f is not None]
    if len(fees) < 2:
        return {"verdict": "NOT-CHECKED", "fee_yoy_pct": None,
                "reason": "fewer than two years of audit fee disclosed"}
    if fees[-2] <= 0:
        return {"verdict": "NOT-CHECKED", "fee_yoy_pct": None,
                "reason": "prior-year audit fee is zero or negative — no trend to read"}

    fee_yoy = spine.pct(fees[-1] - fees[-2], fees[-2])
    rev_yoy = None
    if revenues and len(revenues) >= 2 and revenues[-2]:
        rev_yoy = spine.pct(revenues[-1] - revenues[-2], revenues[-2])
    profit_yoy = None
    if profits and len(profits) >= 2 and profits[-2]:
        profit_yoy = spine.pct(profits[-1] - profits[-2], profits[-2])

    notes = []
    verdict = "PASS"
    if rev_yoy is not None and fee_yoy - rev_yoy > FEE_EXCESS_PP:
        verdict = "FLAG"
        notes.append(f"audit fee +{fee_yoy:.1f}% vs revenue {rev_yoy:+.1f}% — "
                     f"outrunning the business by {fee_yoy - rev_yoy:.1f}pp")
    if profit_yoy is not None and profit_yoy < 0 and fee_yoy > 0:
        verdict = "FLAG"
        notes.append(f"audit fee rose {fee_yoy:+.1f}% in a year profit fell "
                     f"{profit_yoy:.1f}%")
    if not notes:
        notes.append(f"audit fee {fee_yoy:+.1f}% YoY" +
                     (f" against revenue {rev_yoy:+.1f}%" if rev_yoy is not None else ""))
    return {"verdict": verdict, "fee_yoy_pct": fee_yoy, "revenue_yoy_pct": rev_yoy,
            "profit_yoy_pct": profit_yoy, "reason": "; ".join(notes)}


def _selftest():
    ok = remuneration_check(30.0, 1000.0)["verdict"] == "PASS"
    ok &= remuneration_check(80.0, 1000.0)["verdict"] == "FLAG"
    ok &= remuneration_check(130.0, 1000.0)["verdict"] == "FAIL"
    ok &= remuneration_check(60.0, 1000.0, managing_directors=1)["verdict"] == "FAIL"
    ok &= remuneration_check(None, 1000.0)["verdict"] == "NOT-CHECKED"
    ok &= auditor_fee_check([2.0, 2.1], revenues=[100.0, 108.0])["verdict"] == "PASS"
    ok &= auditor_fee_check([2.0, 2.6], revenues=[100.0, 102.0])["verdict"] == "FLAG"
    ok &= auditor_fee_check([2.0], revenues=[100.0])["verdict"] == "NOT-CHECKED"
    print("selftest", "ok" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="Integrity-gate arithmetic.")
    ap.add_argument("--remuneration", type=float, help="total managerial remuneration")
    ap.add_argument("--net-profit", type=float, help="net profit, same unit")
    ap.add_argument("--managing-directors", type=int)
    ap.add_argument("--fees", help="comma-separated audit fees, oldest first")
    ap.add_argument("--revenues", help="comma-separated revenues, oldest first")
    ap.add_argument("--profits", help="comma-separated profits, oldest first")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    nums = lambda s: [float(x) for x in s.split(",")] if s else None
    out = {}
    if a.remuneration is not None or a.net_profit is not None:
        out["remuneration"] = remuneration_check(a.remuneration, a.net_profit,
                                                 a.managing_directors)
    if a.fees:
        out["auditor_fee"] = auditor_fee_check(nums(a.fees), nums(a.revenues),
                                               nums(a.profits))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
