---
name: deep-analysis
description: Full multi-agent investment debate on a single Indian stock — six lenses (technical; the numbers, with the annual report and concall read directly; management integrity & skill; valuation triangulating a story-driven DCF with relative multiples; news sentiment; sector context), then bull vs bear researchers debate, and a portfolio-manager issues the verdict, synthesized into one readable report. Use whenever the user asks to analyze, research, deep-dive, evaluate, or form a view on a specific ticker or company name ("should I buy X?", "what do you think of Tata Motors?"), even if they don't say "deep analysis". Its fundamentals-only mode is also the home of the fundamental read without the debate — "are the fundamentals good?", "is X fundamentally sound?", "fundamental analysis of Y".
argument-hint: "TICKER (NSE symbol or company name) [--quick | --deep | --fundamentals]"
allowed-tools: Read, Write, Bash, Agent, mcp__indmoney__*, mcp__kite__*, mcp__upstox__*, mcp__finance-market__*, mcp__finance-company__*
---

# Deep Stock Analysis — multi-agent debate

Read `references/reference.md` — it owns how the six lenses combine into one verdict and the debate protocol. Resolve the argument to an NSE symbol first; `get_company_fundamentals` on the candidate symbol confirms the company name.

## Run mode — resolve first

**Resolve the mode before anything else**, then size the rest of the run to it.

| Mode | Primary documents | Legs | Debate | ~Agents |
|---|---|---|---|---|
| `quick` | not fetched — ratios and CMP only | technical, financials, valuation | 1 `contest-researcher` (single pass) | ~4 |
| `standard` *(default)* | warmed by you in phase 0 | all 6 | round 1, escalate to round 2 only on genuine divergence | ~7–8 |
| `deep` | warmed by you in phase 0 | all 6 | up to 3 rounds with convergence check | ~12 |
| `fundamentals` | warmed by you in phase 0 | financials, management, valuation | none | 3 |

Resolution — the two reads the helper can't make, then the helper itself, which decides first-match-wins:

1. **A fundamentals-only request is the `--fundamentals` flag.** "Are the fundamentals good?", "is X fundamentally sound?", "fundamental analysis of X" ask for the numbers, the people and the price without the debate — append `--fundamentals` to the argument string you hand the helper.
2. Check the broker: if a broker MCP is connected (`mcp__indmoney__*` / `mcp__kite__*` / `mcp__upstox__*`), look up whether the resolved ticker is a **live holding or open position**. Script code can't call MCP tools, so this is your job; pass the result to the helper.
3. `python3 <plugin>/skills/deep-analysis/scripts/resolve_mode.py --args "<the raw argument string>" --symbol <TICKER> [--broker-holding]` → `{mode, reason}`. It applies: **an explicit flag wins** (over the holding escalation too, and `--fundamentals` over the two depth flags — it names the question, not the rigour); else a **holding / open-trade auto-escalates to `deep`**; else **`standard`**. It checks the open-trade artifact half (`state/trades/<SYMBOL>-*.yml` `status: open`) itself.
4. When the holding auto-escalation fires (no explicit flag), print the one-line note: `Held position → running deep analysis (override with --quick).`

Record `{mode, reason}` — the synthesis reports both.

**Refer the earlier run first.** Call `paths.latest_prior("deep-analysis", TICKER)` — `paths.latest_prior("fundamentals", TICKER)` in `fundamentals`, so each mode builds on its own history — if a prior report exists, read it before launching the debate so this run builds on it rather than starting cold, and pass the prior verdict/levels to the legs as context. The synthesized report then opens with a **"What changed since `<date>`"** block (see Synthesize). No prior run is the normal first-time case.

**Sources for this orchestrator only:** `finance-company` — `get_company_fundamentals` (symbol and company name) and `get_documents` (the phase-0 warm-up); `finance-market` — `get_market_context` and `get_quote` (CMP for the report header). Every other number in the report arrives inside a leg's digest or its file; the legs own their own fetching.

## Orchestration

Four phases. Phase 0 is two calls you make yourself; phase 1 is all six legs in **one** parallel wave; phase 2 is the debate; phase 3 decides. **The fan-out scales to the mode** — see the per-mode column.

### Phase 0 — no agent, you run it

- **Market context.** `get_market_context(mode="quick")`. Costs nothing after the first caller of the day. Pass `market_posture` + `volatility.band` to the `portfolio-manager` (they govern **sizing**, never the verdict), and the stock's cap-tier `valuation.stance` to the valuation leg as context for its relative-multiple read.
- **Primary documents.** `get_documents(TICKER, annual_reports=3)` — every mode but `quick`. It returns rows of `{kind, label, url, publisher, text_path, text_chars, text_lines, extracted_by, cached}`: **paths, never text**. Hand the `text_path`s to the legs that read documents; you never open one yourself.

Fetch-once is a **cache guarantee, not an ordering rule**: `get_documents` caches a converted document permanently and `get_company_fundamentals` caches for the day, so every leg that calls them lands on the same bytes whatever order it ran in. That is why phase 1 is a single wave.

In `quick`, skip the document warm-up and tell each leg `documents: none (quick — ratios and CMP only)`; it labels every check that needed a primary document as a gap. The valuation leg is the one exception — the annual report's tax note is its only acceptable source for `tax_rate`, so it pulls that one document rather than working from an unsourced rate.

### Phase 1 — six legs, one parallel wave

Each leg is a **skill run inside a generic profile agent** — issue every `Agent` call in one message. The dispatch names the skill, its mode where the skill has one, the output path, the ticker, and the leg's inputs.

| Leg skill | Profile | Inputs beyond the ticker | Modes |
|---|---|---|---|
| `technical-analysis` | `terminal-analyst` | — (it pulls its own candles) | quick, standard, deep |
| `financial-analysis` | `terminal-analyst` | company name + the document `text_path`s | all |
| `valuation-analysis` | `terminal-analyst` | the document `text_path`s + the cap-tier `valuation.stance` as context | all |
| `sector-analysis` (mode `single-sector`) | `terminal-analyst` | the sector, the ticker **as focus stock**, the cached sector body when fresh (see *Sector leg*) | standard, deep |
| `management-analysis` | `field-analyst` | company name + the document `text_path`s | standard, deep, fundamentals |
| `news-scan` | `field-analyst` | company name | standard, deep |

**Output paths.** Staged work papers go under `artifacts/tmp/staging/<TICKER>/agents/` (`paths.tmp_dir("staging")`) — `technical.md`, `financials.md`, `news.md`, `sector.md`, `contest.md`, `bull-r<N>.md`, `bear-r<N>.md`, `verdict.md`. The valuation and management legs are given their own run-day paths instead — `artifacts/stocks/<TICKER>/YYYY-MM-DD/dcf.md` (the engine also writes `dcf.json` beside it) and `management.md` (`paths.stock_dir`) — so `paths.latest_prior("dcf"/"management", TICKER)` finds them regardless of which skill produced them.

**IO hygiene (all modes).** Each leg `Write`s its **full report to its file** and returns **only a compact digest** — its machine-readable top block plus the path, never the body. Downstream agents (`contest` / `bull` / `bear` / `portfolio-manager`) and your synthesis receive **paths** and Read what they need in their own context; you never hold six full reports at once. Pass each agent only what it needs — they are forked and share no context.

If phase 0 or any leg fails, state the gap and continue; the portfolio-manager weighs missing evidence as uncertainty, not as neutral. If the management leg's **integrity gate is FAIL**, that overrides the rest — the verdict is AVOID regardless of numbers or valuation.

### Phases 2 and 3 — the debate and the verdict

| Phase | Agent | Input | Modes |
|---|---|---|---|
| 2 | `contest-researcher` | the leg report **paths** (technical, financials, valuation) | quick |
| 2 | `bull-researcher` / `bear-researcher` | the phase-1 report **paths** (round 1); the opposing side's previous-round report (round r>1) | standard, deep |
| 3 | `portfolio-manager` | the leg report **paths** + the full debate transcript paths — issues verdict: Buy / Accumulate / Hold / Avoid / Exit, with sizing and invalidation level | quick, standard, deep |

## Debate — by mode

Phase 2's shape depends on the resolved mode.

**`quick` — single-pass contest.** Fork one `contest-researcher` with the three leg paths. It reads them, writes `contest.md` (strongest bull case, strongest bear case, balance-of-evidence lean), and returns the digest. No bull/bear loop. If its lean is **`genuinely split`**, the synthesis appends a one-line suggestion to re-run `standard`/`deep` — it does **not** auto-escalate (the user chose quick).

**`standard` — round 1 + conditional round 2.** Fork `bull-researcher` and `bear-researcher` in parallel (round 1) from the phase-1 paths. Then decide escalation deterministically from their two digests' `debate-block`s (axis + claim + concession): `python3 <plugin>/skills/deep-analysis/scripts/escalation.py --bull <bull-r1.json> --bear <bear-r1.json>` → `{escalate, reason}`. **Escalate to round 2 only on genuine divergence** (both top points on the *same* verdict-relevant axis, distinct evidence-tied claims, neither conceded); otherwise stop at round 1 and go to the PM. (Write each digest's `debate-block` fields to a small JSON for the helper, or apply the same rule by hand — the helper is the source of truth.) One round is the baseline; a second is opt-in on evidence.

**`deep` — up to 3 rounds, early-stop on convergence.** The full loop, capped at 3:
- **Round 1:** `bull` and `bear` in parallel from the phase-1 paths.
- **Round r > 1:** each re-forked, fed the *other* side's round r-1 report (and its own), required to **add new load-bearing evidence or explicitly concede** (`new_evidence: false` is not a valid turn). Tell each agent its round number.
- **Convergence check** after each round (you, the orchestrator — no extra agent): did either side introduce a *new* evidence-tied argument this round (`new_evidence: true`, no concession)? If neither did, **stop**. Otherwise continue, up to round 3.

Write each round's reports as `bull-r<N>.md` / `bear-r<N>.md`. Record how many rounds ran and why it stopped (converged / escalated / hit max / single contest) — the synthesis reports it.

The `portfolio-manager` then runs once on the full transcript (the contest, or all debate rounds) plus the leg report paths.

## Fundamentals mode — three legs, no debate

`fundamentals` runs phase 0 and exactly the three legs the phase-1 table marks, then **stops**: no debate, no portfolio-manager, no technical / news / sector lens.

**Merge, don't paste.** Author one fundamentals report in plain prose from the three digests, re-reading a leg's file for any detail you need: the company overview and checklist highlights (financials), the integrity gate + skill grade (management), and the **combined valuation stance with its DCF-confidence grade**. An integrity FAIL is the headline — overall AVOID regardless of numbers or valuation. There is no verdict table, no entry/stop/target and no sizing: this mode reports what the business is and what it is worth, and leaves the position call to a full run.

In chat, give the fundamentals verdict, the integrity gate result, the intrinsic-value range + DCF confidence, and the two strongest flags.

## Sector leg — shared cache

The sector body (RS, KPIs, tailwinds/headwinds, leaders/laggards, stance) is cached at `state/sectors/<sector>.md` and refreshed monthly; only the focus-stock positioning is stock-specific. Map the stock → sector (its `get_company_fundamentals` industry), then check `paths.sector_cache_age_days(sector)`:

- **≤ 30** — pass the cached body *and* the focus ticker, so the leg reuses the body and computes only the stock's positioning.
- **`None` or > 30** — pass no body; the leg computes a fresh one. Seeding the cache and raising the next-refresh reminder are steps the `sector-analysis` skill owns; you do neither.

## Synthesize from the work papers

The work papers above are the legs' own output — you do **not** write them. Build the report **from** them: the digests they returned, re-reading a leg's file for any detail you need.

Write the synthesized report to `artifacts/tmp/staging/<TICKER>.md` — in `fundamentals`, `artifacts/tmp/staging/<TICKER>.fundamentals.md` (`paths.tmp_dir("staging")`) — using `assets/deep-analysis.md` (bundled with this skill). The template is a **readable synthesis** — you (the orchestrator) author every section in plain prose from the work papers, not by dumping leg output:

- **Mode header & banners:** record the resolved `MODE` and the one-line `MODE_REASON`. In `quick` and in `fundamentals`, open with the template's banner for that mode, naming what was skipped, so the read is never mistaken for a full debate.
- **Summary placeholders you fill yourself:** CMP, COMPANY_NAME_SUFFIX (" · <Company>" or empty), ONE_LINE_THESIS, CALL_NARRATIVE, the verdict table (ENTRY_SL_TARGET/RRR/ALLOC_CAP/INVALIDATION/REVIEW_TRIGGER from the portfolio-manager), the At-a-Glance lens table — every lens the mode ran, with the rest marked "not run (<mode>)"; each lens's stance + one-line read; the valuation line carries the **combined stance + DCF confidence**, the management line the integrity/skill grade. COMPANY_OVERVIEW (the financials leg's "Company overview" block), TOP_BULL_POINT / TOP_BEAR_POINT (from the debate or the contest's two sides), SECTOR_STANCE_ONELINE, KEY_LEVEL (nearest decision level from the technical read), DATA_GAPS (union of every leg's gaps, plus the lenses the mode skipped), DEBATE_ROUNDS (`single contest (quick)`, or `N rounds; stopped converged / escalated / hit max`), AGENT_COUNT (the profile agents that ran + the debate agents + the PM).
- **Synthesized sections:** BULL_SYNTHESIS / BEAR_SYNTHESIS (distil each side's *strongest surviving* case across all rounds — or the contest's two sides — evidence-tied), DECISIVE_POINTS (what the PM kept/discarded + dissent worth keeping), SECTOR_CONTEXT (the sector read + where the stock sits in its sector), and the Evidence-by-Lens blocks (condense each leg report to its load-bearing facts and levels — keep the numbers and cites, drop the boilerplate).
- **"What changed since `<date>`" block (only when a prior run was found):** verdict then→now, the DCF fair-value shift, whether the thesis is intact, and any notable new risk. Omit the block entirely on a first-ever run.

The report **must contain a `## Telegram Brief` section** (≤ 10 lines). The plugin's Stop hook archives the staged report to `artifacts/stocks/<TICKER>/YYYY-MM-DD/` — `deep-analysis.md`, or `fundamental-analysis.md` from the `.fundamentals` staging name — moves the work papers to the folder of the same name beside it, and sends the brief to Telegram. Do not send Telegram messages yourself and do not move the files. **The two modes archive to separate files on purpose**: a fundamentals run must never overwrite the day's full run, and `paths.latest_prior("deep-analysis"/"fundamentals", TICKER)` then builds each mode on its own history.

In chat (the debate modes), give the verdict, the two strongest opposing arguments, the sector stance, and the invalidation level — not the whole report.

## Alerts this skill raises (via `finance/compute/alerts.py`)

On a completed analysis, write watch-items for `daily-brief` (set `dedup_key` so a re-analysis updates in place):

- **`reanalyze_due`** — a date reminder to revisit the thesis (`trigger: {due: <today + N days>}`, N from the verdict's review cadence; `subject: {type: stock, id: <TICKER>}`, `created_by: deep-analysis`, `severity: watch`, `action.suggest: "/deep-analysis <TICKER>"`, `dedup_key: reanalyze-<TICKER>`).
- **`price_cross` invalidation** — the PM's invalidation level as a cheap trigger (`trigger: {metric: close, op: "<", level: <invalidation>}` for a long thesis; `severity: act`, `action.text` = "thesis invalidation level", `dedup_key: invalidate-<TICKER>`).
- On a **BUY** verdict, also raise an **`opportunity`** alert (the vetted feed daily-brief reads): `severity: watch`, `action.text` = the one-line thesis, `action.suggest: "/find-trade"` or `/trade-tracker <TICKER>`, `dedup_key: opp-<TICKER>`.

In `fundamentals` only `reanalyze_due` applies — the other two need the portfolio-manager's verdict.
