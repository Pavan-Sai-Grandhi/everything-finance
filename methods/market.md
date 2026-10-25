# The market context

**Consumers:** market-analysis, and every skill that reads `get_market_context`. **Sources:**
`plugin`, `soic-mf`, `moneypurse-mf`.

`finance/compute/context.py` computes the context and `finance/contracts.md` (*Artifact:
market-context*) defines its fields. This file is how to read them.

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

## Is now a good time to add?

Starting valuation has decided later returns more than anything else a holder can see. Money
Purse's Nifty study: entering below a P/E of about 20 gave better odds over the next three to
ten years, while entering at 24–27 averaged −4.2% a year over the next three
[moneypurse-mf:qC12_EZvShw@06:26] [moneypurse-mf:qC12_EZvShw@08:05]. Read it through the
percentile above, not an absolute band. A trailing P/E overstates expense when earnings are
depressed, which is why P/B sits in the blend [moneypurse-mf:qC12_EZvShw@09:48]. *Variants:*
forward-P/E bands (16–21× a lump-sum zone, above 25× very expensive)
[soic-mf:CfRMqIFXfaw@36:32]; the P/E against its own three-year average
[moneypurse-mf:7KPjxZLcj2w@08:01]. Absolute bands drift as the index's composition changes.

- **A breadth washout is the second signal.** When fewer than 25% of the top 500 stocks are
  above their 200-day average (`breadth.pct_above_sma200`), lump sums have been well placed,
  most of all in small caps; above about 95% marked euphoria [soic-mf:KhtCYiZRLo8@46:53]
  [soic-mf:KhtCYiZRLo8@49:08].
- **A month the Nifty falls more than 3–4% at an average valuation** is a time to raise a SIP,
  not stop it [soic-mf:CfRMqIFXfaw@10:26].
- **Stage a lump sum.** Put about half in when the reading is attractive and the rest in over
  further falls, because nobody knows how far a fall runs [moneypurse-mf:qC12_EZvShw@11:18].
- **Small-cap cycles are long.** Two or three strong years have been followed by 12 to 18
  months of fall or sideways drift, and "time corrections" have lasted up to about two years
  [soic-mf:CfRMqIFXfaw@14:23] [soic-mf:CfRMqIFXfaw@32:41]. Context for patience, not a timer.
- **Expected return is arithmetic, not hope**: an index returns roughly nominal GDP growth plus
  the change in its multiple, so lower inflation means lower nominal returns
  [soic-mf:On_60FfH32o@22:48]. A planning rate of 10–13% for diversified equity is a labelled
  estimate with that reason [soic-mf:CfRMqIFXfaw@10:52] [soic-mf:On_60FfH32o@24:16].

None of these is a timing model. They decide whether fresh money goes in now or in tranches;
they never decide whether to stop a SIP.

## Flows and macro

FII/DII flows are for one session. One session supports a statement about that day only; persistent buying or selling needs several sessions.

Macro series are context. Note each series' instrument, date and unit: some are futures rather than spot prices, and a yield is not a return. Rate-cycle data has no approved source, so it is a gap; never fill it from memory.

## Reading rules

- A missing value is a data gap. Null breadth fails a strategy gate, and a `neutral` posture
  caused by missing data does not mean conditions are normal.
- Use each component's own date: the Nifty bar's date says nothing about how fresh flows or
  valuations are.
- Compare trailing windows with trailing windows, never with a calendar year
  (`methods/funds.md` → *Window discipline*).
