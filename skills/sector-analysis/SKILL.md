---
name: sector-analysis
description: >-
  Read one Indian sector deep — first its growth story (how big, how fast, what drives it, what policy backs or threatens it, who has pricing power), then relative strength vs Nifty, the sector's own KPIs, sourced tailwinds and headwinds, leaders and laggards, and where a focus stock sits inside it. Use whenever the user names a sector: "how does banking look", "is IT turning", "is pharma a buy", or wants sector context before picking a stock. Ranking the whole rotation ("which sector is hot") is `discover sectors`; this skill reads one named sector.
argument-hint: "<sector, e.g. 'banking' or 'IT'> [optional: a focus stock to position inside it]"
allowed-tools: Read, Write, Skill, WebSearch, WebFetch, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-workflow__manage_alerts, mcp__plugin_everything-finance_finance-workflow__manage_alerts
---

# Sector Analysis: one sector deep

Reads one named sector; given a company, resolve it to its sector first. An empty
`/sector-analysis` hands off to `discover sectors`, which ranks the rotation. A sector's future
decides more than its chart, so the growth story is read first and carries the stance; relative
strength, cycle and leaders are the market's current read on that story, reported second. It
reads the sector, not the stock (the chart, numbers and value of a name belong to their own
skills), and gives no trade advice beyond the stance.

**Method:** `methods/sectors.md`.

**Where the evidence comes from.** For the growth story: `get_documents(<SYMBOL>,
annual_reports=1, concalls=1)` for the focus company and two or three leaders (their MD&A
`industry`, `opportunities_threats` and `outlook` sections and the concall), and the
issuing-authority and industry-body sites the method names, through `WebSearch` with
`allowed_domains` and `WebFetch` of the document itself. A policy is cited from the authority that
issued it, by number and date; a headline is a pointer, never the source of its terms, and a
policy you cannot reach there is a gap. For the market's read: `run_sector_screen` (the one RS
definition; read this sector's row), `get_technicals` for each stock's position against its
50-EMA, `get_indices` for levels, `get_company_fundamentals` for the constituent set and KPIs,
`run_technical_screen` for the constituent cross-section in one call, and
`get_news("<sector> policy OR budget OR regulation OR duty OR PLI")` for the items a tailwind or
headwind cites.

## Workflow

1. **Inputs**: the sector; optionally a focus ticker, the caller's constituent or peer list, an
   output path, and a cached sector body (passed only when fresh).
2. **Cached body given**: reuse its growth story, RS, cycle, KPIs, tailwinds and headwinds,
   leaders and stance as they are; work only the focus-stock position (method step 5), and note
   `sector body reused from cache (generated <date>)`.
3. **Otherwise**: write the growth story first, then the method's five steps in order. A sector
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
## Sector Read — <SECTOR> (<date>)

## Findings
<Everything from this leg that could change a verdict, in 3-6 plain sentences — each with its number and where it came from, the growth story first and the market's read second. A reader who stops here has the leg's whole case.>

## Detail

### The growth story
**What the industry is**: what it sells, to whom, and its size today with unit, year and source
**Growth**: the last five years and the cited outlook, each sourced; say whose forecast it is
**Demand drivers**: up to 3, each sourced
**Structural shifts**: formalisation, import substitution, technology, consolidation
**Policy & regulation**: each item with the issuing authority, document number and date; what it does and until when
**Competitive structure**: fragmented or consolidated, who sets price, barriers to entry, where returns are made
**Lifecycle & verdict**: the `story` class with one paragraph on why, and the one thing that would break it

### The market's read
**RS vs Nifty**: 1M <±x.x%> / 3M <±x.x%> / 6M <±x.x%> → classification
**Cycle position**: one line — where it sits in the rotation and why now
**KPI snapshot**: the sector's signature KPIs, reading and trend, each sourced
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
