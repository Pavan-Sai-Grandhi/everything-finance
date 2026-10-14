# News & sentiment method (self-contained)

Coverage is evidence about a company only after it has been dated, attributed and separated from opinion. Everything below is how that separation is made.

## The window

The default is the last ~60 days — recent enough that the market still cares, long enough to show a pattern rather than one day's headline. Widen `days` when a **thesis-controlling event sits just outside it** (a tax or regulatory change, an M&A announcement, a fraud allegation) and say in the report that you widened it and why. The window serves recency, not amnesia.

## Fact vs narrative — the separation that carries the whole read

- **FACT** — an event with a date and a named source that either already happened or is contractually committed: an order win, a results beat or miss, a regulatory action, a capacity commissioning, a resignation, a fundraise. `get_news` tags items `reported` or `narrative` from the headline only. A `reported` item is a claim until a primary source confirms it. Keep allegations labelled as allegations.
- **NARRATIVE** — broker price targets, upgrades and downgrades, "buzz", anchor opinion, sector think-pieces, anonymous "sources say". Narrative is worth reporting because it moves price, never worth reporting as evidence about the business.

**Publisher tier weighs the claim.** Each item carries `publisher_tier` (`established` | `aggregator` | `unknown`), read from the feed's publisher name, so it does not verify the outlet or the story. A claim from one aggregator or unknown publisher is that publisher's assertion; label it so, without dropping or promoting it.

**Cross-check against the exchange.** A material development a company has not announced to the exchange is **rumor-grade** — report it, mark it rumor-grade, and name what filing would confirm it. The reverse case is more valuable: a filing coverage has not picked up is the one edge a news scan can genuinely produce.

## The sentiment traps

1. **Stale news re-reported as fresh.** An aggregator recycling a six-month-old order win reads as new positive flow. Check the underlying event date, not the publication date.
2. **Placed articles.** Promoter-friendly coverage clusters around a fundraise, an IPO, an OFS or a pledge release. A sudden burst of uniformly positive, similarly-worded pieces with no filing behind them is a placement pattern, not sentiment.
3. **Lagging downgrade clusters.** Broker downgrades arrive *after* the price move. A cluster of them describes what already happened; treating it as forward signal is double-counting the fall.
4. **Volume mistaken for direction.** More articles is not more positive. Count the direction, not the coverage.

## Scoring

| Score | What it means |
|---|---|
| +2 | Coverage is dominated by dated, filing-backed positives that change the business, not the mood |
| +1 | Net positive, but carried by narrative or by facts too small to move the thesis |
| 0 | Genuinely quiet — few material items, and the ones present cancel or are immaterial |
| −1 | Net negative: a real problem is being reported, or the positives have stopped |
| −2 | A thesis-threatening negative with a filing or regulator behind it |

**Never average away disagreement.** If coverage is split, the score *is* the split — "+1 on business news, −1 on governance coverage" — never a fake 0. A 0 means quiet; it does not mean contested.

**Confidence** is driven by source quality and volume: `high` when several established publishers and at least one exchange filing corroborate the read; `med` when the read rests on a thin item count or on aggregators; `low` when a source was blocked, the window returned almost nothing, or the picture is one publisher's.

## Evidence standard

Quote sparingly and date everything. Never return an empty report because one source was blocked — name the degradation the envelope already reports and give the read the remaining items support.
