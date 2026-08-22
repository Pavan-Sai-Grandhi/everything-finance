---
name: portfolio-review
description: Audit the real cross-broker book — stocks and mutual funds — for what to exit, trim, or fix. XIRR-driven laggard detection, multi-dimensional allocation & concentration (asset class, market-cap, AMC, style, sector, single-stock), cheap per-holding health with a bounded deep-dive only on flagged names, and rebalancing moves in ₹. Runs `quick` (a compact investments digest other skills consume) or `deep` (the full review). Use when the user asks to review their portfolio, holdings, or positions, asks "should I exit anything", wants a risk check, or mentions rebalancing.
argument-hint: "[holdings inline / CSV / watchlist.json] [--quick | --deep]"
allowed-tools: Read, Write, Bash, Skill, mcp__indmoney__*, mcp__plugin_everything-finance_indmoney__*, mcp__kite__*, mcp__plugin_everything-finance_kite__*, mcp__upstox__*, mcp__plugin_everything-finance_upstox__*, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-funds__*, mcp__plugin_everything-finance_finance-funds__*
---

# Portfolio Review

This skill looks for what to **exit, trim, or fix**. It sits on the real book and defers all per-name depth downstream — stock depth to `deep-analysis`, fund depth to `mf-analysis` — so it owns the *portfolio* view (allocation, concentration, laggards) and never re-implements single-name analysis. Read `references/reference.md` for the review rubric.

**Sources for this skill only:**

- **IndMoney / broker** (`mcp__indmoney__*`, `mcp__kite__*`, `mcp__upstox__*`, read-only) — the book itself: holdings, units, invested/current value, XIRR. Normalized through `finance/compute/holdings.py`.
- **`get_company_fundamentals`** — the cheap per-stock drift snapshot (§2).
- **`get_stock_ratios`** — `cap_rank`, the cap classification for the allocation read.
- **`get_corporate_actions`** + **`get_history`** — the split/bonus check that stops a phantom P&L (§1).
- **`get_market_context`** — the tape the small-cap concentration threshold is read against.

All per-name *depth* is delegated to `deep-analysis` / `mf-analysis` — do not fetch it here.

## Depth mode — resolve first

- **`deep`** (default on direct user invocation) — the full review: holdings source (§1), per-stock hybrid health (§2), per-fund hybrid health (§3), full multi-dimensional allocation (§4), the holdings table with verdicts, and a prioritized action list.
- **`quick`** (another skill requested it — the investments leg `wealth-manager` consumes — or the user passed `--quick` / asked for a "quick take") — multi-dimensional allocation + concentration flags + the top exit/laggard flags + the XIRR summary, returned as the compact **`investments-block` digest** (`finance/contracts.md`). **No per-holding deep fan-out** (no auto `deep-analysis`/`mf-analysis` deep calls) — skip straight to Output.

## Section 1 — Holdings source

Review the **real book, not a hand-typed approximation**. Source through the shared `finance/compute/holdings.py` resolver, precedence **IndMoney → broker MCP → manual paste / CSV / `watchlist.json`**. The resolver runs in script context and cannot call MCP tools, so the **handoff is**: invoke IndMoney `networth_holdings` (and any connected broker's holdings+positions), **write the raw payload to a temp file** under `paths.tmp_dir("holdings")`, then take each slice:

```bash
PYTHONPATH=<plugin> python3 -m finance.compute.holdings --indmoney <ind.json> [--kite <k.json>] --equity-only   # stock passes
PYTHONPATH=<plugin> python3 -m finance.compute.holdings --indmoney <ind.json> --mf-only                          # fund passes
```

**A caller may hand you the payload instead.** When the invocation names a holdings payload path, that file *is* the book — run the resolver over it and **make no broker call of your own**. That is how the `quick` leg reaches the book from a context with no personal-broker grant.

Each equity row drives the per-stock passes (§2); each MF row drives the per-fund passes (§3).

- **XIRR** (from IndMoney) drives position-level performance and laggard detection where present; where absent (broker/manual path), label the performance read **inferred**.
- **Corporate-action sanity check (mandatory)**: if avg cost is wildly off CMP (> ±40%), check for a split/bonus (`get_corporate_actions`; an older action shows up as a step in `get_history`) before computing P&L — a 1:1 bonus halves the price and a naive comparison reports a phantom ±50% move. Adjust the avg cost for the action, **state the adjustment**, and only then assign a verdict (never report phantom P&L). Note the standalone-vs-consolidated ratio caveat the same way.
- Ask once for total portfolio value and the intended equity:debt:cash split if not stated and not derivable from the book; otherwise compute splits from holdings and say the drift section is **relative**.

## Section 2 — Per-stock health (hybrid)

Light on a large book, deep only where there is a problem, with **no single-stock logic duplicated** from `deep-analysis`.

1. **Cheap drift check on *all* stock holdings** — one `get_company_fundamentals` snapshot per name, read against the reference.md rubric (ROCE trend, debt creep, promoter pledge, earnings trajectory). Flag *changes for the worse* — "would I buy this today?" — not static imperfection. Prefer consolidated but sanity-check vs standalone (IT/holding-cos distort; if they diverge wildly use standalone and say so).
2. **Bounded deep-dive on the worst flags only** — auto-invoke **`deep-analysis --quick`** (via `Skill`) **only** on holdings that trip a drift / exit / concentration flag, capped at a small N (**≤ 5 worst**) so the fan-out can't blow up on a large book. Feed its verdict into the holding's row.
3. **Suggest `/deep-analysis <T>` (full)** on the most serious flags rather than auto-running full diligence.
4. **Swing positions** (anything the user calls a trade, or held < 3 months with an SL): keep the daily-brief position states (ON-TRACK / NEAR-SL / TARGET-ZONE / SL-HIT / STALE) and the ~4-week time-stop check. Needs the entry date; if unavailable, label the staleness verdict **inferred**. An SL-hit position still held gets the bluntest line in the report.

## Section 3 — Per-fund health (hybrid, mirrors stocks)

Same shape as stocks; **`mf-analysis` owns all fund depth**.

1. **`mf-analysis quick` on *all* held funds** (via `Skill`) — the descriptive digest: NAV, AUM, expense vs category, returns 1/3/5Y, AUM-stability, held XIRR. Cheap, no look-through, **no category rank** (that needs the scan `quick` deliberately skips).
2. **Targeted `mf-analysis deep` on flagged funds only** — a fund whose quick digest reads as a laggard (returns behind the category, expense drag, AUM instability, weak held XIRR). Bounded the same way as the stock deep-dive; the deep run is what confirms style drift and standing among peers.
3. **Suggest `/mf-analysis` (full)** on serious fund flags, and on any same-category overlap question (holdings-overlap needs the look-through this skill defers).

## Section 4 — Multi-dimensional allocation

Run `scripts/allocation.py` over the normalized book — enrich each holding with the tags gathered above (`sector`, `market_cap`, `amc`, `style`, `asset_class`, `kind`, current `value`), and pass the pre-aggregated cap & style splits as `breakdowns`:

```bash
python3 <plugin>/skills/portfolio-review/scripts/allocation.py --book <book.json>
```

It returns per-dimension breakdowns (with coverage), asset-class drift vs target, and the ranked concentration flags — each carrying its **₹ amount at risk** and a concrete **₹ rebalancing move**; the thresholds it defaults to are in reference.md. Dimension inputs:

- **Asset class** — equity : debt : cash vs the stated target (ask once if not given; report **relative** otherwise).
- **Market cap** — from **`get_stock_ratios.cap_rank`** for direct stocks and the `mf-analysis` look-through for the fund sleeve. **A personal source reports what you hold, never what tier it is** — an IndMoney/broker cap breakdown is not a classification input. Rank bands, never absolute ₹Cr bands: bands reported a real small-cap fund as 0% small-cap.
  **Read the small+micro threshold against the tape, not in a vacuum**: `get_market_context(mode="quick")` → `valuation["NIFTY SMALLCAP 250"].stance` and `relative.percentile_spread`. An expensive tier (`rich`/`expensive`, spread ≥ +25) tightens the flag from 30% to 25%; a `cheap` tier relaxes it to 35%. Say which threshold was applied and why.
- **Investing style** — the growth / value / factor mix from the `mf-analysis` look-through.
- **AMC · Sector · Single stock** — aggregated from the per-holding tags.

The engine surfaces per-dimension coverage and gaps rather than a confident zero. Rebalancing prefers fresh inflows over taxable switches (reference.md).

## Section 5 — Output

Markdown report: the holdings table with a verdict column (**KEEP / TRIM / EXIT / REVIEW** + one falsifiable one-line reason each), the multi-dimensional allocation breakdown, the concentration flags with ₹ amounts, and a prioritized action list (**max ~5**) of concrete **rebalancing ₹ moves** plus explicit **suggestions to run `/deep-analysis <T>` or `/mf-analysis <F>`** on the flagged names. Save to `artifacts/portfolio-review/YYYY-MM-DD.md` (`paths.report_path("portfolio-review")`).

Holdings values are sensitive — the **full table lives in the artifact**; in chat, give only the verdicts, the concentration flags (with ₹), and the actions.

`quick` writes only the `investments-block` digest to the artifact and returns it — no per-holding table, no deep fan-out.

## Section 6 — Degradation specifics

- **No IndMoney/broker** → manual paste / CSV / `watchlist.json` fallback; XIRR labelled **unavailable**.
- **`mf-analysis` / `deep-analysis` not invokable** → a labelled gap + a manual `/…` suggestion instead of the auto deep-dive.
- **Missing target allocation** → report the relative splits and say drift is relative.

## Alerts this skill raises (via `finance/compute/alerts.py`)

When the review concludes the book has drifted from target (concentration breach, large cash drag, an allocation well off plan), raise a **`rebalance_due`** alert (`subject: {type: portfolio}`, `created_by: portfolio-review`, `severity: watch`, `action.text` = the drift in one line, `action.suggest: "/portfolio-review"`, `dedup_key: rebalance`). It is a date/standing reminder, not a cheap price trigger — `daily-brief` lists it among due actions until the next review clears it.
