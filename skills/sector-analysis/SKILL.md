---
name: sector-analysis
description: Read one Indian sector deep — relative strength vs Nifty, the sector's own KPIs, sourced tailwinds and headwinds, leaders and laggards, and where a focus stock sits inside it — or, when no sector is named, rank the NSE sectoral indices by relative strength and deep-dive the top three. Use whenever the user asks about a sector: "how does banking look", "is IT turning", "which sectors are hot", sector rotation, where money is flowing, "which sector should I look at", or wants sector context before picking a stock.
argument-hint: "[sector, e.g. 'banking' or 'IT' — omit to rank the rotation and deep-dive the top three] [optional: a focus stock to position inside it]"
allowed-tools: Read, Write, Bash, Agent, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*
---

# Sector Analysis — one sector deep, or the rotation ranked

Read `references/reference.md` first — it owns the method: the five-step per-sector read, the relative-strength windows and classification, the evidence rule for tailwinds and headwinds, the sector KPI map, how the constituent set is built, the index ticker map and the rotation notes. This SKILL is the workflow.

**Sources for this skill only:** `finance-market` — `get_history` for sectoral-index and stock OHLCV (relative strength, price vs 50-EMA), `get_market_context` (mode `quick`) for the shared sector ranking, `get_indices` for sectoral index levels; `finance-company` — `get_company_fundamentals` for the constituent set and stock-level KPIs, and `get_news("<sector> policy OR budget OR regulation OR duty OR PLI")` for the policy, duty and regulation items a tailwind or headwind bullet cites.

**Policy has no approved source.** Google News RSS is a headline feed, not a policy source: a headline can tell you a duty moved, it cannot give you the mechanism, the quantum or the effective date. Those are a **labelled data gap** unless the user supplies the document — never a remembered figure and never an improvised scrape.

## Modes

- **Single-sector** — exactly one sector is named, by the user or by a caller passing a sector plus an optional focus ticker and an optional cached body. Produce the read for that one sector here, in this context.
- **Multi-sector** — no sector named (rank the rotation and take the top three), or several named (skip the ranking and take exactly those). One `terminal-analyst` per sector.

**Single-sector mode fans out to nothing — it launches no agent, for any reason.** The profile agent the multi-sector path spawns invokes this same skill; if the single-sector path spawned one too, the skill would call itself without limit. A named sector is one read, computed inline.

## Single-sector workflow

1. **Inputs**: the sector, optionally a focus ticker to position inside it, optionally the constituent list the caller resolved, optionally an output path, optionally a cached sector body (a caller passes one only when its cache is fresh). Given a company name instead of a sector, resolve it to its sector first.
2. **Cached body given — position-only.** Reuse the cached RS, cycle, KPI snapshot, tailwinds/headwinds, leaders/laggards and stance **as-is; recompute no part of the sector body**. Work only step 5 of the reference, the focus-stock position, and carry the reused body verbatim into the report with a one-line `sector body reused from cache (generated <date>)`, then skip to the report.
3. **No cached body — work the reference's five steps in order**, computing the full body.
4. **No unsourced tailwind or headwind.** Each bullet carries the KPI reading (company + period), the `get_news` item (publisher + date) or the index series and window behind it; a factor you cannot source becomes a **Data gaps** line instead of a bullet — the reference's *Evidence rule* has the standard.
5. **Seed the shared cache**, whenever step 3 computed a fresh body (never on the position-only path): write the **sector-level body** — not the focus-stock overlay — to `paths.sector_cache_path(sector)` with frontmatter `generated: <today>` + `rs_class: <classification>`, and set the next-refresh reminder with `manage_alerts(action="add", kind="sector_refresh_due", subject_type="sector", subject_id="<sector>", due="<today + 30d>", created_by="sector-analysis", severity="watch", suggest="/sector-analysis <sector>", dedup_key="sector-refresh-<sector>")` (dedup updates any existing reminder in place). A later `deep-analysis` on a stock in this sector reuses that body instead of recomputing it.

### Produce this report

The leading block is machine-read, so the caller cites the sector read without re-deriving it:

```
<!-- sector-block
sector: <slug>   rs_class: Leading | Improving | Weakening | Lagging
stance: favorable | neutral | unfavorable   confidence: low | med | high
focus_position: leader | laggard | n/a
-->
## Sector Read — <SECTOR> (<date>)

## Findings
<Everything from this leg that could change a verdict, in 3-6 plain sentences — each with its number and where it came from. A reader who stops here has the leg's whole case.>

## Detail

**RS vs Nifty**: 1M <±x.x%> / 3M <±x.x%> / 6M <±x.x%> → classification (Leading/Improving/Weakening/Lagging)
**Cycle position**: one line — where this sector sits in the rotation cycle and why now
**KPI snapshot**: the sector's signature KPIs, current reading + trend, each sourced (NIM/GNPA/CASA, EBITDA/tonne, VNB margin/combined ratio, SSSG, ARR/RevPAR, etc.)
**Tailwinds**: 2–3 bullets, each carrying its source
**Headwinds**: 2–3 bullets, each carrying its source
**Leaders / laggards**: 3 leaders + the weakest name, one KPI each
**<FOCUS TICKER> within the sector**: [only if a focus stock was given] RS vs the sector index, KPI vs sector median, leader-or-laggard, does the sector tail/headwind help or hurt it
**Sector stance**: favorable / neutral / unfavorable for new longs, one sentence why, confidence low/med/high
**Data gaps**: every KPI, index or factor that could not be sourced, and why
```

Write it to the output path you were given, or to `artifacts/sector-analysis/YYYY-MM-DD/<sector>.md` (`paths.report_dir("sector-analysis", date)`) when none was. **Keep every field name exactly as the block has it.** Persist the full report, then return only the `sector-block` fields plus `path`.

## Multi-sector workflow

1. **Rank the rotation** — only when no sector was named; with sectors named, go straight to step 2 and keep the grid as light context. Cheap first pass: `get_market_context` (mode `quick`) and its `sectors.leaders` / `sectors.laggards` (a 1-year ranking, already computed from one NSE fetch) decides which sectors are worth the full treatment. For those, pull the index series with `get_history` and compute RS over the reference's windows and classification. Then pick the **top three** by the reference's ranking rule.
2. **Fan out — one `everything-finance:terminal-analyst` per sector, in parallel.** Each call names the skill `sector-analysis`, the mode `single-sector`, the sector, no focus stock, and the output path `artifacts/sector-analysis/YYYY-MM-DD/<sector>.md` (`paths.report_dir("sector-analysis", date)`). Each returns the `sector-block` digest plus its `path`; `Read` the files and synthesize from them — do not paste the digests back.
3. **Output.** Emit the render projection `artifacts/sector-analysis/<date>.report.json` — a **render input with no consumer** (a missing field renders as a labelled gap, never a fabricated number), shaped like the worked example at `skills/_report/scripts/fixtures/sector-analysis.sample.json`: the cover rotation verdict, the RS **grid** colored by classification (the full grid when the ranking ran, the named sectors otherwise), a `deepdives` list (one slide per analyzed sector — RS windows, cycle, KPI table, tailwinds/headwinds, stance), a `picks` table built from the per-sector leaders, a `drivers` synthesis, and the gaps/sources slide. Then produce the deck:

   ```
   python3 skills/_report/scripts/render_report.py \
     --report-json artifacts/sector-analysis/<date>.report.json \
     --template sector-analysis \
     --out artifacts/sector-analysis/<date>.html
   ```

   `render_report.py` is pure compute over that JSON (it fetches nothing); every RS number and KPI in it carries the source and window it came from, and a classification chip's tone (Leading→pos, Improving→accent, Weakening→warn, Lagging→neg) is the read. In chat: open with the 2–3 sentence rotation story (what leads, what is turning, what to avoid), then per analyzed sector its stance, the one tailwind and one headwind that matter, and its top pick with a one-line reason.

## Boundaries

This reads the sector, not the stock: the chart on a name is `technical-analysis`, its numbers are `financial-analysis`, what it is worth is `valuation-analysis`. Every RS number and KPI cites its source and window. A blocked source or an unpulled KPI is a **Data gaps** line, never a guess — a caller treats missing evidence as uncertainty, not as neutral. No trade advice beyond the sector stance; position-level calls belong to the caller.
