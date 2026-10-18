---
name: trade-tracker
description: Track your live broker positions against the rationale that put you in them, and flag when to hold or exit early. Reads live positions read-only via IndMoney (net worth across assets) or your broker (Kite/Upstox), takes exact fills from broker order history, matches each open position to its trade-idea artifact (from discover), a deep-analysis report, a strategy spec, or a rationale you type, then re-validates the thesis — stop hit, target hit, time stop, broken setup, or regime change — and recommends hold / trim / exit. Use whenever the user asks to check open trades, review positions, "is my thesis still valid", "should I exit X", track a trade, or sync the broker.
argument-hint: "[optional: SYMBOL to check one position | 'all' | broker:kite|upstox]"
allowed-tools: Read, Write, Skill, mcp__indmoney__*, mcp__plugin_everything-finance_indmoney__*, mcp__kite__*, mcp__plugin_everything-finance_kite__*, mcp__upstox__*, mcp__plugin_everything-finance_upstox__*, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-personal__resolve_holdings, mcp__plugin_everything-finance_finance-personal__resolve_holdings, mcp__finance-personal__check_trade, mcp__plugin_everything-finance_finance-personal__check_trade, mcp__finance-workflow__manage_alerts, mcp__plugin_everything-finance_finance-workflow__manage_alerts
---

# Trade Tracker: does the reason I'm in this trade still hold?

One question per open position: is the original rationale intact, or is an early exit warranted?
It reads what you hold and your exact fills, pairs each position with why you took it, and
re-checks that against today's price and regime. It recommends; you place the order.

**Method:** `methods/trade-management.md`.

## 1. Live state and fills

Read the book as `RULES.md` → *Reading your holdings* describes, `equity` slice, honouring a
`broker:kite|upstox` override. With no source connected, stop and ask the user to authenticate;
never fabricate positions. Take only the fields you need (symbol, quantity, average, price).

The entry fill comes **only** from broker order history (`mcp__kite__*`, `mcp__upstox__*`) or a
real fill already recorded on the artifact (`fill_avg`, `entry_date`); never from IndMoney's
average cost. Without either, report live health but make R and the time stop a gap ("entry
unknown — connect a broker for fills").

## 2. Pair each position with its rationale

In order: the most recent open trade-idea artifact `artifacts/state/trades/<SYMBOL>-*.yml` (from
discover: plan, `thesis_invalidation`, `strategy`, `regime_at_creation`); a deep-analysis report
or the strategy spec the idea names; otherwise ask the user for the thesis (stop, target, what
would prove it wrong) and write a new artifact `artifacts/state/trades/<SYMBOL>-<today>.yml`
(`finance/contracts.md` → *Artifact: trade-idea*).

When order history matches an `idea`, set `status: open` and record `fill_avg`, `entry_date` and
the filled quantity in `sizing.qty`; keep `plan.entry` and `plan.stop` unchanged. After a partial
exit, `sizing.qty` stays the entry quantity and the remaining quantity goes to `check_trade`.

**Close only when broker exit executions cover the whole entry quantity.** A position missing
from holdings, a failed fetch, an exit recommendation or the user agreeing to it proves nothing:
leave the artifact open, note the mismatch in `tracker_log`, check order history, and mark the
position's alerts done only after the close is confirmed.

## 3. Re-validate mechanically

`check_trade(trade=<artifact>, entry=<broker fill>, qty=<live qty>, ltp=<live price>)`. A personal
price values unrealized P&L only. Report stale bars and every gap, and save the envelope to
`artifacts/trade-tracker/<date>/validate-<SYMBOL>.json`. Pass `ohlcv=<csv>` only when the series
must come from a file.

## 4. Judge what the tool cannot

- **`manual_review` conditions**: check them with `get_filings` and `get_news` (or a
  `/filings-watch` or `/deep-analysis` run when the user wants depth).
- **Regime**: for a strategy-linked trade, load the spec's `regime_required` and
  `get_market_context(mode="quick")`; a failed regime is a regime exit even when price has not
  hit the stop.

`check_trade`'s verdict is the floor: a broken qualitative thesis or a failed regime can turn a
mechanical HOLD into a recommended exit; say why.

## 5. Report

Fill `assets/tracker-report.md`: one row per position with symbol, quantity, average and price,
unrealized R and P&L, the verdict, a one-line reason and the action (hold, trim or exit, with the
level to watch). Save to `artifacts/trade-tracker/<date>.md` and lead the chat summary with
anything that needs action today. Add a Data gaps line for positions with no rationale or no price
data. Append a dated `tracker_log` note (recommendation and data date) to each artifact.

On a confirmed close, write `result` from broker fills and charges as the method's *Recording a
close* describes; never copy `check_trade`'s unrealized figures into it. Fictional example (fill
₹100, stop ₹90, quantity 50):

```yaml
status: closed
result:
  exit_date: 2026-07-01
  exit_reason: EXIT_STOP        # EXIT_STOP | EXIT_THESIS | EXIT_TARGET | EXIT_TIME | MANUAL
  exit_price: 89.5
  exit_qty: 50                  # reconciles to sizing.qty
  charges: 25                   # actual entry + exit charges
  realized_R: -1.1
  realized_pnl: -550
  holding_sessions: 12
  execution:
    source: kite                # kite | upstox
    exit_trade_ids: [example-trade-id]
```

`/strategy-manager optimize` verifies this evidence before using a close. Never make up execution
ids or charges.

## Alerts (`manage_alerts`, `created_by: trade-tracker`, `subject_type: stock`)

- **Exit watch**: the stop and the target as `price_cross` triggers (long: `<=` stop, `>=`
  target; short reversed), `metric: close`, `severity: act` for the stop,
  `suggest: "/trade-tracker <SYMBOL>"`, `dedup_key: stop-<SYMBOL>` and `target-<SYMBOL>`.
- **Time stop**: `check: trade-tracker`, `severity: watch`, `dedup_key: timestop-<SYMBOL>`. Count
  sessions from `entry_date` at each check; never turn them into a calendar date.
- **Regime change** (strategy-linked): `kind: regime_change`, `check: trade-tracker`,
  `severity: watch`, `text: "regime no longer supports this strategy"`,
  `dedup_key: regime-<SYMBOL>`.

After a confirmed full exit, dismiss the position's alerts.
