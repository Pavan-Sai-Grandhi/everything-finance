#!/usr/bin/env python3
"""Relative-strength-vs-benchmark math — the one definition.

Windowed price returns and the Leading/Improving/Weakening/Lagging classification that
`compute/stock_scan.py` (rank a stock by its momentum vs Nifty) and
`compute/sector_scan.py` (rank the sectoral indices) both draw on, so a stock's RS and a
sector's RS are computed the same way. Pure math over a close series already fetched.

Windows are fixed trading-day counts (21/63/126 ≈ 1M/3M/6M) so reads are comparable.
"""
from __future__ import annotations

import math

from finance import spine


WINDOWS = {"1m": 21, "3m": 63, "6m": 126}


def pct_return(closes, lookback):
    """% return over the last `lookback` bars, or None if the series is too short."""
    if type(lookback) is not int or lookback < 1 or not closes or len(closes) <= lookback:
        return None
    start = closes[-1 - lookback]
    if not spine.is_finite(start) or not spine.is_finite(closes[-1]) or start <= 0 or closes[-1] <= 0:
        return None
    result = 100.0 * (closes[-1] / start - 1.0)
    return round(result, 2) if math.isfinite(result) else None


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
    if not spine.is_finite(rs_1m) or not spine.is_finite(rs_3m):
        return "unclassified"
    if rs_1m >= 0 and rs_3m >= 0:
        return "Leading"
    if rs_1m >= 0 > rs_3m:
        return "Improving"
    if rs_1m < 0 <= rs_3m:
        return "Weakening"
    return "Lagging"


def load_history(closes_fn, symbol, fresh=False):
    try:
        loaded = closes_fn(symbol, fresh)
        # Bare arrays are the existing pure-compute test injection contract.
        history = loaded if isinstance(loaded, dict) else {"closes": loaded, "dates": [], "gaps": []}
        closes = history["closes"]
        if not isinstance(closes, list) or any(isinstance(v, bool) or not isinstance(v, (int,float)) or not math.isfinite(v) or v <= 0 for v in closes):
            raise ValueError("invalid close series")
        return history
    except Exception as exc:
        return {"closes": [], "dates": [], "gaps": [f"price history unavailable ({type(exc).__name__})"]}
