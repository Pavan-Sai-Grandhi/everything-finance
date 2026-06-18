#!/usr/bin/env python3
"""Offline dry-run test for the artifact migration. Builds a fixture flat tree and
asserts the planned moves and that unclassifiable files are reported, not moved.
Run: python3 lib/test_migrate_artifacts.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import migrate_artifacts as mig  # noqa: E402

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


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write("x")


with tempfile.TemporaryDirectory() as tmp:
    root = os.path.join(tmp, "artifacts")
    # dated bucket — stock + singleton files
    touch(os.path.join(root, "2026-05-01", "RELIANCE-deep-analysis.md"))
    touch(os.path.join(root, "2026-05-01", "RELIANCE-deep-analysis", "agents", "technical.md"))
    touch(os.path.join(root, "2026-05-01", "dcf-RELIANCE.md"))
    touch(os.path.join(root, "2026-05-01", "dcf-RELIANCE.json"))
    touch(os.path.join(root, "2026-05-01", "management-RELIANCE.md"))
    touch(os.path.join(root, "2026-05-01", "TCS-filings.md"))
    touch(os.path.join(root, "2026-05-01", "daily-brief.md"))
    touch(os.path.join(root, "2026-05-01", "regime.json"))
    touch(os.path.join(root, "2026-05-01", "mystery-file.md"))  # unclassifiable
    # durable + disposable tiers
    touch(os.path.join(root, "strategies", "ema-pullback.yml"))
    touch(os.path.join(root, "trades", "TCS-2026-05-01.yml"))
    touch(os.path.join(root, ".cache", "ohlcv", "RELIANCE_2y.csv"))
    touch(os.path.join(root, ".staging", "RELIANCE.md"))
    touch(os.path.join(root, "watchlist.json"))
    touch(os.path.join(root, "stray.txt"))  # unclassifiable top-level

    moves, unclassified = mig.plan(root)
    dests = {os.path.relpath(d, root) for _, d in moves}

    expected = {
        "stocks/RELIANCE/2026-05-01/deep-analysis.md",
        "stocks/RELIANCE/2026-05-01/deep-analysis",
        "stocks/RELIANCE/2026-05-01/dcf.md",
        "stocks/RELIANCE/2026-05-01/dcf.json",
        "stocks/RELIANCE/2026-05-01/management.md",
        "stocks/TCS/2026-05-01/filings.md",
        "daily-brief/2026-05-01.md",
        "regime/2026-05-01.json",
        "state/strategies/ema-pullback.yml",
        "state/trades/TCS-2026-05-01.yml",
        "cache/ohlcv",
        "tmp/staging/RELIANCE.md",
        "state/watchlist.json",
    }
    for e in sorted(expected):
        check(f"plans move -> {e}", e in dests, sorted(dests))

    unrel = {os.path.relpath(s, root) for s, _ in unclassified}
    check("mystery file reported, not moved",
          any(u.endswith("mystery-file.md") for u in unrel), unrel)
    check("stray top-level reported, not moved", "stray.txt" in unrel, unrel)

    # dry-run must not have touched the filesystem
    check("dry-run left source in place",
          os.path.isfile(os.path.join(root, "2026-05-01", "RELIANCE-deep-analysis.md")))
    check("dry-run did not create new tree", not os.path.isdir(os.path.join(root, "stocks")))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
