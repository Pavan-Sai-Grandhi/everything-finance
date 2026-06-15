#!/usr/bin/env python3
"""Offline tests for the find-trade screen engine. No network.
Run: python3 skills/find-trade/scripts/test_screen.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import screen  # noqa: E402

pd = screen.pd
PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


def row(**kw):
    return pd.Series(kw, dtype=float)


# --- predicate evaluator --------------------------------------------------- #
def test_eval_filter():
    r = row(Close=110, ema50=100, rsi14=55, vol10=1000, Volume=1800, ema50_rising=1)
    check("bare truthy col", screen.eval_filter("ema50_rising", r))
    check("gt comparison", screen.eval_filter("Close > ema50", r))
    check("lt false", not screen.eval_filter("Close < ema50", r))
    check("between true", screen.eval_filter("rsi14 between 40 and 60", r))
    check("between false", not screen.eval_filter("rsi14 between 60 and 70", r))
    check("scalar-mul term", screen.eval_filter("Volume > 1.5 * vol10", r))   # 1800 > 1500
    check("scalar-mul false", not screen.eval_filter("Volume > 2 * vol10", r))  # 1800 < 2000
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


# --- build_signal ---------------------------------------------------------- #
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
    spec = {"exit": {"stop": "ema50_minus_2atr", "target": "next_resistance", "min_rrr": 1.5},
            "sizing": {"risk_per_trade_pct": 1.0}}
    sig = screen.build_signal(df, spec, capital=500000)
    # stop = ema50 - 2*atr = 95 - 4 = 91; risk = 9; target = 100 + 1.5*9 = 113.5
    check("stop = ema50-2atr", sig["stop"] == 91.0, str(sig))
    check("target = entry + minRRR*risk", sig["target"] == 113.5, str(sig))
    check("rrr == min", sig["rrr"] == 1.5)
    check("qty = risk budget / risk", sig["qty"] == int(5000 / 9), str(sig["qty"]))


def test_build_signal_measured_move():
    df = _ind_frame(close=100, ema50=95, ll20=90, hh20=130)
    spec = {"exit": {"stop": "range_low", "target": "measured_move", "min_rrr": 1.2},
            "sizing": {"risk_per_trade_pct": 1.0}}
    sig = screen.build_signal(df, spec, capital=500000)
    # stop = ll20 = 90; risk 10; measured move = hh20-ll20 = 40 -> target 140
    check("measured-move target", sig["target"] == 140.0, str(sig))
    check("target_basis labelled", sig["target_basis"] == "measured-move")


def test_build_signal_rejects_low_rrr():
    # A measured-move target whose move is small vs the stop distance -> RRR below
    # the gate. (next_resistance targets are defined AS entry + min_rrr*risk, so they
    # meet the gate tautologically; only price-derived targets can fail it.)
    df = _ind_frame(close=100, ema50=99, atr14=0.4, ll20=99, hh20=101)  # risk 1.8, move 2
    spec = {"exit": {"stop": "ema50_minus_2atr", "target": "measured_move", "min_rrr": 1.5},
            "sizing": {"risk_per_trade_pct": 1.0}}
    sig = screen.build_signal(df, spec, capital=500000)  # rrr = 2/1.8 = 1.11 < 1.5
    check("below min_rrr skipped", "skip" in sig and "RRR" in sig["skip"], str(sig))
    spec["exit"]["min_rrr"] = 1.0  # now 1.11 >= 1.0 -> passes
    check("at/above min_rrr passes", "skip" not in screen.build_signal(df, spec, 500000))


def test_build_signal_floors_tight_stop():
    # A swing-low stop a hair under entry (a squeeze/NR candle) must floor so the
    # risk denominator can't collapse toward zero and blow up the R-multiple.
    df = _ind_frame(close=100, ema50=95, atr14=3.0)
    df["Low"] = [99.9] * len(df)            # swing low only 0.1% under entry
    spec = {"exit": {"stop": "recent_swing_low", "target": "next_resistance", "min_rrr": 1.5},
            "sizing": {"risk_per_trade_pct": 1.0}}
    sig = screen.build_signal(df, spec, capital=500000)
    # floor = max(0.5*atr=1.5, 1% of 100=1.0) = 1.5 -> stop 98.5, risk 1.5 (not 0.1)
    check("tight stop floored to entry-0.5atr", sig["stop"] == 98.5, str(sig))
    check("risk_per_share floored, not ~0", sig["risk_per_share"] == 1.5, str(sig))


def test_exit_signal_series():
    # The discretionary-exit grammar (entry's), e.g. a mean-reversion close back
    # above the 5-SMA — fires only on the bars where the condition holds.
    df = _ind_frame(close=100, ema50=95)
    df["sma5"] = [98, 99, 101, 102] + [100] * 8     # Close 100 > sma5 only at bars 0,1
    fires = list(screen.strategy.exit_signal_series(df, {"exit": {"exit_signal": "Close > sma5"}}))
    check("exit_signal fires where Close>sma5", fires[:4] == [True, True, False, False], str(fires[:4]))
    check("no exit_signal -> never fires",
          not screen.strategy.exit_signal_series(df, {"exit": {}}).any())


def test_build_signal_rejects_wide_stop():
    df = _ind_frame(close=100, ema50=80, atr14=20)  # stop 40 -> 60% risk, too wide
    spec = {"exit": {"stop": "ema50_minus_2atr", "target": "measured_move", "min_rrr": 1.0},
            "sizing": {"risk_per_trade_pct": 1.0}}
    check("too-wide stop skipped", "skip" in screen.build_signal(df, spec, 500000))


# --- screen_compute end to end (synthetic loader) -------------------------- #
def test_screen_compute_discriminates():
    res = screen.screen_compute(["UPTREND", "DOWNTREND"], screen.SELFTEST_SPEC, 2,
                                500000, "/tmp", loader=lambda s: screen._synth(s.lower()))
    names = [c["symbol"] for c in res["candidates"]]
    check("uptrend selected", names == ["UPTREND"], str(names))
    check("downtrend rejected", any(r["symbol"] == "DOWNTREND" for r in res["rejected"]))


def test_screen_compute_handles_loader_failure():
    def bad(sym):
        if sym == "BAD":
            raise RuntimeError("no data")
        return screen._synth("uptrend")
    res = screen.screen_compute(["BAD", "GOOD"], screen.SELFTEST_SPEC, 2, 500000, "/tmp",
                                loader=bad)
    check("failed symbol -> data gap", any("BAD" in g for g in res["data_gaps"]))
    check("good symbol still screened", any(c["symbol"] == "GOOD" for c in res["candidates"]))


def main():
    for fn in sorted(g for g in globals() if g.startswith("test_")):
        print(f"\n[{fn}]")
        globals()[fn]()
    print(f"\n{'='*48}\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
