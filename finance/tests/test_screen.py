#!/usr/bin/env python3
"""Offline tests for the discover screen engine. No network."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import screen
from finance.tests.harness import check, run
from finance.tests import fixtures  # noqa: E402

pd = screen.pd


def row(**kw):
    return pd.Series(kw, dtype=float)


def test_eval_filter():
    r = row(Close=110, ema50=100, rsi14=55, vol10=1000, Volume=1800, ema50_rising=1)
    check("bare truthy col", screen.eval_filter("ema50_rising", r))
    check("gt comparison", screen.eval_filter("Close > ema50", r))
    check("lt false", not screen.eval_filter("Close < ema50", r))
    check("between true", screen.eval_filter("rsi14 between 40 and 60", r))
    check("between false", not screen.eval_filter("rsi14 between 60 and 70", r))
    check("scalar-mul term", screen.eval_filter("Volume > 1.5 * vol10", r))
    check("scalar-mul false", not screen.eval_filter("Volume > 2 * vol10", r))
    check("case-insensitive AND/BETWEEN",
          screen.eval_filter("rsi14 BETWEEN 40 AND 60", r))


def test_eval_filter_unknown_col():
    r = row(Close=10)
    try:
        screen.eval_filter("nonexistent > 5", r)
        check("unknown col raises", False)
    except KeyError:
        check("unknown col raises", True)


def test_passes_technical_collects_reasons():
    df = pd.DataFrame({"ema50_rising": [1.0], "Close": [90.0], "ema50": [100.0],
                       "rsi14": [80.0]})
    ok, reasons = screen.passes_technical(df, ["ema50_rising", "Close > ema50",
                                               "rsi14 between 40 and 60"])
    check("fails when one filter false", not ok)
    check("reasons name the failures", len(reasons) == 2, str(reasons))


def _ind_frame(close, ema50, atr14=2.0, ll20=None, hh20=None, vol10=1000, rsi14=55):
    """One-row indicator frame plus a Low column for swing-low stop math."""
    n = 12
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    df = pd.DataFrame(index=idx)
    df["Close"] = [close] * n
    df["Low"] = [close - 5] * n
    df["High"] = [close + 5] * n
    df["Volume"] = [1500] * n
    df["ema50"] = [ema50] * n
    df["atr14"] = [atr14] * n
    df["ll20"] = [ll20 if ll20 is not None else close - 10] * n
    df["hh20"] = [hh20 if hh20 is not None else close + 10] * n
    df["vol10"] = [vol10] * n
    df["rsi14"] = [rsi14] * n
    df["ema50_rising"] = [1.0] * n
    return df


def test_build_signal_min_rrr_target():
    df = _ind_frame(close=100, ema50=95)
    spec = {"exit": {"stop": "ema50_minus_2atr", "target": "min_rrr", "min_rrr": 1.5},
            "sizing": {"risk_per_trade_pct": 1.0}}
    sig = screen.build_signal(df, spec, capital=500000)
    check("stop = ema50-2atr", sig["stop"] == 91.0, str(sig))
    check("target = entry + minRRR*risk", sig["target"] == 113.5, str(sig))
    check("rrr == min", sig["rrr"] == 1.5)
    check("qty = risk budget / risk", sig["qty"] == int(5000 / 9), str(sig["qty"]))


def test_build_signal_measured_move():
    df = _ind_frame(close=100, ema50=95, ll20=90, hh20=130)
    spec = {"exit": {"stop": "range_low", "target": "measured_move", "min_rrr": 1.5},
            "sizing": {"risk_per_trade_pct": 1.0}}
    sig = screen.build_signal(df, spec, capital=500000)
    check("measured-move target", sig["target"] == 140.0, str(sig))
    check("target_basis labelled", sig["target_basis"] == "measured-move")


def test_build_signal_rejects_low_rrr():
    df = _ind_frame(close=100, ema50=99, atr14=0.4, ll20=99, hh20=101)
    spec = {"exit": {"stop": "ema50_minus_2atr", "target": "measured_move", "min_rrr": 1.5},
            "sizing": {"risk_per_trade_pct": 1.0}}
    sig = screen.build_signal(df, spec, capital=500000)
    check("below min_rrr skipped", "skip" in sig and "RRR" in sig["skip"], str(sig))
    spec["exit"]["min_rrr"] = 1.0
    check("spec cannot lower the mandatory RRR floor", "skip" in screen.build_signal(df, spec, 500000))


def test_build_signal_floors_tight_stop():
    df = _ind_frame(close=100, ema50=95, atr14=3.0)
    df["Low"] = [99.9] * len(df)
    spec = {"exit": {"stop": "recent_swing_low", "target": "min_rrr", "min_rrr": 1.5},
            "sizing": {"risk_per_trade_pct": 1.0}}
    sig = screen.build_signal(df, spec, capital=500000)
    check("tight stop floored to entry-0.5atr", sig["stop"] == 98.5, str(sig))
    check("risk_per_share floored, not ~0", sig["risk_per_share"] == 1.5, str(sig))


def test_exit_signal_series():
    df = _ind_frame(close=100, ema50=95)
    df["sma5"] = [98, 99, 101, 102] + [100] * 8
    fires = list(screen.strategy.exit_signal_series(df, {"exit": {"exit_signal": "Close > sma5"}}))
    check("exit_signal fires where Close>sma5", fires[:4] == [True, True, False, False], str(fires[:4]))
    check("no exit_signal -> never fires",
          not screen.strategy.exit_signal_series(df, {"exit": {}}).any())


def test_build_signal_rejects_wide_stop():
    df = _ind_frame(close=100, ema50=80, atr14=20)
    spec = {"exit": {"stop": "ema50_minus_2atr", "target": "measured_move", "min_rrr": 1.5},
            "sizing": {"risk_per_trade_pct": 1.0}}
    check("too-wide stop skipped", "skip" in screen.build_signal(df, spec, 500000))


def test_screen_compute_discriminates():
    res = screen.screen_compute(["UPTREND", "DOWNTREND"], fixtures.SCREEN_SPEC, 2,
                                500000, loader=lambda s: fixtures.screen_frame(s.lower()))
    names = [c["symbol"] for c in res["candidates"]]
    check("uptrend selected", names == ["UPTREND"], str(names))
    check("downtrend rejected", any(r["symbol"] == "DOWNTREND" for r in res["rejected"]))


def test_screen_compute_handles_loader_failure():
    def bad(sym):
        if sym == "BAD":
            raise RuntimeError("no data")
        return fixtures.screen_frame("uptrend")
    res = screen.screen_compute(["BAD", "GOOD"], fixtures.SCREEN_SPEC, 2, 500000,
                                loader=bad)
    check("failed symbol -> data gap", any("BAD" in g for g in res["data_gaps"]))
    check("good symbol still screened", any(c["symbol"] == "GOOD" for c in res["candidates"]))


def test_live_screen_honors_explicit_entry_signal():
    spec = {**fixtures.SCREEN_SPEC, "entry": {"signal": ["Close < 0"]}}
    res = screen.screen_compute(["UP"], spec, 2, 500000,
                                loader=lambda _: fixtures.screen_frame("uptrend"))
    check("coarse uptrend cannot bypass a false precise entry signal", not res["candidates"])
    check("rejection identifies the entry condition",
          any("Close < 0" in str(r["why"]) for r in res["rejected"]))


def test_textual_archetype_does_not_change_entry_price():
    spec = {**fixtures.SCREEN_SPEC, "archetype": "breakout",
            "entry": {"signal": ["Close > 0"]}}
    raw = fixtures.screen_frame("uptrend")
    res = screen.screen_compute(["UP"], spec, 2, 500000, loader=lambda _: raw)
    check("entry uses the signal close consistently with backtest sizing",
          res["candidates"] and res["candidates"][0]["entry"] == round(raw.Close.iloc[-1], 2))


def _run_with(res, out):
    orig_load, orig_compute = screen.load_spec, screen.screen_compute
    screen.load_spec = lambda path: {**fixtures.SCREEN_SPEC, "name": "test-spec"}
    screen.screen_compute = lambda *a, **k: res
    try:
        return screen.run("spec.yml", ["RELIANCE", "TCS"], years=2, capital=100000, out=out)
    finally:
        screen.load_spec, screen.screen_compute = orig_load, orig_compute


def test_run_envelope_and_report_file():
    import json
    import tempfile
    out = os.path.join(tempfile.mkdtemp(), "screen.json")
    res = {"candidates": [{"symbol": "RELIANCE", "rrr": 2.0}],
           "rejected": [{"symbol": "TCS", "why": ["Close > ema50"]}],
           "data_gaps": ["INFY: no price history"]}
    env = _run_with(res, out)
    check("run returns the data-spine envelope",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"}, sorted(env))
    check("run is ok when something passed", env["ok"] is True)
    check("run returns the ranked candidates inline",
          env["data"]["candidates"] == res["candidates"], env["data"]["candidates"])
    check("run counts rejections instead of shipping them",
          env["data"]["rejected_count"] == 1 and "rejected" not in env["data"],
          sorted(env["data"]))
    check("run carries the config a report has to cite",
          env["data"]["config"]["spec"] == "test-spec"
          and env["data"]["config"]["symbols"] == 2, env["data"]["config"])
    check("run surfaces per-symbol data gaps",
          env["gaps"] == ["INFY: no price history"], env["gaps"])
    check("run writes the full result, rejections included, to report_path",
          env["data"]["report_path"] == out)
    with open(out) as fh:
        written = json.load(fh)
    check("the written report keeps every rejection and its reason",
          written["rejected"][0]["why"] == ["Close > ema50"], written["rejected"])


def test_run_falls_back_to_spec_universe_source():
    """With no symbols passed, run resolves the spec's own universe.source."""
    import tempfile
    seen = {}
    orig_load, orig_compute = screen.load_spec, screen.screen_compute
    screen.load_spec = lambda path: {**fixtures.SCREEN_SPEC, "name": "s", "universe": {"source": "AAA,BBB"}}

    def _capture(syms, *a, **k):
        seen["syms"] = syms
        return {"candidates": [], "rejected": [], "data_gaps": []}
    screen.screen_compute = _capture
    try:
        screen.run("spec.yml", out=os.path.join(tempfile.mkdtemp(), "s.json"))
    finally:
        screen.load_spec, screen.screen_compute = orig_load, orig_compute
    check("run resolves the spec's universe when no symbols are passed",
          seen["syms"] == ["AAA", "BBB"], str(seen))


def test_run_with_no_candidates_is_a_labelled_gap():
    import tempfile
    out = os.path.join(tempfile.mkdtemp(), "screen.json")
    env = _run_with({"candidates": [], "rejected": [], "data_gaps": []}, out)
    check("an empty screen is ok:false", env["ok"] is False)
    check("an empty screen says so rather than reading as a silent pass",
          any("no candidate passed" in g for g in env["gaps"]), env["gaps"])


def test_run_unwritable_report_is_a_gap_not_a_crash():
    env = _run_with({"candidates": [{"symbol": "RELIANCE", "rrr": 2.0}], "rejected": [],
                     "data_gaps": []}, "/nonexistent-root/deep/screen.json")
    check("an unwritable report path degrades to a gap",
          any("could not write" in g for g in env["gaps"]), env["gaps"])
    check("an unwritable report path reports no path", env["data"]["report_path"] is None)
    check("an unwritable report still returns the candidates",
          len(env["data"]["candidates"]) == 1)


def test_risk_parameters_apply_to_live_signals():
    df = _ind_frame(close=100, ema50=95)
    for capital, risk in ((0, 1), (float("inf"), 1), (500000, 0), (500000, 2), (500000, float("nan"))):
        spec = {"sizing": {"risk_per_trade_pct": risk}, "exit": {"min_rrr": 1.5}}
        result = screen.build_signal(df, spec, capital)
        check(f"invalid capital/risk {capital}/{risk} cannot emit a live trade", "skip" in result, result)


def test_condition_input_contract():
    engine = screen.strategy
    frame = pd.DataFrame({"Close": [100., 110.], "ema21": [105., 105.], "Volume": [100., 200.]})
    spec = {"entry": {"signal": "Close > ema21"}}
    check("string entry stays one expression", engine.entry_filters(spec) == ["Close > ema21"])
    check("features inside a string signal are materialized", "ema21" in engine.referenced_features(spec))
    for expr, expected in (("Close BeTwEeN 99 AnD 105", [True, False]), ("100 between 90 and 110", [True, True]), ("Close > 105 Or Volume > 150", [False, True])):
        try:
            check("condition grammar: " + expr, engine.eval_series(expr, frame).tolist() == expected)
        except Exception as exc:
            check("condition grammar: " + expr, False, repr(exc))
    for spec in ({}, {"entry": {"signal": [""]}}, {"entry": {"signal": [True]}}, {"entry": {"signal": 5}}):
        try:
            engine.entry_filters(spec)
            check("empty or malformed entry cannot trade every bar", False, spec)
        except ValueError:
            check("empty or malformed entry cannot trade every bar", True)
        except Exception as exc:
            check("malformed entry raises a clear validation error", False, repr(exc))
    for expr in ("Close < inf", "Close > -inf", "Volume > nan * Close"):
        try:
            engine.eval_series(expr, frame)
            check("nonfinite expression constant rejected: " + expr, False)
        except ValueError:
            check("nonfinite expression constant rejected: " + expr, True)


def test_missing_spec_or_conditions_is_a_gap_before_loading_prices():
    env = screen.run("/tmp/ef-screen-spec-that-does-not-exist.yml", ["SYNTH"])
    check("missing spec is a labelled envelope", not env["ok"] and bool(env["gaps"]))
    called = []
    def load(symbol):
        called.append(symbol)
        return fixtures.screen_frame("uptrend")
    result = screen.screen_compute(["SYNTH"], {}, 2, 500000, loader=load)
    check("empty trigger cannot fetch or emit a trade", not called and not result["candidates"] and bool(result["data_gaps"]), result)
    spec = {**fixtures.SCREEN_SPEC, "entry": {"signal": "Close > ema21"}}
    result = screen.screen_compute(["SYNTH"], spec, 2, 500000, loader=load)
    check("string trigger runs through live orchestration", bool(result["candidates"]), result)


def test_screen_preserves_price_gaps_and_bar_date():
    import unittest.mock as mock
    frame = fixtures.screen_frame("uptrend")
    with mock.patch.object(screen.prices, "history_df", return_value=(frame, ["fixture partial history"])):
        result = screen.screen_compute(["SYNTH"], fixtures.SCREEN_SPEC, 2, 500000)
    check("screen retains degraded price history", any("fixture partial history" in gap for gap in result["data_gaps"]), result)
    check("candidate identifies its decision bar date", result["candidates"] and result["candidates"][0].get("as_of") == str(frame.index[-1].date()))



def test_live_signal_risk_uses_published_prices():
    from decimal import Decimal
    spec={"exit":{"stop":"ema50_minus_2atr","target":"min_rrr","min_rrr":1.5}}
    for entry,stop,capital in ((50.006,47.004,9910),(50.005,47.001,10000)):
        sig=screen.build_signal(_ind_frame(entry,stop+4),spec,capital)
        check("rounding regression still yields a usable candidate", "skip" not in sig,sig)
        if "skip" in sig:
            continue
        risk=Decimal(str(sig["entry"]))-Decimal(str(sig["stop"]))
        reward=Decimal(str(sig["target"]))-Decimal(str(sig["entry"]))
        check("quantity respects the budget at the displayed entry and stop",risk*sig["qty"] <= Decimal(str(capital))/100,sig)
        check("reported risk agrees with the displayed levels",Decimal(str(sig["risk_per_share"]))==risk,sig)
        check("displayed target meets the declared reward-to-risk requirement",reward/risk>=Decimal('1.5'),sig)


def test_invalid_rrr_rejected_before_loading_data():
    from unittest import mock
    from finance.compute import backtest
    for value in (1.0, True, float("nan"), float("inf"), "invalid"):
        spec = {**fixtures.SCREEN_SPEC, "exit": {"min_rrr": value}}
        with mock.patch.object(screen, "load_spec", return_value=spec), mock.patch("finance.sources.universe.resolve_symbols") as universe:
            result = screen.run("fixture.yml", "nifty500")
        check("invalid RRR screen rejects before universe fetch", not universe.called and not result["ok"], result)
        loader = mock.Mock()
        result = screen.screen_compute(["SYNTH"], spec, 2, 500000, loader=loader)
        check("invalid RRR compute rejects before prices", not loader.called and bool(result["data_gaps"]), result)
        with mock.patch.object(backtest, "load_yaml", return_value=spec), mock.patch.object(backtest.universe, "resolve_symbols") as universe:
            result = backtest.run("fixture.yml", "nifty500")
        check("invalid RRR backtest rejects before universe fetch", not universe.called and not result["ok"], result)
        try:
            screen.strategy.build_bt_strategy(spec, 500000)
            check("direct backtest construction rejects invalid RRR", False, value)
        except ValueError:
            check("direct backtest construction rejects invalid RRR", True)


def test_invalid_exit_rules_rejected_before_data():
    from unittest import mock
    from finance.compute import backtest
    for key, value in (("stop", "recent_swng_low"), ("stop", None),
                       ("time_stop_sessions", 0), ("time_stop_sessions", -1),
                       ("time_stop_sessions", 2.5), ("time_stop_sessions", True),
                       ("trail_atr", -1), ("trail_atr", float("nan")),
                       ("trail_atr", float("inf")), ("trail_atr", True)):
        spec = {**fixtures.SCREEN_SPEC, "exit": {key: value}}
        loader = mock.Mock()
        result = screen.screen_compute(["SYNTH"], spec, 2, 500000, loader=loader)
        check("bad exit rejects before price fetch", not loader.called and bool(result["data_gaps"]), (key,value,result))
        with mock.patch.object(backtest, "load_yaml", return_value=spec), mock.patch.object(backtest.universe, "resolve_symbols") as universe:
            result = backtest.run("fixture.yml", "nifty500")
        check("bad exit rejects before backtest universe fetch", not universe.called and not result["ok"], (key,value,result))
        result = screen.build_signal(_ind_frame(100, 99), spec, 500000)
        check("direct live signal rejects malformed exit", "skip" in result, (key,value,result))


def test_target_names_are_exact_machine_rules():
    for target in ("not_measured_move", "next_resistance", "min_rrr; for blue-sky use measured_move", "recent swing high", None, 2):
        try:
            screen.strategy.validate_exit({"target": target})
            check("ambiguous target rejected", False, target)
        except ValueError:
            check("ambiguous target rejected", True)
    for target in ("measured_move", "min_rrr"):
        try:
            screen.strategy.validate_exit({"target": target})
            check("exact fixed target accepted", True)
        except ValueError:
            check("exact fixed target accepted", False, target)
    for exitb in ({"target":"trailing"}, {"target":"signal"}, {"target":"none"}):
        try:
            screen.strategy.validate_exit(exitb)
            check("unmanaged open target rejected", False, exitb)
        except ValueError:
            check("unmanaged open target rejected", True)


def test_dynamic_exit_does_not_invent_live_take_profit():
    for exitb in ({"target":"trailing", "trail_atr":2.5},
                  {"target":"signal", "exit_signal":"Close < ema50"},
                  {"target":"none", "trail_atr":2}):
        spec = {"exit": {"stop":"ema50_minus_2atr", **exitb}}
        signal = screen.build_signal(_ind_frame(100, 99), spec, 500000)
        check("dynamic exit cannot masquerade as fixed live target", "no fixed target" in signal.get("skip", ""), signal)
        check("dynamic exit remains backtestable", screen.strategy.build_bt_strategy(spec, 500000) is not None)


def test_coarse_screen_cannot_substitute_for_entry():
    from unittest.mock import patch
    from finance.compute import backtest
    coarse = dict(fixtures.SCREEN_SPEC, entry={'trigger': 'wait for a discretionary retest'})
    for missing in ({'trigger': 'wait for a retest'}, {'signal': []}):
        spec = dict(coarse, entry=missing)
        calls = []
        result = screen.screen_compute(['SYNTH'], spec, 2, 500000,
                                       loader=lambda symbol: calls.append(symbol))
        check('coarse-only live strategy refuses before prices', not calls and not result['candidates'] and bool(result['data_gaps']))
        with patch.object(backtest, 'load_yaml', return_value=spec), \
             patch.object(backtest.universe, 'resolve_symbols', side_effect=AssertionError('must reject before universe')) as resolve:
            result = backtest.run('synthetic.yml', 'nifty50')
            check('coarse-only backtest refuses before universe', not result['ok'] and not resolve.called)
            check('backtest explains missing explicit signal', any('entry.signal' in gap for gap in result['gaps']))


if __name__ == "__main__":
    run(globals())
