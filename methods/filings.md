# Exchange filings

**Consumers:** filings-watch, daily-brief, news-scan, discover (special situations).
**Sources, in priority order:** `law` (SEBI LODR disclosure categories), `moneypurse`, `plugin`.

Triage for NSE corporate filings. `get_filings` applies these tiers as a first pass; the tiers are
the plugin's heuristics, not legal materiality and not trade instructions [plugin]. Read the
disclosure before saying how it affects a thesis.

## Materiality taxonomy

🔴 **Act-on (thesis-relevant within days)**
- Financial results + board meeting intimations for results
- M&A, demerger, asset sale, new large capacity announcement
- Buyback / dividend / split / bonus announcements (and their record/ex-dates)
- Auditor resignation or qualification; CFO/MD/KMP exit
- SEBI/ED/regulatory action, search/seizure, fraud disclosure; court/tribunal judgments resolving disclosed regulatory matters
- Promoter pledge creation/increase; bulk/block deals by promoters
- Credit rating downgrade
- Order wins material to the business: compare the order value with revenue over the same period, and note execution period and cancellation terms. No fixed percentage decides materiality

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

- **Promoter %**: a change can come from buying, selling, dilution or reclassification. Check share counts before calling it buying or selling.
- **Pledge**: give the filing date and say whether the percentage is of promoter holding or of total shares; the two differ. Do not predict a crash from a pledge level or a falling price. If there is no current figure, say unknown and date any older one.
- **Institutional ownership**: FII/DII stake changes are holdings at quarter end, not money flows. NSE's public category includes institutions, so it is not retail and cannot be added to the institutional figures.
- **A known buyer is an idea, not a signal.** A rising fund stake or a famous investor's bulk deal shows the entry, not the thesis, the holding period or the size: ₹1 crore is 0.1% of a ₹1,000 crore book but a 1% stake in a ₹100 crore company, and the exit surfaces a quarter late. Name the buyer as a lead and test the company on its own case [moneypurse:2ZqGwAWel1E@08:49] [moneypurse:2ZqGwAWel1E@10:49] [moneypurse:2ZqGwAWel1E@15:53].
- A quarterly filing does not show when or why shares changed hands within the quarter.

The [NSE shareholding-pattern page](https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern) identifies the published ownership categories. [NSE's pledge table](https://betanseapi.nseindia.com/companies-listing/corporate-filings-pledged-data) distinguishes the two percentage denominators. Fetch the figures themselves only through the MCP tools.

## Corporate-actions mechanics worth stating in reports

- Give the exchange's ex-date and record date, and any later correction. Explain eligibility from the notice itself, not a general calendar rule.
- Separate regular from special dividends. A split or bonus changes the share count, so adjust per-share figures before reading a price or EPS change as value created.
- For a buyback, report the route, terms, eligibility, funding and timetable from the notice. Entitlement is not the amount that will be accepted. An announcement is not price support and not proof of undervaluation.
