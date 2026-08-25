---
name: deep-analysis
description: Full multi-agent investment debate on a single Indian stock — six lenses (technical; the numbers, with the annual report and concall read directly; management integrity & skill; valuation triangulating a story-driven DCF with relative multiples; news sentiment; sector context), then bull vs bear researchers debate, and a portfolio-manager issues the verdict, synthesized into one readable report. Use whenever the user asks to analyze, research, deep-dive, evaluate, or form a view on a specific ticker or company name ("should I buy X?", "what do you think of Tata Motors?"), even if they don't say "deep analysis". Its fundamentals-only mode is also the home of the fundamental read without the debate — "are the fundamentals good?", "is X fundamentally sound?", "fundamental analysis of Y".
argument-hint: "TICKER (NSE symbol or company name) [--quick | --deep | --fundamentals]"
allowed-tools: Read, Write, Bash, Agent, mcp__indmoney__*, mcp__plugin_everything-finance_indmoney__*, mcp__kite__*, mcp__plugin_everything-finance_kite__*, mcp__upstox__*, mcp__plugin_everything-finance_upstox__*, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*
---

# Deep Stock Analysis — multi-agent debate

Read `references/reference.md` — it owns how the six lenses combine into one verdict and the debate protocol. Resolve the argument to an NSE symbol first; `get_company_fundamentals` on the candidate symbol confirms the company name.

## Run mode — resolve first

**Resolve the mode before anything else**, then size the rest of the run to it.

| Mode | Primary documents | Legs | Debate | ~Agents |
|---|---|---|---|---|
| `quick` | not fetched — ratios and CMP only | technical, financials, valuation | 1 `everything-finance:contest-researcher` (single pass) | ~4 |
| `standard` *(default)* | warmed by you in phase 0 | all 6 | up to 2 rounds, the helper decides | ~7–8 |
| `deep` | warmed by you in phase 0 | all 6 | up to 3 rounds, the helper decides | ~12 |
| `fundamentals` | warmed by you in phase 0 | financials, management, valuation | none | 3 |

Resolution — the two reads the helper can't make, then the helper itself, which decides first-match-wins:

1. **A fundamentals-only request is the `--fundamentals` flag.** "Are the fundamentals good?", "is X fundamentally sound?", "fundamental analysis of X" ask for the numbers, the people and the price without the debate — append `--fundamentals` to the argument string you hand the helper.
2. **Check the broker, across every connected server.** Whether the resolved ticker is a **live holding or open position** decides the depth, so one server erroring is not an answer: try `mcp__indmoney__*`, then `mcp__upstox__*`, then `mcp__kite__*`, and stop at the first that returns. The result is `yes` (found in any book), `no` (at least one server answered and the ticker is not in it), or `unknown` (none connected, or every connected one errored). Script code can't call MCP tools, so this is your job. Keep the qty, avg cost and unrealised % where you get them — the portfolio-manager needs them in phase 3.
3. `python3 <plugin>/skills/deep-analysis/scripts/resolve_mode.py --args "<the raw argument string>" --symbol <TICKER> --holding <yes|no|unknown>` → `{mode, reason, gaps}`. It applies: **an explicit flag wins** (over the holding escalation too, and `--fundamentals` over the two depth flags — it names the question, not the rigour); else a **holding / open-trade auto-escalates to `deep`**; else **`standard`**. It checks the open-trade artifact half (`state/trades/<SYMBOL>-*.yml` `status: open`) itself.
4. When the holding auto-escalation fires (no explicit flag), print the one-line note: `Held position → running deep analysis (override with --quick).`

Record `{mode, reason, gaps}` — the synthesis reports the first two and folds the third into DATA_GAPS.

**Refer the earlier run first.** Call `get_prior_run(skill="deep-analysis", subject=TICKER)` — `skill="fundamentals"` in `fundamentals`, so each mode builds on its own history — if a prior report exists, read it before launching the debate so this run builds on it rather than starting cold, and pass the prior verdict/levels to the legs as context. The synthesized report then opens with a **"What changed since `<date>`"** block (see Synthesize). No prior run is the normal first-time case.

**Sources for this orchestrator only:** `finance-company` — `get_company_fundamentals` (symbol and company name) and `get_documents` (the phase-0 warm-up); `finance-market` — `get_market_context`, `get_quote` (CMP for the report header) and `get_prior_run`. Every other number in the report arrives inside a leg's digest or its file; the legs own their own fetching.

## Orchestration

Four phases. Phase 0 is two calls you make yourself; phase 1 is all six legs in **one** parallel wave; phase 2 is the debate; phase 3 decides. **The fan-out scales to the mode** — see the per-mode column.

**Your context is the run's largest single cost**, because every turn re-reads all of it. Two rules keep it small. The phase table below **is** the plan — do not mirror it into a task list. And **a wave is launched in one message that ends the turn**: issue the `Agent` calls, say in one line what is running, and stop there. The harness re-invokes you when an agent completes, so there is nothing to wait for and nothing to poll — a filler command, a no-op shell call and a scheduled wakeup each buy a full context re-read and no information. An arriving notification is likewise not a cue to write: summarise nothing until the wave is complete, then move straight to the next phase.

**Scripts and assets are under this skill's own base directory**, given to you in the header above. Use it — do not search the filesystem for the plugin.

### Phase 0 — no agent, you run it

- **Market context.** `get_market_context(mode="quick")`. Costs nothing after the first caller of the day. Pass `market_posture` + `volatility.band` to the `portfolio-manager` (they govern **sizing**, never the verdict), and the stock's cap-tier `valuation.stance` to the valuation leg as context for its relative-multiple read.
- **Primary documents.** `get_documents(TICKER, annual_reports=3)` — every mode but `quick`. It returns rows of `{kind, label, url, publisher, text_path, text_chars, text_lines, extracted_by, cached, outline}`: **paths, never text**. Hand each row's `text_path` *and* its `outline` — the map from each note to its line numbers — to the legs that read documents, so a leg reads the lines it needs instead of searching a report that runs to tens of thousands of lines. You never open one yourself.
- **The peer set.** `get_company_fundamentals(TICKER)` already returned `peers`, each row carrying `ttm_pe` and `pb`. Pass that list to **both** the valuation and sector legs, so the peer-median multiple and the "leader or laggard in its group" read describe the same companies. Neither leg builds its own.

Fetch-once is a **cache guarantee, not an ordering rule**: `get_documents` caches a converted document permanently and `get_company_fundamentals` caches for the day, so every leg that calls them lands on the same bytes whatever order it ran in. That is why phase 1 is a single wave.

In `quick`, skip the document warm-up and tell each leg `documents: none (quick — ratios and CMP only)`; it labels every check that needed a primary document as a gap. The valuation leg is the one exception — the annual report's tax note is its only acceptable source for `tax_rate`, so it pulls that one document rather than working from an unsourced rate.

### Phase 1 — six legs, one parallel wave

Each leg is a **skill run inside a generic profile agent** — issue every `Agent` call in one message. The dispatch names the skill, its mode where the skill has one, the output path, the ticker, and the leg's inputs.

| Leg skill | Profile | Inputs beyond the ticker | Modes |
|---|---|---|---|
| `technical-analysis` | `everything-finance:terminal-analyst` | — (it pulls its own candles) | quick, standard, deep |
| `financial-analysis` | `everything-finance:terminal-analyst` | company name + the document `text_path`s and `outline`s | all |
| `valuation-analysis` | `everything-finance:terminal-analyst` | the document `text_path`s and `outline`s, the peer list, + the cap-tier `valuation.stance` as context | all |
| `sector-analysis` (mode `single-sector`) | `everything-finance:terminal-analyst` | the sector, the ticker **as focus stock**, the peer list, the cached sector body when fresh (see *Sector leg*) | standard, deep |
| `management-analysis` | `everything-finance:field-analyst` | company name + the document `text_path`s and `outline`s | standard, deep, fundamentals |
| `news-scan` | `everything-finance:field-analyst` | company name | standard, deep |

The financials leg reports the earnings base (`clean_eps`, `eps_adjustments`) and the valuation leg strikes its multiples on it. They run in the same wave, so the valuation leg derives its own adjustment from the same published rows; where the two disagree, the synthesis names both and says which the verdict used.

**Output paths.** Staged work papers go under `artifacts/tmp/staging/<TICKER>/agents/` (`paths.tmp_dir("staging")`) — `technical.md`, `financials.md`, `news.md`, `sector.md`, `contest.md`, `bull-r<N>.md`, `bear-r<N>.md`, `verdict.md`. The valuation and management legs are given their own run-day paths instead — `artifacts/stocks/<TICKER>/YYYY-MM-DD/dcf.md` (the engine also writes `dcf.json` beside it) and `management.md` (`paths.stock_dir`) — so `get_prior_run(skill="dcf"|"management")` finds them regardless of which skill produced them.

**IO hygiene (all modes).** Each leg `Write`s its **full report to its file** — opening with its machine-read block, then a `## Findings` section carrying the leg's whole case in a few sentences — and returns **only a compact digest** — its machine-readable top block plus the path, never the body. Downstream agents (`contest` / `bull` / `bear` / `portfolio-manager`) and your synthesis receive **paths** and Read what they need in their own context; you never hold six full reports at once. Pass each agent only what it needs — they are forked and share no context.

If phase 0 or any leg fails, state the gap and continue; the portfolio-manager weighs missing evidence as uncertainty, not as neutral. If the management leg's **integrity gate is FAIL**, that overrides the rest — the verdict is AVOID regardless of numbers or valuation.

### Phases 2 and 3 — the debate and the verdict

| Phase | Agent | Input | Modes |
|---|---|---|---|
| 2 | `everything-finance:contest-researcher` | the leg report **paths** (technical, financials, valuation) | quick |
| 2 | `everything-finance:bull-researcher` / `everything-finance:bear-researcher` | the phase-1 report **paths** (round 1); the opposing side's previous-round report, its own, the round number and the helper's `directive` (round r>1) | standard, deep |
| 3 | `everything-finance:portfolio-manager` | its **output path** (`verdict.md`), the leg report **paths**, the full debate transcript paths, `position` (from step 2's broker check: `{held, qty, avg_cost, unrealised_pct}`), `debate` (`{rounds_run, stopped_because, engaged}`) and the market context — issues verdict: Buy / Accumulate / Hold / Avoid / Exit, with sizing and invalidation level | quick, standard, deep |

## Debate — by mode

Phase 2's shape depends on the resolved mode.

**`quick` — single-pass contest.** Fork one `everything-finance:contest-researcher` with the three leg paths. It reads them, writes `contest.md` (strongest bull case, strongest bear case, balance-of-evidence lean), and returns the digest. No bull/bear loop. If its lean is **`genuinely split`**, the synthesis appends a one-line suggestion to re-run `standard`/`deep` — it does **not** auto-escalate (the user chose quick).

**`standard` and `deep` — round 1, then the helper decides.** Fork `everything-finance:bull-researcher` and `everything-finance:bear-researcher` in parallel (round 1) from the phase-1 paths. After every round, write each side's `debate-block` fields to a small JSON and run:

`python3 <plugin>/skills/deep-analysis/scripts/escalation.py --bull <bull-rN.json> --bear <bear-rN.json> --mode <standard|deep> --round <N>` → `{escalate, reason, directive, gaps}`

It is the source of truth for both modes and it caps the rounds itself (standard 2, deep 3); the reference's § "Debate protocol" owns when a further round is worth running. **Put `directive` in both round prompts verbatim** — it names what that round is for, and the researchers act on it.

**Round r > 1:** re-fork each side with its own round r-1 report, the *other* side's round r-1 report, the directive, and its round number. Each must add new load-bearing evidence, explicitly concede, or report `new_evidence: false` — **which is a valid, debate-ending turn**. A side with nothing new says so; it does not manufacture a point to keep the loop alive.

Write each round's reports as `bull-r<N>.md` / `bear-r<N>.md`. Record `rounds_run`, the helper's `reason` for stopping, and whether the sides ever engaged on a common axis — all three go to the portfolio-manager and into the synthesis. A `gaps` entry from the helper means a digest broke its contract; report it, do not treat it as convergence.

The `everything-finance:portfolio-manager` then runs once on the full transcript (the contest, or all debate rounds) plus the phase-3 inputs above. **Pass it facts, not rulings** — it holds its own judging rules, and restating them in the dispatch anchors the decision you asked it to make. Give it the `verdict.md` path in the dispatch: without one it replies with the verdict as body text, which lands the whole thing in your context and leaves you to copy it to disk by hand.

## Fundamentals mode — three legs, no debate

`fundamentals` runs phase 0 and exactly the three legs the phase-1 table marks, then **stops**: no debate, no portfolio-manager, no technical / news / sector lens.

The `everything-finance:report-writer` merges the three legs the same way it does a full run — pass it the three paths and the run facts. There is no verdict table, no entry/stop/target and no sizing: this mode reports what the business is and what it is worth, and leaves the position call to a full run. An integrity FAIL is the headline — overall AVOID regardless of numbers or valuation.

In chat, give the fundamentals verdict, the integrity gate result, the intrinsic-value range + DCF confidence, and the two strongest flags.

## Sector leg — shared cache

The sector body (RS, KPIs, tailwinds/headwinds, leaders/laggards, stance) is cached at `artifacts/state/sectors/<sector-slug>.md` under the session's cwd and refreshed monthly; only the focus-stock positioning is stock-specific. Map the stock → sector (its `get_company_fundamentals` industry), then read the cache file's `generated: YYYY-MM-DD` frontmatter line and age it against today — a missing file or an undated one counts as stale:

- **≤ 30** — pass the cached body *and* the focus ticker, so the leg reuses the body and computes only the stock's positioning.
- **`None` or > 30** — pass no body; the leg computes a fresh one. Seeding the cache and raising the next-refresh reminder are steps the `sector-analysis` skill owns; you do neither.

## Synthesize — one forked `report-writer`

The work papers are the legs' own output; you do **not** write them, and you do **not** read them to write the report. Fork one `everything-finance:report-writer` with the template path, the output path, the work-paper paths, and the run facts only you hold:

`ticker`, company, date, CMP · `mode` + `MODE_REASON` · `debate` (`rounds_run`, `stopped_because`, `engaged`) · `agent_count` · the prior-run path when `get_prior_run` found one · the gaps you recorded yourself (the broker check, a failed leg, a skipped phase-0 call).

It reads the papers in its own context, authors the report, and returns the path. Six leg reports, a multi-round transcript and a verdict never enter your context at once — that is the point of the fork, so do not read them "to check" and do not ask it for the body.

Output path: `artifacts/tmp/staging/<TICKER>.md` — in `fundamentals`, `artifacts/tmp/staging/<TICKER>.fundamentals.md` (`paths.tmp_dir("staging")`). Template: `assets/deep-analysis.md`, bundled with this skill; it owns the section list and what fills each placeholder.

The report **must contain a `## Telegram Brief` section** (≤ 10 lines). The plugin's Stop hook archives the staged report to `artifacts/stocks/<TICKER>/YYYY-MM-DD/` — `deep-analysis.md`, or `fundamental-analysis.md` from the `.fundamentals` staging name — moves the work papers to the folder of the same name beside it, and sends the brief to Telegram. Do not send Telegram messages yourself and do not move the files. **The two modes archive to separate files on purpose**: a fundamentals run must never overwrite the day's full run, and `get_prior_run(skill="deep-analysis"|"fundamentals")` then builds each mode on its own history.

In chat (the debate modes), give the verdict, the two strongest opposing arguments, the sector stance, and the invalidation level — from the digests you already hold, not from the report file.

## Alerts this skill raises (via `manage_alerts`)

On a completed analysis, write watch-items for `daily-brief` (set `dedup_key` so a re-analysis updates in place):

- **`reanalyze_due`** — a date reminder to revisit the thesis (`trigger: {due: <today + N days>}`, N from the verdict's review cadence; `subject: {type: stock, id: <TICKER>}`, `created_by: deep-analysis`, `severity: watch`, `action.suggest: "/deep-analysis <TICKER>"`, `dedup_key: reanalyze-<TICKER>`).
- **`price_cross` invalidation** — the PM's invalidation level as a cheap trigger (`trigger: {metric: close, op: "<", level: <invalidation>}` for a long thesis; `severity: act`, `action.text` = "thesis invalidation level", `dedup_key: invalidate-<TICKER>`).
- On a **BUY** verdict, also raise an **`opportunity`** alert (the vetted feed daily-brief reads): `severity: watch`, `action.text` = the one-line thesis, `action.suggest: "/find-trade"` or `/trade-tracker <TICKER>`, `dedup_key: opp-<TICKER>`.

In `fundamentals` only `reanalyze_due` applies — the other two need the portfolio-manager's verdict.
