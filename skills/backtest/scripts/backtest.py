#!/usr/bin/env python3
"""Swing-rule backtester for NSE daily data (everything-finance plugin).

Tests the swing-trading technical triggers historically with no-lookahead
execution: signal on bar t close -> entry at bar t+1 open. Pessimistic
intrabar tie-break (SL before target). Conservative all-in costs.

Usage:
  python3 backtest.py --symbols RELIANCE,TCS --strategy both --years 5 \
      --capital 500000 --risk-pct 1.0 --out artifacts/2026-06-10/backtest
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date

try:
    import pandas as pd
    import numpy as np
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                           "--break-system-packages", "pandas", "numpy"])
    import pandas as pd
    import numpy as np

# 20 liquid large-caps — NOT the full Nifty 50; reports must call it a 20-stock basket
LARGECAP20_BASKET = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "BHARTIARTL", "SBIN",
    "LT", "ITC", "HINDUNILVR", "MARUTI", "M&M", "SUNPHARMA", "TITAN",
    "BAJFINANCE", "AXISBANK", "KOTAKBANK", "ASIANPAINT", "TATASTEEL", "NTPC",
]

# Tickers whose yfinance symbol changed (demergers/renames); extend as discovered.
SYMBOL_ALIASES = {
    "TATAMOTORS": "TATAMOTORS",  # post-2025 demerger: verify CV/PV split symbol on yfinance
}

ROUND_TRIP_COST = 0.0025  # 0.25% all-in (charges + slippage), applied on exit
TIME_STOP_SESSIONS = 20
TARGET_R = 2.0


def load_ohlcv(symbol: str, years: int, cache_dir: str) -> pd.DataFrame:
    """Daily OHLCV via yfinance (.NS), cached as CSV per symbol+span."""
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, f"{symbol}_{years}y.csv")
    if os.path.exists(cache):
        df = pd.read_csv(cache, index_col=0, parse_dates=True)
        if len(df) > 200:
            return df
    try:
        import yfinance as yf
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                               "--break-system-packages", "yfinance"])
        import yfinance as yf
    yf_symbol = SYMBOL_ALIASES.get(symbol, symbol)
    df = yf.download(f"{yf_symbol}.NS", period=f"{years}y", interval="1d",
                     auto_adjust=True, progress=False)
    if df is None or df.empty:
        raise RuntimeError(
            f"no data for {symbol} ({yf_symbol}.NS) — likely delisted/renamed "
            f"(demerger?); check the current yfinance symbol and add it to SYMBOL_ALIASES")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    df.to_csv(cache)
    return df


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["vol10"] = df["Volume"].rolling(10).mean()
    df["hh20"] = df["High"].rolling(20).max().shift(1)  # prior 20-session high
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift(1)).abs(),
        (df["Low"] - df["Close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14).mean()
    df["ema50_rising"] = df["ema50"] > df["ema50"].shift(5)
    return df


def signals_breakout(df: pd.DataFrame) -> pd.Series:
    """Close above prior 20-session high on volume > 1.5x 10d avg,
    after a quiet base (range of prior 20 sessions < 10%)."""
    base_range = (df["High"].rolling(20).max().shift(1)
                  - df["Low"].rolling(20).min().shift(1)) / df["Close"]
    return (
        (df["Close"] > df["hh20"])
        & (df["Volume"] > 1.5 * df["vol10"])
        & (base_range < 0.10)
        & df["ema50_rising"]
    )


def signals_pullback(df: pd.DataFrame) -> pd.Series:
    """Uptrend (price above rising 50-EMA), low tags the EMA zone,
    close recovers above the EMA."""
    return (
        df["ema50_rising"]
        & (df["Low"] <= df["ema50"] * 1.01)
        & (df["Close"] > df["ema50"])
        & (df["Close"].shift(1) > df["ema50"].shift(1) * 0.97)
    )


def run_symbol(df: pd.DataFrame, signal: pd.Series, symbol: str,
               strategy: str, capital: float, risk_pct: float) -> list[dict]:
    """Event loop: one open position at a time per symbol; entry next open."""
    trades = []
    i = 60  # warm-up for indicators
    n = len(df)
    while i < n - 2:
        if not bool(signal.iloc[i]):
            i += 1
            continue
        # entry at next bar's open (no lookahead)
        e = i + 1
        entry = float(df["Open"].iloc[e])
        if strategy == "breakout":
            sl = float(df["Low"].rolling(10).min().iloc[i])  # base low
        else:
            sl = float(df["ema50"].iloc[i] - 2 * df["atr14"].iloc[i])
        if sl >= entry or (entry - sl) / entry > 0.15:
            i += 1  # malformed or too-wide stop: skip
            continue
        risk = entry - sl
        target = entry + TARGET_R * risk
        qty = max(int((capital * risk_pct / 100) / risk), 0)
        if qty == 0:
            i += 1
            continue

        exit_px, exit_reason, exit_idx = None, None, None
        for j in range(e, min(e + TIME_STOP_SESSIONS, n)):
            bar = df.iloc[j]
            # pessimistic: SL checked before target within the same bar
            if bar["Low"] <= sl:
                exit_px, exit_reason, exit_idx = sl, "SL", j
                break
            if bar["High"] >= target:
                exit_px, exit_reason, exit_idx = target, "TARGET", j
                break
        if exit_px is None:
            exit_idx = min(e + TIME_STOP_SESSIONS, n - 1)
            exit_px, exit_reason = float(df["Close"].iloc[exit_idx]), "TIME"

        gross = (exit_px - entry) * qty
        cost = ROUND_TRIP_COST * entry * qty
        pnl = gross - cost
        trades.append({
            "symbol": symbol, "strategy": strategy,
            "entry_date": str(df.index[e].date()), "entry": round(entry, 2),
            "sl": round(sl, 2), "target": round(target, 2), "qty": qty,
            "exit_date": str(df.index[exit_idx].date()),
            "exit": round(exit_px, 2), "reason": exit_reason,
            "pnl": round(pnl, 2),
            "r_multiple": round((exit_px - entry) / risk - ROUND_TRIP_COST * entry / risk, 3),
            "year": df.index[e].year,
        })
        i = exit_idx + 1  # no overlapping positions per symbol
    return trades


def buy_and_hold(df: pd.DataFrame) -> dict:
    ret = float(df["Close"].iloc[-1] / df["Close"].iloc[0] - 1)
    peak = df["Close"].cummax()
    mdd = float(((df["Close"] - peak) / peak).min())
    return {"total_return_pct": round(100 * ret, 1), "max_dd_pct": round(100 * mdd, 1)}


def summarize(trades: list[dict], capital: float) -> dict:
    if not trades:
        return {"trades": 0, "note": "no signals generated"}
    t = pd.DataFrame(trades)
    wins, losses = t[t.pnl > 0], t[t.pnl <= 0]
    gross_p, gross_l = wins.pnl.sum(), abs(losses.pnl.sum())
    equity = capital + t.pnl.cumsum()
    peak = equity.cummax()
    return {
        "trades": len(t),
        "win_rate_pct": round(100 * len(wins) / len(t), 1),
        "avg_win_R": round(wins.r_multiple.mean(), 2) if len(wins) else 0.0,
        "avg_loss_R": round(losses.r_multiple.mean(), 2) if len(losses) else 0.0,
        "expectancy_R": round(t.r_multiple.mean(), 3),
        "profit_factor": round(gross_p / gross_l, 2) if gross_l > 0 else float("inf"),
        "total_pnl": round(t.pnl.sum(), 0),
        "return_on_capital_pct": round(100 * t.pnl.sum() / capital, 1),
        "max_dd_on_equity_pct": round(100 * ((equity - peak) / peak).min(), 1),
        "exit_breakdown": t.reason.value_counts().to_dict(),
        # current calendar year is flagged partial so the yearly table can't mislead
        "by_year_pnl": {
            (f"{k} (partial)" if k == date.today().year else str(k)): round(v, 0)
            for k, v in t.groupby("year").pnl.sum().items()
        },
        "by_year_expectancy_R": {
            (f"{k} (partial)" if k == date.today().year else str(k)): round(v, 3)
            for k, v in t.groupby("year").r_multiple.mean().items()
        },
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True,
                   help="comma-separated NSE symbols, or 'largecap20' "
                        "(20-stock liquid large-cap basket; 'nifty50' is a deprecated alias)")
    p.add_argument("--strategy", default="both",
                   choices=["breakout", "pullback", "both"])
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--capital", type=float, default=500000)
    p.add_argument("--risk-pct", type=float, default=1.0)
    p.add_argument("--out", default=f"artifacts/{date.today()}/backtest")
    args = p.parse_args()

    basket_key = args.symbols.lower()
    if basket_key == "nifty50":
        print("warning: 'nifty50' is a deprecated alias for 'largecap20' "
              "(20 symbols, not the full index)", file=sys.stderr)
    symbols = (LARGECAP20_BASKET if basket_key in ("largecap20", "nifty50")
               else [s.strip().upper() for s in args.symbols.split(",")])
    strategies = ["breakout", "pullback"] if args.strategy == "both" else [args.strategy]
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    cache_dir = "artifacts/.cache/ohlcv"

    all_trades, bh, failures = [], {}, []
    for sym in symbols:
        try:
            df = add_indicators(load_ohlcv(sym, args.years, cache_dir))
        except Exception as exc:  # data gap: skip symbol, keep going
            failures.append(f"{sym}: {exc}")
            continue
        bh[sym] = buy_and_hold(df)
        for strat in strategies:
            sig = signals_breakout(df) if strat == "breakout" else signals_pullback(df)
            all_trades += run_symbol(df, sig, sym, strat, args.capital, args.risk_pct)

    result = {
        "config": vars(args) | {"symbols_resolved": symbols,
                                "cost_round_trip": ROUND_TRIP_COST,
                                "time_stop_sessions": TIME_STOP_SESSIONS,
                                "target_R": TARGET_R},
        "by_strategy": {s: summarize([t for t in all_trades if t["strategy"] == s],
                                     args.capital) for s in strategies},
        "buy_and_hold": bh,
        "data_gaps": failures,
        "caveats": [
            "survivorship bias: current symbols only (delisted losers absent)",
            "in-sample, fixed Varsity parameters (not optimized, but also not walk-forward validated)",
            "tests mechanical triggers only - not the fundamental gate or discretionary S/R reads",
        ],
    }
    if all_trades:
        pd.DataFrame(all_trades).to_csv(f"{args.out}-trades.csv", index=False)
    with open(f"{args.out}-summary.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(json.dumps(result, indent=2, default=str))
    print(f"\nwrote {args.out}-summary.json"
          + (f" and {args.out}-trades.csv ({len(all_trades)} trades)" if all_trades else ""))


if __name__ == "__main__":
    main()
