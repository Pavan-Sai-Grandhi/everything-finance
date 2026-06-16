---
name: deep-analysis
description: Full multi-agent investment debate on a single Indian stock — technical analyst, fundamental analyst (reads annual reports and concall transcripts from screener.in), news sentiment, sector analyst (where the stock sits in its sector), bull vs bear researchers, and a portfolio-manager verdict, synthesized into one readable report. Use whenever the user asks to analyze, research, deep-dive, evaluate, or form a view on a specific ticker or company name ("should I buy X?", "what do you think of Tata Motors?"), even if they don't say "deep analysis".
argument-hint: "TICKER (NSE symbol or company name)"
allowed-tools: WebFetch, Read, Write, Bash, Agent, mcp__playwright__*
---

# Deep Stock Analysis — multi-agent debate

Read `references/reference.md` for the fundamental-analysis grounding and the debate protocol. Resolve the argument to an NSE symbol first (screener.in search if ambiguous).

**Sites for this skill only:** screener.in (financials, annual reports, concalls), yfinance + NSE (price), ET via Playwright/curl + Moneycontrol via real-Chrome Playwright or its `priceapi` JSON (news/quotes — WebFetch tool is blocked by both, browsers/curl work). TradingView not scraped (yfinance covers data; optional human chart link only).

## Orchestration

Run the seven plugin agents as forked subagents. Phases 1–3 launch in parallel; 4–5 consume their output; 6 decides.

| Phase | Agent | Input |
|---|---|---|
| 1 (parallel) | `technical-analyst` | ticker + cached OHLCV if you already fetched any (saves the agent a fetch) |
| 1 (parallel) | `fundamental-analyst` | ticker — must pull the latest annual report PDF + most recent concall transcript/PPT from the screener.in "Documents" section |
| 1 (parallel) | `news-sentiment` | ticker + company name |
| 1 (parallel) | `sector-analyst` | ticker + company name **as the focus stock**, so it positions the stock inside its sector (it maps the company → sector itself) |
| 2 (parallel) | `bull-researcher` | all four phase-1 reports |
| 2 (parallel) | `bear-researcher` | all four phase-1 reports |
| 3 | `portfolio-manager` | everything — issues verdict: Buy / Accumulate / Hold / Avoid / Exit, with sizing and invalidation level |

Pass each agent only the data it needs, as text — agents are forked and share no context. **Give each agent its output path** as part of the input: `artifacts/.staging/<TICKER>/agents/<role>.md` — one file per agent: `technical.md`, `fundamental.md`, `news.md`, `sector.md`, `bull.md`, `bear.md`, `verdict.md`. Each agent writes its **own raw report** to that path and returns the same text. If any phase-1 agent fails (scrape block, missing documents), continue the debate with the gap explicitly stated; the portfolio-manager must weigh missing evidence as uncertainty, not as neutral.

## Synthesize from the work papers

The work papers above are the agents' own output — you do **not** write them. The comprehensive report is built **from** them (the returned text, or re-read the staged files), not by pasting them.

Write the synthesized report to `artifacts/.staging/<TICKER>.md` using `assets/deep-analysis.md` (bundled with this skill). The template is a **readable synthesis** — you (the orchestrator) author every section in plain prose from the work papers, not by dumping agent output:

- **Summary placeholders you fill yourself:** CMP, COMPANY_NAME_SUFFIX (" · <Company>" or empty), ONE_LINE_THESIS, CALL_NARRATIVE, the verdict table (ENTRY_SL_TARGET/RRR/ALLOC_CAP/INVALIDATION/REVIEW_TRIGGER from the portfolio-manager), the five-lens At-a-Glance table (each lens's stance + one-line read), COMPANY_OVERVIEW (the fundamental analyst's "Business overview" block — what the company does, segments & revenue mix, geography, products, moat), TOP_BULL_POINT (bull's argument 1), TOP_BEAR_POINT (bear's argument 1), SECTOR_STANCE_ONELINE, KEY_LEVEL (nearest decision level from the technical read), DATA_GAPS (union of all agents' gaps), AGENT_COUNT = 7.
- **Synthesized sections:** BULL_SYNTHESIS / BEAR_SYNTHESIS (distil each side's 2–3 strongest evidence-tied points), DECISIVE_POINTS (what the PM kept/discarded + dissent worth keeping), SECTOR_CONTEXT (the sector read + where the stock sits in its sector), and the three Evidence-by-Lens blocks (condense each agent report to its load-bearing facts and levels — keep the numbers and cites, drop the boilerplate).

The report **must contain a `## Telegram Brief` section** (≤ 10 lines: verdict, one bull point, one bear point, sector one-liner, key level, invalidation). The plugin's Stop hook archives `artifacts/.staging/<TICKER>.md` → `artifacts/YYYY-MM-DD/<TICKER>-deep-analysis.md`, moves the work papers to `artifacts/YYYY-MM-DD/<TICKER>-deep-analysis/agents/`, and sends the brief to Telegram — do not send Telegram messages yourself and do not move the files.

In chat, give the verdict, the two strongest opposing arguments, the sector stance, and the invalidation level — not the whole report. End with the standard risk note.
