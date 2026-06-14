#!/usr/bin/env python3
"""Shared technical-analysis primitives for the everything-finance plugin.

One definition of every indicator and candlestick pattern, imported by every
skill that computes them (`backtest`, `find-trade`, the `technical-analyst`
agent) so they agree by construction. Numeric indicators delegate to TA-Lib,
whose native library must be present (macOS: `brew install ta-lib`) — bootstrapped
by `_need_talib()`. Candlestick/range patterns stay pure-pandas and geometric.

Import from a skill script (skills/<name>/scripts/<x>.py):

    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "..", "lib"))
    import ta

Input is a DataFrame with Open/High/Low/Close/Volume on a DatetimeIndex.
Indicators return a Series aligned to it (NaN until the lookback fills); pattern
functions return a boolean Series. Nothing mutates its input. Offline-testable
except the cache-first yfinance loader (test_ta.py).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys


def _need(mod, pip_name=None):
    """Import `mod`, pip-installing it (PEP 668 override) on first miss."""
    try:
        return __import__(mod)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                               "--break-system-packages", pip_name or mod])
        return __import__(mod)


def _need_talib():
    """Import TA-Lib, bootstrapping the native lib + wrapper if missing. The wheel
    needs the TA-Lib C library at build time; on Homebrew we install the keg and
    point the build at it, else we raise an actionable error."""
    try:
        import talib
        return talib
    except ImportError:
        pass
    import shutil
    env = os.environ.copy()
    if shutil.which("brew"):
        try:
            prefix = subprocess.check_output(["brew", "--prefix", "ta-lib"],
                                             text=True).strip()
        except subprocess.CalledProcessError:
            subprocess.check_call(["brew", "install", "ta-lib"])
            prefix = subprocess.check_output(["brew", "--prefix", "ta-lib"],
                                             text=True).strip()
        env["TA_INCLUDE_PATH"] = f"{prefix}/include"
        env["TA_LIBRARY_PATH"] = f"{prefix}/lib"
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                               "--break-system-packages", "TA-Lib"], env=env)
        import talib
        return talib
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "TA-Lib could not be imported or built. Install the native library "
            "first (macOS: `brew install ta-lib`; Debian/Ubuntu: build from "
            "https://ta-lib.org), then `pip install --break-system-packages "
            f"TA-Lib`. Underlying error: {exc}") from exc


pd = _need("pandas")
np = _need("numpy")
talib = _need_talib()


def _np(series):
    """Series -> contiguous float64 ndarray (what TA-Lib expects)."""
    return np.ascontiguousarray(series.to_numpy(dtype="float64"))


def _ser(arr, index):
    """TA-Lib ndarray output -> Series realigned to the source index."""
    return pd.Series(arr, index=index)


# --------------------------------------------------------------------------- #
# Moving averages & trend                                                      #
# --------------------------------------------------------------------------- #
def sma(series, span):
    """Simple moving average (TA-Lib SMA)."""
    return _ser(talib.SMA(_np(series), timeperiod=span), series.index)


def ema(series, span):
    """Exponential moving average (TA-Lib EMA — SMA-seeded over the first `span`
    values, then recursive with a=2/(span+1)). The charting-standard EMA."""
    return _ser(talib.EMA(_np(series), timeperiod=span), series.index)


def slope_up(series, lookback=5):
    """True where the series is higher than `lookback` bars ago — the 'rising'
    trend filter (e.g. ema50 rising)."""
    return series > series.shift(lookback)


# --------------------------------------------------------------------------- #
# Momentum & volatility                                                        #
# --------------------------------------------------------------------------- #
def rsi(close, period=14):
    """Wilder's RSI (TA-Lib). TA-Lib returns 0 for a perfectly flat window; we map
    only that degenerate no-change case to a neutral 50 (a real downtrend also
    reads near 0 and is left untouched)."""
    out = _ser(talib.RSI(_np(close), timeperiod=period), close.index)
    flat = close.diff().abs().rolling(period).sum() == 0
    return out.mask(flat, 50.0)


def macd(close, fast=12, slow=26, signal=9):
    """MACD line, signal line, histogram (TA-Lib MACD, classic 12/26/9)."""
    m, s, h = talib.MACD(_np(close), fastperiod=fast, slowperiod=slow,
                         signalperiod=signal)
    return pd.DataFrame({"macd": _ser(m, close.index),
                         "signal": _ser(s, close.index),
                         "hist": _ser(h, close.index)})


def true_range(df):
    """Wilder true range = max(H-L, |H-Cprev|, |L-Cprev|) (TA-Lib TRANGE; first
    bar NaN)."""
    return _ser(talib.TRANGE(_np(df["High"]), _np(df["Low"]), _np(df["Close"])),
                df.index)


def atr(df, period=14):
    """Average true range (TA-Lib ATR, Wilder's smoothing) — for stop placement."""
    return _ser(talib.ATR(_np(df["High"]), _np(df["Low"]), _np(df["Close"]),
                          timeperiod=period), df.index)


def bollinger(close, period=20, mult=2.0):
    """Bollinger bands -> DataFrame(mid, upper, lower) (TA-Lib BBANDS)."""
    up, mid, low = talib.BBANDS(_np(close), timeperiod=period,
                                nbdevup=mult, nbdevdn=mult)
    return pd.DataFrame({"mid": _ser(mid, close.index),
                         "upper": _ser(up, close.index),
                         "lower": _ser(low, close.index)})


def adx(df, period=14):
    """Average directional index (TA-Lib ADX) — trend strength, 0-100 (>25 trending)."""
    return _ser(talib.ADX(_np(df["High"]), _np(df["Low"]), _np(df["Close"]),
                          timeperiod=period), df.index)


def stochastic(df, k=14, d=3):
    """Slow stochastic -> DataFrame(stoch_k, stoch_d) (TA-Lib STOCH)."""
    sk, sd = talib.STOCH(_np(df["High"]), _np(df["Low"]), _np(df["Close"]),
                         fastk_period=k, slowk_period=d, slowk_matype=0,
                         slowd_period=d, slowd_matype=0)
    return pd.DataFrame({"stoch_k": _ser(sk, df.index),
                         "stoch_d": _ser(sd, df.index)})


def obv(df):
    """On-balance volume (TA-Lib OBV) — cumulative volume flow."""
    return _ser(talib.OBV(_np(df["Close"]), _np(df["Volume"])), df.index)


# --------------------------------------------------------------------------- #
# Levels, volume, relative strength                                           #
# --------------------------------------------------------------------------- #
def rolling_high(series, span, exclude_current=True):
    """Highest value over `span` bars. exclude_current shifts by 1 so a
    'break above the prior N-day high' test doesn't compare today to itself."""
    h = series.rolling(span).max()
    return h.shift(1) if exclude_current else h


def rolling_low(series, span, exclude_current=True):
    low = series.rolling(span).min()
    return low.shift(1) if exclude_current else low


def vol_avg(volume, span=10):
    """Average volume over `span` bars — the confirmation baseline."""
    return volume.rolling(span).mean()


def relative_strength(close, benchmark_close, lookback=126):
    """Price return over `lookback` bars minus the benchmark's over the same
    window (default ~6 months). Positive => outperforming. Benchmark is aligned
    to the stock's index by reindex+ffill so calendars need not match exactly."""
    bench = benchmark_close.reindex(close.index).ffill()
    stock_ret = close / close.shift(lookback) - 1
    bench_ret = bench / bench.shift(lookback) - 1
    return stock_ret - bench_ret


def fib_levels(swing_low, swing_high):
    """Retracement levels of an up-leg (entry zones) + common extensions
    (targets). Returns a dict keyed by ratio."""
    rng = swing_high - swing_low
    return {
        "0.0": swing_high,
        "0.382": swing_high - 0.382 * rng,
        "0.5": swing_high - 0.5 * rng,
        "0.618": swing_high - 0.618 * rng,
        "1.0": swing_low,
        "1.272_ext": swing_high + 0.272 * rng,
        "1.618_ext": swing_high + 0.618 * rng,
    }


# --------------------------------------------------------------------------- #
# Candlestick / range patterns (boolean Series — geometric, not TA-Lib CDL)   #
# --------------------------------------------------------------------------- #
def _body(df):
    return (df["Close"] - df["Open"]).abs()


def bullish_engulfing(df):
    """Today's green body fully engulfs yesterday's red body."""
    prev_red = df["Close"].shift(1) < df["Open"].shift(1)
    today_green = df["Close"] > df["Open"]
    engulf = (df["Close"] >= df["Open"].shift(1)) & (df["Open"] <= df["Close"].shift(1))
    return prev_red & today_green & engulf


def hammer(df):
    """Small body near the top, long lower shadow >= 2x body, short upper shadow
    — a reversal candle that only matters at support (caller checks location)."""
    body = _body(df)
    lower = df[["Open", "Close"]].min(axis=1) - df["Low"]
    upper = df["High"] - df[["Open", "Close"]].max(axis=1)
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    return (lower >= 2 * body) & (upper <= body) & (body / rng < 0.4)


def piercing(df):
    """Yesterday red; today opens below yest low and closes back above the
    midpoint of yesterday's body."""
    prev_red = df["Close"].shift(1) < df["Open"].shift(1)
    mid = (df["Open"].shift(1) + df["Close"].shift(1)) / 2
    return prev_red & (df["Open"] < df["Low"].shift(1)) & (df["Close"] > mid) & \
        (df["Close"] < df["Open"].shift(1))


def bullish_reversal(df):
    """Any of the bullish reversal candles we screen on — convenience union."""
    return bullish_engulfing(df) | hammer(df) | piercing(df)


def bearish_engulfing(df):
    """Today's red body fully engulfs yesterday's green body."""
    prev_green = df["Close"].shift(1) > df["Open"].shift(1)
    today_red = df["Close"] < df["Open"]
    engulf = (df["Open"] >= df["Close"].shift(1)) & (df["Close"] <= df["Open"].shift(1))
    return prev_green & today_red & engulf


def shooting_star(df):
    """Small body near the low, long upper shadow >= 2x body — the bearish mirror
    of the hammer (matters at resistance; caller checks location)."""
    body = _body(df)
    upper = df["High"] - df[["Open", "Close"]].max(axis=1)
    lower = df[["Open", "Close"]].min(axis=1) - df["Low"]
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    return (upper >= 2 * body) & (lower <= body) & (body / rng < 0.4)


def dark_cloud_cover(df):
    """Yesterday green; today opens above yest high and closes below the midpoint
    of yesterday's body (bearish mirror of piercing)."""
    prev_green = df["Close"].shift(1) > df["Open"].shift(1)
    mid = (df["Open"].shift(1) + df["Close"].shift(1)) / 2
    return prev_green & (df["Open"] > df["High"].shift(1)) & (df["Close"] < mid) & \
        (df["Close"] > df["Open"].shift(1))


def doji(df):
    """Open and close near-equal — body <= 10% of the bar's range (indecision)."""
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    return _body(df) / rng <= 0.1


def bearish_reversal(df):
    """Any of the bearish reversal candles — convenience union."""
    return bearish_engulfing(df) | shooting_star(df) | dark_cloud_cover(df)


def inside_bar(df):
    """Today's range is inside yesterday's (high lower, low higher) — a
    volatility-contraction / coil bar."""
    return (df["High"] < df["High"].shift(1)) & (df["Low"] > df["Low"].shift(1))


def outside_bar(df):
    """Today's range engulfs yesterday's (higher high and lower low) — an
    expansion / engulfing-range bar."""
    return (df["High"] > df["High"].shift(1)) & (df["Low"] < df["Low"].shift(1))


def nr(df, n):
    """NR-n: today's high-low range is the narrowest of the last n bars — a
    volatility squeeze that often precedes an expansion move. nr(df,4)=NR4,
    nr(df,7)=NR7."""
    rng = df["High"] - df["Low"]
    return rng == rng.rolling(n).min()


def coil_breakout(df, valid_for=3):
    """Today's close breaks above the high of a recent coil bar (inside-bar or
    NR7). The coil high stays a live trigger for `valid_for` sessions, so the
    breakout must come promptly — the entry trigger volatility-breakout strategies
    need that a single-bar column comparison can't express."""
    coil = inside_bar(df) | nr(df, 7)
    coil_high = df["High"].where(coil).shift(1).ffill(limit=valid_for)
    return df["Close"] > coil_high


# --------------------------------------------------------------------------- #
# Derived signals (boolean) — common cross/threshold/breakout events           #
# --------------------------------------------------------------------------- #
def _cross_up(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))


def golden_cross(df, fast=50, slow=200):
    """50-SMA crosses above the 200-SMA on this bar (the classic regime flip)."""
    return _cross_up(sma(df["Close"], fast), sma(df["Close"], slow))


def death_cross(df, fast=50, slow=200):
    """50-SMA crosses below the 200-SMA on this bar."""
    return _cross_up(sma(df["Close"], slow), sma(df["Close"], fast))


def above_sma200(df):
    return df["Close"] > sma(df["Close"], 200)


def below_sma200(df):
    return df["Close"] < sma(df["Close"], 200)


def macd_bullish_cross(df):
    """MACD line crosses above its signal line."""
    m = macd(df["Close"])
    return _cross_up(m["macd"], m["signal"])


def macd_bearish_cross(df):
    m = macd(df["Close"])
    return _cross_up(m["signal"], m["macd"])


def macd_above_zero(df):
    return macd(df["Close"])["macd"] > 0


def rsi_oversold(df, period=14, level=30):
    return rsi(df["Close"], period) < level


def rsi_overbought(df, period=14, level=70):
    return rsi(df["Close"], period) > level


def bb_squeeze(df, period=20, lookback=20):
    """Bollinger bandwidth at its narrowest of the last `lookback` bars — a
    volatility squeeze (the band-based cousin of NR7)."""
    bb = bollinger(df["Close"], period)
    width = (bb["upper"] - bb["lower"]) / bb["mid"]
    return width == width.rolling(lookback).min()


def bb_breakout_up(df, period=20):
    """Close pushes above the upper Bollinger band."""
    return df["Close"] > bollinger(df["Close"], period)["upper"]


def bb_breakout_down(df, period=20):
    return df["Close"] < bollinger(df["Close"], period)["lower"]


def volume_surge(df, mult=1.5, span=20):
    """Volume more than `mult`x its `span`-day average — participation."""
    return df["Volume"] > mult * vol_avg(df["Volume"], span)


def gap_up(df):
    """Today opens above yesterday's high."""
    return df["Open"] > df["High"].shift(1)


def gap_down(df):
    return df["Open"] < df["Low"].shift(1)


def new_high_20(df):
    """Close breaks the prior 20-session high (the 20-day breakout)."""
    return df["Close"] > rolling_high(df["High"], 20)


def new_high_52w(df):
    """Close at/above the 52-week (252-session) high, current bar included."""
    return df["Close"] >= rolling_high(df["High"], 252, exclude_current=False)


# --------------------------------------------------------------------------- #
# Feature registry + resolver — the vocabulary the strategy engine draws on    #
# --------------------------------------------------------------------------- #
# Derived/pattern features that only SOME strategies want — computed on demand
# via materialize(), kept out of add_indicators. Two ways a spec names one:
#   * a registered name below (a pattern or a derived signal), or
#   * a PARAMETERIZED indicator token <kind><N>[ _rising ] resolved by regex —
#     e.g. ema21, sma100, rsi9, atr20, adx14, hh50, ll50, vol30, nr5, ema21_rising.
# So a new strategy that wants a different period or a standard pattern needs NO
# code change here; only a genuinely new primitive does.
FEATURES = {
    # bar / candlestick patterns
    "inside_bar":        inside_bar,
    "outside_bar":       outside_bar,
    "engulfing":         bullish_engulfing,
    "bullish_engulfing": bullish_engulfing,
    "bearish_engulfing": bearish_engulfing,
    "hammer":            hammer,
    "shooting_star":     shooting_star,
    "piercing":          piercing,
    "dark_cloud_cover":  dark_cloud_cover,
    "doji":              doji,
    "bullish_reversal":  bullish_reversal,
    "bearish_reversal":  bearish_reversal,
    "coil_breakout":     coil_breakout,
    # moving-average / momentum signals
    "golden_cross":      golden_cross,
    "death_cross":       death_cross,
    "above_sma200":      above_sma200,
    "below_sma200":      below_sma200,
    "macd_bullish_cross": macd_bullish_cross,
    "macd_bearish_cross": macd_bearish_cross,
    "macd_above_zero":   macd_above_zero,
    "rsi_oversold":      rsi_oversold,
    "rsi_overbought":    rsi_overbought,
    "stoch_k":           lambda df: stochastic(df)["stoch_k"],
    "stoch_d":           lambda df: stochastic(df)["stoch_d"],
    "obv":               obv,
    # volatility / breakout / volume
    "bb_squeeze":        bb_squeeze,
    "bb_breakout_up":    bb_breakout_up,
    "bb_breakout_down":  bb_breakout_down,
    "volume_surge":      volume_surge,
    "gap_up":            gap_up,
    "gap_down":          gap_down,
    "new_high_20":       new_high_20,
    "new_high_52w":      new_high_52w,
}

# Parameterized indicator families: <kind><N> -> a Series of that indicator at
# period N. With an optional `_rising` suffix the result is the boolean slope test.
_PARAM_BUILDERS = {
    "ema": lambda df, n: ema(df["Close"], n),
    "sma": lambda df, n: sma(df["Close"], n),
    "rsi": lambda df, n: rsi(df["Close"], n),
    "atr": lambda df, n: atr(df, n),
    "adx": lambda df, n: adx(df, n),
    "hh":  lambda df, n: rolling_high(df["High"], n),
    "ll":  lambda df, n: rolling_low(df["Low"], n),
    "vol": lambda df, n: vol_avg(df["Volume"], n),
    "nr":  lambda df, n: nr(df, n),
}
_PARAM_RE = re.compile(r"^(%s)(\d+)(_rising)?$" % "|".join(_PARAM_BUILDERS))


def is_feature(name):
    """True if `name` is a registered feature or a parameterized indicator token."""
    return name in FEATURES or bool(_PARAM_RE.match(name))


def feature_series(df, name):
    """Compute one feature column by name — a registered FEATURES entry or a
    parameterized indicator (ema100, rsi9, hh50, adx14, ema21_rising, ...).
    Returns a Series, or None if the name resolves to nothing."""
    if name in FEATURES:
        return FEATURES[name](df)
    m = _PARAM_RE.match(name)
    if m:
        kind, n, rising = m.group(1), int(m.group(2)), m.group(3)
        s = _PARAM_BUILDERS[kind](df, n)
        return slope_up(s, 5) if rising else s
    return None


def materialize(df, names):
    """Return a copy of `df` with each requested feature attached as a column
    (skips names already present or unresolvable). Names come from a spec via
    strategy.referenced_features — registered patterns/signals or parameterized
    indicator tokens, so most strategies need no code change to be screened."""
    out = df.copy()
    for n in names or []:
        if n and n not in out.columns:
            s = feature_series(out, n)
            if s is not None:
                out[n] = s
    return out


# --------------------------------------------------------------------------- #
# Indicator bundle + OHLCV loader (the two things every consumer wants)        #
# --------------------------------------------------------------------------- #
def add_indicators(df):
    """Attach the standard swing indicator set — the single source of truth for
    the column names every skill keys off. Patterns are on-demand via materialize."""
    df = df.copy()
    df["ema20"] = ema(df["Close"], 20)
    df["ema50"] = ema(df["Close"], 50)
    df["sma200"] = sma(df["Close"], 200)
    df["ema50_rising"] = slope_up(df["ema50"], 5)
    df["rsi14"] = rsi(df["Close"], 14)
    df["vol10"] = vol_avg(df["Volume"], 10)
    df["atr14"] = atr(df, 14)
    df["hh20"] = rolling_high(df["High"], 20)   # prior 20-session high
    df["ll20"] = rolling_low(df["Low"], 20)
    return df


def load_ohlcv(symbol, years, cache_dir):
    """Daily OHLCV via yfinance (`<SYMBOL>.NS`), cached as CSV per symbol+span, so
    the backtester and live screen share prices. Raises on an empty result."""
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, f"{symbol}_{years}y.csv")
    if os.path.exists(cache):
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        if len(df) > 200:
            return df
    yf = _need("yfinance")
    df = yf.download(f"{symbol}.NS", period=f"{years}y", interval="1d",
                     auto_adjust=True, progress=False)
    if df is None or df.empty:
        raise RuntimeError(
            f"no data for {symbol} ({symbol}.NS) — likely delisted/renamed "
            f"(demerger?); verify the current yfinance symbol")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.to_csv(cache)
    return df
