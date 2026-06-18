---
name: backtest
description: Backtest a strategy spec on historical NSE daily data — runs the bundled Backtesting.py engine (driven by the shared lib/strategy.py spec interpreter on lib/ta.py / TA-Lib indicators) on any strategy-manager spec's rules, reporting win rate, expectancy, profit factor, max drawdown vs buy-and-hold. Use whenever the user asks to backtest, validate, or "check if this strategy actually works", wants historical performance of a setup, or after find-trade produces signals and the user questions the strategy's edge.
argument-hint: "--spec <strategy>.yml TICKER(s) or 'largecap20' [years, default 5]"
allowed-tools: Read, Write, Bash
---

# Backtest — historical validation of a strategy spec

Read `references/reference.md` first — it carries the methodology (bias traps, cost model, how to read the metrics) and must shape how you present results.

No web scraping: data comes from Yahoo Finance via `yfinance` (`.NS` suffix for NSE symbols), cached under `artifacts/cache/ohlcv/`. This skill validates **rules**, not stock picks — it answers "does this setup have an edge?", never "will this trade win?".

**This backtester is strategy-AGNOSTIC.** It carries no built-in setups: the entry condition, stop, target, time-stop and sizing all come from the `strategy-manager` spec you point it at, interpreted by the shared `lib/strategy.py` — the *same* module find-trade's live screen uses, so a stock cannot pass the live screen on logic the backtest computes differently. A new strategy becomes testable by *existing*; there is no per-archetype code to extend. The simulation runs on **Backtesting.py** (no-lookahead next-open fills; pessimistic intrabar exits — stop taken when stop and target are both hit in one bar), indicators via **TA-Lib** (`lib/ta.py`).

**Spec required.** Always invoke against a `strategy-manager` spec (`artifacts/state/strategies/<name>.yml` or a seed under `strategy-manager/assets/seed-strategies/`) — usually because `strategy-manager` is driving you in its VALIDATE mode. The engine reads `entry.signal` (the machine-readable trigger; falls back to `screening.technical.compute_filters` if absent), `exit.{stop,target,min_rrr,time_stop_sessions}`, and `sizing.risk_per_trade_pct`. After the run **write the results back** into the spec's `expectancy_assumptions` (`win_rate`, `expectancy_R`, `profit_factor`, `n_trades`, `validated_by` = the summary artifact path). You report the numbers and the verdict; **`strategy-manager` owns the lifecycle decision** — it applies the activation gate (`expectancy_R > 0.2` over ≥ ~30 trades → `status: active`) and flips the status. Don't set `status` yourself.

## Run it

The bundled script does the heavy lifting — use it, don't reimplement:

```bash
# run from the session cwd (artifacts land under ./artifacts/), script via its absolute skill path:
python3 <skill-dir>/scripts/backtest.py \
  --spec artifacts/state/strategies/ema-pullback-swing.yml \
  --symbols RELIANCE,TCS,HDFCBANK --years 5 --capital 500000
# --out defaults to artifacts/backtest/<spec>/YYYY-MM-DD/report (via lib/paths.py)
```

(`--symbols largecap20` expands to a built-in **20-stock** liquid large-cap basket — it is *not* the full Nifty 50; name it as "20-stock large-cap basket" in the report. `--risk-pct` overrides the spec's `sizing.risk_per_trade_pct`. The script auto-installs `yfinance`/`pandas`/`backtesting`; TA-Lib needs its native lib — `brew install ta-lib` — which `lib/ta.py` bootstraps. `--selftest` runs offline on synthetic data.)

How the engine trades the spec (it matches find-trade's live screen by construction — both go through `lib/strategy.py`; simplifications are listed in reference.md and must be mentioned in output):
- **entry**: next-bar open after `entry.signal` fires (one position at a time per symbol; no lookahead)
- **stop**: from `exit.stop` (`recent_swing_low` | `ema50_minus_2atr` | `range_low`); too-wide (> 15%) or malformed stops are skipped
- **target**: from `exit.target` (`measured_move` → prior consolidation height; else a next-resistance proxy at `min_rrr`); entries below `min_rrr` are not taken
- **exit**: stop / target intrabar (stop wins ties), else `exit.time_stop_sessions` time stop. Commission ~0.25% round trip (charged per side).

## Interpret — this is the actual skill

The script writes a **JSON summary and a trade-log CSV only** — the markdown summary is *your* deliverable, built from those. Your job on top:

1. **Verdict** (the run tests one spec; read `summary`), mapped explicitly from `expectancy_R`: < 0R = **no edge**; 0–0.2R = **no tradeable edge (fragile)**; > 0.2R with ≥ 30 trades = **edge**; < 30 trades = **inconclusive — insufficient sample** regardless of expectancy.
2. **Honesty checks** (from reference.md): in-sample only? survivorship (current constituents)? regime concentration (did all profit come from one bull year — check the yearly breakdown)? Say these out loud in the report.
3. **Compare vs buy-and-hold** of the same symbols — but note that return-on-capital under 1%-risk sizing leaves most capital idle and is *not* directly comparable to fully-invested B&H; lean on expectancy and drawdown for the comparison and say so in the report. Also check `exit_breakdown`: if TIME exits dominate (> 50%), the target/time-stop pairing is mis-specified for the universe — report that as the diagnosis, don't tune parameters in-sample.
4. If the user came from find-trade: state clearly what was and wasn't tested (the backtest tests the technical trigger mechanics, not the fundamental screen or discretionary S/R reading).

Save the summary to `artifacts/backtest/<spec-name>/YYYY-MM-DD/report.md` (i.e. `paths.backtest_dir(spec, date)`) alongside the script's CSV outputs. End with: backtests describe the past; live edge degrades — position sizing discipline is what survives.
