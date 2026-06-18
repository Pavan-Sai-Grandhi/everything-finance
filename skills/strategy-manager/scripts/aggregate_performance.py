#!/usr/bin/env python3
"""Aggregate realized trade outcomes per strategy and recommend keep/optimize/deactivate.

Responsibility 4 of strategy-manager. trade-tracker writes a `result` block into each
trade-idea artifact when it closes (realized_R, exit_reason, ...). This reads those closed
trades, groups them by their `strategy` link, computes realized expectancy vs the strategy's
backtested expectancy, and emits a recommendation per strategy:

  KEEP        — live edge holding up (or sample still small)
  OPTIMIZE    — live edge positive but decaying well below backtest -> tune & re-backtest
  DEACTIVATE  — live expectancy negative over a real sample -> retire the strategy

With --update-spec, it also writes live_performance back into the matching spec and, on a
DEACTIVATE recommendation, flips status->inactive with a lifecycle reason (the only mutation
this script makes; everything else is read-only reporting the skill acts on).

Usage:
  python3 aggregate_performance.py          # defaults to artifacts/state/{trades,strategies}
  python3 aggregate_performance.py --strategy nifty500-momentum-swing --update-spec
Exit: 0 ok, 2 error.
"""
import argparse, glob, json, os, sys, subprocess
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "lib"))
import paths

MIN_SAMPLE = 10           # below this, never act — too few trades to judge
DECAY_FLOOR_R = 0.1       # live expectancy below this (but >=0) with backtest edge -> OPTIMIZE


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


def dump_yaml(obj, path):
    yaml = _need("yaml", "pyyaml")
    with open(path, "w") as f:
        yaml.safe_dump(obj, f, sort_keys=False, default_flow_style=False)


def metrics(realized):
    n = len(realized)
    wins = [r for r in realized if r > 0]
    losses = [r for r in realized if r <= 0]
    win_rate = round(len(wins) / n, 3) if n else None
    expectancy = round(sum(realized) / n, 3) if n else None
    avg_win = round(sum(wins) / len(wins), 3) if wins else None
    avg_loss = round(sum(losses) / len(losses), 3) if losses else None
    gp, gl = sum(wins), abs(sum(losses))
    pf = round(gp / gl, 3) if gl else (float("inf") if gp else None)
    return {"trades_closed": n, "win_rate": win_rate, "expectancy_R": expectancy,
            "avg_win_R": avg_win, "avg_loss_R": avg_loss,
            "profit_factor": (None if pf == float("inf") else pf)}


def recommend(m, backtest_R):
    n, e = m["trades_closed"], m["expectancy_R"]
    if n < MIN_SAMPLE:
        return "KEEP", f"only {n} closed trades (< {MIN_SAMPLE}) — insufficient sample to act"
    if e is None:
        return "KEEP", "no realized R values"
    if e < 0:
        return "DEACTIVATE", f"live expectancy {e}R over {n} trades is negative — edge gone"
    if backtest_R and e < max(DECAY_FLOOR_R, 0.5 * backtest_R):
        return "OPTIMIZE", (f"live expectancy {e}R well below backtest {backtest_R}R "
                            f"over {n} trades — decaying, tune & re-backtest")
    return "KEEP", f"live expectancy {e}R over {n} trades holding up"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--trades", default=None, help="default: artifacts/state/trades")
    p.add_argument("--strategies", default=None, help="default: artifacts/state/strategies")
    p.add_argument("--strategy", help="limit to one strategy name")
    p.add_argument("--update-spec", action="store_true",
                   help="write live_performance back; deactivate on DEACTIVATE rec")
    p.add_argument("--out")
    args = p.parse_args()
    if args.trades is None:
        args.trades = paths.state_dir("trades")
    if args.strategies is None:
        args.strategies = paths.state_dir("strategies")

    # gather closed trades grouped by strategy
    groups, exit_reasons = {}, {}
    for f in sorted(glob.glob(os.path.join(args.trades, "*.yml"))
                    + glob.glob(os.path.join(args.trades, "*.yaml"))):
        try:
            t = load_yaml(f)
        except Exception:
            continue
        if not isinstance(t, dict) or t.get("status") != "closed":
            continue
        res = t.get("result") or {}
        r = res.get("realized_R")
        if r is None:
            continue
        strat = t.get("strategy") or "_unlinked"
        if args.strategy and strat != args.strategy:
            continue
        groups.setdefault(strat, []).append(float(r))
        reason = res.get("exit_reason", "UNKNOWN")
        exit_reasons.setdefault(strat, {}).setdefault(reason, 0)
        exit_reasons[strat][reason] += 1

    # backtest expectancy per strategy (from its spec)
    def spec_path(name):
        for ext in ("yml", "yaml"):
            pth = os.path.join(args.strategies, f"{name}.{ext}")
            if os.path.exists(pth):
                return pth
        return None

    report = []
    for strat, realized in sorted(groups.items()):
        m = metrics(realized)
        sp = spec_path(strat) if strat != "_unlinked" else None
        backtest_R = None
        spec = None
        if sp:
            try:
                spec = load_yaml(sp)
                backtest_R = (spec.get("expectancy_assumptions") or {}).get("expectancy_R")
            except Exception:
                pass
        rec, why = recommend(m, backtest_R)
        drift = None
        if backtest_R is not None and m["expectancy_R"] is not None:
            drift = f"live {m['expectancy_R']}R vs backtest {backtest_R}R"
        entry = {"strategy": strat, "spec_file": sp, "metrics": m,
                 "exit_reasons": exit_reasons.get(strat, {}),
                 "backtest_expectancy_R": backtest_R, "drift": drift,
                 "recommendation": rec, "reason": why}
        report.append(entry)

        if args.update_spec and spec and sp:
            spec["live_performance"] = {
                "trades_closed": m["trades_closed"], "win_rate": m["win_rate"],
                "expectancy_R": m["expectancy_R"], "profit_factor": m["profit_factor"],
                "last_updated": str(date.today()), "drift_note": drift,
            }
            if rec == "DEACTIVATE":
                spec["status"] = "inactive"
                lc = spec.setdefault("lifecycle", {})
                lc["deactivated_at"] = str(date.today())
                lc["deactivated_reason"] = why
            dump_yaml(spec, sp)
            entry["spec_updated"] = True

    out = {"as_of": str(date.today()), "strategies": report,
           "min_sample": MIN_SAMPLE}
    print(json.dumps(out, indent=2))
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(out, open(args.out, "w"), indent=2)


if __name__ == "__main__":
    main()
