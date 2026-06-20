---
name: sector-analysis
description: Sector analysis for Indian markets — deep-dive the sector(s) the user names, or, if none is named, rank the NSE sectoral indices by relative strength and deep-dive the top three in the current market. Each sector read covers relative strength, sector-specific KPIs, tailwinds/headwinds, and top stock picks. Use whenever the user asks about a specific sector, which sectors are hot, sector rotation, where money is flowing, "which sector should I look at", or wants sector-level context before picking stocks.
argument-hint: "[optional: one or more sectors to deep-dive, e.g. 'banking' or 'IT, pharma' — omit for the top sectors now]"
allowed-tools: WebFetch, Read, Write, Bash, Agent, mcp__playwright__*
---

# Sector Analysis — rotation + per-sector deep dives

Read `references/reference.md` for the sector KPI map (Varsity sector-analysis module) and the relative-strength method. The per-sector analytical read is done by the **`sector-analyst` agent** (forked, self-contained) — this skill decides *which* sectors to analyze, runs that agent on each, then assembles the rotation grid and the comprehensive writeup.

**Sources for this skill only:** the data spine `lib/prices.py` for index OHLCV (sectoral index RS — primary; index-aware yfinance in one place), NSE (sectoral index data), Moneycontrol (sector pages, index returns) as cross-checks, and `lib/fundamentals.py` / screener.in for stock-level KPIs. The agent uses the same set. Do not use other sites.

## Decide which sectors to analyze

- **User named one or more sectors** → analyze exactly those. Skip the ranking grid (or keep it as light context only).
- **No sector named** → rank the rotation first (Step 1), then deep-dive the **top three** sectors in the current market.

## Step 1 — Rank the rotation (only when no sector was named)

Pull 1-month, 3-month, and 6-month returns (**21 / 63 / 126 trading days** — fixed so runs are comparable) for the NSE sectoral indices plus Nifty 50 as the benchmark. Source order (verified 2026-06): **the data spine `lib/prices.py`** — `prices.history("^NSEI", "1y")` and the sectoral index tickers (map in reference.md; index-aware yfinance under the hood, works in any session, primary), Moneycontrol Nifty JSON `curl 'https://priceapi.moneycontrol.com/pricefeed/notapplicable/inidicesindia/in%3BNSX'` (cross-check, no browser; `;` must be `%3B`), NSE index pages or Moneycontrol HTML via Playwright **real Chrome** (the WebFetch tool is blocked by both, browsers/curl work).

Compute relative strength = sector return − Nifty 50 return for each window. Classify:
- **Leading**: positive RS on both 1M and 3M
- **Improving**: positive 1M, negative 3M (early rotation candidate — flag these prominently, they're the actionable ones)
- **Weakening**: negative 1M, positive 3M
- **Lagging**: negative both

Guards: thin/narrow indices (Media, and anything with < 10 constituents) can classify Leading on noise — keep them in the grid but exclude from "top sectors" and say why. Tie-breaks for the top three: higher 1M RS wins, then 3M. If Nifty itself fell over the window, say explicitly that positive RS may mean "falling less", not rising. **Pick the top three**, prioritizing the actionable **Improving** class, then **Leading**.

## Step 2 — Deep-dive each chosen sector via the agent

For each sector to analyze (the named ones, or the top three), launch the **`sector-analyst` agent** in parallel — one call per sector, passing the sector name (no focus stock here; that mode is for deep-analysis) **and its output path `artifacts/sector-analysis/YYYY-MM-DD/<sector>.md`** (`paths.report_dir("sector-analysis", date)`). Each agent writes its own raw report to that path and returns the structured Sector Read: RS classification, KPI snapshot, tailwinds/headwinds, leaders/laggards, and a sector stance. Synthesize from those files — do not just paste the agent outputs back.

## Output

Render `assets/sector-analysis.html` (bundled with this skill) — the RS grid colored by classification (full grid when ranking was done; just the analyzed sectors otherwise) plus a picks table built from the agents' leaders — and save to `artifacts/sector-analysis/YYYY-MM-DD.html` (`paths.report_path("sector-analysis", date, "html")`). In chat, give the comprehensive read assembled from the agent reports: for each analyzed sector, its stance, the one tailwind and one headwind that matter, and its top pick with a one-line reason; when ranking was done, open with the 2–3 sentence rotation story (what's leading, what's turning, what to avoid). Note data gaps. End with the standard risk note.
