# Mutual funds

**Consumers:** mf-analysis, discover (funds), portfolio-review (the fund sleeve). **Sources, in
priority order:** `law` (SEBI scheme categorisation and the cap-rank definition, the Finance Act
for tax), `varsity-pf`, `soic-mf` (the lead practitioner for judging an equity fund),
`moneypurse-mf` (the lead practitioner for debt funds and the selection sequence), `dtt-mf`,
`plugin`.

A fund answers two questions, kept apart: **is this fund good**, and **is its category worth
adding to now**. The first rests on two pillars: **the record**, recomputed from NAV history,
and **the fund itself**: what it owns, what it costs, how it is built and who runs it. The
second is a reading of the cap tier's valuation (`methods/market.md`). A verdict reflects
potential, not trailing returns alone.

`finance/compute/rolling.py` computes the record, `finance/compute/fund_scan.py` the category
ranking and its gates, `finance/compute/lookthrough.py` the priced book. Where a rule below is
enforced there, it names the module; change both together.

## The category comes before the fund

Pick the category from the goal's horizon and the holder's tolerance for a fall, then the fund
inside it [moneypurse-mf:imTFTLKJSX0@04:34] [varsity-pf:24-26]. A good fund in the wrong
category is the wrong investment.

- **Equity needs at least five years**, and the five is a floor, not a date to sell
  [moneypurse-mf:0XabWUZK_Zc@14:58] [moneypurse-mf:imTFTLKJSX0@07:29]
  [dtt-mf:iJ1s0j0qJ0I@04:08]. For a goal about five years out use an index, flexi-cap or
  multi-cap fund, not small caps [moneypurse-mf:0XabWUZK_Zc@13:59].
- **Small caps need at least seven.** The small-cap index has had a 7% chance of a loss over
  five years and none over seven, against none over five for the Nifty 50
  [soic-mf:KhtCYiZRLo8@07:36] [moneypurse-mf:0XabWUZK_Zc@15:03]. *Variant:* ten years or more
  [moneypurse-mf:imTFTLKJSX0@07:38] [dtt-mf:VCvrI1fycJ0@08:47]; a seven-year mindset for any
  equity [dtt-mf:t30uuDXAh4I@20:54].
- **The fund's own history sets the horizon it has needed.** The SIP view (§ *The record*)
  reports how often an N-year SIP in this fund ended below the money put in. Quote that
  computed share; the category figures above are the prior, not the finding [plugin].
- **Large caps are index-first.** A large-cap fund must hold 80% in the top 100, so the manager
  has little room to add value, and most active large-cap funds do not beat the index after
  cost [varsity-pf:18-23] [dtt-mf:t30uuDXAh4I@22:04] [dtt-mf:VCvrI1fycJ0@04:00].
- **Sector and thematic funds are tactical calls**, not a core holding: picking one needs a
  view on the sector's cycle [moneypurse-mf:imTFTLKJSX0@08:20], and chasing the sector that just
  ran is recency bias [soic-mf:CfRMqIFXfaw@04:06]. Judge one as a sector call
  (`methods/sectors/`), never as a fund pick.
- **Small caps are convex**: they run harder up and fall harder down
  [soic-mf:KhtCYiZRLo8@45:53]. Peak-to-trough, the small-cap index fell 66% in 2008 and 60% in
  2020 against 54% and 38% for the Nifty 50 [soic-mf:KhtCYiZRLo8@06:34], and after its 2008 peak
  it took about nine years to regain it [dtt-mf:VCvrI1fycJ0@07:08]. A holder who cannot sit
  through that should not own the category, whatever the fund.
- **Debt horizons** are in § *Debt funds*.

## Plan hygiene

Settle these before any comparison; each is a guaranteed cost.

- **Direct plan, Growth option.** Regular pays a distributor out of the holder's return; IDCW
  pays out what would otherwise compound [dtt-mf:iJ1s0j0qJ0I@01:27] [dtt-mf:iJ1s0j0qJ0I@04:51]
  [soic-mf:2oq9R_qScvM@14:34]. A holder in Regular or IDCW gets the switch named as an action.
- **Exit load** is read before a switch is suggested [dtt-mf:t30uuDXAh4I@15:25].
- **A fund of funds pays two expense ratios.** A gold fund that buys a gold ETF costs more than
  the ETF [dtt-mf:t30uuDXAh4I@27:38].
- **Expense ratio (TER)** is a compounding drag: 1% extra costs about **16%** of the final corpus
  over 20 years (12% gross → 11% net compounds to 8.06× instead of 9.65×). State it as a share of
  corpus, never as "1% a year", which reads as trivial [varsity-pf:18-23]
  [soic-mf:2oq9R_qScvM@17:30]. Index funds: TER below 0.2% expected; active equity Direct below
  1% preferred. A slightly dearer fund that has earned more after its cost is still the better
  fund: compare net records, not TERs alone [moneypurse-mf:imTFTLKJSX0@14:09].

## The record (pillar 1)

### Returns: the hierarchy [varsity-pf:18-23]

- **Point-to-point returns lie**: they hang on two endpoints, and picking the dates proves
  anything [soic-mf:On_60FfH32o@21:45]. A fund can show a great 5Y CAGR because the start was a
  crash bottom.
- **Rolling returns are the standard**: roll a 1/3/5-year window daily across the full NAV
  history and report mean, median and min with the window count. A fund whose *minimum* 5Y
  rolling return is positive has not lost money for any lump-sum 5-year holding **within the
  observed history**: scoped to the windows it rests on, silent about the future.
- CAGR for periods over a year; absolute returns only under a year, and never for a SIP, whose
  instalments each have a different holding period [soic-mf:pvQ9BwfVHbE@20:35]. A SIP is
  measured by XIRR [soic-mf:pvQ9BwfVHbE@33:39].
- **Judge in three-, five- and seven-year blocks**, never months; a fund deserves ten or more
  years of watching before a firm view [soic-mf:KhtCYiZRLo8@33:25]
  [soic-mf:b-UmyDvGOpM@21:03].

### The SIP view

Most holders invest monthly, so the record includes what a SIP in this fund did.
`rolling.sip_outcomes` runs every monthly SIP of the window's length the history holds and
reports the share that ended below the money put in, with the median and worst XIRR.

- **Early red is the normal path.** A SIP buys more units when the NAV falls, so the falls are
  where the units come from; flat or negative years one to five are common even in funds that
  end at 18–19% XIRR over ten [moneypurse-mf:0XabWUZK_Zc@10:13] [moneypurse-mf:0XabWUZK_Zc@12:19]
  [soic-mf:CfRMqIFXfaw@07:15]. CRISIL's study across seven categories put the chance of a
  negative SIP at 29.4% after one year, 0.63% after five and none beyond ten
  [moneypurse-mf:0XabWUZK_Zc@13:24].
- **A SIP in the red after one to three years is not a reason to stop it**
  [moneypurse-mf:0XabWUZK_Zc@14:24] [dtt-mf:iJ1s0j0qJ0I@08:19]; judge it over five- to seven-year
  rolling periods [soic-mf:CfRMqIFXfaw@08:52]. Compounding is back-ended, so the early
  instalments do the most work: in an 18-year goal SIP the first six years build about 58% of
  the corpus, and interrupting them costs the most [soic-mf:nQwah2nxdWU@00:40]
  [soic-mf:nQwah2nxdWU@08:34]. Most of the gap between a fund's return and its
  holders' return is behaviour [soic-mf:HNbs4Df-NNo@18:08]: about half of online SIPs are
  cancelled within two years [moneypurse-mf:0XabWUZK_Zc@03:18].
- A SIP judged sound is not a fund judged sound. The SIP view describes the record; the fund
  still needs pillar 2.

### Drawdown and recovery

Report the deepest fall as the episode a holder lived through: depth, peak, trough, and the days
until the NAV regained the peak, or that it has not (`rolling.drawdown_episode`). Depth alone
hides the cost; the wait is what makes people sell. Compare the depth with the category's and
the benchmark's over the same episode when both are sourced [soic-mf:KhtCYiZRLo8@06:12]. "Falls
less than its category in down markets" is the half of consistency that matters most for
staying invested [dtt-mf:VCvrI1fycJ0@01:47] [varsity-pf:18-23].

### Risk and quality metrics [varsity-pf:18-23]

- **Standard deviation**: category-relative; higher SD needs higher return to justify. Between
  two funds a fraction apart in return, the steadier one wins
  [moneypurse-mf:imTFTLKJSX0@12:52].
- **Beta**: below 1 defensive, above 1 amplifies. Only meaningful against the right benchmark.
- **Sharpe**: excess return per unit of total risk; within a category only. **Sortino**
  (downside only) is the preferred refinement.
- **Capture ratios**: upside capture above 100 and downside below 100 is the ideal asymmetry;
  downside capture matters more for staying invested [dtt-mf:VCvrI1fycJ0@01:47].
- **Alpha**: an active fund must beat its benchmark *after* TER over rolling 3Y+.

### Consistency over a peak year

There is no best fund, only consistent ones: the category's top fund one year is often outside
its top ten the next [moneypurse-mf:imTFTLKJSX0@09:12]. A 2017 category leader returned −17% in
2018 [moneypurse-mf:imTFTLKJSX0@01:38]. The scan's rolling-return ranks are the consistency test;
a fund that sits in the top half of its category across the 1, 3 and 5-year windows (top
quarter is better) has earned a shortlist place [moneypurse-mf:imTFTLKJSX0@10:42]. A strong
long record with a weak current one is a flag to diagnose (§ *Diagnosing underperformance*),
not a pass [moneypurse-mf:imTFTLKJSX0@13:24].

### Window discipline

**Never explain a trailing-window number with a calendar-year number.** Defending a weak trailing
1Y by quoting a bad CY2025 compares two different windows and is not an argument. Compare
trailing to trailing, calendar year to calendar year, rolling to rolling.

### Whose record is it?

The credited window must belong to the people and the process running the fund now.

- **Manager tenure** must cover the window being credited. A 3-year number earned by a manager
  who left 22 months ago belongs to someone else. Check tenure before ranking, not after: in a
  live small-cap scan this removed the top-scoring fund and the fourth [plugin].
- **The strategy's start** counts the same way. After an AMC acquisition, a merger or a
  re-mandate, the record starts when the current strategy did: Quant's schemes are judged from
  2018, not on the inherited Escorts record [soic-mf:b-UmyDvGOpM@01:57].
- **A new fund has no record of its own.** Borrow the manager's from the schemes they ran
  before, labelled as theirs and not the fund's, and lean on the philosophy and the book; three-
  and six-month returns of a young fund prove nothing [soic-mf:mVr1OFOzUsw@24:00]
  [soic-mf:KhtCYiZRLo8@33:25]. A young scheme's TER is high until its AUM grows; say so
  rather than scoring it against mature peers.
- **Capital gating** by the AMC, such as closing to lump sums, says the fund thinks size is
  hurting it [plugin].

## The fund itself (pillar 2)

### Look-through valuation [plugin]

A fund's portfolio P/E and P/B are published nowhere reliable, so `get_fund_lookthrough`
computes them from the underlying stocks' ratios over the **complete** holdings list.

- **Aggregation is not averaging.** Portfolio P/E and P/B aggregate by the **weighted harmonic
  mean**, because multiples don't add. ROE uses the weighted arithmetic mean. The look-through
  computes no earnings-growth figure; a growth lean needs a sourced per-holding series or is a
  labelled gap.
- **Coverage is a gate** (below).
- **Read:** a fund trading at a large P/E premium to its category while carrying only average
  look-through ROE is priced for perfection, a forward risk no trailing chart shows. Check the
  book's valuation against the category's [soic-mf:CfRMqIFXfaw@18:02].
- **The right multiple for the business:** banks and lenders on P/B, insurers on embedded
  value, a business that reinvests its cash flow on price to operating or free cash flow
  [soic-mf:On_60FfH32o@13:06] [soic-mf:KhtCYiZRLo8@40:15] [soic-mf:HNbs4Df-NNo@14:35]. A
  portfolio P/E heavy in financials understates or overstates accordingly; say so.

### Coverage is a gate, not a footnote [plugin]

Report the equity weight each metric covers. The engine withholds a value below 60% coverage,
labels 60–85% indicative and 85% or more decision-grade. An indicative value must not decide a
recommendation. Never extrapolate to the uncovered part, and do not confuse a missing ratio
with a zero allocation. A ratio computed on a partial book describes a different fund, not an
approximation of this one. Holdings staleness, look-through coverage and every gated-out fund
are always surfaced.

### Cap classification: by rank, never by rupees [law]

SEBI defines the tiers by **market-cap rank**: top 100 large, 101-250 mid, 251+ small
[soic-mf:KhtCYiZRLo8@02:26]. Classify holdings that way (the rank AMFI publishes and
`get_stock_ratios` serves as `cap_rank`), never by ₹Cr bands. The bands are systematically wrong
in the direction that matters, because a small-cap fund's largest holdings are by construction
its biggest names: applied to a real small-cap fund they reported **0% small-cap** (true: 67%)
and invented a 19% large-cap "drift" (true: 0%). Small cap does not mean tiny: the 251st company
is worth about ₹33,000 Cr [soic-mf:KhtCYiZRLo8@02:43].

### Does the book match the claimed style?

Judge a fund by what it owns, not by what its manager says [soic-mf:On_60FfH32o@05:43]
[soic-mf:KhtCYiZRLo8@22:39]. Name the style the fund claims (value, quality, growth, GARP,
momentum, contra) from its own documents and the manager's interviews
[soic-mf:CfRMqIFXfaw@17:53], then test it against the book:

- **value** should show a P/E and P/B below the category and a higher dividend yield; PPFAS's
  value claim held at P/E 18 against a category 25 and a yield of 2.3% against 1.2%
  [soic-mf:On_60FfH32o@11:47];
- **quality** should show ROE and ROCE well above the index's, usually at a P/E premium; Axis
  Long Term Equity carried a weighted P/E near twice the Nifty's for an ROE near twice
  [soic-mf:MiUQ8Xen9Nw@07:23];
- **growth** at a high P/E needs the growth to carry it; a PEG near 1.5 reads growth-biased, not
  P/E-biased [soic-mf:KhtCYiZRLo8@28:01];
- **momentum or quant** shows high turnover by design [soic-mf:b-UmyDvGOpM@13:38].

A book that contradicts its label is a finding. So is **style drift**: compare today's cap tilt
and sector mix with earlier disclosures (`allocation_history`). A "large-cap" fund drifting into
mid and small caps changes its risk without changing its name [plugin].

### Conviction and construction

- **Conviction shows in position sizing.** A fund whose weights are spread evenly is throwing
  darts; 20 to 30 well-sized stocks is apt diversification for most mandates
  [soic-mf:CfRMqIFXfaw@17:07] [soic-mf:2oq9R_qScvM@22:29]. Report the holding count, the top-10
  weight, the top-3 sector weight and the largest position.
- **Avoid index huggers and AUM gatherers.** A manager who strays from the index risks their
  career, so many stay close to it [soic-mf:CfRMqIFXfaw@17:35]. An active fund with a very long
  list, small even weights and a low tracking error is buying the index at an active fee; name
  it a closet indexer when all three hold [plugin].
- **Read the count against size.** A small-cap fund holds many names because liquidity forces
  it, not by choice: at ₹17,380 Cr of AUM a 1% position is ₹174 Cr
  [soic-mf:CfRMqIFXfaw@30:21]. Across small-cap funds, those holding up to 50 stocks earned a
  26% average 3Y rolling return against 21% for those above 75 [soic-mf:KhtCYiZRLo8@35:18]; one
  study, one period, a lean not a law.
- **No single small-cap position above about 3%** is a sign of risk control in a young small-cap
  book [soic-mf:KhtCYiZRLo8@41:18].
- **Earnings distress** (below) is part of construction: what share of the book earns its keep.

### Turnover

Turnover is the share of the book bought and sold in a year; its inverse is the average holding
period, so 25% means about four years [soic-mf:2oq9R_qScvM@21:02] [soic-mf:MiUQ8Xen9Nw@05:12].
For a buy-and-hold style it should sit well below the category: PPFAS ran 20% against a
category 79% [soic-mf:HNbs4Df-NNo@06:39], and above about 80% a fund looks more like trading than
investing [soic-mf:2oq9R_qScvM@21:16]. Read it against the claimed style, not as an absolute: a
momentum or quant fund churns by design [soic-mf:b-UmyDvGOpM@15:24]. Turnover comes from the
AMC's factsheet, cited with its date; no tool serves it.

### Cash

Cash is a position. Held deliberately it is dry powder, buying when others sell
[soic-mf:CfRMqIFXfaw@20:05] [soic-mf:HNbs4Df-NNo@02:52]; held persistently in a rising market it
is a drag on the record. Report the non-equity weight from the holdings (`equity_weight`), say
which reading the fund's own record supports, and whether REITs, arbitrage or near-cash lines
sit inside it [soic-mf:On_60FfH32o@07:12].

### Size, liquidity and float

Size is the enemy of returns [soic-mf:KhtCYiZRLo8@33:54] [soic-mf:On_60FfH32o@03:22]
[dtt-mf:VCvrI1fycJ0@13:22]. Only free float can be bought, and other funds already own much of
it, so a large fund's mid- and small-cap holdings shrink as it grows
[soic-mf:On_60FfH32o@03:48]. A 2% position in a ₹1.41 lakh Cr fund is about ₹2,800 Cr in one
company.

- `fund_scan` scores **AUM agility** against a per-category ceiling (small cap ₹25,000 Cr, mid
  cap ₹40,000 Cr, flexi cap ₹80,000 Cr, large cap ₹2,00,000 Cr). *Variant:* a small-cap scheme
  of ₹60,000 Cr–1 lakh Cr is "like buying the market", while flexi and large caps can carry
  ₹1–1.5 lakh Cr [soic-mf:CfRMqIFXfaw@18:09]; franchise products struggle past ₹10–15 thousand
  Cr [soic-mf:KhtCYiZRLo8@33:54].
- **The liquidity stress test** that small- and mid-cap schemes publish, the days to sell half
  the book, is the direct measure: about 40 days for Nippon Small Cap against two to three for
  funds a thirtieth its size or smaller [soic-mf:KhtCYiZRLo8@24:08]. Read it from the AMC's
  disclosure, cited with its date.
- **AUM trend** matters as much as level: a flood of inflows into a small-cap strategy erodes
  agility; persistent outflows can force selling [plugin].

### Earnings-distress dispersion [plugin]

Report the share of the book in companies earning poorly (**ROE < 8%**) against the share
earning strongly (**ROE > 18%**). Two funds with identical portfolio P/Es can differ enormously
here: in one real comparison, 36.6% of one book sat in distress against 16.9% of another. Then
say which kind it is:

- **Cyclical**: a whole sector at a low point in its cycle (real estate, metals, chemicals).
  Low ROE here can mean-revert; a fund cheap for this reason is making a contrarian bet.
- **Idiosyncratic**: a company underperforming a *healthy* sector. A lender earning 3.8% ROE
  while banking is doing fine is a mistake in the book.
- **Structural**: accounting that suppresses ROE by design (holding companies, loss-making
  platforms). Not distress; exclude it from the narrative.

**A P/E on collapsed earnings is not cheap.** State which of the three explains a fund's
cheapness before calling it value.

### P/B ÷ ROE: compare only matched holdings [plugin]

The engine computes P/B and weighted ROE over the holdings that have both, and applies the
coverage gate to that set. A cross-check, not an override of other valuation evidence.

## Who runs it

Each claim here carries its source URL and date: the AMC's own documents, SEBI orders, AMFI,
manager interviews, news.

- **The manager's whole record.** A manager runs several funds; if most of them trail their
  categories while one shines, the shining one is the exception. Three or more of five in their
  category's top tier is a manager; one or two is luck [moneypurse-mf:imTFTLKJSX0@11:23]
  [moneypurse-mf:imTFTLKJSX0@11:31].
- **The fund house's bench.** Managers move. The AMC needs the depth and the means to replace
  one with someone as good, and a philosophy owned by the house rather than one person
  [moneypurse-mf:imTFTLKJSX0@12:09] [soic-mf:HNbs4Df-NNo@17:40].
- **The philosophy, in the manager's words**: read the AMC's letters and watch the interviews,
  then check the book against them (§ *Does the book match the claimed style?*)
  [soic-mf:CfRMqIFXfaw@17:53].
- **Experience across cycles**: how the fund and its manager behaved in earlier falls and
  phases, not only in the current one [soic-mf:CfRMqIFXfaw@18:29]
  [soic-mf:CfRMqIFXfaw@19:16].
- **Skin in the game.** Insiders investing in their own scheme beyond the regulatory minimum is
  a plus, stated in rupees from the AMC's disclosure [soic-mf:HNbs4Df-NNo@05:02].
- **Client-first conduct**: closing a strategy to protect its holders, cash calls instead of
  forced deployment; against that, mis-selling, expense abuse, front-running, side-pocketing and
  SEBI orders [soic-mf:HNbs4Df-NNo@02:52] [plugin].

## Diagnosing underperformance

When a fund trails, ask why, and whether the cause persists [soic-mf:HNbs4Df-NNo@18:32]. A
fund that trails for a reason that passes is a different decision from one that trails for a
reason that stays. Work through the causes in order and name the one the evidence supports:

1. **The style is out of favour.** Quality and high-P/E styles de-rate when rates rise, because
   rates act as gravity on valuations; Axis Long Term Equity led its category from 2010 to
   2020, has trailed since, and its quality book de-rated as rates rose
   [soic-mf:MiUQ8Xen9Nw@00:06] [soic-mf:MiUQ8Xen9Nw@08:51] [soic-mf:MiUQ8Xen9Nw@12:44]. Value funds lag in momentum markets [soic-mf:HNbs4Df-NNo@09:04].
   Test: do funds of the same style trail too? If they do, the cause is the cycle, and it
   passes; the holder decides whether they want that style.
2. **Size has caught up with it** [soic-mf:On_60FfH32o@20:42]. Test: AUM growth against the
   category ceiling, the liquidity stress test, a shrinking share of mid and small caps. Size
   does not reverse.
3. **A constraint binds**, such as a regulatory cap on overseas investing that cut a fund's
   foreign share from about 30% to 11% [soic-mf:On_60FfH32o@04:27]. Persists until the
   constraint lifts; name it and do not forecast the lift.
4. **Cash drag**: high cash in a rising market [soic-mf:On_60FfH32o@07:12]. Passes if the
   cash is deployed; check the record of earlier cash calls.
5. **The people or the process changed**: a new manager, a merger, a new mandate
   (§ *Whose record is it?*). The old record no longer describes the fund.
6. **The book has deteriorated**: rising distress share, a style the book no longer matches,
   drift. This is the one a holder should act on soonest.

The plugin's own reading: causes 1, 3 and 4 are reasons to hold a fund whose style the holder
wants; 2, 5 and 6 are reasons to review it [plugin].

## Index funds

An index fund is judged on cost and fidelity, not on a manager: the **expense ratio** first,
then the **tracking error** against its index, lower on both [dtt-mf:VCvrI1fycJ0@05:14]
[dtt-mf:t30uuDXAh4I@22:49] [soic-mf:_ylJeMaQepE@20:29]. For an index fund the scan's
`tracking_error` is the decision field; the alpha and capture metrics do not apply. If the whole
selection process is too much for the holder, an index fund is the default
[moneypurse-mf:imTFTLKJSX0@14:34].

- **Measure against the Total Returns Index**, which adds reinvested dividends, never the price
  index; SEBI has required TRI benchmarks since 2018 [soic-mf:_ylJeMaQepE@17:41] [law].
- **Compare like with like**: Direct with Direct, a fund with the TRI of the index it tracks
  [soic-mf:_ylJeMaQepE@33:55].
- **Tracking error has causes**: transaction costs, the expense ratio, imperfect execution,
  cash held for flows, and impact cost in the less liquid broad indices. It tends to fall as AUM
  grows and the TER falls [soic-mf:_ylJeMaQepE@21:29] [soic-mf:_ylJeMaQepE@28:38].
- **An ETF trades at a price, not the NAV**: check its premium to NAV and its trading volume
  before buying [soic-mf:_ylJeMaQepE@36:15] [dtt-mf:t30uuDXAh4I@17:50]. An index fund takes a SIP;
  an ETF needs an order each time [soic-mf:_ylJeMaQepE@35:13].
- **Which index**: the Nifty 50 is concentrated in its top ten names; a Nifty 500 fund is the
  broader alternative at a slightly higher cost [soic-mf:nQwah2nxdWU@05:22].

## Debt funds

A debt fund is chosen by three things in order: the **horizon match**, the **credit quality**,
then the **rate sensitivity**. Return comes last [moneypurse-mf:ZxF5cQ0ygqM@11:52].

### Match the horizon to the category's mandate

Each SEBI debt category fixes the maturity or duration of what it holds [law]. Hold money in the
category whose mandate matches when it is needed; a mismatch either costs return or adds
volatility the holder did not want [moneypurse-mf:xJtNKZXWgmU@03:00].

| Horizon | Category (SEBI mandate) |
|---|---|
| days | overnight (1-day paper) |
| up to about 3 months | liquid (paper up to 91 days); a liquid ETF on a demat account is the exchange-traded equivalent [dtt-mf:t30uuDXAh4I@17:50] |
| 3–6 months | ultra-short duration |
| 6–12 months | low duration, money market (paper up to a year) |
| 1–3 years | short duration |
| 3 years and more | medium, medium-to-long and long duration; gilt; corporate bond; banking and PSU; dynamic bond |

[law] [moneypurse-mf:xJtNKZXWgmU@03:59] [moneypurse-mf:xJtNKZXWgmU@17:06]

### Credit quality before yield

A higher yield is the market's price for a higher chance of default
[moneypurse-mf:ZxF5cQ0ygqM@08:21] [dtt-mf:UvRjV_t-lJA@13:40]. Before comparing returns, read where
the book sits on the rating scale: the share in sovereign and AAA paper, and the share below AA
[moneypurse-mf:ZxF5cQ0ygqM@11:52].

- **A small yield pickup is not worth weaker paper.** Between a mostly-AAA fund at 8% and an
  A-rated one at 8.3%, take the AAA fund; extra credit risk needs a gap of one to three points
  to be worth considering [moneypurse-mf:ZxF5cQ0ygqM@12:38].
- **Ratings move.** A rating is reviewed continuously and can fall to D, as DHFL's did
  [moneypurse-mf:ZxF5cQ0ygqM@10:46] [moneypurse-mf:ZxF5cQ0ygqM@11:20].
- **In a credit-risk fund, no single issuer should be more than about 2–4% of the book**, so one
  default is a small hit [moneypurse-mf:xJtNKZXWgmU@21:43]. Never park money in a credit-risk
  fund [varsity-pf:24-26].
- **Gilt funds carry no credit risk, only rate risk** [dtt-mf:UvRjV_t-lJA@28:38].
- **For a debt fund, larger AUM is better**, unlike equity: it meets redemptions without forced
  sales [dtt-mf:UvRjV_t-lJA@25:40] [dtt-mf:1EjK7vG7kuI@25:35].
- **A short-duration fund showing equity-like returns is taking risk to get them.** In the
  liquid-to-short categories, a return well above its peers' is a reason to read the book, not
  a reason to buy [dtt-mf:1EjK7vG7kuI@26:10].

### Rate sensitivity: show both directions

Bond prices move against rates, and more so the longer the duration
[moneypurse-mf:xJtNKZXWgmU@07:48] [dtt-mf:UvRjV_t-lJA@02:08]. Over a year, roughly:

> expected return ≈ YTM − TER − modified duration × change in yield (percentage points)

[moneypurse-mf:xJtNKZXWgmU@11:51]. A fund at YTM 8.26% and duration 4.17 earns about 12.4% if
yields fall a point and about 4.1% if they rise one; a fund at 9.26% with duration 1.99 earns
about 11.3% and 7.3% [moneypurse-mf:xJtNKZXWgmU@12:48] [moneypurse-mf:xJtNKZXWgmU@15:09].

`run_debt_scenarios` computes them; report both the +1 and −1 point outcomes, never one. Long duration and gilt suit a holder who
expects rates to fall; accrual and short duration suit one who expects them to rise or holds no
view; a dynamic bond fund hands the call to the manager [moneypurse-mf:xJtNKZXWgmU@16:17]
[moneypurse-mf:xJtNKZXWgmU@17:51] [dtt-mf:UvRjV_t-lJA@22:38]. The rate view is the holder's,
stated and labelled; the plugin has no approved rate-cycle source and never supplies one
(`methods/market.md`). YTM, modified duration and the rating mix come from the AMC's factsheet,
cited with its date.

### Tax

Gains on a debt-oriented fund bought from 2023-04-01 are taxed at the holder's slab rate,
whatever the holding period [law] [dtt-mf:UvRjV_t-lJA@31:40]; there is no indexation, so a debt
fund and an FD at the same pre-tax yield are taxed alike. Arbitrage funds are taxed as equity
and suit a high-slab holder parking money for over a year [dtt-mf:t30uuDXAh4I@20:09].

## Weighing the evidence [plugin]

The verdict is a forward-leaning **fund-quality grade** (Hold-worthy / Watch / Avoid) combining
the book's valuation and quality, style fit, construction, cost, size and the people, with the
rolling and SIP record as one input, not the headline. State the two or three deciding factors.
Every data gap (a young fund without 5Y windows, stale holdings, look-through coverage below
100%, a factsheet field not found) is named, never filled.

A fund grade is not a category call. "Is this fund good?" and "is its category worth adding to
now?" get separate answers; the second comes from the cap tier's valuation percentile and
breadth (`methods/market.md`).

## Sources

Fund facts no tool serves come from the fund's own documents, cited by name and date: the AMC's
monthly factsheet (turnover, YTM, modified duration, rating mix, manager and tenure), the scheme
information document (mandate, benchmark), the monthly liquidity stress-test disclosure, and the
AMC's disclosure of insiders' investment. Morningstar and Value Research pages can point to a
fact; they are not its source [dtt-mf:VCvrI1fycJ0@14:26].

These were tested for holdings and do not serve them; `get_fund_holdings` serves the complete
book.

| Source | Result |
|---|---|
| Morningstar India `detailed-portfolio.aspx` | Paywalled: data behind "Unlock" |
| AMFI portfolio-disclosure portal | JS-driven; WebFetch sees an empty dropdown. Tickertape's API already returns the complete book |
| AdvisorKhoj monthly-disclosure pages | Lists months, but every link bounces to a generic AMC downloads page |
| ValueResearch portfolio-holdings page | Partial, top-N only |
| Tickertape **HTML** fund page | Top-5 plus "See All"; the **API** is the right door |
| mfapi.in for holdings | NAV-only by design |
| Groww TER on a Direct-plan page | **Trap:** can serve the Regular-plan expense ratio. Verify against AMFI or the AMC factsheet |
