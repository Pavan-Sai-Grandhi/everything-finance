# How `run_backtest` trades a spec

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
- **target** — from `exit.target`: `measured_move` uses the prior 20-bar range; `min_rrr` sets the target at the minimum reward:risk; `trailing`, `signal` and `none` have no fixed target. Entries below `min_rrr` are not taken.
- **exit** — stop / target intrabar (stop wins ties), else `exit.time_stop_sessions` time stop. An open that gaps through the stop or target fills at the open and is still labelled SL or TARGET. Commission ~0.25% round trip, charged per side.
- **output** — `summary_path` (JSON summary), `trades_path` (trades) and `equity_path` (daily equity per symbol); the names include a content hash, so use the returned paths. R is measured from the actual fill to the original stop, even after a trailing stop moves. You write the markdown report from these files.

## What a backtest does not test (state it in every report)

- The strategy's **fundamental screen** (the engine does not load dated fundamental screening inputs)
- Discretionary S/R zone quality and candlestick pattern reading (only mechanical triggers are coded)
- Liquidity/impact for position sizes beyond retail scale

**Resuming a crashed run:** reuse a `summary_path` the tool returned, after checking that its spec, parameters, symbols and dates match the run you want. A file that merely exists is not proof the run finished.
