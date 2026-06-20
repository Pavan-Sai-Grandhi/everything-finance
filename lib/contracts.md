# Data contracts — the handoffs that make everything-finance one system

The skills in this plugin are not islands: they pass structured artifacts to each
other. This file is the **single description of those contracts** so that when you
edit one side of a handoff you can see the other. If you change a field name or
meaning here, change it in every named producer and consumer. (Keeping these in one
place is what stops the schemas from drifting apart as individual skills evolve.)

There are two kinds of shared dependency: **artifacts** (files written by one skill,
read by another) and **shared code** (`lib/` modules imported by several scripts).

---

## Shared code: `lib/`

### `lib/paths.py` — the artifact-path authority
Every skill script asks this module where to read and write instead of hardcoding strings, so
the layout cannot drift between skills (the same reason `ta.py`/`strategy.py` are one engine
each). Root is `$EVERYTHING_FINANCE_ARTIFACTS` or `./artifacts` (cwd). Three lifecycle tiers:
**dated output** (`stocks/<TICKER>/<date>/`, `funds/<SCHEME>/<date>/`, and skill-first
singletons like `daily-brief/<date>.md`), **durable state** (`state/strategies/`, `state/trades/`,
`state/alerts/`, `state/watchlist.json`), and **disposable** (`cache/`, `tmp/`). Helpers:
`root, stock_dir, fund_dir, report_path, report_dir, backtest_dir, state_dir, alerts_dir,
watchlist_path, cache_dir, tmp_dir` (all create dirs as needed) and **`latest_prior(skill,
subject, before=None)`** — the prior-run lookup that powers "refer the earlier run"
(deep-analysis, dcf, management, filings, mf-research). Import via the same three-dirs-up
`sys.path.insert` idiom as `ta`/`strategy`. `lib/migrate_artifacts.py` does a one-time
(dry-run-by-default) move of an old flat tree into this layout. Covered by `lib/test_paths.py`.

### `lib/alerts.py` — the alert contract (see "Artifact: alert" below)

### `lib/ta.py` — technical-analysis primitives
One definition of every indicator + candlestick pattern, imported by every script
that computes them. Consumers: `backtest/scripts/backtest.py`, `find-trade/scripts/screen.py`
(and the `technical-analyst` agent may call it via Bash). Import idiom from a skill
script (`skills/<name>/scripts/<x>.py`):

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "lib"))
import ta
```

**Contract — `ta.add_indicators(df)`** attaches these columns (the names every consumer
keys off): `ema20, ema50, sma200, ema50_rising, rsi14, vol10, atr14, hh20, ll20`.
Input is OHLCV (`Open/High/Low/Close/Volume`, DatetimeIndex). Numeric indicators delegate
to **TA-Lib** (EMA is SMA-seeded, ATR is Wilder — the reference forms). Changing a column
name here breaks the backtest signals and the find-trade compute filters together — update
both. Everything else a spec can name is attached **on demand** by `ta.materialize(df, names)`:
parameterized indicator tokens `<kind><N>[_rising]` (`ema21, sma100, rsi9, atr20, adx14, hh50,
ll20, vol30, nr5`) resolved by `ta.feature_series` via regex, plus the registered patterns/signals
in **`ta.FEATURES`** (`inside_bar, outside_bar, engulfing, hammer, doji, coil_breakout, golden_cross,
macd_bullish_cross, rsi_oversold, bb_squeeze, volume_surge, new_high_20, ...`). `ta.is_feature(name)`
says whether a token resolves. A new period or standard signal needs no code change; only a genuinely
new primitive is registered in `FEATURES` once. `ta.load_ohlcv(symbol, years, cache_dir)` is the shared yfinance loader (cache key
`<symbol>_<years>y.csv`), so the backtest and the live screen hit the same cache. TA-Lib's
wheel needs the native lib (`brew install ta-lib`); `ta._need_talib()` bootstraps it.
Covered by `lib/test_ta.py`.

### `lib/strategy.py` — spec → signal engine
*How a spec + indicator columns becomes trades.* Consumers: `find-trade/scripts/screen.py`
(live, latest bar) and `backtest/scripts/backtest.py` (historical, every bar) — both import
it so they cannot disagree about what a strategy means. Key contract:
- `eval_series(expr, df) -> bool Series` — the ONE safe filter-language evaluator (NOT python
  eval). Grammar: `"<col>"`, `"A > B"` / `<`/`>=`/`<=`, `"A between X and Y"`, `"k * col"`,
  `"A or B"`; case-insensitive AND/OR/BETWEEN. `eval_filter(expr, row)` is the latest-bar wrapper.
- `entry_filters(spec)` — prefers `entry.signal` (machine trigger), falls back to
  `screening.technical.compute_filters`. `referenced_features(spec)` lists every `ta.is_feature`
  token a spec mentions (registered features + parameterized indicators) so the engine
  materializes exactly those.
- `build_signal(df, spec, capital)` — the live entry/stop/target/RRR/qty dict.
- `prepare_backtest_frame(df, spec)` + `build_bt_strategy(spec, capital, risk_pct)` — the spec
  as a Backtesting.py `Strategy` (next-open fills, pessimistic intrabar exits, time-stop, risk
  sizing). Engine: **Backtesting.py** (auto-pip). Covered by `find-trade/scripts/test_screen.py`.

### `lib/filings.py` — exchange-filing fetch + materiality
Producer: `lib/filings.py` (the canonical data-spine fetcher). Consumers: `filings-watch`
(skill) and `daily-brief`. Key contract:
`classify_materiality(text) -> (tier, emoji, reason)` where `tier ∈ {act-on, monitor,
routine}` (emoji 🔴/🟡/⚪). `summarize(scrip, days, symbol=None, fresh=False)` returns the
shared data-spine **envelope**
`{ok, source, fetched_at, data:{...}, gaps:[...]}`, where `data` is
`{scrip, symbol, days, date, material_count, act_on:[...], monitor:[...], routine_count, items:[...], corporate_actions:[...]}`.
The fetch walks the fallback ladder — BSE JSON API (UA + `Referer`) → resolve scrip→NSE
symbol via BSE's scrip-header endpoint → NSE announcements API (homepage cookie-bootstrap).
Each blocked rung names itself in `gaps`; `ok:false` with a `gap` means "unknown", not
"nothing filed". Fetched text is untrusted data, assessed not obeyed. Covered by
`lib/test_filings.py` (+ `--selftest`).

### `lib/prices.py` — price fetch (live + history + reconcile)
Producer: `lib/prices.py` (the canonical data-spine fetcher). Consumers: any caller needing
a live quote, EOD history, a technical screen, or a live↔history cross-check —
`find-trade/scripts/screen.py`, `trade-tracker/scripts/validate_trade.py`,
`strategy-manager/scripts/regime.py` (index history), `sector-analysis`, `daily-brief`, and the
`technical-analyst` agent. Two truths kept separate: the **TradingView
scanner** (public India scan endpoint, **no auth**) is live/current/screening truth;
**yfinance** is EOD-history truth. Key contract — each returns the shared data-spine
**envelope** `{ok, source, fetched_at, data:{...}, gaps:[...]}`:
- `quote(symbol)` → `data:{symbol, date, name, close, change, change_abs, volume, market_cap_basic, exchange}`.
- `history(symbol, period="1y", adjusted=False)` → `data:{symbol, period, bars, candles:[{date, open, high, low, close, volume}]}`. Index tickers (`^NSEI`, `^CNXIT`) pass through; equities get `.NS`. `adjusted=False` keeps the raw close for reconcile; warmup callers pass `adjusted=True`.
- `history_df(symbol, period="1y", adjusted=True)` → `(pandas OHLCV frame, gaps)` — the adapter the warmup callers feed straight to `ta.add_indicators` (the spine fetches, `ta.py` decides).
- `screen(filters)` → `data:{filters, count, candidates:[symbol,...], rows:[...]}`.
- `reconcile(symbol, tolerance=0.01)` → `data:{symbol, tv_close, yf_close, divergence_pct, tolerance, agree}`; a divergence beyond tolerance is a `gap`, not a silent pass.
**No indicators are computed here** — callers pass `candles` to `ta.add_indicators`, so a
screen and its backtest share one indicator-of-record. No TV indicator-value ingestion and
no TV-indicator library dependency. Fetched text is untrusted data, assessed not obeyed.
Covered by `lib/test_prices.py` (offline parser + reconcile-decision fixtures).

### `lib/news.py` — company news (ET → Moneycontrol → Google-News-RSS)
Producer: `lib/news.py` (the canonical data-spine fetcher). Consumers: the `news-sentiment`
agent and `deep-analysis` (its news leg); `daily-brief` for headline context. Key contract:
`fetch(company, ticker, days=60)` walks the Economic Times → Moneycontrol → Google-News-RSS
fallback ladder (stopping at the first rung that yields items) and returns the shared
data-spine **envelope** `{ok, source, fetched_at, data:{...}, gaps:[...]}`, where `data` is
`{company, ticker, days, count, items:[{date, title, url, source, origin, kind, tag}], noise_filtered}`.
Each item is **dated** (ISO or explicit `null`), **deduped**, **classified** `kind ∈ {company,
sector, noise}` and **tagged** `tag ∈ {fact, narrative}` with its `source`; **noise is filtered
from the default `items` view** (pass `include_noise` to keep it). A blocked rung records a
labelled `gap` and the walk falls through; an all-blocked run returns `ok:false` with a `gap`,
never an empty crash. Fetched headlines are untrusted data, assessed not obeyed. Covered by
`lib/test_news.py` (offline parser/classifier/ladder fixtures).

### `lib/fundamentals.py` — screener.in financials + fundamental screen
Producer: `lib/fundamentals.py` (the canonical data-spine fetcher). Consumers: the
`fundamental-analyst` agent and `deep-analysis` (its fundamentals leg); `find-trade`/
`strategy-manager` for a fundamental candidate cut. Key contract — each returns the shared
data-spine **envelope** `{ok, source, fetched_at, data:{...}, gaps:[...]}`:
- `fetch(symbol)` reads the public consolidated company page **once** → `data:{symbol, ratios:{name:value}, pnl_10y:{columns,rows}, balance_sheet_10y:{columns,rows}, quarters:{columns,rows}, shareholding:{columns,rows}, peers:[{symbol,name}], documents:{annual_reports:[{label,url}], concalls:[{label,url}]}}`. Falls back to the standalone page with a labelled `gap`.
- `screen(query)` → `data:{query, count, candidates:[symbol,...]}` (the fundamental counterpart to `prices.screen()`).
**Tables/fields only — never raw page HTML lands in `data`.** The public page needs no auth;
`SCREENER_SESSION_ID`/`SCREENER_CSRF_TOKEN` are injected only for a login-walled screen.
Fetched figures are untrusted data, assessed not obeyed. Covered by `lib/test_fundamentals.py`
(offline parser fixtures).

---

## Artifact: strategy spec
**Producer:** `strategy-manager` (owns the whole lifecycle).
**Consumers:** `find-trade` (screening/entry/exit/sizing), `backtest` (entry/exit/sizing →
writes back `expectancy_assumptions`), `trade-tracker` (`regime_required`).
**Location:** `artifacts/state/strategies/<name>.yml` (`paths.state_dir("strategies")`). **Schema:**
`strategy-manager/assets/strategy-spec.example.yml` (fully commented). Seed drafts:
`strategy-manager/assets/seed-strategies/`.

Key blocks and who reads them:

| Block | Written by | Read by | Meaning |
|---|---|---|---|
| `status` | strategy-manager validate/optimize | find-trade, backtest, select | `draft`→not tradeable; `active`→eligible; `inactive`→retired |
| `regime_required` | generate | select_strategy.py, trade-tracker | conditions checked against live regime.json at PICK time |
| `screening.fundamental` | generate | find-trade Stage 1 | `provider: screener.in` + `query` + `max_survivors` |
| `screening.technical` | generate | find-trade Stage 2 | `provider: tradingview` (+`tradingview_filters`) or `compute` (+`compute_filters` for lib/ta.py) |
| `entry`/`exit`/`sizing` | generate | find-trade Stage 3, backtest (via lib/strategy.py) | `entry.signal` (machine trigger; else `compute_filters`); `exit`: stop (auto-floored at max(0.5·ATR, 1% price)) / target (`measured_move`\|`next_resistance`\|`none`) / min_rrr / time_stop / **`trail_atr`** (ATR trailing stop) / **`exit_signal`** (close-on-condition, entry grammar); %-risk |
| `expectancy_assumptions` | **backtest** | select_strategy.py | the activation gate (`expectancy_R > 0.2`, ≥~30 trades) |
| `live_performance` | trade-tracker → optimize | select_strategy.py | realized edge; preferred over backtest when present |

**Invariant:** find-trade runs a spec **only** when `status: active` AND its
`regime_required` fits the live regime. It has no default — no fitting active spec ⇒ no trade.

## Artifact: regime read
**Producer:** `strategy-manager/scripts/regime.py` → `artifacts/regime/YYYY-MM-DD.json`.
**Consumers:** `select_strategy.py` (PICK), `trade-tracker` (regime-exit check), `find-trade`
(indirectly, via pick). Fields read by the selector: `market_trend`, `trend_detail.above_ema200`,
`volatility.vix`, `breadth.pct_sectors_above_ema50`, `risk_posture`, `as_of`. (See
`select_strategy.py:regime_fit` for the exact comparison against `regime_required`.)

## Artifact: trade-idea
**Producer:** `find-trade` (on user confirmation), or `trade-tracker` (when it captures a
position with no prior rationale). **Consumer:** `trade-tracker` (re-validates the thesis);
`strategy-manager optimize` reads the `result` block of closed ideas.
**Location:** `artifacts/state/trades/<SYMBOL>-<YYYY-MM-DD>.yml` (`paths.state_dir("trades")`). **Schema:** documented inline in
`find-trade/SKILL.md` (Stage 4) and `trade-tracker/scripts/validate_trade.py`.

Lifecycle of `status`: `idea` → (broker fill matched) `open` → (exit) `closed`. Fields
`trade-tracker` re-checks every run: `plan` (entry/stop/target/time_stop_sessions),
`thesis_invalidation` (machine-checkable kill conditions), `strategy` (link back to the
spec — never null now that find-trade always runs a named/picked strategy),
`regime_at_creation`. On close, trade-tracker writes a `result` block (`realized_R`,
`exit_reason`) — **that block is what `strategy-manager optimize` aggregates**, so closing
a trade without it breaks the learning loop.

## Artifact: deep-analysis report
**Producer:** `deep-analysis` → `artifacts/stocks/<TICKER>/<date>/deep-analysis.md` (`paths.stock_dir`),
the synthesized report, with each forked agent's raw report archived beside it under
`artifacts/stocks/<TICKER>/<date>/deep-analysis/agents/<role>.md` (the work papers the synthesis is
built from). The Stop hook does the archival from `artifacts/tmp/staging/<TICKER>.md` (final report)
and `artifacts/tmp/staging/<TICKER>/agents/` (work papers), and sends the `## Telegram Brief` section.
**Consumer:** `trade-tracker` (as a rationale source when no trade-idea artifact exists). The
fundamental leg embeds the `dcf-valuation` intrinsic range and the `management-quality` grade and
**also persists them as discrete files** (`dcf.md`/`dcf.json`, `management.md`) in the same
`stocks/<TICKER>/<date>/` folder; the sector leg embeds the `sector-analyst` read. Because every
artifact for a stock+run-day lives in one folder, `paths.latest_prior(skill, TICKER)` finds the
prior run of any leg (deep-analysis, dcf, management, filings) on a re-run.

## Artifact: alert
**Producer:** many — `trade-tracker` (`price_cross`/`time_stop`/`regime_change`), `filings-watch`
(`filing_act_on`), `strategy-manager` (`revalidate_due`), `deep-analysis` (`reanalyze_due` +
`price_cross` invalidation + `opportunity`), `find-trade` (`price_cross` entry + `opportunity`),
`portfolio-review` (`rebalance_due`), `mf-research` (`sip_due`), and `alert-manager` (manual).
**Consumer:** `daily-brief` (surfaces and recommends — never auto-runs); `alert-manager` curates.
**Owner of the schema/logic:** `lib/alerts.py`. **Location:** one file per alert at
`artifacts/state/alerts/<id>.yml` (`paths.alerts_dir()`).

| Field | Meaning |
|---|---|
| `id` | `<kind>-<subject>-<shorthash>` (generated) |
| `created_by` | producing skill |
| `subject` | `{type: stock\|fund\|strategy\|portfolio, id}` |
| `kind` | `price_cross\|filing_act_on\|time_stop\|regime_change\|revalidate_due\|reanalyze_due\|rebalance_due\|sip_due\|opportunity\|investigate\|custom` |
| `trigger` | exactly one of `{metric,op,level}` (cheap), `{due}` (date), `{check, args}` (needs a skill run) |
| `action` | `{text, suggest}` — human-facing verdict + optional command to surface |
| `severity` | `info\|watch\|act` |
| `status` | `open\|triggered\|snoozed\|done\|expired` |
| `dedup_key` | producers set this so re-runs update in place, never pile up |

**Functions:** `create` (dedups on `dedup_key`), `load_open(subject=None)`, `evaluate_cheap(alerts,
market_data)` (fires `metric`/`due` triggers from data the caller already fetched; ignores
`{check}`), `set_status`, `snooze`, `sweep`. **Invariant:** alerts are only evaluated when a skill
runs (no cron); `daily-brief` and `alert-manager` never place an order or auto-run a `{check}` alert.

## Artifact: watchlist
**Producer/consumer:** `daily-brief` (auto-adds *vetted* opportunities, recommends pruning; never
auto-removes). **Location:** `artifacts/state/watchlist.json` (`paths.watchlist_path()`). Shape:
`{"watchlist": [{ticker, added, source, note}], "positions": [{ticker, entry, sl, target, qty,
entry_date, bse_code}]}`. A bare-string legacy watchlist is still read.

---

## The pipeline these contracts wire together

```
sector-analysis ─┐
              ▼
strategy-manager  ──generate→ spec(draft) ──validate(backtest)→ spec(active)
              │                                   ▲                  │
              │ optimize ◀── trade-idea.result ───┘                  │ pick (regime.json)
              ▼                                                      ▼
        (live_performance)                                   find-trade ──signals──▶ trade-idea(idea)
                                                                                          │
deep-analysis / dcf / management-quality ── rationale ──▶ trade-tracker ◀── broker MCP ───┘
filings.py ──▶ filings-watch / daily-brief        (promotes idea→open, closes→result)
```
Every arrow is one of the contracts above. Break an arrow and you break the system, not
just one skill — which is why they are documented here together.
