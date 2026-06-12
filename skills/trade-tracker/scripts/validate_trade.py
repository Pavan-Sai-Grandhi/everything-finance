#!/usr/bin/env python3
"""Re-validate an open trade against its original rationale (everything-finance plugin).

Given a trade-idea artifact (the YAML find-trade / strategy-manager persist) and
current price data, this decides — deterministically — whether the trade should be HELD
or EXITED early, and why. It is the mechanical core of the trade-tracker skill: the skill
pulls live positions from the broker MCP (Kite/Upstox), then calls this per position so the
hold/exit call is reproducible rather than vibes.

Checks, in priority order (first hit wins the verdict):
  1. STOP        — price has breached the stoploss            -> EXIT_STOP
  2. THESIS      — a machine-checkable invalidation fired      -> EXIT_THESIS
  3. TARGET      — price reached the target                    -> EXIT_TARGET (book / trail)
  4. TIME_STOP   — held >= time_stop_sessions, neither S/T hit  -> EXIT_TIME
  5. otherwise                                                  -> HOLD
Qualitative invalidation conditions this script can't parse (e.g. "earnings miss") are
returned under `manual_review` for the skill/LLM to judge. Regime-change checks for
strategy-linked trades are likewise deferred to the skill (it re-runs regime.py).

Price source: yfinance (`<SYMBOL>.NS`) by default, or an OHLCV CSV via --ohlcv (offline /
testing). Actual broker fill can be injected with --entry / --qty / --ltp so the report
reflects the real position, not the planned one.

Usage:
  python3 validate_trade.py --trade artifacts/trades/TITAN-2026-06-11.yml
  python3 validate_trade.py --trade t.yml --ohlcv bars.csv --ltp 3650 --entry 3300 --qty 41
Exit code: 0 = HOLD, 10 = an EXIT_* verdict, 2 = error.
"""
import argparse, json, re, sys, subprocess
from datetime import date, datetime


def _need(mod, pip_name=None):
    try:
        return __import__(mod)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                               "--break-system-packages", pip_name or mod])
        return __import__(mod)


def load_yaml(path):
    yaml = _need("yaml", "pyyaml")
    with open(path) as f:
        return yaml.safe_load(f)


def load_ohlcv_csv(path):
    """CSV with header Date,Open,High,Low,Close,Volume -> list of dict rows (floats)."""
    rows = []
    with open(path) as f:
        header = [h.strip().lower() for h in f.readline().strip().split(",")]
        for line in f:
            line = line.strip()
            if not line:
                continue
            vals = line.split(",")
            r = dict(zip(header, vals))
            for k in ("open", "high", "low", "close", "volume"):
                if k in r and r[k] != "":
                    r[k] = float(r[k])
            rows.append(r)
    return rows


def fetch_ohlcv_yf(symbol, period="1y"):   # 1y (~248 bars) so 200-DMA conditions resolve
    yf = _need("yfinance")
    df = yf.download(symbol + ".NS", period=period, interval="1d",
                     auto_adjust=True, progress=False)
    if df is None or df.empty:
        return None
    pd = _need("pandas")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    rows = []
    for idx, row in df.iterrows():
        rows.append({"date": str(idx.date()), "open": float(row["Open"]),
                     "high": float(row["High"]), "low": float(row["Low"]),
                     "close": float(row["Close"]), "volume": float(row["Volume"])})
    return rows


def ema(values, span):
    if not values:
        return None
    k = 2 / (span + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def parse_ma(text):
    """Return (kind, period) for an MA reference in text, or None.
    kind in {'ema','sma'}.  '50-EMA','ema50','50 day EMA' -> ('ema',50);
    '200-DMA'/'200 SMA'/'50 MA' -> ('sma',200)."""
    t = text.lower()
    m = re.search(r"(\d+)\s*[-\s]?\s*(?:day\s*)?(ema|dma|sma|ma)\b", t) \
        or re.search(r"\b(ema|dma|sma|ma)\s*[-\s]?\s*(\d+)", t)
    if not m:
        return None
    g = m.groups()
    if g[0].isdigit():
        period, kw = int(g[0]), g[1]
    else:
        kw, period = g[0], int(g[1])
    kind = "ema" if kw == "ema" else "sma"   # dma/sma/ma -> simple
    return (kind, period)


def eval_condition(cond, closes):
    """Evaluate a single invalidation string against the close series.
    Returns (status, detail): status in {'fired','ok','manual'}."""
    last = closes[-1]
    t = cond.lower()
    # word-boundary match so "lose"/"close" etc. don't false-match inside other words
    if re.search(r"\b(below|under|break|breaks|loses|lose|loss|fall|falls|breakdown)\b", t):
        comp = "<"
    elif re.search(r"\b(above|over|reclaim|reclaims|cross|crosses|breakout)\b", t):
        comp = ">"
    else:
        return ("manual", f"no comparator parsed: {cond!r}")

    ma = parse_ma(t)
    if ma:
        kind, period = ma
        if len(closes) < period:
            return ("manual", f"not enough bars for {period}-{kind.upper()} in {cond!r}")
        target = ema(closes, period) if kind == "ema" else sma(closes, period)
        label = f"{period}-{kind.upper()} ({target:.2f})"
    else:
        nums = re.findall(r"\d[\d,]*\.?\d*", t.replace(",", ""))
        if not nums:
            return ("manual", f"no level/MA parsed: {cond!r}")
        target = float(nums[-1])
        label = f"{target:.2f}"

    fired = (last < target) if comp == "<" else (last > target)
    rel = "below" if comp == "<" else "above"
    detail = f"close {last:.2f} {'is' if fired else 'not'} {rel} {label} — {cond}"
    return ("fired" if fired else "ok", detail)


def sessions_held(rows, created):
    """Count bars dated on/after `created` (YYYY-MM-DD). Falls back to len(rows)."""
    if not created:
        return None
    try:
        c = datetime.strptime(str(created), "%Y-%m-%d").date()
    except ValueError:
        return None
    n = 0
    for r in rows:
        d = r.get("date")
        if not d:
            return None
        try:
            if datetime.strptime(d, "%Y-%m-%d").date() >= c:
                n += 1
        except ValueError:
            return None
    return n


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--trade", required=True, help="path to trade-idea YAML")
    p.add_argument("--ohlcv", help="OHLCV CSV (offline). Default: fetch yfinance")
    p.add_argument("--ltp", type=float, help="override last price (broker LTP)")
    p.add_argument("--entry", type=float, help="actual fill avg price (broker)")
    p.add_argument("--qty", type=float, help="actual position qty (broker)")
    p.add_argument("--sessions-held", type=int, help="override sessions held")
    p.add_argument("--out", help="also write verdict JSON here")
    args = p.parse_args()

    try:
        trade = load_yaml(args.trade)
    except Exception as e:
        print(json.dumps({"error": f"cannot read trade: {e}"})); sys.exit(2)

    plan = trade.get("plan", {}) or {}
    direction = (trade.get("direction") or "long").lower()
    symbol = trade.get("symbol", "?")
    stop = plan.get("stop")
    target = plan.get("target")
    entry = args.entry if args.entry is not None else plan.get("entry")
    time_stop = plan.get("time_stop_sessions")
    invalidations = trade.get("thesis_invalidation") or []

    if args.ohlcv:
        rows = load_ohlcv_csv(args.ohlcv)
    else:
        rows = fetch_ohlcv_yf(symbol)
    if not rows:
        print(json.dumps({"error": f"no price data for {symbol}"})); sys.exit(2)

    closes = [r["close"] for r in rows if r.get("close") is not None]
    last_close = closes[-1]
    last_low = rows[-1].get("low", last_close)
    last_high = rows[-1].get("high", last_close)
    price = args.ltp if args.ltp is not None else last_close

    long = direction != "short"
    reasons, manual = [], []

    # 1. STOP
    stop_hit = False
    if stop is not None:
        breach = min(last_low, price) if long else max(last_high, price)
        stop_hit = (breach <= stop) if long else (breach >= stop)
        if stop_hit:
            reasons.append(f"STOP breached: {('low' if long else 'high')} {breach:.2f} "
                           f"vs stop {stop:.2f}")

    # 2. THESIS invalidation
    thesis_fired = []
    for cond in invalidations:
        st, detail = eval_condition(str(cond), closes)
        if st == "fired":
            thesis_fired.append(detail)
        elif st == "manual":
            manual.append(detail)

    # 3. TARGET
    target_hit = False
    if target is not None:
        reach = max(last_high, price) if long else min(last_low, price)
        target_hit = (reach >= target) if long else (reach <= target)

    # 4. TIME stop
    held = args.sessions_held if args.sessions_held is not None \
        else sessions_held(rows, trade.get("created"))
    time_hit = (time_stop is not None and held is not None and held >= time_stop)

    # verdict priority
    if stop_hit:
        verdict = "EXIT_STOP"
    elif thesis_fired:
        verdict = "EXIT_THESIS"
        reasons += [f"thesis invalidated: {d}" for d in thesis_fired]
    elif target_hit:
        verdict = "EXIT_TARGET"
        reasons.append(f"TARGET reached: price {price:.2f} vs target {target:.2f} "
                       "(book or trail per plan)")
    elif time_hit:
        verdict = "EXIT_TIME"
        reasons.append(f"TIME stop: held {held} sessions >= {time_stop}, "
                       "neither stop nor target hit")
    else:
        verdict = "HOLD"
        reasons.append("rationale intact: no stop/target/thesis/time trigger")

    # metrics
    unreal_R = None
    if entry is not None and stop is not None and (entry - stop) != 0:
        risk = (entry - stop) if long else (stop - entry)
        move = (price - entry) if long else (entry - price)
        unreal_R = round(move / abs(risk), 2) if risk else None
    pnl = None
    if entry is not None and args.qty:
        pnl = round(((price - entry) if long else (entry - price)) * args.qty, 2)
    rem_rrr = None
    if target is not None and stop is not None and (price - stop) != 0:
        if long and price < target and price > stop:
            rem_rrr = round((target - price) / (price - stop), 2)
        elif not long and price > target and price < stop:
            rem_rrr = round((price - target) / (stop - price), 2)

    out = {
        "symbol": symbol, "direction": direction, "as_of": str(date.today()),
        "verdict": verdict,
        "reasons": reasons,
        "manual_review": manual,
        "regime_check": "deferred_to_skill" if trade.get("strategy") else "n/a",
        "metrics": {
            "price": round(price, 2), "entry": entry, "stop": stop, "target": target,
            "qty": args.qty, "sessions_held": held, "time_stop_sessions": time_stop,
            "unrealized_R": unreal_R, "unrealized_pnl": pnl,
            "remaining_rrr_to_target": rem_rrr,
        },
        "source_trade": args.trade,
    }
    print(json.dumps(out, indent=2))
    if args.out:
        import os
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w") as f:
            json.dump(out, f, indent=2)
    sys.exit(10 if verdict.startswith("EXIT") else 0)


if __name__ == "__main__":
    main()
