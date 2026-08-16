#!/usr/bin/env python3
"""DEPRECATED — the regime read moved to the `market-analysis` skill.

This script used to be the plugin's entire market-context engine. It now exists only as a
compatibility shim for one release: it delegates to
`skills/market-analysis/scripts/market_context.py` (the single market-of-record) and writes
the legacy `artifacts/regime/<date>.json` shape so any caller still pointing here keeps
working.

Why it moved: six other skills needed market context and could not reach it inside
strategy-manager; the old script hand-rolled a pandas EWM instead of using `lib/ta.py`'s
TA-Lib reference (a real indicator drift); it had no caching, so three skills in one
morning re-downloaded the same indices; and it had no valuation dimension at all.

**New callers must use market-analysis directly** — it returns strictly more, cached:
    python3 skills/market-analysis/scripts/market_context.py --mode quick

The one rename: `risk_posture` -> `market_posture`. This shim emits BOTH so nothing breaks
mid-migration; the legacy key disappears when the shim does.

Usage: python3 regime.py [--out artifacts/regime/<today>.json]
"""
import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "..", "lib"))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "market-analysis", "scripts"))
import market_context  # noqa: E402
import paths  # noqa: E402


def to_legacy(ctx):
    """The market-context digest in the old regime.json shape.

    Only the keys the legacy consumers actually read are mapped; everything richer stays
    in the market-analysis artifact, which is where callers should be looking.
    """
    vol = ctx.get("volatility") or {}
    br = ctx.get("breadth") or {}
    posture = ctx.get("market_posture")
    legacy_posture = {"risk_on": "risk-on", "risk_off": "risk-off",
                      "neutral": "neutral"}.get(posture, posture)
    return {
        "as_of": ctx.get("as_of"),
        "market_trend": ctx.get("market_trend"),
        "trend_detail": ctx.get("trend_detail") or {},
        "volatility": {"vix": vol.get("vix"),
                       "vix_1y_percentile": vol.get("percentile_1y"),
                       "regime": vol.get("band")},
        "breadth": {"pct_sectors_above_ema50": br.get("pct_sectors_above_ema50"),
                    "detail": br.get("sectors_above_ema50_detail") or {}},
        "risk_posture": legacy_posture,      # deprecated mirror
        "market_posture": posture,           # the canonical name
        "rationale": ctx.get("rationale"),
        "data_gaps": ctx.get("gaps") or [],
        "deprecated": ("regime.py is a shim — use skills/market-analysis "
                       "(scripts/market_context.py --mode quick) instead"),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=None,
                   help="output path (default: artifacts/regime/<today>.json)")
    p.add_argument("--fresh", action="store_true")
    a = p.parse_args()

    print("DEPRECATED: regime.py now delegates to the market-analysis skill. "
          "Call skills/market-analysis/scripts/market_context.py --mode quick instead.",
          file=sys.stderr)

    ctx = None if a.fresh else market_context.load_today()
    if ctx is None:
        ctx = market_context.compute(mode="standard")
        mc_out = market_context.artifact_path()
        os.makedirs(os.path.dirname(mc_out) or ".", exist_ok=True)
        with open(mc_out, "w") as fh:
            json.dump(ctx, fh, indent=2, ensure_ascii=False)

    legacy = to_legacy(ctx)
    out = a.out or paths.report_path("regime", ext="json")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as fh:
        json.dump(legacy, fh, indent=2)
    print(json.dumps(legacy, indent=2))
    print(f"\nwrote {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
