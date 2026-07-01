# Vehicle insurance — best-practice reference

Motor cover (car / two-wheeler). Read with `reference.md`. Interview, scoring, and Q&A on motor policies all draw on this.

## Interview — what to ask (one at a time)

Make / model / year / variant · current IDV + no-claim bonus (NCB) % · usage pattern (personal / commercial, annual km) · city (claim frequency, garage network) · prior claims (last 3–5 years) · existing add-ons. Also useful: ex-showroom price of the variant (anchors the IDV sanity check), whether a loan/hypothecation is on the vehicle.

Missing → stated assumption in the Assumptions table.

## Comprehensive vs third-party

- **Third-party (TP)** is the legal minimum — covers only damage you cause to others. Never sufficient for anything but a very old, low-value vehicle.
- **Comprehensive** = TP + own-damage (theft, accident, fire, natural calamity). Default recommendation for any vehicle with meaningful value.

## IDV & NCB sanity (feeds `insurance_math.idv_ncb_sanity`)

- **IDV (Insured Declared Value)** = the sum insured = ex-showroom × an age-based retention factor (IRDAI grid: ~95% ≤6mo, 85% 1y, 80% 2y, 70% 3y, 60% 4y, 50% 5y; >5y mutually agreed). A quote **below** the band under-insures you (lower claim/theft payout); **above** the band just inflates premium. Don't chase the lowest IDV to cut premium — it caps your total-loss payout.
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

- **IDV lowballed** to advertise a cheaper premium — bites at total loss/theft.
- **Quoted NCB above entitlement** — voids on verification.
- Comprehensive marketed but **add-ons that matter (zero-dep/RTI) missing** for a new car.
- Owner-driver **personal-accident (PA) cover** absent — it's mandatory and cheap.
- Undeclared prior claims or commercial use on a private policy → rejection at claim time.
