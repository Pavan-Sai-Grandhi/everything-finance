#!/usr/bin/env python3
"""Peer-median P/E, own-band percentile and PEG, returned by `run_dcf`.

`pe` and every `peer_pe` must be trailing-twelve-month. Bare numbers arrive here, so a breach
is undetectable, and an annualised figure among them skews a +/-10% band by ~8% — enough to
flip the premium/discount read on its own.
"""
from __future__ import annotations

PEG_CAVEAT = ("PEG assumes equal risk across the peer set and a linear growth↔P/E "
              "relationship — a cross-check, not a standalone verdict.")

MIN_PEERS = 3                        # fewer priced peers and a median is one company's accident
PE_BASES = ("reported", "adjusted")  # a one-off gain can halve a reported P/E; the two never mix
MIN_GROWTH_PCT = 1.0                 # below this, growth is a fraction passed as a percent


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _num_list(value):
    """(numbers, rejected_count) — a tool schema is filled by an LLM, so a bad shape is
    counted, never raised."""
    if isinstance(value, dict):
        value = list(value.values())
    elif not isinstance(value, (list, tuple)):
        return [], 0 if value is None else 1
    nums = [_num(v) for v in value]
    return [n for n in nums if n is not None], sum(n is None for n in nums)


def median(values):
    """Median, not mean — multiples are skewed."""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None
    mid = len(xs) // 2
    return float(xs[mid]) if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def peg(pe, growth_pct):
    if pe is None or growth_pct is None or growth_pct <= 0:
        return None
    return round(pe / growth_pct, 2)


def band_percentile(current, history):
    """Share of the company's own historical band below `current`, 0-100."""
    xs = [v for v in history if v is not None]
    return round(sum(v < current for v in xs) / len(xs) * 100.0, 1) if xs else None


def _peer_signal(pe, peer_median):
    if peer_median is None or pe is None:
        return 0, "n/a"
    if pe < peer_median * 0.9:
        return -1, "discount"
    return (1, "premium") if pe > peer_median * 1.1 else (0, "in line")


def _band_signal(pct):
    return 0 if pct is None or 35 <= pct <= 65 else (-1 if pct < 35 else 1)


def relative_read(figures):
    """`peer_pe`/`own_pe_history` are flat number lists, `growth` is {value, basis} in percent;
    anything else becomes a gap, never an exception."""
    gaps = []
    pe = _num(figures.get("pe"))
    if pe is None and figures.get("pe") is not None:
        gaps.append("pe is not a number — the company multiple is void")

    peer_nums, rejected = _num_list(figures.get("peer_pe"))
    peer_pe = [p for p in peer_nums if p > 0]
    if rejected:
        gaps.append(f"{rejected} peer_pe entr{'y' if rejected == 1 else 'ies'} were not a number "
                    f"and were dropped — pass a flat list of P/E values")

    own_hist, hist_rejected = _num_list(figures.get("own_pe_history"))
    if hist_rejected:
        gaps.append("own_pe_history is not a list of numbers — the own-band read is void")

    growth = figures.get("growth")
    growth = growth if isinstance(growth, dict) else {"value": growth}
    g_val = _num(growth.get("value"))
    g_basis = growth.get("basis") or "unstated"
    if growth.get("estimated"):
        g_basis = f"{g_basis} (estimate)"
    if g_val is not None and pe is not None and 0 < g_val < MIN_GROWTH_PCT:
        gaps.append(f"growth {g_val} looks like a fraction, not a percent — PEG needs "
                    f"{g_val * 100:g} for {g_val * 100:g}% growth; PEG withheld")
        g_val = None

    basis, peer_basis = figures.get("pe_basis", "reported"), figures.get("peer_pe_basis", "reported")
    for name, b in (("pe_basis", basis), ("peer_pe_basis", peer_basis)):
        if b not in PE_BASES:
            gaps.append(f"{name} {b!r} is not one of {list(PE_BASES)}")

    peer_med = median(peer_pe)
    pct = band_percentile(pe, own_hist) if pe is not None else None
    peer_score, peer_label = _peer_signal(pe, peer_med)
    peer_counts = len(peer_pe) >= MIN_PEERS and basis == peer_basis
    if len(peer_pe) < MIN_PEERS:
        gaps.append(f"peer set too thin ({len(peer_pe)} priced, {MIN_PEERS} needed) — the peer "
                    f"comparison is void; this is an own-band read only")
    elif not peer_counts:
        gaps.append(f"P/E basis mismatch: the company is {basis}, the peers are {peer_basis} — the "
                    f"peer comparison is directional only and does not carry the stance")
    if not peer_counts:
        peer_score, peer_label = 0, "not comparable"

    if not peer_counts and pct is None:
        stance = "not computable"
        gaps.append(f"the peer comparison does not count ({len(peer_pe)} priced peers) and there "
                    f"is no own P/E history — nothing is left to read")
    else:
        score = peer_score + _band_signal(pct)
        stance = "undervalued" if score <= -1 else "overvalued" if score >= 1 else "fair"

    return {
        "pe": pe, "pe_basis": basis, "peer_pe_basis": peer_basis, "peer_median_pe": peer_med,
        "peers_priced": len(peer_pe), "peers_excluded_nonpositive": sum(p <= 0 for p in peer_nums),
        "peer_read_counts": peer_counts, "pe_vs_peer_median": peer_label,
        "own_band_percentile": pct, "peg": peg(pe, g_val), "peg_caveat": PEG_CAVEAT,
        "growth_basis": g_basis, "relative_stance": stance, "gaps": gaps,
    }
