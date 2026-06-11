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

## Discipline report framing

The xlsx embodies "give every rupee a bucket before the month starts." The report should judge **adherence**, not just describe: each bucket gets ✅ within band / ⚠️ near edge / ❌ breached, plus the trend vs prior months when artifacts exist. The single most useful output is naming the controllable leak (lifestyle/discretionary), not lamenting fixed costs.

## Related calculators in the workbook

Retirement, child education, and incremental SIP sheets exist for goal math — if the discipline report shows investment surplus capacity, point the user at the incremental SIP concept (step-up SIP compounding) rather than generic advice.
