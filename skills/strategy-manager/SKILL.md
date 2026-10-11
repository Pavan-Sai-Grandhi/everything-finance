---
name: strategy-manager
description: Own the full lifecycle of rule-based trading strategies for Indian markets — (1) GENERATE a complete strategy from a reference article you supply, (2) VALIDATE it by backtesting the spec on historical NSE daily data (the bundled Backtesting.py engine on TA-Lib indicators — win rate, expectancy, profit factor, max drawdown vs buy-and-hold) and mark it active when it passes, (3) PICK the active strategy that fits the current market regime, and (4) OPTIMIZE or retire strategies from live trade outcomes fed back by trade-tracker. Use whenever the user asks to design/build a strategy, to backtest or validate one, "check if this strategy actually works", the historical performance of a setup, "what strategy should I run now / in this market", review or tune a strategy's live performance, activate/deactivate a strategy, or after discover produces signals and the user questions the strategy's edge.
argument-hint: "[generate <article URL/file> | validate <name> [symbols] [years] | pick | optimize <name|all> | <name to inspect>]"
allowed-tools: WebFetch, Read, Write, Bash, Skill, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*
---

# Strategy Manager — generate → validate → pick → optimize

This skill owns a strategy's whole life. A strategy lives as a spec at `artifacts/state/strategies/<name>.yml` (schema: `assets/strategy-spec.example.yml`) and moves through a lifecycle:

```
 mode: generate            mode: validate              mode: optimize
 (from article)            (backtest passes)           (live edge decays)
   ┌────────┐  draft   ┌────────┐  active   ┌───────────────┐  inactive
   │ DRAFT  ├─────────▶│ ACTIVE │◀─────────▶│ OPTIMIZE/RETIRE│
   └────────┘          └───┬────┘           └───────────────┘
                           │ mode: pick (runtime regime-fit) → hand to discover
```

`status` is the lifecycle state (`draft | active | inactive`); **regime-fit is NOT a status** — it's decided fresh each time in `pick` mode against the live tape. Read `references/reference.md` first for the system framework, the activation thresholds, the selection logic, and the optimization rules this skill enforces; `references/backtesting.md` carries the engine contract, the bias traps, the cost model and how to read the metrics, and must shape how VALIDATE presents results.

**A spec has a `purpose`: `trading` or `investment`.** A **trading** spec (the default) carries the full universe/screening/entry/exit/sizing/regime and is validated by backtest — the whole lifecycle above. An **investment** spec (for `discover stocks --invest`) carries `universe` + `screening.fundamental` + `ranking` + `regime_required` only, omits the trading half, is validated by a **completeness check** (not a backtest), and has **no optimize loop** (there is no live trade to learn from). Each mode below notes where the two diverge.

A third value, **`purpose: fund`**, is a thin seed consumed by `discover funds`, not by this skill: it carries `regime_required` + a `scan` block (`category`/`window`/`min_aum`/`top`) that maps a market cycle to `get_fund_scan` arguments — it re-implements no scoring (get_fund_scan owns every gate and weight), is not generated/validated/backtested here, and lives only as a seed (`assets/seed-strategies/*-fund.yml`). Schema note in `flexicap-allweather-fund.yml`.

**The reference article the user provides is the one source outside the tool map** — a URL via `WebFetch`, or a local file via `Read`. It is REQUIRED for `generate`, and every trade rule in an emitted spec must be traceable to it.

## Route to a mode

- A reference article / "design a strategy from this" → **GENERATE**.
- "backtest / validate <name>", "does <name> actually work", the historical performance of a setup, or right after generate → **VALIDATE**.
- "what should I trade now", "pick a strategy", "which strategy fits this market" → **PICK**.
- "review / tune / optimize <name>", "is <name> still working", "should I retire <name>" → **OPTIMIZE**.
- A bare strategy name with no verb → inspect it (print status, expectancy, live_performance, regime-fit now) and offer the relevant next mode.

---

## Mode 1 — GENERATE (from a reference article)

**Trading or investment.** If the article describes a *screening philosophy* rather than an entry/exit system ("quality-momentum microcaps", "high-ROCE compounders"), emit an **investment** spec — fill only `universe`, `screening.fundamental`, `ranking` (`metric` + `top_n`) and `regime_required`, set `purpose: investment`, and skip the entry/exit/sizing/indicator-study steps below (there is no trigger to study). Example: `assets/seed-strategies/quality-momentum-invest.yml`. The rest of this mode is the trading path.

This skill invents **no trade logic of its own** — it always comes from the article. It supplies the *system framework* (completeness, expectancy, %-risk sizing, regime gate). A **seed library of pre-generated drafts** (common swing methods distilled from a reference article) lives in `assets/seed-strategies/` — these are starting points the user copies into `artifacts/state/strategies/` and must still VALIDATE; they are `status: draft`, never a shortcut around the backtest gate.

1. **Ingest the reference(s) — REQUIRED.** URL → `WebFetch`; local file → `Read`. If the user gives none, **stop and ask** for a URL/file/pasted rules. Extract — and quote the source for — the strategy's universe, entry, exit, ranking/rebalance, indicators, and the regime it claims (reference.md extraction table).
2. **Read the market as context.** `get_market_context(mode="quick")` returns trend, India VIX, breadth, cap-tier valuation, flows and macro in one cached digest, so nothing here recomputes the tape. Call `sector-analysis` for leadership. This informs `regime_required`, not the entry trigger.
3. **Complete the system.** Fill every component the article omits from the framework — sizing (default 1% risk), risk caps (heat 6%), `regime_required` from the article's claimed conditions (minimum structural gate if it's silent), and the **`screening` block** (how discover cuts the universe): the `fundamental` cut (provider `tickertape` + a query in Tickertape field names) and the `technical` cut (provider `tradingview` with server-side filter rows, or `compute` with local `finance/compute/ta.py` predicates when TradingView can't express the filter — e.g. NR-bars, fib zones). A spec missing universe/screening/entry/exit/sizing/risk/regime is incomplete; don't emit it.
   - **Map the article's exit to the engine's exit vocabulary — don't approximate it.** The engine expresses more than a fixed target, so encode the source's *actual* exit: a **trailing stop** → `trail_atr: <mult>` with `target: trailing` (a long `time_stop` is not a substitute — it caps winners and the optimizer misreads it); a **moving-average / indicator exit** (a "close back above the 5-SMA" mean-reversion exit, a "close below the 20-EMA" trend break) → `exit_signal: "<expr>"` in `entry.signal`'s grammar. Reserve `measured_move`/`min_rrr` targets for setups whose source names a fixed objective. If the source's exit genuinely can't be expressed, say so in the rationale — but reach for `trail_atr`/`exit_signal` first.
   - **Use exact target names**, never prose in `exit.target`. Put source objectives and unimplemented conditions in the rationale. Dynamic-only exits can be backtested, but the live screen skips them because it cannot supply a sourced fixed target. Do not replace that skip with an invented risk-multiple objective or describe a proxy as chart resistance.
4. **Indicator study — REQUIRED, numeric not screenshot.** Confirm the article's entry/exit on 2–3 representative symbols against the indicator-of-record (TA-Lib via `finance/compute/ta.py`), and carry a **static TradingView link** for the human to eyeball. No chart rendering and no screenshots: the substance is the numbers, the chart is a courtesy link. Both reads run the spec's own rules, so write the draft file (step 5) first — it is `status: draft` and untradeable until VALIDATE, so nothing is at risk.
   - **Latest-bar read:** `run_strategy_screen(spec="artifacts/state/strategies/<name>.yml", symbols="NTPC,TCS,SBIN", years=3)`. It materializes exactly the indicator columns the spec's rules reference and reports, per symbol, either the built signal or the precise expression that failed — read the written report and confirm the condition that fired is the article's.
   - **Historical read:** inspect the first 2–3 chronological trades from `run_backtest`'s log, regardless of profit. Verify the rule, fill timing and original stop on their dated bars. Cite symbol, entry date, exit reason and R as illustrations of mechanics, not independent proof of edge.
   - Compare indicator values only over matching candle dates, adjustment settings and warm-up history; differences in those inputs can explain a chart mismatch.
   - **Put a human-facing chart link in the rationale:** `https://www.tradingview.com/symbols/NSE-<TICKER>/`.
   - Record the numeric confirmation as `indicator_study`; leave it `PENDING` until done — never fabricate it.
An explicit nonempty `entry.signal` is required by both live screening and backtesting. A prose trigger or coarse `compute_filters` alone is rejected before data fetching. For legacy specs and seeds without a signal, encode the intended rules explicitly; do not automatically copy a broad screen and claim it tests the described entry.

5. **Emit the spec as `status: draft`.** Fill `assets/strategy-spec.example.yml` → `artifacts/state/strategies/<name>.yml` with `source_references` populated, `lifecycle.generated_at` set, `expectancy_assumptions`/`live_performance` null. Write the rationale doc → `artifacts/strategy-manager/YYYY-MM-DD/<name>.md` citing the article for each trade rule and the framework for the risk layer. **A draft is not tradeable** — immediately offer VALIDATE.
   - **Quote every free-text value, then round-trip the file before trusting it.** Any string that can contain a `:`, `#`, parentheses, or a path — `validated_by`, `target`, `deactivated_reason`, `optimization_log` notes — must be double-quoted, or a `key: value` fragment inside it reads as a nested map and the spec silently becomes unloadable (`run_backtest`/discover then crash on it). After writing, verify it parses: `python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" artifacts/state/strategies/<name>.yml`.

## Mode 2 — VALIDATE (backtest → active)

Turn a draft into an active strategy *only if it earns it*. This mode validates **rules**, not stock picks — it answers "does this setup have an edge?", never "will this trade win?".

**An investment spec is not backtested** — there is no entry/exit to test. Its validation is a **completeness check**: (1) `universe.source` resolves via `get_universe`; (2) `screening.fundamental.provider` is `tickertape` and every query field resolves against its catalogue (a dry `run_fundamental_screen` succeeds or names the unsupported field); (3) `ranking.metric` is one of `return_12m | return_6m | rs_vs_nifty`. All pass → set `status: active` and `lifecycle.validated_at`; otherwise keep `draft` with the gap named. This establishes an executable research screen, not investment merit. Legacy `screener_in` specs are unsupported under the source policy: re-author explicitly using approved data, never translate cross-period criteria into different point-in-time filters without saying the idea changed. The rest of this mode is the trading/backtest path.

1. **Run the engine.** `run_backtest` against the spec — arguments and mechanics in `references/backtesting.md`.
   - **Never pass market context into a historical run.** The market-analysis artifact describes *today*; feeding it in is lookahead — the strategy would "know" a regime that had not happened yet.
2. **Map `expectancy_R` to a verdict**, then to a status:

   | expectancy_R | verdict | status |
   |---|---|---|
   | < 0R | no edge | `inactive` |
   | 0–0.2R | no tradeable edge (fragile) | stays `draft` |
   | > 0.2R over ≥ ~30 trades | edge | `active` |

   **Unassessed expectancy or material unresolved data gaps prevent activation. `n_trades` < 30 overrides the whole table: the run is *inconclusive — insufficient sample*, whatever the expectancy.** 0.9R over 12 trades is an anecdote, not an edge; the spec stays `draft`. Widen symbols/years and re-run before concluding anything.
3. **Run the honesty checks and say them out loud in the report:**
   - **In-sample?** The spec's parameters were fixed before the run, or the number is curve-fit.
   - **Survivorship.** `symbols="largecap20"` expands to a built-in **20-stock** liquid large-cap basket of *current* constituents — it is *not* the full Nifty 50; name it as "20-stock large-cap basket" in the report.
   - **Regime concentration.** Did all the profit come from one bull year? Check the yearly breakdown.
   - **Open at the end.** Report `open_trades_at_end`. Those positions remain marked in account equity but are excluded from closed-trade expectancy; inspect whether this omission changes the interpretation of the sample. Do not manufacture a final exit or claim the final-bar signal filled.
   - **`exit_breakdown`.** TIME exits > 50% ⇒ the target/time-stop pairing is mis-specified for the universe — report that as the diagnosis, don't tune parameters in-sample.
   - **Buy-and-hold comparison.** Report the independent-account capital denominator and actual price windows. Match the worst drawdown to `max_drawdown_symbol`'s benchmark and inspect `equity_path`; do not call it portfolio drawdown. State the exposure and cost-model differences.
   - **Arriving from discover:** state what was *not* tested — the backtest tests the technical trigger mechanics, not the fundamental screen or the discretionary S/R read.
4. **Write the results into the spec's `expectancy_assumptions`** (`win_rate`, `expectancy_R`, `profit_factor`, `n_trades`, `validated_by` = the summary artifact path).
5. **Apply the activation gate (reference.md) and set `status`** per step 2's mapping — say which and why. On activation set `lifecycle.validated_at` and `activated_at`. If the numeric indicator study never ran (`indicator_study` PENDING) it cannot go active — finish that read first.
6. **Report.** Save the summary to `paths.backtest_dir(spec, date)` (`artifacts/backtest/<spec-name>/YYYY-MM-DD/report.md`) alongside the engine's CSV outputs. A passed backtest is a hypothesis that survived history, not a guaranteed edge — end with: backtests describe the past; live edge degrades — position sizing discipline is what survives.

## Mode 3 — PICK (select the active strategy that fits now)

Answer "what should I trade in this market" from the **validated library**, not from a fresh opinion.

1. Refresh the market-of-record: `get_market_context(mode="quick")` — the shared daily read, so this selection tests the regime every other skill sees, not a fresh opinion of the tape.
2. Select: `python3 <skill-dir>/scripts/select_strategy.py [--purpose trading|investment] --out artifacts/strategy-manager/YYYY-MM-DD/selection.json` (`--regime` defaults to today's `artifacts/market-analysis/<date>.json`, the digest `market-analysis` persists; `--strategies` to `artifacts/state/strategies`). It keeps only `status: active` specs (of `--purpose` when given — this is the `pick(purpose, regime)` `discover` calls), tests each `regime_required` against the live market read, and ranks the fitting ones by edge — validated expectancy for trading, recency for investment.
3. Present the **selected** strategy (and the ranked runners-up), plus the ones rejected for regime-fit and why. If **none fit** (exit 11) say so plainly — the disciplined move is to stand aside, not to force a misfit strategy; suggest GENERATE/OPTIMIZE if the library is thin. If there are **no active specs** (exit 12), there's nothing validated to run — point to GENERATE→VALIDATE.
4. Hand off: tell the user to run `/discover stocks --trade --strategy <selected>` to screen live candidates against it (or just `/discover`, which calls this pick itself when no strategy is named).

## Mode 4 — OPTIMIZE (learn from live trades; retire what's broken)

Close the loop with reality. `trade-tracker` writes a `result` block (realized R, exit reason) into each trade-idea artifact when it closes; those are the input. **Trading specs only** — an investment spec places no trades, so it has nothing to optimize; retire one manually (`status: inactive`) if its philosophy no longer holds.

1. Aggregate: `python3 <skill-dir>/scripts/aggregate_performance.py [--strategy <name>] --out artifacts/strategy-manager/YYYY-MM-DD/performance.json` (`--trades`/`--strategies` default to `artifacts/state/trades` and `artifacts/state/strategies`). It validates the execution evidence and net-P&L/R arithmetic required by `finance/contracts.md`, groups verified closes by `strategy`, and computes win rate, expectancy_R, R-weighted profit factor, and exit reasons. It recommends **KEEP / OPTIMIZE / DEACTIVATE**, or **REVIEW** when outcomes are excluded or unreadable (rules in reference.md: needs ≥ 10 closed trades to act; negative live expectancy → deactivate; positive but decaying well below backtest → optimize).
2. Re-run with `--update-spec` to write `live_performance` and its `drift_note` atomically. The script owns `eligible_for_selection`: true only for complete samples with at least ten execution-backed closes. PICK ignores legacy/unverified live scores and falls back to the backtest. Report every gap; reconcile legacy closes from broker history instead of filling missing evidence with estimates.
3. Act on the verdict:
   - **REVIEW** → reconcile excluded or unreadable outcomes first. Do not optimize or deactivate from the remaining subset.
   - **DEACTIVATE** → set `status: inactive`, `lifecycle.deactivated_at`/`deactivated_reason` (the script does this with `--update-spec`). The strategy stops being selectable. Explain that the observed net expectancy triggered the suspension policy; this sample does not prove a permanent loss of edge.
   - **OPTIMIZE** → propose a concrete rule change driven by the diagnostic (e.g. TIME exits dominate the losers → tighten `time_stop_sessions`; stops too tight → widen to structure). **Bump `version`, append an `optimization_log` entry, then re-run VALIDATE** — an optimized strategy must re-pass the backtest gate before it's active again. Never tune parameters and call it active without re-validation (that's in-sample curve-fitting).
   - **KEEP** → record the live numbers, no change.

## Alerts this skill raises (via `manage_alerts`)

When a spec goes stale — the live regime has drifted away from an active strategy's `regime_required`, or OPTIMIZE flags decaying live expectancy — raise a **`revalidate_due`** alert (`subject: {type: strategy, id: <name>}`, `created_by: strategy-manager`, `severity: watch`, `action.text` = why it's stale, `action.suggest: "/strategy-manager validate <name>"` or `optimize <name>`, `trigger: {check: strategy-manager}`, `dedup_key: revalidate-<name>`). `daily-brief` lists it among due actions until a re-validation clears it.

## How other skills consume this
`discover` runs only an **active, regime-fitting** spec — and when the user names none, it calls this skill's PICK mode to choose one (it has no default of its own); it reads the spec's `screening`/`entry`/`exit`/`sizing`. `deep-analysis` checks a ticker against an active strategy's regime/archetype; `trade-tracker` reads a trade's linked strategy `regime_required` for its regime-exit check and feeds closed trades back here for OPTIMIZE.
