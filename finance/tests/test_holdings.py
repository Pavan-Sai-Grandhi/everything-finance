#!/usr/bin/env python3
"""Offline tests for the holdings resolver/normalizer. No network, no MCP."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import holdings
from finance.tests.harness import check, run


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
         "current_value": 87500, "xirr": 12.0},
    ],
}

KITE = {
    "holdings": [
        {"tradingsymbol": "RELIANCE", "exchange": "NSE", "isin": "INE002A01018",
         "quantity": 50, "average_price": 2400.0, "last_price": 2950.5, "pnl": 27525.0},
        {"tradingsymbol": "TITAN", "exchange": "NSE", "quantity": 10,
         "average_price": 3300.0, "last_price": 3650.0},
    ],
    "positions": {
        "net": [
            {"tradingsymbol": "INFY", "quantity": 20, "average_price": 1500.0,
             "last_price": 1620.0, "pnl": 2400.0},
            {"tradingsymbol": "SBIN", "quantity": 0, "average_price": 600.0,
             "last_price": 610.0, "pnl": 0.0},
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
         "qty": 25, "entry_date": "2026-05-01"},
    ],
}


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


def test_portfolio_normalize():
    pos = holdings.normalize(PORTFOLIO, "portfolio")
    check("portfolio: 1 position", len(pos) == 1)
    p = pos[0]
    check("portfolio: entry -> avg", p["avg"] == 1500.0)
    check("portfolio: qty", p["qty"] == 25.0)
    check("portfolio: no live price/pnl", (p["ltp"], p["pnl"]) == (None, None))
    check("portfolio: entry_date -> as_of", p["as_of"] == "2026-05-01")


def test_equity_only():
    pos = holdings.normalize(INDMONEY, "indmoney")
    eq = holdings.equity_only(pos)
    tks = sorted(p["ticker"] for p in eq)
    check("equity_only: drops mutual fund, keeps stocks", tks == ["AAPL", "RELIANCE"], tks)
    bro = holdings.equity_only(holdings.normalize(KITE, "kite"))
    check("equity_only: broker None-class kept", len(bro) == 3, len(bro))


def test_mf_only():
    pos = holdings.normalize(INDMONEY, "indmoney")
    mf = holdings.mf_only(pos)
    tks = sorted(p["ticker"] for p in mf)
    check("mf_only: keeps mutual fund, drops stocks", tks == ["PPFAS"], tks)
    bro = holdings.mf_only(holdings.normalize(KITE, "kite"))
    check("mf_only: broker None-class dropped", bro == [], bro)


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
    class Boom(dict):
        def get(self, *a, **k):
            raise RuntimeError("boom")
    env = holdings.resolve(payloads={"indmoney": Boom(), "kite": KITE})
    check("resolve: broken source falls through", env["source"] == "kite")
    check("resolve: failure recorded as gap",
          any("normalize failed" in g for g in env["gaps"]), env["gaps"])


def test_num_coercion():
    check("num: ₹/comma string", holdings._num("₹1,23,456") == 123456.0)
    check("num: percent string", holdings._num("18.4%") == 18.4)
    check("num: NA -> None", holdings._num("NA") is None)
    check("num: bool -> None", holdings._num(True) is None)
    for invalid in (float("nan"), float("inf"), "-inf"):
        check("nonfinite personal amount is unavailable", holdings._num(invalid) is None)


def test_value_only_assets_survive_normalization():
    from finance.compute import allocation, wealth
    env = holdings.resolve(payloads={"indmoney": {"holdings": [
        {"name": "Deposit", "asset_class": "Fixed Deposit", "current_value": 50000},
        {"name": "Spent account", "asset_class": "Cash", "current_value": 0},
    ]}})
    pos = env["data"]["positions"]
    check("reported current value is retained", pos[0].get("value") == 50000)
    check("reported zero value is retained", pos[1].get("value") == 0)
    check("allocation values the same personal book", allocation.review(pos)["total"] == 50000)
    check("wealth values the same personal book",
          wealth.build_spine(positions_env=env)["total_networth"] == 50000)


def test_kite_t1_purchase_is_not_dropped():
    payload = {"holdings": [
        {"tradingsymbol": "NEWBUY", "quantity": 0, "t1_quantity": 5, "average_price": 100.0,
         "last_price": 110.0, "pnl": 50.0},
        {"tradingsymbol": "MIXED", "quantity": 10, "t1_quantity": 2, "average_price": 50.0,
         "last_price": 55.0, "pnl": 60.0},
        {"tradingsymbol": "SOLD", "quantity": 0, "t1_quantity": 0, "average_price": 10.0,
         "last_price": 11.0}]}
    pos = {p["ticker"]: p for p in holdings.normalize(payload, "kite")}
    check("kite: a T+1 purchase with zero settled quantity is still held",
          "NEWBUY" in pos and pos["NEWBUY"]["qty"] == 5, pos)
    check("kite: held quantity adds settled and T+1 shares", pos.get("MIXED", {}).get("qty") == 12, pos)
    check("kite: the unsettled part is labelled", pos.get("MIXED", {}).get("unsettled_qty") == 2, pos)
    check("kite: a fully closed line is still dropped", "SOLD" not in pos, pos)


def test_upstox_total_quantity_is_not_double_counted():
    payload = {"data": [
        {"trading_symbol": "MIXED", "quantity": 12, "t1_quantity": 2, "average_price": 50.0,
         "last_price": 55.0, "pnl": 60.0},
        {"trading_symbol": "NEWBUY", "quantity": 0, "t1_quantity": 5, "average_price": 100.0,
         "last_price": 110.0}]}
    pos = {p["ticker"]: p for p in holdings.normalize(payload, "upstox")}
    check("upstox: documented total quantity is not increased by T+1", pos.get("MIXED", {}).get("qty") == 12, pos)
    check("upstox: the T+1 part is still labelled", pos.get("MIXED", {}).get("unsettled_qty") == 2, pos)
    check("upstox: quantity below T+1 shows it was excluded, so both count",
          pos.get("NEWBUY", {}).get("qty") == 5, pos)


def _indmoney_live_shape(rows):
    """The live networth_holdings envelope: a JSON string under `result` (dummy values)."""
    import json as _json
    return {"result": _json.dumps({"positions": None, "open_orders": [], "holdings": rows,
                                   "asset_summary": {"total_value": 1}, "source_status": {"holdings": "success"}})}


def _ind_row(**kw):
    row = {"investment_code": "INDS00001", "investment": "Alpha Ltd", "asset_type": "STOCK",
           "assetclass_l2": "equity", "invested_amount": 300, "market_value": 330,
           "holding_percent": 50.0, "total_pnl": 30, "pnl_per": 10.0, "total_units": 3,
           "unit_price": 110.0, "broker": "INDmoney", "market_cap": "mid",
           "one_day_change": 1, "one_day_change_percentage": 0.1}
    row.update(kw)
    return row


def test_indmoney_live_envelope_and_field_names():
    pos = holdings.normalize(_indmoney_live_shape([_ind_row()]), "indmoney")
    check("indmoney: the JSON-string `result` envelope is decoded", len(pos) == 1, pos)
    p = pos[0] if pos else {}
    check("indmoney: total_units / unit_price / total_pnl map to qty / ltp / pnl",
          (p.get("qty"), p.get("ltp"), p.get("pnl")) == (3.0, 110.0, 30.0), p)
    check("indmoney: the internal investment_code is never used as a ticker",
          p.get("ticker") == "Alpha Ltd" and p.get("instrument_code") == "INDS00001", p)
    check("indmoney: invested and current value carried", (p.get("invested"), p.get("value")) == (300.0, 330.0), p)


def test_indmoney_linked_broker_cost_is_not_trusted():
    row = _ind_row(broker="Upstox", invested_amount=330, market_value=330, total_pnl=0, pnl_per=0)
    p = holdings.normalize(_indmoney_live_shape([row]), "indmoney")[0]
    check("indmoney: a linked-broker row reporting cost == value and zero P&L has unknown cost",
          p.get("invested") is None and p.get("pnl") is None and p.get("avg") is None, p)
    check("indmoney: its current value is still carried", p.get("value") == 330.0, p)
    check("indmoney: the unknown cost is flagged on the row", p.get("cost_basis") == "unreported_by_linked_broker", p)
    genuine = holdings.normalize(_indmoney_live_shape([_ind_row(broker="Upstox")]), "indmoney")[0]
    check("indmoney: a linked-broker row with a real gain keeps its cost", genuine.get("invested") == 300.0, genuine)


def test_resolver_points_to_broker_cost_when_indmoney_lacks_it():
    row = _ind_row(broker="Upstox", invested_amount=330, market_value=330, total_pnl=0, pnl_per=0)
    env = holdings.resolve(payloads={"indmoney": _indmoney_live_shape([row]),
                                     "upstox": {"data": [{"trading_symbol": "ALPHA", "quantity": 3,
                                                          "average_price": 90.0, "last_price": 110.0}]}})
    check("resolver: IndMoney still wins precedence", env["source"] == "indmoney", env)
    check("resolver: a gap names the uncosted rows and the broker that carries cost",
          any("no cost basis" in g and "upstox" in g for g in env["gaps"]), env["gaps"])


def test_cli_combines_one_indmoney_payload_per_asset_type():
    import json as _json, subprocess, sys as _sys, tempfile as _tf, os as _os
    d = _tf.mkdtemp()
    stock = _os.path.join(d, "stock.json"); fund = _os.path.join(d, "mf.json")
    _json.dump(_indmoney_live_shape([_ind_row()]), open(stock, "w"))
    _json.dump(_indmoney_live_shape([_ind_row(investment_code="3229", investment="Fund A Direct Growth",
                                              asset_type="MF", broker=None, market_cap=None)]), open(fund, "w"))
    root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
    out = subprocess.run([_sys.executable, "-m", "finance.compute.holdings", "--indmoney", stock,
                          "--indmoney", fund, "--mf-only"], capture_output=True, text=True,
                         cwd=root, env=dict(_os.environ, PYTHONPATH=root))
    env = _json.loads(out.stdout)
    check("cli: repeated --indmoney payloads combine; the MF slice finds the fund",
          [p["ticker"] for p in env["data"]["positions"]] == ["Fund A Direct Growth"], out.stdout[-300:] + out.stderr[-300:])


def _kite_live_row(sym, exch="NSE", isin="INE000000001"):
    """Live Kite holdings row shape (bare list element), dummy values."""
    return {"tradingsymbol": sym, "exchange": exch, "instrument_token": 1, "isin": isin,
            "product": "CNC", "quantity": 10, "t1_quantity": 0, "realised_quantity": 10,
            "average_price": 100.0, "last_price": 110.0, "close_price": 109.0, "pnl": 100.0}


def test_kite_live_symbols_and_instrument_types():
    rows = [_kite_live_row("ALPHA"), _kite_live_row("TTOT-BE"), _kite_live_row("REIT-RR"),
            _kite_live_row("ITBEES", isin="INF204KB15V2"),
            _kite_live_row("SGBMR29XII", exch="BSE", isin="IN0020200427")]
    pos = {p["broker_symbol"]: p for p in holdings.normalize(rows, "kite")}
    check("kite: an NSE series suffix is stripped to the base symbol",
          pos["TTOT-BE"]["ticker"] == "TTOT" and pos["REIT-RR"]["ticker"] == "REIT", pos)
    check("kite: exchange and ISIN are carried", pos["SGBMR29XII"]["exchange"] == "BSE"
          and pos["ALPHA"]["isin"] == "INE000000001", pos["SGBMR29XII"])
    check("kite: an INF ISIN is exchange-traded fund units, not a stock",
          pos["ITBEES"]["asset_class"] == "etf", pos["ITBEES"])
    check("kite: an RR-series line is a REIT", pos["REIT-RR"]["asset_class"] == "reit", pos["REIT-RR"])
    check("kite: an IN0 SGB line is a sovereign gold bond",
          pos["SGBMR29XII"]["asset_class"] == "sovereign gold bond", pos["SGBMR29XII"])
    eq = {p["broker_symbol"] for p in holdings.equity_only(list(pos.values()))}
    check("kite: the equity slice keeps stocks and drops ETF/REIT/SGB units",
          eq == {"ALPHA", "TTOT-BE"}, eq)


if __name__ == "__main__":
    run(globals())
