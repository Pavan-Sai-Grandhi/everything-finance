---
name: discover
description: >-
  Find candidates worth acting on — to trade or to invest — across stocks, funds and sectors. Discover is the market's front door for "I don't have a specific name in mind": it runs a deterministic screen, triages the survivors, and hands you a ranked shortlist plus the three names that earn a full deep-dive. Use whenever the user asks to screen, scan the market, find swing trades or setups, find stocks/funds worth buying, rank sectors, "what should I buy", "anything worth trading this week", "which small-cap fund", "which sector is hot" — even without the word "screen". A named entity does NOT come here — it runs its own skill directly; discover is reached only when no entity is named (including from an entity skill invoked with no argument).
argument-hint: "[stocks|funds|sectors] [--trade|--invest|--special-situations] [--strategy <name>] [--universe <name>] [--top N] [capital ₹ | sector filter]"
allowed-tools: Read, Write, Skill, Agent, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-funds__*, mcp__plugin_everything-finance_finance-funds__*, mcp__finance-workflow__*, mcp__plugin_everything-finance_finance-workflow__*
---

# Discover: the market's front door

Turns "I don't have a name in mind" into a ranked shortlist: the right deterministic screen for
the purpose and kind, run against today's regime, triaged cheaply, with the three names that earn
a full deep-dive. Screening is deterministic; the judgment on each finalist belongs to the
per-item skill it is handed to. Discover behaves the same whether the user typed `/discover` or
arrived from an entity skill invoked with no argument.

**Method:** `methods/trading-system.md` and `methods/technical.md` (the trade path),
`methods/special-situations.md`.

```
discover [stocks|funds|sectors]                        # kind, default stocks
         [--trade | --invest | --special-situations]   # purpose; infer from phrasing, else ask once
         [--strategy <name>] [--universe <name>] [--top N] [capital ₹ | sector filter]
```

## The pipeline

1. **Purpose and kind.** Kind defaults to stocks. Honour an explicit flag; else infer (trade:
   "swing", "setup", "trade this week"; invest: "invest", "hold", "quality", "SIP"); if genuinely
   ambiguous, ask one question.
2. **The spec.** `select_strategy(purpose=<trading|investment>)`, or the spec `--strategy` names.
   No default, ever: an `outcome` of `none_fit` or `no_active` means stand aside and say so,
   pointing to `/strategy-manager generate` or `validate`. Funds are category-driven (below).
3. **Screen**: resolve the universe with `get_universe` (the spec's `universe.source` or
   `--universe`), record the market with `get_market_context(mode="quick")`, and run the kind's
   screener into a ranked pool on file.
4. **Triage and shortlist**, per kind below.
5. **Present** the ranked shortlist, name the top three for a deep-dive, and ask: *"Deep-dive
   these 3? (all / pick / no)"*. Run the deep mode only on confirmed names; discover never
   launches the expensive dive on its own. Raise the alerts below.

## stocks · trade

The deliverable is an actionable signal, so the path stops at the signal.

1. **Fundamental cut** (`screening.fundamental`): `run_fundamental_screen(query=<the spec's query
   verbatim>)`, or no gate when the spec says `none`. A provider other than `tickertape` stops the
   spec with a source-policy gap. Cap at `max_survivors`. A required screen that returns nothing
   or is refused stops the spec: never reuse another run's survivors, loosen the criteria or fall
   back to momentum.
2. **Technical cut** (`screening.technical`): `provider: tradingview` runs `run_technical_screen`
   with the spec's filter rows; `provider: compute` (or TradingView down with
   `fallback_compute: true`) evaluates the spec's local entry rules with `run_strategy_screen`.
   The local path uses EMAs where TradingView uses SMAs, so report a fallback as a different
   screen. Keep `NSE:` rows, strip the prefix, drop BSE duplicates.
3. **Signal**: `run_strategy_screen(spec=<path>, symbols=<survivors>, years=2, capital=<₹>,
   out="artifacts/discover/<date>.json")`. It builds entry, stop, target, reward:risk and quantity
   per survivor, drops anything below `exit.min_rrr` or with a malformed stop (with the reason),
   and ranks a below-average-volume candidate last as "weak". `risk_off` halves the risk per
   trade. A `min_rrr` target is a multiple of risk, not a chart level, so check for resistance
   below it. A spec with only trailing or signal exits has no fixed target and is skipped; never
   invent one. Grade each candidate on the method's checklist.
4. **Present** the table through `assets/signal-report.html` (ticker, setup, entry/stop/target,
   reward:risk, volume, fundamental snapshot, indicator read, TradingView link), saved to
   `artifacts/discover/<date>.html`, with the top three and a Data gaps section in chat.
5. **Commit**: suggest the highest-conviction candidate and ask *"Track <TICKER>? (yes / pick
   another / no)"*. Only on an explicit yes, write the trade-idea artifact
   `artifacts/state/trades/<SYMBOL>-<YYYY-MM-DD>.yml` (`finance/contracts.md` → *Artifact:
   trade-idea*) with `source_skill: discover`, `strategy: <name>`, and every field filled,
   especially `rationale` and `thesis_invalidation`. Confirm the path and point to `/trade-tracker`.

## stocks · invest

1. **Scan**: `run_stock_scan(spec=<investment spec>, top=<N>)`: the spec's query, intersected
   with its universe and ranked by `ranking.metric`. No entry, exit or size: this picks what to
   deep-dive, not when to enter.
2. **Quick triage**: one `everything-finance:terminal-analyst` worker per candidate runs
   `deep-analysis <TICKER> --quick` with the candidate's scan data and criteria; run them one at a
   time if the host cannot run them in parallel. Each returns keep, reject or review.
3. **Shortlist**: keeps in scan order, `review` cases listed separately with the evidence they
   need, and the reason for each reject. Name up to three keeps; leave a slot empty rather than
   fill it with an unchecked name.
4. **Deep**, on confirmation: `deep-analysis <TICKER> --deep`. Present each verdict with its
   invalidation level.

## stocks · special situations

1. **Candidates**: the watchlist (`artifacts/state/watchlist.json`) plus any `--universe`. There is
   no market-wide event feed; a full-universe sweep is one filings call per name, so scope it and
   say so.
2. **Events**: one `get_filings(symbol, days=90)` per name. Its act-on items carry buybacks,
   demergers, mergers, delistings, open offers, rights and preferential issues, and its
   `corporate_actions` list the splits, bonuses and special dividends. Do not also call
   `get_corporate_actions`.
3. **Classify** each hit into the method's eight event types; drop the no-signal ones.
4. **Judge the value creation, not the event**: hand a survivor with a real case to
   `deep-analysis <TICKER> --quick`, then `--deep` on confirmation.

## funds · invest

1. **Scan**: `get_fund_scan(category=…, market_context=<today's market-analysis artifact>)`. With
   no category named, take `category`, `window`, `min_aum` and `top` from the fund seed whose
   `regime_required` fits the tape (`skills/strategy-manager/assets/seed-strategies/*-fund.yml`):
   `flexicap-allweather-fund` (any regime), `midcap-growth-fund` (risk-on),
   `largecap-defensive-fund` (weak or volatile). The seed only chooses arguments; the scan owns
   every gate and score.
2. **Quick triage**: `mf-analysis <scheme> --quick` per shortlisted fund.
3. **Shortlist** and name the top three; **deep** on confirmation: `mf-analysis <scheme> --deep`.

## sectors · invest

1. **Scan**: `run_sector_screen(top=<N>)` (or a sector spec via `--strategy`): sectoral indices
   ranked by relative strength and classified. Deterministic, no triage pass;
   `get_market_context`'s sector leaders and laggards are a cross-check.
2. **Shortlist** the rotation with the top three named.
3. **Deep**, on confirmation: one `everything-finance:terminal-analyst` per sector running
   `sector-analysis <sector>` (no focus stock, output
   `artifacts/sector-analysis/<date>/<sector>.md`). Read the files, do not paste the digests back.
4. **Rotation deck**: write `artifacts/discover/<date>/sector-rotation.report.json`, shaped like
   `finance/report/fixtures/sector-analysis.sample.json`: the rotation verdict, the RS grid by
   class, one deep-dive per sector led by its `story` class and growth story in one sourced
   sentence, a picks table from the sector leaders, the drivers, and the gaps and sources. Render
   it with `render_report(template="sector-analysis", out=…/sector-rotation.html)`. In chat: the
   rotation story in two or three sentences, then per sector its stance, the tailwind and
   headwind that matter, and its top pick.

## Alerts (`manage_alerts`, `created_by: discover`)

- **Entry trigger** (trade): `price_cross` at the entry level for a high-conviction candidate not
  yet filled; `severity: watch`, `suggest: "/discover stocks --trade --strategy <name>"`,
  `dedup_key: entry-<SYMBOL>`.
- **Vetted opportunity**: a candidate that clears the gates off an active spec, or earns a deep
  BUY, or a special situation that clears the deep read; `kind: opportunity`, `severity: watch`,
  `text` = the one-line basis, `suggest: "/deep-analysis <SYMBOL>"`, `dedup_key: opp-<SYMBOL>`
  (`specialsit-<SYMBOL>` for a special situation). daily-brief reads these as its vetted feed.
