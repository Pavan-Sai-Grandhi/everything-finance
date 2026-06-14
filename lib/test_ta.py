#!/usr/bin/env python3
"""Offline unit tests for the shared TA module. No network — every fixture is
synthetic and deterministic. Run: python3 lib/test_ta.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ta  # noqa: E402

pd = ta.pd
np = ta.np

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


def frame(closes, highs=None, lows=None, opens=None, vols=None):
    """Build an OHLCV frame from plain lists. Columns are assigned positionally
    (lists, not Series) so nothing gets reindexed against the date index."""
    closes = [float(c) for c in closes]
    n = len(closes)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    opens = list(opens) if opens is not None else [closes[0]] + closes[:-1]
    highs = list(highs) if highs is not None else [c + 1 for c in closes]
    lows = list(lows) if lows is not None else [c - 1 for c in closes]
    vols = list(vols) if vols is not None else [1000] * n
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows,
                         "Close": closes, "Volume": vols}, index=idx)


# --- moving averages ------------------------------------------------------- #
def test_sma_ema():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    check("sma(3) last == 4", ta.sma(s, 3).iloc[-1] == 4.0)
    check("sma(3) warmup NaN", pd.isna(ta.sma(s, 3).iloc[0]))
    # TA-Lib EMA: warmup NaN until the SMA seed at index span-1, then recursive
    # e_t = a*x + (1-a)*e_{t-1}, a=2/(span+1). Seed at idx2 = SMA([1,2,3]) = 2.
    e = ta.ema(s, 3)
    check("ema(3) warmup NaN", pd.isna(e.iloc[0]) and pd.isna(e.iloc[1]))
    check("ema(3) seed == SMA3", abs(e.iloc[2] - 2.0) < 1e-9, f"{e.iloc[2]}")
    a = 2 / 4
    manual = 2.0  # talib seed
    for x in [4, 5]:
        manual = a * x + (1 - a) * manual
    check("ema(3) recursive from seed matches", abs(e.iloc[-1] - manual) < 1e-9,
          f"{e.iloc[-1]} vs {manual}")


def test_slope_up():
    rising = pd.Series(range(10), dtype=float)
    check("slope_up all rising", bool(ta.slope_up(rising, 5).iloc[-1]))
    falling = pd.Series(range(10, 0, -1), dtype=float)
    check("slope_up falling false", not bool(ta.slope_up(falling, 5).iloc[-1]))


# --- RSI ------------------------------------------------------------------- #
def test_rsi_bounds_and_extremes():
    up = pd.Series(np.linspace(100, 200, 60))
    r = ta.rsi(up, 14)
    check("rsi monotonic-up near 100", r.iloc[-1] > 95, f"{r.iloc[-1]}")
    down = pd.Series(np.linspace(200, 100, 60))
    check("rsi monotonic-down near 0", ta.rsi(down, 14).iloc[-1] < 5)
    flat = pd.Series([100.0] * 60)
    check("rsi flat == 50", abs(ta.rsi(flat, 14).iloc[-1] - 50) < 1e-6)
    check("rsi within [0,100]", r.dropna().between(0, 100).all())


# --- ATR / true range ------------------------------------------------------ #
def test_atr():
    df = frame([10, 11, 12, 13, 14, 15],
               highs=[11, 12, 13, 14, 15, 16], lows=[9, 10, 11, 12, 13, 14])
    tr = ta.true_range(df)
    # bar 1: max(H-L=2, |H-Cprev|=|12-10|=2, |L-Cprev|=0)=2
    check("true_range bar1 == 2", abs(tr.iloc[1] - 2) < 1e-9, f"{tr.iloc[1]}")
    check("atr(3) defined after warmup", not pd.isna(ta.atr(df, 3).iloc[-1]))


# --- levels / volume / RS -------------------------------------------------- #
def test_rolling_high_excludes_current():
    s = pd.Series([1, 5, 2, 8, 3], dtype=float)
    hh = ta.rolling_high(s, 2, exclude_current=True)
    # at idx 3 (value 8), prior-2 high over idx1..2 = max(5,2)=5, shifted
    check("rolling_high excludes current", hh.iloc[3] == 5.0, f"{hh.iloc[3]}")


def test_relative_strength():
    idx = pd.date_range("2024-01-01", periods=130, freq="B")
    stock = pd.Series(np.linspace(100, 150, 130), index=idx)   # +50%
    bench = pd.Series(np.linspace(100, 110, 130), index=idx)   # +10%
    rs = ta.relative_strength(stock, bench, lookback=126)
    check("RS positive when outperforming", rs.iloc[-1] > 0.3, f"{rs.iloc[-1]}")


def test_fib_levels():
    f = ta.fib_levels(100, 200)
    check("fib 0.5 == 150", f["0.5"] == 150.0)
    check("fib 0.618 below 0.5", f["0.618"] < f["0.5"])
    check("fib 1.618 ext above high", f["1.618_ext"] > 200)


# --- patterns -------------------------------------------------------------- #
def test_bullish_engulfing():
    # bar0 red (open 10 close 8), bar1 green engulfing (open 7 close 11)
    df = frame([8, 11], highs=[11, 12], lows=[7, 6], opens=[10, 7])
    check("bullish_engulfing fires", bool(ta.bullish_engulfing(df).iloc[1]))


def test_hammer():
    # small body up top, long lower wick
    df = frame([10.2], highs=[10.3], lows=[8.0], opens=[10.0])
    check("hammer fires", bool(ta.hammer(df).iloc[0]))
    # tall body, no wick -> not a hammer
    df2 = frame([12], highs=[12.1], lows=[10], opens=[10])
    check("non-hammer rejected", not bool(ta.hammer(df2).iloc[0]))


def test_inside_and_nr():
    df = frame([10, 10, 10, 10], highs=[20, 15, 14, 13], lows=[1, 5, 6, 7])
    check("inside_bar fires when range contracts", bool(ta.inside_bar(df).iloc[1]))
    # narrowest range of last 4 should be the last bar (13-7=6)
    nr4 = ta.nr(df, 4)
    check("nr4 marks narrowest bar", bool(nr4.iloc[3]), f"{nr4.tolist()}")


# --- feature registry ------------------------------------------------------ #
def test_features_materialize():
    df = frame([10, 10, 10, 10], highs=[20, 15, 14, 13], lows=[1, 5, 6, 7])
    # registry resolves nr7/inside_bar by name; only requested features attach
    out = ta.materialize(df, ["inside_bar", "nr4"])
    check("materialize adds inside_bar col", "inside_bar" in out.columns)
    check("materialize adds nr4 col", "nr4" in out.columns)
    check("materialize skips unrequested", "engulfing" not in out.columns)
    check("materialize matches direct inside_bar",
          bool(out["inside_bar"].iloc[1]) == bool(ta.inside_bar(df).iloc[1]))
    check("materialize ignores unknown name", "bogus" not in
          ta.materialize(df, ["bogus"]).columns)
    check("materialize does not mutate input", "inside_bar" not in df.columns)


# --- parameterized indicator resolver -------------------------------------- #
def test_parameterized_features():
    closes = list(np.linspace(100, 160, 80))
    df = frame(closes, vols=list(range(1000, 1080)))
    # is_feature: registered names, parameterized tokens, and non-features
    check("is_feature registered", ta.is_feature("golden_cross"))
    check("is_feature parameterized ema100", ta.is_feature("ema100"))
    check("is_feature rising suffix", ta.is_feature("ema21_rising"))
    check("is_feature rejects column", not ta.is_feature("Close"))
    check("is_feature rejects bogus", not ta.is_feature("foobar"))
    # parameterized resolution matches the direct call
    check("ema50 token == ema(50)",
          abs(ta.feature_series(df, "ema50").iloc[-1]
              - ta.ema(df["Close"], 50).iloc[-1]) < 1e-9)
    check("hh50 token == rolling_high(50)",
          ta.feature_series(df, "hh50").iloc[-1] == ta.rolling_high(df["High"], 50).iloc[-1])
    check("rsi9 token == rsi(9)",
          abs(ta.feature_series(df, "rsi9").iloc[-1] - ta.rsi(df["Close"], 9).iloc[-1]) < 1e-9)
    check("nr5 token == nr(5)",
          bool(ta.feature_series(df, "nr5").iloc[-1]) == bool(ta.nr(df, 5).iloc[-1]))
    check("ema21_rising is boolean slope",
          bool(ta.feature_series(df, "ema21_rising").iloc[-1])
          == bool(ta.slope_up(ta.ema(df["Close"], 21), 5).iloc[-1]))
    # materialize attaches parameterized columns on demand
    out = ta.materialize(df, ["ema100", "rsi9", "adx14"])
    check("materialize adds ema100", "ema100" in out.columns)
    check("materialize adds rsi9", "rsi9" in out.columns)
    check("materialize adds adx14", "adx14" in out.columns)


# --- derived signals ------------------------------------------------------- #
def test_derived_signals():
    down = list(np.linspace(200, 100, 60))
    check("rsi_oversold fires on downtrend", bool(ta.rsi_oversold(frame(down)).iloc[-1]))
    up = list(np.linspace(100, 200, 60))
    check("rsi_overbought fires on uptrend", bool(ta.rsi_overbought(frame(up)).iloc[-1]))
    # a strong step makes a fresh 20-day high (High = Close+1, step 4 > 1)
    steps = list(range(0, 240, 4))
    check("new_high_20 fires on breakout", bool(ta.new_high_20(frame(steps)).iloc[-1]))
    # volume surge on the last bar
    vols = [1000] * 39 + [3000]
    check("volume_surge fires on spike", bool(ta.volume_surge(frame(up[:40], vols=vols)).iloc[-1]))
    # golden/death cross logic (small periods so the fixture stays readable)
    flip_up = frame([10] * 6 + [20] * 6)
    check("golden_cross fires on up-flip", int(ta.golden_cross(flip_up, fast=3, slow=5).sum()) >= 1)
    flip_dn = frame([20] * 6 + [10] * 6)
    check("death_cross fires on down-flip", int(ta.death_cross(flip_dn, fast=3, slow=5).sum()) >= 1)
    # macd bullish cross on a V-shaped reversal
    v = list(np.linspace(120, 80, 40)) + list(np.linspace(80, 140, 40))
    check("macd_bullish_cross fires on V", int(ta.macd_bullish_cross(frame(v)).sum()) >= 1)


# --- bearish / range patterns ---------------------------------------------- #
def test_bearish_and_range_patterns():
    # bar0 green (open 8 close 11), bar1 red engulfing (open 12 close 7)
    be = frame([11, 7], highs=[12, 13], lows=[7, 6], opens=[8, 12])
    check("bearish_engulfing fires", bool(ta.bearish_engulfing(be).iloc[1]))
    # small body near the low, long upper shadow
    ss = frame([10.0], highs=[12.5], lows=[9.9], opens=[10.2])
    check("shooting_star fires", bool(ta.shooting_star(ss).iloc[0]))
    # outside bar: higher high and lower low than prior
    ob = frame([10, 10], highs=[10, 12], lows=[5, 4])
    check("outside_bar fires", bool(ta.outside_bar(ob).iloc[1]))
    # doji: open == close, body negligible vs range
    dj = frame([10.0], highs=[11.0], lows=[9.0], opens=[10.0])
    check("doji fires", bool(ta.doji(dj).iloc[0]))


# --- bundle ---------------------------------------------------------------- #
def test_add_indicators():
    closes = list(np.linspace(100, 130, 60))
    df = frame(closes, highs=[c + 1 for c in closes], lows=[c - 1 for c in closes],
               vols=list(range(1000, 1060)))
    out = ta.add_indicators(df)
    for col in ["ema20", "ema50", "sma200", "ema50_rising", "rsi14", "vol10",
                "atr14", "hh20", "ll20"]:
        check(f"add_indicators has {col}", col in out.columns)
    check("ema50 rising on uptrend", bool(out["ema50_rising"].iloc[-1]))
    check("add_indicators does not mutate input", "ema20" not in df.columns)


def main():
    for fn in sorted(g for g in globals() if g.startswith("test_")):
        print(f"\n[{fn}]")
        globals()[fn]()
    print(f"\n{'='*48}\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
