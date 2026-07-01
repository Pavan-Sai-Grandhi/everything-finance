#!/usr/bin/env python3
"""Offline tests for deep-analysis mode resolution. No network. Each test that
touches the trade store runs inside a temp artifacts root. Run:
  python3 skills/deep-analysis/scripts/test_resolve_mode.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resolve_mode  # noqa: E402

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


def write_trade(root, symbol, date, status):
    d = os.path.join(root, "state", "trades")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{symbol}-{date}.yml"), "w") as f:
        f.write(f"symbol: {symbol}\nstatus: {status}\n")


# --- step 1: explicit flag wins -----------------------------------------------
r = resolve_mode.resolve("RRKABEL --quick", symbol="RRKABEL")
check("--quick → quick", r["mode"] == "quick", r)
check("--quick reason mentions flag", "flag" in r["reason"].lower(), r)

r = resolve_mode.resolve("--deep RRKABEL", symbol="RRKABEL")
check("--deep → deep", r["mode"] == "deep", r)

# explicit flag overrides holding auto-escalation
r = resolve_mode.resolve("RRKABEL --quick", symbol="RRKABEL", broker_holding=True)
check("--quick beats broker holding", r["mode"] == "quick", r)

# --- step 3: default ----------------------------------------------------------
r = resolve_mode.resolve("RRKABEL", symbol="RRKABEL")
check("no flag, not held → standard", r["mode"] == "standard", r)
check("default reason", "default" in r["reason"].lower(), r)

# --- step 2: holding auto-escalation -----------------------------------------
r = resolve_mode.resolve("RRKABEL", symbol="RRKABEL", broker_holding=True)
check("broker holding → deep", r["mode"] == "deep", r)
check("holding reason note", "override with --quick" in r["reason"], r)

with tempfile.TemporaryDirectory() as root:
    write_trade(root, "RRKABEL", "2026-06-01", "open")
    r = resolve_mode.resolve("RRKABEL", symbol="RRKABEL", root=root)
    check("open trade artifact → deep", r["mode"] == "deep", r)

with tempfile.TemporaryDirectory() as root:
    write_trade(root, "RRKABEL", "2026-06-01", "closed")
    r = resolve_mode.resolve("RRKABEL", symbol="RRKABEL", root=root)
    check("closed trade artifact → standard", r["mode"] == "standard", r)

with tempfile.TemporaryDirectory() as root:
    write_trade(root, "OTHERCO", "2026-06-01", "open")
    r = resolve_mode.resolve("RRKABEL", symbol="RRKABEL", root=root)
    check("open trade for a different symbol is ignored", r["mode"] == "standard", r)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
