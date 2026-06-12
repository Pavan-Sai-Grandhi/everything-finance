#!/usr/bin/env python3
"""find-trade screening + signal engine (everything-finance plugin).

find-trade is strategy-AGNOSTIC: it runs whatever ACTIVE, regime-fitting strategy
spec it is handed (chosen by `strategy-manager pick`). This script is the
deterministic core of that run — it does NOT decide *what* to trade, it executes a
spec's screening + signal rules on price data:

  1. screen_compute()  — the local technical cut (spec.screening.technical.compute_filters)
                         over a universe, using the shared indicators in lib/ta.py.
                         This is the fallback when the TradingView provider is
                         unreachable, and the offline-testable heart of the engine.
  2. build_signal()    — turns a surviving stock into entry / stop / target / RRR /
                         qty from the spec's entry/exit/sizing blocks.

The auth'd provider fetches (screener.in fundamental screen, TradingView technical
screen via the browser) live in the SKILL workflow, which feeds their survivor list
into this script. Keeping the math here means the live screen and the backtest agree
by construction (both import lib/ta.py) and the logic is unit-testable with no network.

Usage:
  python3 screen.py --spec <strategy>.yml --symbols RELIANCE,TCS[,...] \
      --capital 500000 --years 2 --out artifacts/2026-06-12/find-trade.json
  python3 screen.py --selftest         # synthetic data, no network
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "lib"))
import ta  # noqa: E402

pd = ta.pd


# --------------------------------------------------------------------------- #
# compute-path predicate evaluator                                            #
# --------------------------------------------------------------------------- #
# A tiny, SAFE mini-language for spec.screening.technical.compute_filters — NOT
# Python eval. Supported forms, evaluated on the latest bar of an indicator frame:
#   "<col>"                       bare column -> truthy (e.g. "ema50_rising")
#   "<term> > <term>"             comparison  (e.g. "Close > ema50")
#   "<term> < <term>"
#   "<col> between <x> and <y>"   range       (e.g. "rsi14 between 40 and 60")
# where <term> is a column name, a number, or "<number> * <col>" (e.g. "1.5 * vol10").
def _term(token, row):
    token = token.strip()
    if "*" in token:
        a, b = (t.strip() for t in token.split("*", 1))
        return float(a) * _term(b, row)
    try:
        return float(token)
    except ValueError:
        if token not in row:
            raise KeyError(f"unknown column in filter: {token!r}")
        return float(row[token])


def eval_filter(expr, row):
    """Evaluate one compute_filter string against a Series `row` (latest bar)."""
    e = expr.strip()
    low = e.lower()
    if " between " in low and " and " in low:
        col, rest = e.split(" between ", 1) if " between " in e else e.split(" BETWEEN ", 1)
        lo, hi = rest.replace(" AND ", " and ").split(" and ", 1)
        v = _term(col, row)
        return _term(lo, row) <= v <= _term(hi, row)
    for op in (">=", "<=", ">", "<"):
        if op in e:
            a, b = e.split(op, 1)
            va, vb = _term(a, row), _term(b, row)
            return {">": va > vb, "<": va < vb, ">=": va >= vb, "<=": va <= vb}[op]
    # bare column -> truthy
    return bool(row[e.strip()])


def passes_technical(df, filters):
    """True if the latest bar of `df` satisfies every compute_filter. Returns
    (ok, reasons) where reasons lists any failed/again-unevaluable filter."""
    row = df.iloc[-1]
    reasons = []
    for f in filters or []:
        try:
            if not eval_filter(f, row):
                reasons.append(f"fail: {f}")
        except (KeyError, ValueError) as exc:
            reasons.append(f"uneval: {f} ({exc})")
    return (len(reasons) == 0), reasons


# --------------------------------------------------------------------------- #
# signal construction                                                          #
# --------------------------------------------------------------------------- #
def _resolve_stop(df, kind):
    """Stop level from spec.exit.stop on the latest bar."""
    last = df.iloc[-1]
    if kind == "ema50_minus_2atr":
        return float(last["ema50"] - 2 * last["atr14"])
    if kind == "range_low":
        return float(last["ll20"])
    # default: recent_swing_low — lowest low of the last 10 sessions
    return float(df["Low"].rolling(10).min().iloc[-1])


def build_signal(df, spec, capital, entry_override=None):
    """Construct a trade signal for one stock from the spec. Returns a dict, or
    {skip: reason} when the RRR gate or a malformed stop rejects it."""
    last = df.iloc[-1]
    exitb = spec.get("exit", {}) or {}
    sizing = spec.get("sizing", {}) or {}
    min_rrr = float(exitb.get("min_rrr", 1.5))

    # entry: an explicit trigger if the setup defines one (breakout -> prior high),
    # else the latest close (pullback/reversal setups enter at/near current price).
    entry = float(entry_override) if entry_override is not None else float(last["Close"])
    stop = _resolve_stop(df, exitb.get("stop", "recent_swing_low"))
    if not (stop < entry) or (entry - stop) / entry > 0.15:
        return {"skip": f"malformed/too-wide stop (entry {entry:.2f}, stop {stop:.2f})"}
    risk = entry - stop

    target_spec = str(exitb.get("target", "")).lower()
    if "measured_move" in target_spec or "measured" in target_spec:
        target = entry + float(last["hh20"] - last["ll20"])   # consolidation height
        target_basis = "measured-move"
    else:
        target = entry + min_rrr * risk                       # next-resistance proxy
        target_basis = "min-RRR (next resistance to be confirmed on chart)"
    rrr = (target - entry) / risk
    if rrr < min_rrr:
        return {"skip": f"RRR {rrr:.2f} < min {min_rrr}"}

    risk_pct = float(sizing.get("risk_per_trade_pct", 1.0))
    qty = max(int((capital * risk_pct / 100) / risk), 0)
    if qty == 0:
        return {"skip": "qty rounds to 0 at this risk budget"}

    return {
        "entry": round(entry, 2), "stop": round(stop, 2), "target": round(target, 2),
        "rrr": round(rrr, 2), "qty": qty, "risk_per_share": round(risk, 2),
        "target_basis": target_basis,
        "stop_basis": exitb.get("stop", "recent_swing_low"),
        "indicators": {
            "close": round(float(last["Close"]), 2),
            "ema50": round(float(last["ema50"]), 2),
            "rsi14": round(float(last["rsi14"]), 1),
            "vol_vs_10d": round(float(last["Volume"] / last["vol10"]), 2),
            "ema50_rising": bool(last["ema50_rising"]),
        },
    }


# --------------------------------------------------------------------------- #
# orchestration                                                               #
# --------------------------------------------------------------------------- #
def screen_compute(symbols, spec, years, capital, cache_dir, loader=None):
    """Run the local technical cut + signal build over `symbols`. `loader` lets
    tests inject synthetic frames; production uses lib/ta.load_ohlcv."""
    load = loader or (lambda s: ta.load_ohlcv(s, years, cache_dir))
    tech = (spec.get("screening", {}) or {}).get("technical", {}) or {}
    filters = tech.get("compute_filters", [])
    breakout = "breakout" in str(spec.get("archetype", "")).lower() \
        or "prior_20d_high" in str((spec.get("entry") or {}).get("trigger", "")).lower() \
        or "20d_high" in str((spec.get("entry") or {}).get("trigger", "")).lower()

    candidates, rejected, gaps = [], [], []
    for sym in symbols:
        try:
            df = ta.add_indicators(load(sym))
        except Exception as exc:
            gaps.append(f"{sym}: {exc}")
            continue
        if len(df.dropna(subset=["ema50", "rsi14", "vol10"])) < 1:
            gaps.append(f"{sym}: insufficient history for indicators")
            continue
        ok, reasons = passes_technical(df, filters)
        if not ok:
            rejected.append({"symbol": sym, "why": reasons})
            continue
        entry_override = float(df["hh20"].iloc[-1]) if breakout else None
        sig = build_signal(df, spec, capital, entry_override=entry_override)
        if "skip" in sig:
            rejected.append({"symbol": sym, "why": [sig["skip"]]})
            continue
        candidates.append({"symbol": sym, **sig})
    candidates.sort(key=lambda c: c["rrr"], reverse=True)
    return {"candidates": candidates, "rejected": rejected, "data_gaps": gaps}


def load_spec(path):
    yaml = ta._need("yaml", "pyyaml")
    with open(path) as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------------------- #
# selftest (synthetic, offline)                                               #
# --------------------------------------------------------------------------- #
def _synth(kind):
    """Build a deterministic OHLCV frame: 'uptrend' passes an ema-pullback screen,
    'downtrend' fails it."""
    import numpy as np
    n = 260
    idx = pd.date_range("2023-01-02", periods=n, freq="B")
    if kind == "uptrend":
        base = np.linspace(100, 200, n)
        close = base + np.sin(np.arange(n) / 6) * 3
    else:
        base = np.linspace(200, 100, n)
        close = base + np.sin(np.arange(n) / 6) * 3
    close = pd.Series(close, index=idx)
    high = close + 1.5
    low = close - 1.5
    op = close.shift(1).fillna(close.iloc[0])
    vol = pd.Series([1000] * n, index=idx)
    vol.iloc[-1] = 2000  # last-bar volume surge
    return pd.DataFrame({"Open": op, "High": high, "Low": low,
                         "Close": close, "Volume": vol}, index=idx)


SELFTEST_SPEC = {
    "name": "selftest-ema-pullback", "archetype": "pullback",
    "screening": {"technical": {"compute_filters": [
        "ema50_rising", "Close > ema50", "rsi14 between 40 and 100"]}},
    "entry": {"trigger": "bullish candle near ema50"},
    "exit": {"stop": "ema50_minus_2atr", "target": "next_resistance", "min_rrr": 1.5},
    "sizing": {"risk_per_trade_pct": 1.0},
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--spec", help="path to a strategy <name>.yml")
    p.add_argument("--symbols", help="comma list of NSE symbols, or a file with one per line")
    p.add_argument("--years", type=int, default=2)
    p.add_argument("--capital", type=float, default=500000)
    p.add_argument("--out")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()

    if args.selftest:
        res = screen_compute(["UPTREND", "DOWNTREND"], SELFTEST_SPEC, 2, 500000,
                             "/tmp", loader=lambda s: _synth(s.lower()))
        print(json.dumps(res, indent=2, default=str))
        ok = (len(res["candidates"]) == 1 and res["candidates"][0]["symbol"] == "UPTREND"
              and any(r["symbol"] == "DOWNTREND" for r in res["rejected"]))
        print(f"\nselftest: {'PASS' if ok else 'FAIL'}", file=sys.stderr)
        sys.exit(0 if ok else 1)

    if not args.spec or not args.symbols:
        print("error: --spec and --symbols required (or use --selftest)", file=sys.stderr)
        sys.exit(2)
    spec = load_spec(args.spec)
    if os.path.exists(args.symbols):
        symbols = [l.strip().upper() for l in open(args.symbols) if l.strip()]
    else:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]

    cache_dir = "artifacts/.cache/ohlcv"
    res = screen_compute(symbols, spec, args.years, args.capital, cache_dir)
    res["config"] = {"spec": spec.get("name"), "symbols": len(symbols),
                     "capital": args.capital, "as_of": str(date.today()),
                     "screen_path": "compute (local lib/ta.py)"}
    out = json.dumps(res, indent=2, default=str)
    print(out)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        open(args.out, "w").write(out)
        print(f"\nwrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
