---
name: financial-analysis
description: >-
  Score one Indian company's numbers against the seven-check due-diligence scorecard and write a standalone Company Overview of what the business actually is — returns (ROE DuPont'd, ROCE vs cost of capital), the five-year operating-margin trend, debt and interest cover, whether cash follows profit, promoter holding and pledge, revenue growth, and whether reported profit is the profit the business earned — with the annual report and latest concall read directly and cited by page. Use whenever the user asks whether a company's numbers stack up: "are the fundamentals good", "is X financially sound", "what's their ROCE / debt like", "is the profit backed by real cash", "is that P/E real", "what does this company actually do", "what did their annual report / last concall say", "any red flags in the accounts". This is the numbers-and-business read on one company — what it's worth is valuation-analysis, whether the people running it can be trusted is management-analysis, and the full bull/bear debate is deep-analysis.
argument-hint: "TICKER [optional: company name; optional: document paths already fetched]"
allowed-tools: Read, Write, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*
---

# Financial Analysis: the scorecard and the Company Overview

The numbers-and-business leg. It states multiples and does not judge them: the peer set, the
peer-median multiple, PEG, the own-band percentile and the value stance all belong to
`valuation-analysis`, which consumes this leg's `clean_eps`. Whether management can be trusted is
`management-analysis`. Point at those legs rather than answering for them. It informs a decision;
it does not recommend or size a position.

**Method:** `methods/fundamentals.md`.

## Workflow

1. **Inputs**: the ticker, the company name where known, and, from an orchestrator, document
   paths with their outlines and an output path.
2. **Figures**: `get_company_fundamentals(SYMBOL)`, once (it is day-cached).
3. **Documents**: `get_documents(SYMBOL)` unless paths were handed to you. Read the line ranges
   the `outline` gives for `tax_note` (required: nothing on the feed carries the effective rate),
   `segment` and `mdna` (the overview), and `contingent_liabilities`, `emphasis_of_matter` and
   `related_party` (the flags). A missing key means searching the text for other heading wording;
   if that fails, or the document did not download, the affected checks carry a gap.
4. **Score the seven checks**, each with the number that decided it (NOT-APPLICABLE for checks 3
   and 4 on a bank, NBFC or insurer), and set `checklist_score`.
5. **Write the Company Overview** from the segment note and MD&A.
6. **Pull out the flags**, red and green, each tied to a figure or a cited page, and call the
   verdict.

## Report

```
<!-- financials-block
verdict: investment-grade | watch | avoid   confidence: low | med | high
checklist_score: <n PASS> of <7 or the applicable count>   roce: <x%>   de: <x or n/a>   cfo_ebitda: <cycle CFO ÷ (EBITDA − tax paid − material other income), or n/a>   rev_cagr_5y: <x%>
clean_eps: <₹x, or a bracketed range>   eps_adjustments: <what was stripped, or none>
flags: <comma-separated top red/green flags>
axis: growth_durability
-->
## Financials — <TICKER> (<date>)

## Findings
<Everything from this leg that could change a verdict, in 3-6 plain sentences — each with its number and where it came from. A reader who stops here has the leg's whole case.>

## Detail

**Company overview**: what it does, segment revenue (and EBIT where disclosed) mix %, geography, flagship products or brands, end-markets, and the moat.
**Checklist scorecard**: ROE/ROCE (3y trend) | margins | D/E + interest cover | CFO vs EBITDA less tax and other income | promoter holding & pledge | revenue CAGR | earnings quality — each PASS/FLAG/FAIL + the number
**Annual report findings**: 3–5 specifics with page or section cites
**Concall takeaways**: guidance and 2–3 management statements with the quarter
**Earnings quality**: reported vs clean EPS, what was stripped and its source, the adjustment as a % of reported PAT
**Multiples (context, not a call)**: the current P/E and market cap as sourced facts, and P/B derived (labelled) as Current Price ÷ Book Value. Where `eps_adjustments` is not `none`, the P/E on both bases, labelled
**Red flags** / **Green flags**: bulleted, evidence-tied
**Verdict**: one sentence, with confidence
```

Write it to the output path given, or to `artifacts/stocks/<TICKER>/<YYYY-MM-DD>/financials.md`.
Keep every field name exactly as the block has it. Return only the `financials-block` fields plus
`path`.
