# Market analysis knowledge base

The grounding for the plugin's market-of-record. Method, taxonomy, and the traps that make a market read wrong in ways that look right.

## Why percentiles, not levels

A multiple on its own carries no information. "The Smallcap 250 trades at 34× earnings" is unusable — expensive or cheap only exists relative to a distribution. The same index at 34× is dear against a 10-year median of 32× and a bargain against one of 45×.

So every valuation figure here is reported as **level + percentile against that index's own history**. Percentile rank is also invariant to monotone transforms, which means ranking on P/E and ranking on earnings yield give the same answer — the choice of expression cannot smuggle in a conclusion.

Ten years is the default window: long enough to contain a full earnings cycle and both a bear and a bull phase, short enough that the market's composition is still recognisable.

## The earnings-collapse trap (the most important thing in this file)

An index P/E is `price ÷ trailing earnings`. When aggregate earnings collapse, the denominator approaches zero and the ratio explodes. The Nifty Smallcap 250's own history contains month-ends above a P/E of **44,000** — real published prints from the mid-2020 earnings trough.

Those points describe *vanished earnings*, not an expensive market. Left in a percentile they are catastrophic: they make almost any present-day multiple look cheap by comparison, and a skill would confidently report "smallcaps are at the 56th percentile" when the honest number is meaningfully higher.

Three defences, all implemented:
1. **Exclude and count.** Samples above 3× the median are dropped, and the number dropped is reported alongside the percentile. A silent filter would be its own kind of lie.
2. **Weight P/B and dividend yield equally with P/E.** Book value does not evaporate in an earnings trough and dividends fall far less than earnings do, so these two stay meaningful exactly when P/E stops being. The stance blends all three.
3. **Invert the yield.** A *low* dividend yield is an *expensive* market. It enters the blend as `100 − dy_percentile`.

When P/E and P/B percentiles diverge sharply, the divergence is itself the finding — it usually means earnings have moved a long way relative to book, and the direction tells you whether the market is pricing a recovery or a peak.

## Regime taxonomy

**Trend** (Nifty 50, EMA from `finance/compute/ta.py`):
- `up` — price above both the 50- and 200-EMA, with the 50-EMA rising.
- `down` — price below both, with the 50-EMA falling.
- `range` — anything else. Most of the time is `range`, and that is a real answer, not a failure to decide.

**Volatility** (India VIX): `low` < 13, `normal` 13–20, `high` > 20, reported with 1-year and 5-year percentiles. A low VIX is not automatically safe — it is the condition under which position sizes quietly get too large.

**Posture**: `risk_on` (uptrend + acceptable volatility + participation), `risk_off` (downtrend, high volatility, or narrow breadth), else `neutral`. This is a **risk gate for sizing**, not a directional forecast.

## Breadth — the check that catches a hollow rally

An index is a weighted average, so a handful of heavyweights can carry it while most stocks fall. Breadth is the difference between a broad advance and a narrow one:

- **`pct_above_sma50` / `pct_above_sma200`** over the top 500 NSE names by market cap — the numbers actually worth reasoning about. Above 60% is broad participation; below 40% is narrow.
- **`pct_near_52w_high` vs `pct_near_52w_low`** — the leadership/distress balance.
- **`pct_sectors_above_ema50`** — a coarse 10-sector count, kept under a frozen name because strategy specs gate on it. Ten indices cannot distinguish a broad advance from five heavyweights, so the stock-level numbers above should outweigh it.

**Index at highs + falling breadth** is the classic warning: fewer names doing more of the work. **Index flat + rising breadth** is the opposite and is usually constructive.

## Cap tiers and relative valuation

The three tiers — Nifty 50 (large), Midcap 150, Smallcap 250 — are compared on where each sits versus its *own* history, then against each other. The relative read uses **P/B** because it survives an earnings trough, with the P/E ratio alongside.

A `percentile_spread` (smallcap blended percentile − largecap blended percentile) above +25 means the cap tier itself is the dominant risk: in that state, picking a better small-cap fund is a second-order decision compared with how much belongs in small-caps at all. Below −25, the tier is offering the better entry.

This distinction matters more than it sounds. "Which is the best small-cap fund?" and "should I be adding to small-caps now?" are different questions with different answers, and a skill that fuses them will recommend the best fund in an expensive category without ever saying the category is expensive.

## Flows

FII/FPI and DII net cash-market flows, in ₹ Cr, from the exchange's own daily report. The structural fact of recent Indian markets is domestic (DII/SIP) money absorbing foreign selling; the flow rung exists so that claim is **sourced on the day** rather than asserted from memory. One session's flow is noise — read the direction and the persistence, not the print.

## Macro backdrop

India VIX, USDINR, gold, Brent, US 10-Year — each as level, 1-month change, and 5-year percentile. These are context for risk appetite (a rising US 10Y and a weakening rupee tighten conditions for Indian equity), never signals on their own.

The rate cycle sits outside this set: no approved RBI or MoSPI feed exists, which is why the repo rate, CPI and the policy stance are a labelled gap rather than a rung.
