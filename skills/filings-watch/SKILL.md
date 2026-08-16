---
name: filings-watch
description: Pull NSE exchange filings for a ticker — corporate announcements, corporate actions (dividend/split/bonus/buyback), board meetings, and shareholding pattern changes — and classify what's material. Use whenever the user asks what a company announced, about recent filings, results dates, dividends, promoter stake changes, bulk/block deals, or "any news from the exchanges on X".
argument-hint: "TICKER [lookback window, default 30 days]"
allowed-tools: WebFetch, Read, Write, Bash, mcp__finance-data__*
---

# Exchange Filings Watch

Read `references/reference.md` for the materiality classification. The mechanical fetch+classify core is the `finance-data` server, so the endpoints and the materiality taxonomy live in one place. This skill is the judgement layer on top: the "so what" narrative.

**Sources for this skill only:** the `finance-data` tools `get_filings`, `get_corporate_actions`, `get_shareholding` (all NSE), and `get_company_fundamentals(sections=['shareholding'])` for the FII/DII split. No news sites — this skill reports *filings*; the news-sentiment agent handles press.

## Workflow

1. **Resolve the NSE symbol** — the primary key for every tool here. (BSE scrip codes are no longer used; BSE was dropped as a source, so a BSE-only-listed company is a labelled gap, not a silent empty.)

2. **Fetch + classify the feed.** Call `get_filings` (symbol, days) and `get_corporate_actions` (symbol).

   The envelope gives `ok`, `source`, announcements already classified into act-on / monitor / routine under `data.items`, forthcoming corporate actions, and a `gaps` list. **A blocked source names itself in `gaps`** — a labelled gap, never a silent empty, so `ok:false` with a gap means "unknown", not "nothing filed". The full item list is written to `data.items_path`; read that file rather than re-calling the tool.

3. **Review the script's classification** (taxonomy in reference.md): 🔴 act-on (results, M&A, pledge increase, resignation of auditor/KMP, fraud/regulatory action, buyback) / 🟡 monitor (capex, order wins, credit-rating notes, investor-meet PPTs) / ⚪ routine (trading windows, ESOP allotments, newspaper copies). The script is the first-pass filter; **apply judgement on top** — an "unclassified → monitor" item, or an order win whose size you can size against revenue, may move tiers. Most filings are noise; the value of this skill is the filter plus that judgement.

4. **Shareholding delta**: call `get_shareholding` (promoter %, public %, pledge, per quarter) and `get_company_fundamentals(sections=['shareholding'])` (the FII/DII/public split across 12 quarters). Fixed table format — `Quarter | Promoter % | Pledge % | FII % | DII % | Public %`, ≥ 4 quarters. If no SHP was filed inside the lookback window, show the latest quarterly anyway and say so in the section header. Pledge rising while stock falls is the classic red flag — call it out explicitly. **NSE frequently returns no pledge rows; that means UNKNOWN, not nil** — the tool labels it as a gap and the report must repeat it as a gap, never as zero pledge.

## Output

Markdown report (text-first, no HTML template): materiality-grouped filing list with dates and one-line summaries, corporate-actions calendar (ex-dates), shareholding delta table, and a 2–3 sentence "so what". Save to `artifacts/stocks/<TICKER>/YYYY-MM-DD/filings.md` (`paths.stock_dir(ticker, date)`). On a re-run, `paths.latest_prior("filings", TICKER)` finds the previous scan — add a one-line `prior run: <path> (<date>)` link and report only what's new since then. If NSE blocks, continue with whatever was gathered and name the gap — an unreachable source means "unknown", never "nothing filed".

## Alerts this skill raises (via `lib/alerts.py`)

For every **🔴 act-on** filing found, raise a **`filing_act_on`** alert so `daily-brief` surfaces it (`subject: {type: stock, id: <TICKER>}`, `created_by: filings-watch`, `severity: act`, `action.text` = the one-line filing summary, `action.suggest: "/filings-watch <TICKER>"` or `/deep-analysis <TICKER>`, `trigger: {check: filings-watch, args: {symbol: <TICKER>}}`, `dedup_key: filing-<TICKER>-<filing-date>`). 🟡 monitor / ⚪ routine items do **not** raise alerts — keep the inbox act-worthy only.
