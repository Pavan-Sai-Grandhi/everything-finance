#!/usr/bin/env python3
"""Offline tests for finance/sources/screener_screen.py — the screener.in saved-screen provider.

`transport.request` is stubbed with a url -> (body, gap) map, so the parser is exercised against
fixture HTML shaped like a real screener.in screen (query textarea, data-table with /company/
links including a numeric BSE-only code, and a 'Showing page X of Y' marker)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance import paths, transport
from finance.sources import screener_screen as ss
from finance.tests.harness import check, run


def _page(query, rows, page_no, pages_total):
    """A minimal screener.in screen page: a query textarea + a data-table of /company/ links."""
    links = "".join(f'<tr><td><a href="/company/{r}/">{r}</a></td></tr>' for r in rows)
    q = f'<textarea name="query" rows="3">{query}</textarea>' if query is not None else ""
    return (f'<html><body>{q}'
            f'<table class="data-table">{links}</table>'
            f'<div class="pagination">Showing page {page_no} of {pages_total}</div>'
            f'</body></html>')


def _stub_transport(pagemap):
    """Route transport.request to a {url: body} map; unknown urls become a gap."""
    saved = transport.request

    def fake(url, *, dest=None, **kw):
        if url in pagemap:
            return pagemap[url], None
        return None, f"{url}: no fixture"
    transport.request = fake
    return saved


def _isolate_cache():
    """Point the cache tier at a fresh temp dir so a prior run's cache can't mask a parse."""
    saved = os.environ.get("EVERYTHING_FINANCE_ARTIFACTS")
    os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = tempfile.mkdtemp()
    paths.reset_cache() if hasattr(paths, "reset_cache") else None
    return saved


def test_rejects_a_non_screener_url():
    env = ss.screen("https://example.com/screens/1/foo/")
    check("a non-screener.in URL is refused", env["ok"] is False)
    check("the refusal names the expected URL shape",
          any("saved-screen URL" in g for g in env["gaps"]), env["gaps"])


def test_parses_query_symbols_and_skips_bse_codes():
    url = "https://www.screener.in/screens/999/demo/"
    body = _page("Market Cap > 500 AND ROCE > ROCE preceding year",
                 ["TCS", "INFY", "534535", "WIPRO"], 1, 1)
    saved_t = _stub_transport({url: body})
    saved_a = _isolate_cache()
    try:
        env = ss.screen(url, fresh=True)
    finally:
        transport.request = saved_t
        if saved_a is not None:
            os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = saved_a
    check("the screen resolves ok", env["ok"] is True, env["gaps"])
    check("the author's cross-period query text is carried back",
          env["data"]["query"] == "Market Cap > 500 AND ROCE > ROCE preceding year",
          env["data"]["query"])
    check("the NSE symbols are the candidates",
          env["data"]["candidates"] == ["TCS", "INFY", "WIPRO"], env["data"]["candidates"])
    check("the numeric BSE-only code is skipped, not emitted",
          "534535" not in env["data"]["candidates"])
    check("the skipped BSE code is a labelled gap",
          any("BSE-only" in g and "534535" in g for g in env["gaps"]), env["gaps"])


def test_walks_pages_to_max_survivors():
    base = "https://www.screener.in/screens/42/multi/"
    p1 = _page("Market Cap > 100", ["AAA", "BBB", "CCC"], 1, 2)
    p2 = _page("Market Cap > 100", ["DDD", "EEE"], 2, 2)
    saved_t = _stub_transport({base: p1, base + "?page=2": p2})
    saved_a = _isolate_cache()
    try:
        env = ss.screen(base, max_survivors=4, fresh=True)
    finally:
        transport.request = saved_t
        if saved_a is not None:
            os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = saved_a
    check("paging stops at max_survivors", env["data"]["count"] == 4, env["data"])
    check("page one and page two both contributed",
          env["data"]["candidates"] == ["AAA", "BBB", "CCC", "DDD"], env["data"]["candidates"])


def test_login_walled_screen_is_a_labelled_gap():
    url = "https://www.screener.in/screens/7/private/"
    body = '<html><body><form><input name="password" type="password"></form></body></html>'
    saved_t = _stub_transport({url: body})
    saved_a = _isolate_cache()
    try:
        env = ss.screen(url, fresh=True)
    finally:
        transport.request = saved_t
        if saved_a is not None:
            os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = saved_a
    check("a private screen is ok:false", env["ok"] is False)
    check("a private screen says it is login-walled, not empty",
          any("login-walled" in g for g in env["gaps"]), env["gaps"])


if __name__ == "__main__":
    run(globals())
