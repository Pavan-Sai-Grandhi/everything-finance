---
name: management-quality
description: Judge whether an Indian company's management can be trusted and whether they're any good — the part of fundamental analysis that ratios can't capture (Philip Fisher put ~90% of analysis effort on management). Screen integrity first as a hard gate (remuneration vs profit, related-party transactions, criminal/regulatory record, media-savvy/share-price obsession, CFO/auditor churn and fees, refusal to own mistakes, promoter pledging), then grade skill (qualification & experience, growth vs comfort-zone mindset, capital allocation, succession plan). Reach for this skill whenever the user asks about the people running a specific company — "is the promoter honest/trustworthy", "any governance red flags", "should I worry about the related-party dealings or the pledging", "their auditor/CFO just resigned", "is there a succession plan", "are they good capital allocators", "is the management any good" — even when they don't say the word "management". This is the governance/integrity read on one company, distinct from exchange-filing alerts (→ filings-watch) and from the fundamental ratio scorecard. Invoked by the management-analyst as the management read inside deep-analysis and fundamental-analysis.
argument-hint: "TICKER or company name"
allowed-tools: WebFetch, WebSearch, Read, Write, Skill, mcp__finance-company__*
---

# Management Quality — integrity gate, then skill grade

Read `references/reference.md` first — it is the full method: every sub-check, its threshold and what it means, and how the two pillars combine into a verdict. This SKILL is the workflow.

Two pillars, in order: **integrity** (will they treat minority shareholders honestly?) as a *hard gate*, then **skill** (can they grow the business?) for the honest ones.

## Data gathering (primary sources only)

First, **check for a prior run** with `paths.latest_prior("management", SYMBOL)` — if an earlier `management.md` exists, read it for context and open this scorecard with a one-line `prior run: <path> (<date>)` link noting any change in the integrity gate or skill grade.

The evidence lives in disclosures, not opinions. Gather, in order:

1. **`get_company_fundamentals(symbol)`** — the shareholding trend and the `documents` links (annual reports, concall transcripts). **`get_shareholding(symbol)`** for promoter **pledge %** by quarter; an empty pledge list is a labelled gap, **not zero pledge**.
2. **Latest 2–3 annual reports** (the envelope's `documents` links, read with `WebFetch`) — read these notes specifically:
   - **Remuneration of directors / KMP** (and related-party remuneration) — vs net profit, vs MCA limit, relatives on payroll.
   - **Related-party transactions** — counterparties, amounts, rates; look for abnormal loans/purchases/deposits.
   - **Payment to auditors** — level and trend (5–10y), peer-relative.
   - **Board & KMP profiles** — qualification, sector experience, age (succession).
   - **MD&A over multiple years** — durable plans vs fad-chasing; were past plans executed?
   - **Impairments / goodwill write-offs** — owned honestly or rationalised away?
   Use the `pdf` skill (via Skill) for extraction if a PDF resists direct reading.
3. **Concall transcripts** — capital-allocation commentary, candour, dodged questions, succession.
4. **Criminal / regulatory history** — `WebSearch` the company and promoter names with "scam / fraud / SEBI order / warning"; for IPOs read the **RHP** litigation section. Use only filings, the regulator, and well-known financial press.

## Produce this report

Fill `assets/management-scorecard.example.md` → `artifacts/stocks/<SYMBOL>/YYYY-MM-DD/management.md` (`paths.stock_dir(symbol, date)`):

- **Integrity scorecard** — each of the 7 sub-checks: PASS / FLAG / FAIL with the specific number / AR note / filing behind it.
- **Integrity verdict**: PASS / FLAG / FAIL, per the reference's hard-failure list.
- **Skill scorecard** (only meaningful if integrity isn't FAIL) — the 4 checks: qualification & experience, mindset, capital allocation, succession — each STRONG / ADEQUATE / WEAK with evidence.
- **Overall management grade** + one-line rationale + confidence (low/med/high). Integrity FAIL ⇒ overall **AVOID**.
- **Data gaps** — what you couldn't verify.

## Boundaries

This grades *people and intention*, so a grade always carries a confidence. You inform a decision; you don't size a position.
