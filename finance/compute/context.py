"""The plugin's single market-of-record — computes market state, emits a compact digest.

The one place the plugin decides what the market is doing: trend, posture, stock-level
breadth, cap-tier valuation percentiles, institutional flows and the cross-asset backdrop.
Every other skill reads this answer instead of computing its own, so they cannot disagree
about the tape or re-download the same indices on the same morning.

Compute wide, report narrow: all fetching and arithmetic happen here and the full result is
persisted as JSON, but what crosses into a model's context is the digest — ~30 lines of
decision-grade numbers. Indicator values come from `ta.py` and raw data from
`sources/market.py` / `sources/prices.py`, so this module owns interpretation only.

FROZEN KEY NAMES (do not rename): `strategy_library.regime_fit` gates on
exactly four key paths, so renaming one silently breaks every strategy spec's
`regime_required` — `market_trend`, `trend_detail.above_ema200`, `volatility.vix`,
`breadth.pct_sectors_above_ema50`. The posture key is `market_posture`, never
`risk_posture`: wealth-manager uses that name for a personal balance-sheet posture and the
two would collide.

Modes: `quick` reuses today's artifact if it exists (zero fetches) — this is what other
skills call, so N skills in a day cost one computation; `standard` computes every rung;
`deep` adds regime-transition history and the per-sector valuation table.

Reached through: get_market_context.
"""
from __future__ import annotations

import json
import fcntl
import threading
import os
from datetime import date

from finance import paths, spine
from finance.compute import ta
from finance.sources import market
from finance.sources import prices

NIFTY = "^NSEI"
_CONTEXT_VERSION = 3
_CONTEXT_LOCK = threading.RLock()

# One P/E ranking method for every index-valuation reader, owned by the source layer.
robust_pe_percentile = market.robust_pe_percentile

# Percentile cut-points for a valuation stance. Deliberately asymmetric at the top: the
# distribution of index multiples is right-skewed, so "rich" starts before the midpoint of
# the remaining range would suggest.
STANCE_BANDS = [(25, "cheap"), (45, "below average"), (65, "fair"), (85, "rich")]


def _percentage(value):
    return spine.is_finite(value) and 0 <= value <= 100


def _closes(df, minimum, label, gaps):
    """Require intact positive closes; dropping rows changes indicator time periods."""
    if df is None or "Close" not in df or len(df) < minimum:
        gaps.append(f"{label}: insufficient price history")
        return None
    close = df["Close"]
    if not all(spine.is_finite(v) and v > 0 for v in close):
        gaps.append(f"{label}: invalid or missing close prices")
        return None
    return close


def classify_trend(above50, above200, slope_up):
    """up / range / down — the taxonomy every strategy spec's `regime_required.
    market_trend` is written against, so the labels are part of the contract."""
    if any(type(v) is not bool for v in (above50, above200, slope_up)):
        return "unknown"
    if above50 and above200 and slope_up:
        return "up"
    if (not above50) and (not above200) and not slope_up:
        return "down"
    return "range"


def classify_vol_band(vix):
    """low / normal / high on the 13/20 India-VIX cut-points."""
    if not spine.is_finite(vix) or vix <= 0:
        return "unknown"
    return "low" if vix < 13 else ("high" if vix > 20 else "normal")


def classify_stance(pe_pct, pb_pct, dy_pct):
    """One valuation stance from the three percentiles that are available.

    P/B and dividend yield carry equal weight to P/E on purpose: book value and dividends
    do not evaporate in an earnings trough, so they stay meaningful exactly when P/E stops
    being. A cheap dividend yield is an EXPENSIVE market, hence the inversion.
    Returns (stance, blended_percentile).
    """
    parts = [p for p in (pe_pct, pb_pct) if _percentage(p)]
    if _percentage(dy_pct):
        parts.append(100 - dy_pct)
    if not parts:
        return "unknown", None
    blended = round(sum(parts) / len(parts), 1)
    for cut, label in STANCE_BANDS:
        if blended < cut:
            return label, blended
    return "expensive", blended


def classify_posture(trend, vol_band, breadth_pct):
    """risk_on / neutral / risk_off + the one-line reason."""
    valid_breadth = _percentage(breadth_pct)
    strong = valid_breadth and breadth_pct >= 60
    weak = valid_breadth and breadth_pct < 40
    if trend == "up" and vol_band in ("low", "normal") and valid_breadth and not weak:
        return "risk_on", ("Uptrend, acceptable volatility and participation — "
                           "directional long systems have a tailwind.")
    if vol_band == "high" or trend == "down" or weak:
        return "risk_off", ("Downtrend, high volatility or narrow participation — "
                            "size down or stand aside; trend-following will whipsaw.")
    if trend not in ("up", "range", "down") or vol_band not in ("low", "normal", "high") or not valid_breadth:
        return "neutral", "Market evidence incomplete — no risk-on authorization."
    return "neutral", ("No clear trend or mixed participation — "
                       "confirmation-heavy entries, modest size." if not strong else
                       "Broad participation without a confirmed index trend — selective.")


def _pct(count_of):
    """{'count': c, 'of': n} -> percentage, or None when nothing was priced."""
    if not isinstance(count_of, dict):
        return None
    count, total = count_of.get("count"), count_of.get("of")
    if (type(count) is not int or type(total) is not int
            or total <= 0 or not 0 <= count <= total):
        return None
    return round(100.0 * count_of["count"] / count_of["of"], 1)


def _trend(gaps):
    """Nifty 50 trend via the canonical TA-Lib EMA — not a hand-rolled pandas ewm."""
    df, g = prices.history_df(NIFTY, period="2y", adjusted=True)
    gaps.extend(g or [])
    close = _closes(df, 200, "Nifty", gaps)
    if close is None:
        gaps.append("Nifty history unavailable — trend gate could not be computed")
        return "unknown", {}, None

    e50, e200 = ta.ema(close, 50), ta.ema(close, 200)
    px = float(close.iloc[-1])
    above50, above200 = px > float(e50.iloc[-1]), px > float(e200.iloc[-1])
    slope_up = float(e50.iloc[-1]) > float(e50.iloc[-20])
    high_52w = float(close.tail(252).max()) if len(close) >= 252 else None
    if high_52w is None:
        gaps.append("Nifty: fewer than 252 observations for the 52-week high")
    detail = {
        "index": "NIFTY 50",
        "close": round(px, 1),
        "ema50": round(float(e50.iloc[-1]), 1),
        "ema200": round(float(e200.iloc[-1]), 1),
        "above_ema50": above50,
        "above_ema200": above200,      # consumed by select_strategy.py — keep this name
        "ema50_rising": slope_up,
        "pct_from_52w_high": round(100.0 * (px - high_52w) / high_52w, 1) if high_52w else None,
    }
    return classify_trend(above50, above200, slope_up), detail, str(close.index[-1].date())


def _volatility(gaps, expected_as_of=None):
    df, g = prices.history_df("^INDIAVIX", period="5y", adjusted=True)
    gaps.extend(g or [])
    close = _closes(df, 30, "India VIX", gaps)
    if close is None:
        return {"vix": None, "percentile_1y": None, "percentile_5y": None, "band": "unknown"}
    s = [float(v) for v in close]
    lvl = s[-1]
    observed = str(close.index[-1].date())
    if expected_as_of is not None and observed != expected_as_of:
        gaps.append(f"India VIX session {observed} differs from Nifty {expected_as_of}; gate withheld")
        return {"vix": None, "observed_vix": round(lvl, 2), "as_of": observed,
                "percentile_1y": None, "percentile_5y": None, "band": "unknown"}
    return {
        "as_of": observed,
        "observations": len(s),
        "first_observation": str(close.index[0].date()),
        "vix": round(lvl, 2),                       # consumed by select_strategy.py
        "percentile_1y": market.percentile(s[-252:], lvl),
        "percentile_5y": market.percentile(s, lvl),
        "band": classify_vol_band(lvl),
    }


def _breadth(gaps, expected_as_of=None):
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
        "requested_universe": (env.get("data") or {}).get("requested_universe"),
        "counts": counts,
        "pct_above_sma50": _pct(counts.get("above_sma50")),
        "pct_above_sma200": _pct(counts.get("above_sma200")),
        "pct_advancing": _pct(counts.get("advancing")),
        "pct_near_52w_high": _pct(counts.get("near_52w_high")),
        "pct_near_52w_low": _pct(counts.get("near_52w_low")),
    }

    above, total, detail = 0, 0, {}
    observation_dates = {}
    for name, tk in market.SECTOR_YF.items():
        df, _g = prices.history_df(tk, period="6mo", adjusted=True)
        gaps.extend(_g or [])
        close = _closes(df, 50, name, gaps)
        if close is None:
            detail[name] = None
            continue
        observed = str(close.index[-1].date())
        observation_dates[name] = observed
        if expected_as_of is not None and observed != expected_as_of:
            detail[name] = None
            gaps.append(f"{name} session {observed} differs from Nifty {expected_as_of}; gate withheld")
            continue
        ok = float(close.iloc[-1]) > float(ta.ema(close, 50).iloc[-1])
        detail[name] = ok
        above += int(ok)
        total += 1
    same_session = len(set(observation_dates.values())) <= 1
    complete = total and total == len(market.SECTOR_YF) and same_session
    out["pct_sectors_above_ema50"] = round(100.0 * above / total, 0) if complete else None
    if not same_session:
        gaps.append("sector history sessions differ; breadth gate withheld")
    out["sector_observation_dates"] = observation_dates
    out["sectors_above_ema50_detail"] = detail
    out["sectors_available"] = total
    out["sectors_expected"] = len(market.SECTOR_YF)
    if total < len(market.SECTOR_YF):
        gaps.append(f"sectoral breadth incomplete: {total}/{len(market.SECTOR_YF)} sectors available; gate withheld")
    return out


def _valuation(gaps, live, years=10):
    """Cap-tier valuation: level + own-history percentile for P/E, P/B and dividend yield.

    Decides whether a CATEGORY is worth adding money to — a separate question from which
    fund inside it is best.
    """
    snapshot = (live.get("data") or {}).get("indices") or {}

    out = {}
    for ix in market.CAP_TIER_INDICES:
        cur = snapshot.get(ix) or {}
        hist = market.valuation_history(ix, years=years)
        gaps.extend(hist.get("gaps") or [])
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
            "source_timestamp": (live.get("data") or {}).get("source_timestamp"),
            "pe": cur.get("pe"), "pe_pctile": pe_pct,
            "pb": cur.get("pb"), "pb_pctile": pb_pct,
            "dy": cur.get("dy"), "dy_pctile": dy_pct,
            "stance": stance, "blended_pctile": blended,
            "history_years": years, "samples": len(series),
            "requested_samples": (hist.get("data") or {}).get("requested_samples"),
            "first_observation": (hist.get("data") or {}).get("first_observation"),
            "last_observation": (hist.get("data") or {}).get("last_observation"),
            "chg_1y_pct": cur.get("pct_change_1y"),
        }
        if n_dropped:
            rec["pe_pctile_note"] = (
                f"{n_dropped} of {n_used + n_dropped} monthly samples excluded as "
                f"statistical outliers (P/E >= 3x median; heuristic, cause unverified)")
        out[ix] = rec
    return out


def _relative(valuation):
    """Smallcap vs largecap richness — the comparison a cap-tier allocation turns on.

    Expressed on P/B because it survives an earnings trough, with the P/E ratio alongside.
    """
    small = valuation.get("NIFTY SMALLCAP 250") or {}
    large = valuation.get("NIFTY 50") or {}
    if not all(spine.is_finite(v) and v > 0 for v in (small.get("pb"), large.get("pb"))):
        return {}
    pb_ratio = round(small["pb"] / large["pb"], 2)
    pe_ratio = (round(small["pe"] / large["pe"], 2)
                if all(spine.is_finite(v) and v > 0 for v in (small.get("pe"), large.get("pe"))) else None)
    spread = None
    if all(_percentage(v) for v in (small.get("blended_pctile"), large.get("blended_pctile"))):
        spread = round(small["blended_pctile"] - large["blended_pctile"], 1)
    read = ("relative historical valuation unavailable" if spread is None else
            "smallcaps and largecaps have similar blended historical valuation percentiles")
    if spread is not None and spread >= 25:
        read = ("smallcaps are expensive relative to their own history while largecaps are "
                "not — the cap tier, not the fund, is the bigger risk right now")
    elif spread is not None and spread <= -25:
        read = ("smallcaps are cheap relative to their own history while largecaps are not "
                "— the cap tier is offering the better entry")
    return {"smallcap_vs_largecap_pb_ratio": pb_ratio,
            "smallcap_vs_largecap_pe_ratio": pe_ratio,
            "percentile_spread": spread, "read": read}


def _sectors(gaps, live):
    """Sector leaders/laggards by 1-year change, from the single allIndices fetch."""
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
    for fn in sorted(os.listdir(d), reverse=True):
        if not fn.endswith(".json"):
            continue
        try:
            stamp = date.fromisoformat(fn[:-5])
            if stamp >= date.today():
                continue
            with open(os.path.join(d, fn), encoding="utf-8") as fh:
                blob = json.load(fh)
            if not isinstance(blob, dict) or blob.get("market_trend") not in ("up", "range", "down", "unknown"):
                continue
            if blob.get("market_posture") not in ("risk_on", "neutral", "risk_off"):
                continue
            if blob.get("as_of") is None or date.fromisoformat(blob["as_of"]) > stamp:
                continue
            out.append({"date": blob["as_of"], "trend": blob["market_trend"],
                        "posture": blob["market_posture"]})
            if len(out) >= limit:
                break
        except (OSError, ValueError, TypeError):
            continue
    return out


def compute(mode="standard", years=10):
    gaps = []
    trend, trend_detail, as_of = _trend(gaps)
    vol = _volatility(gaps, expected_as_of=as_of)
    br = _breadth(gaps, expected_as_of=as_of)
    live = market.indices()
    gaps.extend(live.get("gaps") or [])
    val = _valuation(gaps, live, years=years)
    posture, why = classify_posture(trend, vol.get("band"), br.get("pct_sectors_above_ema50"))

    flows_env = market.flows()
    gaps.extend(flows_env.get("gaps") or [])
    macro_env = market.macro()
    gaps.extend(macro_env.get("gaps") or [])

    ctx = {
        "as_of": as_of,
        "generated": str(date.today()),
        "mode": mode,
        "history_years": years,
        "context_version": _CONTEXT_VERSION,
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
        "sectors": _sectors(gaps, live),
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
             f">200DMA (metric denominators: {br.get('counts')}) | sectors >50EMA {br.get('pct_sectors_above_ema50')}%"
             f" | near 52w high {br.get('pct_near_52w_high')}% vs low {br.get('pct_near_52w_low')}%")
    L.append("valuation (level, own-history percentile over "
             f"{(ctx.get('valuation') or {}).get('NIFTY 50', {}).get('history_years', 10)}y):")
    for ix, v in (ctx.get("valuation") or {}).items():
        L.append(f"  {ix}: P/E {v.get('pe')} ({v.get('pe_pctile')}p) | "
                 f"P/B {v.get('pb')} ({v.get('pb_pctile')}p) | "
                 f"DY {v.get('dy')} ({v.get('dy_pctile')}p) -> {v.get('stance')}"
                 f" [{v.get('blended_pctile')}p blended]")
        L.append(f"    history: {v.get('samples')} unique observations / "
                 f"{v.get('requested_samples')} requested, "
                 f"{v.get('first_observation')} to {v.get('last_observation')}")
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


def load_today(years=10):
    """Reuse only a complete artifact produced by this implementation and request."""
    try:
        with open(artifact_path(), encoding="utf-8") as fh:
            ctx = json.load(fh)
        if not isinstance(ctx, dict):
            return None
        if (ctx.get("context_version") != _CONTEXT_VERSION
                or ctx.get("generated") != str(date.today())
                or ctx.get("history_years") != years
                or ctx.get("mode") not in ("quick", "standard", "deep")
                or ctx.get("market_trend") not in ("up", "range", "down", "unknown")
                or ctx.get("market_posture") not in ("risk_on", "neutral", "risk_off")
                or not isinstance(ctx.get("rationale"), str)):
            return None
        if ctx.get("as_of") is not None:
            if date.fromisoformat(ctx["as_of"]) > date.today():
                return None
        if not all(isinstance(ctx.get(key), dict) for key in
                   ("trend_detail", "volatility", "breadth", "valuation", "relative",
                    "flows", "macro", "sectors")):
            return None
        if not isinstance(ctx.get("gaps"), list) or not all(isinstance(g, str) for g in ctx["gaps"]):
            return None
        json.dumps(ctx, allow_nan=False)
        return ctx
    except (OSError, ValueError, TypeError):
        return None


def persist(ctx, out=None):
    """Replace the daily snapshot atomically; a failed write preserves the prior file."""
    out = out or artifact_path()
    body = json.dumps(ctx, indent=2, ensure_ascii=False, allow_nan=False)
    return spine.atomic_write(out, body, fsync=True)


def _resolve_locked(mode, years, fresh, out):
    if mode == "quick" and not fresh:
        ctx = load_today(years=years)
        if ctx is not None:
            if out:
                try:
                    persist(ctx, out)
                except OSError as exc:
                    ctx["gaps"].append(f"market-context output unavailable: {exc}")
            return ctx
    ctx = compute(mode=mode, years=years)
    # Always publish the shared record, even when an additional output was requested.
    for target in dict.fromkeys([artifact_path(), out] if out else [artifact_path()]):
        try:
            persist(ctx, target)
        except OSError as exc:
            ctx["gaps"].append(f"market-context persistence unavailable: {exc}")
    return ctx


def resolve(mode="standard", years=10, fresh=False, out=None):
    """Serialize daily reuse/computation so simultaneous readers share one snapshot."""
    if mode not in ("quick", "standard", "deep"):
        raise ValueError("mode must be quick, standard or deep")
    if type(years) is not int or years <= 0:
        raise ValueError("years must be a positive integer")
    if type(fresh) is not bool:
        raise ValueError("fresh must be a boolean")
    with _CONTEXT_LOCK:
        try:
            lock = open(artifact_path() + ".lock", "a")
            try:
                fcntl.flock(lock, fcntl.LOCK_EX)
            except OSError:
                lock.close()
                raise
        except OSError as exc:
            ctx = _resolve_locked(mode, years, fresh, out)
            ctx["gaps"].append(f"market-context cache lock unavailable: {exc}")
            return ctx
        with lock:
            return _resolve_locked(mode, years, fresh, out)
