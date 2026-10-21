---
name: sector-analysis
description: >-
  Read one Indian sector deep. First its growth story (its value chain, how big and how fast, what drives demand, what supply is coming, what policy backs or threatens it, who has pricing power), then its valuation against its own history, relative strength vs Nifty, the sector's own KPIs, sourced tailwinds and headwinds, leaders and laggards, and where a focus stock sits inside it. Use whenever the user names a sector: "how does banking look", "is IT turning", "is pharma a buy", or wants sector context before picking a stock. Ranking the whole rotation ("which sector is hot") is `discover sectors`; this skill reads one named sector.
argument-hint: "<sector, e.g. 'banking' or 'IT'> [optional: a focus stock to position inside it]"
allowed-tools: Read, Write, Skill, WebSearch, WebFetch, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-workflow__manage_alerts, mcp__plugin_everything-finance_finance-workflow__manage_alerts
---

# Sector analysis: one sector deep

Reads one named sector; given a company, resolve it to its sector first. An empty
`/sector-analysis` hands off to `discover sectors`, which ranks the rotation. A sector's future
decides more than its chart, so the growth story is read first and carries the stance; relative
strength, cycle and leaders are the market's current read on that story, reported second. It
reads the sector, not the stock (the chart, numbers and value of a name belong to their own
skills), and gives no trade advice beyond the stance.

**Method:** `methods/sectors/framework.md` for the evidence and the market's read, plus the
sector's own file it indexes (value chain, KPIs, swing factors). The lens below is how to think
about any sector; the sector file says what that thinking looks at for this one.

**Where the evidence comes from.** For the growth story: `get_documents(<SYMBOL>,
annual_reports=1, concalls=1)` for the focus company and two or three leaders (their MD&A
`industry`, `opportunities_threats` and `outlook` sections and the concall), and the
issuing-authority and industry-body sites the method names, through `WebSearch` with
`allowed_domains` and `WebFetch` of the document itself. A policy is cited from the authority that
issued it, by number and date; a headline is a pointer, never the source of its terms, and a
policy you cannot reach there is a gap. For the market's read: `run_sector_screen` (the one RS
definition; read this sector's row), `get_technicals` for each stock's position against its
50-EMA, `get_indices` for levels, `get_index_valuation_history` for the index's P/E and P/B percentile,
`get_company_fundamentals` for the constituent set and KPIs,
`run_technical_screen` for the constituent cross-section in one call, and
`get_news("<sector> policy OR budget OR regulation OR duty OR PLI")` for the items a tailwind or
headwind cites.

## The lens: reading any sector

These questions apply to every sector. Each one cites where it comes from. Answer them in order.
The growth story is built from questions 1 to 5 and carries the stance's direction. Questions 6
and 7 feed the market's read.

1. **Split the sector, then map its value chain.**
   - **Split.** "Pharma" or "IT" names several businesses with different economics, so split
     the sector into sub-groups, each with its own problem [soic-sectors:PM4Tu3Oj-YU@02:50]. One
     name can cover unrelated industries ("pipes" spans steel, stainless and plastic). Never
     compare companies across the splits [soic-sectors:2o-FV9b-yJw@06:21].
   - **Map the chain** layer by layer, from raw material to end customer. Say three things
     about it [soic-sectors:0vcpmbL_BLs@02:11]:
     - where margins sit;
     - which layer is technology- or capital-heavy;
     - which layer is easy to enter.

     The bottleneck layer that everything passes through earns the returns, and the layers
     downstream of it compete hard. A layer with one or two suppliers is a choke point and
     holds the power [soic-sectors:3nmtnVb7pJk@15:30] [soic-sectors:aSBuzr4ufx0@31:19]. In a young industry the
     layers earn in sequence: assembly on imported cores comes first, then policy pulls the core
     layer onshore. Ask which layer is earning now [soic-sectors:BQAPVmZC72o@15:41]
     [soic-sectors:BQAPVmZC72o@50:47].
   - **Revenue streams.** List how the companies make money, stream by stream, and which
     streams are regulated [soic-sectors:snogVxecaVs@05:40]. Say who controls the profit pool
     in each sub-segment [soic-sectors:8yL5g4Gd8DY@05:22].
   - **Place and sort the companies.** Place each company on the chain before judging it
     [soic-sectors:1hKTKUTxtLw@03:12]. Then sort them into types, each with its own risk
     [soic-sectors:SwmOLZ7Bp3g@03:38] [soic-sectors:sdG9b3Xue-k@41:00]:
     - the leader that has cracked the model;
     - the mean-reversion name with temporarily hurt margins;
     - the proxy that sells to the sector (picks and shovels);
     - the aspiring entrant funding the move with another business.

     Score each one on growth against its barrier to entry [soic-sectors:Funuk-of7t8@1:05:23].
     For a theme stock, check what share of its revenue the theme actually is
     [soic-sectors:aSBuzr4ufx0@1:10:08].
2. **Size it and find the demand driver.**
   - **The filter.** A sector worth owning grows faster than nominal GDP, or takes share from
     somewhere else [soic-sectors:AirPj2owHLA@00:11].
   - **The need.** Start with why the product is needed at all [soic-sectors:BQAPVmZC72o@00:22].
   - **Size and growth.** Give today's size with unit, year and source; the last five years'
     growth; and the outlook with whose forecast it is. MD&A sections often quote a
     third-party figure (CRISIL, ICRA, a ministry); cite the company, FY and section *and* the
     source it names [plugin].
   - **The driver.** A driver needs a reading, not a slogan: "credit/GDP at X%" beats
     "under-penetrated" [plugin].
   - **Where leadership is moving.** Market leadership rotates by regime. The next leaders sit
     where capital formation and government support are moving
     [soic-sectors:ICz5ejNhJFc@00:07] [soic-sectors:ICz5ejNhJFc@03:54]. Where a product is mostly
     imported, the import share sizes what localisation can capture
     [soic-sectors:ICz5ejNhJFc@36:09].
   - **A theme that spans sectors** (rural, capex, defence). Find where the theme's money comes
     from and a gauge of its stress. List each dependent sector with its share of exposure.
     The theme is live when the linked sectors are cheap and their RS rises together
     [soic-sectors:MWQNACOuo9I@00:17] [soic-sectors:MWQNACOuo9I@01:49].
   - **Share migrating inside the sector.** Share can move from unorganised to organised
     players, from PSU to private, or from in-house teams to outsourced specialists. A rule such
     as GST or hallmarking often pushes it. That migration can be the story even when the
     industry grows slowly [soic-sectors:J6tTMG2FxCA@03:07] [soic-sectors:J6tTMG2FxCA@08:19]
     [soic-sectors:AirPj2owHLA@02:25].
3. **Read the supply side.**
   - **Structural or cyclical.** If cyclical, say which phase [soic-sectors:osKVi2JSIzQ@04:15].
     Say how deep the cycle runs: margins that swing a few points are a different risk from
     losses [soic-sectors:0i_mVwvtXuE@21:35]. A one-time build-out, where the spend does not
     repeat once the asset is laid, gives a few good years and then several bad ones
     [soic-sectors:-fp3XootfB4@15:17]. For a sector coming back, list the chain of causes
     that ended its last boom and check which are absent now [soic-sectors:Funuk-of7t8@06:04].
   - **Supply overshoots.** High prices pull in capacity, and every shortfall eventually becomes
     oversupply [soic-sectors:osKVi2JSIzQ@04:50] [soic-sectors:0vcpmbL_BLs@26:43]. High returns
     attract entrants even while demand grows ("your margin is my opportunity"), and supply is
     easier to forecast than demand [soic-sectors:3S7Ky_bHf8Q@03:06]
     [soic-sectors:3S7Ky_bHf8Q@03:30].
   - **Capacity arithmetic.**
     - Add up the capex announced by listed players and entrants, from their filings and
       concalls.
     - Multiply by the guided asset turn to get the sales capacity it creates
       [soic-sectors:ZSbojYZUZg4@22:28].
     - Set that against demand grown at its *realised* rate, not the rate a capex announcement
       assumes [soic-sectors:3S7Ky_bHf8Q@18:38] [soic-sectors:3S7Ky_bHf8Q@21:52].
     - Compare installed capacity with actual sales [soic-sectors:0vcpmbL_BLs@19:43].
   - **Returns on capital.** If capital employed grows faster than profit, industry ROCE falls
     and the stocks de-rate [soic-sectors:3S7Ky_bHf8Q@11:38]. Where entry is easy, a market value
     far above the replacement cost of assets (Tobin's Q well above 1) invites capital. Where a
     moat blocks replication, that test does not apply [soic-sectors:3S7Ky_bHf8Q@05:16]
     [soic-sectors:3S7Ky_bHf8Q@06:57].
   - **Global supply.** China's output and exports set the global price for much of Indian
     manufacturing, so check them [soic-sectors:ZSbojYZUZg4@12:30]. In a commodity, the cost of
     the largest producer sets the price floor [soic-sectors:osKVi2JSIzQ@16:13].
4. **Name who holds pricing power, and why.**
   - **Who sets price.** Count the players and their shares, and say who sets price and why
     [soic-sectors:ZSbojYZUZg4@40:30] [soic-sectors:0vcpmbL_BLs@03:46]
     [soic-sectors:2o-FV9b-yJw@1:08:08]:
     - scale;
     - a licence;
     - customer-approval cycles;
     - consolidation;
     - integration;
     - freight cost, which caps how far a heavy product travels.

     Some sectors have several winners, so do not assume the leader takes all
     [soic-sectors:J6tTMG2FxCA@10:22]. Test a pricing-power claim on margins: did they hold through an
     adverse event (a tariff, an input spike), and how do they compare with peers selling
     similar products [soic-sectors:ufBz90jnI9Q@04:41] [soic-sectors:ufBz90jnI9Q@16:15]?
   - **Protected prices.** A price protected by policy (a duty, a domestic-content rule, a
     licence) is weaker than an earned one. Name the instrument and its expiry, because when the
     policy goes the profits go [soic-sectors:0vcpmbL_BLs@33:34]. Each policy item names the
     issuing authority, document number and date.
   - **Regulated returns.** A tariff order or a capped ROE makes growth predictable, not high. A
     concession's end date limits how long the story runs [soic-sectors:snogVxecaVs@07:44]
     [soic-sectors:snogVxecaVs@29:03].
5. **Set the story class and what breaks it.** The classes are:
   - `structural_growth`: demand compounding above GDP for years.
   - `cyclical_upswing` / `cyclical_downswing`: a commodity or capex cycle.
   - `mature`: grows with GDP; consolidation sets returns.
   - `structural_decline`: shrinking demand or a substitute.

   Name the single thing that would break the story. For a disruption threat, state the bear and
   bull cases, then track revenue and margin rather than pick one
   [soic-sectors:PM4Tu3Oj-YU@33:42]. A story with no sourced size or growth is
   `story_confidence: low` and says so; it is never filled from memory [plugin].
6. **Read the economics through the cycle.**
   - **Margins.** Compare each bellwether's current margin with its own long-run average, and
     ask whether the gap reverts [soic-sectors:ZSbojYZUZg4@03:48]
     [soic-sectors:1hKTKUTxtLw@54:53]. Note how many quarters cost increases take to reach
     price [soic-sectors:0i_mVwvtXuE@23:07].
   - **Converters.** Where raw material is most of sales, read earnings per unit, not
     percentage margin [soic-sectors:2o-FV9b-yJw@41:07].
   - **Mix.** Product mix usually explains margin gaps between peers (the studded share in
     jewellery, the CDMO share in pharma, the value-added share in dairy). A richer mix also
     makes margins less cyclical [soic-sectors:J6tTMG2FxCA@22:54]
     [soic-sectors:0i_mVwvtXuE@25:02].
   - **Share and margin together.** Share bought at a thin margin leaves poor returns
     [soic-sectors:BtlIHcvhYZg@14:35].
   - **Capacity.**
     - New capacity at low utilisation means margins expand as it fills
       [soic-sectors:ZSbojYZUZg4@44:37].
     - Capacity near 100% leaves no room to grow [soic-sectors:sdG9b3Xue-k@36:01].
     - An asset turn near 1x caps return on capital [soic-sectors:1hKTKUTxtLw@49:00].
     - Capex is worth more as a dedicated block against a signed contract, and brownfield earns
       more than greenfield [soic-sectors:sdG9b3Xue-k@33:35].
     - Payback depends on where the expansion goes: brownfield pays back in months, a new
       site in a new geography in years. Today's high ROCE is often the payoff of a past
       low-return capex cycle, and a new expansion resets it [soic-sectors:lKtSrARFu6Q@04:37]
       [soic-sectors:lKtSrARFu6Q@05:13].
   - **Cash.**
     - CFO to EBITDA shows who sets the payment terms.
     - A customer that is the company's own group is a concentration to measure
       [soic-sectors:3nmtnVb7pJk@29:25] [soic-sectors:3nmtnVb7pJk@33:09].
     - Where the government is the buyer, watch receivables
       [soic-sectors:yfcouNoKV3w@32:49].
   - **Order books.** In an order-led sector, read the order book against sales for the years
     of revenue it covers [soic-sectors:yfcouNoKV3w@43:18].
   - **Time frame.**
     - Judge lumpy results over two to three years, not a quarter
       [soic-sectors:sdG9b3Xue-k@37:42].
     - Once fundamentals turn, momentum tends to last 8 to 12 quarters up and 4 to 8 down
       [soic-sectors:PM4Tu3Oj-YU@20:19].
7. **Set the price against the story.**
   - **What drives return.** Shareholder return is earnings growth, plus payouts, plus any change
     in the multiple [soic-sectors:PM4Tu3Oj-YU@10:37] [soic-sectors:3RhFffI1WK0@18:02].
   - **The temperature check.** Set the multiple against where earnings sit in their cycle
     [soic-sectors:3reNGUatnUE@00:48] [soic-sectors:3reNGUatnUE@15:08]:
     - A peak multiple on peak earnings means a drawdown is near.
     - A bottom multiple on bottom earnings means very cheap.
     - A below-average multiple with healthy earnings growth means value remains.
     - An average multiple with growing earnings means compounding can continue.
   - **Where the multiple sits.**
     - A multiple near the top of its own history with maturing growth leaves nothing for
       re-rating.
     - Earnings growing while the multiple falls is the contrarian setup. List the reasons for
       the de-rating explicitly [soic-sectors:3RhFffI1WK0@01:45].
     - When competition rises, the multiple can revert to its mean even while earnings grow 18
       to 20% [soic-sectors:3S7Ky_bHf8Q@27:13].
   - **Cyclicals.**
     - In a downturn, assume earnings recover and see what multiple remains
       [soic-sectors:ZSbojYZUZg4@55:53].
     - Study a seasonal or cyclical sector in its bad season, when the weakness is outside the
       companies' control.
     - At a cyclical low, read value on price to sales [soic-sectors:BtlIHcvhYZg@01:23]
       [soic-sectors:BtlIHcvhYZg@31:11].

**Signals the cycle has turned against a sector or a name**, read from concalls and filings:

- Managements start talking about cost cutting [soic-sectors:PM4Tu3Oj-YU@23:39].
- Guidance slips a second year [soic-sectors:ZSbojYZUZg4@30:33].
- A lender's covenant is breached [soic-sectors:1hKTKUTxtLw@38:10].
- Cash flow is weak inside a strong theme [soic-sectors:ICz5ejNhJFc@35:50].
- Growth comes from lower-margin products [soic-sectors:ZSbojYZUZg4@49:42].

## Workflow

1. **Inputs**: the sector; optionally a focus ticker, the caller's constituent or peer list, an
   output path, and a cached sector body (passed only when fresh).
2. **Cached body given**: reuse its growth story, RS, cycle, KPIs, tailwinds and headwinds,
   leaders and stance as they are; work only the focus-stock position (method step 6), and note
   `sector body reused from cache (generated <date>)`.
3. **Otherwise**: write the growth story first, then the method's six steps in order. A sector
   the screen does not cover (cement, hotels, retail, media) has no RS row: report it as a gap, or
   compute it on a named constituent basket and say it is a basket, not an index.
4. **No unsourced tailwind, headwind or story claim** (the method's evidence rule): an unsourced
   factor is a Data gaps line, not a bullet.
5. **Seed the cache** whenever step 3 ran: write the sector-level body (not the focus-stock
   overlay) to `artifacts/state/sectors/<sector-slug>.md` with frontmatter `generated: <today>`
   and `rs_class: <class>`, and set the refresh reminder: `manage_alerts(action="add",
   kind="sector_refresh_due", subject_type="sector", subject_id="<sector>", due="<today + 30d>",
   created_by="sector-analysis", severity="watch", suggest="/sector-analysis <sector>",
   dedup_key="sector-refresh-<sector>")`.

## Report

```
<!-- sector-block
sector: <slug>   rs_class: Leading | Improving | Weakening | Lagging
story: structural_growth | cyclical_upswing | mature | cyclical_downswing | structural_decline   story_confidence: low | med | high
stance: favorable | neutral | unfavorable   confidence: low | med | high
focus_position: leader | laggard | n/a
-->
## Sector read: <SECTOR> (<date>)

## Findings
<Everything from this leg that could change a verdict, in 3-6 plain sentences, each with its number and where it came from, the growth story first and the market's read second. A reader who stops here has the leg's whole case.>

## Detail

### The growth story
**What the industry is**: what it sells, to whom, and its size today with unit, year and source
**Value chain**: the sub-groups and the chain's layers; where margins sit, which layer is risky, which is protected
**Growth**: the last five years and the cited outlook, each sourced; say whose forecast it is
**Demand drivers**: up to 3, each sourced
**Structural shifts**: formalisation, import substitution, technology, consolidation
**Supply side**: capacity being added against demand, installed capacity against sales, the import and China read, each sourced
**Policy & regulation**: each item with the issuing authority, document number and date; what it does and until when
**Competitive structure**: fragmented or consolidated, who sets price, barriers to entry, where returns are made
**Lifecycle & verdict**: the `story` class with one paragraph on why, and the one thing that would break it

### The market's read
**RS vs Nifty**: 1M <±x.x%> / 3M <±x.x%> / 6M <±x.x%> → classification
**Cycle position**: one line on where it sits in the rotation and why now
**KPI snapshot**: the sector's signature KPIs, reading and trend, each sourced; current margins against their own long-run average
**Valuation vs its history**: the index's P/E or P/B percentile, and whether the multiple and earnings growth agree
**Tailwinds**: up to 3, each with its source; "none sourced" is a valid answer
**Headwinds**: up to 3, each with its source
**Leaders / laggards**: 3 leaders and the weakest name, one KPI each
**<FOCUS TICKER> within the sector**: [only with a focus stock] RS against the sector index, KPI against the sector median, leader or laggard, whether the tailwind or headwind helps or hurts it
**Sector stance**: favorable / neutral / unfavorable for new longs, one sentence, with confidence. The story sets the direction; RS and cycle set the timing. A `structural_decline` story is never favorable; `structural_growth` with weak RS reads "favorable story, poor timing"
**Data gaps**: every KPI, index or factor that could not be sourced, and why
```

Write it to the output path given, or to `artifacts/sector-analysis/<YYYY-MM-DD>/<sector>.md`. Keep
every field name exactly as the block has it: `discover sectors` builds its deck from these
blocks. Return only the `sector-block` fields plus `path`.
