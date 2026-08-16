# Mutual fund research knowledge base

Grounded in Zerodha Varsity — Personal Finance module (https://zerodha.com/varsity/module/personalfinance/, 33 chapters: fund mechanics, debt/equity/index funds, performance measurement ch. 18–23, fund analysis ch. 24–26). Fetched and summarized 2026-06-10.

## Returns: the Varsity hierarchy

- **Point-to-point returns lie** — they depend entirely on the two endpoints. A fund can show a great 5Y CAGR purely because the start date was a crash bottom.
- **Rolling returns are the standard**: roll a 1/3/5-year window daily across the full NAV history. Report mean, median, min, and consistency (% of windows above benchmark). A fund whose *minimum* 5Y rolling return is positive has never lost money for any 5-year holder — that's the kind of statement this analysis should produce.
- CAGR for periods > 1 year; absolute returns only for < 1 year.

## Risk & quality metrics (ch. 18–23)

- **Standard deviation**: category-relative; higher SD needs higher return to justify.
- **Beta**: <1 defensive vs benchmark, >1 amplifies. Only meaningful vs the right benchmark.
- **Sharpe**: excess return per unit of total risk — compare within category only. **Sortino** (downside-only) is Varsity's preferred refinement.
- **Capture ratios**: upside capture >100 and downside capture <100 is the ideal asymmetry; downside capture matters more for staying invested.
- **Expense ratio (TER)**: compounding drag — 1% extra TER ≈ 10%+ of corpus over 20 years. Always Direct plan. Index funds: TER < 0.2% expected; active equity: < 1% (Direct) preferred.
- **Alpha**: active fund must beat benchmark *after* TER over rolling 3Y+; most large-cap active funds don't → index-first default for large-cap.

## Fund selection checklist (ch. 24–26)

1. Category fits the goal horizon: equity only for ≥ 5–7y goals; debt (liquid/ultra-short) for < 3y; hybrid in between.
2. AUM not too small (< ₹500 Cr = viability/liquidity questions for equity; very large AUM hurts small/midcap agility).
3. Fund manager tenure ≥ 3y over the performance window being credited.
4. Rolling-return consistency vs both benchmark and category median.
5. Portfolio sanity: top-10 concentration, sector bets, # of holdings; for two funds held together, overlap > 60% = redundant diversification.
6. Debt funds: credit quality (AAA/sovereign share), modified duration vs rate view, YTM minus TER as expected carry. Varsity's debt chapters stress credit risk is asymmetric — avoid credit-risk funds for parking money.

## Framework context (ch. 1–5, 31–33)

Order of operations Varsity teaches: emergency fund (6 months expenses, liquid fund/FD) → term + health insurance → then investing. SIP is a discipline device, not a return enhancer; incremental/step-up SIP (also in the user's budget workbook) compounds materially. Asset allocation (equity:debt by age/goals, rebalanced annually) explains most outcome variance — fund selection is second-order to allocation.

## Forward-looking quality — the second pillar

Everything above measures the *past*. Trailing/rolling returns are backward-looking; a fund's forward potential rides on what it owns now, what it costs, and who runs it. This pillar grades that, so the verdict reflects *potential*, not just history.

### Look-through valuation

A fund's portfolio P/E-P/B is published nowhere, so compute it from the underlying stocks' ratios via `scripts/lookthrough.py`, sourcing the **complete** holdings list through `lib/funds.py`.

> **Never source holdings from the IndMoney MCP.** `get_mf_funds_details.holdings` caps at 20 rows with no pagination, reports that cap as the total, and claims 91-98% coverage beside a list summing to 6-27%. Real funds hold 64-278 positions. One fund's 20-row slice omitted its actual top three holdings; another was nine months stale. Every ratio built on it was wrong.

- **Aggregation is not averaging.** Portfolio P/E and P/B aggregate by the **weighted harmonic mean** — you sum earnings/book *yields* across holdings, then invert — because multiples don't add. ROE and earnings growth use the weighted arithmetic mean.
- **Coverage is a gate.** Report the % of AUM priced, and **withhold the ratio below ~85%** rather than caveating it (see "Coverage is a gate" below); never extrapolate the uncovered remainder.
- **Read:** a flexicap trading at a large P/E premium to its category while carrying only average look-through ROE/growth is priced for perfection — a forward risk no trailing chart shows.

### Style & drift

- **Cap-tilt** — large/mid/small by weight, classified by **SEBI market-cap rank** (see "Cap classification" below); never by absolute ₹Cr bands.
- **Value/growth lean** — low P/B + dividend tilt vs high P/E + high earnings-growth tilt.
- **Concentration** — top-5/top-10 weight and the Herfindahl index; sector bets.
- **Style drift** — compare current cap-tilt/sector mix against prior holdings disclosures. A "large-cap" fund quietly drifting mid/small changes its risk without changing its name — flag it explicitly.

### AMC & manager trust (each claim sourced)

- **Fund-house pedigree** — process discipline and breadth; a track record of investor-first conduct vs mis-selling, expense abuse, or penalties.
- **Manager tenure ≥ 3y** over the window being credited (ties back to the ch. 24–26 checklist) and **alpha consistency** — is the record the current manager's, or a predecessor's?
- **AUM stability/trend** — sudden inflows into a small/midcap strategy erode agility; persistent outflows can force selling.
- **Governance & regulatory flags** — SEBI actions, front-running/expense-abuse cases, side-pocketing history.

### Weighing the two pillars

The verdict is a forward-leaning **fund-quality grade** (Hold-worthy / Watch / Avoid) combining valuation + holdings quality + style-fit + cost + AMC/manager trust, with rolling/trailing performance as *one input*, not the headline. State the 2–3 deciding factors. Every data gap (young fund lacks 5Y, holdings stale, look-through coverage < 100%) is named, never fabricated.

### Cap classification — by rank, never by rupees

SEBI defines the tiers by **market-cap rank**: top 100 large, 101-250 mid, 251+ small. Classify holdings that way (`cap_rank` from `lib/funds.py`), never by absolute ₹Cr bands. The bands are not merely imprecise — they are systematically wrong in the direction that matters, because a small-cap fund's *largest* holdings are by construction its biggest names. Applied to a real small-cap fund the bands reported **0% small-cap** (true figure: 67%) and invented a 19% large-cap "drift" that did not exist (true figure: 0%).

### Coverage is a gate, not a footnote

Report the % of the book priced — and **withhold the ratio below ~85%** rather than printing it with a caveat. A ratio computed on a fifth of a portfolio is not an approximation of the portfolio; it describes a different fund. Recomputed from 20% to 92% coverage, one fund's look-through P/E moved from ~46 to **27.75** and another's from 12.05 to 17.29. Both would have driven the wrong verdict. Never extrapolate the uncovered remainder; unlisted holdings carry weight but no ratios, and that weight is counted as unpriced, never dropped.

### P/B ÷ ROE — the metric that survives bad data

Across three rounds of progressively better data on the same funds, **P/B ÷ ROE was the only valuation measure that stayed stable**. It answers "what am I paying per unit of profitability", which is the question a portfolio P/E cannot answer when earnings are depressed. Lower is cheaper. Use it as the tie-breaker whenever P/E and P/B disagree.

### Earnings-distress dispersion — and the cyclical/idiosyncratic split

Report the share of the book in companies earning poorly (**ROE < 8%**) against the share earning strongly (**ROE > 18%**). Two funds with identical portfolio P/Es can differ enormously here — in one real comparison, 36.6% of one book sat in distress against 16.9% of another.

Then make the distinction that decides how to read it:

- **Cyclical** — a whole sector at a low point in its cycle (real estate, metals, chemicals). Low ROE here is a position in the cycle and can mean-revert. A fund cheap for this reason is making a contrarian bet.
- **Idiosyncratic** — a company underperforming a *healthy* sector. A lender earning 3.8% ROE while banking is doing fine is not at a cycle trough; it is a mistake in the book.
- **Structural** — businesses whose accounting suppresses ROE by design (holding companies, loss-making platforms). Not distress at all; exclude them from the distress narrative.

**A P/E on collapsed earnings is not cheap.** State which of the three explains a fund's cheapness before calling it value.

### Window discipline

**Never explain a trailing-window number with a calendar-year number.** Defending a weak trailing 1Y by quoting a bad CY2025 compares two different windows and is not an argument. Compare trailing to trailing, calendar year to calendar year, rolling to rolling.

### Is it the manager's record?

Manager tenure must cover **the window being credited**. A fund whose 3-year number was earned by a manager who left 22 months ago has a 3-year record that belongs to someone else. Check tenure before ranking, not after — in a live small-cap scan this single check removed the top-scoring fund and the fourth, because both had turned over their management inside the credited window. Also weigh **AUM trend** (sudden inflows erode a small/midcap manager's agility; persistent outflows force selling) and any **capital gating** by the AMC — a fund closing to lump-sum money is telling you it thinks size is hurting it.

### Rejected sources — tested and dead, do not re-test

| Source | Result |
|---|---|
| Morningstar India `detailed-portfolio.aspx` | Paywalled — data behind "Unlock" |
| AMFI portfolio-disclosure portal | JS-driven; WebFetch sees an empty dropdown. Would need Playwright real-Chrome. Audit-grade only |
| AdvisorKhoj monthly-disclosure pages | Lists months, but every link bounces to a generic AMC downloads page |
| Legacy AMC monthly-portfolio XLSX URLs | HTTP 200 with `content-type: text/html` — dead pattern |
| ValueResearch portfolio-holdings page | Partial / top-N only |
| Tickertape **HTML** fund page | Top-5 plus "See All" — the **API** is the right door |
| mfapi.in for holdings | NAV-only by design |
| Groww TER on a Direct-plan page | **Trap:** can serve the Regular-plan expense ratio. Verify against AMFI/the AMC factsheet |
