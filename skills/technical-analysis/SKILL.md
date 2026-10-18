---
name: technical-analysis
description: >-
  Read the chart for one NSE stock — Dow trend stage, the support/resistance map with touch-count evidence, the active candlestick or structural pattern in its location context, the volume signature, RSI/MACD as confirmation only, and the two price levels that invalidate a bull or a bear thesis. Use whenever the user wants the chart view on a ticker — "what do the charts say on X", "is X in an uptrend", "where is support / resistance", "is this a breakout or a fakeout", "what is the RSI/MACD saying", "where would my stop go on X", "is it overbought" — even when they never say "technical analysis". This is the chart read on one stock: scanning the whole market against a strategy is discover, testing a strategy on history is strategy-manager, and the full bull/bear debate is deep-analysis.
argument-hint: "TICKER"
allowed-tools: Read, Write, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*
---

# Technical Analysis: the chart read on one NSE ticker

Every level cites its evidence (touch dates and counts, never an eyeballed round number), and
indicators never override price structure. No trade advice beyond the levels: sizing and the
call belong to the caller.

**Method:** `methods/technical.md`.

## Workflow

1. **Inputs**: the ticker and, from an orchestrator, an output path.
2. **The series**: `get_quote(symbol)` for the live bar, then `get_technicals(symbol,
   period="1y")` for the indicator columns on adjusted candles, and read every bar at
   `rows_path`. If the last bar is an unclosed session (mid-session, or shortly after the close,
   its high or low is provisional or missing), call again with `drop_last: true` so no level, range
   or ATR stop is struck on it. Say which session the levels are struck on.
3. **Work the checklist in the method's order**: pattern, support and resistance, volume, Dow
   stage, indicators.
4. **Name both invalidation levels**, each with its touch evidence.

## Report

```
<!-- technical-block
verdict: bullish | bearish | neutral   confidence: low | med | high
trend_stage: <accumulation|markup|distribution|markdown|range>
support: <S1>   resistance: <R1>   bull_invalidated_below: <level>   bear_invalidated_above: <level>
axis: technical_structure
-->
## Technical Read — <TICKER> (<date>)

## Findings
<Everything from this leg that could change a verdict, in 3-6 plain sentences — each with its number and where it came from. A reader who stops here has the leg's whole case.>

## Detail

**Trend (Dow stage)**: primary trend; phase; the HH-HL or LH-LL evidence
**Key levels**: S1, S2 / R1, R2 with the touch evidence for each
**Price vs MAs**: position against the 50-EMA and 200-EMA (`ema200`; `sma200` is a simple average), and the slope of each
**Pattern**: the active pattern, if any, with its location (at support? mid-air?)
**Volume**: recent moves against the 10-day average; accumulation or distribution
**Indicators (confirmation only)**: RSI and its zone; MACD state; agreement or divergence with price
**Bull invalidated below**: <level> / **Bear invalidated above**: <level>
**Verdict**: one sentence, with confidence
```

Write it to the output path given, or to `artifacts/stocks/<TICKER>/<YYYY-MM-DD>/technical.md`. Keep
every field name exactly as the block has it. Data that could not be fetched is a Data gaps
section, never a guess. Return only the `technical-block` fields plus `path`.
