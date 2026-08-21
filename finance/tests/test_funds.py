#!/usr/bin/env python3
"""Offline unit tests for finance/sources/funds.py (the mutual-fund data-spine fetcher).

Deterministic, no network — every rung runs against saved response fixtures with the
shared transport and Tickertape seams swapped out, mirroring test_prices.py /
test_fundamentals.py / test_market.py. Artifact roots are temp dirs, so a run never touches the user's real
./artifacts. Run:
    python3 finance/tests/test_funds.py
"""
import atexit
import contextlib
import json
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Point the path authority at a throwaway root BEFORE anything can write a cache file.
_TMP_ROOT = tempfile.mkdtemp(prefix="ef-test-funds-")
os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = os.path.join(_TMP_ROOT, "artifacts")
atexit.register(shutil.rmtree, _TMP_ROOT, True)

from finance import caps
from finance import spine
from finance import transport  # noqa: E402
from finance.sources import funds  # noqa: E402
from finance.sources import tickertape  # noqa: E402
from finance.tests.harness import check, run  # noqa: E402


@contextlib.contextmanager
def swap(module, attr, fake):
    """Temporarily replace a module attribute (the offline seam)."""
    orig = getattr(module, attr)
    setattr(module, attr, fake)
    try:
        yield
    finally:
        setattr(module, attr, orig)


def fresh_root(tag):
    """Give the next test its own empty artifacts root so caches never leak between tests."""
    os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = os.path.join(_TMP_ROOT, tag)


def envelope_keys(env):
    return set(env) == {"ok", "source", "fetched_at", "data", "gaps"}


# --------------------------------------------------------------------------- #
# saved fixtures                                                               #
# --------------------------------------------------------------------------- #

# AMFI NAVAll.txt — headers, blank lines, scheme-type banners and AMC names all share the
# file with the data rows, so the parser has to be picky about what a row is.
AMFI_NAVALL = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Small Cap Fund)

Nippon India Mutual Fund

118778;INF204K01XB8;INF204K01XC6;Nippon India Small Cap Fund - Direct Plan - Growth Option;198.4562;16-Aug-2026
118779;-;-;Nippon India Small Cap Fund - IDCW Option;45.1234;16-Aug-2026
notacode;INF204K01XD4;INF204K01XE2;Bogus Non-Numeric Code Row;1.0000;16-Aug-2026
120503;INF209KA12Z1;Truncated Row With Too Few Fields
;;;Empty Code Row;1.0;16-Aug-2026

PPFAS Mutual Fund

122639;INF879O01027;INF879O01019;Parag Parikh Flexi Cap Fund - Direct Plan - Growth;89.1200;16-Aug-2026
"""

# Tickertape mf-screener/query — three funds across two sub-categories and two options.
SCREEN_BLOB = {
    "data": {"result": [
        {"mfId": "M_ALPHA", "name": "Alpha Small Cap Fund - Direct Growth", "slug": "alpha-sc",
         "sector": "Equity", "values": [
             {"filter": "aum", "doubleVal": 1000.0},
             {"filter": "subsector", "strVal": "Small Cap Fund"},
             {"filter": "option", "strVal": "Growth"},
             {"filter": "expRatio", "doubleVal": 0.72}]},
        {"mfId": "M_BETA", "name": "Beta Small Cap Fund - Direct IDCW", "slug": "beta-sc",
         "sector": "Equity", "values": [
             {"filter": "aum", "doubleVal": 5000.0},
             {"filter": "subsector", "strVal": "Small Cap Fund"},
             {"filter": "option", "strVal": "IDCW"},
             {"filter": "expRatio", "doubleVal": 0.81}]},
        {"mfId": "M_GAMMA", "name": "Gamma Flexi Cap Fund - Direct Growth", "slug": "gamma-fc",
         "sector": "Equity", "values": [
             {"filter": "aum", "doubleVal": 9000.0},
             {"filter": "subsector", "strVal": "Flexi Cap Fund"},
             {"filter": "option", "strVal": "Growth"},
             {"filter": "expRatio", "doubleVal": 0.55}]},
        {"mfId": "M_DELTA", "name": "Delta Small Cap Fund - Direct Growth", "slug": "delta-sc",
         "sector": "Equity", "values": [
             {"filter": "aum", "doubleVal": 7500.0},
             {"filter": "subsector", "strVal": "Small Cap Fund"},
             {"filter": "option", "strVal": "Growth"},
             {"filter": "expRatio", "doubleVal": 0.64}]},
    ]}
}

# Tickertape mutualfunds/<mfId>/holdings — the COMPLETE allocation, equity + debt + cash,
# with one weightless row that must be dropped rather than counted as 0.
HOLDINGS_BLOB = {
    "data": {
        "currentAllocation": [
            {"sid": "RELI", "ticker": "RELIANCE", "title": "Reliance Industries",
             "latest": 8.5, "change3m": 0.4, "type": "equity"},
            {"sid": "TCS", "ticker": "TCS", "title": "Tata Consultancy Services",
             "latest": 6.25, "change3m": -0.9, "type": "equity"},
            {"sid": "RECM", "ticker": "RECLTD", "title": "REC Ltd",
             "latest": 3.0, "change3m": 0.1, "type": "equity"},
            {"sid": "UNLI", "ticker": None, "title": "Unlisted Holdco Pvt Ltd",
             "latest": 2.25, "change3m": None, "type": "equity"},
            {"sid": "GSEC", "ticker": None, "title": "7.26% GOI 2033",
             "latest": 4.0, "change3m": 0.0, "type": "debt"},
            {"sid": "CASH", "ticker": None, "title": "Net Receivables / Cash",
             "latest": None, "change3m": None, "type": "cash"},
        ],
        "sectorWeightage": [
            {"name": "Financials", "latest": 24.6},
            {"name": "Technology", "latest": 12.1},
            {"name": "Unweighted Sector", "latest": None},
            "not a dict",
        ],
        "assetAllocationHistory": [{"date": "2026-07-31", "equity": 95.1}],
    }
}

# Same shape, but a cash-heavy book that must trip the low-equity gap.
HYBRID_HOLDINGS_BLOB = {
    "data": {"currentAllocation": [
        {"sid": "RELI", "ticker": "RELIANCE", "title": "Reliance Industries",
         "latest": 30.0, "type": "equity"},
        {"sid": "TCS", "ticker": "TCS", "title": "TCS", "latest": 15.0, "type": "equity"},
        {"sid": "GSEC", "ticker": None, "title": "7.26% GOI 2033", "latest": 55.0, "type": "debt"},
    ]}
}

# Tickertape stocks/info/<sid> — note sid RECM vs ticker RECLTD, the join-key trap.
STOCK_INFO_BLOB = {
    "data": {
        "info": {"ticker": "RECLTD", "name": "REC Ltd", "sector": "Financials",
                 "isin": "INE020B01018"},
        "ratios": {"pe": 8.4, "ttmPe": 8.1, "pb": 1.6, "roe": 21.5, "eps": 62.3,
                   "marketCap": 132000.0, "marketCapLabel": "Midcap",
                   "divYield": 3.9, "beta": 1.4, "indpe": 14.2, "indpb": 2.1},
    }
}

# amfiindia.com/otherdata/categorisation-of-stocks — the live page lists every past
# edition next to the current one, in both an <a href> and an escaped JSON blob, and the
# newest is not last.
CAP_INDEX_HTML = """<html><body>
<a href="https://www.amfiindia.com/Themes/Theme1/downloads/AverageMarketCapitalization31Dec2025.xlsx">Dec 2025</a>
<a href="https://portal.amfiindia.com/spages/AverageMarketCapitalization30Jun2026.xlsx">Jun 2026</a>
<a href="https://portal.amfiindia.com/spages/AverageMarketCapitalization30Jun2026.pdf">PDF</a>
<a href="https://www.amfiindia.com/Themes/Theme1/downloads/AverageMarketCapitalizationoflistedcompaniesduringthesixmonthsended30June2022.xlsx">Jun 2022</a>
<script>{\\"excelUrl\\":\\"https://portal.amfiindia.com/spages/AverageMarketCapitalization30Jun2026.xlsx\\"}</script>
</body></html>"""

CAP_XLSX_URL = "https://portal.amfiindia.com/spages/AverageMarketCapitalization30Jun2026.xlsx"

# The workbook's own layout: a title row above the header, `Sr. No.` as the SEBI rank, a
# "-" NSE symbol for the BSE-only listings that make the ISIN key load-bearing.
CAP_XLSX_ROWS = [
    ("Average Market Capitalization of listed companies during the six months ended "
     "30 June 2026", None, None, None, None, None, None, None, None, None, None),
    ("Sr. No.", "Company name", "ISIN", "BSE Symbol",
     "BSE 6 month Avg Total Market Cap in (Rs. Crs.)", "NSE Symbol",
     "NSE 6 month Avg Total Market Cap (Rs. Crs.)", "MSEI Symbol",
     "MSEI 6 month Avg Total Market Cap in (Rs Crs.)", "Average of All Exchanges (Rs. Cr.)",
     "Categorization as per SEBI Circular dated Oct 6, 2017"),
    (1, "Reliance Industries Ltd", "INE002A01018", "RELIANCE", 1873294.7, "RELIANCE",
     1873278.8, "-", None, 1873286.8, "Large Cap"),
    (100, "Gail (India) Ltd.", "INE129A01019", "GAIL", 106346.2, "GAIL", 106346.1,
     "-", None, 106346.15, "Large Cap"),
    (101, "Bosch Ltd", "INE323A01026", "BOSCHLTD", 106278.2, "BOSCHLTD", 106278.2,
     "-", None, 106278.2, "Mid Cap"),
    (117, "REC Ltd", "INE020B01018", "RECLTD", 92824.2, "RECLTD", 92824.2,
     "-", None, 92824.2, "Mid Cap"),
    (250, "Godrej Industries Ltd.", "INE233A01035", "GODREJIND", 33664.2, "GODREJIND",
     33664.2, "-", None, 33664.2, "Mid Cap"),
    (251, "Navin Fluorine International Limited", "INE048G01026", "NAVINFLUOR", 33441.9,
     "NAVINFLUOR", 33441.9, "-", None, 33441.9, "Small Cap"),
    (5427, "Bengal Steel Industries Ltd.", "INE523W01017", "BENGALS", 0.0245, "-",
     None, "-", None, 0.0245, "Small Cap"),
]


def cap_xlsx_fixture():
    """Write CAP_XLSX_ROWS to a real workbook — the parser reads openpyxl, not a list."""
    openpyxl = __import__("openpyxl")
    book = openpyxl.Workbook()
    for row in CAP_XLSX_ROWS:
        book.active.append(row)
    path = os.path.join(_TMP_ROOT, "cap-fixture.xlsx")
    book.save(path)
    return path


CAP_XLSX_PATH = cap_xlsx_fixture()


@contextlib.contextmanager
def cap_index(stocks=None, period="2026-06-30", gaps=()):
    """Pin the process-wide cap-list memo, so no test reaches AMFI for a rank."""
    stocks = {} if stocks is None else stocks
    by_isin = {r["isin"]: r for r in stocks.values() if r.get("isin")}
    orig = funds._cap_index_memo
    funds._cap_index_memo = (stocks, by_isin, period, list(gaps))
    try:
        yield
    finally:
        funds._cap_index_memo = orig


@contextlib.contextmanager
def cap_index_cold():
    """Clear the memo so a test exercises the real fetch-and-parse path."""
    orig = funds._cap_index_memo
    funds._cap_index_memo = None
    try:
        yield
    finally:
        funds._cap_index_memo = orig


def cap_stocks():
    """The parsed fixture map, keyed as funds.amfi_cap_list keys it."""
    stocks, gap = funds._parse_cap_xlsx(CAP_XLSX_PATH)
    assert not gap, gap
    return stocks


def serve_cap(index_html=CAP_INDEX_HTML, xlsx=CAP_XLSX_PATH, calls=None):
    """A `transport.request` stand-in serving the index page, then the fixture to `dest`."""
    def fake(url, payload=None, timeout=30, referer=None, dest=None):
        if calls is not None:
            calls.append(url)
        if dest is None:
            return index_html, None
        shutil.copyfile(xlsx, dest)
        return dest, None
    return fake

# mfapi.in /mf/<code> — newest first, DD-MM-YYYY, with two rows that must be skipped.
NAV_BLOB = {
    "meta": {"scheme_name": "Nippon India Small Cap Fund - Direct Plan - Growth Option",
             "scheme_code": 118778},
    "data": [
        {"date": "16-08-2026", "nav": "198.45620"},
        {"date": "15-08-2026", "nav": "197.10000"},
        {"date": "not-a-date", "nav": "1.0"},
        {"date": "14-08-2026", "nav": "unparseable"},
        {"date": "13-08-2026", "nav": "195.00000"},
    ],
}


# --------------------------------------------------------------------------- #
# pure: name scoring                                                           #
# --------------------------------------------------------------------------- #
DIRECT_GROWTH = "Nippon India Small Cap Fund - Direct Plan - Growth Option"
REGULAR_GROWTH = "Nippon India Small Cap Fund - Growth Option"
DIRECT_IDCW = "Nippon India Small Cap Fund - Direct Plan - IDCW Option"


def test_score_name_requires_every_query_token():
    q = "nippon india small cap"
    check("a name missing a query token scores -1",
          funds._score_name(q, "SBI Small Cap Fund - Direct Plan - Growth") == -1,
          funds._score_name(q, "SBI Small Cap Fund - Direct Plan - Growth"))
    check("a name carrying every query token scores positive",
          funds._score_name(q, DIRECT_GROWTH) > 0, funds._score_name(q, DIRECT_GROWTH))
    check("one missing token is enough to reject, however close the rest",
          funds._score_name("nippon india small cap zzz", DIRECT_GROWTH) == -1)
    check("scoring is case-insensitive",
          funds._score_name("NIPPON INDIA SMALL CAP", DIRECT_GROWTH) ==
          funds._score_name("nippon india small cap", DIRECT_GROWTH))
    check("a hyphenated query is split into tokens",
          funds._score_name("parag-parikh flexi cap",
                            "Parag Parikh Flexi Cap Fund - Direct Plan - Growth") > 0)
    check("an empty query matches anything (no token can be missing)",
          funds._score_name("", DIRECT_GROWTH) > 0)


def test_score_name_prefers_direct_growth():
    q = "nippon india small cap"
    check("Direct beats Regular for the same fund",
          funds._score_name(q, DIRECT_GROWTH) > funds._score_name(q, REGULAR_GROWTH),
          (funds._score_name(q, DIRECT_GROWTH), funds._score_name(q, REGULAR_GROWTH)))
    check("Growth beats IDCW for the same plan",
          funds._score_name(q, DIRECT_GROWTH) > funds._score_name(q, DIRECT_IDCW),
          (funds._score_name(q, DIRECT_GROWTH), funds._score_name(q, DIRECT_IDCW)))
    check("Direct+Growth is the top-scoring variant of a fund",
          funds._score_name(q, DIRECT_GROWTH) == max(
              funds._score_name(q, n) for n in (DIRECT_GROWTH, REGULAR_GROWTH, DIRECT_IDCW)))


def test_score_name_penalises_payout_plans():
    q = "nippon india small cap"
    for word in ("IDCW", "Dividend", "Payout", "Bonus"):
        name = f"Nippon India Small Cap Fund - Direct Plan - {word} Option"
        base = f"Nippon India Small Cap Fund - Direct Plan - {'x' * len(word)} Option"
        check(f"a {word} plan is penalised against an equal-length neutral name",
              funds._score_name(q, name) < funds._score_name(q, base),
              (funds._score_name(q, name), funds._score_name(q, base)))


def test_score_name_prefers_the_tighter_name():
    check("a name closer in length to the query scores higher",
          funds._score_name("small cap fund", "Small Cap Fund") >
          funds._score_name("small cap fund",
                            "Small Cap Fund Of A Very Long Winded Asset Manager Series II"))


# --------------------------------------------------------------------------- #
# rung 1 — amfi_index() line parser                                            #
# --------------------------------------------------------------------------- #
def test_amfi_index_parses():
    fresh_root("amfi")
    with swap(transport, "request", lambda url, payload=None, timeout=30, referer=None:
              (AMFI_NAVALL, None)):
        env = funds.amfi_index(fresh=True)
    check("amfi_index returns the envelope", envelope_keys(env), sorted(env))
    check("amfi_index ok:true with schemes", env["ok"] is True)
    check("amfi_index source is AMFI", env["source"] == "AMFI")
    schemes = env["data"]["schemes"]
    check("amfi_index keeps only real scheme rows", len(schemes) == 3, [s["code"] for s in schemes])
    check("amfi_index count matches the list", env["data"]["count"] == len(schemes))
    codes = [s["code"] for s in schemes]
    check("amfi_index skips the header row", "Scheme Code" not in codes, codes)
    check("amfi_index skips a non-numeric scheme code", "notacode" not in codes, codes)
    check("amfi_index skips a truncated row", "120503" not in codes, codes)
    check("amfi_index skips a blank-code row", "" not in codes, codes)
    first = schemes[0]
    check("amfi_index parses the scheme code", first["code"] == "118778", first)
    check("amfi_index parses the ISIN", first["isin"] == "INF204K01XB8", first)
    check("amfi_index parses the exact AMFI name", first["name"] == DIRECT_GROWTH, first)
    check("amfi_index parses the NAV as a float", first["nav"] == 198.4562, first)
    check("amfi_index keeps the NAV date", first["nav_date"] == "16-Aug-2026", first)
    check("amfi_index carries schemes from every AMC block in the file",
          "122639" in codes, codes)


def test_amfi_index_dash_isin_is_none():
    fresh_root("amfi-dash")
    with swap(transport, "request", lambda url, payload=None, timeout=30, referer=None:
              (AMFI_NAVALL, None)):
        env = funds.amfi_index(fresh=True)
    idcw = [s for s in env["data"]["schemes"] if s["code"] == "118779"][0]
    check("a '-' ISIN becomes None, not the literal dash", idcw["isin"] is None, idcw)
    check("a '-' ISIN row still keeps its code and name",
          idcw["code"] == "118779" and "IDCW" in idcw["name"], idcw)


def test_amfi_index_blocked_degrades():
    fresh_root("amfi-blocked")
    with swap(transport, "request", lambda url, payload=None, timeout=30, referer=None:
              (None, "curl exit 6 for portal.amfiindia.com")):
        env = funds.amfi_index(fresh=True)
    check("amfi_index blocked returns ok:false", env["ok"] is False)
    check("amfi_index blocked still has the envelope shape", envelope_keys(env))
    check("amfi_index blocked carries a labelled gap",
          env["gaps"] and env["gaps"][0].startswith("AMFI NAVAll:"), env["gaps"])
    check("amfi_index blocked returns an empty scheme list", env["data"]["schemes"] == [])


def test_amfi_index_unparseable_body_degrades():
    fresh_root("amfi-junk")
    with swap(transport, "request", lambda url, payload=None, timeout=30, referer=None:
              ("<html>login wall</html>", None)):
        env = funds.amfi_index(fresh=True)
    check("amfi_index with no parseable rows is ok:false", env["ok"] is False)
    check("amfi_index with no parseable rows names the gap",
          env["gaps"] == ["AMFI NAVAll returned no parseable scheme rows"], env["gaps"])


# --------------------------------------------------------------------------- #
# rung 1a — amfi_cap_list(): the SEBI cap rank                                 #
# --------------------------------------------------------------------------- #
def test_cap_label_boundaries():
    check("rank 1 is large", caps.cap_label(1) == "Large Cap")
    check("rank 100 is the LAST large cap", caps.cap_label(100) == "Large Cap")
    check("rank 101 is the FIRST mid cap", caps.cap_label(101) == "Mid Cap")
    check("rank 250 is the LAST mid cap", caps.cap_label(250) == "Mid Cap")
    check("rank 251 is the FIRST small cap", caps.cap_label(251) == "Small Cap")
    check("a deep-tail rank is small", caps.cap_label(5427) == "Small Cap")
    check("no rank is no label", caps.cap_label(None) is None)
    check("a non-positive rank is not a classification", caps.cap_label(0) is None)


def test_cap_link_discovery_takes_the_newest_period():
    url, period, gap = funds._cap_xlsx_link(CAP_INDEX_HTML)
    check("link discovery raises no gap on a normal page", gap is None, gap)
    check("discovery picks the newest edition, not the first listed",
          url == CAP_XLSX_URL, url)
    check("discovery ignores the PDF beside it", url.endswith(".xlsx"), url)
    check("the period is parsed off the filename", period == "2026-06-30", period)


def test_cap_link_discovery_handles_a_root_relative_href():
    url, period, gap = funds._cap_xlsx_link(
        '<a href="/downloads/AverageMarketCapitalization31Dec2026.xlsx">latest</a>')
    check("a root-relative href is resolved against the AMFI host",
          url == "https://www.amfiindia.com/downloads/"
                 "AverageMarketCapitalization31Dec2026.xlsx", url)
    check("the later period wins even from a relative link", period == "2026-12-31", period)
    check("a relative href is not a gap", gap is None, gap)


def test_cap_link_discovery_no_match_is_a_gap():
    url, period, gap = funds._cap_xlsx_link("<html><body>no downloads here</body></html>")
    check("a page with no matching link returns no url", url is None and period is None)
    check("a page with no matching link is a labelled gap, not an exception",
          gap is not None and "no dated" in gap, gap)
    undated = funds._cap_xlsx_link(
        '<a href="/d/AverageMarketCapitalizationLatest.xlsx">x</a>')
    check("an undated filename is refused rather than guessed at",
          undated[0] is None and undated[2] is not None, undated)
    check("no html at all degrades the same way", funds._cap_xlsx_link(None)[2] is not None)


def test_cap_xlsx_parse_keys_on_nse_symbol_then_isin():
    stocks = cap_stocks()
    check("the title row above the header does not become a stock", "Sr. No." not in stocks)
    check("every ranked row is present", len(stocks) == 7, sorted(stocks))
    check("Sr. No. IS the rank", stocks["RELIANCE"]["rank"] == 1, stocks["RELIANCE"])
    check("the NSE symbol is the key", stocks["RECLTD"]["rank"] == 117, stocks["RECLTD"])
    check("the row carries its ISIN for the fallback join",
          stocks["RECLTD"]["isin"] == "INE020B01018", stocks["RECLTD"])
    check("the company name travels with the rank",
          stocks["RECLTD"]["name"] == "REC Ltd", stocks["RECLTD"])
    check("the all-exchange average is the ₹Cr column read",
          stocks["RECLTD"]["avg_mcap_cr"] == 92824.2, stocks["RECLTD"])
    check("a BSE-only row falls back to its ISIN as the key",
          stocks["INE523W01017"]["rank"] == 5427, sorted(stocks))
    check("a '-' NSE symbol is absent, never stored as a symbol",
          stocks["INE523W01017"]["symbol"] is None, stocks["INE523W01017"])
    check("the boundary ranks survive the parse",
          (stocks["GAIL"]["rank"], stocks["BOSCHLTD"]["rank"],
           stocks["GODREJIND"]["rank"], stocks["NAVINFLUOR"]["rank"]) == (100, 101, 250, 251),
          stocks)


def test_cap_xlsx_parse_without_a_header_is_a_gap():
    openpyxl = __import__("openpyxl")
    book = openpyxl.Workbook()
    book.active.append(("Company", "Rank"))
    path = os.path.join(_TMP_ROOT, "cap-headerless.xlsx")
    book.save(path)
    stocks, gap = funds._parse_cap_xlsx(path)
    check("a workbook with no Sr. No. header yields nothing", stocks == {}, stocks)
    check("an unrecognised layout is a labelled gap",
          gap is not None and "header row" in gap, gap)
    missing, gap = funds._parse_cap_xlsx(os.path.join(_TMP_ROOT, "not-there.xlsx"))
    check("an unreadable workbook degrades rather than raising",
          missing == {} and gap is not None and "unreadable" in gap, gap)


def test_amfi_cap_list_end_to_end():
    fresh_root("cap-list")
    calls = []
    with cap_index_cold(), swap(transport, "request", serve_cap(calls=calls)):
        env = funds.amfi_cap_list(fresh=True)
    check("amfi_cap_list returns the envelope", envelope_keys(env), sorted(env))
    check("amfi_cap_list ok:true with rows", env["ok"] is True)
    check("the source is AMFI, the publisher of record", env["source"] == "AMFI")
    d = env["data"]
    check("the resolved workbook url travels with the data", d["url"] == CAP_XLSX_URL, d["url"])
    check("the period the classification covers is reported", d["period"] == "2026-06-30", d)
    check("the row count matches the parsed map", d["count"] == len(d["stocks"]) == 7, d["count"])
    check("discovery then download is exactly two fetches", len(calls) == 2, calls)
    check("the index page is fetched before the workbook",
          calls[0] == funds._AMFI_CAP_INDEX and calls[1] == CAP_XLSX_URL, calls)

    def explode(*a, **k):
        raise AssertionError("cap list re-fetched despite a warm cache")

    with cap_index_cold(), swap(transport, "request", explode):
        again = funds.amfi_cap_list()
    check("the parsed map is served from the long-TTL cache",
          again["data"]["count"] == 7, again["data"]["count"])
    check("the cap list is cached far longer than the weekly scheme list",
          funds._CAP_LIST_MAX_AGE_DAYS > 7, funds._CAP_LIST_MAX_AGE_DAYS)


def test_cap_index_is_memoised_for_the_process():
    fresh_root("cap-memo")
    calls = []
    with cap_index_cold(), swap(transport, "request", serve_cap(calls=calls)):
        first, second = funds._cap_index(), funds._cap_index()
        check("the second read reuses the built map rather than reloading the cache",
              first[0] is second[0])
        check("a second read costs no extra fetch", len(calls) == 2, calls)
        check("the ISIN index is derived once alongside the symbol map",
              second[1]["INE020B01018"]["rank"] == 117, second[1].get("INE020B01018"))
        check("the memo carries the period the gaps quote", second[2] == "2026-06-30",
              second[2])


def test_amfi_cap_list_degrades_at_every_step():
    fresh_root("cap-list-blocked")
    with cap_index_cold(), swap(transport, "request", lambda *a, **k: (None, "HTTP 503")):
        env = funds.amfi_cap_list(fresh=True)
    check("a blocked index page is ok:false", env["ok"] is False)
    check("a blocked index page keeps the envelope shape", envelope_keys(env))
    check("a blocked index page names the gap",
          any("cap-list index" in g for g in env["gaps"]), env["gaps"])
    check("a blocked index page returns an empty map", env["data"]["stocks"] == {})

    fresh_root("cap-list-nolink")
    with cap_index_cold(), swap(transport, "request", serve_cap(index_html="<html></html>")):
        env = funds.amfi_cap_list(fresh=True)
    check("an index page with no link is a gap, not an abort", env["ok"] is False)
    check("the no-link gap names what was looked for",
          any("AverageMarketCapitalization" in g for g in env["gaps"]), env["gaps"])

    fresh_root("cap-list-nofile")

    def index_ok_download_blocked(url, payload=None, timeout=30, referer=None, dest=None):
        return (CAP_INDEX_HTML, None) if dest is None else (None, "HTTP 404")

    with cap_index_cold(), swap(transport, "request", index_ok_download_blocked):
        env = funds.amfi_cap_list(fresh=True)
    check("a blocked workbook download is a gap", env["ok"] is False)
    check("a blocked download still reports the period it was after",
          env["data"]["period"] == "2026-06-30", env["data"])
    check("the download gap names the workbook",
          any("cap workbook" in g for g in env["gaps"]), env["gaps"])


# --------------------------------------------------------------------------- #
# rung 1b — resolve()                                                          #
# --------------------------------------------------------------------------- #
def _amfi_env(names):
    schemes = [{"code": str(100000 + i), "isin": f"INF{i:09d}", "name": n,
                "nav": 10.0, "nav_date": "16-Aug-2026"} for i, n in enumerate(names)]
    return funds._envelope(True, "AMFI", {"schemes": schemes, "count": len(schemes)}, [])


def test_resolve_prefers_direct_growth():
    fresh_root("resolve")
    with swap(funds, "amfi_index", lambda fresh=False:
              _amfi_env([REGULAR_GROWTH, DIRECT_IDCW, DIRECT_GROWTH])), \
         swap(funds, "_tickertape_fund", lambda name:
              ({"mf_id": "M_NIMS", "name": "Nippon India Small Cap Fund"}, None)):
        env = funds.resolve("Nippon India Small Cap")
    check("resolve returns the envelope", envelope_keys(env), sorted(env))
    check("resolve ok:true when identified", env["ok"] is True)
    d = env["data"]
    check("resolve picks the Direct-Growth scheme", d["amfi_name"] == DIRECT_GROWTH, d)
    check("resolve labels the plan Direct", d["plan"] == "Direct", d)
    check("resolve carries the AMFI scheme code", d["scheme_code"] is not None, d)
    check("resolve carries the Tickertape mf_id", d["mf_id"] == "M_NIMS", d)
    check("resolve raises no Regular-plan gap for a Direct match",
          not any("Regular plan" in g for g in env["gaps"]), env["gaps"])


def test_resolve_regular_only_is_a_labelled_gap():
    fresh_root("resolve-regular")
    with swap(funds, "amfi_index", lambda fresh=False: _amfi_env([REGULAR_GROWTH])), \
         swap(funds, "_tickertape_fund", lambda name: (None, "no confident Tickertape match")):
        env = funds.resolve("Nippon India Small Cap")
    check("resolve still identifies a Regular-only fund", env["data"]["plan"] == "Regular")
    check("resolve warns that a Regular expense ratio overstates a Direct cost",
          any("Regular plan" in g for g in env["gaps"]), env["gaps"])
    check("a missing Tickertape match is a labelled gap, not a failure",
          env["ok"] is True and any("Tickertape" in g for g in env["gaps"]), env["gaps"])
    check("resolve leaves mf_id None when Tickertape has no match",
          env["data"]["mf_id"] is None)


def test_resolve_no_match_at_all():
    fresh_root("resolve-none")
    with swap(funds, "amfi_index", lambda fresh=False: _amfi_env([DIRECT_GROWTH])), \
         swap(funds, "_tickertape_fund", lambda name: (None, "no confident Tickertape match")):
        env = funds.resolve("Some Fund That Does Not Exist")
    check("resolve with no match is ok:false", env["ok"] is False)
    check("resolve with no match still has the envelope shape", envelope_keys(env))
    check("resolve with no match names the AMFI gap",
          any("no AMFI scheme matched" in g for g in env["gaps"]), env["gaps"])


# --------------------------------------------------------------------------- #
# rung 2 — screen()                                                            #
# --------------------------------------------------------------------------- #
def _screen_seam(blob, captured):
    def fake(url, payload=None, timeout=30):
        captured.append({"url": url, "payload": payload})
        return blob, None
    return fake


def test_screen_filters_subsector_and_option_client_side():
    fresh_root("screen")
    seen = []
    with swap(tickertape, "get_json", _screen_seam(SCREEN_BLOB, seen)):
        env = funds.screen(subsector="Small Cap Fund", option="Growth", fresh=True)
    check("screen returns the envelope", envelope_keys(env), sorted(env))
    check("screen ok:true with funds", env["ok"] is True)
    ids = [f["mf_id"] for f in env["data"]["funds"]]
    check("screen keeps only the requested sub-category",
          "M_GAMMA" not in ids, ids)
    check("screen keeps only the requested option (IDCW dropped)", "M_BETA" not in ids, ids)
    check("screen keeps the matching funds", set(ids) == {"M_DELTA", "M_ALPHA"}, ids)
    check("screen count matches the filtered list", env["data"]["count"] == 2, env["data"]["count"])
    check("screen echoes the filter it applied",
          (env["data"]["subsector"], env["data"]["option"]) == ("Small Cap Fund", "Growth"))
    # the string filters are applied HERE, never sent — the endpoint silently ignores them
    check("no string filter is pushed into the server-side match",
          seen[0]["payload"]["match"] == {"aum": {"g": 100.0}}, seen[0]["payload"]["match"])
    check("the numeric AUM floor IS pushed server-side",
          seen[0]["payload"]["match"]["aum"]["g"] == 100.0)
    check("subsector and option are projected so they can be filtered locally",
          {"subsector", "option"} <= set(seen[0]["payload"]["project"]),
          seen[0]["payload"]["project"])


def test_screen_sorts_by_aum_desc():
    fresh_root("screen-sort")
    with swap(tickertape, "get_json", _screen_seam(SCREEN_BLOB, [])):
        env = funds.screen(subsector="Small Cap Fund", option="Growth", fresh=True)
    aums = [f["aum"] for f in env["data"]["funds"]]
    check("screen sorts largest AUM first", aums == [7500.0, 1000.0], aums)
    check("screen flattens the values list onto the record",
          env["data"]["funds"][0]["expRatio"] == 0.64, env["data"]["funds"][0])
    check("screen keeps the identity fields",
          env["data"]["funds"][0]["slug"] == "delta-sc"
          and env["data"]["funds"][0]["name"].startswith("Delta"), env["data"]["funds"][0])


def test_screen_whole_universe_when_unfiltered():
    fresh_root("screen-all")
    with swap(tickertape, "get_json", _screen_seam(SCREEN_BLOB, [])):
        env = funds.screen(subsector=None, option=None, fresh=True)
    ids = [f["mf_id"] for f in env["data"]["funds"]]
    check("screen(subsector=None, option=None) returns the whole universe",
          len(ids) == 4, ids)
    check("the unfiltered universe is still AUM-sorted",
          ids == ["M_GAMMA", "M_DELTA", "M_BETA", "M_ALPHA"], ids)


def test_screen_strips_premium_fields():
    fresh_root("screen-premium")
    seen = []
    asked = ["aum", "subsector", "option", "maxDrawdown", "percTop10H", "ret3yVsCat"]
    with swap(tickertape, "get_json", _screen_seam(SCREEN_BLOB, seen)):
        env = funds.screen(subsector="Small Cap Fund", option="Growth",
                           fields=asked, fresh=True)
    project = seen[0]["payload"]["project"]
    check("no premium field reaches the request (one 403s the WHOLE query)",
          not (set(project) & funds.PREMIUM_FIELDS), project)
    check("the free fields survive the strip",
          set(project) == {"aum", "subsector", "option"}, project)
    check("the dropped premium fields are named in a labelled gap",
          any("maxDrawdown" in g and "percTop10H" in g and "ret3yVsCat" in g
              for g in env["gaps"]), env["gaps"])
    check("the strip is a gap, not a failure", env["ok"] is True, env["gaps"])
    check("PREMIUM_FIELDS and SCREEN_FIELDS never overlap",
          not (set(funds.SCREEN_FIELDS) & funds.PREMIUM_FIELDS),
          set(funds.SCREEN_FIELDS) & funds.PREMIUM_FIELDS)
    with swap(tickertape, "get_json", _screen_seam(SCREEN_BLOB, [])):
        clean = funds.screen(subsector="Small Cap Fund", option="Growth", fresh=True)
    check("the default field set raises no premium gap",
          not any("premium-gated" in g for g in clean["gaps"]), clean["gaps"])


def test_screen_403_is_a_labelled_gap():
    fresh_root("screen-403")
    refused = {"statusCode": 403, "message": "Premium fields: maxDrawdown"}
    with swap(tickertape, "get_json", _screen_seam(refused, [])):
        env = funds.screen(subsector="Small Cap Fund", fresh=True)
    check("a 403 from the screener returns ok:false", env["ok"] is False)
    check("a 403 still has the envelope shape", envelope_keys(env))
    check("a 403 names the refused fields in the gap",
          any("refused fields" in g for g in env["gaps"]), env["gaps"])


def test_screen_blocked_degrades():
    fresh_root("screen-blocked")
    with swap(tickertape, "get_json", lambda url, payload=None, timeout=30:
              (None, "non-JSON from api.tickertape.in")):
        env = funds.screen(subsector="Small Cap Fund", fresh=True)
    check("screen blocked returns ok:false", env["ok"] is False)
    check("screen blocked still has the envelope shape", envelope_keys(env))
    check("screen blocked carries a labelled gap naming the page",
          any(g.startswith("Tickertape screener page 0:") for g in env["gaps"]), env["gaps"])
    check("screen blocked returns no funds", env["data"]["funds"] == [])


def test_screen_no_match_is_a_labelled_gap():
    fresh_root("screen-nomatch")
    with swap(tickertape, "get_json", _screen_seam(SCREEN_BLOB, [])):
        env = funds.screen(subsector="Banking & PSU Fund", option="Growth", fresh=True)
    check("a sub-category with no members is ok:false", env["ok"] is False)
    check("a sub-category with no members names the gap",
          any("no funds matched" in g for g in env["gaps"]), env["gaps"])


# --------------------------------------------------------------------------- #
# rung 3 — holdings()                                                          #
# --------------------------------------------------------------------------- #
def test_holdings_parses_the_full_book():
    fresh_root("holdings")
    with swap(tickertape, "get_json", lambda url, payload=None, timeout=30: (HOLDINGS_BLOB, None)):
        env = funds.holdings("M_NIMS", fresh=True)
    check("holdings returns the envelope", envelope_keys(env), sorted(env))
    check("holdings ok:true with an allocation", env["ok"] is True)
    d = env["data"]
    check("holdings drops the weightless row", d["position_count"] == 5, d["position_count"])
    check("holdings echoes the mf_id", d["mf_id"] == "M_NIMS")
    pos = {p["sid"]: p for p in d["positions"]}
    check("holdings keeps every equity, debt and unlisted position",
          set(pos) == {"RELI", "TCS", "RECM", "UNLI", "GSEC"}, sorted(pos))
    check("holdings parses the weight", pos["RELI"]["weight"] == 8.5, pos["RELI"])
    check("holdings parses the 3m weight change", pos["TCS"]["change3m"] == -0.9, pos["TCS"])
    check("holdings keeps sid and ticker separately (RECM != RECLTD)",
          pos["RECM"]["sid"] == "RECM" and pos["RECM"]["ticker"] == "RECLTD", pos["RECM"])
    check("holdings keeps the position name", pos["RELI"]["name"] == "Reliance Industries")
    check("holdings keeps the asset type", pos["GSEC"]["type"] == "debt")


def test_holdings_equity_weight_and_sectors():
    fresh_root("holdings-weights")
    with swap(tickertape, "get_json", lambda url, payload=None, timeout=30: (HOLDINGS_BLOB, None)):
        env = funds.holdings("M_NIMS", fresh=True)
    d = env["data"]
    check("equity_weight sums ONLY the equity legs",
          d["equity_weight"] == 20.0, d["equity_weight"])
    check("equity_weight excludes debt and cash",
          d["equity_weight"] != 24.0, d["equity_weight"])
    sw = d["sector_weights"]
    check("sector weights are parsed", sw == {"Financials": 24.6, "Technology": 12.1}, sw)
    check("a sector row with no weight is dropped, not zeroed", "Unweighted Sector" not in sw, sw)
    check("allocation history is passed through",
          d["allocation_history"] == [{"date": "2026-07-31", "equity": 95.1}], d)
    # This fixture is a 20%-equity toy book, so the hybrid/cash-heavy warning SHOULD fire.
    check("a cash-heavy book raises the low-equity gap",
          any("equity weight only" in g for g in env["gaps"]), env["gaps"])


def test_holdings_normal_book_is_silent():
    """A genuinely equity-heavy book must raise no low-equity gap — the warning has to
    stay rare enough to mean something."""
    fresh_root("holdings-normal")
    blob = {"data": {"currentAllocation": [
        {"type": "Equity", "title": "A Ltd", "sid": "AAAA", "ticker": "A", "latest": 60.0},
        {"type": "Equity", "title": "B Ltd", "sid": "BBBB", "ticker": "B", "latest": 35.4},
        {"type": "cash", "title": "Cash", "sid": None, "ticker": None, "latest": 4.6},
    ]}}
    with swap(tickertape, "get_json", lambda url, payload=None, timeout=30: (blob, None)):
        env = funds.holdings("M_TEST", fresh=True)
    check("equity-heavy book sums to its equity weight",
          env["data"]["equity_weight"] == 95.4, env["data"]["equity_weight"])
    check("a normal equity book raises no low-equity gap", env["gaps"] == [], env["gaps"])


def test_holdings_low_equity_gap():
    fresh_root("holdings-hybrid")
    with swap(tickertape, "get_json", lambda url, payload=None, timeout=30: (HYBRID_HOLDINGS_BLOB, None)):
        env = funds.holdings("M_HYBRID", fresh=True)
    check("a cash/debt-heavy book still parses", env["ok"] is True)
    check("its equity weight is the real sum", env["data"]["equity_weight"] == 45.0,
          env["data"]["equity_weight"])
    check("a sub-60% equity weight raises a labelled gap",
          any("equity weight only" in g and "hybrid" in g for g in env["gaps"]), env["gaps"])


def test_holdings_blocked_degrades():
    fresh_root("holdings-blocked")
    with swap(tickertape, "get_json", lambda url, payload=None, timeout=30:
              (None, "curl exit 28 for api.tickertape.in")):
        env = funds.holdings("M_NIMS", fresh=True)
    check("holdings blocked returns ok:false", env["ok"] is False)
    check("holdings blocked still has the envelope shape", envelope_keys(env))
    check("holdings blocked carries a labelled gap naming the fund",
          any("M_NIMS" in g for g in env["gaps"]), env["gaps"])
    check("holdings blocked returns an empty position list — never a partial book",
          env["data"]["positions"] == [])


def test_holdings_empty_allocation_degrades():
    fresh_root("holdings-empty")
    with swap(tickertape, "get_json", lambda url, payload=None, timeout=30: ({"data": {}}, None)):
        env = funds.holdings("M_EMPTY", fresh=True)
    check("holdings with no currentAllocation is ok:false", env["ok"] is False)
    check("holdings with no currentAllocation names the gap",
          any("no currentAllocation" in g for g in env["gaps"]), env["gaps"])


# --------------------------------------------------------------------------- #
# rung 4 — stock_ratios() / enrich()                                           #
# --------------------------------------------------------------------------- #
def test_stock_ratios_parses():
    fresh_root("ratios")
    with swap(tickertape, "get_json", lambda url, payload=None, timeout=30: (STOCK_INFO_BLOB, None)), \
            cap_index(cap_stocks()):
        env = funds.stock_ratios("RECM", fresh=True)
    check("stock_ratios returns the envelope", envelope_keys(env), sorted(env))
    check("stock_ratios ok:true with ratios", env["ok"] is True)
    check("stock_ratios names both sources", env["source"] == "AMFI+Tickertape", env["source"])
    d = env["data"]
    check("stock_ratios keeps the sid as the join key", d["sid"] == "RECM", d)
    check("stock_ratios reports the DIFFERENT ticker", d["ticker"] == "RECLTD", d)
    check("stock_ratios parses pe/pb/roe", (d["pe"], d["pb"], d["roe"]) == (8.4, 1.6, 21.5), d)
    check("stock_ratios carries the SEBI cap RANK, not just the ₹Cr size",
          d["cap_rank"] == 117.0, d)
    check("cap_rank sits between the SEBI large and mid cut-offs",
          caps.SEBI_CAP_RANKS["large"] < d["cap_rank"] <= caps.SEBI_CAP_RANKS["mid"],
          (d["cap_rank"], caps.SEBI_CAP_RANKS))
    check("cap_label is derived from the rank, so the two cannot disagree",
          d["cap_label"] == "Mid Cap", d)
    check("a ranked holding raises no cap gap", env["gaps"] == [], env["gaps"])
    check("stock_ratios carries the industry comparables",
          d["industry_pe"] == 14.2 and d["industry_pb"] == 2.1, d)


def test_stock_ratios_unranked_falls_back_to_the_provider_label():
    fresh_root("ratios-unranked")
    with swap(tickertape, "get_json", lambda url, payload=None, timeout=30: (STOCK_INFO_BLOB, None)), \
            cap_index({}, period="2026-06-30"):
        env = funds.stock_ratios("RECM", fresh=True)
    d = env["data"]
    check("a symbol absent from the AMFI list has no rank", d["cap_rank"] is None, d)
    check("the provider label is the documented fallback", d["cap_label"] == "Midcap", d)
    check("the fallback is a labelled gap naming the symbol",
          any("RECLTD is unranked" in g for g in env["gaps"]), env["gaps"])
    check("the gap names the period the classification covers",
          any("2026-06-30" in g for g in env["gaps"]), env["gaps"])
    check("an unranked holding is still ok — only the cap basis degraded",
          env["ok"] is True and d["pe"] == 8.4, d)


def test_stock_ratios_joins_on_isin_when_the_ticker_misses():
    fresh_root("ratios-isin")
    blob = {"data": {"info": {"ticker": "RECLIMITED", "name": "REC Ltd",
                              "isin": "INE020B01018"},
                     "ratios": {"pe": 8.4}}}
    with swap(tickertape, "get_json", lambda url, payload=None, timeout=30: (blob, None)), \
            cap_index(cap_stocks()):
        env = funds.stock_ratios("RECM", fresh=True)
    check("a ticker the AMFI list does not use still ranks via ISIN",
          env["data"]["cap_rank"] == 117.0, env["data"])
    check("the ISIN join raises no unranked gap", env["gaps"] == [], env["gaps"])


def test_stock_ratios_unlisted_degrades():
    fresh_root("ratios-unlisted")
    with swap(tickertape, "get_json", lambda url, payload=None, timeout=30:
              ({"data": {"info": {"ticker": None}}}, None)):
        env = funds.stock_ratios("UNLI", fresh=True)
    check("an unlisted holding returns ok:false", env["ok"] is False)
    check("an unlisted holding still has the envelope shape", envelope_keys(env))
    check("an unlisted holding names the gap",
          any("no ratios published" in g for g in env["gaps"]), env["gaps"])


def test_enrich_priced_unpriced_split():
    fresh_root("enrich")
    positions = HOLDINGS_BLOB["data"]["currentAllocation"]
    positions = [{"sid": p["sid"], "ticker": p.get("ticker"), "name": p["title"],
                  "weight": p["latest"], "type": p["type"]}
                 for p in positions if p["latest"] is not None]
    priced = {"RELI": {"pe": 24.0, "pb": 2.1, "cap_rank": 8.0},
              "TCS": {"pe": 28.5, "pb": 12.0, "cap_rank": 11.0},
              "RECM": {"pe": 8.4, "pb": 1.6, "cap_rank": 118.0}}

    def fake_ratios(sid, fresh=False):
        if sid in priced:
            return funds._envelope(True, "Tickertape", {"sid": sid, **priced[sid]}, [])
        return funds._envelope(False, "Tickertape", {"sid": sid},
                               [f"no ratios published for {sid} (unlisted or newly listed)"])

    with swap(funds, "stock_ratios", fake_ratios), cap_index(cap_stocks()):
        out, gaps = funds.enrich(positions)
    check("enrich covers every equity position and only those",
          {p["sid"] for p in out} == {"RELI", "TCS", "RECM", "UNLI"}, sorted(p["sid"] for p in out))
    check("enrich drops the debt leg (nothing to price)",
          "GSEC" not in {p["sid"] for p in out})
    check("enrich flags the priced positions",
          all(p["priced"] for p in out if p["sid"] in priced), out)
    check("enrich flags the unpriced position rather than dropping it",
          [p for p in out if p["sid"] == "UNLI"][0]["priced"] is False)
    check("an unpriced position KEEPS its weight (coverage must not overstate itself)",
          [p for p in out if p["sid"] == "UNLI"][0]["weight"] == 2.25)
    check("an unpriced position carries no fabricated ratios",
          "pe" not in [p for p in out if p["sid"] == "UNLI"][0])
    check("enrich attaches the ratios to the priced positions",
          [p for p in out if p["sid"] == "RECM"][0]["pe"] == 8.4)
    check("enrich reports the unpriced WEIGHT, not just the count",
          any("2.25% of the book is unpriced" in g for g in gaps), gaps)
    check("the unpriced gap says the weight is excluded, never extrapolated",
          any("never extrapolated" in g for g in gaps), gaps)
    check("the failing holding's own gap is propagated too",
          any("no ratios published for UNLI" in g for g in gaps), gaps)


def test_enrich_fully_priced_book_raises_no_gap():
    fresh_root("enrich-clean")
    positions = [{"sid": "RELI", "weight": 8.5, "type": "equity"},
                 {"sid": "TCS", "weight": 6.25, "type": "equity"}]
    with swap(funds, "stock_ratios", lambda sid, fresh=False:
              funds._envelope(True, "AMFI+Tickertape",
                              {"sid": sid, "pe": 20.0, "cap_rank": 5.0}, [])), \
            cap_index(cap_stocks()):
        out, gaps = funds.enrich(positions)
    check("a fully priced book raises no unpriced gap", gaps == [], gaps)
    check("a fully priced book marks everything priced", all(p["priced"] for p in out))


def test_enrich_reports_the_unranked_weight():
    fresh_root("enrich-unranked")
    positions = [{"sid": "RELI", "weight": 8.5, "type": "equity"},
                 {"sid": "NEWCO", "weight": 1.75, "type": "equity"}]

    def fake_ratios(sid, fresh=False):
        rank = 1.0 if sid == "RELI" else None
        return funds._envelope(True, "AMFI+Tickertape",
                               {"sid": sid, "pe": 20.0, "cap_rank": rank}, [])

    with swap(funds, "stock_ratios", fake_ratios), cap_index(cap_stocks()):
        out, gaps = funds.enrich(positions)
    check("enrich reports the unranked WEIGHT so cap-tilt's basis is visible",
          any("1.75% of the book is unranked" in g for g in gaps), gaps)
    check("the unranked gap names the AMFI period",
          any("2026-06-30" in g for g in gaps), gaps)
    check("an unranked holding is still priced and keeps its ratios",
          [p for p in out if p["sid"] == "NEWCO"][0]["pe"] == 20.0, out)


def test_enrich_fetches_the_cap_list_once_for_the_whole_book():
    fresh_root("enrich-once")
    positions = [{"sid": f"S{i}", "weight": 1.0, "type": "equity"} for i in range(40)]
    calls = []
    with cap_index_cold(), \
            swap(transport, "request", serve_cap(calls=calls)), \
            swap(tickertape, "get_json", lambda url, payload=None, timeout=30:
                 (STOCK_INFO_BLOB, None)):
        out, _ = funds.enrich(positions, workers=10)
    check("a 40-position book downloads the AMFI workbook once, not once per position",
          len([u for u in calls if u.endswith(".xlsx")]) == 1, calls)
    check("every position still got its rank from that single read",
          all(p["cap_rank"] == 117.0 for p in out), out[:2])


def test_enrich_empty_input():
    fresh_root("enrich-empty")
    out, gaps = funds.enrich([{"sid": "GSEC", "weight": 100.0, "type": "debt"}])
    check("enrich of a no-equity book returns nothing to price", out == [], out)
    check("enrich of a no-equity book raises no gap", gaps == [], gaps)


# --------------------------------------------------------------------------- #
# rung 5 — nav_history()                                                       #
# --------------------------------------------------------------------------- #
def test_nav_history_dates_and_order():
    fresh_root("nav")
    with swap(transport, "json_request", lambda url, payload=None, timeout=30: (NAV_BLOB, None)):
        env = funds.nav_history("118778", fresh=True)
    check("nav_history returns the envelope", envelope_keys(env), sorted(env))
    check("nav_history ok:true with rows", env["ok"] is True)
    check("nav_history source is mfapi.in", env["source"] == "mfapi.in")
    navs = env["data"]["navs"]
    check("nav_history skips the unparseable date row and the unparseable NAV row",
          len(navs) == 3, navs)
    check("nav_history count matches the series", env["data"]["count"] == 3)
    check("nav_history converts DD-MM-YYYY to ISO",
          [n["date"] for n in navs] == ["2026-08-13", "2026-08-15", "2026-08-16"], navs)
    check("nav_history is OLDEST FIRST (mfapi serves newest first)",
          navs == sorted(navs, key=lambda n: n["date"]), navs)
    check("nav_history NAVs are floats", all(isinstance(n["nav"], float) for n in navs))
    check("nav_history keeps the newest NAV last", navs[-1]["nav"] == 198.4562, navs[-1])
    check("nav_history passes the scheme meta through",
          env["data"]["meta"]["scheme_code"] == 118778, env["data"]["meta"])


def test_nav_history_blocked_degrades():
    fresh_root("nav-blocked")
    with swap(transport, "json_request", lambda url, payload=None, timeout=30:
              (None, "curl exit 6 for api.mfapi.in")):
        env = funds.nav_history("118778", fresh=True)
    check("nav_history blocked returns ok:false", env["ok"] is False)
    check("nav_history blocked still has the envelope shape", envelope_keys(env))
    check("nav_history blocked carries a labelled gap naming the scheme",
          any("mfapi 118778:" in g for g in env["gaps"]), env["gaps"])
    check("nav_history blocked returns an empty series", env["data"]["navs"] == [])


def test_nav_history_empty_series_degrades():
    fresh_root("nav-empty")
    with swap(transport, "json_request", lambda url, payload=None, timeout=30: ({"data": []}, None)):
        env = funds.nav_history("999999", fresh=True)
    check("nav_history with no rows is ok:false", env["ok"] is False)
    check("nav_history with no rows names the gap",
          env["gaps"] == ["mfapi returned no NAV rows for 999999"], env["gaps"])


# --------------------------------------------------------------------------- #
# the cache tier                                                               #
# --------------------------------------------------------------------------- #
def test_cache_round_trip_and_ageing():
    fresh_root("cache")
    p = funds._cache_path("meta", "probe key/with:junk")
    check("cache_path sanitises the key into one file",
          os.path.basename(p) == "probe_key_with_junk.json", p)
    env = funds._envelope(True, "AMFI", {"schemes": [{"code": "118778"}]}, [])
    funds._write_cache(p, env)
    check("write_cache stamps today under the reserved key",
          env["data"][spine.CACHE_STAMP] == date.today().isoformat())
    got = funds._read_cache(p, fresh=False)
    check("read_cache returns today's blob", got is not None and got["data"]["schemes"][0]["code"] == "118778")
    check("read_cache honours fresh=True", funds._read_cache(p, fresh=True) is None)
    check("read_cache of a missing file is None",
          funds._read_cache(funds._cache_path("meta", "absent"), fresh=False) is None)


def test_cache_max_age():
    fresh_root("cache-age")
    p = funds._cache_path("meta", "aged")
    stale = funds._envelope(True, "AMFI", {"schemes": []}, [])
    stale["data"][spine.CACHE_STAMP] = (date.today() - timedelta(days=3)).isoformat()
    with open(p, "w") as fh:
        json.dump(stale, fh)
    check("a 3-day-old blob is rejected by a same-day cache",
          funds._read_cache(p, fresh=False) is None)
    check("a 3-day-old blob is accepted inside a 7-day window",
          funds._read_cache(p, fresh=False, max_age_days=7) is not None)
    check("a 3-day-old blob is rejected by a 2-day window",
          funds._read_cache(p, fresh=False, max_age_days=2) is None)
    with open(p, "w") as fh:
        fh.write("{ not json")
    check("a corrupt cache file never blocks a fetch",
          funds._read_cache(p, fresh=False, max_age_days=7) is None)


def test_holdings_cache_round_trip():
    fresh_root("holdings-cache")
    with swap(tickertape, "get_json", lambda url, payload=None, timeout=30: (HOLDINGS_BLOB, None)):
        funds.holdings("M_NIMS", fresh=True)

    def explode(*a, **k):
        raise AssertionError("holdings re-fetched despite a warm cache")

    with swap(tickertape, "get_json", explode):
        env = funds.holdings("M_NIMS")
    check("holdings serves the cached book without refetching", env["ok"] is True)
    check("the cached book round-trips the parsed positions",
          env["data"]["position_count"] == 5 and env["data"]["equity_weight"] == 20.0,
          env["data"])


# --------------------------------------------------------------------------- #
# envelope + coercion primitives                                               #
# --------------------------------------------------------------------------- #
def test_envelope_shape():
    env = funds._envelope(True, "Tickertape", {"x": 1}, [])
    check("envelope has the contract keys", envelope_keys(env), sorted(env))
    check("envelope ok is a bool", isinstance(env["ok"], bool))
    check("envelope gaps is a list", isinstance(env["gaps"], list))
    check("envelope fetched_at is an ISO timestamp", "T" in env["fetched_at"])
    failed = funds._envelope(0, None, {}, ["blocked"])
    check("a failed envelope coerces ok to False", failed["ok"] is False)
    check("a failed envelope keeps the same shape", envelope_keys(failed))


def test_f_coercion():
    check("_f parses a numeric string", funds._f("198.4562") == 198.4562)
    check("_f of '' is None", funds._f("") is None)
    check("_f of None is None", funds._f(None) is None)
    check("_f of junk is None", funds._f("unparseable") is None)
    check("_f keeps a real zero", funds._f(0) == 0.0)
    check("_f keeps a negative", funds._f("-0.9") == -0.9)


if __name__ == "__main__":
    run((test_score_name_requires_every_query_token, test_score_name_prefers_direct_growth,
         test_score_name_penalises_payout_plans,
         test_score_name_prefers_the_tighter_name, test_amfi_index_parses,
         test_amfi_index_dash_isin_is_none, test_amfi_index_blocked_degrades,
         test_amfi_index_unparseable_body_degrades,
         test_cap_label_boundaries, test_cap_link_discovery_takes_the_newest_period,
         test_cap_link_discovery_handles_a_root_relative_href,
         test_cap_link_discovery_no_match_is_a_gap,
         test_cap_xlsx_parse_keys_on_nse_symbol_then_isin,
         test_cap_xlsx_parse_without_a_header_is_a_gap,
         test_amfi_cap_list_end_to_end, test_cap_index_is_memoised_for_the_process,
         test_amfi_cap_list_degrades_at_every_step,
         test_resolve_prefers_direct_growth,
         test_resolve_regular_only_is_a_labelled_gap, test_resolve_no_match_at_all,
         test_screen_filters_subsector_and_option_client_side,
         test_screen_sorts_by_aum_desc, test_screen_whole_universe_when_unfiltered,
         test_screen_strips_premium_fields, test_screen_403_is_a_labelled_gap,
         test_screen_blocked_degrades, test_screen_no_match_is_a_labelled_gap,
         test_holdings_parses_the_full_book, test_holdings_equity_weight_and_sectors,
         test_holdings_normal_book_is_silent, test_holdings_low_equity_gap,
         test_holdings_blocked_degrades, test_holdings_empty_allocation_degrades,
         test_stock_ratios_parses,
         test_stock_ratios_unranked_falls_back_to_the_provider_label,
         test_stock_ratios_joins_on_isin_when_the_ticker_misses,
         test_stock_ratios_unlisted_degrades,
         test_enrich_priced_unpriced_split, test_enrich_fully_priced_book_raises_no_gap,
         test_enrich_reports_the_unranked_weight,
         test_enrich_fetches_the_cap_list_once_for_the_whole_book,
         test_enrich_empty_input, test_nav_history_dates_and_order,
         test_nav_history_blocked_degrades, test_nav_history_empty_series_degrades,
         test_cache_round_trip_and_ageing, test_cache_max_age,
         test_holdings_cache_round_trip, test_envelope_shape, test_f_coercion))
