---
name: insurance-check
description: Audit life and health insurance coverage adequacy against actual need — income replacement math, health cover sizing, policy red flags (room rent caps, co-pay, exclusions), and a prioritized gap list. Use whenever the user asks if their insurance is enough, wants to review/buy term or health insurance, mentions a policy document, asks about ULIPs/endowment plans, or asks "how much cover do I need".
argument-hint: "[current covers + income + dependents, or path to policy docs]"
allowed-tools: WebFetch, Read, Write, Bash
---

# Insurance Coverage Check

Read `references/reference.md` first — it carries the Varsity insurance module's framework (cover sizing, policy red flags, what's a gimmick).

This skill is primarily **interview + arithmetic**, not scraping. Web use is limited to: Varsity chapters for framework details if needed. No insurer marketing pages, no aggregator quote engines.

## Step 1 — Gather the picture

From the user (or policy PDFs they point to — read them):
- Age, annual income, dependents (ages), outstanding loans, existing corpus
- Life: each policy's type (term/endowment/ULIP), sum assured, premium, total policy term, years already paid, expected maturity/bonus value if known, surrender value if known
- Health: sum insured, individual vs family floater, employer vs personal, room-rent cap, co-pay, disease sub-limits, waiting periods served

Missing data: proceed with stated assumptions rather than stalling; list assumptions in the report.

## Step 2 — Compute need vs have

**Life (term) need** = larger of:
- Income replacement: 10–15× annual income (15× if dependents are young), plus
- Liability + goals method: outstanding loans + children's education corpus + (annual family expenses × years to youngest dependent's independence) − existing liquid corpus

**Health need**: metro baseline ₹10L individual / ₹15–25L family floater (medical inflation ~12–14%); employer cover counts at half weight (it vanishes with the job). Super top-up is the cheap way to extend.

**Flag traditional products**: endowment/ULIP/moneyback held for "investment" — compute the implied IRR (typically 1–5%; flag anything below inflation). If policy term or maturity value is unknown, run labeled scenarios rather than guessing one number. For in-force policies the decision-relevant figure is the **marginal IRR of continuing** (forgo surrender value + pay remaining premiums → maturity), not the whole-policy IRR — compute both and say which is which. Recommendation framework in reference.md is buy-term-invest-the-difference.

## Step 3 — Gap report

Markdown report (no HTML template — this skill is deliberately text-first, no assets/ dir) with: current vs required table, ₹ gap per category, an **Assumptions table** (every value assumed in Step 1, with the assumed figure), policy-level red flags found (room rent cap < 1% of SI/day, co-pay > 0, restoration absent, claim-settlement-relevant disclosure risks), and 3–5 prioritized actions with rough premium magnitudes. Save to `artifacts/insurance/YYYY-MM-DD.md` (`paths.report_path("insurance")`). End with: this is needs analysis, not solicitation of any product.
