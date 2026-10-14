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
import hashlib
import json
import math
from datetime import date

from finance import paths
from finance import transport
from finance.spine import (envelope as _envelope, f as _f, norm_symbol as _norm,
                           read_cache as _read_cache, write_cache as _write_cache)


_TV_SCAN = "https://scanner.tradingview.com/india/scan"

# Order matters: the scanner returns each row's `d` array aligned to this list.
QUOTE_COLUMNS = ["name", "close", "change", "change_abs", "volume", "market_cap_basic"]
SCREEN_COLUMNS = ["name", "close", "change", "volume", "market_cap_basic"]


def _cache_path(kind, *identity):
    # Symbols and periods are untrusted identifiers, never filesystem components.
    key = hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()
    return os.path.join(paths.cache_dir("prices"), f"{kind}_{key}.json")


def _valid_quote(row, symbol):
    return (isinstance(row, dict) and row.get("symbol") == symbol
            and row.get("exchange") == "NSE"
            and _f(row.get("close")) is not None and _f(row["close"]) > 0)


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
    if type(limit) is not int or limit <= 0:
        raise ValueError("limit must be a positive integer")
    if not isinstance(columns, list) or not columns or any(not isinstance(col,str) or not col.strip() for col in columns) or len(set(columns)) != len(columns):
        raise ValueError("columns must be a nonempty list of distinct field names")
    if filters is not None and not isinstance(filters, (dict,list)):
        raise ValueError("filters must be a list or scanner payload mapping")
    if isinstance(filters, dict):
        body = dict(filters)
    else:
        body = {"filter": list(filters or [])}
    body.setdefault("filter", [])
    if not isinstance(body["filter"], list) or any(not isinstance(row,dict) for row in body["filter"]):
        raise ValueError("filter must be a list of scanner filter mappings")
    body["filter"] = [*body["filter"], {"left":"exchange", "operation":"equal", "right":"NSE"}]
    body.setdefault("options", {"lang": "en"})
    body["markets"] = ["india"]
    body.setdefault("symbols", {"query": {"types": []}, "tickers": []})
    body["columns"] = list(columns)
    body.setdefault("sort", {"sortBy": "volume", "sortOrder": "desc"})
    body["range"] = [0, limit]
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
    if not isinstance(rows, list):
        return out
    for r in rows:
        if not isinstance(r, dict):
            continue
        sym = r.get("s", "") or ""
        vals = r.get("d", [])
        if (not isinstance(sym, str) or sym.count(":") != 1
                or not all(sym.split(":")) or not isinstance(vals, list)
                or len(vals) != len(columns)):
            continue
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
    cache_file = _cache_path("quote", sym)
    cached = _read_cache(cache_file, fresh)
    if (isinstance(cached, dict) and cached.get("ok") is True
            and cached.get("source") == "TradingView"
            and _valid_quote(cached.get("data"), sym)):
        return cached

    payload, gap = _scan_post(_quote_body(sym, QUOTE_COLUMNS))
    if gap:
        return _envelope(False, "TradingView", {"symbol": sym}, [gap])
    parsed = _parse_scan(payload, QUOTE_COLUMNS)
    rows = [row for row in parsed if row.get("symbol") == sym and row.get("exchange") == "NSE"]
    if len(rows) != 1 or not _valid_quote(rows[0], sym):
        return _envelope(False, "TradingView", {"symbol": sym},
                         [f"TradingView: expected one usable quote for NSE:{sym}; missing, invalid or ambiguous response"])
    row = rows[0]
    data = {"symbol": sym, "date": date.today().isoformat(), **row}
    env = _envelope(True, "TradingView", data, [])
    _write_cache(cache_file, env)
    return env


def screen(filters, columns=None, limit=50):
    """Run a technical screen over the India market and return a candidate symbol list.
    `filters` is a scanner payload or a list of filter rows."""
    failure = {"filters":filters, "count":0, "candidates":[], "rows":[]}
    try:
        cols = SCREEN_COLUMNS if columns is None else columns
        body = _screen_body(filters, cols, limit)
    except (ValueError, TypeError) as exc:
        return _envelope(False, "TradingView", failure, [f"invalid screen inputs: {exc}"])
    payload, gap = _scan_post(body)
    if gap:
        return _envelope(False, "TradingView", failure, [gap])
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return _envelope(False, "TradingView", failure, ["TradingView: malformed screen response (missing data list)"])
    parsed = _parse_scan(payload, cols)
    gaps = []
    if len(parsed) != len(payload["data"]):
        gaps.append("TradingView: malformed screen rows excluded; results are incomplete")
    rows, seen = [], set()
    for row in parsed:
        if row["exchange"] != "NSE" or ("close" in cols and not _valid_quote(row,row["symbol"])):
            gaps.append("TradingView: non-NSE or unusable price row excluded")
            continue
        if row["symbol"] in seen:
            gaps.append(f"TradingView: duplicate screen symbol {row['symbol']} excluded")
            continue
        seen.add(row["symbol"])
        rows.append(row)
    if len(rows) > limit:
        gaps.append("TradingView: response exceeded requested limit; truncated locally")
        rows = rows[:limit]
    data = {"filters": filters, "count": len(rows),
            "candidates": [r["symbol"] for r in rows], "rows": rows}
    if not rows:
        gaps.append("TradingView screen returned no usable NSE matches")
    return _envelope(bool(rows), "TradingView", data, list(dict.fromkeys(gaps)))


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


def _validate_candles(rows):
    """Validate source/cache OHLCV without inventing prices or choosing duplicates."""
    if not isinstance(rows, list):
        raise ValueError("candles must be a list")
    dated, seen = {}, set()
    invalid = 0
    today = date.today().isoformat()
    for row in rows:
        try:
            day = row["date"]
            if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day or day > today:
                raise ValueError("invalid/future candle date")
            if day in seen:
                if day in dated:
                    dated.pop(day)
                    invalid += 1
                raise ValueError("duplicate candle date")
            seen.add(day)
            values = {key: _f(row.get(key)) for key in ("open","high","low","close","volume")}
            if any(value is None for value in values.values()):
                raise ValueError("missing OHLCV")
            if any(values[key] <= 0 for key in ("open","high","low","close")) or values["volume"] < 0:
                raise ValueError("nonpositive price or negative volume")
            if not values["low"] <= min(values["open"],values["close"]) <= max(values["open"],values["close"]) <= values["high"]:
                raise ValueError("inconsistent OHLC range")
            dated[day] = {"date":day, **values}
        except (ValueError, TypeError, KeyError, AttributeError):
            invalid += 1
    candles = [dated[day] for day in sorted(dated)]
    gaps = [f"yfinance: excluded {invalid} invalid or ambiguous OHLCV rows; history is incomplete"] if invalid else []
    return candles, invalid, gaps


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
    cache_file = _cache_path("history", sym, period, adjusted)
    cached = _read_cache(cache_file, fresh)
    if isinstance(cached, dict) and cached.get("ok") is True and cached.get("source") == "yfinance":
        data = cached.get("data")
        if (isinstance(data, dict) and data.get("symbol") == sym and data.get("period") == period
                and data.get("adjusted") is adjusted):
            try:
                candles, invalid, _ = _validate_candles(data.get("candles"))
                if candles and not invalid and candles == data["candles"] and data.get("bars") == len(candles) and data.get("as_of") == candles[-1]["date"]:
                    return cached
            except (ValueError, TypeError):
                pass

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
    try:
        candles, dropped, gaps = _validate_candles(_df_to_candles(df))
    except (ValueError, TypeError, AttributeError) as exc:
        return _envelope(False, "yfinance", {"symbol":sym, "period":period, "candles":[]},
                         [f"yfinance malformed OHLCV response: {exc}"])
    data = {"symbol": sym, "period": period, "adjusted": adjusted,
            "bars": len(candles), "candles": candles,
            "as_of": candles[-1]["date"] if candles else None,
            "bars_dropped_invalid": dropped}
    if candles and candles[-1]["date"] == date.today().isoformat():
        gaps.append("yfinance: latest daily bar is dated today; session completion is not verified")
    if not candles:
        gaps.append(f"yfinance returned no usable bars for {yf_t}")
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


def close_history(sym, fresh=False, period="2y"):
    """Default close-series loader — 2y adjusted EOD via the data spine, enough for a
    12-month lookback. Retains source provenance and validates dated closes."""
    env = history(sym, period=period, adjusted=True, fresh=fresh)
    rows = (env.get("data") or {}).get("candles") or []
    gaps = list(env.get("gaps") or [])
    dated = {}
    try:
        if env.get("ok") is not True:
            raise ValueError("price source did not succeed")
        for row in rows:
            day = date.fromisoformat(row["date"]).isoformat()
            close = row["close"]
            if day in dated or day > date.today().isoformat():
                raise ValueError("duplicate or future candle date")
            if isinstance(close, bool) or not isinstance(close, (int,float)) or not math.isfinite(close) or close <= 0:
                raise ValueError("unusable close price")
            dated[day] = close
    except (ValueError, TypeError, KeyError) as exc:
        return {"closes": [], "dates": [], "gaps": gaps + [str(exc)]}
    dates = sorted(dated)
    return {"closes": [dated[day] for day in dates], "dates": dates, "gaps": gaps,
            "source": env.get("source"), "fetched_at": env.get("fetched_at")}
