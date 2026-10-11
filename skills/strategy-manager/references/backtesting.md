# Backtesting — engine contract and methodology

The historical-validation half of the lifecycle: what `run_backtest` does to a spec, the biases
that fake an edge, and how to read the metrics it returns. The system framework, the activation
gate and the optimization rules are in `reference.md`.

Sources (fetched 2026-06-10): Varsity *Trading Systems*; QuantInsti backtesting guide (https://www.quantinsti.com/articles/backtesting-trading/); Marketcalls on look-ahead bias (https://www.marketcalls.in/python/understanding-look-ahead-bias-and-how-to-avoid-it-in-trading-strategies.html); ForTraders bias guide (https://www.fortraders.com/blog/how-to-avoid-bias-in-backtesting).

## The four biases that fake an edge

1. **Look-ahead bias** — using information not available at decision time. Defenses baked into the engine: signals computed on bar *t* close, execution at bar *t+1* open; indicators use only trailing windows; no same-bar entry+exit on the signal bar. When both SL and target fall inside one bar's range, assume **SL hit first** (pessimistic tie-break).
2. **Survivorship bias** — testing only today's index members overstates returns (the delisted losers are missing). Our data source (yfinance, current symbols) **does not reconstruct historical membership** — always disclose this limitation. Its effect is unmeasured here; do not apply a guessed annual return adjustment.
3. **Overfitting / data-snooping** — tuning parameters until the past looks great. Defense: a spec's parameters are fixed from its source article (e.g. 20-day breakout, 50-EMA, 1.5× volume), not optimized. If the user asks to tune, insist on a train/test split: tune on the older 70%, report only the untouched recent 30% (simple walk-forward).
4. **Cost blindness** — the engine charges a fixed **model assumption** of 0.125% per side, approximately 0.25% round trip. This is not a quote of current broker tariffs and does not model each tax, brokerage fee, DP charge or market impact separately. Test cost sensitivity before relying on a small apparent edge; actual execution costs can differ.


## Metrics and how to read them

- **Expectancy (in R)** is the number the verdict maps from, and **win rate** on its own decides nothing — both are defined and thresholded in `reference.md` § *Expectancy*.
- **Profit factor** = positive net trade P&L / absolute negative net trade P&L. Above one means the closed sample made money; assess sample size and outlier contribution before inferring an edge. With no losing P&L it is undefined (`null`), not Infinity.
- **Max drawdown** — `max_dd_on_equity_pct` is the worst individual account's daily marked drawdown, including the initial cash peak and losses while a trade remains open. `max_drawdown_symbol` identifies which buy-and-hold series to compare. It is not portfolio drawdown. Inspect the returned equity CSV to verify it.
- **Yearly breakdown** — an edge that exists only in 2024's bull leg is a bull-market detector, not a strategy. Use `by_year_expectancy_R` (regime check in R beats rupee PnL); realized P&L and R belong to the exit year, and the current year is flagged "(partial)".
- **Return-on-capital vs buy-and-hold**: each symbol has an independent account. `return_on_capital_pct` uses total initial capital across all successful tests, including zero-trade accounts. Compare corresponding symbols and date windows; capital utilization can differ substantially from fully invested buy-and-hold. This is not a portfolio allocation simulation.
- **exit_breakdown**: labels are SL / TARGET / TIME (held to the time-stop) / SIGNAL/OTHER (an `exit_signal` close). Two diagnoses: **TIME > 50%** with a fixed target = the target/time-stop pairing doesn't fit the universe's volatility — if the source actually *trails*, that's a sign the spec should use `trail_atr`, not a longer time-stop (a long time-stop is a kludge for a trailing exit, and lengthening it in-sample to chase a number is curve-fitting). **Note when `trail_atr` is set, an SL exit is often a trailing-stop exit on a *winner*, not a loss** — read SL alongside the per-trade R, don't assume SL = loss.
- **Resuming a crashed run**: use a completed returned `summary_path` and its referenced evidence files. Confirm the spec, parameters, symbols, price dates and gaps match the intended run before reuse. A matching filename or an old cache alone does not prove the run completed. Changed reruns write new content-addressed files.

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

- **spec** — an `artifacts/state/strategies/<name>.yml` or a seed under `assets/seed-strategies/`. The engine reads `entry.signal` (the machine-readable trigger — required; a missing or empty signal is refused before any fetch, never replaced by `screening.technical.compute_filters`), `exit.{stop,target,min_rrr,time_stop_sessions}`, and `sizing.risk_per_trade_pct`.
- **symbols** — a comma-separated list, or `"largecap20"` for the built-in basket. `years` defaults to 5; `capital` and `risk_pct` (which overrides the spec's `sizing.risk_per_trade_pct`) size the book; `out` defaults to `paths.backtest_dir(spec, date)`.
- **entry** — next-bar open after `entry.signal` fires; one position at a time per symbol. Final-bar signals cannot fill: forced finalization is disabled because it replays the last bar. Still-open positions are counted in `open_trades_at_end` and marked in account equity, but do not enter closed-trade expectancy or `total_pnl`. `total_account_pnl` includes their marks, excluding unpaid exit charges. Review them before interpreting the closed sample.
- **stop** — from `exit.stop` (`recent_swing_low` | `ema50_minus_2atr` | `range_low`), floored at the wider of 0.5×ATR14 and 1% of price; too-wide (> 15%) or malformed stops are skipped, and so are warm-up bars without a finite ATR14 — exactly as the live screen skips them.
- **target** — from `exit.target` (exact `measured_move` → prior 20-bar range height; `min_rrr` or legacy `next_resistance` → risk-multiple proxy; `trailing`/`signal`/`none` → no fixed take-profit with the corresponding exit configured); entries below `min_rrr` are not taken.
- **exit** — stop / target intrabar (stop wins ties), else `exit.time_stop_sessions` time stop. An open that gaps through the stop or target fills beyond the level and is still labelled SL / TARGET. Commission ~0.25% round trip, charged per side.
- **output** — `summary_path` for the JSON summary, `trades_path` for full-precision trades, and `equity_path` for dated per-symbol equity. Filenames include content hashes; use returned paths. R uses the actual next-open fill and original stop, preserved even when trailing changes the active stop. Missing risk leaves R/expectancy unknown. The markdown report is written on top of them, not by the engine.

Keep validation on the same spec interpreter and Backtesting.py engine as live screening. Add another engine only after a measured bottleneck justifies its maintenance cost and execution-parity tests; a faster parameter sweep can also accelerate overfitting.

## What this backtest does NOT test (state in every report)

- The strategy's **fundamental screen** (the engine does not load dated fundamental screening inputs)
- Discretionary S/R zone quality and candlestick pattern reading (only mechanical triggers are coded)
- Liquidity/impact for position sizes beyond retail scale
