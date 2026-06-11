#!/usr/bin/env python3
"""Offline test harness for trade-tracker/scripts/validate_trade.py."""
import json, os, subprocess, sys, tempfile, textwrap

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate_trade.py")
D = tempfile.mkdtemp()


def write(name, content):
    p = os.path.join(D, name)
    with open(p, "w") as f:
        f.write(content)
    return p


def csv(name, bars):
    """bars: list of (date, o,h,l,c,v)"""
    lines = ["Date,Open,High,Low,Close,Volume"]
    for d, o, h, l, c, v in bars:
        lines.append(f"{d},{o},{h},{l},{c},{v}")
    return write(name, "\n".join(lines) + "\n")


def run(trade, ohlcv=None, extra=None):
    cmd = [sys.executable, SCRIPT, "--trade", trade]
    if ohlcv:
        cmd += ["--ohlcv", ohlcv]
    if extra:
        cmd += extra
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        out = json.loads(r.stdout)
    except json.JSONDecodeError:
        print("STDOUT:", r.stdout, "STDERR:", r.stderr)
        raise
    return out, r.returncode


def flat(n, price, name, start=1):
    from datetime import date, timedelta
    base = date(2026, 1, 1)
    bars = []
    for i in range(n):
        d = (base + timedelta(days=i)).isoformat()
        bars.append((d, price, price, price, price, 100000))
    return csv(name, bars)


def bars_to_csv(name, closes, start="2026-01-01"):
    from datetime import date, timedelta
    y, m, dd = map(int, start.split("-"))
    base = date(y, m, dd)
    out = []
    for i, c in enumerate(closes):
        d = (base + timedelta(days=i)).isoformat()
        # high/low = close ± tiny so stop/target isolation is clean
        out.append((d, c, c + 0.5, c - 0.5, c, 100000))
    return csv(name, out)


TRADE_LONG = textwrap.dedent("""\
    symbol: TESTCO
    exchange: NSE
    source_skill: swing-trading
    strategy: null
    created: 2026-01-01
    status: idea
    setup: range-breakout
    direction: long
    rationale: test
    thesis_invalidation:
      - "daily close below 50-EMA"
      - "break of breakout pivot 85"
      - "promoter pledge increase"
    plan:
      entry: 100
      stop: 90
      target: 130
      rrr: 3.0
      time_stop_sessions: 20
      entry_basis: test
    sizing: {capital: 500000, risk_per_trade_pct: 1.0, qty: 50}
    """)

PASS, FAIL = 0, 0


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}  {detail}")


# ---- 1. HOLD: flat at 100, recently entered (5 sessions) -> nothing triggers ----
t = write("long.yml", TRADE_LONG)
c = bars_to_csv("hold.csv", [100] * 60)
out, rc = run(t, c, extra=["--sessions-held", "5"])
check("HOLD verdict", out["verdict"] == "HOLD", out["verdict"])
check("HOLD exit code 0", rc == 0, rc)
check("HOLD flags pledge as manual_review",
      any("pledge" in m for m in out["manual_review"]), out["manual_review"])
check("HOLD unrealized_R ~0", abs(out["metrics"]["unrealized_R"]) < 0.05,
      out["metrics"]["unrealized_R"])

# ---- 2. EXIT_STOP: last bar low pierces 90 ----
closes = [100] * 59 + [89]
c = bars_to_csv("stop.csv", closes)
out, rc = run(t, c)
check("EXIT_STOP verdict", out["verdict"] == "EXIT_STOP", out["verdict"])
check("EXIT_STOP exit code 10", rc == 10, rc)

# ---- 3. EXIT_TARGET: last high reaches 130 ----
closes = [100] * 59 + [131]
c = bars_to_csv("target.csv", closes)
out, rc = run(t, c)
check("EXIT_TARGET verdict", out["verdict"] == "EXIT_TARGET", out["verdict"])

# ---- 4. EXIT_THESIS via 50-EMA: 55 flat @100 then drop to 80 (above stop? 80<90 stop!) ----
# To isolate thesis, raise so stop(90) not hit but close below ema50. Use 95 (>90) end.
closes = [100] * 55 + [95, 95, 95, 95, 95]
c = bars_to_csv("ema.csv", closes)
out, rc = run(t, c)
# ema50 of mostly-100 series ~ >95 so "close below 50-EMA" fires; stop 90 not hit (low 94.5)
check("EXIT_THESIS (50-EMA) verdict", out["verdict"] == "EXIT_THESIS", out["verdict"])
check("EXIT_THESIS reason mentions 50-EMA",
      any("50-EMA" in r or "ema" in r.lower() for r in out["reasons"]), out["reasons"])

# ---- 5. EXIT_THESIS via numeric pivot 85 (stop is 90, so pivot break needs stop not hit) ----
# Make a trade whose stop is BELOW the pivot so pivot-break fires before stop.
TRADE_PIVOT = TRADE_LONG.replace("stop: 90", "stop: 80").replace(
    'plan:\n      entry: 100', 'plan:\n      entry: 100')
t2 = write("pivot.yml", TRADE_PIVOT)
closes = [100] * 59 + [84]   # 84 < pivot 85, but > stop 80
c = bars_to_csv("pivot.csv", closes)
out, rc = run(t2, c)
check("EXIT_THESIS (pivot 85) verdict", out["verdict"] == "EXIT_THESIS", out["verdict"])
check("EXIT_THESIS pivot reason", any("85" in r for r in out["reasons"]), out["reasons"])

# ---- 6. EXIT_TIME: held >= 20, no stop/target/thesis ----
# 60 flat bars from 2026-01-01 -> sessions_held=60 >=20; close 100 (no thesis), stop/target untouched
c = bars_to_csv("time.csv", [100] * 60)
out, rc = run(t, c)
# but 50-EMA ~100 so "close below 50-EMA" not fired; pivot 85 ok; should be EXIT_TIME
check("EXIT_TIME verdict", out["verdict"] == "EXIT_TIME", out["verdict"])
check("EXIT_TIME sessions_held=60", out["metrics"]["sessions_held"] == 60,
      out["metrics"]["sessions_held"])

# ---- 6b. HOLD when within time: override sessions-held=5 ----
out, rc = run(t, c, extra=["--sessions-held", "5"])
check("HOLD when sessions<time_stop", out["verdict"] == "HOLD", out["verdict"])

# ---- 7. Broker fill injection: entry/qty/ltp -> pnl + R ----
out, rc = run(t, c, extra=["--entry", "100", "--qty", "50", "--ltp", "110"])
check("broker LTP used as price", out["metrics"]["price"] == 110, out["metrics"]["price"])
check("pnl = (110-100)*50 = 500", out["metrics"]["unrealized_pnl"] == 500.0,
      out["metrics"]["unrealized_pnl"])
check("unrealized_R = (110-100)/(100-90)=1.0", out["metrics"]["unrealized_R"] == 1.0,
      out["metrics"]["unrealized_R"])

# ---- 8. SHORT trade: stop above entry, target below ----
TRADE_SHORT = textwrap.dedent("""\
    symbol: SHORTCO
    exchange: NSE
    source_skill: swing-trading
    strategy: momentum-x
    created: 2026-01-01
    status: idea
    setup: breakdown
    direction: short
    rationale: test short
    thesis_invalidation:
      - "close above 120"
    plan:
      entry: 100
      stop: 110
      target: 80
      rrr: 2.0
      time_stop_sessions: 20
    sizing: {capital: 500000, risk_per_trade_pct: 1.0, qty: 50}
    """)
ts = write("short.yml", TRADE_SHORT)
# short stop hit: high pierces 110
closes = [100] * 59 + [111]
c = bars_to_csv("short_stop.csv", closes)
out, rc = run(ts, c)
check("SHORT EXIT_STOP", out["verdict"] == "EXIT_STOP", out["verdict"])
# short target hit: low reaches 80
closes = [100] * 59 + [79]
c = bars_to_csv("short_tgt.csv", closes)
out, rc = run(ts, c)
check("SHORT EXIT_TARGET", out["verdict"] == "EXIT_TARGET", out["verdict"])
check("SHORT regime_check deferred (has strategy)",
      out["regime_check"] == "deferred_to_skill", out["regime_check"])
# short thesis "close above 120"
closes = [100] * 59 + [121]
c = bars_to_csv("short_th.csv", closes)
out, rc = run(ts, c)
# note: 121 high also >110 stop, so STOP wins (higher priority) — that's correct behavior
check("SHORT stop precedence over thesis", out["verdict"] == "EXIT_STOP", out["verdict"])

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
