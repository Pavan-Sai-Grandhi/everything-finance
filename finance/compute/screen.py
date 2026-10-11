#!/usr/bin/env python3
"""discover screening + signal engine.

discover is strategy-AGNOSTIC: it runs whatever active, regime-fitting spec it is handed
(chosen by `strategy-manager pick`). This module is the deterministic core of that run — it
does NOT decide what to trade, it executes a spec's screening and signal rules on price
data.

The evaluator and signal math live in `finance/compute/strategy.py`, shared verbatim with
the backtest; this file is just the live-screen orchestration around it.

Reached through: run_strategy_screen.
"""
from __future__ import annotations

import json
import os
from datetime import date

from finance import paths
from finance import spine
from finance.compute import strategy
from finance.compute import ta
from finance.sources import prices

pd = ta.pd

# The screen engine IS finance/compute/strategy.py; these re-exports keep the skill workflow
# and the tests on exactly one implementation of each.
eval_filter = strategy.eval_filter
passes_technical = strategy.passes_technical
build_signal = strategy.build_signal


def screen_compute(symbols, spec, years, capital, loader=None):
    """Run the local technical cut + signal build over `symbols`. `loader` lets
    tests inject synthetic frames; production fetches via the data spine (`prices.history_df`,
    which owns the cache through paths.py). Source gaps remain visible."""
    try:
        filters = strategy.entry_filters(spec)
        features = strategy.referenced_features(spec)
        capital, _ = strategy.risk_parameters(spec, capital)
        strategy.validate_exit(spec.get("exit"))
    except ValueError as exc:
        return {"candidates": [], "rejected": [], "data_gaps": [f"invalid strategy: {exc}"]}

    candidates, rejected, gaps = [], [], []
    for sym in symbols:
        try:
            if loader is None:
                raw, source_gaps = prices.history_df(sym, f"{years}y", adjusted=True)
                gaps.extend(f"{sym}: {gap}" for gap in source_gaps)
            else:
                raw = loader(sym)
            if raw is None or len(raw) == 0:
                raise ValueError("no usable price history")
            df = ta.materialize(ta.add_indicators(raw), features)
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
        try:
            sig = build_signal(df, spec, capital)
        except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
            gaps.append(f"{sym}: cannot construct signal: {exc}")
            continue
        if "skip" in sig:
            rejected.append({"symbol": sym, "why": [sig["skip"]]})
            continue
        candidates.append({"symbol": sym, "as_of": str(df.index[-1].date()), **sig})
    candidates.sort(key=lambda c: c["rrr"], reverse=True)
    return {"candidates": candidates, "rejected": rejected, "data_gaps": gaps}


def load_spec(path):
    yaml = ta._need("yaml", "pyyaml")
    with open(path) as f:
        return yaml.safe_load(f)


def resolve_symbols(symbols):
    """The universe as callers express it — a list, comma-string, file path or named
    universe — resolved by the one authority in `sources/universe.py`."""
    from finance.sources import universe
    return universe.resolve_symbols(symbols)[0]


def run(spec, symbols=None, years=2, capital=500000, out=None):
    """The whole live screen in the shared data-spine envelope.

    `spec` is a path to a strategy YAML — the rules always come from a spec, never from
    here. `symbols` is the universe to screen; when omitted it falls back to the spec's own
    `universe.source`, so `universe: {source: nifty500}` resolves without a caller. The
    complete result, every rejection and its reason included, is written to `out` (default
    `artifacts/discover/<date>.json`); the envelope returns the config, the ranked
    candidates and the rejection tally.
    """
    from finance.sources import universe
    try:
        doc = load_spec(spec)
        if not isinstance(doc, dict):
            raise ValueError("strategy must be a mapping")
        strategy.entry_filters(doc)
        strategy.referenced_features(doc)
        capital, _ = strategy.risk_parameters(doc, capital)
        strategy.validate_exit(doc.get("exit"))
        if symbols is None:
            symbols = (doc.get("universe") or {}).get("source")
        syms, uni_gaps = universe.resolve_symbols(symbols)
        res = screen_compute(syms, doc, years, capital)
    except Exception as exc:
        return spine.envelope(False, "finance.compute.screen", {}, [f"cannot run strategy screen: {exc}"])
    price_dates = sorted({candidate["as_of"] for candidate in res["candidates"] if candidate.get("as_of")})
    res["config"] = {"spec": doc.get("name"), "spec_path": spec, "symbols": len(syms),
                     "capital": capital, "years": years, "generated_on": str(date.today()),
                     "as_of": price_dates[0] if len(price_dates) == 1 else None,
                     "price_dates": price_dates}
    path = out or paths.report_path("discover", ext="json")
    gaps = list(res["data_gaps"]) + uni_gaps
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
    "entry": {"signal": ["ema50_rising", "Close > ema50", "rsi14 between 40 and 100"],
              "trigger": "synthetic test condition: rising EMA50, close above EMA50 and RSI 40–100"},
    "exit": {"stop": "ema50_minus_2atr", "target": "next_resistance", "min_rrr": 1.5},
    "sizing": {"risk_per_trade_pct": 1.0},
}
