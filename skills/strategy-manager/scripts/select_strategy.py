#!/usr/bin/env python3
"""Pick the active strategy that fits the current market regime (everything-finance).

Responsibility 3 of strategy-manager. Reads every strategy spec in a directory, keeps the
ones with status==active, tests each one's `regime_required` against the live regime read
(regime.json from strategy-manager/scripts/regime.py), and ranks the fitting ones by their
validated edge (live expectancy if available, else backtest expectancy). Selection is a
RUNTIME decision — an active spec is simply not selected while the tape doesn't fit it; its
status does not change here.

Usage:
  python3 select_strategy.py --regime artifacts/regime/2026-06-11.json
  # --strategies defaults to artifacts/state/strategies
Exit: 0 = a strategy selected, 11 = none fit, 12 = no active specs, 2 = error.
"""
import argparse, glob, json, os, sys, subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "lib"))
import paths


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


def regime_fit(req, regime):
    """Return (fits: bool, fails: [str]) for a spec's regime_required vs live regime.json."""
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
    p.add_argument("--regime", required=True, help="regime.json from regime.py")
    p.add_argument("--out")
    args = p.parse_args()
    if args.strategies is None:
        args.strategies = paths.state_dir("strategies")

    try:
        regime = json.load(open(args.regime))
    except Exception as e:
        print(json.dumps({"error": f"cannot read regime: {e}"})); sys.exit(2)

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
                   "risk_posture": regime.get("risk_posture"),
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
