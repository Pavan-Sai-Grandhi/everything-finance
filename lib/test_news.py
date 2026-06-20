#!/usr/bin/env python3
"""Offline unit tests for lib/news.py (the data-spine news fetcher).

Deterministic, no network — the parsers, classifier, dedup and the ladder's degradation
run against saved response fixtures, mirroring test_prices.py / test_filings.py / test_ta.py.
Each test names the section-B acceptance criterion it proves. Run:
    python3 lib/test_news.py   # exits 0
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import news  # noqa: E402

_passed = 0
_failed = 0


def check(name, cond, extra=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name} {extra}")


# --- saved fixture: a Google News RSS search response ----------------------- #
RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Reliance - Google News</title>
  <item>
    <title>Reliance Industries Q4 net profit rises 12% YoY - Economic Times</title>
    <link>https://news.google.com/articles/aaa</link>
    <pubDate>Fri, 19 Jun 2026 10:30:00 GMT</pubDate>
    <source url="https://economictimes.indiatimes.com">Economic Times</source>
  </item>
  <item>
    <title>Brokerage raises Reliance target price to 3200, maintains Buy - Moneycontrol</title>
    <link>https://news.google.com/articles/bbb</link>
    <pubDate>Thu, 18 Jun 2026 06:00:00 GMT</pubDate>
    <source url="https://moneycontrol.com">Moneycontrol</source>
  </item>
  <item>
    <title>10 stocks to watch in today's session - Mint</title>
    <link>https://news.google.com/articles/ccc</link>
    <pubDate>Thu, 18 Jun 2026 04:00:00 GMT</pubDate>
    <source url="https://livemint.com">Mint</source>
  </item>
  <item>
    <title>Banking sector outlook brightens on rate-cut hopes - Business Standard</title>
    <link>https://news.google.com/articles/ddd</link>
    <pubDate>Wed, 17 Jun 2026 09:00:00 GMT</pubDate>
    <source url="https://business-standard.com">Business Standard</source>
  </item>
  <item>
    <title>Reliance Industries Q4 net profit rises 12% YoY - The Hindu</title>
    <link>https://news.google.com/articles/eee</link>
    <pubDate>Fri, 19 Jun 2026 11:00:00 GMT</pubDate>
    <source url="https://thehindu.com">The Hindu</source>
  </item>
</channel></rss>"""

# --- saved fixture: an Economic Times topic-page HTML snippet --------------- #
ET_HTML_FIXTURE = """
<div class="topicList">
  <a href="/markets/stocks/news/reliance-bags-large-order-from-defence-ministry/123.cms">
     Reliance bags large order from defence ministry</a>
  <a href="/login">Sign In</a>
  <a href="/markets/stocks/news/reliance-launches-new-energy-arm/124.cms">
     Reliance launches new energy arm</a>
</div>
"""

# A frozen "today" so the recency window is deterministic across runs.
TODAY = news.date(2026, 6, 20)


# --- B1: fetch walks the ladder and returns the envelope with data.items ---- #
def test_B1_fetch_walks_ladder_returns_items(monkeypatched=None):
    # ET blocks, Moneycontrol blocks, Google RSS answers — the ladder degrades through.
    orig = (news._fetch_et, news._fetch_moneycontrol, news._fetch_google_rss)
    news._fetch_et = lambda c, t, d: ([], "HTTP 403")
    news._fetch_moneycontrol = lambda c, t, d: ([], "fetch failed: blocked")
    news._fetch_google_rss = lambda c, t, d: (news._parse_rss(RSS_FIXTURE, "Google News RSS"), None)
    try:
        env = news.fetch("Reliance Industries", ticker="RELIANCE", days=60, fresh=True)
    finally:
        news._fetch_et, news._fetch_moneycontrol, news._fetch_google_rss = orig
    check("B1 envelope has the data-spine keys",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"})
    check("B1 data carries items", isinstance(env["data"].get("items"), list))
    check("B1 source is the rung that answered", env["source"] == "Google News RSS")
    check("B1 ok:true when items returned", env["ok"] is True)


# --- B2: items are dated, deduped, classified, tagged; noise filtered ------- #
def test_B2_items_dated():
    items = news._process(news._parse_rss(RSS_FIXTURE, "Google News RSS"),
                          "Reliance Industries", "RELIANCE", 60, today=TODAY)
    check("B2 every item is dated (ISO or explicit None)",
          all(it["date"] is None or it["date"][:4].isdigit() for it in items))
    check("B2 RFC-822 pubDate parsed to ISO", any(it["date"] == "2026-06-19" for it in items))


def test_B2_items_classified():
    check("B2 company headline -> company",
          news._classify("Reliance Industries Q4 net profit rises 12%", "Reliance Industries",
                         "RELIANCE") == "company")
    check("B2 sector headline -> sector",
          news._classify("Banking sector outlook brightens on rate-cut hopes",
                         "Reliance Industries", "RELIANCE") == "sector")
    check("B2 listicle -> noise",
          news._classify("10 stocks to watch in today's session", "Reliance Industries",
                         "RELIANCE") == "noise")
    check("B2 ticker mention -> company",
          news._classify("RELIANCE hits record high", "Reliance Industries", "RELIANCE")
          == "company")


def test_B2_items_tagged():
    check("B2 reported event -> fact",
          news._tag("Reliance bags large order from defence ministry") == "fact")
    check("B2 broker target -> narrative",
          news._tag("Brokerage raises Reliance target price to 3200, maintains Buy")
          == "narrative")


def test_B2_items_deduped():
    raw = news._parse_rss(RSS_FIXTURE, "Google News RSS")
    items = news._process(raw, "Reliance Industries", "RELIANCE", 60, today=TODAY)
    titles = [it["title"] for it in items]
    check("B2 same story across wires collapses to one",
          titles.count("Reliance Industries Q4 net profit rises 12% YoY") == 1)


def test_B2_each_item_has_source():
    items = news._process(news._parse_rss(RSS_FIXTURE, "Google News RSS"),
                          "Reliance Industries", "RELIANCE", 60, today=TODAY)
    check("B2 every item carries a source", all(it.get("source") for it in items))
    check("B2 Google-News publisher recovered from title",
          any(it["source"] == "Economic Times" for it in items))


def test_B2_noise_filtered_from_default_view():
    orig = (news._fetch_et, news._fetch_moneycontrol, news._fetch_google_rss)
    news._fetch_et = lambda c, t, d: (news._parse_rss(RSS_FIXTURE, "Economic Times"), None)
    news._fetch_moneycontrol = news._fetch_google_rss = lambda c, t, d: ([], "skipped")
    try:
        env = news.fetch("Reliance Industries", ticker="RELIANCE", days=3650, fresh=True)
        env_noise = news.fetch("Reliance Industries", ticker="RELIANCE", days=3650,
                               fresh=True, include_noise=True)
    finally:
        news._fetch_et, news._fetch_moneycontrol, news._fetch_google_rss = orig
    check("B2 no noise item in the default view",
          all(it["kind"] != "noise" for it in env["data"]["items"]))
    check("B2 noise_filtered counts what was hidden", env["data"]["noise_filtered"] >= 1)
    check("B2 include_noise surfaces the noise item",
          any(it["kind"] == "noise" for it in env_noise["data"]["items"]))


def test_B2_recency_window_drops_stale():
    raw = [{"title": "Reliance ancient news", "url": "", "date": "2024-01-01",
            "source": "X", "origin": "X"},
           {"title": "Reliance fresh news", "url": "", "date": "2026-06-19",
            "source": "X", "origin": "X"}]
    items = news._process(raw, "Reliance Industries", "RELIANCE", 60, today=TODAY)
    titles = [it["title"] for it in items]
    check("B2 stale item dropped from window", "Reliance ancient news" not in titles)
    check("B2 fresh item kept", "Reliance fresh news" in titles)


# --- B3: degradation — blocked rung records a gap; all-blocked -> ok:false --- #
def test_B3_single_block_degrades_with_gap():
    orig = (news._fetch_et, news._fetch_moneycontrol, news._fetch_google_rss)
    news._fetch_et = lambda c, t, d: ([], "HTTP 403")
    news._fetch_moneycontrol = lambda c, t, d: (news._parse_anchor_list(ET_HTML_FIXTURE,
                                                                        "Moneycontrol"), None)
    news._fetch_google_rss = lambda c, t, d: ([], "unused")
    try:
        env = news.fetch("Reliance Industries", ticker="RELIANCE", days=3650, fresh=True)
    finally:
        news._fetch_et, news._fetch_moneycontrol, news._fetch_google_rss = orig
    check("B3 blocked rung recorded as a labelled gap",
          any("Economic Times" in g for g in env["gaps"]))
    check("B3 walk fell through to the next rung", env["source"] == "Moneycontrol")
    check("B3 ok:true once a later rung answered", env["ok"] is True)


def test_B3_all_blocked_returns_ok_false_with_gap():
    orig = (news._fetch_et, news._fetch_moneycontrol, news._fetch_google_rss)
    news._fetch_et = lambda c, t, d: ([], "HTTP 403")
    news._fetch_moneycontrol = lambda c, t, d: ([], "fetch failed: Akamai 403")
    news._fetch_google_rss = lambda c, t, d: ([], "no RSS items returned")
    try:
        env = news.fetch("Nonexistent Co", ticker="ZZZZ", days=60, fresh=True)
    finally:
        news._fetch_et, news._fetch_moneycontrol, news._fetch_google_rss = orig
    check("B3 all-blocked run returns ok:false", env["ok"] is False)
    check("B3 all-blocked run still carries a gap", len(env["gaps"]) >= 1)
    check("B3 never an empty crash — envelope shape intact",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"})
    check("B3 data.items present (empty list, not missing)", env["data"]["items"] == [])


# --- parser fixtures: RSS + HTML anchor list (feeds B1/B2 inputs) ----------- #
def test_parse_rss_fixture():
    items = news._parse_rss(RSS_FIXTURE, "Google News RSS")
    check("rss parser emits one raw item per <item>", len(items) == 5)
    check("rss parser strips ' - Publisher' off the title",
          items[0]["title"] == "Reliance Industries Q4 net profit rises 12% YoY")
    check("rss parser recovers the link", items[0]["url"].endswith("/aaa"))
    check("rss parser tolerates malformed xml", news._parse_rss("<not xml", "x") == [])


def test_parse_anchor_list_fixture():
    items = news._parse_anchor_list(ET_HTML_FIXTURE, "Economic Times",
                                    "https://economictimes.indiatimes.com")
    titles = [it["title"] for it in items]
    check("anchor parser keeps headlines",
          "Reliance bags large order from defence ministry" in titles)
    check("anchor parser drops short nav links", "Sign In" not in titles)
    check("anchor parser makes absolute urls",
          all(it["url"].startswith("http") for it in items))


def test_envelope_shape():
    env = news._envelope(True, "Google News RSS", {"items": []}, [])
    check("envelope has the contract keys",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"})


# --- B4 is this file passing: every test above runs offline on fixtures ----- #
def main():
    for fn in (test_B1_fetch_walks_ladder_returns_items,
               test_B2_items_dated, test_B2_items_classified, test_B2_items_tagged,
               test_B2_items_deduped, test_B2_each_item_has_source,
               test_B2_noise_filtered_from_default_view, test_B2_recency_window_drops_stale,
               test_B3_single_block_degrades_with_gap,
               test_B3_all_blocked_returns_ok_false_with_gap,
               test_parse_rss_fixture, test_parse_anchor_list_fixture, test_envelope_shape):
        fn()
    print(f"\n{'=' * 48}\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
