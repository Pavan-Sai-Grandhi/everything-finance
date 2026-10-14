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

Review the **real book, not a hand-typed approximation**. Source through the shared `finance/compute/holdings.py` resolver, precedence **IndMoney → broker MCP → manual paste / CSV / `watchlist.json`**. The resolver is a script and cannot call MCP tools, so call them yourself: IndMoney `networth_holdings` once per `asset_type` (`IND_STOCK` and `US_STOCK` for equity, `MF` for funds; it serves one type per call), and each connected broker's holdings and positions. **Write each raw payload to a file** under `paths.tmp_dir("holdings")`, then take each slice:

```bash
PYTHONPATH=<plugin> python3 -m finance.compute.holdings --indmoney <ind-stock.json> --indmoney <ind-us.json> [--upstox <u.json>] --equity-only   # stock passes
PYTHONPATH=<plugin> python3 -m finance.compute.holdings --indmoney <ind-mf.json> --mf-only                                                  # fund passes
```

IndMoney rows carry no XIRR and no NSE symbol; stocks held through a linked broker carry no cost (`cost_basis: unreported_by_linked_broker`). When the resolver's gap names them, re-resolve with `--prefer <broker>` for the equity pass's cost and P&L.

**A caller may hand you the payload instead.** When the invocation names a holdings payload path, that file *is* the book — run the resolver over it and **make no broker call of your own**. That is how the `quick` leg reaches the book from a context with no personal-broker grant.

Each equity row drives the per-stock passes (§2); each MF row drives the per-fund passes (§3).

- **XIRR**: neither IndMoney's `networth_holdings` nor the brokers supply it, so it is normally **unavailable**; say so. Report unrealized P&L separately and do not present it as an annual return.
- **Corporate-action sanity check (mandatory)**: if avg cost is wildly off CMP (> ±40%), check for a split/bonus (`get_corporate_actions`; an older action shows up as a step in `get_history`) before computing P&L — a 1:1 bonus halves the price and a naive comparison reports a phantom ±50% move. Check the action date, purchase history, quantities and whether the broker already adjusted the cost before changing it, so you never adjust twice. If you cannot settle it, keep the broker's cost and mark the P&L unavailable. Note the standalone-vs-consolidated ratio caveat the same way.
- Ask once for total portfolio value and the intended equity:debt:cash split if not stated and not derivable from the book; otherwise compute splits from holdings and say the drift section is **relative**.

## Section 2 — Per-stock health (hybrid)

Light on a large book, deep only where there is a problem, with **no single-stock logic duplicated** from `deep-analysis`.

1. **Cheap drift check on *all* stock holdings** — one `get_company_fundamentals` snapshot per name, read against the reference.md rubric (ROCE trend, debt creep, promoter pledge, earnings trajectory). Flag *changes for the worse* — "would I buy this today?" — not static imperfection. Use the same basis (standalone or consolidated) for every period.
2. **Bounded deep-dive on the worst flags only** — auto-invoke **`deep-analysis --quick`** (via `Skill`) **only** on holdings that trip a drift / exit / concentration flag, capped at a small N (**≤ 5 worst**) so the fan-out can't blow up on a large book. Feed its verdict into the holding's row.
3. **Suggest `/deep-analysis <T>` (full)** on the most serious flags rather than auto-running full diligence.
4. **Trading positions** — run `check_trade` on the recorded trade idea and its fills. Apply only that plan's stop, target, invalidation and time stop; a missing entry date or time-stop rule is a gap. A breached stop means recommend an exit, not that one happened.

## Section 3 — Per-fund health (hybrid, mirrors stocks)

Same shape as stocks; **`mf-analysis` owns all fund depth**.

1. **`mf-analysis quick` on *all* held funds** (via `Skill`) — the descriptive digest: NAV, AUM, expense vs category, returns 1/3/5Y, AUM-stability, held XIRR. Cheap, no look-through, **no category rank** (that needs the scan `quick` deliberately skips).
2. **Targeted `mf-analysis deep` on at most five flagged funds only** — flag funds on sourced category returns, expense ratios or AUM changes. Your XIRR on a fund is not comparable with a category's time-weighted return. Bounded the same way as the stock deep-dive; the deep run is what confirms style drift and standing among peers.
3. **Suggest `/mf-analysis` (full)** on serious fund flags, and on any same-category overlap question (holdings-overlap needs the look-through this skill defers).

## Section 4 — Multi-dimensional allocation

Run `scripts/allocation.py` over the normalized book — enrich each holding with the tags gathered above (`sector`, `market_cap`, `amc`, `style`, `asset_class`, `kind`, current `value`), and pass the pre-aggregated cap & style splits as `breakdowns`:

```bash
python3 <plugin>/skills/portfolio-review/scripts/allocation.py --book <book.json>
```

It returns per-dimension breakdowns with coverage, asset-class drift vs target, and the ranked concentration flags. Rebalancing amounts appear only when every holding is valued and classified. The default thresholds are in reference.md. Dimension inputs:

- **Asset class** — equity : debt : cash vs the stated target (ask once if not given; report **relative** otherwise).
- **Market cap** — from **`get_stock_ratios.cap_rank`** for direct stocks and the `mf-analysis` look-through for the fund sleeve. **A personal source reports what you hold, never what tier it is** — an IndMoney/broker cap breakdown is not a classification input. Rank bands, never absolute ₹Cr bands: bands reported a real small-cap fund as 0% small-cap.
  **Read the small+micro threshold against the tape, not in a vacuum**: `get_market_context(mode="quick")`, then read its persisted full context for `valuation["NIFTY SMALLCAP 250"].stance` and `relative.percentile_spread`; those blocks are not in the compact tool return. Keep the user's own limit and describe valuation as context; do not change the limit because of a percentile. If the user set no limit, say which default you used.
- **Investing style** — the growth / value / factor mix from the `mf-analysis` look-through.
- **AMC · Sector · Single stock** — aggregated from the per-holding tags.

When `asset_drift.coverage_complete` is false, `move_value` is null and `rebalance` is empty; do not work out the trades from the percentages yourself. AMC flags are a share of the fund sleeve; other percentages are a share of the valued book. Rebalancing prefers fresh inflows over taxable switches (reference.md).

## Section 5 — Output

Markdown report: the holdings table with a verdict column (**KEEP / TRIM / EXIT / REVIEW** + one falsifiable one-line reason each), the multi-dimensional allocation breakdown, the concentration flags with ₹ amounts, and a prioritized action list (**max ~5**) of concrete **rebalancing ₹ moves** plus explicit **suggestions to run `/deep-analysis <T>` or `/mf-analysis <F>`** on the flagged names. Save to `artifacts/portfolio-review/YYYY-MM-DD.md` (`paths.report_path("portfolio-review")`).

Holdings values are sensitive — the **full table lives in the artifact**; in chat, give only the verdicts, the concentration flags (with ₹), and the actions.

`quick` writes only the `investments-block` digest to the artifact and returns it — no per-holding table, no deep fan-out.

## Section 6 — Degradation specifics

- **No IndMoney/broker** → manual paste / CSV / `watchlist.json` fallback; XIRR labelled **unavailable**.
- **`mf-analysis` / `deep-analysis` not invokable** → a labelled gap + a manual `/…` suggestion instead of the auto deep-dive.
- **Missing target allocation** → report the relative splits and say drift is relative.

## Alerts this skill raises (via `manage_alerts`)

For a supported plan-drift finding, call `manage_alerts(action="add", subject_type="portfolio", subject_id="portfolio", kind="rebalance_due", created_by="portfolio-review", check="review_allocation", severity="watch", text="<sourced drift and coverage limitation>", suggest="/portfolio-review", dedup_key="rebalance")`. It stays open until a later review confirms the drift is fixed and dismisses it.
