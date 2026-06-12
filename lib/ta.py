#!/usr/bin/env python3
"""Shared technical-analysis primitives for the everything-finance plugin.

ONE definition of every indicator and candlestick pattern, imported by every
skill that computes them — `backtest`, `find-trade`, and (via a Bash call) the
`technical-analyst` agent. The point is consistency: if the backtest's EMA and
the live screen's EMA were computed by two hand-rolled implementations, a stock
could pass the screen and fail the backtest for no real reason. Compute it once,
here, and every consumer agrees by construction.

Import from a skill script (which lives at skills/<name>/scripts/<x>.py):

    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "..", "lib"))
    import ta

Everything is pure pandas/numpy and deterministic — no network, no globals —
so it is unit-testable offline (see test_ta.py). The OHLCV loader (yfinance)
is the one networked helper and is cache-first.

Conventions: input is a DataFrame with columns Open/High/Low/Close/Volume and a
DatetimeIndex. Indicator functions return a Series aligned to that index; early
positions are NaN until the lookback fills. Pattern functions return a boolean
Series. Nothing mutates its input.
"""
from __future__ import annotations

import os
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


pd = _need("pandas")
np = _need("numpy")


# --------------------------------------------------------------------------- #
# Moving averages & trend                                                      #
# --------------------------------------------------------------------------- #
def sma(series, span):
    """Simple moving average."""
    return series.rolling(span).mean()


def ema(series, span):
    """Exponential moving average (adjust=False — the recursive form charting
    tools and our backtester both use, so live and historical EMAs match)."""
    return series.ewm(span=span, adjust=False).mean()


def slope_up(series, lookback=5):
    """True where the series is higher than `lookback` bars ago — a cheap,
    robust 'rising' test used as the trend filter (e.g. ema50 rising)."""
    return series > series.shift(lookback)


# --------------------------------------------------------------------------- #
# Momentum & volatility                                                        #
# --------------------------------------------------------------------------- #
def rsi(close, period=14):
    """Wilder's RSI. Uses Wilder smoothing (ewm alpha=1/period), the standard
    TradingView/Varsity definition — not a simple rolling mean of gains."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    out = 100 - (100 / (1 + rs))
    # all-gain windows -> avg_loss 0 -> rs inf -> RSI 100 (correct); fill the
    # degenerate 0/0 (flat price) as a neutral 50 rather than NaN.
    return out.where(avg_loss != 0, 100.0).where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)


def macd(close, fast=12, slow=26, signal=9):
    """MACD line, signal line, histogram (the classic 12/26/9)."""
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": macd_line, "signal": signal_line,
                         "hist": macd_line - signal_line})


def true_range(df):
    """Wilder true range = max(H-L, |H-Cprev|, |L-Cprev|)."""
    prev_close = df["Close"].shift(1)
    return pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)


def atr(df, period=14):
    """Average true range (rolling mean of true range — the simple-MA form the
    backtester uses for stop placement)."""
    return true_range(df).rolling(period).mean()


def bollinger(close, period=20, mult=2.0):
    """Bollinger bands -> DataFrame(mid, upper, lower)."""
    mid = sma(close, period)
    sd = close.rolling(period).std(ddof=0)
    return pd.DataFrame({"mid": mid, "upper": mid + mult * sd, "lower": mid - mult * sd})


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
# Candlestick / range patterns (boolean Series)                               #
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


def inside_bar(df):
    """Today's range is inside yesterday's (high lower, low higher) — a
    volatility-contraction / coil bar."""
    return (df["High"] < df["High"].shift(1)) & (df["Low"] > df["Low"].shift(1))


def nr(df, n):
    """NR-n: today's high-low range is the narrowest of the last n bars — a
    volatility squeeze that often precedes an expansion move. nr(df,4)=NR4,
    nr(df,7)=NR7."""
    rng = df["High"] - df["Low"]
    return rng == rng.rolling(n).min()


# --------------------------------------------------------------------------- #
# Indicator bundle + OHLCV loader (the two things every consumer wants)        #
# --------------------------------------------------------------------------- #
def add_indicators(df):
    """Attach the standard swing indicator set in one pass. The single source
    of truth for the column names + math every skill keys off."""
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
    """Daily OHLCV via yfinance (`<SYMBOL>.NS`), cached as CSV per symbol+span.
    Shared so the backtester and the live screen pull prices the same way and
    hit the same cache. Raises RuntimeError on an empty result (delist/rename)."""
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
