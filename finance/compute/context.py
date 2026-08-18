#!/usr/bin/env python3
"""The plugin's single market-of-record — computes market state, emits a compact digest.

WHAT THIS IS
------------
The one place the plugin decides what the market is doing: trend, posture, stock-level
breadth, cap-tier valuation percentiles, institutional flows and the cross-asset backdrop.
Every other skill reads this answer instead of computing its own, so they cannot disagree
about the tape or re-download the same indices on the same morning.

THE DESIGN RULE — compute wide, report narrow
---------------------------------------------
All fetching and all arithmetic happen HERE, deterministically, in Python. The full result
is persisted as JSON. What crosses into a model's context is the **digest**: ~30 lines of
decision-grade numbers. A model reasoning about the market needs "Smallcap P/B at the 77th
percentile of 10 years, dividend yield at the 9th" — never 122 monthly samples, never 500
screener rows. Everything here exists to make that one compact statement trustworthy.

Indicator values come from `finance/compute/ta.py` (TA-Lib) and raw data from
`finance/sources/market.py` / `finance/sources/prices.py`, so this script owns
*interpretation* only — never a second definition of
an EMA or a second path to an endpoint.

FROZEN KEY NAMES (do not rename)
--------------------------------
`strategy-manager/scripts/select_strategy.py` gates on exactly four key paths, so renaming
one silently breaks every strategy spec's `regime_required`: `market_trend`,
`trend_detail.above_ema200`, `volatility.vix`, `breadth.pct_sectors_above_ema50`. The
posture key is `market_posture`, never `risk_posture` — wealth-manager uses that name for a
personal balance-sheet posture and the two would collide.

MODES
-----
  quick     reuse today's artifact if it exists (zero fetches); else compute standard.
            This is what OTHER skills call — N skills in a day cost one computation.
  standard  compute every rung, write the artifact, emit the digest.
  deep      standard + regime-transition history (free: diffs prior dated artifacts)
            + the per-sector valuation table.

CLI:
  python3 -m finance.compute.context --mode standard
  python3 -m finance.compute.context --mode quick --format digest
  python3 -m finance.compute.context --mode deep --format json
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import date

from finance import paths                 # the single path authority
from finance.compute import ta            # the indicator-of-record (TA-Lib)
from finance.sources import market        # the market-wide data spine
from finance.sources import prices        # EOD history

NIFTY = "^NSEI"

# Percentile cut-points for a valuation stance. Deliberately asymmetric at the top: the
# distribution of index multiples is right-skewed, so "rich" starts before the midpoint of
# the remaining range would suggest.
STANCE_BANDS = [(25, "cheap"), (45, "below average"), (65, "fair"), (85, "rich")]


# --------------------------------------------------------------------------- #
# pure classifiers (offline-testable; no fetching, no I/O)                     #
# --------------------------------------------------------------------------- #
def classify_trend(above50, above200, slope_up):
    """up / range / down — the taxonomy every strategy spec's `regime_required.
    market_trend` is written against, so the labels are part of the contract."""
    if above50 and above200 and slope_up:
        return "up"
    if (not above50) and (not above200) and not slope_up:
        return "down"
    return "range"


def classify_vol_band(vix):
    """low / normal / high on the 13/20 India-VIX cut-points."""
    if vix is None:
        return "unknown"
    return "low" if vix < 13 else ("high" if vix > 20 else "normal")


def robust_pe_percentile(pe_series, current_pe):
    """P/E percentile with the earnings-collapse distortion handled explicitly.

    An index P/E explodes when aggregate earnings collapse — the Smallcap 250's history
    contains months at a P/E of 44,692 (mid-2020), which are real prints but describe
    vanished earnings, not an expensive market. Left in, they make today look cheap by
    comparison. Samples above 3x the median are dropped and COUNTED, so the caller can say
    how many were excluded instead of quietly ranking against nonsense.
    Returns (percentile, n_used, n_dropped).
    """
    pool = [p for p in (pe_series or []) if p is not None]
    if not pool or current_pe is None:
        return None, 0, 0
    med = statistics.median(pool)
    clean = [p for p in pool if p < 3 * med]
    return market.percentile(clean, current_pe), len(clean), len(pool) - len(clean)


def classify_stance(pe_pct, pb_pct, dy_pct):
    """One valuation stance from the three percentiles that are available.

    P/B and dividend yield carry equal weight to P/E on purpose: book value and dividends
    do not evaporate in an earnings trough, so they stay meaningful exactly when P/E stops
    being. A cheap dividend yield is an EXPENSIVE market, hence the inversion.
    Returns (stance, blended_percentile).
    """
    parts = [p for p in (pe_pct, pb_pct, (100 - dy_pct) if dy_pct is not None else None)
             if p is not None]
    if not parts:
        return "unknown", None
    blended = round(sum(parts) / len(parts), 1)
    for cut, label in STANCE_BANDS:
        if blended < cut:
            return label, blended
    return "expensive", blended


def classify_posture(trend, vol_band, breadth_pct):
    """risk_on / neutral / risk_off + the one-line reason."""
    strong = breadth_pct is not None and breadth_pct >= 60
    weak = breadth_pct is not None and breadth_pct < 40
    if trend == "up" and vol_band != "high" and not weak:
        return "risk_on", ("Uptrend, acceptable volatility and participation — "
                           "directional long systems have a tailwind.")
    if vol_band == "high" or trend == "down" or weak:
        return "risk_off", ("Downtrend, high volatility or narrow participation — "
                            "size down or stand aside; trend-following will whipsaw.")
    return "neutral", ("No clear trend or mixed participation — "
                       "confirmation-heavy entries, modest size." if not strong else
                       "Broad participation without a confirmed index trend — selective.")


def _pct(count_of):
    """{'count': c, 'of': n} -> percentage, or None when nothing was priced."""
    if not count_of or not count_of.get("of"):
        return None
    return round(100.0 * count_of["count"] / count_of["of"], 1)


# --------------------------------------------------------------------------- #
# rungs                                                                        #
# --------------------------------------------------------------------------- #
def _trend(gaps):
    """Nifty 50 trend via the canonical TA-Lib EMA — not a hand-rolled pandas ewm."""
    df, g = prices.history_df(NIFTY, period="2y", adjusted=True)
    gaps.extend(g or [])
    if df is None or len(df) < 200:
        gaps.append("Nifty history unavailable — trend gate could not be computed")
        return "unknown", {}, None

    close = df["Close"].dropna()
    e50, e200 = ta.ema(close, 50), ta.ema(close, 200)
    px = float(close.iloc[-1])
    above50, above200 = px > float(e50.iloc[-1]), px > float(e200.iloc[-1])
    slope_up = float(e50.iloc[-1]) > float(e50.iloc[-20])
    high_52w = float(close.tail(252).max())
    detail = {
        "index": "NIFTY 50",
        "close": round(px, 1),
        "ema50": round(float(e50.iloc[-1]), 1),
        "ema200": round(float(e200.iloc[-1]), 1),
        "above_ema50": above50,
        "above_ema200": above200,      # consumed by select_strategy.py — keep this name
        "ema50_rising": slope_up,
        "pct_from_52w_high": round(100.0 * (px - high_52w) / high_52w, 1),
    }
    return classify_trend(above50, above200, slope_up), detail, str(close.index[-1].date())


def _volatility(gaps):
    df, g = prices.history_df("^INDIAVIX", period="5y", adjusted=True)
    if df is None or len(df) < 30:
        gaps.append("India VIX unavailable — volatility band defaulted to 'normal'")
        return {"vix": None, "percentile_1y": None, "percentile_5y": None, "band": "normal"}
    s = [float(v) for v in df["Close"].dropna()]
    lvl = s[-1]
    return {
        "vix": round(lvl, 2),                       # consumed by select_strategy.py
        "percentile_1y": market.percentile(s[-252:], lvl),
        "percentile_5y": market.percentile(s, lvl),
        "band": classify_vol_band(lvl),
    }


def _breadth(gaps):
    """Two breadth reads: stock-level participation, plus the sector count.

    `pct_sectors_above_ema50` keeps its exact name because strategy specs gate on it; the
    stock-level numbers are the ones worth reasoning about, since 10 sector indices
    cannot tell a broad advance from five heavyweights.
    """
    env = market.breadth(universe=500)
    gaps.extend(env.get("gaps") or [])
    counts = (env.get("data") or {}).get("counts") or {}
    out = {
        "universe": (env.get("data") or {}).get("universe"),
        "pct_above_sma50": _pct(counts.get("above_sma50")),
        "pct_above_sma200": _pct(counts.get("above_sma200")),
        "pct_advancing": _pct(counts.get("advancing")),
        "pct_near_52w_high": _pct(counts.get("near_52w_high")),
        "pct_near_52w_low": _pct(counts.get("near_52w_low")),
    }

    above, total, detail = 0, 0, {}
    for name, tk in market.SECTOR_YF.items():
        df, _g = prices.history_df(tk, period="6mo", adjusted=True)
        if df is None or len(df) < 50:
            detail[name] = None
            continue
        close = df["Close"].dropna()
        ok = float(close.iloc[-1]) > float(ta.ema(close, 50).iloc[-1])
        detail[name] = ok
        above += int(ok)
        total += 1
    out["pct_sectors_above_ema50"] = round(100.0 * above / total, 0) if total else None
    out["sectors_above_ema50_detail"] = detail
    if not total:
        gaps.append("sectoral breadth unavailable")
    return out


def _valuation(gaps, years=10):
    """Cap-tier valuation: level + own-history percentile for P/E, P/B and dividend yield.

    Decides whether a CATEGORY is worth adding money to — a separate question from which
    fund inside it is best.
    """
    live = market.indices()
    gaps.extend(live.get("gaps") or [])
    snapshot = (live.get("data") or {}).get("indices") or {}

    out = {}
    for ix in market.CAP_TIER_INDICES:
        cur = snapshot.get(ix) or {}
        hist = market.valuation_history(ix, years=years)
        series = (hist.get("data") or {}).get("series") or []
        if not series:
            gaps.append(f"no valuation history for {ix}")
        pes = [s["pe"] for s in series if s.get("pe") is not None]
        pbs = [s["pb"] for s in series if s.get("pb") is not None]
        dys = [s["dy"] for s in series if s.get("dy") is not None]

        pe_pct, n_used, n_dropped = robust_pe_percentile(pes, cur.get("pe"))
        pb_pct = market.percentile(pbs, cur.get("pb"))
        dy_pct = market.percentile(dys, cur.get("dy"))
        stance, blended = classify_stance(pe_pct, pb_pct, dy_pct)
        rec = {
            "pe": cur.get("pe"), "pe_pctile": pe_pct,
            "pb": cur.get("pb"), "pb_pctile": pb_pct,
            "dy": cur.get("dy"), "dy_pctile": dy_pct,
            "stance": stance, "blended_pctile": blended,
            "history_years": years, "samples": len(series),
            "chg_1y_pct": cur.get("pct_change_1y"),
        }
        if n_dropped:
            rec["pe_pctile_note"] = (
                f"{n_dropped} of {n_used + n_dropped} monthly samples excluded as "
                f"earnings-collapse distortions (P/E > 3x median)")
        out[ix] = rec
    return out


def _relative(valuation):
    """Smallcap vs largecap richness — the comparison a cap-tier allocation turns on.

    Expressed on P/B because it survives an earnings trough, with the P/E ratio alongside.
    """
    small = valuation.get("NIFTY SMALLCAP 250") or {}
    large = valuation.get("NIFTY 50") or {}
    if not (small.get("pb") and large.get("pb")):
        return {}
    pb_ratio = round(small["pb"] / large["pb"], 2)
    pe_ratio = (round(small["pe"] / large["pe"], 2)
                if small.get("pe") and large.get("pe") else None)
    spread = None
    if small.get("blended_pctile") is not None and large.get("blended_pctile") is not None:
        spread = round(small["blended_pctile"] - large["blended_pctile"], 1)
    read = "smallcaps and largecaps are priced similarly versus their own histories"
    if spread is not None and spread >= 25:
        read = ("smallcaps are expensive relative to their own history while largecaps are "
                "not — the cap tier, not the fund, is the bigger risk right now")
    elif spread is not None and spread <= -25:
        read = ("smallcaps are cheap relative to their own history while largecaps are not "
                "— the cap tier is offering the better entry")
    return {"smallcap_vs_largecap_pb_ratio": pb_ratio,
            "smallcap_vs_largecap_pe_ratio": pe_ratio,
            "percentile_spread": spread, "read": read}


def _sectors(gaps):
    """Sector leaders/laggards by 1-year change, from the single allIndices fetch."""
    live = market.indices()
    snap = (live.get("data") or {}).get("indices") or {}
    rows = [{"index": ix, "chg_1y_pct": snap[ix].get("pct_change_1y"),
             "pe": snap[ix].get("pe")}
            for ix in market.SECTOR_INDICES
            if ix in snap and snap[ix].get("pct_change_1y") is not None]
    if not rows:
        gaps.append("sector table unavailable")
        return {}
    rows.sort(key=lambda r: -(r["chg_1y_pct"] or 0))
    return {"leaders": rows[:4], "laggards": rows[-4:]}


def _transitions(limit=6):
    """Prior market_posture readings — free history, since every run leaves an artifact."""
    out = []
    d = paths.report_dir("market-analysis")
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d), reverse=True)[:limit]:
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, fn)) as fh:
                blob = json.load(fh)
            out.append({"date": blob.get("as_of"), "trend": blob.get("market_trend"),
                        "posture": blob.get("market_posture")})
        except Exception:  # noqa: BLE001
            continue
    return out


# --------------------------------------------------------------------------- #
# compute + digest                                                             #
# --------------------------------------------------------------------------- #
def compute(mode="standard", years=10):
    gaps = []
    trend, trend_detail, as_of = _trend(gaps)
    vol = _volatility(gaps)
    br = _breadth(gaps)
    val = _valuation(gaps, years=years)
    posture, why = classify_posture(trend, vol.get("band"), br.get("pct_sectors_above_ema50"))

    flows_env = market.flows()
    gaps.extend(flows_env.get("gaps") or [])
    macro_env = market.macro()
    gaps.extend(macro_env.get("gaps") or [])

    ctx = {
        "as_of": as_of or str(date.today()),
        "generated": str(date.today()),
        "mode": mode,
        "market_trend": trend,               # consumed by select_strategy.py
        "market_posture": posture,
        "rationale": why,
        "trend_detail": trend_detail,
        "volatility": vol,
        "breadth": br,
        "valuation": val,
        "relative": _relative(val),
        "flows": (flows_env.get("data") or {}).get("flows") or {},
        "flows_session": (flows_env.get("data") or {}).get("session"),
        "macro": (macro_env.get("data") or {}).get("macro") or {},
        "sectors": _sectors(gaps),
        "gaps": gaps,
    }
    if mode == "deep":
        ctx["recent_readings"] = _transitions()
    return ctx


def digest(ctx):
    """The ~30 decision-grade lines a model actually reads. Everything else stays on disk."""
    L = []
    td = ctx.get("trend_detail") or {}
    vol = ctx.get("volatility") or {}
    br = ctx.get("breadth") or {}
    L.append(f"as_of: {ctx.get('as_of')} | trend: {ctx.get('market_trend')} | "
             f"posture: {ctx.get('market_posture')}")
    L.append(f"rationale: {ctx.get('rationale')}")
    if td:
        L.append(f"NIFTY 50 {td.get('close')} | >50EMA {td.get('above_ema50')} "
                 f"| >200EMA {td.get('above_ema200')} | {td.get('pct_from_52w_high')}% from 52w high")
    L.append(f"VIX {vol.get('vix')} ({vol.get('band')}, {vol.get('percentile_1y')}th pctile of 1y)")
    L.append(f"breadth: {br.get('pct_above_sma50')}% >50DMA, {br.get('pct_above_sma200')}% "
             f">200DMA of {br.get('universe')} | sectors >50EMA {br.get('pct_sectors_above_ema50')}%"
             f" | near 52w high {br.get('pct_near_52w_high')}% vs low {br.get('pct_near_52w_low')}%")
    L.append("valuation (level, own-history percentile over "
             f"{(ctx.get('valuation') or {}).get('NIFTY 50', {}).get('history_years', 10)}y):")
    for ix, v in (ctx.get("valuation") or {}).items():
        L.append(f"  {ix}: P/E {v.get('pe')} ({v.get('pe_pctile')}p) | "
                 f"P/B {v.get('pb')} ({v.get('pb_pctile')}p) | "
                 f"DY {v.get('dy')} ({v.get('dy_pctile')}p) -> {v.get('stance')}"
                 f" [{v.get('blended_pctile')}p blended]")
        if v.get("pe_pctile_note"):
            L.append(f"    note: {v['pe_pctile_note']}")
    rel = ctx.get("relative") or {}
    if rel:
        L.append(f"relative: smallcap/largecap P/B {rel.get('smallcap_vs_largecap_pb_ratio')}, "
                 f"percentile spread {rel.get('percentile_spread')} — {rel.get('read')}")
    fl = ctx.get("flows") or {}
    if fl:
        L.append(f"flows ({ctx.get('flows_session')}): FII net ₹{(fl.get('FII') or {}).get('net_cr')} Cr, "
                 f"DII net ₹{(fl.get('DII') or {}).get('net_cr')} Cr")
    mac = ctx.get("macro") or {}
    if mac:
        L.append("macro: " + " | ".join(
            f"{k} {v.get('last')} ({v.get('chg_1m_pct')}% 1M, {v.get('percentile_5y')}p)"
            for k, v in mac.items()))
    sec = ctx.get("sectors") or {}
    if sec.get("leaders"):
        L.append("sector leaders 1Y: " + ", ".join(
            f"{r['index'].replace('NIFTY ', '')} {r['chg_1y_pct']}%" for r in sec["leaders"]))
        L.append("sector laggards 1Y: " + ", ".join(
            f"{r['index'].replace('NIFTY ', '')} {r['chg_1y_pct']}%" for r in sec["laggards"]))
    for r in ctx.get("recent_readings") or []:
        L.append(f"prior: {r.get('date')} {r.get('trend')}/{r.get('posture')}")
    gaps = ctx.get("gaps") or []
    L.append(f"gaps: {gaps if gaps else '[]'}")
    return "\n".join(L)


def report(mode="quick", years=10, fresh=False):
    """The market-of-record in the shared data-spine envelope: the digest plus the few
    structured fields a caller branches on without parsing prose.

    `fetched_at` is the context's own as-of, not the moment of the call — this is a daily
    artifact, and dating it now would claim a freshness it does not have.
    """
    ctx = resolve(mode=mode, years=years, fresh=fresh)
    return {
        "ok": True,
        "source": "market-analysis",
        "fetched_at": ctx.get("as_of"),
        "data": {
            "digest": digest(ctx),
            "as_of": ctx.get("as_of"),
            "market_trend": ctx.get("market_trend"),
            "market_posture": ctx.get("market_posture"),
            "rationale": ctx.get("rationale"),
        },
        "gaps": ctx.get("gaps", []),
    }


def artifact_path(day=None):
    return paths.report_path("market-analysis", date=day, ext="json")


def load_today():
    p = artifact_path()
    if not os.path.exists(p):
        return None
    try:
        with open(p) as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def persist(ctx, out=None):
    """Write the day's context to the artifact every other caller reads."""
    out = out or artifact_path()
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as fh:
        json.dump(ctx, fh, indent=2, ensure_ascii=False)
    return out


def resolve(mode="standard", years=10, fresh=False, out=None):
    """Today's context, computed once a day and shared.

    `quick` returns the day's artifact when it exists — that reuse is what lets every
    skill read the same market without N recomputations, so it has to live here rather
    than in a CLI, or a caller that never touches the CLI silently refetches and the
    reads drift apart. Any other mode, or `fresh`, recomputes and rewrites the artifact.
    """
    if mode == "quick" and not fresh:
        ctx = load_today()
        if ctx is not None:
            return ctx
    ctx = compute(mode=mode, years=years)
    persist(ctx, out)
    return ctx


def main():
    p = argparse.ArgumentParser(description="the plugin's single market-of-record")
    p.add_argument("--mode", choices=["quick", "standard", "deep"], default="standard")
    p.add_argument("--format", choices=["digest", "json"], default="digest")
    p.add_argument("--years", type=int, default=10, help="valuation-percentile lookback")
    p.add_argument("--out", default=None)
    p.add_argument("--fresh", action="store_true", help="ignore today's artifact")
    a = p.parse_args()

    ctx = resolve(mode=a.mode, years=a.years, fresh=a.fresh, out=a.out)

    if a.format == "json":
        json.dump(ctx, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        print(digest(ctx))


if __name__ == "__main__":
    main()
