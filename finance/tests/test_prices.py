#!/usr/bin/env python3
"""Offline unit tests for finance/sources/prices.py (data-spine prices fetcher)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.sources import prices
from finance.tests.harness import check, run


SCAN_FIXTURE = {
    "totalCount": 2,
    "data": [
        {"s": "NSE:RELIANCE", "d": ["RELIANCE", 2951.25, 1.23, 35.8, 6543210, 1.99e13]},
        {"s": "NSE:TCS", "d": ["TCS", 3890.0, -0.45, -17.6, 1234567, 1.41e13]},
    ],
}

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
    check("quote_body has no auth field", "auth" not in body and "session" not in body)


def test_screen_body_india_params():
    body = prices._screen_body([{"left": "close", "operation": "greater", "right": 100}],
                               prices.SCREEN_COLUMNS, limit=25)
    check("screen_body sets the India market (A2)", body["markets"] == ["india"])
    check("screen_body keeps the filter rows", body["filter"][0]["left"] == "close")
    check("screen_body honors the limit range", body["range"] == [0, 25])
    ready = prices._screen_body({"filter": [], "sort": {"sortBy": "name", "sortOrder": "asc"}},
                                prices.SCREEN_COLUMNS)
    check("screen_body passes a ready payload's sort through", ready["sort"]["sortBy"] == "name")
    basket = {"symbols": {"tickers": ["NSE:TCS"]}}
    body = prices._screen_body(basket, prices.SCREEN_COLUMNS)
    check("a basket-only payload stays a basket", body["symbols"] == basket["symbols"], body)
    check("payload keys never become filter strings", body.get("filter", []) == [{"left":"exchange","operation":"equal","right":"NSE"}], body)



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


def test_quote_uses_requested_issuer_and_rejects_bad_quotes():
    from unittest import mock
    from copy import deepcopy
    import tempfile
    with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"EVERYTHING_FINANCE_ARTIFACTS": root}):
        with mock.patch.object(prices, "_scan_post", return_value=(SCAN_FIXTURE, None)):
            result = prices.quote("TCS", fresh=True)
        check("quote selects requested issuer instead of first row", result["ok"] and result["data"]["symbol"] == "TCS" and result["data"]["close"] == 3890, result)
        for payload in ({"data":[SCAN_FIXTURE["data"][0]]}, {"data":"bad"},
                        {"data":[SCAN_FIXTURE["data"][1],SCAN_FIXTURE["data"][1]]},
                        {"data":[{"s":7,"d":[1]}]}, {"data":[{"s":"NSE:TCS","d":"bad"}]}):
            with mock.patch.object(prices, "_scan_post", return_value=(payload, None)):
                result = prices.quote("TCS", fresh=True)
            check("wrong or malformed quote is a gap", not result["ok"] and bool(result["gaps"]), result)
        for close in (None, True, -1, 0, float("inf")):
            payload=deepcopy(SCAN_FIXTURE)
            payload["data"][1]["d"][1]=close
            with mock.patch.object(prices, "_scan_post", return_value=(payload, None)):
                result=prices.quote("TCS", fresh=True)
            check("unusable close cannot become a successful quote", not result["ok"], result)
        wrong = prices._envelope(True, "TradingView", {"symbol":"RELIANCE", "exchange":"NSE", "close":100}, [])
        with mock.patch.object(prices, "_read_cache", return_value=wrong), mock.patch.object(prices, "_scan_post", return_value=(SCAN_FIXTURE,None)) as fetch:
            result=prices.quote("TCS")
        check("wrong cached identity is refetched", fetch.called and result["data"]["symbol"]=="TCS", result)


def test_price_cache_identity_is_contained_and_distinct():
    from pathlib import Path
    from unittest import mock
    import tempfile
    with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"EVERYTHING_FINANCE_ARTIFACTS": root}):
        first = Path(prices._cache_path("history", "../../escape", "../../period", False))
        check("untrusted cache identity remains inside price cache", first.parent == Path(root)/"cache"/"prices")
        check("adjustment has distinct cache identity", prices._cache_path("history", "TCS", "1y", False) != prices._cache_path("history", "TCS", "1y", True))
        check("cache identity stable for same request", first == Path(prices._cache_path("history", "../../escape", "../../period", False)))


def test_history_validates_actual_download_and_reports_drops():
    from unittest import mock
    import tempfile
    import types
    frame = _ohlcv_frame()
    frame.loc[frame.index[1], "Close"] = float("nan")
    fake = types.SimpleNamespace(download=mock.Mock(return_value=frame))
    with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"EVERYTHING_FINANCE_ARTIFACTS":root}), mock.patch.dict(sys.modules, {"yfinance":fake}):
        result=prices.history("RELIANCE", fresh=True)
    check("valid candles remain usable", result["ok"] and result["data"]["bars"]==2, result)
    check("missing historical close is a visible gap", bool(result["gaps"]), result)
    check("invalid candle count describes missing data honestly", result["data"].get("bars_dropped_invalid")==1, result)
    check("finite close does not claim settlement", "bars_dropped_unsettled" not in result["data"], result)


def test_history_rejects_invalid_geometry_and_duplicate_dates():
    from unittest import mock
    import tempfile
    import types
    import pandas as pd
    for column, value in (("High",1), ("Low",9999), ("Open",0), ("Volume",-1)):
        frame=_ohlcv_frame();frame.loc[frame.index[1],column]=value
        fake=types.SimpleNamespace(download=mock.Mock(return_value=frame))
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"EVERYTHING_FINANCE_ARTIFACTS":root}), mock.patch.dict(sys.modules, {"yfinance":fake}):
            result=prices.history("RELIANCE",fresh=True)
        check("invalid OHLCV excluded with gap",result["data"]["bars"]==2 and bool(result["gaps"]),(column,result))
    frame=_ohlcv_frame();frame=pd.concat([frame,frame.iloc[[1]]])
    fake=types.SimpleNamespace(download=mock.Mock(return_value=frame))
    with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"EVERYTHING_FINANCE_ARTIFACTS":root}), mock.patch.dict(sys.modules, {"yfinance":fake}):
        result=prices.history("RELIANCE",fresh=True)
    check("ambiguous duplicate session excluded entirely", result["data"]["bars"]==2 and all(c["date"]!="2026-06-18" for c in result["data"]["candles"]), result)


def test_history_cache_checks_identity_and_today_is_unverified():
    from unittest import mock
    from datetime import date
    import tempfile
    import types
    fake=types.SimpleNamespace(download=mock.Mock(return_value=_ohlcv_frame()))
    bad=prices._envelope(True,"yfinance",{"symbol":"OTHER","period":"1y","adjusted":False,"candles":[]},[])
    with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"EVERYTHING_FINANCE_ARTIFACTS":root}), mock.patch.dict(sys.modules, {"yfinance":fake}):
        with mock.patch.object(prices,"_read_cache",return_value=bad):
            result=prices.history("RELIANCE")
        check("wrong history cache refetched", fake.download.called and result["data"]["bars"]==3,result)
        fake.download.reset_mock()
        cached=prices.history("RELIANCE")
        check("validated history cache reused",not fake.download.called and cached["data"]==result["data"])
        frame=_ohlcv_frame().iloc[[-1]].copy()
        import pandas as pd
        frame.index=pd.to_datetime([date.today().isoformat()])
        fake.download.return_value=frame
        result=prices.history("RELIANCE",fresh=True)
        check("finite current-day close is explicitly unverified",result["ok"] and any("completion is not verified" in gap for gap in result["gaps"]),result)


def test_screen_input_errors_stop_before_fetch():
    from unittest import mock
    for kwargs in ({"limit":0},{"limit":True},{"limit":1.5},{"columns":"close"},
                   {"columns":["close","close"]},{"filters":"close > 100"}):
        args={"filters":[],**kwargs}
        with mock.patch.object(prices,"_scan_post") as fetch:
            result=prices.screen(**args)
        check("invalid scanner inputs rejected locally",not fetch.called and not result["ok"] and bool(result["gaps"]),args)


def test_screen_bad_rows_are_visible_and_candidates_are_unique_nse():
    from unittest import mock
    payload={"data":[{"s":"NSE:TCS","d":[100]}, {"s":"NSE:TCS","d":[100]},
                     {"s":"BSE:TCS","d":[100]}, {"s":"NSE:BAD","d":"bad"},
                     {"s":"NSE:ZERO","d":[0]}]}
    with mock.patch.object(prices,"_scan_post",return_value=(payload,None)):
        result=prices.screen([],columns=["close"],limit=10)
    check("unique usable NSE candidates only",result["data"]["candidates"]==["TCS"],result)
    check("excluded screen rows produce gaps",bool(result["gaps"]),result)
    with mock.patch.object(prices,"_scan_post",return_value=({"error":"fixture"},None)):
        result=prices.screen([])
    check("malformed response not described as no matches", not result["ok"] and any("malformed" in gap for gap in result["gaps"]),result)


if __name__ == "__main__":
    run(globals())
