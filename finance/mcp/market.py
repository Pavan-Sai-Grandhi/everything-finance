"""finance-market: prices, technicals, market-wide state, and the engines that run a
strategy spec over price history."""
from __future__ import annotations

from finance.compute import backtest as _backtest
from finance.compute import context as _context
from finance.compute import screen as _screen
from finance.compute import sector_scan as _sector_scan
from finance.compute import stock_scan as _stock_scan
from finance.compute import technicals as _technicals
from finance.deps import load_yaml as _load_yaml
from finance.sources import market as _market
from finance.sources import prices as _prices
from finance.sources import universe as _universe

from finance.mcp._server import create, safe_name, spill

SERVER = create(
    "finance-market",
    "Indian market data: live and end-of-day prices, index levels and valuation, breadth, "
    "institutional flows, the cross-asset macro backdrop, the plugin's shared "
    "market-of-record, and the engines that run a strategy spec over price history "
    "(live screen and historical backtest).",
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
    description="Indicator read for one NSE symbol on split- and bonus-adjusted daily "
                "candles, computed by the plugin's indicator-of-record (TA-Lib via "
                "ta.py, the same columns the screens and backtest use): EMA 20/50/200, "
                "SMA 200, RSI 14, ATR 14, MACD, Bollinger, 10-day volume average, "
                "20-day high/low, plus any `features` tokens (ema100, rsi9, hh50, nr7). "
                "`patterns_latest` names the candlestick and signal patterns on the last "
                "bar. Every bar's row is written to `rows_path`; `keep` rows come back "
                "inline. `drop_last` excludes an unclosed final session."
)
def get_technicals(symbol: str, period: str = "1y", features: list | None = None,
                   drop_last: bool = False, keep: int = 5, fresh: bool = False) -> dict:
    return spill(_technicals.report(symbol, period=period, features=features,
                                    drop_last=drop_last, fresh=fresh),
                 "rows", f"technicals-{safe_name(symbol)}-{safe_name(period)}", keep=keep)


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
def run_technical_screen(filters: list | dict, columns: list | None = None,
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
    description="Resolve a named universe to its NSE symbols: nifty50|nifty100|nifty200|"
                "nifty500|microcap|fno|largecap20, or a list / comma-string / file path. "
                "The symbol list is written to a dated file and NOT returned inline — the "
                "response carries `symbols_count` and `universe_path`; read the file for the "
                "symbols. Named universes come from NSE's published constituent CSVs; a "
                "failed fetch falls back to the newest cached copy as a labelled gap."
)
def get_universe(name: str, fresh: bool = False) -> dict:
    return _universe.resolve(name, fresh=fresh)


@SERVER.tool(
    description="Run a strategy spec's screening and signal rules over a universe today: "
                "each survivor comes back with entry, stoploss, target, reward:risk and "
                "risk-sized quantity. `spec` is the path to a strategy YAML — the rules "
                "always come from a spec, never from the caller. `symbols` is a list, a "
                "comma-separated string, a named universe, or a path to a symbols file; "
                "omit it to use the spec's own universe.source. Every rejection and its "
                "reason is in the written report."
)
def run_strategy_screen(spec: str, symbols: list | str | None = None, years: int = 2,
                        capital: float = 500000, out: str | None = None) -> dict:
    return _screen.run(spec, symbols, years=years, capital=capital, out=out)


@SERVER.tool(
    description="Investment stock discovery scan: run the spec's business-quality query "
                "through the Tickertape screener, intersect the survivors with the spec's "
                "named universe, rank by ranking.metric (return_12m | return_6m | "
                "rs_vs_nifty) and cap to the top N. NO entry/stop/target/size and no "
                "backtest — this picks what to deep-dive, not when to enter. `spec` is the "
                "path to an investment strategy YAML; the ranked shortlist is written to "
                "file and the response carries the summary."
)
def run_stock_scan(spec: str, top: int = 5, fresh: bool = False,
                   out: str | None = None) -> dict:
    return _stock_scan.report(_load_yaml(spec), top=top, fresh=fresh, out=out)


@SERVER.tool(
    description="Sector discovery scan: rank the NSE sectoral indices by the spec's metric "
                "(rs_vs_nifty — RS vs Nifty over 1M/3M/6M, classified "
                "Improving/Leading/Weakening/Lagging — by default; or "
                "index_valuation_percentile, cheapest first) and take the top N. `spec` is "
                "the path to a sector YAML, or omit it for the built-in RS spec. The ranked "
                "shortlist is written to file and the response carries the summary."
)
def run_sector_screen(spec: str | None = None, top: int = 3, fresh: bool = False,
                      out: str | None = None) -> dict:
    return _sector_scan.report(_load_yaml(spec) if spec else None, top=top,
                               fresh=fresh, out=out)


@SERVER.tool(
    description="Backtest a strategy spec on historical NSE daily data (Backtesting.py: "
                "no lookahead, stop wins a bar that touches both stop and target). "
                "Returns win rate, expectancy, profit factor and the worst single-symbol "
                "drawdown. Each symbol is a separate account, and return counts accounts "
                "that never traded; this is not a portfolio simulation. The summary JSON "
                "and trade/equity CSVs are at the returned paths. `symbols` accepts 'largecap20' for the 20-stock liquid "
                "large-cap basket. Historical validation only — never a live signal."
)
def run_backtest(spec: str, symbols: list | str, years: int = 5,
                 capital: float = 500000, risk_pct: float | None = None,
                 out: str | None = None) -> dict:
    return _backtest.run(spec, symbols, years=years, capital=capital,
                         risk_pct=risk_pct, out=out)


def main():
    SERVER.run("stdio")


if __name__ == "__main__":
    main()
