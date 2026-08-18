#!/usr/bin/env python3
"""Offline tests for finance/spine.py — the primitives every data-spine fetcher shares.

The coercion and cache rules have one implementation, so they get one test here; the
per-module tests exercise the names those modules re-export.

Run: python3 finance/tests/test_spine.py
"""
import json
import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance import spine
from finance.tests.harness import check, run


def test_envelope():
    env = spine.envelope(1, "NSE", {"a": 1}, ["a gap"])
    check("ok is coerced to a real bool", env["ok"] is True)
    check("source is carried", env["source"] == "NSE")
    check("data is carried", env["data"] == {"a": 1})
    check("gaps are carried", env["gaps"] == ["a gap"])
    check("fetched_at is stamped", isinstance(env["fetched_at"], str) and env["fetched_at"])
    check("the contract has exactly the five keys",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"}, sorted(env))
    check("a falsy ok stays False", spine.envelope(0, None, {}, [])["ok"] is False)


def test_f_coercion():
    """A blank must be None, never 0 — a fabricated zero poisons an average silently."""
    check("parses a plain numeric string", spine.f("198.4562") == 198.4562)
    check("parses a number", spine.f(12) == 12.0)
    check("strips Indian digit grouping", spine.f("1,23,456.78") == 123456.78)
    check("strips a percent sign", spine.f("12.5%") == 12.5)
    check("keeps a real zero", spine.f("0") == 0.0)
    check("keeps a negative", spine.f("-3,000.00") == -3000.0)
    check("keeps a negative decimal", spine.f("-0.9") == -0.9)
    for blank in (None, "", "-", "--", "NA", "N.A.", "N/A", "None", "null"):
        check(f"blank {blank!r} is None, not 0", spine.f(blank) is None)
    check("junk is None", spine.f("unparseable") is None)
    check("junk with digits is None", spine.f("n/a-ish") is None)
    check("a list is None, never a raise", spine.f([1, 2]) is None)


def test_first():
    row = {"a": "", "b": None, "c": [], "d": "hit", "e": "later"}
    check("skips empty string, None and []", spine.first(row, "a", "b", "c", "d") == "hit")
    check("takes the earliest present key", spine.first(row, "d", "e") == "hit")
    check("all-missing yields the default", spine.first(row, "x", "y") is None)
    check("the default is overridable", spine.first(row, "x", default="") == "")
    check("a non-dict yields the default, never a raise", spine.first(None, "x") is None)
    check("a real zero is a hit, not an absence", spine.first({"n": 0}, "n") == 0)


def test_norm_symbol():
    check("uppercases", spine.norm_symbol("reliance") == "RELIANCE")
    check("strips an exchange prefix", spine.norm_symbol("NSE:TCS") == "TCS")
    check("strips a .NS suffix", spine.norm_symbol("INFY.NS") == "INFY")
    check("strips both", spine.norm_symbol(" nse:infy.ns ") == "INFY")
    check("None yields empty, never a raise", spine.norm_symbol(None) == "")


def _blob(stamp, key="date"):
    return {"ok": True, "data": {key: stamp, "v": 1}}


def test_cache_roundtrip():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "c.json")

    env = {"ok": True, "data": {"v": 1}}
    spine.write_cache(p, env)
    check("write stamps today's date", env["data"]["date"] == spine.today())
    check("a written cache reads back", (spine.read_cache(p, False) or {}).get("data", {}).get("v") == 1)
    check("fresh=True bypasses the cache", spine.read_cache(p, True) is None)

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    json.dump(_blob(yesterday), open(p, "w"))
    check("a stale entry is not served", spine.read_cache(p, False) is None)
    check("max_age_days admits a stale-but-young entry",
          spine.read_cache(p, False, max_age_days=7) is not None)
    old = (date.today() - timedelta(days=30)).isoformat()
    json.dump(_blob(old), open(p, "w"))
    check("max_age_days still rejects a too-old entry",
          spine.read_cache(p, False, max_age_days=7) is None)


def test_cache_never_blocks_a_fetch():
    """Every failure mode must read as a miss, so a bad cache can't take a skill down."""
    d = tempfile.mkdtemp()
    missing = os.path.join(d, "nope.json")
    check("a missing file is a miss", spine.read_cache(missing, False) is None)

    corrupt = os.path.join(d, "bad.json")
    open(corrupt, "w").write("{not json")
    check("a corrupt file is a miss, not a raise", spine.read_cache(corrupt, False) is None)

    nostamp = os.path.join(d, "nostamp.json")
    json.dump({"ok": True, "data": {"v": 1}}, open(nostamp, "w"))
    check("an unstamped entry is a miss", spine.read_cache(nostamp, False) is None)

    junkstamp = os.path.join(d, "junk.json")
    json.dump(_blob("not-a-date"), open(junkstamp, "w"))
    check("an unparseable stamp is a miss",
          spine.read_cache(junkstamp, False, max_age_days=7) is None)

    spine.write_cache("/nonexistent-dir/x.json", {"data": {}})
    check("an unwritable path is swallowed, never raised", True)


def test_cache_stamp_key_is_selectable():
    """fundamentals/news stamp with `cached_on`; prices/funds with `date`."""
    d = tempfile.mkdtemp()
    p = os.path.join(d, "c.json")
    env = {"ok": True, "data": {"v": 1}}
    spine.write_cache(p, env, stamp_key="cached_on")
    check("write honours the stamp key", env["data"]["cached_on"] == spine.today())
    check("read honours the stamp key",
          spine.read_cache(p, False, stamp_key="cached_on") is not None)
    check("the wrong stamp key reads as a miss", spine.read_cache(p, False) is None)


def test_f_rejects_nonfinite():
    """NaN survives every `is not None` filter, so the one coercion must kill it.
    A NaN close reaching percentile math reports the value as the lowest ever seen."""
    check("NaN -> None", spine.f(float("nan")) is None)
    check("string nan -> None", spine.f("nan") is None)
    check("+inf -> None", spine.f(float("inf")) is None)
    check("-inf -> None", spine.f(float("-inf")) is None)
    check("a real float still passes", spine.f(11.31) == 11.31)
    check("zero still passes, not falsy-dropped", spine.f(0) == 0.0)
    check("negative still passes", spine.f(-2.5) == -2.5)


def test_iso_date():
    """Every date this plugin emits is YYYY-MM-DD. NSE serves DD-Mon-YYYY, so an
    un-normalised filing date cannot be compared against a news or candle date — a
    consumer doing that arithmetic raises, or silently mis-orders."""
    check("NSE DD-Mon-YYYY", spine.iso_date("17-Aug-2026") == "2026-08-17")
    check("NSE DD-MON-YYYY upper", spine.iso_date("30-JUN-2026") == "2026-06-30")
    check("single-digit day", spine.iso_date("5-Jun-2026") == "2026-06-05")
    check("ISO passes through", spine.iso_date("2026-08-17") == "2026-08-17")
    check("ISO timestamp is truncated", spine.iso_date("2026-08-17T09:15:00") == "2026-08-17")
    check("slashes tolerated", spine.iso_date("17/Aug/2026") == "2026-08-17")
    check("garbage -> None, never a wrong date", spine.iso_date("garbage") is None)
    check("empty -> None", spine.iso_date("") is None)
    check("None -> None", spine.iso_date(None) is None)
    check("bad month -> None", spine.iso_date("17-Xyz-2026") is None)


if __name__ == "__main__":
    run((test_envelope, test_f_coercion, test_first, test_norm_symbol, test_cache_roundtrip,
         test_cache_never_blocks_a_fetch, test_cache_stamp_key_is_selectable, test_f_rejects_nonfinite, test_iso_date))
