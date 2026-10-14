---
name: filings-watch
description: Pull NSE exchange filings for a ticker — corporate announcements, corporate actions (dividend/split/bonus/buyback), board meetings, and shareholding pattern changes — and classify what's material. Use whenever the user asks what a company announced, about recent filings, results dates, dividends, promoter stake changes, bulk/block deals, or "any news from the exchanges on X".
argument-hint: "TICKER [lookback window, default 30 days]"
allowed-tools: Read, Write, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-market__get_prior_run, mcp__finance-market__manage_alerts, mcp__plugin_everything-finance_finance-market__get_prior_run, mcp__plugin_everything-finance_finance-market__manage_alerts
---

# Exchange Filings Watch

The tools do the mechanical fetch and first-pass classification; this skill is the judgement layer on top — the "so what" narrative. Read `references/reference.md` for the materiality taxonomy.

**Sources for this skill only:** `finance-company` — `get_filings`, `get_corporate_actions`, `get_shareholding` (all NSE) and `get_company_fundamentals(sections=['shareholding'])` for the FII/DII split, and `finance-market` `get_prior_run` for the previous scan. No news sites — this skill reports *filings*; `news-scan` handles press.

## Workflow

1. **Resolve the NSE symbol** — the primary key for every tool here. A company listed only on BSE is a labelled gap, not a silent empty.

2. **Fetch + classify the feed.** Call `get_filings` (symbol, days); its `data.corporate_actions` already has the corporate actions. Call `get_corporate_actions` only when the user wants actions alone.

   The envelope gives `ok`, `source`, announcements already classified into act-on / monitor / routine under `data.items`, forthcoming corporate actions, and a `gaps` list. **`ok:false` with a gap means "unknown", not "nothing filed"** — never report an unreachable source as a clean feed. The full item list is written to `data.items_path`; read that file rather than re-calling the tool.

3. **Review the classification** (taxonomy in reference.md): 🔴 act-on (results, M&A, pledge increase, resignation of auditor/KMP, fraud/regulatory action, buyback) / 🟡 monitor (capex, order wins, credit-rating notes, investor-meet PPTs) / ⚪ routine (trading windows, ESOP allotments, newspaper copies). That is the first-pass filter; **apply judgement on top** — an "unclassified → monitor" item, or an order win whose size you can size against revenue, may move tiers. Most filings are noise; the value of this skill is the filter plus that judgement.

4. **Shareholding delta**: call `get_shareholding` (promoter %, public %, pledge, per quarter) and `get_company_fundamentals(sections=['shareholding'])` (the FII/DII/public split across the six quarters Tickertape publishes). Table format — `Quarter | Promoter % | Pledge % | FII % | DII % | Public %`; request at least four quarters, show only quarters with data and label the missing ones. Say what each percentage is of. NSE's public category includes institutions, so do not add it to FII/DII as if it were retail. If no SHP was filed inside the lookback window, show the latest quarterly anyway and say so in the section header. Report a rising pledge and a falling price as two separate facts; you may note collateral risk, but do not predict a forced sale or guess at motive. **NSE frequently returns no pledge rows; that means UNKNOWN, not nil** — the tool labels it as a gap and the report must repeat it as a gap, never as zero pledge.

## Output

Markdown report (text-first, no HTML template): materiality-grouped filing list with dates and one-line summaries, corporate-actions calendar (ex-dates), shareholding delta table, and a 2–3 sentence "so what". Save to `artifacts/stocks/<TICKER>/YYYY-MM-DD/filings.md` (`paths.stock_dir(ticker, date)`). On a re-run, `get_prior_run(skill="filings", subject=TICKER)` finds the previous scan in `data.path` — add a one-line `prior run: <path> (<date>)` link and report only what's new since then.

## Alerts this skill raises (via `manage_alerts`)

For every **🔴 act-on** filing found, raise a **`filing_act_on`** alert so `daily-brief` surfaces it (`subject: {type: stock, id: <TICKER>}`, `created_by: filings-watch`, `severity: act`, `action.text` = the one-line filing summary, `action.suggest: "/filings-watch <TICKER>"` or `/deep-analysis <TICKER>`, `trigger: {check: filings-watch, args: {symbol: <TICKER>}}`, `dedup_key: filing-<TICKER>-<filing_id>`). 🟡 monitor / ⚪ routine items do **not** raise alerts — keep the inbox act-worthy only.

Use the item's `filing_id`, because several filings can share a date. Each material filing gets its own alert, and a rerun updates the existing one.
