# everything-finance plugin — working conventions

India-focused personal financial intelligence. Every skill in this plugin follows these rules; read this before executing any of them.

## Secrets

All credentials live in `~/.claude/.env` — never hardcode, never echo values into the transcript:

- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — Telegram briefs
- `SCREENER_SESSION_ID`, `SCREENER_CSRF_TOKEN` — screener.in authenticated screens (optional; public pages work without them). Session id goes in the `sessionid` cookie; the CSRF token is needed as the `csrftoken` cookie + `X-CSRFToken` header for POST endpoints.

Load with `set -a; source ~/.claude/.env; set +a` inside hook/automation scripts. If a secret is missing, skip the step that needs it and note the gap in the output — do not fail the whole skill.

## Data sources & browser automation

Always take the cheapest path that works for a given source — the **verified access matrix below (tested 2026-06-11)** is authoritative; don't assume "blocked" without checking which tool was tried:

| Source | Cheapest working path | Notes |
|---|---|---|
| screener.in (public company pages) | WebFetch / curl | works unauthenticated |
| screener.in (saved screens, screen builder) | curl/Playwright with **`sessionid` + `csrftoken` cookies** from `~/.claude/.env` | auth confirmed working; the public screen-builder URL is login-walled |
| Moneycontrol — index/quote data | **`priceapi.moneycontrol.com/pricefeed/...` JSON over plain curl** (no browser) | Nifty index: `…/pricefeed/notapplicable/inidicesindia/in%3BNSX` — the `;` MUST be URL-encoded as `%3B` (literal `;` returns "No data found"), and keep MC's own misspelling `inidicesindia`. Stock: `…/pricefeed/nse/equitycash/<SC_ID>` |
| Moneycontrol — HTML pages | **Playwright with real Chrome** (`channel:"chrome"`) | bundled headless chromium gets a 403 Akamai wall; real Chrome returns 200 |
| Economic Times | Playwright (headless OK) **or** plain curl with a browser UA | only the WebFetch *tool* is blocklisted, not browsers/curl |
| NSE (quotes, filings, SHP) | Playwright real Chrome, homepage cookie-bootstrap first | naive clients blocked |
| BSE (announcements, actions) | **BSE JSON API over curl** with browser UA + `Referer: https://www.bseindia.com/` | a 200 + "No Record Found!" everywhere = fingerprint-block → move on |
| AMFI / mutual-fund NAV | `api.mfapi.in` JSON over curl | |
| OHLCV / index price math | **yfinance** (`<SYMBOL>.NS`, `^NSEI`, `^CNX*`) via Python | primary for everything computed; no bot-wall |

- **WebFetch** is fine for static, non-blocking pages (screener public, Varsity, mfapi, BSE JSON) but is blocklisted by Moneycontrol and ET — use curl/Playwright there instead.
- **Playwright** (`npx @playwright/mcp@latest`, or `npx playwright` driven from Bash) must use the **real Chrome channel** to beat Akamai-protected sites (Moneycontrol, NSE). Headless bundled chromium is the most-blocked config.
- **Claude in Chrome** is the last-resort fallback when even real-Chrome Playwright hits a CAPTCHA: navigate, then pause and ask the user to clear the challenge.
- Extract only the relevant DOM/JSON (tables, headline lists, specific fields) — never dump full page HTML into context.
- Each skill names the only sites it may use; do not wander to the full pool.

## Graceful degradation

A scrape failure never aborts a skill. Continue with the remaining sources, and include a "Data gaps" line in the output naming what's missing and why (e.g., "BSE shareholding: fetch blocked, skipped"). Partial truth labeled as partial beats silent failure.

## Output conventions

- Currency in INR: `₹1,23,456` (Indian digit grouping). Large values as `₹4.2 Cr`, `₹12 L`.
- Dates as `YYYY-MM-DD`. Market-relative phrasing ("3 sessions ago") only alongside an absolute date.
- **Artifacts always go under `./artifacts/` of the directory the session is running in** (cwd), never inside the plugin and never to absolute paths elsewhere. Layout: `artifacts/YYYY-MM-DD/<skill-output>` for dated reports, `artifacts/.cache/` for reusable downloads (NAV JSON, OHLCV), `artifacts/.staging/` only for the deep-analysis→hook handoff. Create directories as needed.
- Every stock/fund recommendation ends with: risk note + "Not investment advice — personal research tool."
- Report templates are bundled with each skill in `skills/<name>/assets/` — fill data, keep structure.

## Trading discipline (applies to every signal this plugin emits)

- Never present an entry without a stoploss and a target. Minimum reward:risk 1.5, prefer ≥ 2.
- Position size from risk, not conviction: risk per trade ≤ 1% of capital → qty = (capital × 1%) / (entry − SL).
- Technical signals need volume confirmation (above 10-day average) or must be flagged "low-volume, weak signal".
- Indicators (RSI, MACD) confirm; price action + S/R decide. Varsity's checklist order: pattern → S&R → volume → Dow stage → indicator agreement → RRR.

## Excluded by design

No scheduled cron inside the plugin (run externally) and no order execution ever. Backtesting lives in the `backtest` skill — historical validation only, never live signals.
