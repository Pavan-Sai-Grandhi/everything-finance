# Daily brief reference

Compiled 2026-06-10. Self-contained: everything the brief needs is here (the deep versions live in sector-analysis and filings-watch for their own skills).

## Materiality cheat-sheet (for the watchlist section)

- 🔴 act-on: results/board-meeting-for-results, M&A/demerger, buyback/dividend/split announcements, auditor or KMP exit, regulatory action, promoter pledge increase, rating downgrade, order win > ~5% of revenue
- 🟡 monitor: investor-meet PPTs, capex/JV updates, rating affirmations, modest order wins
- ⚪ routine (never in the brief): trading-window closures, ESOP allotments, newspaper-ad copies, compliance certificates

## Sources (ladder verified 2026-06-11 — the WebFetch *tool* is blocked by Moneycontrol and ET, but curl/Playwright are not)

- Indices + 50-EMA + sector tone: **yfinance via Python** (`^NSEI`, `^BSESN`, `^NSEBANK`, sectoral map in the sector-analysis skill's reference) — primary, and sufficient on its own. Optional cross-check: Moneycontrol Nifty JSON `curl 'https://priceapi.moneycontrol.com/pricefeed/notapplicable/inidicesindia/in%3BNSX'` — the `;` MUST be encoded `%3B` (literal `;` → "No data found"). NSE/Moneycontrol HTML need Playwright real Chrome.
- Headlines: **ET works** via plain curl with a browser UA — `https://economictimes.indiatimes.com/markets/stocks/news`. **Google News RSS** fallback needs `-L` and `ceid`: `curl -sL 'https://news.google.com/rss/search?q=nifty+markets&hl=en-IN&gl=IN&ceid=IN:en'` (bare URL 302-redirects to an empty body). Moneycontrol HTML needs real-Chrome Playwright. Take only the top 3–5 market-moving items; skip opinion pieces and "multibagger" listicles entirely.
- Watchlist/holdings filings: via the shared `lib/filings.py --scrip <BSE_CODE>` (it walks the ladder itself — BSE public JSON API with browser UA + `Referer: https://www.bseindia.com/` first; on a BSE fingerprint block, a 200 "No Record Found!", it resolves the scrip to its NSE symbol and reads the NSE announcements API after a homepage cookie-bootstrap) → screener.in company Documents section as the reliable last fallback.
- Watchlist/holdings **news** (per name, distinct from filings): **Google News RSS search per company** — `curl -sL 'https://news.google.com/rss/search?q=<COMPANY+NAME>+share&hl=en-IN&gl=IN&ceid=IN:en'` (needs `-L` + `ceid`, like the market headlines). Keep only 1–2 genuinely market-moving items per name (results, large orders, management/regulatory, rating, M&A); **drop opinion, "multibagger"/listicle, and target-price clickbait**. ET company search is the fallback. Filings are *what the company told the exchange*; news is *what the press is saying* — the brief wants both, deduped (a results filing and a "Q4 results" headline are one item).

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
