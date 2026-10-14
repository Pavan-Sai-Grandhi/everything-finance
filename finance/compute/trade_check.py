#!/usr/bin/env python3
"""Re-validate a trade's levels and thesis; never infer or execute a fill.

Decision prices come from prices.history (or a supplied OHLCV CSV). Broker LTP is
only a mark for unrealized position value. Entry and elapsed sessions require a
recorded broker fill, not the idea's planned entry or creation date. Shared TA
primitives define moving averages exactly as in screening and backtesting.
"""
import csv
import re

from finance import spine
from finance.deps import load_yaml
from finance.sources import prices

_SOURCE = "finance.compute.trade_check"


def load_ohlcv_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as stream:
        return [{str(k).strip().lower(): v for k, v in row.items()}
                for row in csv.DictReader(stream)]


def _positive(value):
    # A percentage or boolean is not a price, quantity, or session count.
    number = None if isinstance(value, bool) or "%" in str(value) else spine.f(value)
    return number if number is not None and number > 0 else None


def _price_rows(raw, gaps):
    """Validate before ordering: missing/bad bars must remain visible as gaps."""
    rows, seen = [], set()
    for row in raw:
        if not isinstance(row, dict):
            gaps.append("invalid price row skipped")
            continue
        day = spine.iso_date(row.get("date"))
        close = _positive(row.get("close"))
        high = _positive(row.get("high"))
        low = _positive(row.get("low"))
        if day is None or None in (close, high, low) or not low <= close <= high:
            gaps.append(f"invalid OHLC row skipped: {day or 'date unknown'}")
            continue
        if day in seen:
            raise ValueError(f"duplicate price date {day}; cannot choose a bar")
        seen.add(day)
        rows.append({"date": day, "close": close, "high": high, "low": low})
    return sorted(rows, key=lambda row: row["date"])


def parse_ma(text):
    """A complete MA reference, with a valid TA-Lib period (at least two)."""
    match = re.fullmatch(r"(\d+)\s*[-\s]?\s*(?:day\s*)?(ema|dma|sma|ma)", text.lower()) \
        or re.fullmatch(r"(ema|dma|sma|ma)\s*[-\s]?\s*(\d+)", text.lower())
    if not match:
        return None
    a, b = match.groups()
    period, kind = (int(a), b) if a.isdigit() else (int(b), a)
    return ("ema" if kind == "ema" else "sma", period) if period >= 2 else None


def eval_condition(cond, closes, ma_closes=None):
    """Evaluate only unambiguous price comparisons; prose remains manual review.

    `closes` are nominal decision closes; `ma_closes` (default `closes`) is the adjusted
    series moving averages are computed on, ending on the same bar."""
    ma_closes = closes if ma_closes is None else ma_closes
    manual = ("manual", f"cannot evaluate as a price condition: {cond!r}")
    if not isinstance(cond, str) or not closes:
        return manual
    text = cond.lower().strip()
    match = re.fullmatch(
        r"(?:(?:daily\s+)?(?:close|price)(?:\s+(?:falls?|breaks?|rises?))?|breaks?)"
        r"\s+(below|under|above|over)\s+(.+)", text)
    if match:
        relation, level = match.groups()
        below = relation in ("below", "under")
    else:
        match = re.fullmatch(r"break of (?:breakout )?pivot\s+(.+)", text)
        if not match:
            return manual
        below, level = True, match[1]

    ma = parse_ma(level)
    if ma:
        kind, period = ma
        if len(ma_closes) < period:
            return ("manual", f"not enough bars for {period}-{kind.upper()} in {cond!r}")
        try:
            from finance.compute import ta
            target = spine.f(getattr(ta, kind)(ta.pd.Series(ma_closes, dtype=float), period).iloc[-1])
        except Exception as exc:  # dependency/indicator failure cannot certify a condition
            return ("manual", f"{period}-{kind.upper()} unavailable: {exc}")
        if target is None:
            return manual
        label = f"{period}-{kind.upper()} ({target:.2f})"
    else:
        if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{2,3})+)(?:\.\d+)?", level):
            return manual
        target = _positive(level)
        if target is None:
            return manual
        label = f"{target:.2f}"
    last = _positive(closes[-1])
    if last is None:
        return manual
    fired = last < target if below else last > target
    detail = f"close {last:.2f} {'is' if fired else 'not'} {'below' if below else 'above'} {label} — {cond}"
    return ("fired" if fired else "ok", detail)


def sessions_since(rows, entry_date):
    """Elapsed observed sessions after the fill session; unknown if coverage is short."""
    entered = spine.iso_date(entry_date)
    days = [spine.iso_date(row.get("date")) for row in rows]
    if not entered or not days or None in days:
        return None
    days = sorted(set(days))
    if not days[0] <= entered <= days[-1]:
        return None
    return sum(day > entered for day in days)


def check(trade, ohlcv=None, ltp=None, entry=None, qty=None, sessions_held=None):
    """Return a recommendation and unrealized metrics in the standard envelope.

    `entry` overrides the recorded `fill_avg`; planned entries are never used.
    `qty` overrides actual `sizing.qty` on an open artifact. `sessions_held` can
    supply a verified elapsed count when the price history cannot cover the fill.
    Neither EXIT_* nor an unrealized metric is evidence of an executed exit.
    """
    identity = {"source_trade": str(trade)}
    try:
        doc = load_yaml(trade)
        if not isinstance(doc, dict):
            raise ValueError("trade must be a mapping")
        plan = doc.get("plan") or {}
        sizing = doc.get("sizing") or {}
        if not isinstance(plan, dict) or not isinstance(sizing, dict):
            raise ValueError("plan and sizing must be mappings")
        direction = str(doc.get("direction") or "long").lower()
        if direction not in ("long", "short"):
            raise ValueError("direction must be long or short")
    except Exception as exc:  # unreadable or malformed user artifact is a labelled gap
        return spine.envelope(False, _SOURCE, identity, [f"cannot read trade {trade}: {exc}"])

    symbol = doc.get("symbol", "?")
    identity["symbol"] = symbol
    gaps = []

    def positive(value, label):
        result = _positive(value)
        if value is not None and result is None:
            gaps.append(f"{label} must be a finite positive number; skipped")
        return result

    def session_count(value, label, allow_zero=False):
        number = spine.f(value) if not isinstance(value, bool) and "%" not in str(value) else None
        if number is not None and number.is_integer() and number >= (0 if allow_zero else 1):
            return int(number)
        if value is not None:
            gaps.append(f"{label} must be a {'nonnegative' if allow_zero else 'positive'} integer; skipped")
        return None

    stop = positive(plan.get("stop"), "stop")
    target = positive(plan.get("target"), "target")
    entry = positive(entry if entry is not None else doc.get("fill_avg"), "fill price")
    qty = positive(qty if qty is not None else
                   sizing.get("qty") if doc.get("status") == "open" else None, "quantity")
    ltp = positive(ltp, "personal LTP")
    time_stop = session_count(plan.get("time_stop_sessions"), "time stop")
    entered = spine.iso_date(doc.get("entry_date"))
    if entry is None:
        gaps.append("entry fill unknown — unrealized R and computed P&L unavailable")
    invalidations = doc.get("thesis_invalidation") or []
    if isinstance(invalidations, str):
        invalidations = [invalidations]
    if not isinstance(invalidations, list):
        gaps.append("thesis_invalidation must be a list of conditions; skipped")
        invalidations = []

    # Plan levels are nominal rupees, so breaches are read on unadjusted bars; moving
    # averages use the split/dividend-adjusted series shared with screening/backtests.
    try:
        if ohlcv:
            raw = adjusted_raw = load_ohlcv_csv(ohlcv)
        else:
            env = prices.history(symbol, period="1y", adjusted=False)
            gaps.extend(env.get("gaps", []))
            raw = adjusted_raw = env.get("data", {}).get("candles", [])
            # The adjusted series is only read by moving-average conditions.
            if any(re.search(r"\b(?:\d+\s*-?\s*(?:day\s*)?)?(?:ema|dma|sma|ma)\b", str(c).lower())
                   for c in invalidations):
                adj_env = prices.history(symbol, period="1y", adjusted=True)
                gaps.extend(g for g in adj_env.get("gaps", []) if g not in gaps)
                adjusted_raw = adj_env.get("data", {}).get("candles", [])
        before = len(gaps)
        rows = _price_rows(raw, gaps)
        missing_bars = len(gaps) > before
        adjusted_rows = rows if adjusted_raw is raw else _price_rows(adjusted_raw, [])
    except Exception as exc:
        return spine.envelope(False, _SOURCE, identity, gaps + [f"cannot read price data for {symbol}: {exc}"])
    if not rows:
        return spine.envelope(False, _SOURCE, identity, gaps + [f"no price data for {symbol}"])
    if entered and rows[-1]["date"] < entered:
        return spine.envelope(False, _SOURCE, identity, gaps + ["price history ends before entry; no post-entry decision price"])

    closes = [row["close"] for row in rows]
    ma_closes = [row["close"] for row in adjusted_rows]
    if not adjusted_rows or adjusted_rows[-1]["date"] != rows[-1]["date"]:
        gaps.append("adjusted history does not end on the decision bar; moving-average conditions left for manual review")
        ma_closes = []
    last = rows[-1]
    price = last["close"]
    mark = ltp if ltp is not None else price
    # A daily high/low can predate an intraday fill. With no known fill date, or on
    # its own day, only the decision close is usable; never assume an old breach.
    # Check every session after the fill, so a breach still counts after price recovers.
    window = [row for row in rows if entered is not None and row["date"] > entered]
    if not window:
        window = [{"date": last["date"], "low": price, "high": price}]
        gaps.append("entry date unknown or same as latest bar — intrabar breaches require post-fill evidence; using close only")
    long = direction == "long"
    reasons, manual, thesis_fired = [], [], []
    checked = stop is not None or target is not None
    for condition in invalidations:
        status, detail = eval_condition(condition, closes, ma_closes)
        if status == "manual":
            manual.append(detail)
        else:
            checked = True
            if status == "fired":
                thesis_fired.append(detail)

    held = session_count(sessions_held, "sessions held", allow_zero=True) if sessions_held is not None \
        else None if missing_bars else sessions_since(rows, entered)
    if time_stop is not None and held is None:
        gaps.append("time stop unassessed — need entry_date and covering price history, or verified sessions_held")
    checked = checked or (time_stop is not None and held is not None)
    adverse, favourable = ("low", "high") if long else ("high", "low")
    stop_bar = next((row for row in window if stop is not None
                     and (row["low"] <= stop if long else row["high"] >= stop)), None)
    target_bar = next((row for row in window if target is not None
                       and (row["high"] >= target if long else row["low"] <= target)), None)
    if stop_bar:
        verdict = "EXIT_STOP"
        reasons.append(f"STOP breached on {stop_bar['date']}: {adverse} {stop_bar[adverse]:.2f} "
                       f"vs stop {stop:.2f}")
    elif thesis_fired:
        verdict = "EXIT_THESIS"
        reasons.extend(f"thesis invalidated: {detail}" for detail in thesis_fired)
    elif target_bar:
        verdict = "EXIT_TARGET"
        reasons.append(f"TARGET reached on {target_bar['date']}: {favourable} "
                       f"{target_bar[favourable]:.2f} vs target {target:.2f} (book or trail per plan)")
    elif time_stop is not None and held is not None and held >= time_stop:
        verdict = "EXIT_TIME"
        reasons.append(f"TIME stop: held {held} sessions >= {time_stop}, neither stop nor target hit")
    else:
        verdict = "HOLD"
        reasons.append("no mechanical exit trigger; review any outstanding gaps and manual conditions")
    if not checked:
        gaps.append("no evaluable stop/target/invalidation/time stop — this HOLD is the absence of a check, not a passed one")
        manual.append("nothing mechanical was checked; confirm the plan and conditions by hand")

    def metric(value, label):
        number = spine.f(value)
        if number is None:
            gaps.append(f"{label} calculation is nonfinite; unavailable")
            return None
        return round(number, 2)

    unreal_r = pnl = remaining_rrr = None
    if entry is not None:
        move = mark - entry if long else entry - mark
        pnl = metric(move * qty, "unrealized P&L") if qty is not None else None
        if stop is not None:
            risk = entry - stop if long else stop - entry
            if risk > 0:
                unreal_r = metric(move / risk, "unrealized R")
            else:
                gaps.append("stop is not on the risk side of the fill — unrealized R unavailable")
    if target is not None and stop is not None:
        if long and stop < price < target:
            remaining_rrr = metric((target - price) / (price - stop), "remaining RRR")
        elif not long and target < price < stop:
            remaining_rrr = metric((price - target) / (stop - price), "remaining RRR")

    return spine.envelope(True, _SOURCE, {
        **identity, "direction": direction, "as_of": last["date"],
        "verdict": verdict, "reasons": reasons, "manual_review": manual,
        "regime_check": "deferred_to_skill" if doc.get("strategy") else "n/a",
        "metrics": {
            "price": round(price, 2), "mark_price": round(mark, 2),
            "mark_source": "personal_ltp" if ltp is not None else "decision_close",
            "entry": entry, "stop": stop, "target": target, "qty": qty,
            "sessions_held": held, "time_stop_sessions": time_stop,
            "unrealized_R": unreal_r, "unrealized_pnl": pnl,
            "remaining_rrr_to_target": remaining_rrr,
        },
    }, gaps)
