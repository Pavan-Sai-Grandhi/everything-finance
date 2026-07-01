#!/usr/bin/env python3
"""Relative-valuation math for the valuation leg (spec §5).

Per Damodaran, relative multiples are shortcuts to the same DCF drivers (cash
flow/payout, growth, risk), so the valuation leg triangulates intrinsic (DCF) and
relative (multiples) into one stance. This module is the *relative* half, kept
deterministic and unit-tested so the figures are reproducible:

  - PEG = P/E ÷ expected EPS growth (%) — a cross-check, never a standalone verdict;
    its equal-risk + linear-growth assumptions are flagged by the agent.
  - peer-group **median** multiple (median, not mean — multiples are skewed).
  - the company's position within its **own historical multiple band** (percentile).

Every input comes from the screener.in data-pack (ratios + peers — already
whitelisted). The expected-growth input for PEG is a labelled estimate (basis
stated), never fabricated.

CLI:
  python3 relval.py --figures figures.json
  python3 relval.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys

PEG_CAVEAT = ("PEG assumes equal risk across the peer set and a linear growth↔P/E "
              "relationship — a cross-check, not a standalone verdict.")


def median(values):
    """Median of a numeric list (median, not mean — multiples are skewed). None if empty."""
    xs = sorted(v for v in values if v is not None)
    n = len(xs)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return float(xs[mid])
    return (xs[mid - 1] + xs[mid]) / 2.0


def peg(pe, growth_pct):
    """P/E ÷ expected EPS growth in percent (e.g. 22 for 22%). None when growth is
    non-positive (PEG is undefined / meaningless there)."""
    if pe is None or growth_pct is None or growth_pct <= 0:
        return None
    return round(pe / growth_pct, 2)


def band_percentile(current, history):
    """Percentile of `current` within its own historical band — the share of the
    band strictly below it, 0–100. None if no history."""
    xs = [v for v in history if v is not None]
    if not xs:
        return None
    below = sum(1 for v in xs if v < current)
    return round(below / len(xs) * 100.0, 1)


def _peer_signal(pe, peer_median):
    if peer_median is None or pe is None:
        return 0, "n/a"
    if pe < peer_median * 0.9:
        return -1, "discount"
    if pe > peer_median * 1.1:
        return 1, "premium"
    return 0, "in line"


def _band_signal(pct):
    if pct is None:
        return 0
    if pct < 35:
        return -1   # low in its own band
    if pct > 65:
        return 1    # high in its own band
    return 0


def relative_read(figures):
    """Compute the relative-only read from data-pack figures. Returns peer-median
    P/E, the company's P/E vs that median, its own-band percentile, PEG (+ basis),
    and a relative-only stance — undervalued / fair / overvalued. The agent
    reconciles this against the DCF; this is the reproducible relative component."""
    pe = figures.get("pe")
    peer_pe = figures.get("peer_pe") or []
    own_hist = figures.get("own_pe_history") or []
    growth = figures.get("growth") or {}

    peer_med = median(peer_pe)
    pct = band_percentile(pe, own_hist) if pe is not None else None
    g_val = growth.get("value")
    g_basis = growth.get("basis", "unstated")
    if growth.get("estimated"):
        g_basis = f"{g_basis} (estimate)"

    peer_score, peer_label = _peer_signal(pe, peer_med)
    score = peer_score + _band_signal(pct)
    stance = "fair"
    if score <= -1:
        stance = "undervalued"
    elif score >= 1:
        stance = "overvalued"

    return {
        "pe": pe,
        "peer_median_pe": peer_med,
        "pe_vs_peer_median": peer_label,
        "own_band_percentile": pct,
        "peg": peg(pe, g_val),
        "peg_caveat": PEG_CAVEAT,
        "growth_basis": g_basis,
        "relative_stance": stance,
    }


def _selftest():
    ok = median([12, 15, 20, 25, 30]) == 20
    ok &= peg(18.0, 22.0) == 0.82
    ok &= band_percentile(18.0, [12, 15, 20, 25, 30]) == 40.0
    ok &= relative_read({"pe": 18.0, "peer_pe": [28, 24, 30, 22],
                         "own_pe_history": [20, 25, 28, 30, 32]})["relative_stance"] == "undervalued"
    print("selftest", "ok" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--figures", help="path to a JSON of data-pack figures")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    with open(a.figures) as f:
        figures = json.load(f)
    print(json.dumps(relative_read(figures), indent=2))


if __name__ == "__main__":
    main()
