#!/usr/bin/env python3
"""Pick the active strategy that fits the current market regime (everything-finance).

Responsibility 3 of strategy-manager. Reads every strategy spec in a directory, keeps the
ones with status==active, tests each one's `regime_required` against the market-context
artifact from the market-analysis skill, and ranks the fitting ones by validated edge (live
expectancy if available, else backtest expectancy). Selection is a RUNTIME decision — an
active spec is simply not selected while the tape doesn't fit it; its status is unchanged.

Usage:
  python3 select_strategy.py
  # --regime     defaults to today's artifacts/market-analysis/<date>.json
  # --strategies defaults to artifacts/state/strategies
Exit: 0 = a strategy selected, 11 = none fit, 12 = no active specs, 2 = error.
"""
import argparse, glob, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
                   os.path.dirname(os.path.abspath(__file__))))))
from finance import paths
from finance.deps import load_yaml


def regime_fit(req, regime):
    """Return (fits: bool, fails: [str]) for a spec's regime_required vs the market read."""
    fails = []
    if not req:
        return True, []
    trend = regime.get("market_trend")
    want_trend = req.get("market_trend")
    if want_trend and trend and want_trend != trend:
        fails.append(f"trend is {trend}, needs {want_trend}")

    if req.get("nifty_above") == "ema200":
        above = (regime.get("trend_detail") or {}).get("above_ema200")
        if above is False:
            fails.append("Nifty below 200-EMA")

    vol = regime.get("volatility") or {}
    vix = vol.get("vix")
    vmax = req.get("vix_max")
    if vix is not None and vmax is not None and vix > vmax:
        fails.append(f"VIX {vix} > max {vmax}")

    br = (regime.get("breadth") or {}).get("pct_sectors_above_ema50")
    bmin = req.get("breadth_min_pct")
    if br is not None and bmin is not None and br < bmin:
        fails.append(f"breadth {br}% < min {bmin}%")

    return (len(fails) == 0), fails


def edge_score(spec):
    """Prefer realized (live) expectancy, fall back to backtest expectancy. None -> -inf."""
    lp = spec.get("live_performance") or {}
    ea = spec.get("expectancy_assumptions") or {}
    live = lp.get("expectancy_R")
    back = ea.get("expectancy_R")
    val = live if live is not None else back
    pf = (lp.get("profit_factor") if live is not None else ea.get("profit_factor"))
    return (val if val is not None else float("-inf"),
            pf if pf is not None else float("-inf"),
            "live" if live is not None else ("backtest" if back is not None else "none"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strategies", default=None,
                   help="dir of <name>.yml specs (default: artifacts/state/strategies)")
    p.add_argument("--regime", default=None,
                   help="market-context JSON "
                        "(default: today's artifacts/market-analysis/<date>.json)")
    p.add_argument("--out")
    args = p.parse_args()
    if args.strategies is None:
        args.strategies = paths.state_dir("strategies")
    if args.regime is None:
        args.regime = paths.report_path("market-analysis", ext="json")

    try:
        regime = json.load(open(args.regime))
    except Exception as e:
        print(json.dumps({
            "error": f"cannot read market context: {e}",
            "hint": "run: python3 -m finance.compute.context --mode quick",
        })); sys.exit(2)

    files = sorted(glob.glob(os.path.join(args.strategies, "*.yml"))
                   + glob.glob(os.path.join(args.strategies, "*.yaml")))
    candidates, actives = [], 0
    for f in files:
        try:
            spec = load_yaml(f)
        except Exception:
            continue
        if not isinstance(spec, dict) or spec.get("status") != "active":
            continue
        actives += 1
        fits, fails = regime_fit(spec.get("regime_required"), regime)
        score, pf, src = edge_score(spec)
        candidates.append({
            "name": spec.get("name", os.path.basename(f)),
            "file": f, "fits_regime": fits, "fails": fails,
            "expectancy_R": (None if score == float("-inf") else score),
            "edge_source": src,
            "archetype": spec.get("archetype"),
        })

    fitting = [c for c in candidates if c["fits_regime"]]
    fitting.sort(key=lambda c: (c["expectancy_R"] is not None, c["expectancy_R"] or 0),
                 reverse=True)

    selected = fitting[0] if fitting else None
    out = {
        "as_of": regime.get("as_of"),
        "regime": {"market_trend": regime.get("market_trend"),
                   "market_posture": regime.get("market_posture"),
                   "vix": (regime.get("volatility") or {}).get("vix")},
        "active_specs": actives,
        "selected": selected,
        "ranked_fitting": fitting,
        "rejected_unfit": [c for c in candidates if not c["fits_regime"]],
    }
    print(json.dumps(out, indent=2))
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        json.dump(out, open(args.out, "w"), indent=2)

    if actives == 0:
        sys.exit(12)
    sys.exit(0 if selected else 11)


if __name__ == "__main__":
    main()
