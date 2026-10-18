"""deep-analysis run control: which mode a run takes, and whether the debate runs another round.

Mode, first match wins: an explicit flag (`--fundamentals` outranks `--deep`, which outranks
`--quick`); else a live holding or open trade escalates to `deep`; else `standard`. The
holding answer is tri-state because only the caller can ask the brokers, and `unknown`
must never read as unheld.

A debate round runs while the two sides still have something to test: different axes
(cross-examination) or the same axis with distinct claims (rebuttal). A concession, a
restated claim, no new evidence from either side after round 1, or the round cap ends it.
"""
import os
import re

from finance import paths, spine
from finance.deps import load_yaml

_SOURCE = "finance.compute.debate"

MODES = ("quick", "standard", "deep", "fundamentals")
FLAG_PRECEDENCE = ("--fundamentals", "--deep", "--quick")
HOLDING_STATES = ("yes", "no", "unknown")
HOLDING_REASON = "Held position → running deep analysis (override with --quick)."
UNKNOWN_GAP = ("broker holding check unavailable — depth resolved as if not held; "
               "a live holding would have escalated to deep")

VALID_AXES = {"valuation", "growth_durability", "balance_sheet_risk", "governance",
              "technical_structure"}
ROUND_CAP = 3
CROSS_EXAMINE = ("cross-examine: each side must answer the OPPONENT's axis directly "
                 "before restating its own")
REBUT = "rebut: both sides are on the same axis — attack the opposing claim's evidence"


def _explicit_flag(args):
    tokens = args.split()
    for flag in FLAG_PRECEDENCE:
        if flag in tokens:
            return flag[2:]
    return None


def _has_open_trade(symbol):
    """-> (an open trade record exists for `symbol`, gaps)."""
    if not symbol:
        return False, []
    sym = spine.norm_symbol(symbol)
    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9&_.-]*", sym):
        return False, ["open-trade lookup: invalid NSE symbol"]
    try:
        trades = paths.state_dir("trades", create=False)
        names = sorted(os.listdir(trades))
    except FileNotFoundError:
        return False, []
    except (OSError, ValueError) as exc:
        return False, [f"open-trade store unavailable ({type(exc).__name__})"]
    found, gaps = False, []
    for name in names:
        if not name.startswith(sym + "-") or not name.endswith((".yml", ".yaml")):
            continue
        try:
            trade = load_yaml(paths._contained(os.path.join(trades, name)))
            if not isinstance(trade, dict) or spine.norm_symbol(trade.get("symbol")) != sym:
                raise ValueError("trade identity does not match its filename")
            if trade.get("status") not in ("idea", "open", "closed"):
                raise ValueError("invalid trade status")
            found |= trade["status"] == "open"
        except Exception as exc:  # noqa: BLE001 — any unreadable record leaves the status unknown
            gaps.append(f"open-trade record {name} unreadable ({type(exc).__name__}); status unknown")
    return found, gaps


def resolve_mode(args, symbol=None, holding="unknown"):
    """-> {mode, reason, gaps}. `holding` is the caller's broker check: yes | no | unknown."""
    if holding not in HOLDING_STATES:
        raise ValueError(f"holding must be one of {HOLDING_STATES}, got {holding!r}")
    flag = _explicit_flag(args)
    if flag:
        return {"mode": flag, "reason": f"explicit --{flag} flag", "gaps": []}
    open_trade, gaps = _has_open_trade(symbol)
    if holding == "yes" or open_trade:
        return {"mode": "deep", "reason": HOLDING_REASON, "gaps": gaps}
    if holding == "unknown":
        gaps.append(UNKNOWN_GAP)
    if gaps:
        return {"mode": "standard",
                "reason": "default (no flag; holding/open-trade status incomplete)",
                "gaps": gaps}
    return {"mode": "standard", "reason": "default (no flag, not a held position)", "gaps": []}


def _norm(claim):
    """Normalize typography without deleting signs, operators or decimals."""
    return re.sub(r"\s+", " ", claim.casefold()).strip().rstrip(".!?").strip()


def next_round(bull, bear, round_no=1):
    """Round-`round_no` digests {axis, claim, conceded, new_evidence} -> {escalate, reason,
    directive, gaps}. `directive` names what the next round is for."""
    def stop(reason, gaps=()):
        return {"escalate": False, "reason": reason, "directive": None, "gaps": list(gaps)}

    if isinstance(round_no, bool) or not isinstance(round_no, int) or round_no < 1:
        return stop("invalid debate controls", ["round must be a positive integer"])
    bad = []
    for side, digest in (("bull", bull), ("bear", bear)):
        if not isinstance(digest, dict):
            bad.append(f"{side} digest must be an object")
            continue
        axis = digest.get("axis")
        if not isinstance(axis, str) or axis not in VALID_AXES:
            bad.append(f"{side} axis {axis!r} is not one of {sorted(VALID_AXES)}")
        if not isinstance(digest.get("claim"), str) or not _norm(digest["claim"]):
            bad.append(f"{side} gave no evidence-tied claim")
        for key in ("conceded", "new_evidence"):
            if not isinstance(digest.get(key), bool):
                bad.append(f"{side} {key} must be a JSON boolean")
    if bad:
        return stop("invalid digest — engagement not assessable", bad)
    if round_no >= ROUND_CAP:
        return stop(f"round {round_no} is the cap of {ROUND_CAP}")

    if bull["conceded"] and bear["conceded"]:
        return stop("both sides conceded their top point — debate converged")
    if bull["conceded"]:
        return stop("the bull conceded its top point — debate converged")
    if bear["conceded"]:
        return stop("the bear conceded its top point — debate converged")
    if round_no > 1 and not bull["new_evidence"] and not bear["new_evidence"]:
        return stop(f"neither side brought new evidence in round {round_no} — converged")

    if bull["axis"] != bear["axis"]:
        return {"escalate": True,
                "reason": (f"sides argued different axes ({bull['axis']} vs {bear['axis']}) — "
                           "neither has tested the other's case"),
                "directive": CROSS_EXAMINE, "gaps": []}
    if _norm(bull["claim"]) == _norm(bear["claim"]):
        return stop("both sides restate the same point — no genuine divergence")
    return {"escalate": True,
            "reason": f"genuine divergence on {bull['axis']}: distinct evidence-tied claims, no concession",
            "directive": REBUT, "gaps": []}


@spine.guarded(_SOURCE)
def mode_report(args, symbol=None, holding="unknown"):
    result = resolve_mode(args, symbol=symbol, holding=holding)
    return spine.envelope(True, _SOURCE, {"mode": result["mode"], "reason": result["reason"]},
                          result["gaps"])


@spine.guarded(_SOURCE)
def round_report(bull, bear, round_no=1):
    result = next_round(bull, bear, round_no=round_no)
    gaps = result.pop("gaps")
    return spine.envelope(not gaps, _SOURCE, result, gaps)
