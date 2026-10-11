# Budget framework reference

The user's `Monthly Budget Planning.xlsx`, when supplied, is the authority for their targets. Do not assume a private Downloads file exists, is blank, or has particular sheet names. The bands below are optional planning heuristics bundled with this plugin; label them as framework comparisons when no user targets are available. They are not lender rules or a universal measure of financial health.

## The five buckets (from the Monthly Budget sheet)

The sheet computes each bucket as a % of TOTAL MONTHLY INFLOW (income + additional + rental + spouse's income):

| Bucket | Workbook categories | Target band |
|---|---|---|
| **Essential expenses** | House rent & maintenance, property tax, utilities, groceries, transportation, medical, children school fees, insurance premiums | ≤ 50% |
| **Lifestyle expenses** | Maid, shopping, travel, dine & entertainment | ≤ 10–15% |
| **EMIs** | Home loan, car loan, personal loan, other EMIs | ≤ 20–25% (framework comparison only; no universal lender ceiling implied) |
| **Investments** | Mutual funds, stocks, fixed deposits, others | ≥ 20% (treat as a fixed bill — pay yourself first) |
| **Leftout** | Inflow − all outflows | ≥ 0; reconcile unassigned cash against reserves, upcoming bills and goals before proposing a use |

Compare actual percentages with the user's populated targets when available, and label the fallback bands otherwise. Missing statements or unclear inflows prevent a reliable adherence verdict.

## Category mapping taxonomy

Statement narration tokens → workbook category:

- **Groceries**: BIGBASKET, BLINKIT, ZEPTO, DMART, INSTAMART, RELIANCE FRESH, kirana UPI handles
- **Dine & Entertainment**: ZOMATO, SWIGGY, EATCLUB, restaurant names, BOOKMYSHOW, PVR, INOX, NETFLIX, SPOTIFY, HOTSTAR, PRIME
- **Transportation**: UBER, OLA, RAPIDO, IRCTC, fuel (IOCL/HPCL/BPCL), FASTAG, METRO
- **Utilities**: electricity board tokens (BESCOM/TSSPDCL/etc.), JIO, AIRTEL, ACT, broadband, gas (HP GAS/INDANE), water
- **House rent & maintenance**: NOBROKER/CRED rent pay, society maintenance, landlord transfer (recurring same-amount monthly transfer near month start)
- **Medical**: APOLLO, PHARMEASY, TATA 1MG, NETMEDS, hospital/clinic names
- **Insurance premiums**: LIC, HDFC LIFE, ICICI PRU, STAR HEALTH, ACKO, DIGIT, POLICYBAZAAR
- **Shopping**: AMAZON, FLIPKART, MYNTRA, AJIO, NYKAA, CROMA, IKEA
- **Travel**: MAKEMYTRIP, GOIBIBO, CLEARTRIP, IXIGO, airline names, OYO, AIRBNB, hotel names
- **EMIs**: narrations with EMI/ACH/NACH/ECS + lender names (BAJAJ FIN, HDFC LTD, ...) — recurring identical debits
- **Investments**: ZERODHA, GROWW, KUVERA, COIN, BSE LIMITED/INDIAN CLEARING (MF autopay), NPS, PPF transfer, FD bookings
- **Income** (credits): salary (recurring large credit, employer name), dividends, interest credits

Heuristics: recurring identical amounts = subscriptions/EMIs/rent; intra-account transfers and CC bill payments are *not* spend (the CC's own line items are the spend) — CC-payment narration tokens to exclude: `CRED CLUB`, `<BANK> CARD PAYMENT`, `BBPS CC`, `AUTOPAY CC`, `IB BILLPAY CC`. Cash/ATM withdrawals: separate `ATM/Cash` line under Lifestyle unless the user reclassifies — and the discipline verdict must caveat that ATM cash is *untracked* spend, not analyzed spend.

## Durable map layered over the taxonomy

The taxonomy above is the fallback, not the first authority. `scripts/categorize.py` resolves each transaction in this order:

1. **Durable merchant map** — `artifacts/budget/merchant-map.json` (`paths.merchant_map_path()`), loaded at the start of every run. Keyed by a *normalized merchant token* (uppercased, narration plumbing — `UPI`/`POS`/`ACH`, masked card numbers, `@handle` suffixes, short/numeric words — stripped, first significant word). So `UPI/DR/…/ZOMATO/YESB/zomato@ybl` and `POS 41XXXX ZOMATO LTD` both collapse to the token `ZOMATO` and share one rule.
2. **Taxonomy tokens** — match complete narration tokens, never substrings inside another merchant name; the category→token table above, scanned most-specific-first (`SWIGGY INSTAMART` → Groceries, not Dine, because `INSTAMART` is matched before `SWIGGY`).
3. **UNCATEGORIZED** — no match.

The **same tokenizer** keys both lookup and write, so a correction always resolves the merchant it was made against. When the user classifies an UNCATEGORIZED merchant (or overrides a taxonomy guess), `--learn` writes `token → category` back to the map; next month that merchant resolves in step 1 and UNCATEGORIZED shrinks. The map stores tokens, never raw narrations. A missing map starts empty. An unreadable or invalid map is preserved: categorization continues with taxonomy and an explicit gap, while learning refuses to overwrite it. Restore or repair the saved file before learning again. Corrections are validated against the supported categories; the CLI locks the full read–modify–write operation and publishes atomically.

## Recurring-detection rules

`scripts/recurring.py` groups **debits** by the same merchant token and account and looks across the current statements plus prior `artifacts/budget/` months:

- **Cadence** requires every inter-charge gap to fall in the same band (the median describes the observed interval): monthly (24–38 days), quarterly (80–100), annual (350–400). `monthly_equivalent` = amount ÷ months-per-charge (monthly = amount, quarterly = amount/3, annual = amount/12).
- **Roughly stable amount** — recurring only if the relative spread stays within tolerance (a modest rise is allowed and flagged as creep, not disqualified); genuinely variable spend (groceries) is *not* called recurring even at a regular cadence.
- **Confidence**: high (≥3 regular charges), medium (2), low (single charge — candidate only). An observed pattern is still not proof of a contractual obligation.
- **Flags**: `new` (first appearance is the current month), `price_creep` (latest amount rose vs the prior cadence — cite prior→now), `dormant` (an established recurring charge overdue by >1.6× its cadence — possibly a missed cancellation worth confirming; **excluded** from the committed monthly total).
- **Single period** (no prior months): surface a familiar subscription merchant as a low-confidence candidate, with `cadence` and `monthly_equivalent` null. Exclude it from `total_committed_monthly` until recurrence is observed or independently confirmed; an Apple/Google charge may be a one-off purchase.
- **Coverage**: exclude transactions after `as_of`, invalid dates/amounts, investments, ATM withdrawals and card-bill settlements. Carry returned `gaps` into the report. Separate accounts are separate series. Repeated imports must be deduplicated by statement transaction identity before this script; identical amounts alone do not prove duplicates.

Deterministic and reproducible from the artifacts — every cited amount carries the months it was observed in.

## Discipline report framing

The xlsx embodies "give every rupee a bucket before the month starts." The report should judge **adherence**, not just describe: each bucket gets ✅ within band / ⚠️ near edge / ❌ breached, plus the trend vs prior months when artifacts exist. The single most useful output is naming the controllable leak (lifestyle/discretionary), not lamenting fixed costs.

## Related calculators in the workbook

Retirement, child education, and incremental SIP sheets exist for goal math — if the discipline report shows investment surplus capacity, point the user at the incremental SIP concept (step-up SIP compounding) rather than generic advice.
