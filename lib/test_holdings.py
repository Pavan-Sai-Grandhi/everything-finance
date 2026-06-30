#!/usr/bin/env python3
"""Offline tests for the holdings resolver/normalizer. No network, no MCP.
Run: python3 lib/test_holdings.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import holdings  # noqa: E402

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


# --- captured sample payloads (shapes the skills hand off via temp files) --- #

INDMONEY = {
    "as_of": "2026-06-27",
    "holdings": [
        {"name": "Reliance Industries", "symbol": "RELIANCE", "asset_class": "Indian Stocks",
         "units": 50, "avg_price": 2400.0, "ltp": 2950.5, "invested": 120000,
         "current_value": 147525, "pnl": 27525, "xirr": 18.4, "broker": "Zerodha",
         "isin": "INE002A01018"},
        {"name": "Parag Parikh Flexi Cap", "symbol": "PPFAS", "asset_class": "Mutual Funds",
         "units": 1200.5, "avg_price": 60.0, "nav": 78.2, "invested": 72030,
         "xirr": 22.1, "broker": "IND Money"},
        {"name": "Apple Inc", "symbol": "AAPL", "asset_class": "US Stocks",
         "units": 5, "avg_price": 180.0, "ltp": 210.0, "invested": 75000,
         "current_value": 87500, "xirr": 12.0},  # pnl absent -> derived
    ],
}

KITE = {
    "holdings": [
        {"tradingsymbol": "RELIANCE", "exchange": "NSE", "isin": "INE002A01018",
         "quantity": 50, "average_price": 2400.0, "last_price": 2950.5, "pnl": 27525.0},
        {"tradingsymbol": "TITAN", "exchange": "NSE", "quantity": 10,
         "average_price": 3300.0, "last_price": 3650.0},  # pnl absent -> derived
    ],
    "positions": {
        "net": [
            {"tradingsymbol": "INFY", "quantity": 20, "average_price": 1500.0,
             "last_price": 1620.0, "pnl": 2400.0},
            {"tradingsymbol": "SBIN", "quantity": 0, "average_price": 600.0,
             "last_price": 610.0, "pnl": 0.0},  # closed intraday -> skipped
        ],
        "day": [],
    },
}

UPSTOX = [
    {"trading_symbol": "TATAMOTORS", "quantity": 30, "average_price": 700.0,
     "last_price": 980.0, "pnl": 8400.0},
]

PORTFOLIO = {
    "positions": [
        {"ticker": "HDFCBANK", "entry": 1500.0, "sl": 1420.0, "target": 1700.0,
         "qty": 25, "entry_date": "2026-05-01", "bse_code": "500180"},
    ],
}


# --- normalize: IndMoney ----------------------------------------------------- #

def test_indmoney_normalize():
    pos = holdings.normalize(INDMONEY, "indmoney")
    check("indmoney: 3 positions", len(pos) == 3, len(pos))
    rel = pos[0]
    check("indmoney: ticker", rel["ticker"] == "RELIANCE")
    check("indmoney: qty/avg/ltp", (rel["qty"], rel["avg"], rel["ltp"]) == (50.0, 2400.0, 2950.5))
    check("indmoney: pnl", rel["pnl"] == 27525.0)
    check("indmoney: xirr", rel["xirr"] == 18.4)
    check("indmoney: invested", rel["invested"] == 120000.0)
    check("indmoney: broker", rel["broker"] == "Zerodha")
    check("indmoney: asset_class lowercased", rel["asset_class"] == "indian stocks")
    check("indmoney: source label", rel["source"] == "indmoney")
    check("indmoney: as_of inherited", rel["as_of"] == "2026-06-27")
    aapl = pos[2]
    check("indmoney: pnl derived from value-invested", aapl["pnl"] == 12500.0, aapl["pnl"])
    mf = pos[1]
    check("indmoney: nav read as ltp", mf["ltp"] == 78.2)
    check("indmoney: pnl derived from (ltp-avg)*qty when no current_value",
          mf["pnl"] == round((78.2 - 60.0) * 1200.5, 2), mf["pnl"])


# --- normalize: broker ------------------------------------------------------- #

def test_kite_normalize():
    pos = holdings.normalize(KITE, "kite")
    tks = [p["ticker"] for p in pos]
    check("kite: holdings+net, zero-qty dropped", tks == ["RELIANCE", "TITAN", "INFY"], tks)
    titan = next(p for p in pos if p["ticker"] == "TITAN")
    check("kite: pnl derived", titan["pnl"] == round((3650.0 - 3300.0) * 10, 2), titan["pnl"])
    check("kite: no xirr/invested/asset_class from broker",
          (titan["xirr"], titan["invested"], titan["asset_class"]) == (None, None, None))
    check("kite: source label", pos[0]["source"] == "kite")


def test_upstox_list_normalize():
    pos = holdings.normalize(UPSTOX, "upstox")
    check("upstox: bare list + trading_symbol key", len(pos) == 1 and pos[0]["ticker"] == "TATAMOTORS")
    check("upstox: source label", pos[0]["source"] == "upstox")


# --- normalize: portfolio ---------------------------------------------------- #

def test_portfolio_normalize():
    pos = holdings.normalize(PORTFOLIO, "portfolio")
    check("portfolio: 1 position", len(pos) == 1)
    p = pos[0]
    check("portfolio: entry -> avg", p["avg"] == 1500.0)
    check("portfolio: qty", p["qty"] == 25.0)
    check("portfolio: no live price/pnl", (p["ltp"], p["pnl"]) == (None, None))
    check("portfolio: entry_date -> as_of", p["as_of"] == "2026-05-01")


# --- equity_only ------------------------------------------------------------- #

def test_equity_only():
    pos = holdings.normalize(INDMONEY, "indmoney")
    eq = holdings.equity_only(pos)
    tks = sorted(p["ticker"] for p in eq)
    check("equity_only: drops mutual fund, keeps stocks", tks == ["AAPL", "RELIANCE"], tks)
    # broker/portfolio (asset_class None) are equity by construction
    bro = holdings.equity_only(holdings.normalize(KITE, "kite"))
    check("equity_only: broker None-class kept", len(bro) == 3, len(bro))


# --- resolve: precedence ----------------------------------------------------- #

def test_resolve_indmoney_wins():
    env = holdings.resolve(payloads={"indmoney": INDMONEY, "kite": KITE, "portfolio": PORTFOLIO})
    check("resolve: indmoney wins", env["source"] == "indmoney")
    check("resolve: ok", env["ok"] is True)
    check("resolve: positions from indmoney (3)", len(env["data"]["positions"]) == 3)
    check("resolve: envelope keys", set(env) == {"ok", "source", "fetched_at", "data", "gaps"})


def test_resolve_falls_to_broker():
    env = holdings.resolve(payloads={"kite": KITE, "portfolio": PORTFOLIO})
    check("resolve: broker wins when no indmoney", env["source"] == "kite")
    check("resolve: indmoney noted absent",
          any("indmoney: not connected" in g for g in env["gaps"]), env["gaps"])


def test_resolve_falls_to_portfolio():
    env = holdings.resolve(payloads={"portfolio": PORTFOLIO})
    check("resolve: portfolio wins as last resort", env["source"] == "portfolio")
    check("resolve: broker noted absent",
          any("broker: not connected" in g for g in env["gaps"]))


def test_resolve_nothing_connected():
    env = holdings.resolve(payloads={})
    check("resolve: no source -> ok False", env["ok"] is False and env["source"] is None)
    check("resolve: positions empty", env["data"]["positions"] == [])
    check("resolve: all three sources flagged absent", len(env["gaps"]) == 3)


def test_resolve_prefer_override():
    env = holdings.resolve(prefer="kite", payloads={"indmoney": INDMONEY, "kite": KITE})
    check("resolve: prefer bumps broker ahead of indmoney", env["source"] == "kite")


def test_resolve_empty_source_falls_through():
    env = holdings.resolve(payloads={"indmoney": {"holdings": []}, "kite": KITE})
    check("resolve: empty indmoney falls through to broker", env["source"] == "kite")
    check("resolve: empty source recorded as gap",
          any("indmoney: connected but returned no positions" in g for g in env["gaps"]),
          env["gaps"])


def test_resolve_broken_source_falls_through():
    # a payload that makes normalize raise -> must fall through, not abort
    class Boom(dict):
        def get(self, *a, **k):
            raise RuntimeError("boom")
    env = holdings.resolve(payloads={"indmoney": Boom(), "kite": KITE})
    check("resolve: broken source falls through", env["source"] == "kite")
    check("resolve: failure recorded as gap",
          any("normalize failed" in g for g in env["gaps"]), env["gaps"])


# --- coercion helpers -------------------------------------------------------- #

def test_num_coercion():
    check("num: ₹/comma string", holdings._num("₹1,23,456") == 123456.0)
    check("num: percent string", holdings._num("18.4%") == 18.4)
    check("num: NA -> None", holdings._num("NA") is None)
    check("num: bool -> None", holdings._num(True) is None)


def main():
    for fn in sorted(g for g in globals() if g.startswith("test_")):
        print(f"\n[{fn}]")
        globals()[fn]()
    print(f"\n{'='*48}\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
