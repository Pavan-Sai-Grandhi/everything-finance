---
name: deep-analysis
description: Full multi-agent investment debate on a single Indian stock — six lenses (the company's story and its people; the sector's growth story; the numbers, with the annual report and concalls read directly; management integrity & skill; valuation triangulating a story-driven DCF with relative multiples; news sentiment; technical), then bull vs bear researchers debate, and a portfolio-manager issues the verdict, synthesized into one readable report deck. Use whenever the user asks to analyze, research, deep-dive, evaluate, or form a view on a specific ticker or company name ("should I buy X?", "what do you think of Tata Motors?"), even if they don't say "deep analysis". Its fundamentals-only mode is also the home of the fundamental read without the debate — "are the fundamentals good?", "is X fundamentally sound?", "fundamental analysis of Y".
argument-hint: "TICKER (NSE symbol or company name) [--quick | --deep | --fundamentals]"
allowed-tools: Read, Write, Agent, Skill, mcp__indmoney__*, mcp__plugin_everything-finance_indmoney__*, mcp__kite__*, mcp__plugin_everything-finance_kite__*, mcp__upstox__*, mcp__plugin_everything-finance_upstox__*, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-personal__resolve_holdings, mcp__plugin_everything-finance_finance-personal__resolve_holdings, mcp__finance-workflow__*, mcp__plugin_everything-finance_finance-workflow__*
---

# Deep Analysis: the multi-agent debate on one stock

Reads one named stock. With no company or ticker ("analyze a good stock"), hand off to
`discover stocks --invest`; never guess a stock.

**Method:** `methods/verdict.md` (how the lenses combine and how the debate runs). Each leg skill
names its own method.

## 1. Resolve the stock

Resolve the argument to an NSE symbol; `get_company_fundamentals` on it confirms the company. For
`--quick` request only `sections=["ratios", "pnl_10y", "balance_sheet_10y", "cash_flow_10y",
"shareholding", "peers"]` and keep the response for the quick pass; other modes take the full
response.

If the symbol will not resolve, do not brute-force it: one clean symbol and at most one obvious
alternative. A rename that Tickertape search cannot reach still has a sid: read it from the
Tickertape stock URL (…-SID), pass `sid=` to `get_company_fundamentals`, and hand the same sid to
the legs. Without a trustworthy sid, ask the user at once. Never proceed on a near-match ticker's
financials.

## 2. Resolve the mode

| Mode | Documents | Legs | Debate | Agents |
|---|---|---|---|---|
| `quick` | none, structured data only | one pass here | none | 0 |
| `standard` (default) | fetched in phase 0 | financials, management, valuation, news, sector | one contest pass | 8 |
| `deep` | fetched in phase 0 | all six (adds technical) | up to 3 bull/bear rounds | 10–14 |
| `fundamentals` | fetched in phase 0 | financials, management, valuation | none | 4 |

`quick` is the elimination screen: keep, reject or review with cited reasons, no score, no deck.
`standard` is the full investment judgment; timing (technical) is left out because timing does not
eliminate a stock, while an industry with no growth story does. `deep` brings back the chart and
the iterative debate for finalists.

1. A fundamentals-only request ("are the fundamentals good?") means appending `--fundamentals` to
   the argument string.
2. **Check every connected account** for a holding or open position: `networth_holdings` with
   `asset_type="IND_STOCK"`, and each broker's holdings and positions. `yes` is a match in any
   account; `no` needs every connected account to answer completely; otherwise `unknown`. List a
   failed account as a gap even when another said `yes`. Normalize through `resolve_holdings`,
   keeping per-account quantity and cost; if the overlap cannot be reconciled, leave totals
   unknown and pass the account rows and the gap to the portfolio-manager. `--quick` may skip the
   check when no holdings were supplied (it sizes nothing) and record `unknown`.
3. `resolve_analysis_mode(args=<raw argument string>, symbol=<TICKER>, holding=<yes|no|unknown>)`
   returns `{mode, reason}` and gaps. When a holding escalated the run, print its reason line.

Record the mode, the reason and the gaps; the synthesis reports all three.

**Build on the last run.** `get_prior_run(skill="deep-analysis", subject=TICKER)`
(`skill="fundamentals"` in fundamentals mode). If one exists, read it and pass the prior verdict
and levels to the legs as context; the deck then carries a "what changed since" slide.

## 3. Phase 0: you run it, no agent

- **Market context**: `get_market_context(mode="quick")`. Its `market_posture` and
  `volatility.band` go to the portfolio-manager (sizing only); the stock's cap-tier
  `valuation.stance` goes to the valuation leg as context.
- **Documents** (not `quick`): `get_documents(TICKER, annual_reports=3, concalls=4)`. A year of
  concalls lets the management leg test promises against delivery. It returns paths, never text:
  hand each row's `text_path` and `outline` to the document-reading legs. You never open one.
- **The peer set** (not `quick`): the `peers` rows from `get_company_fundamentals` are grouped by
  Tickertape sub-sector, not by business. Drop rows that do not compete for the same customers and
  add the listed competitors the annual report or concall names, each priced with
  `get_company_fundamentals(<SYMBOL>, sections=["ratios"])`. Record what you dropped and added and
  why. Pass the corrected list to both the valuation and sector legs, so the peer median and the
  "leader or laggard" read describe the same companies.

Pass the phase-0 responses and paths, with their dates, to every leg. A leg fetches again only for
a missing section or a deliberate refresh, and notes what changed.

**Sector cache.** Map the stock to its sector (its `get_company_fundamentals` industry) and read
`artifacts/state/sectors/<sector-slug>.md`. With a `generated:` date at most 30 days old and a
`### The growth story` section, pass the cached body and the focus ticker so the leg computes only
the stock's position; otherwise pass no body. Seeding the cache is the sector skill's job.

## 4. Phase 1: the legs, one wave

Each leg is a skill run inside a profile agent. Create the bundle first:
`prepare_report(session=<session id from SessionStart>, ticker, date, mode, telegram=<only if the
user asked>)`. On a client without that hook, generate one UUID and reuse it. Pass the returned
`run_dir`, `report_json`, `report_html` and `agents_dir`; never build these paths yourself. Work
papers go in `agents_dir` (valuation writes `dcf.md` and `dcf-inputs.yml`, management writes
`management.md`).

| Leg skill | Profile | Inputs beyond the ticker | Modes |
|---|---|---|---|
| `financial-analysis` | `everything-finance:terminal-analyst` | company name, document paths and outlines | standard, deep, fundamentals |
| `valuation-analysis` | `everything-finance:terminal-analyst` | document paths and outlines, the peer list, the cap-tier stance | standard, deep, fundamentals |
| `management-analysis` | `everything-finance:field-analyst` | company name, document paths and outlines | standard, deep, fundamentals |
| `news-scan` | `everything-finance:field-analyst` | company name | standard, deep |
| `sector-analysis` | `everything-finance:terminal-analyst` | sector, the ticker as focus stock, the peer list, document paths and outlines, the cached body when fresh | standard, deep |
| `technical-analysis` | `everything-finance:terminal-analyst` | none | deep |

Issue every `Agent` call of the wave in one message when the host allows parallel agents;
otherwise run them one at a time with the same scope. Wait the way the host supports: if it
resumes you when an agent finishes, stop after dispatching; never poll with sleeps. Read an output
path only after its writer has finished; if a worker reports failure but its file is complete,
check the file before rerunning.

Each leg writes its full report (its machine-read block, then `## Findings`, then `## Detail`) and
returns only its digest and path (`finance/contracts.md` → *Convention: leg digest*). Downstream
agents and the writer receive paths; you never hold six reports at once.

The financials leg reports `clean_eps`; the valuation leg derives its own adjustment from the same
rows in the same wave. Where the two disagree, the synthesis names both and says which the verdict
used. A failed leg is a gap and the run continues.

## 5. Phases 2 and 3: the debate and the verdict

- **`quick`**, run here, no agents. Pair periods by label, keeping FY and TTM apart, and read cash
  conversion, debt and interest burden, returns and their trend, shareholding and pledge, and
  current multiples against peers (`methods/fundamentals.md`). Call `get_shareholding` only if
  pledge data is missing and `get_stock_ratios` only for a missing field. Ratios cannot show
  fraud, integrity or intrinsic value; those stay unassessed, and a high P/E alone is no reason to
  reject. `reject` needs a sourced failure of the stated criteria (criterion, period, evidence);
  `keep` means the checks that could run passed, and says which (worth full research, not a BUY);
  `review` means a material check is missing, contradictory or needs documents. Write `quick.md`
  under the stock's dated directory as a `quick-block` (`verdict`, `lean`, `flags`, `reasons`,
  `gaps`) and a short sourced explanation; return those fields and the path. When discover
  launched a worker for this name, that worker does the whole pass. Nothing below applies.
- **`standard`**: fork one `everything-finance:contest-researcher` with the five leg paths and an
  output path. A `genuinely split` lean adds a one-line suggestion to re-run `deep`; it never
  escalates on its own.
- **`deep`**: fork `everything-finance:debate-researcher` twice per round, once with `side: bull`
  and once with `side: bear`, starting with the six leg paths in round 1. After each round, call
  `decide_debate_round(bull=<bull debate-block>, bear=<bear debate-block>, round=<N>)`. While it
  escalates, re-fork each side with its own previous report, the other side's, the round number
  and the returned `directive`, verbatim. Name the files `bull-r<N>.md` and `bear-r<N>.md`. Record
  `rounds_run`, the stop reason, and whether the sides ever met on one axis. An `ok:false` result
  means a digest broke its contract: report it, do not treat it as convergence.
- **Verdict** (standard and deep): fork `everything-finance:portfolio-manager` once with its
  output path (`agents_dir/verdict.md`), the leg paths, the debate paths, `position` (`{held, qty,
  avg_cost, unrealised_pct}` from step 2), `debate` (`{rounds_run, stopped_because, engaged}`)
  and the market context. Pass facts, not rulings: it holds its own judging method.
- **`fundamentals`**: no debate, no verdict agent. The deck renders the sector and technical slots
  as `not run (fundamentals)`; there is no entry, stop, target or sizing. An integrity FAIL is the
  headline: AVOID whatever the numbers say.

## 6. Synthesis and the deck

`quick` stops at step 5. For the other modes the deck is the deliverable; there is no markdown
report. Fork one `everything-finance:report-writer` with the bundle's `report_json` as output path,
the fixture `finance/report/fixtures/deep-analysis.sample.json`, every work-paper path, and the run
facts only you hold: ticker, company, date, CMP (`get_quote`), mode and its reason, the debate
shape, the agent count, the prior-run path, the peer rows dropped and added, and the gaps you
recorded (the broker check, a failed leg, a skipped phase-0 call). Do not read the papers yourself
to check its work.

Then `render_report(report_json=<report_json>, template="deep-analysis", out=<report_html>)`. When
the deck is rendered and every work paper is written, create an empty `ready` file in `run_dir`
and call `publish_report(session=…, run_id=<run_dir's name>)`. Link the archived `report_html`. If
publishing fails, leave staging in place and report the gap; the Stop hook retries ready bundles
from this session.

In chat, from the digests you already hold: the verdict, the two strongest opposing arguments, the
sector's growth story in one line with its stance, and the invalidation level. In fundamentals
mode: the fundamentals verdict, the integrity gate, the intrinsic-value range with DCF confidence,
and the two strongest flags.

## Alerts (`manage_alerts`, `created_by: deep-analysis`)

- `reanalyze_due`: `due` = today plus the verdict's review cadence, `subject_type: stock`,
  `severity: watch`, `suggest: "/deep-analysis <TICKER>"`, `dedup_key: reanalyze-<TICKER>`.
- `price_cross` at the invalidation level: for a long thesis `metric: close`, `op: "<"`,
  `level: <invalidation>`, `severity: act`, `text: "thesis invalidation level"`,
  `dedup_key: invalidate-<TICKER>`.
- On a BUY, an `opportunity` alert: `severity: watch`, `text` = the one-line thesis,
  `suggest: "/trade-tracker <TICKER>"`, `dedup_key: opp-<TICKER>`.

Fundamentals mode raises only `reanalyze_due`.
