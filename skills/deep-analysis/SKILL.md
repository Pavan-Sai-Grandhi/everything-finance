---
name: deep-analysis
description: Full multi-agent investment debate on a single Indian stock, at one of three depths — six lenses (technical; financials from a fetch-once data-pack of annual reports & concalls; management integrity & skill; valuation triangulating a story-driven DCF with relative multiples; news sentiment; sector context), then bull vs bear researchers debate, and a portfolio-manager issues the verdict, synthesized into one readable report. Use whenever the user asks to analyze, research, deep-dive, evaluate, or form a view on a specific ticker or company name ("should I buy X?", "what do you think of Tata Motors?"), even if they don't say "deep analysis".
argument-hint: "TICKER (NSE symbol or company name) [--quick | --deep]"
allowed-tools: WebFetch, Read, Write, Bash, Agent, mcp__playwright__*, mcp__indmoney__*, mcp__kite__*, mcp__upstox__*
---

# Deep Stock Analysis — multi-agent debate

Read `references/reference.md` for the fundamental-analysis grounding, the three depth modes, and the debate protocol. Resolve the argument to an NSE symbol first (screener.in search if ambiguous).

## Depth mode — resolve first

This skill runs at three depths so the common question stops paying full-diligence cost. **Resolve the mode before anything else**, then size the rest of the run to it.

| Mode | Fetch | Legs | Debate | ~Agents |
|---|---|---|---|---|
| `quick` | **lite** data-pack (screener envelope only) | technical, financials, valuation | 1 `contest-researcher` (single pass) | ~4 |
| `standard` *(default)* | full fetch-once data-pack | all 6 | round 1, escalate to round 2 only on genuine divergence | ~7–8 |
| `deep` | full fetch-once data-pack | all 6 | up to 3 rounds with convergence check | ~12 |

Resolution (first match wins) — run the helper, then layer the broker check it can't do:

1. Check the broker first: if a broker MCP is connected (`mcp__indmoney__*` / `mcp__kite__*` / `mcp__upstox__*`), look up whether the resolved ticker is a **live holding or open position**. Script code can't call MCP tools, so this is your job; pass the result to the helper.
2. `python3 scripts/resolve_mode.py --args "<the raw argument string>" --symbol <TICKER> [--broker-holding]` → `{mode, reason}`. It applies: **explicit `--quick`/`--deep` wins** (over the holding escalation too); else a **holding / open-trade auto-escalates to `deep`**; else **`standard`**. It checks the open-trade artifact half (`state/trades/<SYMBOL>-*.yml` `status: open`) itself.
3. When the holding auto-escalation fires (no explicit flag), print the one-line note: `Held position → running deep analysis (override with --quick).`

Record `{mode, reason}` — the synthesis reports both.

**Refer the earlier run first.** Call `paths.latest_prior("deep-analysis", TICKER)` — if a prior report exists, read it before launching the debate so this run builds on it rather than starting cold, and pass the prior verdict/levels to the agents as context. The synthesized report then opens with a **"What changed since `<date>`"** block (see Synthesize). No prior run is the normal first-time case.

**Sites for this skill only:** screener.in (financials, annual reports, concalls), yfinance + NSE (price), ET via Playwright/curl + Moneycontrol via real-Chrome Playwright or its `priceapi` JSON (news/quotes — WebFetch tool is blocked by both, browsers/curl work). TradingView not scraped (yfinance covers data; optional human chart link only).

## Orchestration

Forked subagents in four phases. Phase 0 fetches the fundamentals **once**; phase 1 runs the analytical legs in parallel off it; phase 2 is the debate; phase 3 decides. **The fan-out scales to the mode** — see the per-mode column.

| Phase | Agent | Input | Modes |
|---|---|---|---|
| 0 | `fundamentals-data` | ticker + output path + **fetch depth** (`lite` in `quick`, `full` otherwise) — pulls the screener.in envelope and CMP always; in `full` also the annual-report priority sections (incl. management signals) + concall. One sourced **data-pack**; the only fundamentals fetch in the run. | all |
| 1 (parallel) | `technical-analyst` | ticker + cached OHLCV if you already fetched any (saves the agent a fetch) | all |
| 1 (parallel) | `financials-analyst` | **data-pack path** — Varsity checklist + company overview + concall takeaways + relative valuation | all |
| 1 (parallel) | `valuation-analyst` | **data-pack path** + **mode** — DCF + relative multiples → combined stance + **DCF-confidence grade** | all |
| 1 (parallel) | `management-analyst` | **data-pack path** — integrity gate + skill grade (does its own criminal/regulatory WebSearch) | standard, deep |
| 1 (parallel) | `news-sentiment` | ticker + company name | standard, deep |
| 1 (parallel) | `sector-analyst` | ticker + company name **as the focus stock**, plus the cached sector body when fresh (see *Sector leg* below) | standard, deep |
| 2 (`quick`) | `contest-researcher` | the leg report **paths** (technical, financials, valuation) | quick |
| 2 (`standard`/`deep`) | `bull-researcher` / `bear-researcher` | the phase-1 report **paths** (round 1); the opposing side's previous-round report (round r>1) | standard, deep |
| 3 | `portfolio-manager` | the leg report **paths** + the full debate transcript paths — issues verdict: Buy / Accumulate / Hold / Avoid / Exit, with sizing and invalidation level | all |

The fundamental legs (`financials`, `valuation`, and — in `standard`/`deep` — `management`) **must run after** phase 0 — they Read the data-pack and never re-fetch, so all reason off the same sourced numbers. Pass each agent only what it needs — agents are forked and share no context. **Give each agent its output path**: the data-pack at `artifacts/tmp/staging/<TICKER>/fundamentals/data-pack.md`, agent reports at `artifacts/tmp/staging/<TICKER>/agents/<role>.md` (`paths.tmp_dir("staging")`) — `technical.md`, `financials.md`, `management.md`, `valuation.md`, `news.md`, `sector.md`, `contest.md`, `bull-r<N>.md`, `bear-r<N>.md`, `verdict.md`.

**IO hygiene (all modes).** Each agent `Write`s its **full report to its file** and returns to you **only a compact digest** (its structured top block + path), never the full body. Downstream agents (`contest` / `bull` / `bear` / `portfolio-manager`) and your synthesis receive **paths** and Read what they need in their own context — you never hold all six full reports at once. This is the single biggest cost lever after not running all 12 agents.

If phase 0 or any leg fails (scrape block, missing documents), continue with the gap explicitly stated; the portfolio-manager weighs missing evidence as uncertainty, not as neutral. If the management leg's **integrity gate is FAIL** (`standard`/`deep`), that overrides the rest — the verdict is AVOID regardless of numbers or valuation.

## Debate — by mode

Phase 2's shape depends on the resolved mode.

**`quick` — single-pass contest.** Fork one `contest-researcher` with the three leg paths. It reads them, writes `contest.md` (strongest bull case, strongest bear case, balance-of-evidence lean), and returns the digest. No bull/bear loop. If its lean is **`genuinely split`**, the synthesis appends a one-line suggestion to re-run `standard`/`deep` — it does **not** auto-escalate (the user chose quick).

**`standard` — round 1 + conditional round 2.** Fork `bull-researcher` and `bear-researcher` in parallel (round 1) from the phase-1 paths. Then decide escalation deterministically from their two digests' `debate-block`s (axis + claim + concession): `python3 scripts/escalation.py --bull <bull-r1.json> --bear <bear-r1.json>` → `{escalate, reason}`. **Escalate to round 2 only on genuine divergence** (both top points on the *same* verdict-relevant axis, distinct evidence-tied claims, neither conceded); otherwise stop at round 1 and go to the PM. (Write each digest's `debate-block` fields to a small JSON for the helper, or apply the same rule by hand — the helper is the source of truth.) One round is the baseline; a second is opt-in on evidence.

**`deep` — up to 3 rounds, early-stop on convergence.** The full loop, capped at 3:
- **Round 1:** `bull` and `bear` in parallel from the phase-1 paths.
- **Round r > 1:** each re-forked, fed the *other* side's round r-1 report (and its own), required to **add new load-bearing evidence or explicitly concede** (`new_evidence: false` is not a valid turn). Tell each agent its round number.
- **Convergence check** after each round (you, the orchestrator — no extra agent): did either side introduce a *new* evidence-tied argument this round (`new_evidence: true`, no concession)? If neither did, **stop**. Otherwise continue, up to round 3.

Write each round's reports as `bull-r<N>.md` / `bear-r<N>.md`. Record how many rounds ran and why it stopped (converged / escalated / hit max / single contest) — the synthesis reports it.

The `portfolio-manager` then runs once on the full transcript (the contest, or all debate rounds) plus the leg report paths.

## Sector leg — shared cache

The sector body (RS, KPIs, tailwinds/headwinds, leaders/laggards, stance) is cached at `state/sectors/<sector>.md` and refreshed monthly; only the focus-stock positioning is stock-specific. Map the stock → sector (screener industry), then:

- **Cache fresh** (`paths.sector_cache_age_days(sector) ≤ 30`): pass the cached body **and** the focus ticker to `sector-analyst`; it reuses the body and computes only the stock's positioning — no re-fetch of RS/KPIs.
- **Missing or stale** (`None` or `> 30`): run `sector-analyst` full (sector + focus); write the **sector-level body** of its report to `paths.sector_cache_path(sector)` with frontmatter `generated: <today>` + `rs_class:`; then raise the next-refresh reminder via `lib/alerts.py`: `kind: sector_refresh_due`, `subject: {type: sector, id: <sector>}`, `trigger: {due: <today + 30d>}`, `created_by: deep-analysis`, `severity: watch`, `action.suggest: "/sector-analysis <sector>"`, `dedup_key: sector-refresh-<sector>`.

## Synthesize from the work papers

The work papers above are the agents' own output — you do **not** write them. The comprehensive report is built **from** them (the digests they returned, then re-read the staged file for any detail you need), not by pasting them.

Write the synthesized report to `artifacts/tmp/staging/<TICKER>.md` (`paths.tmp_dir("staging")`) using `assets/deep-analysis.md` (bundled with this skill). The template is a **readable synthesis** — you (the orchestrator) author every section in plain prose from the work papers, not by dumping agent output:

- **Mode header & quick banner:** record the resolved `MODE` and the one-line `MODE_REASON`. In `quick`, open the report with the banner **"Quick read — not full diligence"** and name what was skipped (annual report, concall, and the management / news / sector lenses) so the read is never mistaken for a full debate.
- **Summary placeholders you fill yourself:** CMP, COMPANY_NAME_SUFFIX (" · <Company>" or empty), ONE_LINE_THESIS, CALL_NARRATIVE, the verdict table (ENTRY_SL_TARGET/RRR/ALLOC_CAP/INVALIDATION/REVIEW_TRIGGER from the portfolio-manager), the At-a-Glance lens table — in `standard`/`deep` all six lenses (technical, financials, management, valuation, news, sector), in `quick` the three that ran (technical, financials, valuation) with the rest marked "not run (quick)"; each lens's stance + one-line read; the valuation line carries the **combined stance + DCF confidence**, the management line the integrity/skill grade. COMPANY_OVERVIEW (the financials analyst's "Company overview" block), TOP_BULL_POINT / TOP_BEAR_POINT (from the debate or the contest's two sides), SECTOR_STANCE_ONELINE (or "not run (quick)"), KEY_LEVEL (nearest decision level from the technical read), DATA_GAPS (union of all agents' gaps, plus the lenses skipped in `quick`), DEBATE_ROUNDS (`single contest (quick)`, or `N rounds; stopped converged / escalated / hit max`), AGENT_COUNT (count the legs actually run — phase-0 fetch + the legs + the debate agents + PM).
- **Synthesized sections:** BULL_SYNTHESIS / BEAR_SYNTHESIS (distil each side's *strongest surviving* case across all rounds — or the contest's two sides — evidence-tied), DECISIVE_POINTS (what the PM kept/discarded + dissent worth keeping), SECTOR_CONTEXT (the sector read + where the stock sits in its sector; omit in `quick`), and the Evidence-by-Lens blocks (condense each agent report to its load-bearing facts and levels — keep the numbers and cites, drop the boilerplate; the fundamental lens splits into financials / management / valuation).
- **"What changed since `<date>`" block (only when a prior run was found):** verdict then→now, the DCF fair-value shift, whether the thesis is intact, and any notable new risk. Omit the block entirely on a first-ever run.

The report **must contain a `## Telegram Brief` section** (≤ 10 lines: verdict, one bull point, one bear point, sector one-liner, key level, invalidation). The plugin's Stop hook archives `artifacts/tmp/staging/<TICKER>.md` → `artifacts/stocks/<TICKER>/YYYY-MM-DD/deep-analysis.md`, moves the work papers to `artifacts/stocks/<TICKER>/YYYY-MM-DD/deep-analysis/agents/`, and sends the brief to Telegram — do not send Telegram messages yourself and do not move the files.

**Persist the embedded leg artifacts.** The valuation leg runs the DCF engine (every mode) and, in `standard`/`deep`, the management leg grades governance; write their outputs as discrete files in the same run-day folder — `artifacts/stocks/<TICKER>/YYYY-MM-DD/dcf.md` (+ `dcf.json`, from the valuation leg's engine run) and `management.md` (when the management leg ran) — so the stock's history is unified whether the artifact came from a standalone `/dcf-valuation`, `/management-quality`, or `/fundamental-analysis` run or from inside this debate, and `paths.latest_prior("dcf", TICKER)` / `latest_prior("management", TICKER)` find them all.

In chat, give the verdict, the two strongest opposing arguments, the sector stance, and the invalidation level — not the whole report. End with the standard risk note.

## Alerts this skill raises (via `lib/alerts.py`)

On a completed analysis, write watch-items for `daily-brief` (set `dedup_key` so a re-analysis updates in place):

- **`reanalyze_due`** — a date reminder to revisit the thesis (`trigger: {due: <today + N days>}`, N from the verdict's review cadence; `subject: {type: stock, id: <TICKER>}`, `created_by: deep-analysis`, `severity: watch`, `action.suggest: "/deep-analysis <TICKER>"`, `dedup_key: reanalyze-<TICKER>`).
- **`price_cross` invalidation** — the PM's invalidation level as a cheap trigger (`trigger: {metric: close, op: "<", level: <invalidation>}` for a long thesis; `severity: act`, `action.text` = "thesis invalidation level", `dedup_key: invalidate-<TICKER>`).
- On a **BUY** verdict, also raise an **`opportunity`** alert (the vetted feed daily-brief reads): `severity: watch`, `action.text` = the one-line thesis, `action.suggest: "/find-trade"` or `/trade-tracker <TICKER>`, `dedup_key: opp-<TICKER>`.
- **`sector_refresh_due`** — only when the sector leg refreshed a missing/stale cache (see *Sector leg*): the next monthly refresh reminder (`trigger: {due: <today + 30d>}`, `subject: {type: sector, id: <sector>}`, `action.suggest: "/sector-analysis <sector>"`, `dedup_key: sector-refresh-<sector>`).
