# Vehicle insurance

Motor cover (car / two-wheeler). **Sources:** `law` (IRDAI), `varsity-ins`, `plugin`; the scoring weights,
sizing scenarios and rules of thumb are the plugin's [plugin].

## Interview: what to ask, one question at a time

Make / model / year / variant · whether the model is discontinued · current IDV + no-claim bonus (NCB) % · usage pattern (personal / commercial, annual km) · city (claim frequency, garage network) · prior claims (last 3–5 years) · existing add-ons. Also useful: ex-showroom price of the variant (anchors the IDV sanity check), whether a loan/hypothecation is on the vehicle.

## Comprehensive vs third-party

- **Third-party (TP)** is the legal minimum — covers only damage you cause to others. Never sufficient for anything but a very old, low-value vehicle.
- **Comprehensive** = TP + own-damage (theft, accident, fire, natural calamity). Default recommendation for any vehicle with meaningful value.

## IDV & NCB sanity (feeds `idv_ncb_sanity`)

- **IDV (Insured Declared Value):** the age schedule covers vehicles up to five years old; for older vehicles and discontinued models the insurer and owner agree the IDV. Pass `model_discontinued:true` when it applies. A null `idv_ok` means the check could not run, not a pass or a fail. The tool's tolerance is a screening assumption; confirm the agreed IDV and its basis in the policy. Source: [New India private-car policy, pages 2–3](https://www.newindia.co.in/assets/docs/know-more/motor/STANDARD%20FORM%20FOR%20PRIVATE%20CAR%20PACKAGE%20POLICY.pdf), checked 2026-09-28.
- **NCB** rewards claim-free years on a slab: 20% (1y) → 25% (2y) → 35% (3y) → 45% (4y) → 50% (5y, caps). A quoted NCB **above** the slab your claim-free history entitles is a red flag (verify history — misdeclaration voids it). **NCB is portable** across insurers and vehicles; **NCB-protect** add-on preserves it through one claim.

## Add-ons — worth it vs situational

| Add-on | Verdict |
|---|---|
| **Zero-depreciation (bumper-to-bumper)** | worth it for cars < ~5y — pays full part cost without depreciation cut |
| **NCB protection** | worth it if you've built up 35–50% NCB — keeps the discount after a claim |
| **Return-to-invoice (RTI)** | worth it for new/financed cars — total loss pays invoice price, not depreciated IDV |
| **Engine protection** | worth it in flood-prone cities / low-clearance cars |
| **Consumables** | situational — covers oils/nuts/bolts a normal claim excludes |
| **Roadside assistance** | cheap convenience, not essential |

## Scoring checklist (weighted — score each candidate, higher = better)

| Criterion | Weight | What good looks like |
|---|---|---|
| **IDV accuracy** | high | set at fair depreciated value, not lowballed to cut premium |
| **Own-damage claim-settlement reputation** | high | high settlement %, low disputed-rejection record |
| **Cashless garage network** | high | dense network in the user's city |
| **Relevant add-ons available** | med | zero-dep / RTI / NCB-protect offered for the vehicle's age |
| **Premium for the IDV + add-ons** | med | competitive for equivalent cover, not cheap via a thin IDV |
| **NCB transfer handling** | low | cleanly ports existing NCB |

## Red flags (claim-repudiation risk)

A lowballed IDV, an NCB above entitlement, or a missing zero-dep/RTI on a new car are the § IDV & NCB and § Add-on rules failed — flag them from there. The two the tables can't hold:

- Owner-driver **personal-accident (PA) cover** absent — it's mandatory and cheap.
- Undeclared prior claims, or commercial use on a private policy → rejection at claim time.
