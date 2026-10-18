---
name: management-analysis
description: Judge whether an Indian company's management can be trusted and whether they're any good — the part of fundamental analysis that ratios can't capture (Philip Fisher put ~90% of analysis effort on management). Screen integrity first as a hard gate (remuneration vs profit, related-party transactions, criminal/regulatory record, media-savvy/share-price obsession, CFO/auditor churn and fees, refusal to own mistakes, promoter pledging), then grade skill (qualification & experience, growth vs comfort-zone mindset, capital allocation, succession plan). Reach for this skill whenever the user asks about the people running a specific company — "is the promoter honest/trustworthy", "any governance red flags", "should I worry about the related-party dealings or the pledging", "their auditor/CFO just resigned", "is there a succession plan", "are they good capital allocators", "is the management any good" — even when they don't say the word "management". This is the governance/integrity read on one company, distinct from exchange-filing alerts (→ filings-watch) and from the fundamental ratio scorecard. It is also the governance leg inside deep-analysis, and it writes the company's story — how it started, how it grew, and who the promoters and leaders are — that the deck opens with.
argument-hint: "TICKER or company name"
allowed-tools: WebFetch, WebSearch, Read, Write, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-workflow__get_prior_run, mcp__plugin_everything-finance_finance-workflow__get_prior_run
---

# Management Analysis: the integrity gate, then the skill grade

Two pillars, in order: **integrity** as a hard gate, then **skill** for the honest ones. This
judges intention and pattern, so keep verified fact, allegation and inference apart, and run the
full method whatever depth was asked: integrity is a gate, not a level of detail. A grade always
carries a confidence; an unsourced signal is a labelled gap. It informs a decision; it never
sizes a position.

**Method:** `methods/management.md`.

## Gather the evidence

The evidence is disclosures, not opinions.

0. **Prior run**: `get_prior_run(skill="management", subject=SYMBOL)`. If one exists, read it and
   open the scorecard with `prior run: <path> (<date>)`, noting any change in the gate or grade.
1. **Shareholding**: `get_company_fundamentals(symbol)` for the six-quarter trend with
   Tickertape's pledge figure, and `get_shareholding(symbol)` for NSE's pledge rows. An empty
   pledge list is a gap, never zero pledge.
2. **Documents**: `get_documents(symbol, annual_reports=3)`, unless the paths were handed to you.
   Read the line ranges each `outline` gives and cite the filing itself. Both tools cache, so call
   each once.
3. **In the annual reports**: `remuneration`, `related_party`, `auditor_remuneration`,
   `corporate_governance` (board and KMP profiles), and `mdna` across all three years, plus
   impairments and goodwill write-offs. A missing key means searching for other heading wording
   before marking a check NOT-CHECKED.
4. **In the concall**: the Q&A as asked and answered (`outline.qna`): capital allocation,
   candour, the questions evaded, succession.
5. **Criminal and regulatory record**, the one thing no filing holds: `WebSearch` the method's
   defined query set (check 3), built from the board and KMP names you just read, and report the
   queries you ran. Three attempts per question, then stop: an open matter (a pending approval, a
   live proceeding) reads the same as a search that missed, so record it as unresolved with the
   date you looked. For an IPO read the RHP's litigation section.
6. **The story and the people**: read `outline.history`, `outline.chairman_message` and
   `outline.director_profiles` in the newest report, and for founding facts the offer document's
   *History and Certain Corporate Matters* and *Our Promoters* chapters (the RHP or DRHP on
   `sebi.gov.in`, `nseindia.com` or `bseindia.com`, through `WebSearch` restricted to those
   domains). The company's own "about" or "history" page is a primary source for its milestones;
   cite its URL. Every year, name and role carries a source; anything none of these give is a
   gap.
7. **The arithmetic**: `run_governance_checks` scores check 1 (pay against profit) and the fee
   half of check 5 on the figures you read. Never do this division by hand.

## Report

Write only to the path deep-analysis gives you; standalone, fill
`assets/management-scorecard.example.md` into `artifacts/stocks/<SYMBOL>/<YYYY-MM-DD>/management.md`.
Its leading `management-block` is machine-read: keep every field name exactly as the template has
it. Score each of the seven integrity checks separately and aggregate them into the gate per the
method. A FAIL overrides every other lens: say so explicitly and make it unmissable in the digest.

Return only the `management-block` fields plus `path`.
