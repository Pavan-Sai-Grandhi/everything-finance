---
name: daily-brief
description: Morning market one-pager — index levels and tone, sector leaders/laggards, watchlist filings and news, open-position health check — formatted for Telegram. Use when the user asks for the daily brief, morning summary, "what's the market doing", "anything I should know today", or wants a pre-market/post-market rundown.
argument-hint: "[optional: 'send' to push to Telegram immediately]"
allowed-tools: WebFetch, Read, Write, Bash, mcp__playwright__*
disable-model-invocation: false
---

# Daily Brief

A fast composite — breadth over depth; every section is 2–4 lines. Target: readable in 60 seconds on a phone.

**Sites for this skill only:** NSE (indices), Moneycontrol + ET (market wrap, top headlines), screener.in (watchlist company pages). Method specifics live in this skill's `references/reference.md`.

## Inputs

- **Watchlist + open positions**: read `watchlist.json` in the session cwd if present (`{"watchlist": ["TICKER",...], "positions": [{"ticker","entry","sl","target","qty","entry_date"}...]}`). `entry_date` (YYYY-MM-DD) enables the STALE check — without it that state is unreachable; suggest adding it once. Missing file → build the brief without those sections and suggest creating it once. Renamed/demerged tickers that 404 on data sources: report "ticker not found — possibly renamed (corporate action?)", don't silently drop.

## Sections (in order, using `assets/daily-brief.md` (bundled with this skill))

1. **Indices**: Nifty 50, Sensex, Bank Nifty — level, day change, and whether Nifty holds above/below its 50-EMA (one structural sentence, not commentary).
2. **Sector tone**: top 2 / bottom 2 sectoral indices today (NSE or Moneycontrol indices page).
3. **Watchlist filings & news**: for each watchlist ticker, only 🔴/🟡-grade items (materiality cheat-sheet in this skill's `references/reference.md`) from the last session — silence is a valid and common answer.
4. **Position health**: for each open position — CMP vs entry/SL/target, distance to SL in %, and a state: ON-TRACK / NEAR-SL (within 2%) / TARGET-ZONE / SL-HIT (say it plainly). No new advice here, just status.
5. **One thing**: the single most decision-relevant item today, one sentence.

## Output

Fill `assets/daily-brief.md` (bundled with this skill), save to `artifacts/YYYY-MM-DD/daily-brief.md` (date = the day the run started), and print it in chat. If the user said "send" (or asks to), also send the Telegram-compressed version via `assets/telegram-brief.md` format using `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` from `~/.claude/.env` (curl to the Bot API); missing token → note it and skip. Degrade gracefully: any section that fails to fetch becomes "— data unavailable" rather than blocking the rest.
