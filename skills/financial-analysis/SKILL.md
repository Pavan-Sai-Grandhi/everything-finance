---
name: financial-analysis
description: Score one Indian company's numbers against the Varsity due-diligence checklist and write a standalone Company Overview of what the business actually is — returns (ROE DuPont'd, ROCE vs cost of capital), the five-year operating-margin trend, debt and interest cover, whether cash follows profit, promoter holding and pledge, revenue growth, and whether reported profit is the profit the business earned — with the annual report and latest concall read directly and cited by page. Use whenever the user asks whether a company's numbers stack up: "are the fundamentals good", "is X financially sound", "what's their ROCE / debt like", "is the profit backed by real cash", "is that P/E real", "what does this company actually do", "what did their annual report / last concall say", "any red flags in the accounts". This is the numbers-and-business read on one company — what it's worth is valuation-analysis, whether the people running it can be trusted is management-analysis, and the full bull/bear debate is deep-analysis.
argument-hint: "TICKER [optional: company name; optional: document paths already fetched]"
allowed-tools: Read, Write, mcp__finance-company__*
---

# Financial Analysis — the Varsity checklist and the Company Overview

Read `references/reference.md` first — it owns the method: the seven checks with their thresholds and what each is really testing, the published-row vocabulary and the four labels that mean something other than they say, what the primary documents must supply, and how the verdict is graded. This SKILL is the workflow.

**Sources for this skill only:** `finance-company` — `get_company_fundamentals(symbol)` (ten fiscal years of balance sheet and cash flow, ten plus a trailing-twelve-month column of P&L, quarters, ratios, six quarters of shareholding) and `get_documents(symbol)` (annual report and latest concall, downloaded and converted to cached local text).

## Workflow

1. **Inputs**: the ticker, the company name where you have it, and — where an orchestrator already called `get_documents` — the document `text_path`s and an output path.
2. **Pull the figures.** `get_company_fundamentals(SYMBOL)`. It is day-cached at the tool, so call it once and work from what it returned.
3. **Read the primary documents.** `get_documents(SYMBOL)` unless the paths were handed to you. Each row's `outline` maps the notes to their line numbers in `text_path` — read those line ranges rather than the whole file, which runs to tens of thousands of lines. You need `tax_note` (the effective rate is *required*; nothing on the feed carries it), `segment` and `mdna` for the overview, `contingent_liabilities`, `emphasis_of_matter` and `related_party` for the flags. A key absent from `outline`, or a document that would not download, is a labelled gap for the checks that needed it.
4. **Score the seven checks**, each PASS / FLAG / FAIL with the number that decided it, and set `varsity_score` to the count of PASS.
5. **Write the Company Overview** from the segment note and MD&A, with the mix percentages tying to the published revenue.
6. **Pull the flags out**, red and green, each tied to a figure or a cited page, and call the verdict.

## Produce this report

The leading block is machine-read, so the PM and synthesis cite the scorecard without re-deriving it:

```
<!-- financials-block
verdict: investment-grade | watch | avoid   confidence: low | med | high
varsity_score: <n-of-7 PASS>   roce: <x%>   de: <x>   cfo_ebitda: <x>   rev_cagr_5y: <x%>
clean_eps: <₹x, or a bracketed range>   eps_adjustments: <what was stripped, or none>
flags: <comma-separated top red/green flags>
axis: growth_durability
-->
## Financials — <TICKER> (<date>)
**Company overview**: what it does, segments & revenue (and EBIT where disclosed) mix %, geography split, flagship products/brands, key end-markets, and the moat that protects economics. Self-contained — a reader meeting the company here should be oriented.
**Checklist scorecard**: ROE/ROCE (3y trend) | margins | D/E + interest cover | CFO vs EBITDA | promoter holding & pledge | revenue CAGR | earnings quality — each PASS/FLAG/FAIL + the number
**Annual report findings**: 3–5 specifics with page/section cites (auditor quals, RPTs, contingent liabilities, segment shifts)
**Concall takeaways**: guidance + 2–3 management quotes/paraphrases with quarter cite
**Earnings quality**: reported vs clean EPS, what was stripped and its source, and the adjustment as a % of reported PAT
**Multiples (context, not a call)**: the current P/E and market cap as sourced facts, and P/B **derived** (labelled) as `Current Price ÷ Book Value` — both are in `ratios`, but the P/B ratio itself is not published — stated beside the growth and return numbers above. Where `eps_adjustments` is not `none`, state the P/E **on both bases** and label which is which
**Red flags** / **Green flags**: bulleted, evidence-tied
**Verdict**: investment-grade / watch / avoid, one sentence, confidence low/med/high
```

Write it to the output path you were given, or to `artifacts/stocks/<TICKER>/YYYY-MM-DD/financials.md` (`paths.stock_dir(symbol, date)`) when none was. **Keep every field name exactly as the block has it.** Persist the full report, then return only the `financials-block` fields plus `path`.

## Boundaries

This is the numbers leg. **It states multiples; it does not judge them.** The peer set, the peer-median multiple, PEG, the own-history band percentile and the Undervalued / Fair / Overvalued call all belong to `valuation-analysis`, which computes them once — do not build a second peer comparison here. `clean_eps` is the exception it consumes: the earnings base is a *numbers* finding, and the valuation leg strikes its multiples on whichever basis this leg reports. Whether management can be trusted with these numbers is `management-analysis`. Where either is relevant to a flag, point at that leg rather than answering for it.

You inform a decision; you do not recommend or size a position.
