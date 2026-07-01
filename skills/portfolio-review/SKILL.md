---
name: portfolio-review
description: Audit current stock and mutual-fund holdings — exit signals on swing positions, allocation drift vs plan, sector/stock concentration risk, and laggard funds. Use when the user asks to review their portfolio, holdings, or positions, asks "should I exit anything", wants a risk check, or mentions rebalancing.
argument-hint: "[holdings inline, or path to holdings CSV / watchlist.json]"
allowed-tools: WebFetch, Read, Write, Bash, Agent, mcp__playwright__*
---

# Portfolio Review

The complement to the buy-side skills: this one looks for what to **exit, trim, or fix**. Read `references/reference.md` for the review rubric.

**Sites for this skill only:** screener.in (stock fundamentals snapshot), NSE (prices), mfapi.in (fund NAVs). Fund-metric method is summarized in this skill's `references/reference.md`.

## Inputs

Holdings from (in priority order): user-pasted list, a CSV they point to (broker holdings export — Zerodha console format: symbol, qty, avg cost), or `watchlist.json` positions. Need at minimum: ticker, quantity, average cost. Ask once for total portfolio value and intended equity:debt split if not stated; otherwise compute splits from holdings only and say the plan-drift section is relative. For anything the user calls a trade, also ask the **entry date** (the time-stop check needs it; if unavailable, label the staleness verdict "inferred").

**Corporate-action sanity check (mandatory)**: if avg cost is wildly off CMP (> ±40%), check the stock's split/bonus history (screener.in company page) before computing P&L — a 1:1 bonus halves the price and a naive comparison reports a phantom ±50% move. Adjust the user's avg cost for the action, state the adjustment, and only then assign a verdict.

## Review passes

1. **Swing positions** (anything the user marks as a trade, or held < 3 months with an SL): apply the daily-brief position states (ON-TRACK / NEAR-SL / TARGET-ZONE / SL-HIT / STALE). SL-hit positions still held get the bluntest line in the report.
2. **Investment holdings — fundamentals drift**: for each stock, screener.in snapshot vs the rubric in reference.md (ROCE trend, debt creep, promoter pledge, earnings trajectory). Prefer consolidated figures but sanity-check vs standalone — for IT/holding-structure companies the consolidated page can show distorted ratios (seen: P/E 250 consolidated vs 37 standalone); if they diverge wildly, use standalone and say so. Flag *changes for the worse*, not static imperfection — the question is "would I buy this today?".
3. **Concentration**: single stock > 10% of portfolio, single sector > 25%, smallcap+microcap > 30% → concentration flags with the ₹ amount at risk.
4. **Funds**: rolling-3Y consistency vs the relevant index fund, computed from mfapi.in NAVs (feasible from this skill's allowed sources). Holdings-overlap and category-quartile checks need holdings/category data this skill's sources don't expose — if comparing two same-category active funds, note overlap as a *data gap* and suggest running `/mf-analysis` on the pair rather than guessing.
5. **Allocation drift**: current equity:debt:cash vs intended; drift > 10pp → rebalance suggestion with concrete ₹ moves.

## Output

Markdown report: holdings table with verdict column (KEEP / TRIM / EXIT / REVIEW + one-line reason each), the flags from passes 1–5, and a prioritized action list (max 5 items). Save to `artifacts/portfolio-review/YYYY-MM-DD.md` (`paths.report_path("portfolio-review")`). Holdings values are sensitive — full table in the artifact; in chat, only the verdicts and actions. End with the standard risk note.

## Alerts this skill raises (via `lib/alerts.py`)

When the review concludes the book has drifted from target (concentration breach, large cash drag, an allocation well off plan), raise a **`rebalance_due`** alert (`subject: {type: portfolio}`, `created_by: portfolio-review`, `severity: watch`, `action.text` = the drift in one line, `action.suggest: "/portfolio-review"`, `dedup_key: rebalance`). It is a date/standing reminder, not a cheap price trigger — `daily-brief` lists it among due actions until the next review clears it.
