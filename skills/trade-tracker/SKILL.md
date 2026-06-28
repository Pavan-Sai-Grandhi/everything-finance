---
name: trade-tracker
description: Track your live broker positions against the rationale that put you in them, and flag when to hold or exit early. Reads live positions read-only via IndMoney (net worth across assets, with XIRR) or your broker (Kite/Upstox), takes exact fills from broker order history, matches each open position to its trade-idea artifact (from find-trade), a deep-analysis report, a strategy spec, or a rationale you type, then re-validates the thesis — stop hit, target hit, time stop, broken setup, or regime change — and recommends hold / trim / exit. Use whenever the user asks to check open trades, review positions, "is my thesis still valid", "should I exit X", track a trade, or sync the broker.
argument-hint: "[optional: SYMBOL to check one position | 'all' | broker:kite|upstox]"
allowed-tools: Read, Write, Bash, WebFetch, Skill, mcp__indmoney__*, mcp__kite__*, mcp__upstox__*
---

# Trade Tracker — does the reason I'm in this trade still hold?

This skill answers one question per open position: **is the original rationale still intact, or is an early exit warranted?** It reads what you actually hold (IndMoney net worth, or the broker) and your exact fills (broker order history), pairs each position with *why* you took the trade, and re-checks that "why" against today's price and regime. It never places orders — the hosted IndMoney/Kite/Upstox MCPs are read-only by design, and so is this plugin (CLAUDE.md). You execute exits yourself.

**Sources for this skill only:** the shared `lib/holdings.py` resolver for live position state (**IndMoney** `mcp__indmoney__*` → broker fallback), the broker MCP (Kite/Upstox) for **order/trade history** (the only source of exact fills), the trade artifacts under `artifacts/state/trades/` and a stock's deep-analysis under `artifacts/stocks/<TICKER>/<date>/` (rationale), `scripts/validate_trade.py` + yfinance (price/indicator re-check), and `strategy-manager`'s `regime.py` for strategy-linked regime checks. Read `references/reference.md` first — it defines the exit-decision framework this skill enforces.

## 1. Source live state, and fills (read-only)

**Live position state — via `lib/holdings.py`** (precedence **IndMoney → broker**). The resolver runs in script context and cannot call MCP tools, so for each connected source invoke its holdings tool (IndMoney `networth_holdings`; broker holdings + positions), **write the raw payload to a temp file** under `paths.tmp_dir("holdings")`, then resolve and take the equity slice:
```bash
python3 <plugin>/lib/holdings.py --indmoney <ind.json> --kite <kite.json> --equity-only
```
The envelope gives each open position's symbol / qty / avg / ltp / **P&L and XIRR** (IndMoney populates XIRR; broker leaves it `None`). All sources are read-only by design (CLAUDE.md) — never place an order. Detect connections by tool presence (`mcp__indmoney__*`, `mcp__kite__*` = Zerodha, `mcp__upstox__*` = Upstox); honor a `broker:kite|upstox` override. If **no** source is connected, stop and tell the user to authenticate — never fabricate positions.

**Fill price + date — broker order history ONLY.** The exact entry that R-multiple and the time-stop depend on comes from the broker's `orders`/`trades` history (`mcp__kite__*` / `mcp__upstox__*`), or from a real fill already recorded on the artifact (`fill_avg` / `entry_date`). **IndMoney's avg-cost is never used to approximate an entry.** So:
- **Broker connected (or a recorded fill exists)** → use the real fill; full re-validation.
- **IndMoney-only, no broker, no recorded fill** → still report live position health (CMP, P&L, XIRR, state), but **R-multiple and time-stop are a labelled gap** ("entry unknown — connect a broker for fills"). Do not infer entry from the IndMoney avg.

Extract only the fields you need (symbol, qty, avg, ltp); don't dump the whole payload into context.

## 2. Pair each position with its rationale

For every open position, find the "why" in this order:
1. **Trade-idea artifact** — `artifacts/state/trades/<SYMBOL>-*.yml` (persisted by `find-trade` on confirmation). Most recent open one wins. This is the richest source: it carries `plan` (entry/stop/target/time-stop), `thesis_invalidation`, `strategy` link, and `regime_at_creation`.
2. **Deep-analysis / strategy artifact** — a `deep-analysis` report for the ticker, or a `strategy-manager` spec named in the idea's `strategy` field.
3. **Custom rationale** — if no artifact exists, ask the user for the thesis (stop, target, and what would prove it wrong) and **write a fresh artifact** to `artifacts/state/trades/<SYMBOL>-<today>.yml` (same trade-idea schema find-trade uses — see `<plugin>/lib/contracts.md`) so the position is tracked from now on. A position with no recorded rationale is the exact problem this skill exists to fix — capture it.

When a broker fill matches an artifact still at `status: idea`, **promote it to `status: open`** and write the real fill back into `sizing.qty`, a new `fill_avg` field, and `entry_date` (the fill date from broker order history) — don't overwrite the planned `entry`; record both. Promotion always requires a real broker fill; IndMoney live state never promotes an idea on its own. When a position is gone from the broker (or you recommend and the user confirms an exit), mark its artifact `status: closed` and write the `result` block described in §5 — that block is what `strategy-manager optimize` later aggregates, so closing a trade without it breaks the learning loop.

## 3. Re-validate the thesis (mechanical, per position)

Run the bundled validator with the **real fill** as `--entry` (broker order history, or the recorded `fill_avg`) and the resolved live `--qty`/`--ltp`, so the verdict reflects the real position, not the plan:
```bash
python3 <skill-dir>/scripts/validate_trade.py \
  --trade artifacts/state/trades/<SYMBOL>-<date>.yml \
  --entry <broker_fill> --qty <live_qty> --ltp <live_ltp> \
  --out artifacts/trade-tracker/YYYY-MM-DD/validate-<SYMBOL>.json
```
It fetches OHLCV (yfinance) and returns a verdict in priority order — **EXIT_STOP → EXIT_THESIS → EXIT_TARGET → EXIT_TIME → HOLD** — plus unrealized R, P&L, and any conditions it could not parse under `manual_review`. (For offline/testing or when yfinance lacks the symbol, pass `--ohlcv <csv>` instead.) **When no real fill is available** (IndMoney-only, no broker, no recorded `fill_avg`): skip the R-multiple/time-stop math, record it as a Data gap, and still report the price-mechanical checks (stop/target/thesis vs CMP) and live health — never pass the IndMoney avg as `--entry`.

## 4. Judge what the script can't (qualitative + regime)

The script handles price-mechanical checks. You handle the rest:
- **`manual_review` conditions** — qualitative invalidations like "earnings miss", "promoter pledge increase", "sector downgrade". Check them with the plugin's allowed news/filings paths (WebFetch / a quick `/filings-watch` or `/deep-analysis` if the user wants depth) and decide if the thesis is broken.
- **Regime change (strategy-linked trades)** — if the artifact has a `strategy`, load that spec's `regime_required`, re-read the live regime (`python3 <strategy-manager-dir>/scripts/regime.py --out artifacts/regime/YYYY-MM-DD.json`), and if the regime now **fails** the strategy's conditions, flag a regime-exit even when price hasn't hit the stop — the edge that justified the trade is gone.

Fold these into the final call: the script's verdict is the floor; a broken qualitative thesis or a failed regime can turn a mechanical HOLD into a recommended exit (say why).

## 5. Report

Render `assets/tracker-report.md` (bundled) — one row per position with: symbol, qty, avg/LTP, unrealized R & P&L, the verdict, the one-line reason, and the **action** (Hold / Trim / Exit + the level to watch). Save to `artifacts/trade-tracker/YYYY-MM-DD.md` (`paths.report_path("trade-tracker")`; per-position `validate-<SYMBOL>.json` work papers go under `artifacts/trade-tracker/YYYY-MM-DD/` via `paths.report_dir`) and summarize in chat, leading with anything that needs action today. Include a **Data gaps** line for positions with no rationale found or no price data.

## Alerts this skill raises (via `lib/alerts.py`)

As it re-validates each open position, write watch-items for `daily-brief` (set `dedup_key` per symbol so a re-run updates in place):

- **`price_cross` exit-watch** — the active stop and target as cheap triggers (`trigger: {metric: close, op: "<", level: <stop>}` and a `>=` target watch; `subject: {type: stock, id: <SYMBOL>}`, `created_by: trade-tracker`, `severity: act` for the stop, `action.suggest: "/trade-tracker <SYMBOL>"`, `dedup_key: stop-<SYMBOL>` / `target-<SYMBOL>`).
- **`time_stop`** — a date alert at the plan's time-stop (`trigger: {due: <entry + time_stop_sessions>}`, `severity: watch`, `dedup_key: timestop-<SYMBOL>`).
- **`regime_change`** (strategy-linked trades) — when the live regime fails the linked strategy's `regime_required`, raise a `regime_change` alert (`trigger: {check: trade-tracker, args: {symbol: <SYMBOL>}}`, `severity: watch`, `action.text` = "regime no longer supports this strategy", `dedup_key: regime-<SYMBOL>`). On exit, dismiss the position's alerts via `alert-manager` (status `done`).

Update each artifact's `status` and append a dated `tracker_log` note (verdict + date) so the next run sees the history.

**On close, write the `result` block** (this is the feedback that lets `strategy-manager` optimize/retire the linked strategy) — use the validator's exit numbers:
```yaml
status: closed
result:
  exit_date: 2026-07-01
  exit_reason: EXIT_STOP        # EXIT_STOP | EXIT_THESIS | EXIT_TARGET | EXIT_TIME | MANUAL
  exit_price: 1253.2
  realized_R: -1.0             # the validator's unrealized_R at exit becomes realized
  realized_pnl: -4100
  holding_sessions: 12
```
For strategy-linked closed trades, mention that `/strategy-manager optimize <strategy>` can now fold this outcome in (it needs ≥ 10 closed trades before it acts).

End with the standard risk note and a reminder: **this skill recommends; you place the order. No automated execution.**
