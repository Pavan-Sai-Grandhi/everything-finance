#!/usr/bin/env python3
"""find-trade screening + signal engine (everything-finance plugin).

find-trade is strategy-AGNOSTIC: it runs whatever ACTIVE, regime-fitting strategy
spec it is handed (chosen by `strategy-manager pick`). This script is the
deterministic core of that run — it does NOT decide *what* to trade, it executes a
spec's screening + signal rules on price data:

  1. screen_compute()  — the local technical cut (spec.screening.technical.compute_filters)
                         over a universe, using the shared indicators in finance/compute/ta.py.
                         This is the fallback when the TradingView provider is
                         unreachable, and the offline-testable heart of the engine.
  2. build_signal()    — turns a surviving stock into entry / stop / target / RRR /
                         qty from the spec's entry/exit/sizing blocks.

The evaluator + signal math live in `finance/compute/strategy.py`, shared verbatim with the
backtest; this file is just the live-screen orchestration around it.

Usage:
  python3 -m finance.compute.screen --spec <strategy>.yml --symbols RELIANCE,TCS[,...] \
      --capital 500000 --years 2 --out artifacts/find-trade/2026-06-12.json
  python3 -m finance.compute.screen --selftest         # synthetic data, no network
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

from finance import paths
from finance import spine
from finance.compute import strategy
from finance.compute import ta
from finance.sources import prices  # data spine — EOD history; indicators via ta.py

pd = ta.pd

# The screen engine IS finance/compute/strategy.py — re-export the pieces the SKILL workflow
# the tests reference, so there is exactly one implementation of each.
eval_filter = strategy.eval_filter
passes_technical = strategy.passes_technical
build_signal = strategy.build_signal


# --------------------------------------------------------------------------- #
# orchestration                                                               #
# --------------------------------------------------------------------------- #
def _spine_loader(years):
    """Default price loader: EOD history through the data spine (`prices.history_df`,
    yfinance under the hood), adjusted so the live screen shares the backtest's series.
    Indicators are still computed by `ta.add_indicators` — the spine fetches, ta.py decides."""
    def load(sym):
        df, gaps = prices.history_df(sym, f"{years}y", adjusted=True)
        if df is None or len(df) == 0:
            raise RuntimeError(gaps[0] if gaps else "no price history")
        return df
    return load


def screen_compute(symbols, spec, years, capital, cache_dir, loader=None):
    """Run the local technical cut + signal build over `symbols`. `loader` lets
    tests inject synthetic frames; production fetches via the data spine (`prices.history_df`,
    which self-caches through paths.py — `cache_dir` is kept for the injected-loader API)."""
    load = loader or _spine_loader(years)
    tech = (spec.get("screening", {}) or {}).get("technical", {}) or {}
    filters = tech.get("compute_filters", [])
    features = strategy.referenced_features(spec)
    breakout = "breakout" in str(spec.get("archetype", "")).lower() \
        or "prior_20d_high" in str((spec.get("entry") or {}).get("trigger", "")).lower() \
        or "20d_high" in str((spec.get("entry") or {}).get("trigger", "")).lower() \
        or "Close > hh20" in filters

    candidates, rejected, gaps = [], [], []
    for sym in symbols:
        try:
            df = ta.materialize(ta.add_indicators(load(sym)), features)
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


def resolve_symbols(symbols):
    """The universe as callers express it: a list, a comma-separated string, or a path to a
    file with one NSE symbol per line."""
    if isinstance(symbols, str):
        rows = (open(symbols).read().splitlines() if os.path.exists(symbols)
                else symbols.split(","))
    else:
        rows = list(symbols or [])
    return [str(s).strip().upper() for s in rows if str(s).strip()]


def run(spec, symbols, years=2, capital=500000, out=None):
    """The whole live screen in the shared data-spine envelope.

    `spec` is a path to a strategy YAML — the rules always come from a spec, never from
    here. The complete result, every rejection and its reason included, is written to `out`
    (default `artifacts/find-trade/<date>.json`); the envelope returns the config, the
    ranked candidates and the rejection tally, so a caller reads the file only when it
    wants to know why a name was dropped.
    """
    doc = load_spec(spec)
    syms = resolve_symbols(symbols)
    res = screen_compute(syms, doc, years, capital, paths.cache_dir("ohlcv"))
    res["config"] = {"spec": doc.get("name"), "spec_path": spec, "symbols": len(syms),
                     "capital": capital, "years": years, "as_of": str(date.today())}
    path = out or paths.report_path("find-trade", ext="json")
    gaps = list(res["data_gaps"])
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(res, fh, indent=2, default=str)
    except OSError as exc:
        gaps.append(f"could not write the screen result to {path}: {exc}")
        path = None
    if not res["candidates"]:
        gaps.append(f"no candidate passed {doc.get('name')!r} in this universe")
    return spine.envelope(
        bool(res["candidates"]), "finance.compute.screen",
        {"config": res["config"], "candidates": res["candidates"],
         "rejected_count": len(res["rejected"]), "report_path": path},
        gaps)


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
    env = run(args.spec, args.symbols, years=args.years, capital=args.capital,
              out=args.out)
    print(json.dumps(env, indent=2, default=str))


if __name__ == "__main__":
    main()
