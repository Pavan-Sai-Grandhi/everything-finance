# Seed strategy library

Starter strategy specs distilled from common Indian swing-trading methods
(`.refs/swing-strategies.txt`). They exist so you don't start from a blank page —
**but every one ships as `status: draft` and is NOT tradeable until you validate it.**
strategy-manager's discipline still binds: a draft is a hypothesis, not an edge.

## How to use one

```bash
# 1. copy a seed into your live library (session cwd)
mkdir -p artifacts/strategies && cp ema-pullback-swing.yml artifacts/strategies/
# 2. do the mandatory TradingView visual study + backtest, then validate
/strategy-manager validate ema-pullback-swing
# 3. once active, find-trade can run it (or pick it for the regime)
/find-trade strategy:ema-pullback-swing      # or just /find-trade -> pick
```

Validation is not a formality: the **mechanical EMA-pullback backtested to *negative*
expectancy** in the bundled backtest when stripped of its reversal-candle + tested-S/R
filters (see `find-trade/references/reference.md`). Seeds encode the *idea*; only your
backtest tells you whether this parameterisation has an edge on a real basket.

## What's here, and how it relates to the breakout example spec

The documented example spec (`../strategy-spec.example.yml`) is a **breakout-momentum**
system. The seeds add the methods it doesn't cover:

| Seed | Method (refs §3) | Relation to the example breakout spec |
|---|---|---|
| `ema-pullback-swing` | 1 — MA Pullback (20/50 EMA) | **distinct** — enters a pullback, not a breakout |
| `breakout-retest-swing` | 2 — Breakout + Retest | **variant** — same breakout, but enters on the retest (fewer false breaks) |
| `rsi-trendline-reversal-swing` | 3 — RSI + Trendline | **distinct** — trendline touch with RSI in the 38–45 trend-support zone |
| `inside-bar-nr7-swing` | 4 — Inside / NR4-NR7 | **distinct** — volatility-squeeze expansion (compute-path screen; TV has no NR filter) |
| `fibonacci-retracement-swing` | 5 — Fibonacci | **distinct** — 38–62% retracement of an impulse leg |

**Refs §3 Strategy 6 — Multi-Timeframe — is deliberately NOT a separate spec.** It is an
*overlay*, not a setup: "confirm the weekly trend, enter on the daily, time with the
intraday." Encode it inside any of the above by (a) keeping `regime_required.nifty_above:
ema200` as the higher-timeframe gate and (b) the entry's daily trigger — rather than as a
standalone strategy with no entry of its own. (This plugin's horizon is daily/weekly, never
intraday, per CLAUDE.md, so the 4-hour leg becomes "confirm on the daily close".)

## The screening block

Each seed populates the `screening` block the schema now carries: a **screener.in**
fundamental cut and a **technical** cut that is either `provider: tradingview` (server-side
filters) or `provider: compute` (local `lib/ta.py`) where TradingView can't express the
filter (NR-bars, fib zones). `fallback_compute: true` everywhere means find-trade reproduces
the cut locally from yfinance if a provider is unreachable. See `find-trade` for how these run.
