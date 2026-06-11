---
name: filings-watch
description: Pull NSE and BSE exchange filings for a ticker — corporate announcements, corporate actions (dividend/split/bonus/buyback), board meetings, and shareholding pattern changes — and classify what's material. Use whenever the user asks what a company announced, about recent filings, results dates, dividends, promoter stake changes, bulk/block deals, or "any news from the exchanges on X".
argument-hint: "TICKER [lookback window, default 30 days]"
allowed-tools: WebFetch, Read, Write, Bash, mcp__playwright__*
---

# Exchange Filings Watch

Read `references/reference.md` for the materiality classification and source endpoints.

**Sites for this skill only:** NSE and BSE (primary, via Playwright — both block plain HTTP clients), screener.in Documents section (fallback mirror for announcements/shareholding). No news sites — this skill reports *filings*, the news-sentiment agent handles press.

## Workflow

1. **Resolve symbol** on both exchanges (NSE symbol + BSE scrip code; screener.in company page header lists both).

2. **Fetch — try in this order** (verified 2026-06: the BSE *JSON API* works over plain HTTP; only the exchanges' HTML pages block non-browser clients):
   - (a) **BSE public JSON APIs via WebFetch/curl** — announcements and corporate actions endpoints pinned in reference.md; no browser needed
   - (b) **NSE pages via Playwright** (cookie bootstrap from the homepage first) — needed for the SHP pledge detail
   - (c) **screener.in via WebFetch** — Documents/Announcements mirror + shareholding table
   De-duplicate announcements filed on both exchanges (same subject ± minutes apart). **Single-exchange rule**: if only one exchange is reachable, skip de-dup and state in the data-gaps note that the other is assumed to mirror it — near-lossless for dual-listed large caps; for NSE-only/BSE-only listings, name what's missing.

3. **Classify by materiality** (taxonomy in reference.md): 🔴 act-on (results, M&A, pledge increase, resignation of auditor/KMP, fraud/regulatory action, buyback) / 🟡 monitor (capex, order wins, credit-rating notes, investor-meet PPTs) / ⚪ routine (trading windows, ESOP allotments, newspaper-ad copies). Most filings are noise — the value of this skill is the filter.

4. **Shareholding delta**: fixed table format — `Quarter | Promoter % | Pledge % | FII % | DII % | Public %`, ≥ 4 quarters. If no SHP was filed inside the lookback window, show the latest quarterly anyway and say so in the section header. Pledge rising while stock falls is the classic red flag — call it out explicitly; if pledge data is unreachable (it often needs the browser path), state that as a gap rather than implying nil.

## Output

Markdown report (text-first, no HTML template): materiality-grouped filing list with dates and one-line summaries, corporate-actions calendar (ex-dates), shareholding delta table, and a 2–3 sentence "so what". Save to `artifacts/YYYY-MM-DD/<TICKER>-filings.md`. If one exchange blocks even Playwright, continue with the other + screener.in and note the gap.
