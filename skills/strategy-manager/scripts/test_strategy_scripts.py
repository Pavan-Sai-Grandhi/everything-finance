#!/usr/bin/env python3
"""Offline tests for select_strategy.py and aggregate_performance.py."""
import json, os, subprocess, sys, tempfile, textwrap

BASE = os.path.dirname(os.path.abspath(__file__))
SELECT = f"{BASE}/select_strategy.py"
AGG = f"{BASE}/aggregate_performance.py"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(BASE))))
from finance.tests.harness import check, summary  # noqa: E402


def w(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(r.stdout), r.returncode
    except json.JSONDecodeError:
        print("STDOUT:", r.stdout, "\nSTDERR:", r.stderr); raise


def spec(name, status, trend, exp_R, pf=1.5, vix_max=20, breadth=50, live_R=None):
    live = ""
    if live_R is not None:
        live = f"\nlive_performance:\n  expectancy_R: {live_R}\n  profit_factor: 2.0\n  eligible_for_selection: true\n"
    return textwrap.dedent(f"""\
        name: {name}
        status: {status}
        archetype: test
        regime_required:
          market_trend: {trend}
          nifty_above: ema200
          vix_max: {vix_max}
          breadth_min_pct: {breadth}
        expectancy_assumptions:
          expectancy_R: {exp_R}
          profit_factor: {pf}
          n_trades: 40
        """) + live


# ===================== select_strategy.py =====================
print("== select_strategy ==")
D = tempfile.mkdtemp()
sdir = os.path.join(D, "strategies")
w(os.path.join(sdir, "A.yml"), spec("A", "active", "up", 0.35))
w(os.path.join(sdir, "B.yml"), spec("B", "active", "up", 0.50))
w(os.path.join(sdir, "C.yml"), spec("C", "active", "range", 0.40))
w(os.path.join(sdir, "D.yml"), spec("D", "draft", "up", 0.99))
w(os.path.join(sdir, "E.yml"), spec("E", "inactive", "up", 0.99))

regime_up = json.dumps({
    "as_of": "2026-06-11", "market_trend": "up",
    "trend_detail": {"above_ema200": True},
    "volatility": {"vix": 12.0, "regime": "low"},
    "breadth": {"pct_sectors_above_ema50": 60.0}, "market_posture": "risk_on"})
rpath = os.path.join(D, "regime_up.json"); w(rpath, regime_up)

out, rc = run([sys.executable, SELECT, "--strategies", sdir, "--regime", rpath])
check("active_specs==3 (A,B,C; draft/inactive ignored)", out["active_specs"] == 3, out["active_specs"])
check("selected is B (0.5 > 0.35)", out["selected"]["name"] == "B", out["selected"])
check("exit 0 when selected", rc == 0, rc)
check("2 fitting (A,B)", len(out["ranked_fitting"]) == 2, out["ranked_fitting"])
check("C rejected as unfit (trend range)",
      any(c["name"] == "C" for c in out["rejected_unfit"]), out["rejected_unfit"])
check("B ranked above A", [c["name"] for c in out["ranked_fitting"]] == ["B", "A"],
      [c["name"] for c in out["ranked_fitting"]])

# live_performance overrides backtest for scoring
w(os.path.join(sdir, "A.yml"), spec("A", "active", "up", 0.35, live_R=0.9))
out, rc = run([sys.executable, SELECT, "--strategies", sdir, "--regime", rpath])
check("A wins when live expectancy 0.9 > B backtest 0.5",
      out["selected"]["name"] == "A" and out["selected"]["edge_source"] == "live", out["selected"])

# down regime -> nothing fits -> exit 11
regime_down = json.dumps({"as_of": "x", "market_trend": "down",
                          "trend_detail": {"above_ema200": False},
                          "volatility": {"vix": 26.0}, "breadth": {"pct_sectors_above_ema50": 25.0},
                          "market_posture": "risk_off"})
rd = os.path.join(D, "rd.json"); w(rd, regime_down)
out, rc = run([sys.executable, SELECT, "--strategies", sdir, "--regime", rd])
check("none fit in down regime -> selected None", out["selected"] is None, out["selected"])
check("exit 11 when none fit", rc == 11, rc)

# no active specs -> exit 12
missing = os.path.join(D, "missing.json")
for missing_key in ("market_trend", "trend_detail", "volatility", "breadth"):
    partial = json.loads(regime_up)
    partial.pop(missing_key)
    w(missing, json.dumps(partial))
    out, rc = run([sys.executable, SELECT, "--strategies", sdir, "--regime", missing])
    check(f"missing required {missing_key} evidence refuses selection",
          rc == 11 and out["selected"] is None, out)

# no active specs -> exit 12
empty = os.path.join(D, "empty"); os.makedirs(empty, exist_ok=True)
w(os.path.join(empty, "X.yml"), spec("X", "draft", "up", 0.5))
out, rc = run([sys.executable, SELECT, "--strategies", empty, "--regime", rpath])
check("exit 12 when no active specs", rc == 12, rc)

# vix gate: active up spec but vix_max 10 while live vix 12 -> unfit
w(os.path.join(sdir, "A.yml"), spec("A", "active", "up", 0.35, vix_max=10))
out, rc = run([sys.executable, SELECT, "--strategies", sdir, "--regime", rpath])
a = next(c for c in (out["ranked_fitting"] + out["rejected_unfit"]) if c["name"] == "A")
check("vix_max gate rejects A", a in out["rejected_unfit"], a)

# --purpose filter: an active investment spec sits beside the trading ones
inv = textwrap.dedent("""\
    name: INV
    status: active
    purpose: investment
    regime_required:
      market_trend: up
    universe:
      source: nifty500
    screening:
      fundamental:
        query: "ROCE > 15"
    ranking:
      metric: return_12m
    lifecycle:
      generated_at: 2026-08-01
    """)
w(os.path.join(sdir, "A.yml"), spec("A", "active", "up", 0.35))   # restore A as trading
w(os.path.join(sdir, "INV.yml"), inv)
out, _ = run([sys.executable, SELECT, "--strategies", sdir, "--regime", rpath,
              "--purpose", "investment"])
check("--purpose investment keeps only the investment spec",
      out["active_specs"] == 1 and out["selected"]["name"] == "INV", out)
out, _ = run([sys.executable, SELECT, "--strategies", sdir, "--regime", rpath,
              "--purpose", "trading"])
check("--purpose trading excludes the investment spec",
      all(c["name"] != "INV" for c in out["ranked_fitting"] + out["rejected_unfit"]), out)

# ===================== aggregate_performance.py =====================
print("== aggregate_performance ==")
D2 = tempfile.mkdtemp()
tdir = os.path.join(D2, "trades"); sdir2 = os.path.join(D2, "strategies")


def trade(sym, strat, realized_R, reason="EXIT_STOP", status="closed"):
    res = "" if status != "closed" else textwrap.dedent(f"""\
        result:
          exit_date: 2026-07-01
          exit_price: {1000 + realized_R * 100}
          charges: 0
          exit_qty: 50
          execution: {{source: kite, exit_trade_ids: ["fixture-{sym}"]}}
          exit_reason: {reason}
          realized_R: {realized_R}
          realized_pnl: {realized_R * 5000}
          holding_sessions: 10
        """)
    return textwrap.dedent(f"""\
        symbol: {sym}
        strategy: {strat}
        status: {status}
        direction: long
        fill_avg: 1000
        plan: {{stop: 900}}
        entry_date: 2026-06-17
        sizing: {{qty: 50}}
        """) + res


# stratX: 12 trades, net negative expectancy -> DEACTIVATE
xs = [-1, -1, -1, -1, -1, -1, -1, 2, 2, -1, -1, 0.5]
for i, r in enumerate(xs):
    w(os.path.join(tdir, f"X{i}.yml"), trade(f"XX{i}", "stratX", r,
      reason="EXIT_STOP" if r < 0 else "EXIT_TARGET"))
w(os.path.join(sdir2, "stratX.yml"), spec("stratX", "active", "up", 0.35))

# stratY: 12 trades, small positive expectancy well below backtest 0.4 -> OPTIMIZE
ys = [1, -1, 1, -1, 1, -1, 1, -1, 1, -1, 0.2, -0.1]   # mean ~0.1
for i, r in enumerate(ys):
    w(os.path.join(tdir, f"Y{i}.yml"), trade(f"YY{i}", "stratY", r,
      reason="EXIT_TIME" if r <= 0 else "EXIT_TARGET"))
w(os.path.join(sdir2, "stratY.yml"), spec("stratY", "active", "up", 0.40))

# stratZ: 5 trades -> insufficient -> KEEP
for i in range(5):
    w(os.path.join(tdir, f"Z{i}.yml"), trade(f"ZZ{i}", "stratZ", -1))
w(os.path.join(sdir2, "stratZ.yml"), spec("stratZ", "active", "up", 0.30))

# an open (non-closed) trade should be ignored
w(os.path.join(tdir, "open1.yml"), trade("OP", "stratX", 5, status="open"))

out, rc = run([sys.executable, AGG, "--trades", tdir, "--strategies", sdir2])
by = {r["strategy"]: r for r in out["strategies"]}
check("stratX -> DEACTIVATE", by["stratX"]["verdict"] == "DEACTIVATE", by["stratX"])
check("stratX counts 12 closed (open ignored)",
      by["stratX"]["metrics"]["trades_closed"] == 12, by["stratX"]["metrics"])
check("stratX expectancy negative",
      by["stratX"]["metrics"]["expectancy_R"] < 0, by["stratX"]["metrics"]["expectancy_R"])
check("stratY -> OPTIMIZE", by["stratY"]["verdict"] == "OPTIMIZE", by["stratY"])
check("stratZ -> KEEP (insufficient sample)", by["stratZ"]["verdict"] == "KEEP", by["stratZ"])
check("exit_reasons breakdown present",
      sum(by["stratX"]["exit_reasons"].values()) == 12, by["stratX"]["exit_reasons"])

# --update-spec deactivates stratX and writes live_performance
out, rc = run([sys.executable, AGG, "--trades", tdir, "--strategies", sdir2,
               "--strategy", "stratX", "--update-spec"])
import importlib
yaml = importlib.import_module("yaml")
updated = yaml.safe_load(open(os.path.join(sdir2, "stratX.yml")))
check("spec status flipped to inactive", updated["status"] == "inactive", updated["status"])
check("deactivated_reason recorded",
      bool(updated.get("lifecycle", {}).get("deactivated_reason")), updated.get("lifecycle"))
check("live_performance written",
      updated["live_performance"]["trades_closed"] == 12, updated.get("live_performance"))

# Closed status and an unrealized number alone are not proof of execution.
legacy = trade("LEGACY", "stratX", 100).replace('  execution: {source: kite, exit_trade_ids: ["fixture-LEGACY"]}\n', "")
w(os.path.join(tdir, "legacy.yml"), legacy)
out, rc = run([sys.executable, AGG, "--trades", tdir, "--strategies", sdir2])
x = next(row for row in out["strategies"] if row["strategy"] == "stratX")
check("legacy close without execution evidence is excluded", x["metrics"]["trades_closed"] == 12, x)
check("excluded legacy close is reported", bool(out.get("gaps")), out)
check("incomplete outcomes cannot optimize/deactivate", x["verdict"] == "REVIEW", x)

# Trade-supplied names must not allow --update-spec to mutate another directory.
outside = os.path.join(D2, "outside.yml")
w(outside, spec("outside", "active", "up", 0.3))
for i in range(12):
    w(os.path.join(tdir, f"escape{i}.yml"), trade(f"ESC{i}", "../outside", -1))
out, rc = run([sys.executable, AGG, "--trades", tdir, "--strategies", sdir2, "--update-spec"])
with open(outside) as stream:
    check("strategy names cannot escape the selected directory", yaml.safe_load(stream)["status"] == "active")

# Selection must not reuse cached performance created by the old unchecked workflow.
w(os.path.join(sdir, "A.yml"), spec("A", "active", "up", 0.35, live_R=9).replace("  eligible_for_selection: true\n", ""))
out, _ = run([sys.executable, SELECT, "--strategies", sdir, "--regime", rpath, "--purpose", "trading"])
check("legacy live scores cannot override backtest", out["selected"]["name"] == "B", out["selected"])

import copy
import aggregate_performance as aggregation
valid = yaml.safe_load(trade("GOOD", "stratZ", -1))
for label, mutate in (
    ("nonfinite R", lambda t: t["result"].update(realized_R=float("nan"))),
    ("wrong result shape", lambda t: t.update(result=[1])),
    ("partial exit", lambda t: t["result"].update(exit_qty=25)),
    ("missing charges", lambda t: t["result"].pop("charges")),
    ("negative charges", lambda t: t["result"].update(charges=-1)),
    ("unrealized substituted for realized", lambda t: t["result"].update(realized_R=2)),
    ("inconsistent PnL", lambda t: t["result"].update(realized_pnl=100)),
    ("reversed dates", lambda t: t["result"].update(exit_date="2026-01-01")),
    ("wrong execution source", lambda t: t["result"]["execution"].update(source="indmoney")),
):
    artifact = copy.deepcopy(valid)
    mutate(artifact)
    try:
        aggregation.closed_result(artifact)
        check(label + " excluded from learning", False)
    except ValueError:
        check(label + " excluded from learning", True)

artifact = copy.deepcopy(valid)
artifact["result"].update(charges=25, realized_pnl=-5025, realized_R=-1.005)
check("learning recomputes net R from actual costs", aggregation.closed_result(artifact)[0] == -1.005)

D3 = tempfile.mkdtemp()
t3, s3 = os.path.join(D3, "trades"), os.path.join(D3, "strategies")
w(os.path.join(s3, "one.yml"), spec("one", "active", "up", 0.3))
w(os.path.join(s3, "two.yml"), spec("two", "active", "up", 0.3))
w(os.path.join(t3, "one.yml"), trade("SAME", "one", -1))
w(os.path.join(t3, "two.yml"), trade("SAME", "two", -1))
out, _ = run([sys.executable, AGG, "--trades", t3, "--strategies", s3, "--update-spec"])
check("shared execution IDs require reconciliation for both strategies", len(out["strategies"]) == 2 and all(row["verdict"] == "REVIEW" for row in out["strategies"]), out)
with open(os.path.join(s3, "one.yml")) as stream:
    check("incomplete live sample is ineligible for selection", yaml.safe_load(stream)["live_performance"]["eligible_for_selection"] is False)
link = os.path.join(s3, "linked.yml")
os.symlink(outside, link)
try:
    aggregation.spec_path(s3, "linked")
    check("strategy symlink cannot escape root", False)
except ValueError:
    check("strategy symlink cannot escape root", True)

summary()
