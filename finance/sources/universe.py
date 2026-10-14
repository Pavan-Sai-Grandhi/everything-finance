#!/usr/bin/env python3
"""The universe authority — resolve a named universe to its NSE symbols.

One place decides what `nifty500`, `microcap`, `fno`, `largecap20`, a `[list]`, a
comma-string or a file path mean, so every screener (`compute/screen.py`,
`compute/stock_scan.py`, `compute/backtest.py`, `compute/sector_scan.py`) draws its
universe from the same definition instead of each carrying its own resolver.

Named universes come from NSE's published constituent CSVs, fetched only through
`finance/transport.py`. The symbol LIST is written to a dated file under
`cache_dir('universe')` and never returned inline — the same rule holdings, NAV series
and candles follow. A failed fetch falls back to the newest cached copy with a labelled
gap; with no cache it is a gap, never a fabricated list.

Reached through: get_universe.
"""
from __future__ import annotations

import csv
import glob
import io
import os
import hashlib
from datetime import date

from finance import paths
from finance import transport
from finance.spine import envelope as _envelope, norm_symbol as _norm

# Named index universes → the NSE constituent CSV filename. All share the column layout
# `Company Name,Industry,Symbol,Series,ISIN Code`, so one parser serves them.
_INDEX_CSV = "https://nsearchives.nseindia.com/content/indices/{fname}"
_INDEX_FILES = {
    "nifty50": "ind_nifty50list.csv",
    "nifty100": "ind_nifty100list.csv",
    "nifty200": "ind_nifty200list.csv",
    "nifty500": "ind_nifty500list.csv",
    "microcap": "ind_niftymicrocap250_list.csv",
}

# The F&O security list has its own padded layout (`UNDERLYING, SYMBOL, <month lots>…`);
# the index underlyings in it are not tradeable equities and are dropped.
_FNO_CSV = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"
_FNO_NON_STOCK = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50",
                  "NIFTYINFRA", "NIFTYIT"}

# 20 liquid large-caps — NOT the full Nifty 50; reports must call it a 20-stock basket.
LARGECAP20_BASKET = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "BHARTIARTL", "SBIN",
    "LT", "ITC", "HINDUNILVR", "MARUTI", "M&M", "SUNPHARMA", "TITAN",
    "BAJFINANCE", "AXISBANK", "KOTAKBANK", "ASIANPAINT", "TATASTEEL", "NTPC",
]

NAMED = tuple(_INDEX_FILES) + ("fno", "largecap20")


def _referer():
    return "https://www.nseindia.com/"


def _parse_index_csv(text):
    """A constituent CSV → its NSE symbols, in file order."""
    out = []
    for row in csv.DictReader(io.StringIO(text or "")):
        sym = _norm(row.get("Symbol"))
        if sym:
            out.append(sym)
    return out


def _parse_fno_csv(text):
    """The F&O lot-size CSV → the equity underlyings, index underlyings dropped.
    Cells are space-padded, so every value is stripped before use."""
    out = []
    for row in csv.reader(io.StringIO(text or "")):
        if len(row) < 2:
            continue
        sym = _norm(row[1])
        if not sym or sym == "SYMBOL" or sym in _FNO_NON_STOCK:
            continue
        out.append(sym)
    return out


def _fetch_named(key):
    """`(symbols, gap)` for a named universe fetched from NSE."""
    if key == "largecap20":
        return list(LARGECAP20_BASKET), None
    if key == "fno":
        body, gap = transport.request(_FNO_CSV, referer=_referer(), timeout=25)
        return (_parse_fno_csv(body), None) if not gap else ([], gap)
    body, gap = transport.request(_INDEX_CSV.format(fname=_INDEX_FILES[key]),
                                  referer=_referer(), timeout=25)
    return (_parse_index_csv(body), None) if not gap else ([], gap)


def _cache_path(key, day=None):
    day = day or date.today().isoformat()
    return os.path.join(paths.cache_dir("universe"), f"{key}-{day}.txt")


def _newest_cached(key):
    """Path to the most recent cached list for `key`, or None."""
    hits = sorted(glob.glob(os.path.join(paths.cache_dir("universe"), f"{key}-*.txt")))
    return hits[-1] if hits else None


def _write_list(path, symbols):
    with open(path, "w") as fh:
        fh.write("\n".join(symbols) + "\n")


def _local_symbols(name):
    """A list, comma-string or file path → its symbols. None for a named-universe token."""
    if isinstance(name, (list, tuple)):
        rows = list(name)
    elif isinstance(name, str):
        if name.strip().lower() in NAMED:
            return None
        rows = (open(name).read().splitlines() if os.path.exists(name)
                else name.split(","))
    else:
        rows = []
    return [_norm(s) for s in rows if str(s).strip()]


def resolve_symbols(name, fresh=False):
    """`(symbols, gaps)` — the pure list resolver every screener delegates to.

    Named universes (`nifty50/100/200/500`, `microcap`, `fno`, `largecap20`) come from
    NSE, cached dated, with a stale-cache fallback on a failed fetch. A list, comma-string
    or file path is resolved locally.
    """
    local = _local_symbols(name)
    if local is not None:
        return local, []

    key = name.strip().lower()
    if not fresh and os.path.exists(_cache_path(key)):
        return open(_cache_path(key)).read().split(), []

    symbols, gap = _fetch_named(key)
    if symbols:
        _write_list(_cache_path(key), symbols)
        return symbols, []

    stale = _newest_cached(key)
    if stale:
        return (open(stale).read().split(),
                [f"{key} constituents: fetch failed ({gap}); using cached "
                 f"{os.path.basename(stale)}"])
    return [], [f"{key} constituents: {gap or 'no data'}, and no cached copy"]


def _key_for(name):
    """A filesystem-safe key for the on-disk list name."""
    if isinstance(name, str) and name.strip().lower() in NAMED:
        return name.strip().lower()
    return "custom"


def resolve(name, fresh=False):
    """Resolve a universe to its NSE symbols in the spine envelope.

    The symbol list is written to `cache_dir('universe')/<name>-<date>.txt` (one symbol
    per line) and NEVER returned inline; `data` carries the count and the path.
    """
    symbols, gaps = resolve_symbols(name, fresh=fresh)
    key = _key_for(name)
    if key == "custom":
        digest = hashlib.sha256("\n".join(symbols).encode()).hexdigest()[:16]
        path = _cache_path(f"custom-{digest}")
    else:
        # A failed refresh returns the original snapshot. Do not copy it into today's
        # file, or the list would look newer than it is.
        path = _newest_cached(key) if gaps else _cache_path(key)
    if symbols and key == "custom":
        _write_list(path, symbols)
    data = {"name": key, "symbols_count": len(symbols),
            "universe_path": path if symbols else None,
            "as_of": os.path.basename(path)[-14:-4] if symbols and path else None}
    return _envelope(bool(symbols), "NSE", data,
                     gaps + ([] if symbols else [f"universe {key!r} resolved to no symbols"]))
