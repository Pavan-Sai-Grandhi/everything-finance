#!/usr/bin/env python3
"""Offline unit tests for lib/market.py (the market-wide data-spine fetcher).

Deterministic, no network — every rung runs against saved response fixtures with the
module's own HTTP/scanner seams swapped out, mirroring test_prices.py /
test_fundamentals.py / test_filings.py. Artifact roots are temp dirs, so a run never
touches the user's real ./artifacts. Run:
    python3 lib/test_market.py    # exits 0 when all pass
"""
import atexit
import contextlib
import json
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Point the path authority at a throwaway root BEFORE anything can write a cache file.
_TMP_ROOT = tempfile.mkdtemp(prefix="ef-test-market-")
os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = os.path.join(_TMP_ROOT, "artifacts")
atexit.register(shutil.rmtree, _TMP_ROOT, True)

import market  # noqa: E402
import paths  # noqa: E402
import prices  # noqa: E402

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

# NSE archives ind_close_all_<DDMMYYYY>.csv — note the blank P/E on Smallcap 250 (real:
# NSE published none for it for years) and the "-" sentinel on the Microcap P/B.
IND_CLOSE_CSV = (
    "Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,"
    "Closing Index Value,Points Change,Change(%),Volume,Turnover (Rs. Cr.),"
    "P/E,P/B,Div Yield\n"
    "Nifty 50,16-08-2026,24500.10,24610.55,24455.20,24572.30,72.20,0.29,"
    "250000000,32000.55,22.45,3.85,1.24\n"
    "Nifty Smallcap 250,16-08-2026,17800.00,17950.00,17750.00,17902.15,102.15,0.57,"
    "120000000,9500.10,,4.10,0.68\n"
    "  nifty   bank ,16-08-2026,52000.00,52400.00,51900.00,52310.75,310.75,0.60,"
    "90000000,15000.00,14.02,2.55,0.95\n"
    "Nifty Microcap 250,16-08-2026,29000.00,29200.00,28900.00,29150.40,150.40,0.52,"
    "40000000,2100.00,-,-,0.41\n"
    ",16-08-2026,0,0,0,0,0,0,0,0,0,0,0\n"
)

# NSE /api/allIndices — the live rung. "-" P/E must land as None, not 0.
ALL_INDICES_PAYLOAD = {
    "data": [
        {"index": "NIFTY 50", "last": "24,572.30", "pe": "22.45", "pb": "3.85",
         "dy": "1.24", "percentChange": 0.29, "perChange365d": 12.5},
        {"index": "Nifty Smallcap 250", "last": "17902.15", "pe": "-", "pb": "4.10",
         "dy": "0.68", "percentChange": 0.57, "perChange365d": -3.2},
        "this row is not a dict",
        {"index": "", "last": "1.0"},
    ]
}

# NSE /api/fiidiiTradeReact — the flow rung.
FII_DII_PAYLOAD = [
    {"category": "DII **", "date": "16-Aug-2026", "buyValue": "12,000.50",
     "sellValue": "9,000.25", "netValue": "3,000.25"},
    {"category": "FII/FPI *", "date": "16-Aug-2026", "buyValue": "15,000.00",
     "sellValue": "18,000.00", "netValue": "-3,000.00"},
    "not a dict",
]

# prices.screen() breadth rows — deliberately holed so each metric's denominator differs.
BREADTH_ROWS = [
    {"name": "A", "close": 100.0, "SMA50": 90.0, "SMA200": 80.0, "change": 1.2,
     "price_52_week_high": 105.0, "price_52_week_low": 60.0, "market_cap_basic": 9e11},
    {"name": "B", "close": 50.0, "SMA50": 60.0, "SMA200": 40.0, "change": -0.5,
     "price_52_week_high": 80.0, "price_52_week_low": 48.0, "market_cap_basic": 6e11},
    {"name": "C", "close": 70.0, "SMA50": None, "SMA200": 65.0, "change": 0.0,
     "price_52_week_high": 75.0, "price_52_week_low": 69.0, "market_cap_basic": 3e11},
    {"name": "D", "close": None, "SMA50": 10.0, "SMA200": 10.0, "change": None,
     "price_52_week_high": None, "price_52_week_low": None, "market_cap_basic": 1e11},
]


# --------------------------------------------------------------------------- #
# pure: the archive CSV parser                                                 #
# --------------------------------------------------------------------------- #
def test_parse_ind_close_csv():
    snap = market._parse_ind_close_csv(IND_CLOSE_CSV)
    check("ind_close parses one entry per named index row", len(snap) == 4, sorted(snap))
    check("ind_close keys are canonical", "NIFTY 50" in snap and "NIFTY SMALLCAP 250" in snap)
    check("ind_close canonicalises a messy CSV spelling ('  nifty   bank ')",
          "NIFTY BANK" in snap, sorted(snap))
    check("ind_close drops the unnamed row", "" not in snap)
    n50 = snap["NIFTY 50"]
    check("ind_close close parsed", n50["close"] == 24572.30, n50)
    check("ind_close P/E parsed", n50["pe"] == 22.45, n50)
    check("ind_close P/B parsed", n50["pb"] == 3.85, n50)
    check("ind_close div yield parsed", n50["dy"] == 1.24, n50)


def test_parse_ind_close_blank_pe_is_none_not_zero():
    snap = market._parse_ind_close_csv(IND_CLOSE_CSV)
    sc = snap["NIFTY SMALLCAP 250"]
    # A zero here would silently drag every percentile down — the whole point of the rule.
    check("blank P/E cell becomes None", sc["pe"] is None, sc)
    check("blank P/E is NOT 0", sc["pe"] != 0 and sc["pe"] is not False, sc)
    check("the rest of a blank-P/E row still parses", sc["pb"] == 4.10 and sc["close"] == 17902.15, sc)
    mc = snap["NIFTY MICROCAP 250"]
    check("'-' sentinel P/E becomes None", mc["pe"] is None, mc)
    check("'-' sentinel P/B becomes None", mc["pb"] is None, mc)
    check("'-' sentinel row keeps its real numbers", mc["dy"] == 0.41, mc)


def test_parse_ind_close_empty():
    check("ind_close of an empty string is {}", market._parse_ind_close_csv("") == {})
    check("ind_close of None is {}", market._parse_ind_close_csv(None) == {})
    check("ind_close of a header-only body is {}",
          market._parse_ind_close_csv("Index Name,P/E,P/B,Div Yield\n") == {})


# --------------------------------------------------------------------------- #
# pure: canonicalisation                                                       #
# --------------------------------------------------------------------------- #
def test_canon():
    # The live JSON and the archive CSV disagree on case and spacing; _canon is what makes
    # a percentile of the archive comparable to today's live level.
    check("canon upper-cases", market._canon("Nifty Smallcap 250") == "NIFTY SMALLCAP 250")
    check("canon collapses inner whitespace", market._canon("NIFTY   50") == "NIFTY 50")
    check("canon strips outer whitespace", market._canon("  nifty bank  ") == "NIFTY BANK")
    check("canon is idempotent", market._canon(market._canon("Nifty IT")) == "NIFTY IT")
    check("live JSON and CSV spellings canonicalise to one key",
          market._canon("NIFTY SMALLCAP 250") == market._canon("Nifty Smallcap 250"))
    check("canon of None is ''", market._canon(None) == "")
    check("canon of '' is ''", market._canon("") == "")
    check("canon keeps '&' sector names", market._canon("Nifty Oil & Gas") == "NIFTY OIL & GAS")
    check("every BROAD_INDICES key is already canonical",
          all(market._canon(k) == k for k in market.BROAD_INDICES))
    check("every SECTOR_INDICES key is already canonical",
          all(market._canon(k) == k for k in market.SECTOR_INDICES))


# --------------------------------------------------------------------------- #
# pure: month-end sampling                                                     #
# --------------------------------------------------------------------------- #
def test_month_ends():
    today = date(2026, 8, 16)
    got = market._month_ends(1, today=today)
    check("month_ends returns 12 month-ends + today for years=1", len(got) == 14, len(got))
    check("month_ends is oldest first", got == sorted(got), got[:3])
    check("month_ends has no duplicates", len(set(got)) == len(got))
    check("month_ends holds no future date", all(d <= today for d in got))
    check("month_ends ends on today (the current level is a sample)", got[-1] == today, got[-1])
    check("month_ends samples are month-ends", all(
        (d + timedelta(days=1)).day == 1 for d in got[:-1]), got[:3])
    check("month_ends oldest sample is ~12 months back",
          got[0] == date(2025, 7, 31), got[0])
    check("month_ends crosses the year boundary correctly", date(2025, 12, 31) in got)


def test_month_ends_ten_years():
    today = date(2026, 8, 16)
    got = market._month_ends(10, today=today)
    check("month_ends(10) is ~121 samples", len(got) == 122, len(got))
    check("month_ends(10) still oldest-first with today last",
          got == sorted(got) and got[-1] == today)
    check("month_ends(10) spans ten years", (today - got[0]).days > 365 * 9.9, got[0])


def test_month_ends_on_the_first_of_a_month():
    today = date(2026, 3, 1)
    got = market._month_ends(1, today=today)
    check("month_ends on the 1st keeps today last", got[-1] == today, got[-1])
    check("month_ends on the 1st has no future date", all(d <= today for d in got))
    check("month_ends on the 1st includes the prior month-end", date(2026, 2, 28) in got)


# --------------------------------------------------------------------------- #
# pure: percentile                                                             #
# --------------------------------------------------------------------------- #
def test_percentile():
    check("percentile of an empty pool is None", market.percentile([], 5) is None)
    check("percentile of None pool is None", market.percentile(None, 5) is None)
    check("percentile of an all-None pool is None", market.percentile([None, None], 5) is None)
    check("percentile of a None value is None", market.percentile([1, 2, 3], None) is None)
    check("percentile of a single element is 50", market.percentile([5.0], 5.0) == 50.0,
          market.percentile([5.0], 5.0))
    check("percentile splits ties evenly", market.percentile([1, 2, 2, 3], 2) == 50.0,
          market.percentile([1, 2, 2, 3], 2))
    check("percentile at the exact min", market.percentile([1, 2, 3], 1) == 16.7,
          market.percentile([1, 2, 3], 1))
    check("percentile at the exact max", market.percentile([1, 2, 3], 3) == 83.3,
          market.percentile([1, 2, 3], 3))
    check("percentile above the whole pool is 100", market.percentile([1, 2, 3], 10) == 100.0)
    check("percentile below the whole pool is 0", market.percentile([1, 2, 3], 0) == 0.0)
    check("percentile drops None pool members from the denominator",
          market.percentile([1, None, 3], 3) == 75.0, market.percentile([1, None, 3], 3))
    check("percentile of a zero value is computed, not skipped",
          market.percentile([-1, 0, 1], 0) == 50.0, market.percentile([-1, 0, 1], 0))


# --------------------------------------------------------------------------- #
# rung 1 — indices()                                                           #
# --------------------------------------------------------------------------- #
def test_indices_parses():
    fresh_root("indices")
    with swap(market, "_nse_json", lambda url, referer: (ALL_INDICES_PAYLOAD, None)):
        env = market.indices(fresh=True)
    check("indices returns the data-spine envelope", envelope_keys(env), sorted(env))
    check("indices ok:true with rows", env["ok"] is True)
    check("indices source is NSE", env["source"] == "NSE")
    idx = env["data"]["indices"]
    check("indices skips non-dict rows and unnamed indices", env["data"]["count"] == 2, sorted(idx))
    check("indices keys are canonical", set(idx) == {"NIFTY 50", "NIFTY SMALLCAP 250"}, sorted(idx))
    n50 = idx["NIFTY 50"]
    check("indices strips thousands separators from last", n50["last"] == 24572.30, n50)
    check("indices carries pe/pb/dy", (n50["pe"], n50["pb"], n50["dy"]) == (22.45, 3.85, 1.24), n50)
    check("indices carries 1d and 1y change",
          n50["pct_change"] == 0.29 and n50["pct_change_1y"] == 12.5, n50)
    check("indices '-' P/E is None, never 0", idx["NIFTY SMALLCAP 250"]["pe"] is None)
    check("indices keeps a negative 1y change", idx["NIFTY SMALLCAP 250"]["pct_change_1y"] == -3.2)


def test_indices_blocked_degrades():
    fresh_root("indices-blocked")
    with swap(market, "_nse_json", lambda url, referer: (None, "curl exit 28 for www.nseindia.com")):
        env = market.indices(fresh=True)
    check("indices blocked returns ok:false", env["ok"] is False)
    check("indices blocked still has the envelope shape", envelope_keys(env), sorted(env))
    check("indices blocked carries a labelled gap",
          len(env["gaps"]) == 1 and env["gaps"][0].startswith("NSE allIndices:"), env["gaps"])
    check("indices blocked returns an empty index map, never a partial lie",
          env["data"]["indices"] == {})


def test_indices_empty_payload_gap():
    fresh_root("indices-empty")
    with swap(market, "_nse_json", lambda url, referer: ({"data": []}, None)):
        env = market.indices(fresh=True)
    check("indices with no rows is ok:false", env["ok"] is False)
    check("indices with no rows names the gap",
          env["gaps"] == ["NSE allIndices returned no index rows"], env["gaps"])


# --------------------------------------------------------------------------- #
# rung 2 — index_snapshot() / valuation_history()                              #
# --------------------------------------------------------------------------- #
def _csv_server(requested, empty_days=()):
    """Fake _http_get that serves the archive CSV for any weekday not in `empty_days`."""
    def fake(url, timeout=25, referer=None, cookie_jar=None):
        stamp = url.rsplit("_", 1)[-1].replace(".csv", "")
        requested.append(stamp)
        return ("" if stamp in empty_days else IND_CLOSE_CSV), None
    return fake


def test_index_snapshot_skips_weekends():
    fresh_root("snapshot-weekend")
    saturday = date(2026, 8, 15)
    check("fixture date really is a Saturday", saturday.weekday() == 5)
    seen = []
    with swap(market, "_http_get", _csv_server(seen)):
        snap, actual, gap = market.index_snapshot(saturday.isoformat())
    check("snapshot walks back off a weekend to the prior session",
          actual == "2026-08-14", (actual, seen))
    check("snapshot spends no fetch on a Sat/Sun", seen == ["14082026"], seen)
    check("snapshot has no gap when it lands", gap is None, gap)
    check("snapshot carries every index from the one fetch", len(snap) == 4, sorted(snap))


def test_index_snapshot_walks_back_over_a_holiday():
    fresh_root("snapshot-holiday")
    seen = []
    # 2026-08-14 is a Friday; make it a holiday (empty body, not a 404) -> Thursday.
    with swap(market, "_http_get", _csv_server(seen, empty_days={"14082026"})):
        snap, actual, gap = market.index_snapshot("2026-08-14")
    check("snapshot treats an empty archive body as a holiday and walks back",
          actual == "2026-08-13", (actual, seen))
    check("snapshot tried the holiday first, then the prior day",
          seen == ["14082026", "13082026"], seen)
    check("snapshot returns the prior session's data", snap["NIFTY 50"]["close"] == 24572.30)


def test_index_snapshot_cache_round_trip():
    fresh_root("snapshot-cache")
    seen = []
    with swap(market, "_http_get", _csv_server(seen)):
        market.index_snapshot("2026-08-14")
    check("snapshot fetched once on a cold cache", len(seen) == 1, seen)

    def explode(*a, **k):
        raise AssertionError("index_snapshot re-fetched a cached day")

    with swap(market, "_http_get", explode):
        snap, actual, gap = market.index_snapshot("2026-08-14")
    check("snapshot second call is served from the permanent cache", gap is None and snap, gap)
    check("cached snapshot keeps the resolved trading day", actual == "2026-08-14", actual)
    check("cached snapshot round-trips the parsed values",
          snap["NIFTY 50"]["pe"] == 22.45 and snap["NIFTY SMALLCAP 250"]["pe"] is None, snap)
    check("snapshot cache file lives under the artifacts cache tier",
          os.path.isfile(market._snapshot_cache_path("2026-08-14")),
          market._snapshot_cache_path("2026-08-14"))


def test_index_snapshot_all_blocked():
    fresh_root("snapshot-blocked")
    with swap(market, "_http_get", lambda *a, **k: (None, "curl exit 6 for nsearchives.nseindia.com")):
        snap, actual, gap = market.index_snapshot("2026-08-14", walk_back=2)
    check("snapshot all-blocked returns no data", snap == {} and actual is None)
    check("snapshot all-blocked returns the last labelled gap", "curl exit 6" in (gap or ""), gap)


def test_valuation_history_offline():
    fresh_root("valuation")
    seen = []
    with swap(market, "_http_get", _csv_server(seen)):
        env = market.valuation_history("nifty 50", years=1)
    check("valuation_history returns the envelope", envelope_keys(env), sorted(env))
    check("valuation_history ok:true with samples", env["ok"] is True)
    check("valuation_history canonicalises the index name", env["data"]["index"] == "NIFTY 50")
    series = env["data"]["series"]
    check("valuation_history samples every month-end plus today", len(series) == 14, len(series))
    check("valuation_history is oldest first",
          [s["date"] for s in series] == sorted(s["date"] for s in series))
    check("valuation_history rows carry close/pe/pb/dy",
          set(series[0]) == {"date", "close", "pe", "pb", "dy"}, sorted(series[0]))
    check("valuation_history has no P/E gap when every sample is priced", env["gaps"] == [], env["gaps"])

    # One day-snapshot serves EVERY index — the second index costs no fetch at all.
    def explode(*a, **k):
        raise AssertionError("valuation_history re-fetched a day another index already cached")

    with swap(market, "_http_get", explode):
        env2 = market.valuation_history("Nifty Smallcap 250", years=1)
    check("a cached day snapshot serves a different index for free", env2["ok"] is True)
    check("second index gets the same sample count", env2["data"]["samples"] == 14,
          env2["data"]["samples"])
    check("unpriced samples are labelled as a gap, not silently zeroed",
          any("carry no P/E" in g for g in env2["gaps"]), env2["gaps"])
    check("every unpriced sample keeps pe=None",
          all(s["pe"] is None for s in env2["data"]["series"]))


def test_valuation_history_unknown_index():
    fresh_root("valuation-unknown")
    with swap(market, "_http_get", _csv_server([])):
        env = market.valuation_history("NIFTY NOT AN INDEX", years=1)
    check("valuation_history for an unknown index is ok:false", env["ok"] is False)
    check("valuation_history for an unknown index names the gap",
          any("no archive valuation history" in g for g in env["gaps"]), env["gaps"])
    check("valuation_history for an unknown index still has the envelope shape", envelope_keys(env))


# --------------------------------------------------------------------------- #
# rung 3 — breadth()                                                           #
# --------------------------------------------------------------------------- #
def _breadth_env(rows, gaps=None):
    return {"ok": True, "source": "TradingView", "fetched_at": "x",
            "data": {"rows": rows}, "gaps": gaps or []}


def test_breadth_counts_and_denominators():
    fresh_root("breadth")
    with swap(prices, "screen", lambda body, columns=None, limit=None: _breadth_env(BREADTH_ROWS)):
        env = market.breadth(universe=500, fresh=True)
    check("breadth returns the envelope", envelope_keys(env), sorted(env))
    check("breadth ok:true with rows", env["ok"] is True)
    check("breadth universe is the row count", env["data"]["universe"] == 4, env["data"])
    c = env["data"]["counts"]
    check("breadth reports the five participation metrics",
          set(c) == {"above_sma50", "above_sma200", "advancing",
                     "near_52w_high", "near_52w_low"}, sorted(c))
    check("above_sma50 counts only rows that HAVE close+SMA50",
          c["above_sma50"] == {"count": 1, "of": 2}, c["above_sma50"])
    check("above_sma200 has its own (larger) denominator",
          c["above_sma200"] == {"count": 3, "of": 3}, c["above_sma200"])
    check("advancing excludes a flat 0.0% change from the count but not the denominator",
          c["advancing"] == {"count": 1, "of": 3}, c["advancing"])
    check("near_52w_high uses the 5% band",
          c["near_52w_high"] == {"count": 1, "of": 3}, c["near_52w_high"])
    check("near_52w_low uses the 5% band",
          c["near_52w_low"] == {"count": 2, "of": 3}, c["near_52w_low"])
    check("each metric carries its OWN denominator (they genuinely differ)",
          len({m["of"] for m in c.values()}) > 1, c)
    check("a row missing a field is excluded from that denominator, not counted as false",
          c["above_sma50"]["of"] == 2 and env["data"]["universe"] == 4, c)
    check("breadth returns counts only, never the constituent list",
          "rows" not in env["data"] and "constituents" not in env["data"], sorted(env["data"]))


def test_breadth_all_fields_missing_gives_empty_denominator():
    fresh_root("breadth-holes")
    holed = [{"name": "X", "close": None, "SMA50": None, "SMA200": None, "change": None,
              "price_52_week_high": None, "price_52_week_low": None}]
    with swap(prices, "screen", lambda body, columns=None, limit=None: _breadth_env(holed)):
        env = market.breadth(fresh=True)
    c = env["data"]["counts"]
    check("an all-holes row yields a zero denominator, not a false count",
          all(m == {"count": 0, "of": 0} for m in c.values()), c)
    check("universe still reports the row that was fetched", env["data"]["universe"] == 1)


def test_breadth_no_rows_degrades():
    fresh_root("breadth-empty")
    empty = {"ok": False, "source": "TradingView", "fetched_at": "x",
             "data": {"rows": []}, "gaps": ["TradingView blocked"]}
    with swap(prices, "screen", lambda body, columns=None, limit=None: empty):
        env = market.breadth(fresh=True)
    check("breadth with no rows is ok:false", env["ok"] is False)
    check("breadth with no rows still has the envelope shape", envelope_keys(env))
    check("breadth propagates the screen's labelled gap", env["gaps"] == ["TradingView blocked"],
          env["gaps"])
    check("breadth with no rows reports a zero universe", env["data"]["universe"] == 0)


# --------------------------------------------------------------------------- #
# rung 4 — flows()                                                             #
# --------------------------------------------------------------------------- #
def test_flows_categorisation():
    fresh_root("flows")
    with swap(market, "_nse_json", lambda url, referer: (FII_DII_PAYLOAD, None)):
        env = market.flows(fresh=True)
    check("flows returns the envelope", envelope_keys(env), sorted(env))
    check("flows ok:true with rows", env["ok"] is True)
    f = env["data"]["flows"]
    check("flows splits into exactly FII and DII", set(f) == {"FII", "DII"}, sorted(f))
    check("'FII/FPI *' is categorised as FII", f["FII"]["net_cr"] == -3000.00, f["FII"])
    check("'DII **' is categorised as DII", f["DII"]["net_cr"] == 3000.25, f["DII"])
    check("flows strips thousands separators from buy/sell",
          f["DII"]["buy_cr"] == 12000.50 and f["DII"]["sell_cr"] == 9000.25, f["DII"])
    check("flows keeps the session date", env["data"]["session"] == "16-Aug-2026", env["data"])
    check("flows skips non-dict rows", len(f) == 2)


def test_flows_blocked_degrades():
    fresh_root("flows-blocked")
    with swap(market, "_nse_json", lambda url, referer: (None, "NSE returned non-JSON")):
        env = market.flows(fresh=True)
    check("flows blocked returns ok:false", env["ok"] is False)
    check("flows blocked still has the envelope shape", envelope_keys(env))
    check("flows blocked carries a labelled gap",
          env["gaps"] and env["gaps"][0].startswith("NSE FII/DII:"), env["gaps"])
    check("flows blocked returns no flow numbers", env["data"]["flows"] == {})


# --------------------------------------------------------------------------- #
# rung 5 — macro()                                                             #
# --------------------------------------------------------------------------- #
def test_macro_reduces_each_series_to_three_numbers():
    fresh_root("macro")
    candles = [{"date": (date(2026, 7, 1) + timedelta(days=i)).isoformat(),
                "close": 100.0 + i} for i in range(30)]

    def fake_history(ticker, period="5y", fresh=False):
        return {"ok": True, "source": "yfinance", "fetched_at": "x",
                "data": {"candles": candles}, "gaps": []}

    with swap(prices, "history", fake_history):
        env = market.macro(fresh=True)
    check("macro returns the envelope", envelope_keys(env), sorted(env))
    check("macro covers every configured series",
          set(env["data"]["macro"]) == set(market._MACRO_TICKERS), sorted(env["data"]["macro"]))
    vix = env["data"]["macro"]["india_vix"]
    check("macro reduces a series to last/1m-change/percentile/as_of",
          set(vix) == {"last", "chg_1m_pct", "percentile_5y", "as_of"}, sorted(vix))
    check("macro last is the newest close", vix["last"] == 129.0, vix)
    check("macro 1m change is measured 22 sessions back", vix["chg_1m_pct"] == 19.44, vix)
    check("macro percentile comes from the same pure ranker",
          vix["percentile_5y"] == 98.3, vix)
    check("macro as_of is the last candle's date", vix["as_of"] == "2026-07-30", vix)
    check("macro never returns raw candles", "candles" not in json.dumps(env["data"]))


def test_macro_missing_history_is_a_labelled_gap():
    fresh_root("macro-empty")
    empty = {"ok": False, "source": "yfinance", "fetched_at": "x",
             "data": {"candles": []}, "gaps": []}
    with swap(prices, "history", lambda t, period="5y", fresh=False: empty):
        env = market.macro(fresh=True)
    check("macro with no history is ok:false", env["ok"] is False)
    check("macro with no history still has the envelope shape", envelope_keys(env))
    check("macro names every missing series in the gaps",
          len(env["gaps"]) == len(market._MACRO_TICKERS), env["gaps"])
    check("macro gaps name the ticker that failed",
          all("no history" in g for g in env["gaps"]), env["gaps"])


# --------------------------------------------------------------------------- #
# the day-scoped cache                                                         #
# --------------------------------------------------------------------------- #
def test_day_cache_round_trip():
    fresh_root("daycache")
    f = os.path.join(paths.cache_dir("market"), "probe.json")
    env = market._envelope(True, "NSE", {"indices": {"NIFTY 50": {"pe": 22.45}}}, [])
    market._write_day_cache(f, env)
    check("write_day_cache stamps today's date on the payload",
          env["data"]["date"] == date.today().isoformat(), env["data"].get("date"))
    got = market._read_day_cache(f, fresh=False)
    check("read_day_cache returns today's cached envelope", got is not None)
    check("day cache round-trips the data intact",
          got["data"]["indices"]["NIFTY 50"]["pe"] == 22.45, got)
    check("read_day_cache honours fresh=True (forces a refetch)",
          market._read_day_cache(f, fresh=True) is None)
    check("read_day_cache of a missing file is None",
          market._read_day_cache(os.path.join(paths.cache_dir("market"), "nope.json"), False) is None)


def test_day_cache_from_a_previous_day_is_ignored():
    fresh_root("daycache-stale")
    f = os.path.join(paths.cache_dir("market"), "stale.json")
    stale = market._envelope(True, "NSE", {"date": (date.today() - timedelta(days=1)).isoformat(),
                                           "indices": {"NIFTY 50": {"pe": 9.99}}}, [])
    with open(f, "w") as fh:
        json.dump(stale, fh)
    check("yesterday's cache is ignored", market._read_day_cache(f, fresh=False) is None)

    undated = market._envelope(True, "NSE", {"indices": {}}, [])
    undated["data"].pop("date", None)
    with open(f, "w") as fh:
        json.dump(undated, fh)
    check("an undated cache file is ignored", market._read_day_cache(f, fresh=False) is None)

    with open(f, "w") as fh:
        fh.write("{ not json at all")
    check("a corrupt cache file never blocks a fetch",
          market._read_day_cache(f, fresh=False) is None)


def test_indices_cache_round_trip_through_the_public_rung():
    fresh_root("indices-cache")
    with swap(market, "_nse_json", lambda url, referer: (ALL_INDICES_PAYLOAD, None)):
        market.indices(fresh=True)

    def explode(url, referer):
        raise AssertionError("indices re-fetched despite a same-day cache")

    with swap(market, "_nse_json", explode):
        env = market.indices()
    check("indices serves today's cache without refetching", env["ok"] is True)
    check("cached indices round-trip canonical keys and values",
          env["data"]["indices"]["NIFTY 50"]["pe"] == 22.45, env["data"]["indices"])

    # Age the cache file by a day; the stale copy must NOT be served.
    cache_file = os.path.join(paths.cache_dir("market"), "indices.json")
    with open(cache_file) as fh:
        blob = json.load(fh)
    blob["data"]["date"] = (date.today() - timedelta(days=1)).isoformat()
    with open(cache_file, "w") as fh:
        json.dump(blob, fh)
    with swap(market, "_nse_json", lambda url, referer: (None, "blocked")):
        env2 = market.indices()
    check("a cache written on a previous day is ignored, not served stale",
          env2["ok"] is False and env2["data"]["indices"] == {}, env2["data"])


# --------------------------------------------------------------------------- #
# envelope + coercion primitives                                               #
# --------------------------------------------------------------------------- #
def test_envelope_shape():
    env = market._envelope(True, "NSE", {"x": 1}, [])
    check("envelope has the contract keys", envelope_keys(env), sorted(env))
    check("envelope ok is a bool", isinstance(env["ok"], bool))
    check("envelope gaps is a list", isinstance(env["gaps"], list))
    check("envelope fetched_at is an ISO timestamp", "T" in env["fetched_at"])
    failed = market._envelope(0, None, {}, ["blocked"])
    check("a failed envelope coerces ok to False", failed["ok"] is False)
    check("a failed envelope keeps the same shape", envelope_keys(failed))


def test_f_coercion():
    check("_f strips commas", market._f("1,23,456.78") == 123456.78)
    check("_f of '-' is None", market._f("-") is None)
    check("_f of '' is None", market._f("") is None)
    check("_f of None is None", market._f(None) is None)
    check("_f of 'NA' is None", market._f("NA") is None)
    check("_f of junk is None", market._f("n/a-ish") is None)
    check("_f keeps a real zero", market._f("0") == 0.0)
    check("_f keeps a negative", market._f("-3,000.00") == -3000.0)


def main():
    for fn in (test_parse_ind_close_csv, test_parse_ind_close_blank_pe_is_none_not_zero,
               test_parse_ind_close_empty, test_canon,
               test_month_ends, test_month_ends_ten_years, test_month_ends_on_the_first_of_a_month,
               test_percentile,
               test_indices_parses, test_indices_blocked_degrades, test_indices_empty_payload_gap,
               test_index_snapshot_skips_weekends, test_index_snapshot_walks_back_over_a_holiday,
               test_index_snapshot_cache_round_trip, test_index_snapshot_all_blocked,
               test_valuation_history_offline, test_valuation_history_unknown_index,
               test_breadth_counts_and_denominators,
               test_breadth_all_fields_missing_gives_empty_denominator,
               test_breadth_no_rows_degrades,
               test_flows_categorisation, test_flows_blocked_degrades,
               test_macro_reduces_each_series_to_three_numbers,
               test_macro_missing_history_is_a_labelled_gap,
               test_day_cache_round_trip, test_day_cache_from_a_previous_day_is_ignored,
               test_indices_cache_round_trip_through_the_public_rung,
               test_envelope_shape, test_f_coercion):
        fn()
    print(f"\n{'=' * 48}\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
