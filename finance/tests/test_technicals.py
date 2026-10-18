#!/usr/bin/env python3
"""Offline tests for finance/compute/technicals.py over a synthetic candle frame."""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import ta, technicals
from finance.tests.harness import check, run

pd = ta.pd


def _frame(n=260):
    closes = [100 + i * 0.5 for i in range(n)]
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame({"Open": [c - 0.2 for c in closes], "High": [c + 1 for c in closes],
                         "Low": [c - 1 for c in closes], "Close": closes,
                         "Volume": [1000 + i for i in range(n)]}, index=idx)


def test_report_carries_the_indicator_of_record():
    frame = _frame()
    with mock.patch.object(technicals.prices, "history_df", return_value=(frame, [])):
        env = technicals.report("TESTCO", features=["ema100", "nr7"])
    latest = env["data"]["latest"]
    check("report is ok on a full series", env["ok"], env.get("gaps"))
    check("rows cover every bar", env["data"]["bars"] == 260 and len(env["data"]["rows"]) == 260)
    expected = ta.ema(frame["Close"], 50).iloc[-1]
    check("ema50 equals ta.ema on the same closes", abs(latest["ema50"] - expected) < 1e-3, latest["ema50"])
    check("requested feature tokens are materialized", "ema100" in latest and "nr7" in latest, sorted(latest))
    check("macd and bollinger columns are named apart",
          {"macd", "macd_signal", "macd_hist", "bb_mid", "bb_upper", "bb_lower"} <= set(latest))
    check("patterns are reported as names, not columns in latest",
          isinstance(env["data"]["patterns_latest"], list) and "doji" not in latest)


def test_drop_last_and_bad_inputs():
    frame = _frame()
    with mock.patch.object(technicals.prices, "history_df", return_value=(frame, [])):
        env = technicals.report("TESTCO", drop_last=True)
        check("drop_last strikes levels on the prior session",
              env["data"]["as_of"] == frame.index[-2].date().isoformat(), env["data"]["as_of"])
        check("an unknown feature token is a labelled gap",
              not technicals.report("TESTCO", features=["vibes9"])["ok"])
    with mock.patch.object(technicals.prices, "history_df", return_value=(None, ["fetch blocked"])):
        env = technicals.report("TESTCO")
    check("no candles is ok:false with the source gap", not env["ok"] and env["gaps"] == ["fetch blocked"], env)


if __name__ == "__main__":
    run(globals())
