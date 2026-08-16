# Daily brief reference

Compiled 2026-06-10. Self-contained: everything the brief needs is here (the deep versions live in sector-analysis and filings-watch for their own skills).

## Materiality cheat-sheet (for the watchlist section)

- 🔴 act-on: results/board-meeting-for-results, M&A/demerger, buyback/dividend/split announcements, auditor or KMP exit, regulatory action, promoter pledge increase, rating downgrade, order win > ~5% of revenue
- 🟡 monitor: investor-meet PPTs, capex/JV updates, rating affirmations, modest order wins
- ⚪ routine (never in the brief): trading-window closures, ESOP allotments, newspaper-ad copies, compliance certificates

## Sources — all via the `finance-data` MCP server

- Indices + 50-EMA + sector tone: `get_market_context` (the shared daily read — preferred, so the brief and every other skill agree) or `get_indices` / `get_history` for a specific index.
- Headlines: `get_news` (Google News RSS). Every item carries a `publisher_tier` — prefer `established` wires and treat an `aggregator`-only story as unconfirmed. Take only the top 3–5 market-moving items; the noise classifier already drops "multibagger" listicles, so anything still tagged `noise` stays out.
- Watchlist/holdings filings: `get_filings` (NSE symbol). A blocked fetch is a labelled gap meaning "unknown", never "nothing filed".
- Watchlist/holdings **news** (per name, distinct from filings): `get_news(company, ticker, days=2)` per name. Keep only 1–2 genuinely market-moving items per name (results, large orders, management/regulatory, rating, M&A); **drop opinion, "multibagger"/listicle, and target-price clickbait**. ET company search is the fallback. Filings are *what the company told the exchange*; news is *what the press is saying* — the brief wants both, deduped (a results filing and a "Q4 results" headline are one item).

## Telegram constraints

- Bot API `sendMessage` hard limit 4096 chars; target ≤ 1500 for phone readability.
- No reliable markdown tables in Telegram — the telegram-brief template uses emoji + line items instead.
- Use `parse_mode=HTML` if formatting is needed (`<b>`, `<i>`); plain text is safer. Escape user-uncontrolled text.

## Position-state thresholds

- NEAR-SL: CMP within 2% of stoploss → user should be at the screen today.
- TARGET-ZONE: CMP within 2% of target → decide book/trail today.
- SL-HIT / TARGET-HIT: level crossed at yesterday's close — state it as fact; the discipline rule (CLAUDE.md) is exit, not hope.
- Time-stop note: swing positions older than ~4 weeks (needs `entry_date` in watchlist.json) without progress deserve a STALE tag — capital has opportunity cost (Varsity trading-systems expectancy framing).
- **State precedence** (report the first that applies): SL-HIT / TARGET-HIT → NEAR-SL / TARGET-ZONE → STALE → ON-TRACK. A stopped-out position outranks a merely stale one, so STALE only surfaces on a position that is old *and* still sitting between its stop and target with no progress.

## Tone

Factual, compressed, zero filler ("markets remained volatile amid global cues" is banned). Every line either carries a number or names an action. If nothing happened, the brief should be short — brevity on quiet days builds trust in loud ones.
