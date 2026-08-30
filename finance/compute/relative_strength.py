#!/usr/bin/env python3
"""Relative-strength-vs-benchmark math — the one definition.

Windowed price returns and the Leading/Improving/Weakening/Lagging classification that
`compute/stock_scan.py` (rank a stock by its momentum vs Nifty) and
`compute/sector_scan.py` (rank the sectoral indices) both draw on, so a stock's RS and a
sector's RS are computed the same way. Pure math over a close series already fetched.

Windows are fixed trading-day counts (21/63/126 ≈ 1M/3M/6M) so reads are comparable.
"""
from __future__ import annotations

WINDOWS = {"1m": 21, "3m": 63, "6m": 126}


def pct_return(closes, lookback):
    """% return over the last `lookback` bars, or None if the series is too short."""
    if not closes or len(closes) <= lookback:
        return None
    start = closes[-1 - lookback]
    if not start:
        return None
    return round(100.0 * (closes[-1] / start - 1.0), 2)


def window_returns(closes, windows=None):
    """{window: % return} over each named window."""
    return {k: pct_return(closes, n) for k, n in (windows or WINDOWS).items()}


def rs_vs_benchmark(closes, benchmark, windows=None):
    """{window: series return − benchmark return} — positive means outperforming."""
    s = window_returns(closes, windows)
    b = window_returns(benchmark, windows)
    return {k: (round(s[k] - b[k], 2) if s[k] is not None and b[k] is not None else None)
            for k in (windows or WINDOWS)}


def classify(rs_1m, rs_3m):
    """Leading / Improving / Weakening / Lagging from the 1M and 3M RS readings.

    Improving (1M positive, 3M negative) is early rotation — the actionable class.
    Either window missing yields 'unclassified' rather than a guessed label.
    """
    if rs_1m is None or rs_3m is None:
        return "unclassified"
    if rs_1m >= 0 and rs_3m >= 0:
        return "Leading"
    if rs_1m >= 0 > rs_3m:
        return "Improving"
    if rs_1m < 0 <= rs_3m:
        return "Weakening"
    return "Lagging"
