---
name: deep-analysis
description: Full multi-agent investment debate on a single Indian stock — six lenses (technical; financials from a fetch-once data-pack of annual reports & concalls; management integrity & skill; valuation via a story-driven DCF with a confidence grade; news sentiment; sector context), then bull vs bear researchers debate up to three rounds, and a portfolio-manager issues the verdict, synthesized into one readable report. Use whenever the user asks to analyze, research, deep-dive, evaluate, or form a view on a specific ticker or company name ("should I buy X?", "what do you think of Tata Motors?"), even if they don't say "deep analysis".
argument-hint: "TICKER (NSE symbol or company name)"
allowed-tools: WebFetch, Read, Write, Bash, Agent, mcp__playwright__*
---

# Deep Stock Analysis — multi-agent debate

Read `references/reference.md` for the fundamental-analysis grounding and the debate protocol. Resolve the argument to an NSE symbol first (screener.in search if ambiguous).

**Refer the earlier run first.** Call `paths.latest_prior("deep-analysis", TICKER)` — if a prior report exists, read it before launching the debate so this run builds on it rather than starting cold, and pass the prior verdict/levels to the agents as context. The synthesized report then opens with a **"What changed since `<date>`"** block (see Synthesize). No prior run is the normal first-time case.

**Sites for this skill only:** screener.in (financials, annual reports, concalls), yfinance + NSE (price), ET via Playwright/curl + Moneycontrol via real-Chrome Playwright or its `priceapi` JSON (news/quotes — WebFetch tool is blocked by both, browsers/curl work). TradingView not scraped (yfinance covers data; optional human chart link only).

## Orchestration

Forked subagents in four phases. Phase 0 fetches the fundamentals **once**; phase 1 runs the six analytical legs in parallel off it; phase 2 is the bull/bear debate (up to 3 rounds, early-stop); phase 3 decides.

| Phase | Agent | Input |
|---|---|---|
| 0 | `fundamentals-data` | ticker + output path — pulls the screener.in envelope, annual-report priority sections (incl. management signals), concall, and CMP into one sourced **data-pack**. The only fundamentals fetch in the run. |
| 1 (parallel) | `technical-analyst` | ticker + cached OHLCV if you already fetched any (saves the agent a fetch) |
| 1 (parallel) | `financials-analyst` | **data-pack path** — Varsity checklist + company overview + concall takeaways + relative valuation |
| 1 (parallel) | `management-analyst` | **data-pack path** — integrity gate + skill grade (does its own criminal/regulatory WebSearch) |
| 1 (parallel) | `valuation-analyst` | **data-pack path** — story-driven DCF + intrinsic range + **DCF-confidence grade** |
| 1 (parallel) | `news-sentiment` | ticker + company name |
| 1 (parallel) | `sector-analyst` | ticker + company name **as the focus stock**, plus the cached sector body when fresh (see *Sector leg* below) |
| 2 (loop ≤3) | `bull-researcher` / `bear-researcher` | the six phase-1 reports (round 1); the opposing side's previous-round report (round r>1) |
| 3 | `portfolio-manager` | everything incl. the full debate transcript — issues verdict: Buy / Accumulate / Hold / Avoid / Exit, with sizing and invalidation level |

The three fundamental legs (`financials`, `management`, `valuation`) **must run after** phase 0 — they Read the data-pack and never re-fetch, so all three reason off the same sourced numbers. Pass each agent only what it needs, as text — agents are forked and share no context. **Give each agent its output path**: the data-pack at `artifacts/tmp/staging/<TICKER>/fundamentals/data-pack.md`, agent reports at `artifacts/tmp/staging/<TICKER>/agents/<role>.md` (`paths.tmp_dir("staging")`) — `technical.md`, `financials.md`, `management.md`, `valuation.md`, `news.md`, `sector.md`, `bull-r<N>.md`, `bear-r<N>.md`, `verdict.md`. Each agent writes its **own raw report** and returns the same text. If phase 0 or any leg fails (scrape block, missing documents), continue with the gap explicitly stated; the portfolio-manager weighs missing evidence as uncertainty, not as neutral. If the management leg's **integrity gate is FAIL**, that overrides the rest — the verdict is AVOID regardless of numbers or valuation.

## Debate — up to 3 rounds, early-stop on convergence

Phase 2 is a loop, capped at 3 rounds:

- **Round 1:** `bull-researcher` and `bear-researcher` forked in parallel from the six phase-1 reports.
- **Round r > 1:** each re-forked, fed the *other* side's round r-1 report (and its own), and required to **add new load-bearing evidence or explicitly concede** — a restated argument is not a valid turn. Tell each agent its round number.
- **Convergence check** after each round (you, the orchestrator, in this session — no extra agent): *did either side introduce a new evidence-tied argument this round vs prior rounds?* If neither did, **stop**. Otherwise continue, up to round 3.
- Write each round's reports as `bull-r<N>.md` / `bear-r<N>.md`. Record how many rounds ran and why it stopped (converged / hit max) — the synthesis reports it.

The `portfolio-manager` then runs once on the full transcript (all rounds, both sides) plus the six phase-1 reports.

## Sector leg — shared cache

The sector body (RS, KPIs, tailwinds/headwinds, leaders/laggards, stance) is cached at `state/sectors/<sector>.md` and refreshed monthly; only the focus-stock positioning is stock-specific. Map the stock → sector (screener industry), then:

- **Cache fresh** (`paths.sector_cache_age_days(sector) ≤ 30`): pass the cached body **and** the focus ticker to `sector-analyst`; it reuses the body and computes only the stock's positioning — no re-fetch of RS/KPIs.
- **Missing or stale** (`None` or `> 30`): run `sector-analyst` full (sector + focus); write the **sector-level body** of its report to `paths.sector_cache_path(sector)` with frontmatter `generated: <today>` + `rs_class:`; then raise the next-refresh reminder via `lib/alerts.py`: `kind: sector_refresh_due`, `subject: {type: sector, id: <sector>}`, `trigger: {due: <today + 30d>}`, `created_by: deep-analysis`, `severity: watch`, `action.suggest: "/sector-analysis <sector>"`, `dedup_key: sector-refresh-<sector>`.

## Synthesize from the work papers

The work papers above are the agents' own output — you do **not** write them. The comprehensive report is built **from** them (the returned text, or re-read the staged files), not by pasting them.

Write the synthesized report to `artifacts/tmp/staging/<TICKER>.md` (`paths.tmp_dir("staging")`) using `assets/deep-analysis.md` (bundled with this skill). The template is a **readable synthesis** — you (the orchestrator) author every section in plain prose from the work papers, not by dumping agent output:

- **Summary placeholders you fill yourself:** CMP, COMPANY_NAME_SUFFIX (" · <Company>" or empty), ONE_LINE_THESIS, CALL_NARRATIVE, the verdict table (ENTRY_SL_TARGET/RRR/ALLOC_CAP/INVALIDATION/REVIEW_TRIGGER from the portfolio-manager), the six-lens At-a-Glance table (technical, financials, management, valuation, news, sector — each lens's stance + one-line read; the valuation line carries intrinsic MoS + DCF confidence, the management line carries the integrity/skill grade), COMPANY_OVERVIEW (the financials analyst's "Company overview" block — what the company does, segments & revenue mix, geography, products, moat), TOP_BULL_POINT (bull's argument 1), TOP_BEAR_POINT (bear's argument 1), SECTOR_STANCE_ONELINE, KEY_LEVEL (nearest decision level from the technical read), DATA_GAPS (union of all agents' gaps), DEBATE_ROUNDS (N rounds; stopped converged / hit max), AGENT_COUNT (count the legs actually run — phase-0 fetch + 6 phase-1 + bull/bear across rounds + PM).
- **Synthesized sections:** BULL_SYNTHESIS / BEAR_SYNTHESIS (distil each side's *strongest surviving* case across all rounds, evidence-tied), DECISIVE_POINTS (what the PM kept/discarded + dissent worth keeping), SECTOR_CONTEXT (the sector read + where the stock sits in its sector), and the Evidence-by-Lens blocks (condense each agent report to its load-bearing facts and levels — keep the numbers and cites, drop the boilerplate; the fundamental lens splits into financials / management / valuation).
- **"What changed since `<date>`" block (only when a prior run was found):** verdict then→now, the DCF fair-value shift, whether the thesis is intact, and any notable new risk. Omit the block entirely on a first-ever run.

The report **must contain a `## Telegram Brief` section** (≤ 10 lines: verdict, one bull point, one bear point, sector one-liner, key level, invalidation). The plugin's Stop hook archives `artifacts/tmp/staging/<TICKER>.md` → `artifacts/stocks/<TICKER>/YYYY-MM-DD/deep-analysis.md`, moves the work papers to `artifacts/stocks/<TICKER>/YYYY-MM-DD/deep-analysis/agents/`, and sends the brief to Telegram — do not send Telegram messages yourself and do not move the files.

**Persist the embedded leg artifacts.** The valuation leg runs the DCF engine and the management leg grades governance; write their outputs as discrete files in the same run-day folder — `artifacts/stocks/<TICKER>/YYYY-MM-DD/dcf.md` (+ `dcf.json`, from the valuation leg's engine run) and `management.md` (from the management leg) — so the stock's history is unified whether the artifact came from a standalone `/dcf-valuation`, `/management-quality`, or `/fundamental-analysis` run or from inside this debate, and `paths.latest_prior("dcf", TICKER)` / `latest_prior("management", TICKER)` find them all.

In chat, give the verdict, the two strongest opposing arguments, the sector stance, and the invalidation level — not the whole report. End with the standard risk note.

## Alerts this skill raises (via `lib/alerts.py`)

On a completed analysis, write watch-items for `daily-brief` (set `dedup_key` so a re-analysis updates in place):

- **`reanalyze_due`** — a date reminder to revisit the thesis (`trigger: {due: <today + N days>}`, N from the verdict's review cadence; `subject: {type: stock, id: <TICKER>}`, `created_by: deep-analysis`, `severity: watch`, `action.suggest: "/deep-analysis <TICKER>"`, `dedup_key: reanalyze-<TICKER>`).
- **`price_cross` invalidation** — the PM's invalidation level as a cheap trigger (`trigger: {metric: close, op: "<", level: <invalidation>}` for a long thesis; `severity: act`, `action.text` = "thesis invalidation level", `dedup_key: invalidate-<TICKER>`).
- On a **BUY** verdict, also raise an **`opportunity`** alert (the vetted feed daily-brief reads): `severity: watch`, `action.text` = the one-line thesis, `action.suggest: "/find-trade"` or `/trade-tracker <TICKER>`, `dedup_key: opp-<TICKER>`.
- **`sector_refresh_due`** — only when the sector leg refreshed a missing/stale cache (see *Sector leg*): the next monthly refresh reminder (`trigger: {due: <today + 30d>}`, `subject: {type: sector, id: <sector>}`, `action.suggest: "/sector-analysis <sector>"`, `dedup_key: sector-refresh-<sector>`).
