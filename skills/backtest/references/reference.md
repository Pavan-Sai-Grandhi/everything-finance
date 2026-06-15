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
- **exit_breakdown**: labels are SL / TARGET / TIME (held to the time-stop) / SIGNAL/OTHER (an `exit_signal` close). Two diagnoses: **TIME > 50%** with a fixed target = the target/time-stop pairing doesn't fit the universe's volatility — if the source actually *trails*, that's a sign the spec should use `trail_atr`, not a longer time-stop (a long time-stop is a kludge for a trailing exit, and lengthening it in-sample to chase a number is curve-fitting). **Note when `trail_atr` is set, an SL exit is often a trailing-stop exit on a *winner*, not a loss** — read SL alongside the per-trade R, don't assume SL = loss.
- **Resuming a crashed run**: outputs are deterministic given the OHLCV cache — validate the existing summary JSON (has `summary`/`buy_and_hold`/`caveats`) instead of re-running.

## Engine (what runs under the hood)

The backtester is **strategy-agnostic** and built on credible libraries, not a hand-rolled loop:
- **Backtesting.py** runs the simulation. Its defaults are the discipline a real-money test needs: no lookahead (signal on bar *t* → fill at *t+1* open) and **pessimistic intrabar exits** (when stop and target are both touched in one bar, the **stop** is taken). Verified against synthetic bars where the answer is known.
- **`lib/strategy.py`** turns the spec into entry/stop/target/size — the *same* module find-trade's live screen uses, so a stock can't pass the live screen on logic the backtest computes differently.
- **TA-Lib** (via `lib/ta.py`) computes the indicators — the industry-standard reference (EMA is SMA-seeded, ATR is Wilder).

If the user later needs **parameter sweeps** across many symbols/params, `vectorbt` is the right addition (vectorized, fast) — reserve it for `strategy-manager optimize`, keeping Backtesting.py as the auditable validation engine. `backtrader` is featureful but maintenance has slowed; avoid for new work.

## What this backtest does NOT test (state in every report)

- The strategy's **fundamental screen** (point-in-time fundamentals aren't freely available — historical screens can't be reproduced)
- Discretionary S/R zone quality and candlestick pattern reading (only mechanical triggers are coded)
- Liquidity/impact for position sizes beyond retail scale
