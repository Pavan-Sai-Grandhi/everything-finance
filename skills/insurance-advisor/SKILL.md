---
name: insurance-advisor
description: Advise on buying, auditing, or understanding insurance — term life, health, and vehicle. Three modes. (1) Advise/buy — interview, size the need, research the market, shortlist exactly two policies and compare them side by side. (2) Audit — need-vs-have gap, red flags, and whether to keep an in-force endowment/ULIP. (3) Ask — answer questions about a policy the user already holds. Use whenever the user wants to buy/compare insurance, asks if their cover is enough, mentions a policy document, asks about ULIPs/endowment plans, "how much cover do I need", or a question about their own policy.
argument-hint: "[what you want: buy/compare, review my cover, or a question about my policy — + policy type and details]"
allowed-tools: WebFetch, WebSearch, Read, Write, mcp__finance-personal__run_insurance_math, mcp__plugin_everything-finance_finance-personal__run_insurance_math
---

# Insurance Advisor

Term life, health and vehicle. Insurer and IRDAI pages are reached with `WebFetch` and
`WebSearch`; no data tool covers insurance products, and the user's own policies come from what
they paste or the PDFs they point at. Every computed figure comes from `run_insurance_math`; each
input is a sourced figure or a stated assumption, and every assumption lands in the report's
Assumptions table.

**Method:** `methods/insurance/framework.md` plus the type's file: `term.md`, `health.md` or
`vehicle.md` in the same directory.

## Route the request

- "help me buy / compare / which policy / how much cover" → **Advise**.
- "is my cover enough / review my policies / should I keep this ULIP" → **Audit**.
- "does my policy cover X / explain this clause / portability / renewal" → **Ask**.

Identify the type too. If either is ambiguous, ask one short question, then load the method files.

## Advise

1. **Interview**: the type's questions, one at a time. Missing facts are gaps, not zero.
2. **Size the need** with `run_insurance_math`:
   - term: `term_cover_need` with every input explicit (`annual_income`, `income_multiple`,
     `outstanding_loans`, `education_corpus`, `annual_expenses`, `years_to_independence`,
     `existing_corpus`, `existing_cover`). The multiple and the goals are scenario assumptions
     you explain. A positive support horizon needs annual expenses; without them that calculation
     is a gap.
   - health: `health_sum_insured` with `base_target`, `total_target`, `deductible`,
     `personal_cover` and `employer_cover`, the targets labelled as scenarios and the deductible
     and covers taken from the policy documents. Keep employer cover apart from personal cover. A
     gap figure says nothing about whether a claim would be paid.
   - vehicle: `idv_ncb_sanity` on the quoted IDV and NCB, with discontinued-model status. A null
     result is settled from the policy, never assumed to pass; NCB is checked only with both the
     claim-free years and the quoted bonus.
3. **Research candidates** under the framework's sourcing rules.
4. **Score** each against the type's weighted checklist.
5. **Shortlist exactly two**, compare them side by side on the type's criteria, make a reasoned
   pick, and say in one line what would change it.
6. **Save** to `artifacts/insurance/<type>/<YYYY-MM-DD>.md`. End with the compliance close.

## Audit

- Read the current policies the user supplies.
- Compute need against cover with `run_insurance_math` and report the ₹ gap per category in a
  current-vs-required table, with the Assumptions table beside it.
- Red flags from the type's file, each tied to the clause in the user's own document.
- For an in-force endowment or ULIP held "for investment", `marginal_irr_continue` (forgo the
  surrender value, pay the remaining premiums, collect at maturity), compared with a
  `hurdle_rate` only when one is supplied with its source. The IRR alone never decides surrender:
  weigh the cover, replacement availability, guarantees, charges and tax. Label marginal against
  whole-policy IRR.
- Three to five prioritised actions with rough premium magnitudes.
- Save to `artifacts/insurance/<YYYY-MM-DD>.md`. End with the compliance close.
- **As wealth-manager's protection leg**: open the report with the `protection-block`
  (`finance/contracts.md` → *Convention: protection-leg digest*), transcribed from the gap table
  and red flags above, and return that block plus the path.

## Ask

Read the policy the user points to and answer the specific question, quoting the wording relied
on. Keep what the document says apart from general practice. If the document does not settle it,
say so and name what to ask the insurer; never invent a term. A short answer stays in chat; a full
review may be saved to `artifacts/insurance/<YYYY-MM-DD>.md`. End with the compliance close.
