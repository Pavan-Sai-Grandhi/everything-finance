#!/usr/bin/env python3
"""SEBI market-cap classification — the one definition of the tiers.

SEBI classifies by market-cap RANK, not by absolute size: top 100 large, 101-250 mid,
251+ small. AMFI publishes that rank half-yearly (`finance/sources/funds.py`
`amfi_cap_list`), and every consumer of a cap tier resolves it here.

Absolute ₹Cr bands are refused outright: a small-cap fund's biggest holdings are, by
construction, its largest names, so bands fabricate style drift out of nothing.

Network-free and dependency-free by design, so the pure math core in
`finance/compute/lookthrough.py` and the fetcher in `finance/sources/funds.py` can both
sit on it.
"""
import math
import re

SEBI_CAP_RANKS = {"large": 100, "mid": 250}


def cap_bucket(cap_rank=None, cap_label=None):
    """-> ("large"|"mid"|"small"|None, source).

    Rank is the fact; the provider's own text label is the labelled fallback when a rank
    is missing. `source` is `"rank"` or `"label"` so a consumer can report which of the
    two a classification rests on.
    """
    try:
        r = float(cap_rank) if not isinstance(cap_rank, bool) else None
    except (ValueError, TypeError, OverflowError):
        r = None
    if r is not None and math.isfinite(r) and r > 0 and r.is_integer():
        if r <= SEBI_CAP_RANKS["large"]:
            return "large", "rank"
        if r <= SEBI_CAP_RANKS["mid"]:
            return "mid", "rank"
        return "small", "rank"
    if not isinstance(cap_label, str):
        return None, None
    lab = re.sub(r"[\s_-]+", "", cap_label.lower())
    labels = {"large":"large", "largecap":"large", "mid":"mid", "midcap":"mid",
              "small":"small", "smallcap":"small", "micro":"small", "microcap":"small"}
    bucket = labels.get(lab)
    return (bucket, "label") if bucket else (None, None)


def cap_label(rank):
    """The SEBI cap band for a market-cap rank, or None. Derived from the rank so a
    published label and the rank it came from cannot disagree."""
    bucket, source = cap_bucket(cap_rank=rank)
    return f"{bucket.capitalize()} Cap" if source == "rank" else None
