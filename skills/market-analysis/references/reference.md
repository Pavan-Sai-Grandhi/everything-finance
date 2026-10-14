# Market-context methodology

The calculation is in `finance/compute/context.py` and the fields are in `finance/contracts.md` (market-context). This file explains how to read them.

## Historical valuation

Report each multiple with its percentile against the same index's history. A percentile describes that sample; it is not intrinsic value or a forecast. The default is ten years of month-end samples, but missing samples and changes in index membership limit the comparison, and ten years requested is not proof of a full cycle.

The P/E filter drops samples at or above three times the median and reports how many. An extreme P/E often comes from collapsed earnings, but the ratio alone cannot tell that apart from a data error, so always state the exclusions.

The stance weights the P/E percentile, the P/B percentile and the inverted dividend-yield percentile equally. That is a convention, not a calibrated model. A missing input changes the blend, so compare the individual metrics before reading a difference between tiers.

Dividend yield is inverted so that a higher blended score always means a richer valuation. A low yield alone does not mean overvalued, because payout policy also matters.

## Trend, volatility and participation

The trend uses Nifty's position against its 50 and 200 EMAs and the 50-EMA slope; missing data gives `unknown`. The VIX and breadth cutoffs are screening conventions.

`risk_on` needs an uptrend, a known and acceptable VIX, and complete sector breadth. High volatility, a downtrend or weak breadth can give `risk_off`; anything else is `neutral`. Read the rationale, because missing data also gives `neutral`.

Stock breadth is measured over the stocks that could be priced, which may be fewer than requested. Sector breadth is a coarse index count, and its gate is withheld if any sector is missing. Saying breadth is rising or falling needs an earlier reading to compare with.

## Relative valuation and allocation

Nifty 50, Midcap 150 and Smallcap 250 stand in for the cap tiers; they are not the user's portfolio. A gap between their blended percentiles is worth investigating but does not by itself make one tier the main risk or a good entry. Check coverage, profitability, index composition and the user's exposure before suggesting an allocation change.

## Flows and macro

FII/DII flows are for one session. One session supports a statement about that day only; persistent buying or selling needs several sessions.

Macro series are context. Note each series' instrument, date and unit: some are futures rather than spot prices, and a yield is not a return. Rate-cycle data has no approved source, so it is a gap; never fill it from memory.
