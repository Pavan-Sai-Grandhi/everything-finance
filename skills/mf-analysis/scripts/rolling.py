#!/usr/bin/env python3
"""Rolling-return math for the past-performance pillar (mf-analysis, spec §2).

Varsity's hierarchy: point-to-point returns lie (they hang on two endpoints), so the
headline is **daily-rolled rolling returns** — roll a 1/3/5-year window across every
NAV observation and report mean/median/min plus the % of windows that beat a benchmark
(windows aligned by identical start dates across the compared funds). Max drawdown and
Sharpe (6% risk-free) round out the risk read; point-to-point CAGR is kept but labelled
inferior. Extracted from the ad-hoc inline math into one tested, reproducible script.

All figures derive from the cached mfapi.in NAV JSON — nothing fetched here (the skill
caches the series first). The math core is pure and offline-tested (`test_rolling.py`).

CLI:
  python3 rolling.py --navs fund.json [benchmark.json]   # first = subject, second = benchmark
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta

YEAR_DAYS = 365.25
RISK_FREE = 0.06          # ₹ repo-rate proxy (Varsity: compare Sharpe within category)
TRADING_DAYS = 252        # NAV is per-trading-day; annualisation assumes ~252/yr
HORIZONS = {"1y": 1, "3y": 3, "5y": 5}


# --------------------------------------------------------------------------- #
# parsing                                                                     #
# --------------------------------------------------------------------------- #
def parse_mfapi(payload):
    """mfapi.in payload (or a bare data list) → (dates ascending, navs parallel).
    Input rows are newest-first with DD-MM-YYYY dates; bad rows are skipped."""
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    rows = []
    for it in data or []:
        try:
            dt = datetime.strptime(it["date"], "%d-%m-%Y").date()
            nav = float(it["nav"])
        except (KeyError, ValueError, TypeError):
            continue
        if nav > 0:
            rows.append((dt, nav))
    rows.sort(key=lambda r: r[0])
    return [r[0] for r in rows], [r[1] for r in rows]


# --------------------------------------------------------------------------- #
# pure rolling math                                                           #
# --------------------------------------------------------------------------- #
def rolling_returns(dates, navs, years):
    """Daily-rolled annualised return (%) for each start that has an observation ~`years`
    later. Returns {start_date_iso: annualised_return_pct} — the map lets two funds align
    on identical start dates. Empty when history is shorter than the window."""
    target = years * YEAR_DAYS
    out, j, n = {}, 0, len(dates)
    for i in range(n):
        if j <= i:
            j = i + 1
        while j < n and (dates[j] - dates[i]).days < target:
            j += 1
        if j >= n:
            break
        elapsed = (dates[j] - dates[i]).days / YEAR_DAYS
        out[dates[i].isoformat()] = ((navs[j] / navs[i]) ** (1.0 / elapsed) - 1.0) * 100.0
    return out


def rolling_stats(returns_map):
    """mean/median/min/n over a rolling-return map. None fields when empty (young fund)."""
    vals = list(returns_map.values())
    if not vals:
        return {"mean": None, "median": None, "min": None, "n": 0}
    return {"mean": round(statistics.fmean(vals), 2),
            "median": round(statistics.median(vals), 2),
            "min": round(min(vals), 2),
            "n": len(vals)}


def pct_beating(fund_map, bench_map):
    """% of *aligned* windows (common start dates) where the fund beat the benchmark.
    None when the two share no window — never compare misaligned windows."""
    common = [k for k in fund_map if k in bench_map]
    if not common:
        return None
    beat = sum(1 for k in common if fund_map[k] > bench_map[k])
    return round(100.0 * beat / len(common), 1)


def max_drawdown(navs):
    """Deepest peak-to-trough decline over the full series, as a positive %."""
    if len(navs) < 2:
        return None
    peak, mdd = navs[0], 0.0
    for v in navs:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return round(abs(mdd) * 100.0, 2)


def sharpe(navs, rf=RISK_FREE, periods=TRADING_DAYS):
    """Annualised Sharpe from per-observation returns. None if volatility is zero /
    too little history. Compare within category only (Varsity)."""
    rets = [navs[k] / navs[k - 1] - 1.0 for k in range(1, len(navs))]
    if len(rets) < 2:
        return None
    sd = statistics.stdev(rets)
    if sd == 0:
        return None
    ann_ret = statistics.fmean(rets) * periods
    ann_vol = sd * (periods ** 0.5)
    return round((ann_ret - rf) / ann_vol, 2)


def trailing_cagr(dates, navs, years):
    """Point-to-point CAGR (%) over the trailing `years` — labelled inferior, kept for
    familiarity. None when history is shorter than the horizon."""
    if not dates:
        return None
    target = dates[-1] - timedelta(days=round(years * YEAR_DAYS))
    if dates[0] > target:
        return None
    i = next(k for k, d in enumerate(dates) if d >= target)
    elapsed = (dates[-1] - dates[i]).days / YEAR_DAYS
    if elapsed <= 0:
        return None
    return round(((navs[-1] / navs[i]) ** (1.0 / elapsed) - 1.0) * 100.0, 2)


# --------------------------------------------------------------------------- #
# report assembly                                                             #
# --------------------------------------------------------------------------- #
def analyze(dates, navs, bench=None):
    """Full past-performance read for one fund, optionally vs an aligned benchmark
    (bench = (dates, navs)). Young-fund gaps are labelled, never padded."""
    bench_dates, bench_navs = bench if bench else (None, None)
    rolling, gaps = {}, []
    for label, yrs in HORIZONS.items():
        fmap = rolling_returns(dates, navs, yrs)
        stats = rolling_stats(fmap)
        if bench:
            stats["pct_beating_benchmark"] = pct_beating(
                fmap, rolling_returns(bench_dates, bench_navs, yrs))
        if stats["n"] == 0:
            gaps.append(f"{label} rolling: history shorter than the window — omitted")
        rolling[label] = stats

    return {
        "span": {"from": dates[0].isoformat() if dates else None,
                 "to": dates[-1].isoformat() if dates else None,
                 "observations": len(dates)},
        "rolling_returns": rolling,
        "max_drawdown_pct": max_drawdown(navs),
        "sharpe": sharpe(navs),
        "point_to_point_cagr": {  # inferior — endpoint-dependent
            k: trailing_cagr(dates, navs, y) for k, y in HORIZONS.items()},
        "gaps": gaps,
    }


def main():
    ap = argparse.ArgumentParser(description="Rolling-return math for a fund (vs a benchmark).")
    ap.add_argument("--navs", nargs="+", required=True,
                    help="mfapi.in NAV JSON path(s): first = subject, optional second = benchmark")
    args = ap.parse_args()
    with open(args.navs[0]) as f:
        dates, navs = parse_mfapi(json.load(f))
    bench = None
    if len(args.navs) > 1:
        with open(args.navs[1]) as f:
            bench = parse_mfapi(json.load(f))
    print(json.dumps(analyze(dates, navs, bench), indent=2))


if __name__ == "__main__":
    main()
