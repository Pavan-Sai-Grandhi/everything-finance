# Portfolio review rubric

Use this rubric to identify evidence requiring review. Thresholds are configurable research heuristics, not statutory limits, forecasts, or automatic instructions to transact.

## Trades and investments

Judge a recorded trade against its own entry, stop, target, invalidation and time-stop rules. Do not impose a universal holding period or infer the trade plan from a recent acquisition. Missing rationale is a review gap. A recommended exit and a confirmed broker fill are different events.

For an investment, compare the current business evidence with its recorded thesis and comparable earlier periods. Price drawdown alone does not prove thesis failure.

## Performance and health

Held XIRR reflects the investor's dated cash flows. A category return or published NAV CAGR is usually a different measure; the same start/end dates do not make the two comparable. To compare investor outcomes, a benchmark simulation needs those same dated cash flows. If unavailable, report the measures separately without inferring underperformance from their difference. Missing XIRR remains unavailable.

Sourced deterioration in returns on capital, margins, debt service, cash conversion or governance can warrant review. Compare like reporting periods and bases, account for business-specific economics, and distinguish allegations from established findings. A single ratio cutoff or shareholding movement does not independently establish an exit, trim or keep verdict.

Fund quick digests are descriptive. Use available comparable performance, fees and changes as triage evidence; confirm consequential fund judgments through the bounded deep review. Portfolio overlap can indicate redundancy but does not by itself determine which fund to sell. Consider mandate, cost, goals and switching implications before recommending a change. Fund count alone is not proof of poor diversification.

## Concentration and coverage

`finance/compute/allocation.py` owns the thresholds and arithmetic. Defaults flag a stock above 10% of the valued book, a sector above 25% (above 35% escalates the flag), a small/micro sleeve above 30%, an AMC above 40% of the **fund sleeve**, and asset drift above 10 percentage points. These are review conventions. Use explicitly supplied plan limits when available and disclose the applied limits.

Cross-account rows of the same ticker combine for stock concentration. Fund ownership and classification remain separate: personal sources establish units and values; approved decision sources establish cap and style. Missing fund look-through is a coverage gap, not evidence that the fund owns no smallcaps or shares no sectors with direct holdings.

Supplied breakdowns must be disjoint category amounts or explicit percentages of the full valued book. Do not pass equity-sleeve percentages as whole-book percentages. Report the denominator and coverage for every dimension. A tagged subset is never renormalized to imply complete coverage.

## Rebalancing

Use the user's stated targets; there is no automatic age-based target. Target weights must sum to 100%. When targets are absent, report relative allocations. When values or asset classifications are incomplete, preserve the engine's withheld move amounts and request the missing evidence.

A complete-book rupee move is a calculation under a fixed-total scenario, not an execution instruction or tax-adjusted optimum. Selling one asset and buying another differs from adding fresh cash, which changes the denominator. State the scenario and consider liquidity, costs and taxes before advising implementation. Do not claim an engine-calculated trim amount applies unchanged to a fresh-inflow plan.

## Reporting

Lead with the finding, its evidence and coverage limits. Keep the action list prioritized and short. Use REVIEW when the evidence cannot support a stronger verdict; do not fill every holding with a confident keep/exit label simply to complete a table.
