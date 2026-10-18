---
name: filings-watch
description: Pull NSE exchange filings for a ticker — corporate announcements, corporate actions (dividend/split/bonus/buyback), board meetings, and shareholding pattern changes — and classify what's material. Use whenever the user asks what a company announced, about recent filings, results dates, dividends, promoter stake changes, bulk/block deals, or "any news from the exchanges on X".
argument-hint: "TICKER [lookback window, default 30 days]"
allowed-tools: Read, Write, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-workflow__get_prior_run, mcp__plugin_everything-finance_finance-workflow__get_prior_run, mcp__finance-workflow__manage_alerts, mcp__plugin_everything-finance_finance-workflow__manage_alerts
---

# Filings Watch

The tools fetch and do the first-pass classification; this skill is the judgment on top, the
"so what". It reports filings; press coverage is `news-scan`.

**Method:** `methods/filings.md`.

## Workflow

1. **Resolve the NSE symbol**, the key for every tool here. A BSE-only company is a labelled gap,
   not an empty feed.
2. **Fetch**: `get_filings(symbol, days)`. Its items arrive classified act-on, monitor or routine
   in the file at `data.items_path`, and `data.corporate_actions` carries the actions; call
   `get_corporate_actions` only when the user wants actions alone. `ok:false` with a gap means
   unknown, never "nothing filed".
3. **Review the classification** against the method and apply judgment: an unclassified item, or
   an order win you can size against revenue, may move tiers.
4. **Shareholding**: `get_shareholding` (promoter, public and pledge by quarter) and
   `get_company_fundamentals(sections=['shareholding'])` (the FII/DII/public split over six
   quarters). Tabulate `Quarter | Promoter % | Pledge % | FII % | DII % | Public %` for at least
   four quarters, showing only quarters with data and labelling the missing ones. If no pattern
   was filed inside the window, show the latest and say so. An empty NSE pledge list is unknown,
   never zero.

## Output

A markdown report: the filings grouped by materiality with dates and one-line summaries, the
corporate-actions calendar with ex-dates, the shareholding table, and a two-to-three-sentence "so
what". Save it to `artifacts/stocks/<TICKER>/<YYYY-MM-DD>/filings.md`. On a re-run,
`get_prior_run(skill="filings", subject=TICKER)` returns the previous scan: link it as
`prior run: <path> (<date>)` and report only what is new.

## Alerts

For every act-on filing, a `filing_act_on` alert: `subject_type: stock`, `subject_id: <TICKER>`,
`created_by: filings-watch`, `severity: act`, `text` = the one-line summary,
`suggest: "/filings-watch <TICKER>"`, `check: filings-watch`, and
`dedup_key: filing-<TICKER>-<filing_id>` (several filings can share a date). Monitor and routine
items raise no alert.
