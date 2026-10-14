---
name: trade-tracker
description: Track your live broker positions against the rationale that put you in them, and flag when to hold or exit early. Reads live positions read-only via IndMoney (net worth across assets, with XIRR) or your broker (Kite/Upstox), takes exact fills from broker order history, matches each open position to its trade-idea artifact (from discover), a deep-analysis report, a strategy spec, or a rationale you type, then re-validates the thesis — stop hit, target hit, time stop, broken setup, or regime change — and recommends hold / trim / exit. Use whenever the user asks to check open trades, review positions, "is my thesis still valid", "should I exit X", track a trade, or sync the broker.
argument-hint: "[optional: SYMBOL to check one position | 'all' | broker:kite|upstox]"
allowed-tools: Read, Write, Bash, Skill, mcp__indmoney__*, mcp__plugin_everything-finance_indmoney__*, mcp__kite__*, mcp__plugin_everything-finance_kite__*, mcp__upstox__*, mcp__plugin_everything-finance_upstox__*, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*
---

# Trade Tracker — does the reason I'm in this trade still hold?

This skill answers one question per open position: **is the original rationale still intact, or is an early exit warranted?** It reads what you actually hold (IndMoney net worth, or the broker) and your exact fills (broker order history), pairs each position with *why* you took the trade, and re-checks that "why" against today's price and regime.

Read `references/reference.md` first — it defines the exit-decision framework this skill enforces.

## 1. Source live state, and fills (read-only)

**Live position state — via `finance/compute/holdings.py`** (precedence **IndMoney → broker**). The resolver is a script and cannot call MCP tools, so call each connected source yourself: IndMoney `networth_holdings` once per `asset_type` (`IND_STOCK` and `US_STOCK` for equity, `MF` for funds; it serves one type per call), and the broker's holdings and positions. **Write each raw payload to a file** under `paths.tmp_dir("holdings")`, then resolve and take the equity slice:
```bash
PYTHONPATH=<plugin> python3 -m finance.compute.holdings --indmoney <ind-stock.json> --indmoney <ind-us.json> --kite <kite.json> --equity-only
```
The envelope gives each open position's name/symbol, qty, ltp and value. IndMoney has **no XIRR** and no NSE symbol (its `investment_code` is internal), and gives no cost for stocks held through a linked broker (`cost_basis: unreported_by_linked_broker`); take cost and fills from that broker, which the resolver's gap names. Detect connections by tool presence (`mcp__indmoney__*`, `mcp__kite__*` = Zerodha, `mcp__upstox__*` = Upstox); honor a `broker:kite|upstox` override. If **no** source is connected, stop and tell the user to authenticate — never fabricate positions.

**Fill price + date — broker order history ONLY.** The exact entry that R-multiple and the time-stop depend on comes from the broker's `orders`/`trades` history (`mcp__kite__*` / `mcp__upstox__*`), or from a real fill already recorded on the artifact (`fill_avg` / `entry_date`). **IndMoney's avg-cost is never used to approximate an entry.** So:
- **Broker connected (or a recorded fill exists)** → use the real fill; full re-validation.
- **IndMoney-only, no broker, no recorded fill** → still report live position health (CMP, P&L, XIRR, state), but **R-multiple and time-stop are a labelled gap** ("entry unknown — connect a broker for fills").

Extract only the fields you need (symbol, qty, avg, ltp); don't dump the whole payload into context.

## 2. Pair each position with its rationale

For every open position, find the "why" in this order:
1. **Trade-idea artifact** — `artifacts/state/trades/<SYMBOL>-*.yml` (persisted by `discover` on confirmation). Most recent open one wins. This is the richest source: it carries `plan` (entry/stop/target/time-stop), `thesis_invalidation`, `strategy` link, and `regime_at_creation`.
2. **Deep-analysis / strategy artifact** — a `deep-analysis` report for the ticker, or a `strategy-manager` spec named in the idea's `strategy` field.
3. **Custom rationale** — if no artifact exists, ask the user for the thesis (stop, target, and what would prove it wrong) and **write a fresh artifact** to `artifacts/state/trades/<SYMBOL>-<today>.yml` (same trade-idea schema discover uses — see `<plugin>/finance/contracts.md`) so the position is tracked from now on.

When broker order history matches an artifact at `status: idea`, set `status: open` and record `fill_avg`, `entry_date` and the filled quantity in `sizing.qty`. Keep `plan.entry` and `plan.stop` unchanged; the stop defines the initial risk. After a partial exit, leave `sizing.qty` as the entry quantity and pass the remaining quantity to `check_trade`.

**Close only when broker exit executions cover the whole entry quantity.** A position missing from the holdings, a failed fetch, an exit recommendation, or the user agreeing to it does not prove an exit. Leave the artifact open, note the mismatch in `tracker_log`, and check order history. Mark the position's alerts done only after the close is confirmed.

## 3. Re-validate the thesis (mechanical, per position)

Call `check_trade` with the **real fill** as `entry` (or let it read recorded `fill_avg`) and the absolute remaining live `qty`. A personal `ltp`, if passed, values unrealized P&L only; stop, target and thesis checks use market price history:
```
check_trade(trade="artifacts/state/trades/<SYMBOL>-<date>.yml",
            entry=<broker_fill>, qty=<live_qty>, ltp=<live_ltp>)
```
It returns a verdict in priority order — **EXIT_STOP → EXIT_THESIS → EXIT_TARGET → EXIT_TIME → HOLD** — plus unrealized R, P&L, and any conditions it could not parse under `manual_review`. `as_of` is the decision bar's date, `metrics.price` its close, and `metrics.mark_price`/`mark_source` the price used for unrealized P&L. Report stale bars and every gap. Sessions held count from the day after `entry_date`; if history does not reach the entry, the time stop is unassessed. Every session after the fill is checked, so a stop or target hit earlier is reported with its date even if price has recovered. On the fill day, or with no fill date, the day's high and low may predate the entry, so only the close is used. Save the returned envelope to `artifacts/trade-tracker/YYYY-MM-DD/validate-<SYMBOL>.json`. (Pass `ohlcv=<csv path>` when the price series must come from a file instead of the live fetch.) **When no real fill is available**: skip the R-multiple/time-stop math, record it as a Data gap, and still report the price-mechanical checks (stop/target/thesis vs CMP) and live health.

## 4. Judge what the tool can't (qualitative + regime)

`check_trade` handles price-mechanical checks. You handle the rest:
- **`manual_review` conditions** — qualitative invalidations like "earnings miss", "promoter pledge increase", "sector downgrade". Check them with `get_filings` / `get_news` (or a `/filings-watch` or `/deep-analysis` run if the user wants depth) and decide if the thesis is broken.
- **Regime change (strategy-linked trades)** — if the artifact has a `strategy`, load that spec's `regime_required`, re-read the live market context with `get_market_context(mode="quick")`, and if the regime now **fails** the strategy's conditions, flag a regime-exit even when price hasn't hit the stop — the edge that justified the trade is gone.

Fold these into the final call: `check_trade`'s verdict is the floor; a broken qualitative thesis or a failed regime can turn a mechanical HOLD into a recommended exit (say why).

## 5. Report

Render `assets/tracker-report.md` (bundled) — one row per position with: symbol, qty, avg/LTP, unrealized R & P&L, the verdict, the one-line reason, and the **action** (Hold / Trim / Exit + the level to watch). Save to `artifacts/trade-tracker/YYYY-MM-DD.md` (`paths.report_path("trade-tracker")`; per-position `validate-<SYMBOL>.json` work papers go under `artifacts/trade-tracker/YYYY-MM-DD/` via `paths.report_dir`) and summarize in chat, leading with anything that needs action today. Include a **Data gaps** line for positions with no rationale found or no price data.

## Alerts this skill raises (via `manage_alerts`)

As it re-validates each open position, write watch-items for `daily-brief` (set `dedup_key` per symbol so a re-run updates in place):

- **`price_cross` exit-watch** — the active stop and target as cheap triggers (long: `<=` stop and `>=` target; short: `>=` stop and `<=` target; `trigger: {metric: close, op: <operator>, level: <level>}`; `subject: {type: stock, id: <SYMBOL>}`, `created_by: trade-tracker`, `severity: act` for the stop, `action.suggest: "/trade-tracker <SYMBOL>"`, `dedup_key: stop-<SYMBOL>` / `target-<SYMBOL>`).
- **`time_stop`** — a revalidation watch (`trigger: {check: trade-tracker}`, `severity: watch`, `dedup_key: timestop-<SYMBOL>`, `action.suggest: "/trade-tracker <SYMBOL>"`). Count trading sessions from `entry_date` at each check; do not turn them into a calendar due date.
- **`regime_change`** (strategy-linked trades) — when the live regime fails the linked strategy's `regime_required`, raise a `regime_change` alert (`trigger: {check: trade-tracker}`, `severity: watch`, `action.text` = "regime no longer supports this strategy", `dedup_key: regime-<SYMBOL>`). On confirmed execution of the full exit, dismiss the position's alerts via `alert-manager` (status `done`).

Append a dated `tracker_log` note (recommendation and data date) on each run. Change status as in §2 only with execution evidence.

**On a confirmed close, write `result` from broker fills and charges:** the quantity-weighted exit price across all exits, the last execution date, and the trade IDs. Net P&L is fills minus charges; realized R is net P&L ÷ ((fill − original stop) × quantity), with signs reversed for shorts. Never copy `check_trade`'s unrealized figures into `result`. If charges or the original stop are unknown, close it with those figures null and a gap; the learning script will skip it.

Fictional schema example (entry fill ₹100, original stop ₹90, quantity 50):
```yaml
status: closed
result:
  exit_date: 2026-07-01
  exit_reason: EXIT_STOP        # STOP | THESIS | TARGET | TIME use EXIT_ prefix; or MANUAL
  exit_price: 89.5
  exit_qty: 50                  # must reconcile to original sizing.qty
  charges: 25                  # actual total entry + exit charges
  realized_R: -1.1
  realized_pnl: -550
  holding_sessions: 12
  execution:
    source: kite               # kite | upstox
    exit_trade_ids: [example-trade-id]
```

`/strategy-manager optimize <strategy>` checks this evidence and arithmetic before using a close. Never make up execution IDs or charges for an old artifact. An unverified close gives `REVIEW`, and fewer than ten verified closes cannot change a strategy's status or replace its backtest figures.

End with the reminder: **this skill recommends; you place the order.**
