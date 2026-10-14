# Budget framework reference

The user's `Monthly Budget Planning.xlsx`, when supplied, sets their targets. Do not assume the file exists or has particular sheet names. The bands below are this plugin's planning heuristics, not lender rules; label them as framework comparisons when the user gives no targets.

## The five buckets (from the Monthly Budget sheet)

The sheet computes each bucket as a % of TOTAL MONTHLY INFLOW (income + additional + rental + spouse's income):

| Bucket | Workbook categories | Target band |
|---|---|---|
| **Essential expenses** | House rent & maintenance, property tax, utilities, groceries, transportation, medical, children school fees, insurance premiums | ≤ 50% |
| **Lifestyle expenses** | Maid, shopping, travel, dine & entertainment | ≤ 10–15% |
| **EMIs** | Home loan, car loan, personal loan, other EMIs | ≤ 20–25% (framework heuristic, not a lender limit) |
| **Investments** | Mutual funds, stocks, fixed deposits, others | ≥ 20% (treat as a fixed bill — pay yourself first) |
| **Leftout** | Inflow − all outflows | ≥ 0; check it against reserves, upcoming bills and goals before proposing a use |

Compare actual percentages with the user's targets when available, and label the fallback bands otherwise. With missing statements or unclear inflows, give no adherence verdict.

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

The **same tokenizer** keys both lookup and write, so a correction always resolves the merchant it was made against. When the user classifies an UNCATEGORIZED merchant (or overrides a taxonomy guess), `--learn` writes `token → category` back to the map; next month that merchant resolves in step 1 and UNCATEGORIZED shrinks. The map stores tokens, never raw narrations. A missing map starts empty. An unreadable map is left alone: categorization uses the taxonomy with a gap, and `--learn` refuses to write until the file is repaired. Corrections must name a supported category; the CLI locks the file and writes it atomically.

## Recurring-detection rules

`scripts/recurring.py` groups **debits** by the same merchant token and account and looks across the current statements plus prior `artifacts/budget/` months:

- **Cadence** requires every inter-charge gap to fall in the same band (the median describes the observed interval): monthly (24–38 days), quarterly (80–100), annual (350–400). `monthly_equivalent` = amount ÷ months-per-charge (monthly = amount, quarterly = amount/3, annual = amount/12).
- **Roughly stable amount** — recurring only if the relative spread stays within tolerance (a modest rise is allowed and flagged as creep, not disqualified); genuinely variable spend (groceries) is *not* called recurring even at a regular cadence.
- **Confidence**: high (≥3 regular charges), medium (2), low (single charge, candidate only).
- **Flags**: `new` (first appearance is the current month), `price_creep` (latest amount rose vs the prior cadence — cite prior→now), `dormant` (an established recurring charge overdue by >1.6× its cadence — possibly a missed cancellation worth confirming; **excluded** from the committed monthly total).
- **Single period** (no prior months): list a known subscription merchant as a low-confidence candidate with `cadence` and `monthly_equivalent` null, and leave it out of `total_committed_monthly` until it recurs. An Apple or Google charge may be a one-off purchase.
- **Coverage**: the script skips transactions after `as_of`, invalid dates or amounts, investments, ATM withdrawals and card-bill payments, and reports them in `gaps`. Each account is its own series. Remove duplicate imports by transaction ID before running it; equal amounts alone are not duplicates.

Deterministic and reproducible from the artifacts — every cited amount carries the months it was observed in.

## Discipline report framing

The xlsx embodies "give every rupee a bucket before the month starts." The report should judge **adherence**, not just describe: each bucket gets ✅ within band / ⚠️ near edge / ❌ breached, plus the trend vs prior months when artifacts exist. The single most useful output is naming the controllable leak (lifestyle/discretionary), not lamenting fixed costs.

## Related calculators in the workbook

Retirement, child education, and incremental SIP sheets exist for goal math — if the discipline report shows investment surplus capacity, point the user at the incremental SIP concept (step-up SIP compounding) rather than generic advice.
