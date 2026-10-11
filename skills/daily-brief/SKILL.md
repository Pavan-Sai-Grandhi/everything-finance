---
name: daily-brief
description: Morning market one-pager — index levels and tone, a market-moving news digest, sector leaders/laggards, the open-alert inbox and any actions due, a strictly-capped opportunities shortlist, watchlist filings and news, and open-position health — formatted for Telegram. Use when the user asks for the daily brief, morning summary, "what's the market doing", "anything I should know today", or wants a pre-market/post-market rundown.
argument-hint: "[optional: 'send' to push to Telegram immediately]"
allowed-tools: Read, Write, Bash, mcp__indmoney__*, mcp__plugin_everything-finance_indmoney__*, mcp__kite__*, mcp__plugin_everything-finance_kite__*, mcp__upstox__*, mcp__plugin_everything-finance_upstox__*, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*
disable-model-invocation: false
---

# Daily Brief

A fast composite — breadth over depth; every section is 2–4 lines. Target: readable in 60 seconds on a phone.

**Sources for this skill only:** `finance-market` — `get_market_context` / `get_indices` / `get_flows` (market state), `get_quote` (current decision price) and `get_history` (completed-session close); `finance-company` — `get_news` (`India stock market` for the market digest; `<company> share` per name) and `get_filings` (NSE announcements + materiality); plus `manage_alerts` (the alert inbox) and live holdings through the shared `finance/compute/holdings.py` resolver (**IndMoney** first, **broker MCP** Kite/Upstox fallback). Method specifics live in this skill's `references/reference.md`.

## Inputs

- **Live holdings (preferred) — via `finance/compute/holdings.py`.** Source the real book through the shared resolver, precedence **IndMoney → broker → watchlist positions**. IndMoney (`mcp__indmoney__*`) is net worth across asset classes; the broker MCPs (`mcp__kite__*` = Zerodha, `mcp__upstox__*` = Upstox) are the equity fallback. The resolver runs in script context and cannot call MCP tools, so the **handoff is**: for each connected source, invoke its holdings tool (IndMoney `networth_holdings` once per needed `asset_type` (`IND_STOCK` and `US_STOCK` for equity, `MF` for funds — the tool requires it and serves one type per call); broker holdings + positions), **write the raw payload to a temp file** under `paths.tmp_dir("holdings")`, then resolve and take the equity slice:
  ```bash
  PYTHONPATH=<plugin> python3 -m finance.compute.holdings --indmoney <ind-stock.json> --indmoney <ind-us.json> --kite <kite.json> --equity-only
  ```
  (pass only the files for sources that are connected; add `--portfolio <watchlist.json>` to fold the hand-maintained positions in as the last fallback). The envelope's `data.positions` give authoritative ownership, quantity, cost and personal P&L. Broker/aggregator `ltp` is only a personal valuation mark, never the price used to evaluate stops, targets, daily moves or alerts in the position-health section — **XIRR is available but not surfaced here** (depth belongs to wealth-manager / portfolio-review). `source` and `gaps` tell you which source won and what was absent. If no source is connected, build the brief without the position sections and suggest connecting one.
- **Watchlist + open positions (fallback / supplement)** — the managed list at `paths.watchlist_path()` (`artifacts/state/watchlist.json`); its `positions` block is also the `--portfolio` fallback the resolver folds in when no live source is connected. Shape:
  ```json
  {"watchlist": [{"ticker": "TICKER", "added": "YYYY-MM-DD", "source": "discover", "note": "..."}],
   "positions": [{"ticker": "TICKER", "entry": null, "sl": null, "target": null, "qty": null, "entry_date": "YYYY-MM-DD"}]}
  ```
  `entry_date` (YYYY-MM-DD) enables the STALE check. Missing file + no broker → build the brief without those sections and suggest creating one once. Renamed/demerged tickers that 404: report "ticker not found — possibly renamed (corporate action?)", don't silently drop.
- **Decision observations** — deduplicate the union of held and watched symbols before fetching quotes/history. Record each observation date/time. A missing source leaves position health or the trigger unassessed; it never falls back to a personal mark.
- **Alert inbox** — `manage_alerts(action="list")` returns the open alerts, severity first; pass `subject` to narrow to one name. Take the held + watched names plus the portfolio-wide items; this feeds the Alerts & actions section and the vetted half of Opportunities.

## Sections (in order; these become the fields of the `report.json` projection — see Output)

1. **Indices**: Nifty 50, Sensex, Bank Nifty — level, day change, and whether Nifty holds above/below its 50-EMA (one structural sentence, not commentary).
2. **Market analysis** (a market-level news digest, not stock-specific): the top **3–5 genuinely market-moving** items of the day — RBI/Fed, crude, FII/DII flows, global cues, major domestic policy or index-heavyweight results — one line each, then the **net read taken from market-analysis, not authored here** — call `get_market_context` (mode `quick`) and quote its `market_posture` + `rationale`, plus one breadth line (`breadth.pct_above_sma200` of `breadth.universe`) and the FII/DII nets from `flows`. **Never author a second verdict beside the computed one.** Sources: `get_news` (`India stock market`), preferring items whose `publisher_tier` is `established`. **Skip opinion, listicles, and target-price clickbait.** Cap at 5 items; if nothing genuinely moved the market, say so in one line.
3. **Sector tone**: top 2 / bottom 2 sectoral indices today — from `get_market_context` (`sectors.leaders` / `sectors.laggards`) or `get_indices`.
4. **⏰ Alerts & actions** (the inbox the rest of the plugin fills): surface what's open and what fired, never run anything.
   1. `manage_alerts(action="list")` for held + watched names and portfolio-wide alerts.
   2. `alerts.evaluate_cheap(open_alerts, market_data)` where `market_data` uses **decision-source observations only**, fetched once per unique held/watched symbol. Use `get_quote` for current-price health, and a verified completed-session candle from `get_history` for `close` alerts. Never relabel an intraday quote as a completed close, and never use broker marks, costs or watchlist entry prices as market observations — `{"date": "<today>", "prices": {SYMBOL: {"close":…, "day_change_pct":…, "dist_to_sl_pct":…}}}`. Print fired alerts inline with their `action.text`.
   3. List due date-based alerts (`sip_due`, `reanalyze_due`, `revalidate_due`, `rebalance_due`).
   4. For `{check: …}` alerts, print the exact `action.suggest` command for the user — **never auto-run it.**
   5. Lead with anything at `severity: act`. Curating these (dismiss/snooze) is the `alert-manager` skill's job; here you only surface.
5. **Opportunities** — high-conviction *new* ideas (not already held or on the watchlist), **strictly capped to avoid noise**:
   - **Vetted** (≤ 2) — from the alert inbox: `opportunity` alerts (`discover` candidate off an active strategy, a `deep-analysis` BUY verdict, a sector leader). Show source + one-line basis + the command to act.
   - **News-flagged, unvetted** (≤ 1) — at most one stock the morning's news strongly flags, **labelled "unvetted"** with a `/deep-analysis <T>` suggestion to confirm. Never present it as a signal.
   - Dedup against holdings, the watchlist, and yesterday's brief. If nothing clears the bar, print "no new opportunities — staying patient" (this is the correct, common case).
6. **Watchlist & holdings — filings & news**: for each watchlist ticker **and each resolved holding** (the equity slice from `holdings.py`), surface what's material from two sources:
   - **Filings** — `get_filings` with the NSE symbol and `days: 3` (don't re-derive the materiality), only 🔴/🟡 items. If the envelope comes back `ok:false` with a `gap`, say "filings unavailable" for that name, not silence.
   - **News** — the last 1–2 days of headlines per name via `get_news(company, ticker, days=2)` → take only the **1–2 genuinely market-moving** items (results, orders, management/regulatory, rating, M&A). **Skip opinion, "multibagger"/listicle, and target-price clickbait entirely.** A name with nothing material is the normal, correct case — print "nothing material".
   For speed, run only names you hold or watch.
7. **Position health & attention** (the section that earns the brief): for **every resolved open position** (`holdings.py` equity slice; watchlist fallback) — decision-source CMP vs personal avg/SL/target, distance to SL in %, sourced day move, and a state: ON-TRACK / **NEAR-SL** (within 2%) / TARGET-ZONE / SL-HIT / **STALE** (past time-stop) / **NEEDS-ATTENTION** (a 🔴 filing today, or a >5% adverse day move). Keep it minimal — symbol / qty / avg / ltp / pnl plus the state; SL/target are matched in from the watchlist `positions` block or a trade-idea artifact by ticker. Lead with anything needing attention; say it plainly, no new trade advice. If a live position has no matching rationale artifact, note that `/trade-tracker` can pair and re-validate it.
8. **One thing**: the single most decision-relevant item today, one sentence.

## Watchlist maintenance

The watchlist at `paths.watchlist_path()` is a managed, stamped list — keep it clean:

- **Auto-add vetted opportunities only.** When a *vetted* opportunity surfaces (Section 5), append `{ticker, added: <today>, source: <producer>, note: <one-line basis>}` if not already present, so it's tracked from the next run. **Never** auto-add a news-flagged/unvetted idea — that keeps the durable list signal-only.
- **Recommend pruning, never auto-remove.** When a watchlist entry has gone stale (e.g. "TATASTEEL: 30d on watch, no setup, no position → drop?"), flag it in the brief and let the user authorize a watchlist edit (`alert-manager` curates alerts, not watchlist entries). daily-brief never deletes a watchlist entry on its own.

## Output

The brief is a single self-contained **HTML page** (a phone-scroll one-pager, not a slide deck) rendered through the shared `_report` pipeline — there is no `.md` artifact.

1. Project the sections above into a `report.json` — the field shape is documented by the worked example `skills/_report/scripts/fixtures/daily-brief.sample.json` (its keys map 1:1 onto the sections). Every value must trace to what this run fetched; a section that failed to fetch becomes "— data unavailable" (or is dropped) rather than blocking the rest. Write it to `paths.report_path("daily-brief", ext="report.json")` (`artifacts/daily-brief/YYYY-MM-DD.report.json`, date = the day the run started).
2. Render it:
   ```bash
   PYTHONPATH=<plugin> python3 skills/_report/scripts/render_report.py \
     --report-json <…/YYYY-MM-DD.report.json> --template daily-brief \
     --out <…/YYYY-MM-DD.report.html>
   ```
   (`paths.report_path("daily-brief", ext="report.html")`). The page is theme-aware and needs no network. Surface the `.report.html` to the user.

If the user said "send" (or asks to), also send the Telegram-compressed **text** version via `assets/telegram-brief.md` format using `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` through the shared secrets loader. Write the text under `paths.tmp_dir("telegram")`, then run `bash <plugin-root>/bin/send-telegram.sh --text-file <path>`. Do not call curl directly or put credentials in command arguments. A failure or uncertain result is a delivery gap; preserve the rendered brief and do not automatically retry.
