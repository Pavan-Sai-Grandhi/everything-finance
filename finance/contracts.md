# Data contracts — the handoffs that make everything-finance one system

Skills pass structured artifacts to each other; this file is the **single description of those contracts**, so
editing one side of a handoff shows you the other. Change a field name or meaning here and change it in every
named producer and consumer. Two dependency kinds: **artifacts** (files one skill writes and another reads) and
**shared code** (`finance/` modules many callers import).

---

## The data layer: one door, one transport

**`finance/mcp/{market,company,funds,personal}.py` — the four servers.** The only door to decision data: 30
tools over the seven finalized sources (CLAUDE.md's source table) plus their compute engines, each delegating
to the matching `sources/` or `compute/` module and returning the shared **envelope** `{ok, source, fetched_at,
data, gaps}`. No name appears on two servers.

| server | tools |
|---|---|
| `finance-market` | `get_quote` `get_history` `run_technical_screen` `get_indices` `get_index_valuation_history` `get_breadth` `get_flows` `get_macro` `get_market_context` `run_strategy_screen` `run_backtest` `check_trade` `manage_alerts` `get_prior_run` |
| `finance-company` | `get_company_fundamentals` `get_documents` `run_fundamental_screen` `get_stock_ratios` `get_news` `get_filings` `get_shareholding` `get_corporate_actions` `run_dcf` |
| `finance-funds` | `resolve_fund` `screen_funds` `get_fund_holdings` `get_nav_history` `get_fund_scan` `get_fund_lookthrough` |
| `finance-personal` | `run_insurance_math` |

**Layering rule:** anything that fetches, or computes over fetched data, is a **tool** — leaving a skill's
`scripts/` pure compute over user-supplied files. Bulk lists (`candles`, `positions`, `navs`, `items`,
`funds`) **spill to disk**: the tool writes the full list to cache and returns `data[<key>]` truncated plus
`data[<key>_total]` and `data[<key>_path]`. Documents are *only* ever a path (*Artifact: document cache*).

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
`funds/<SCHEME>/<date>/`, skill-first singletons like `daily-brief/<date>.md`), **durable state**
(`state/{strategies,trades,alerts,sectors}/`, `state/watchlist.json`), **disposable** (`cache/`, `tmp/`);
helpers create dirs on demand. **`latest_prior(skill, subject, before=None)`** / **tool `get_prior_run`**
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
registered once. `ta.load_ohlcv(symbol, years, cache_dir)` is the shared yfinance loader (cache key
`<symbol>_<years>y.csv`) — backtest and live screen share one cache. TA-Lib needs the native lib (`brew install
ta-lib`), bootstrapped by `ta._need_talib()`. `test_ta.py`.

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
| `screen.py` | `run_strategy_screen` | spec → shortlist with entry/stop/target/qty per candidate |
| `backtest.py` | `run_backtest` | spec → historical expectancy, profit factor, drawdown vs buy-and-hold |
| `trade_check.py` | `check_trade` | a trade-idea artifact + live price → verdict, `unrealized_R`, exit numbers |
| `fund_scan.py` | `get_fund_scan` | a whole SEBI sub-category → gated, scored shortlist (rolling-return math from `rolling.py`) |
| `lookthrough.py` | `get_fund_lookthrough` | complete holdings + per-stock ratios → weighted portfolio valuation, cap tilt, concentration |
| `rolling.py` | *(internal to `fund_scan`)* | rolling returns, drawdown, risk-adjusted ratios from a NAV series |
| `dcf.py` + `relval.py` | `run_dcf` | sourced inputs → intrinsic value/share (+ optional grids) and the relative-multiples read, one answer; full JSON spilled to `stocks/<TICKER>/<date>/dcf.json` |
| `alerts.py` | `manage_alerts` | the alert inbox: list / add / dismiss / snooze / sweep (see *Artifact: alert*) |
| `insurance_math.py` | `run_insurance_math` | user-supplied figures → term cover need, health sum insured, IDV/NCB sanity, marginal IRR of continuing a policy |

`test_{context,screen,backtest,trade_check,fund_scan,lookthrough,rolling,dcf,relval,insurance_math,alerts}.py`;
`backtest.py` from both sides — spec interpretation via `compute/strategy.py` in `test_screen.py`, and the
Backtesting.py wiring (fill timing, cost, stop/target precedence, time-stop) in `test_backtest.py`.

### `finance/sources/filings.py` — exchange-filing fetch + materiality
Consumers: `get_filings` / `get_shareholding` / `get_corporate_actions`, read by `filings-watch`,
`daily-brief`, `news-scan`. `classify_materiality(text) -> (tier, emoji, reason)`, `tier ∈ {act-on, monitor,
routine}` (🔴/🟡/⚪). `summarize(symbol, days, fresh=False)` → envelope `data:{symbol, days, date,
material_count, act_on:[…], monitor:[…], routine_count, items:[…], corporate_actions:[…]}`. **Primary key is
the NSE symbol** — BSE-only is a labelled gap. Also `shareholding(symbol, quarters)` → `data:{symbol,
quarters:[{quarter, promoter_pct, public_pct, employee_trusts_pct, filed_on, xbrl}], pledge:[…]}` and
`corporate_actions(symbol)` → `data:{symbol, corporate_actions:[…]}`. **An empty `pledge` list is a labelled
gap meaning UNKNOWN, never "no pledge".** The announcements fetch re-checks the symbol client-side (the endpoint
has returned the whole market when its filter is not honoured); `ok:false` + `gap` means "unknown", not "nothing
filed". `test_filings.py` (+ `--selftest`).

### `finance/sources/prices.py` — price fetch (live + history + reconcile)
Consumers: `get_quote` / `get_history` / `run_technical_screen`, plus `compute/{screen,trade_check,context}.py`
and `sources/market.py`. Two truths kept separate: the **TradingView scanner** (public India scan, **no auth**)
is live/screening truth; **yfinance** is EOD-history truth. Envelope forms:
- `quote(symbol)` → `data:{symbol, date, name, close, change, change_abs, volume, market_cap_basic, exchange}`.
- `history(symbol, period="1y", adjusted=False)` → `data:{symbol, period, bars, candles:[{date,open,high,low,close,volume}]}`. Index tickers (`^NSEI`, `^CNXIT`) pass through, equities get `.NS`; `adjusted=False` keeps the raw close for reconcile, warmup callers pass `adjusted=True`.
- `history_df(symbol, period="1y", adjusted=True)` → `(pandas OHLCV frame, gaps)` — fed straight to `ta.add_indicators`.
- `screen(filters, columns=None, limit=50)` → `data:{filters, count, candidates:[…], rows:[…]}`.
- `reconcile(symbol, tolerance=0.01)` → `data:{symbol, tv_close, yf_close, divergence_pct, tolerance, agree}`; a divergence beyond tolerance is a `gap`.
**No indicators computed here** — callers pass `candles` to `ta.add_indicators`, so a screen and its backtest
share one indicator-of-record; no TV indicator ingestion or library. `test_prices.py` (offline parser + reconcile fixtures).

### `finance/sources/news.py` — company news (Google News RSS)
Consumer: `get_news`, read by `news-scan`, `deep-analysis` (news leg), `daily-brief`. `fetch(company, ticker,
days=60)` reads Google News RSS (the single source) → envelope `data:{company, ticker, days, count,
items:[{date, title, url, source, origin, kind, tag, publisher_tier}], noise_filtered, established_count}`.
Each item is **dated** (ISO or `null`), **deduped**, **classified** `kind ∈ {company, sector, noise}`, **tagged**
`tag ∈ {fact, narrative}`, and carries `publisher_tier ∈ {established, aggregator, unknown}` (never dropped —
weigh a single-sourced `aggregator` claim accordingly). **Noise is filtered from the default `items` view**
(pass `include_noise` to keep it). A block returns `ok:false` + labelled `gap`, never an empty crash.
`test_news.py` (offline parser/classifier/ladder fixtures).

### `finance/sources/tickertape.py` — the one Tickertape client
Consumers: `sources/fundamentals.py`, `sources/funds.py`. Holds the `tickertape.in` Referer every path 403s
without; `resolve_sid(symbol)` → `({sid, ticker, name, sector, slug}, gap)`, the only NSE-symbol→Tickertape-sid
map (sid differs from ticker — REC is `RECLTD`/`RECM`). Only exact ticker equality is accepted (a near-miss
misattributes financials). Cached 90 days.

### `finance/sources/fundamentals.py` — Tickertape financials + the screener.in document index
Consumers: `get_company_fundamentals` / `run_fundamental_screen`, read by `financial-analysis`,
`valuation-analysis`, and `find-trade` / `strategy-manager` (fundamental cut). Envelope forms:
- `fetch(symbol, sections=None)` → `data:{symbol, name, sid, ratios:{name:value}, pnl_10y:{columns,period_kinds,rows}, balance_sheet_10y:{…}, cash_flow_10y:{…}, quarters:{…}, shareholding:{columns,rows}, peers:[{symbol,name,sid,ttm_pe,pb}], documents:{annual_reports:[{label,url}], concalls:[{label,url}]}}`. `period_kinds` parallels `columns` (`FY`/`TTM`/`interim`). Each peer row carries its own **trailing** multiples from the same response, so the relative read needs no per-peer call; an unpublished multiple is `None`. `sections` narrows both answer and **work** (only those endpoints are called — what keeps `get_documents` to one screener fetch); a narrowed read does not populate the day cache, only a full one does.
- `screen(query, limit=1000)` → `data:{query, count, candidates:[…]}`, biggest market cap first. `query` is `FIELD >/< VALUE` clauses joined by `AND` over Tickertape's screener field names; `>=`/`<=` and an unresolvable name **refuse the whole query** (a half-resolved query returns companies that never passed the cut).

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

### `finance/sources/documents.py` — primary documents as cached local text
Consumer: `get_documents` (envelope, cache layout, reading legs in *Artifact: document cache*).
`fetch(symbol, annual_reports=1, concalls=1, fresh=False)` → envelope. Takes the index from
`fundamentals.fetch(symbol, sections=["documents"])` (one screener fetch) and downloads each link via
`transport.request(url, dest=…)` (the one socket). Each section is newest-first by year (and quarter) parsed
from the label; a label with no parseable year falls back to list position + a labelled gap. Conversion is
`pdftotext -layout` for PDFs (keeps table column alignment) and an in-process strip for text/HTML;
`extracted_by` records which ran. A zero-char PDF (scanned image) and a missing `pdftotext` (`brew install
poppler`) are labelled gaps, never crashes. `test_documents.py`.

### `finance/sources/market.py` — market-wide fetch (indices, valuation history, breadth, flows, macro)
Consumers: `get_indices` / `get_index_valuation_history` / `get_breadth` / `get_flows` / `get_macro`, and
`compute/context.py`. **No skill reads this for a market view** — every skill reads the market-context artifact.
Envelope forms:
- `indices()` → `data.indices:{<CANONICAL NAME>:{last, pe, pb, dy, pct_change, pct_change_1y}}` for ~139 NSE indices in one call (NSE `allIndices`). `index_levels(names=None)` is the budgeted form (`None` = `BROAD_INDICES`; ~139 are too many inline).
- `index_snapshot(day)` / `valuation_history(index, years)` → month-end `{date, close, pe, pb, dy}` from NSE archive CSVs. **One fetch per sampled DATE serves every index**, cached permanently (what makes a 10y multi-index percentile affordable). `valuation_percentiles(index, years)` → ranks only `{index, years, samples, pe|pb|dy:{current, percentile, n}}`.
- `breadth(universe)` → `data.counts:{above_sma50, above_sma200, advancing, near_52w_high, near_52w_low}`, each `{count, of}`.
- `flows()` → `data.flows:{FII,DII}:{buy_cr, sell_cr, net_cr}`; `macro(period)` → `{last, chg_1m_pct, percentile_5y, as_of}` per series.
- `percentile(values, value)` — the one pure primitive; ranks, does not judge.
`SECTOR_YF` is the **single** NSE-sectoral yfinance ticker map (which sectors exist). Fetches only — no regime
label, stance or score. `test_market.py`.

### `finance/sources/funds.py` — mutual-fund fetch (identity, category screen, full holdings, NAV)
Consumers: `resolve_fund` / `screen_funds` / `get_fund_holdings` / `get_nav_history` / `get_stock_ratios`, plus
`compute/{fund_scan,lookthrough}.py`. Envelope forms:
- `resolve(name)` → `{scheme_code, isin, amfi_name, plan, mf_id, tickertape_name}`; AMFI `NAVAll.txt` is the scheme-code/ISIN authority (mfapi's search misses funds).
- `screen(subsector, option, min_aum)` → `data.funds:[{mf_id, name, aum, expRatio, ret1y/3y/5y, sharpe, sortino, alpha, stdDevAnn, percSmallcap/Midcap/Largecap, ageInMon, …}]`. Vendor `match` string filters are ignored, so filtering is client-side; `PREMIUM_FIELDS` are stripped (one gated field 403s the whole call).
- `holdings(mf_id)` → `data.positions:[{sid, ticker, name, weight, change3m, type}]` — the **complete** book (64-278 positions, 90-99% coverage), plus `equity_weight`, `sector_weights`, `allocation_history`. `sid` is the join key (differs from `ticker`).
- `stock_ratios(sid)` / `enrich(positions)` → per-holding `{pe, ttm_pe, pb, roe, market_cap_cr, cap_rank, cap_label, sector, …}`, threaded + cached. **`pe` is annualised, `ttm_pe` is TTM** — for a peer comparison against a company's own `Stock P/E` (TTM) use `ttm_pe` (else ~8% skew). **`cap_rank`/`cap_label` from `amfi_cap_list()`** — AMFI's half-yearly `AverageMarketCapitalization*.xlsx` (link resolved from the categorisation index), whose `Sr. No.` **is** the SEBI rank (`caps.py`), joined on NSE symbol (ISIN fallback). A symbol absent from the period gets `cap_rank: None` + gap, `cap_label` falls back to the provider label. The rest of the row is Tickertape's sid-joined ratios.
- `nav_history(code)` → `data.navs:[{date ISO, nav}]` oldest-first.
**Fund holdings never come from the IndMoney feed** — it caps at 20 rows, misreports coverage, can be months
stale. `test_funds.py`.

### `finance/compute/holdings.py` — holdings source-resolver + normalizer
Consumers: `daily-brief`, `trade-tracker`, and the personal-finance cluster (`wealth-manager`,
`portfolio-review`, `mf-analysis`). Turns whichever read source is connected into ONE canonical position shape
under a fixed precedence.
- **Envelope:** `resolve(…)` → `{ok, source, fetched_at, data:{positions:[…]}, gaps:[…]}`.
- **Canonical position:** `{ticker, qty, avg, ltp, pnl, xirr, broker, asset_class, invested, source, as_of}`.
  `xirr`/`broker`/`invested`/`asset_class` populate from **IndMoney**, `None` when only broker/portfolio data
  exists. `source` labels the winning source per position (`indmoney`, `kite`/`upstox`, `portfolio`).
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
**Producer:** `strategy-manager` (owns the lifecycle). **Consumers:** `find-trade` via `run_strategy_screen`,
`run_backtest` (writes back `expectancy_assumptions`), `trade-tracker` (`regime_required`). **Location:**
`artifacts/state/strategies/<name>.yml` (`paths.state_dir("strategies")`). **Schema:**
`strategy-manager/assets/strategy-spec.example.yml` (commented); seed drafts in `assets/seed-strategies/`.

Key blocks and who reads them:

| Block | Written by | Read by | Meaning |
|---|---|---|---|
| `status` | strategy-manager validate/optimize | find-trade, select | `draft`→not tradeable; `active`→eligible; `inactive`→retired |
| `regime_required` | generate | select_strategy.py, trade-tracker | conditions checked against the live **market-context** artifact at PICK time |
| `screening.fundamental` | generate | find-trade Stage 1 | `provider: tickertape` + `query` (Tickertape catalogue field names, `>`/`<` only) + `max_survivors` |
| `screening.technical` | generate | find-trade Stage 2 | `provider: tradingview` (+`tradingview_filters`) or `compute` (+`compute_filters` naming `ta` features) |
| `entry`/`exit`/`sizing` | generate | `run_strategy_screen`, `run_backtest` (both via `compute/strategy.py`) | `entry.signal` (machine trigger; else `compute_filters`); `exit`: stop (auto-floored at max(0.5·ATR, 1% price)) / target (`measured_move`\|`next_resistance`\|`none`) / min_rrr / time_stop / **`trail_atr`** (ATR trailing stop) / **`exit_signal`** (close-on-condition, entry grammar); %-risk |
| `expectancy_assumptions` | **`run_backtest`** results, written back by strategy-manager | strategy-manager validate, select_strategy.py | `{win_rate, expectancy_R, profit_factor, n_trades, validated_by}`. strategy-manager applies the activation gate — `active` only on `expectancy_R > 0.2` over ≥~30 trades; select_strategy.py uses `expectancy_R` to rank |
| `live_performance` | trade-tracker → optimize | select_strategy.py | realized edge; `expectancy_R` here is preferred over the backtest's when present |

**Invariant:** find-trade runs a spec **only** when `status: active` AND its
`regime_required` fits the live regime. It has no default — no fitting active spec ⇒ no trade.

## Artifact: market-context
**Producer:** `market-analysis` — calls `get_market_context` (`finance/compute/context.py`) and persists the
digest to `artifacts/market-analysis/YYYY-MM-DD.json` (`paths.report_path("market-analysis", ext="json")`);
a run that does not persist it breaks every consumer. **Consumer:** every other skill — none computes its own
market view. Read-only callers pass `mode="quick"`; direct invocation uses `deep`, which also attaches
`recent_readings` (regime-transition history, diffed from prior dated artifacts). The **persisted file** —
not a tool return — is what `select_strategy.py`, `get_fund_scan(market_context=…)` and the next run's
transition history read, so the day's artifact is the shared market-of-record.

`as_of` is the **last trading bar**, not the generation date — on a weekend the context is legitimately Friday's.

| Field | Meaning | Read by |
|---|---|---|
| `market_trend` | `up`\|`range`\|`down` (Nifty vs 50/200-EMA + slope) | select_strategy.py, trade-tracker, find-trade, daily-brief |
| `market_posture` | `risk_on`\|`neutral`\|`risk_off` — the sizing gate | find-trade (size), deep-analysis (portfolio-manager sizing), daily-brief, trade-tracker |
| `rationale` | one line explaining the posture | daily-brief (the net read) |
| `trend_detail.above_ema200` | Nifty vs 200-EMA | select_strategy.py (`nifty_above: ema200`) |
| `trend_detail.{close,ema50,ema200,ema50_rising,pct_from_52w_high}` | trend context | daily-brief, find-trade |
| `volatility.vix` | India VIX level | select_strategy.py (`vix_max`), find-trade sizing |
| `volatility.{percentile_1y,percentile_5y,band}` | where that VIX sits historically | deep-analysis sizing, daily-brief |
| `breadth.pct_sectors_above_ema50` | coarse 10-sector count | select_strategy.py (`breadth_min_pct`) — **name frozen** |
| `breadth.{pct_above_sma50,pct_above_sma200,pct_near_52w_high,pct_near_52w_low,universe}` | real stock-level participation over the top 500 | find-trade, daily-brief, sector-analysis |
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
**Producers:** `find-trade` (on confirmation), `trade-tracker` (capturing a position with no rationale).
**Consumers:** `trade-tracker` + `check_trade` (re-validate); `strategy-manager optimize`
(`aggregate_performance.py`) reads closed ideas' `result` block. **Location:**
`artifacts/state/trades/<SYMBOL>-<YYYY-MM-DD>.yml` (`paths.state_dir("trades")`; SYMBOL is the NSE symbol, no
`.NS`). **This file is the schema:**

```yaml
symbol: TESTCO                 # NSE trading symbol
exchange: NSE
source_skill: find-trade       # find-trade | trade-tracker
strategy: nifty500-momentum-swing   # link back to the spec — never null from find-trade
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

`status` lifecycle: `idea` → (broker fill) `open` → (exit) `closed`. On promotion `trade-tracker` adds
**`fill_avg`** + **`entry_date`** from broker order history (without overwriting planned `entry`), writes the
real `sizing.qty`, and appends a dated **`tracker_log`** each run. On close it writes a `result` block
`{exit_date, exit_reason ∈ EXIT_STOP|EXIT_THESIS|EXIT_TARGET|EXIT_TIME|MANUAL, exit_price, realized_R,
realized_pnl, holding_sessions}` — **what `strategy-manager optimize` aggregates**, so closing without it breaks
the learning loop. `check_trade` reads `plan, direction, thesis_invalidation, strategy, created`; it defers the
regime check to the skill.

## Artifact: document cache
**Producer:** `get_documents` (on `sources/documents.py`) → one `.txt` per document under
`paths.cache_dir("documents")`, addressed by a hash of the source URL. **Consumers:** `financial-analysis`,
`management-analysis`, `valuation-analysis` — every leg that cites a primary document. The envelope carries
**paths, never body text**: `data:{symbol, documents:[{kind ∈ annual_report|concall, label, url, publisher,
text_path, text_chars, text_lines, extracted_by, cached, outline}], documents_total, annual_reports_available,
concalls_available}`. A published report never changes at its URL, so the cache has **no expiry** (`fresh=True`
is the only re-download); a document that will not download/convert is a labelled gap, the others still come back.

`outline` is `{section_key: [{line, text}]}` — the notes a leg must cite, mapped to best-first candidate line
numbers in `text_path`. Keys: `auditors_report, emphasis_of_matter, auditor_remuneration, mdna,
directors_report, corporate_governance, related_party, contingent_liabilities, remuneration, tax_note, segment,
cash_flow, esop, shareholding, qna`. Ranked so the first is the section not its contents-page entry, capped at
four. **An absent key means the document has no such section** — the labelled gap for that check, not a reason
to grep. Built once at conversion and cached with the document.

An orchestrator calls `get_documents` once and hands each leg the `text_path`s, so several legs land on the same
bytes; a leg given no paths calls the tool itself and gets the same cached file. **Extraction only** — nothing
here summarises, scores or judges; every verdict belongs to the leg reading the text.

## Convention: leg digest (deep-analysis IO hygiene)
Every forked leg **writes its full report to its file** and **returns only a compact digest** — its
machine-readable top block plus the file `path`, never the body. Downstream agents receive **paths** and Read
what they need, so the orchestrator never re-carries six full reports. A lens leg is a **skill run inside a
profile agent** (`terminal-analyst`, `field-analyst`, `desk-analyst`): the profile carries no method — the
skill owns the block below, the profile returns it unchanged plus `path`. Debate roles are named agents owning
their own blocks.

| Producer | Block | Fields |
|---|---|---|
| `technical-analysis` | `technical-block` | `verdict`, `confidence`, `trend_stage`, `support`, `resistance`, `bull_invalidated_below`, `bear_invalidated_above`, `axis: technical_structure` |
| `financial-analysis` | `financials-block` | `verdict`, `confidence`, `varsity_score` (of 7), `roce`, `de`, `cfo_ebitda`, `rev_cagr_5y`, **`clean_eps`**, **`eps_adjustments`**, `flags`, `axis: growth_durability` |
| `management-analysis` | `management-block` | `integrity` (the hard gate), **`integrity_checks`** (all seven sub-checks, each PASS/FLAG/FAIL/NOT-CHECKED), `skill`, `overall_grade`, `confidence`, `axis: governance` |
| `valuation-analysis` | `valuation-block` | `combined_stance`, `dcf_mos`, `dcf_confidence`, **`terminal_weight`**, `pe`, **`pe_basis`**, **`eps_adjustments`**, `peg`, `peer_median_pe`, **`peers_priced`**, **`ev_ebitda`**, `relative_stance`, `axis: valuation` |
| `news-scan` | `news-block` | `sentiment_score` (−2…+2), `confidence`, `recurring_theme`, `next_event`, `axis: growth_durability` |
| `sector-analysis` | `sector-block` | `sector`, `rs_class`, `stance`, `confidence`, `focus_position` |
| `contest-researcher` | `contest-block` | `lean ∈ {bull, bear, genuinely split}`, `axis`, one-line `bull`, one-line `bear` |
| `bull-researcher` / `bear-researcher` | `debate-block` | `axis`, `claim`, `conceded`, `new_evidence` |
| `portfolio-manager` | `verdict-block` | `call`, `conviction`, **`value_stance`**, **`action_driver`**, `invalidation`, `review`, `integrity_gate`, `integrity_partial`, **`evidence`**, **`weakest_load_bearing_input`** |

An **integrity FAIL** in `management-block` overrides every other lens; an `integrity` of
`FLAG` is a live concern short of disqualifying, and `PASS (partial, k of 7)` is uncertainty; neither is a cleared gate, and neither may reach `verdict-block` as `PASS`.

`deep-analysis/scripts/escalation.py` reads the `debate-block`'s `axis` + `claim` + `conceded` +
`new_evidence` to decide the next round (`standard`/`deep`): it escalates when the sides still have something to
test — **different** axes (cross-examination) or the **same** axis with distinct unconceded claims (rebuttal). A
concession, an identical claim, `new_evidence: false` on both sides after round 1, or the round cap (standard 2,
deep 3) ends it. `axis` must come from `VALID_AXES` (`valuation, growth_durability, balance_sheet_risk,
governance, technical_structure`); anything else is a broken contract, not a converged debate. A `contest-block`
lean of `genuinely split` makes the synthesis suggest a re-run; it never auto-escalates.

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

## Artifact: deep-analysis report
**Producer:** `deep-analysis` → `artifacts/stocks/<TICKER>/<date>/` (`paths.stock_dir`). **The deck is the
deliverable — no markdown report.** The run writes a self-contained deck (`deep-analysis.html` in the debate
modes, `fundamental-analysis.html` in `fundamentals`) plus its render input beside it (`<report>.report.json`,
see *Artifact: report projection*); each leg's raw report lands under `<report>/agents/<role>.md`. The two
report names are **distinct on purpose** — a `fundamentals` run and a full run on the same day must not
overwrite each other, so each mode builds on its own history. `get_prior_run(skill="deep-analysis" |
"fundamentals")` resolves to the **`.report.json`** (readable prose + every figure), not the HTML; `paths.py`
`_STOCK_ARTIFACT` is the authority on the names. **Consumer:** `trade-tracker` (reads the `.report.json` as a
rationale source when no trade-idea artifact exists).

Work papers present depend on **mode**: `quick` → `technical, financials, contest, verdict`; `standard`/`deep`
→ `technical, financials, news, sector, bull-r1…N, bear-r1…N, verdict`; `fundamentals` → `financials` only.
The Stop hook archives the `artifacts/tmp/staging/<TICKER>/` tree plus the staged deck + render input (`.report.html`
+ `.report.json`, or the `.fundamentals.` pair) and sends the brief from `coverage.brief`.

The valuation and management legs write **into the run-day folder**, not staging: `dcf.md` + `dcf.json` and
`management.md`. The valuation report is the **multi-method** read — intrinsic DCF range with a DCF-confidence
grade plus the relative multiples (P/E, PEG, peer-median, EV/EBITDA) in one combined stance, both cited without
re-derivation. The sector leg reads from the shared sector cache (*Artifact: sector cache*). Because every
artifact for a stock+run-day shares one folder, `get_prior_run(skill, TICKER)` finds the prior run of any leg
(deep-analysis, fundamentals, dcf, management, filings).

## Artifact: report projection — **render input only**
**Producer:** the `report-writer` → `artifacts/tmp/staging/<TICKER>.report.json` (in `fundamentals`,
`<TICKER>.fundamentals.report.json`) — its **only** output; no markdown. **Consumers:** `render_report.py`
renders it to `report.html`; `get_prior_run` reads it as the readable prior-run artifact — but **nothing reads
it back into a live decision.** No decision dependency may be wired on it: a figure a later agent must *act* on
comes from the sourced artifact (`dcf.json`, the leg digests), never here. The Stop hook
(`post-deep-analysis.sh`) triggers on this staged JSON, archives it and the rendered `report.html` into the
run-day folder as `<report>.report.json` / `<report>.html`, and reads `coverage.brief` for the Telegram send.

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
**not** the focus-stock overlay (computed fresh). **Freshness:** `paths.sector_cache_age_days(sector)` `>30` or
`None` ⇒ stale ⇒ refresh + a `sector_refresh_due` alert (`dedup_key: sector-refresh-<sector>`, due +30d). Dated
trail under `sector-analysis/<date>/`.

## Artifact: alert
**Producers:** `trade-tracker` (`price_cross`/`time_stop`/`regime_change`), `filings-watch` (`filing_act_on`),
`strategy-manager` (`revalidate_due`), `deep-analysis` (`reanalyze_due` + `price_cross` + `opportunity`),
`find-trade` (`price_cross` + `opportunity`), `market-analysis` (`regime_change`), `portfolio-review`
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
overrides). The **same tokenizer** keys lookup and the `--learn` write. Missing/corrupt map ⇒ taxonomy-only,
then rebuild — never a crash. `test_categorize.py`.

## Convention: cashflow-leg digest (budget-tracker `quick`)
**Producer:** `budget-tracker` `quick`. **Consumer:** `wealth-manager` — the cheap cashflow read (same digest
hygiene as the deep-analysis agents). `quick` writes **no HTML** and no transaction detail; it returns only:

```
<!-- cashflow-block
savings_rate: <pct>            # (investments + leftout) / total inflow
buckets: { Essential:{actual_pct,target,status}, Lifestyle:{...}, EMIs:{...}, Investments:{...} }
biggest_leak: <category> ₹<amount>
recurring_monthly: ₹<committed recurring/month>   # scripts/recurring.py total (dormant excluded)
monthly_outflow: ₹<total spend/month>             # wealth-manager's emergency-fund runway denominator
target_source: workbook | framework
gaps: [ ... ]                 # "UNCATEGORIZED ₹X across N txns", "no prior months", ...
month: <YYYY-MM>
-->
```

`target_source` names whether the bands came from the workbook or framework percentages (labelled, never
silently defaulted). Transaction-level data stays in the artifact.

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
An un-sizable line is a labelled gap, never a fabricated sum-assured or need.

## Artifact: net-worth spine + financial-health scorecard (wealth-manager)
**Producer:** `compute/wealth.py` (deterministic engine). **Consumer:** the `wealth-manager` orchestrator, whose
artifact is `artifacts/wealth/YYYY-MM-DD.md` (`paths.report_path("wealth")`) plus a rendered deck. The engine
reads a **picture JSON** — raw IndMoney `networth_snapshot` +
`networth_allocation_breakdown`, the `compute/holdings.py` positions envelope, the three leg digests above, and
an optional `profile` (age/dependents/monthly_expenses) — and owns every number.

- **Net-worth spine** (`build_spine`): `{ total_networth, as_of, allocation:{<bucket>:{label,value,pct}},
  liquid, equity_share_pct, holdings_xirr:{count,avg (value-weighted),best,worst}, source, coverage:
  complete|tradeable-only, gaps:[…] }`. Allocation precedence: IndMoney breakdown (sees every class)
  → else aggregate tradeable positions by class (labelled `tradeable-only`). Liquid = cash + FDs only;
  equity share = equity + funds + US equity. Buckets are the fixed `canonical_class` set (equity,
  mutual_funds, us_equity, debt, fd, epf, real_estate, gold, cash, insurance, crypto, other).
- **Cross-domain** (`emergency_fund` / `protection_read` / `risk_posture`): emergency-fund months of
  runway (liquid ÷ monthly expenses vs a 3–6 month target); protection-vs-net-worth status; risk
  posture (equity share vs an age band, **gated by** the emergency-fund + protection state — a weak
  foundation forces `fix-foundation-first` whatever the share).
- **Scorecard** (`build_scorecard`): `{ domains:{net_worth,investments,protection,cashflow,
  emergency_fund:{status,line}}, overall, actions:[{priority,domain,text,next_step,run}] }`. Status ∈
  strong|adequate|weak|critical|not_assessed; `overall` = worst *assessed* domain (an absent leg is a
  gap, never sets overall). Actions are ordered **across** domains by the health stack
  (emergency-fund/protection before fresh equity), max 5, each naming the spoke to run for depth.
- `--snapshot` returns spine + cross-domain flags only (no legs, no scorecard). Deterministic and
  offline; covered by `finance/tests/test_wealth.py`.
