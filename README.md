# everything-finance

A Claude Code plugin for one person's India-focused money workflow: swing trading the Nifty 500, multi-agent deep-dives on single stocks, designing and backtesting rule-based strategies, tracking live broker positions against the rationale that opened them, sectors, mutual funds, insurance, budgeting, filings and whole-picture net worth.

Most skills carry a `references/reference.md` distilled from [Zerodha Varsity](https://zerodha.com/varsity/). The strategy engine takes Varsity's *system* discipline — completeness, expectancy, risk sizing, regime gating — but its trade logic from reference articles you supply.

The rules every skill runs under — data integrity, the personal-vs-decision source boundary, artifact paths, output and trading discipline — live in [CLAUDE.md](CLAUDE.md). This file is the map: what is here, how to install it, how to test it.

It ships in two formats from one tree: Claude Code's native layout (`.claude-plugin/`, `.mcp.json`) and the portable [Agent Plugins 1.0.0](https://agent-plugins.org/specification) standard (`plugin.json`, `mcp.json`) that Codex, Cursor, Copilot, VS Code and others read. The skills and MCP servers are shared; only the manifests differ.

> Personal research tool. Nothing it outputs is investment advice.

## Install

```bash
claude plugin install <path-to>/everything-finance
# or, via the bundled marketplace:
#   /plugin marketplace add <path-to>/everything-finance
#   /plugin install everything-finance@everything-finance
```

Credentials live in a `.env`, never in the repo. Copy [`.env.example`](.env.example) to a `.env` the plugin loads — next to the plugin (`$PLUGIN_ROOT/.env`) or in the client's persistent dir (`$PLUGIN_DATA/.env`); `bin/load-env.sh` takes the first that exists. [CLAUDE.md](CLAUDE.md) → *Secrets* has the full list. Only the Telegram pair is needed for briefs; every other secret is optional and its absence degrades to a labelled gap:

```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## MCP servers

Seven servers ([`.mcp.json`](.mcp.json)) in two classes with deliberately opposite rules.

**`finance-market` (17 tools), `finance-company` (11), `finance-funds` (6), `finance-personal` (1)** — local, all four launched by `bin/finance-mcp.sh <market|company|funds|personal>`, together the only door to every number the plugin reasons about. 35 tools over seven verified sources (TradingView, Yahoo, Tickertape, NSE, screener.in, AMFI, Google News RSS) plus the compute engines that run on them; no ad-hoc `curl`, no `WebFetch` at a data site, no browser automation anywhere. They need no configuration: the launcher uses your `python3` when it already has the MCP SDK, otherwise bootstraps a venv under the plugin's data directory once.

**`kite`** (Zerodha), **`upstox`**, **`indmoney`** — optional, read-only, personal. They answer only *what you own and what it is worth* and never feed a view (CLAUDE.md rule 3). Connect whichever you use: IndMoney is the broadest — every asset class, per-position value and P&L (no XIRR, and no cost for stocks held through a linked broker) — but carries no order history, so exact entry fills come from a broker MCP. All three run through `bin/mcp-bridge.sh`, an `mcp-remote` wrapper that points every Claude session at one shared OAuth store (`~/.mcp-auth`): **log in once and every session is logged in**, on one client registration and one token per broker. `finance/tests/test_mcp_bridge.py` covers it; `EF_BRIDGE_E2E=1` adds end-to-end scenarios against a stub broker.

Every tool returns the same envelope `{ok, source, fetched_at, data, gaps}`, so a blocked source is a labelled gap the report names rather than a crash. Bulk results (holdings, NAV series, candles, news) spill to disk and the tool returns a summary plus the path, so a 278-row portfolio never lands in a context window.

## Skills

| Skill | What it does |
|---|---|
| `/market-analysis` | The plugin's market-of-record: trend and posture, real stock-level breadth, VIX percentile, cap-tier valuation percentiles against each index's own 10-year history, FII/DII flows, macro, sector leadership. Persists one dated artifact a day — every other skill reads that instead of forming its own view |
| `/discover` | Find candidates — trade or invest — across **stocks, funds and sectors**: deterministic screen (universe → regime-fit spec → shortlist) then per-item judgment. `stocks --trade` builds entry/SL/target/size signals off a validated strategy and persists a trade-idea for `/trade-tracker`; `stocks --invest` ranks a quality universe and deep-dives the top names; `funds --invest` scans a SEBI category; `sectors --invest` ranks the rotation. No hardcoded default — it asks `/strategy-manager pick` or stands aside |
| `/deep-analysis TICKER [--quick\|--deep\|--fundamentals]` | Multi-agent debate at four modes — `quick` (one local structured-data review, no deck), `standard` (four lenses + one contest pass and verdict), `deep` (six lenses, up to 3 rounds), `fundamentals` (financials + management + valuation, no debate). Each lens is a leg skill run in a profile agent, over primary documents warmed once by `get_documents`; the `portfolio-manager` issues the verdict. Report and work papers archived as one immutable bundle; optional authorized Telegram delivery |
| `/sector-analysis SECTOR` | Deep-dive one named sector — RS vs Nifty from the shared sector screen, sourced KPIs, tailwinds/headwinds, leaders and laggards, and where a focus stock sits. With no sector it hands off to `/discover sectors`, which ranks the rotation. Seeds the shared monthly sector cache `/deep-analysis` reuses |
| `/mf-analysis FUND` | Mutual funds, two pillars: past performance recomputed from NAV history (rolling returns, drawdown, Sortino) and forward quality (look-through portfolio valuation, style + drift, AMC/manager trust), for named funds or the funds you hold. Picking a fund within a category is `/discover funds` |
| `/insurance-advisor` | Term/health/vehicle — advise & compare (shortlist 2), audit existing cover, or answer questions on a policy you hold |
| `/budget-tracker` | Parse bank/CC statements (PDF/CSV), categorize against a durable merchant memory, detect recurring spend, compare against the Monthly Budget Planning framework |
| `/filings-watch TICKER` | NSE announcements, corporate actions, shareholding pattern and promoter-pledge changes, classified by materiality |
| `/daily-brief` | Morning one-pager: indices, market-moving news, sector tone, the open-alert inbox and actions due, a capped opportunities shortlist, watchlist filings & news, open-position health — Telegram-ready. Surfaces and recommends; never auto-runs a skill or places an order |
| `/alert-manager` | The inbox for alerts the other skills raise (stop levels, act-on filings, thesis rechecks, vetted opportunities): list, add, dismiss, snooze, sweep expired |
| `/portfolio-review` | Cross-broker holdings audit: P&L-driven laggards (XIRR where a source supplies it), allocation and concentration across asset class / cap / AMC / style / sector, exit-trim-fix calls and rebalancing moves in ₹ |
| `/wealth-manager [--snapshot\|--full-review]` | Total net worth across every IndMoney asset class, then the three personal-finance spokes (portfolio-review, insurance-advisor, budget-tracker) in cheap mode into one financial-health scorecard and a cross-domain action plan. `snapshot` = spine only; `full-review` = full fan-out |
| `/strategy-manager` | Strategy lifecycle: **generate** from a reference article you supply → **validate** on historical NSE data with the strategy-agnostic **Backtesting.py** engine driven by the shared spec interpreter on **TA-Lib** indicators (expectancy, profit factor, drawdown vs buy-and-hold), and mark active only if it passes the gate → **pick** the active strategy fitting the current regime → **optimize** or retire from live outcomes fed back by `/trade-tracker` |
| `/trade-tracker` | Match each open broker position to its rationale (a discover idea, deep-analysis, strategy spec, or one you type) and re-validate the thesis — stop / target / time stop / broken setup / regime change → hold, trim or exit |
| `/valuation-analysis TICKER` | Story-driven FCFF DCF (Damodaran) — project growth and margin, fund it via sales-to-capital, discount at WACC, disciplined terminal value → intrinsic value per share with margin of safety, sensitivity grids and reality-check flags — reconciled with the multiples read (P/E vs peer median and own band, PEG, EV/EBITDA) into one stance weighted by a DCF-confidence grade |
| `/management-analysis TICKER` | Integrity as a hard gate (remuneration vs profit, related-party transactions, criminal/regulatory record, CFO/auditor churn and fees, pledging, owning mistakes, plans promised vs executed, questions dodged on the call) then a skill grade (experience, mindset, capital allocation, succession) |
| `/financial-analysis TICKER` | The Varsity due-diligence scorecard plus a standalone Company Overview — ROE DuPont'd, ROCE vs cost of capital, the five-year margin trend, debt and interest cover, whether cash follows profit, promoter holding and pledge — with the annual report and latest concall read directly and cited by page |
| `/technical-analysis TICKER` | The chart read on one ticker: Dow trend stage, the S/R map with touch-count evidence, the active pattern in its location context, the volume signature, RSI/MACD as confirmation only, and the two levels that invalidate a bull or a bear thesis |
| `/news-scan TICKER` | ~60 days of press, exchange announcements and analyst commentary scored to a −2…+2 sentiment with dated, sourced evidence — hard fact separated from narrative, the recurring storyline named, and the filing the coverage missed |

## Agents (`agents/`, all `context: fork`)

Eight files, in two kinds.

**Tool profiles** — a generic runner that carries no method: it invokes the skill named in its input, ensures the report lands at the given path, and returns only that skill's digest. They differ solely in reach. `terminal-analyst` has the three decision-data servers (`financial-analysis`, `valuation-analysis`, `technical-analysis`, `sector-analysis`, `portfolio-review`); `field-analyst` has the open web (`management-analysis`, `news-scan`); `desk-analyst` has no network at all, only what is already on disk plus deterministic math (`insurance-advisor`, `budget-tracker`).

**Named roles** — the debate, where the role itself is the method: `bull-researcher` and `bear-researcher` argue one side per round, `contest-researcher` does both sides in a single pass for `quick`, and `portfolio-manager` reads every full report and issues the verdict with sizing and invalidation.

## Hooks

- **Stop → `post-deep-analysis.sh`** — recovers ready report bundles belonging to the supplied session id and cwd. Complete bundles archive atomically under `artifacts/stocks/<TICKER>/<date>/runs/<run-id>/`; Telegram delivery requires explicit authorization when preparing the run. Normal completion publishes explicitly, so clients without hooks work too.
- **SessionStart → `session-context.sh`** — injects today's India date and the regular NSE session hours (not a live open/closed or holiday check), plus the session id report publication needs.

## Layout

```
finance/          the one library — transport, spine, paths, deps, caps, plus report
                  publication (publication, report_hook, telegram)
  sources/        one module per data domain (prices market funds fundamentals documents news filings) + the shared tickertape client
  compute/        ta strategy holdings alerts context rolling relative_strength lookthrough
                  fund_scan screen stock_scan sector_scan backtest dcf relval governance
                  trade_check insurance_math wealth allocation
  mcp/            the four servers: declaration + delegation only
  tests/          harness.py + standalone test files
  contracts.md    the artifact handoffs between skills — producer and consumer per field
skills/<name>/    SKILL.md, plus references/ assets/ scripts/ where the skill needs them
agents/  bin/  docs/  hooks/
```

A skill's `scripts/` holds only pure compute over user-supplied files. Everything that fetches — and every compute a skill would otherwise re-implement — is a tool on one of the four servers. See [CLAUDE.md](CLAUDE.md) → *The `finance/` package* for the rules, and [`finance/contracts.md`](finance/contracts.md) for the contracts between skills.

## Tests

```bash
./bin/test.sh          # every test file, summed; VERBOSE=1 to dump a failing file's output
```

Standalone test scripts in `finance/tests/` and beside the skill scripts they cover over the shared `finance/tests/harness.py`. There is no pytest here: each file runs as `python3 <file>`, prints `N passed, M failed`, and exits non-zero on failure, which the runner parses and sums. The runner isolates artifact storage from any inherited personal portfolio path and rejects missing assertion summaries. The suite is offline — fixtures, no network (verified by running it behind a recording proxy: zero outbound requests).

## Artifacts

Everything a skill produces lands under `./artifacts/` of the directory you run Claude in (or `$EVERYTHING_FINANCE_ARTIFACTS`), addressed only through `finance/paths.py`. Three lifecycle tiers: dated output (`stocks/<TICKER>/<date>/`, `funds/<SCHEME>/<date>/`, and skill-first singletons like `daily-brief/<date>.md`), durable state (`state/strategies/`, `state/trades/`, `state/alerts/`, `state/sectors/`, `state/watchlist.json`), and disposable (`cache/`, `tmp/`).

Report decks (`deep-analysis`, `mf-analysis`, `sector-analysis`, `daily-brief`, `wealth-manager`) render from a `report.json` projection through the shared `skills/_report/` renderer. Other templates ship per skill in `skills/<name>/assets/` — HTML for the signal report and budget dashboard, markdown for text-first outputs.

## Deliberately out of scope

Scheduled crons (run them outside the plugin) and any **order execution** — `/trade-tracker` reads positions and recommends exits, but you place every order yourself; the broker MCPs are read-only.
