---
name: news-scan
description: >-
  Scan roughly the last 60 days of press, exchange announcements and analyst commentary on one Indian company and score the sentiment from sourced, dated evidence — hard facts separated from narrative, the recurring storyline named, what the filings show that coverage has missed, and the scheduled events ahead. Use whenever the user asks what is being said about a company: "any news on X", "why did X fall today", "what's the sentiment on X", "is the coverage bullish or bearish", "anything I should know before their results", "is that story about X real". This is the press-and-sentiment read on one company — the exchange filings themselves are filings-watch, the whole-market morning digest is daily-brief, and the full bull/bear debate is deep-analysis.
argument-hint: "TICKER or company name [optional: lookback window, default 60 days]"
allowed-tools: Read, Write, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*
---

# News Scan: sentiment on one company, from dated evidence

It reads coverage, not the business: whether the numbers hold up is `financial-analysis`, whether
the price reflects it is `valuation-analysis`, and the governance verdict on an allegation is
`management-analysis`. Sentiment is an input to a decision, never the decision.

**Method:** `methods/news.md`.

## Workflow

1. **Inputs**: the ticker, the company name and, from an orchestrator, an output path.
2. **Fetch once**: `get_news(company, ticker, days=60)` and `get_filings(symbol, days=60)`, then
   read the filings file at `data.items_path`. `get_news` items arrive dated, deduplicated,
   classified and tagged `reported` or `narrative` from the headline alone (unverified), each with
   its `publisher_tier`. Widen the window only for the reason the method gives.
3. **Sort** the items into verified fact, reported claim or allegation, and narrative, weighing
   each by publisher tier and by whether a filing stands behind it. Where outlets carry different
   numbers for one reported figure, the difference is usually standalone against consolidated or a
   restated comparative: resolve it against the filing and report the filed figure with the
   discrepancy named.
4. **Find the storyline** the coverage keeps returning to, and the filing it has not picked up.
5. **Score and grade confidence** on the method's scale, then check the read against each of the
   four traps.

## Report

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

**Sentiment score**: −2 … +2, with a one-line justification
**Material events (last 60d)**: dated list, each tagged FACT (primary-source verified), REPORTED/ALLEGATION or NARRATIVE, with its source
**Recurring theme**: the storyline the coverage keeps returning to
**What the news misses**: what the filings show that coverage has not picked up, or "none found"
**Event risk ahead**: scheduled items the announcements name (results date, AGM, regulatory deadlines)
**Confidence**: low/med/high, from source quality and volume
```

Write it to the output path given, or to `artifacts/stocks/<TICKER>/<YYYY-MM-DD>/news.md`. Keep
every field name exactly as the block has it. Return only the `news-block` fields plus `path`.
