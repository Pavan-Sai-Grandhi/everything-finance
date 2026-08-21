---
name: insurance-advisor
description: Advise on buying, auditing, or understanding insurance — term life, health, and vehicle. Three modes. (1) Advise/buy — interview, size the need, research the market, shortlist exactly two policies and compare them side by side. (2) Audit — need-vs-have gap, red flags, and whether to keep an in-force endowment/ULIP. (3) Ask — answer questions about a policy the user already holds. Use whenever the user wants to buy/compare insurance, asks if their cover is enough, mentions a policy document, asks about ULIPs/endowment plans, "how much cover do I need", or a question about their own policy.
argument-hint: "[what you want: buy/compare, review my cover, or a question about my policy — + policy type and details]"
allowed-tools: WebFetch, WebSearch, Read, Write, mcp__finance-personal__run_insurance_math
---

# Insurance Advisor

Always load `references/reference.md` (shared framework, interview discipline, web-research guardrails, compliance close) **plus** the relevant per-type reference — `references/term.md`, `references/health.md`, or `references/vehicle.md`. Each type is judged on different criteria; those files carry them.

**Sources for this skill only:** insurer and IRDAI pages via `WebFetch` / `WebSearch`. No data tool in this plugin covers insurance products, and no personal MCP is read here — the user's own policies come from what they paste or the PDFs they point at.

All computed figures come from `run_insurance_math` — call it, don't eyeball. Pass the calculation's keyword inputs as `inputs`; each one is a sourced figure or a stated assumption, and every assumption lands in the report's Assumptions table.

## Route the intent first

Read the user's phrasing and pick the mode:
- **"help me buy / compare / which policy / how much cover"** → **Advise**.
- **"is my cover enough / review my policies / should I keep this ULIP"** → **Audit**.
- **"does my policy cover X / explain this clause / portability / renewal"** → **Ask**.

Also identify the **type** (term / health / vehicle) from the request. If the mode is ambiguous, ask which of the three the user wants (one short question). If the type is unclear, ask that too — then proceed. Load the shared reference + the per-type reference for the chosen type.

---

## Mode: Advise (buy) — primary flow

Type-aware interview → size the need → research candidates → score → **shortlist exactly 2** → side-by-side.

**1 — Interview.** Ask the per-type questions (see the type's reference), **one at a time**, conversationally. Missing answers become **stated assumptions** in the Assumptions table — never stall.

**2 — Size the need** with `run_insurance_math`:
- term → `term_cover_need` (larger of income-replacement and liability+goals; gap vs existing cover).
- health → `health_sum_insured` (base + super top-up; employer cover at half weight).
- vehicle → `idv_ncb_sanity` on the current/quoted IDV & NCB.

**3 — Research candidates** under the sourcing guardrails in `reference.md` (IRDAI authoritative, every figure sourced and dated, premiums indicative, too-few-candidates handling).

**4 — Score** each candidate against the type's weighted checklist in its reference.

**5 — Shortlist exactly 2** and render a **side-by-side comparison** on the type-specific criteria, then a **reasoned pick** and a one-line **"what would change the call."**

**6 — Save** to `paths.insurance_report_path(<type>)` → `insurance/<type>/YYYY-MM-DD.md`. Text-first (no HTML). End with the compliance close.

---

## Mode: Audit (existing coverage)

- Gather current policies (from the user or policy PDFs they point to — read them).
- Compute **need vs have** with `run_insurance_math`; report the **₹ gap per category** in a current-vs-required table.
- **Assumptions table** — every value assumed, with the figure used.
- **Policy-level red flags** from the relevant per-type reference, each tied to the clause in the user's own document.
- For an in-force **endowment/ULIP** held "for investment": compute the **marginal IRR of *continuing*** (`marginal_irr_continue` — forgo surrender value + pay remaining premiums → maturity) and compare to a safe hurdle. Say plainly whether to keep it or surrender-and-buy-term-invest-the-rest, and label marginal-IRR vs whole-policy-IRR.
- 3–5 prioritised actions with rough premium magnitudes.
- Save to `paths.report_path("insurance")` → `insurance/YYYY-MM-DD.md`. End with the compliance close.
- **As wealth-manager's protection leg:** the need-vs-have gap table and red-flag list computed here are exactly the `protection-block` digest (`finance/contracts.md`) — the `wealth-leg` runner distils them from this report. Nothing extra to compute here.

---

## Mode: Ask (Q&A on a held policy)

- Read the user's policy PDF (they point to it) and answer the specific question — does it cover X, what does this clause mean, portability, renewal call — grounded in the relevant per-type reference.
- Quote the policy wording you're relying on; separate **what the document says** from **general best-practice**. If the document doesn't settle it, say so and name what to check with the insurer — never fabricate a term.
- Short answers stay conversational (no artifact needed); a full policy review can be saved via `paths.report_path("insurance")`. End with the compliance close.

