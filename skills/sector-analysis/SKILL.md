---
name: sector-analysis
description: >-
  Read one Indian sector deep — first its growth story (how big, how fast, what drives it, what policy backs or threatens it, who has pricing power), then relative strength vs Nifty, the sector's own KPIs, sourced tailwinds and headwinds, leaders and laggards, and where a focus stock sits inside it. Use whenever the user names a sector: "how does banking look", "is IT turning", "is pharma a buy", or wants sector context before picking a stock. Ranking the whole rotation ("which sector is hot") is `discover sectors`; this skill reads one named sector.
argument-hint: "<sector, e.g. 'banking' or 'IT'> [optional: a focus stock to position inside it]"
allowed-tools: Read, Write, Bash, Skill, WebSearch, WebFetch, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*
---

# Sector Analysis — one sector deep

This skill reads **one named sector**. Ranking the sectoral indices to find which is worth a look ("which sector is hot", "where's money flowing") is discovery — an empty `/sector-analysis` hands off to `discover sectors`, which ranks the rotation and calls this skill on each top sector. Given a company instead of a sector, resolve it to its sector first.

Read `references/reference.md` first — it owns the method: the growth story and where each part of it is sourced, the five-step per-sector read, the relative-strength classification, the evidence rule for tailwinds and headwinds, the sector KPI map, how the constituent set is built, and the index ticker map. This SKILL is the workflow.

**A sector's future decides more than its chart.** If the industry has no growth story, a stock inside it rarely compounds whatever its RS says, so the growth story is read first and carries the stance; relative strength, cycle and leaders/laggards are the market's current read on that story — secondary, and reported second.

**Sources for this skill only:** for the growth story, `finance-company` `get_documents(<SYMBOL>, annual_reports=1, concalls=1)` for the focus company and the two or three sector leaders — read the `outline` sections `industry`, `opportunities_threats` and `outlook` (the MD&A every listed company must publish under SEBI LODR Schedule V) and the concall — plus the issuing-authority and industry-body sites the reference's § "Growth-story sources" names, through `WebSearch` with `allowed_domains` and `WebFetch` of the document itself. For the market's read, `finance-market` — `run_sector_screen` for the sector's RS-vs-Nifty windows and classification (the single RS definition — read this sector's row), `get_history(..., adjusted=True)` for stock OHLCV (price vs 50-EMA, on the same adjusted basis as the screens) and any index chart cross-check, `get_indices` for sectoral index levels; `finance-company` — `get_company_fundamentals` for the constituent set and stock-level KPIs, and `get_news("<sector> policy OR budget OR regulation OR duty OR PLI")` for the policy, duty and regulation items a tailwind or headwind bullet cites.

**Policy comes from the authority that issued it.** Google News RSS is a headline feed: a headline can tell you a duty moved, it cannot give you the mechanism, the quantum or the effective date. Find the notification, circular or final finding on the issuing authority's own site (reference § "Growth-story sources") and cite its number and date. A policy you cannot reach there is a **labelled data gap** — never a remembered figure, never a news paraphrase promoted to fact.

## Workflow

1. **Inputs**: the sector, optionally a focus ticker to position inside it, optionally the constituent list the caller resolved, optionally an output path, optionally a cached sector body (a caller passes one only when its cache is fresh). Given a company name instead of a sector, resolve it to its sector first.
2. **Cached body given — position-only.** Reuse the cached growth story, RS, cycle, KPI snapshot, tailwinds/headwinds, leaders/laggards and stance **as-is; recompute no part of the sector body**. Work only step 5 of the reference, the focus-stock position, and carry the reused body verbatim into the report with a one-line `sector body reused from cache (generated <date>)`, then skip to the report.
3. **No cached body — write the growth story first** (reference § "The growth story"), **then work the reference's five steps in order**, computing the full body. Step 1's RS comes from **`run_sector_screen`** (it returns every sector's classified RS — read this sector's row). A sector the screen does not cover (cement, hotels, retail, media…) has no row: report RS as a data gap, or compute it on a named constituent basket with `get_history(..., adjusted=True)` and say that it is a basket, not an index; steps 2–5 (KPIs, cycle, leaders/laggards, focus position) are computed here.
4. **No unsourced tailwind, headwind or story claim.** Each carries the KPI reading (company + period), the annual-report section (company + FY + section), the issuing authority's document (number + date), the `get_news` item (publisher + date) or the index series and window behind it; a factor you cannot source becomes a **Data gaps** line instead of a bullet — the reference's *Evidence rule* has the standard.
5. **Seed the shared cache**, whenever step 3 computed a fresh body (never on the position-only path): write the **sector-level body** — not the focus-stock overlay — to `paths.sector_cache_path(sector)` with frontmatter `generated: <today>` + `rs_class: <classification>`, and set the next-refresh reminder with `manage_alerts(action="add", kind="sector_refresh_due", subject_type="sector", subject_id="<sector>", due="<today + 30d>", created_by="sector-analysis", severity="watch", suggest="/sector-analysis <sector>", dedup_key="sector-refresh-<sector>")` (dedup updates any existing reminder in place). A later `deep-analysis` on a stock in this sector reuses that body instead of recomputing it.

### Produce this report

The leading block is machine-read, so the caller cites the sector read without re-deriving it:

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
**What the industry is**: what it sells, to whom, and how big it is today — size with its unit, year and source
**Growth**: the last five years and management's or the cited industry outlook, each sourced; say whose forecast it is
**Demand drivers**: up to 3, each sourced — what makes people buy more of this every year
**Structural shifts**: formalisation, import substitution, technology, consolidation — what is changing the industry's shape
**Policy & regulation**: each item with the issuing authority, document number and date; what it does and until when
**Competitive structure**: fragmented or consolidated, who sets price, barriers to entry, where returns are made
**Lifecycle & verdict**: the `story` class with one paragraph on why, and the one thing that would break it

### The market's read
**RS vs Nifty**: 1M <±x.x%> / 3M <±x.x%> / 6M <±x.x%> → classification (Leading/Improving/Weakening/Lagging)
**Cycle position**: one line — where this sector sits in the rotation cycle and why now
**KPI snapshot**: the sector's signature KPIs, current reading + trend, each sourced (NIM/GNPA/CASA, EBITDA/tonne, VNB margin/combined ratio, SSSG, ARR/RevPAR, etc.)
**Tailwinds**: up to 3 bullets, each with its source; "none sourced" is a valid answer
**Headwinds**: up to 3 bullets, each carrying its source — same rule
**Leaders / laggards**: 3 leaders + the weakest name, one KPI each
**<FOCUS TICKER> within the sector**: [only if a focus stock was given] RS vs the sector index, KPI vs sector median, leader-or-laggard, does the sector tail/headwind help or hurt it
**Sector stance**: favorable / neutral / unfavorable for new longs, one sentence why, confidence low/med/high. The story sets the direction; RS and cycle set the timing. A `structural_decline` story is never `favorable`, and a `structural_growth` story with weak RS reads "favorable story, poor timing" rather than unfavorable.
**Data gaps**: every KPI, index or factor that could not be sourced, and why
```

Write it to the output path you were given, or to `artifacts/sector-analysis/YYYY-MM-DD/<sector>.md` (`paths.report_dir("sector-analysis", date)`) when none was. **Keep every field name exactly as the block has it.** Persist the full report, then return only the `sector-block` fields plus `path`.

When `discover sectors` runs this skill per top sector, it reads these `sector-block` digests to build the rotation deck — so the block and its field names are the contract.

## Boundaries

This reads the sector, not the stock: the chart on a name is `technical-analysis`, its numbers are `financial-analysis`, what it is worth is `valuation-analysis`. Every RS number and KPI cites its source and window. A blocked source or an unpulled KPI is a **Data gaps** line, never a guess — a caller treats missing evidence as uncertainty, not as neutral. No trade advice beyond the sector stance; position-level calls belong to the caller.
