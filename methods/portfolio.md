# Portfolio review

**Consumers:** portfolio-review, wealth-manager (the investments leg). **Sources:** `moneypurse`,
`soic-mf`, `dtt-mf`, `plugin`.

A rubric for finding holdings that need review. The thresholds are adjustable heuristics, not
trade instructions.

## Trades and investments

Judge a trade against its own entry, stop, target, invalidation and time stop. Do not apply a standard holding period or guess the plan from a recent purchase. A missing rationale is a gap. Recommending an exit is not the same as a broker fill.

Judge an investment by comparing the business today with its recorded thesis and earlier periods. A falling price alone does not break the thesis.

## Performance and health

Your XIRR depends on when you put money in. A category return or NAV CAGR does not, so the two are not comparable even over the same dates. A fair comparison runs the benchmark on your dated cash flows; without that, report both and draw no conclusion from the difference. XIRR is the measure for any SIP or irregular flows, CAGR only for a single lump sum, and absolute return for neither [soic-mf:pvQ9BwfVHbE@33:39].

Direct stocks earn their place against funds. Every two or three years compare the stock book's XIRR with what the same cash flows earned in the funds held; if the stocks did not win, the case for more capital in them is unmade [soic-mf:CfRMqIFXfaw@04:53].

A sourced decline in returns on capital, margins, debt service, cash conversion or governance is a reason to review. Compare like periods on the same basis and keep allegations apart from established facts. One ratio crossing a cutoff, or one shareholding change, does not decide exit, trim or keep.

Fund quick digests describe; they do not judge. Use performance, fees and changes to pick funds for the deep review, which makes the judgment. A SIP in the red after one to three years is not by itself a review trigger (`methods/funds.md` → *The SIP view*). A held Regular plan or IDCW option is: the switch to Direct Growth is an action, weighed against exit load and tax [dtt-mf:iJ1s0j0qJ0I@06:05].

Overlap suggests redundancy but does not say which fund to sell; weigh mandate, cost, goals and switching cost first. Three or four funds with distinct styles (value, quality, growth, momentum) cover an equity sleeve; more funds of one style add overlap, not diversification [soic-mf:CfRMqIFXfaw@07:57] [soic-mf:On_60FfH32o@25:13]. Owning many funds is not by itself proof of poor diversification: judge the styles and the overlap.

## Concentration and coverage

`finance/compute/allocation.py` owns the thresholds and arithmetic. Defaults flag a stock above 10% of the valued book, a sector above 25% (above 35% escalates the flag), a small/micro sleeve above 30%, an AMC above 40% of the **fund sleeve**, and asset drift above 10 percentage points. Use the user's own limits when given, and state which limits applied.

Too many direct stocks is a finding as well: more names than the holder can follow dilutes the winners. The source puts 15–20 as enough even above ₹1 crore and says a 50–100-stock book never compounds [moneypurse:5V5QugxC7cs@25:30] [moneypurse:5V5QugxC7cs@26:05].

Cross-account rows of the same ticker combine for stock concentration. Personal sources give a fund's units and value; decision sources give its cap and style. A fund with no look-through is a coverage gap, not evidence that it holds no smallcaps.

A supplied breakdown must be non-overlapping amounts, or percentages of the whole valued book, not of the equity sleeve. Report the denominator and coverage for every dimension, and never scale a partial breakdown up to 100%.

## Rebalancing

Use the user's stated targets, which must sum to 100%; there is no age-based default. Without targets, report the current allocation only. When values or classes are missing, leave the move amounts withheld and ask for the missing data.

The rupee moves assume the book total stays fixed, as in selling one asset to buy another, and ignore tax. Adding fresh cash changes the total, so the amounts differ. Say which case you mean and weigh liquidity, costs and taxes before suggesting a trade.

## Reporting

Lead with the finding, its evidence and its coverage limits. Keep the action list short and ordered. Use REVIEW when the evidence does not support a firmer verdict.
