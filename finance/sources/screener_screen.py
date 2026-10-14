"""Compatibility response for retired saved screens; no network or cache access.

AGENTS.md approves screener.in only for annual-report/concall document discovery.
Keep legacy callers informed instead of silently changing their screening criteria.
"""
from finance.spine import envelope


def screen(screen_url, max_survivors=200, fresh=False):
    return envelope(False, "screener.in", {
        "query": None, "screen_url": screen_url, "count": 0, "candidates": [],
    }, ["Saved screens are retired: screener.in is approved for documents only. Rewrite "
        "the spec with Tickertape fields, or report criteria Tickertape cannot express "
        "as data gaps; do not substitute a different screen."])
