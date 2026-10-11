#!/usr/bin/env python3
"""Resolve the deep-analysis run mode — quick / standard / deep / fundamentals.

This is the deterministic half of the selection. Resolution order, first match wins:

  1. Explicit flag — `--fundamentals`, `--deep` or `--quick` in the argument always
     wins, including over the holding auto-escalation. `--fundamentals` outranks the
     two depth flags because it names a different question (the fundamentals-only
     read, which has no debate) rather than a level of rigour within the debate.
  2. Holding auto-escalation — no explicit flag and the ticker is a live holding
     or open trade → `deep`. The broker-MCP holdings check is the orchestrator's
     job (it passes the result in as `holding`, since script code can't call MCP
     tools); the open-trade-artifact half is a pure file read done here.
  3. Default — `standard`.

The broker half is **tri-state**: `yes` / `no` / `unknown`. `unknown` — no broker
connected, or connected-account coverage was incomplete — resolves to the same depth as `no` but
must never read as `no`: it returns a gap and a reason that does not claim the ticker
is unheld, because a missed holding costs the run its `deep` escalation.

Returns `{mode, reason, gaps}` — all three are recorded by the synthesis.

CLI:
  python3 resolve_mode.py --args "RRKABEL --quick" --symbol RRKABEL --holding no
  python3 resolve_mode.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from finance import paths
from finance.deps import load_yaml
from finance.spine import norm_symbol

VALID_MODES = ("quick", "standard", "deep", "fundamentals")
FLAG_PRECEDENCE = ("--fundamentals", "--deep", "--quick")
HOLDING_STATES = ("yes", "no", "unknown")
HOLDING_REASON = "Held position → running deep analysis (override with --quick)."
UNKNOWN_GAP = ("broker holding check unavailable — depth resolved as if not held; "
               "a live holding would have escalated to deep")


def _explicit_flag(args):
    """Return the mode a flag in the argument string names, else None. Flags are
    mutually exclusive; when several appear, FLAG_PRECEDENCE decides. Between the two
    depth flags deep wins — more rigour never harms, and it matches the held-position
    bias."""
    toks = args.split()
    for flag in FLAG_PRECEDENCE:
        if flag in toks:
            return flag[2:]
    return None


def _has_open_trade(symbol):
    """Read matching trade records through the path authority; return (found, gaps)."""
    if not symbol:
        return False, []
    sym = norm_symbol(symbol)
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
            path = paths._contained(os.path.join(trades, name))
            trade = load_yaml(path)
            if not isinstance(trade, dict) or norm_symbol(trade.get("symbol")) != sym:
                raise ValueError("trade identity does not match its filename")
            status = trade.get("status")
            if status not in ("idea", "open", "closed"):
                raise ValueError("invalid trade status")
            found |= status == "open"
        except Exception as exc:
            gaps.append(f"open-trade record {name} unreadable ({type(exc).__name__}); status unknown")
    return found, gaps


def resolve(args, symbol=None, holding="unknown"):
    """Resolve the depth mode. `args` is the raw argument string; `holding` is the
    orchestrator's broker-MCP result, one of yes/no/unknown. Returns
    {mode, reason, gaps}."""
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
        # An incomplete broker or local record check cannot establish an unheld position.
        return {"mode": "standard",
                "reason": "default (no flag; holding/open-trade status incomplete)",
                "gaps": gaps}
    return {"mode": "standard", "reason": "default (no flag, not a held position)",
            "gaps": []}


def _selftest():
    ok = resolve("X --quick", symbol="X", holding="no")["mode"] == "quick"
    ok &= resolve("X", symbol="X", holding="no")["mode"] == "standard"
    ok &= resolve("X", symbol="X", holding="yes")["mode"] == "deep"
    ok &= resolve("X --fundamentals", symbol="X",
                  holding="yes")["mode"] == "fundamentals"
    unk = resolve("X", symbol="X", holding="unknown")
    ok &= unk["mode"] == "standard" and unk["gaps"] and "not a held position" not in unk["reason"]
    print("selftest", "ok" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--args", default="", help="raw deep-analysis argument string")
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--holding", choices=HOLDING_STATES, default="unknown",
                    help="the orchestrator's broker-MCP result: yes (a holding or open "
                         "position), no (checked, not held), unknown (no broker connected, "
                         "or connected-account coverage was incomplete). Default unknown — never "
                         "silently 'no'.")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    print(json.dumps(resolve(a.args, symbol=a.symbol, holding=a.holding)))


if __name__ == "__main__":
    main()
