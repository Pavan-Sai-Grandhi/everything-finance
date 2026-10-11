#!/usr/bin/env python3
"""Offline tests for the backtest engine. No network — OHLCV is synthetic."""
import json
import os
import shutil
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import backtest
from finance.sources import universe
from finance.tests.harness import approx, check, run

pd = backtest.pd


def trade(pnl, r, reason="SL", year=2024, **kw):
    d = {"symbol": "X", "pnl": pnl, "r_multiple": r, "reason": reason, "year": year,
         "entry_date": f"{year}-01-02", "exit_date": f"{year}-06-01"}
    d.update(kw)
    return d


def crash_frame():
    """Uptrend long enough to trigger entries, then a fall steep enough to take out
    a stop before the time-stop can fire — the only way the SL path gets exercised."""
    np = backtest.ta.np
    n_up, n_dn = 300, 20
    idx = pd.date_range("2022-01-03", periods=n_up + n_dn, freq="B")
    base = np.concatenate([np.linspace(100, 240, n_up), np.linspace(240, 144, n_dn)])
    close = pd.Series(base + np.sin(np.arange(len(base)) / 7) * 4, index=idx)
    return pd.DataFrame({"Open": close.shift(1).fillna(close.iloc[0]),
                         "High": close + 2.0, "Low": close - 2.0, "Close": close,
                         "Volume": pd.Series([1000] * len(idx), index=idx)}, index=idx)


def test_buy_and_hold():
    df = pd.DataFrame({"Close": [100.0, 110.0, 120.0]})
    bh = backtest.buy_and_hold(df)
    check("total return pct", approx(bh["total_return_pct"], 20.0))
    check("no drawdown on a monotonic rise", approx(bh["max_dd_pct"], 0.0))

    df = pd.DataFrame({"Close": [100.0, 50.0, 75.0]})
    bh = backtest.buy_and_hold(df)
    check("negative return", approx(bh["total_return_pct"], -25.0))
    check("drawdown from peak", approx(bh["max_dd_pct"], -50.0))

    df = pd.DataFrame({"Close": [100.0, 200.0, 150.0, 400.0]})
    bh = backtest.buy_and_hold(df)
    check("dd measured off running peak", approx(bh["max_dd_pct"], -25.0))
    check("return still off the first bar", approx(bh["total_return_pct"], 300.0))


def test_summarize_empty():
    s = backtest.summarize([], 500000, {})
    check("no trades reported as zero", s["trades"] == 0)
    check("no-completed-trade note present", "no completed trades" in s["note"])
    check("no fabricated win rate", "win_rate_pct" not in s)


def test_summarize_core():
    trades = [trade(2000, 2.0, "TARGET"), trade(-1000, -1.0, "SL"),
              trade(1000, 1.0, "TARGET"), trade(-1000, -1.0, "SL")]
    s = backtest.summarize(trades, 100000, {"X": pd.Series([100000, 102000, 101000, 102000, 101000])})
    check("trade count", s["trades"] == 4)
    check("win rate", approx(s["win_rate_pct"], 50.0))
    check("avg win R", approx(s["avg_win_R"], 1.5))
    check("avg loss R", approx(s["avg_loss_R"], -1.0))
    check("expectancy is mean R", approx(s["expectancy_R"], 0.25))
    check("profit factor = gross win / gross loss", approx(s["profit_factor"], 1.5))
    check("total pnl", approx(s["total_pnl"], 1000))
    check("return on capital", approx(s["return_on_capital_pct"], 1.0))
    check("exit breakdown counts", s["exit_breakdown"] == {"TARGET": 2, "SL": 2})


def test_summarize_edges():
    s = backtest.summarize([trade(0, 0.0)], 100000, {"X": pd.Series([100000, 100000])})
    check("zero-pnl trade is not a win", approx(s["win_rate_pct"], 0.0))

    s = backtest.summarize([trade(500, 1.0), trade(700, 1.4)], 100000, {"X": pd.Series([100000, 100500, 101200])})
    check("no losses -> undefined profit factor, valid JSON", s["profit_factor"] is None)
    check("no losses -> avg_loss_R is unknown", s["avg_loss_R"] is None)

    s = backtest.summarize([trade(-500, -1.0)], 100000, {"X": pd.Series([99500])})
    check("no wins -> avg_win_R is unknown", s["avg_win_R"] is None)
    check("all losses -> profit factor 0", approx(s["profit_factor"], 0.0))

    s = backtest.summarize([trade(10000, 1.0), trade(-4000, -1.0), trade(-1000, -0.5)],
                           100000, {"X": pd.Series([100000, 110000, 106000, 105000])})
    check("equity drawdown off the running peak", approx(s["max_dd_on_equity_pct"], -4.55, 0.05))


def test_summarize_partial_year():
    this_year = date.today().year
    trades = [trade(100, 0.5, year=2023), trade(200, 1.0, year=this_year)]
    s = backtest.summarize(trades, 100000, {"X": pd.Series([100000, 100100, 100300])})
    check("closed year is plain", "2023" in s["by_year_pnl"])
    check("current year flagged partial",
          f"{this_year} (partial)" in s["by_year_pnl"],
          f"got {list(s['by_year_pnl'])}")
    check("partial flag on expectancy table too",
          f"{this_year} (partial)" in s["by_year_expectancy_R"])
    check("closed year not flagged", "2023 (partial)" not in s["by_year_pnl"])


def test_exit_reason():
    check("stop hit", backtest._exit_reason(
        {"ExitPrice": 95.0, "SL": 95.0, "TP": 120.0}) == "SL")
    check("target hit", backtest._exit_reason(
        {"ExitPrice": 120.0, "SL": 95.0, "TP": 120.0}) == "TARGET")
    check("neither -> signal", backtest._exit_reason(
        {"ExitPrice": 108.0, "SL": 95.0, "TP": 120.0}) == "SIGNAL/OTHER")
    check("float noise still counts as a stop", backtest._exit_reason(
        {"ExitPrice": 95.0000000001, "SL": 95.0, "TP": 120.0}) == "SL")
    check("trailed stop above entry is still SL", backtest._exit_reason(
        {"ExitPrice": 130.0, "SL": 130.0, "TP": 200.0}) == "SL")
    check("time stop at the limit", backtest._exit_reason(
        {"ExitPrice": 108.0, "SL": 95.0, "TP": 120.0, "EntryBar": 10, "ExitBar": 25},
        time_stop=15) == "TIME")
    check("held short of the limit is not TIME", backtest._exit_reason(
        {"ExitPrice": 108.0, "SL": 95.0, "TP": 120.0, "EntryBar": 10, "ExitBar": 24},
        time_stop=15) == "SIGNAL/OTHER")
    check("stop takes precedence over time", backtest._exit_reason(
        {"ExitPrice": 95.0, "SL": 95.0, "TP": 120.0, "EntryBar": 10, "ExitBar": 30},
        time_stop=15) == "SL")
    check("a stop gapped through at the open is still SL", backtest._exit_reason(
        {"ExitPrice": 91.0, "SL": 95.0, "TP": 120.0, "EntryBar": 10, "ExitBar": 30},
        time_stop=15) == "SL")
    check("a target gapped through at the open is still TARGET", backtest._exit_reason(
        {"ExitPrice": 125.0, "SL": 95.0, "TP": 120.0}) == "TARGET")
    check("missing SL/TP degrades, never raises", backtest._exit_reason(
        {"ExitPrice": 108.0, "SL": float("nan"), "TP": float("nan")}) == "SIGNAL/OTHER")


def test_load_ohlcv_source_contract():
    seen = {}

    def fake(sym, period, adjusted):
        seen.update(sym=sym, period=period, adjusted=adjusted)
        return "frame", []

    orig, backtest.prices.history_df = backtest.prices.history_df, fake
    try:
        backtest.load_ohlcv("RELIANCE", 5)
        check("unaliased symbol passes through", seen["sym"] == "RELIANCE")
        check("backtest asks for matching adjusted history", seen["period"] == "5y" and seen["adjusted"] is True)
    finally:
        backtest.prices.history_df = orig


def test_run_symbol_wiring():
    df = backtest._synth("up")
    trades = backtest.run_symbol(df, backtest.SELFTEST_SPEC, "SYNTH", 500000, 1.0)["trades"]
    check("an uptrend fires trades", len(trades) > 0, f"got {len(trades)}")
    if not trades:
        return
    t0 = trades[0]
    for f in ("symbol", "strategy", "entry_date", "entry", "sl", "target", "qty",
              "exit_date", "exit", "reason", "pnl", "r_multiple", "year"):
        check(f"trade carries {f}", f in t0)
    check("symbol tagged", t0["symbol"] == "SYNTH")
    check("strategy tagged", t0["strategy"] == backtest.SELFTEST_SPEC["name"])
    check("qty is a whole number of shares", isinstance(t0["qty"], int) and t0["qty"] > 0)
    check("stop sits below entry on a long", t0["sl"] < t0["entry"])
    check("exit is not before entry", all(t["exit_date"] >= t["entry_date"] for t in trades))
    check("year matches realized exit date",
          all(t["year"] == int(t["exit_date"][:4]) for t in trades))
    check("every exit is labelled",
          all(t["reason"] in ("SL", "TARGET", "TIME", "SIGNAL/OTHER") for t in trades))
    check("R sign agrees with P&L sign",
          all((t["r_multiple"] > 0) == (t["pnl"] > 0)
              for t in trades if t["pnl"] != 0 and t["r_multiple"] != 0))
    for t in trades:
        bar = df.loc[pd.Timestamp(t["entry_date"])]
        check(f"fill is at the bar open ({t['entry_date']})",
              approx(t["entry"], float(bar["Open"]), 0.01),
              f"entry {t['entry']} vs open {float(bar['Open']):.4f}")
        check(f"fill is NOT at the bar close ({t['entry_date']})",
              not approx(t["entry"], float(bar["Close"]), 0.01),
              f"entry {t['entry']} equals close {float(bar['Close']):.4f} — lookahead")
    check("no fill on the first bar", all(t["entry_date"] > str(df.index[0].date())
                                          for t in trades))
    rate = backtest.COMMISSION_PER_SIDE
    for t in trades:
        gross = (t["exit"] - t["entry"]) * t["qty"]
        expected = gross - (t["entry"] + t["exit"]) * t["qty"] * rate
        tol = max(1.0, t["qty"] * 0.02)
        check(f"P&L is net of both-side commission ({t['entry_date']})",
              approx(t["pnl"], expected, tol), f"net {t['pnl']} vs expected {expected:.2f}")
        check(f"net is worse than gross ({t['entry_date']})", t["pnl"] < gross)

    ts = backtest.SELFTEST_SPEC["exit"]["time_stop_sessions"]
    timed = [t for t in trades if t["reason"] == "TIME"]
    check("the time-stop fires", len(timed) > 0,
          f"reasons={sorted({t['reason'] for t in trades})}")
    for t in timed:
        held = len(df.loc[pd.Timestamp(t["entry_date"]):pd.Timestamp(t["exit_date"])]) - 1
        check(f"time exit fills the bar after the threshold ({t['entry_date']})",
              held == ts + 1, f"held {held} bars, time_stop={ts}")


def test_run_symbol_downtrend():
    df = backtest._synth("down")
    trades = backtest.run_symbol(df, backtest.SELFTEST_SPEC, "SYNTH", 500000, 1.0)["trades"]
    check("a long-only pullback spec takes no longs in a downtrend",
          len(trades) == 0, f"got {len(trades)}")


def test_run_symbol_stop_out():
    """The stop path, end to end: sizing, stop placement and costs at once."""
    capital, risk_pct = 500000.0, 1.0
    trades = backtest.run_symbol(crash_frame(), backtest.SELFTEST_SPEC, "SYNTH",
                                 capital, risk_pct)["trades"]
    stopped = [t for t in trades if t["reason"] == "SL"]
    check("a crash takes out the stop", len(stopped) > 0,
          f"reasons={[t['reason'] for t in trades]}")
    if not stopped:
        return
    t = stopped[0]
    check("stop-out exits AT the stop", approx(t["exit"], t["sl"], 1e-6))
    check("stop-out is a loss", t["pnl"] < 0)

    budget = capital * risk_pct / 100.0
    gross_risk = (t["entry"] - t["initial_stop"]) * t["qty"]
    check("position sized to the risk budget", approx(gross_risk, budget, budget * 0.01),
          f"risked {gross_risk:.0f} against a {budget:.0f} budget")
    check("never sized above the budget", gross_risk <= budget)

    check("stop-out is about -1R", approx(t["r_multiple"], -1.0, 0.1), f"R={t['r_multiple']}")
    check("costs make it worse than -1R, never better", t["r_multiple"] < -1.0)


def test_run_envelope():
    tmp = tempfile.mkdtemp()
    spec_path = os.path.join(tmp, "selftest.yml")
    yaml = backtest.ta._need("yaml", "pyyaml")
    with open(spec_path, "w") as fh:
        yaml.safe_dump(backtest.SELFTEST_SPEC, fh)

    orig = backtest.load_ohlcv
    backtest.load_ohlcv = lambda sym, years: (backtest._synth("up"), [])
    try:
        out = os.path.join(tmp, "report")
        env = backtest.run(spec_path, ["SYNTH1", "SYNTH2"], years=2, capital=500000,
                           risk_pct=1.0, out=out)
        for k in ("ok", "source", "fetched_at", "data", "gaps"):
            check(f"envelope has {k}", k in env)
        check("source names the module", env["source"] == "finance.compute.backtest")
        d = env["data"]
        check("ok when trades fired", env["ok"] is True)
        check("both symbols resolved", d["config"]["symbols_resolved"] == ["SYNTH1", "SYNTH2"])
        check("commission recorded in config",
              approx(d["config"]["commission_per_side"], backtest.COMMISSION_PER_SIDE, 1e-9))
        check("caveats ride with the numbers", len(d["caveats"]) == len(backtest.CAVEATS))
        check("buy-and-hold per symbol", set(d["buy_and_hold"]) == {"SYNTH1", "SYNTH2"})
        check("trade count is an int", isinstance(d["trades"], int) and d["trades"] > 0)

        check("summary file written", os.path.exists(d["summary_path"]))
        check("trades csv written", os.path.exists(d["trades_path"]))
        with open(d["summary_path"]) as fh:
            saved = json.load(fh)
        check("saved summary matches the envelope", saved["summary"] == d["summary"])
        equity = pd.read_csv(d["equity_path"], index_col="date")
        check("equity evidence contains both independent accounts", set(equity) == {"SYNTH1", "SYNTH2"})
        check("total capital includes both accounts", d["summary"]["total_initial_capital"] == 1000000)
        check("return and drawdown bases are labelled", "per-symbol" in d["summary"]["drawdown_basis"] and "idle" in d["summary"]["return_basis"])
        rows = pd.read_csv(d["trades_path"])
        check("csv row count matches", len(rows) == d["trades"])
        check("per-trade log stays on disk, not inline", "trades_log" not in d)
    finally:
        backtest.load_ohlcv = orig
        shutil.rmtree(tmp, ignore_errors=True)


def test_run_degrades():
    tmp = tempfile.mkdtemp()
    spec_path = os.path.join(tmp, "selftest.yml")
    yaml = backtest.ta._need("yaml", "pyyaml")
    with open(spec_path, "w") as fh:
        yaml.safe_dump(backtest.SELFTEST_SPEC, fh)

    orig = backtest.load_ohlcv

    def one_bad(sym, years):
        if sym == "BAD":
            raise RuntimeError("no data for BAD")
        return backtest._synth("up"), []

    try:
        backtest.load_ohlcv = one_bad
        env = backtest.run(spec_path, ["SYNTH1", "BAD"], years=2,
                           out=os.path.join(tmp, "r1"))
        check("a dead symbol does not abort the run", env["ok"] is True)
        check("the failure is a labelled gap",
              any("BAD" in g for g in env["gaps"]), f"gaps={env['gaps']}")
        check("the good symbol still produced trades", env["data"]["trades"] > 0)

        backtest.load_ohlcv = lambda sym, years: (backtest._synth("down"), [])
        env = backtest.run(spec_path, ["SYNTH1"], years=2, out=os.path.join(tmp, "r2"))
        check("no trades -> not ok", env["ok"] is False)
        check("no trades is called out as untested",
              any("untested" in g for g in env["gaps"]), f"gaps={env['gaps']}")
        check("summary still written for an empty run",
              os.path.exists(env["data"]["summary_path"]))
        check("no trades csv when nothing fired", env["data"]["trades_path"] is None)
    finally:
        backtest.load_ohlcv = orig
        shutil.rmtree(tmp, ignore_errors=True)


def test_caveats():
    check("caveats are non-empty", len(backtest.CAVEATS) >= 4)
    joined = " ".join(backtest.CAVEATS).lower()
    for word in ("survivorship", "in-sample", "portfolio", "mechanical"):
        check(f"caveat covers {word}", word in joined)
    check("commission is a per-side fraction", 0 < backtest.COMMISSION_PER_SIDE < 0.01)


def test_simulated_equity_accounting():
    from backtesting import Backtest
    original_run, original_load = Backtest.run, backtest.load_ohlcv
    engine = []
    def capture(self, **kwargs):
        stats = original_run(self, **kwargs)
        engine.append(stats)
        return stats
    Backtest.run = capture
    backtest.load_ohlcv = lambda sym, years: (backtest._synth("down") if sym == "IDLE" else crash_frame(), [])
    try:
        with tempfile.TemporaryDirectory() as tmp:
            spec_path = os.path.join(tmp, "spec.yml")
            with open(spec_path, "w") as stream:
                backtest.ta._need("yaml", "pyyaml").safe_dump(backtest.SELFTEST_SPEC, stream)
            env = backtest.run(spec_path, ["ONE", "TWO", "IDLE"], capital=500000, out=os.path.join(tmp, "report"))
            s = env["data"]["summary"]
            expected_return = sum(float(stats["Return [%]"]) for stats in engine) / 3
            expected_dd = min(float(stats["Max. Drawdown [%]"]) for stats in engine)
            check("return uses capital for every independently tested symbol including idle", approx(s["return_on_capital_pct"], expected_return, 0.051), (s, expected_return))
            check("drawdown is actual worst per-symbol marked equity", approx(s["max_dd_on_equity_pct"], expected_dd, 0.051), (s, expected_dd))
    finally:
        Backtest.run, backtest.load_ohlcv = original_run, original_load


def test_first_loss_drawdown():
    s = backtest.summarize([trade(-500, -1.0)], 100000, {"X": pd.Series([99500])})
    check("initial capital is a drawdown peak", approx(s["max_dd_on_equity_pct"], -0.5), s)

def test_exit_year_and_trade_order():
    trades = [trade(100, 0.5, year=2024, exit_date="2025-01-02"), trade(-50, -0.25, year=2023)]
    curves = {"X": pd.Series([100000, 99950, 100050])}
    s = backtest.summarize(trades, 100000, curves)
    check("cross-year trade belongs to realization year", s["by_year_pnl"] == {"2023": -50, "2025": 100}, s)
    check("trade enumeration cannot change equity statistics", s == backtest.summarize(trades[::-1], 100000, curves))
    missing = backtest.summarize([trade(100, None)], 100000, {"X": pd.Series([100000, 100100])})
    check("missing original risk cannot certify expectancy", missing["expectancy_R"] is None and missing["trades_missing_R"] == 1)
    json.dumps(missing, allow_nan=False)
    check("missing risk remains valid JSON", True)


def test_gapped_fill_uses_actual_risk():
    frame = backtest._synth("up")
    frame["Open"] = frame["Close"].shift(1).fillna(frame["Close"].iloc[0]) * 1.01
    frame["High"] = frame[["High", "Open"]].max(axis=1) + 1
    tested = backtest.run_symbol(frame, backtest.SELFTEST_SPEC, "GAP", 500000, 1.0)
    check("gap fixture produces trades", bool(tested["trades"]))
    for t in tested["trades"]:
        expected = t["pnl"] / ((t["entry"] - t["initial_stop"]) * t["qty"])
        check("R uses actual fill and original stop " + t["entry_date"], approx(t["r_multiple"], expected, 1e-10))

def test_run_input_and_output_boundaries():
    import unittest.mock as mock
    with tempfile.TemporaryDirectory() as tmp:
        spec_path = os.path.join(tmp, "spec.yml")
        with open(spec_path, "w") as stream:
            backtest.ta._need("yaml", "pyyaml").safe_dump(backtest.SELFTEST_SPEC, stream)
        for key, value in (("capital", float("nan")), ("capital", 0), ("years", 0), ("years", 1.5), ("risk_pct", 2)):
            try:
                with mock.patch.object(backtest, "load_ohlcv", side_effect=AssertionError("unexpected fetch")) as loader:
                    env = backtest.run(spec_path, ["TEST"], out=os.path.join(tmp, "invalid"), **{key: value})
                check(f"invalid {key}={value} rejects before data fetch", not loader.called and not env["ok"] and any("input" in g for g in env["gaps"]), env)
            except Exception as exc:
                check(f"invalid {key}={value} is an envelope, not a crash", False, str(exc))
        with mock.patch.object(backtest, "load_ohlcv", return_value=(backtest._synth("up"), [])):
            with mock.patch.object(backtest.universe, "resolve_symbols", return_value=(["ONE"], ["fixture stale universe"])):
                degraded = backtest.run(spec_path, "named-basket", out=os.path.join(tmp, "degraded"))
            check("backtest keeps the universe authority's gaps", "fixture stale universe" in degraded["gaps"] and degraded["data"]["config"]["symbols_resolved"] == ["ONE"])
            first = backtest.run(spec_path, ["ONE"], out=os.path.join(tmp, "report"))
            path = first["data"]["trades_path"]
            before = open(path, "rb").read()
            second = backtest.run(spec_path, ["TWO"], out=os.path.join(tmp, "report"))
            check("rerun preserves previous trade evidence", first["data"]["trades_path"] != second["data"]["trades_path"] and open(path, "rb").read() == before)
        with mock.patch.object(backtest, "load_ohlcv", return_value=(backtest._synth("up"), [])), mock.patch.object(backtest.os, "replace", side_effect=OSError("fixture disk failure")):
            try:
                env = backtest.run(spec_path, ["ONE"], out=os.path.join(tmp, "failed"))
                check("output failure preserves computed metrics and labels gap", env["ok"] and env["data"]["summary_path"] is None and bool(env["gaps"]))
            except Exception as exc:
                check("output failure is an envelope, not a crash", False, str(exc))

def test_last_bar_signal_cannot_fill_without_a_next_bar():
    frame = backtest._synth("up")
    frame.loc[frame.index[-1], "Volume"] = 1000000
    spec = {**backtest.SELFTEST_SPEC, "entry": {"signal": ["Volume > 999999"]}}
    result = backtest.run_symbol(frame, spec, "LAST", 500000, 1.0)
    check("last-bar signal has no next-open execution", result["equity"].iloc[-1] == 500000, result["equity"].iloc[-1])


def test_unfinished_position_is_marked_not_realized():
    frame = backtest._synth("up")
    frame.loc[frame.index[-2], "Volume"] = 1000000
    spec = {**backtest.SELFTEST_SPEC, "entry": {"signal": ["Volume > 999999"]}}
    result = backtest.run_symbol(frame, spec, "OPEN", 500000, 1.0)
    check("real next-open fill remains open at end", result["open_trades"] == 1, result)
    check("unclosed trade does not enter realized sample", result["trades"] == [])
    check("open mark affects actual equity", result["equity"].iloc[-1] != 500000)


def test_backtest_loader_uses_source_cache_not_undated_csv():
    import unittest.mock as mock
    from finance.sources import prices
    with tempfile.TemporaryDirectory() as cache:
        stale, current = backtest._synth("up"), backtest._synth("down")
        stale.to_csv(os.path.join(cache, "SYNTH_2y.csv"))
        with mock.patch.object(prices, "history_df", return_value=(current, ["fixture history degradation"])) as source:
            result = backtest.load_ohlcv("SYNTH", 2)
        check("backtest delegates to the source cache", source.called)
        check("loader retains source gaps", isinstance(result, tuple) and result[1] == ["fixture history degradation"])


def test_backtest_warmup_matches_live_atr_requirement():
    from finance.compute import strategy
    try:
        strategy.floor_stop(100, 99.5, float("nan"))
        floored = False
    except ValueError:
        floored = True
    check("a nonfinite ATR cannot silently skip the stop floor", floored)
    frame = backtest._synth("up")
    frame.loc[:, "Volume"] = 1000000
    spec = {**backtest.SELFTEST_SPEC, "entry": {"signal": ["Volume > 999999"]}}
    trades = backtest.run_symbol(frame, spec, "WARM", 500000, 1.0)["trades"]
    first = str(frame.index[14].date())
    check("no backtest entry before ATR14 exists (live would skip)",
          trades and all(t["entry_date"] > first for t in trades),
          [t["entry_date"] for t in trades[:3]])


run(globals())
