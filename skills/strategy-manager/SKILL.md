---
name: strategy-manager
description: Own the full lifecycle of rule-based trading strategies for Indian markets — (1) GENERATE a complete strategy from a reference article you supply, (2) VALIDATE it by backtesting the spec on historical NSE daily data (the bundled Backtesting.py engine on TA-Lib indicators — win rate, expectancy, profit factor, max drawdown vs buy-and-hold) and mark it active when it passes, (3) PICK the active strategy that fits the current market regime, and (4) OPTIMIZE or retire strategies from live trade outcomes fed back by trade-tracker. Use whenever the user asks to design/build a strategy, to backtest or validate one, "check if this strategy actually works", the historical performance of a setup, "what strategy should I run now / in this market", review or tune a strategy's live performance, activate/deactivate a strategy, or after discover produces signals and the user questions the strategy's edge.
argument-hint: "[generate <article URL/file> | validate <name> [symbols] [years] | pick | optimize <name|all> | <name to inspect>]"
allowed-tools: WebFetch, Read, Write, Skill, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__run_fundamental_screen, mcp__plugin_everything-finance_finance-company__run_fundamental_screen, mcp__finance-workflow__*, mcp__plugin_everything-finance_finance-workflow__*
---

# Strategy Manager: generate → validate → pick → optimize

A strategy is a spec at `artifacts/state/strategies/<name>.yml` (schema:
`assets/strategy-spec.example.yml`, contract: `finance/contracts.md` → *Artifact: strategy spec*)
moving through `draft → active → inactive`. Regime fit is not a status: it is decided fresh at
pick time against the live tape.

**Method:** `methods/trading-system.md`, with `methods/technical.md` for the indicator study.
`references/engine.md` is how `run_backtest` trades a spec.

A spec's `purpose` is `trading` (the default: the full lifecycle, validated by backtest),
`investment` (for `discover stocks --invest`: `universe`, `screening.fundamental`, `ranking` and
`regime_required` only, validated by a completeness check, never optimized), or `fund` (a seed
that maps a market regime to `get_fund_scan` arguments for `discover funds`; it lives only in
`assets/seed-strategies/*-fund.yml` and is not generated or validated here).

The reference article the user supplies is the one source outside the tool table: a URL through
`WebFetch` or a file through `Read`. Generate requires it, and every trade rule in a spec traces
to it.

## Route

- an article, "design a strategy from this" → **generate**;
- "backtest / validate <name>", "does <name> work", right after generate → **validate**;
- "what should I trade now", "which strategy fits this market" → **pick**;
- "review / tune / optimize / retire <name>" → **optimize**;
- a bare name → inspect it (status, expectancy, live performance, regime fit now) and offer the
  next mode.

## Generate

If the article describes a screening philosophy rather than an entry/exit system ("high-ROCE
compounders"), emit an **investment** spec: `universe`, `screening.fundamental`, `ranking`
(`metric`, `top_n`), `regime_required`, `purpose: investment`
(example: `assets/seed-strategies/quality-momentum-invest.yml`), and skip the trading steps.

The seed library in `assets/seed-strategies/` holds drafts to copy into
`artifacts/state/strategies/`; they still have to pass validate (`assets/seed-strategies/README.md`
lists what each needs).

1. **Ingest the article.** With none given, stop and ask for a URL, file or pasted rules. Extract
   each element in the method's table, quoting the source.
2. **Read the market as context**: `get_market_context(mode="quick")`, and `sector-analysis` for
   leadership. This informs `regime_required`, never the trigger.
3. **Complete the system** from the method: sizing (1% risk default), heat cap, `regime_required`
   from the article's claimed conditions, and the `screening` block: the `fundamental` cut
   (provider `tickertape`, a query in Tickertape field names) and the `technical` cut
   (`tradingview` filter rows, or `compute` predicates for what TradingView cannot express, such
   as NR bars or Fibonacci zones). Encode the article's real exit: a trailing stop is
   `trail_atr: <mult>` with `target: trailing`; an indicator exit is `exit_signal: "<expr>"` in
   `entry.signal`'s grammar. `exit.target` takes a target name, never prose. Both the live screen
   and the backtest need an `entry.signal`; a prose trigger or `compute_filters` alone is refused.
4. **Write the draft** (`status: draft`, untradeable) so the study can run it. Double-quote every
   free-text value that can hold a `:`, `#`, parentheses or a path (`validated_by`, `target`,
   `deactivated_reason`, log notes), or the YAML silently changes shape.
5. **Indicator study, numeric, required.** `run_strategy_screen(spec=<path>,
   symbols="NTPC,TCS,SBIN", years=3)` reports, per symbol, the built signal or the exact
   expression that failed; confirm the condition that fired is the article's. A parse error here
   means fix the spec. Then check the first two or three trades in `run_backtest`'s log against
   their bars (the rule fired, the fill was the next open, the stop is right) and cite symbol,
   entry date, exit reason and R. When values differ from a chart, check dates, adjustment and
   warm-up first. Put `https://www.tradingview.com/symbols/NSE-<TICKER>/` in the rationale as a
   courtesy link. Record the result as `indicator_study`, `PENDING` until done.
6. **Emit**: `source_references` filled, `lifecycle.generated_at` set, `expectancy_assumptions` and
   `live_performance` null, and the rationale at `artifacts/strategy-manager/<date>/<name>.md`
   citing the article for each trade rule and the framework for the risk layer. Offer validate.

## Validate

Validate tests rules, not picks: "does this setup have an edge?", never "will this trade win?".

**Investment spec**, a completeness check: `universe.source` resolves through `get_universe`; the
provider is `tickertape` and a dry `run_fundamental_screen` on the query succeeds or names the
unsupported field; `ranking.metric` is one of `return_12m | return_6m | rs_vs_nifty`. All pass →
`status: active` with `lifecycle.validated_at`; otherwise it stays draft with the gap named.
Active means the screen runs, not that it picks good investments.

**Trading spec:**

1. `run_backtest` against the spec. Never pass market context into a historical run: today's
   regime fed into the past is look-ahead.
2. Map `expectancy_R` to a verdict with the method's table, including the sample-size override.
3. Say the honesty checks out loud: parameters fixed before the run; survivorship (`largecap20` is
   a 20-stock basket of current large caps, not the Nifty 50: name it so); regime concentration in
   the yearly breakdown; `open_trades_at_end`; the exit breakdown; buy-and-hold symbol by symbol;
   and, arriving from discover, what was not tested (`references/engine.md`).
4. Write `expectancy_assumptions` (`win_rate`, `expectancy_R`, `profit_factor`, `n_trades`,
   `validated_by` = the summary path).
5. Apply the activation gate and set `status`, saying which and why; on activation set
   `validated_at` and `activated_at`. A PENDING indicator study blocks activation.
6. Save the report to `artifacts/backtest/<spec-name>/<date>/report.md` beside the engine's files,
   ending: backtests describe the past; live edge degrades; position-sizing discipline is what
   survives.

## Pick

1. `get_market_context(mode="quick")`, so selection tests the regime every other skill sees.
2. `select_strategy(purpose=<trading|investment>, out="artifacts/strategy-manager/<date>/selection.json")`.
3. Present the selection, the ranked runners-up, and the specs rejected for regime fit with their
   reasons. `none_fit`: stand aside, and suggest generate or optimize if the library is thin.
   `no_active`: nothing validated to run; point to generate and validate.
4. Hand off: `/discover stocks --trade --strategy <selected>`.

## Optimize (trading specs only)

trade-tracker writes a `result` block into each trade idea it closes; those are the input.

1. `review_strategy_performance(strategy=<name>, out="artifacts/strategy-manager/<date>/performance.json")`.
   It accepts only execution-verified closes and recommends KEEP, OPTIMIZE, DEACTIVATE or REVIEW.
2. Re-run with `update_spec: true` to write `live_performance`; it marks the spec eligible for
   live-ranked selection only with ten or more verified closes. Report every gap; fix old closes
   from broker history, never by estimating.
3. Act on the verdict:
   - **REVIEW**: fix the excluded or unreadable trades first; change nothing on the rest.
   - **DEACTIVATE**: done by the update; say that negative live expectancy triggered it, which
     does not prove the edge is gone for good.
   - **OPTIMIZE**: propose one rule change from the exit-reason diagnosis, bump `version`, append
     an `optimization_log` entry, and re-validate before it can be active again.
   - **KEEP**: record the live numbers.

## Alerts

When an active spec's `regime_required` no longer fits the live regime, or optimize flags decaying
expectancy, a `revalidate_due` alert: `subject_type: strategy`, `subject_id: <name>`,
`created_by: strategy-manager`, `severity: watch`, `text` = why it is stale,
`suggest: "/strategy-manager validate <name>"`, `check: strategy-manager`,
`dedup_key: revalidate-<name>`.

## Who consumes a spec

`discover` runs only an active, regime-fitting spec and asks pick for one when none is named.
`trade-tracker` reads a trade's linked `regime_required` for its regime-exit check and feeds
closes back here.
