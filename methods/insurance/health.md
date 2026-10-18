# Health insurance

Indemnity cover for hospitalisation. **Sources:** `law` (IRDAI), `varsity-ins`, `plugin`; the scoring weights,
sizing scenarios and rules of thumb are the plugin's [plugin].

## Interview: what to ask, one question at a time

Family composition + ages · city tier (metro / tier-2 / tier-3) · existing conditions / pre-existing diseases (PED) · current cover (employer group vs personal, sum insured of each) · preferred hospitals / network need · annual premium budget. Also useful: whether senior parents are to be covered (they need a separate policy, not the floater).

## Sizing (feeds `health_sum_insured`)

Choose a `base_target` and a `total_target` from the interview, the policy options and
sourced research, and explain them. They are scenario assumptions, not a city-tier formula
or a forecast of medical costs. If the evidence is too thin, state the gap instead of using a
default. Size each covered group separately.

Supply the policy's `deductible`, existing `personal_cover` and `employer_cover`. The
calculator keeps the two covers separate. `top_up_target = total_target - deductible` is the
sum insured needed above the deductible; compare it with any existing top-up and its own
deductible. Check both deductible gaps, then the policy's eligibility, exclusions, limits and
aggregate-deductible rules before treating any amount as real protection.

[HDFC ERGO's super-top-up FAQ](https://www.hdfcergo.com/faqs/my-health-medisure-super-top-up-insurance-policy-faqs)
(checked 2026-09-28) explains the difference between deductible and top-up sum insured.

## Scoring checklist (weighted — score each candidate, higher = better)

| Criterion | Weight | What good looks like |
|---|---|---|
| **Room-rent / ICU cap** | high | **no room-rent limit** or single-private-room; a 1%-of-SI/day cap triggers *proportionate deduction* that scales down the **whole** bill |
| **Co-pay** | high | zero mandatory co-pay (common trap in senior plans — insurer keeps skin in *your* game) |
| **Disease sub-limits** | high | none, or generous, on cataract / knee / other common procedures — sub-limits silently gut the cover |
| **Restoration / recharge** | med | full SI restored after a claim within the year — valuable for floaters |
| **PED waiting period** | med | shorter (2–3y) beats 4y; served waiting periods are preserved on porting |
| **No-claim bonus** | med | cumulative bonus that grows SI without loading premium |
| **Network / cashless** | med | strong cashless-hospital network in the user's city; low claim-rejection reputation |
| **Day-care & modern-treatment cover** | low | day-care procedures and modern treatments included |
| **Consumables** | low | consumables rider or built-in cover (non-payable items such as gloves and syringes can be a material share of a bill; check the policy's excluded-items list) — one of the few riders worth paying for |

## Red flags (claim-repudiation risk)

Every high-weight criterion above, failed, is a red flag — **a room-rent cap with proportionate deduction is the single most damaging clause in Indian health insurance**, and a mandatory co-pay or a disease sub-limit dressed up as a cheaper premium is the next. Beyond the table:

- PED **under-declared** to lower the premium → the rejection arrives at the claim, years later.
- "Everything covered" marketing that on reading carries caps/exclusions.

## Sizing sanity (unverified rule of thumb)

A commonly quoted band of about ₹15–25k/yr for a ₹10L individual floater, rising steeply with age, has no source. A quote far below comparable quotes is a reason to read the policy for caps and co-pay. Compare real quotes for the same members, sum insured and features, and never cite the band as evidence.
