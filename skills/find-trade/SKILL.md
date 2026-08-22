---
name: find-trade
description: Find swing/positional trade candidates in the Nifty 500 by running a chosen, validated trading strategy against today's market — screen the universe down (fundamentals via Tickertape, technicals via TradingView or a local TA-Lib compute), then construct entry/stoploss/target/size signals and, on confirmation, persist a trade-idea artifact the trade-tracker skill monitors. This is the strategy-AGNOSTIC execution engine — it carries no setups of its own; the rules always come from an active strategy spec owned by strategy-manager. Use whenever the user asks to screen stocks, find swing trades, scan the market, look for setups, run the pipeline, or "anything worth trading this week?" — even if they don't say "screen". If the user names a strategy use it; if they don't, the skill asks strategy-manager to pick the active strategy that fits the current regime (it never falls back to a hardcoded default — a screen with no validated strategy behind it is not a tradeable signal).
argument-hint: "[strategy:<name>] [optional: capital ₹ | sector filter]"
allowed-tools: Read, Write, Bash, Skill, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*
---

# Find Trade — run a validated strategy against today's market (Nifty 500)

find-trade is the **executor**, not the strategy: every screening filter and entry/exit rule comes from an **active, regime-fitting strategy spec** that `strategy-manager` owns (schema: `strategy-manager/assets/strategy-spec.example.yml`; full contract: `<plugin>/finance/contracts.md`). Take that spec, cut the Nifty 500 down to a shortlist, build disciplined signals. Read `references/reference.md` for the screening method and the candidate-grading checklist.

## Step 0 — Resolve the strategy (no defaults, ever)

- **User named a strategy** (`strategy:<name>`, or referenced a managed strategy) → load `artifacts/state/strategies/<name>.yml`. Two gates, in order:
  1. **Status** must be `active` (`draft` = not yet backtested, `inactive` = retired). A non-active strategy isn't validated to trade — return zero candidates and point to `/strategy-manager validate <name>`.
  2. **Regime fit** — even when active, only run while the tape fits its `regime_required`. If unsure, defer to `/strategy-manager pick`. If the user *force-runs* a named strategy, you may proceed but flag any `regime_required` conflict with the live regime.
- **No strategy named** → **call `strategy-manager` in `pick` mode** (via the `Skill` tool) to select the active strategy that fits the current regime, then run that one.
- **`pick` returns nothing** (no active specs, or none fit the regime) → **stand aside**. Say so plainly: there is no validated, regime-appropriate strategy to run, and the disciplined move is not to trade. Point the user to `/strategy-manager generate` (build one from a reference article) or `validate` (activate a draft). **Do not screen with an ad-hoc default** — signals with no backtested edge behind them are not tradeable.

Once a spec is resolved, its `screening`, `entry`, `exit`, and `sizing` blocks ARE the rules below.

## Stage 1 — Fundamental screen → cut the universe (`screening.fundamental`)

Run `run_fundamental_screen(query=<the spec's query, verbatim>)` only if `screening.fundamental.provider` is `tickertape` (else skip this stage). Cap at `max_survivors`; if exceeded, tighten per the spec's note (e.g. ROCE > 15). Save survivors to `artifacts/cache/gate_survivors.json`.

If the screen comes back empty, or `ok:false` with a gap naming an unresolvable field or an unsupported operator: reuse the most recent `gate_survivors.json` if < 7 days old (fundamentals move slowly), else skip the fundamental cut, pre-rank the Nifty 500 by 6-month momentum instead, and flag "fundamental screen skipped — <the gap, verbatim>" in data gaps. A refused query is a spec defect, not a transient outage — report it so `strategy-manager` can fix the spec.

## Stage 2 — Technical screen → shortlist (`screening.technical`)

This is the **coarse chart-state cut** (whole universe → a shortlist), distinct from the per-stock entry trigger in Stage 3. Branch on the spec's `screening.technical.provider`:

- **`provider: tradingview`** — call **`run_technical_screen`**. Translate the spec's human-readable `tradingview_filters` into scanner filter objects and pass them as `filters`, with the columns you need:
  ```
  run_technical_screen(
    filters=[{"left":"SMA50","operation":"greater","right":"SMA200"},
             {"left":"close","operation":"greater","right":"SMA50"},
             {"left":"RSI","operation":"in_range","right":[40,60]},
             {"left":"market_cap_basic","operation":"egreater","right":50000000000}],
    columns=["name","close","RSI","SMA50","SMA200","volume","market_cap_basic"],
    limit=60)
  ```
  Notes that make this work: cross-column tests use `"right":"<COLUMN>"` (e.g. `SMA50 > SMA200`); the response `data[].s` is `"NSE:SYMBOL"` / `"BSE:SYMBOL"` — **keep `NSE:` and strip the prefix, dropping the BSE duplicate of each name**; `data[].d` is the columns array in request order. This is the shortlist Stage 3 builds signals on. A filter that genuinely can't be expressed in the scanner (rare) is computed locally instead — that is what the `compute` branch below does.
- **`provider: compute`**, OR TradingView unreachable with `fallback_compute: true` — the cut is reproduced from EOD OHLCV using the spec's `compute_filters` inside `run_strategy_screen` (Stage 3), which screens and builds signals in one pass. Feed it the Stage-1 survivors; with no fundamental stage, feed the Nifty 500 list. When you fall back, **say so** in data gaps — a local compute of "SMA50>SMA200 & RSI 40-60" approximates TradingView's server-side screen, it doesn't equal it.

## Stage 2.5 — Record the market the screen ran in

Call `get_market_context(mode="quick")` and carry `as_of`, `market_trend`, `market_posture` and `volatility.band` into the output header. `market_posture` governs **sizing aggressiveness only** — never the entry rule, which always comes from the spec: `risk_off` caps risk-per-trade at half the spec's figure and `risk_on` permits the full figure, with the reason stated.

## Stage 3 — Signal construction (`entry` / `exit` / `sizing`)

```
run_strategy_screen(spec="artifacts/state/strategies/<name>.yml",
                    symbols=<survivor list, comma-separated string, or path to a symbols file>,
                    years=2, capital=<₹>,
                    out="artifacts/find-trade/YYYY-MM-DD.json")
```

It builds a signal per survivor from the spec: entry (the breakout trigger for breakout archetypes, else the last close for pullback/reversal setups), stop from `exit.stop` (`recent_swing_low` | `ema50_minus_2atr` | `range_low`), target from `exit.target` (`measured_move` → consolidation height; else next-resistance proxy at `min_rrr`), RRR gated at `exit.min_rrr`, and qty at `sizing.risk_per_trade_pct`. Anything failing the RRR gate or with a malformed/too-wide stop is dropped with a reason — never silently; every rejection and its reason is in the written report.

Volume confirmation is mandatory (the engine reports `vol_vs_10d`); a candidate without above-average volume is flagged "weak" and ranked last, not dropped silently. For a `next_resistance` target the engine uses a min-RRR proxy — **confirm the real overhead resistance on the chart** before acting, and say so.

## Output

Render `assets/signal-report.html` filled with the candidate table (ticker, setup/strategy, entry, SL, target, RRR, volume confirmation, fundamental snapshot, indicator read), the **strategy name + how it was chosen** (named vs picked, and the regime it fits), save to `artifacts/find-trade/YYYY-MM-DD.html` (`paths.report_path("find-trade", date, "html")`), and summarize the top 3 in chat. Include a **Data gaps** section for any failed fetch or compute-fallback, and a **TradingView chart link** (`tradingview.com/symbols/NSE-<SYMBOL>/`) per candidate for the user's own eyeball check.

## Stage 4 — Suggest & commit (hand-off to trade-tracker)

Suggest the single highest-conviction candidate (or top 2–3 if genuinely tied) in one line each: ticker, setup, entry/SL/target, RRR, one-sentence thesis. Then ask plainly: *"Want me to track <TICKER>? (yes / pick another / no)"*

**Only on an explicit "yes"** (or the user naming which to track) persist a **trade-idea artifact** — the contract `trade-tracker` reads (schema + every field documented in `<plugin>/finance/contracts.md`):

- Path: `artifacts/state/trades/<SYMBOL>-<YYYY-MM-DD>.yml` (`paths.state_dir("trades")`; SYMBOL = NSE trading symbol, no `.NS`). Create the dir if needed; if a file for the same symbol+date exists, append `-2` etc. rather than overwriting.
- Set `source_skill: find-trade` and `strategy: <name>` (the strategy you ran — never null, since find-trade always runs a named or picked strategy). Fill **every** field from the screen you just ran — especially `rationale` and `thesis_invalidation`, which are exactly what `trade-tracker` re-checks.

Confirm the saved path in chat and tell the user to run `/trade-tracker` once they execute. If the user says no, persist nothing.

## Alerts this skill raises (via `finance/compute/alerts.py`)

As a side-effect of a confirmed run, write watch-items so `daily-brief` can surface them later (set `dedup_key` so re-runs update in place, never pile up):

- **`price_cross` entry-trigger** — for a high-conviction candidate the user wants but that hasn't filled yet, raise a `price_cross` alert at the entry trigger level (`subject: {type: stock, id: <SYMBOL>}`, `created_by: find-trade`, `severity: watch`, `action.suggest: "/find-trade strategy:<name>"`, `dedup_key: entry-<SYMBOL>`).
- **`opportunity` (vetted)** — when a candidate clears both gates off an *active* strategy, raise an `opportunity` alert (`severity: watch`, `action.text` = the one-line basis, `action.suggest: "/deep-analysis <SYMBOL>"`, `dedup_key: opp-<SYMBOL>`). This is the vetted feed daily-brief's Opportunities section reads — and a vetted opportunity is what daily-brief auto-adds to the watchlist.
