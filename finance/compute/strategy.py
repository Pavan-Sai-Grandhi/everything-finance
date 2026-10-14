#!/usr/bin/env python3
"""Spec -> signal engine.

The ONE place a strategy spec becomes trade logic (`ta.py` turns OHLCV into columns; this
turns spec + columns into entries/stops/targets/size). The live screen (`screen.py`, latest
bar) and the backtest (`backtest.py`, every bar) both sit on it, so they cannot disagree
about what a strategy means — which is what makes the backtest strategy-agnostic.

The filter language is a tiny SAFE vectorized evaluator, NOT python eval.
"""
from __future__ import annotations

import re
import math
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from finance.compute import ta

pd = ta.pd


# Evaluated over a whole indicator DataFrame, returning a boolean Series aligned
# to it. Supported forms (case-insensitive AND/OR/BETWEEN):
#   "<col>"                       bare column -> truthy        (e.g. "ema50_rising")
#   "<term> > <term>"  / "<"/">="/"<="    comparison           (e.g. "Close > ema50")
#   "<col> between <x> and <y>"   inclusive range              ("rsi14 between 40 and 60")
#   "<expr> or <expr>"            disjunction                  ("nr7 or inside_bar")
# where <term> is a column, a number, or "<number> * <col>"   ("1.5 * vol10").
# AND across conditions is expressed by listing them separately (entry_filters).
def _block(doc, key):
    if not isinstance(doc, dict):
        raise ValueError("strategy blocks must be mappings")
    value = doc.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a mapping")
    return value


def _conditions(value, label, required=False):
    """One grammar contract for entry, screening, and exit condition lists."""
    if value is None:
        value = []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{label} must be a nonempty expression or a list of nonempty expressions")
    if required and not value:
        raise ValueError(f"{label} needs at least one machine condition")
    return [item.strip() for item in value]


def _constant(token):
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("expression constants must be finite")
    return value


def _term(token, df):
    """A finite numeric constant, a column, or a constant times a term."""
    token = token.strip()
    if "*" in token:
        a, b = (part.strip() for part in token.split("*", 1))
        return _constant(a) * _term(b, df)
    # Try numeric syntax separately so a nonfinite number cannot fall through as
    # an alleged missing column. Actual columns keep their case-sensitive names.
    try:
        float(token)
    except ValueError:
        if token not in df.columns:
            raise KeyError(f"unknown column in filter: {token!r}")
        return df[token]
    return _constant(token)


def eval_series(expr, df):
    """Evaluate the safe grammar, always returning an aligned boolean Series."""
    expr = _conditions(expr, "filter", required=True)
    if len(expr) != 1:
        raise ValueError("eval_series accepts one expression")
    e = re.sub(r"\s+", " ", expr[0])
    e = re.sub(r"\b(or|and|between)\b", lambda match: match[0].lower(), e, flags=re.I)

    def aligned(value):
        return value.fillna(False).astype(bool) if isinstance(value, pd.Series) else pd.Series(bool(value), index=df.index)

    if " or " in e:
        out = pd.Series(False, index=df.index)
        for part in e.split(" or "):
            out |= eval_series(part, df)
        return out
    if " between " in e and " and " in e:
        col, rest = e.split(" between ", 1)
        lo, hi = rest.split(" and ", 1)
        value = _term(col, df)
        return aligned((value >= _term(lo, df)) & (value <= _term(hi, df)))
    for op in (">=", "<=", ">", "<"):
        if op in e:
            a, b = e.split(op, 1)
            va, vb = _term(a, df), _term(b, df)
            compared = {">": lambda: va > vb, "<": lambda: va < vb,
                        ">=": lambda: va >= vb, "<=": lambda: va <= vb}[op]()
            return aligned(compared)
    if e not in df.columns:
        raise KeyError(f"unknown column in filter: {e!r}")
    return aligned(df[e])


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


def referenced_features(spec):
    """The features a spec mentions in its technical/entry expressions — registered
    patterns/signals or parameterized indicator tokens (ema100, rsi9, hh50, ...) —
    so the engine materializes exactly those columns and nothing more."""
    tech = _block(_block(spec, "screening"), "technical")
    entry = _block(spec, "entry")
    exitb = _block(spec, "exit")
    exprs = _conditions(tech.get("compute_filters"), "compute_filters")
    exprs += _conditions(entry.get("signal"), "entry.signal")
    exprs += _conditions(entry.get("confirm_indicators"), "confirm_indicators")
    exprs += _conditions(exitb.get("exit_signal"), "exit_signal")
    names = set()
    for expr in exprs:
        for tok in re.findall(r"[A-Za-z_]\w*", str(expr)):
            if ta.is_feature(tok):
                names.add(tok)
    return names


def entry_filters(spec):
    """Require an explicit executable entry; screening/prose cannot define trades."""
    return _conditions(_block(spec, "entry").get("signal"), "entry.signal", required=True)


def entry_signal_series(df, spec):
    """Boolean Series: where the spec's full entry condition holds, bar by bar."""
    df = ta.materialize(df, referenced_features(spec))
    out = pd.Series(True, index=df.index)
    for f in entry_filters(spec):
        out &= eval_series(f, df)
    return out.fillna(False)


def exit_signal_series(df, spec):
    """Boolean Series where the spec's `exit.exit_signal` holds — entry's grammar,
    for exits a price target can't express (a mean-reversion close back above the
    5-SMA, a trend break below the 20-EMA). Empty when the spec names none, leaving
    stop/target/time-stop to govern the close."""
    exprs = _conditions(_block(spec, "exit").get("exit_signal"), "exit_signal")
    if not exprs:
        return pd.Series(False, index=df.index)
    out = pd.Series(True, index=df.index)
    for f in exprs:
        out &= eval_series(f, df)
    return out.fillna(False)


def floor_stop(entry, stop, atr):
    """Floor a stop's distance from entry at the wider of 0.5*ATR and 1% of price.
    A narrow-range entry (NR/inside bar, a squeeze low) can sit a hair under the
    close, collapsing `risk = entry - stop` toward zero and exploding every
    R-multiple; no one trades a sub-1% stop anyway. Applied on both paths so live
    and backtest price risk identically. A nonfinite input is unusable, never unfloored."""
    entry, stop, atr = float(entry), float(stop), float(atr)
    if not all(math.isfinite(v) for v in (entry, stop, atr)) or atr < 0:
        raise ValueError("entry, stop and ATR must be usable finite values")
    floor = max(0.5 * atr, 0.01 * entry)
    return min(stop, entry - floor)


def resolve_stop(df, kind):
    """Stop level from spec.exit.stop on the latest bar."""
    validate_exit({"stop": kind})
    last = df.iloc[-1]
    if kind == "ema50_minus_2atr":
        return float(last["ema50"] - 2 * last["atr14"])
    if kind == "range_low":
        return float(last["ll20"])
    return float(df["Low"].rolling(10).min().iloc[-1])   # recent_swing_low


def minimum_rrr(exitb):
    """Validate the trading discipline floor shared by live and historical plans."""
    if exitb is None:
        exitb = {}
    if not isinstance(exitb, dict):
        raise ValueError("exit must be a mapping")
    value = exitb.get("min_rrr", 1.5)
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("min_rrr must be finite and at least 1.5") from exc
    if isinstance(value, bool) or not math.isfinite(result) or result < 1.5:
        raise ValueError("min_rrr must be finite and at least 1.5")
    return result


def target_kind(exitb):
    """Exact executable target names; prose belongs in the strategy rationale."""
    kind = exitb.get("target", "trailing" if exitb.get("trail_atr") else
                     "signal" if exitb.get("exit_signal") else "min_rrr")
    if kind not in ("measured_move", "min_rrr", "next_resistance", "trailing", "signal", "none"):
        raise ValueError("target must be measured_move, min_rrr, next_resistance, trailing, signal or none; put prose in rationale")
    if kind == "trailing" and not exitb.get("trail_atr"):
        raise ValueError("target trailing requires a positive trail_atr")
    if kind == "signal" and not _conditions(exitb.get("exit_signal"), "exit_signal"):
        raise ValueError("target signal requires exit_signal")
    if kind == "none" and not (exitb.get("trail_atr") or _conditions(exitb.get("exit_signal"), "exit_signal")):
        raise ValueError("target none requires trail_atr or exit_signal")
    return kind


def validate_exit(exitb):
    """Reject malformed executable exit rules before either engine fetches data."""
    minimum_rrr(exitb)
    exitb = {} if exitb is None else exitb
    stop = exitb.get("stop", "recent_swing_low")
    if stop not in ("recent_swing_low", "ema50_minus_2atr", "range_low"):
        raise ValueError("stop must be recent_swing_low, ema50_minus_2atr or range_low")
    sessions = exitb.get("time_stop_sessions", 20)
    if type(sessions) is not int or sessions <= 0:
        raise ValueError("time_stop_sessions must be a positive integer")
    trail = exitb.get("trail_atr", 0)
    if isinstance(trail, bool) or not isinstance(trail, (int, float)):
        raise ValueError("trail_atr must be a finite nonnegative number")
    try:
        valid = math.isfinite(trail) and trail >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("trail_atr must be a finite nonnegative number")
    target_kind(exitb)


def target_from_spec(entry, risk, exitb, last):
    """(target_price, basis) from spec.exit.target. measured_move -> the prior
    consolidation height; else a next-resistance proxy placed at min_rrr."""
    entry, risk = Decimal(str(entry)), Decimal(str(risk))
    min_rrr = Decimal(str(minimum_rrr(exitb)))
    kind = target_kind(exitb)
    if kind in ("trailing", "signal", "none"):
        raise ValueError("dynamic exit has no fixed target: backtest supported, live entry requires a sourced fixed objective")
    if kind == "measured_move":
        target = entry + Decimal(str(last["hh20"])) - Decimal(str(last["ll20"]))
        return float(target.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)), "measured-move"
    target = (entry + min_rrr * risk).quantize(Decimal("0.01"), rounding=ROUND_CEILING)
    return float(target), "min-RRR (next resistance to be confirmed on chart)"


def risk_parameters(spec, capital, risk_pct=None):
    """The shared capital/risk boundary for live sizing and historical runs."""
    sizing = spec.get("sizing") or {}
    if not isinstance(sizing, dict):
        raise ValueError("sizing must be a mapping")
    raw_risk = risk_pct if risk_pct is not None else sizing.get("risk_per_trade_pct", 1.0)
    if isinstance(capital, bool) or isinstance(raw_risk, bool):
        raise ValueError("capital and risk percent must be numbers")
    try:
        capital, risk_pct = float(capital), float(raw_risk)
    except (TypeError, ValueError) as exc:
        raise ValueError("capital and risk percent must be numbers") from exc
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("capital must be finite and positive")
    if not math.isfinite(risk_pct) or not 0 < risk_pct <= 1:
        raise ValueError("risk per trade must be positive and at most 1%")
    return capital, risk_pct



def validate_spec(spec, capital, risk_pct=None):
    """Check a trading spec's entry, features, sizing and exit once, before any fetch.

    Returns the validated `(capital, risk_pct)`; raises ValueError on the first problem.
    """
    entry_filters(spec)
    referenced_features(spec)
    capital, risk_pct = risk_parameters(spec, capital, risk_pct)
    validate_exit(spec.get("exit"))
    return capital, risk_pct

def build_signal(df, spec, capital, entry_override=None):
    """Construct a live trade signal for one stock from the spec. Returns a dict,
    or {skip: reason} when the RRR gate or a malformed stop rejects it."""
    try:
        capital, risk_pct = risk_parameters(spec, capital)
        last = df.iloc[-1]
        exitb = _block(spec, "exit")
        validate_exit(exitb)
        min_rrr = Decimal(str(minimum_rrr(exitb)))
        raw_entry = float(entry_override) if entry_override is not None else float(last["Close"])
        atr = float(last["atr14"])
        raw_stop = resolve_stop(df, exitb.get("stop", "recent_swing_low"))
        if not all(math.isfinite(v) for v in (raw_entry, atr, raw_stop)) or raw_entry <= 0 or atr < 0:
            raise ValueError("entry, stop and ATR must be usable finite values")
        # Size the published plan. Rounding after sizing can exceed the risk budget.
        entry_d = Decimal(str(raw_entry)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        stop = floor_stop(float(entry_d), raw_stop, atr)
        stop_d = Decimal(str(stop)).quantize(Decimal("0.01"), rounding=ROUND_FLOOR)
        entry, stop = float(entry_d), float(stop_d)
        if not 0 < stop_d < entry_d or (entry_d - stop_d) / entry_d > Decimal("0.15"):
            return {"skip": f"malformed/too-wide stop (entry {entry:.2f}, stop {stop:.2f})"}
        risk_d = entry_d - stop_d
        target, target_basis = target_from_spec(entry_d, risk_d, exitb, last)
        rrr_d = (Decimal(str(target)) - entry_d) / risk_d
        if not rrr_d.is_finite() or rrr_d < min_rrr:
            return {"skip": f"RRR {rrr_d:.2f} < min {min_rrr}"}
        budget = Decimal(str(capital)) * Decimal(str(risk_pct)) / 100
        qty = int(budget / risk_d)
        risk, rrr = float(risk_d), float(rrr_d)
    except (ValueError, TypeError, KeyError, IndexError, InvalidOperation, ZeroDivisionError) as exc:
        return {"skip": str(exc)}
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


def prepare_backtest_frame(df, spec):
    """Indicator + feature columns + a numeric `entry_signal` (1.0/0.0) column,
    ready for Backtesting.py — so the backtest never re-derives the entry."""
    enriched = ta.add_indicators(df)
    enriched = ta.materialize(enriched, referenced_features(spec))
    enriched["entry_signal"] = entry_signal_series(enriched, spec).astype(float)
    enriched["exit_signal"] = exit_signal_series(enriched, spec).astype(float)
    return enriched


def build_bt_strategy(spec, capital, risk_pct=None):
    """Return a Backtesting.py Strategy subclass that trades `spec` exactly: enter
    next-open when entry_signal fires (one position at a time); manage the close via
    exit.stop (floored), a fixed target gated at min_rrr, an optional ATR trailing
    stop, an optional discretionary exit_signal, and the time_stop; size by
    risk_per_trade_pct. The frame must come from prepare_backtest_frame()."""
    exitb = _block(spec, "exit")
    validate_exit(exitb)
    min_rrr = minimum_rrr(exitb)
    capital, rpct = risk_parameters(spec, capital, risk_pct)
    ta._need("backtesting")
    from backtesting import Strategy
    stop_kind = exitb.get("stop", "recent_swing_low")
    kind = target_kind(exitb)
    measured = kind == "measured_move"
    trail_atr = float(exitb.get("trail_atr", 0))
    use_exit_signal = bool(exitb.get("exit_signal"))
    no_target = kind in ("trailing", "none", "signal")
    time_stop = exitb.get("time_stop_sessions", 20)

    class SpecStrategy(Strategy):
        def init(self):
            pass

        def next(self):
            i = len(self.data) - 1
            for tr in list(self.trades):
                held = i - tr.entry_bar
                # discretionary exit (e.g. close back above the 5-SMA) takes priority
                if use_exit_signal and bool(self.data.exit_signal[-1]):
                    tr.close()
                    continue
                if held >= time_stop:
                    tr.close()
                    continue
                if trail_atr:   # ratchet the stop up under the high since entry
                    hi = float(max(self.data.High[-(held + 1):]))
                    new_sl = hi - trail_atr * float(self.data.atr14[-1])
                    if (tr.sl is None or new_sl > tr.sl) and new_sl < float(self.data.Close[-1]):
                        tr.sl = new_sl
            if self.position or not bool(self.data.entry_signal[-1]):
                return
            # stop from the spec, resolved on the signal bar (matches live)
            if stop_kind == "ema50_minus_2atr":
                stop = float(self.data.ema50[-1] - 2 * self.data.atr14[-1])
            elif stop_kind == "range_low":
                stop = float(self.data.ll20[-1])
            else:                                   # recent_swing_low
                if len(self.data) < 10:              # same rolling warmup as live
                    return
                stop = float(min(self.data.Low[-10:]))
            entry = float(self.data.Close[-1])      # sizing proxy; fill is next open
            try:                                    # warmup bars: live skips these too
                stop = floor_stop(entry, stop, self.data.atr14[-1])
            except ValueError:
                return
            if not (stop < entry) or (entry - stop) / entry > 0.15:
                return
            risk = entry - stop
            target = None
            if not no_target:
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
            # Preserve the original stop through trailing/closing. Realized R uses
            # the actual next-open fill, which can differ from this sizing proxy.
            self.buy(size=qty, sl=stop, tp=target, tag={"initial_stop": stop})

    return SpecStrategy
