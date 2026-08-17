# Insurance knowledge base — shared framework

Grounded in Zerodha Varsity — Insurance module (https://zerodha.com/varsity/module/insurance/, 9 chapters by Ditto: Perverse Incentives, The Nudge, Skin in the Game, Dunning-Kruger Effect, A Mighty Defence, No Free Lunch, Gimmick or Not 1–2). Fetched and summarized 2026-06-10. This file is the **shared layer** every mode loads; the per-type detail lives in `term.md`, `health.md`, `vehicle.md` — always load this plus the relevant per-type reference.

## The one stance: insurance is protection, not investment

- **Buy term, invest the difference.** Mixing insurance with investment (endowment, ULIP, moneyback) buys bad versions of both — typical traditional-plan IRR is 4–5%, below inflation. Pure protection (term life, indemnity health, comprehensive motor) + the premium difference invested per the MF framework beats bundled products.
- **Disclosure is the claim.** Smoking, pre-existing conditions, family history, prior claims — misdeclaration is the #1 cause of claim rejection ("Perverse Incentives", "Dunning-Kruger"). Never optimise premium via omission; a cheaper policy that won't pay is worthless.
- **A brochure claim never overrides a best-practice red flag** — the per-type red-flag lists win over marketing copy.

## Interview discipline (all modes)

- **One question at a time**, type-aware (each per-type reference lists exactly what to ask). Conversational, not a form dump.
- **Never stall on a gap.** Missing data → proceed on a **stated assumption**, recorded in the report's **Assumptions table** with the figure used and why. A labelled assumption beats a stalled interview; a labelled gap beats a fabricated number.
- Interview defaults when the user gives no number (assume, label, list):
  - Children's education corpus: ₹40–60L per child in today's money (use ₹50L mid-point).
  - Annual family expenses: 40–50% of gross income if unstated (45% mid).
  - Endowment bonus accrual: run low/mid/high scenarios (simple reversionary ₹40–50 per ₹1,000 SA as mid) rather than one guess.

## Web research + sourcing (Advise mode fetches; all modes obey)

Insurance products are the one domain no `finance-data` source covers, so **named-source WebFetch/WebSearch on insurer and IRDAI pages is the right tool here**. **IRDAI is authoritative** for claim-settlement ratios and registered-insurer status. The research stays qualitative, and every figure carries its source URL + as-of date.

- Premiums are labelled **"indicative — verify with insurer"**. Quote engines that need personal data are flagged **"needs a real quote"** — never auto-fill invented inputs to extract a number.
- Flag promotional/one-sided passages and down-weight them.
- A page that blocks WebFetch is a labelled gap, not a reason to escalate to a browser.
- Too few candidates for a type → present what was found, state the shortfall, ask the user to supply brochures/quotes for the finalists.

## Deterministic math

Every computed figure comes from `scripts/insurance_math.py` (term cover need, health sum-insured sizing, IDV/NCB sanity, marginal-IRR of continuing an in-force endowment/ULIP), not eyeballed in prose. The assumptions feeding it appear in the Assumptions table.

## Artifact contract

- **Advise** (per-type): `paths.insurance_report_path(<type>)` → `insurance/<type>/YYYY-MM-DD.md`.
- **Audit / Ask** (not per-type): `paths.report_path("insurance")` → `insurance/YYYY-MM-DD.md`.
- Text-first (no HTML asset).

## Compliance close (every output ends with this)

> This is a needs analysis and market research, **not a solicitation or financial advice**. Premiums shown are indicative — verify with the insurer / IRDAI before acting. Insurance is a personal decision. No product is sold here.
