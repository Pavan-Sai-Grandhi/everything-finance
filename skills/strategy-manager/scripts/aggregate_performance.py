#!/usr/bin/env python3
"""Aggregate execution-backed closed trades and optionally update strategy specs.

Unknown outcomes remain gaps and prevent automatic lifecycle changes. Old closed
artifacts require broker execution references before they enter the learning sample.
Usage: python3 aggregate_performance.py [--strategy NAME] [--update-spec]
"""
import argparse
from collections import Counter, defaultdict
from contextlib import nullcontext
from datetime import date
import fcntl
import glob
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
                   os.path.dirname(os.path.abspath(__file__))))))
from finance import paths, spine
from finance.deps import need, load_yaml

MIN_SAMPLE = 10
DECAY_FLOOR_R = 0.1


def dump_yaml(obj, path):
    """Never leave a strategy half-written after a failed serialization or process."""
    yaml = need("yaml", "pyyaml")
    spine.atomic_write(path, lambda stream: yaml.safe_dump(
        obj, stream, sort_keys=False, default_flow_style=False),
        mode=os.stat(path).st_mode & 0o777)


def metrics(realized):
    n = len(realized)
    wins = [r for r in realized if r > 0]
    losses = [r for r in realized if r <= 0]
    gp, gl = sum(wins), abs(sum(losses))
    return {
        "trades_closed": n,
        "win_rate": round(len(wins) / n, 3) if n else None,
        "expectancy_R": round(sum(realized) / n, 3) if n else None,
        "avg_win_R": round(sum(wins) / len(wins), 3) if wins else None,
        "avg_loss_R": round(sum(losses) / len(losses), 3) if losses else None,
        # This is an R-weighted factor, not the rupee profit factor when risk sizes vary.
        "profit_factor": round(gp / gl, 3) if gl else None,
        "profit_factor_basis": "R multiples",
    }


def recommend(m, backtest_R):
    n, e = m["trades_closed"], m["expectancy_R"]
    if n < MIN_SAMPLE:
        return "KEEP", f"only {n} closed trades (< {MIN_SAMPLE}) — insufficient sample to act"
    if e is None:
        return "KEEP", "no realized R values"
    if e < 0:
        return "DEACTIVATE", f"live expectancy {e}R over {n} trades is negative — suspend under the risk policy"
    if backtest_R and e < max(DECAY_FLOOR_R, 0.5 * backtest_R):
        return "OPTIMIZE", f"live expectancy {e}R well below backtest {backtest_R}R over {n} trades — tune & re-backtest"
    return "KEEP", f"live expectancy {e}R over {n} trades holding up"


def _number(value):
    return None if isinstance(value, bool) or "%" in str(value) else spine.f(value)


def closed_result(trade):
    """Validate provenance/completeness before accepting a reported realized return."""
    result = trade.get("result")
    if not isinstance(result, dict):
        raise ValueError("closed trade needs a result mapping")
    execution = result.get("execution")
    if not isinstance(execution, dict) or execution.get("source") not in ("kite", "upstox"):
        raise ValueError("result needs broker execution evidence; reconcile legacy close with order history")
    ids = execution.get("exit_trade_ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(x, str) and x.strip() for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("execution needs distinct nonempty exit_trade_ids")
    entered, exited = spine.iso_date(trade.get("entry_date")), spine.iso_date(result.get("exit_date"))
    if not entered or not exited or entered > exited:
        raise ValueError("entry and exit dates must describe a completed holding interval")
    sizing = trade.get("sizing")
    qty = _number(sizing.get("qty")) if isinstance(sizing, dict) else None
    exit_qty = _number(result.get("exit_qty"))
    entry, exit_price = _number(trade.get("fill_avg")), _number(result.get("exit_price"))
    if any(x is None or x <= 0 for x in (entry, exit_price, qty, exit_qty)) or exit_qty != qty:
        raise ValueError("need actual positive fills and exit quantity equal to the full matched entry quantity")
    realized = _number(result.get("realized_R"))
    if realized is None or _number(result.get("realized_pnl")) is None:
        raise ValueError("realized R and P&L must be finite, sourced outcomes")
    plan = trade.get("plan") or {}
    stop = _number(plan.get("stop")) if isinstance(plan, dict) else None
    direction = trade.get("direction", "long")
    costs = _number(result.get("charges"))
    if stop is None or stop <= 0 or direction not in ("long", "short") or costs is None or costs < 0:
        raise ValueError("need original stop, direction and actual nonnegative charges for net realized R")
    risk = (entry - stop if direction == "long" else stop - entry) * qty
    net_pnl = ((exit_price - entry) if direction == "long" else (entry - exit_price)) * qty - costs
    computed_r = net_pnl / risk if risk > 0 else None
    if computed_r is None or not math.isfinite(computed_r) or not math.isfinite(net_pnl):
        raise ValueError("original fill-to-stop risk must be positive and calculations finite")
    if abs(net_pnl - _number(result["realized_pnl"])) > 0.02 or abs(computed_r - realized) > 0.011:
        raise ValueError("realized R/P&L do not reconcile with actual fills, charges and original risk")
    reason = result.get("exit_reason")
    if reason not in ("EXIT_STOP", "EXIT_THESIS", "EXIT_TARGET", "EXIT_TIME", "MANUAL"):
        raise ValueError("unknown exit reason")
    return computed_r, reason, {(execution["source"], ident) for ident in ids}


def spec_path(directory, name):
    """Artifact names cannot traverse or follow a symlink outside the selected root."""
    if not isinstance(name, str) or name in ("", ".", "..") or any(c in name for c in ("/", "\\", "\0")):
        raise ValueError("invalid strategy name")
    root = os.path.realpath(directory)
    for extension in ("yml", "yaml"):
        path = os.path.join(root, f"{name}.{extension}")
        if os.path.commonpath((root, os.path.realpath(path))) != root:
            raise ValueError("strategy file points outside the strategy directory")
        if os.path.isfile(path):
            return path
    return None


def aggregate(args):
    groups, reasons, excluded = defaultdict(list), defaultdict(Counter), Counter()
    gaps, seen_executions, unattributed = [], {}, 0
    for path in sorted(glob.glob(os.path.join(args.trades, "*.yml")) + glob.glob(os.path.join(args.trades, "*.yaml"))):
        strategy = None
        try:
            trade = load_yaml(path)
            if not isinstance(trade, dict):
                raise ValueError("trade must be a mapping")
            if trade.get("status") != "closed":
                continue
            strategy = trade.get("strategy") or "_unlinked"
            if args.strategy and strategy != args.strategy:
                continue
            spec_path(args.strategies, strategy)
            value, reason, execution_ids = closed_result(trade)
            collisions = execution_ids & seen_executions.keys()
            if collisions:
                for other in {seen_executions[key] for key in collisions}:
                    if other != strategy:
                        excluded[other] += 1
                raise ValueError("exit executions already attributed to another trade; reconcile duplicate or shared fills")
            seen_executions.update({key: strategy for key in execution_ids})
            groups[strategy].append(value)
            reasons[strategy][reason] += 1
        except Exception as exc:
            gaps.append(f"{os.path.basename(path)}: {exc}")
            if isinstance(strategy, str):
                excluded[strategy] += 1
            else:
                unattributed += 1

    report = []
    for strategy in sorted(groups.keys() | excluded.keys()):
        m = metrics(groups[strategy])
        sp, spec, backtest_r = None, None, None
        try:
            sp = spec_path(args.strategies, strategy) if strategy != "_unlinked" else None
            if sp:
                spec = load_yaml(sp)
                if not isinstance(spec, dict):
                    raise ValueError("strategy must be a mapping")
                assumptions = spec.get("expectancy_assumptions") or {}
                if not isinstance(assumptions, dict):
                    raise ValueError("expectancy_assumptions must be a mapping")
                backtest_r = _number(assumptions.get("expectancy_R"))
        except Exception as exc:
            gaps.append(f"{strategy}: {exc}")
            sp = spec = None
        rec, why = recommend(m, backtest_r)
        if excluded[strategy] or unattributed:
            rec, why = "REVIEW", f"{excluded[strategy]} closed outcome(s) unverified, {unattributed} unreadable/unattributed artifact(s); reconcile before lifecycle changes"
        drift = f"live {m['expectancy_R']}R vs backtest {backtest_r}R" if backtest_r is not None and m["expectancy_R"] is not None else None
        row = {"strategy": strategy, "spec_file": sp, "metrics": m,
               "excluded_closed": excluded[strategy], "exit_reasons": dict(reasons[strategy]),
               "backtest_expectancy_R": backtest_r, "drift": drift, "verdict": rec, "reason": why}
        report.append(row)
        if args.update_spec and spec is not None and sp:
            try:
                spec["live_performance"] = {
                    **m, "last_updated": str(date.today()), "drift_note": drift,
                    "eligible_for_selection": not excluded[strategy] and not unattributed and m["trades_closed"] >= MIN_SAMPLE,
                    "excluded_closed": excluded[strategy],
                }
                if rec == "DEACTIVATE":
                    lifecycle = spec.get("lifecycle") or {}
                    if not isinstance(lifecycle, dict):
                        raise ValueError("lifecycle must be a mapping")
                    lifecycle.update(deactivated_at=str(date.today()), deactivated_reason=why)
                    spec.update(status="inactive", lifecycle=lifecycle)
                dump_yaml(spec, sp)
                row["spec_updated"] = True
            except Exception as exc:
                gaps.append(f"{strategy}: cannot update spec: {exc}")
                row["spec_updated"] = False
    return {"as_of": str(date.today()), "strategies": report, "min_sample": MIN_SAMPLE, "gaps": gaps}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", help="default: artifacts/state/trades")
    parser.add_argument("--strategies", help="default: artifacts/state/strategies")
    parser.add_argument("--strategy", help="limit to one strategy name")
    parser.add_argument("--update-spec", action="store_true", help="write performance; deactivate only on complete execution-backed evidence")
    parser.add_argument("--out")
    args = parser.parse_args()
    args.trades = args.trades or paths.state_dir("trades")
    args.strategies = args.strategies or paths.state_dir("strategies")
    # Serialize this command's read/modify/write cycle across concurrent invocations.
    try:
        lock = open(os.path.join(args.strategies, ".aggregate.lock"), "a") if args.update_spec else nullcontext()
        with lock as stream:
            if stream is not None:
                fcntl.flock(stream, fcntl.LOCK_EX)
            out = aggregate(args)
        rendered = json.dumps(out, indent=2, allow_nan=False)
        if args.out:
            os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
            with open(args.out, "w") as stream:
                stream.write(rendered + "\n")
        print(rendered)
    except (OSError, ValueError) as exc:
        print(json.dumps({"strategies": [], "gaps": [str(exc)]}))
        sys.exit(2)


if __name__ == "__main__":
    main()
