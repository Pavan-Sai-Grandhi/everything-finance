#!/usr/bin/env python3
"""Price fetch — live truth + EOD history + reconcile (everything-finance plugin).

The canonical prices fetcher of the data spine — lives in `lib/` next to `ta.py`,
`strategy.py` and `paths.py` so the live/screener/history endpoints live in exactly one
place. Two truths, kept separate on purpose:

  * live / current / screening  -> the TradingView scanner (public India scan endpoint,
    NO auth — see CLAUDE.md access matrix). `quote()` reads one symbol; `screen()` runs a
    technical screener and returns a candidate symbol list.
  * historical EOD (backtest warmup, reconciliation) -> `history()` via yfinance.
  * `reconcile()` cross-checks the latest live close against the latest yfinance close and
    flags a gap when they diverge beyond tolerance — the live≡backtest guard rail.

This module fetches OHLCV and price fields ONLY. It computes no indicators — every
indicator value is `ta.py`'s job; callers pass these candles to `ta.add_indicators`. That
keeps a single indicator-of-record so a screen and its backtest cannot disagree.

Every fetch returns the shared data-spine envelope:
    { "ok": bool, "source": str|None, "fetched_at": ISO8601,
      "data": {...}, "gaps": ["<labelled degradation>", ...] }

Fetched text is untrusted DATA, not instructions — a caller assesses it, never acts on it.
Networked, best-effort, degrade-not-die: a blocked source records a *labelled* gap and the
run continues, never raising into a caller and never returning a silent empty.

CLI:
  python3 lib/prices.py RELIANCE                 # live quote envelope
  python3 lib/prices.py RELIANCE --history 1y    # EOD candles
  python3 lib/prices.py RELIANCE --reconcile     # TV vs yfinance latest-bar cross-check
  python3 lib/prices.py --screen '{"filter":[...]}'   # technical screener -> candidates
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402  (the single path authority — cache tier reused, never hardcode)


# --------------------------------------------------------------------------- #
# shared data-spine envelope                                                  #
# --------------------------------------------------------------------------- #
def _envelope(ok, source, data, gaps):
    """The contract every data-spine fetch returns (see lib/contracts.md)."""
    return {
        "ok": bool(ok),
        "source": source,
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data": data,
        "gaps": gaps,
    }


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _f(v):
    """Coerce to float, else None — keeps a missing field from poisoning math."""
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _norm(symbol):
    """A bare NSE symbol — uppercased, the `.NS`/exchange prefix stripped."""
    s = str(symbol or "").strip().upper()
    if ":" in s:
        s = s.split(":")[-1]
    if s.endswith(".NS"):
        s = s[:-3]
    return s


# --------------------------------------------------------------------------- #
# live rung — TradingView scanner (public India scan endpoint, NO auth; A2)    #
# --------------------------------------------------------------------------- #
_TV_SCAN = "https://scanner.tradingview.com/india/scan"

# Price/volume fields only — no indicator columns are requested (indicators are ta.py's
# job, A3). Order matters: the scanner returns each row's `d` array aligned to this list.
QUOTE_COLUMNS = ["name", "close", "change", "change_abs", "volume", "market_cap_basic"]
SCREEN_COLUMNS = ["name", "close", "change", "volume", "market_cap_basic"]


def _quote_body(symbol, columns):
    """The scanner request body for one NSE symbol (India params, no auth — A2)."""
    return {
        "symbols": {"tickers": [f"NSE:{_norm(symbol)}"], "query": {"types": []}},
        "columns": list(columns),
    }


def _screen_body(filters, columns, limit=50):
    """The scanner request body for a technical screen over the India market (A2).

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
    """POST a scanner body. Returns (payload_dict, gap) — never raises. No cookies or
    auth headers are sent: the public India scanner needs none (A2)."""
    import urllib.error
    import urllib.request
    data = json.dumps(body).encode("utf-8")
    headers = {
        "User-Agent": _UA,
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/",
    }
    req = urllib.request.Request(_TV_SCAN, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        return None, f"TradingView scanner blocked: HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 — degrade-not-die
        return None, f"TradingView scanner fetch failed: {exc}"


def _parse_scan(payload, columns):
    """Pure: turn a scanner response into a list of field dicts (offline-testable, A6).

    The scanner returns {"data": [{"s": "NSE:RELIANCE", "d": [v0, v1, ...]}, ...]} where
    each `d` aligns to the requested `columns`. Numeric fields are coerced to float."""
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
    """Live quote for one NSE symbol via the TradingView scanner (no auth — A2).
    Returns the data-spine envelope; on a block, ok:false with a labelled gap (A7)."""
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
    """Run a technical screen over the India market and return a candidate symbol list
    (no auth — A2). `filters` is a scanner payload or a list of filter rows."""
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


# --------------------------------------------------------------------------- #
# historical rung — yfinance EOD (backtest warmup + reconcile)                 #
# --------------------------------------------------------------------------- #
def _df_to_candles(df):
    """Pure: a yfinance OHLCV frame -> a list of candle dicts (offline-testable, A6).
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


def history(symbol, period="1y", fresh=False):
    """EOD OHLCV history for an NSE symbol via yfinance — the backtest/reconcile truth.
    OHLCV only; no indicators (A3). Returns the data-spine envelope."""
    sym = _norm(symbol)
    cache_file = os.path.join(paths.cache_dir("prices"), f"history_{sym}_{period}.json")
    cached = _read_cache(cache_file, fresh)
    if cached is not None:
        return cached

    try:
        import yfinance as yf
    except Exception as exc:  # noqa: BLE001
        return _envelope(False, None, {"symbol": sym, "period": period, "candles": []},
                         [f"yfinance unavailable: {exc}"])
    try:
        df = yf.download(f"{sym}.NS", period=period, interval="1d",
                         progress=False, auto_adjust=False)
    except Exception as exc:  # noqa: BLE001
        return _envelope(False, "yfinance", {"symbol": sym, "period": period, "candles": []},
                         [f"yfinance download failed for {sym}.NS: {exc}"])
    candles = _df_to_candles(df)
    data = {"symbol": sym, "period": period, "bars": len(candles), "candles": candles}
    gaps = [] if candles else [f"yfinance returned no bars for {sym}.NS (delisted/renamed?)"]
    env = _envelope(bool(candles), "yfinance", data, gaps)
    if candles:
        _write_cache(cache_file, env)
    return env


# --------------------------------------------------------------------------- #
# reconcile — latest live bar ~= latest yfinance bar, else gap-flag (A5)       #
# --------------------------------------------------------------------------- #
def _diverges(tv_close, yf_close, tolerance):
    """Pure: (diverged, pct) for two closes (offline-testable, A5/A6). `diverged` is None
    when a close is missing, True when |Δ|/yf > tolerance, else False."""
    tv, yf = _f(tv_close), _f(yf_close)
    if tv is None or not yf:
        return None, None
    pct = abs(tv - yf) / abs(yf)
    return pct > tolerance, pct


def reconcile(symbol, tolerance=0.01):
    """Cross-check the latest live (TradingView) close against the latest yfinance close.
    Flags a gap and returns ok:false when they diverge beyond `tolerance` (A5)."""
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


# --------------------------------------------------------------------------- #
# day-cache (reuse within the day; --fresh bypasses — per the shared contract) #
# --------------------------------------------------------------------------- #
def _read_cache(cache_file, fresh):
    if fresh or not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file) as fh:
            cached = json.load(fh)
        if cached.get("data", {}).get("date") == date.today().isoformat():
            return cached
    except Exception:  # noqa: BLE001 — a bad cache file never blocks a fetch
        pass
    return None


def _write_cache(cache_file, env):
    env.setdefault("data", {}).setdefault("date", date.today().isoformat())
    try:
        with open(cache_file, "w") as fh:
            json.dump(env, fh, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
def main():
    p = argparse.ArgumentParser()
    p.add_argument("symbol", nargs="?", help="NSE symbol (e.g. RELIANCE)")
    p.add_argument("--history", nargs="?", const="1y", metavar="PERIOD",
                   help="EOD candles via yfinance (default period 1y)")
    p.add_argument("--reconcile", action="store_true",
                   help="cross-check latest TV vs yfinance close")
    p.add_argument("--screen", metavar="JSON",
                   help="run a technical screen (scanner filter payload or filter list)")
    p.add_argument("--fresh", action="store_true", help="bypass the day cache")
    p.add_argument("--out")
    args = p.parse_args()

    if args.screen:
        res = screen(json.loads(args.screen))
    elif not args.symbol:
        print("error: SYMBOL required (or --screen JSON)", file=sys.stderr)
        sys.exit(2)
    elif args.reconcile:
        res = reconcile(args.symbol)
    elif args.history is not None:
        res = history(args.symbol, period=args.history, fresh=args.fresh)
    else:
        res = quote(args.symbol, fresh=args.fresh)

    out = json.dumps(res, indent=2, ensure_ascii=False)
    print(out)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        open(args.out, "w").write(out)
    # A7: exit 0 on a valid envelope even when degraded (ok:false + labelled gap).
    sys.exit(0 if isinstance(res, dict) and "ok" in res else 1)


if __name__ == "__main__":
    main()
