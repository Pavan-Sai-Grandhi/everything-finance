"""The strategy library: pick the active spec that fits today's market, and learn from closes.

Selection keeps `status: active` specs whose `regime_required` the market-context artifact
satisfies, ranked by edge: verified live expectancy, else backtest expectancy, for a trading
spec; recency for an investment spec, which has no backtest. Regime fit is decided here at
run time and never written into `status`.

Performance review accepts a closed trade only with broker execution evidence whose net R
reconciles with the fills, charges and original stop, then recommends KEEP, OPTIMIZE,
DEACTIVATE, or REVIEW when any outcome could not be verified.
"""
from collections import Counter, defaultdict
from contextlib import nullcontext
from datetime import date
import fcntl
import glob
import math
import os

from finance import paths, spine
from finance.deps import load_yaml, need

_SOURCE = "finance.compute.strategy_library"
MIN_SAMPLE = 10
DECAY_FLOOR_R = 0.1


def _yaml_files(directory):
    return sorted(glob.glob(os.path.join(directory, "*.yml"))
                  + glob.glob(os.path.join(directory, "*.yaml")))


def regime_fit(req, regime):
    """-> (fits, reasons it does not) for a spec's regime_required vs the market read."""
    if not req:
        return True, []
    fails = []
    trend, want = regime.get("market_trend"), req.get("market_trend")
    if want and want != trend:
        fails.append(f"trend is {trend}, needs {want}")
    if req.get("nifty_above") == "ema200":
        above = (regime.get("trend_detail") or {}).get("above_ema200")
        if above is not True:
            fails.append("Nifty below 200-EMA" if above is False else "Nifty 200-EMA evidence missing")
    vix, vmax = spine.f((regime.get("volatility") or {}).get("vix")), req.get("vix_max")
    if vmax is not None:
        if vix is None:
            fails.append("VIX evidence missing")
        elif vix > vmax:
            fails.append(f"VIX {vix} > max {vmax}")
    breadth = spine.f((regime.get("breadth") or {}).get("pct_sectors_above_ema50"))
    bmin = req.get("breadth_min_pct")
    if bmin is not None:
        if breadth is None:
            fails.append("breadth evidence missing")
        elif breadth < bmin:
            fails.append(f"breadth {breadth}% < min {bmin}%")
    return not fails, fails


def purpose(spec):
    return spec.get("purpose") or "trading"


def edge_score(spec):
    """-> (score, tie-break, source). Investment specs rank on an ISO recency string."""
    if purpose(spec) == "investment":
        lc = spec.get("lifecycle") or {}
        stamp = (lc.get("validated_at") or lc.get("activated_at")
                 or lc.get("generated_at") or spec.get("created") or "")
        return str(stamp), "", "recency"
    live_block = spec.get("live_performance") or {}
    backtest_block = spec.get("expectancy_assumptions") or {}
    live = (spine.f(live_block.get("expectancy_R"))
            if live_block.get("eligible_for_selection") is True else None)
    back = spine.f(backtest_block.get("expectancy_R"))
    value = live if live is not None else back
    pf = spine.f(live_block.get("profit_factor") if live is not None
                 else backtest_block.get("profit_factor"))
    return (value if value is not None else float("-inf"),
            pf if pf is not None else float("-inf"),
            "live" if live is not None else ("backtest" if back is not None else "none"))


def select(regime, strategies=None, want=None):
    """Rank the active specs in `strategies` against the market-context dict `regime`."""
    strategies = strategies or paths.state_dir("strategies")
    candidates, actives = [], 0
    for path in _yaml_files(strategies):
        try:
            spec = load_yaml(path)
        except Exception:  # noqa: BLE001 — an unreadable spec cannot be selected
            continue
        if not isinstance(spec, dict) or spec.get("status") != "active":
            continue
        if want and purpose(spec) != want:
            continue
        actives += 1
        fits, fails = regime_fit(spec.get("regime_required"), regime)
        score, _, source = edge_score(spec)
        scored = score != float("-inf")
        candidates.append({
            "name": spec.get("name", os.path.basename(path)),
            "file": path, "fits_regime": fits, "fails": fails,
            "purpose": purpose(spec),
            "rank_score": score if scored else None,
            "expectancy_R": score if purpose(spec) == "trading" and scored else None,
            "edge_source": source,
            "archetype": spec.get("archetype"),
        })
    # Purpose precedes score, so a float expectancy never compares with a date string.
    fitting = sorted((c for c in candidates if c["fits_regime"]),
                     key=lambda c: (c["rank_score"] is not None, c["purpose"],
                                    c["rank_score"] if c["rank_score"] is not None else ""),
                     reverse=True)
    selected = fitting[0] if fitting else None
    return {
        "as_of": regime.get("as_of"),
        "regime": {"market_trend": regime.get("market_trend"),
                   "market_posture": regime.get("market_posture"),
                   "vix": (regime.get("volatility") or {}).get("vix")},
        "active_specs": actives,
        "outcome": "selected" if selected else ("none_fit" if actives else "no_active"),
        "selected": selected,
        "ranked_fitting": fitting,
        "rejected_unfit": [c for c in candidates if not c["fits_regime"]],
    }


def metrics(realized):
    n = len(realized)
    wins = [r for r in realized if r > 0]
    losses = [r for r in realized if r <= 0]
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    return {
        "trades_closed": n,
        "win_rate": round(len(wins) / n, 3) if n else None,
        "expectancy_R": round(sum(realized) / n, 3) if n else None,
        "avg_win_R": round(sum(wins) / len(wins), 3) if wins else None,
        "avg_loss_R": round(sum(losses) / len(losses), 3) if losses else None,
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
        "profit_factor_basis": "R multiples",
    }


def recommend(m, backtest_r):
    n, e = m["trades_closed"], m["expectancy_R"]
    if n < MIN_SAMPLE:
        return "KEEP", f"only {n} closed trades (< {MIN_SAMPLE}) — insufficient sample to act"
    if e is None:
        return "KEEP", "no realized R values"
    if e < 0:
        return "DEACTIVATE", f"live expectancy {e}R over {n} trades is negative — suspend under the risk policy"
    if backtest_r and e < max(DECAY_FLOOR_R, 0.5 * backtest_r):
        return "OPTIMIZE", f"live expectancy {e}R well below backtest {backtest_r}R over {n} trades — tune & re-backtest"
    return "KEEP", f"live expectancy {e}R over {n} trades holding up"


def _number(value):
    return None if isinstance(value, bool) or "%" in str(value) else spine.f(value)


def closed_result(trade):
    """-> (net realized R, exit reason, execution ids) for a verified close, else ValueError."""
    result = trade.get("result")
    if not isinstance(result, dict):
        raise ValueError("closed trade needs a result mapping")
    execution = result.get("execution")
    if not isinstance(execution, dict) or execution.get("source") not in ("kite", "upstox"):
        raise ValueError("result needs broker execution evidence; reconcile the close with order history")
    ids = execution.get("exit_trade_ids")
    if (not isinstance(ids, list) or not ids or len(set(ids)) != len(ids)
            or not all(isinstance(x, str) and x.strip() for x in ids)):
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
    """The spec file for `name` inside `directory`; a name cannot traverse or escape it."""
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


def _dump_yaml(obj, path):
    yaml = need("yaml", "pyyaml")
    spine.atomic_write(path, lambda stream: yaml.safe_dump(
        obj, stream, sort_keys=False, default_flow_style=False),
        mode=os.stat(path).st_mode & 0o777)


def _aggregate(trades, strategies, only, update_spec):
    groups, reasons, excluded = defaultdict(list), defaultdict(Counter), Counter()
    gaps, seen_executions, unattributed = [], {}, 0
    for path in _yaml_files(trades):
        strategy = None
        try:
            trade = load_yaml(path)
            if not isinstance(trade, dict):
                raise ValueError("trade must be a mapping")
            if trade.get("status") != "closed":
                continue
            strategy = trade.get("strategy") or "_unlinked"
            if only and strategy != only:
                continue
            spec_path(strategies, strategy)
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
        except Exception as exc:  # noqa: BLE001 — every unverified close is a named gap
            gaps.append(f"{os.path.basename(path)}: {exc}")
            if isinstance(strategy, str):
                excluded[strategy] += 1
            else:
                unattributed += 1

    report = []
    for strategy in sorted(groups.keys() | excluded.keys()):
        m = metrics(groups[strategy])
        path, spec, backtest_r = None, None, None
        try:
            path = spec_path(strategies, strategy) if strategy != "_unlinked" else None
            if path:
                spec = load_yaml(path)
                if not isinstance(spec, dict):
                    raise ValueError("strategy must be a mapping")
                assumptions = spec.get("expectancy_assumptions") or {}
                if not isinstance(assumptions, dict):
                    raise ValueError("expectancy_assumptions must be a mapping")
                backtest_r = _number(assumptions.get("expectancy_R"))
        except Exception as exc:  # noqa: BLE001
            gaps.append(f"{strategy}: {exc}")
            path = spec = None
        verdict, why = recommend(m, backtest_r)
        if excluded[strategy] or unattributed:
            verdict, why = "REVIEW", (f"{excluded[strategy]} closed outcome(s) unverified, "
                                      f"{unattributed} unreadable/unattributed artifact(s); "
                                      "reconcile before lifecycle changes")
        drift = (f"live {m['expectancy_R']}R vs backtest {backtest_r}R"
                 if backtest_r is not None and m["expectancy_R"] is not None else None)
        row = {"strategy": strategy, "spec_file": path, "metrics": m,
               "excluded_closed": excluded[strategy], "exit_reasons": dict(reasons[strategy]),
               "backtest_expectancy_R": backtest_r, "drift": drift, "verdict": verdict,
               "reason": why}
        report.append(row)
        if update_spec and spec is not None and path:
            try:
                spec["live_performance"] = {
                    **m, "last_updated": str(date.today()), "drift_note": drift,
                    "eligible_for_selection": (not excluded[strategy] and not unattributed
                                               and m["trades_closed"] >= MIN_SAMPLE),
                    "excluded_closed": excluded[strategy],
                }
                if verdict == "DEACTIVATE":
                    lifecycle = spec.get("lifecycle") or {}
                    if not isinstance(lifecycle, dict):
                        raise ValueError("lifecycle must be a mapping")
                    lifecycle.update(deactivated_at=str(date.today()), deactivated_reason=why)
                    spec.update(status="inactive", lifecycle=lifecycle)
                _dump_yaml(spec, path)
                row["spec_updated"] = True
            except Exception as exc:  # noqa: BLE001
                gaps.append(f"{strategy}: cannot update spec: {exc}")
                row["spec_updated"] = False
    return {"as_of": str(date.today()), "strategies": report, "min_sample": MIN_SAMPLE, "gaps": gaps}


def review_performance(strategy=None, update_spec=False, trades=None, strategies=None):
    """Aggregate verified closes per strategy; `update_spec` writes live_performance and
    deactivates on a complete negative sample. Concurrent updates serialize on a lock."""
    trades = trades or paths.state_dir("trades")
    strategies = strategies or paths.state_dir("strategies")
    lock = open(os.path.join(strategies, ".aggregate.lock"), "a") if update_spec else nullcontext()
    with lock as stream:
        if stream is not None:
            fcntl.flock(stream, fcntl.LOCK_EX)
        return _aggregate(trades, strategies, strategy, update_spec)


@spine.guarded(_SOURCE)
def select_report(want=None, regime=None, strategies=None, out=None):
    regime = regime or paths.report_path("market-analysis", ext="json")
    try:
        context = spine.read_json(regime)
        if not isinstance(context, dict):
            raise ValueError("market context must be a JSON object")
    except (OSError, ValueError) as exc:
        return spine.envelope(False, _SOURCE, {"outcome": "no_market_context"},
                              [f"cannot read market context {regime}: {exc}; "
                               "call get_market_context(mode=\"quick\") first"])
    result = select(context, strategies=strategies, want=want)
    if out:
        spine.write_json(result, out)
    return spine.envelope(True, _SOURCE, dict(result, result_path=out), [])


@spine.guarded(_SOURCE)
def performance_report(strategy=None, update_spec=False, trades=None, strategies=None, out=None):
    result = review_performance(strategy, update_spec, trades=trades, strategies=strategies)
    if out:
        spine.write_json(result, out)
    gaps = result.pop("gaps")
    return spine.envelope(True, _SOURCE, dict(result, result_path=out), gaps)
