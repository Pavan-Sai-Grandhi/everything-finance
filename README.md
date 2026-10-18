# everything-finance

A Claude Code plugin for one person's India-focused money workflow: swing trading the Nifty 500, multi-agent deep-dives on single stocks, designing and backtesting rule-based strategies, tracking live broker positions against the rationale that opened them, sectors, mutual funds, insurance, budgeting, filings and whole-picture net worth.

Four layers, each owning one kind of thing:

- **`RULES.md`**: the runtime contract every session and agent receives (data integrity, the approved sources, output and trading discipline).
- **`methods/`**: the knowledge the skills apply, one file per topic, every rule cited to its source (Zerodha Varsity, Damodaran, Money Purse, SOIC, …). `methods/SOURCES.md` is the registry; a new source is merged into the topics it covers.
- **`skills/` and `agents/`**: workflow only — which tools to call in which order, and the shape of what comes back.
- **`finance/`**: every fetch and calculation, reached only through the MCP tools.

`CLAUDE.md` is the guide for developing the plugin. It ships in two formats from one tree: Claude Code's native layout (`.claude-plugin/`, `.mcp.json`) and the portable [Agent Plugins 1.0.0](https://agent-plugins.org/specification) standard (`plugin.json`, `mcp.json`).

> Personal research tool. Nothing it outputs is investment advice.

## Install

```bash
claude plugin install <path-to>/everything-finance
# or, via the bundled marketplace:
#   /plugin marketplace add <path-to>/everything-finance
#   /plugin install everything-finance@everything-finance
```

Credentials live in a `.env`, never in the repo. Copy [`.env.example`](.env.example) to a `.env` the plugin loads — next to the plugin (`$PLUGIN_ROOT/.env`) or in the client's persistent dir (`$PLUGIN_DATA/.env`); `bin/load-env.sh` takes the first that exists. Only the Telegram pair is needed for briefs; every other secret is optional and its absence degrades to a labelled gap:

```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## MCP servers

Eight servers ([`.mcp.json`](.mcp.json)) in two classes with deliberately opposite rules.

**`finance-market`, `finance-company`, `finance-funds`, `finance-personal`, `finance-workflow`** — local, launched by `bin/finance-mcp.sh <name>`, together the only door into the library: market and company data from eight approved sources (TradingView, Yahoo, Tickertape, NSE, screener.in, AMFI, Google News RSS, Damodaran's country-risk dataset), the compute engines on them, computations over your own files, and the plugin's own run machinery (alerts, the strategy library, report bundles). `RULES.md` → *The servers* lists what each holds. They need no configuration: the launcher uses your `python3` when it already has the MCP SDK, otherwise bootstraps a venv under the plugin's data directory once.

**`kite`** (Zerodha), **`upstox`**, **`indmoney`** — optional, read-only, personal. They answer only *what you own and what it is worth* and never feed a view (`RULES.md` rule 3). Connect whichever you use. IndMoney covers every asset class with per-position value and P&L, but has no XIRR, no cost for stocks held through a linked broker, and no order history, so exact entry fills come from a broker MCP. All three run through `bin/mcp-bridge.sh`, an `mcp-remote` wrapper that points every Claude session at one shared OAuth store (`~/.mcp-auth`): **log in once and every session is logged in**, on one client registration and one token per broker. One process at a time refreshes the token, ten minutes before it expires, so sessions never race on a single-use refresh token. A login, when one is needed, opens a single tab that stays valid for 15 minutes even after the session that opened it gives up; proxies themselves never open a browser. Set `MCP_TIMEOUT=120000` in the project's `.claude/settings.local.json` `env` so a login finished within two minutes connects in the same attempt; otherwise reconnect the server (`/mcp`) after logging in. `finance/tests/test_mcp_bridge.py` covers it; `EF_BRIDGE_E2E=1` adds end-to-end scenarios against a stub broker.

Every tool returns the same envelope `{ok, source, fetched_at, data, gaps}`, so a blocked source is a labelled gap the report names rather than a crash. Bulk results (holdings, NAV series, candles, news) spill to disk and the tool returns a summary plus the path, so a 278-row portfolio never lands in a context window.

## Skills

| Skill | What it does |
|---|---|
| `/market-analysis` | The plugin's market-of-record: trend and posture, real stock-level breadth, VIX percentile, cap-tier valuation percentiles against each index's own 10-year history, FII/DII flows, macro, sector leadership. Persists one dated artifact a day — every other skill reads that instead of forming its own view |
| `/discover` | Find candidates — trade or invest — across **stocks, funds and sectors**: deterministic screen (universe → regime-fit spec → shortlist) then per-item judgment. `stocks --trade` builds entry/SL/target/size signals off a validated strategy and persists a trade-idea for `/trade-tracker`; `stocks --invest` ranks a quality universe and deep-dives the top names; `funds --invest` scans a SEBI category; `sectors --invest` ranks the rotation. No hardcoded default — it asks `/strategy-manager pick` or stands aside |
| `/deep-analysis TICKER [--quick\|--deep\|--fundamentals]` | Multi-agent debate at four modes — `quick` (one local structured-data review, no deck), `standard` (four lenses + one contest pass and verdict), `deep` (six lenses, up to 3 rounds), `fundamentals` (financials + management + valuation, no debate). Each lens is a leg skill run in a profile agent, reading primary documents fetched once by `get_documents`; the `portfolio-manager` issues the verdict. The deck and work papers are archived together, and sent to Telegram only if you ask |
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
| `/financial-analysis TICKER` | The seven-check due-diligence scorecard plus a standalone Company Overview — ROE DuPont'd, ROCE vs cost of capital, the five-year margin trend, debt and interest cover, whether cash follows profit, promoter holding and pledge — with the annual report and latest concall read directly and cited by page |
| `/technical-analysis TICKER` | The chart read on one ticker: Dow trend stage, the S/R map with touch-count evidence, the active pattern in its location context, the volume signature, RSI/MACD as confirmation only, and the two levels that invalidate a bull or a bear thesis |
| `/news-scan TICKER` | ~60 days of press, exchange announcements and analyst commentary scored to a −2…+2 sentiment with dated, sourced evidence — hard fact separated from narrative, the recurring storyline named, and the filing the coverage missed |

## Agents

**Profile runners** carry no method: each invokes the skill named in its input and returns that skill's digest. They differ only in reach. `terminal-analyst` has the decision-data servers and the personal computations (`financial-analysis`, `valuation-analysis`, `technical-analysis`, `sector-analysis`, `portfolio-review`); `field-analyst` has the web and one company's disclosures (`management-analysis`, `news-scan`); `desk-analyst` has no network, only files on disk and the personal computations (`insurance-advisor`, `budget-tracker`).

**Debate roles**: `debate-researcher` argues one side (`side: bull` or `bear`) per round in `deep`, `contest-researcher` does both sides in one pass in `standard`, `portfolio-manager` issues the verdict, and `report-writer` authors the deck projection.

## Hooks

`hooks/hook.sh` is the one launcher:

- **SessionStart** prints today's India date, the session id report publication uses, the plugin root, and `RULES.md`.
- **SubagentStart** hands `RULES.md` to the plugin's own agents.
- **Stop** archives any ready report bundle from this session to `artifacts/stocks/<TICKER>/<date>/runs/<run-id>/` and sends it to Telegram only if you asked when the run started.

## Tests

```bash
./bin/test.sh          # every finance/tests/test_*.py, summed; VERBOSE=1 to dump a failing file
python3 -m finance.mcp.smoke_test --quick    # the live servers, against their real sources
```

The suite is offline: standalone scripts over `finance/tests/harness.py`, each ending `N passed, M failed`, with artifacts pointed at a temporary directory. It also checks the plugin's own wiring: every tool a skill calls is granted, every `methods/` pointer resolves, and every source a method cites is registered.

## Artifacts

Everything lands under `./artifacts/` of the directory you run Claude in (or `$EVERYTHING_FINANCE_ARTIFACTS`), laid out by `finance/paths.py`: dated output (`stocks/<TICKER>/<date>/`, `funds/<SCHEME>/<date>/`, `<skill>/<date>.<ext>`), durable state (`state/strategies/`, `state/trades/`, `state/alerts/`, `state/sectors/`, `state/watchlist.json`) and disposable (`cache/`, `tmp/`). Report decks render from a `report.json` projection through `render_report`, with templates and worked fixtures in `finance/report/`.

## Deliberately out of scope

Scheduled crons (run them outside the plugin) and any **order execution** — `/trade-tracker` reads positions and recommends exits, but you place every order yourself; the broker MCPs are read-only.
