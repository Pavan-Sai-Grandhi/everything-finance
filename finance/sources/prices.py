#!/usr/bin/env python3
"""Price fetch — live truth + EOD history + reconcile.

Two truths, kept separate on purpose: live/screening comes from the TradingView scanner,
historical EOD from yfinance. `reconcile()` cross-checks the two latest closes and flags a
gap beyond tolerance — the live≡backtest guard rail.

This module fetches OHLCV and price fields ONLY. Every indicator value is `ta.py`'s job, so
a screen and its backtest cannot disagree about what an indicator means.

Returns the shared data-spine envelope (finance/contracts.md).

Reached through: get_quote, get_history, run_technical_screen.
"""
from __future__ import annotations

import os
from datetime import date

from finance import paths
from finance import transport
from finance.spine import (envelope as _envelope, f as _f, norm_symbol as _norm,
                           read_cache as _read_cache, write_cache as _write_cache)


_TV_SCAN = "https://scanner.tradingview.com/india/scan"

# Order matters: the scanner returns each row's `d` array aligned to this list.
QUOTE_COLUMNS = ["name", "close", "change", "change_abs", "volume", "market_cap_basic"]
SCREEN_COLUMNS = ["name", "close", "change", "volume", "market_cap_basic"]


def _quote_body(symbol, columns):
    """The scanner request body for one NSE symbol."""
    return {
        "symbols": {"tickers": [f"NSE:{_norm(symbol)}"], "query": {"types": []}},
        "columns": list(columns),
    }


def _screen_body(filters, columns, limit=50):
    """The scanner request body for a technical screen over the India market.

    `filters` is either a ready scanner payload ({"filter": [...], "sort": {...}}) or a
    plain list of filter rows ([{left, operation, right}, ...]); both build the same shape.
    """
    if isinstance(filters, dict) and ("filter" in filters or "sort" in filters):
        body = dict(filters)
    else:
        body = {"filter": list(filters or [])}
    body.setdefault("options", {"lang": "en"})
    body["markets"] = ["india"]
    body.setdefault("symbols", {"query": {"types": []}, "tickers": []})
    body["columns"] = list(columns)
    body.setdefault("sort", {"sortBy": "volume", "sortOrder": "desc"})
    body.setdefault("range", [0, int(limit)])
    return body


def _scan_post(body, timeout=20):
    """POST a scanner body. Returns (payload_dict, gap).

    No cookies or auth headers are sent: the public India scanner needs none."""
    payload, gap = transport.json_request(
        _TV_SCAN, payload=body, timeout=timeout,
        origin="https://www.tradingview.com", referer="https://www.tradingview.com/")
    if gap:
        return None, f"TradingView scanner: {gap}"
    return payload, None


def _parse_scan(payload, columns):
    """Turn a scanner response into a list of field dicts.

    The scanner returns {"data": [{"s": "NSE:RELIANCE", "d": [v0, v1, ...]}, ...]} where
    each `d` aligns to the requested `columns`."""
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sym = r.get("s", "") or ""
        vals = r.get("d", []) or []
        rec = {}
        for col, val in zip(columns, vals):
            rec[col] = _f(val) if col != "name" else val
        rec["symbol"] = sym.split(":")[-1] if ":" in sym else sym
        rec["exchange"] = sym.split(":")[0] if ":" in sym else "NSE"
        out.append(rec)
    return out


def quote(symbol, fresh=False):
    """Live quote for one NSE symbol via the TradingView scanner."""
    sym = _norm(symbol)
    cache_file = os.path.join(paths.cache_dir("prices"), f"quote_{sym}.json")
    cached = _read_cache(cache_file, fresh)
    if cached is not None:
        return cached

    payload, gap = _scan_post(_quote_body(sym, QUOTE_COLUMNS))
    if gap:
        return _envelope(False, "TradingView", {"symbol": sym}, [gap])
    rows = _parse_scan(payload, QUOTE_COLUMNS)
    if not rows:
        return _envelope(False, "TradingView", {"symbol": sym},
                         [f"TradingView: no row for NSE:{sym} (symbol unknown/renamed?)"])
    row = rows[0]
    data = {"symbol": sym, "date": date.today().isoformat(), **row}
    env = _envelope(True, "TradingView", data, [])
    _write_cache(cache_file, env)
    return env


def screen(filters, columns=None, limit=50):
    """Run a technical screen over the India market and return a candidate symbol list.
    `filters` is a scanner payload or a list of filter rows."""
    cols = list(columns) if columns else SCREEN_COLUMNS
    payload, gap = _scan_post(_screen_body(filters, cols, limit))
    if gap:
        return _envelope(False, "TradingView", {"filters": filters, "candidates": []}, [gap])
    rows = _parse_scan(payload, cols)
    data = {
        "filters": filters,
        "count": len(rows),
        "candidates": [r["symbol"] for r in rows],
        "rows": rows,
    }
    gaps = [] if rows else ["TradingView screen matched no symbols (filters too tight?)"]
    return _envelope(bool(rows), "TradingView", data, gaps)


def _df_to_candles(df):
    """A yfinance OHLCV frame -> a list of candle dicts.
    Flattens the MultiIndex columns yfinance returns for a single-ticker download."""
    if df is None or len(df) == 0:
        return []
    cols = getattr(df, "columns", None)
    if cols is not None and getattr(cols, "nlevels", 1) > 1:
        df = df.copy()
        df.columns = [c[0] for c in cols]
    out = []
    for idx, row in df.iterrows():
        d = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
        out.append({
            "date": d,
            "open": _f(row.get("Open")),
            "high": _f(row.get("High")),
            "low": _f(row.get("Low")),
            "close": _f(row.get("Close")),
            "volume": _f(row.get("Volume")),
        })
    return out


def _yf_ticker(sym):
    """yfinance market form of a symbol: indices (`^NSEI`, `^CNXIT`) and non-equity
    instruments (FX `INR=X`, futures `GC=F`, already-suffixed `NIFTY_FIN_SERVICE.NS`) pass
    through; a bare NSE equity gets the `.NS` suffix. Keeps the spine usable for equities,
    the indices the regime gate reads, and the cross-asset macro series market.py fetches —
    suffixing those produced `INR=X.NS` and a silent empty series."""
    if sym.startswith("^") or "=" in sym or "." in sym:
        return sym
    return f"{sym}.NS"


def history(symbol, period="1y", fresh=False, adjusted=False):
    """EOD OHLCV history via yfinance — the backtest/reconcile truth.

    `adjusted` toggles split/bonus adjustment: reconcile wants the raw close (default) to
    match the live TV bar; warmup callers want `adjusted=True` to share the backtest's
    adjusted series."""
    sym = _norm(symbol)
    yf_t = _yf_ticker(sym)
    suffix = "_adj" if adjusted else ""
    cache_file = os.path.join(paths.cache_dir("prices"), f"history_{sym}_{period}{suffix}.json")
    cached = _read_cache(cache_file, fresh)
    if cached is not None:
        return cached

    try:
        import yfinance as yf
    except Exception as exc:  # noqa: BLE001
        return _envelope(False, None, {"symbol": sym, "period": period, "candles": []},
                         [f"yfinance unavailable: {exc}"])
    try:
        df = yf.download(yf_t, period=period, interval="1d",
                         progress=False, auto_adjust=adjusted)
    except Exception as exc:  # noqa: BLE001
        return _envelope(False, "yfinance", {"symbol": sym, "period": period, "candles": []},
                         [f"yfinance download failed for {yf_t}: {exc}"])
    candles = _df_to_candles(df)
    # A bar with no close has not settled — yfinance publishes the session's O/H/L
    # before the close is final. It is not a session, and NaN survives every
    # `is not None` filter downstream, so it is dropped here at the source rather
    # than left to become a confident wrong number in someone's arithmetic.
    settled = [c for c in candles
               if isinstance(c.get("close"), (int, float)) and c["close"] == c["close"]]
    dropped = len(candles) - len(settled)
    candles = settled
    # `bars_dropped_unsettled` rather than a gap: nothing that existed was lost, and the
    # series is complete through its last settled session, which `as_of` states.
    data = {"symbol": sym, "period": period, "bars": len(candles), "candles": candles,
            "as_of": candles[-1]["date"] if candles else None,
            "bars_dropped_unsettled": dropped}
    gaps = [] if candles else [f"yfinance returned no bars for {yf_t} (delisted/renamed?)"]
    env = _envelope(bool(candles), "yfinance", data, gaps)
    if candles:
        _write_cache(cache_file, env)
    return env


def history_df(symbol, period="1y", adjusted=True, fresh=False):
    """`history()` as the pandas OHLCV frame `ta.add_indicators` consumes.

    Lets warmup callers (discover screen, trade re-validation, the regime gate) fetch
    through the spine yet keep the indicator-of-record in `ta.py`. `adjusted=True` keeps
    them on the backtest's series so live≡backtest holds. Returns (frame_or_None, gaps)."""
    import pandas as pd
    env = history(symbol, period=period, adjusted=adjusted, fresh=fresh)
    candles = env.get("data", {}).get("candles", [])
    if not candles:
        return None, env.get("gaps", [])
    df = pd.DataFrame(candles)
    df.index = pd.to_datetime(df.pop("date"))
    df = df.rename(columns={"open": "Open", "high": "High", "low": "Low",
                            "close": "Close", "volume": "Volume"})
    return df[["Open", "High", "Low", "Close", "Volume"]], env.get("gaps", [])


def _diverges(tv_close, yf_close, tolerance):
    """(diverged, pct) for two closes. `diverged` is None when a close is missing,
    True when |Δ|/yf > tolerance, else False."""
    tv, yf = _f(tv_close), _f(yf_close)
    if tv is None or not yf:
        return None, None
    pct = abs(tv - yf) / abs(yf)
    return pct > tolerance, pct


def reconcile(symbol, tolerance=0.01):
    """Cross-check the latest live (TradingView) close against the latest yfinance close.
    Flags a gap and returns ok:false when they diverge beyond `tolerance`."""
    sym = _norm(symbol)
    q = quote(sym)
    h = history(sym, period="5d")
    tv_close = (q.get("data") or {}).get("close")
    candles = (h.get("data") or {}).get("candles") or []
    yf_close = candles[-1]["close"] if candles else None
    gaps = list(q.get("gaps") or []) + list(h.get("gaps") or [])

    diverged, pct = _diverges(tv_close, yf_close, tolerance)
    if diverged is None:
        gaps.append("reconcile: missing a close from one source — cannot cross-check")
        ok = False
    elif diverged:
        gaps.append(f"reconcile: TV {tv_close} vs yfinance {yf_close} "
                    f"diverge {pct:.2%} > {tolerance:.0%} tolerance")
        ok = False
    else:
        ok = True
    data = {
        "symbol": sym,
        "tv_close": _f(tv_close),
        "yf_close": _f(yf_close),
        "divergence_pct": round(pct, 4) if pct is not None else None,
        "tolerance": tolerance,
        "agree": bool(ok),
    }
    return _envelope(ok, "TradingView+yfinance", data, gaps)
