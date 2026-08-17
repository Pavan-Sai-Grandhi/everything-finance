# Data sources — the decision record

Every data point this plugin fetches, the source that serves it, who consumes it, and what
was rejected. **This file is the authority.** A source absent from the finalized table below
must not be fetched by any skill, agent, script or hook.

Seven sources across eight hosts, one transport (`finance/transport.py`), one door (the three
local MCP servers `finance-market`, `finance-company`, `finance-funds`). AMFI is one logical
source at two endpoints — its own scheme registry and the `mfapi.in` NAV mirror — and is
counted once. Every "verified" claim here was tested against the live endpoint on 2026-08-16,
not assumed.

## Two classes of source, two different rules

| | Personal data | Decision data |
|---|---|---|
| **What** | The user's own holdings, positions, orders, net worth | Everything that shapes a view: prices, fundamentals, valuations, holdings of *funds*, news, filings |
| **Sources** | Kite, Upstox, IndMoney (all optional) | The 7 below |
| **Rule** | **Maximal** — connect whatever you have | **Minimal** — one source per data point, no duplicates |
| **Transport** | Remote MCP (OAuth, read-only) | The local `finance-market` / `finance-company` / `finance-funds` servers |

A personal source may supply only *what the user owns and what it is worth* — never a
returns-vs-benchmark, rank, valuation, cap classification, news item, analyst view or
sentiment score. Every decision input has a named owner in the tables below, so there is no
case where a broker field is the best source for one.

### Why the boundary is enforced

The rule is not hygiene, it is measurement. IndMoney's convenience fields *look* authoritative
because the connection is authenticated, and they were wrong:

- **`get_mf_funds_details.holdings` caps at 20 rows with no pagination, and reports that cap as
  the total.** Real funds hold **64–278** positions. It claimed 91–98% weight coverage beside a
  list whose weights summed to **6–27%**.
- One fund's 20-row slice **omitted its actual top three holdings**. Another was **nine months
  stale**.
- Every ratio built on that slice — look-through P/E, cap tilt, concentration, sector mix — was
  wrong, and wrong in a direction that flattered the fund.

So fund holdings come from `get_fund_holdings` (S5, the complete book), cap tiers from
`get_stock_ratios.mrktCapRank` (SEBI rank, never ₹Cr bands), fund performance recomputed from
S6's NAV series, news from `get_news`. A personal source answers "what do I own and what is it
worth", and nothing else.

## Finalized decision-data sources (7)

| # | Source | Serves | Access | Auth |
|---|---|---|---|---|
| S1 | **TradingView** scanner | live quote, technical screen, market breadth | `scanner.tradingview.com/india/scan` (POST JSON) | none |
| S2 | **Yahoo Finance** (yfinance) | EOD OHLCV, sector index history, macro | python `yfinance` | none |
| S3 | **screener.in** | company financials (10y P&L/BS, quarters, shareholding, peers, doc links), fundamental screen | public company pages; cookies only for saved screens | optional |
| S4 | **NSE** | index levels + P/E/P/B/DY (live + any past day), FII/DII flows, corporate announcements, corporate actions, shareholding + pledge | JSON APIs + archive CSVs, cookie-bootstrapped | none |
| S5 | **Tickertape** | fund category screen, **complete** fund holdings, per-stock ratios incl. SEBI `mrktCapRank` | `api.tickertape.in` | none |
| S6 | **AMFI** — two endpoints, one data owner | fund resolution (name→code→ISIN) via the portal's scheme registry; full NAV history via the `mfapi.in` mirror | `portal.amfiindia.com`, `api.mfapi.in` | none |
| S7 | **Google News RSS** | company and market news | `news.google.com/rss/search` | none |

Nothing else. No browser automation anywhere in the plugin.

## Data-point inventory

Every row names the one tool that serves it. A data point with no row here has no source.

| Data point | Source | Tool | Consumed by |
|---|---|---|---|
| Live quote (price, change, volume, mcap) | S1 | `get_quote` | find-trade, trade-tracker, daily-brief, technical-analyst |
| Technical screen (filters → candidates) | S1 | `run_technical_screen` | find-trade |
| Market breadth (% above 50/200 DMA) | S1 | `get_breadth` | market-analysis |
| EOD OHLCV history | S2 | `get_history` | `finance/compute/ta.py`, backtest, technical-analyst, trade-tracker |
| Sector index history (relative strength) | S2 | `get_history` | sector-analysis, sector-analyst |
| Macro (India VIX, USDINR, gold, crude, US 10Y) | S2 | `get_macro` | market-analysis |
| Company financials, ratios, quarters, FII/DII shareholding split, peers, doc links | S3 | `get_company_fundamentals` | fundamentals-data, financials-analyst, valuation-analyst, dcf-valuation, management-quality |
| Fundamental screen (query → symbols) | S3 | `run_fundamental_screen` | find-trade |
| Index levels + P/E, P/B, dividend yield (live, ~139 indices) | S4 | `get_indices` | market-analysis |
| Historical index valuation (any past trading day) | S4 | `get_index_valuation_history` | market-analysis (valuation percentiles) |
| FII/DII net flows | S4 | `get_flows` | market-analysis, daily-brief |
| Corporate announcements / filings + materiality | S4 | `get_filings` | filings-watch, daily-brief, news-sentiment |
| Corporate actions (dividend, split, bonus, record dates) | S4 | `get_corporate_actions` | filings-watch, daily-brief, portfolio-review |
| Shareholding pattern + promoter pledge (quarterly) | S4 | `get_shareholding` | filings-watch, management-quality, deep-analysis |
| Fund category screen (AUM, TER, returns, risk, cap mix) | S5 | `screen_funds` | mf-analysis (category scan) |
| Fund complete holdings + sector weights | S5 | `get_fund_holdings` | mf-analysis (look-through) |
| Per-stock ratios + SEBI market-cap rank | S5 | `get_stock_ratios` | mf-analysis (look-through), portfolio-review (cap tiers) |
| Fund identity (name → scheme code → ISIN) | S6 | `resolve_fund` | mf-analysis |
| Fund NAV history | S6 | `get_nav_history` | mf-analysis (rolling returns, drawdown) |
| Company + market news | S7 | `get_news` | news-sentiment, daily-brief, deep-analysis |

Six further tools — `get_market_context`, `run_strategy_screen`, `run_backtest`, `check_trade`,
`get_fund_scan`, `get_fund_lookthrough` — are **compute over the rows above**, not additional
sources. They fetch through the same modules and reach no host that is not S1–S7.

## What was dropped, and why

| Dropped | Reason |
|---|---|
| **BSE** (`api.bseindia.com`) — announcements, corp actions, security master | Fully covered by S4; NSE's `corporate-announcements` and `corporates-corporateActions` both verified. BSE was also fingerprint-blocked often enough to need a fallback ladder of its own. Residual loss: BSE-only-listed companies — a labelled gap, never silently absorbed. |
| ~~**AMFI portal**~~ — **evaluated and KEPT** | `api.mfapi.in/mf/search?q=` looked like a drop-in replacement for the ~9 MB `NAVAll.txt` registry; testing killed that. The search is a substring match on the *registered* name (`"TRUST Small Cap"` returns nothing — AMFI registers it as "TRUSTMF") and — decisively — it **caps at 15 results with no pagination**, so the broad fallback query `"Small Cap Fund"` silently omits most of the category. The registry stays the resolution authority, cached weekly. Name matching was hardened instead (word-prefix aware, so "TRUST" matches "TRUSTMF" without "ITI" matching inside "MULTI"). |
| **Economic Times** scraper | Subsumed by S7. |
| **Moneycontrol** scraper | Subsumed by S7; also the only consumer requiring Playwright with real Chrome (bundled chromium hit an Akamai 403). |
| **Playwright MCP** | Nothing is reachable only by browser. The "browser-only" shareholding/pledge read turned out not to need one either: NSE's `corporate-share-holdings-master` is served over the same cookie-bootstrapped request as announcements (verified). |
| **stockscans.in** | Evaluated and **rejected**: a paid product (₹500/mo, ₹5,999/yr) with no public API — probing `/api/*` returns 404. Its scan surface (announcement / result / shareholding / concall scans, peer comparison) duplicates what S3 + S4 already serve free. |
| **Tickertape drawdown & rolling-return fields** | Premium-gated, and one gated field in the projection **403s the whole request** — so they are stripped before the call (`PREMIUM_FIELDS`) and both metrics are recomputed from S6's NAV series instead. |

**S7 subsumes ET and Moneycontrol (verified)** — a 30-day query returned 100 items whose
publishers included Moneycontrol (10), The Economic Times (9), Business Today (11), NDTV
Profit (9), Business Standard (6) and Mint (4): a strict superset of the two-rung ladder, with
no bot wall and no browser. Because it also indexes low-quality aggregators,
`finance/sources/news.py` keeps its noise classifier and applies a publisher trust tier.

## Sources kept despite overlap, and why

- **S1 and S2 both carry prices.** S1 is a *snapshot* engine — one POST returns hundreds of
  symbols with SMA/52-week/market-cap fields already computed, which is what makes screening
  and breadth cheap — but serves no time series. S2 is the only free source of the OHLCV
  history indicators and backtests need. Neither can do the other's job.
- **S5 and S6 both cover funds.** S6 (AMFI) is the regulatory record: scheme codes, ISINs and
  the official daily NAV. S5 is the only free source of a fund's *complete* current holdings
  and per-stock SEBI cap rank. Rolling returns are computed from S6's NAV series.

## Adding a source later

The test is not "is this useful" — everything is useful. It is: **name the data point no
finalized source can serve.** If an existing source serves it, use that one. If none does, add
the source here first with its verified access path, then implement it in the matching
`finance/sources/` module, then expose it as a tool on the server that owns the domain. Never
fetch first and document later.
