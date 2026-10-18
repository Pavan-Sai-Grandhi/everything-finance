"""One symbol's indicator read on adjusted daily candles, computed by `ta.py`.

The same indicator-of-record the screens and the backtest use, so a chart read cannot
disagree with the screen that surfaced the stock.
"""
import math

from finance import spine
from finance.compute import ta
from finance.sources import prices

_SOURCE = "finance.compute.technicals"
PATTERNS = ("bullish_engulfing", "bearish_engulfing", "hammer", "shooting_star", "piercing",
            "dark_cloud_cover", "doji", "inside_bar", "outside_bar", "golden_cross",
            "death_cross", "macd_bullish_cross", "macd_bearish_cross", "volume_surge",
            "gap_up", "gap_down", "new_high_52w")


def _cell(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        return round(value, 4) if math.isfinite(value) else None
    return value


@spine.guarded(_SOURCE)
def report(symbol, period="1y", features=None, drop_last=False, fresh=False):
    """Indicator columns for every bar, plus the patterns that fired on the latest bar.

    `features` adds `ta` tokens (`ema100`, `rsi9`, `nr7`) to the standard set. `drop_last`
    excludes the final bar, for when it is an unclosed session.
    """
    frame, gaps = prices.history_df(symbol, period=period, adjusted=True, fresh=fresh)
    if frame is None or frame.empty:
        return spine.envelope(False, _SOURCE, {"symbol": spine.norm_symbol(symbol)},
                              gaps or ["no candles"])
    if drop_last:
        frame = frame.iloc[:-1]
    unknown = [name for name in features or [] if not ta.is_feature(name)]
    if unknown:
        raise ValueError(f"unknown feature token(s): {', '.join(unknown)}")
    frame = ta.add_indicators(frame)
    frame["ema200"] = ta.ema(frame["Close"], 200)
    frame = frame.join(ta.macd(frame["Close"]).rename(columns={"signal": "macd_signal",
                                                               "hist": "macd_hist"}))
    frame = frame.join(ta.bollinger(frame["Close"]).add_prefix("bb_"))
    frame = ta.materialize(frame, list(features or []) + list(PATTERNS))
    rows = [{"date": index.date().isoformat(), **{k: _cell(v) for k, v in row.items()}}
            for index, row in frame.iterrows()]
    latest = rows[-1]
    return spine.envelope(True, _SOURCE, {
        "symbol": spine.norm_symbol(symbol),
        "as_of": latest["date"],
        "bars": len(rows),
        "latest": {k: v for k, v in latest.items() if k not in PATTERNS},
        "patterns_latest": [p for p in PATTERNS if latest.get(p) is True],
        "rows": rows,
    }, gaps)
