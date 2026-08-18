#!/usr/bin/env python3
"""Offline tests for the backtest engine. No network — OHLCV is synthetic and
deterministic, and `run` is exercised with its loader swapped out.

The engine decides whether a strategy is tradeable, so the wiring assertions below
(fill timing, cost inclusion, stop/target precedence, time-stop) matter as much as
the arithmetic: a silently wrong fill makes a losing spec look validated.

Run: python3 finance/tests/test_backtest.py
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import backtest
from finance.tests.harness import approx, check, run

pd = backtest.pd


def trade(pnl, r, reason="SL", year=2024, **kw):
    d = {"symbol": "X", "pnl": pnl, "r_multiple": r, "reason": reason, "year": year}
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


# --- universe resolution --------------------------------------------------- #
def test_resolve_universe():
    check("list passes through", backtest.resolve_universe(["TCS", "INFY"]) == ["TCS", "INFY"])
    check("comma string splits", backtest.resolve_universe("TCS,INFY") == ["TCS", "INFY"])
    check("whitespace trimmed", backtest.resolve_universe(" tcs , infy ") == ["TCS", "INFY"])
    check("lowercase upcased", backtest.resolve_universe(["tcs"]) == ["TCS"])
    check("empty entries dropped", backtest.resolve_universe("TCS,,INFY") == ["TCS", "INFY"])
    check("None -> empty", backtest.resolve_universe(None) == [])
    check("empty string -> empty", backtest.resolve_universe("") == [])
    basket = backtest.resolve_universe("largecap20")
    check("largecap20 expands", basket == backtest.LARGECAP20_BASKET)
    check("largecap20 case-insensitive", backtest.resolve_universe("LargeCap20") == basket)
    check("basket is 20 names", len(basket) == 20)
    check("basket has no duplicates", len(set(basket)) == 20)
    check("expansion is a copy, not the module list",
          backtest.resolve_universe("largecap20") is not backtest.LARGECAP20_BASKET)


# --- buy and hold ---------------------------------------------------------- #
def test_buy_and_hold():
    df = pd.DataFrame({"Close": [100.0, 110.0, 120.0]})
    bh = backtest.buy_and_hold(df)
    check("total return pct", approx(bh["total_return_pct"], 20.0))
    check("no drawdown on a monotonic rise", approx(bh["max_dd_pct"], 0.0))

    df = pd.DataFrame({"Close": [100.0, 50.0, 75.0]})
    bh = backtest.buy_and_hold(df)
    check("negative return", approx(bh["total_return_pct"], -25.0))
    check("drawdown from peak", approx(bh["max_dd_pct"], -50.0))

    # drawdown is measured from the running peak, not from the first bar
    df = pd.DataFrame({"Close": [100.0, 200.0, 150.0, 400.0]})
    bh = backtest.buy_and_hold(df)
    check("dd measured off running peak", approx(bh["max_dd_pct"], -25.0))
    check("return still off the first bar", approx(bh["total_return_pct"], 300.0))


# --- summary arithmetic ---------------------------------------------------- #
def test_summarize_empty():
    s = backtest.summarize([], 500000)
    check("no trades reported as zero", s["trades"] == 0)
    check("no-signal note present", "no signals" in s["note"])
    check("no fabricated win rate", "win_rate_pct" not in s)


def test_summarize_core():
    trades = [trade(2000, 2.0, "TARGET"), trade(-1000, -1.0, "SL"),
              trade(1000, 1.0, "TARGET"), trade(-1000, -1.0, "SL")]
    s = backtest.summarize(trades, 100000)
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
    # a scratch trade (pnl == 0) is a loss, never a win — the gate must not be gamed
    s = backtest.summarize([trade(0, 0.0)], 100000)
    check("zero-pnl trade is not a win", approx(s["win_rate_pct"], 0.0))

    s = backtest.summarize([trade(500, 1.0), trade(700, 1.4)], 100000)
    check("no losses -> infinite profit factor", s["profit_factor"] == float("inf"))
    check("no losses -> avg_loss_R is 0, not NaN", s["avg_loss_R"] == 0.0)

    s = backtest.summarize([trade(-500, -1.0)], 100000)
    check("no wins -> avg_win_R is 0, not NaN", s["avg_win_R"] == 0.0)
    check("all losses -> profit factor 0", approx(s["profit_factor"], 0.0))

    # equity drawdown runs on the cumulative curve, not on single trades
    s = backtest.summarize([trade(10000, 1.0), trade(-4000, -1.0), trade(-1000, -0.5)],
                           100000)
    check("equity drawdown off the running peak", approx(s["max_dd_on_equity_pct"], -4.55, 0.05))


def test_summarize_partial_year():
    this_year = date.today().year
    trades = [trade(100, 0.5, year=2023), trade(200, 1.0, year=this_year)]
    s = backtest.summarize(trades, 100000)
    check("closed year is plain", "2023" in s["by_year_pnl"])
    check("current year flagged partial",
          f"{this_year} (partial)" in s["by_year_pnl"],
          f"got {list(s['by_year_pnl'])}")
    check("partial flag on expectancy table too",
          f"{this_year} (partial)" in s["by_year_expectancy_R"])
    check("closed year not flagged", "2023 (partial)" not in s["by_year_pnl"])


# --- exit labelling -------------------------------------------------------- #
def test_exit_reason():
    check("stop hit", backtest._exit_reason(
        {"ExitPrice": 95.0, "SL": 95.0, "TP": 120.0}) == "SL")
    check("target hit", backtest._exit_reason(
        {"ExitPrice": 120.0, "SL": 95.0, "TP": 120.0}) == "TARGET")
    check("neither -> signal", backtest._exit_reason(
        {"ExitPrice": 108.0, "SL": 95.0, "TP": 120.0}) == "SIGNAL/OTHER")
    check("float noise still counts as a stop", backtest._exit_reason(
        {"ExitPrice": 95.0000000001, "SL": 95.0, "TP": 120.0}) == "SL")
    # a trailed stop can close a WINNER — the label is about mechanism, not P&L
    check("trailed stop above entry is still SL", backtest._exit_reason(
        {"ExitPrice": 130.0, "SL": 130.0, "TP": 200.0}) == "SL")
    check("time stop at the limit", backtest._exit_reason(
        {"ExitPrice": 108.0, "SL": 95.0, "TP": 120.0, "EntryBar": 10, "ExitBar": 25},
        time_stop=15) == "TIME")
    check("held short of the limit is not TIME", backtest._exit_reason(
        {"ExitPrice": 108.0, "SL": 95.0, "TP": 120.0, "EntryBar": 10, "ExitBar": 24},
        time_stop=15) == "SIGNAL/OTHER")
    # price levels win over the holding period: a stop that fired ON the time-stop bar
    # is a stop, not a time exit
    check("stop takes precedence over time", backtest._exit_reason(
        {"ExitPrice": 95.0, "SL": 95.0, "TP": 120.0, "EntryBar": 10, "ExitBar": 30},
        time_stop=15) == "SL")
    check("missing SL/TP degrades, never raises", backtest._exit_reason(
        {"ExitPrice": 108.0, "SL": float("nan"), "TP": float("nan")}) == "SIGNAL/OTHER")


# --- symbol aliasing ------------------------------------------------------- #
def test_load_ohlcv_alias():
    seen = {}

    def fake(sym, years, cache):
        seen["sym"] = sym
        return "frame"

    orig, backtest.ta.load_ohlcv = backtest.ta.load_ohlcv, fake
    try:
        backtest.load_ohlcv("RELIANCE", 5, "/tmp")
        check("unaliased symbol passes through", seen["sym"] == "RELIANCE")
        key = next(iter(backtest.SYMBOL_ALIASES))
        backtest.load_ohlcv(key, 5, "/tmp")
        check("aliased symbol resolves", seen["sym"] == backtest.SYMBOL_ALIASES[key])
    finally:
        backtest.ta.load_ohlcv = orig


# --- the engine wiring (Backtesting.py), on synthetic data ----------------- #
def test_run_symbol_wiring():
    df = backtest._synth("up")
    trades = backtest.run_symbol(df, backtest.SELFTEST_SPEC, "SYNTH", 500000, 1.0)
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
    check("year matches entry date",
          all(t["year"] == int(t["entry_date"][:4]) for t in trades))
    check("every exit is labelled",
          all(t["reason"] in ("SL", "TARGET", "TIME", "SIGNAL/OTHER") for t in trades))
    check("R sign agrees with P&L sign",
          all((t["r_multiple"] > 0) == (t["pnl"] > 0)
              for t in trades if t["pnl"] != 0 and t["r_multiple"] != 0))
    # Entries fill at the NEXT bar's OPEN. If they filled at the signal bar's close
    # the engine would be trading on information it could not have had — the error
    # that makes a worthless spec backtest beautifully. Open != Close in this frame,
    # so the two cases are distinguishable.
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
    # costs are inside every reported P&L — commission is charged on both sides, so
    # net = gross - (entry + exit) * qty * rate. An engine that reported gross would
    # make a marginal spec look tradeable.
    rate = backtest.COMMISSION_PER_SIDE
    for t in trades:
        gross = (t["exit"] - t["entry"]) * t["qty"]
        expected = gross - (t["entry"] + t["exit"]) * t["qty"] * rate
        # entry/exit are reported rounded to paise while P&L is computed on the raw
        # fills, so the residual scales with size — bound it rather than hide it
        tol = max(1.0, t["qty"] * 0.02)
        check(f"P&L is net of both-side commission ({t['entry_date']})",
              approx(t["pnl"], expected, tol), f"net {t['pnl']} vs expected {expected:.2f}")
        check(f"net is worse than gross ({t['entry_date']})", t["pnl"] < gross)

    # The time-stop must actually fire, not merely be configured. A grinding uptrend
    # reaches neither stop nor target, so the time-stop is the only thing that closes
    # these trades; if it silently never fires they just drift to the next signal.
    ts = backtest.SELFTEST_SPEC["exit"]["time_stop_sessions"]
    timed = [t for t in trades if t["reason"] == "TIME"]
    check("the time-stop fires", len(timed) > 0,
          f"reasons={sorted({t['reason'] for t in trades})}")
    # The threshold trips on bar `ts`, and the exit fills at the NEXT open — the same
    # no-lookahead rule entries obey — so a time exit lands ts+1 bars after entry.
    for t in timed:
        held = len(df.loc[pd.Timestamp(t["entry_date"]):pd.Timestamp(t["exit_date"])]) - 1
        check(f"time exit fills the bar after the threshold ({t['entry_date']})",
              held == ts + 1, f"held {held} bars, time_stop={ts}")


def test_run_symbol_downtrend():
    df = backtest._synth("down")
    trades = backtest.run_symbol(df, backtest.SELFTEST_SPEC, "SYNTH", 500000, 1.0)
    check("a long-only pullback spec takes no longs in a downtrend",
          len(trades) == 0, f"got {len(trades)}")


def test_run_symbol_stop_out():
    """The stop path, end to end: sizing, stop placement and costs at once."""
    capital, risk_pct = 500000.0, 1.0
    trades = backtest.run_symbol(crash_frame(), backtest.SELFTEST_SPEC, "SYNTH",
                                 capital, risk_pct)
    stopped = [t for t in trades if t["reason"] == "SL"]
    check("a crash takes out the stop", len(stopped) > 0,
          f"reasons={[t['reason'] for t in trades]}")
    if not stopped:
        return
    t = stopped[0]
    check("stop-out exits AT the stop", approx(t["exit"], t["sl"], 1e-6))
    check("stop-out is a loss", t["pnl"] < 0)

    # size comes from risk, not conviction: qty * (entry - sl) ~= capital * risk%
    budget = capital * risk_pct / 100.0
    gross_risk = (t["entry"] - t["sl"]) * t["qty"]
    check("position sized to the risk budget", approx(gross_risk, budget, budget * 0.01),
          f"risked {gross_risk:.0f} against a {budget:.0f} budget")
    check("never sized above the budget", gross_risk <= budget)

    # a stop-out is -1R by construction, and costs make it slightly worse
    check("stop-out is about -1R", approx(t["r_multiple"], -1.0, 0.1), f"R={t['r_multiple']}")
    check("costs make it worse than -1R, never better", t["r_multiple"] < -1.0)


# --- run(): envelope, artifacts, degradation ------------------------------- #
def test_run_envelope():
    tmp = tempfile.mkdtemp()
    spec_path = os.path.join(tmp, "selftest.yml")
    yaml = backtest.ta._need("yaml", "pyyaml")
    with open(spec_path, "w") as fh:
        yaml.safe_dump(backtest.SELFTEST_SPEC, fh)

    orig = backtest.load_ohlcv
    backtest.load_ohlcv = lambda sym, years, cache: backtest._synth("up")
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

    def one_bad(sym, years, cache):
        if sym == "BAD":
            raise RuntimeError("no data for BAD")
        return backtest._synth("up")

    try:
        backtest.load_ohlcv = one_bad
        env = backtest.run(spec_path, ["SYNTH1", "BAD"], years=2,
                           out=os.path.join(tmp, "r1"))
        check("a dead symbol does not abort the run", env["ok"] is True)
        check("the failure is a labelled gap",
              any("BAD" in g for g in env["gaps"]), f"gaps={env['gaps']}")
        check("the good symbol still produced trades", env["data"]["trades"] > 0)

        # a spec that never triggers must NOT read as a validated strategy
        backtest.load_ohlcv = lambda sym, years, cache: backtest._synth("down")
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


# --- the constants a report leans on --------------------------------------- #
def test_caveats():
    check("caveats are non-empty", len(backtest.CAVEATS) >= 4)
    joined = " ".join(backtest.CAVEATS).lower()
    for word in ("survivorship", "in-sample", "portfolio", "mechanical"):
        check(f"caveat covers {word}", word in joined)
    check("commission is a per-side fraction", 0 < backtest.COMMISSION_PER_SIDE < 0.01)


run(globals())
