---
name: market-analysis
description: Read the Indian market's shared trend, breadth, volatility, valuation and flow context. Use for market conditions, cap-tier valuation, sector leadership or risk context before a stock/fund decision. Quick returns the shared daily digest; deep produces a written market read.
argument-hint: "[--quick | --deep] [--years N] (e.g. 'what's the market doing', 'is smallcap expensive')"
allowed-tools: Read, Write, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-workflow__manage_alerts, mcp__plugin_everything-finance_finance-workflow__manage_alerts
---

# Market Analysis

The one place the plugin decides what the market is doing: trend and posture, stock-level
breadth, cap-tier valuation percentiles, flows and the cross-asset backdrop. Every other skill
reads this answer instead of forming its own. It informs a decision; it never predicts direction
or times an entry.

**Method:** `methods/market.md`.

`get_market_context` does all fetching and arithmetic and returns a digest of decision-grade
numbers ("Smallcap 250 P/B at the 77th percentile of 10 years"), never the samples behind them.
Never paste raw series, screener output or whole JSON artifacts into the conversation. Reach for a
raw tool (`get_indices`, `get_breadth`, `get_flows`, `get_macro`, `get_index_valuation_history`,
`get_history`) only for what the digest does not carry, such as more sectors' valuations in `deep`.

## Modes

- **`quick`** (another skill asked, or `--quick`): reuse today's artifact for the same history
  window, recomputing only if it is missing or does not match. Emit the digest and stop.
- **`deep`** (default on direct invocation): compute every rung, then write the market read.

## Workflow

1. `get_market_context(mode="deep", years=10)`. `as_of` is the last trading bar: on a weekend or
   holiday the context is legitimately Friday's; say so.
2. **Read the four dimensions together**; no single one decides: trend and posture (the gate
   strategy specs validate against), breadth (real participation or a few heavyweights; reason on
   the stock-level `pct_above_sma50/200`), valuation percentiles (is this a good time to add to a
   segment, which is a different question from which fund or stock), and flows with macro.
3. **Resolve the contradictions explicitly**: a benign trend with rich valuations, cheap large
   caps beside expensive small caps, an index near its high on narrowing breadth. Name the tension
   and say which side governs the decision at hand.
4. **State what it implies**: the regime for sizing, the cap-tier stance for allocation, and what
   would change the read.

## Output

The tool saves the full context to `artifacts/market-analysis/<date>.json`; strategy selection,
fund scans and later runs read it, so never overwrite it. In `deep`, read it for fields the reply
leaves out and write the read to `artifacts/market-analysis/<date>.md` from `assets/market-read.md`.
In chat: posture and trend, the breadth check, the cap-tier valuation table, the one tension that
matters, and the gaps. `quick` returns only the digest.

## Alerts

On a posture change between complete, comparable readings:
`manage_alerts(action="add", subject_type="market", subject_id="nifty", kind="regime_change",
created_by="market-analysis", check="review_regime_change", severity="watch",
text="<prior posture/date> to <current posture/date>: re-check open positions and active strategy fit",
dedup_key="regime-<date>")`. A posture that changed only because data was missing is not a regime
change.
