---
name: deep-analysis
description: Full multi-agent investment debate on a single Indian stock — technical analyst, fundamental analyst (reads annual reports and concall transcripts from screener.in), news sentiment, bull vs bear researchers, and a portfolio-manager verdict. Use whenever the user asks to analyze, research, deep-dive, evaluate, or form a view on a specific ticker or company name ("should I buy X?", "what do you think of Tata Motors?"), even if they don't say "deep analysis".
argument-hint: "TICKER (NSE symbol or company name)"
allowed-tools: WebFetch, Read, Write, Bash, Agent, mcp__playwright__*
---

# Deep Stock Analysis — multi-agent debate

Read `references/reference.md` for the fundamental-analysis grounding and the debate protocol. Resolve the argument to an NSE symbol first (screener.in search if ambiguous).

**Sites for this skill only:** screener.in (financials, annual reports, concalls), yfinance + NSE (price), ET via Playwright/curl + Moneycontrol via real-Chrome Playwright or its `priceapi` JSON (news/quotes — WebFetch tool is blocked by both, browsers/curl work). TradingView not scraped (yfinance covers data; optional human chart link only).

## Orchestration

Run the six plugin agents as forked subagents. Phases 1–3 launch in parallel; 4–5 consume their output; 6 decides.

| Phase | Agent | Input |
|---|---|---|
| 1 (parallel) | `technical-analyst` | ticker + cached OHLCV if you already fetched any (saves the agent a fetch) |
| 1 (parallel) | `fundamental-analyst` | ticker — must pull the latest annual report PDF + most recent concall transcript/PPT from the screener.in "Documents" section |
| 1 (parallel) | `news-sentiment` | ticker + company name |
| 2 (parallel) | `bull-researcher` | all three phase-1 reports |
| 2 (parallel) | `bear-researcher` | all three phase-1 reports |
| 3 | `portfolio-manager` | everything — issues verdict: Buy / Accumulate / Hold / Avoid / Exit, with sizing and invalidation level |

Pass each agent only the data it needs, as text — agents are forked and share no context. If any phase-1 agent fails (scrape block, missing documents), continue the debate with the gap explicitly stated; the portfolio-manager must weigh missing evidence as uncertainty, not as neutral.

## Artifact + hook contract

Write the full report to `artifacts/.staging/<TICKER>.md` using `assets/deep-analysis.md` (bundled with this skill). **You (the orchestrator) fill the template's summary placeholders yourself** — CMP, TOP_BULL_POINT (bull's argument 1), TOP_BEAR_POINT (bear's argument 1), KEY_LEVEL (the nearest decision level from the technical read), COMPANY_OVERVIEW (lift the fundamental analyst's "Business overview" block — what the company does, its major verticals/segments and revenue mix, geography, key products, and the moat; so a reader meeting the company here is oriented before the debate), DATA_GAPS (union of all agents' gaps), AGENT_COUNT = 6 — agents only supply their section bodies. When pasting an agent's report into its template section, drop the agent's own `## ...` title line so headings don't double up. The report **must contain a `## Telegram Brief` section** (≤ 10 lines: verdict, one bull point, one bear point, key level, invalidation). The plugin's Stop hook archives the file to `artifacts/YYYY-MM-DD/<TICKER>.md` and sends that section to Telegram — do not send Telegram messages yourself and do not move the file.

If an active `strategy-manager` spec exists in `artifacts/strategies/`, note whether this ticker fits its `universe` and whether the current regime matches the strategy's `regime_required` — a great company in the wrong regime for the active system is still a "not now" for that book.

In chat, give the verdict, the two strongest opposing arguments, and the invalidation level — not the whole report. End with the standard risk note.
