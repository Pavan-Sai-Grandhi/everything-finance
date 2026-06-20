#!/usr/bin/env python3
"""Offline unit tests for lib/prices.py (data-spine prices fetcher).

Deterministic, no network — the parsers and the reconcile decision run against saved
response fixtures, mirroring test_filings.py / test_ta.py. Proves A6. Run:
    python3 lib/test_prices.py    # exits 0 when all pass
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prices  # noqa: E402

_passed = 0
_failed = 0


def check(name, cond, extra=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok  {name}")
    else:
        _failed += 1
        print(f"  FAIL {name} {extra}")


# --- saved fixture: a TradingView scanner response (NSE:RELIANCE single-symbol scan) --- #
SCAN_FIXTURE = {
    "totalCount": 2,
    "data": [
        {"s": "NSE:RELIANCE", "d": ["RELIANCE", 2951.25, 1.23, 35.8, 6543210, 1.99e13]},
        {"s": "NSE:TCS", "d": ["TCS", 3890.0, -0.45, -17.6, 1234567, 1.41e13]},
    ],
}

# --- saved fixture: a yfinance-style OHLCV frame, built without a network call --------- #
def _ohlcv_frame():
    import pandas as pd
    idx = pd.to_datetime(["2026-06-17", "2026-06-18", "2026-06-19"])
    return pd.DataFrame(
        {"Open": [2900.0, 2920.0, 2945.0], "High": [2935.0, 2950.0, 2960.0],
         "Low": [2890.0, 2915.0, 2940.0], "Close": [2925.0, 2948.0, 2951.0],
         "Volume": [5_000_000, 5_500_000, 6_543_210]},
        index=idx,
    )


def test_parse_scan():
    rows = prices._parse_scan(SCAN_FIXTURE, prices.QUOTE_COLUMNS)
    check("parse_scan returns one row per data entry", len(rows) == 2)
    r0 = rows[0]
    check("parse_scan strips the NSE: prefix to a bare symbol", r0["symbol"] == "RELIANCE")
    check("parse_scan records the exchange", r0["exchange"] == "NSE")
    check("parse_scan aligns close to the column order", r0["close"] == 2951.25, r0)
    check("parse_scan coerces numerics to float", isinstance(r0["volume"], float))
    check("parse_scan keeps name as text", r0["name"] == "RELIANCE")


def test_parse_scan_empty():
    check("parse_scan of an empty payload is []", prices._parse_scan({}, prices.QUOTE_COLUMNS) == [])
    check("parse_scan of None is []", prices._parse_scan(None, prices.QUOTE_COLUMNS) == [])


def test_quote_body_no_auth():
    body = prices._quote_body("reliance", prices.QUOTE_COLUMNS)
    check("quote_body targets the NSE ticker", body["symbols"]["tickers"] == ["NSE:RELIANCE"])
    check("quote_body carries the requested columns", body["columns"] == prices.QUOTE_COLUMNS)
    # A2: the body carries no auth/session field — the public scanner needs none.
    check("quote_body has no auth field", "auth" not in body and "session" not in body)


def test_screen_body_india_params():
    body = prices._screen_body([{"left": "close", "operation": "greater", "right": 100}],
                               prices.SCREEN_COLUMNS, limit=25)
    check("screen_body sets the India market (A2)", body["markets"] == ["india"])
    check("screen_body keeps the filter rows", body["filter"][0]["left"] == "close")
    check("screen_body honors the limit range", body["range"] == [0, 25])
    # passthrough of a ready scanner payload keeps its own sort
    ready = prices._screen_body({"filter": [], "sort": {"sortBy": "name", "sortOrder": "asc"}},
                                prices.SCREEN_COLUMNS)
    check("screen_body passes a ready payload's sort through", ready["sort"]["sortBy"] == "name")


def test_df_to_candles():
    candles = prices._df_to_candles(_ohlcv_frame())
    check("df_to_candles emits one candle per bar", len(candles) == 3)
    check("df_to_candles dates are ISO", candles[0]["date"] == "2026-06-17")
    check("df_to_candles last close is right", candles[-1]["close"] == 2951.0)
    check("df_to_candles ohlcv are floats", all(isinstance(candles[0][k], float)
          for k in ("open", "high", "low", "close", "volume")))
    check("df_to_candles of an empty frame is []", prices._df_to_candles(None) == [])


def test_df_to_candles_multiindex():
    import pandas as pd
    df = _ohlcv_frame()
    df.columns = pd.MultiIndex.from_product([df.columns, ["RELIANCE"]])
    candles = prices._df_to_candles(df)
    check("df_to_candles flattens yfinance MultiIndex columns", len(candles) == 3 and candles[-1]["close"] == 2951.0)


def test_reconcile_decision():
    # A5: within tolerance -> not diverged; beyond -> diverged; missing -> None.
    diverged, pct = prices._diverges(2951.0, 2950.0, 0.01)
    check("reconcile agrees within tolerance", diverged is False and pct < 0.01)
    diverged, pct = prices._diverges(3100.0, 2950.0, 0.01)
    check("reconcile flags a >tolerance divergence (A5)", diverged is True and pct > 0.01)
    diverged, pct = prices._diverges(None, 2950.0, 0.01)
    check("reconcile is None when a close is missing", diverged is None)
    diverged, pct = prices._diverges(2950.0, 0, 0.01)
    check("reconcile is None on a zero denominator", diverged is None)


def test_envelope_shape():
    env = prices._envelope(True, "TradingView", {"x": 1}, [])
    for k in ("ok", "source", "fetched_at", "data", "gaps"):
        check(f"envelope has {k}", k in env)
    check("envelope ok is a bool", isinstance(env["ok"], bool))
    check("envelope gaps is a list", isinstance(env["gaps"], list))


def test_norm():
    check("norm strips .NS", prices._norm("reliance.ns") == "RELIANCE")
    check("norm strips an exchange prefix", prices._norm("NSE:TCS") == "TCS")


def main():
    for fn in (test_parse_scan, test_parse_scan_empty, test_quote_body_no_auth,
               test_screen_body_india_params, test_df_to_candles,
               test_df_to_candles_multiindex, test_reconcile_decision,
               test_envelope_shape, test_norm):
        fn()
    print(f"\n{'=' * 48}\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
