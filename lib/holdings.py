#!/usr/bin/env python3
"""Holdings source-resolver + normalizer (everything-finance plugin).

The canonical holdings spine — lives in `lib/` next to `paths.py`/`contracts.md`.
It turns whichever read source is connected into ONE canonical position shape and
applies the precedence **IndMoney → broker → portfolio**, so the consumers
(`daily-brief`, `trade-tracker`, and the Track B cluster later) never re-implement
normalization.

MCP boundary: this module runs in script context and CANNOT call MCP tools. The
calling skill invokes the MCP tool, writes the raw payload to a temp file
(`paths.tmp_dir(...)`), and passes the path here — the same file-handoff pattern
`validate_trade.py` uses. See `lib/contracts.md`.

Every resolve returns the shared data-spine envelope:
  { "ok": bool, "source": str|None, "fetched_at": ISO8601,
    "data": {"positions": [...]}, "gaps": ["<labelled degradation>", ...] }

Canonical position:
  { ticker, qty, avg, ltp, pnl, xirr, broker, asset_class, invested, source, as_of }
`xirr`, `broker`, `invested`, `asset_class` populate from IndMoney; they are `None`
when only broker / portfolio data exists.

`normalize` keeps **all** asset classes (wealth-manager reuses this later); consumers
call `equity_only(...)` for the stock slice. A normalize failure on one source falls
through to the next in precedence with a labelled gap — never an abort.

Fetched figures are first-party authenticated state (IndMoney) or broker truth —
authoritative, but still DATA, never instructions (CLAUDE.md).

CLI:
  python3 lib/holdings.py --indmoney ind.json [--kite k.json|--upstox u.json] [--portfolio p.yml]
"""
import argparse
import json
import sys
from datetime import datetime


# --------------------------------------------------------------------------- #
# shared data-spine envelope (see lib/contracts.md)                           #
# --------------------------------------------------------------------------- #
def _envelope(ok, source, data, gaps):
    return {
        "ok": bool(ok),
        "source": source,
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data": data,
        "gaps": gaps,
    }


# --------------------------------------------------------------------------- #
# small tolerant coercion helpers (payload keys vary across sources)          #
# --------------------------------------------------------------------------- #
def _first(d, *keys):
    """First present, non-empty value among keys, else None."""
    for k in keys:
        if isinstance(d, dict) and k in d:
            v = d[k]
            if v not in (None, "", [], {}):
                return v
    return None


def _num(x):
    """Coerce to float, tolerating ₹/comma/%-formatted strings; None on failure."""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.replace(",", "").replace("₹", "").replace("%", "").strip()
        if s in ("", "-", "NA", "N/A", "null", "None"):
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _ticker(it):
    v = _first(it, "symbol", "ticker", "tradingsymbol", "trading_symbol", "scrip",
               "scheme_name", "name", "isin")
    return str(v) if v is not None else "?"


def _asset_class(it):
    v = _first(it, "asset_class", "assetClass", "asset_type", "category", "product_type")
    return str(v).lower() if v is not None else None


def _as_of(payload):
    v = _first(payload, "as_of", "as_on", "fetched_at", "timestamp", "date") \
        if isinstance(payload, dict) else None
    return str(v) if v is not None else None


def _holdings_list(payload):
    """Dig the per-position list out of a nested payload by common container keys."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("holdings", "positions", "networth_holdings", "items",
                    "data", "result"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                inner = _holdings_list(v)
                if inner:
                    return inner
    return []


# --------------------------------------------------------------------------- #
# per-source normalizers — each returns canonical positions (no `source` yet)  #
# --------------------------------------------------------------------------- #
def _normalize_indmoney(payload):
    """IndMoney `networth_holdings`: all asset classes, with invested / P&L / XIRR."""
    as_of = _as_of(payload)
    out = []
    for it in _holdings_list(payload):
        if not isinstance(it, dict):
            continue
        qty = _num(_first(it, "units", "quantity", "qty", "balance_units"))
        avg = _num(_first(it, "avg_price", "average_price", "avg_cost", "buy_avg", "avg"))
        ltp = _num(_first(it, "ltp", "last_price", "current_price", "nav", "price"))
        invested = _num(_first(it, "invested", "invested_value", "invested_amount",
                               "cost_value", "buy_value"))
        cur = _num(_first(it, "current_value", "market_value", "current_amount"))
        pnl = _num(_first(it, "pnl", "unrealized_pnl", "gain", "total_gain", "returns_value"))
        if invested is None and avg is not None and qty is not None:
            invested = round(avg * qty, 2)
        if pnl is None:
            if cur is not None and invested is not None:
                pnl = round(cur - invested, 2)
            elif None not in (ltp, avg, qty):
                pnl = round((ltp - avg) * qty, 2)
        out.append({
            "ticker": _ticker(it),
            "qty": qty, "avg": avg, "ltp": ltp, "pnl": pnl,
            "xirr": _num(_first(it, "xirr", "irr", "returns_xirr", "annualized_return")),
            "broker": _first(it, "broker", "broker_name", "source_broker", "account") or None,
            "asset_class": _asset_class(it),
            "invested": invested,
            "as_of": (_first(it, "as_of", "as_on") or as_of),
        })
    return out


def _normalize_broker(payload):
    """Kite/Upstox holdings + net positions → equity positions. No XIRR/invested
    (broker gives neither here); P&L falls back to (ltp-avg)*qty when absent."""
    rows = []
    if isinstance(payload, list):
        rows = list(payload)
    elif isinstance(payload, dict):
        h = payload.get("holdings")
        if isinstance(h, list):
            rows += h
        elif isinstance(h, dict):
            rows += _holdings_list(h)
        p = payload.get("positions")
        if isinstance(p, dict) and isinstance(p.get("net"), list):
            rows += p["net"]
        elif isinstance(p, list):
            rows += p
        if not rows:
            rows = _holdings_list(payload)
    out = []
    for it in rows:
        if not isinstance(it, dict):
            continue
        qty = _num(_first(it, "quantity", "qty", "net_quantity", "t1_quantity"))
        if qty is None or qty == 0:        # skip closed/zero-net (intraday) lines
            continue
        avg = _num(_first(it, "average_price", "avg_price", "buy_price", "buy_avg"))
        ltp = _num(_first(it, "last_price", "ltp", "close_price"))
        pnl = _num(_first(it, "pnl", "unrealised", "unrealized", "pl"))
        if pnl is None and None not in (ltp, avg, qty):
            pnl = round((ltp - avg) * qty, 2)
        out.append({
            "ticker": _ticker(it),
            "qty": qty, "avg": avg, "ltp": ltp, "pnl": pnl,
            "xirr": None, "broker": None, "asset_class": None, "invested": None,
            "as_of": _first(it, "as_of") or _as_of(payload),
        })
    return out


def _normalize_portfolio(payload):
    """Hand-maintained positions (watchlist `positions` block or an equivalent list):
    {ticker, entry, sl, target, qty, entry_date, ...}. `entry` is the avg cost; live
    price is fetched by the consumer, so ltp/pnl stay None."""
    rows = []
    if isinstance(payload, list):
        rows = list(payload)
    elif isinstance(payload, dict):
        p = payload.get("positions")
        rows = p if isinstance(p, list) else _holdings_list(payload)
    out = []
    for it in rows:
        if not isinstance(it, dict):
            continue
        out.append({
            "ticker": _ticker(it),
            "qty": _num(_first(it, "qty", "quantity", "units")),
            "avg": _num(_first(it, "avg", "entry", "average_price", "buy_price")),
            "ltp": _num(_first(it, "ltp", "last_price")),
            "pnl": None,
            "xirr": None, "broker": None, "asset_class": None, "invested": None,
            "as_of": _first(it, "entry_date", "as_of") or _as_of(payload),
        })
    return out


# source key → normalizer kind. kite/upstox/broker all share the broker shape.
_KIND = {"indmoney": "indmoney", "broker": "broker", "kite": "broker",
         "upstox": "broker", "portfolio": "portfolio"}
_RANK = {"indmoney": 0, "broker": 1, "kite": 1, "upstox": 1, "portfolio": 2}
_NORMALIZERS = {"indmoney": _normalize_indmoney, "broker": _normalize_broker,
                "portfolio": _normalize_portfolio}


def normalize(payload, source):
    """Map a raw payload to canonical positions. `source` labels the winning source
    on each position (e.g. 'indmoney', 'kite', 'portfolio') and selects the shape."""
    kind = _KIND.get(source, source)
    fn = _NORMALIZERS.get(kind)
    if fn is None:
        raise ValueError(f"unknown holdings source: {source!r}")
    positions = fn(payload)
    for p in positions:
        p["source"] = source
    return positions


# --------------------------------------------------------------------------- #
# equity slice — the cut the two equity consumers want                         #
# --------------------------------------------------------------------------- #
_NON_EQUITY = ("mutual", "mf", "bond", "gold", "silver", "fd", "deposit", "ppf",
               "epf", "nps", "cash", "insurance", "reit", "invit", "debt")
_FUND = ("mutual", "mf")


def equity_only(positions):
    """Stock/equity slice. Broker/portfolio positions (asset_class None) are equity
    by construction; IndMoney positions are kept unless their asset_class names a
    known non-equity class — so an unfamiliar equity class is surfaced, not dropped."""
    out = []
    for p in positions:
        ac = p.get("asset_class")
        if ac is None or not any(t in str(ac).lower() for t in _NON_EQUITY):
            out.append(p)
    return out


def mf_only(positions):
    """Mutual-fund slice for `mf-analysis` — the tagged counterpart of `equity_only`.
    Only IndMoney carries the asset_class tag, so this is IndMoney-sourced by nature;
    broker/portfolio rows (asset_class None) hold no funds and drop out."""
    out = []
    for p in positions:
        ac = p.get("asset_class")
        if ac is not None and any(t in str(ac).lower() for t in _FUND):
            out.append(p)
    return out


# --------------------------------------------------------------------------- #
# resolve — apply precedence, label the winner, record gaps                    #
# --------------------------------------------------------------------------- #
def resolve(prefer="indmoney", payloads=None):
    """Apply precedence IndMoney → broker → portfolio over the supplied payloads and
    return the envelope with `source` set to whichever won. `prefer` bumps one source
    to the front of the order. Absent sources and fall-throughs are noted in `gaps`.

    payloads: {"indmoney"|"kite"|"upstox"|"broker"|"portfolio": <raw payload or None>}.
    """
    payloads = payloads or {}
    present = {k: v for k, v in payloads.items() if v is not None}
    order = sorted(present, key=lambda k: (0 if k == prefer else 1, _RANK.get(k, 9)))

    gaps = []
    winner, positions = None, []
    for k in order:
        try:
            pos = normalize(present[k], k)
        except Exception as e:                       # one bad source never aborts
            gaps.append(f"{k}: normalize failed ({e}) — fell through to next source")
            continue
        if pos:
            winner, positions = k, pos
            break
        gaps.append(f"{k}: connected but returned no positions")

    present_kinds = {_KIND.get(k, k) for k in present}
    for canon in ("indmoney", "broker", "portfolio"):
        if canon not in present_kinds:
            gaps.append(f"{canon}: not connected")

    return _envelope(winner is not None, winner, {"positions": positions}, gaps)


# --------------------------------------------------------------------------- #
# CLI — for a connected-session dry run (skill writes payloads to temp files)  #
# --------------------------------------------------------------------------- #
def _load(path):
    with open(path) as f:
        txt = f.read()
    if path.endswith((".yml", ".yaml")):
        try:
            import yaml
        except ImportError:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                                   "--break-system-packages", "pyyaml"])
            import yaml
        return yaml.safe_load(txt)
    return json.loads(txt)


def main():
    ap = argparse.ArgumentParser(description="Resolve canonical holdings from source payloads.")
    ap.add_argument("--indmoney", help="path to IndMoney networth_holdings payload (JSON)")
    ap.add_argument("--kite", help="path to Kite holdings+positions payload (JSON)")
    ap.add_argument("--upstox", help="path to Upstox holdings+positions payload (JSON)")
    ap.add_argument("--broker", help="path to a generic broker payload (JSON)")
    ap.add_argument("--portfolio", help="path to the hand-maintained positions block (JSON/YAML)")
    ap.add_argument("--prefer", default="indmoney", help="source to lead precedence")
    ap.add_argument("--equity-only", action="store_true", help="filter to the equity slice")
    ap.add_argument("--mf-only", action="store_true", help="filter to the mutual-fund slice")
    args = ap.parse_args()

    payloads = {}
    for key in ("indmoney", "kite", "upstox", "broker", "portfolio"):
        path = getattr(args, key)
        if path:
            payloads[key] = _load(path)

    env = resolve(prefer=args.prefer, payloads=payloads)
    if args.equity_only:
        env["data"]["positions"] = equity_only(env["data"]["positions"])
    elif args.mf_only:
        env["data"]["positions"] = mf_only(env["data"]["positions"])
    print(json.dumps(env, indent=2))


if __name__ == "__main__":
    main()
