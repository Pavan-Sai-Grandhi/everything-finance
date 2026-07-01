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

IndMoney gives a fund's holdings + weights but not its portfolio P/E-P/B — so compute them from the underlying stocks' screener.in ratios (`lib/fundamentals.py`), via `scripts/lookthrough.py`.

- **Aggregation is not averaging.** Portfolio P/E and P/B aggregate by the **weighted harmonic mean** — you sum earnings/book *yields* across holdings, then invert — because multiples don't add. ROE and earnings growth use the weighted arithmetic mean.
- **Coverage is a first-class number.** Report the % of AUM that could be priced (e.g. "ratios cover 82% of AUM"); never extrapolate the uncovered remainder.
- **Read:** a flexicap trading at a large P/E premium to its category while carrying only average look-through ROE/growth is priced for perfection — a forward risk no trailing chart shows.

### Style & drift

- **Cap-tilt** — large/mid/small by weight (absolute market-cap bands are indicative; SEBI classifies by rank).
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
