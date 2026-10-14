# Backtesting — engine contract and methodology

The historical-validation half of the lifecycle: what `run_backtest` does to a spec, the biases
that fake an edge, and how to read the metrics it returns. The system framework, the activation
gate and the optimization rules are in `reference.md`.

Sources (fetched 2026-06-10): Varsity *Trading Systems*; QuantInsti backtesting guide (https://www.quantinsti.com/articles/backtesting-trading/); Marketcalls on look-ahead bias (https://www.marketcalls.in/python/understanding-look-ahead-bias-and-how-to-avoid-it-in-trading-strategies.html); ForTraders bias guide (https://www.fortraders.com/blog/how-to-avoid-bias-in-backtesting).

## The four biases that fake an edge

1. **Look-ahead bias** — using information not available at decision time. Defenses baked into the engine: signals computed on bar *t* close, execution at bar *t+1* open; indicators use only trailing windows; no same-bar entry+exit on the signal bar. When both SL and target fall inside one bar's range, assume **SL hit first** (pessimistic tie-break).
2. **Survivorship bias** — testing only today's index members overstates returns (the delisted losers are missing). Our data source (yfinance, current symbols) **does not reconstruct historical membership**, so always disclose it. Its size is unknown here; do not apply a guessed adjustment.
3. **Overfitting / data-snooping** — tuning parameters until the past looks great. Defense: a spec's parameters are fixed from its source article (e.g. 20-day breakout, 50-EMA, 1.5× volume), not optimized. If the user asks to tune, insist on a train/test split: tune on the older 70%, report only the untouched recent 30% (simple walk-forward).
4. **Cost blindness** — the engine charges an assumed 0.125% per side, about 0.25% round trip. That is not a current broker tariff and does not model taxes, DP charges or market impact one by one. Test a higher cost before trusting a small edge.


## Metrics and how to read them

- **Expectancy (in R)** is the number the verdict maps from, and **win rate** on its own decides nothing — both are defined and thresholded in `reference.md` § *Expectancy*.
- **Profit factor** = gross winning P&L / gross losing P&L. Above 1 means the closed trades made money; check the sample size and whether one outlier carries it. With no losing trades it is `null`.
- **Max drawdown** — `max_dd_on_equity_pct` is the worst single account's daily drawdown, counting starting cash as a peak and open-trade losses. `max_drawdown_symbol` names the buy-and-hold series to compare it with. It is not a portfolio drawdown; the equity CSV shows the curve.
- **Yearly breakdown** — an edge that exists only in 2024's bull leg is a bull-market detector, not a strategy. Use `by_year_expectancy_R` (regime check in R beats rupee PnL); realized P&L and R belong to the exit year, and the current year is flagged "(partial)".
- **Return-on-capital vs buy-and-hold**: each symbol is its own account. `return_on_capital_pct` divides by the starting capital of every successful test, including accounts that never traded. Compare symbol by symbol over the same dates, remembering the strategy is often in cash while buy-and-hold never is.
- **exit_breakdown**: labels are SL / TARGET / TIME (held to the time-stop) / SIGNAL/OTHER (an `exit_signal` close). Two diagnoses: **TIME > 50%** with a fixed target = the target/time-stop pairing doesn't fit the universe's volatility — if the source actually *trails*, that's a sign the spec should use `trail_atr`, not a longer time-stop (a long time-stop is a kludge for a trailing exit, and lengthening it in-sample to chase a number is curve-fitting). **Note when `trail_atr` is set, an SL exit is often a trailing-stop exit on a *winner*, not a loss** — read SL alongside the per-trade R, don't assume SL = loss.
- **Resuming a crashed run**: reuse a `summary_path` the tool returned, after checking that its spec, parameters, symbols and dates match the run you want. A file that merely exists is not proof the run finished.

## Engine contract — how `run_backtest` trades a spec

The engine is **strategy-agnostic**: entry, stop, target, time-stop and sizing all come from the
spec. **Backtesting.py** runs the simulation, `finance/compute/strategy.py` turns the spec into
entry/stop/target/size — the *same* module discover's live screen uses, so a stock cannot pass
the live screen on logic the backtest computes differently — and **TA-Lib** (via
`finance/compute/ta.py`) computes the indicators (EMA is SMA-seeded, ATR is Wilder).

```
run_backtest(spec="artifacts/state/strategies/ema-pullback-swing.yml",
             symbols="RELIANCE,TCS,HDFCBANK", years=5, capital=500000)
```

- **spec** — an `artifacts/state/strategies/<name>.yml` or a seed under `assets/seed-strategies/`. The engine reads `entry.signal` (the machine-readable trigger — required; without it the spec is refused before any fetch), `exit.{stop,target,min_rrr,time_stop_sessions}`, and `sizing.risk_per_trade_pct`.
- **symbols** — a comma-separated list, or `"largecap20"` for the built-in basket. `years` defaults to 5; `capital` and `risk_pct` (which overrides the spec's `sizing.risk_per_trade_pct`) size the book; `out` defaults to `paths.backtest_dir(spec, date)`.
- **entry** — next-bar open after `entry.signal` fires; one position at a time per symbol. A signal on the last bar does not fill. Positions still open at the end are counted in `open_trades_at_end` and included in `total_account_pnl`, but not in expectancy or `total_pnl`.
- **stop** — from `exit.stop` (`recent_swing_low` | `ema50_minus_2atr` | `range_low`), floored at the wider of 0.5×ATR14 and 1% of price. A stop wider than 15%, a malformed stop, or a warm-up bar with no ATR14 is skipped, as in the live screen.
- **target** — from `exit.target`: `measured_move` uses the prior 20-bar range; `min_rrr` (old name `next_resistance`) sets the target at the minimum reward:risk; `trailing`, `signal` and `none` have no fixed target. Entries below `min_rrr` are not taken.
- **exit** — stop / target intrabar (stop wins ties), else `exit.time_stop_sessions` time stop. An open that gaps through the stop or target fills at the open and is still labelled SL or TARGET. Commission ~0.25% round trip, charged per side.
- **output** — `summary_path` (JSON summary), `trades_path` (trades) and `equity_path` (daily equity per symbol); the names include a content hash, so use the returned paths. R is measured from the actual fill to the original stop, even after a trailing stop moves. You write the markdown report from these files.

Validation uses the same spec interpreter and Backtesting.py engine as live screening. Add another engine only if speed becomes a measured problem, and only with tests that it executes the same way; faster sweeps also make overfitting easier.

## What this backtest does NOT test (state in every report)

- The strategy's **fundamental screen** (the engine does not load dated fundamental screening inputs)
- Discretionary S/R zone quality and candlestick pattern reading (only mechanical triggers are coded)
- Liquidity/impact for position sizes beyond retail scale
