# everything-finance

A Claude Code plugin for one person's India-focused money workflow: swing trading the Nifty 500, multi-agent deep-dives on single stocks, designing and backtesting rule-based strategies, tracking live broker positions against the rationale that opened them, sectors, mutual funds, insurance, budgeting, filings and whole-picture net worth.

Most skills carry a `references/reference.md` distilled from [Zerodha Varsity](https://zerodha.com/varsity/). The strategy engine takes Varsity's *system* discipline — completeness, expectancy, risk sizing, regime gating — but its trade logic from reference articles you supply.

The rules every skill runs under — data integrity, the personal-vs-decision source boundary, artifact paths, output and trading discipline — live in [CLAUDE.md](CLAUDE.md). This file is the map: what is here, how to install it, how to test it.

> Personal research tool. Nothing it outputs is investment advice.

## Install

```bash
claude plugin install <path-to>/everything-finance
# or, via the bundled marketplace:
#   /plugin marketplace add <path-to>/everything-finance
#   /plugin install everything-finance@everything-finance
```

Credentials live in `~/.claude/.env`, never in the repo — [CLAUDE.md](CLAUDE.md) → *Secrets* has the full list. Only the Telegram pair is needed for briefs; every other secret is optional and its absence degrades to a labelled gap:

```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## MCP servers

Six servers ([`.mcp.json`](.mcp.json)) in two classes with deliberately opposite rules.

**`finance-market` (12 tools), `finance-company` (7), `finance-funds` (6)** — local, all three launched by `bin/finance-mcp.sh <market|company|funds>`, together the only door to every number the plugin reasons about. 25 tools over seven verified sources (TradingView, Yahoo, screener.in, NSE, Tickertape, AMFI, Google News RSS); no ad-hoc `curl`, no `WebFetch` at a data site, no browser automation anywhere. They need no configuration: the launcher uses your `python3` when it already has the MCP SDK, otherwise bootstraps a venv under the plugin's data directory once. Source rationale and the per-data-point inventory: [`docs/data-sources.md`](docs/data-sources.md).

**`kite`** (Zerodha), **`upstox`**, **`indmoney`** — optional, read-only, personal. They answer only *what you own and what it is worth* and never feed a view (CLAUDE.md rule 3). Connect whichever you use: IndMoney is the broadest — every asset class, per-position P&L and XIRR — but carries no order history, so exact entry fills come from a broker MCP. All three run through `bin/mcp-bridge.sh`, an `mcp-remote` wrapper that gives each Claude session its own OAuth config dir (`~/.mcp-auth-sessions/<pid>`) so concurrent sessions register on independent callback ports instead of colliding on one; it reaps the dirs of exited sessions and any orphaned bridge. The cost of that isolation is authenticating once per session.

Every tool returns the same envelope `{ok, source, fetched_at, data, gaps}`, so a blocked source is a labelled gap the report names rather than a crash. Bulk results (holdings, NAV series, candles, news) spill to disk and the tool returns a summary plus the path, so a 278-row portfolio never lands in a context window.

## Skills

| Skill | What it does |
|---|---|
| `/market-analysis` | The plugin's market-of-record: trend and posture, real stock-level breadth, VIX percentile, cap-tier valuation percentiles against each index's own 10-year history, FII/DII flows, macro, sector leadership. Persists one dated artifact a day — every other skill reads that instead of forming its own view |
| `/find-trade` | Run a chosen, validated strategy against the Nifty 500 — screen the universe (screener.in fundamentals + TradingView/local technical cut), build entry / SL / target / size signals; on your "yes" persists a trade-idea artifact for `/trade-tracker`. Strategy-agnostic: you name a strategy or it asks `/strategy-manager pick`; no hardcoded default |
| `/deep-analysis TICKER [--quick\|--deep]` | Multi-agent debate at three depths — `quick` (3 lenses + one contest pass), `standard` (six lenses, a 2nd debate round only on genuine divergence), `deep` (six lenses, up to 3 rounds). Lenses: technical, financials, management (integrity gate + skill), valuation (DCF + relative multiples, weighted by DCF confidence), news, sector — fed by a fetch-once data-pack; portfolio-manager verdict. Report archived with its agent work papers + Telegram brief via the Stop hook |
| `/fundamental-analysis TICKER` | The same fetch-once pack without the debate: financials (Varsity checklist + overview), management, and valuation legs merged into one report |
| `/sector-analysis [sector]` | Deep-dive the sectors you name, or rank the NSE sectoral indices and deep-dive the top three — RS, sector KPIs, tailwinds/headwinds, top picks. Seeds the shared monthly sector cache `/deep-analysis` reuses |
| `/mf-analysis` | Mutual funds, two pillars: past performance recomputed from NAV history (rolling returns, drawdown, Sortino) and forward quality (look-through portfolio valuation, style + drift, AMC/manager trust). Scans a whole SEBI sub-category down to a gated shortlist, or reviews the funds you hold |
| `/insurance-advisor` | Term/health/vehicle — advise & compare (shortlist 2), audit existing cover, or answer questions on a policy you hold |
| `/budget-tracker` | Parse bank/CC statements (PDF/CSV), categorize against a durable merchant memory, detect recurring spend, compare against the Monthly Budget Planning framework |
| `/filings-watch TICKER` | NSE announcements, corporate actions, shareholding pattern and promoter-pledge changes, classified by materiality |
| `/daily-brief` | Morning one-pager: indices, market-moving news, sector tone, the open-alert inbox and actions due, a capped opportunities shortlist, watchlist filings & news, open-position health — Telegram-ready. Surfaces and recommends; never auto-runs a skill or places an order |
| `/alert-manager` | The inbox for alerts the other skills raise (stop levels, act-on filings, thesis rechecks, vetted opportunities): list, add, dismiss, snooze, sweep expired |
| `/portfolio-review` | Cross-broker holdings audit: XIRR-driven laggards, allocation and concentration across asset class / cap / AMC / style / sector, exit-trim-fix calls and rebalancing moves in ₹ |
| `/wealth-manager [--snapshot\|--full-review]` | Total net worth across every IndMoney asset class, then the three personal-finance spokes (portfolio-review, insurance-advisor, budget-tracker) in cheap mode into one financial-health scorecard and a cross-domain action plan. `snapshot` = spine only; `full-review` = full fan-out |
| `/backtest` | Validate a strategy spec on historical NSE data — the strategy-agnostic **Backtesting.py** engine driven by the shared spec interpreter on **TA-Lib** indicators: expectancy, profit factor, drawdown vs buy-and-hold |
| `/strategy-manager` | Strategy lifecycle: **generate** from a reference article you supply → **validate** by backtest and mark active → **pick** the active strategy fitting the current regime → **optimize** or retire from live outcomes fed back by `/trade-tracker` |
| `/trade-tracker` | Match each open broker position to its rationale (a find-trade idea, deep-analysis, strategy spec, or one you type) and re-validate the thesis — stop / target / time stop / broken setup / regime change → hold, trim or exit |
| `/dcf-valuation TICKER` | Story-driven FCFF DCF (Damodaran): project growth and margin, fund it via sales-to-capital, discount at WACC, disciplined terminal value → intrinsic value per share with margin of safety, a WACC×g sensitivity grid and reality-check flags |
| `/management-quality TICKER` | Integrity as a hard gate (remuneration vs profit, related-party transactions, criminal/regulatory record, CFO/auditor churn and fees, pledging, owning mistakes) then a skill grade (experience, mindset, capital allocation, succession) |

## Agents (`agents/`, all `context: fork`)

`technical-analyst`, `fundamentals-data` (the fetch-once source pack) → `financials-analyst` · `management-analyst` · `valuation-analyst`, `news-sentiment`, `sector-analyst`, `bull-researcher`, `bear-researcher`, `contest-researcher`, `portfolio-manager` — orchestrated by `/deep-analysis` and reusable individually. The four fundamental agents also power `/fundamental-analysis`; `sector-analyst` also powers `/sector-analysis`. `wealth-leg` runs one wealth spoke in cheap mode and returns only its digest.

## Hooks

- **Stop → `post-deep-analysis.sh`** — archives the staged report and its agent work papers to `artifacts/stocks/<TICKER>/<date>/`, then sends the Telegram brief. Anchors to the session cwd from the hook's stdin, so it fires regardless of where the hook process starts.
- **SessionStart → `session-context.sh`** — injects today's date and market open/closed status.

## Layout

```
finance/          the one library — transport, spine, paths, deps
  sources/        one module per data domain (prices market funds fundamentals news filings)
  compute/        ta strategy holdings alerts context rolling lookthrough fund_scan screen backtest
  mcp/            the three servers: declaration + delegation only
  tests/          harness.py + 18 standalone test files
  contracts.md    the artifact handoffs between skills — producer and consumer per field
skills/<name>/    SKILL.md, plus references/ assets/ scripts/ where the skill needs them
agents/  bin/  docs/  hooks/
```

A skill's `scripts/` holds only pure compute over user-supplied files. Everything that fetches — and every compute that needs fetched data — is a tool on one of the three servers. See [CLAUDE.md](CLAUDE.md) → *The `finance/` package* for the rules, and [`finance/contracts.md`](finance/contracts.md) for the contracts between skills.

## Tests

```bash
./bin/test.sh          # every test file, summed; VERBOSE=1 to dump a failing file's output
```

28 standalone test scripts (18 in `finance/tests/`, 10 beside the skill scripts they cover) over the shared `finance/tests/harness.py`. There is no pytest here: each file runs as `python3 <file>`, prints `N passed, M failed`, and exits non-zero on failure, which the runner parses and sums. The suite is offline — fixtures, no network.

## Artifacts

Everything a skill produces lands under `./artifacts/` of the directory you run Claude in (or `$EVERYTHING_FINANCE_ARTIFACTS`), addressed only through `finance/paths.py`. Three lifecycle tiers: dated output (`stocks/<TICKER>/<date>/`, `funds/<SCHEME>/<date>/`, and skill-first singletons like `daily-brief/<date>.md`), durable state (`state/strategies/`, `state/trades/`, `state/alerts/`, `state/sectors/`, `state/watchlist.json`), and disposable (`cache/`, `tmp/`).

Report templates ship per skill in `skills/<name>/assets/` — HTML where visuals help (signal report, budget dashboard, sector grid, fund comparison), markdown for text-first outputs.

## Deliberately out of scope

Scheduled crons (run them outside the plugin) and any **order execution** — `/trade-tracker` reads positions and recommends exits, but you place every order yourself; the broker MCPs are read-only.
