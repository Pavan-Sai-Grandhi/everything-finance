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
`data[<key>_total]` and `data[<key>_path]`. Spill files are immutable content-addressed snapshots: later calls cannot replace the evidence at an earlier returned path. Documents are *only* ever a path (*Artifact: document cache*).

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
helpers create dirs on demand. Entity components cannot contain traversal or separators; cache namespaces may nest within their tier. Dates are validated calendar days (monthly singleton reports also accept YYYY-MM). Existing symlinks cannot redirect paths outside the configured root. **`latest_prior(skill, subject, before=None)`** / **tool `get_prior_run`**
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
registered once. `sources/prices.history_df` owns price loading and the dated source cache for both
backtesting and live screening. The old undated `<symbol>_<years>y.csv` cache and fetcher inside `ta.py`
are removed; existing legacy CSVs are left untouched and ignored. TA-Lib needs the native lib
(`brew install ta-lib`), bootstrapped by `ta._need_talib()`; ordinary Python dependencies use `deps.need`.
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
| `trade_check.py` | `check_trade` | a trade-idea artifact + decision prices → recommendation and unrealized position metrics; never execution evidence |
| `fund_scan.py` | `get_fund_scan` | a whole SEBI sub-category → gated, scored shortlist (rolling-return math from `rolling.py`) |
| `lookthrough.py` | `get_fund_lookthrough` | complete holdings + per-stock ratios → weighted portfolio valuation, cap tilt, concentration |
| `rolling.py` | *(internal to `fund_scan`)* | rolling returns, drawdown, risk-adjusted ratios from a NAV series |
| `dcf.py` + `relval.py` | `run_dcf` | sourced inputs → intrinsic value/share (+ optional grids) and the relative-multiples read, one answer; full JSON and exact supplied inputs spilled immutably to `stocks/<TICKER>/<date>/dcf-<hash>.json` |
| `governance.py` | `run_governance_checks` | annual-report figures → `remuneration` (`ratio_pct` vs the 11% total cap; `executive_ratio_pct` vs the 5%/10% MD/WTD cap only when `executive_remuneration` and `managing_directors` are given) and `auditor_fee` (fee YoY vs aligned revenue/profit series); PASS/FLAG/FAIL/NOT-CHECKED, and invalid or unbenchmarked inputs are NOT-CHECKED, never PASS. Consumed by `management-analysis` checks 1 and 5 |
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
`corporate_actions(symbol)` → `data:{symbol, corporate_actions:[…]}`. `quarters` must be a positive integer (rejected before fetch); rows are ordered newest-first by their own period date and the pledge summary reads the newest filing's XBRL, fetched only from an HTTPS `nseindia.com` host. **Absent readable pledge evidence is a labelled gap meaning UNKNOWN, never "no pledge".**
Announcement items in `summarize` carry `filing_id`, a stable SHA-256 of date, attachment
URL and complete, untruncated source headline. Exact repeats collapse; distinct attachments or
headlines remain separate. Alert producers use `filing-<TICKER>-<filing_id>`, never a
date-only key. Version-3 filing caches exclude legacy snapshots that may have lost rows
through headline truncation or prefix deduplication. Long headlines retain full evidence;
reports may shorten their displayed summary without changing identity. IDs distinguish returned evidence, not a guaranteed
exchange event lineage; corrected or differently indexed disclosures may have new IDs.
An explicit XBRL `false`/`0` can establish zero pledged shares, but cannot establish zero other
encumbrances. Unknown/nil values remain unknown; invalid ranges, conflicting contexts and
contradictory declaration/figures produce gaps, also forwarded to the outer envelope.
All four exchange lists re-check issuer identity before selecting rows; missing/foreign symbols
are excluded with a gap. Shareholding filters before the quarter limit and XBRL fetch, and
symbols such as `M&M` are query-encoded. The endpoint has returned the whole market when its
filter is not honoured; `ok:false` + `gap` means "unknown", not "nothing
filed". `test_filings.py` (offline exchange/XBRL fixtures).

### `finance/sources/prices.py` — price fetch (live + history + reconcile)
Consumers: `get_quote` / `get_history` / `run_technical_screen`, plus `compute/{screen,trade_check,context}.py`
and `sources/market.py`. Two truths kept separate: the **TradingView scanner** (public India scan, **no auth**)
is live/screening truth; **yfinance** is EOD-history truth. Envelope forms:
- `quote(symbol)` → `data:{symbol, date, name, close, change, change_abs, volume, market_cap_basic, exchange}`.
- `history(symbol, period="1y", adjusted=False)` → `data:{symbol, period, adjusted, bars, as_of, bars_dropped_invalid, candles:[{date,open,high,low,close,volume}]}`. Index tickers (`^NSEI`, `^CNXIT`) pass through, equities get `.NS`; `adjusted=False` keeps the raw close for reconcile, warmup callers pass `adjusted=True`.
- `history_df(symbol, period="1y", adjusted=True)` → `(pandas OHLCV frame, gaps)` — fed straight to `ta.add_indicators`.
- `screen(filters, columns=None, limit=50)` → `data:{filters, count, candidates:[…], rows:[…]}`.
- `reconcile(symbol, tolerance=0.01)` → `data:{symbol, tv_close, yf_close, divergence_pct, tolerance, agree}`; a divergence beyond tolerance is a `gap`.
Technical screens require a positive integer limit and distinct nonempty column names.
The request enforces NSE and range `[0, limit]`; malformed responses and excluded rows
produce gaps. Returned candidates are unique NSE symbols; requested close values must be
finite and positive, and the limit is re-applied locally. A partial screen remains usable
with its gaps; market breadth forwards those gaps with its actual per-metric denominators.

History validates calendar dates, finite positive OHLC, nonnegative volume and consistent
low/open/close/high ranges, and sorts unique sessions. Invalid or duplicate sessions are
excluded with gaps and `bars_dropped_invalid`; a missing close does not establish why the
bar is missing. The old `bars_dropped_unsettled` field is removed because it asserted an
unverified cause. A bar dated today carries a completion-unverified gap; consumers must
not use that bar as proof of a completed-close event. Cache hits verify symbol, period,
adjustment, candle validity and summary identity before reuse. Current-day completion
verification still requires exchange/session evidence, not just a finite close.

**No indicators computed here** — callers pass `candles` to `ta.add_indicators`, so a screen and its backtest
share one indicator-of-record; no TV indicator ingestion or library. `test_prices.py` (offline parser + reconcile fixtures).

### `finance/sources/universe.py` — the universe authority
Consumers: `get_universe`, plus `compute/{screen,stock_scan,sector_scan,backtest}.py` (every screener resolves
its universe here — the one resolver). `resolve_symbols(name, fresh=False)` → `(symbols, gaps)` is the pure list
resolver; `resolve(name, fresh=False)` → the envelope (`data:{name, symbols_count, universe_path, as_of}`; see
*Artifact: universe*). Named universes (`nifty50|nifty100|nifty200|nifty500`, `microcap`, `fno`, `largecap20`)
come from NSE's published constituent CSVs via `transport.py`, cached dated with a stale-cache fallback; a list,
comma-string or file path is resolved locally. Holds `LARGECAP20_BASKET`. Symbol normalization belongs to the price source; no unverified demerger alias is applied.
`test_universe.py` (stubbed transport).

### `finance/sources/news.py` — company news (Google News RSS)
Consumer: `get_news`, read by `news-scan`, `deep-analysis` (news leg), `daily-brief`. `fetch(company, ticker,
days=60)` reads Google News RSS (the single source) → envelope `data:{company, ticker, days, count,
items:[{date, title, url, source, origin, kind, tag, publisher_tier}], noise_filtered, established_count}`.
Each item is **dated** (ISO or `null`), **deduped**, **classified** `kind ∈ {company, sector, noise}`, **tagged**
`tag ∈ {reported, narrative}`, and carries `publisher_tier ∈ {established, aggregator, unknown}` (never dropped —
weigh a single-sourced `aggregator` claim accordingly). **Noise is filtered from the default `items` view**
(pass `include_noise` to keep it). A block returns `ok:false` + labelled `gap`, never an empty crash.
The tag is title-only triage: `reported` is an unverified claim, never a verified fact.
Publisher tiers match known display labels exactly; they do not authenticate the publisher or
prove a claim. Material figures still need primary-source corroboration. Raw feeds are cached
once per company/query window/day using the shared atomic cache; ticker classification, noise
filtering and reference-date windows are derived per call. `fetched_at` retains the feed acquisition
time. `noise_filtered` counts only items actually removed. Invalid/unknown dates are `null` and
visible undated items produce a recency gap. Old processed caches are ignored.
`test_news.py` (offline parser/classifier/cache fixtures).

### `finance/sources/tickertape.py` — the one Tickertape client
Consumers: `sources/fundamentals.py`, `sources/funds.py`. Holds the `tickertape.in` Referer every path 403s
without; `resolve_sid(symbol)` → `({sid, ticker, name, sector, slug}, gap)`, the only NSE-symbol→Tickertape-sid
map (sid differs from ticker — REC is `RECLTD`/`RECM`). Only exact ticker equality is accepted (a near-miss
misattributes financials). Cached 90 days, with exact ticker/security-id validation on read; conflicting exact-match IDs are unresolved. Cache keys are content-hashed to avoid punctuation collisions, and the shared client rejects provider-declared failures/malformed responses.

### `finance/sources/fundamentals.py` — Tickertape financials + the screener.in document index
Consumers: `get_company_fundamentals` / `run_fundamental_screen`, read by `financial-analysis`,
`valuation-analysis`, and `discover` / `strategy-manager` (fundamental cut). Envelope forms:
- `fetch(symbol, sections=None)` → `data:{symbol, name, sid, ratios:{name:value}, pnl_10y:{columns,period_kinds,rows}, balance_sheet_10y:{…}, cash_flow_10y:{…}, quarters:{…}, shareholding:{columns,rows}, peers:[{symbol,name,sid,ttm_pe,pb}], documents:{annual_reports:[{label,url}], concalls:[{label,url}]}}`. `period_kinds` parallels `columns` (`FY`/`TTM`/`interim`). Each peer row carries its own **trailing** multiples from the same response, so the relative read needs no per-peer call; an unpublished multiple is `None`. `sections` narrows both answer and **work** (only those endpoints are called — what keeps `get_documents` to one screener fetch); a narrowed read does not populate the day cache, only a full one does. Unknown/malformed section requests refuse the whole request before fetching; cached projections list only returned sections and recompute `ok` for them. Full caches are keyed by NSE symbol plus any explicit security-id override; legacy symbol-only caches are ignored. Each source section degrades independently to its typed empty value and a gap on malformed data; empty table metadata is not usable evidence.
- `screen(query, limit=1000)` → `data:{query, count, candidates:[…]}`, biggest market cap first. `query` is `FIELD >/< VALUE` clauses joined by `AND` over Tickertape's screener field names; `>=`/`<=` and an unresolvable name **refuse the whole query** (a half-resolved query returns companies that never passed the cut). Repeated lower/upper bounds combine using the strongest constraint, independent of clause order; contradictory strict bounds and nonfinite/malformed thresholds refuse the query. Returned numeric projections are checked against every bound client-side; missing or failing rows are excluded with gaps. The limit must be a positive integer. Old unverified candidate caches are ignored.

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

### `finance/sources/screener_screen.py` — retired compatibility endpoint
`run_saved_screen` remains callable for legacy clients but always returns `ok:false`, an empty candidate list and a source-policy gap. It performs no network or cache access. Repository policy approves screener.in only for document discovery, not screening or financial inputs. Investment specs accept Tickertape only and must name a universe. Re-author unsupported saved-screen specs explicitly; do not weaken or substitute criteria automatically. `test_screener_screen.py` and `test_stock_scan.py` enforce refusal before fetching.

### `finance/sources/documents.py` — primary documents as cached local text
Consumer: `get_documents` (envelope, cache layout, reading legs in *Artifact: document cache*).
`fetch(symbol, annual_reports=1, concalls=1, fresh=False)` → envelope. Counts must be nonnegative integers; zero disables a section. Malformed index rows are gaps, URLs are deduplicated per section before applying the count, and individual document failures preserve other results. Takes the index from
`fundamentals.fetch(symbol, sections=["documents"])` (one screener fetch) and downloads each link via
`transport.request(url, dest=…)` (the one socket). Index links are untrusted: an IP-literal, loopback or local-network host is refused with a gap before download (a redirect from a public host is not re-checked). Each section is newest-first by year (and quarter) parsed
from the label; a label with no parseable year falls back to list position + a labelled gap. Conversion is
`pdftotext -layout` for PDFs (keeps table column alignment) and an in-process strip for text/HTML;
`extracted_by` records which ran. PDF URLs must return PDF bytes; non-PDF text must decode as UTF-8 and contain no binary controls. Known access/error page titles are rejected. These format checks do not prove publisher trust or document authenticity. Older metadata without format-validation status is re-extracted. A zero-char PDF extraction (cause unverified) and a missing `pdftotext` (`brew install
poppler`) are labelled gaps, never crashes. `test_documents.py`.

### `finance/sources/market.py` — market-wide fetch (indices, valuation history, breadth, flows, macro)
Consumers: `get_indices` / `get_index_valuation_history` / `get_breadth` / `get_flows` / `get_macro`, and
`compute/context.py`. **No skill reads this for a market view** — every skill reads the market-context artifact.
Envelope forms:
- `indices()` → `data.indices:{<CANONICAL NAME>:{last, pe, pb, dy, pct_change, pct_change_1y}}` for ~139 NSE indices in one call (NSE `allIndices`). `index_levels(names=None)` is the budgeted form (`None` = `BROAD_INDICES`; ~139 are too many inline).
- `breadth()` ranks NSE rows with positive market capitalization without a fixed rupee floor. `requested_universe` records the request; `universe` counts unique usable identities and each `counts.<metric>.of` is that metric's priced denominator. Missing coverage is a gap. Context preserves these counts; percentages must not be described as percentages of a larger requested universe.
- `macro()` retains source gaps and validates unique dated observations. Its `chg_1m_pct` is a 21-observation-interval proxy requiring 22 closes and a positive base, with `chg_1m_from` identifying that base date; otherwise null. `history_period`, `observations` and `first_observation` disclose the actual sample. `percentile` ranks available observations; legacy `percentile_5y` is only populated for a `5y` request and does not guarantee complete five-year coverage. Cache keys hash the period instead of interpolating it into a path.
- `flows()` returns only recognized FII/FPI and DII categories from one latest available session. Unknown categories, invalid/future dates, duplicate session/category rows and inconsistent buy-minus-sell versus net values are labelled gaps; an older category is never merged into the newer session. Net arithmetic allows ₹0.02 Cr of source rounding. Missing categories remain absent. Daily market caches use the shared atomic spine implementation.
- `index_snapshot(day)` / `valuation_history(index, years)` → month-end `{date, close, pe, pb, dy}` from NSE archive CSVs. **One fetch per sampled DATE serves every index**. Named CSV rows must match the requested archive session; duplicate index identities reject the snapshot. Permanent caches require a validated format version, numeric shape and a date within the requested fallback window; old caches are refetched. Snapshots are published atomically and future requests are rejected before transport. Validated snapshots are cached permanently (what makes a 10y multi-index percentile affordable). History de-duplicates actual trading dates after holiday fallback, forwards failed-sample gaps, and reports `requested_samples`, `first_observation` and `last_observation` alongside the unique `samples`. Nonpositive P/E/P/B and negative yields are unavailable for ranking. `max_fetches` bounds uncached or forced snapshot requests (a snapshot may try several holiday fallback dates). `valuation_percentiles(index, years)` → ranks only `{index, years, samples, pe|pb|dy:{current, percentile, n}}`; `pe` also carries `excluded` — P/E is ranked by `robust_pe_percentile` (samples ≥ 3× median dropped), the same method `get_market_context` uses, so the two cannot disagree.
- `breadth(universe)` → `data.counts:{above_sma50, above_sma200, advancing, near_52w_high, near_52w_low}`, each `{count, of}`.
- `flows()` → `data.flows:{FII,DII}:{buy_cr, sell_cr, net_cr}`; `macro(period)` → `{last, chg_1m_pct, percentile_5y, as_of}` per series.
- `percentile(values, value)` — the one pure primitive; ranks, does not judge.
`SECTOR_YF` is the **single** NSE-sectoral yfinance ticker map (which sectors exist). Fetches only — no regime
label, stance or score. `test_market.py`.

### `finance/sources/funds.py` — mutual-fund fetch (identity, category screen, full holdings, NAV)
Consumers: `resolve_fund` / `screen_funds` / `get_fund_holdings` / `get_nav_history` / `get_stock_ratios`, plus
`compute/{fund_scan,lookthrough}.py`. Envelope forms:
- `resolve(name)` → `{scheme_code, isin, amfi_name, plan, mf_id, tickertape_name}`; AMFI `NAVAll.txt` is the scheme-code/ISIN authority (mfapi's search misses funds).
- `screen(subsector, option, min_aum)` → `data.funds:[{mf_id, name, aum, expRatio, ret1y/3y/5y, sharpe, sortino, alpha, stdDevAnn, percSmallcap/Midcap/Largecap, ageInMon, …}]`. Vendor `match` string filters are ignored, so filtering is client-side; `PREMIUM_FIELDS` are stripped (one gated field 403s the whole call). `min_aum` must be finite and nonnegative, `limit_pages` a positive integer. A full final page at the page cap is a truncation gap, and a universe with any pagination gap is never cached.
- `holdings(mf_id)` → `data.positions:[{sid, ticker, name, weight, change3m, type}]` — the **complete** book (64-278 positions, 90-99% coverage), plus `equity_weight`, `sector_weights` (from the newest dated `sectorDistribution` snapshot), `sector_weights_as_of`, `allocation_history`. `sid` is the join key (differs from `ticker`). Equity rows must weigh 0–100%; non-equity lines such as net receivables/payables may be negative.
- `stock_ratios(sid)` / `enrich(positions)` → per-holding `{pe, ttm_pe, pb, roe, market_cap_cr, cap_rank, cap_label, sector, …}`, threaded + cached. **`pe` is annualised, `ttm_pe` is TTM** — for a peer comparison against a company's own `Stock P/E` (TTM) use `ttm_pe` (else ~8% skew). **`cap_rank`/`cap_label` from `amfi_cap_list()`** — AMFI's half-yearly `AverageMarketCapitalization*.xlsx` (link resolved from the categorisation index), whose `Sr. No.` **is** the SEBI rank (`caps.py`), joined on NSE symbol (ISIN fallback). A symbol absent from the period gets `cap_rank: None` + gap, `cap_label` falls back to the provider label. The rest of the row is Tickertape's sid-joined ratios.
- `nav_history(code)` → `data.navs:[{date ISO, nav}]` oldest-first.
- Identifiers are validated before cache or transport: `mf_id`/`sid` must be one URL path segment (`[A-Za-z0-9][A-Za-z0-9&_.-]*`), `scheme_code` a positive integer. `lookthrough.report(workers=…)` requires a positive integer.
**Fund holdings never come from the IndMoney feed** — it caps at 20 rows, misreports coverage, can be months
stale. `test_funds.py`.

AMFI workbook discovery accepts HTTPS URLs on `www.amfiindia.com` and
`portal.amfiindia.com`, without credentials or nonstandard ports. Relative links resolve
against the index URL. Both index and workbook requests refuse redirects; a changed
endpoint therefore produces a gap rather than an unchecked fetch. Future-dated periods
are ineligible both during discovery and when reading the workbook cache. Pre-validation AMFI
workbook caches are bypassed.

AMFI workbook ranks must be finite positive integers under the shared cap rules.
Invalid ranks and all rows sharing duplicate symbols or ISINs are excluded with a gap;
valid unrelated rows remain available. A ticker match that contradicts the supplied
ISIN cannot supply a rank. Pre-validation workbook and stock-ratio caches are bypassed.

The in-memory AMFI cap index is reused within one calendar day and artifact root.
A new day rechecks the disk cache's 30-day freshness policy; failed in-memory reads
therefore do not persist for the server's entire lifetime. Workbook downloads use
per-request temporary directories and the parser closes its workbook before cleanup.

Fund-source caches use hashes of complete keys, so punctuation in distinct fund/security
identities cannot collapse to the same cache entry. Existing disposable caches using
sanitized filenames are ignored and repopulated on demand. Malformed company-info,
ratio or classification payloads return a source gap for that holding; they do not abort
the other holdings' enrichment.

Enrichment fetches each distinct security ID once and preserves gaps from both successful
partial responses and failed responses. A missing ratio is not evidence that a holding
is unlisted. Look-through skips per-stock enrichment when the equity allocation is unknown:
additional ratio requests cannot repair the missing coverage denominator. Available
position counts and upstream gaps remain in the unusable report.

The look-through `pb_over_roe` uses P/B and ROE recomputed on their common holding set,
with coverage measured on that intersection. It may differ from dividing the separately
reported portfolio ratios, which can cover different holdings. The same coverage gate
applies; separate 60% coverage does not imply 60% shared coverage.

Look-through portfolio metrics require finite holding-weight percentages in [0,100],
a total no greater than 100%, and no listed weight above the supplied equity allocation
(apart from floating-point roundoff). Explicit zero allocation is not treated as missing. A nonempty holdings list requires
an explicit equity allocation; summing whatever rows arrived cannot substitute for a
missing coverage denominator. Tickertape holdings retain the full precision of the sum
of disclosed equity positions; this is disclosed-position coverage, not independent
verification that a provider omitted no positions. Malformed rows, invalid weights or
asset types, duplicate security IDs, and disclosed totals above 100% leave
`equity_weight:null` with gaps; valid positions remain available for inspection, but
cannot support coverage claims. Malformed optional sector data is separately labelled
and does not invalidate otherwise usable position weights. Legacy holdings caches are
bypassed by the validated cache namespace.
Invalid weights return `ok:false`, empty `metrics`, `confidence: unusable`, and
`ratios_publishable:false` with source and validation gaps; they cannot yield coverage
or valuation conclusions.

Fund-scan reports are immutable JSON snapshots under `paths.fund_dir("<category> scan")`.
`report_path` points to `fund-scan-<content-hash>.json`. An optional `out` is a filename
prefix hint, not an overwrite destination; consumers must use the returned path. A later
scan cannot replace an earlier shortlist, and identical content reuses its address.
Write failures return the computed shortlist with a gap and null `report_path`.

For cross-provider fund-scan ranking, `compute/fund_scan.match_amfi_scheme` requires
identifying-name token equality after plan/noise terms, Direct and Growth markers,
no excluded distribution-plan marker, and exactly one distinct AMFI scheme code.
Multiple candidates are a gap; shortest-name selection is not identity evidence.
Duplicate registry rows for the same code do not create ambiguity.

Fund identity matching requires every identifying query token at a word boundary (AMC word prefixes are allowed); an empty query cannot pick an arbitrary scheme. NAV parsing rejects invalid dates and nonfinite/nonpositive values with a labelled gap. Fund-screen caches include requested fields and page limits, and always project columns needed by client-side filters.

### `finance/compute/holdings.py` — holdings source-resolver + normalizer
Consumers: `daily-brief`, `trade-tracker`, and the personal-finance cluster (`wealth-manager`,
`portfolio-review`, `mf-analysis`). Turns whichever read source is connected into ONE canonical position shape
under a fixed precedence.
- **Envelope:** `resolve(…)` → `{ok, source, fetched_at, data:{positions:[…]}, gaps:[…]}`.
- **Canonical position:** `{ticker, qty, avg, ltp, pnl, xirr, broker, asset_class, invested, value, unsettled_qty, source, as_of}`. For Kite, `qty` = settled `quantity` + `t1_quantity` (Kite documents `quantity` as the T+2 settled amount, so a T+1 purchase has quantity 0 and is still held). Upstox documents `quantity` as the total holding, so `qty` = `quantity` there, unless `quantity` < `t1_quantity` proves T+1 was excluded. `unsettled_qty` names the T+1 part either way. Broker rows also carry `broker_symbol` (raw), `exchange` and `isin`; `ticker` drops an NSE series suffix (`-BE`, `-RR`, `-IV`, `-SM`…), and `asset_class` is set only from published identifiers — ISIN `INF…` → `etf`, `IN0…` → `sovereign gold bond`/`government security`, series RR/IV → `reit`/`invit` — so the equity slice excludes them (verified on a live Kite payload 2026-10-12). Neither broker documents a total formula; these are the plugin's stated readings of each broker's field definitions.
  `broker`/`invested`/`asset_class` populate from **IndMoney**, `None` when only broker/portfolio data. The live IndMoney `networth_holdings` (verified 2026-10-11) is a JSON string under `result`, one `asset_type` per call (the CLI takes `--indmoney` repeatedly), with `total_units`/`unit_price`/`total_pnl`/`investment`/`investment_code` and **no XIRR**; `investment_code` is an internal id kept as `instrument_code`, never a ticker. Linked-broker stock rows report cost equal to value with zero P&L; they normalize to unknown cost with `cost_basis: unreported_by_linked_broker`, and the resolver's gap names the connected broker to `--prefer` for their cost.
  exists. `value` retains a reported current value, including zero. The shared `market_value` helper used by allocation and wealth resolves reported value → invested plus P&L → quantity times current price; cost alone stays unavailable. `source` labels the winning source per position (`indmoney`, `kite`/`upstox`, `portfolio`).
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
| `entry`/`exit`/`sizing` | generate | `run_strategy_screen`, `run_backtest` (both via `compute/strategy.py`) | `entry.signal` (required explicit machine trigger; no screening-filter fallback); `exit`: stop (auto-floored at max(0.5·ATR, 1% price)) / target (exact `measured_move`\|`min_rrr`\|`next_resistance`\|`trailing`\|`signal`\|`none`) / min_rrr (finite, at least 1.5) / time_stop / **`trail_atr`** (ATR trailing stop) / **`exit_signal`** (close-on-condition, entry grammar); %-risk |
| `expectancy_assumptions` | **`run_backtest`** results, written back by strategy-manager | strategy-manager validate, select_strategy.py | `{win_rate, expectancy_R, profit_factor, n_trades, validated_by}`. strategy-manager applies the activation gate — `active` only on `expectancy_R > 0.2` over ≥~30 trades; select_strategy.py uses `expectancy_R` to rank |
| `live_performance` | trade-tracker → optimize | select_strategy.py | realized edge; `expectancy_R` overrides backtest only when the aggregator sets `eligible_for_selection: true` (≥10 execution-backed closes, no excluded/unattributed outcomes). Legacy scores lack this flag and are ignored |

Target names are exact machine values; free-text alternatives are rejected. `measured_move`
uses the prior 20-bar range height. `min_rrr` is a risk-multiple objective;
`next_resistance` is a legacy alias for that proxy, not detected chart resistance.
`trailing` requires positive `trail_atr`; `signal` requires `exit_signal`; `none`
requires either. If target is omitted, the engine selects trailing/signal when configured,
otherwise min_rrr. Dynamic exits remain backtestable, but the live screen returns a skip:
it cannot invent a fixed objective to satisfy the plugin's entry/stop/target discipline.
A fixed target can coexist with trailing or signal exits; those may close the trade earlier.
Unknown stop rules, nonpositive/noninteger holding periods and negative/nonfinite trailing
multipliers are rejected before source requests. Existing free-text specs need an explicit
rule chosen by their author; their prose is not silently migrated.

Machine condition fields (`entry.signal`, `compute_filters`, `exit_signal`) accept either
one nonempty expression or a list of nonempty expressions. Strings remain whole when extracting
features. AND/OR/BETWEEN keywords are case-insensitive; column names retain their case. Constants
must be finite and scalar comparisons produce an aligned boolean series. AND is used within BETWEEN;
conjunction across conditions is expressed as a list. A trading entry requires
at least one explicit `entry.signal`; coarse screening filters cannot substitute for it. A missing/empty/malformed trigger cannot become an all-bars entry or a backtest of a different setup. Legacy specs without a signal remain research drafts until their author explicitly encodes the intended entry and revalidates; no automatic migration copies screening filters into a trade trigger. Invalid specs become labelled gaps before the price loader runs. Source price gaps survive screening
and backtesting. Each live candidate carries its decision bar `as_of`; screen config separates
`generated_on` from `as_of` (the shared candidate date, or null for mixed/unknown dates) and lists
`price_dates`. Generation time cannot make old prices appear current.

**Invariant:** discover runs a spec **only** when `status: active` AND its
`regime_required` fits the live regime, with evidence for every required trend/EMA/VIX/breadth condition; missing evidence fails selection. It has no default — no fitting active spec ⇒ no trade.

## Artifact: backtest evidence
**Producer:** `run_backtest` (`compute/backtest.py`, with `compute/strategy.py` interpreting rules).
**Consumers:** `strategy-manager validate` and its saved `expectancy_assumptions.validated_by` reference.
`out` is a path prefix, default `paths.backtest_dir(spec)/report`. The tool returns `summary_path`,
`trades_path` and `equity_path`: content-addressed JSON/CSV filenames under that prefix. Identical
evidence can reuse a file; changed reruns cannot overwrite prior evidence. Writes publish only after
complete serialization. A persistence failure returns the available metrics/paths and a labelled gap.

The JSON contains config, summary, buy-and-hold comparisons, caveats and data gaps. The trades CSV
contains actual simulated fill/exit prices, `initial_stop` (preserved through trailing), final `sl`
and `target`, quantity, net P&L, R and dates at full numeric precision. **R uses actual fill minus
original stop**, not the preceding signal close. Unknown/nonpositive initial risk leaves R null
and expectancy unassessed. `year`, `by_year_pnl` and `by_year_expectancy_R` use the realized **exit**
year; the current year is labelled partial. No observations produce null means/profit factor,
never fabricated zeros or JSON Infinity.

The equity CSV has a date column and one independent account per successful symbol, using the
engine's daily marked equity. `return_on_capital_pct` divides aggregate account gains by
`capital_per_symbol × symbols_tested`, including successful zero-trade accounts. Failed tests
are excluded and named in gaps. `max_dd_on_equity_pct` is the **worst individual account** drawdown,
including initial capital as a peak; `max_drawdown_symbol` identifies its matching benchmark.
It is not a combined portfolio simulation. Forced finalization is disabled: a final-bar signal
cannot execute without a following bar. `open_trades_at_end` counts still-open simulated positions;
`total_account_pnl`/account returns include their marked value, while `total_pnl`, win rate and
expectancy include closed trades only. Unpaid exit charges are not deducted from open marks.
Review remaining open positions before treating the closed sample as representative. Entry-time sizing uses the prior signal close, so
next-open gaps can exceed the planned risk budget. Every account may have a different available
price window. Report these bases and compare corresponding symbols/dates, not a concatenated trade curve.

Shared `strategy.risk_parameters` rejects nonfinite/nonpositive capital and risk outside `(0, 1]%`
for both live signal sizing and historical runs. Backtests require positive integer years and
long-only trading specs. They validate these inputs before fetching data, preserve universe gaps,
and continue past individual failed price histories/tests.

## Artifact: universe
**Producer:** `get_universe` (on `sources/universe.py`). **Consumers:** `compute/{screen,stock_scan,sector_scan,
backtest}.py` (via `resolve_symbols`). **Location:** `paths.cache_dir("universe")/<name>-<date>.txt`, one NSE
symbol per line. The symbol list is **only ever a file** — the envelope carries `symbols_count` and
`universe_path`, never the list inline (the holdings/NAV/candles rule). Named universes come from NSE's
published constituent CSVs, cached dated; a failed fetch falls back to the newest cached copy as a labelled gap,
never a fabricated list. A fallback preserves the original snapshot path and `as_of` date; it is never copied into today’s cache. Custom universe paths include a content hash so one custom basket cannot overwrite another.

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
`paths.report_dir("discover")/sector-scan-<hash>.json` (`out` supplies a filename/prefix hint; use the returned path). **Shape:** `{as_of, generated_on, metric, ranking_rule,
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

Quick reuse requires today's `generated` date, the requested `history_years`, a compatible `context_version`, valid structure and finite JSON values. Older artifacts are recomputed. Publication atomically replaces the daily snapshot; simultaneous quick callers serialize cache lookup and computation. A requested extra output also receives cached results, and freshly computed results always update the canonical daily artifact. Filesystem failures return available evidence with a labelled persistence/locking gap.

`as_of` is the **last trading bar**, not the generation date — on a weekend the context is legitimately Friday's. It is null when the Nifty trend history is unavailable; generation time must never substitute for missing market evidence.

VIX records its actual `as_of`, observation count and first observation. VIX and sector-history gates must use the same session as Nifty; mismatches preserve dated evidence but withhold the gate. Sector dates are in `breadth.sector_observation_dates`. Live-index `source_timestamp` is preserved as supplied and a missing timestamp is a gap; it must not be replaced by fetch time. Duplicate canonical live-index identities are withheld, invalid nonpositive price/multiple fields are null, and missing requested indices produce an unsuccessful filtered response. Selecting indices does not mutate the full snapshot.

Missing or invalid VIX has band `unknown`. `risk_on` requires a known trend, valid VIX band and complete sector breadth; missing evidence yields a neutral posture with an explicit rationale unless available evidence already warrants `risk_off`. Sector breadth retains per-sector detail and `sectors_available` / `sectors_expected`, but its frozen gate percentage is null when coverage is incomplete. Consumers must not turn these null gates into passing defaults.

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

`status` lifecycle: `idea` → (matched broker fill) `open` → (fully executed matched exit) `closed`.
On promotion `trade-tracker` adds **`fill_avg`** and **`entry_date`** from broker order history,
records original actual entry quantity in `sizing.qty`, and preserves `plan.entry` and the original
`plan.stop`. Append a dated `tracker_log` each run. Partial exits, missing broker positions and
accepted recommendations do not close an artifact; reconcile actual execution history first.

On confirmed close, `result` carries `{exit_date, exit_reason, exit_price, exit_qty, charges,
realized_R, realized_pnl, holding_sessions, execution: {source, exit_trade_ids}}`.
`exit_reason` is `EXIT_STOP|EXIT_THESIS|EXIT_TARGET|EXIT_TIME|MANUAL`; `execution.source` is
`kite|upstox`, with distinct nonempty broker trade IDs. `exit_qty` accounts for the entire original
`sizing.qty`, and `exit_price` is the quantity-weighted actual price across those exits. Charges
are actual total entry/exit charges. Net P&L = signed (exit − fill) × quantity − charges;
realized R = net P&L / (signed initial fill-to-stop distance × quantity). Preserve full fill
precision; reported P&L/R may be rounded to two decimals. Missing inputs leave derived metrics
null with a gap, never inferred from a quote or an accepted recommendation.

`aggregate_performance.py` validates execution references, dates, quantities, finite values and
reconciles the reported arithmetic. Reused exit IDs require reconciliation. It reports excluded
closed artifacts in `gaps` and returns `REVIEW` for incomplete strategy samples, preventing
automatic lifecycle changes. Its `profit_factor` is explicitly R-weighted, not a rupee profit
factor when trade risk sizes differ. `--update-spec` writes atomically under a command-level lock,
rejects strategy traversal/symlink escapes, and sets `live_performance.eligible_for_selection` only
for complete samples of at least ten verified closes. **Migration:** legacy closed artifacts
without execution references/charges remain untouched and excluded until reconciled with broker
records; legacy cached live scores are ineligible. Never invent missing evidence to migrate them.

`check_trade` reads `plan, direction, thesis_invalidation, strategy, fill_avg, entry_date, sizing`.
An explicit `entry` overrides `fill_avg`; it never falls back to `plan.entry`. `qty` overrides the
actual original quantity on an open artifact. Sessions are observed bars strictly after the fill
session; history not covering entry leaves the count unknown unless `sessions_held` is supplied.
The tool uses shared TA-Lib averages and only parses complete, unambiguous price conditions.
Qualitative/compound conditions remain `manual_review`; no evaluable conditions cannot certify HOLD.

Decision prices come from `prices.history` or the supplied OHLCV file. `data.as_of` is the latest
valid decision bar's date and `metrics.price` its close. Personal `ltp` is used only as
`metrics.mark_price` for unrealized P&L/R (`mark_source: personal_ltp|decision_close`). It never
triggers a stop, target or thesis decision. Daily high/low are usable only after the recorded fill
date; same-day/unknown-fill-date checks use close and label the intrabar limitation. Every full
session after the fill is scanned, so a breach followed by a recovery still exits; the reason names
the first breaching session. Nominal plan levels are compared with unadjusted bars
(`prices.history(adjusted=False)`); moving-average conditions use the adjusted series and go to
`manual_review` when it does not end on the decision bar. Source and
input gaps survive into the envelope. Recommendations contain no realized exit data. The skill
defers regime/qualitative checks and raises time-stop **revalidation** alerts, never adds a number
of trading sessions to a calendar date.

## Artifact: document cache
**Producer:** `get_documents` (on `sources/documents.py`) → one `.txt` per document under
`paths.cache_dir("documents")`, named with hashes of the source URL and extracted text. **Consumers:** `financial-analysis`,
`management-analysis`, `valuation-analysis` — every leg that cites a primary document. The envelope carries
**paths, never body text**: `data:{symbol, documents:[{kind ∈ annual_report|concall, label, url, publisher,
text_path, text_chars, text_lines, extracted_by, cached, outline}], documents_total, annual_reports_available,
concalls_available}`. The URL identifies a mutable metadata pointer to an immutable text snapshot. A refresh
can detect changed content without overwriting earlier citations. Each download/conversion
uses a private temporary directory; metadata is atomically replaced only after successful
nonempty extraction. Cache hits verify the snapshot SHA-256 as well as file counts;
corrupt text is not served when a replacement download fails. The cache has **no automatic expiry** (`fresh=True` requests a re-download); a document that will not download/convert is a labelled gap, the others still come back.

`outline` is `{section_key: [{line, text}]}` — the notes a leg must cite, mapped to best-first candidate line
numbers in `text_path`. Keys: `auditors_report, emphasis_of_matter, auditor_remuneration, mdna,
directors_report, corporate_governance, related_party, contingent_liabilities, remuneration, tax_note, segment,
cash_flow, esop, shareholding, qna`. Ranked so the first is the section not its contents-page entry, capped at
four. **An absent key means the heading matcher found no candidate**, not that the section
is absent. Search the saved text for alternate wording when the check needs it; if still
unresolved, report a data gap. Built once at conversion and cached with the document.

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
| `deep-analysis` (`quick` mode) | `quick-block` | `verdict ∈ {keep, reject, review}`, `lean` (one line), `flags`, `reasons` (cited criteria/evidence), `gaps` — a screening review from structured data only, executed in the current context without nested dispatch. Discovery’s Stage B retains the deterministic scan order among keeps, separates review cases, and ignores legacy `score` fields. Keep is not BUY or an integrity pass. |
| `contest-researcher` | `contest-block` | `lean ∈ {bull, bear, genuinely split}`, `axis`, one-line `bull`, one-line `bear` |
| `bull-researcher` / `bear-researcher` | `debate-block` | `axis`, `claim`, `conceded`, `new_evidence` |
| `portfolio-manager` | `verdict-block` | `call`, `conviction`, **`value_stance`**, **`action_driver`**, `invalidation`, `review`, `integrity_gate`, `integrity_partial`, **`evidence`**, **`weakest_load_bearing_input`** |

An **integrity FAIL** in `management-block` overrides every other lens; an `integrity` of
`FLAG` is a live concern short of disqualifying, and `PASS (partial, k of 7)` is uncertainty; neither is a cleared gate, and neither may reach `verdict-block` as `PASS`.

`deep-analysis/scripts/escalation.py` reads the `debate-block`'s `axis` + `claim` + `conceded` +
`new_evidence` to decide the next round in `deep`: it escalates when the sides still have something to
test — **different** axes (cross-examination) or the **same** axis with distinct unconceded claims (rebuttal). A
concession, an identical claim, `new_evidence: false` on both sides after round 1, or the round cap (deep 3; standard is one contest pass, never another round) ends it. `axis` must come from `VALID_AXES` (`valuation, growth_durability, balance_sheet_risk,
governance, technical_structure`); anything else is a broken contract, not a converged debate. A `contest-block`
lean of `genuinely split` makes the synthesis suggest a deep re-run; it never auto-escalates.
The helper defaults to deep, validates modes/rounds and all digest field types before any stopping
rule, and preserves comparison operators, signs and decimals when comparing claims. A JSON string
`"false"` is not a boolean concession. Invalid files/digests stop with gaps, not claimed convergence.

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

The mode resolver reads only matching, contained trade records with parsed top-level `symbol` and
`status` (`idea|open|closed`), using `paths.state_dir("trades", create=False)`. Nested or quoted notes
cannot establish an open trade; malformed/unreadable records leave a gap and cannot prove no holding.
Broker `no` requires complete coverage of every connected account; any observed holding establishes
`yes`, and incomplete unmatched coverage is `unknown`. Keep overlapping aggregator/broker snapshots
separate until reconciled so quantities are not counted twice.

## Artifact: deep-analysis report
**Producer:** `deep-analysis` → an immutable bundle at `artifacts/stocks/<TICKER>/<date>/runs/<run-id>/`.
The deck (`report.html`) is the deliverable, with its readable projection (`report.json`) and `agents/`
work papers beside it. Publication moves the whole ready bundle at once and never overwrites a prior run.
`get_prior_run(skill="deep-analysis"|"fundamentals")` resolves the latest earlier matching projection,
with separate mode histories and legacy report-file support. **Consumer:** `trade-tracker` may read the
projection as rationale when there is no trade-idea artifact; decision numbers must be refreshed from
approved sources. See *Report bundle publication* for preparation, identity and delivery rules.

The modes differ by **amount of judgment**: `quick` is one consolidated pass in the context already running the skill (structured
data only, no nested agent or skill dispatch) → one `quick.md` under the run-day folder, **no deck**; `standard` → four legs (financials,
management, valuation, news) + one contest pass → verdict; `deep` → all six legs + multi-round bull/bear →
verdict; `fundamentals` → financials, management, valuation, no debate. Work papers use the bundle's
returned `agents_dir`. Standard has financials, news, contest and verdict; deep also has technical,
sector and bull/bear rounds. Quick produces no deck or publication bundle.

Valuation and management write directly to the bundle's supplied `agents/dcf.md`,
`agents/dcf-inputs.yml` and `agents/management.md`. Standalone runs retain dated report defaults.
The DCF engine returns immutable content-addressed `dcf_path` evidence in the stock's run-day folder;
every input, result and relative read is retained together. Identical calls reuse that path; changed
calls cannot overwrite it. `revisions` remains an empty compatibility field: authors explicitly cite
old/new evidence paths and changed assumptions rather than inferring revision lineage from a shared
filename. `get_prior_run` finds dcf/management work papers in published bundles as well as legacy
standalone reports. Sector context still uses the shared sector cache contract below.

## Artifact: report projection — **render input only**
The renderer requires an object projection with unique JSON keys and finite numeric literals. Template names are simple bundled names. It renders fully before atomically replacing the HTML output, rejects an output path resolving to its JSON source, and preserves any existing report if rendering/publication fails. CLI input/template/storage errors produce a nonzero status and structured stderr gap; no partial HTML is published.

Report-authored rich prose passes through the renderer's `rich_text` filter: emphasis, line breaks, code and HTTP(S) anchors are preserved; scripts, event attributes, embedded media and arbitrary styling are not trusted. Generated chart/runtime markup remains separate. Percentage allocation charts retain absolute supplied shares and show an unclassified remainder; they never renormalize partial coverage to 100%. Invalid/over-total allocation data renders a labelled gap.

**Producer:** `report-writer` writes only the prepared bundle's returned `report_json` path.
**Consumers:** `render_report.py` renders to that bundle's `report_html`; publication requires matching
`meta.ticker`, `meta.date`, `meta.mode`, a complete deck and readiness marker. `get_prior_run` and
trade-tracker read the archived projection as prior reasoning, with source attribution and gaps retained.
Use current source data for a new decision. `coverage.brief` is the caption for explicitly authorized
Telegram delivery, performed only after archiving. No individual staged file is moved separately.

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
overrides). The **same tokenizer** keys lookup and the `--learn` write. Missing map ⇒ empty initial rules. Invalid/unreadable map ⇒ taxonomy-only with a reported gap for reads; learning refuses to overwrite existing state. CLI corrections validate category/key shape, lock the full read–modify–write operation and publish atomically. `test_categorize.py`.

## Convention: cashflow-leg digest (budget-tracker `quick`)
**Producer:** `budget-tracker` `quick`. **Consumer:** `wealth-manager` — the cheap cashflow read (same digest
hygiene as the deep-analysis agents). `quick` writes **no HTML** and no transaction detail; it returns only:

```
<!-- cashflow-block
savings_rate: <pct>            # (investments + leftout) / total inflow
buckets: { Essential:{actual_pct,target,status}, Lifestyle:{...}, EMIs:{...}, Investments:{...} }
biggest_leak: <category> ₹<amount>
recurring_monthly: ₹<observed active recurring/month> # excludes dormant and unconfirmed single charges
monthly_outflow: ₹<total spend/month>             # wealth-manager's emergency-fund runway denominator
target_source: workbook | framework
gaps: [ ... ]                 # "UNCATEGORIZED ₹X across N txns", "no prior months", ...
month: <YYYY-MM>
-->
```

`recurring.py` returns `gaps` for excluded malformed/post-as-of debit rows. Carry these into the digest. Its subscription rows include `account`; a single familiar-merchant charge is a low-confidence candidate with null `cadence` and `monthly_equivalent`, not a monthly obligation. `total_committed_monthly` is the historical field name for the sum of observed active patterns; it does not certify contractual commitments. Merchant/account series must satisfy the cadence band at every interval. Normalized imports must be deduplicated by source transaction identity before detection.

`target_source` names whether the bands came from the workbook or framework percentages (labelled, never
silently defaulted). Transaction-level data stays in the artifact.

## Allocation computation input constraints
`compute/allocation.py` accepts a long-only valued holdings book. Missing, malformed or negative-valued positions are excluded with gaps; reported totals and percentages cover only the valued subset. Stock concentration combines matching case-normalized ticker rows across accounts. AMC concentration flags use the valued fund sleeve and declare `denominator: fund_sleeve`; descriptive whole-book allocation breakdowns retain their book denominator. Supplied cap/style breakdowns represent disjoint categories: values must be finite and nonnegative, explicit percentages require the book total, and combined amounts cannot exceed that total. If both value and percentage are supplied they must agree. Normalized category aliases are summed rather than overwritten. Partial coverage is not scaled to 100%. Invalid breakdowns raise an input error; the allocation CLI reports that error without emitting a partial JSON result. Targets must name unique normalized asset classes and total 100%; thresholds must be recognized finite percentages between 0 and 100. `asset_drift.coverage_complete` requires usable values for every supplied holding and no valued unknown asset class. Without that coverage, `move_value` is null and `rebalance` is empty, with a labelled gap. Concentration flags on a partially valued book request review instead of prescribing a trim amount. Exact rupee values, not rounded displayed percentages, drive complete-book rebalancing amounts. These checks do not prove complete portfolio coverage or authorize a transaction.

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

Wealth-manager does not interpret an investments digest containing only gaps or omitted checks as a strong book. Confirmed severe findings may still be reported from partial evidence. For emergency-fund calculations, recurring spending alone is an expense floor: the derived `months_upper_bound` is not `months`, status stays `not_assessed`, and it cannot authorize extra risk. Invalid liquid balances or nonpositive/missing expenses also remain unassessed.

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
An un-sizable line is a labelled gap, never a fabricated sum-assured or need. Missing term or health assessment cannot yield strong overall protection or permission to add investment risk; an assessed weak/critical line still retains its adverse status.

## Artifact: net-worth spine + financial-health scorecard (wealth-manager)
**Producer:** `compute/wealth.py` (deterministic engine). **Consumer:** the `wealth-manager` orchestrator, whose
artifact is `artifacts/wealth/YYYY-MM-DD.md` (`paths.report_path("wealth")`) plus a rendered deck. The engine
reads a **picture JSON** — raw IndMoney `networth_snapshot` +
`networth_allocation_breakdown`, the `compute/holdings.py` positions envelope, the three leg digests above, and
an optional `profile` (age/dependents/monthly_expenses/equity_band:{min_pct,max_pct}/emergency_reserve:{available_value,as_of,source}) — and owns every number.

- **Net-worth spine** (`build_spine`): `{ total_networth, as_of, allocation:{<bucket>:{label,value,pct}},
  liquid, equity_share_pct, holdings_xirr:{count,avg (descriptive value-weighted mean),weighted_count,method,portfolio_xirr:null,best,worst}, source, coverage:
  complete|incomplete|tradeable-only, gaps:[…] }`. Allocation precedence: IndMoney breakdown (sees every class)
  → else aggregate tradeable positions by class (labelled `tradeable-only`). Malformed/missing/negative asset rows or a breakdown sum differing from reported net worth produce `incomplete` coverage and a reconciliation gap. Reported nonpositive net worth never supplies a percentage denominator. `allocation_total` retains the observed asset sum; it is not an inferred liability adjustment. `observed_liquid` retains observed cash/FD amounts without asserting availability. `liquid` is null until `run` validates an explicit `profile.emergency_reserve` (nonnegative available_value, nonfuture ISO as_of, nonempty source); reserve evidence is passed through to the spine/cross-domain output. This independently verified reserve can be assessed despite incomplete net worth;
  `known_equity_share_pct` reports direct Indian/US equity only; crypto is excluded. `unclassified_equity_value` records unresolved fund/other/retirement/insurance composition. Total `equity_share_pct` is null while such exposure exists or coverage is incomplete, so the risk comparison cannot assume all funds are equity. Buckets are the fixed `canonical_class` set (equity,
  mutual_funds, us_equity, debt, fd, epf, real_estate, gold, cash, insurance, crypto, other).
Picture may include `liabilities:{total,as_of,source}`: a nonnegative outstanding balance with nonfuture ISO date and first-party/user evidence. Never infer this input as a balancing difference. With valid liability evidence, the engine compares reported net worth to `allocation_total - liabilities_total`, or calculates that net amount when no snapshot total exists. `allocation_basis: gross_assets` then uses the asset subtotal for composition percentages; without this input, legacy reported-total percentages remain labelled `reported_total`. Missing snapshot plus missing liabilities produces an incomplete asset-subtotal view, not certified net worth. Liability evidence and any reconciliation gap survive into the report.

Holding XIRRs are normalized finite rates; invalid entries produce gaps. `holdings_xirr.avg` is only a descriptive current-value-weighted mean over `weighted_count` positively valued holdings. It is not portfolio XIRR, and best/worst holding rates may span different cash-flow histories. Computing portfolio XIRR requires aggregate dated cash flows (or a separately attributed first-party portfolio figure); do not promote this mean into a return for the book.

- **Cross-domain** (`emergency_fund` / `protection_read` / `risk_posture`): emergency-fund months of
  runway (liquid ÷ monthly expenses vs a 3–6 month target); protection-vs-net-worth status; risk
  posture (equity share vs an explicit `profile.equity_band`, **gated by** the emergency-fund + protection state — a weak or unassessed
  foundation forces `fix-foundation-first` whatever the share). Without a valid stated range the comparison is `unknown`; age never defines a limit. Valid comparisons return `below-target`, `within-target`, or `above-target`, replacing the old automatic add/reduce-risk labels. Out-of-range comparisons request review rather than a trade.
- **Scorecard** (`build_scorecard`): `{ domains:{net_worth,investments,protection,cashflow,
  emergency_fund:{status,line}}, overall, assessed_domains, total_domains, coverage_complete, actions:[{priority,domain,text,next_step,run}] }`. Status ∈
  strong|adequate|weak|critical|not_assessed; `overall` = worst *assessed* domain (an absent leg is a
  gap, never sets overall). Actions are ordered **across** domains by the health stack
  (emergency-fund/protection before fresh equity), max 5, each naming the spoke to run for depth.
Emergency-fund status thresholds use the unrounded ratio; displayed months remain rounded. Invalid (>100%) savings rates or cashflow gaps withhold the cashflow score. Unresolved policy red flags cannot certify strong protection. Scorecard `overall` still summarizes assessed domains only: always disclose `assessed_domains`/`total_domains` and `coverage_complete` to prevent a partial good result reading as comprehensive health. Wealth CLI validates object-shaped top-level blocks and emits strict finite JSON or a structured nonzero error without a partial report.

- `--snapshot` returns spine + cross-domain flags only (no legs, no scorecard). Deterministic and
  offline; covered by `finance/tests/test_wealth.py`.

Live plans size quantity from the published two-decimal entry and stop. Entry rounds to nearest, stops down, and proxy targets up so rounding cannot exceed the declared risk budget or undercut minimum RRR. Historical execution retains source precision and fills at the next open; gaps and transaction costs can make actual risk differ from a signal-bar plan.

## Report bundle publication

`finance.publication.prepare(session, ticker, day, mode)` creates a unique run under
`paths.report_stage(session, run_id)`: `tmp/report-staging/<session-hash>/<run-id>/`.
It returns explicit paths for `report.json`, `report.html` and `agents/`, and writes immutable
identity fields in `run.json` (session, ticker, date, mode, run_id). Modes are standard, deep or
fundamentals. The run id is a sortable creation timestamp plus a UUID; sessions never share a
staging directory. Callers write `ready` only after rendering, verification and all work-paper
writes finish.

`publish(session, run_id)` requires matching projection meta (ticker/date/mode), a nonempty deck,
work-paper directory and readiness marker. Symlinks are refused. A kernel lock serializes repeated
publication attempts, and one rename publishes the whole directory to
`paths.report_archive(ticker, day, run_id)` at `stocks/<ticker>/<day>/runs/<run-id>/`. Existing
archives are never replaced. A failure leaves the staging bundle for repair. The `publish()` library function performs no network or
notification; its CLI delegates authorized delivery after publication succeeds. CLI equivalents are `python -m finance.publication prepare`
and `publish` with named arguments (`--help` lists them). For explicit completion, invoke
`<plugin-root>/hooks/post-deep-analysis.sh publish ...` to load optional credentials through the
shared loader before publication and authorized delivery.

`get_prior_run` reads these complete bundles for deep-analysis/fundamentals, selects the newest
run id from the latest earlier day and retains legacy report-file support. Fundamental-only and
standard/deep histories stay separate. The writer uses returned bundle paths; the orchestrator marks readiness after rendering verification. Normal
completion publishes explicitly; the Stop hook recovers ready bundles for the JSON payload's exact
session_id and cwd. It never scans legacy flat staging. Without SessionStart, callers retain a generated
UUID session identity and publish explicitly. `prepare --telegram` records user-authorized delivery;
credentials alone do not authorize it. Delivery uses the archived deck, keeps the token off process
arguments, follows no redirect and never automatically retries an uncertain send. Delivery gaps cannot
undo publication. Old flat staging is retained for explicit inspection and migration, never guessed into
a session.

### DCF scenario invariants

The terminal sensitivity grid resolves its center from the actual WACC path, including a buildup,
and freezes explicit-period discount rates in every cell. A terminal-rate change cannot silently
change the young-company explicit discount-rate fade. Story margin scenarios shift both explicit
and terminal margins, preserve negative margins, and reproduce the base value at zero shift.
Reverse margin solving uses the same signed path/terminal shift. Sales-to-capital ratios must be
finite and strictly positive in every explicit year; zero never means costless growth.

DCF model scalars and path entries are finite numbers; numeric text and booleans do not substitute
for quantities. Paths cannot be empty. The forecast horizon and glide timing use integers, with
glide endpoints inside the horizon. Financing weights lie in [0,1] and sum to one; recovery fractions
lie in [0,1]. Explicit discount factors must remain finite and positive, and revenue growth cannot
be below -100%. Default-free confirmation requires the boolean true, never a truthy string.
Reverse-margin output preserves the signed path used by its solver.

Supplied current prices must be finite and strictly positive. Risk-free rates retain their
calculation precision when passed from the WACC buildup into validation and scenarios;
display rounding must not change model inputs. Unrepresentable numeric inputs and nonfinite
valuation totals are rejected, not published as a successful valuation.

Reverse solving accepts endpoint roots and either direction of response within a bracket.
It reports `solved: false` when the iteration limit is reached or the endpoints do not bracket
the target. An unbracketed result is not evidence that a stock is cheap or expensive: interior
or multiple roots may exist. Successful shifts and implied paths preserve solver precision.
The target and tolerance must be positive finite numbers; the iteration limit a positive integer.
DCF input files reject duplicate fields at every mapping level in JSON and YAML, including
overrides introduced through YAML merges. Model field names must be strings. Keep one explicit
value per assumption instead of relying on parser precedence. Bundled example values are
synthetic, not sourced company observations or current market assumptions.

The existing `model_shape: equity` adaptation treats `base_revenue` as after-tax earnings.
Every explicit and terminal margin must equal 1, every explicit and terminal tax rate must
equal 0, and `net_debt` must equal 0. A rate buildup must use equity weight 1 and debt weight 0.
These checks prevent applying firm-side transformations to an equity stream; they cannot
verify that a supplied scalar discount rate is actually a sourced cost of equity.

Optional DCF sensitivity/story/reverse calculations cannot discard a valid base valuation.
Expected model/numeric failures produce a named `gaps` entry in the complete result and tool
envelope; unavailable grids are null and reverse failures have `solved: false` plus `reason`.
The CLI prints those gaps as well. Invalid base inputs still reject the valuation.

Discovery must not bypass a required screen: a failed fundamental gate or unresolved named
universe produces no shortlist. A successful degraded universe retains its source gaps. Invalid
ranking/provider/limit inputs refuse before fetching; one symbol's price-loader exception leaves
other symbols usable with a labelled gap. A trade workflow cannot substitute shared cached
survivors or momentum for a failed required fundamental gate.

Stock-scan evidence carries `price_as_of`, `price_source` and `price_fetched_at` per candidate.
Top-level `as_of` is the common actual price date (null when unavailable); `generated_on` is the
run date. Source price gaps survive ranking. Invalid/nonpositive/nonfinite closes, duplicate or
future dates are rejected. Production histories are sorted by date. Ranking excludes differing
endpoints and mismatched return-window sessions; relative context validates each comparison
window independently, so differing total history lengths are permitted when recent dates match.

Stock-scan `out` is a filename/prefix hint: returned `report_path` is content-addressed JSON, using
shared atomic evidence publication. Consumers must use the returned path, not reconstruct the
old mutable `stock-scan.json` filename. A persistence failure preserves the inline result with a gap.

Sector RS uses the same `prices.close_history` adapter as stock scans. Source gaps are retained,
and production sector/benchmark windows must share the same 127 closing-session dates for 6M
coverage. Invalid prices cannot form returns or classifications; missing/nonfinite RS is
unclassified. One failed sector does not abort the others. Valuation rankings require a successful
source response, positive current P/E and a finite percentile in [0,100]. As with stock scans,
`as_of` describes available price evidence and `generated_on` is the run date; undated valuation
responses do not acquire a fabricated observation date.

Alert mutations serialize complete read/modify/write transactions across threads and processes.
Writes replace a completed temporary YAML file atomically. IDs include a UUID; alerts without
explicit dedup keys never overwrite each other, and completed history is retained when a new
alert uses the same key. Dedup refresh includes snoozed records and preserves their snooze state;
a key cannot change subject or kind. Evaluation reloads current persisted state before firing,
so stale snapshots cannot resurrect dismissed or currently snoozed alerts. Invalid IDs, dates,
severities, statuses and metric thresholds refuse with gaps through manage_alerts.

Alert reads validate each YAML record independently, including identity/filename agreement,
subject, action, trigger shape, status, dates and log type. Invalid records remain on disk and are
excluded with a named gap; one record cannot hide the rest of the inbox. `load_all(gaps)` and
`load_open(subject, gaps)` optionally collect those gaps; direct calls without a collector emit a
warning. `manage_alerts` returns them in its envelope. Exactly one trigger type is required, and
null dates cannot become today's date. Expired unswept records do not absorb dedup refreshes.

Daily-brief ownership and performance figures come from personal sources; decision CMP, daily
moves and alert observations come only from approved market sources. Completed-close alerts require
a verified completed-session candle, not an intraday quote. A price-level event does not establish
an execution or close a position. Time-stop labels use the matched trade/strategy rule, never an
invented universal expiry. Incomplete alert inbox gaps remain visible.

`finance.telegram` owns text and report-document delivery through transport.request. User-authorized
brief sends use `bin/send-telegram.sh --text-file <path>` and the shared secrets loader. Tokens and
text are kept out of process arguments, private URLs do not redirect, and uncertain sends are not
retried automatically. Missing credentials or a rejected message leave local reports intact.

Insurance IRR calculations require a finite numeric cash-flow sequence containing both
inflows and outflows, finite bounds satisfying `-1 < lo < hi`, and positive tolerance.
Empty, zero-only and one-sided flows have no solvable IRR; they never return an endpoint
rate. The solver supports exactly one cash-flow sign change; multiple sign changes are
withheld because a single IRR may be ambiguous. Bisection uses scale-independent sign
evaluation and absolute rate-interval tolerance. Unbracketed or unconverged flows return
no supported solution. Invalid inputs and arithmetic failures return labelled gaps from
`run_insurance_math`. Continuation premiums are modelled at t0 through
`remaining_premiums-1`, with the surrender opportunity cost also at t0.

Insurance arithmetic rejects negative supplied amounts or ages rather than clamping them
to zero. Counts require nonnegative integers (booleans are not numeric inputs); NCB and IDV tolerance are fractions in [0,1].
The public adapter rejects non-finite computed outputs. A continuation calculation with
no supported IRR returns `ok:false` with a gap while preserving its cash-flow evidence.
These numeric guarantees do not validate the insurance-sizing assumptions themselves.

Term-cover expense runway requires explicit `annual_expenses` when
`years_to_independence > 0`. Missing expenses no longer default to a percentage of income.
An explicit zero is retained; with no runway requested, missing expenses remain null in
the breakdown. Callers must surface a missing-input gap rather than silently removing
the support horizon.

Vehicle IDV checks return `expected_idv_low:null`, `expected_idv_high:null`, `idv_ok:null`
and `idv_gap` for age >5 years or `model_discontinued:true`. The gap also appears in the
outer envelope; `ok:true` can still carry the independently computed NCB result. Consumers
must distinguish unknown IDV from a passing check. Exactly five years remains in the
schedule. `idv_tolerance` is a screening assumption, not a policy rule. Source and scope:
`skills/insurance-advisor/references/vehicle.md`.

Health sizing now accepts explicit INR scenario inputs: `base_target`, `total_target`,
`deductible`, `personal_cover`, `employer_cover`, all required. Demographic inputs and the
city/age increments, fixed catastrophic target and half-weight employer rule are removed.
Old demographic-only calls return a labelled input gap; callers must gather and justify
the scenario rather than translate demographics into hidden defaults.

`HealthNeed` echoes those five inputs and returns `base_gap=max(base_target-personal_cover,0)`,
`top_up_target=total_target-deductible`, `deductible_gap=max(deductible-personal_cover,0)`,
and `planned_deductible_gap=max(deductible-base_target,0)`. It requires
`0 < base_target <= total_target` and `0 <= deductible <= total_target`.
The old `base_recommended`, `effective_existing`, `top_up_recommended`, `gap`, `structure`
and `breakdown` fields are replaced by these explicit fields. Producer: insurance_math;
consumers: personal MCP description, insurance workflow/reference, CLI example and tests.
These are nominal scenario calculations, not claims adjudication or proof of sufficiency.

Term-cover inputs are now all explicit: `annual_income`, `income_multiple`,
`outstanding_loans`, `education_corpus`, `annual_expenses`, `years_to_independence`,
`existing_corpus`, and `existing_cover`. Omission returns an input gap; no 12× multiplier
or absent-liability/cover assumption is supplied by the engine. `annual_expenses:null`
is allowed only when the support horizon is zero. Other numeric inputs require finite
nonnegative values (and a positive multiple). The existing result shape is unchanged;
it describes the supplied scenario, not an endorsed universal coverage formula.

The insurance CLI rejects malformed/non-object JSON, duplicate keys and non-finite
JSON numbers as usage errors (exit 2, stderr, no calculation). Valid inputs still delegate
to the shared calculator; a computed gap returns exit 1 and its JSON envelope.

`marginal_irr_continue` no longer assumes a 7% benchmark. With omitted/null `hurdle_rate`,
a supported IRR and cash flows remain available, `hurdle_rate` and `beats_hurdle` are null,
and the envelope names the unavailable comparison. An explicit finite hurdle above -1
retains the comparison. A comparison outcome alone does not decide policy surrender.

Missing `claim_free_years` or `quoted_ncb` now leaves the vehicle `ncb_ok:null` with
`ncb_gap`, also propagated to the envelope. The IDV check remains independently available.
A supplied history can still yield `expected_ncb`; an omitted history cannot default to
zero. Explicit zero history and zero quoted bonus remain valid numeric inputs.


### Rolling-return endpoint coverage

Rolling windows use the first observation on or after `years × 365.25` calendar days,
provided it is no more than seven calendar days late. This is an explicit weekend/holiday
tolerance, not an exchange-calendar guarantee. Later observations are excluded; sparse
history must not turn a multi-year return into a nominal one-year observation. No eligible
windows means null rolling statistics, zero `n_windows`, and unknown return confidence,
even when the first-to-last history span is long. Shortlist flags expose missing coverage.
A category scan requires at least one eligible rolling window before ranking; age metadata
and other score components cannot substitute for the requested return coverage. NAV-stage
rejection retains the count that passed the earlier screening gates. Cross-series comparisons
must align endpoint calendars as well as starts.


### Document reporting-period selection

Annual-report label ordering uses the explicitly named reporting year, or the ending year
of a one-year fiscal range, rather than a later incidental filing date. Labels with multiple
unresolved years fall back with a recency gap instead of selecting the largest year. Label
ordering is index metadata, not verification of the period printed inside the document.


Look-through aggregation scales weighted arithmetic and harmonic calculations to avoid
intermediate overflow on finite inputs. Coverage alone cannot authorize publication: a
missing/nonfinite computed value is withheld with its actual coverage and a numeric gap.


RSI values preserve TA-Lib's reference output, including its flat-series convention.
A flat trailing window does not reset Wilder's earlier smoothed gains/losses to a
synthetic neutral value. Strategies previously validated with the removed RSI=50
override need revalidation if their rules depend on RSI; no strategy is reactivated automatically.
