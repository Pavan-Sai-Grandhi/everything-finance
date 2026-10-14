---
name: market-analysis
description: Read the Indian market's shared trend, breadth, volatility, valuation and flow context. Use for market conditions, cap-tier valuation, sector leadership or risk context before a stock/fund decision. Quick returns the shared daily digest; deep produces a written market read.
argument-hint: "[--quick | --deep] [--years N] (e.g. 'what's the market doing', 'is smallcap expensive')"
allowed-tools: Read, Write, Bash, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*
---

# Market Analysis

The one place this plugin decides **what the market is doing** — trend, posture, real stock-level breadth, **cap-tier valuation percentiles**, institutional flows and the cross-asset backdrop. Every other skill reads that answer instead of computing its own.

Read `references/reference.md` for the grounding — what each dimension means, how the regime taxonomy is defined, why a valuation percentile beats a raw multiple, and the limitations of its valuation heuristics.

## The design rule — compute wide, report narrow

`get_market_context` does all fetching and all arithmetic deterministically and returns the **digest**: ~30 lines of decision-grade numbers — "Smallcap 250 P/B at the 77th percentile of 10 years, dividend yield at the 9th", never the 122 monthly samples behind it or the 500 screener rows behind the breadth count. **Never paste raw series, full screener output, or whole JSON artifacts into the conversation.**

Reach for a raw `finance-market` tool (`get_indices`, `get_breadth`, `get_flows`, `get_macro`, `get_index_valuation_history`, `get_history`) only for something the digest does not carry — the per-sector valuation table in `deep`, say. Everything the digest already answers comes from the digest.

**The rate cycle has no approved source.** The repo rate, CPI and the policy stance are a **labelled data gap** unless the user supplies them — never a remembered figure and never an improvised scrape.

## Depth modes

- **`quick`** (another skill requested it, or the user passed `--quick`) — reuse today's artifact for the same history window without fetching; recompute if it is missing or does not match. Every other skill calls this mode, so N skills in one day cost one computation. Emit the digest and stop.
- **`deep`** (default on direct user invocation) — compute every rung, write the artifact, and write the market read below, including earlier regime readings. Call `get_indices` only if you need valuations for more sectors than the digest's leaders and laggards.

## Workflow

1. **Compute the context** — `get_market_context(mode="deep", years=10)`. `as_of` is the **last trading bar**, not today — on a weekend or holiday the market context is legitimately Friday's; say so rather than restamping it.

2. **Read the four dimensions together.** No single one decides anything:
   - **Trend + posture** — the risk gate strategy specs are validated against.
   - **Breadth** — whether the index move is real participation or a handful of heavyweights. The stock-level numbers (`pct_above_sma50/200` over 500 names) are the ones to reason about; `pct_sectors_above_ema50` is retained only because strategy specs gate on it.
   - **Valuation percentiles** — where each cap tier sits versus its OWN history. This is the dimension that answers "is this a good time to put money into this segment", which is a different question from "which fund/stock is best inside it".
   - **Flows + macro** — who is buying, and the cross-asset backdrop.

3. **Resolve the contradictions explicitly.** The interesting market reads are the ones where dimensions disagree — a benign trend with rich valuations, cheap largecaps beside expensive smallcaps, an index near its highs on narrowing breadth. Name the tension and say which side governs the decision at hand; do not average them into a bland verdict.

4. **State what it implies.** Regime for position sizing, cap-tier stance for allocation, and what would change the read. Market context is an input to a decision, never a market call — this skill does not predict direction and does not time entries.

## Output

The tool saves the **full context** to `paths.report_path("market-analysis", ext="json")`; strategy selection, fund scans and later market runs read that file. Never overwrite it yourself. In `deep`, read that JSON for fields the tool's reply leaves out, then write the report to `paths.report_path("market-analysis", ext="md")` using `assets/market-read.md`. If the tool could not save the file, report the gap.
Summarize in chat: posture and trend, the breadth check, the cap-tier valuation table, the one tension that matters, and the data gaps. `quick` returns only the digest — no report, no chat narrative.

**The market-context digest is a consumed contract** — `finance/contracts.md` (*Artifact: market-context*) lists every field, its meaning, which skill reads it, and the four spellings frozen because `strategy-manager/scripts/select_strategy.py` gates on them. The library writes the JSON; keep its field names when reading it.

## Reporting rules specific to this read

- Percentiles are against **that index's own history**, never another index or a remembered "normal". A multiple without its own distribution behind it is not evidence.
- Report how many P/E samples were excluded and why (at or above 3× the median). The rule does not tell you what caused the outlier. Percentile bands and blends are conventions, not forecasts.
- Missing values are data gaps. Null breadth fails a strategy gate, and `neutral` because of missing data does not mean conditions are normal. Use each component's own date; the Nifty bar date says nothing about how fresh flows or valuations are.
- Never explain a **trailing-window** number with a **calendar-year** number. "The trailing 1Y is weak but CY2025 was worse" compares two different windows and is not an argument.

## Alerts this skill raises (via `manage_alerts`)

On a posture change between complete, comparable readings, use `manage_alerts(action="add", subject_type="market", subject_id="nifty", kind="regime_change", created_by="market-analysis", check="review_regime_change", severity="watch", text="<prior posture/date> to <current posture/date>: re-check open positions and active strategy fit", dedup_key="regime-<date>")`. The alert asks for a manual review, never a trade. A posture that changed only because data was missing is not a regime change.
