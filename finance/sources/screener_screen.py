"""Compatibility response for retired saved screens; no network or cache access.

AGENTS.md approves screener.in only for annual-report/concall document discovery.
Keep legacy callers informed instead of silently changing their screening criteria.
"""
from finance.spine import envelope


def screen(screen_url, max_survivors=200, fresh=False):
    return envelope(False, "screener.in", {
        "query": None, "screen_url": screen_url, "count": 0, "candidates": [],
    }, ["Saved fundamental screens are not an approved decision source. screener.in is "
        "approved for document discovery only. Re-author the spec using the supported "
        "Tickertape fields, or report unsupported criteria as data gaps; do not silently "
        "substitute a different screen."])
