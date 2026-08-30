---
name: discover
description: Find candidates worth acting on — to trade or to invest — across stocks, funds and sectors. Discover is the market's front door for "I don't have a specific name in mind": it runs a deterministic screen, triages the survivors, and hands you a ranked shortlist plus the three names that earn a full deep-dive. Use whenever the user asks to screen, scan the market, find swing trades or setups, find stocks/funds worth buying, rank sectors, "what should I buy", "anything worth trading this week", "which small-cap fund", "which sector is hot" — even without the word "screen". A named entity does NOT come here — it runs its own skill directly; discover is reached only when no entity is named (including from an entity skill invoked with no argument).
argument-hint: "[stocks|funds|sectors] [--trade|--invest] [--strategy <name>] [--universe <name>] [--top N] [capital ₹ | sector filter]"
allowed-tools: Read, Write, Bash, Skill, Agent, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-funds__*, mcp__plugin_everything-finance_finance-funds__*
---

# Discover — the market's front door

Discover answers one question: **"I don't have a name in mind — what's worth a closer look?"** It turns a vague ask into a ranked shortlist of concrete candidates by running the right deterministic screen for the purpose and kind against the current regime, triaging the survivors cheaply, and naming the three that earn the full deep-dive.

Screening is deterministic — ratios, prices, filters — and needs no LLM. Discover owns that screen and the routing around it. The *judgment* on each finalist (reading a concall, the multi-round bull/bear debate) belongs to the per-item skills; discover hands the finalists to them. Read `references/reference.md` for the trade-candidate grading checklist.

**Discover is stateless about its caller.** The same pipeline runs whether the user typed `/discover` or arrived from an entity skill invoked with no argument (`/deep-analysis` → `discover stocks --invest`, `/mf-analysis` → `discover funds`, `/sector-analysis` → `discover sectors`). Discover produces the shortlist and hands off; who consumes it — the user, or the entity skill continuing on the chosen name — is not discover's concern.

## Arguments

```
discover [stocks|funds|sectors]   # asset kind — default stocks
         [--trade | --invest]     # purpose; infer from phrasing, else ask one question
         [--strategy <name>]      # force a spec, skip the regime pick
         [--universe <name>]      # override the spec's universe (nifty500|microcap|fno|largecap20|…)
         [--top N]                # shortlist size (default 5; deep-dive the top 3)
         [capital ₹ | sector filter]
```

## The pipeline

1. **Resolve purpose × kind.** Kind defaults to `stocks`. Honour an explicit `--trade`/`--invest`; else infer from phrasing (trade: "swing / setup / trade this week"; invest: "invest / hold / quality / SIP"); if genuinely ambiguous, ask one question.
2. **Pick the spec.** `strategy-manager pick(purpose, kind, regime)` via `select_strategy.py --purpose <purpose>` (or load `--strategy <name>`). **No default, ever** — if pick returns nothing (no active spec of that purpose, or none fits the regime), **stand aside** and say so; point to `/strategy-manager generate` or `validate`. Funds are category-driven (their branch).
3. **Screen deterministically.** Resolve the universe via `get_universe` (the spec's `universe.source` or `--universe`), record the market with `get_market_context(mode="quick")`, and run the kind's screener → a ranked candidate pool written to file.
4. **Triage and shortlist** (per-kind branch below). For stocks/funds this runs the cheap `--quick` pass over the pool automatically; sectors are ranked deterministically with no LLM pass.
5. **Present the ranked shortlist**, name the **top 3** for a deep-dive, and ask to run it (see *Confirmation*). Raise `opportunity` / watchlist alerts.

---

## stocks · trade

The trade path's deliverable is an actionable signal, not a research report — so it screens and builds the signal, then stops.

1. **Fundamental screen** (`screening.fundamental`) — `run_fundamental_screen(query=<the spec's query verbatim>)` if `provider: tickertape`, else skip. Cap at `max_survivors`; tighten per the spec's note if exceeded. Save survivors to `artifacts/cache/gate_survivors.json`. On an empty/refused screen, reuse a `gate_survivors.json` < 7 days old, else pre-rank the universe by 6-month momentum and flag the skip. A refused query is a spec defect — report it.
2. **Technical screen** (`screening.technical`) — the coarse chart-state cut. `provider: tradingview` → `run_technical_screen` with the spec's filter rows; `provider: compute` (or TradingView down with `fallback_compute: true`) → the cut is reproduced from EOD OHLCV inside `run_strategy_screen`. Keep `NSE:` rows, strip the prefix, drop the BSE duplicate. Say so in data gaps when you fall back.
3. **Signal construction** — `run_strategy_screen(spec=<path>, symbols=<survivors>, years=2, capital=<₹>, out="artifacts/discover/YYYY-MM-DD.json")`. It builds entry / stop / target / RRR / qty per survivor, drops anything below `exit.min_rrr` or with a malformed stop (with the reason), and flags a below-average-volume candidate "weak" and ranks it last. `market_posture` governs sizing only (`risk_off` halves risk-per-trade). For a `next_resistance` target it uses a min-RRR proxy — confirm the real overhead resistance and say so.
4. **Present** the ranked candidate table via `assets/signal-report.html` (ticker, setup/strategy, entry/SL/target, RRR, volume, fundamental snapshot, indicator read, TradingView chart link), saved to `artifacts/discover/YYYY-MM-DD.html`, and summarise the top 3 in chat with a **Data gaps** section.
5. **Commit** — suggest the highest-conviction candidate (or top 2–3 if tied) and ask *"Track <TICKER>? (yes / pick another / no)"*. **Only on an explicit yes**, persist a trade-idea artifact (schema in `<plugin>/finance/contracts.md`): `artifacts/state/trades/<SYMBOL>-<YYYY-MM-DD>.yml`, `source_skill: discover`, `strategy: <name>` (never null), every field filled — especially `rationale` and `thesis_invalidation`. Confirm the path; tell the user to run `/trade-tracker`.

## stocks · invest

1. **Scan** — `run_stock_scan(spec=<investment spec path>, top=<N>)`: the business-quality query, intersected with the spec's universe, ranked by `ranking.metric`, capped to the pool. No entry/exit/sizing.
2. **Quick triage (automatic)** — fan out `deep-analysis <TICKER> --quick` over the pool in one parallel wave (each is the 1-agent elimination screen: structured data only → keep/reject + score + one-line lean). This is the red-flag catch a ratio filter can't make.
3. **Shortlist** — rank the keeps by their quick score; present them, and name the **top 3** for the deep-dive.
4. **Deep (on confirmation)** — `deep-analysis <TICKER> --deep` on the confirmed names — the full multi-round debate and verdict. Present the verdicts with their invalidation levels. Raise `opportunity` alerts for BUYs.

## funds · invest

1. **Scan** — `get_fund_scan(category=<user-named or regime-suggested SEBI sub-category>, market_context=<today's market-analysis artifact>)` → the gated, scored shortlist.
2. **Quick triage (automatic)** — `mf-analysis <scheme> --quick` per shortlisted fund (tool calls only, no sub-agents) — the descriptive digest.
3. **Shortlist** — present the ranked funds; name the **top 3** for the deep-dive.
4. **Deep (on confirmation)** — `mf-analysis <scheme> --deep` on the confirmed funds — the full two-pillar verdict.

## sectors · invest

1. **Scan** — `run_sector_screen(top=<N>)` (or a sector spec via `--strategy`): the sectoral indices ranked by RS-vs-Nifty and classified (Improving/Leading/Weakening/Lagging). Deterministic — no LLM quick pass. `get_market_context`'s `sectors.leaders`/`laggards` is a cheap cross-check.
2. **Shortlist** — present the ranked rotation in chat with the **top 3** sectors named for the deep-dive.
3. **Deep (on confirmation)** — fan out one `everything-finance:terminal-analyst` per confirmed sector running `sector-analysis <sector>` (no focus stock, output `artifacts/sector-analysis/YYYY-MM-DD/<sector>.md`). Each returns its `sector-block` digest + path; `Read` the files, don't paste the digests back.
4. **Rotation deck** — emit the render projection `artifacts/discover/<date>/sector-rotation.report.json` (shape: `skills/_report/scripts/fixtures/sector-analysis.sample.json` — cover rotation verdict, the RS grid colored by classification, a `deepdives` list per analyzed sector, a `picks` table from the per-sector leaders, a `drivers` synthesis, gaps/sources; a missing field renders as a labelled gap, never a fabricated number), then render:

   ```
   python3 skills/_report/scripts/render_report.py \
     --report-json artifacts/discover/<date>/sector-rotation.report.json \
     --template sector-analysis --out artifacts/discover/<date>/sector-rotation.html
   ```

   In chat: the 2–3 sentence rotation story (what leads, what's turning, what to avoid), then per analyzed sector its stance, the tailwind and headwind that matter, and its top pick.

---

## Confirmation

Discover runs the deterministic screen and the cheap quick triage **automatically** — that is how it earns a *tight* shortlist. It never launches the expensive deep-dive on its own: after presenting the ranked shortlist it names the top 3 and asks *"Deep-dive these 3? (all / pick / no)"*, then runs the respective deep mode only on the confirmed names. One gate, symmetric with the trade path's "track it?".

## Alerts this skill raises (via `manage_alerts`)

Set `dedup_key` so re-runs update in place. `created_by: discover`.

- **`price_cross` entry-trigger** (trade) — for a high-conviction candidate not yet filled, at the entry level (`subject: {type: stock, id: <SYMBOL>}`, `severity: watch`, `action.suggest: "/discover stocks --trade --strategy <name>"`, `dedup_key: entry-<SYMBOL>`).
- **`opportunity` (vetted)** — a candidate that clears the gates off an active spec (trade) or earns a deep BUY (invest): `severity: watch`, `action.text` = the one-line basis, `action.suggest: "/deep-analysis <SYMBOL>"`, `dedup_key: opp-<SYMBOL>`. This is the vetted feed daily-brief reads and auto-adds to the watchlist.
