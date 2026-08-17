#!/usr/bin/env python3
"""Spec-driven swing backtester for NSE daily data (everything-finance plugin).

Validates any STRATEGY SPEC, not a hardcoded archetype: entry, stop, target,
time-stop and sizing all come from the spec via `finance/compute/strategy.py` — the same
module the live find-trade screen uses, so a new strategy is backtestable by
existing, with no per-archetype code here.

Engine: **Backtesting.py** (MIT). Its defaults give the discipline a real-money
test needs: no lookahead (signal on bar t -> fill at t+1 open) and pessimistic
intrabar exits (both stop and target touched in one bar -> the STOP is taken).
Indicators come from TA-Lib via finance/compute/ta.py. Commission is charged per side, set so
the round trip ~= 0.25% all-in (charges + slippage).

Usage:
  python3 -m finance.compute.backtest --spec artifacts/state/strategies/ema-pullback-swing.yml \
      --symbols RELIANCE,TCS --years 5 --capital 500000
  # --out defaults to artifacts/backtest/<spec>/<today>/report
  python3 -m finance.compute.backtest --selftest        # synthetic data, no network
"""

import argparse
import json
import os
import sys
from datetime import date

# Shared engine: finance/compute/ta.py (indicators) + finance/compute/strategy.py
# (spec -> signals) + finance/paths.py (artifact locations).
from finance import paths
from finance import spine
from finance.compute import strategy
from finance.compute import ta

pd = ta.pd

# What every report built on this engine must carry alongside its numbers.
CAVEATS = [
    "survivorship bias: current symbols only (delisted losers absent)",
    "in-sample, spec parameters as written (not optimized; not walk-forward validated)",
    "per-symbol expectancy test (each symbol sized off full capital), not a portfolio sim",
    "tests the spec's mechanical entry/exit only — not the fundamental gate "
    "or discretionary S/R reads",
]

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

# Per-side commission; ~0.00125/side ≈ 0.25% round trip (all-in charges + slippage).
COMMISSION_PER_SIDE = 0.00125


def load_ohlcv(symbol, years, cache_dir):
    """Daily OHLCV via the shared loader, resolving demerger/rename aliases."""
    return ta.load_ohlcv(SYMBOL_ALIASES.get(symbol, symbol), years, cache_dir)


def strategy_load(path):
    """Load a strategy spec YAML (shares find-trade's loader convention)."""
    yaml = ta._need("yaml", "pyyaml")
    with open(path) as f:
        return yaml.safe_load(f)


def run_symbol(df, spec, symbol, capital, risk_pct):
    """Backtest one symbol's enriched frame against the spec. Returns a list of
    trade dicts with cost-inclusive R multiples (R = net PnL / risk-at-entry)."""
    from backtesting import Backtest
    frame = strategy.prepare_backtest_frame(df, spec)
    strat = strategy.build_bt_strategy(spec, capital, risk_pct)
    time_stop = int((spec.get("exit", {}) or {}).get("time_stop_sessions", 20) or 20)
    bt = Backtest(frame, strat, cash=capital, commission=COMMISSION_PER_SIDE,
                  exclusive_orders=True, trade_on_close=False, finalize_trades=True)
    stats = bt.run()
    trades = []
    for _, t in stats["_trades"].iterrows():
        risk = t.get("Tag")
        if risk is None or pd.isna(risk):                       # fallback if untagged
            risk = float(t["EntryPrice"]) - float(t["SL"]) if not pd.isna(t.get("SL")) else None
        size = abs(float(t["Size"]))
        pnl = float(t["PnL"])
        r = (pnl / (float(risk) * size)) if risk and size else 0.0   # net, cost-inclusive
        exit_reason = _exit_reason(t, time_stop)
        trades.append({
            "symbol": symbol, "strategy": spec.get("name"),
            "entry_date": str(pd.Timestamp(t["EntryTime"]).date()),
            "entry": round(float(t["EntryPrice"]), 2),
            "sl": round(float(t["SL"]), 2) if not pd.isna(t.get("SL")) else None,
            "target": round(float(t["TP"]), 2) if not pd.isna(t.get("TP")) else None,
            "qty": int(size),
            "exit_date": str(pd.Timestamp(t["ExitTime"]).date()),
            "exit": round(float(t["ExitPrice"]), 2), "reason": exit_reason,
            "pnl": round(pnl, 2), "r_multiple": round(r, 3),
            "year": pd.Timestamp(t["EntryTime"]).year,
        })
    return trades


def _exit_reason(t, time_stop=None):
    """Label why a trade closed: SL (incl. a trailed stop — which can be a *win*),
    TARGET, TIME (held to the time-stop), or SIGNAL/OTHER (a discretionary
    exit_signal close). Distinguishing TIME from SIGNAL matters because
    strategy-manager's optimize step reads the exit mix as its diagnostic."""
    ex = float(t["ExitPrice"])
    if not pd.isna(t.get("SL")) and abs(ex - float(t["SL"])) < 1e-6:
        return "SL"
    if not pd.isna(t.get("TP")) and abs(ex - float(t["TP"])) < 1e-6:
        return "TARGET"
    if (time_stop is not None and not pd.isna(t.get("ExitBar"))
            and not pd.isna(t.get("EntryBar"))
            and int(t["ExitBar"]) - int(t["EntryBar"]) >= time_stop):
        return "TIME"
    return "SIGNAL/OTHER"


def buy_and_hold(df):
    ret = float(df["Close"].iloc[-1] / df["Close"].iloc[0] - 1)
    peak = df["Close"].cummax()
    mdd = float(((df["Close"] - peak) / peak).min())
    return {"total_return_pct": round(100 * ret, 1), "max_dd_pct": round(100 * mdd, 1)}


def summarize(trades, capital):
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


def resolve_universe(symbols):
    """The test universe: a list, a comma-separated string, or `largecap20`."""
    if isinstance(symbols, str):
        if symbols.strip().lower() == "largecap20":
            return list(LARGECAP20_BASKET)
        symbols = symbols.split(",")
    return [str(s).strip().upper() for s in (symbols or []) if str(s).strip()]


def run(spec, symbols, years=5, capital=500000, risk_pct=None, out=None):
    """Backtest a spec over a universe and return the shared data-spine envelope.

    `spec` is a path to a strategy YAML. `out` is a path PREFIX: `<out>-summary.json` always,
    `<out>-trades.csv` when trades fired (default prefix
    `artifacts/backtest/<spec>/<date>/report`). The envelope carries the performance
    summary, the buy-and-hold comparison, the caveats that qualify both, and those paths —
    the per-trade log stays on disk.
    """
    doc = strategy_load(spec)
    symbols = resolve_universe(symbols)
    if out is None:
        name = doc.get("name") or os.path.splitext(os.path.basename(spec))[0]
        out = os.path.join(paths.backtest_dir(name), "report")
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    cache_dir = paths.cache_dir("ohlcv")

    all_trades, bh, gaps = [], {}, []
    for sym in symbols:
        try:
            df = load_ohlcv(sym, years, cache_dir)
        except Exception as exc:  # noqa: BLE001 — a data gap skips the symbol, never the run
            gaps.append(f"{sym}: {exc}")
            continue
        bh[sym] = buy_and_hold(df)
        try:
            all_trades += run_symbol(df, doc, sym, capital, risk_pct)
        except Exception as exc:  # noqa: BLE001
            gaps.append(f"{sym}: backtest error: {exc}")

    if not all_trades:
        gaps.append("the spec produced no trades over this universe and window — "
                    "an untested spec, not a validated one")
    result = {
        "config": {"spec": doc.get("name"), "spec_path": spec,
                   "symbols_resolved": symbols, "years": years, "capital": capital,
                   "risk_pct": risk_pct or doc.get("sizing", {}).get("risk_per_trade_pct"),
                   "commission_per_side": COMMISSION_PER_SIDE,
                   "engine": "Backtesting.py + finance/compute/strategy.py (spec-driven)"},
        "summary": summarize(all_trades, capital),
        "buy_and_hold": bh,
        "data_gaps": gaps,
        "caveats": CAVEATS,
    }
    trades_path = None
    if all_trades:
        trades_path = f"{out}-trades.csv"
        pd.DataFrame(all_trades).to_csv(trades_path, index=False)
    with open(f"{out}-summary.json", "w") as fh:
        json.dump(result, fh, indent=2, default=str)
    return spine.envelope(
        bool(all_trades), "finance.compute.backtest",
        {"config": result["config"], "summary": result["summary"],
         "buy_and_hold": bh, "caveats": CAVEATS,
         "trades": len(all_trades), "summary_path": f"{out}-summary.json",
         "trades_path": trades_path},
        gaps)


def _synth(kind):
    """Deterministic OHLCV: a clean uptrend (signals fire) vs a downtrend."""
    np = ta.np
    n = 400
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    base = np.linspace(100, 240, n) if kind == "up" else np.linspace(240, 100, n)
    close = pd.Series(base + np.sin(np.arange(n) / 7) * 4, index=idx)
    high = close + 2.0
    low = close - 2.0
    op = close.shift(1).fillna(close.iloc[0])
    vol = pd.Series([1000] * n, index=idx)
    return pd.DataFrame({"Open": op, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


SELFTEST_SPEC = {
    "name": "selftest-ema-pullback", "archetype": "pullback",
    "screening": {"technical": {"compute_filters": [
        "ema50_rising", "Close > ema50"]}},
    "entry": {"signal": ["ema50_rising", "Close > ema50", "rsi14 between 40 and 80"]},
    "exit": {"stop": "ema50_minus_2atr", "target": "next_resistance",
             "min_rrr": 1.5, "time_stop_sessions": 15},
    "sizing": {"risk_per_trade_pct": 1.0},
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--spec", help="path to a strategy <name>.yml (the rules to test)")
    p.add_argument("--symbols",
                   help="comma-separated NSE symbols, or 'largecap20' "
                        "(20-stock liquid large-cap basket)")
    p.add_argument("--years", type=int, default=5)
    p.add_argument("--capital", type=float, default=500000)
    p.add_argument("--risk-pct", type=float, default=None,
                   help="override the spec's sizing.risk_per_trade_pct")
    p.add_argument("--out", default=None,
                   help="output path prefix (default: artifacts/backtest/<spec>/<today>/report)")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()

    if args.selftest:
        up = run_symbol(_synth("up"), SELFTEST_SPEC, "UPTREND", 500000, None)
        down = run_symbol(_synth("down"), SELFTEST_SPEC, "DOWNTREND", 500000, None)
        s_up = summarize(up, 500000)
        print(json.dumps({"up": s_up, "down_trades": len(down)}, indent=2, default=str))
        ok = len(up) > 0 and len(down) == 0   # fires in an uptrend, stands down in a downtrend
        print(f"\nselftest: {'PASS' if ok else 'FAIL'}", file=sys.stderr)
        sys.exit(0 if ok else 1)

    if not args.spec or not args.symbols:
        print("error: --spec and --symbols required (or use --selftest)", file=sys.stderr)
        sys.exit(2)
    env = run(args.spec, args.symbols, years=args.years, capital=args.capital,
              risk_pct=args.risk_pct, out=args.out)
    print(json.dumps(env, indent=2, default=str))
    data = env["data"]
    print(f"\nwrote {data['summary_path']}"
          + (f" and {data['trades_path']} ({data['trades']} trades)"
             if data["trades_path"] else ""))


if __name__ == "__main__":
    main()
