# Backtesting methodology reference

Compiled 2026-06-10 from web research and Varsity Trading Systems framing. Sources: QuantInsti backtesting guide (https://www.quantinsti.com/articles/backtesting-trading/), Marketcalls on look-ahead bias (https://www.marketcalls.in/python/understanding-look-ahead-bias-and-how-to-avoid-it-in-trading-strategies.html), ForTraders bias guide (https://www.fortraders.com/blog/how-to-avoid-bias-in-backtesting), library comparison (https://www.qmr.ai/best-backtesting-library-for-python/).

## The four biases that fake an edge

1. **Look-ahead bias** — using information not available at decision time. Defenses baked into the bundled script: signals computed on bar *t* close, execution at bar *t+1* open; indicators use only trailing windows; no same-bar entry+exit on the signal bar. When both SL and target fall inside one bar's range, assume **SL hit first** (pessimistic tie-break).
2. **Survivorship bias** — testing only today's index members overstates returns (the delisted losers are missing). Our data source (yfinance, current symbols) **has this bias and it cannot be fully fixed for free** — always disclose it; treat absolute returns as optimistic by roughly 1–4%/yr at portfolio level.
3. **Overfitting / data-snooping** — tuning parameters until the past looks great. Defense: parameters here are fixed from Varsity rules (20-day breakout, 50-EMA, 1.5× volume), not optimized. If the user asks to tune, insist on a train/test split: tune on the older 70%, report only the untouched recent 30% (simple walk-forward).
4. **Cost blindness** — Indian delivery round trip ≈ 0.10–0.12% in charges (STT 0.1% both sides dominates; brokerage ₹0 on delivery for discount brokers) plus slippage; the script defaults to 0.25% round trip total as a conservative all-in figure.

## Metrics and how to read them

- **Expectancy (in R)** = (win% × avg win in R) − (loss% × avg loss in R). The single most important number: >0.2R with a real sample = tradeable edge; 0–0.2R = fragile; <0 = no edge regardless of win rate.
- **Win rate** alone is marketing — a 35% win rate with 2.5R winners beats a 65% win rate with 0.5R winners.
- **Profit factor** = gross profit / gross loss; > 1.5 healthy, > 2 suspicious (check for one outlier trade carrying everything — the script's trade log makes this checkable).
- **Max drawdown** — compare against buy-and-hold's drawdown; the legitimate reason a lower-return strategy can win.
- **Sample size**: < 30 trades = anecdote, not statistics. Widen symbols/years before concluding.
- **Yearly breakdown** — an edge that exists only in 2024's bull leg is a bull-market detector, not a strategy. Use `by_year_expectancy_R` (regime check in R beats rupee PnL); the current year is flagged "(partial)".
- **Return-on-capital vs buy-and-hold**: under 1%-risk sizing most capital sits idle, so return_on_capital_pct is *not* comparable to fully-invested B&H — compare expectancy and drawdown instead, and state this in the report.
- **exit_breakdown**: TIME exits > 50% means the 2R-target/20-session pairing doesn't fit the universe's volatility — that diagnosis goes in the report; do not tune parameters in-sample to fix it.
- **Resuming a crashed run**: outputs are deterministic given the OHLCV cache — validate the existing summary JSON (has by_strategy/buy_and_hold/caveats) instead of re-running.

## Library landscape (if the user outgrows the bundled script)

- `backtesting.py` — simplest, great reports, single-asset focus.
- `vectorbt` — fastest for parameter sweeps across many symbols; steep, opinionated API.
- `backtrader` — most featureful event-driven engine; aging but battle-tested.
The bundled pandas script is deliberately dependency-light and transparent — every rule is readable in ~50 lines. Prefer extending it over adding a framework until parameter optimization is genuinely needed.

## What this backtest does NOT test (state in every report)

- The strategy's **fundamental screen** (point-in-time fundamentals aren't freely available — historical screens can't be reproduced)
- Discretionary S/R zone quality and candlestick pattern reading (only mechanical triggers are coded)
- Liquidity/impact for position sizes beyond retail scale
