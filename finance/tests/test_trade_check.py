#!/usr/bin/env python3
"""Offline tests for finance/compute/trade_check.py. No network."""
import os, sys, tempfile, textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from finance.compute import trade_check
from finance.tests.harness import check, summary

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


_KW = {"--sessions-held": "sessions_held", "--ltp": "ltp",
       "--entry": "entry", "--qty": "qty"}


def run(trade, ohlcv=None, extra=None):
    """Call the checker. The code is 10 for an EXIT verdict, 0 for HOLD and 2 when the
    checker refused the inputs."""
    kw = {}
    extra = list(extra or [])
    for i in range(0, len(extra), 2):
        kw[_KW[extra[i]]] = float(extra[i + 1])
    env = trade_check.check(trade, ohlcv=ohlcv, **kw)
    if not env.get("ok"):
        return env, 2
    rec = env["data"]
    return rec, 10 if str(rec.get("verdict", "")).startswith("EXIT") else 0


def bars_to_csv(name, closes, start="2026-01-01"):
    from datetime import date, timedelta
    y, m, dd = map(int, start.split("-"))
    base = date(y, m, dd)
    out = []
    for i, c in enumerate(closes):
        d = (base + timedelta(days=i)).isoformat()
        out.append((d, c, c + 0.5, c - 0.5, c, 100000))
    return csv(name, out)


TRADE_LONG = textwrap.dedent("""\
    symbol: TESTCO
    exchange: NSE
    source_skill: discover
    strategy: null
    created: 2026-01-01
    status: open
    fill_avg: 100
    entry_date: 2026-01-01
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

t = write("long.yml", TRADE_LONG)
c = bars_to_csv("hold.csv", [100] * 60)
out, rc = run(t, c, extra=["--sessions-held", "5"])
check("HOLD verdict", out["verdict"] == "HOLD", out["verdict"])
check("HOLD exit code 0", rc == 0, rc)
check("HOLD flags pledge as manual_review",
      any("pledge" in m for m in out["manual_review"]), out["manual_review"])
check("HOLD unrealized_R ~0", abs(out["metrics"]["unrealized_R"]) < 0.05,
      out["metrics"]["unrealized_R"])

closes = [100] * 59 + [89]
c = bars_to_csv("stop.csv", closes)
out, rc = run(t, c)
check("EXIT_STOP verdict", out["verdict"] == "EXIT_STOP", out["verdict"])
check("EXIT_STOP exit code 10", rc == 10, rc)

closes = [100] * 59 + [131]
c = bars_to_csv("target.csv", closes)
out, rc = run(t, c)
check("EXIT_TARGET verdict", out["verdict"] == "EXIT_TARGET", out["verdict"])

closes = [100] * 55 + [95, 95, 95, 95, 95]
c = bars_to_csv("ema.csv", closes)
out, rc = run(t, c)
check("EXIT_THESIS (50-EMA) verdict", out["verdict"] == "EXIT_THESIS", out["verdict"])
check("EXIT_THESIS reason mentions 50-EMA",
      any("50-EMA" in r or "ema" in r.lower() for r in out["reasons"]), out["reasons"])

TRADE_PIVOT = TRADE_LONG.replace("stop: 90", "stop: 80")
t2 = write("pivot.yml", TRADE_PIVOT)
closes = [100] * 59 + [84]
c = bars_to_csv("pivot.csv", closes)
out, rc = run(t2, c)
check("EXIT_THESIS (pivot 85) verdict", out["verdict"] == "EXIT_THESIS", out["verdict"])
check("EXIT_THESIS pivot reason", any("85" in r for r in out["reasons"]), out["reasons"])

c = bars_to_csv("time.csv", [100] * 60)
out, rc = run(t, c)
check("EXIT_TIME verdict", out["verdict"] == "EXIT_TIME", out["verdict"])
check("EXIT_TIME sessions_held=59", out["metrics"]["sessions_held"] == 59,
      out["metrics"]["sessions_held"])

out, rc = run(t, c, extra=["--sessions-held", "5"])
check("HOLD when sessions<time_stop", out["verdict"] == "HOLD", out["verdict"])

out, rc = run(t, c, extra=["--entry", "100", "--qty", "50", "--ltp", "110"])
check("broker LTP only marks unrealized value", out["metrics"]["mark_price"] == 110 and out["metrics"]["price"] == 100)
check("pnl = (110-100)*50 = 500", out["metrics"]["unrealized_pnl"] == 500.0,
      out["metrics"]["unrealized_pnl"])
check("unrealized_R = (110-100)/(100-90)=1.0", out["metrics"]["unrealized_R"] == 1.0,
      out["metrics"]["unrealized_R"])

TRADE_SHORT = textwrap.dedent("""\
    symbol: SHORTCO
    exchange: NSE
    source_skill: discover
    strategy: momentum-x
    created: 2026-01-01
    status: open
    fill_avg: 100
    entry_date: 2026-01-01
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
closes = [100] * 59 + [111]
c = bars_to_csv("short_stop.csv", closes)
out, rc = run(ts, c)
check("SHORT EXIT_STOP", out["verdict"] == "EXIT_STOP", out["verdict"])
closes = [100] * 59 + [79]
c = bars_to_csv("short_tgt.csv", closes)
out, rc = run(ts, c)
check("SHORT EXIT_TARGET", out["verdict"] == "EXIT_TARGET", out["verdict"])
check("SHORT regime_check deferred (has strategy)",
      out["regime_check"] == "deferred_to_skill", out["regime_check"])
closes = [100] * 59 + [121]
c = bars_to_csv("short_th.csv", closes)
out, rc = run(ts, c)
check("SHORT stop precedence over thesis", out["verdict"] == "EXIT_STOP", out["verdict"])

from finance.compute import trade_check as tc  # noqa: E402

flat = bars_to_csv("envelope.csv", [100] * 60)
env = tc.check(t, ohlcv=flat, sessions_held=5)
check("check returns the data-spine envelope",
      set(env) == {"ok", "source", "fetched_at", "data", "gaps"}, sorted(env))
check("check is ok when it reached a verdict", env["ok"] is True)
check("check puts the verdict record in data", env["data"]["verdict"] == "HOLD",
      env["data"].get("verdict"))
check("check reports no gap on a clean read", env["gaps"] == [], env["gaps"])
check("check names the trade it judged", env["data"]["source_trade"] == t)

env_missing = tc.check(os.path.join(D, "not-a-trade.yml"))
check("an unreadable trade file is ok:false, not an exception",
      env_missing["ok"] is False)
check("an unreadable trade file names the gap",
      any("cannot read trade" in g for g in env_missing["gaps"]), env_missing["gaps"])

env_nodata = tc.check(t, ohlcv=csv("empty.csv", []))
check("no price data is a labelled gap, not a fabricated verdict",
      env_nodata["ok"] is False
      and any("no price data" in g for g in env_nodata["gaps"]), env_nodata["gaps"])


t = write("vacuous.yml", "symbol: TESTCO\nstatus: open\ndirection: long\n"
                         "entry: 100\nstop: 90\ntarget: 130\n")
c = bars_to_csv("vacuous.csv", [100.0] * 30)
out, rc = run(t, c)
check("a file with no plan/invalidation still answers", out.get("verdict") == "HOLD", out.get("verdict"))

env = trade_check.check(t, ohlcv=c)
check("the vacuous HOLD carries a gap, not silence",
      any("absence of a check" in g for g in env["gaps"]), env["gaps"])
check("and is flagged for manual review",
      any("nothing mechanical was checked" in m for m in env["data"]["manual_review"]),
      env["data"]["manual_review"])

t2 = write("checked.yml", "symbol: TESTCO\nstatus: open\ndirection: long\n"
                          "plan: {entry: 100, stop: 90, target: 130}\nfill_avg: 100\nentry_date: 2026-01-01\n")
env2 = trade_check.check(t2, ohlcv=c)
check("a real plan produces no such gap", env2["gaps"] == [], env2["gaps"])


# Regression scenarios: execution evidence, source separation and malformed inputs.
def regression(name, fn):
    try:
        fn()
    except Exception as exc:
        check(name + " does not crash", False, repr(exc))


def execution_evidence():
    idea = write("idea-only.yml", TRADE_LONG.replace("status: open", "status: idea").replace("fill_avg: 100\n", "").replace("entry_date: 2026-01-01\n", ""))
    env = tc.check(idea, ohlcv=flat, ltp=110, qty=50)
    m = env["data"]["metrics"]
    check("a planned entry cannot become a fill", m["entry"] is None)
    check("missing fill leaves R and PnL unknown", m["unrealized_R"] is None and m["unrealized_pnl"] is None)
    check("idea creation does not start the holding clock", m["sessions_held"] is None)
    filled = write("filled.yml", TRADE_LONG.replace("fill_avg: 100", "fill_avg: 102").replace("entry_date: 2026-01-01", "entry_date: 2026-02-28"))
    env = tc.check(filled, ohlcv=flat, ltp=110)
    m = env["data"]["metrics"]
    check("recorded fill and actual quantity are used", m["entry"] == 102 and m["qty"] == 50)
    check("sessions count after fill, not idea", m["sessions_held"] == 1, m["sessions_held"])
    check("personal quote only values the position", m["price"] == 100 and m["mark_price"] == 110)
    check("recorded fill PnL", m["unrealized_pnl"] == 400)
    check("as_of identifies the decision bar", env["data"]["as_of"] == "2026-03-01")
    env = tc.check(filled, ohlcv=flat, ltp=80)
    check("personal quote cannot trigger a decision", env["data"]["verdict"] == "HOLD", env)


def parsing_and_clock():
    check("break above is not below", tc.eval_condition("break above 120", [130])[0] == "fired")
    for condition in ("revenue falls below 10%", "close below 90 after 3 sessions", "close below 0-EMA", "close below 1e309"):
        check("nonmechanical condition remains manual: " + condition,
              tc.eval_condition(condition, [100] * 60)[0] == "manual")
    # SMA seed: [10,20,30] seeds EMA3 at 20, followed by 21 -> 20.5.
    check("EMA uses the shared SMA-seeded definition",
          tc.eval_condition("close below 3-EMA", [10, 20, 30, 21])[0] == "ok")
    rows = [{"date": "2026-02-27"}, {"date": "2026-03-02"}, {"date": "2026-03-03"}]
    check("entry session is zero elapsed sessions", tc.sessions_since(rows, "2026-03-03") == 0)
    check("weekend is not a session", tc.sessions_since(rows, "2026-02-27") == 2)
    check("truncated history cannot certify time held", tc.sessions_since(rows, "2025-01-01") is None)


def malformed_inputs():
    for name, content in (("scalar", "42"), ("list", "[1, 2]"), ("badplan", "symbol: X\nplan: [1]"),
                          ("direction", "symbol: X\ndirection: sideways")):
        env = tc.check(write(name + ".yml", content), ohlcv=flat)
        check(name + " trade is a labelled gap", env["ok"] is False and bool(env["gaps"]))
    env = tc.check(write("valid.yml", TRADE_LONG), ohlcv=os.path.join(D, "missing.csv"))
    check("missing CSV is a gap", not env["ok"] and bool(env["gaps"]))
    env = tc.check(write("valid.yml", TRADE_LONG), ohlcv=bars_to_csv("nan.csv", [float("nan")]))
    check("all invalid prices is a gap", not env["ok"] and bool(env["gaps"]))
    env = tc.check(write("bad-level.yml", TRADE_LONG.replace("stop: 90", "stop: .inf")), ohlcv=flat)
    check("nonfinite level does not fire", env["data"]["verdict"] != "EXIT_STOP" and bool(env["gaps"]))
    env = tc.check(write("one-condition.yml", "symbol: X\nplan: {stop: 80}\nthesis_invalidation: close below 105\n"), ohlcv=flat)
    check("a string invalidation is a single condition", env["data"]["verdict"] == "EXIT_THESIS")


for name, fn in (("execution evidence", execution_evidence), ("parser and clock", parsing_and_clock), ("invalid input", malformed_inputs)):
    regression(name, fn)

def price_coverage():
    fill = write("coverage.yml", TRADE_LONG.replace("entry_date: 2026-01-01", "entry_date: 2026-03-02"))
    same_day = csv("same-day.csv", [("2026-03-02", 100, 140, 70, 100, 1)])
    env = tc.check(fill, ohlcv=same_day)
    check("pre-fill intraday extremes cannot trigger exit", env["data"]["verdict"] == "HOLD" and bool(env["gaps"]))
    check("fill day has zero elapsed sessions", env["data"]["metrics"]["sessions_held"] == 0)
    env = tc.check(fill, ohlcv=flat)
    check("pre-entry history cannot generate a verdict", not env["ok"] and bool(env["gaps"]))
    reverse = csv("reverse.csv", [("2026-03-03", 100, 101, 99, 100, 1), ("2026-03-02", 100, 101, 99, 100, 1)])
    env = tc.check(fill, ohlcv=reverse)
    check("out-of-order bars sort before analysis", env["data"]["as_of"] == "2026-03-03" and env["data"]["metrics"]["sessions_held"] == 1)
    duplicate = csv("duplicate.csv", [("2026-03-03", 100, 101, 99, 100, 1)] * 2)
    env = tc.check(fill, ohlcv=duplicate)
    check("ambiguous duplicate dates are rejected", not env["ok"] and bool(env["gaps"]))
    original = tc.prices.history
    try:
        tc.prices.history = lambda *a, **kw: {"data": {"candles": [{"date": "2026-03-03", "high": 101, "low": 99, "close": 100}]}, "gaps": ["fixture upstream degraded"]}
        env = tc.check(fill)
        check("source gaps survive revalidation", "fixture upstream degraded" in env["gaps"])
    finally:
        tc.prices.history = original

regression("price coverage", price_coverage)
def numeric_boundaries():
    import json
    env = tc.check(write("overflow.yml", TRADE_LONG), ohlcv=flat, entry=100, qty=1e308, ltp=1e308)
    try:
        json.dumps(env, allow_nan=False)
        check("overflow cannot leak nonfinite JSON", True)
    except ValueError:
        check("overflow cannot leak nonfinite JSON", False)
    check("overflow PnL is an explicit gap", env["data"]["metrics"]["unrealized_pnl"] is None and bool(env["gaps"]))
    env = tc.check(write("sessions-percent.yml", TRADE_LONG), ohlcv=flat, sessions_held="25%")
    check("percent is not an elapsed session count", env["data"]["metrics"]["sessions_held"] is None and bool(env["gaps"]))

regression("numeric boundaries", numeric_boundaries)

def earlier_post_fill_breach():
    tc = trade_check
    trade = write("breach.yml", TRADE_LONG.replace('      - "daily close below 50-EMA"\n', ""))
    # Fill on 03-02; stop 90 pierced on 03-04, recovered by the decision bar.
    bars = csv("breach.csv", [("2026-03-02", 100, 101, 99, 100, 1),
                              ("2026-03-03", 100, 101, 95, 96, 1),
                              ("2026-03-04", 96, 97, 88, 92, 1),
                              ("2026-03-05", 95, 101, 94, 100, 1)])
    fill = write("breach-fill.yml", open(trade).read().replace("entry_date: 2026-01-01", "entry_date: 2026-03-02"))
    env = tc.check(fill, ohlcv=bars)
    check("a stop breached after the fill is not hidden by a later recovery",
          env["data"]["verdict"] == "EXIT_STOP", env["data"])
    check("the breach names its session", any("2026-03-04" in r for r in env["data"]["reasons"]), env["data"]["reasons"])
    pre = csv("prefill.csv", [("2026-03-02", 100, 101, 85, 100, 1),
                              ("2026-03-03", 100, 101, 95, 99, 1)])
    env = tc.check(fill, ohlcv=pre)
    check("the fill-session low cannot breach a stop placed after it",
          env["data"]["verdict"] == "HOLD", env["data"])
    tgt = csv("target.csv", [("2026-03-02", 100, 101, 99, 100, 1),
                             ("2026-03-03", 100, 131, 99, 120, 1),
                             ("2026-03-04", 120, 121, 110, 115, 1)])
    env = tc.check(fill, ohlcv=tgt)
    check("a target reached after the fill is reported with its session",
          env["data"]["verdict"] == "EXIT_TARGET"
          and any("2026-03-03" in r for r in env["data"]["reasons"]), env["data"])
    calls = []
    original = tc.prices.history
    raw = [{"date": "2026-03-02", "high": 101, "low": 99, "close": 100},
           {"date": "2026-03-03", "high": 101, "low": 89, "close": 100},
           {"date": "2026-03-04", "high": 101, "low": 99, "close": 100}]
    adj = [{**r, "low": r["low"] * 0.5, "high": r["high"] * 0.5, "close": r["close"] * 0.5}
           for r in raw[:-1]] + [raw[-1]]
    try:
        def fake(symbol, period="1y", fresh=False, adjusted=False):
            calls.append(adjusted)
            return {"data": {"candles": adj if adjusted else raw}, "gaps": []}
        tc.prices.history = fake
        env = tc.check(fill)
    finally:
        tc.prices.history = original
    check("nominal stop levels are compared with unadjusted bars",
          env["data"]["verdict"] == "EXIT_STOP" and False in calls, (env["data"], calls))

regression("earlier post-fill breach", earlier_post_fill_breach)
summary()
