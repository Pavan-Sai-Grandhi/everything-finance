---
name: backtest
description: Backtest swing trading rules on historical NSE daily data — runs the bundled pandas backtester on the swing-trading setups (breakout, EMA pullback) or custom rules, reporting win rate, expectancy, profit factor, max drawdown vs buy-and-hold. Use whenever the user asks to backtest, validate, or "check if this strategy actually works", wants historical performance of a setup, or after swing-trading produces signals and the user questions the strategy's edge.
argument-hint: "TICKER(s) or 'largecap20' [strategy: breakout|pullback|both] [years, default 5]"
allowed-tools: Read, Write, Bash
---

# Backtest — historical validation of swing rules

Read `references/reference.md` first — it carries the methodology (bias traps, cost model, how to read the metrics) and must shape how you present results.

No web scraping: data comes from Yahoo Finance via `yfinance` (`.NS` suffix for NSE symbols), cached under `artifacts/.cache/ohlcv/`. This skill validates **rules**, not stock picks — it answers "does this setup have an edge?", never "will this trade win?".

**Strategy spec (optional):** if invoked against a `strategy-manager` spec (`artifacts/strategies/<name>.yml`) — usually because `strategy-manager` is driving you in its VALIDATE mode — read its `entry`/`exit`/`sizing` as the rules to test, and after the run **write the results back** into the spec's `expectancy_assumptions` (`win_rate`, `expectancy_R`, `profit_factor`, `n_trades`, `validated_by` = the summary artifact path). You report the numbers and the verdict; **`strategy-manager` owns the lifecycle decision** — it applies the activation gate (`expectancy_R > 0.2` over ≥ ~30 trades → `status: active`) and flips the status. Don't set `status` yourself. The bundled script's built-in breakout/pullback strategies are the default when no spec is given.

## Run it

The bundled script does the heavy lifting — use it, don't reimplement:

```bash
# run from the session cwd (artifacts land under ./artifacts/), script via its absolute skill path:
python3 <skill-dir>/scripts/backtest.py --symbols RELIANCE,TCS,HDFCBANK --strategy both --years 5 \
  --capital 500000 --risk-pct 1.0 --out artifacts/YYYY-MM-DD/backtest
```

(`--symbols largecap20` expands to a built-in **20-stock** liquid large-cap basket — it is *not* the full Nifty 50; name it as "20-stock large-cap basket" in the report. `nifty50` is accepted as a deprecated alias. The script auto-installs `yfinance`/`pandas` if missing.)

Strategies implemented (faithful, simplified versions of the swing-trading setups — the simplifications are listed in reference.md and must be mentioned in output):
- **breakout**: close above the prior 20-session high after ≥20 sessions of consolidation, volume > 1.5× 10-day average; entry next open
- **pullback**: price above rising 50-EMA, low touches the EMA zone, close back above it; entry next open
- Exits for both: structural SL (pattern low / EMA−2×ATR), 2R target, 20-session time stop. Costs default 0.25% round trip.

## Interpret — this is the actual skill

The script writes a **JSON summary and a trade-log CSV only** — the markdown summary is *your* deliverable, built from those. Your job on top:

1. **Verdict per strategy**, mapped explicitly from expectancy: < 0R = **no edge**; 0–0.2R = **no tradeable edge (fragile)**; > 0.2R with ≥ 30 trades = **edge**; < 30 trades = **inconclusive — insufficient sample** regardless of expectancy.
2. **Honesty checks** (from reference.md): in-sample only? survivorship (current constituents)? regime concentration (did all profit come from one bull year — check the yearly breakdown)? Say these out loud in the report.
3. **Compare vs buy-and-hold** of the same symbols — but note that return-on-capital under 1%-risk sizing leaves most capital idle and is *not* directly comparable to fully-invested B&H; lean on expectancy and drawdown for the comparison and say so in the report. Also check `exit_breakdown`: if TIME exits dominate (> 50%), the target/time-stop pairing is mis-specified for the universe — report that as the diagnosis, don't tune parameters in-sample.
4. If the user came from swing-trading: state clearly what was and wasn't tested (the backtest tests the technical trigger mechanics, not the fundamental gate or discretionary S/R reading).

Save the summary to `artifacts/YYYY-MM-DD/backtest-<strategy>.md` alongside the script's CSV outputs. End with: backtests describe the past; live edge degrades — position sizing discipline is what survives.
