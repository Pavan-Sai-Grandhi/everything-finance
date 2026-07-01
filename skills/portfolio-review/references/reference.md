# Portfolio review rubric

Compiled 2026-06-10, grounded in Varsity Fundamental Analysis (due-diligence checklist), Trading Systems (expectancy, position discipline), and Personal Finance (asset allocation chapters).

## The two-book separation

Trades and investments answer to different judges — the first mistake reviews catch is positions migrating between books ("it fell, so now it's a long-term investment"). Classify every holding into one book and hold it to that book's rules:

- **Trading book**: judged by the system — entry/SL/target honored, time-stop ~4 weeks. An SL-hit position still in the account is a rule breach, not a market opinion.
- **Investment book**: judged by the business — the fundamental drift checks below. Price drawdown alone is not an exit reason here; thesis damage is.

## Scope — the portfolio view, depth deferred

This skill owns the **portfolio** lens (allocation across dimensions, concentration, laggard detection, the KEEP/TRIM/EXIT verdict) and defers all **single-name** depth. On every holding it runs a *cheap* read to decide whether a name warrants a closer look, then hands the closer look downstream — it never re-derives single-stock or single-fund analysis here:

- **Stock depth → `deep-analysis`.** The cheap read is the screener drift snapshot below; only names that trip a flag are confirmed with a bounded `deep-analysis --quick` (≤ 5 worst), and the most serious get a `/deep-analysis` (full) suggestion.
- **Fund depth → `mf-analysis`.** The cheap read is an `mf-analysis quick` digest on every held fund; only flagged funds get a targeted `mf-analysis deep`.

The book comes from `lib/holdings.py` (IndMoney → broker → manual), so **XIRR is the primary performance lens** where present — a real laggard is a poor *held* XIRR, not a point-to-point guess. Where XIRR is absent the read is labelled inferred.

## Investment-book drift checks (exit/trim triggers)

Would-I-buy-today test on current data, focusing on deterioration:
- ROCE/ROE declining 2+ consecutive years, or margin structure broken vs 5y band
- Debt/equity rising materially or interest coverage < 3
- Promoter pledge appearing/increasing; promoter stake dropping without dilution explanation
- CFO diverging from EBITDA for 2+ years (profits not converting to cash)
- Auditor qualification, KMP churn, related-party creep
- Valuation stretch alone (P/E > 2× own 5y median with flat growth) → TRIM, not EXIT

Three KEEP-grade reasons that survive drawdowns: intact growth + ROCE, falling debt, rising promoter/institutional holding. Name which applies.

## Concentration thresholds (multi-dimensional)

`scripts/allocation.py` computes every dimension and returns each breach with its ₹-at-risk and a concrete ₹ trim. The thresholds it defaults to:

- **Single stock** > 10% of portfolio → flag (winner concentration is allowed but must be a conscious choice)
- **Single sector** > 25% → flag; > 35% → urgent
- **Market cap** — small+microcap sleeve > 30% → liquidity-risk flag (exit doors are narrow in corrections). Cap split comes from IndMoney `networth_allocation_breakdown` plus fund look-through, not guessed per row.
- **AMC** — one fund house > 40% of the fund sleeve → flag (platform/AMC-level risk hides behind fund-level diversification)
- **Investing style** — the growth/value/factor mix (from mf-analysis style data); a single-factor tilt is a conscious choice, not a default — surface it
- **Trading book** total > 20% of overall portfolio → the tail is wagging the dog

Because dimensions like market-cap and style are portfolio-level weights, the engine takes them as pre-aggregated breakdowns (provenance-honest) while single-stock/sector/AMC aggregate the per-holding tags; missing tags lower a dimension's coverage rather than reading as zero.

## Fund-sleeve checks (method summary — depth deferred to mf-analysis)

Every held fund gets an `mf-analysis quick` digest; the checks below decide which funds escalate to `mf-analysis deep`:

- **Held XIRR** materially below the fund's own category rank / benchmark → REVIEW (the primary laggard signal on the real book); persistently bottom-quartile → EXIT candidate (switch, mind capital gains + exit load)
- Expense-ratio drag vs category, category-rank percentile slipping, AUM instability, or visible style drift → escalate to deep
- Pairwise overlap > 60% between two equity funds → redundant; keep the cheaper/more consistent one (overlap needs the look-through — defer the pair to `/mf-analysis`)
- Fund count sanity: > 6–7 equity funds is diworsification

## Allocation drift

Varsity's allocation chapters: the equity:debt split (age/goal-based, e.g. 100−age in equity as a default anchor) does more work than any selection decision. Drift > 10pp from plan → rebalance; specify the ₹ move and which instrument (fresh inflows first to avoid tax, then switches). Rebalancing is also the only systematic sell-high mechanism a personal portfolio has — frame it that way.

## Report tone

Verdicts must be falsifiable and specific: "EXIT — pledge up from 0 to 18% over two quarters while ROCE fell to 9%" not "weak fundamentals". Maximum five actions — a 15-item action list produces zero actions.
