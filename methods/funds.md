# Mutual funds

**Consumers:** mf-analysis, discover (funds), portfolio-review (the fund sleeve). **Sources, in
priority order:** `law` (the SEBI cap-rank definition), `varsity-pf`, `plugin`.

Two pillars: **past performance**, recomputed from NAV history, and **forward-looking quality**:
what the fund owns, what it costs and who runs it. A verdict reflects potential, not trailing
returns alone.

## Returns: the hierarchy [varsity-pf:18-23]

- **Point-to-point returns lie** — they depend entirely on the two endpoints. A fund can show a great 5Y CAGR purely because the start date was a crash bottom.
- **Rolling returns are the standard**: roll a 1/3/5-year window daily across the full NAV history. Report mean, median and min — the distribution of what a holder actually earned, and how many windows it rests on. A fund whose *minimum* 5Y rolling return is positive has not lost money for any lump-sum 5-year holding **within the observed NAV history** — that's the kind of statement this analysis should produce, scoped to the windows it rests on (it says nothing about SIPs or future windows).
- CAGR for periods > 1 year; absolute returns only for < 1 year.

## Risk and quality metrics [varsity-pf:18-23]

- **Standard deviation**: category-relative; higher SD needs higher return to justify.
- **Beta**: <1 defensive vs benchmark, >1 amplifies. Only meaningful vs the right benchmark.
- **Sharpe**: excess return per unit of total risk; compare within a category only. **Sortino** (downside risk only) is the preferred refinement.
- **Capture ratios**: upside capture >100 and downside capture <100 is the ideal asymmetry; downside capture matters more for staying invested.
- **Expense ratio (TER)**: compounding drag — 1% extra TER costs ≈**16%** of the final corpus over 20 years (12% gross → 11% net compounds to 8.06× instead of 9.65×). State it as a share of corpus, never as "1% a year", which reads as trivial. Always Direct plan. Index funds: TER < 0.2% expected; active equity: < 1% (Direct) preferred.
- **Alpha**: active fund must beat benchmark *after* TER over rolling 3Y+; most large-cap active funds don't → index-first default for large-cap.

## Fund selection checklist [varsity-pf:24-26]

1. Category fits the goal horizon: equity only for ≥ 5–7y goals; debt (liquid/ultra-short) for < 3y; hybrid in between.
2. AUM not too small (< ₹500 Cr = viability/liquidity questions for equity; very large AUM hurts small/midcap agility).
3. Fund manager tenure ≥ 3y over the performance window being credited.
4. Rolling-return consistency vs both benchmark and category median.
5. Portfolio sanity: top-10 concentration, sector bets, # of holdings; for two funds held together, overlap > 60% = redundant diversification.
6. Debt funds: credit quality (AAA/sovereign share), modified duration against the rate view, YTM minus TER as expected carry. Credit risk is asymmetric; avoid credit-risk funds for parking money.

## Forward-looking quality: the second pillar [plugin]

Everything above measures the *past*. Trailing/rolling returns are backward-looking; a fund's forward potential rides on what it owns now, what it costs, and who runs it. This pillar grades that, so the verdict reflects *potential*, not just history.

### Look-through valuation

A fund's portfolio P/E-P/B is published nowhere, so `get_fund_lookthrough` computes it from the underlying stocks' ratios over the **complete** holdings list.

- **Aggregation is not averaging.** Portfolio P/E and P/B aggregate by the **weighted harmonic mean** — you sum earnings/book *yields* across holdings, then invert — because multiples don't add. ROE uses the weighted arithmetic mean. The look-through computes no earnings-growth figure; a growth lean needs a sourced per-holding series or is a labelled gap.
- **Coverage is a gate.** Report the % of the equity book priced: below 60% the engine withholds the ratio, 60–85% is indicative only, 85%+ is decision-grade (see § Coverage is a gate).
- **Read:** a flexicap trading at a large P/E premium to its category while carrying only average look-through ROE/growth is priced for perfection — a forward risk no trailing chart shows.

### Style & drift

- **Cap-tilt** — large/mid/small by weight, classified by **SEBI market-cap rank** (see "Cap classification" below); never by absolute ₹Cr bands.
- **Value/growth lean** — low P/B + dividend tilt vs high P/E + high earnings-growth tilt.
- **Concentration** — top-5/top-10 weight and the Herfindahl index; sector bets.
- **Style drift** — compare current cap-tilt/sector mix against prior holdings disclosures. A "large-cap" fund quietly drifting mid/small changes its risk without changing its name — flag it explicitly.

### AMC & manager trust (each claim sourced)

- **Fund-house pedigree** — process discipline and breadth; a track record of investor-first conduct vs mis-selling, expense abuse, or penalties.
- **Alpha consistency** — is the record the current manager's or a predecessor's? (tenure rule: § Is it the manager's record?)
- **AUM stability/trend** — sudden inflows into a small/midcap strategy erode agility; persistent outflows can force selling.
- **Governance & regulatory flags** — SEBI actions, front-running/expense-abuse cases, side-pocketing history.

### Weighing the two pillars

The verdict is a forward-leaning **fund-quality grade** (Hold-worthy / Watch / Avoid) combining valuation + holdings quality + style-fit + cost + AMC/manager trust, with rolling/trailing performance as *one input*, not the headline. State the 2–3 deciding factors. Every data gap (young fund lacks 5Y, holdings stale, look-through coverage < 100%) is named, never fabricated.

### Cap classification — by rank, never by rupees

SEBI defines the tiers by **market-cap rank**: top 100 large, 101-250 mid, 251+ small. Classify holdings that way (the rank AMFI publishes and `get_stock_ratios` serves as `cap_rank`), never by absolute ₹Cr bands. The bands are not merely imprecise — they are systematically wrong in the direction that matters, because a small-cap fund's *largest* holdings are by construction its biggest names. Applied to a real small-cap fund the bands reported **0% small-cap** (true figure: 67%) and invented a 19% large-cap "drift" that did not exist (true figure: 0%).

### Coverage is a gate, not a footnote

Report the equity weight each metric covers. The engine withholds a value below 60% coverage, labels 60–85% indicative and 85% or more decision-grade. An indicative value must not decide a recommendation. Never extrapolate to the uncovered part, and do not confuse a missing ratio with a zero allocation. A ratio computed on a partial book describes a different fund, not an approximation of this one. Holdings staleness, look-through coverage and every gated-out fund are always surfaced.

### P/B ÷ ROE — compare only matched holdings

The engine computes P/B and weighted ROE over the holdings that have both, and applies the coverage gate to that set. Use the result as a cross-check, not as something that overrides other valuation evidence. Explain differences in coverage, sectors, accounting and profitability before concluding anything.

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

Manager tenure must cover **the window being credited**. A fund whose 3-year number was earned by a manager who left 22 months ago has a 3-year record that belongs to someone else. Check tenure before ranking, not after — in a live small-cap scan this single check removed the top-scoring fund and the fourth, because both had turned over their management inside the credited window. Also weigh any **capital gating** by the AMC — a fund closing to lump-sum money is telling you it thinks size is hurting it.

### Sources that do not serve fund holdings

These were tested; do not reach for them. `get_fund_holdings` serves the complete book.

| Source | Result |
|---|---|
| Morningstar India `detailed-portfolio.aspx` | Paywalled — data behind "Unlock" |
| AMFI portfolio-disclosure portal | JS-driven; WebFetch sees an empty dropdown, and the plugin has no browser. Tickertape's API already returns the complete book |
| AdvisorKhoj monthly-disclosure pages | Lists months, but every link bounces to a generic AMC downloads page |
| ValueResearch portfolio-holdings page | Partial / top-N only |
| Tickertape **HTML** fund page | Top-5 plus "See All" — the **API** is the right door |
| mfapi.in for holdings | NAV-only by design |
| Groww TER on a Direct-plan page | **Trap:** can serve the Regular-plan expense ratio. Verify against AMFI/the AMC factsheet |
