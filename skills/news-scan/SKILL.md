---
name: news-scan
description: Scan roughly the last 60 days of press, exchange announcements and analyst commentary on one Indian company and score the sentiment from sourced, dated evidence — hard facts separated from narrative, the recurring storyline named, what the filings show that coverage has missed, and the scheduled events ahead. Use whenever the user asks what is being said about a company: "any news on X", "why did X fall today", "what's the sentiment on X", "is the coverage bullish or bearish", "anything I should know before their results", "is that story about X real". This is the press-and-sentiment read on one company — the exchange filings themselves are filings-watch, the whole-market morning digest is daily-brief, and the full bull/bear debate is deep-analysis.
argument-hint: "TICKER or company name [optional: lookback window, default 60 days]"
allowed-tools: Read, Write, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*
---

# News Scan — sentiment on one company, from dated evidence

Read `references/reference.md` first — it owns the method: the window rule, the fact-vs-narrative standard, how publisher tier weighs a claim, the four sentiment traps, and the −2…+2 scale with its confidence rubric. This SKILL is the workflow.

**Sources for this skill only:** `finance-company` — `get_news(company, ticker, days=60)` and `get_filings(symbol, days)`. No article scraping: `get_news` already returns each item **dated, deduped, classified** (`company` | `sector` | `noise`), tagged **fact | narrative**, and carrying its `source` and `publisher_tier`, with noise filtered from the default view and a blocked publisher rung as a labelled `gap`. `get_filings` returns **no items inline** — its whole list goes to `data.items_path`, so `Read` that file rather than re-calling the tool.

## Workflow

1. **Inputs**: the ticker and the company name, and — where an orchestrator has one — an output path.
2. **Fetch once.** `get_news` over the window, `get_filings` over the same span, then `Read` the filings file. The work here is judgement, not plumbing; widen the window only for the reason the reference gives.
3. **Sort the items** into fact and narrative, weighing each by publisher tier and by whether a filing stands behind it. Where two outlets carry **different numbers for the same reported figure**, the disagreement is usually standalone-vs-consolidated or a restated comparative — resolve it against the filing in `get_filings`, which is the primary source, and report the filed figure with the discrepancy named. Leaving both numbers in as a gap passes a resolvable conflict downstream.
4. **Find the storyline** the coverage keeps returning to, and the filing it has *not* picked up.
5. **Score and grade confidence** on the reference's scale, then check the read against each of the four traps before you commit to it.

## Produce this report

The leading block is machine-read, so the PM and synthesis cite the read without re-deriving it:

```
<!-- news-block
sentiment_score: <-2..+2>   confidence: low | med | high
recurring_theme: <one phrase>   next_event: <item + date, or none>
axis: growth_durability
-->
## News & Sentiment — <COMPANY> (<date>)

## Findings
<Everything from this leg that could change a verdict, in 3-6 plain sentences — each with its number and where it came from. A reader who stops here has the leg's whole case.>

## Detail

**Sentiment score**: -2 (strongly negative) … +2 (strongly positive), with one-line justification
**Material events (last 60d)**: dated list, each tagged FACT/NARRATIVE + source
**Recurring theme**: the one storyline the coverage keeps returning to
**What the news misses**: anything filings show that coverage hasn't picked up (or "none found")
**Event risk ahead**: scheduled items the announcements name — results date, AGM, regulatory deadlines (the dividend/split calendar is `filings-watch`'s, not yours)
**Confidence**: low/med/high (driven by source quality and volume)
```

Write it to the output path you were given, or to `artifacts/stocks/<TICKER>/YYYY-MM-DD/news.md` (`paths.stock_dir(symbol, date)`) when none was. **Keep every field name exactly as the block has it.** Persist the full report, then return only the `news-block` fields plus `path`.

## Boundaries

This reads coverage, not the business: it scores what is being said and how well sourced it is. Whether the numbers behind the story hold up is `financial-analysis`, whether the price already reflects it is `valuation-analysis`, and the governance verdict on an allegation is `management-analysis`. Sentiment is an input to a decision, never the decision.
