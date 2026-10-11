---
name: discover
description: >-
  Find candidates worth acting on — to trade or to invest — across stocks, funds and sectors. Discover is the market's front door for "I don't have a specific name in mind": it runs a deterministic screen, triages the survivors, and hands you a ranked shortlist plus the three names that earn a full deep-dive. Use whenever the user asks to screen, scan the market, find swing trades or setups, find stocks/funds worth buying, rank sectors, "what should I buy", "anything worth trading this week", "which small-cap fund", "which sector is hot" — even without the word "screen". A named entity does NOT come here — it runs its own skill directly; discover is reached only when no entity is named (including from an entity skill invoked with no argument).
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
         [--trade | --invest | --special-situations]   # purpose; infer from phrasing, else ask one question
                                  # --special-situations (stocks): corporate-action scan, see that mode below
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

1. **Fundamental screen** (`screening.fundamental`) — `tickertape` → `run_fundamental_screen(query=<the spec's query verbatim>)`; explicit `none` → no quality gate by design. `screener_in` is retired: it is approved only for document discovery, so stop that spec with a source-policy gap. Cap at `max_survivors`; use only survivors from this exact spec and request. On an empty/refused required screen, stop this spec's trade pipeline; do not reuse another survivor file, weaken its criteria, or substitute momentum. An unqualified research watchlist cannot become an actionable trade from that run.
2. **Technical screen** (`screening.technical`) — the coarse chart-state cut. `provider: tradingview` → `run_technical_screen` with the spec's filter rows; `provider: compute` (or TradingView down with `fallback_compute: true`) → evaluate the explicit local entry rules on EOD OHLCV using `run_strategy_screen`. This does not establish equivalence with provider filters (SMA and EMA cuts can differ); report the changed coverage and do not treat it as validation of the original provider cut. Keep `NSE:` rows, strip the prefix, drop the BSE duplicate. Say so in data gaps when you fall back.
3. **Signal construction** — `run_strategy_screen(spec=<path>, symbols=<survivors>, years=2, capital=<₹>, out="artifacts/discover/YYYY-MM-DD.json")`. It builds entry / stop / target / RRR / qty per survivor, drops anything below `exit.min_rrr` or with a malformed stop (with the reason), and flags a below-average-volume candidate "weak" and ranks it last. `market_posture` governs sizing only (`risk_off` halves risk-per-trade). For `min_rrr` or legacy `next_resistance`, the target is a risk-multiple proxy — confirm real overhead resistance and say so. Dynamic-only exit specs return a labelled skip because there is no fixed objective; do not invent a target to bypass it.
4. **Present** the ranked candidate table via `assets/signal-report.html` (ticker, setup/strategy, entry/SL/target, RRR, volume, fundamental snapshot, indicator read, TradingView chart link), saved to `artifacts/discover/YYYY-MM-DD.html`, and summarise the top 3 in chat with a **Data gaps** section.
5. **Commit** — suggest the highest-conviction candidate (or top 2–3 if tied) and ask *"Track <TICKER>? (yes / pick another / no)"*. **Only on an explicit yes**, persist a trade-idea artifact (schema in `<plugin>/finance/contracts.md`): `artifacts/state/trades/<SYMBOL>-<YYYY-MM-DD>.yml`, `source_skill: discover`, `strategy: <name>` (never null), every field filled — especially `rationale` and `thesis_invalidation`. Confirm the path; tell the user to run `/trade-tracker`.

## stocks · invest

1. **Scan** — `run_stock_scan(spec=<investment spec path>, top=<N>)`: the spec's query through Tickertape, intersected with its named universe and ranked by `ranking.metric`, capped to the pool. No entry/exit/sizing. Unsupported providers fail before fetching.
2. **Quick triage (automatic)** — use one `everything-finance:terminal-analyst` worker per pool candidate, running `deep-analysis <TICKER> --quick` with the candidate’s scan evidence and criteria. The worker performs the pass locally without nested dispatch. Run sequentially if the user requests it or concurrency is unavailable. Each returns keep/reject/review with cited reasons, gaps and a path.
3. **Shortlist** — retain `run_stock_scan` order among the keeps; never re-rank on legacy quick scores. Present `review` cases separately with the evidence needed, and explain supported rejects. Name up to **3 keeps** for the deep-dive; do not fill vacant slots with unverified candidates.
4. **Deep (on confirmation)** — `deep-analysis <TICKER> --deep` on the confirmed names — the full multi-round debate and verdict. Present the verdicts with their invalidation levels. Raise `opportunity` alerts for BUYs.

## stocks · special-situations

Event-driven, not ratio-driven — a corporate-action scan, not a fundamental screen. Follow
`assets/special-situations-checklist.md` (SOIC event taxonomy + per-event signal + discipline).

1. **Candidate set** — the watchlist (`artifacts/state/watchlist.json`) plus any `--universe` named.
   A full-universe per-name sweep is one filings call each — scope it and flag the cost.
2. **Pull events per name** — one `get_filings(symbol, days=90)` call: buyback/demerger/merger/
   delisting/open offer/rights/preferential land as `act-on`, and its `corporate_actions` list carries
   split/bonus/special dividend. Do not also call `get_corporate_actions`. There is no market-wide
   event feed; the scan is this per-symbol loop.
3. **Classify** into the checklist's eight event types; drop no-signal bonus/splits.
4. **Judge the value creation, not the event** — hand survivors with a real case to
   `deep-analysis <TICKER> --quick`, then `--deep` on confirmation. Raise `opportunity` alerts
   (`dedup_key: specialsit-<SYMBOL>`) for those that clear.

## funds · invest

1. **Scan** — `get_fund_scan(category=<user-named or regime-suggested SEBI sub-category>, market_context=<today's market-analysis artifact>)` → the gated, scored shortlist. When the user hasn't named a category, take `category` (and `window`/`min_aum`/`top`) from the **fund spec whose `regime_required` fits the live tape** — the cycle→category mapping lives in `strategy-manager/assets/seed-strategies/*-fund.yml` (`purpose: fund`): `flexicap-allweather-fund` (core, any regime), `midcap-growth-fund` (risk-on), `largecap-defensive-fund` (weak/volatile). The spec only chooses the scan arguments; get_fund_scan still owns every gate and score.
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
