---
name: daily-brief
description: Morning market one-pager — index levels and tone, a market-moving news digest, sector leaders/laggards, the open-alert inbox and any actions due, a strictly-capped opportunities shortlist, watchlist filings and news, and open-position health — formatted for Telegram. Use when the user asks for the daily brief, morning summary, "what's the market doing", "anything I should know today", or wants a pre-market/post-market rundown.
argument-hint: "[optional: 'send' to push to Telegram immediately]"
allowed-tools: Read, Write, mcp__indmoney__*, mcp__plugin_everything-finance_indmoney__*, mcp__kite__*, mcp__plugin_everything-finance_kite__*, mcp__upstox__*, mcp__plugin_everything-finance_upstox__*, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-personal__resolve_holdings, mcp__plugin_everything-finance_finance-personal__resolve_holdings, mcp__finance-workflow__*, mcp__plugin_everything-finance_finance-workflow__*
---

# Daily Brief

A fast composite, breadth over depth: every section is two to four lines, readable in a minute on
a phone. It surfaces and recommends; it never runs a skill or places an order.

**Method:** `methods/filings.md` (the materiality tiers), `methods/news.md` (what counts as
market-moving), `methods/trade-management.md` (§ Position states).

## Inputs

- **Holdings**: read the book as `RULES.md` → *Reading your holdings* describes, equity slice.
  Pass `portfolio` as the watchlist's `positions` block so it is the last fallback. Personal
  prices value a holding; they are never the price for stops, targets, day moves or alerts.
- **Watchlist**: `artifacts/state/watchlist.json` (`finance/contracts.md` → *Artifact:
  watchlist*). Without it or a broker, build the brief without the position sections and suggest
  creating one once. A ticker that no longer resolves is reported "ticker not found — possibly
  renamed", never dropped silently.
- **Decision prices**: one `get_quote` and one `get_history` per symbol across holdings and the
  watchlist, with the time each was observed. A missing price leaves that position unassessed.
- **Alerts**: `manage_alerts(action="list")`.

## Sections

These become the fields of the `report.json` projection.

1. **Indices**: Nifty 50, Sensex, Bank Nifty: level, day change, and whether Nifty holds above or
   below its 50-EMA, in one structural sentence.
2. **Market**: the three to five genuinely market-moving items of the day (RBI or Fed, crude,
   FII/DII flows, global cues, major policy, index-heavyweight results), one line each, from
   `get_news("India stock market")`, preferring `established` publishers. Then the net read
   **quoted from `get_market_context(mode="quick")`**: its `market_posture` and `rationale`, one
   breadth line (`breadth.pct_above_sma200` of `breadth.universe`) and the FII/DII nets. Never
   write a second verdict beside it. If nothing moved the market, say so in one line.
3. **Sector tone**: top two and bottom two from the context's `sectors.leaders` and
   `sectors.laggards`.
4. **Alerts and actions**: the inbox the rest of the plugin fills.
   1. `manage_alerts(action="evaluate", prices=…, as_of=<today>)` with decision-source
      observations only: `get_quote` for current health and a completed-session close from
      `get_history` for `close` triggers. An intraday quote is not a close; broker prices, costs
      and watchlist entries are not market data. Print fired alerts with their `action.text`.
   2. List due date alerts (`sip_due`, `reanalyze_due`, `revalidate_due`, `rebalance_due`).
   3. For a `check` alert, print its `action.suggest` command for the user to run.
   4. Lead with `severity: act`. Dismissing and snoozing are `alert-manager`'s job.
5. **Opportunities**, new names only (not held, not watched), strictly capped:
   - **vetted** (at most two): `opportunity` alerts from discover, a deep-analysis BUY or a
     sector leader, each with its source, a one-line basis and the command to act;
   - **news-flagged** (at most one), labelled "unvetted" with a `/deep-analysis <T>` suggestion.
     Never present it as a signal.
   Deduplicate against holdings, the watchlist and yesterday's brief. Nothing clearing the bar is
   the common, correct case: "no new opportunities — staying patient".
6. **Watchlist and holdings: filings and news**, for names you hold or watch only.
   - `get_filings(symbol, days=3)`: act-on and monitor items only, as classified. An `ok:false`
     envelope is "filings unavailable" for that name, not silence.
   - `get_news(company, ticker, days=2)`: the one or two genuinely market-moving items (results,
     orders, management or regulatory, rating, M&A). A results filing and its "Q4 results"
     headline are one item. "Nothing material" is normal.
7. **Position health**: for every open position, decision-source price against the personal
   average, stop and target, distance to stop in %, the sourced day move, and the state from the
   method, plus **NEEDS-ATTENTION** for an act-on filing today or an adverse day move above 5%.
   Stops and targets come from the watchlist `positions` block or a trade-idea artifact. Lead with
   what needs attention; no new trade advice. A live position with no rationale artifact gets a
   note that `/trade-tracker` can pair it.
8. **One thing**: the single most decision-relevant item today, in one sentence.

Tone: factual and compressed; every line carries a number or names an action. "Markets remained
volatile amid global cues" is banned. A quiet day makes a short brief.

## Watchlist upkeep

Append a **vetted** opportunity as `{ticker, added, source, note}` when it is not already present;
never auto-add an unvetted one. Recommend pruning a stale entry ("30 days on watch, no setup, no
position — drop?") and let the user approve; this skill never deletes an entry.

## Output

A single phone-scroll HTML page, no markdown artifact. Write the projection to
`artifacts/daily-brief/<YYYY-MM-DD>.report.json` (the date the run started), shaped like
`finance/report/fixtures/daily-brief.sample.json`, then
`render_report(report_json=…, template="daily-brief", out=…/<YYYY-MM-DD>.report.html)`. A section
that failed to fetch reads "— data unavailable" rather than blocking the rest. Surface the page.

**Telegram**, only when the user said "send": fill `assets/telegram-brief.md` as plain text (no
tables or links, at most 1500 characters; the hard limit is 4096), write it under the artifacts
`tmp/telegram/` directory and call `send_telegram(text_file=…)`. A failed or unclear send is a
delivery gap; never retry it.
