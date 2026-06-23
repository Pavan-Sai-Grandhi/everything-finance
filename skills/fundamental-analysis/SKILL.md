---
name: fundamental-analysis
description: Fundamentals-only view of one Indian company — fetches the source data once, then runs the numbers (Varsity checklist + company overview), management (integrity gate + skill), and valuation (story-driven DCF with a confidence grade) legs in parallel and merges them into one report. Use when the user wants the fundamental read on a stock without the full bull/bear debate — "are the fundamentals good?", "is X fundamentally sound?", "fundamental analysis of Y". For the full multi-agent debate use deep-analysis instead.
argument-hint: "TICKER (NSE symbol or company name)"
allowed-tools: Read, Write, Bash, Agent
---

# Fundamental Analysis — fetch-once, then three parallel legs

The standalone fundamentals path. The same four agents `deep-analysis` uses for its fundamental block, orchestrated here without the debate. Resolve the argument to an NSE symbol first (screener.in search if ambiguous).

**Refer the earlier run first.** Call `paths.latest_prior("deep-analysis", TICKER)` and `paths.latest_prior("dcf"/"management", TICKER)` — if prior artifacts exist, read them so this run builds on them, and open the merged report with a one-line `prior run: <path> (<date>)` note where the grade or fair value moved.

**Sites for this skill only:** screener.in (financials, annual reports, concalls), yfinance via `lib/prices.py` (CMP), and the WebSearch the management leg does for the criminal/regulatory record. The fetcher uses the data spine (`lib/fundamentals.py`, `lib/prices.py`); do not wander elsewhere.

## Orchestration

1. **Fetch once.** Run `fundamentals-data` (forked) with the ticker and output path `artifacts/tmp/staging/<TICKER>/fundamentals/data-pack.md` (`paths.tmp_dir("staging")`). It writes the sourced data-pack — the single source the next three legs read.
2. **Three legs in parallel**, each forked, each given the **data-pack path** and its own output path under `artifacts/tmp/staging/<TICKER>/agents/`:
   - `financials-analyst` → `financials.md`
   - `management-analyst` → `management.md`
   - `valuation-analyst` → `valuation.md`
   Pass each agent only the data-pack path (they Read it themselves) — agents are forked and share no context. If a leg fails, continue and state the gap; do not let one leg abort the report.
3. **Merge, don't paste.** Author one fundamentals report in plain prose from the three legs: company overview (financials), the checklist scorecard highlights, the management integrity gate + skill grade, and the intrinsic-value range + margin of safety **with its DCF-confidence grade** and the relative cross-check. If the integrity gate is FAIL, that is the headline — overall AVOID regardless of numbers or valuation.

## Persist

Write the merged report to `artifacts/stocks/<TICKER>/YYYY-MM-DD/fundamental-analysis.md` (`paths.stock_dir`). Also persist the discrete leg artifacts into the same run-day folder so the stock's history is unified and `paths.latest_prior` finds them whether they came from here or from deep-analysis: `dcf.md`/`dcf.json` (from the valuation leg's engine run), `management.md` (from the management leg). Move the work papers to `artifacts/stocks/<TICKER>/YYYY-MM-DD/fundamental-analysis/agents/`.

In chat, give the fundamentals verdict, the integrity gate result, the intrinsic-value range + DCF confidence, and the two strongest flags — not the whole report. End with the standard risk note + "Not investment advice — personal research tool."
