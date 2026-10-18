"""The integrity-gate checks that are arithmetic, not judgement.

`management-analysis` grades seven integrity sub-checks. Two of them are a division
over figures the annual report publishes, and a gate that returns PASS on a check
nobody performed is worse than no gate — so they are computed here, deterministically
and unit-tested, rather than eyeballed.

  - **Managerial remuneration vs profit.** Companies Act s.197 caps total directors'
    remuneration at 11% of net profits computed under s.198, and MD/WTD/manager pay at
    5% for one or 10% for more than one; shareholders' general-meeting approval under
    the provisos may exceed them, and a no/inadequate-profit year falls under Schedule V.
    Well below the cap, the working norm is ~5% of net profit; above it, the promoter is
    paying themselves ahead of the shareholder.
  - **Auditor fee trend.** The fee itself means little; the fee accelerating away from
    the business — and especially rising into a profit collapse — is the signal.

Both return a PASS / FLAG / FAIL verdict with the number that decided it, and both
return `NOT-CHECKED` when an input is missing rather than assuming the benign reading.

Reached through `run_governance_checks` on `finance-company`.
"""
from __future__ import annotations

from finance import spine

# Companies Act s.197 ceilings, as a percentage of net profit computed under s.198.
# The total cap covers all directors' pay; the single/multiple caps cover MD/WTD/manager
# pay only. A shareholders' general-meeting approval under the provisos may exceed them.
CAP_TOTAL_PCT = 11.0
CAP_SINGLE_MD_PCT = 5.0
CAP_MULTIPLE_MD_PCT = 10.0

# Below this share of net profit, pay is not competing with the shareholder.
NORM_PCT = 5.0

# An audit fee outrunning revenue by this much is worth naming.
FEE_EXCESS_PP = 15.0

_EXCESS_ROUTE = ("lawful only with shareholders' general-meeting approval under the s.197(1) "
                 "provisos (and a defaulted secured lender's prior approval) — check the annual "
                 "report or AGM notice for it; reported PAT approximates s.198 net profit")


def _num(value):
    """A finite real number, else None. Strings and booleans are not figures."""
    return float(value) if spine.is_finite(value) else None


def _not_checked(reason):
    return {"verdict": "NOT-CHECKED", "ratio_pct": None, "cap_pct": None,
            "executive_ratio_pct": None, "executive_cap_pct": None, "reason": reason}


def remuneration_check(total_remuneration, net_profit, managing_directors=None,
                       executive_remuneration=None):
    """Total managerial remuneration against net profit and the s.197 ceilings.

    `total_remuneration` is all directors' pay (including MD/WTD/manager);
    `executive_remuneration` is the MD/WTD/manager part. All figures share one
    currency unit. `managing_directors` — the count of MD/WTD/managers — selects the
    5% (one) or 10% (more than one) ceiling, which applies to `executive_remuneration`
    only; without that figure the per-executive ceiling is reported as not checked.
    """
    if total_remuneration is None or net_profit is None:
        return _not_checked("remuneration or net profit not disclosed at the granularity needed")
    pay, profit = _num(total_remuneration), _num(net_profit)
    if pay is None or profit is None or pay < 0:
        return _not_checked("remuneration and net profit must be finite numbers, "
                            "remuneration non-negative")
    mds = managing_directors
    if mds is not None and (isinstance(mds, bool) or not isinstance(mds, int) or mds < 0):
        return _not_checked("managing_directors must be a non-negative whole count")
    executive = None
    if executive_remuneration is not None:
        executive = _num(executive_remuneration)
        if executive is None or executive < 0 or executive > pay:
            return _not_checked("MD/WTD remuneration must be a finite non-negative "
                                "part of total remuneration")
    if profit <= 0:
        return {"verdict": "FLAG", "ratio_pct": None, "cap_pct": CAP_TOTAL_PCT,
                "executive_ratio_pct": None, "executive_cap_pct": None,
                "reason": f"pay of {pay:,.2f} drawn against a non-positive net profit "
                          f"({profit:,.2f}) — s.197(3) permits it only within Schedule V "
                          f"(board/NRC approval, a special resolution, its caps); check the "
                          f"annual report for that compliance"}

    ratio = spine.pct(pay, profit)
    exec_cap = (CAP_SINGLE_MD_PCT if mds == 1 else
                CAP_MULTIPLE_MD_PCT if mds and mds > 1 else None)
    exec_ratio = spine.pct(executive, profit) if exec_cap is not None and executive is not None else None

    breaches = []
    if ratio > CAP_TOTAL_PCT:
        breaches.append(f"{ratio:.2f}% of net profit exceeds the s.197 ceiling of "
                        f"{CAP_TOTAL_PCT:.0f}%")
    if exec_ratio is not None and exec_ratio > exec_cap:
        breaches.append(f"MD/WTD pay at {exec_ratio:.2f}% of net profit exceeds the s.197 "
                        f"ceiling of {exec_cap:.0f}% for {mds} MD/WTD")
    if breaches:
        verdict, reason = "FAIL", "; ".join(breaches) + f" — {_EXCESS_ROUTE}"
    elif ratio > NORM_PCT:
        verdict, reason = "FLAG", (f"{ratio:.2f}% of net profit is inside the s.197 ceiling "
                                   f"of {CAP_TOTAL_PCT:.0f}% but above the ~{NORM_PCT:.0f}% norm")
    else:
        verdict, reason = "PASS", (f"{ratio:.2f}% of net profit, against a ~{NORM_PCT:.0f}% "
                                   f"norm and a {CAP_TOTAL_PCT:.0f}% ceiling")
    if exec_cap is not None and exec_ratio is None:
        reason += (f"; the {exec_cap:.0f}% MD/WTD ceiling was not checked — "
                   f"MD/WTD remuneration not supplied")
    return {"verdict": verdict, "ratio_pct": ratio, "cap_pct": CAP_TOTAL_PCT,
            "executive_ratio_pct": exec_ratio, "executive_cap_pct": exec_cap,
            "reason": reason}


def _latest_pair(series, years):
    """The final two values of a series aligned to `years` fee years, or None."""
    if not series or len(series) != years:
        return None
    a, b = _num(series[-2]), _num(series[-1])
    return (a, b) if a is not None and b is not None else None


def auditor_fee_check(fees, revenues=None, profits=None):
    """Audit-fee trend against the business it audits.

    `fees` is oldest-first, at least two years, same unit throughout. `revenues` and
    `profits` are the matching series, one value per fee year — the fee is read against
    revenue growth, and a fee rising into a profit fall is called out separately. Without
    an aligned revenue series the fee has no benchmark and cannot PASS.
    """
    fees = list(fees or [])
    base = {"fee_yoy_pct": None, "revenue_yoy_pct": None, "profit_yoy_pct": None}
    if len(fees) < 2:
        return {"verdict": "NOT-CHECKED", **base,
                "reason": "fewer than two years of audit fee disclosed"}
    prior, latest = _num(fees[-2]), _num(fees[-1])
    if prior is None or latest is None:
        return {"verdict": "NOT-CHECKED", **base,
                "reason": "latest two years of audit fee are not both finite figures"}
    if prior <= 0:
        return {"verdict": "NOT-CHECKED", **base,
                "reason": "prior-year audit fee is zero or negative — no trend to read"}

    fee_yoy = spine.pct(latest - prior, prior)
    rev = _latest_pair(revenues, len(fees))
    rev_yoy = spine.pct(rev[1] - rev[0], rev[0]) if rev and rev[0] > 0 else None
    prof = _latest_pair(profits, len(fees))
    profit_fell = bool(prof) and prof[1] < prof[0]
    profit_yoy = spine.pct(prof[1] - prof[0], prof[0]) if prof and prof[0] > 0 else None

    notes = []
    if rev_yoy is not None and fee_yoy - rev_yoy > FEE_EXCESS_PP:
        notes.append(f"audit fee +{fee_yoy:.1f}% vs revenue {rev_yoy:+.1f}% — "
                     f"outrunning the business by {fee_yoy - rev_yoy:.1f}pp")
    if profit_fell and fee_yoy > 0:
        fall = f" {profit_yoy:.1f}%" if profit_yoy is not None else \
               f" from {prof[0]:,.2f} to {prof[1]:,.2f}"
        notes.append(f"audit fee rose {fee_yoy:+.1f}% in a year profit fell{fall}")
    if notes:
        verdict = "FLAG"
    elif rev_yoy is not None:
        verdict = "PASS"
        notes.append(f"audit fee {fee_yoy:+.1f}% YoY against revenue {rev_yoy:+.1f}%")
    else:
        verdict = "NOT-CHECKED"
        notes.append(f"audit fee {fee_yoy:+.1f}% YoY, but no aligned positive-base "
                     f"revenue series to read it against")
    return {"verdict": verdict, "fee_yoy_pct": fee_yoy, "revenue_yoy_pct": rev_yoy,
            "profit_yoy_pct": profit_yoy, "reason": "; ".join(notes)}


def checks(total_remuneration=None, net_profit=None, managing_directors=None,
           fees=None, revenues=None, profits=None, executive_remuneration=None):
    """Both arithmetic checks in one envelope, for the `run_governance_checks` tool.

    A check whose figures were not supplied is absent from `data` and named in `gaps`,
    so `management-analysis` scores it NOT-CHECKED rather than reading silence as a pass.
    """
    data, gaps = {}, []
    if total_remuneration is None and net_profit is None:
        gaps.append("remuneration: no pay or net-profit figure supplied — NOT-CHECKED")
    else:
        data["remuneration"] = remuneration_check(total_remuneration, net_profit,
                                                  managing_directors,
                                                  executive_remuneration)
    if not fees:
        gaps.append("auditor_fee: no audit-fee series supplied — NOT-CHECKED")
    else:
        data["auditor_fee"] = auditor_fee_check(fees, revenues, profits)
    return spine.envelope(bool(data), "finance.compute.governance", data, gaps)
