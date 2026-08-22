#!/usr/bin/env python3
"""Relative-valuation math for the valuation leg.

Per Damodaran, relative multiples are shortcuts to the same DCF drivers (cash
flow/payout, growth, risk), so the valuation leg triangulates intrinsic (DCF) and
relative (multiples) into one stance. This module is the *relative* half, kept
deterministic and unit-tested so the figures are reproducible:

  - PEG = P/E ÷ expected EPS growth (%) — a cross-check, never a standalone verdict;
    its equal-risk + linear-growth assumptions travel with it as `PEG_CAVEAT`.
  - peer-group **median** multiple (median, not mean — multiples are skewed).
  - the company's position within its **own historical multiple band** (percentile).

Every input comes from `get_company_fundamentals` — the company's own ratios and its
peer rows. The expected-growth input for PEG is a labelled estimate (basis stated),
never fabricated.

CLI:
  PYTHONPATH=<plugin> python3 -m finance.compute.relval --figures figures.json
  PYTHONPATH=<plugin> python3 -m finance.compute.relval --selftest
"""
from __future__ import annotations

import argparse
import json
import sys

PEG_CAVEAT = ("PEG assumes equal risk across the peer set and a linear growth↔P/E "
              "relationship — a cross-check, not a standalone verdict.")

# Below this many priced peers a median is one company's accident, not a peer centre.
MIN_PEERS = 3

# Whether a P/E is struck on reported earnings or on earnings adjusted for one-offs.
# The two are not comparable: a recurring fair-value gain can halve a reported P/E.
PE_BASES = ("reported", "adjusted")


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
    """Compute the relative-only read from sourced figures. Returns peer-median
    P/E, the company's P/E vs that median, its own-band percentile, PEG (+ basis),
    and a relative-only stance — undervalued / fair / overvalued. `valuation-analysis`
    reconciles this against the DCF; this is the reproducible relative component.

    One consistency requirement the caller must meet, because this module sees only
    numbers and cannot detect a breach: `pe` and every `peer_pe` MUST be the
    trailing-twelve-month P/E (the company's `Stock P/E` and each peer's `ttm_pe`, NOT
    the annualised `pe`). Mixing TTM with annualised injects an ~8% skew into a ±10%
    peer band, enough to flip the premium/discount read on its own.

    The *earnings* basis is checked here instead of assumed: `pe_basis` and
    `peer_pe_basis` each declare "reported" or "adjusted". When they differ the peer
    comparison is directional only and contributes nothing to the stance.

    A negative or zero peer P/E is not a multiple (loss-making peer): it is excluded from
    the median here and the count is reported, so a couple of loss-makers cannot drag the
    peer centre and read the company as a spurious 'premium'.

    Fewer than `MIN_PEERS` priced peers voids the peer half of the read; with no own-band
    history either, there is nothing left and the stance is `not computable` — an absent
    comparison must not arrive downstream as a computed one."""
    pe = figures.get("pe")
    peer_pe_raw = figures.get("peer_pe") or []
    peer_pe = [p for p in peer_pe_raw if p is not None and p > 0]
    peers_excluded = sum(1 for p in peer_pe_raw if p is not None and p <= 0)
    own_hist = figures.get("own_pe_history") or []
    growth = figures.get("growth") or {}

    peer_med = median(peer_pe)
    pct = band_percentile(pe, own_hist) if pe is not None else None
    g_val = growth.get("value")
    g_basis = growth.get("basis", "unstated")
    if growth.get("estimated"):
        g_basis = f"{g_basis} (estimate)"

    gaps = []
    basis = figures.get("pe_basis", "reported")
    peer_basis = figures.get("peer_pe_basis", "reported")
    for name, b in (("pe_basis", basis), ("peer_pe_basis", peer_basis)):
        if b not in PE_BASES:
            gaps.append(f"{name} {b!r} is not one of {list(PE_BASES)}")

    peer_score, peer_label = _peer_signal(pe, peer_med)
    peer_counts = True
    if len(peer_pe) < MIN_PEERS:
        peer_counts = False
        gaps.append(f"peer set too thin ({len(peer_pe)} priced, {MIN_PEERS} needed) — "
                    f"the peer comparison is void; this is an own-band read only")
    elif basis != peer_basis:
        peer_counts = False
        gaps.append(f"P/E basis mismatch: the company is {basis}, the peers are "
                    f"{peer_basis} — the peer comparison is directional only and does "
                    f"not carry the stance")

    if not peer_counts:
        peer_score = 0
        peer_label = "not comparable"

    if not peer_counts and pct is None:
        stance = "not computable"
        gaps.append("no priced peers and no own P/E history — there is no relative read")
    else:
        score = peer_score + _band_signal(pct)
        stance = "fair"
        if score <= -1:
            stance = "undervalued"
        elif score >= 1:
            stance = "overvalued"

    return {
        "pe": pe,
        "pe_basis": basis,
        "peer_pe_basis": peer_basis,
        "peer_median_pe": peer_med,
        "peers_priced": len(peer_pe),
        "peers_excluded_nonpositive": peers_excluded,
        "peer_read_counts": peer_counts,
        "pe_vs_peer_median": peer_label,
        "own_band_percentile": pct,
        "peg": peg(pe, g_val),
        "peg_caveat": PEG_CAVEAT,
        "growth_basis": g_basis,
        "relative_stance": stance,
        "gaps": gaps,
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
    ap.add_argument("--figures", help="path to a JSON of sourced figures")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(_selftest())
    with open(a.figures) as f:
        figures = json.load(f)
    print(json.dumps(relative_read(figures), indent=2))


if __name__ == "__main__":
    main()
