---
name: portfolio-review
description: Audit the real cross-broker book — stocks and mutual funds — for what to exit, trim, or fix. XIRR-driven laggard detection, multi-dimensional allocation & concentration (asset class, market-cap, AMC, style, sector, single-stock), cheap per-holding health with a bounded deep-dive only on flagged names, and rebalancing moves in ₹. Runs `quick` (a compact investments digest other skills consume) or `deep` (the full review). Use when the user asks to review their portfolio, holdings, or positions, asks "should I exit anything", wants a risk check, or mentions rebalancing.
argument-hint: "[holdings inline / CSV / watchlist.json] [--quick | --deep]"
allowed-tools: WebFetch, Read, Write, Bash, Agent, Skill, mcp__indmoney__*, mcp__playwright__*
---

# Portfolio Review

The complement to the buy-side skills: this one looks for what to **exit, trim, or fix**. It sits on the real book (via `lib/holdings.py`) and defers all per-name depth downstream — stock depth to `deep-analysis`, fund depth to `mf-analysis` — so it owns the *portfolio* view (allocation, concentration, laggards) and never re-implements single-name analysis. Read `references/reference.md` for the review rubric.

**Sites/sources for this skill only:** live holdings via the shared `lib/holdings.py` resolver (**IndMoney** read-only net worth first, **broker MCP** fallback), screener.in (the cheap per-stock fundamentals drift snapshot), mfapi.in (fund NAVs for the cheap fund read). All per-name *depth* is delegated — do not fetch it here.

## Depth mode — resolve first

- **`deep`** (default on direct user invocation) — the full review: holdings source (§1), per-stock hybrid health (§2), per-fund hybrid health (§3), full multi-dimensional allocation (§4), the holdings table with verdicts, and a prioritized action list.
- **`quick`** (another skill requested it — the investments leg `wealth-manager` consumes — or the user passed `--quick` / asked for a "quick take") — multi-dimensional allocation + concentration flags + the top exit/laggard flags + the XIRR summary, returned as the compact **`investments-block` digest** (`lib/contracts.md`). **No per-holding deep fan-out** (no auto `deep-analysis`/`mf-analysis` deep calls). Mirrors the deep-analysis/mf-analysis digest hygiene; skip straight to Output.

## Section 1 — Holdings source

Review the **real book, not a hand-typed approximation**. Source through the shared `lib/holdings.py` resolver, precedence **IndMoney → broker MCP → manual paste / CSV / `watchlist.json`** (the old manual path stays as the fallback). The resolver runs in script context and cannot call MCP tools, so the **handoff is**: invoke IndMoney `networth_holdings` (and any connected broker's holdings+positions), **write the raw payload to a temp file** under `paths.tmp_dir("holdings")`, then take each slice:

```
python3 <plugin>/lib/holdings.py --indmoney <ind.json> [--kite <k.json>] --equity-only   # stock passes
python3 <plugin>/lib/holdings.py --indmoney <ind.json> --mf-only                          # fund passes
```

Each equity row drives the per-stock passes (§2); each MF row drives the per-fund passes (§3). All read-only by design (CLAUDE.md) — never place an order.

- **XIRR** (from IndMoney) drives position-level performance and laggard detection where present; where absent (broker/manual path), label the performance read **inferred** and never fabricate a return.
- **Corporate-action sanity check (mandatory)**: if avg cost is wildly off CMP (> ±40%), check the stock's split/bonus history (screener.in company page) before computing P&L — a 1:1 bonus halves the price and a naive comparison reports a phantom ±50% move. Adjust the avg cost for the action, **state the adjustment**, and only then assign a verdict (never report phantom P&L). Note the standalone-vs-consolidated ratio caveat the same way.
- Ask once for total portfolio value and the intended equity:debt:cash split if not stated and not derivable from the book; otherwise compute splits from holdings and say the drift section is **relative**.

## Section 2 — Per-stock health (hybrid)

Light on a large book, deep only where there is a problem, with **no single-stock logic duplicated** from `deep-analysis`.

1. **Cheap drift check on *all* stock holdings** — a screener.in snapshot against the reference.md rubric (ROCE trend, debt creep, promoter pledge, earnings trajectory). Flag *changes for the worse* — "would I buy this today?" — not static imperfection. Prefer consolidated but sanity-check vs standalone (IT/holding-cos distort; if they diverge wildly use standalone and say so).
2. **Bounded deep-dive on the worst flags only** — auto-invoke **`deep-analysis --quick`** (via `Skill`) **only** on holdings that trip a drift / exit / concentration flag, capped at a small N (**≤ 5 worst**) so the fan-out can't blow up on a large book. Feed its verdict into the holding's row.
3. **Suggest `/deep-analysis <T>` (full)** on the most serious flags rather than auto-running full diligence.
4. **Swing positions** (anything the user calls a trade, or held < 3 months with an SL): keep the daily-brief position states (ON-TRACK / NEAR-SL / TARGET-ZONE / SL-HIT / STALE) and the ~4-week time-stop check. Needs the entry date; if unavailable, label the staleness verdict **inferred**. An SL-hit position still held gets the bluntest line in the report.

## Section 3 — Per-fund health (hybrid, mirrors stocks)

Same shape as stocks; **`mf-analysis` owns all fund depth**.

1. **`mf-analysis quick` on *all* held funds** (via `Skill`) — the descriptive digest: expense vs category, category-rank percentile, returns, AUM-stability, held XIRR. Cheap, no look-through.
2. **Targeted `mf-analysis deep` on flagged funds only** — a fund whose quick digest reads as a laggard (poor category rank, expense drag, style drift, AUM instability). Bounded the same way as the stock deep-dive.
3. **Suggest `/mf-analysis` (full)** on serious fund flags, and on any same-category overlap question (holdings-overlap needs the look-through this skill defers).

## Section 4 — Multi-dimensional allocation

Run `scripts/allocation.py` over the normalized book (enrich each holding with the tags gathered above — `sector`, `market_cap`, `amc`, `style`, `asset_class`, `kind`, and current `value`; pass the IndMoney `networth_allocation_breakdown` / mf-analysis look-through cap & style splits as `breakdowns`):

```
python3 <plugin>/skills/portfolio-review/scripts/allocation.py --book <book.json>
```

It returns per-dimension breakdowns (with coverage), asset-class drift vs target, and the ranked concentration flags — each carrying its **₹ amount at risk** and a concrete **₹ rebalancing move**. The dimensions:

- **Asset class** — equity : debt : cash vs the stated target (ask once if not given; report **relative** otherwise). Drift > 10pp → rebalance move.
- **Market cap** — large / mid / small / micro (IndMoney breakdown + fund look-through); small+micro sleeve > 30% → liquidity-risk flag.
- **AMC** — exposure piled into one fund house (> 40%).
- **Investing style** — growth / value / factor mix (from mf-analysis style data).
- **Sector** — single sector > 25% (> 35% urgent).
- **Single stock** — any one name > 10% of the book.

Partial data reads as partial — the engine surfaces per-dimension coverage and gaps rather than a confident zero. Rebalancing prefers fresh inflows over taxable switches (reference.md).

## Section 5 — Output

Markdown report: the holdings table with a verdict column (**KEEP / TRIM / EXIT / REVIEW** + one falsifiable one-line reason each), the multi-dimensional allocation breakdown, the concentration flags with ₹ amounts, and a prioritized action list (**max ~5**) of concrete **rebalancing ₹ moves** plus explicit **suggestions to run `/deep-analysis <T>` or `/mf-analysis <F>`** on the flagged names. Save to `artifacts/portfolio-review/YYYY-MM-DD.md` (`paths.report_path("portfolio-review")`).

Holdings values are sensitive — the **full table lives in the artifact**; in chat, give only the verdicts, the concentration flags (with ₹), and the actions. End with the standard risk note.

`quick` writes only the `investments-block` digest to the artifact and returns it — no per-holding table, no deep fan-out.

## Section 6 — Error handling & degradation

A missing source never aborts the review — continue and label the gap (CLAUDE.md graceful degradation):

- **No IndMoney/broker** → manual paste / CSV / `watchlist.json` fallback (the old path); XIRR labelled **unavailable**.
- **`mf-analysis` / `deep-analysis` not invokable** → fall back to a labelled gap + a manual `/…` suggestion instead of the auto deep-dive.
- **Missing target allocation** → report the relative splits and say drift is relative.
- **Corporate-action distortion** → adjust the avg cost, state the adjustment, then verdict — never a phantom P&L.

## Alerts this skill raises (via `lib/alerts.py`)

When the review concludes the book has drifted from target (concentration breach, large cash drag, an allocation well off plan), raise a **`rebalance_due`** alert (`subject: {type: portfolio}`, `created_by: portfolio-review`, `severity: watch`, `action.text` = the drift in one line, `action.suggest: "/portfolio-review"`, `dedup_key: rebalance`). It is a date/standing reminder, not a cheap price trigger — `daily-brief` lists it among due actions until the next review clears it.
