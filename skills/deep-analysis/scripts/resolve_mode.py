#!/usr/bin/env python3
"""Resolve the deep-analysis depth mode for a run — quick / standard / deep.

deep-analysis runs three depth modes; this is the deterministic half of the
selection (spec §2). Resolution order, first match wins:

  1. Explicit flag — `--quick` or `--deep` in the argument always wins, including
     over the holding auto-escalation.
  2. Holding auto-escalation — no explicit flag and the ticker is a live holding
     or open trade → `deep`. The broker-MCP holdings check is the orchestrator's
     job (it passes the result in as `broker_holding`, since script code can't call
     MCP tools); the open-trade-artifact half is a pure file read done here.
  3. Default — `standard`.

Returns `{mode, reason}` — `reason` is recorded by the synthesis.

CLI:
  python3 resolve_mode.py --args "RRKABEL --quick" --symbol RRKABEL [--broker-holding]
  python3 resolve_mode.py --selftest
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

VALID_MODES = ("quick", "standard", "deep")
HOLDING_REASON = "Held position → running deep analysis (override with --quick)."


def _artifacts_root(root=None):
    if root:
        return root
    return os.environ.get("EVERYTHING_FINANCE_ARTIFACTS", "artifacts")


def _explicit_flag(args):
    """Return 'quick'/'deep' if the argument string carries that flag, else None.
    `--deep` and `--quick` are mutually exclusive; if both appear, deep wins
    (more rigour never harms, and it matches the held-position bias)."""
    toks = args.split()
    if "--deep" in toks:
        return "deep"
    if "--quick" in toks:
        return "quick"
    return None


def _has_open_trade(symbol, root):
    """True if any artifacts/state/trades/<SYMBOL>-*.yml has status: open. Pure
    file read — a missing dir or unparseable file is simply 'no open trade'."""
    if not symbol:
        return False
    trades = os.path.join(_artifacts_root(root), "state", "trades")
    for path in glob.glob(os.path.join(trades, f"{symbol}-*.yml")):
        try:
            with open(path) as f:
                for line in f:
                    s = line.strip().lower()
                    if s.startswith("status:") and s.split(":", 1)[1].strip() == "open":
                        return True
        except OSError:
            continue
    return False


def resolve(args, symbol=None, broker_holding=False, root=None):
    """Resolve the depth mode. `args` is the raw argument string; `broker_holding`
    is the orchestrator's broker-MCP result. Returns {mode, reason}."""
    flag = _explicit_flag(args)
    if flag:
        return {"mode": flag, "reason": f"explicit --{flag} flag"}
    if broker_holding or _has_open_trade(symbol, root):
        return {"mode": "deep", "reason": HOLDING_REASON}
    return {"mode": "standard", "reason": "default (no flag, not a held position)"}


def _selftest():
    ok = resolve("X --quick", symbol="X")["mode"] == "quick"
    ok &= resolve("X", symbol="X")["mode"] == "standard"
    ok &= resolve("X", symbol="X", broker_holding=True)["mode"] == "deep"
    print("selftest", "ok" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--args", default="", help="raw deep-analysis argument string")
    ap.add_argument("--symbol", default=None)
    ap.add_argument("--broker-holding", action="store_true",
                    help="set by the orchestrator when broker MCP shows a holding/position")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    print(json.dumps(resolve(a.args, symbol=a.symbol, broker_holding=a.broker_holding)))


if __name__ == "__main__":
    main()
