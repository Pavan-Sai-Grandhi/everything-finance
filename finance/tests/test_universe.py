#!/usr/bin/env python3
"""Offline tests for the universe authority. No network — transport is stubbed."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = tempfile.mkdtemp(prefix="ef-universe-")

from finance import transport
from finance.compute import backtest, screen
from finance.sources import universe
from finance.tests.harness import check, run

_INDEX_CSV = ("Company Name,Industry,Symbol,Series,ISIN Code\n"
              "Reliance Industries Ltd.,Energy,RELIANCE,EQ,INE002A01018\n"
              "Tata Consultancy Services Ltd.,IT,TCS,EQ,INE467B01029\n")
_FNO_CSV = ("UNDERLYING     ,SYMBOL    ,SEP-26  ,\n"
            "NIFTY 50       ,NIFTY     ,65      ,\n"
            "Reliance       ,RELIANCE  ,250     ,\n")


def _stub(body, gap=None):
    orig = transport.request
    transport.request = lambda *a, **k: (body, gap)
    return orig


def test_index_csv_parse():
    orig = _stub(_INDEX_CSV)
    try:
        syms, gaps = universe.resolve_symbols("nifty50", fresh=True)
    finally:
        transport.request = orig
    check("index CSV → its symbols", syms == ["RELIANCE", "TCS"], str(syms))
    check("clean fetch has no gaps", gaps == [], str(gaps))


def test_fno_drops_index_underlyings():
    orig = _stub(_FNO_CSV)
    try:
        syms, _ = universe.resolve_symbols("fno", fresh=True)
    finally:
        transport.request = orig
    check("F&O keeps equities, drops the index underlying", syms == ["RELIANCE"], str(syms))


def test_local_forms():
    check("a list normalises", universe.resolve_symbols([" reliance ", "tcs"])[0]
          == ["RELIANCE", "TCS"])
    check("a comma string splits", universe.resolve_symbols("reliance,tcs")[0]
          == ["RELIANCE", "TCS"])
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        fh.write("reliance\n\ntcs\n")
        path = fh.name
    check("a file reads one symbol per line",
          universe.resolve_symbols(path)[0] == ["RELIANCE", "TCS"])
    os.unlink(path)


def test_largecap20_named():
    syms, gaps = universe.resolve_symbols("largecap20")
    check("largecap20 resolves to the 20-name basket", len(syms) == 20, str(len(syms)))
    check("largecap20 needs no fetch", gaps == [])


def test_fetch_failure_is_a_gap_no_cache():
    orig = _stub(None, gap="nsearchives: HTTP 503")
    try:
        syms, gaps = universe.resolve_symbols("nifty200", fresh=True)
    finally:
        transport.request = orig
    check("a failed fetch with no cache is empty", syms == [])
    check("a failed fetch is a labelled gap", any("503" in g for g in gaps), str(gaps))


def test_stale_cache_fallback():
    orig = _stub(_INDEX_CSV)
    try:
        universe.resolve_symbols("nifty100", fresh=True)   # populate today's cache
    finally:
        transport.request = orig
    orig = _stub(None, gap="nsearchives: HTTP 503")
    try:
        syms, gaps = universe.resolve_symbols("nifty100", fresh=True)
    finally:
        transport.request = orig
    check("a failed fetch falls back to cache", syms == ["RELIANCE", "TCS"], str(syms))
    check("the stale-cache fallback is labelled", any("cached" in g for g in gaps), str(gaps))


def test_resolve_writes_to_file_not_inline():
    orig = _stub(_INDEX_CSV)
    try:
        env = universe.resolve("nifty500", fresh=True)
    finally:
        transport.request = orig
    check("envelope carries the count, not the list", env["data"]["symbols_count"] == 2)
    check("no symbols list is returned inline", "symbols" not in env["data"])
    check("the list is on disk", os.path.exists(env["data"]["universe_path"]))
    check("the file holds the symbols",
          open(env["data"]["universe_path"]).read().split() == ["RELIANCE", "TCS"])


def test_resolver_parity():
    """screen and backtest resolve an input identically, largecap20 included."""
    for name in ("largecap20", "reliance,tcs", ["INFY", "SBIN"]):
        check(f"parity for {name!r}",
              screen.resolve_symbols(name) == backtest.resolve_universe(name),
              f"{screen.resolve_symbols(name)} vs {backtest.resolve_universe(name)}")


if __name__ == "__main__":
    run(globals())
