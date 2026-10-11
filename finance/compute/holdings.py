#!/usr/bin/env python3
"""Holdings source-resolver + normalizer.

Turns whichever read source is connected into ONE canonical position shape and applies the
precedence IndMoney -> broker -> portfolio, so consumers never re-implement normalization.

MCP boundary: this module runs in script context and CANNOT call MCP tools. The calling
skill invokes the MCP tool, writes the raw payload to a temp file, and passes the path here
— the same file-handoff pattern `trade_check.py` uses. See `finance/contracts.md`.

Canonical position:
  { ticker, qty, avg, ltp, pnl, xirr, broker, asset_class, invested, value, unsettled_qty, source, as_of }
`xirr`, `broker`, `invested` and `asset_class` populate from IndMoney only; they are None
when just broker / portfolio data exists.

`normalize` keeps ALL asset classes; consumers call `equity_only(...)` for the stock slice.
A normalize failure on one source falls through to the next in precedence with a labelled
gap — never an abort. Returns the shared data-spine envelope.
"""
import argparse
import json
import re
import sys

from finance.spine import envelope as _envelope, f, first as _first
from finance.deps import load_yaml


def _num(x):
    """Personal amounts may include ₹; reject missing and nonfinite values."""
    return f(x.replace("₹", "")) if isinstance(x, str) else f(x)


def market_value(position):
    """Current value from reported value, cost plus P&L, or quantity times price.

    Cost alone is not a current valuation. This is shared by allocation and wealth
    so neither can silently value a stale cost basis as the market value.
    """
    value = _num(position.get("value"))
    if value is not None:
        return value
    invested, pnl = _num(position.get("invested")), _num(position.get("pnl"))
    if invested is not None and pnl is not None:
        return f(invested + pnl)
    qty, price = _num(position.get("qty")), _num(position.get("ltp"))
    return f(qty * price) if qty is not None and price is not None else None


def _ticker(it):
    v = _first(it, "symbol", "ticker", "tradingsymbol", "trading_symbol", "scrip",
               "scheme_name", "name", "investment", "isin")
    return str(v) if v is not None else "?"


def _asset_class(it):
    v = _first(it, "asset_class", "assetClass", "asset_type", "category", "product_type")
    return str(v).lower() if v is not None else None


def _as_of(payload):
    v = _first(payload, "as_of", "as_on", "fetched_at", "timestamp", "date") \
        if isinstance(payload, dict) else None
    return str(v) if v is not None else None


def _holdings_list(payload):
    """Dig the per-position list out of a nested payload by common container keys.

    MCP tools can return the payload as a JSON string under `result` (IndMoney does);
    a string container is decoded once, never evaluated."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("holdings", "positions", "networth_holdings", "items",
                    "data", "result"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
            if isinstance(v, (dict, str)):
                inner = _holdings_list(v)
                if inner:
                    return inner
    return []


# Each normalizer returns canonical positions without the `source` label; `normalize`
# stamps that on afterwards.
def _normalize_indmoney(payload):
    """IndMoney `networth_holdings`: all asset classes, with invested / P&L / XIRR."""
    as_of = _as_of(payload)
    out = []
    for it in _holdings_list(payload):
        if not isinstance(it, dict):
            continue
        qty = _num(_first(it, "units", "total_units", "quantity", "qty", "balance_units"))
        avg = _num(_first(it, "avg_price", "average_price", "avg_cost", "buy_avg", "avg"))
        ltp = _num(_first(it, "ltp", "last_price", "current_price", "unit_price", "nav", "price"))
        invested = _num(_first(it, "invested", "invested_value", "invested_amount",
                               "cost_value", "buy_value"))
        cur = _num(_first(it, "current_value", "market_value", "current_amount"))
        pnl = _num(_first(it, "pnl", "total_pnl", "unrealized_pnl", "gain", "total_gain",
                          "returns_value"))
        broker = _first(it, "broker", "broker_name", "source_broker", "account") or None
        # IndMoney's own tool notes linked-broker cost is unreliable; live rows report
        # cost equal to value with zero P&L. That is an absent cost, not a zero gain.
        cost_basis = None
        if (broker and str(broker).strip().lower() != "indmoney" and invested is not None
                and cur is not None and invested == cur and not pnl):
            invested = pnl = avg = None
            cost_basis = "unreported_by_linked_broker"
        if invested is None and avg is not None and qty is not None:
            invested = round(avg * qty, 2)
        if pnl is None:
            if cur is not None and invested is not None:
                pnl = round(cur - invested, 2)
            elif None not in (ltp, avg, qty):
                pnl = round((ltp - avg) * qty, 2)
        row = {
            # IndMoney's `investment_code` is an internal id (INDS…), never an NSE symbol.
            "ticker": _ticker(it),
            "qty": qty, "avg": avg, "ltp": ltp, "pnl": pnl,
            "xirr": _num(_first(it, "xirr", "irr", "returns_xirr", "annualized_return")),
            "broker": broker,
            "asset_class": _asset_class(it),
            "invested": invested, "value": cur,
            "as_of": (_first(it, "as_of", "as_on") or as_of),
        }
        code = _first(it, "investment_code")
        if code is not None:
            row["instrument_code"] = str(code)
        if cost_basis:
            row["cost_basis"] = cost_basis
        out.append(row)
    return out


# NSE trades non-EQ series under SYMBOL-SERIES (trade-for-trade BE/BZ, REIT RR, InvIT IV,
# SME SM/ST, gold bond GB); decision tools key on the base symbol.
_NSE_SERIES = re.compile(r"^(?P<base>[A-Z0-9&]+)-(?P<series>BE|BZ|BL|RR|IV|SM|ST|GB)$")


def _instrument(it):
    """(ticker, broker_symbol, exchange, isin, asset_class) from a broker row.

    The class comes only from published identifiers: ISIN country+issuer code `INF`
    marks mutual-fund units (ETFs), `IN0` central-government securities, and the NSE
    series RR/IV marks REIT/InvIT units. Anything else is equity by construction."""
    raw = _ticker(it)
    exchange = _first(it, "exchange")
    isin = _first(it, "isin")
    match = _NSE_SERIES.match(raw.upper()) if str(exchange or "NSE").upper() == "NSE" else None
    ticker, series = (match["base"], match["series"]) if match else (raw, None)
    code = str(isin or "").upper()
    asset_class = ("reit" if series == "RR" else "invit" if series == "IV"
                   else "etf" if code.startswith("INF")
                   else ("sovereign gold bond" if raw.upper().startswith("SGB") else "government security")
                   if code.startswith("IN0") else None)
    return ticker, raw, (str(exchange) if exchange else None), (str(isin) if isin else None), asset_class


def _normalize_broker(payload, quantity_includes_t1=False):
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
        # Kite documents `quantity` as settled (T+2) and `t1_quantity` apart, so both
        # count; Upstox documents `quantity` as the total, so T+1 is only labelled —
        # unless quantity < t1_quantity, which shows T+1 was not included.
        settled = _num(_first(it, "quantity", "qty", "net_quantity"))
        unsettled = _num(it.get("t1_quantity"))
        if settled is None and unsettled is None:
            continue
        if quantity_includes_t1 and settled is not None and settled >= (unsettled or 0.0):
            qty = settled
        else:
            qty = (settled or 0.0) + (unsettled or 0.0)
        if qty == 0:                       # skip closed/zero-net (intraday) lines
            continue
        avg = _num(_first(it, "average_price", "avg_price", "buy_price", "buy_avg"))
        ltp = _num(_first(it, "last_price", "ltp", "close_price"))
        pnl = _num(_first(it, "pnl", "unrealised", "unrealized", "pl"))
        if pnl is None and None not in (ltp, avg, qty):
            pnl = round((ltp - avg) * qty, 2)
        ticker, broker_symbol, exchange, isin, asset_class = _instrument(it)
        out.append({
            "ticker": ticker, "broker_symbol": broker_symbol, "exchange": exchange, "isin": isin,
            "qty": qty, "avg": avg, "ltp": ltp, "pnl": pnl,
            "xirr": None, "broker": None, "asset_class": asset_class, "invested": None,
            "value": _num(_first(it, "current_value", "market_value")),
            "unsettled_qty": unsettled if unsettled else None,
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
            "pnl": None, "value": _num(_first(it, "value", "current_value")),
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
    positions = (fn(payload, quantity_includes_t1=(source == "upstox")) if kind == "broker"
                 else fn(payload))
    for p in positions:
        p["source"] = source
    return positions


_NON_EQUITY = ("mutual", "mf", "bond", "gold", "silver", "fd", "deposit", "ppf",
               "epf", "nps", "cash", "insurance", "reit", "invit", "debt", "etf",
               "government security")
_FUND = ("mutual", "mf")


def equity_only(positions):
    """Stock/equity slice. Broker rows are equity unless their ISIN/series marks ETF,
    REIT/InvIT or government-security units; portfolio rows (asset_class None) are equity; IndMoney positions are kept unless their asset_class names a
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

    uncosted = sorted({str(p.get("broker")) for p in positions
                       if p.get("cost_basis") == "unreported_by_linked_broker"})
    if uncosted:
        n = sum(p.get("cost_basis") == "unreported_by_linked_broker" for p in positions)
        brokers = [k for k in present if _KIND.get(k) == "broker"]
        hint = (f"; re-resolve with --prefer {brokers[0]} for their cost and P&L" if brokers
                else "; connect that broker for cost and P&L")
        gaps.append(f"{winner}: {n} holding(s) via {', '.join(uncosted)} carry no cost basis "
                    f"(the linked broker reports cost as current value){hint}"
                    + (f" (connected: {', '.join(brokers)})" if brokers else ""))

    present_kinds = {_KIND.get(k, k) for k in present}
    for canon in ("indmoney", "broker", "portfolio"):
        if canon not in present_kinds:
            gaps.append(f"{canon}: not connected")

    return _envelope(winner is not None, winner, {"positions": positions}, gaps)


def _load(path):
    with open(path) as f:
        txt = f.read()
    if path.endswith((".yml", ".yaml")):
        return load_yaml(path)
    return json.loads(txt)


def main():
    ap = argparse.ArgumentParser(description="Resolve canonical holdings from source payloads.")
    ap.add_argument("--indmoney", action="append",
                    help="path to an IndMoney networth_holdings payload (JSON); repeat once per "
                         "asset_type call (IND_STOCK, MF, US_STOCK, …)")
    ap.add_argument("--kite", help="path to Kite holdings+positions payload (JSON)")
    ap.add_argument("--upstox", help="path to Upstox holdings+positions payload (JSON)")
    ap.add_argument("--broker", help="path to a generic broker payload (JSON)")
    ap.add_argument("--portfolio", help="path to the hand-maintained positions block (JSON/YAML)")
    ap.add_argument("--prefer", default="indmoney", help="source to lead precedence")
    ap.add_argument("--equity-only", action="store_true", help="filter to the equity slice")
    ap.add_argument("--mf-only", action="store_true", help="filter to the mutual-fund slice")
    args = ap.parse_args()

    payloads = {}
    if args.indmoney:
        # networth_holdings serves one asset type per call; combine their rows.
        payloads["indmoney"] = {"holdings": [row for path in args.indmoney
                                             for row in _holdings_list(_load(path))]}
    for key in ("kite", "upstox", "broker", "portfolio"):
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
