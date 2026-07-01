# Health insurance — best-practice reference

Indemnity cover for hospitalisation. Read with `reference.md`. Interview, scoring, and Q&A on health policies all draw on this.

## Interview — what to ask (one at a time)

Family composition + ages · city tier (metro / tier-2 / tier-3) · existing conditions / pre-existing diseases (PED) · current cover (employer group vs personal, sum insured of each) · preferred hospitals / network need · annual premium budget. Also useful: whether senior parents are to be covered (they need a separate policy, not the floater).

Missing → stated assumption in the Assumptions table.

## Sizing (feeds `insurance_math.health_sum_insured`)

- **Base sum insured** by city + family: metro individual ₹10L / family floater ₹15–25L; lift for older lives and senior parents.
- **Employer cover counts at half weight** — it's real but vanishes with the job.
- **Resilient structure: personal base + super top-up.** A super top-up (₹50L–1Cr above a ₹5–10L deductible) costs little and covers the catastrophic tail. Medical inflation runs 12–14% — a cover that feels generous today halves in real terms in ~6 years.
- **Senior parents → separate policy**, never on the family floater (their premiums and claims would poison everyone's cover).

## Scoring checklist (weighted — score each candidate, higher = better)

| Criterion | Weight | What good looks like |
|---|---|---|
| **Room-rent / ICU cap** | high | **no room-rent limit** or single-private-room; a 1%-of-SI/day cap triggers *proportionate deduction* that scales down the **whole** bill |
| **Co-pay** | high | zero mandatory co-pay (common trap in senior plans — insurer keeps skin in *your* game) |
| **Disease sub-limits** | high | none, or generous, on cataract / knee / other common procedures — sub-limits silently gut the cover |
| **Restoration / recharge** | med | full SI restored after a claim within the year — valuable for floaters |
| **PED waiting period** | med | shorter (2–3y) beats 4y; served waiting periods are preserved on porting |
| **No-claim bonus** | med | cumulative bonus that grows SI without loading premium |
| **Network / cashless** | med | strong cashless-garage… (hospital) network in the user's city; low claim-rejection reputation |
| **Day-care & modern-treatment cover** | low | day-care procedures and modern treatments included |
| **Consumables** | low | consumables rider or built-in cover (gloves/syringes can be 5–10% of a bill) — one of the few riders worth paying for |

## Red flags (claim-repudiation risk)

- **Room-rent cap** with proportionate deduction — the single most damaging clause.
- **Mandatory co-pay**, especially age-linked.
- **Disease sub-limits** dressed up as a cheaper premium.
- **Restoration absent** on a family floater.
- Long/opaque **PED waiting period**, or PED under-declared to lower premium (→ future rejection).
- "Everything covered" marketing that on reading has caps/exclusions — a brochure claim never overrides these red flags.

## Sizing sanity (2026 metro context)

Health ≈ ₹15–25k/yr for a ₹10L individual floater, rising steeply with age. Super top-ups are cheap relative to base. A base-only quote far below this band usually hides caps/co-pay.
