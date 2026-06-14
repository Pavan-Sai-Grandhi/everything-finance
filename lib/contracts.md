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

### `filings-watch/scripts/filings.py` — exchange-filing fetch + materiality
Consumers: `filings-watch` (skill) and `daily-brief`. Key contract:
`classify_materiality(text) -> (tier, emoji, reason)` where `tier ∈ {act-on, monitor,
routine}` (emoji 🔴/🟡/⚪). `summarize(scrip, days)` returns
`{scrip, days, material_count, act_on:[...], monitor:[...], routine_count, corporate_actions:[...], notes:[...]}`.
`notes` is non-empty when a source was blocked/empty — callers must treat that as
"unknown", not "nothing filed". Covered by `test_filings.py`.

---

## Artifact: strategy spec
**Producer:** `strategy-manager` (owns the whole lifecycle).
**Consumers:** `find-trade` (screening/entry/exit/sizing), `backtest` (entry/exit/sizing →
writes back `expectancy_assumptions`), `trade-tracker` (`regime_required`).
**Location:** `artifacts/strategies/<name>.yml`. **Schema:**
`strategy-manager/assets/strategy-spec.example.yml` (fully commented). Seed drafts:
`strategy-manager/assets/seed-strategies/`.

Key blocks and who reads them:

| Block | Written by | Read by | Meaning |
|---|---|---|---|
| `status` | strategy-manager validate/optimize | find-trade, backtest, select | `draft`→not tradeable; `active`→eligible; `inactive`→retired |
| `regime_required` | generate | select_strategy.py, trade-tracker | conditions checked against live regime.json at PICK time |
| `screening.fundamental` | generate | find-trade Stage 1 | `provider: screener.in` + `query` + `max_survivors` |
| `screening.technical` | generate | find-trade Stage 2 | `provider: tradingview` (+`tradingview_filters`) or `compute` (+`compute_filters` for lib/ta.py) |
| `entry`/`exit`/`sizing` | generate | find-trade Stage 3, backtest (via lib/strategy.py) | `entry.signal` (machine trigger; else `compute_filters`), stop/target/min_rrr/time_stop, %-risk |
| `expectancy_assumptions` | **backtest** | select_strategy.py | the activation gate (`expectancy_R > 0.2`, ≥~30 trades) |
| `live_performance` | trade-tracker → optimize | select_strategy.py | realized edge; preferred over backtest when present |

**Invariant:** find-trade runs a spec **only** when `status: active` AND its
`regime_required` fits the live regime. It has no default — no fitting active spec ⇒ no trade.

## Artifact: regime read
**Producer:** `strategy-manager/scripts/regime.py` → `artifacts/YYYY-MM-DD/regime.json`.
**Consumers:** `select_strategy.py` (PICK), `trade-tracker` (regime-exit check), `find-trade`
(indirectly, via pick). Fields read by the selector: `market_trend`, `trend_detail.above_ema200`,
`volatility.vix`, `breadth.pct_sectors_above_ema50`, `risk_posture`, `as_of`. (See
`select_strategy.py:regime_fit` for the exact comparison against `regime_required`.)

## Artifact: trade-idea
**Producer:** `find-trade` (on user confirmation), or `trade-tracker` (when it captures a
position with no prior rationale). **Consumer:** `trade-tracker` (re-validates the thesis);
`strategy-manager optimize` reads the `result` block of closed ideas.
**Location:** `artifacts/trades/<SYMBOL>-<YYYY-MM-DD>.yml`. **Schema:** documented inline in
`find-trade/SKILL.md` (Stage 4) and `trade-tracker/scripts/validate_trade.py`.

Lifecycle of `status`: `idea` → (broker fill matched) `open` → (exit) `closed`. Fields
`trade-tracker` re-checks every run: `plan` (entry/stop/target/time_stop_sessions),
`thesis_invalidation` (machine-checkable kill conditions), `strategy` (link back to the
spec — never null now that find-trade always runs a named/picked strategy),
`regime_at_creation`. On close, trade-tracker writes a `result` block (`realized_R`,
`exit_reason`) — **that block is what `strategy-manager optimize` aggregates**, so closing
a trade without it breaks the learning loop.

## Artifact: deep-analysis report
**Producer:** `deep-analysis` → `artifacts/YYYY-MM-DD/<TICKER>-deep-analysis.md` (+ a staging
copy for the Stop-hook Telegram brief). **Consumer:** `trade-tracker` (as a rationale source
when no trade-idea artifact exists). The fundamental leg embeds the `dcf-valuation` intrinsic
range and the `management-quality` grade.

---

## The pipeline these contracts wire together

```
sector-pulse ─┐
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
