---
name: deep-analysis
description: Full multi-agent investment debate on a single Indian stock — six lenses (technical; the numbers, with the annual report and concall read directly; management integrity & skill; valuation triangulating a story-driven DCF with relative multiples; news sentiment; sector context), then bull vs bear researchers debate, and a portfolio-manager issues the verdict, synthesized into one readable report deck. Use whenever the user asks to analyze, research, deep-dive, evaluate, or form a view on a specific ticker or company name ("should I buy X?", "what do you think of Tata Motors?"), even if they don't say "deep analysis". Its fundamentals-only mode is also the home of the fundamental read without the debate — "are the fundamentals good?", "is X fundamentally sound?", "fundamental analysis of Y".
argument-hint: "TICKER (NSE symbol or company name) [--quick | --deep | --fundamentals]"
allowed-tools: Read, Write, Bash, Agent, Skill, mcp__indmoney__*, mcp__plugin_everything-finance_indmoney__*, mcp__kite__*, mcp__plugin_everything-finance_kite__*, mcp__upstox__*, mcp__plugin_everything-finance_upstox__*, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*
---

# Deep Stock Analysis — multi-agent debate

**No ticker given?** Deep-analysis reads one named stock. If the user invoked it with no company or ticker ("analyze a good stock", "find me something to research"), hand off to `discover stocks --invest` — it screens, triages, and surfaces candidates, then the user's pick flows back here for the full read. Do not guess a stock.

Read `references/reference.md` — it owns how the six lenses combine into one verdict and the debate protocol. Resolve the argument to an NSE symbol first; `get_company_fundamentals` on the candidate symbol confirms the company name. For an explicit `--quick` request, ask only for `sections=["ratios", "pnl_10y", "balance_sheet_10y", "cash_flow_10y", "shareholding", "peers"]` and retain that response for the quick pass; it must not fetch the document index. Other modes may request the full response.

**If the symbol will not resolve, do not brute-force it.** One clean symbol and at most one obvious alternative is the budget — never cycle through name fragments, old tickers, BSE codes and web searches (each failed call is envelope noise every later turn re-reads). A rename Tickertape search cannot reach still has a sid: read it from the Tickertape stock URL slug (…-SID), then pass `sid=` to `get_company_fundamentals` so the full path (10y statements, peers, shareholding) works, and hand that same sid to the legs. If you cannot get a trustworthy sid, `AskUserQuestion` at once — do not proceed on a near-match ticker's financials, and do not fall back to a hand-built read when the sid escape hatch is available.

## Run mode — resolve first

**Resolve the mode before anything else**, then size the rest of the run to it.

The tiers differ by **amount of judgment** — how much of the argument is worth building for the question being asked.

| Mode | Primary documents | Legs | Debate | Additional agents, including synthesis |
|---|---|---|---|---|
| `quick` | none — structured data only | one pass in the current context | none | 0 |
| `standard` *(default)* | warmed by you in phase 0 | financials, management, valuation, news | 1 `everything-finance:contest-researcher` (single pass) | 7 |
| `deep` | warmed by you in phase 0 | all 6 (adds technical, sector) | up to 3 rounds, the helper decides | 10–14 |
| `fundamentals` | warmed by you in phase 0 | financials, management, valuation | none | 4 |

`quick` is the **elimination screen** — one pass reading structured data only and returning keep/reject/review with cited reasons and a one-line balance lean. It does not assign an independent numeric rank; discovery retains the deterministic scan order. It is discovery's per-name Stage B and a fast standalone take; it fetches no documents and renders no deck. `standard` is the full **investment** judgment — business, management, value and red-flag news, since timing (technical) and context (sector) do not *eliminate* a stock. `deep` is where the chart, the sector and the iterative bull/bear debate re-enter, for the finalists that earned the conviction.

Resolution — the two reads the helper can't make, then the helper itself, which decides first-match-wins:

1. **A fundamentals-only request is the `--fundamentals` flag.** "Are the fundamentals good?", "is X fundamentally sound?", "fundamental analysis of X" ask for the numbers, the people and the price without the debate — append `--fundamentals` to the argument string you hand the helper.
2. **Check the broker across connected accounts.** Query all connected personal sources for holdings and open positions, including their pagination/completeness markers. `yes` means a matching position was found anywhere; `no` requires complete successful coverage of every connected account and no match; otherwise use `unknown`. An empty response from one broker says nothing about another broker. Preserve failed/incomplete account names as gaps even if a match elsewhere establishes `yes`. Normalize through `finance/compute/holdings.py`; do not add an aggregator's copy of a broker holding to that broker's own record. Keep exact per-account quantities and costs; if overlapping coverage cannot be reconciled, leave aggregate quantity/cost unknown and pass the account records and gap to the portfolio-manager. Script code cannot call broker MCP tools, so collection is your job. An explicit `--quick` may skip this check when no holdings snapshot was supplied, because it makes no position/sizing call; record status unknown and the omitted check.
3. `python3 <plugin>/skills/deep-analysis/scripts/resolve_mode.py --args "<the raw argument string>" --symbol <TICKER> --holding <yes|no|unknown>` → `{mode, reason, gaps}`. It applies: **an explicit flag wins** (over the holding escalation too, and `--fundamentals` over the two depth flags — it names the question, not the rigour); else a **holding / open-trade auto-escalates to `deep`**; else **`standard`**. It checks the open-trade artifact half (`state/trades/<SYMBOL>-*.yml` `status: open`) itself.
4. When the holding auto-escalation fires (no explicit flag), print the one-line note: `Held position → running deep analysis (override with --quick).`

Record `{mode, reason, gaps}` — the synthesis reports the first two and folds the third into DATA_GAPS.

**Refer the earlier run first.** Call `get_prior_run(skill="deep-analysis", subject=TICKER)` — `skill="fundamentals"` in `fundamentals`, so each mode builds on its own history — if a prior report exists, read it before launching the debate so this run builds on it rather than starting cold, and pass the prior verdict/levels to the legs as context. The synthesized report then opens with a **"What changed since `<date>`"** block (see Synthesize). No prior run is the normal first-time case.

**Sources for this orchestrator only:** `finance-company` — `get_company_fundamentals` (symbol and company name) and `get_documents` (the phase-0 warm-up); `finance-market` — `get_market_context`, `get_quote` (CMP for the report header) and `get_prior_run`. Every other number in the report arrives inside a leg's digest or its file; the legs own their own fetching.

## Orchestration

Four phases. Phase 0 is two calls you make yourself; phase 1 is the legs in **one** parallel wave; phase 2 is the debate; phase 3 decides. **The fan-out scales to the mode** — see the per-mode column. `quick` skips phases 0–2's fan-out entirely and executes the quick pass below in the current context.

**Keep orchestration compact.** Use the phase table as the plan and pass evidence paths plus concise digests between phases. Dispatch a parallel wave only when the user and host permit it; otherwise run the same roles sequentially in the current context or one permitted agent at a time. Preserve the requested analysis scope when adapting execution.

Use the host's documented completion mechanism. On a host that resumes the orchestrator from completion events, yield after dispatch; on a host with an explicit wait tool, wait on the actual running handles. Do not invent automatic resumption, issue filler shell commands, or schedule wakeups merely to poll. Inspect returned output paths once their writers finish; do not guess filenames or repeatedly read files that have not been produced. A failed worker with a complete output needs verification, not an automatic rerun.

**Scripts and assets are under this skill's own base directory**, given to you in the header above. Use it — do not search the filesystem for the plugin.

### Phase 0 — no agent, you run it

- **Market context.** `get_market_context(mode="quick")`. Costs nothing after the first caller of the day. Pass `market_posture` + `volatility.band` to the `portfolio-manager` (they govern **sizing**, never the verdict), and the stock's cap-tier `valuation.stance` to the valuation leg as context for its relative-multiple read.
- **Primary documents.** `get_documents(TICKER, annual_reports=3)` — every mode but `quick`. It returns rows of `{kind, label, url, publisher, text_path, text_chars, text_lines, extracted_by, cached, outline}`: **paths, never text**. Hand each row's `text_path` *and* its `outline` — the map from each note to its line numbers — to the legs that read documents, so a leg reads the lines it needs instead of searching a report that runs to tens of thousands of lines. You never open one yourself.
- **The peer set.** `get_company_fundamentals(TICKER)` already returned `peers`, each row carrying `ttm_pe` and `pb`. Pass that list to **both** the valuation and sector legs, so the peer-median multiple and the "leader or laggard in its group" read describe the same companies. Neither leg builds its own.

Reuse phase-0 response data and returned document paths across the legs. The tools cache results, but a refresh or changed upstream document can produce a new snapshot; caching is not proof that independently fetched responses contain identical evidence. Pass the exact paths and observation dates from this run. Fetch again only for a missing section or an intentional freshness check, and record any changed evidence.

In `quick` there is no phase-0 warm-up and no leg fan-out at all — the current context reads structured data only. Skip phase 0's document and peer calls; still fetch `get_market_context(mode="quick")` for market context, without treating cap-tier valuation as company valuation.

### Phase 1 — the legs, one parallel wave

Each leg is a **skill run inside a generic profile agent** — issue every `Agent` call in one message. The dispatch names the skill, its mode where the skill has one, the output path, the ticker, and the leg's inputs.

`quick` runs no legs and never dispatches itself; its local pass is in *Debate — by mode*. This wave is `standard` (4 legs), `deep` (6) or `fundamentals` (3).

| Leg skill | Profile | Inputs beyond the ticker | Modes |
|---|---|---|---|
| `financial-analysis` | `everything-finance:terminal-analyst` | company name + the document `text_path`s and `outline`s | standard, deep, fundamentals |
| `valuation-analysis` | `everything-finance:terminal-analyst` | the document `text_path`s and `outline`s, the peer list, + the cap-tier `valuation.stance` as context | standard, deep, fundamentals |
| `management-analysis` | `everything-finance:field-analyst` | company name + the document `text_path`s and `outline`s | standard, deep, fundamentals |
| `news-scan` | `everything-finance:field-analyst` | company name | standard, deep |
| `technical-analysis` | `everything-finance:terminal-analyst` | — (it pulls its own candles) | deep |
| `sector-analysis` | `everything-finance:terminal-analyst` | the sector, the ticker **as focus stock**, the peer list, the cached sector body when fresh (see *Sector leg*) | deep |

The financials leg reports the earnings base (`clean_eps`, `eps_adjustments`) and the valuation leg strikes its multiples on it. They run in the same wave, so the valuation leg derives its own adjustment from the same published rows; where the two disagree, the synthesis names both and says which the verdict used.

**Output paths.** Before dispatching any report legs, create one bundle with `python3 -m finance.publication prepare --session <session-id> --ticker <TICKER> --date <YYYY-MM-DD> --mode <mode>`. Use the literal session id printed by SessionStart. On clients without that hook, generate one UUID for this run and retain it for explicit publication. Add `--telegram` only when the user authorized Telegram delivery; credentials alone are not authorization. Keep the returned `run_dir`, `report_json`, `report_html` and `agents_dir` paths and pass them to workers; never reconstruct staging paths from the ticker. Staged work papers go in this run's `agents_dir`. Give valuation the explicit `agents_dir/dcf.md` and `agents_dir/dcf-inputs.yml` output paths, and management `agents_dir/management.md`. They write directly there, not to shared dated report files. The valuation digest cites the immutable `dcf_path` returned by the engine. Pass these exact paths to the debate and writer.

**IO hygiene (all modes).** Each leg `Write`s its **full report to its file** — opening with its machine-read block, then a `## Findings` section carrying the leg's whole case in a few sentences — and returns **only a compact digest** — its machine-readable top block plus the path, never the body. Downstream agents (`contest` / `bull` / `bear` / `portfolio-manager`) and your synthesis receive **paths** and Read what they need in their own context; you never hold six full reports at once. Pass each agent only what it needs — they are forked and share no context.

If phase 0 or any leg fails, state the gap and continue; the portfolio-manager weighs missing evidence as uncertainty, not as neutral. If the management leg's **integrity gate is FAIL**, that overrides the rest — the verdict is AVOID regardless of numbers or valuation.

### Phases 2 and 3 — the debate and the verdict

| Phase | Agent | Input | Modes |
|---|---|---|---|
| 2 | `everything-finance:contest-researcher` | the leg report **paths** (financials, management, valuation, news) | standard |
| 2 | `everything-finance:bull-researcher` / `everything-finance:bear-researcher` | the phase-1 report **paths** (round 1); the opposing side's previous-round report, its own, the round number and the helper's `directive` (round r>1) | deep |
| 3 | `everything-finance:portfolio-manager` | its **output path** (`verdict.md`), the leg report **paths**, the debate transcript paths, `position` (from step 2's broker check: `{held, qty, avg_cost, unrealised_pct}`), `debate` (`{rounds_run, stopped_because, engaged}`) and the market context — issues verdict: Buy / Accumulate / Hold / Avoid / Exit, with sizing and invalidation level | standard, deep |

## Debate — by mode

Phase 2's shape depends on the resolved mode.

**`quick` — execute locally, no child dispatch.** The context already running this skill performs the pass; it must not invoke `deep-analysis`, another lens skill, or an agent. If discovery launched a `terminal-analyst` worker, that worker is the whole pass.

Reuse the structured fundamentals response above. Read annual periods by their labels, keeping FY and TTM separate: cash conversion, debt/service burden, returns and their trends, shareholding/pledge, and comparable current multiples. `get_shareholding` can supplement missing pledge evidence; it does not supply remuneration. Call `get_stock_ratios` only for a needed field absent from the existing response. Fetch no primary documents. Published ratios alone cannot establish fraud, management integrity or intrinsic value; those remain unassessed, and a high P/E alone is not an exclusion.

- `reject`: a sourced, decision-relevant failure of the user's/spec's stated criteria; cite the criterion, period and evidence.
- `keep`: the available screening checks pass, with their limited scope stated. It means worth fuller research, never BUY or a cleared integrity gate.
- `review`: a material check is missing, contradictory or requires documents. Do not convert unavailable evidence into either a pass or an accusation.

Write `quick.md` via `paths.stock_dir`, with a `quick-block` carrying `verdict`, `lean`, `flags`, `reasons` and `gaps`, followed by a short sourced explanation. Return only those fields plus `path`. There is no invented 0–100 score, no debate, no portfolio-manager and no deck. Discovery uses the existing deterministic rank among keeps, and presents review cases separately.
**`standard` — single contest pass → verdict.** After the four legs (financials, management, valuation, news), fork one `everything-finance:contest-researcher` with those four paths. It writes `contest.md` (strongest bull case, strongest bear case, balance-of-evidence lean) and returns the digest — one pass, no bull/bear loop. Then the `portfolio-manager` issues the verdict. If the contest lean is **`genuinely split`**, the synthesis appends a one-line suggestion to re-run `deep` — it does not auto-escalate.

**`deep` — round 1, then the helper decides.** Fork `everything-finance:bull-researcher` and `everything-finance:bear-researcher` in parallel (round 1) from the six phase-1 paths. After every round, write each side's `debate-block` fields to a small JSON and run:

`python3 <plugin>/skills/deep-analysis/scripts/escalation.py --bull <bull-rN.json> --bear <bear-rN.json> --mode deep --round <N>` → `{escalate, reason, directive, gaps}`

It caps the rounds itself (deep 3); the reference's § "Debate protocol" owns when a further round is worth running. **Put `directive` in both round prompts verbatim** — it names what that round is for, and the researchers act on it.

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

**`quick` skips synthesis entirely** — the current context already wrote `quick.md`. Return keep/reject/review, the cited reason, the one-line lean and the path. Everything below is `standard` / `deep` / `fundamentals`.

The deck is the deliverable; **there is no markdown report.** The work papers are the legs' own output; you do **not** write them, and you do **not** read them to build the deck. Fork one `everything-finance:report-writer` with the fixture path (the worked shape example), the output path, the work-paper paths, and the run facts only you hold:

`ticker`, company, date, CMP · `mode` + `MODE_REASON` · `debate` (`rounds_run`, `stopped_because`, `engaged`) · `agent_count` · the prior-run path when `get_prior_run` found one · the gaps you recorded yourself (the broker check, a failed leg, a skipped phase-0 call).

It reads the papers in its own context, authors the deck's **render projection** — a single `.report.json` — and returns the path. The leg reports, the debate transcript and the verdict never enter your context at once — that is the point of the fork, so do not read them "to check" and do not ask it for the body.

Output path: the bundle's returned `report_json`. Pass its exact ticker, date and mode to the writer; projection `meta` must match. Fixture: `skills/_report/scripts/fixtures/deep-analysis.sample.json`; `finance/contracts.md` owns the projection contract.

The projection **must carry `coverage.brief`** (≤ 10 lines) — it is the brief included when Telegram delivery is authorized, so it must stand alone as the run's headline. It is also the prior-run record and can be read by trade-tracker as rationale. Preserve source attribution and data gaps; missing evidence must never become a fabricated number in the projection.

In chat (the debate modes), give the verdict, the two strongest opposing arguments, the sector stance, and the invalidation level — from the digests you already hold, not from the projection file.

## Render the deck

Once the report-writer returns the `.report.json` path, produce the one self-contained deck:

```bash
python3 skills/_report/scripts/render_report.py \
  --report-json "<returned report_json>" \
  --template deep-analysis \
  --out "<returned report_html>"
```

`render_report.py` is pure compute over that JSON (it fetches nothing); charts are the data-driven partials in `skills/_report/scripts/charts.py`, never hand-authored markup. Every number the deck prints comes from the artifact that sourced it — a value the projection does not carry renders as a **labelled gap** (an empty pledge list is "unknown", not "none"), and the gaps slide is never trimmed.

After rendering and verifying the deck, and after every work-paper writer finishes, write the empty `ready` file inside the returned `run_dir`. Publish explicitly with `<plugin-root>/hooks/post-deep-analysis.sh publish --session <session-id> --run-id <run-directory-name>` (the wrapper uses the shared secrets loader). Use the returned archived `report_html` link in the final response. Publication moves the entire bundle atomically into `stocks/<TICKER>/<date>/runs/<run-id>/`; same-day reruns never replace earlier evidence. If publication fails, preserve staging and report the gap. Do not move individual files. The Stop hook is recovery for ready bundles left by the same session; it ignores other sessions and legacy flat staging. Telegram sends the archived deck as a document only when authorized at preparation; a delivery failure leaves the archive intact and is reported without automatic retry.

## Alerts this skill raises (via `manage_alerts`)

On a completed analysis, write watch-items for `daily-brief` (set `dedup_key` so a re-analysis updates in place):

- **`reanalyze_due`** — a date reminder to revisit the thesis (`trigger: {due: <today + N days>}`, N from the verdict's review cadence; `subject: {type: stock, id: <TICKER>}`, `created_by: deep-analysis`, `severity: watch`, `action.suggest: "/deep-analysis <TICKER>"`, `dedup_key: reanalyze-<TICKER>`).
- **`price_cross` invalidation** — the PM's invalidation level as a cheap trigger (`trigger: {metric: close, op: "<", level: <invalidation>}` for a long thesis; `severity: act`, `action.text` = "thesis invalidation level", `dedup_key: invalidate-<TICKER>`).
- On a **BUY** verdict, also raise an **`opportunity`** alert (the vetted feed daily-brief reads): `severity: watch`, `action.text` = the one-line thesis, `action.suggest: "/discover"` or `/trade-tracker <TICKER>`, `dedup_key: opp-<TICKER>`.

In `fundamentals` only `reanalyze_due` applies — the other two need the portfolio-manager's verdict.
