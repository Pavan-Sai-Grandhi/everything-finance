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

# A P/E divided by a growth *fraction* is a PEG a hundred times too large. Below this,
# a growth figure alongside a real P/E is a unit error, not a company growing 0.5%/yr.
MIN_GROWTH_PCT = 1.0


def _num(value):
    """`value` as a float, or None if it is not a number. Bools are not numbers here."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _num_list(value):
    """A numeric list from whatever the caller passed. Returns (numbers, rejected_count).

    A caller reaching this module is an LLM filling a tool schema, and the shapes it
    reaches for — a list of `{symbol, pe}` rows, a `{symbol: pe}` map, a sentence where
    a series was not available — are all iterable and none are numbers. Each is a counted
    rejection the caller sees as a gap, never an exception out of the tool.
    """
    if value is None:
        return [], 0
    if isinstance(value, dict):
        value = list(value.values())
    elif isinstance(value, str) or not isinstance(value, (list, tuple)):
        return [], 1
    out, rejected = [], 0
    for v in value:
        n = _num(v)
        if n is None:
            rejected += 1
        else:
            out.append(n)
    return out, rejected


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
    comparison must not arrive downstream as a computed one.

    Every figure is coerced, never trusted: `peer_pe` and `own_pe_history` are flat lists
    of numbers and `growth` is `{value, basis}` (a bare number is read as the value), but
    this runs behind a tool schema, so anything else arrives as a counted gap and the read
    that depended on it is void. A malformed field must degrade one line of the read, not
    raise out of the tool carrying no result at all."""
    gaps = []
    pe = _num(figures.get("pe"))
    if pe is None and figures.get("pe") is not None:
        gaps.append("pe is not a number — the company multiple is void")

    peer_nums, peer_rejected = _num_list(figures.get("peer_pe"))
    peer_pe = [p for p in peer_nums if p > 0]
    peers_excluded = sum(1 for p in peer_nums if p <= 0)
    if peer_rejected:
        gaps.append(f"{peer_rejected} peer_pe entr{'y' if peer_rejected == 1 else 'ies'} "
                    f"were not a number and were dropped — pass a flat list of P/E values")

    own_hist, hist_rejected = _num_list(figures.get("own_pe_history"))
    if hist_rejected:
        gaps.append("own_pe_history is not a list of numbers — the own-band read is void")

    growth = figures.get("growth")
    if not isinstance(growth, dict):
        growth = {"value": growth, "basis": "unstated"}
    g_val = _num(growth.get("value"))

    peer_med = median(peer_pe)
    pct = band_percentile(pe, own_hist) if pe is not None else None
    g_basis = growth.get("basis") or "unstated"
    if growth.get("estimated"):
        g_basis = f"{g_basis} (estimate)"
    if g_val is not None and pe is not None and 0 < g_val < MIN_GROWTH_PCT:
        gaps.append(f"growth {g_val} looks like a fraction, not a percent — PEG needs "
                    f"{g_val * 100:g} for {g_val * 100:g}% growth; PEG withheld")
        g_val = None

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
        gaps.append(f"the peer comparison does not count ({len(peer_pe)} priced peers) and "
                    f"there is no own P/E history — nothing is left to read")
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
