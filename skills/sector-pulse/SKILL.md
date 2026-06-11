---
name: sector-pulse
description: Sector rotation snapshot for Indian markets — rank NSE sectoral indices by relative strength, identify which sectors are leading/lagging, and surface top stock picks within the leaders using sector-specific KPIs. Use whenever the user asks which sectors are hot, about sector rotation, where money is flowing, "which sector should I look at", or wants sector-level context before picking stocks.
argument-hint: "[optional: specific sector to deep-dive, e.g. 'banking']"
allowed-tools: WebFetch, Read, Write, Bash, mcp__playwright__*
---

# Sector Pulse — rotation + top picks

Read `references/reference.md` for the sector KPI map (Varsity sector-analysis module) and the relative-strength method.

**Sites for this skill only:** NSE (sectoral index data), Moneycontrol (sector pages, index returns), screener.in (stock-level KPIs within a sector). Do not use other sites.

## Step 1 — Rank the rotation

Pull 1-month, 3-month, and 6-month returns (**21 / 63 / 126 trading days** — fixed so runs are comparable) for the NSE sectoral indices plus Nifty 50 as the benchmark. Source order (verified 2026-06): **yfinance index tickers via Python** (map in reference.md — works in any session, primary), Moneycontrol Nifty JSON `curl 'https://priceapi.moneycontrol.com/pricefeed/notapplicable/inidicesindia/in%3BNSX'` (cross-check, no browser; `;` must be `%3B`), NSE index pages or Moneycontrol HTML via Playwright **real Chrome** (the WebFetch tool is blocked by Moneycontrol and headless chromium hits its 403 wall — real Chrome works).

Compute relative strength = sector return − Nifty 50 return for each window. Classify:
- **Leading**: positive RS on both 1M and 3M
- **Improving**: positive 1M, negative 3M (early rotation candidate — flag these prominently, they're the actionable ones)
- **Weakening**: negative 1M, positive 3M
- **Lagging**: negative both

Guards: thin/narrow indices (Media, and anything with < 10 constituents) can classify Leading on noise — keep them in the grid but exclude from "top sectors" and say why. Tie-breaks for the top 2–3: higher 1M RS wins, then 3M. If Nifty itself fell over the window, say explicitly that positive RS may mean "falling less", not rising.

## Step 2 — Top picks in leading/improving sectors

For the top 2–3 sectors, pick 3 candidate stocks each from screener.in's industry directory at `https://www.screener.in/market/` (works unauthenticated via WebFetch; listing tables carry CMP/P/E/ROCE/growth). Note: the deep sector KPIs in reference.md (NIM/GNPA, EBITDA/tonne) need per-company pages — fetch those only for the shortlisted 3 per sector; if skipped for time, rank on listing-level ratios and state that as a gap. Add proximity to a technical setup (price vs 50-EMA, via yfinance). One line of reasoning per pick.

## Output

Render `assets/sector-heatmap.html` (bundled with this skill) (RS grid colored by classification + picks table), save to `artifacts/YYYY-MM-DD/sector-pulse.html`, and summarize the rotation story in chat in 4–6 sentences: what's leading, what's turning, what to avoid. Note data gaps. End with the standard risk note.

If the user named a sector, skip the ranking summary depth and go deep on that sector instead: KPI table for its top 6–8 stocks, sector tailwinds/headwinds from the KPI trends.
