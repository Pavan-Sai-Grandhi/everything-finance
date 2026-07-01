# Budget framework reference

Mirrors the user's workbook: `~/Downloads/Monthly Budget Planning.xlsx` (Money Purse-style planner; sheets: Monthly Budget, Retirement Cal, Child Education Cal, Incremental SIP Cal). Inspected 2026-06-10 — the workbook is a blank template, so targets below are the framework defaults until the user fills it in or states their own.

## The five buckets (from the Monthly Budget sheet)

The sheet computes each bucket as a % of TOTAL MONTHLY INFLOW (income + additional + rental + spouse's income):

| Bucket | Workbook categories | Target band |
|---|---|---|
| **Essential expenses** | House rent & maintenance, property tax, utilities, groceries, transportation, medical, children school fees, insurance premiums | ≤ 50% |
| **Lifestyle expenses** | Maid, shopping, travel, dine & entertainment | ≤ 10–15% |
| **EMIs** | Home loan, car loan, personal loan, other EMIs | ≤ 20–25% (lenders' FOIR logic: total EMIs under ~40% of income is the hard ceiling; 25% is the comfort line) |
| **Investments** | Mutual funds, stocks, fixed deposits, others | ≥ 20% (treat as a fixed bill — pay yourself first) |
| **Leftout** | Inflow − all outflows | ≥ 0; persistent large leftout = idle money, sweep to investments |

The workbook's "CURRENT STATUS" column is exactly the comparison this skill automates: actual % vs these bands.

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
2. **Taxonomy tokens** — the category→token table above, scanned most-specific-first (`SWIGGY INSTAMART` → Groceries, not Dine, because `INSTAMART` is matched before `SWIGGY`).
3. **UNCATEGORIZED** — no match.

The **same tokenizer** keys both lookup and write, so a correction always resolves the merchant it was made against. When the user classifies an UNCATEGORIZED merchant (or overrides a taxonomy guess), `--learn` writes `token → category` back to the map; next month that merchant resolves in step 1 and UNCATEGORIZED shrinks. The map stores tokens, never raw narrations. A missing/corrupt map degrades to taxonomy-only, then starts rebuilding — never a crash.

## Recurring-detection rules

`scripts/recurring.py` groups **debits** by the same merchant token and looks across the current statements plus prior `artifacts/budget/` months:

- **Cadence** from the median inter-charge gap: monthly (24–38 days), quarterly (80–100), annual (350–400). `monthly_equivalent` = amount ÷ months-per-charge (monthly = amount, quarterly = amount/3, annual = amount/12).
- **Roughly stable amount** — recurring only if the relative spread stays within tolerance (a modest rise is allowed and flagged as creep, not disqualified); genuinely variable spend (groceries) is *not* called recurring even at a regular cadence.
- **Confidence**: high (≥3 regular charges), medium (2), low (single-period — inferred, not observed).
- **Flags**: `new` (first appearance is the current month), `price_creep` (latest amount rose vs the prior cadence — cite prior→now), `dormant` (an established recurring charge overdue by >1.6× its cadence — possibly a missed cancellation worth confirming; **excluded** from the committed monthly total).
- **Single period** (no prior months): still surface a known-subscription merchant seen once, at low confidence with an inferred monthly cadence, and say the cadence is inferred.

Deterministic and reproducible from the artifacts — every cited amount carries the months it was observed in.

## Discipline report framing

The xlsx embodies "give every rupee a bucket before the month starts." The report should judge **adherence**, not just describe: each bucket gets ✅ within band / ⚠️ near edge / ❌ breached, plus the trend vs prior months when artifacts exist. The single most useful output is naming the controllable leak (lifestyle/discretionary), not lamenting fixed costs.

## Related calculators in the workbook

Retirement, child education, and incremental SIP sheets exist for goal math — if the discipline report shows investment surplus capacity, point the user at the incremental SIP concept (step-up SIP compounding) rather than generic advice.
