#!/usr/bin/env python3
"""Spec -> signal engine for the everything-finance plugin.

The ONE place a strategy spec becomes trade logic (`ta.py` turns OHLCV into
columns; this turns spec + columns into entries/stops/targets/size). The live
screen (find-trade/screen.py, latest bar) and the backtest (backtest/backtest.py,
every bar) both sit on it, so they can't disagree about what a strategy means —
which is what makes the backtest strategy-agnostic.

Two halves:
  1. A tiny SAFE vectorized filter language (NOT python eval) over indicator
     columns — the single evaluator both paths call.
  2. build_signal() -> a live entry/stop/target/size dict; build_bt_strategy() ->
     a Backtesting.py Strategy class driven entirely by the spec.

Pure/deterministic except build_bt_strategy (imports Backtesting.py); the filter
language and signal math are unit-tested offline (find-trade/test_screen.py).
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import ta  # noqa: E402  (same dir)

pd = ta.pd


# --------------------------------------------------------------------------- #
# The SAFE filter language — ONE vectorized evaluator for both paths           #
# --------------------------------------------------------------------------- #
# Evaluated over a whole indicator DataFrame, returning a boolean Series aligned
# to it. Supported forms (case-insensitive AND/OR/BETWEEN):
#   "<col>"                       bare column -> truthy        (e.g. "ema50_rising")
#   "<term> > <term>"  / "<"/">="/"<="    comparison           (e.g. "Close > ema50")
#   "<col> between <x> and <y>"   inclusive range              ("rsi14 between 40 and 60")
#   "<expr> or <expr>"            disjunction                  ("nr7 or inside_bar")
# where <term> is a column, a number, or "<number> * <col>"   ("1.5 * vol10").
# AND across conditions is expressed by listing them separately (entry_filters).
def _term(token, df):
    """A term -> a Series or a scalar (number)."""
    token = token.strip()
    if "*" in token:
        a, b = (t.strip() for t in token.split("*", 1))
        return float(a) * _term(b, df)
    try:
        return float(token)
    except ValueError:
        if token not in df.columns:
            raise KeyError(f"unknown column in filter: {token!r}")
        return df[token]


def eval_series(expr, df):
    """Evaluate one filter expression over `df` -> boolean Series (NaN -> False)."""
    e = (expr.strip().replace(" OR ", " or ").replace(" AND ", " and ")
         .replace(" BETWEEN ", " between "))
    if " or " in e:
        out = None
        for part in e.split(" or "):
            s = eval_series(part, df)
            out = s if out is None else (out | s)
        return out.fillna(False)
    if " between " in e and " and " in e:
        col, rest = e.split(" between ", 1)
        lo, hi = rest.split(" and ", 1)
        v = _term(col, df)
        return ((v >= _term(lo, df)) & (v <= _term(hi, df))).fillna(False)
    for op in (">=", "<=", ">", "<"):
        if op in e:
            a, b = e.split(op, 1)
            va, vb = _term(a, df), _term(b, df)
            cmp = {">": lambda: va > vb, "<": lambda: va < vb,
                   ">=": lambda: va >= vb, "<=": lambda: va <= vb}[op]()
            return cmp.fillna(False) if hasattr(cmp, "fillna") else pd.Series(cmp, index=df.index)
    col = e.strip()
    if col not in df.columns:
        raise KeyError(f"unknown column in filter: {col!r}")
    return df[col].fillna(False).astype(bool)


def eval_filter(expr, row):
    """Latest-bar convenience: evaluate one expression against a Series `row`.
    Thin wrapper over the vectorized evaluator so the live screen and the backtest
    share ONE grammar (a 1-row frame is just the last bar)."""
    return bool(eval_series(expr, pd.DataFrame([row])).iloc[-1])


def passes_technical(df, filters):
    """True if the LATEST bar satisfies every filter. Returns (ok, reasons)."""
    reasons = []
    for f in filters or []:
        try:
            if not bool(eval_series(f, df).iloc[-1]):
                reasons.append(f"fail: {f}")
        except (KeyError, ValueError) as exc:
            reasons.append(f"uneval: {f} ({exc})")
    return (len(reasons) == 0), reasons


# --------------------------------------------------------------------------- #
# Spec introspection                                                           #
# --------------------------------------------------------------------------- #
def referenced_features(spec):
    """The features a spec mentions in its technical/entry expressions — registered
    patterns/signals or parameterized indicator tokens (ema100, rsi9, hh50, ...) —
    so the engine materializes exactly those columns and nothing more."""
    tech = (spec.get("screening", {}) or {}).get("technical", {}) or {}
    entry = spec.get("entry", {}) or {}
    exprs = list(tech.get("compute_filters", []) or [])
    exprs += list(entry.get("signal", []) or [])
    exprs += list(entry.get("confirm_indicators", []) or [])
    names = set()
    for expr in exprs:
        for tok in re.findall(r"[A-Za-z_]\w*", str(expr)):
            if ta.is_feature(tok):
                names.add(tok)
    return names


def entry_filters(spec):
    """The machine-evaluable entry condition: prefer an explicit `entry.signal`
    (the precise trigger, e.g. coil_breakout), else fall back to the coarse
    `compute_filters` (for setups whose held state IS the entry)."""
    entry = spec.get("entry", {}) or {}
    sig = entry.get("signal")
    if sig:
        return list(sig)
    tech = (spec.get("screening", {}) or {}).get("technical", {}) or {}
    return list(tech.get("compute_filters", []) or [])


def entry_signal_series(df, spec):
    """Boolean Series: where the spec's full entry condition holds, bar by bar."""
    df = ta.materialize(df, referenced_features(spec))
    out = pd.Series(True, index=df.index)
    for f in entry_filters(spec):
        out &= eval_series(f, df)
    return out.fillna(False)


# --------------------------------------------------------------------------- #
# Stop / target / size — the risk layer, shared by live and historical         #
# --------------------------------------------------------------------------- #
def resolve_stop(df, kind):
    """Stop level from spec.exit.stop on the latest bar."""
    last = df.iloc[-1]
    if kind == "ema50_minus_2atr":
        return float(last["ema50"] - 2 * last["atr14"])
    if kind == "range_low":
        return float(last["ll20"])
    return float(df["Low"].rolling(10).min().iloc[-1])   # recent_swing_low


def target_from_spec(entry, risk, exitb, last):
    """(target_price, basis) from spec.exit.target. measured_move -> the prior
    consolidation height; else a next-resistance proxy placed at min_rrr."""
    min_rrr = float(exitb.get("min_rrr", 1.5))
    target_spec = str(exitb.get("target", "")).lower()
    if "measured" in target_spec:
        return entry + float(last["hh20"] - last["ll20"]), "measured-move"
    return entry + min_rrr * risk, "min-RRR (next resistance to be confirmed on chart)"


def build_signal(df, spec, capital, entry_override=None):
    """Construct a live trade signal for one stock from the spec. Returns a dict,
    or {skip: reason} when the RRR gate or a malformed stop rejects it."""
    last = df.iloc[-1]
    exitb = spec.get("exit", {}) or {}
    sizing = spec.get("sizing", {}) or {}
    min_rrr = float(exitb.get("min_rrr", 1.5))

    entry = float(entry_override) if entry_override is not None else float(last["Close"])
    stop = resolve_stop(df, exitb.get("stop", "recent_swing_low"))
    if not (stop < entry) or (entry - stop) / entry > 0.15:
        return {"skip": f"malformed/too-wide stop (entry {entry:.2f}, stop {stop:.2f})"}
    risk = entry - stop
    target, target_basis = target_from_spec(entry, risk, exitb, last)
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
# Backtest strategy factory — the spec, as a Backtesting.py Strategy            #
# --------------------------------------------------------------------------- #
def prepare_backtest_frame(df, spec):
    """Indicator + feature columns + a numeric `entry_signal` (1.0/0.0) column,
    ready for Backtesting.py — so the backtest never re-derives the entry."""
    enriched = ta.add_indicators(df)
    enriched = ta.materialize(enriched, referenced_features(spec))
    enriched["entry_signal"] = entry_signal_series(enriched, spec).astype(float)
    return enriched


def build_bt_strategy(spec, capital, risk_pct=None):
    """Return a Backtesting.py Strategy subclass that trades `spec` exactly: enter
    next-open when entry_signal fires (one position at a time), stop from
    exit.stop, target from exit.target gated at min_rrr, exit on time_stop, size
    by risk_per_trade_pct. The frame must come from prepare_backtest_frame()."""
    ta._need("backtesting")
    from backtesting import Strategy

    exitb = spec.get("exit", {}) or {}
    sizing = spec.get("sizing", {}) or {}
    stop_kind = exitb.get("stop", "recent_swing_low")
    measured = "measured" in str(exitb.get("target", "")).lower()
    min_rrr = float(exitb.get("min_rrr", 1.5))
    time_stop = int(exitb.get("time_stop_sessions", 20) or 20)
    rpct = float(risk_pct if risk_pct is not None
                 else sizing.get("risk_per_trade_pct", 1.0))

    class SpecStrategy(Strategy):
        def init(self):
            pass

        def next(self):
            i = len(self.data) - 1
            # time stop on any open trade (held >= time_stop sessions)
            for tr in list(self.trades):
                if i - tr.entry_bar >= time_stop:
                    tr.close()
            if self.position or not bool(self.data.entry_signal[-1]):
                return
            # stop from the spec, resolved on the signal bar (matches live)
            if stop_kind == "ema50_minus_2atr":
                stop = float(self.data.ema50[-1] - 2 * self.data.atr14[-1])
            elif stop_kind == "range_low":
                stop = float(self.data.ll20[-1])
            else:                                   # recent_swing_low
                stop = float(min(self.data.Low[-10:]))
            entry = float(self.data.Close[-1])      # sizing proxy; fill is next open
            if not (stop < entry) or (entry - stop) / entry > 0.15:
                return
            risk = entry - stop
            if measured:
                target = entry + float(self.data.hh20[-1] - self.data.ll20[-1])
            else:
                target = entry + min_rrr * risk
            if (target - entry) / risk < min_rrr:
                return
            qty = int((capital * rpct / 100) / risk)
            qty = min(qty, int(self.equity * 0.95 / entry))   # never over-commit cash
            if qty < 1:
                return
            # tag the risk-per-share so the R-multiple is recoverable even when the
            # trade later closes on the time-stop (SL/TP columns can go NaN then)
            self.buy(size=qty, sl=stop, tp=target, tag=round(risk, 4))

    return SpecStrategy
