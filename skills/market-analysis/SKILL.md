---
name: market-analysis
description: The plugin's single market-of-record — what the Indian market is doing right now and what that implies for risk. Reads trend and regime (Nifty vs 50/200-EMA), real stock-level breadth, India VIX and its percentile, cap-tier valuation percentiles (Nifty 50 / Midcap 150 / Smallcap 250 P/E, P/B, dividend yield versus their own 10-year history), smallcap-vs-largecap relative richness, FII/DII flows, the cross-asset macro backdrop, and sector leadership. Runs `quick` (a cached digest other skills consume — the common case) or `deep` (the full written market read). Use whenever the user asks what the market is doing, about market conditions, regime, breadth, whether the market or a segment is expensive or cheap, "is this a good time to invest", "is smallcap overvalued", sector rotation, FII/DII flows, or before any skill needs market context to size or time a decision.
argument-hint: "[--quick | --deep] [--years N] (e.g. 'what's the market doing', 'is smallcap expensive')"
allowed-tools: Read, Write, Bash, mcp__finance-market__*
---

# Market Analysis

The one place this plugin decides **what the market is doing** — trend, posture, real stock-level breadth, **cap-tier valuation percentiles**, institutional flows and the cross-asset backdrop. Every other skill reads that answer instead of computing its own.

Read `references/reference.md` for the grounding — what each dimension means, how the regime taxonomy is defined, why a valuation percentile beats a raw multiple, and the traps (the earnings-collapse P/E distortion above all).

## The design rule — compute wide, report narrow

`get_market_context` does all fetching and all arithmetic deterministically and returns the **digest**: ~30 lines of decision-grade numbers — "Smallcap 250 P/B at the 77th percentile of 10 years, dividend yield at the 9th", never the 122 monthly samples behind it or the 500 screener rows behind the breadth count. **Never paste raw series, full screener output, or whole JSON artifacts into the conversation.**

Reach for a raw `finance-market` tool (`get_indices`, `get_breadth`, `get_flows`, `get_macro`, `get_index_valuation_history`, `get_history`) only for something the digest does not carry — the per-sector valuation table in `deep`, say. Everything the digest already answers comes from the digest.

**The rate cycle has no approved source.** The repo rate, CPI and the policy stance are a **labelled data gap** unless the user supplies them — never a remembered figure and never an improvised scrape.

## Depth modes

- **`quick`** (another skill requested it, or the user passed `--quick`) — reuse **today's artifact if it exists, with zero fetches**; compute only if it is missing. This is the mode every other skill calls, and it is why N skills in one day cost one computation. Emit the digest and stop.
- **`deep`** (default on direct user invocation) — compute every rung, write the artifact, and produce the written market read below. Adds the regime-transition history (free — it diffs prior dated artifacts) and the per-sector valuation table.

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

Write the digest to `artifacts/market-analysis/<date>.json` (`paths.report_path("market-analysis", ext="json")`) — `strategy-manager`'s strategy selection, `get_fund_scan(market_context=…)` and the next run's transition history all read that file, so a `deep` run that does not persist it breaks them. In `deep` also write `artifacts/market-analysis/<date>.md`, filled from `assets/market-read.md`.

Summarize in chat: posture and trend, the breadth check, the cap-tier valuation table, the one tension that matters, and the data gaps. `quick` returns only the digest — no report, no chat narrative.

**The market-context digest is a consumed contract** — `finance/contracts.md` (*Artifact: market-context*) lists every field, its meaning, which skill reads it, and the four spellings frozen because `strategy-manager/scripts/select_strategy.py` gates on them. Persist the digest exactly as the tool returned it; never rename a field on either side.

## Reporting rules specific to this read

- Percentiles are against **that index's own history**, never another index or a remembered "normal". A multiple without its own distribution behind it is not evidence.
- **Report the earnings-collapse exclusion count.** Samples above 3× the median are dropped from a P/E percentile because an earnings trough sends the ratio to five figures; the count dropped is part of the finding, not a silent filter (`references/reference.md` has the full case).
- Never explain a **trailing-window** number with a **calendar-year** number. "The trailing 1Y is weak but CY2025 was worse" compares two different windows and is not an argument.

## Alerts this skill raises (via `finance/compute/alerts.py`)

On a **posture change** versus the most recent prior reading (e.g. `risk_on` → `risk_off`), raise a **`regime_change`** alert (`subject: {type: market, id: nifty}`, `created_by: market-analysis`, `trigger: {from: <prior>, to: <current>}`, `severity: watch`, `action.text: "Market posture changed — re-check open positions and active strategy fit"`, `dedup_key: regime-<date>`). `daily-brief` surfaces it and `trade-tracker` re-validates against it. It is a prompt to re-examine, never an instruction to transact.
