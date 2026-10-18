# Personal finance

**Consumers:** wealth-manager, budget-tracker, mf-analysis (held-fund context). **Sources, in
priority order:** `varsity-pf`, `plugin`.

`finance/compute/wealth.py` encodes the thresholds below and `finance/compute/budget.py` the
budget categories; this file is why each one is what it is.

## The order of financial health [varsity-pf:1-5] [plugin]

A household's finances are a stack, and a higher layer is worthless if the one under it is missing. This is the ordering the cross-domain action plan enforces — and the one thing no single-domain spoke can see:

1. **Cashflow** — you must save something. Nothing else is possible without a surplus.
2. **Emergency fund** — 3–6 months of expenses in liquid assets, before any market risk. A thin emergency fund on a large equity book means a forced sale at the worst time.
3. **Protection** — term (if dependents) and health cover, before growing wealth. One uninsured event wipes years of compounding.
4. **Investments** — only once 1–3 are sound does the *quality* of the investment book (allocation, concentration, laggards) become the priority.
5. **Net-worth allocation** — the whole-picture asset mix (equity vs debt vs real estate vs gold vs cash) sits across all of the above.

So a **protection gap or a thin emergency fund always outranks a fresh-equity move**, however exciting the investment book looks. That inversion of the "what's the best stock" instinct is the whole value of the cross-domain view.

SIP is a discipline device, not a return enhancer; a step-up SIP compounds materially. Asset allocation (equity:debt by goals, rebalanced annually) explains most of the outcome; fund selection is second-order [varsity-pf:31-33].

## The net-worth spine [plugin]

The spine is the only place the non-tradeable asset classes are seen — real estate, gold, EPF/PF, FDs, cash, US equity, insurance cash value — beyond the equity+MF book the investment spoke covers. Built by `finance/compute/wealth.py:build_spine`:

- **Allocation** comes from IndMoney's `networth_allocation_breakdown` (authoritative — it sees every class). Only if that is absent do we aggregate the tradeable positions by asset class, and then the spine is labelled **tradeable-only** and the net-worth allocation is flagged incomplete.
- **Total net worth** from `networth_snapshot`; if absent, the allocation sum is labelled as inferred. Missing/invalid asset rows or a mismatch between reported total and asset sum make coverage incomplete. Do not invent a balancing asset or liability. Zero/negative reported net worth cannot be used for an allocation percentage.
- **Liquid pool** uses the explicitly confirmed `profile.emergency_reserve.available_value`, with an observation date and source. Cash/FD totals remain visible as `observed_liquid`, but labels alone do not prove withdrawal availability or freedom from commitments. A verified reserve can be assessed independently of incomplete net worth; an unverified reserve remains unavailable.
- **Known direct-equity share** = Indian + US direct equity divided by the reported total. Crypto is not equity. Generic mutual-fund, retirement, insurance and unknown buckets can contain unresolved equity exposure, so total `equity_share_pct` stays unavailable when these are present or book coverage is incomplete. Do not promote the direct-equity subset into a whole-portfolio equity verdict. Fund labels alone do not establish underlying holdings.
- Asset-class labels are free text from IndMoney; `canonical_class` maps them to fixed buckets. `us_equity` is matched before `equity` so "US Stocks" doesn't fold into Indian equity.

## Cross-domain figures [plugin]

- **Emergency-fund runway** = liquid pool ÷ monthly expenses. Monthly expenses resolve: stated → cashflow-leg `monthly_outflow` → `recurring_monthly` (a labelled *floor*, actual spend is higher) → not-assessed. With complete monthly spending, bands are research conventions: **strong ≥6**, **adequate 3–6**, **thin 1–3**, **critical <1** month. A recurring-only floor yields an upper bound on runway and remains not assessed; it cannot certify a sound foundation.
- **Protection-vs-net-worth** — weighs the protection-leg adequacy: an `absent` core line (term/health) is critical, a `short` line is weak, all `adequate` is strong. Red flags append but don't override.
- **Risk posture** — compare valid equity exposure with the user's stated `profile.equity_band` (`min_pct`, `max_pct`). Missing or invalid ranges yield `unknown`; age alone supplies no ceiling. Weak or unassessed emergency/protection evidence takes precedence as `fix-foundation-first`. A sound foundation permits a descriptive `below-target`, `within-target` or `above-target` comparison, not authorization to buy or sell.

## The financial-health scorecard [plugin]

One status per domain — **strong / adequate / weak / critical / not_assessed** — each with one falsifiable line:

| Domain | Strong | Weak / worse |
|---|---|---|
| Net worth & allocation | diversified across classes | one non-cash class > 60% of net worth |
| Investments | no concentration or exit flags | a severe concentration flag or an EXIT verdict |
| Protection | term + health adequate | a short or absent core line |
| Cashflow | saving ≥ 20% of inflow | saving < 10% |
| Emergency fund | ≥ 6 months runway | < 3 months |

**Overall** = the worst *assessed* domain (a `not_assessed` domain never sets the overall — it's a gap to fill, not a failure). A gap-only investment digest cannot establish absence of risk, and an empty allocation cannot establish diversification. A domain whose leg didn't run is marked "not assessed — run /<spoke>", and the review still produces a verdict on the rest.

## Prioritised action plan (max 5) [plugin]

Ordered by the health stack above, not by domain size. Each action carries a concrete next step and the spoke to run for depth:

1. Emergency fund critical/thin → build it before any fresh equity (`/budget-tracker`).
2. Protection critical/weak → close the cover gap before adding risk (`/insurance-advisor`).
3. Cashflow weak → lift the savings rate, starting at the biggest leak (`/budget-tracker`).
4. Investments weak → fix concentration / exit laggards (`/portfolio-review`).
5. Net-worth allocation weak → diversify the dominant sleeve (`/portfolio-review`).

If the foundation is sound and exposure lies outside an explicit target range, a remaining slot requests an allocation review; it does not recommend adding growth assets automatically. Fund depth routes to `/mf-analysis`; single-stock depth to `/deep-analysis`.

## Budget buckets [plugin]

The user's own budget workbook, when supplied, sets the targets. Do not assume it exists or has
particular sheet names. The bands below are the plugin's planning heuristics, not lender rules;
label them as framework comparisons when the user gives no targets.


The sheet computes each bucket as a % of TOTAL MONTHLY INFLOW (income + additional + rental + spouse's income):

| Bucket | Workbook categories | Target band |
|---|---|---|
| **Essential expenses** | House rent & maintenance, property tax, utilities, groceries, transportation, medical, children school fees, insurance premiums | ≤ 50% |
| **Lifestyle expenses** | Maid, shopping, travel, dine & entertainment | ≤ 10–15% |
| **EMIs** | Home loan, car loan, personal loan, other EMIs | ≤ 20–25% (framework heuristic, not a lender limit) |
| **Investments** | Mutual funds, stocks, fixed deposits, others | ≥ 20% (treat as a fixed bill — pay yourself first) |
| **Leftout** | Inflow − all outflows | ≥ 0; check it against reserves, upcoming bills and goals before proposing a use |

Compare actual percentages with the user's targets when available, and label the fallback bands otherwise. With missing statements or unclear inflows, give no adherence verdict.

## Judging a month [plugin]

The xlsx embodies "give every rupee a bucket before the month starts." The report should judge **adherence**, not just describe: each bucket gets ✅ within band / ⚠️ near edge / ❌ breached, plus the trend vs prior months when artifacts exist. The single most useful output is naming the controllable leak (lifestyle/discretionary), not lamenting fixed costs.

### Goal calculators

Retirement, child education, and incremental SIP sheets exist for goal math — if the discipline report shows investment surplus capacity, point the user at the incremental SIP concept (step-up SIP compounding) rather than generic advice.
