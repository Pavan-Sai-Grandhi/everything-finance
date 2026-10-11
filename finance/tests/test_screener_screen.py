#!/usr/bin/env python3
"""Retired source must never fetch, even for a cached or apparently valid URL."""
import os
import sys
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.sources import screener_screen
from finance import transport, spine
from finance.tests.harness import check, run


def test_retired_source_never_fetches_or_uses_cache():
    with patch.object(transport, 'request', side_effect=AssertionError('network forbidden')) as request, \
         patch.object(spine, 'read_cache', side_effect=AssertionError('cache forbidden')) as cached:
        for url in ('https://www.screener.in/screens/999/example/', 'https://example.com', None):
            result = screener_screen.screen(url, fresh=False)
            check('retired screen returns a labelled refusal', not result['ok'] and bool(result['gaps']))
            check('retired screen cannot produce decision candidates', result['data']['candidates'] == [])
        check('no fetch or stale cache path', not request.called and not cached.called)


if __name__ == '__main__':
    run(globals())
