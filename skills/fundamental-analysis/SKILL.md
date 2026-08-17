---
name: fundamental-analysis
description: Fundamentals-only view of one Indian company — fetches the source data once, then runs the numbers (Varsity checklist + company overview), management (integrity gate + skill), and valuation (story-driven DCF with a confidence grade) legs in parallel and merges them into one report. Use when the user wants the fundamental read on a stock without the full bull/bear debate — "are the fundamentals good?", "is X fundamentally sound?", "fundamental analysis of Y". For the full multi-agent debate use deep-analysis instead.
argument-hint: "TICKER (NSE symbol or company name)"
allowed-tools: Read, Write, Bash, Agent, mcp__finance-company__*
---

# Fundamental Analysis — fetch-once, then three parallel legs

The standalone fundamentals path. The same four agents `deep-analysis` uses for its fundamental block, orchestrated here without the debate. This skill owns the orchestration and the merge only; the **method** belongs to the legs — each forked agent carries its own (the Varsity checklist, the DCF/relative reconciliation, the integrity gate).

**Sources for this skill only:** `finance-company` `get_company_fundamentals` to resolve the argument to an NSE symbol and confirm the company name — that is the orchestrator's only fetch. Every fundamental number reaches the legs through the data-pack.

**Refer the earlier run first.** Call `paths.latest_prior("deep-analysis", TICKER)` and `paths.latest_prior("dcf"/"management", TICKER)` — if prior artifacts exist, read them so this run builds on them, and open the merged report with a one-line `prior run: <path> (<date>)` note where the grade or fair value moved.

## Orchestration

1. **Fetch once.** Run `fundamentals-data` (forked) with the ticker, output path `artifacts/tmp/staging/<TICKER>/fundamentals/data-pack.md` (`paths.tmp_dir("staging")`), and fetch depth `full`. It writes the sourced data-pack — the single source the next three legs read.
2. **Three legs in parallel**, each forked, each given the **data-pack path** and its own output path under `artifacts/tmp/staging/<TICKER>/agents/`:
   - `financials-analyst` → `financials.md`
   - `management-analyst` → `management.md`
   - `valuation-analyst` → `valuation.md` (pass mode `deep` — this is a full single-stock fundamental read, so the valuation leg loads the full DCF method, not the distilled checklist)
   Pass each agent only the data-pack path (they Read it themselves) — agents are forked and share no context.
3. **Merge, don't paste.** Author one fundamentals report in plain prose from the three legs: company overview and checklist highlights (financials), the integrity gate + skill grade (management), and the valuation leg's **combined stance with its DCF-confidence grade**. If the integrity gate is FAIL, that is the headline — overall AVOID regardless of numbers or valuation.

## Persist

Write the merged report to `artifacts/stocks/<TICKER>/YYYY-MM-DD/fundamental-analysis.md` (`paths.stock_dir`). Also persist the discrete leg artifacts into the same run-day folder so `paths.latest_prior` finds them regardless of which skill produced them: `dcf.md`/`dcf.json` (from the valuation leg's engine run), `management.md` (from the management leg). Then move the staged work papers yourself (`mv`) into `artifacts/stocks/<TICKER>/YYYY-MM-DD/fundamental-analysis/agents/` — no hook archives this skill's run.

In chat, give the fundamentals verdict, the integrity gate result, the intrinsic-value range + DCF confidence, and the two strongest flags — not the whole report.
