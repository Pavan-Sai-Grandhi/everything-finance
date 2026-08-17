# Data contracts — the handoffs that make everything-finance one system

The skills pass structured artifacts to each other. This file is the **single description
of those contracts**, so that editing one side of a handoff shows you the other. Change a
field name or meaning here and you must change it in every named producer and consumer.

Two kinds of shared dependency: **artifacts** (files written by one skill, read by another)
and **shared code** (`finance/` modules imported by several callers).

---

## The data layer: one door, one transport

**`finance/mcp/{market,company,funds}.py` — the three servers.** The only door to decision
data. 25 tools over the seven finalized sources (`docs/data-sources.md`), each delegating to
the matching `finance/sources/` or `finance/compute/` module and returning the shared
**envelope** `{ok, source, fetched_at, data, gaps}`. No name appears on two servers.

| server | tools |
|---|---|
| `finance-market` | `get_quote` `get_history` `run_technical_screen` `get_indices` `get_index_valuation_history` `get_breadth` `get_flows` `get_macro` `get_market_context` `run_strategy_screen` `run_backtest` `check_trade` |
| `finance-company` | `get_company_fundamentals` `run_fundamental_screen` `get_stock_ratios` `get_news` `get_filings` `get_shareholding` `get_corporate_actions` |
| `finance-funds` | `resolve_fund` `screen_funds` `get_fund_holdings` `get_nav_history` `get_fund_scan` `get_fund_lookthrough` |

The layering rule: **anything that fetches, or that computes over fetched data, is a tool.**
A skill's `scripts/` holds only pure compute over user-supplied files (statements, policy
figures, a hand-typed book), so it never needs the network. The `mcp/` layer is declaration
and delegation only — a tool body is one call into the library — so there is one
implementation of every rule, not one per entry point.

Bulk lists (`candles`, `positions`, `navs`, `items`, `funds`) are **spilled to disk**: the
tool writes the full list to the cache tier and returns `data[<key>]` truncated plus
`data[<key>_total]` and `data[<key>_path]`. Read the file for the rest; never re-call a
tool to page through data it already wrote.

**`finance/spine.py` — the primitives every fetcher shares.** `envelope(ok, source, data,
gaps)` builds the one envelope shape; `f(value)` coerces to float-or-`None`; `first(row,
*keys, default=None)` picks the first present key from a vendor row; `norm_symbol(value)` and
`today()` normalize the two universal keys; `read_cache(path, fresh, stamp_key="date",
max_age_days=0)` / `write_cache(path, env, stamp_key="date")` are the day-stamped disk cache.
Imported by every source and compute module and by the servers — one definition, so envelopes
and cache staleness cannot diverge. Covered by `finance/tests/test_spine.py`.

**`finance/transport.py` — the one function that touches the network.** `request(url, ...) ->
(body, gap)` and `json_request(...) -> (parsed, gap)`, never raising; `bootstrap()` +
`jar_path()` for cookie-gated hosts; and **`nse_json(url, referer, headers=None)`**, the
cookie-bootstrapped NSE GET shared by `sources/market.py` and `sources/filings.py`. curl-based,
because nseindia.com 403s urllib on the TLS/HTTP2 fingerprint. Every fetcher calls it and no
module opens its own socket. Covered by `finance/tests/test_transport.py`.

**The personal/decision boundary.** `kite` / `upstox` / `indmoney` are separate, optional MCP
servers normalized through `finance/compute/holdings.py`. They supply **only** what the user
owns and what it is worth, never a decision input. See CLAUDE.md rule 3 and the measured
evidence in `docs/data-sources.md` → *Why the boundary is enforced*.

---

## Shared code: `finance/`

### `finance/deps.py` — lazy third-party imports
`need(mod, pip_name=None)` imports a module, pip-installing it (PEP 668 override) on first
miss; `load_yaml(path)` parses YAML via `need`. Skill scripts are run directly rather than
installed, so a missing dependency self-heals instead of tracebacking. Consumers:
`compute/trade_check.py`, `strategy-manager/scripts/{select_strategy,aggregate_performance}.py`,
`dcf-valuation/scripts/dcf.py`. Kept out of `compute/ta.py` so a caller needing only PyYAML
does not drag in pandas and the TA-Lib bootstrap.

### `finance/paths.py` — the artifact-path authority
Every caller asks this module where to read and write instead of hardcoding strings, so the
layout cannot drift between skills. Root is `$EVERYTHING_FINANCE_ARTIFACTS` or `./artifacts`
(cwd). Three lifecycle tiers:
**dated output** (`stocks/<TICKER>/<date>/`, `funds/<SCHEME>/<date>/`, and skill-first
singletons like `daily-brief/<date>.md`), **durable state** (`state/strategies/`,
`state/trades/`, `state/alerts/`, `state/sectors/`, `state/watchlist.json`), and
**disposable** (`cache/`, `tmp/`). Helpers:
`root, stock_dir, fund_dir, report_path, report_dir, backtest_dir, insurance_report_path,
state_dir, alerts_dir, watchlist_path, cache_dir, tmp_dir, sector_cache_path,
merchant_map_path` (all create dirs as needed), the key-normalizers
`ticker_key / scheme_key / sector_key`,
**`sector_cache_age_days(sector)`** (freshness of the monthly sector cache — `None` if
missing/undated), and **`latest_prior(skill, subject, before=None)`** — the prior-run lookup
that powers "refer the earlier run" (deep-analysis, dcf, management, filings, mf-analysis).
Covered by `finance/tests/test_paths.py`.

### `finance/compute/alerts.py` — the alert contract (see "Artifact: alert" below)

### `finance/compute/ta.py` — technical-analysis primitives
One definition of every indicator + candlestick pattern. Consumers: `compute/strategy.py`,
`compute/screen.py`, `compute/backtest.py`, `compute/context.py` (and the `technical-analyst`
agent through the tools that sit on them). Import as `from finance.compute import ta`.

**Contract — `ta.add_indicators(df)`** attaches these columns (the names every consumer
keys off): `ema20, ema50, sma200, ema50_rising, rsi14, vol10, atr14, hh20, ll20`.
Input is OHLCV (`Open/High/Low/Close/Volume`, DatetimeIndex). Numeric indicators delegate
to **TA-Lib** (EMA is SMA-seeded, ATR is Wilder — the reference forms). Changing a column
name here breaks the backtest signals and the screen's compute filters together — update
both. Everything else a spec can name is attached **on demand** by `ta.materialize(df, names)`:
parameterized indicator tokens `<kind><N>[_rising]` (`ema21, sma100, rsi9, atr20, adx14, hh50,
ll20, vol30, nr5`) resolved by `ta.feature_series` via regex, plus the registered patterns/signals
in **`ta.FEATURES`** (`inside_bar, outside_bar, engulfing, hammer, doji, coil_breakout, golden_cross,
macd_bullish_cross, rsi_oversold, bb_squeeze, volume_surge, new_high_20, ...`). `ta.is_feature(name)`
says whether a token resolves. A new period or standard signal needs no code change; only a genuinely
new primitive is registered in `FEATURES` once. `ta.load_ohlcv(symbol, years, cache_dir)` is the
shared yfinance loader (cache key `<symbol>_<years>y.csv`), so the backtest and the live screen hit
the same cache. TA-Lib's wheel needs the native lib (`brew install ta-lib`); `ta._need_talib()`
bootstraps it. Covered by `finance/tests/test_ta.py`.

### `finance/compute/strategy.py` — spec → signal engine
*How a spec + indicator columns becomes trades.* Consumers: `compute/screen.py` (live, latest
bar → `run_strategy_screen`) and `compute/backtest.py` (historical, every bar → `run_backtest`)
— both import it so they cannot disagree about what a strategy means. Key contract:
- `eval_series(expr, df) -> bool Series` — the ONE safe filter-language evaluator (NOT python
  eval). Grammar: `"<col>"`, `"A > B"` / `<`/`>=`/`<=`, `"A between X and Y"`, `"k * col"`,
  `"A or B"`; case-insensitive AND/OR/BETWEEN. `eval_filter(expr, row)` is the latest-bar wrapper.
- `entry_filters(spec)` — prefers `entry.signal` (machine trigger), falls back to
  `screening.technical.compute_filters`. `referenced_features(spec)` lists every `ta.is_feature`
  token a spec mentions (registered features + parameterized indicators) so the engine
  materializes exactly those. `entry_signal_series` / `exit_signal_series` are the series forms.
- `floor_stop`, `resolve_stop`, `target_from_spec` — the stop floor and target resolution
  shared by both callers.
- `build_signal(df, spec, capital)` — the live entry/stop/target/RRR/qty dict.
- `prepare_backtest_frame(df, spec)` + `build_bt_strategy(spec, capital, risk_pct)` — the spec
  as a Backtesting.py `Strategy` (next-open fills, pessimistic intrabar exits, time-stop, risk
  sizing). Engine: **Backtesting.py** (auto-pip). Covered by `finance/tests/test_screen.py`.

### `finance/compute/` — the fetch-driven compute behind the composite tools
Each module owns one interpreted answer and needs fetched data to produce it, so each is
reached through exactly one tool and never re-implemented in a skill:

| module | tool | produces |
|---|---|---|
| `context.py` | `get_market_context` | the market-of-record digest (see *Artifact: market-context*) |
| `screen.py` | `run_strategy_screen` | spec → shortlist with entry/stop/target/qty per candidate |
| `backtest.py` | `run_backtest` | spec → historical expectancy, profit factor, drawdown vs buy-and-hold |
| `trade_check.py` | `check_trade` | a trade-idea artifact + live price → verdict, `unrealized_R`, exit numbers |
| `fund_scan.py` | `get_fund_scan` | a whole SEBI sub-category → gated, scored shortlist (rolling-return math from `rolling.py`) |
| `lookthrough.py` | `get_fund_lookthrough` | complete holdings + per-stock ratios → weighted portfolio valuation, cap tilt, concentration |
| `rolling.py` | *(internal to `fund_scan`)* | rolling returns, drawdown, risk-adjusted ratios from a NAV series |

Covered by `finance/tests/test_{context,screen,trade_check,fund_scan,lookthrough,rolling}.py`.
`backtest.py` has no test file of its own — its spec interpretation is covered through
`compute/strategy.py` in `test_screen.py`; the Backtesting.py wiring is not.

### `finance/sources/filings.py` — exchange-filing fetch + materiality
Consumers: `get_filings` / `get_shareholding` / `get_corporate_actions`, read by
`filings-watch`, `daily-brief` and the `news-sentiment` agent. Key contract:
`classify_materiality(text) -> (tier, emoji, reason)` where `tier ∈ {act-on, monitor,
routine}` (emoji 🔴/🟡/⚪). `summarize(symbol, days, fresh=False)` returns the shared
**envelope**, where `data` is
`{symbol, days, date, material_count, act_on:[...], monitor:[...], routine_count, items:[...], corporate_actions:[...]}`.
**The primary key is the NSE symbol** — a BSE-only listing is a labelled gap.
Also exposed: `shareholding(symbol, quarters)` → `data:{symbol, quarters:[{quarter,
promoter_pct, public_pct, employee_trusts_pct, filed_on, xbrl}], pledge:[...]}` and
`corporate_actions(symbol)` → `data:{symbol, corporate_actions:[...]}`.
**An empty `pledge` list is a labelled gap meaning UNKNOWN, never "no pledge".** The
announcements fetch re-checks the symbol client-side, because the endpoint has been seen
returning the whole market when its symbol filter is not honoured. Each block names itself in
`gaps`; `ok:false` with a `gap` means "unknown", not "nothing filed". Covered by
`finance/tests/test_filings.py` (+ `--selftest`).

### `finance/sources/prices.py` — price fetch (live + history + reconcile)
Consumers: `get_quote` / `get_history` / `run_technical_screen`, plus `compute/screen.py`,
`compute/trade_check.py`, `compute/context.py` (index history) and `sources/market.py`
(breadth screen, macro series). Two truths kept separate: the **TradingView scanner** (public
India scan endpoint, **no auth**) is live/current/screening truth; **yfinance** is EOD-history
truth. Key contract — each returns the shared **envelope**:
- `quote(symbol)` → `data:{symbol, date, name, close, change, change_abs, volume, market_cap_basic, exchange}`.
- `history(symbol, period="1y", adjusted=False)` → `data:{symbol, period, bars, candles:[{date, open, high, low, close, volume}]}`. Index tickers (`^NSEI`, `^CNXIT`) pass through; equities get `.NS`. `adjusted=False` keeps the raw close for reconcile; warmup callers pass `adjusted=True`.
- `history_df(symbol, period="1y", adjusted=True)` → `(pandas OHLCV frame, gaps)` — the adapter the warmup callers feed straight to `ta.add_indicators` (the spine fetches, `ta.py` decides).
- `screen(filters, columns=None, limit=50)` → `data:{filters, count, candidates:[symbol,...], rows:[...]}`.
- `reconcile(symbol, tolerance=0.01)` → `data:{symbol, tv_close, yf_close, divergence_pct, tolerance, agree}`; a divergence beyond tolerance is a `gap`, not a silent pass.
**No indicators are computed here** — callers pass `candles` to `ta.add_indicators`, so a
screen and its backtest share one indicator-of-record. No TV indicator-value ingestion and
no TV-indicator library dependency. Covered by `finance/tests/test_prices.py` (offline parser +
reconcile-decision fixtures).

### `finance/sources/news.py` — company news (Google News RSS)
Consumer: `get_news`, read by the `news-sentiment` agent, `deep-analysis` (its news leg) and
`daily-brief` (headline context). Key contract: `fetch(company, ticker, days=60)` reads Google
News RSS — the single news source — and returns the shared **envelope**, where `data` is
`{company, ticker, days, count, items:[{date, title, url, source, origin, kind, tag, publisher_tier}], noise_filtered, established_count}`.
Each item is **dated** (ISO or explicit `null`), **deduped**, **classified** `kind ∈ {company,
sector, noise}`, **tagged** `tag ∈ {fact, narrative}`, and carries
`publisher_tier ∈ {established, aggregator, unknown}`. Tiering never drops an item; weigh a
single-sourced `aggregator` claim accordingly. **Noise is filtered from the default
`items` view** (pass `include_noise` to keep it). A block returns `ok:false` with a labelled
`gap`, never an empty crash. Covered by `finance/tests/test_news.py` (offline
parser/classifier/ladder fixtures).

### `finance/sources/fundamentals.py` — screener.in financials + fundamental screen
Consumers: `get_company_fundamentals` / `run_fundamental_screen`, read by the
`fundamentals-data` agent (which packs it for `deep-analysis` / `fundamental-analysis`) and by
`find-trade` / `strategy-manager` for a fundamental candidate cut. Key contract — each returns
the shared **envelope**:
- `fetch(symbol, sections=None)` reads the public consolidated company page **once** → `data:{symbol, ratios:{name:value}, pnl_10y:{columns,rows}, balance_sheet_10y:{columns,rows}, quarters:{columns,rows}, shareholding:{columns,rows}, peers:[{symbol,name}], documents:{annual_reports:[{label,url}], concalls:[{label,url}]}}`. Falls back to the standalone page with a labelled `gap`. `sections` narrows what the envelope carries; the fetch and cache are unaffected.
- `screen(query)` → `data:{query, count, candidates:[symbol,...]}` (the fundamental counterpart to `prices.screen()`).
**Tables/fields only — never raw page HTML lands in `data`.** The public page needs no auth;
`SCREENER_SESSION_ID`/`SCREENER_CSRF_TOKEN` are injected only for a login-walled screen, and
`is_logged_out(html)` catches screener's HTTP-200 Register page so an expired cookie reports
"session expired" rather than "no companies matched". Covered by
`finance/tests/test_fundamentals.py` (offline parser fixtures).

### `finance/sources/market.py` — market-wide fetch (indices, valuation history, breadth, flows, macro)
Consumers: `get_indices` / `get_index_valuation_history` / `get_breadth` / `get_flows` /
`get_macro`, and `compute/context.py`. **No skill reads this module for a market view** — every
skill reads the market-context artifact, so there is one market-of-record. Key contract — each
returns the shared **envelope**:
- `indices()` → `data.indices:{<CANONICAL NAME>:{last, pe, pb, dy, pct_change, pct_change_1y}}` for ~139 NSE indices in one call (NSE `allIndices`, cookie-bootstrapped curl). `index_levels(names=None)` is the context-budgeted form — `names=None` means `BROAD_INDICES`, because all ~139 are far too many to read inline.
- `index_snapshot(day)` / `valuation_history(index, years)` → month-end `{date, close, pe, pb, dy}` series from the NSE archive daily CSVs. **One fetch per sampled DATE serves every index**, and snapshots are cached permanently — which is what makes a 10-year, multi-index percentile affordable. `valuation_percentiles(index, years)` returns the ranks only (`{index, years, samples, pe|pb|dy:{current, percentile, n}}`) — where today sits is the decision; the series is a few hundred rows nobody reads.
- `breadth(universe)` → `data.counts:{above_sma50, above_sma200, advancing, near_52w_high, near_52w_low}`, each as `{count, of}` so the priced denominator travels with the number.
- `flows()` → `data.flows:{FII,DII}:{buy_cr, sell_cr, net_cr}`; `macro(period)` → `{last, chg_1m_pct, percentile_5y, as_of}` per series.
- `percentile(values, value)` — the one pure primitive here; it ranks, it does not judge.
`SECTOR_YF` is the **single** NSE-sectoral yfinance ticker map — the one answer to which
sectors exist. Fetches only: no regime label, no stance, no score. Covered by
`finance/tests/test_market.py` (offline fixtures).

### `finance/sources/funds.py` — mutual-fund fetch (identity, category screen, full holdings, NAV)
Consumers: `resolve_fund` / `screen_funds` / `get_fund_holdings` / `get_nav_history` /
`get_stock_ratios`, plus `compute/fund_scan.py` and `compute/lookthrough.py`. Envelope as above:
- `resolve(name)` → `{scheme_code, isin, amfi_name, plan, mf_id, tickertape_name}`; AMFI `NAVAll.txt` is the scheme-code/ISIN authority (mfapi's search misses funds outright).
- `screen(subsector, option, min_aum)` → `data.funds:[{mf_id, name, aum, expRatio, ret1y/3y/5y, sharpe, sortino, alpha, stdDevAnn, percSmallcap/Midcap/Largecap, ageInMon, …}]` — the category scanner. String filters in the vendor's `match` are silently ignored, so category filtering happens client-side; `PREMIUM_FIELDS` are stripped before the request because one gated field 403s the whole call.
- `holdings(mf_id)` → `data.positions:[{sid, ticker, name, weight, change3m, type}]` — the **complete** book (64-278 positions at 90-99% coverage), plus `equity_weight`, `sector_weights`, `allocation_history`. `sid` is the join key and genuinely differs from `ticker` (REC: ticker `RECLTD`, sid `RECM`).
- `stock_ratios(sid)` / `enrich(positions)` → per-holding `{pe, ttm_pe, pb, roe, market_cap_cr, cap_rank, cap_label, sector, …}`, threaded and cached. **`cap_rank` is the SEBI market-cap rank** (`SEBI_CAP_RANKS`: top 100 large, 101-250 mid, 251+ small) — the basis cap-tilt must use.
- `nav_history(code)` → `data.navs:[{date ISO, nav}]` oldest-first, strictly parsed.
**Fund holdings never come from the IndMoney MCP feed** — it caps at 20 rows, misreports its
own coverage, and can be months stale (`docs/data-sources.md` → *Why the boundary is
enforced*). Covered by `finance/tests/test_funds.py` (offline fixtures).

### `finance/compute/holdings.py` — holdings source-resolver + normalizer
Consumers: `daily-brief` and `trade-tracker` (live position state), and the personal-finance
cluster (`wealth-manager`, `portfolio-review`, `mf-analysis`). Turns whichever read source is
connected into ONE canonical position shape under a fixed precedence, so no consumer
re-implements normalization.

- **Envelope:** `resolve(...)` returns `{ok, source, fetched_at, data:{positions:[...]}, gaps:[...]}`.
- **Canonical position:** `{ticker, qty, avg, ltp, pnl, xirr, broker, asset_class, invested, source, as_of}`.
  `xirr`/`broker`/`invested`/`asset_class` populate from **IndMoney**; they are `None` when only
  broker/portfolio data exists. `source` labels the winning source per position (`indmoney`,
  `kite`/`upstox`, `portfolio`).
- **`normalize(payload, source)`** maps an IndMoney `networth_holdings` payload, a Kite/Upstox
  holdings+positions payload, or a hand-maintained positions block (the `watchlist.json`
  `positions` array or an equivalent list) to canonical positions. **Keeps all asset classes**
  (wealth-manager reuses this); consumers filter.
- **`resolve(prefer="indmoney", payloads={...})`** applies precedence **IndMoney → broker →
  portfolio**, sets `source` to whichever won, and notes empty/failed/absent sources in `gaps`.
  A normalize failure on one source falls through to the next with a labelled gap — never an abort.
- **`equity_only(positions)`** / **`mf_only(positions)`** — the two slices consumers want
  (broker / portfolio positions, whose `asset_class` is `None`, are equity by construction;
  IndMoney positions are kept unless their `asset_class` names another class).
- **Payload handoff (contract):** this module is pure compute over files and **never calls an
  MCP tool**. The calling **skill** invokes the personal tool (`mcp__indmoney__*` /
  `mcp__kite__*` / `mcp__upstox__*`), **writes the raw payload to a temp file** under
  `paths.tmp_dir("holdings")`, and passes the path
  (`--indmoney`/`--kite`/`--upstox`/`--portfolio`, plus `--equity-only`/`--mf-only`/`--prefer`).
  **Fills are never sourced here** — exact entry price+date come from broker order history
  only; IndMoney is never used to approximate an entry.
- Covered by `finance/tests/test_holdings.py` (offline fixtures for all three sources +
  precedence/gap combinations).

---

## Artifact: strategy spec
**Producer:** `strategy-manager` (owns the whole lifecycle).
**Consumers:** `find-trade` via `run_strategy_screen` (screening/entry/exit/sizing),
`run_backtest` (entry/exit/sizing → `strategy-manager` writes back `expectancy_assumptions`),
`trade-tracker` (`regime_required`).
**Location:** `artifacts/state/strategies/<name>.yml` (`paths.state_dir("strategies")`). **Schema:**
`strategy-manager/assets/strategy-spec.example.yml` (fully commented). Seed drafts:
`strategy-manager/assets/seed-strategies/`.

Key blocks and who reads them:

| Block | Written by | Read by | Meaning |
|---|---|---|---|
| `status` | strategy-manager validate/optimize | find-trade, backtest, select | `draft`→not tradeable; `active`→eligible; `inactive`→retired |
| `regime_required` | generate | select_strategy.py, trade-tracker | conditions checked against the live **market-context** artifact at PICK time |
| `screening.fundamental` | generate | find-trade Stage 1 | `provider: screener.in` + `query` + `max_survivors` |
| `screening.technical` | generate | find-trade Stage 2 | `provider: tradingview` (+`tradingview_filters`) or `compute` (+`compute_filters` naming `ta` features) |
| `entry`/`exit`/`sizing` | generate | `run_strategy_screen`, `run_backtest` (both via `compute/strategy.py`) | `entry.signal` (machine trigger; else `compute_filters`); `exit`: stop (auto-floored at max(0.5·ATR, 1% price)) / target (`measured_move`\|`next_resistance`\|`none`) / min_rrr / time_stop / **`trail_atr`** (ATR trailing stop) / **`exit_signal`** (close-on-condition, entry grammar); %-risk |
| `expectancy_assumptions` | **`run_backtest`** results, written back by strategy-manager | strategy-manager validate, select_strategy.py | `{win_rate, expectancy_R, profit_factor, n_trades, validated_by}`. strategy-manager applies the activation gate — `active` only on `expectancy_R > 0.2` over ≥~30 trades; select_strategy.py uses `expectancy_R` to rank |
| `live_performance` | trade-tracker → optimize | select_strategy.py | realized edge; `expectancy_R` here is preferred over the backtest's when present |

**Invariant:** find-trade runs a spec **only** when `status: active` AND its
`regime_required` fits the live regime. It has no default — no fitting active spec ⇒ no trade.

## Artifact: market-context
**Producer:** `market-analysis` — it calls `get_market_context` (`finance/compute/context.py`)
and persists the digest to `artifacts/market-analysis/YYYY-MM-DD.json`
(`paths.report_path("market-analysis", ext="json")`). A run that does not persist it breaks
every consumer below.
**Consumer:** every other skill — none computes its own market view. Callers that only need the
read ask for `mode="quick"`; `market-analysis` on direct invocation uses `deep`, which also
attaches `recent_readings` (the regime-transition history, diffed from prior dated artifacts).
It is the **persisted file**, not a tool return, that
`strategy-manager/scripts/select_strategy.py`, `get_fund_scan(market_context=…)` and the next
run's transition history read — so the day's artifact is the shared market-of-record and one
read of the tape serves every skill that day.

`as_of` is the **last trading bar**, not the generation date — on a weekend the context is
legitimately Friday's.

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

**Two naming rules that are load-bearing.** `market_trend`, `trend_detail.above_ema200`,
`volatility.vix` and `breadth.pct_sectors_above_ema50` are frozen spellings because
`select_strategy.py:regime_fit` gates on them — renaming one silently breaks every strategy
spec's `regime_required`. And the market posture is **`market_posture`**, never
`risk_posture`: that name means a *personal balance-sheet* posture in the wealth contract
(see Cross-domain, below), and the two collide the moment wealth-manager reads market context.

## Artifact: trade-idea
**Producer:** `find-trade` (on user confirmation), or `trade-tracker` (when it captures a
position with no prior rationale). **Consumers:** `trade-tracker` and `check_trade`
(re-validate the thesis); `strategy-manager optimize` (`aggregate_performance.py`) reads the
`result` block of closed ideas.
**Location:** `artifacts/state/trades/<SYMBOL>-<YYYY-MM-DD>.yml` (`paths.state_dir("trades")`;
SYMBOL is the NSE trading symbol, no `.NS`). **This file is the schema** — both producers point
here:

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

Lifecycle of `status`: `idea` → (broker fill matched) `open` → (exit) `closed`.
On promotion, `trade-tracker` adds **`fill_avg`** and **`entry_date`** from broker order
history without overwriting the planned `entry` (both are recorded), writes the real
`sizing.qty`, and appends a dated **`tracker_log`** note each run. On close it writes a
`result` block — `{exit_date, exit_reason ∈ EXIT_STOP|EXIT_THESIS|EXIT_TARGET|EXIT_TIME|MANUAL,
exit_price, realized_R, realized_pnl, holding_sessions}`. **That block is what
`strategy-manager optimize` aggregates**, so closing a trade without it breaks the learning
loop. `check_trade` reads `plan`, `direction`, `thesis_invalidation`, `strategy` and `created`;
it defers the regime check to the skill.

## Artifact: fundamentals data-pack
**Producer:** the `fundamentals-data` agent → `artifacts/tmp/staging/<TICKER>/fundamentals/data-pack.md`
— the single sourced fetch of one company's fundamentals for a run. **Consumers:** `financials-analyst`,
`management-analyst`, `valuation-analyst` (each Reads it; none re-fetches), so all three reason off the
same sourced numbers. **Fields:** a `depth:` frontmatter marker (`full` or `lite`); CMP (+ as-of); the
screener envelope (`ratios`, `pnl_10y`, `balance_sheet_10y`, `quarters`, `shareholding`, `peers`);
annual-report excerpts keyed by section (MD&A, segment note, auditor, RPT, contingent liabilities, cash
flow, revenue recognition) each with a page/section cite; management-quality signals (remuneration, RPT
detail, auditor fees & trend, board/KMP profiles, pledging, multi-year MD&A); concall takeaways (quarter
cited); and `Data gaps`. **`depth: lite`** (deep-analysis `quick` mode) carries **only** the screener
envelope + CMP — the annual-report sections, management signals, and concall are omitted and listed as
gaps; consumers label them rather than infer. **`depth: full`** (standard/deep, `/fundamental-analysis`)
carries everything. Facts only — no scoring/verdict. Archived under `deep-analysis/fundamentals/` by the Stop hook.

## Convention: agent digest (deep-analysis IO hygiene)
Every forked deep-analysis agent **writes its full report to its staged file** and **returns to
the orchestrator only a compact digest** — its machine-readable top block plus the file `path`,
never the body. The orchestrator and any downstream agent receive **paths** and Read what they
need in their own context, so the orchestrator never re-carries six full reports.

| Agent | Block | Fields |
|---|---|---|
| `technical-analyst` | `technical-block` | `verdict`, `confidence`, `trend_stage`, `support`, `resistance`, `bull_invalidated_below`, `bear_invalidated_above`, `axis: technical_structure` |
| `financials-analyst` | `financials-block` | `verdict`, `confidence`, `varsity_score`, `roce`, `de`, `cfo_ebitda`, `rev_cagr_5y`, `flags`, `axis: growth_durability` |
| `management-analyst` | `management-block` | `integrity` (the hard gate), `skill`, `overall_grade`, `confidence`, `axis: governance` |
| `valuation-analyst` | `valuation-block` | `combined_stance`, `dcf_mos`, `dcf_confidence`, **`terminal_weight`**, `pe`, `peg`, `peer_median_pe`, **`ev_ebitda`**, `relative_stance`, `axis: valuation` |
| `news-sentiment` | `news-block` | `sentiment_score` (−2…+2), `confidence`, `recurring_theme`, `next_event`, `axis: growth_durability` |
| `sector-analyst` | `sector-block` | `sector`, `rs_class`, `stance`, `confidence`, `focus_position` |
| `contest-researcher` | `contest-block` | `lean ∈ {bull, bear, genuinely split}`, `axis`, one-line `bull`, one-line `bear` |
| `bull-researcher` / `bear-researcher` | `debate-block` | `axis`, `claim`, `conceded`, `new_evidence` |
| `portfolio-manager` | `verdict-block` | `call`, `conviction`, `invalidation`, `review`, `integrity_gate` |

An **integrity FAIL** in `management-block` overrides every other lens. The `debate-block`'s
`axis` + `claim` + `conceded` are exactly what `deep-analysis/scripts/escalation.py` reads to
decide a round 2 — it escalates only when both sides' top points sit on the *same* axis from
`VALID_AXES` (`valuation`, `growth_durability`, `balance_sheet_risk`, `governance`,
`technical_structure`), with distinct claims and neither conceded. A `contest-block` lean of
`genuinely split` makes the synthesis suggest a re-run at `standard`/`deep`; it never
auto-escalates.

## Artifact: deep-analysis report
**Producer:** `deep-analysis` → `artifacts/stocks/<TICKER>/<date>/deep-analysis.md` (`paths.stock_dir`),
the synthesized report, with each forked agent's raw report archived beside it under
`artifacts/stocks/<TICKER>/<date>/deep-analysis/agents/<role>.md`. The work papers present depend on the
run's **depth mode** (recorded in the report): `quick` → `technical`, `financials`, `valuation`,
`contest`, `verdict`; `standard`/`deep` → `technical`, `financials`, `management`, `valuation`, `news`,
`sector`, `bull-r1…N`, `bear-r1…N`, `verdict` — plus the data-pack under `deep-analysis/fundamentals/`.
The Stop hook archives the whole `artifacts/tmp/staging/<TICKER>/` tree (and final report
`artifacts/tmp/staging/<TICKER>.md`), and sends the `## Telegram Brief` section. **Consumer:**
`trade-tracker` (as a rationale source when no trade-idea artifact exists). The valuation leg embeds a
**multi-method** read — intrinsic DCF range **with a DCF-confidence grade** plus the relative multiples
(P/E, PEG, peer-median, EV/EBITDA) reconciled into a combined stance — and the management leg
(standard/deep) embeds the `management-quality` grade; the DCF and management outputs are **also persisted
as discrete files** (`dcf.md`/`dcf.json` always, `management.md` when the leg ran) in the same
`stocks/<TICKER>/<date>/` folder. The sector leg embeds the `sector-analyst`
read, sourced from the shared sector cache (see *Artifact: sector cache*). Because every artifact for a
stock+run-day lives in one folder, `paths.latest_prior(skill, TICKER)` finds the prior run of any leg
(deep-analysis, dcf, management, filings) on a re-run.

## Artifact: sector cache
**Producers:** `sector-analysis` (canonical monthly refresher) and `deep-analysis` (inline refresh when
missing/stale). **Consumer:** `deep-analysis`'s sector leg. **Location:** `state/sectors/<slug>.md`
(`paths.sector_cache_path`) — durable, not dated; one current body per sector, overwritten on refresh.
**Fields:** frontmatter `generated: YYYY-MM-DD` + `rs_class:`; body = the sector-level read (RS vs Nifty,
cycle, KPI snapshot, tailwinds/headwinds, leaders/laggards, stance) — **not** the focus-stock overlay,
which is computed fresh. **Freshness:** `paths.sector_cache_age_days(sector)` — `> 30` or `None` ⇒ stale ⇒
refresh + a `sector_refresh_due` alert (`dedup_key: sector-refresh-<sector>`, due +30d). The dated trail
stays under `sector-analysis/<date>/`.

## Artifact: alert
**Producer:** many — `trade-tracker` (`price_cross`/`time_stop`/`regime_change`), `filings-watch`
(`filing_act_on`), `strategy-manager` (`revalidate_due`), `deep-analysis` (`reanalyze_due` +
`price_cross` invalidation + `opportunity`), `find-trade` (`price_cross` entry + `opportunity`),
`market-analysis` (`regime_change` on a posture change), `portfolio-review` (`rebalance_due`),
`mf-analysis` (`sip_due`), `sector-analysis` + `deep-analysis` (`sector_refresh_due`), and
`alert-manager` (manual).
**Consumer:** `daily-brief` (surfaces and recommends — never auto-runs); `alert-manager` curates.
**Owner of the schema/logic:** `finance/compute/alerts.py`. **Location:** one file per alert at
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

**Functions:** `create` (dedups on `dedup_key`), `load_open(subject=None)`, `evaluate_cheap(alerts,
market_data)` (fires `metric`/`due` triggers from data the caller already fetched; ignores
`{check}`), `set_status`, `snooze`, `sweep`. **Invariant:** alerts are only evaluated when a skill
runs (no cron); `daily-brief` and `alert-manager` never place an order or auto-run a `{check}` alert.
Covered by `finance/tests/test_alerts.py`.

## Artifact: watchlist
**Producer/consumer:** `daily-brief` (auto-adds *vetted* opportunities, recommends pruning; never
auto-removes). **Location:** `artifacts/state/watchlist.json` (`paths.watchlist_path()`). Shape:
`{"watchlist": [{ticker, added, source, note}], "positions": [{ticker, entry, sl, target, qty,
entry_date}]}`. The `positions` array is also the last rung of the holdings precedence in
`compute/holdings.py` (`--portfolio`).

## Artifact: budget merchant map
**Producer/consumer:** `budget-tracker` (`scripts/categorize.py`). **Location:**
`artifacts/budget/merchant-map.json` (`paths.merchant_map_path()`) — durable state, not dated,
co-located with the dated `budget/<YYYY-MM>.html` reports. **Shape:** a flat
`{ "<MERCHANT_TOKEN>": "<Category>" }` object, keyed by the normalized merchant token
`categorize.normalize_token` produces (uppercased, narration plumbing / masked card numbers /
`@handle` suffixes / short+numeric words stripped, first significant word) so UPI/POS/handle
variants of one merchant collapse to a single rule. **Category** is one of the reference.md
workbook categories (Groceries, Dine & Entertainment, EMIs, Investments, …). Resolution order in
`categorize.py`: **map → reference.md taxonomy → UNCATEGORIZED**; the map wins so a correction
overrides the taxonomy. The **same tokenizer** keys lookup and the `--learn` write, so a
correction resolves the merchant it was made against. Missing/corrupt map ⇒ taxonomy-only, then
rebuild — never a crash. Covered by `skills/budget-tracker/scripts/test_categorize.py`.

## Convention: cashflow-leg digest (budget-tracker `quick`)
**Producer:** `budget-tracker` in `quick` mode. **Consumer:** `wealth-manager` — the cheap cashflow
read, following the same digest hygiene as the deep-analysis agents (a compact block, not the
full render). `quick` writes **no HTML** and no transaction detail; it returns only:

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

`target_source` states whether the bands came from the user's workbook or the framework
percentages (graceful degradation — labelled, never silently defaulted). Transaction-level data
stays in the artifact, never in the digest.

## Convention: investments-leg digest (portfolio-review `quick`)
**Producer:** `portfolio-review` in `quick` mode. **Consumer:** `wealth-manager` — the cheap
investments read, the sibling of the cashflow-leg digest above; same hygiene (a compact block,
no per-holding deep fan-out, no report render). `quick`
runs the multi-dimensional allocation + concentration engine (`scripts/allocation.py`) and the
cheap per-holding drift/exit flags, but **not** the bounded `deep-analysis`/`mf-analysis`
fan-out (that is `deep`-only). It returns only:

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

`book_xirr` is `unavailable` when no IndMoney/broker source connected (manual-paste path) and
`inferred` when only staleness could be estimated — never a fabricated number. `market_cap`
splits come from the fund look-through's SEBI `mrktCapRank`, never from a personal source's own
breakdown field. `laggard_funds` rows come from `mf-analysis quick`, whose own digest is
`{scheme, grade_lite, key_numbers, path}` — descriptive only, never a category-rank percentile.
Holdings-value detail (the full KEEP/TRIM/EXIT table) stays in the artifact, never in the
digest (values are sensitive; the digest carries verdicts and percentages only).

## Convention: protection-leg digest (insurance-advisor Audit)
**Producer:** `insurance-advisor` Audit mode, **distilled by wealth-manager's `wealth-leg` runner**
(the Audit writes a full report; the runner transcribes its already-computed need-vs-have gap table
and red-flag list into this compact block — no insurance logic is duplicated). **Consumer:**
`wealth-manager` (the protection leg). Same hygiene as the other two leg digests: a compact block,
never the full report.

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
**Producer:** `wealth-manager/scripts/wealth.py` (the deterministic engine). **Consumer:** the
`wealth-manager` orchestrator (synthesis) and its artifact `artifacts/wealth/YYYY-MM-DD.md`
(`paths.report_path("wealth")`). The engine reads a **picture JSON** — the raw IndMoney
`networth_snapshot` + `networth_allocation_breakdown`, the `compute/holdings.py` positions envelope,
the three leg digests above, and an optional `profile` (age/dependents/monthly_expenses) — and owns
every number (nothing eyeballed).

- **Net-worth spine** (`build_spine`): `{ total_networth, as_of, allocation:{<bucket>:{label,value,pct}},
  liquid, equity_share_pct, holdings_xirr:{count,avg,best,worst}, source, coverage:
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
  offline; covered by `skills/wealth-manager/scripts/test_wealth.py`.

---

## The pipeline these contracts wire together

```
market-analysis ──market-context──┬──▶ strategy-manager (pick) ─┬──▶ find-trade (regime + sizing)
  (one computation per day,       ├──▶ mf-analysis (is the tier ├──▶ deep-analysis (sizing, valuation ctx)
   every later caller quick)      │    worth adding to?)        ├──▶ portfolio-review (smallcap flag)
                                  └──▶ sector-analysis ─────────┴──▶ daily-brief / trade-tracker
sector-analysis ─┐
              ▼
strategy-manager  ──generate→ spec(draft) ──validate(backtest)→ spec(active)
              │                                   ▲                  │
              │ optimize ◀── trade-idea.result ───┘                  │ pick (market-context)
              ▼                                                      ▼
        (live_performance)                                   find-trade ──signals──▶ trade-idea(idea)
                                                                                          │
deep-analysis / dcf / management-quality ── rationale ──▶ trade-tracker ◀── broker MCP ───┘
sources/filings.py ──▶ filings-watch / daily-brief   (promotes idea→open, closes→result)
sources/funds.py ──▶ mf-analysis (fund scan → shortlist → look-through) ──▶ portfolio-review
```
Every arrow is one of the contracts above.
