# Market-context methodology

Implementation authority: `finance/compute/context.py`; handoff fields: `finance/contracts.md` (market-context). This reference explains interpretation rather than duplicating calculation code.

## Historical valuation

Report each multiple alongside its percentile against the same index's available history. A percentile describes that sample, not intrinsic value or a forecast. The default request is ten years of monthly observations; missing samples, index composition changes and the actual available window limit comparability. Do not claim a complete cycle simply because ten years were requested.

The P/E filter excludes positive observations at least three times their sample median and reports the count. This is a statistical heuristic: an extreme P/E can reflect a small earnings denominator, but the ratio alone does not establish earnings collapse or a data error. Disclose exclusions rather than treating the filtered result as the uniquely correct valuation.

The stance equally weights available P/E and P/B percentiles and inverted dividend-yield percentile. This is a research convention, not an empirically calibrated allocation model. Book values and dividends can also change during stress. Missing inputs change the blend's composition; compare individual metrics before interpreting a difference between tiers.

Positive P/E and earnings yield have opposite rankings because reciprocation is decreasing. The inverse dividend-yield percentile is used only to orient higher blended scores toward richer valuations. A low yield alone does not establish overvaluation; payout policy also matters.

## Trend, volatility and participation

The trend uses Nifty's 50/200-EMA position and 50-EMA slope. Missing comparisons produce `unknown`. The fixed VIX and breadth cutoffs in the implementation are screening conventions, not guarantees of safety or return.

`risk_on` requires an uptrend, known acceptable volatility and available sector participation. High volatility, a downtrend or weak participation can warrant `risk_off`; otherwise posture is neutral. Read the rationale: incomplete evidence can also produce neutral, which does not authorize extra risk.

Stock breadth describes the available priced denominator, which may differ from the requested universe. Sector breadth is a coarse index measure; its gate is withheld when any expected sector is unavailable. Neither proves that the same pattern holds across every constituent. One snapshot cannot establish that breadth is rising or falling without a comparable earlier reading.

## Relative valuation and allocation

Nifty 50, Midcap 150 and Smallcap 250 are index proxies, not complete personal portfolio cap classifications. A spread between their blended historical percentiles flags a difference worth investigating. It does not by itself establish the dominant portfolio risk or an attractive entry. Check metric coverage, profitability, composition and the user's existing exposure before deriving an allocation implication.

## Flows and macro

Use the reported session for FII/DII flows. A single session supports a statement about that session, not persistent buying, selling or domestic absorption of foreign outflows. Establish persistence only from multiple comparable sourced sessions.

Macro series provide context; their instruments, observation dates and units matter. Distinguish futures proxies from spot prices and bond yields from returns. Missing rate-cycle inputs remain labelled gaps under the repository's source policy. Do not replace them with remembered figures.
