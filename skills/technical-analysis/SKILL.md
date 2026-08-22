---
name: technical-analysis
description: Read the chart for one NSE stock — Dow trend stage, the support/resistance map with touch-count evidence, the active candlestick or structural pattern in its location context, the volume signature, RSI/MACD as confirmation only, and the two price levels that invalidate a bull or a bear thesis. Use whenever the user wants the chart view on a ticker — "what do the charts say on X", "is X in an uptrend", "where is support / resistance", "is this a breakout or a fakeout", "what is the RSI/MACD saying", "where would my stop go on X", "is it overbought" — even when they never say "technical analysis". This is the chart read on one stock: scanning the whole market against a strategy is find-trade, testing a strategy on history is strategy-manager, and the full bull/bear debate is deep-analysis.
argument-hint: "TICKER [optional: a candles file already fetched]"
allowed-tools: Read, Write, Bash, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*
---

# Technical Analysis — chart read on one NSE ticker

Read `references/reference.md` first — it owns the method: the six-step Varsity checklist and the order it runs in, the moving-average rules, the stale-quote cross-check, and the `ta.py` recipe that produces every indicator value. This SKILL is the workflow.

**Sources for this skill only:** `finance-market` — `get_history(symbol, period="1y")` for EOD candles (the full series is written to `candles_path`; the summary alone is not enough to derive levels) and `get_quote(symbol)` for the live bar.

## Workflow

1. **Inputs**: the ticker, and — where an orchestrator already has them — a candles file path and an output path. Prefer a supplied candles file over fetching the same series again.
2. **Get the series.** `get_history` for the year of daily candles, `get_quote` for the live bar, then `Read` the file at `candles_path`.
3. **Check the last candle is a closed session.** Mid-session, and for a while after the close, the feed's final bar carries a provisional or missing open/high/low. **Drop an unclosed bar from every indicator and level computation** and read the live bar from `get_quote` instead — an estimated high or low silently moves a support level, a range and an ATR-derived stop. Say in the report which session the levels are struck on, and label a same-day reading as intraday.
4. **Compute the indicators** by running `finance/compute/ta.py` over that file — the reference's § "Working the data" carries the recipe. Never hand-roll an indicator value.
5. **Work the checklist in the reference's order.** The order is part of the method: pattern → S&R → volume → Dow stage → indicators.
6. **Name both invalidation levels**, each with the touch evidence behind it.

## Produce this report

The leading block is machine-read, so the PM and synthesis cite levels without re-deriving them:

```
<!-- technical-block
verdict: bullish | bearish | neutral   confidence: low | med | high
trend_stage: <accumulation|markup|distribution|markdown|range>
support: <S1>   resistance: <R1>   bull_invalidated_below: <level>   bear_invalidated_above: <level>
axis: technical_structure
-->
## Technical Read — <TICKER> (<date>)

## Findings
<Everything from this leg that could change a verdict, in 3-6 plain sentences — each with its number and where it came from. A reader who stops here has the leg's whole case; a downstream agent reads only this far unless it needs the detail behind a line.>

**Trend (Dow stage)**: primary trend up/down/range; phase (accumulation/markup/distribution/markdown); HH-HL or LH-LL evidence
**Key levels**: S1, S2 / R1, R2 with the touch-count evidence for each
**Price vs MAs**: position vs 50-EMA and 200-EMA, slope of each
**Pattern**: active candlestick/structural pattern if any, with location context (at support? mid-air?)
**Volume**: recent moves vs 10-day average — accumulation or distribution signature
**Indicators (confirmation only)**: RSI value + zone; MACD state; note agreement/divergence with price
**Bull invalidated below**: <level> / **Bear invalidated above**: <level>
**Verdict**: bullish / bearish / neutral structure, one sentence why, confidence low/med/high
```

Write it to the output path you were given, or to `artifacts/stocks/<TICKER>/YYYY-MM-DD/technical.md` (`paths.stock_dir(symbol, date)`) when none was. **Keep every field name exactly as the block has it.** Persist the full report, then return only the `technical-block` fields plus `path`.

## Boundaries

Every level cites its evidence — touch dates and counts, not an eyeballed round number. Indicators never override price structure. Data that could not be fetched is a "DATA GAP" section, never a guess. No trade advice beyond the levels: sizing and the buy/sell call belong to the caller.
