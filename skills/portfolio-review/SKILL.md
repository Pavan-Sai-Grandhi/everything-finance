---
name: portfolio-review
description: Audit the real cross-broker book — stocks and mutual funds — for what to exit, trim, or fix. XIRR-driven laggard detection, multi-dimensional allocation & concentration (asset class, market-cap, AMC, style, sector, single-stock), cheap per-holding health with a bounded deep-dive only on flagged names, and rebalancing moves in ₹. Runs `quick` (a compact investments digest other skills consume) or `deep` (the full review). Use when the user asks to review their portfolio, holdings, or positions, asks "should I exit anything", wants a risk check, or mentions rebalancing.
argument-hint: "[holdings inline / CSV / watchlist.json] [--quick | --deep]"
allowed-tools: Read, Write, Skill, mcp__indmoney__*, mcp__plugin_everything-finance_indmoney__*, mcp__kite__*, mcp__plugin_everything-finance_kite__*, mcp__upstox__*, mcp__plugin_everything-finance_upstox__*, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-funds__*, mcp__plugin_everything-finance_finance-funds__*, mcp__finance-personal__*, mcp__plugin_everything-finance_finance-personal__*, mcp__finance-workflow__manage_alerts, mcp__plugin_everything-finance_finance-workflow__manage_alerts
---

# Portfolio Review

Looks for what to **exit, trim or fix** on the real book. It owns the portfolio view (allocation,
concentration, laggards) and defers per-name depth: stocks to `deep-analysis`, funds to
`mf-analysis`. It never re-implements single-name analysis.

**Method:** `methods/portfolio.md`, with `methods/fundamentals.md` for the drift check and
`methods/trade-management.md` for trading positions.

## Modes

- **`deep`** (default on direct invocation): every section below, the holdings table with
  verdicts, and a prioritised action list.
- **`quick`** (wealth-manager's investments leg, or `--quick`): allocation, concentration flags,
  the top exit and laggard flags and the return summary, returned as the `investments-block`
  (`finance/contracts.md` → *Convention: investments-leg digest*). No per-holding deep fan-out.

## 1. The book

Review the real book, never a hand-typed approximation. Read it as `RULES.md` → *Reading your
holdings* describes: an `equity` pass and an `mf` pass, falling back to a pasted list, a CSV or
the watchlist positions. When the invocation names payload files, they are the book: resolve them
and make no broker call of your own (that is how the `quick` leg reaches a book from a context with
no broker grant). When a gap names stocks held through a linked broker without cost, re-resolve
the equity pass with `prefer=<broker>`.

- **XIRR**: neither IndMoney nor the brokers supply it, so it is normally unavailable; say so,
  and never present unrealized P&L as an annual return.
- **Corporate-action check (mandatory)**: if the average cost is more than ±40% off the price,
  check for a split or bonus (`get_corporate_actions`; an older one shows as a step in
  `get_history`) before computing P&L. Check the action date, the purchase history, the
  quantities and whether the broker already adjusted the cost, so you never adjust twice. If it
  cannot be settled, keep the broker's cost and mark the P&L unavailable.
- Ask once for the total portfolio value and the intended equity:debt:cash split if neither is
  stated nor derivable; otherwise say the drift read is relative.

## 2. Per-stock health

1. **Drift check on every stock**: one `get_company_fundamentals` snapshot per name, read
   against the rubric (returns trend, debt creep, promoter pledge, earnings path), on the same
   standalone or consolidated basis for every period. Flag changes for the worse ("would I buy
   this today?"), not static imperfection.
2. **Bounded deep-dive**: `deep-analysis --quick` (via `Skill`) only on holdings that trip a drift,
   exit or concentration flag, at most the five worst.
3. Suggest `/deep-analysis <T>` (full) on the most serious flags rather than running it.
4. **Trading positions**: `check_trade` on the recorded trade idea and its fills, applying only
   that plan's stop, target, invalidation and time stop. A breached stop means recommend an exit,
   not that one happened.

## 3. Per-fund health

1. `mf-analysis --quick` (via `Skill`) on every held fund.
2. `mf-analysis --deep` on at most five funds flagged on sourced category returns, expense ratios
   or AUM changes. A Regular-plan or IDCW flag is an action on its own (`methods/portfolio.md`),
   not a reason for a deep run. Your XIRR on a fund is not comparable with a category's time-weighted return.
3. Suggest `/mf-analysis` on serious flags and on any same-category overlap question.

## 4. Allocation

Tag each holding (`sector`, `market_cap`, `amc`, `style`, `asset_class`, `kind`, current `value`),
write the book with any `targets` and the pre-aggregated cap and style `breakdowns` to a JSON file,
and call `review_allocation(book=<file>)`.

- **Asset class** against the stated target; relative when there is none.
- **Market cap** from `get_stock_ratios.cap_rank` for direct stocks and the `mf-analysis`
  look-through for the fund sleeve, never from a personal source's own breakdown. Read the
  small-and-micro limit against the tape: `get_market_context(mode="quick")`, then the persisted
  context's `valuation["NIFTY SMALLCAP 250"].stance` and `relative.percentile_spread`. Keep the
  user's own limit; valuation is context, not a reason to move it. Say which default applied if
  the user set none.
- **Style** from the look-through; **AMC, sector, single stock** from the tags.

When `asset_drift.coverage_complete` is false, `move_value` is null and `rebalance` empty: never
work out the trades from the percentages yourself.

## 5. Output

A markdown report at `artifacts/portfolio-review/<YYYY-MM-DD>.md`: the holdings table with a
verdict column (KEEP / TRIM / EXIT / REVIEW, each with one falsifiable reason), the allocation
breakdown, the concentration flags with ₹ amounts, and at most five prioritised actions: concrete
rebalancing moves and suggestions to run `/deep-analysis` or `/mf-analysis` on flagged names.
Holdings values are sensitive: the full table lives in the artifact; chat gets the verdicts, the
flags with ₹, and the actions. `quick` writes only the `investments-block`.

Degradation: no personal source means the manual fallback with XIRR unavailable; an
uninvokable `mf-analysis` or `deep-analysis` becomes a gap and a manual suggestion; a missing
target allocation means relative splits only.

## Alerts

For a supported plan-drift finding: `manage_alerts(action="add", subject_type="portfolio",
subject_id="portfolio", kind="rebalance_due", created_by="portfolio-review",
check="review_allocation", severity="watch", text="<sourced drift and coverage limitation>",
suggest="/portfolio-review", dedup_key="rebalance")`. It stays open until a later review confirms
the drift is fixed and dismisses it.
