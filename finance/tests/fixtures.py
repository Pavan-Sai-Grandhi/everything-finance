"""Synthetic inputs shared by the offline tests and the live smoke test. None of these numbers
describes a company or a market."""
import numpy as np
import pandas as pd


def trend_frame(kind, n=400, amplitude=4.0, spread=2.0, start="2022-01-03"):
    """Deterministic OHLCV: a clean uptrend (`up`, signals fire) or a downtrend (`down`)."""
    idx = pd.date_range(start, periods=n, freq="B")
    base = np.linspace(100, 240, n) if kind == "up" else np.linspace(240, 100, n)
    close = pd.Series(base + np.sin(np.arange(n) / 7) * amplitude, index=idx)
    volume = pd.Series([1000] * n, index=idx)
    return pd.DataFrame({"Open": close.shift(1).fillna(close.iloc[0]), "High": close + spread,
                         "Low": close - spread, "Close": close, "Volume": volume}, index=idx)


def screen_frame(kind):
    """The live screen's fixture: `uptrend` passes an EMA-pullback spec, `downtrend` fails it."""
    n = 260
    idx = pd.date_range("2023-01-02", periods=n, freq="B")
    base = np.linspace(100, 200, n) if kind == "uptrend" else np.linspace(200, 100, n)
    close = pd.Series(base + np.sin(np.arange(n) / 6) * 3, index=idx)
    volume = pd.Series([1000] * n, index=idx)
    volume.iloc[-1] = 2000
    return pd.DataFrame({"Open": close.shift(1).fillna(close.iloc[0]), "High": close + 1.5,
                         "Low": close - 1.5, "Close": close, "Volume": volume}, index=idx)


BACKTEST_SPEC = {
    "name": "selftest-ema-pullback", "archetype": "pullback",
    "screening": {"technical": {"compute_filters": ["ema50_rising", "Close > ema50"]}},
    "entry": {"signal": ["ema50_rising", "Close > ema50", "rsi14 between 40 and 80"]},
    "exit": {"stop": "ema50_minus_2atr", "target": "min_rrr", "min_rrr": 1.5,
             "time_stop_sessions": 15},
    "sizing": {"risk_per_trade_pct": 1.0},
}

SCREEN_SPEC = {
    "name": "selftest-ema-pullback", "archetype": "pullback",
    "entry": {"signal": ["ema50_rising", "Close > ema50", "rsi14 between 40 and 100"],
              "trigger": "synthetic test condition: rising EMA50, close above EMA50 and RSI 40–100"},
    "exit": {"stop": "ema50_minus_2atr", "target": "min_rrr", "min_rrr": 1.5},
    "sizing": {"risk_per_trade_pct": 1.0},
}

DCF_SPEC = {
    "currency_unit": "INR Crore",
    "years": 10,
    "base_revenue": 1000.0,
    "growth_glide": {"initial": 0.15, "fade_to": 0.04, "years_high": 3},
    "margin_glide": {"start": 0.12, "target": 0.18, "year_target": 5},
    "tax_rate": 0.25,
    "sales_to_capital": 2.0,
    "wacc": 0.11,
    "terminal_growth": 0.04,
    "terminal_roic": 0.13,
    "risk_free": 0.07,
    "net_debt": 500.0,
    "non_operating_cash": 100.0,
    "shares_outstanding": 100.0,
    "current_price": 60.0,
    "timing": {"base_period_end": "2026-03-31", "valuation_date": "2026-09-30"},
}
