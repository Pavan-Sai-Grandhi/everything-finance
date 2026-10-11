#!/usr/bin/env python3
"""Pick the active strategy that fits the current market regime (everything-finance).

Responsibility 3 of strategy-manager, and the `pick(purpose, regime)` discover calls.
Reads every strategy spec in a directory, keeps the ones with status==active (optionally
of a requested `--purpose`), tests each one's `regime_required` against the market-context
artifact, and ranks the fitting ones by edge — validated expectancy for a trading spec
(live if available, else backtest), recency for an investment spec (it has no backtest).
Selection is a RUNTIME decision — an active spec is simply not selected while the tape
doesn't fit it; its status is unchanged.

Usage:
  python3 select_strategy.py [--purpose trading|investment]
  # --regime     defaults to today's artifacts/market-analysis/<date>.json
  # --strategies defaults to artifacts/state/strategies
Exit: 0 = a strategy selected, 11 = none fit, 12 = no active specs, 2 = error.
"""
import argparse, glob, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
                   os.path.dirname(os.path.abspath(__file__))))))
from finance import paths
from finance.deps import load_yaml
from finance.spine import f


def regime_fit(req, regime):
    """Return (fits: bool, fails: [str]) for a spec's regime_required vs the market read."""
    fails = []
    if not req:
        return True, []
    trend = regime.get("market_trend")
    want_trend = req.get("market_trend")
    if want_trend and want_trend != trend:
        fails.append(f"trend is {trend}, needs {want_trend}")

    if req.get("nifty_above") == "ema200":
        above = (regime.get("trend_detail") or {}).get("above_ema200")
        if above is not True:
            fails.append("Nifty below 200-EMA" if above is False else "Nifty 200-EMA evidence missing")

    vol = regime.get("volatility") or {}
    vix = f(vol.get("vix"))
    vmax = req.get("vix_max")
    if vmax is not None:
        if vix is None:
            fails.append("VIX evidence missing")
        elif vix > vmax:
            fails.append(f"VIX {vix} > max {vmax}")

    br = f((regime.get("breadth") or {}).get("pct_sectors_above_ema50"))
    bmin = req.get("breadth_min_pct")
    if bmin is not None:
        if br is None:
            fails.append("breadth evidence missing")
        elif br < bmin:
            fails.append(f"breadth {br}% < min {bmin}%")

    return (len(fails) == 0), fails


def spec_purpose(spec):
    return spec.get("purpose") or "trading"


def edge_score(spec):
    """Rank a spec by edge. Trading: realized (live) expectancy, else backtest, else -inf.
    Investment (no backtest): a recency score from its lifecycle dates. Returns
    (score, tiebreak, source)."""
    if spec_purpose(spec) == "investment":
        lc = spec.get("lifecycle") or {}
        stamp = (lc.get("validated_at") or lc.get("activated_at")
                 or lc.get("generated_at") or spec.get("created") or "")
        return (str(stamp), "", "recency")   # yaml may parse a date; rank as an ISO string
    lp = spec.get("live_performance") or {}
    ea = spec.get("expectancy_assumptions") or {}
    live = f(lp.get("expectancy_R")) if lp.get("eligible_for_selection") is True else None
    back = f(ea.get("expectancy_R"))
    val = live if live is not None else back
    pf = f(lp.get("profit_factor") if live is not None else ea.get("profit_factor"))
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
    p.add_argument("--purpose", choices=("trading", "investment"), default=None,
                   help="keep only active specs of this purpose (default: all)")
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
            "hint": "call get_market_context(mode=\"quick\")",
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
        if args.purpose and spec_purpose(spec) != args.purpose:
            continue
        actives += 1
        fits, fails = regime_fit(spec.get("regime_required"), regime)
        score, _tie, src = edge_score(spec)
        is_trade = spec_purpose(spec) == "trading"
        candidates.append({
            "name": spec.get("name", os.path.basename(f)),
            "file": f, "fits_regime": fits, "fails": fails,
            "purpose": spec_purpose(spec),
            "rank_score": (None if score == float("-inf") else score),
            "expectancy_R": (score if is_trade and score != float("-inf") else None),
            "edge_source": src,
            "archetype": spec.get("archetype"),
        })

    # purpose sits before the score so a mixed (no --purpose) run never compares a trading
    # spec's float expectancy against an investment spec's date-string recency.
    fitting = [c for c in candidates if c["fits_regime"]]
    fitting.sort(key=lambda c: (c["rank_score"] is not None, c["purpose"],
                                c["rank_score"] if c["rank_score"] is not None else ""),
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
