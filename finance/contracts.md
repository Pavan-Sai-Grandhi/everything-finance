# Data contracts — the handoffs that make everything-finance one system

Skills pass structured artifacts to each other; this file is the **single description of those contracts**, so
editing one side of a handoff shows you the other. Change a field name or meaning here and change it in every
named producer and consumer. Two dependency kinds: **artifacts** (files one skill writes and another reads) and
**shared code** (`finance/` modules many callers import).

---

## The data layer: one door, one transport

**`finance/mcp/{market,company,funds,personal}.py` — the four servers.** The only door to decision data: 35
tools over the seven finalized sources (CLAUDE.md's source table) plus their compute engines, each delegating
to the matching `sources/` or `compute/` module and returning the shared **envelope** `{ok, source, fetched_at,
data, gaps}`. No name appears on two servers.

| server | tools |
|---|---|
| `finance-market` | `get_quote` `get_history` `run_technical_screen` `get_indices` `get_index_valuation_history` `get_breadth` `get_flows` `get_macro` `get_market_context` `get_universe` `run_strategy_screen` `run_stock_scan` `run_sector_screen` `run_backtest` `check_trade` `manage_alerts` `get_prior_run` |
| `finance-company` | `get_company_fundamentals` `get_documents` `run_fundamental_screen` `run_saved_screen` `get_stock_ratios` `get_news` `get_filings` `get_shareholding` `get_corporate_actions` `run_dcf` `run_governance_checks` |
| `finance-funds` | `resolve_fund` `screen_funds` `get_fund_holdings` `get_nav_history` `get_fund_scan` `get_fund_lookthrough` |
| `finance-personal` | `run_insurance_math` |

**Layering rule:** anything that fetches, or computes over fetched data, is a **tool** — leaving a skill's
`scripts/` pure compute over user-supplied files. Bulk lists (`candles`, `positions`, `navs`, `items`,
`funds`) **spill to disk**: the tool writes the full list to cache and returns `data[<key>]` truncated plus
`data[<key>_total]` and `data[<key>_path]`. Spill files are named by content hash, so a later call cannot replace a file an earlier call returned. Documents are *only* ever a path (*Artifact: document cache*).

**`finance/spine.py` — shared fetcher primitives.** The envelope builder, float coercion, vendor-row key
picker, symbol/date normalizers, and the day-stamped disk cache. Imported by every source, compute module and
server, so envelopes and cache staleness cannot diverge. `test_spine.py`.

**`finance/transport.py` — the one function that touches the network.** `request` / `json_request` (never
raise, return `(body, gap)`) and **`nse_json`** (the cookie-bootstrapped NSE GET shared by `sources/market.py`
and `sources/filings.py`); curl-based (nseindia.com 403s urllib on the TLS/HTTP2 fingerprint); no module opens
its own socket. `test_transport.py`.

**Personal/decision boundary.** `kite`/`upstox`/`indmoney` are separate optional MCP servers, normalized
through `compute/holdings.py`; they supply **only** what the user owns and its worth, never a decision input
(CLAUDE.md rule 3).

---

## Shared code: `finance/`

### `finance/deps.py` — lazy third-party imports
Imports a module, pip-installing on first miss (PEP 668 override), so missing deps self-heal instead of
tracebacking. Consumers: `compute/{trade_check,dcf}.py`, `strategy-manager/scripts/{select_strategy,
aggregate_performance}.py`, `sources/funds.py` (openpyxl, AMFI cap-list workbook). Kept out of `compute/ta.py`
so a PyYAML-only caller avoids pandas + the TA-Lib bootstrap.

### `finance/caps.py` — the SEBI cap-tier authority
`SEBI_CAP_RANKS` (top 100 large, 101-250 mid, 251+ small); `cap_bucket(cap_rank, cap_label)` → `(bucket,
source)` (`source` = `"rank"` fact or `"label"` provider fallback); `cap_label(rank)` → `"Large Cap"|"Mid
Cap"|"Small Cap"|None`. Network-free; `sources/funds.py` (fills `cap_rank` from AMFI) and `compute/lookthrough.py`
(weights it into `cap_tilt`) both sit on it. `test_funds.py` + `test_lookthrough.py`.

### `finance/paths.py` — the artifact-path authority
Callers ask this module where to read/write instead of hardcoding, so the layout cannot drift. Root is
`$EVERYTHING_FINANCE_ARTIFACTS` or `./artifacts`. Three tiers: **dated output** (`stocks/<TICKER>/<date>/`,
`funds/<SCHEME>/<date>/`, skill-first singletons like `daily-brief/<date>.report.{json,html}`), **durable state**
(`state/{strategies,trades,alerts,sectors}/`, `state/watchlist.json`), **disposable** (`cache/`, `tmp/`);
helpers create dirs on demand. Ticker and scheme components reject `..` and path separators; cache namespaces may nest. Dates must be real calendar days (monthly reports also accept YYYY-MM). A symlink cannot point a path outside the root. **`latest_prior(skill, subject, before=None)`** / **tool `get_prior_run`**
(envelope `data:{skill, subject, before, path, date}`, the only reach for `valuation-analysis`/
`management-analysis`/`filings-watch`, which carry no `Bash`) power "refer the earlier run"; `skill` keys are
exactly `deep-analysis, fundamentals, dcf, management, filings` (stocks) + `mf-analysis` (funds), else
unresolvable. **No earlier run is `ok:true` with a null `path`** (a first run is normal). `test_paths.py`.

### `finance/compute/alerts.py` — the alert contract (see "Artifact: alert" below)

### `finance/compute/ta.py` — technical-analysis primitives
One definition of every indicator + candlestick pattern. Consumers: `compute/{strategy,screen,backtest,
context}.py` (and `technical-analysis` via the tools on them). Import `from finance.compute import ta`.

**`ta.add_indicators(df)`** (input OHLCV, DatetimeIndex) attaches the columns every consumer keys off:
`ema20, ema50, sma200, ema50_rising, rsi14, vol10, atr14, hh20, ll20`. Numeric indicators delegate to **TA-Lib**
(EMA SMA-seeded, ATR Wilder). Renaming a column breaks the backtest signals and screen filters together.
Everything else a spec names is attached on demand by **`ta.materialize(df, names)`**: parameterized tokens
`<kind><N>[_rising]` (`ema21, sma100, rsi9, atr20, adx14, hh50, ll20, vol30, nr5`) resolved by regex, plus
registered patterns/signals in **`ta.FEATURES`** (`inside_bar, outside_bar, engulfing, hammer, doji,
coil_breakout, golden_cross, macd_bullish_cross, rsi_oversold, bb_squeeze, volume_surge, new_high_20, …`);
`ta.is_feature(name)` tests resolution. A new period/signal needs no code change; only a new primitive is
registered once. `sources/prices.history_df` loads and caches prices for both backtesting and live
screening. TA-Lib needs the native lib (`brew install ta-lib`), bootstrapped by `ta._need_talib()`; other
Python dependencies use `deps.need`.
`test_ta.py`.

### `finance/compute/strategy.py` — spec → signal engine
*Spec + indicator columns → trades.* Consumers: `compute/screen.py` (live, latest bar → `run_strategy_screen`)
and `compute/backtest.py` (historical, every bar → `run_backtest`) — both import it so they cannot disagree on
what a strategy means. The ONE safe filter-language evaluator (NOT python eval) reads `entry.signal` /
`compute_filters` with grammar `"<col>"`, `"A >/</>=/<= B"`, `"A between X and Y"`, `"k * col"`, `"A or B"`
(case-insensitive AND/OR/BETWEEN) and materializes exactly the `ta` features a spec names. Produces the live
entry/stop/target/RRR/qty signal and the Backtesting.py `Strategy` (next-open fills, pessimistic intrabar exits,
time-stop, risk sizing; stop auto-floored, target from spec). `test_screen.py`.

### `finance/compute/` — the compute behind the composite tools
Each module owns one interpreted answer, so each is reached through exactly one tool and
never re-implemented in a skill:

| module | tool | produces |
|---|---|---|
| `context.py` | `get_market_context` | the market-of-record digest (see *Artifact: market-context*) |
| `screen.py` | `run_strategy_screen` | trading spec → shortlist with entry/stop/target/qty per candidate |
| `stock_scan.py` | `run_stock_scan` | investment spec: universe ∩ quality gate → rank by momentum → top-N shortlist (no entry/exit; see *Artifact: stock-scan shortlist*) |
| `sector_scan.py` | `run_sector_screen` | sectoral indices → RS-vs-Nifty ranked + classified → top-N (see *Artifact: sector-scan shortlist*) |
| `relative_strength.py` | *(internal to `stock_scan`/`sector_scan`)* | windowed returns + Leading/Improving/Weakening/Lagging classification — the one RS definition |
| `backtest.py` | `run_backtest` | trading spec → historical expectancy, profit factor, drawdown vs buy-and-hold |
| `trade_check.py` | `check_trade` | a trade-idea artifact + decision prices → recommendation and unrealized position metrics. It is not proof of an execution |
| `fund_scan.py` | `get_fund_scan` | a whole SEBI sub-category → gated, scored shortlist (rolling-return math from `rolling.py`) |
| `lookthrough.py` | `get_fund_lookthrough` | complete holdings + per-stock ratios → weighted portfolio valuation, cap tilt, concentration |
| `rolling.py` | *(internal to `fund_scan`)* | rolling returns, drawdown, risk-adjusted ratios from a NAV series |
| `dcf.py` + `relval.py` | `run_dcf` | sourced inputs → intrinsic value/share (+ optional grids) and the relative-multiples read, one answer; full JSON and the supplied inputs written to `stocks/<TICKER>/<date>/dcf-<hash>.json` |
| `governance.py` | `run_governance_checks` | annual-report figures → `remuneration` (`ratio_pct` vs the 11% total cap; `executive_ratio_pct` vs the 5%/10% MD/WTD cap only when `executive_remuneration` and `managing_directors` are given) and `auditor_fee` (fee YoY vs aligned revenue/profit series); PASS/FLAG/FAIL/NOT-CHECKED. Invalid inputs, or a fee with no revenue/profit series, are NOT-CHECKED. Read by `management-analysis` checks 1 and 5 |
| `alerts.py` | `manage_alerts` | the alert inbox: list / add / dismiss / snooze / sweep (see *Artifact: alert*) |
| `insurance_math.py` | `run_insurance_math` | user-supplied figures → term cover need, health sum insured, IDV/NCB sanity, marginal IRR of continuing a policy |

`test_{context,screen,stock_scan,sector_scan,backtest,trade_check,fund_scan,lookthrough,rolling,dcf,relval,governance,insurance_math,alerts}.py`;
`backtest.py` from both sides — spec interpretation via `compute/strategy.py` in `test_screen.py`, and the
Backtesting.py wiring (fill timing, cost, stop/target precedence, time-stop) in `test_backtest.py`.

### `finance/sources/filings.py` — exchange-filing fetch + materiality
Consumers: `get_filings` / `get_shareholding` / `get_corporate_actions`, read by `filings-watch`,
`daily-brief`, `news-scan`. `classify_materiality(text) -> (tier, emoji, reason)`, `tier ∈ {act-on, monitor,
routine}` (🔴/🟡/⚪). `summarize(symbol, days, fresh=False)` → envelope `data:{symbol, days, date,
material_count, act_on:[…], monitor:[…], routine_count, items:[…], corporate_actions:[…]}`. **Primary key is
the NSE symbol** — BSE-only is a labelled gap. Also `shareholding(symbol, quarters)` → `data:{symbol,
quarters:[{quarter, promoter_pct, public_pct, employee_trusts_pct, filed_on, xbrl}], pledge:[…],
pledge_summary:{declared, pledged_pct, pledged_shares, encumbered_pct, encumbered_shares, source, gaps}|null}` and
`corporate_actions(symbol)` → `data:{symbol, corporate_actions:[…]}`. `quarters` must be a positive integer.
Rows are sorted newest-first by their own period date, and the pledge summary reads the newest filing's XBRL,
fetched only from an HTTPS `nseindia.com` host. **Missing pledge evidence is a labelled gap meaning UNKNOWN,
never "no pledge".** An XBRL `false`/`0` shows zero pledged shares but says nothing about other encumbrances.
Invalid ranges and contradictory figures are gaps.

Each announcement in `summarize` carries `filing_id`, a SHA-256 of date, attachment URL and full headline.
Exact repeats collapse into one item. Alert producers key on `filing-<TICKER>-<filing_id>`, never on the date
alone. A corrected or re-indexed disclosure can get a new ID.

All four exchange lists re-check the issuer before using a row, because the endpoint has returned the whole
market when it ignores its filter. Rows for other symbols are dropped with a gap. Symbols such as `M&M` are
URL-encoded. `ok:false` + `gap` means "unknown", not "nothing filed". `test_filings.py`.

### `finance/sources/prices.py` — price fetch (live + history + reconcile)
Consumers: `get_quote` / `get_history` / `run_technical_screen`, plus `compute/{screen,trade_check,context}.py`
and `sources/market.py`. Two truths kept separate: the **TradingView scanner** (public India scan, **no auth**)
is live/screening truth; **yfinance** is EOD-history truth. Envelope forms:
- `quote(symbol)` → `data:{symbol, date, name, close, change, change_abs, volume, market_cap_basic, exchange}`.
- `history(symbol, period="1y", adjusted=False)` → `data:{symbol, period, adjusted, bars, as_of, bars_dropped_invalid, candles:[{date,open,high,low,close,volume}]}`. Index tickers (`^NSEI`, `^CNXIT`) pass through, equities get `.NS`; `adjusted=False` keeps the raw close for reconcile, warmup callers pass `adjusted=True`.
- `history_df(symbol, period="1y", adjusted=True)` → `(pandas OHLCV frame, gaps)` — fed straight to `ta.add_indicators`.
- `screen(filters, columns=None, limit=50)` → `data:{filters, count, candidates:[…], rows:[…]}`.
- `reconcile(symbol, tolerance=0.01)` → `data:{symbol, tv_close, yf_close, divergence_pct, tolerance, agree}`; a divergence beyond tolerance is a `gap`.
`screen` needs a positive integer limit and distinct column names. It requests NSE rows only and returns
unique NSE symbols with a positive close. Malformed or excluded rows are gaps; the rest of the screen is
still usable.

`history` drops bars with a bad date, a nonpositive price, negative volume, impossible OHLC geometry or a
duplicate session, counts them in `bars_dropped_invalid` and adds a gap. A bar dated today carries a gap
saying the session may not be complete, so do not treat it as a completed close. A cache hit must match
symbol, period and adjustment.

**No indicators computed here** — callers pass `candles` to `ta.add_indicators`, so a screen and its backtest
share one indicator-of-record; no TV indicator ingestion or library. `test_prices.py` (offline parser + reconcile fixtures).

### `finance/sources/universe.py` — the universe authority
Consumers: `get_universe`, plus `compute/{screen,stock_scan,sector_scan,backtest}.py` (every screener resolves
its universe here — the one resolver). `resolve_symbols(name, fresh=False)` → `(symbols, gaps)` is the pure list
resolver; `resolve(name, fresh=False)` → the envelope (`data:{name, symbols_count, universe_path, as_of}`; see
*Artifact: universe*). Named universes (`nifty50|nifty100|nifty200|nifty500`, `microcap`, `fno`, `largecap20`)
come from NSE's published constituent CSVs via `transport.py`, cached dated with a stale-cache fallback; a list,
comma-string or file path is resolved locally. Holds `LARGECAP20_BASKET`.
`test_universe.py` (stubbed transport).

### `finance/sources/news.py` — company news (Google News RSS)
Consumer: `get_news`, read by `news-scan`, `deep-analysis` (news leg), `daily-brief`. `fetch(company, ticker,
days=60)` reads Google News RSS (the single source) → envelope `data:{company, ticker, days, count,
items:[{date, title, url, source, origin, kind, tag, publisher_tier}], noise_filtered, established_count}`.
Each item is **dated** (ISO or `null`), **deduped**, **classified** `kind ∈ {company, sector, noise}`, **tagged**
`tag ∈ {reported, narrative}`, and carries `publisher_tier ∈ {established, aggregator, unknown}` (never dropped —
weigh a single-sourced `aggregator` claim accordingly). **Noise is filtered from the default `items` view**
(pass `include_noise` to keep it). A block returns `ok:false` + labelled `gap`, never an empty crash.
The tag is read from the title only, so `reported` means an unverified claim. `publisher_tier` matches the
publisher's display name exactly and does not authenticate it. A material figure still needs a primary
source. The raw feed is cached once per company per day; classification and filtering run on each call.
Undated items add a recency gap. `test_news.py`.

### `finance/sources/tickertape.py` — the one Tickertape client
Consumers: `sources/fundamentals.py`, `sources/funds.py`. Holds the `tickertape.in` Referer every path 403s
without; `resolve_sid(symbol)` → `({sid, ticker, name, sector, slug}, gap)`, the only NSE-symbol→Tickertape-sid
map (sid differs from ticker — REC is `RECLTD`/`RECM`). Only exact ticker equality is accepted (a near-miss
misattributes financials); two exact matches with different sids leave the symbol unresolved. Cached 90 days
under a hashed key. Responses the provider marks as failed, or that are malformed, are gaps.

### `finance/sources/fundamentals.py` — Tickertape financials + the screener.in document index
Consumers: `get_company_fundamentals` / `run_fundamental_screen`, read by `financial-analysis`,
`valuation-analysis`, and `discover` / `strategy-manager` (fundamental cut). Envelope forms:
- `fetch(symbol, sections=None)` → `data:{symbol, name, sid, ratios:{name:value}, pnl_10y:{columns,period_kinds,rows}, balance_sheet_10y:{…}, cash_flow_10y:{…}, quarters:{…}, shareholding:{columns,rows}, peers:[{symbol,name,sid,ttm_pe,pb}], documents:{annual_reports:[{label,url}], concalls:[{label,url}]}}`. `period_kinds` parallels `columns` (`FY`/`TTM`/`interim`). Each peer row carries its own **trailing** multiples from the same response, so the relative read needs no per-peer call; an unpublished multiple is `None`. `sections` narrows both answer and **work** (only those endpoints are called — what keeps `get_documents` to one screener fetch); a narrowed read does not populate the day cache, only a full one does. An unknown section name refuses the request before any fetch. A malformed section returns its empty value and a gap; the other sections are unaffected. The cache key includes any explicit sid override.
- `screen(query, limit=1000)` → `data:{query, count, candidates:[…]}`, biggest market cap first. `query` is `FIELD >/< VALUE` clauses joined by `AND` over Tickertape's screener field names; `>=`/`<=` and an unresolvable name **refuse the whole query** (a half-resolved query returns companies that never passed the cut). Repeated bounds on one field keep the tightest; contradictory bounds or a non-numeric threshold refuse the query. Each returned row is re-checked against every bound, and rows that fail or lack the field are dropped with a gap.

Line-item labels are **Tickertape's own vocabulary**, and three mean less than their name suggests:
- `Taxes & Other Items` (`incToi`) lumps tax with the non-controlling interest — no effective tax rate is
  derivable; read the annual report's tax note via `get_documents`.
- `EBITDA` (`incEbi`) is struck **after** other income — no operating-only margin is separable.
- `Changes in Working Capital` (`cafCiwc`) is **not a working-capital movement**: tested across six companies ×
  four years it reconciles to neither plausible meaning (balance-sheet ΔWC nor the CFO-minus-earnings residual),
  so **never feed it into the reinvestment / sales-to-capital calculation** — take capex and depreciation from
  their own rows and ΔWC from a **labelled derived** balance-sheet delta (or the annual report's cash-flow
  statement when the story turns on it).

The **annual `pnl_10y` carries ten fiscal years plus a TTM column; `balance_sheet_10y` and `cash_flow_10y` do
not** — so the three statements' last columns are different periods. Pair by `period_kinds` (`FY`/`TTM`/`interim`),
never by index: a latest-column CFO ÷ EBITDA silently divides FY by TTM, and a 5y CAGR `[-6]`→`[-1]` spans FY→TTM
(5.4 years read as 5). `EBITDA Margin %` and `Payout Ratio %` are the only derived rows. `cash_flow_10y` is the
source of **CFO, capex and free cash flow** (none in the P&L); `Free Cash Flow` is **published**, not derived
(reconciles to `Cash from Operating Activities − Capital Expenditures`). `cafFee` is dropped — the source names
and renders no row for it, so carrying it would invent a label. `shareholding` runs six quarters and carries
`Promoter Pledge (% of promoter holding)` (denominator is the promoter stake, not share capital); government
holding and a per-quarter shareholder count are not published (current count is in `ratios` as `No. of Shareholders`).

**Tables/fields only — never raw page HTML lands in `data`.** No source here needs auth.
`is_logged_out(html)` catches screener's HTTP-200 Register page, so a gated document index
reports itself rather than reading as a company that has filed nothing. Covered by
`finance/tests/test_fundamentals.py` (offline parser fixtures).

### `finance/sources/screener_screen.py` — retired
`run_saved_screen` still exists for old clients. It always returns `ok:false`, no candidates and a
source-policy gap, and makes no request: screener.in is approved for documents only. Investment specs use
Tickertape and must name a universe. A spec written for a saved screen must be rewritten by its author;
the engine does not substitute criteria. `test_screener_screen.py`, `test_stock_scan.py`.

### `finance/sources/documents.py` — primary documents as cached local text
Consumer: `get_documents` (envelope, cache layout, reading legs in *Artifact: document cache*).
`fetch(symbol, annual_reports=1, concalls=1, fresh=False)` → envelope. Counts are nonnegative integers; zero
skips that section. Duplicate URLs are removed before the count applies, and one failed document does not
affect the others. Takes the index from
`fundamentals.fetch(symbol, sections=["documents"])` (one screener fetch) and downloads each link via
`transport.request(url, dest=…)` (the one socket). A link to an IP literal, loopback or local-network host
is refused with a gap; a public host that redirects to one is not caught. Each section is newest-first by year (and quarter) parsed
from the label; a label with no parseable year falls back to list position + a labelled gap. Conversion is
`pdftotext -layout` for PDFs (keeps table column alignment) and an in-process strip for text/HTML;
`extracted_by` records which ran. A PDF URL must return PDF bytes; other text must be valid UTF-8 with no
binary bytes, and known error-page titles are rejected. These checks do not prove the document is
authentic. A PDF that extracts to zero characters and a missing `pdftotext` (`brew install
poppler`) are labelled gaps, never crashes. `test_documents.py`.

### `finance/sources/market.py` — market-wide fetch (indices, valuation history, breadth, flows, macro)
Consumers: `get_indices` / `get_index_valuation_history` / `get_breadth` / `get_flows` / `get_macro`, and
`compute/context.py`. **No skill reads this for a market view** — every skill reads the market-context artifact.
Envelope forms:
- `indices()` → `data.indices:{<CANONICAL NAME>:{last, pe, pb, dy, pct_change, pct_change_1y}}` for ~139 NSE indices in one call (NSE `allIndices`). `index_levels(names=None)` is the budgeted form (`None` = `BROAD_INDICES`; ~139 are too many inline).
- `index_snapshot(day)` / `valuation_history(index, years)` → month-end `{date, close, pe, pb, dy}` from NSE archive CSVs. **One fetch per sampled DATE serves every index**, and a validated snapshot is cached permanently (what makes a 10y multi-index percentile affordable). A row must match the requested session. When a holiday pushes two samples onto one trading date, it counts once; the result reports `requested_samples`, `samples`, `first_observation` and `last_observation`. `max_fetches` caps uncached requests. Nonpositive P/E or P/B is not ranked.
- `valuation_percentiles(index, years)` → ranks only `{index, years, samples, pe|pb|dy:{current, percentile, n}}`. P/E is ranked by `robust_pe_percentile`, which drops samples at or above 3× the median and reports them in `pe.excluded`. `get_market_context` uses the same function.
- `breadth(universe)` → `data.counts:{above_sma50, above_sma200, advancing, near_52w_high, near_52w_low}`, each `{count, of}`. Each `of` is the number of stocks priced for that metric, which can be smaller than `requested_universe`.
- `flows()` → `data.flows:{FII,DII}:{buy_cr, sell_cr, net_cr}` for the latest session only. Unknown categories, bad dates, duplicates and a net that differs from buy minus sell by more than ₹0.02 Cr are gaps.
- `macro(period)` → `{last, chg_1m_pct, chg_1m_from, percentile, percentile_5y, observations, first_observation, as_of}` per series. `chg_1m_pct` is the change over 21 sessions and is null with fewer than 22 closes. `percentile_5y` is filled only for a `5y` request.
- `percentile(values, value)` — the one pure primitive; ranks, does not judge.
`SECTOR_YF` is the **single** NSE-sectoral yfinance ticker map (which sectors exist). Fetches only — no regime
label, stance or score. `test_market.py`.

### `finance/sources/funds.py` — mutual-fund fetch (identity, category screen, full holdings, NAV)
Consumers: `resolve_fund` / `screen_funds` / `get_fund_holdings` / `get_nav_history` / `get_stock_ratios`, plus
`compute/{fund_scan,lookthrough}.py`. Envelope forms:
- `resolve(name)` → `{scheme_code, isin, amfi_name, plan, mf_id, tickertape_name}`; AMFI `NAVAll.txt` is the scheme-code/ISIN authority (mfapi's search misses funds).
- `screen(subsector, option, min_aum)` → `data.funds:[{mf_id, name, aum, expRatio, ret1y/3y/5y, sharpe, sortino, alpha, stdDevAnn, percSmallcap/Midcap/Largecap, ageInMon, …}]`. Vendor `match` string filters are ignored, so filtering is client-side; `PREMIUM_FIELDS` are stripped (one gated field 403s the whole call). Subsector matching ignores case. If the last page allowed by `limit_pages` is full, the list may be truncated: that is a gap, and an incomplete list is not cached.
- `holdings(mf_id)` → `data.positions:[{sid, ticker, name, weight, change3m, type}]` — the **complete** book (64-278 positions, 90-99% coverage), plus `equity_weight`, `sector_weights` (from the newest dated `sectorDistribution` snapshot), `sector_weights_as_of`, `allocation_history`. `sid` is the join key (differs from `ticker`). Equity rows weigh 0–100%; a non-equity line such as net receivables can be negative.
- `stock_ratios(sid)` / `enrich(positions)` → per-holding `{pe, ttm_pe, pb, roe, market_cap_cr, cap_rank, cap_label, sector, …}`, threaded + cached. **`pe` is annualised, `ttm_pe` is TTM** — for a peer comparison against a company's own `Stock P/E` (TTM) use `ttm_pe` (else ~8% skew). **`cap_rank`/`cap_label` from `amfi_cap_list()`** — AMFI's half-yearly `AverageMarketCapitalization*.xlsx` (link resolved from the categorisation index), whose `Sr. No.` **is** the SEBI rank (`caps.py`), joined on NSE symbol (ISIN fallback). A symbol absent from the period gets `cap_rank: None` + gap, `cap_label` falls back to the provider label. The rest of the row is Tickertape's sid-joined ratios.
- `nav_history(code)` → `data.navs:[{date ISO, nav}]` oldest-first.
- `mf_id`/`sid` must match `[A-Za-z0-9][A-Za-z0-9&_.-]*` and `scheme_code` must be a positive integer, checked before any request.
**Fund holdings never come from the IndMoney feed** — it caps at 20 rows, misreports coverage, can be months
stale. `test_funds.py`.

AMFI workbook links are fetched only over HTTPS from `www.amfiindia.com` or `portal.amfiindia.com`, with no
redirects, so a moved endpoint gives a gap instead of an unchecked download. Future-dated periods are skipped.
A rank must be a positive integer. Rows that share a symbol or ISIN are dropped with a gap, and a ticker match
that contradicts the ISIN supplies no rank. The parsed cap index is kept in memory for one calendar day.

Cache keys are hashes of the full identifier. One holding with a malformed ratio payload gets a gap; the rest
are still enriched. A missing ratio does not mean the holding is unlisted.

Look-through needs an explicit equity allocation. Without it, enrichment is skipped, because summing the rows
that arrived cannot stand in for the coverage denominator. Holding weights must be 0–100, sum to at most 100,
and none may exceed the equity allocation. Malformed rows, duplicate sids or a total above 100 set
`equity_weight:null` with gaps; the result is `ok:false`, `confidence: unusable`, `ratios_publishable:false`,
with no metrics. `pb_over_roe` is computed on the holdings that have both P/B and ROE, and the 60% coverage
gate applies to that shared set. Coverage counts disclosed positions; it cannot prove the provider omitted
nothing.

Fund-scan reports are written to `paths.fund_dir("<category> scan")/fund-scan-<content-hash>.json` and
`report_path` returns that path. `out` is only a filename prefix; read the returned path. A failed write
returns the shortlist with a gap and `report_path: null`.

`compute/fund_scan.match_amfi_scheme` joins a Tickertape fund to an AMFI scheme only when the name tokens
match after dropping plan words, the scheme is Direct Growth, and exactly one scheme code fits. More than one
candidate is a gap. `resolve` needs every query token to match at a word boundary. NAV rows with a bad date
or a nonpositive value are dropped with a gap.

### `finance/compute/holdings.py` — holdings source-resolver + normalizer
Consumers: `daily-brief`, `trade-tracker`, and the personal-finance cluster (`wealth-manager`,
`portfolio-review`, `mf-analysis`). Turns whichever read source is connected into ONE canonical position shape
under a fixed precedence.
- **Envelope:** `resolve(…)` → `{ok, source, fetched_at, data:{positions:[…]}, gaps:[…]}`.
- **Canonical position:** `{ticker, qty, avg, ltp, pnl, xirr, broker, asset_class, invested, value, unsettled_qty, source, as_of}`.
  `source` names the winning source per position (`indmoney`, `kite`/`upstox`, `portfolio`). `value` keeps a
  reported current value, including zero. `market_value`, shared by allocation and wealth, takes the reported
  value, else invested plus P&L, else quantity times price. Cost alone is never a market value.
- **Kite and Upstox quantity.** Kite's `quantity` is the settled (T+2) amount, so `qty` = `quantity` +
  `t1_quantity`. Upstox's `quantity` is already the total, so `qty` = `quantity` unless it is smaller than
  `t1_quantity`. `unsettled_qty` is the T+1 part for both. Neither broker documents a total; this is the
  plugin's reading of their field definitions.
- **Broker identifiers.** Rows carry the raw `broker_symbol`, `exchange` and `isin`. `ticker` drops the series
  suffix (`-BE`, `-RR`, `-IV`, `-SM`). `asset_class` comes only from ISIN and series: `INF…` is `etf`, `IN0…` is
  `sovereign gold bond` or `government security`, series RR/IV is `reit`/`invit`. The equity slice excludes these.
- **IndMoney.** `broker`, `invested` and `asset_class` come from IndMoney and are `None` otherwise.
  `networth_holdings` returns a JSON string under `result`, one `asset_type` per call (pass `--indmoney` once per
  type), with `total_units`, `unit_price`, `total_pnl`, `investment` and `investment_code`, and no XIRR.
  `investment_code` is IndMoney's internal id, kept as `instrument_code` and never used as a ticker. Stocks held
  through a linked broker report cost equal to value; they get unknown cost with
  `cost_basis: unreported_by_linked_broker`, and the gap names the broker to `--prefer` for cost.
- **`normalize(payload, source)`** maps an IndMoney `networth_holdings`, a Kite/Upstox holdings+positions, or a
  hand-maintained positions block (`watchlist.json` `positions` or equivalent) to canonical positions. **Keeps
  all asset classes** (wealth-manager reuses this); consumers filter.
- **`resolve(prefer="indmoney", payloads={…})`** applies precedence **IndMoney → broker → portfolio**, sets
  `source` to the winner, notes empty/failed/absent sources in `gaps` (a normalize failure falls through, never
  aborts).
- **`equity_only(positions)`** / **`mf_only(positions)`** — broker/portfolio positions (`asset_class: None`)
  are equity by construction; IndMoney positions are kept unless their `asset_class` names another class.
- **Payload handoff:** pure compute over files, **never calls an MCP tool**. The **skill** invokes the personal
  tool (`mcp__{indmoney,kite,upstox}__*`), writes the raw payload to a temp file under `paths.tmp_dir("holdings")`,
  and passes the path (`--indmoney`/`--kite`/`--upstox`/`--portfolio`, plus `--equity-only`/`--mf-only`/`--prefer`).
  **Fills are never sourced here** — exact entry price+date come from broker order history only. `test_holdings.py`.

---

## Artifact: strategy spec
**Producer:** `strategy-manager` (owns the lifecycle). **Consumers:** `discover` via
`run_strategy_screen` (trading) or `run_stock_scan` (investment), `run_backtest` (writes back
`expectancy_assumptions`, trading only), `trade-tracker` (`regime_required`). **Location:**
`artifacts/state/strategies/<name>.yml` (`paths.state_dir("strategies")`). **Schema:**
`strategy-manager/assets/strategy-spec.example.yml` (commented); seed drafts in `assets/seed-strategies/`.

**`purpose`: `trading` (default) | `investment`.** A **trading** spec carries every block below and is
validated by backtest. An **investment** spec (feeds `discover stocks --invest`) carries `universe`,
`screening.fundamental` (a richer business-quality query), `ranking` (`metric` ∈ `return_12m | return_6m |
rs_vs_nifty`, `top_n`) and `regime_required` **only** — it OMITS `entry`/`exit`/`sizing`/
`expectancy_assumptions`. It is not backtested: `status` goes `draft → active` on a **completeness check**
(universe resolvable, query fields resolve, ranking metric known), and there is no optimize loop.
`select_strategy.py --purpose` filters by it and ranks investment specs by recency (they have no expectancy).

Key blocks and who reads them:

| Block | Written by | Read by | Meaning |
|---|---|---|---|
| `status` | strategy-manager validate/optimize | discover, select | `draft`→not tradeable; `active`→eligible; `inactive`→retired |
| `regime_required` | generate | select_strategy.py, trade-tracker | conditions checked against the live **market-context** artifact at PICK time |
| `screening.fundamental` | generate | discover Stage 1 | `provider: tickertape` + `query` (Tickertape catalogue field names, `>`/`<` only) + `max_survivors` |
| `screening.technical` | generate | discover Stage 2 | `provider: tradingview` (+`tradingview_filters`) or `compute` (+`compute_filters` naming `ta` features) |
| `entry`/`exit`/`sizing` | generate | `run_strategy_screen`, `run_backtest` (both via `compute/strategy.py`) | `entry.signal` (required machine trigger); `exit`: stop (auto-floored at max(0.5·ATR, 1% price)) / target (`measured_move`\|`min_rrr`\|`next_resistance`\|`trailing`\|`signal`\|`none`) / min_rrr (at least 1.5) / time_stop / **`trail_atr`** (ATR trailing stop) / **`exit_signal`** (close-on-condition, entry grammar); %-risk |
| `expectancy_assumptions` | **`run_backtest`** results, written back by strategy-manager | strategy-manager validate, select_strategy.py | `{win_rate, expectancy_R, profit_factor, n_trades, validated_by}`. strategy-manager applies the activation gate — `active` only on `expectancy_R > 0.2` over ≥~30 trades; select_strategy.py uses `expectancy_R` to rank |
| `live_performance` | trade-tracker → optimize | select_strategy.py | realized edge; its `expectancy_R` replaces the backtest's only when the aggregator sets `eligible_for_selection: true` (at least 10 closes backed by executions, none excluded or unattributed) |

Target names must be one of the values above. `measured_move` uses the prior 20-bar range. `min_rrr` sets the
target at the minimum reward:risk; `next_resistance` is an old name for the same rule and does not detect
resistance. `trailing` needs a positive `trail_atr`, `signal` needs `exit_signal`, and `none` needs one of them.
With no target, the engine uses trailing or signal when configured, else `min_rrr`. A fixed target can sit
alongside a trailing or signal exit, which may close the trade first. Trailing and signal exits can be
backtested, but the live screen skips them because a live entry needs a fixed target. Unknown stop rules,
nonpositive holding periods and negative trail multipliers fail validation before any fetch.

`entry.signal`, `compute_filters` and `exit_signal` take one expression or a list of them; a list means AND.
AND/OR/BETWEEN are case-insensitive and column names are case-sensitive. A trading spec must have an
`entry.signal`; screening filters never stand in for it. An invalid spec is a gap before any price is loaded.
Each live candidate carries the date of its decision bar in `as_of`. The screen config reports `generated_on`
separately, plus `as_of` (null when candidates have different dates) and `price_dates`.
Live quantity is sized from the entry and stop rounded to two decimals: entry to nearest, stop down, target up,
so rounding never raises the risk or lowers the reward:risk below the minimum.

**Invariant:** discover runs a spec **only** when `status: active` AND its
`regime_required` fits the live regime. A required condition with no market evidence fails. It has no default — no fitting active spec ⇒ no trade.

## Artifact: backtest evidence
**Producer:** `run_backtest` (`compute/backtest.py`, with `compute/strategy.py` interpreting rules).
**Consumers:** `strategy-manager validate` and its saved `expectancy_assumptions.validated_by` reference.
`out` is a path prefix, default `paths.backtest_dir(spec)/report`. The tool returns `summary_path`, `trades_path`
and `equity_path`, named by content hash, so a rerun with different results writes new files. A failed write
returns the metrics with a gap.

The JSON holds config, summary, buy-and-hold comparison, caveats and gaps. The trades CSV holds fill and exit
prices, `initial_stop`, final `sl` and `target`, quantity, net P&L, R and dates. **R is measured from the actual
fill to the original stop**, not from the signal close; with no positive initial risk, R is null. Per-year
figures (`by_year_pnl`, `by_year_expectancy_R`) group by exit year, and the current year is marked partial.
With no trades, means and profit factor are null.

The equity CSV has one column per symbol, each an independent account. `return_on_capital_pct` divides total
account gains by `capital_per_symbol × symbols_tested`, counting accounts that never traded. Symbols that
failed are listed in gaps. `max_dd_on_equity_pct` is the worst single account's drawdown, and
`max_drawdown_symbol` names it; this is not a combined portfolio. A signal on the last bar does not execute.
`open_trades_at_end` counts positions still open: their marked value is in `total_account_pnl`, but `total_pnl`,
win rate and expectancy use closed trades only. Sizing uses the signal close, so a gap at the next open can
exceed the planned risk.

`strategy.risk_parameters` rejects nonpositive capital and risk outside `(0, 1]%`, for both live sizing and
backtests. Backtests need a positive integer `years` and a long-only trading spec. A symbol whose history fails
is skipped with a gap.

## Artifact: universe
**Producer:** `get_universe` (on `sources/universe.py`). **Consumers:** `compute/{screen,stock_scan,sector_scan,
backtest}.py` (via `resolve_symbols`). **Location:** `paths.cache_dir("universe")/<name>-<date>.txt`, one NSE
symbol per line. The symbol list is **only ever a file** — the envelope carries `symbols_count` and
`universe_path`, never the list inline (the holdings/NAV/candles rule). Named universes come from NSE's
published constituent CSVs, cached dated; a failed fetch falls back to the newest cached copy as a labelled gap,
never a fabricated list. The fallback keeps its original path and `as_of` date. A custom basket's path includes a content hash.

## Artifact: stock-scan shortlist
**Producer:** `run_stock_scan` (on `compute/stock_scan.py`). **Consumer:** `discover` (`stocks --invest`).
**Location:** `paths.report_dir("discover")/stock-scan.json` (or `out`). **Shape:** `{as_of, purpose:
investment, spec, ranking_metric, universe:{source, screened, in_universe, ranked, shortlisted}, gates:{query,
max_survivors}, market_context, shortlist:[{rank, symbol, metric_value, returns, rs_vs_nifty}], report_path}`.
The screen ∩ universe is ranked by `ranking.metric` (`return_12m|return_6m|rs_vs_nifty`) and capped to top N;
**no entry/exit/sizing** — this chooses what to deep-dive, and `deep-analysis quick` judges the survivors.

## Artifact: sector-scan shortlist
**Producer:** `run_sector_screen` (on `compute/sector_scan.py`). **Consumer:** `discover` (`sectors --invest`),
`sector-analysis` (reads a sector's classified RS row instead of re-deriving it). **Location:**
`paths.report_dir("discover")/sector-scan-<hash>.json` (`out` is a filename prefix; read the returned path). **Shape:** `{as_of, generated_on, metric, ranking_rule,
shortlist:[{rank, sector, ticker, rs_vs_nifty:{1m,3m,6m}, rs_class, returns}], report_path}` for `rs_vs_nifty`
(the default), or `[{rank, sector, pe, pe_percentile}]` for `index_valuation_percentile`. RS is the shared
`compute/relative_strength.py` primitive, so a sector's RS and a stock's RS agree.

## Artifact: market-context
**Producer:** `market-analysis` — calls `get_market_context` (`finance/compute/context.py`) and persists the
digest to `artifacts/market-analysis/YYYY-MM-DD.json` (`paths.report_path("market-analysis", ext="json")`);
a run that does not persist it breaks every consumer. **Consumer:** every other skill — none computes its own
market view. Read-only callers pass `mode="quick"`; direct invocation uses `deep`, which also attaches
`recent_readings` (regime-transition history, diffed from prior dated artifacts). The **persisted file** —
not a tool return — is what `select_strategy.py`, `get_fund_scan(market_context=…)` and the next run's
transition history read, so the day's artifact is the shared market-of-record.

`mode="quick"` reuses today's artifact only if `generated` is today, `history_years` and `context_version`
match, and the JSON is valid; otherwise it recomputes. The daily file is replaced atomically under a lock. A
write failure returns the context with a gap.

`as_of` is the **last trading bar**, not the generation date — on a weekend the context is legitimately Friday's.
It is null when Nifty history is unavailable.

VIX carries its own `as_of`. VIX and sector gates are withheld when their date differs from Nifty's; sector
dates are in `breadth.sector_observation_dates`. A missing live-index `source_timestamp` is a gap, not fetch
time.

Missing VIX has band `unknown`. `risk_on` needs a known trend, a VIX band and complete sector breadth; missing
evidence gives `neutral` unless what is present already says `risk_off`. With incomplete sector coverage,
`pct_sectors_above_ema50` is null and `sectors_available`/`sectors_expected` show the shortfall. Consumers must
treat a null gate as failing.

| Field | Meaning | Read by |
|---|---|---|
| `market_trend` | `up`\|`range`\|`down` (Nifty vs 50/200-EMA + slope) | select_strategy.py, trade-tracker, discover, daily-brief |
| `market_posture` | `risk_on`\|`neutral`\|`risk_off` — the sizing gate | discover (size), deep-analysis (portfolio-manager sizing), daily-brief, trade-tracker |
| `rationale` | one line explaining the posture | daily-brief (the net read) |
| `trend_detail.above_ema200` | Nifty vs 200-EMA | select_strategy.py (`nifty_above: ema200`) |
| `trend_detail.{close,ema50,ema200,ema50_rising,pct_from_52w_high}` | trend context | daily-brief, discover |
| `volatility.vix` | India VIX level | select_strategy.py (`vix_max`), discover sizing |
| `volatility.{percentile_1y,percentile_5y,band}` | where that VIX sits historically | deep-analysis sizing, daily-brief |
| `breadth.pct_sectors_above_ema50` | coarse 10-sector count | select_strategy.py (`breadth_min_pct`) — **name frozen** |
| `breadth.{pct_above_sma50,pct_above_sma200,pct_near_52w_high,pct_near_52w_low,universe}` | real stock-level participation over the top 500 | discover, daily-brief, sector-analysis |
| `valuation.<index>.{pe,pe_pctile,pb,pb_pctile,dy,dy_pctile,stance,blended_pctile}` | cap-tier valuation vs that index's own 10y history, for `NIFTY 50` / `NIFTY MIDCAP 150` / `NIFTY SMALLCAP 250` | **mf-analysis** (is the category worth adding to), portfolio-review (smallcap-sleeve flag), deep-analysis (valuation leg context) |
| `relative.{smallcap_vs_largecap_pb_ratio,percentile_spread,read}` | cap-tier richness against each other | mf-analysis, portfolio-review |
| `flows.{FII,DII}.{buy_cr,sell_cr,net_cr}`, `flows_session` | institutional flow, ₹ Cr | daily-brief |
| `macro.{india_vix,usdinr,gold_usd,crude_brent,us_10y}.{last,chg_1m_pct,percentile_5y}` | cross-asset backdrop | daily-brief, deep-analysis |
| `sectors.{leaders,laggards}` | 1Y sector ranking | sector-analysis (cheap first pass), daily-brief |
| `gaps` | labelled degradations | every consumer — surfaced, never swallowed |

**Two load-bearing naming rules.** `market_trend`, `trend_detail.above_ema200`, `volatility.vix` and
`breadth.pct_sectors_above_ema50` are frozen spellings — `select_strategy.py:regime_fit` gates on them, so
renaming one silently breaks every spec's `regime_required`. And the posture is **`market_posture`**, never
`risk_posture` (that name means the *personal balance-sheet* posture in the wealth contract — the two collide
the moment wealth-manager reads market context).

## Artifact: trade-idea
**Producers:** `discover` (on confirmation), `trade-tracker` (capturing a position with no rationale).
**Consumers:** `trade-tracker` + `check_trade` (re-validate); `strategy-manager optimize`
(`aggregate_performance.py`) reads closed ideas' `result` block. **Location:**
`artifacts/state/trades/<SYMBOL>-<YYYY-MM-DD>.yml` (`paths.state_dir("trades")`; SYMBOL is the NSE symbol, no
`.NS`). **This file is the schema:**

```yaml
symbol: TESTCO                 # NSE trading symbol
exchange: NSE
source_skill: discover       # discover | trade-tracker
strategy: nifty500-momentum-swing   # link back to the spec — never null from discover
created: 2026-01-01
status: idea                   # idea | open | closed
setup: range-breakout
direction: long                # long | short
rationale: "one-line thesis from the screen that produced it"
thesis_invalidation:           # machine-checkable kill conditions, re-checked every run
  - "daily close below 50-EMA"
  - "break of breakout pivot 85"
  - "promoter pledge increase"
plan:
  entry: 100
  stop: 90
  target: 130
  rrr: 3.0
  time_stop_sessions: 20
  entry_basis: "prior 20d high + volume confirmation"
sizing: {capital: 500000, risk_per_trade_pct: 1.0, qty: 50}
regime_at_creation: {...}      # the market-context read the screen ran under (trend + posture)
```

`status` lifecycle: `idea` → (matched broker fill) `open` → (fully executed exit) `closed`. On promotion
`trade-tracker` adds **`fill_avg`** and **`entry_date`** from broker order history, sets `sizing.qty` to the
filled quantity, and keeps `plan.entry` and the original `plan.stop`. It appends a dated `tracker_log` each run.
A partial exit, a position missing from the broker, or the user agreeing to an exit does not close the
artifact; only broker exit executions do.

On close, `result` carries `{exit_date, exit_reason, exit_price, exit_qty, charges, realized_R, realized_pnl,
holding_sessions, execution: {source, exit_trade_ids}}`. `exit_reason` is
`EXIT_STOP|EXIT_THESIS|EXIT_TARGET|EXIT_TIME|MANUAL`; `execution.source` is `kite|upstox` with the broker's
trade IDs. `exit_qty` must cover the whole `sizing.qty`, and `exit_price` is the quantity-weighted exit price.
`charges` are the actual entry and exit charges. Net P&L = (exit − fill) × qty − charges, signed for direction;
realized R = net P&L / ((fill − stop) × qty). A missing input leaves the derived figures null with a gap; they
are never filled from a quote.

`aggregate_performance.py` checks execution IDs, dates, quantities and the P&L arithmetic. A closed artifact
that fails is listed in `gaps` and the strategy gets `REVIEW`, so its status does not change automatically.
`profit_factor` is computed in R, not rupees. `--update-spec` writes under a lock and sets
`live_performance.eligible_for_selection` only for at least ten verified closes. Closed artifacts without
execution IDs or charges stay excluded until the user reconciles them with broker records.

`check_trade` reads `plan, direction, thesis_invalidation, strategy, fill_avg, entry_date, sizing`. An explicit
`entry` argument overrides `fill_avg`; it never falls back to `plan.entry`. Sessions held counts bars after the
fill session, and is unknown when history does not reach the entry unless `sessions_held` is passed. Only
complete price conditions are evaluated; qualitative or compound ones go to `manual_review`, and a trade with
no evaluable condition cannot be certified HOLD.

Decision prices come from `prices.history` or a supplied OHLCV file. `data.as_of` is the last valid bar and
`metrics.price` its close. The personal `ltp` is used only as `metrics.mark_price` for unrealized P&L
(`mark_source: personal_ltp|decision_close`) and never triggers an exit. Every session after the fill is
checked against the stop, so a breach followed by a recovery still exits, and the reason names the breaching
session. On the fill day, or with no fill date, only the close is used. Plan levels are compared with
unadjusted bars; moving-average conditions use adjusted bars and go to `manual_review` if those do not end on
the decision bar. The skill raises time-stop alerts as revalidation reminders and does not convert sessions to
calendar dates.

## Artifact: document cache
**Producer:** `get_documents` (on `sources/documents.py`) → one `.txt` per document under
`paths.cache_dir("documents")`, named by hashes of the source URL and the extracted text. **Consumers:** `financial-analysis`,
`management-analysis`, `valuation-analysis` — every leg that cites a primary document. The envelope carries
**paths, never body text**: `data:{symbol, documents:[{kind ∈ annual_report|concall, label, url, publisher,
text_path, text_chars, text_lines, extracted_by, cached, outline}], documents_total, annual_reports_available,
concalls_available}`. A refresh that finds different text writes a new file, so earlier citations still
resolve. A cache hit checks the file's SHA-256. The cache has **no expiry** (`fresh=True` re-downloads); a
document that will not download or convert is a labelled gap, and the others still come back.

Annual reports are ordered by the reporting year in the label (the end year of a fiscal range), not a later
filing date. A label with several years and no clear reporting year falls back to list position with a gap.

`outline` is `{section_key: [{line, text}]}` — the notes a leg must cite, mapped to best-first candidate line
numbers in `text_path`. Keys: `auditors_report, emphasis_of_matter, auditor_remuneration, mdna,
directors_report, corporate_governance, related_party, contingent_liabilities, remuneration, tax_note, segment,
cash_flow, esop, shareholding, qna`. Ranked so the first is the section not its contents-page entry, capped at
four. **An absent key means the heading matcher found nothing**, not that the section is missing. Search the
text for other wording before reporting a data gap. Built once at conversion and cached with the document.

An orchestrator calls `get_documents` once and hands each leg the `text_path`s, so several legs land on the same
bytes; a leg given no paths calls the tool itself and gets the same cached file. **Extraction only** — nothing
here summarises, scores or judges; every verdict belongs to the leg reading the text.

## Convention: leg digest (deep-analysis IO hygiene)
Every forked leg **writes its full report to its file** and **returns only a compact digest** — its
machine-readable top block plus the file `path`, never the body. Downstream agents receive **paths** and Read
what they need, so the orchestrator never re-carries the full reports. A lens leg is a **skill run inside a
profile agent** (`terminal-analyst`, `field-analyst`, `desk-analyst`): the profile carries no method — the
skill owns the block below, the profile returns it unchanged plus `path`. Debate roles are named agents owning
their own blocks.

| Producer | Block | Fields |
|---|---|---|
| `technical-analysis` | `technical-block` | `verdict`, `confidence`, `trend_stage`, `support`, `resistance`, `bull_invalidated_below`, `bear_invalidated_above`, `axis: technical_structure` |
| `financial-analysis` | `financials-block` | `verdict`, `confidence`, `varsity_score` (PASS count of the applicable checks — 7, or fewer for financials where D/E/cash checks are NOT-APPLICABLE), `roce`, `de`, `cfo_ebitda`, `rev_cagr_5y`, **`clean_eps`**, **`eps_adjustments`**, `flags`, `axis: growth_durability` |
| `management-analysis` | `management-block` | `integrity` (the hard gate), **`integrity_checks`** (all seven sub-checks, each PASS/FLAG/FAIL/NOT-CHECKED), `skill`, `overall_grade`, `confidence`, `axis: governance` |
| `valuation-analysis` | `valuation-block` | `combined_stance`, `dcf_mos`, `dcf_confidence`, **`terminal_weight`**, `pe`, **`pe_basis`**, **`eps_adjustments`**, `peg`, `peer_median_pe`, **`peers_priced`**, **`ev_ebitda`**, `relative_stance`, `axis: valuation` |
| `news-scan` | `news-block` | `sentiment_score` (−2…+2), `confidence`, `recurring_theme`, `next_event`, `axis: growth_durability` |
| `sector-analysis` | `sector-block` | `sector`, `rs_class`, `stance`, `confidence`, `focus_position` |
| `deep-analysis` (`quick` mode) | `quick-block` | `verdict ∈ {keep, reject, review}`, `lean` (one line), `flags`, `reasons`, `gaps`. A screen from structured data only, run in the current context with no sub-agents. Discover's Stage B keeps the scan order among keeps and lists `review` separately. `keep` is not a BUY or an integrity pass. |
| `contest-researcher` | `contest-block` | `lean ∈ {bull, bear, genuinely split}`, `axis`, one-line `bull`, one-line `bear` |
| `bull-researcher` / `bear-researcher` | `debate-block` | `axis`, `claim`, `conceded`, `new_evidence` |
| `portfolio-manager` | `verdict-block` | `call`, `conviction`, **`value_stance`**, **`action_driver`**, `invalidation`, `review`, `integrity_gate`, `integrity_partial`, **`evidence`**, **`weakest_load_bearing_input`** |

An **integrity FAIL** in `management-block` overrides every other lens. `FLAG` is a concern short of
disqualifying, and `PASS (partial, k of 7)` means some checks could not run; neither may reach `verdict-block` as `PASS`.

`deep-analysis/scripts/escalation.py` reads the `debate-block`'s `axis` + `claim` + `conceded` +
`new_evidence` to decide the next round in `deep`: it escalates when the sides still have something to
test — **different** axes (cross-examination) or the **same** axis with distinct unconceded claims (rebuttal). A
concession, an identical claim, `new_evidence: false` on both sides after round 1, or the round cap (3 in
`deep`; `standard` has one contest pass) ends it. `axis` must come from `VALID_AXES` (`valuation, growth_durability, balance_sheet_risk,
governance, technical_structure`); anything else is a broken contract, not a converged debate. A `contest-block`
lean of `genuinely split` makes the synthesis suggest a deep re-run; it never auto-escalates. The helper
checks every digest field's type before applying any rule (the string `"false"` is not a concession), and an
invalid digest stops the debate with a gap.

`financials-block.clean_eps` is the earnings base `valuation-analysis` strikes multiples on: where
`eps_adjustments` is not `none`, the valuation leg's `pe_basis` is `adjusted` and its peer P/Es must be struck
the same way or `relval` voids the comparison. The two legs run in the **same parallel wave** — not a handoff,
so each runs the scan itself and carries `eps_adjustments` in its own block; the synthesis names any
disagreement. `pe_basis: reported (unchecked)` means the scan did not run and travels as a gap, never a clean
multiple.

Every leg report opens with its machine-read block, then **`## Findings`** (the whole case in a few plain
sentences), then **`## Detail`** (the workings). Debaters and the portfolio-manager build on Findings and reach
into Detail only for a load-bearing finding's evidence; the `report-writer` alone reads every paper in full.
A finding that never made the section is one the leg failed to surface.

The mode resolver decides whether the user holds the stock. It reads trade records under
`paths.state_dir("trades")` by their top-level `symbol` and `status`; an unreadable record is a gap. Any
observed holding means `yes`. `no` needs every connected broker account checked; otherwise the answer is
`unknown`. IndMoney and broker snapshots of the same account are not added together.

## Artifact: deep-analysis report
**Producer:** `deep-analysis` → a bundle at `artifacts/stocks/<TICKER>/<date>/runs/<run-id>/` holding the deck
(`report.html`), its projection (`report.json`) and the `agents/` work papers. A new run never overwrites an
earlier one. `get_prior_run(skill="deep-analysis"|"fundamentals")` returns the latest earlier projection for
that mode. **Consumer:** `trade-tracker` may read the projection as rationale when there is no trade-idea
artifact; any number it acts on must be fetched again. See *Report bundle publication*.

The modes differ by **amount of judgment**: `quick` is one pass in the current context (structured data only,
no sub-agents) → one `quick.md` under the run-day folder, **no deck and no bundle**; `standard` → four legs
(financials, management, valuation, news) + one contest pass → verdict; `deep` → all six legs + multi-round
bull/bear → verdict; `fundamentals` → financials, management, valuation, no debate. Work papers go to the
bundle's `agents_dir`.

Valuation and management write to the bundle's `agents/dcf.md`, `agents/dcf-inputs.yml` and
`agents/management.md`; run on their own, they write to the dated stock folder. `run_dcf` writes its full
result to a `dcf_path` named by content hash, so the same inputs reuse the file and different inputs get a new
one. To revise a valuation, cite both paths and say which assumptions changed. `revisions` is always empty and
kept only for compatibility. `get_prior_run` finds dcf and management papers inside bundles too.

## Artifact: report projection — **render input only**
**Producer:** `report-writer` writes the bundle's `report_json` path and nothing else. **Consumers:**
`render_report.py` renders it to the bundle's `report_html`; `get_prior_run` and trade-tracker read it as prior
reasoning. Nothing reads it back into a live decision. `coverage.brief` is the Telegram caption, sent only when
the user authorized delivery and only after archiving.

The renderer rejects JSON that is not an object, has duplicate keys or non-finite numbers. It writes the HTML
to a temporary file and renames it, so a failed render leaves the previous report in place, and it exits
nonzero with the error on stderr. Authored prose goes through the `rich_text` filter, which keeps emphasis,
line breaks, code and HTTP(S) links and strips everything else. Allocation charts show supplied shares as given
plus an unclassified remainder; they do not scale partial data up to 100%.

**Every value traces to a work paper.** A figure a paper does not carry is omitted so the deck renders that
slot's **labelled gap** — never a fabricated number, zero or blank; an empty pledge list is `"unknown"`, not
`"none"`; a missing chart series shows its gap notice. `coverage.brief` is the ≤10-line Telegram brief.
The shape is one key per deck slide over the seven-beat spine (`meta, cover, coverage, glance, overview,
scorecard, record, integrity, dcf, relative, technical, news, debate, sector, invalidation, gaps`);
**`skills/_report/scripts/fixtures/deep-analysis.sample.json` is the worked example and authority on field
names**, `templates/deep-analysis.html` consumes it, and charts come from `charts.py` (nine data-driven types),
never hand-authored markup. Covered by `test_render_report.py` (chart geometry, render integrity, gap-not-blank,
browser-gated 1620px overflow).

## Artifact: sector cache
**Producers:** `sector-analysis` (monthly refresher), `deep-analysis` (inline refresh when missing/stale).
**Consumer:** `deep-analysis`'s sector leg. **Location:** `state/sectors/<slug>.md` (`paths.sector_cache_path`)
— durable, not dated, overwritten on refresh. **Fields:** frontmatter `generated: YYYY-MM-DD` + `rs_class:`;
body = the sector-level read (RS vs Nifty, cycle, KPI snapshot, tailwinds/headwinds, leaders/laggards, stance),
**not** the focus-stock overlay (computed fresh). The **RS numbers come from `run_sector_screen`**
(`compute/sector_scan.py`), not re-derived in the skill. **Freshness:** `paths.sector_cache_age_days(sector)` `>30` or
`None` ⇒ stale ⇒ refresh + a `sector_refresh_due` alert (`dedup_key: sector-refresh-<sector>`, due +30d). Dated
trail under `sector-analysis/<date>/`.

## Artifact: alert
**Producers:** `trade-tracker` (`price_cross`/`time_stop`/`regime_change`), `filings-watch` (`filing_act_on`),
`strategy-manager` (`revalidate_due`), `deep-analysis` (`reanalyze_due` + `price_cross` + `opportunity`),
`discover` (`price_cross` + `opportunity`), `market-analysis` (`regime_change`), `portfolio-review`
(`rebalance_due`), `mf-analysis` (`sip_due`), `sector-analysis`/`deep-analysis` (`sector_refresh_due`),
`alert-manager` (manual). **Consumer:** `daily-brief` (surfaces, recommends — never auto-runs); `alert-manager`
curates. **Schema/logic:** `finance/compute/alerts.py`. **Location:** one file per alert at
`artifacts/state/alerts/<id>.yml` (`paths.alerts_dir()`).

| Field | Meaning |
|---|---|
| `id` | `<kind>-<subject>-<shorthash>` (generated) |
| `created_by` | producing skill |
| `subject` | `{type: stock\|fund\|strategy\|portfolio\|sector\|market, id}` |
| `kind` | `price_cross\|filing_act_on\|time_stop\|regime_change\|revalidate_due\|reanalyze_due\|rebalance_due\|sip_due\|sector_refresh_due\|opportunity\|investigate\|custom` |
| `trigger` | one of `{metric,op,level}` (cheap), `{due}` (date), `{check, args}` (needs a skill run) |
| `action` | `{text, suggest}` — human-facing verdict + optional command to surface |
| `severity` | `info\|watch\|act` |
| `status` | `open\|triggered\|snoozed\|done\|expired` |
| `dedup_key` | producers set this so re-runs update in place, never pile up |

**Functions:** `create` (dedups on `dedup_key`), `load_open(subject=None)`, `evaluate_cheap(alerts, market_data)`
(fires `metric`/`due` from already-fetched data; ignores `{check}`), `set_status`, `snooze`, `sweep`, `manage`
(the `manage_alerts` surface: list/add/dismiss/snooze/sweep, `list` ordered `act`→`watch`→`info`).
**Invariant:** alerts evaluate only when a skill runs (no cron); `daily-brief`/`alert-manager` never place an
order or auto-run a `{check}`. `test_alerts.py`.

## Artifact: watchlist
**Producer/consumer:** `daily-brief` (auto-adds *vetted* opportunities, recommends pruning; never
auto-removes). **Location:** `artifacts/state/watchlist.json` (`paths.watchlist_path()`). Shape:
`{"watchlist": [{ticker, added, source, note}], "positions": [{ticker, entry, sl, target, qty,
entry_date}]}`. The `positions` array is also the last rung of the holdings precedence in
`compute/holdings.py` (`--portfolio`).

## Artifact: budget merchant map
**Producer/consumer:** `budget-tracker` (`scripts/categorize.py`). **Location:**
`artifacts/budget/merchant-map.json` (`paths.merchant_map_path()`) — durable, not dated, co-located with the
dated `budget/<YYYY-MM>.html` reports. **Shape:** a flat `{ "<MERCHANT_TOKEN>": "<Category>" }`, keyed by the
token `categorize.normalize_token` produces (uppercased; narration plumbing / masked card numbers / `@handle`
suffixes / short+numeric words stripped; first significant word) so UPI/POS/handle variants collapse to one
rule. **Category** is a reference.md workbook category (Groceries, Dine & Entertainment, EMIs, Investments, …).
Resolution in `categorize.py`: **map → reference.md taxonomy → UNCATEGORIZED** (map wins, so a correction
overrides). The **same tokenizer** keys lookup and the `--learn` write. A missing map starts empty. An unreadable or
invalid map gives taxonomy-only results with a gap, and `--learn` refuses to overwrite it. `--learn` validates
the category, locks the file and writes it atomically. `test_categorize.py`.

## Convention: cashflow-leg digest (budget-tracker `quick`)
**Producer:** `budget-tracker` `quick`. **Consumer:** `wealth-manager` — the cheap cashflow read (same digest
hygiene as the deep-analysis agents). `quick` writes **no HTML** and no transaction detail; it returns only:

```
<!-- cashflow-block
savings_rate: <pct>            # (investments + leftout) / total inflow
buckets: { Essential:{actual_pct,target,status}, Lifestyle:{...}, EMIs:{...}, Investments:{...} }
biggest_leak: <category> ₹<amount>
recurring_monthly: ₹<observed active recurring/month> # excludes dormant and single charges
monthly_outflow: ₹<total spend/month>             # wealth-manager's emergency-fund runway denominator
target_source: workbook | framework
gaps: [ ... ]                 # "UNCATEGORIZED ₹X across N txns", "no prior months", ...
month: <YYYY-MM>
-->
```

`recurring.py` lists malformed or post-as-of rows it skipped in `gaps`; carry them into the digest. A charge is
recurring only when every interval for that merchant and account falls in the cadence band. A single charge
from a known merchant is a candidate with null `cadence` and `monthly_equivalent`. `total_committed_monthly`
sums observed recurring charges; despite the name, it does not prove a contract. Deduplicate imported
transactions before detection.

`target_source` names whether the bands came from the workbook or framework percentages (labelled, never
silently defaulted). Transaction-level data stays in the artifact.

## Allocation engine (`compute/allocation.py`)
Takes a long-only book. Positions with no value or a negative value are dropped with a gap, and totals cover
only valued positions. The same ticker across accounts is combined before the single-stock check. AMC
concentration is measured against the fund sleeve (`denominator: fund_sleeve`). A supplied cap or style
breakdown must be nonnegative, sum to no more than the book, and match where both value and percentage are
given; an invalid one is an input error and the CLI prints no partial result. Targets must name distinct asset
classes and sum to 100%. Rebalancing amounts are computed only when every holding is valued and classified
(`asset_drift.coverage_complete`); otherwise `move_value` is null, `rebalance` is empty, and concentration flags
ask for review instead of a trim amount.

## Convention: investments-leg digest (portfolio-review `quick`)
**Producer:** `portfolio-review` `quick`. **Consumer:** `wealth-manager` — the cheap investments read, sibling
of the cashflow digest. `quick` runs the allocation + concentration engine (`compute/allocation.py`) and cheap
per-holding drift/exit flags, but **not** the bounded `deep-analysis`/`mf-analysis` fan-out (that is
`deep`-only). It returns only:

```
<!-- investments-block
book_xirr: <blended portfolio XIRR %, or "inferred" | "unavailable">   # IndMoney, via compute/holdings.py
allocation: { asset_class:{equity,debt,cash pct}, market_cap:{large,mid,small,micro pct},
              top_sector:"<name> <pct>", top_amc:"<name> <pct>" }
concentration_flags: [ {dimension, category, pct, severity}, ... ]     # ranked, most-concentrated first
top_exits: [ {ticker, verdict, reason}, ... ]                          # bounded worst-first (EXIT/TRIM/REVIEW)
laggard_funds: [ {scheme, reason}, ... ]                               # from mf-analysis quick digests
value: ₹<total book value>
coverage: { sector:<pct>, market_cap:<pct> }                          # dimension coverage — partial reads as partial
gaps: [ ... ]                 # "no IndMoney — manual paste, XIRR unavailable", "target split not stated", ...
as_of: <YYYY-MM-DD>
-->
```

`book_xirr` is `unavailable` when no IndMoney/broker source connected, `inferred` when only staleness could be
estimated — never fabricated. `market_cap` splits come from the fund look-through's AMFI `cap_rank`, never a
personal source's breakdown. `laggard_funds` rows come from `mf-analysis quick` (`{scheme, grade_lite,
key_numbers, path}`, descriptive only). Holdings-value detail (the KEEP/TRIM/EXIT table) stays in the artifact —
values are sensitive; the digest carries verdicts and percentages only.

An investments digest made only of gaps is `not_assessed`, not strong; a severe finding from partial data is
still reported. Recurring spending alone is a floor on expenses: it yields `months_upper_bound`, not `months`,
and the emergency fund stays `not_assessed`.

## Convention: protection-leg digest (insurance-advisor Audit)
**Producer:** `insurance-advisor` Audit — opens its report with this block, transcribing the need-vs-have gap
table and red-flag list it computed. **Consumer:** `wealth-manager` (protection leg). Same hygiene: a compact
block, never the full report.

```
<!-- protection-block
term:    { have: ₹, need: ₹, gap: ₹, adequacy: adequate|short|absent }
health:  { have: ₹, need: ₹, gap: ₹, adequacy: adequate|short|absent }
vehicle: { status: ok|gap|n/a }
red_flags: [ { policy, flag }, ... ]      # room-rent cap, co-pay, lowballed IDV, ULIP cost drag, …
dependents: <n>|unknown
gaps: [ ... ]                              # "term need un-sizable — income not stated", …
as_of: <YYYY-MM-DD>
-->
```

`adequacy` is `absent` (no cover on that line), `short` (have < need), or `adequate` (have ≥ need).
An un-sizable line is a labelled gap, never a fabricated sum-assured or need. Without both term and health
assessed, protection cannot be strong.

## Artifact: net-worth spine + financial-health scorecard (wealth-manager)
**Producer:** `compute/wealth.py` (deterministic engine). **Consumer:** the `wealth-manager` orchestrator, whose
artifact is `artifacts/wealth/YYYY-MM-DD.md` (`paths.report_path("wealth")`) plus a rendered deck. The engine
reads a **picture JSON** — raw IndMoney `networth_snapshot` +
`networth_allocation_breakdown`, the `compute/holdings.py` positions envelope, the three leg digests above, and
an optional `profile` (`age`, `dependents`, `monthly_expenses`, `equity_band:{min_pct,max_pct}`,
`emergency_reserve:{available_value,as_of,source}`) — and owns every number.

- **Net-worth spine** (`build_spine`): `{ total_networth, as_of, allocation:{<bucket>:{label,value,pct}},
  liquid, observed_liquid, equity_share_pct, known_equity_share_pct, unclassified_equity_value,
  holdings_xirr:{count,avg,weighted_count,method,portfolio_xirr:null,best,worst}, source, coverage:
  complete|incomplete|tradeable-only, gaps:[…] }`. Allocation precedence: IndMoney breakdown (sees every class)
  → else aggregate tradeable positions by class (labelled `tradeable-only`). Buckets are the fixed
  `canonical_class` set (equity, mutual_funds, us_equity, debt, fd, epf, real_estate, gold, cash, insurance,
  crypto, other).
  - Coverage is `incomplete` when an asset row is malformed or negative, or the breakdown does not add up to
    the reported net worth.
  - `observed_liquid` is the cash and FD total. `liquid` stays null until `profile.emergency_reserve` gives a
    dated, sourced balance the user confirmed is available.
  - `known_equity_share_pct` counts direct Indian and US equity only. `equity_share_pct` is null while any fund
    or other holding has unknown composition (`unclassified_equity_value`).
  - `holdings_xirr.avg` is a value-weighted mean of per-holding XIRRs. It is not the portfolio's XIRR, which
    needs dated cash flows.
- **Liabilities.** The picture may carry `liabilities:{total,as_of,source}` from a first-party or user source.
  The engine then checks reported net worth against assets minus liabilities, or computes it when no total
  was reported, and computes percentages on gross assets (`allocation_basis: gross_assets`). Never derive
  liabilities as a balancing figure.
- **Cross-domain** (`emergency_fund` / `protection_read` / `risk_posture`): emergency-fund months of runway
  (liquid ÷ monthly expenses vs a 3–6 month target, using the unrounded ratio); protection-vs-net-worth status;
  risk posture, comparing equity share with the user's stated `profile.equity_band` (`below-target`,
  `within-target`, `above-target`, or `unknown` with no band). A weak or unassessed emergency fund or protection
  forces `fix-foundation-first` whatever the share.
- **Scorecard** (`build_scorecard`): `{ domains:{net_worth,investments,protection,cashflow,
  emergency_fund:{status,line}}, overall, assessed_domains, total_domains, coverage_complete,
  actions:[{priority,domain,text,next_step,run}] }`. Status ∈ strong|adequate|weak|critical|not_assessed;
  `overall` = worst *assessed* domain. Always show `assessed_domains`/`total_domains` so a partial result does
  not read as complete. Actions are ordered **across** domains by the health stack (emergency-fund/protection
  before fresh equity), max 5, each naming the spoke to run for depth. An unresolved policy red flag blocks a
  strong protection score; a savings rate above 100% withholds the cashflow score.
- `--snapshot` returns spine + cross-domain flags only (no legs, no scorecard). Deterministic and
  offline; covered by `finance/tests/test_wealth.py`.

## Report bundle publication

`finance.publication.prepare(session, ticker, day, mode)` creates a run directory at
`tmp/report-staging/<session-hash>/<run-id>/` (`paths.report_stage`) and returns the paths for `report.json`,
`report.html` and `agents/`. `run.json` records session, ticker, date, mode and run id; mode is standard, deep or
fundamentals. Write the `ready` marker only after rendering and every work paper are done.

`publish(session, run_id)` checks that the projection's ticker, date and mode match `run.json`, that the deck
and work papers exist, and that `ready` is present. Under a lock it renames the directory to
`stocks/<ticker>/<day>/runs/<run-id>/` (`paths.report_archive`); an existing archive is never replaced, and a
failure leaves staging in place. CLI: `python -m finance.publication prepare|publish`. To publish at the end of
a run, call `<plugin-root>/hooks/post-deep-analysis.sh publish ...`, which loads credentials first. The Stop
hook publishes ready bundles only for the `session_id` and `cwd` in its JSON input.

`prepare --telegram` records that the user authorized delivery; credentials alone do not. `finance/telegram.py`
sends the archived deck, or brief text via `bin/send-telegram.sh --text-file <path>`, through
`transport.request`. The token never appears in process arguments, redirects are not followed, and a send is
not retried. A failed send does not undo publication.

## DCF engine (`compute/dcf.py`)

- Inputs are finite numbers; numeric strings and booleans are rejected, and so are duplicate keys at any level
  of the JSON or YAML (including YAML merge keys). The horizon and glide years are integers inside the horizon.
  Financing weights and recovery fractions are in [0,1]; growth is above −100%; sales-to-capital is positive in
  every year. Default-free confirmation must be the boolean `true`. The bundled example values are synthetic.
- `model_shape: equity` treats `base_revenue` as after-tax earnings, so every margin must be 1, every tax rate 0,
  `net_debt` 0, and a rate buildup must weight equity at 1.
- Sensitivity grids center on the actual WACC path and hold explicit-period rates fixed when varying the
  terminal rate. Story scenarios shift explicit and terminal margins together and keep negative margins. The
  zero-shift cell equals the base value.
- Reverse solving accepts a root at either end and a response in either direction. It returns `solved: false`
  with a `reason` when the target is not bracketed or the iteration limit is hit; that does not mean the stock
  is cheap or expensive.
- A failed sensitivity, story or reverse calculation adds a gap and keeps the base valuation. Invalid base
  inputs reject the whole call.

## Discovery scans

A failed fundamental gate or an unresolved named universe gives no shortlist; the scan never widens to the
full screen or falls back to momentum. Invalid ranking, provider or limit inputs refuse before any fetch. One
symbol's price failure is a gap and the rest continue.

Each stock-scan candidate carries `price_as_of`, `price_source` and `price_fetched_at`. `as_of` is the common
price date (null when dates differ) and `generated_on` is the run date. Symbols whose return windows end on a
different date from the rest are not ranked. Like the sector scan, `report_path` is named by content hash and
`out` is only a prefix.

Sector RS uses `prices.close_history`, the same loader as the stock scan, and needs 127 closes on the same dates
as the benchmark for the 6M window. A sector with missing or invalid prices is unclassified, and one failed
sector does not stop the scan. Valuation ranking needs a positive P/E and a percentile in [0,100].

## Alert store

Writes run as a locked read-modify-write and replace the file atomically. IDs include a UUID, so alerts without
a `dedup_key` never collide. A refresh by `dedup_key` updates snoozed alerts too and keeps them snoozed; a key
cannot move to another subject or kind. Evaluation re-reads status from disk first, so a dismissed or snoozed
alert cannot fire from a stale copy. Each record is validated on read; an invalid one stays on disk, is skipped
and is reported as a gap (`load_all(gaps)`, `load_open(subject, gaps)`, and the `manage_alerts` envelope).
A trigger must be exactly one type, and a missing date is not read as today.

In `daily-brief`, holdings and performance come from personal sources, while prices, moves and alert checks
come from market tools. A close-based alert needs a completed session's candle, not an intraday quote. A price
event does not close a position. Time stops come from the trade's own strategy rule.

## Insurance math (`compute/insurance_math.py`)

- Term cover needs `annual_income`, `income_multiple`, `outstanding_loans`, `education_corpus`,
  `annual_expenses`, `years_to_independence`, `existing_corpus` and `existing_cover`. A missing input is a
  gap; the engine supplies no multiplier or default. `annual_expenses` may be null only when
  `years_to_independence` is 0.
- Health sizing takes `base_target`, `total_target`, `deductible`, `personal_cover` and `employer_cover`, with
  `0 < base_target <= total_target` and `0 <= deductible <= total_target`. It returns
  `base_gap = max(base_target − personal_cover, 0)`, `top_up_target = total_target − deductible`,
  `deductible_gap = max(deductible − personal_cover, 0)` and `planned_deductible_gap = max(deductible − base_target, 0)`.
- Vehicle: IDV is null with an `idv_gap` for a vehicle older than five years or `model_discontinued: true`.
  NCB is null with an `ncb_gap` when `claim_free_years` or `quoted_ncb` is missing. Each check stands alone.
  `idv_tolerance` is a screening assumption.
- `marginal_irr_continue` needs cash flows with both signs and exactly one sign change; otherwise there is no
  IRR and the result is `ok:false` with the cash flows kept. Remaining premiums fall at t0 through
  `remaining_premiums − 1`, with the surrender value forgone at t0. With no `hurdle_rate`, `beats_hurdle` is null.
- Negative amounts and ages are rejected, not clamped. The CLI exits 2 on malformed JSON and 1 on a computed gap.

## Rolling returns and look-through arithmetic

A rolling window ends at the first NAV on or after `years × 365.25` days, and only if that NAV is no more than
seven days late. With no eligible window, the statistics are null and `n_windows` is 0. A fund needs at least one
eligible window for the requested period before the category scan ranks it.

Look-through scales weighted means to avoid overflow. A metric that is still not finite is withheld with a gap,
whatever its coverage.

RSI is TA-Lib's output as-is, including on flat series.
