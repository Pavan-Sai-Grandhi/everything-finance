# Insurance: the shared framework

**Consumers:** insurance-advisor, wealth-manager (the protection leg). **Sources, in priority
order:** `law` (IRDAI), `varsity-ins`, `plugin`.

Every mode loads this file plus the per-type file: `term.md`, `health.md` or `vehicle.md`.

## Insurance is protection, not investment [varsity-ins]

- **Buy term, invest the difference.** Mixing insurance with investment (endowment, ULIP, moneyback) usually buys weaker versions of both. Judge a plan by the IRR of its own cash flows (`marginal_irr_continue` / `irr`) against a sourced hurdle, never by a remembered "typical" return. Pure protection (term life, indemnity health, comprehensive motor) + the premium difference invested per the MF framework beats bundled products.
- **Disclosure is the claim.** Smoking, pre-existing conditions, family history, prior claims — misdeclaration is the #1 cause of claim rejection [varsity-ins]. Never optimise premium via omission; a cheaper policy that won't pay is worthless.
- **A brochure claim never overrides a best-practice red flag** — the per-type red-flag lists win over marketing copy.

## Interview discipline [plugin]

- **One question at a time**, type-aware (each per-type reference lists exactly what to ask). Conversational, not a form dump.
- **Work around a gap.** Finish the sections you have evidence for and name the missing inputs. Current cover, loans, assets and expenses are facts to ask for, not values to invent or set to zero.
- State the figure, reason and source for every forward assumption. Do not fill a missing answer with a stock education corpus, expense percentage or bonus rate. For a proposed policy, use its guaranteed and illustrated cash flows as stated.

## Research and sourcing [plugin]

**IRDAI is authoritative** for claim-settlement ratios and registered-insurer status. The research stays qualitative, and every figure carries its source URL + as-of date.

- Premiums are labelled **"indicative — verify with insurer"**. Quote engines that need personal data are flagged **"needs a real quote"** — never auto-fill invented inputs to extract a number.
- Flag promotional/one-sided passages and down-weight them.
- A page that blocks WebFetch is a labelled gap, not a reason to escalate to a browser.
- Too few candidates for a type → present what was found, state the shortfall, ask the user to supply brochures/quotes for the finalists.

## Compliance close (every output ends with this) [plugin]

> This is a needs analysis and market research, **not a solicitation or financial advice**. Premiums shown are indicative — verify with the insurer / IRDAI before acting. Insurance is a personal decision. No product is sold here.
