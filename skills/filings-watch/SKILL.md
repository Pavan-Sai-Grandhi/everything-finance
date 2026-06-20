---
name: filings-watch
description: Pull NSE and BSE exchange filings for a ticker — corporate announcements, corporate actions (dividend/split/bonus/buyback), board meetings, and shareholding pattern changes — and classify what's material. Use whenever the user asks what a company announced, about recent filings, results dates, dividends, promoter stake changes, bulk/block deals, or "any news from the exchanges on X".
argument-hint: "TICKER [lookback window, default 30 days]"
allowed-tools: WebFetch, Read, Write, Bash, mcp__playwright__*
---

# Exchange Filings Watch

Read `references/reference.md` for the materiality classification and source endpoints. The mechanical fetch+classify core is the shared **`lib/filings.py`** — the canonical data-spine fetcher (daily-brief calls it too) so the BSE/NSE endpoints and the materiality taxonomy live in one place. This skill is the judgement layer on top: the browser-only shareholding/pledge read and the "so what" narrative.

**Sites for this skill only:** NSE and BSE (primary, via the script's BSE JSON + Playwright for NSE — both block plain HTTP HTML), screener.in Documents section (fallback mirror for announcements/shareholding). No news sites — this skill reports *filings*, the news-sentiment agent handles press.

## Workflow

1. **Resolve symbol** on both exchanges (NSE symbol + BSE scrip code; screener.in company page header lists both). The script needs the **BSE scrip code**.

2. **Fetch + classify the feed with the script** (it walks the fallback ladder itself — BSE JSON API first, then resolves the scrip to its NSE symbol and reads the NSE announcements API after a homepage cookie-bootstrap when BSE is blocked):
   ```bash
   python3 <plugin>/lib/filings.py --scrip <BSE_CODE> --days <lookback> \
       --out artifacts/stocks/<TICKER>/YYYY-MM-DD/filings.json
   ```
   It returns the data-spine envelope — `ok`, `source` (which exchange served it), announcements already classified into act-on / monitor / routine under `data.items` (+ forthcoming corporate actions), and a `gaps` list. **Each blocked rung names itself in `gaps`** (e.g. `BSE fingerprint block: HTTP 200 "No Record Found!"`) — a labelled gap, never a silent empty, so `ok:false` with a gap means "unknown", not "nothing filed". When the script can't resolve the NSE symbol, pass `--symbol <NSE_SYMBOL>`. Two things still need the browser/web rungs:
   - (b) **NSE pages via Playwright** (cookie bootstrap from the homepage first) — the **only** reliable source for the **SHP pledge %** detail.
   - (c) **screener.in via WebFetch** — Documents/Announcements mirror + shareholding table, when both exchange rungs are gapped.
   De-duplicate announcements filed on both exchanges (same subject ± minutes apart). **Single-exchange rule**: if only one exchange is reachable, skip de-dup and state in data-gaps that the other is assumed to mirror it — near-lossless for dual-listed large caps; for single-listed names, name what's missing.

3. **Review the script's classification** (taxonomy in reference.md): 🔴 act-on (results, M&A, pledge increase, resignation of auditor/KMP, fraud/regulatory action, buyback) / 🟡 monitor (capex, order wins, credit-rating notes, investor-meet PPTs) / ⚪ routine (trading windows, ESOP allotments, newspaper copies). The script is the first-pass filter; **apply judgement on top** — an "unclassified → monitor" item, or an order win whose size you can size against revenue, may move tiers. Most filings are noise; the value of this skill is the filter plus that judgement.

4. **Shareholding delta**: fixed table format — `Quarter | Promoter % | Pledge % | FII % | DII % | Public %`, ≥ 4 quarters. If no SHP was filed inside the lookback window, show the latest quarterly anyway and say so in the section header. Pledge rising while stock falls is the classic red flag — call it out explicitly; if pledge data is unreachable (it often needs the browser path), state that as a gap rather than implying nil.

## Output

Markdown report (text-first, no HTML template): materiality-grouped filing list with dates and one-line summaries, corporate-actions calendar (ex-dates), shareholding delta table, and a 2–3 sentence "so what". Save to `artifacts/stocks/<TICKER>/YYYY-MM-DD/filings.md` (`paths.stock_dir(ticker, date)`). On a re-run, `paths.latest_prior("filings", TICKER)` finds the previous scan — add a one-line `prior run: <path> (<date>)` link and report only what's new since then. If one exchange blocks even Playwright, continue with the other + screener.in and note the gap.

## Alerts this skill raises (via `lib/alerts.py`)

For every **🔴 act-on** filing found, raise a **`filing_act_on`** alert so `daily-brief` surfaces it (`subject: {type: stock, id: <TICKER>}`, `created_by: filings-watch`, `severity: act`, `action.text` = the one-line filing summary, `action.suggest: "/filings-watch <TICKER>"` or `/deep-analysis <TICKER>`, `trigger: {check: filings-watch, args: {symbol: <TICKER>}}`, `dedup_key: filing-<TICKER>-<filing-date>`). 🟡 monitor / ⚪ routine items do **not** raise alerts — keep the inbox act-worthy only.
