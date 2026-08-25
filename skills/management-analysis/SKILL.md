---
name: management-analysis
description: Judge whether an Indian company's management can be trusted and whether they're any good — the part of fundamental analysis that ratios can't capture (Philip Fisher put ~90% of analysis effort on management). Screen integrity first as a hard gate (remuneration vs profit, related-party transactions, criminal/regulatory record, media-savvy/share-price obsession, CFO/auditor churn and fees, refusal to own mistakes, promoter pledging), then grade skill (qualification & experience, growth vs comfort-zone mindset, capital allocation, succession plan). Reach for this skill whenever the user asks about the people running a specific company — "is the promoter honest/trustworthy", "any governance red flags", "should I worry about the related-party dealings or the pledging", "their auditor/CFO just resigned", "is there a succession plan", "are they good capital allocators", "is the management any good" — even when they don't say the word "management". This is the governance/integrity read on one company, distinct from exchange-filing alerts (→ filings-watch) and from the fundamental ratio scorecard. It is also the governance leg inside deep-analysis.
argument-hint: "TICKER or company name"
allowed-tools: WebFetch, WebSearch, Read, Write, Bash, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-market__get_prior_run, mcp__plugin_everything-finance_finance-market__get_prior_run
---

# Management Analysis — integrity gate, then skill grade

Read `references/reference.md` first — it is the full method: every sub-check, what counts as evidence for it, its threshold and what it means, and how the two pillars combine into a verdict. This SKILL is the workflow.

Two pillars, in order: **integrity** (will they treat minority shareholders honestly?) as a *hard gate*, then **skill** (can they grow the business?) for the honest ones. This judges intention and pattern, so keep **verified fact**, **allegation** and **inference** apart, and run the full method whatever the depth asked for — integrity is a gate, not a level of detail.

## Data gathering (primary documents only)

First, **check for a prior run** with `get_prior_run(skill="management", subject=SYMBOL)` — if `data.path` names an earlier `management.md`, read it for context and open this scorecard with a one-line `prior run: <path> (<date>)` link noting any change in the integrity gate or skill grade.

The evidence lives in disclosures, not opinions. Gather, in order:

1. **`get_company_fundamentals(symbol)`** — the six-quarter shareholding trend, including Tickertape's `Promoter Pledge (% of promoter holding)`. **`get_shareholding(symbol)`** for NSE's pledge rows by quarter; an empty pledge list is a labelled gap, **not zero pledge**.
2. **`get_documents(symbol, annual_reports=3)`** — the last three annual reports and the latest concall, downloaded and converted to text. Every row carries a `text_path` and an `outline` mapping each note to its line numbers; **`Read` those line ranges and cite the filing itself**, never a précis of it, and never the whole file. Both tools cache — fundamentals for the day, a document for good — so call each once and re-read the cached text rather than re-fetching.
3. **In the annual reports**, read the notes `outline` names: `remuneration`, `related_party`, `auditor_remuneration`, `corporate_governance` (board & KMP profiles), `mdna` **across all three years**, and impairments/goodwill write-offs. A key absent from `outline` is a `NOT-CHECKED` for the check that needed it.
4. **In the concall**, read the **Q&A as asked and answered** (`outline.qna`) — capital-allocation commentary, candour, which questions were evaded, succession.
5. **Criminal / regulatory history** — the one thing no filing holds. `WebSearch` the defined query set in the reference's check 3, built from the board/KMP names you just read, and report which queries you ran. **Three attempts per question, then stop.** An open matter — a pending approval, an undecided term, a live proceeding — reads the same as a search that missed, and rewording the query a fourth time does not distinguish them. Record it as unresolved with the date you looked; that is the finding. For IPOs read the **RHP** litigation section. The reference's § "Evidence standard" governs what counts.
6. **Compute what is arithmetic.** `run_governance_checks` scores check 1 (pay vs profit) and the fee half of check 5 on the figures you just read. Each returns a verdict, the number that decided it, and `NOT-CHECKED` when the disclosure was not there. Never do this division by hand.

## Produce this report

Fill `assets/management-scorecard.example.md` → `artifacts/stocks/<SYMBOL>/YYYY-MM-DD/management.md` (`paths.stock_dir(symbol, date)`). Its leading `management-block` is machine-read by `deep-analysis`'s portfolio-manager, which reads the integrity gate without re-deriving it — **keep every field name exactly as the template has it**.

Score each of the seven integrity checks separately and aggregate them into the gate per the reference's § "Pillar 1". **A `FAIL` is the one finding that overrides every other lens** — the numbers, the chart and the valuation stop mattering. Say so explicitly when it fires, and make it unmissable in the digest.

Persist the full report, then return only the `management-block` fields plus `path`.

## Boundaries

This grades *people and intention*, so a grade always carries a confidence. A signal you could not source is a labelled data gap — never invent evidence to fill it. You inform a decision; you don't size a position.
