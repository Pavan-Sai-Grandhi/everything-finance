# Exchange filings reference

Grounded in NSE corporate filings and SEBI LODR materiality framing.

## Materiality taxonomy

🔴 **Act-on (thesis-relevant within days)**
- Financial results + board meeting intimations for results
- M&A, demerger, asset sale, new large capacity announcement
- Buyback / dividend / split / bonus announcements (and their record/ex-dates)
- Auditor resignation or qualification; CFO/MD/KMP exit
- SEBI/ED/regulatory action, search/seizure, fraud disclosure; court/tribunal judgments resolving disclosed regulatory matters
- Promoter pledge creation/increase; bulk/block deals by promoters
- Credit rating downgrade
- Order wins > ~5% of annual revenue

🟡 **Monitor (context, not action)**
- Investor/analyst meet schedules and presentations (PPTs often carry guidance not in press releases — worth opening)
- Capex updates, subsidiary incorporations, JV announcements
- Rating affirmations and **upgrades**, modest order wins
- Litigation updates without quantified exposure

⚪ **Routine (suppress by default, count only)**
- Trading-window closure, ESOP allotments, duplicate-share-certificate notices
- Newspaper publication copies of already-filed results
- Compliance certificates (Reg 74(5), 7(3), etc.)

## Shareholding pattern reading

- **Promoter %**: rising = confidence; falling needs a reason (dilution? sale?). Compare 4 quarters.
- **Pledge % of promoter holding**: any increase is a flag; > 20% pledged is structurally risky (forced-sale spiral if stock falls). Pledge rising + price falling = the classic pre-crash signature — always call out. Data caveat: pledge % lives reliably only in the NSE shareholding-pattern detail; screener.in omits it for many companies. If unreachable, report the gap and the last-known value — never imply nil from absence.
- **FII + DII %**: direction of institutional flow; retail % rising while institutions exit is distribution.
- Quarterly granularity only — for intra-quarter moves, check bulk/block deal disclosures.

## Corporate-actions mechanics worth stating in reports

- Ex-date is what matters for entitlement (buy before ex-date), record date is administrative.
- Dividend yield context: special vs regular. Splits/bonuses are economically neutral — flag if the market is treating them otherwise.
- Buyback: tender route (record-date entitlement, acceptance ratio matters) vs open-market (slow support). Size as % of market cap decides materiality.
