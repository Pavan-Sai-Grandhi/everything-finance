#!/usr/bin/env python3
"""Offline tests for deep-analysis mode resolution. No network. Each test that
touches the trade store runs inside a temp artifacts root. Run:
  python3 skills/deep-analysis/scripts/test_resolve_mode.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
import resolve_mode  # noqa: E402
from finance.tests.harness import check, summary  # noqa: E402


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

r = resolve_mode.resolve("RRKABEL --deep --quick", symbol="RRKABEL")
check("--deep beats --quick", r["mode"] == "deep", r)

# explicit flag overrides holding auto-escalation
r = resolve_mode.resolve("RRKABEL --quick", symbol="RRKABEL", broker_holding=True)
check("--quick beats broker holding", r["mode"] == "quick", r)

# --- the fundamentals-only mode ----------------------------------------------
check("fundamentals is a valid mode", "fundamentals" in resolve_mode.VALID_MODES,
      resolve_mode.VALID_MODES)

r = resolve_mode.resolve("RRKABEL --fundamentals", symbol="RRKABEL")
check("--fundamentals → fundamentals", r["mode"] == "fundamentals", r)
check("--fundamentals reason mentions flag", "flag" in r["reason"].lower(), r)

# it names the question, not the rigour — so it outranks both depth flags
r = resolve_mode.resolve("RRKABEL --fundamentals --deep", symbol="RRKABEL")
check("--fundamentals beats --deep", r["mode"] == "fundamentals", r)
r = resolve_mode.resolve("RRKABEL --quick --fundamentals", symbol="RRKABEL")
check("--fundamentals beats --quick", r["mode"] == "fundamentals", r)

# and, being an explicit flag, it beats the holding auto-escalation on both halves
r = resolve_mode.resolve("RRKABEL --fundamentals", symbol="RRKABEL", broker_holding=True)
check("--fundamentals beats broker holding", r["mode"] == "fundamentals", r)

with tempfile.TemporaryDirectory() as root:
    write_trade(root, "RRKABEL", "2026-06-01", "open")
    r = resolve_mode.resolve("RRKABEL --fundamentals", symbol="RRKABEL", root=root)
    check("--fundamentals beats an open trade artifact", r["mode"] == "fundamentals", r)

# no flag never selects it — a fundamentals-only read is always asked for
r = resolve_mode.resolve("RRKABEL fundamentals", symbol="RRKABEL")
check("bare word 'fundamentals' is not the flag", r["mode"] == "standard", r)

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

for args in ("RRKABEL", "RRKABEL --quick", "RRKABEL --deep", "RRKABEL --fundamentals"):
    m = resolve_mode.resolve(args, symbol="RRKABEL")["mode"]
    check(f"'{args}' resolves inside VALID_MODES", m in resolve_mode.VALID_MODES, m)

check("selftest passes", resolve_mode._selftest() == 0)

summary()
