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
    """Call the checker and derive the old CLI's status code from the verdict.

    The status was only ever `10 if verdict.startswith("EXIT") else 0`, so the
    verdict assertions below carry over unchanged.
    """
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
    source_skill: find-trade
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
check("EXIT_TIME sessions_held=60", out["metrics"]["sessions_held"] == 60,
      out["metrics"]["sessions_held"])

out, rc = run(t, c, extra=["--sessions-held", "5"])
check("HOLD when sessions<time_stop", out["verdict"] == "HOLD", out["verdict"])

out, rc = run(t, c, extra=["--entry", "100", "--qty", "50", "--ltp", "110"])
check("broker LTP used as price", out["metrics"]["price"] == 110, out["metrics"]["price"])
check("pnl = (110-100)*50 = 500", out["metrics"]["unrealized_pnl"] == 500.0,
      out["metrics"]["unrealized_pnl"])
check("unrealized_R = (110-100)/(100-90)=1.0", out["metrics"]["unrealized_R"] == 1.0,
      out["metrics"]["unrealized_R"])

TRADE_SHORT = textwrap.dedent("""\
    symbol: SHORTCO
    exchange: NSE
    source_skill: find-trade
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
                          "plan: {entry: 100, stop: 90, target: 130}\n")
env2 = trade_check.check(t2, ohlcv=c)
check("a real plan produces no such gap", env2["gaps"] == [], env2["gaps"])


summary()
