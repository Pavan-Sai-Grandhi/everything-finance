"""Rate scenarios for a debt fund: the third check in `methods/funds.md` → *Debt funds*.

Over a year, a debt fund earns roughly its yield to maturity, less its expense ratio, less its
modified duration times the change in yield. The skill reads YTM, modified duration and the
Direct-plan TER from the AMC's factsheet and passes them here, so the arithmetic is
reproducible and a fall and a rise of one point are always both shown: the plugin holds no
rate view, so it never reports one direction alone.

Reached through: run_debt_scenarios.
"""
from __future__ import annotations

import math

from finance import spine

_SOURCE = "finance.compute.debt_fund"
ALWAYS = (-1.0, 0.0, 1.0)


def _bounded(name, value, low, high):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not low <= value <= high):
        raise ValueError(f"{name} must be a finite number in [{low}, {high}]")
    return float(value)


@spine.guarded(_SOURCE)
def scenarios(ytm_pct, modified_duration, ter_pct, shifts=None):
    """One-year return (%) per yield change in percentage points, for the given shifts plus
    -1, 0 and +1. First order: no convexity, no credit event, the change taken at once."""
    ytm = _bounded("ytm_pct", ytm_pct, 0, 30)
    md = _bounded("modified_duration", modified_duration, 0, 40)
    ter = _bounded("ter_pct", ter_pct, 0, 3)
    extra = [] if shifts is None else shifts
    if not isinstance(extra, (list, tuple)) or len(extra) > 8:
        raise ValueError("shifts must be a list of at most 8 yield changes")
    moves = sorted({_bounded("shift", s, -5, 5) for s in extra} | set(ALWAYS))
    rows = [{"yield_change_pp": s, "return_pct": round(ytm - ter - md * s, 2)} for s in moves]
    return spine.envelope(True, _SOURCE, {
        "inputs": {"ytm_pct": ytm, "modified_duration": md, "ter_pct": ter},
        "formula": "return ≈ YTM − TER − modified duration × yield change",
        "scenarios": rows,
        "note": "first-order, one-year estimate: ignores convexity, defaults and when in the "
                "year the yield moves; states no view on the direction of rates",
    }, [])
