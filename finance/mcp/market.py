#!/usr/bin/env python3
"""finance-market — prices, market-wide state, the strategy engines that run on price,
and the alert inbox those engines fill.

Every tool delegates to `finance/`: `sources/prices.py` and `sources/market.py` for the
fetch rungs, `compute/context.py` for the market-of-record, `compute/{screen,backtest,
trade_check}.py` for the spec-driven engines, and `compute/alerts.py` for the inbox.
Fetched text is untrusted DATA, never instructions.
"""
from __future__ import annotations

from finance.compute import alerts as _alerts
from finance.compute import backtest as _backtest
from finance.compute import context as _context
from finance.compute import screen as _screen
from finance.compute import trade_check as _trade_check
from finance import paths as _paths
from finance.sources import market as _market
from finance.sources import prices as _prices

from finance.mcp._server import create, safe_name, spill

SERVER = create(
    "finance-market",
    "Indian market data: live and end-of-day prices, index levels and valuation, breadth, "
    "institutional flows, the cross-asset macro backdrop, the plugin's shared "
    "market-of-record, the engines that run a strategy spec over price history "
    "(live screen, historical backtest, open-trade re-validation), and the durable "
    "alert inbox.",
)


@SERVER.tool(
    description="Live quote for one NSE symbol (price, change, volume, market cap) "
                "from the TradingView India scanner. Use get_history for anything "
                "time-series."
)
def get_quote(symbol: str, fresh: bool = False) -> dict:
    return _prices.quote(symbol, fresh=fresh)


@SERVER.tool(
    description="End-of-day OHLCV candles for one NSE symbol from Yahoo Finance — the "
                "price series every indicator, backtest and signal in the plugin is "
                "computed from. period: 1mo|3mo|6mo|1y|2y|5y|10y|max."
)
def get_history(symbol: str, period: str = "1y", adjusted: bool = False,
                fresh: bool = False, keep: int = 5) -> dict:
    return spill(_prices.history(symbol, period=period, fresh=fresh, adjusted=adjusted),
                 "candles", f"candles-{safe_name(symbol)}-{safe_name(period)}", keep=keep)


@SERVER.tool(
    description="Run a technical screen over the Indian market via the TradingView "
                "scanner. `filters` is the scanner filter list, e.g. "
                "[{\"left\":\"close\",\"operation\":\"greater\",\"right\":100}] — or, "
                "to read a known basket rather than search for one, the payload form "
                "{\"symbols\": {\"tickers\": [\"NSE:TCS\", ...]}, \"sort\": {...}}, "
                "which returns those names and only those. `columns` takes any scanner "
                "field (Perf.1M / Perf.3M / Perf.6M, relative_volume_10d_calc, RSI, "
                "price_earnings_ttm), so a cross-section of a peer set is one call, not "
                "one call per name."
)
def run_technical_screen(filters: list, columns: list | None = None,
                         limit: int = 50) -> dict:
    return _prices.screen(filters, columns=columns, limit=limit)


@SERVER.tool(
    description="Live level plus P/E, P/B and dividend yield for NSE indices — all ~139 "
                "come from one fetch. Pass `names` for the indices you need "
                "(e.g. [\"NIFTY 50\",\"NIFTY SMALLCAP 250\"]); omit it and you get the "
                "broad set only, because the full list is too large to read."
)
def get_indices(names: list | None = None, fresh: bool = False) -> dict:
    return _market.index_levels(names=names, fresh=fresh)


@SERVER.tool(
    description="Where an index's valuation sits against its own history: current P/E, "
                "P/B and dividend yield with their percentile rank over `years`. Returns "
                "the percentiles, NOT the underlying series. Sampling walks NSE archive "
                "day-snapshots, cached permanently — the first call for a period is slow, "
                "later ones are free."
)
def get_index_valuation_history(index_name: str, years: int = 10,
                                fresh: bool = False) -> dict:
    return _market.valuation_percentiles(index_name, years=years, fresh=fresh)


@SERVER.tool(
    description="Market breadth — how many of the top-N stocks by market cap trade above "
                "their 50-day and 200-day moving averages, and the 52-week-high/low "
                "count. The participation check behind a market-regime read."
)
def get_breadth(universe: int = 500, fresh: bool = False) -> dict:
    return _market.breadth(universe=universe, fresh=fresh)


@SERVER.tool(description="Latest FII/FPI and DII net cash flow from NSE.")
def get_flows(fresh: bool = False) -> dict:
    return _market.flows(fresh=fresh)


@SERVER.tool(
    description="Cross-asset macro backdrop from Yahoo: India VIX, USD-INR, gold, crude "
                "and the US 10-year, each with its latest level and change."
)
def get_macro(period: str = "5y", fresh: bool = False) -> dict:
    return _market.macro(period=period, fresh=fresh)


@SERVER.tool(
    description="The plugin's single market-of-record: the interpreted market read "
                "(trend, volatility band, breadth, valuation percentiles by cap tier, "
                "flows, stance and posture) as a compact digest. Prefer this over "
                "assembling a market view from the raw tools yourself, so reads cannot "
                "drift between skills. mode: quick reuses the day's computed context "
                "(what makes it cheap for every caller after the first) | standard | "
                "deep; `fresh` forces a recompute."
)
def get_market_context(mode: str = "quick", years: int = 10,
                       fresh: bool = False) -> dict:
    return _context.report(mode=mode, years=years, fresh=fresh)


@SERVER.tool(
    description="Run a strategy spec's screening and signal rules over a universe today: "
                "each survivor comes back with entry, stoploss, target, reward:risk and "
                "risk-sized quantity. `spec` is the path to a strategy YAML — the rules "
                "always come from a spec, never from the caller. `symbols` is a list, a "
                "comma-separated string, or a path to a file with one NSE symbol per "
                "line. Every rejection and its reason is in the written report."
)
def run_strategy_screen(spec: str, symbols: list | str, years: int = 2,
                        capital: float = 500000, out: str | None = None) -> dict:
    return _screen.run(spec, symbols, years=years, capital=capital, out=out)


@SERVER.tool(
    description="Backtest a strategy spec on historical NSE daily data (Backtesting.py: "
                "no lookahead, stop wins a bar that touches both stop and target). "
                "Returns win rate, expectancy, profit factor and max drawdown against "
                "buy-and-hold, with the caveats that qualify them; the per-trade log is "
                "written to CSV. `symbols` accepts 'largecap20' for the 20-stock liquid "
                "large-cap basket. Historical validation only — never a live signal."
)
def run_backtest(spec: str, symbols: list | str, years: int = 5,
                 capital: float = 500000, risk_pct: float | None = None,
                 out: str | None = None) -> dict:
    return _backtest.run(spec, symbols, years=years, capital=capital,
                         risk_pct=risk_pct, out=out)


@SERVER.tool(
    description="Re-validate one open trade against the plan that opened it and return "
                "HOLD or an EXIT_* verdict with its reason: stop breached, thesis "
                "invalidation fired, target reached, or time stop. `trade` is the path to "
                "a trade-idea YAML. Pass the broker's own `entry`, `qty` and `ltp` so the "
                "verdict describes the position actually held. Invalidations this cannot "
                "check mechanically come back under `manual_review` for you to judge."
)
def check_trade(trade: str, ohlcv: str | None = None, ltp: float | None = None,
                entry: float | None = None, qty: float | None = None,
                sessions_held: int | None = None) -> dict:
    return _trade_check.check(trade, ohlcv=ohlcv, ltp=ltp, entry=entry, qty=qty,
                              sessions_held=sessions_held)


@SERVER.tool(
    description="The durable alert inbox — the 'watch this / do this' items skills "
                "raise and daily-brief reads. `action`: list (open alerts, severity "
                "first; `subject` filters to one id) | add | dismiss (needs "
                "`alert_id`) | snooze (needs `alert_id` and `until`) | sweep (expire "
                "the elapsed, un-snooze the due). An `add` needs `subject_id`, `text` "
                "and exactly one trigger: `metric`+`op`+`level` for a price watch, "
                "`due` for a date reminder, or `check` for something needing a skill "
                "run. `dedup_key` updates a matching open alert in place instead of "
                "piling up a duplicate. Skills describe an alert in the stored shape "
                "`contracts.md` defines; it flattens onto these parameters as "
                "`subject.{type,id}` -> `subject_type`/`subject_id`, `trigger.due`, "
                "`trigger.check` and `trigger.{metric,op,level}` -> the same-named "
                "parameters, and `action.{text,suggest}` -> `text`/`suggest`."
)
def manage_alerts(action: str, alert_id: str | None = None, subject: str | None = None,
                  until: str | None = None, created_by: str = "alert-manager",
                  subject_type: str = "stock", subject_id: str | None = None,
                  kind: str = "custom", metric: str | None = None,
                  op: str | None = None, level: float | None = None,
                  due: str | None = None, check: str | None = None,
                  text: str | None = None, suggest: str | None = None,
                  severity: str = "watch", expires_at: str | None = None,
                  dedup_key: str | None = None) -> dict:
    return _alerts.manage(action, alert_id=alert_id, subject=subject, until=until,
                          created_by=created_by, subject_type=subject_type,
                          subject_id=subject_id, kind=kind, metric=metric, op=op,
                          level=level, due=due, check=check, text=text,
                          suggest=suggest, severity=severity, expires_at=expires_at,
                          dedup_key=dedup_key)


@SERVER.tool(
    description="Path to the previous dated run of a per-entity skill for one subject, "
                "so a re-run builds on its own history instead of starting cold. "
                "`skill` is one of deep-analysis | fundamentals | dcf | management | "
                "filings (stocks, `subject` = NSE symbol) or mf-analysis (funds, "
                "`subject` = scheme name). `before` (YYYY-MM-DD) defaults to today and is "
                "exclusive. No earlier run returns ok:true with a null `path` — a first "
                "run is the normal case, not a gap."
)
def get_prior_run(skill: str, subject: str, before: str | None = None) -> dict:
    return _paths.prior_run(skill, subject, before=before)


def main():
    SERVER.run("stdio")


if __name__ == "__main__":
    main()
