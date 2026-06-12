# everything-finance — personal India-focused financial intelligence plugin

A Claude Code plugin for one person's complete money workflow: swing trading the Nifty 500, deep-diving single stocks with a multi-agent debate, designing rule-based strategies from your own reference articles, tracking live broker positions against their rationale, tracking sectors, researching mutual funds, auditing insurance cover, enforcing budget discipline, and watching exchange filings. Most skills carry a `references/reference.md` distilled from [Zerodha Varsity](https://zerodha.com/varsity/); the strategy engine uses Varsity's *system* discipline (completeness, expectancy, risk sizing, regime gating) but takes its trade logic from reference articles you supply.

> Personal research tool. Nothing this plugin outputs is investment advice.

## Install

```bash
# from a local marketplace / direct path
claude plugin install <path-to>/everything-finance
# or, via the bundled marketplace: /plugin marketplace add <path-to>/everything-finance then
#   /plugin install everything-finance@everything-finance
```

Create `~/.claude/.env` (never committed anywhere):

```bash
TELEGRAM_BOT_TOKEN=...        # for post-analysis Telegram briefs
TELEGRAM_CHAT_ID=...
SCREENER_SESSION_ID=...       # optional, screener.in sessionid cookie (saved screens)
SCREENER_CSRF_TOKEN=...       # optional, screener.in csrftoken cookie
```

The plugin registers three MCP servers:

- **Playwright** (`npx @playwright/mcp@latest`, **real Chrome channel** — needed to beat the Akamai walls on Moneycontrol/NSE) for JS-heavy/authenticated pages.
- **Kite** (Zerodha, `mcp-remote https://mcp.kite.trade/mcp`) and **Upstox** (`mcp-remote https://mcp.upstox.com/mcp`) — read-only broker access for `/trade-tracker`. Both are hosted and OAuth-gated: log in through the MCP (Kite per session, Upstox once per day) before tracking; neither can place orders. You only need the broker you actually use.

Cheap paths are preferred per the access matrix in [CLAUDE.md](CLAUDE.md): yfinance for OHLCV, Moneycontrol's `priceapi` JSON and the BSE/mfapi JSON APIs over plain curl, screener.in with auth cookies. WebFetch handles the static, non-blocking pages; Claude in Chrome is the CAPTCHA fallback. (TradingView is referenced only as a human-facing chart link — all computed data comes from yfinance.)

## Skills

| Skill | What it does |
|---|---|
| `/swing-trading` | Screen the Nifty 500 (screener.in fundamentals gate + technical rules) → swing candidates with entry / SL / target; on your "yes" persists a trade-idea artifact for `/trade-tracker` |
| `/deep-analysis TICKER` | Multi-agent debate: technical, fundamental (reads annual reports + concalls, grades management integrity & skill, computes a story-driven DCF intrinsic value), news, bull vs bear, portfolio-manager verdict. Artifact auto-archived + Telegram brief via Stop hook |
| `/sector-pulse` | Sector rotation snapshot from NSE sectoral indices + top picks per leading sector |
| `/mf-research` | Mutual fund research: NAV history, rolling returns, category comparison, fund quality verdict |
| `/insurance-check` | Life + health coverage adequacy vs need, gap list, action items |
| `/budget-tracker` | Parse bank/CC statements (PDF/CSV), categorize, compare against the Monthly Budget Planning framework, discipline report |
| `/filings-watch TICKER` | NSE + BSE announcements, corporate actions, shareholding pattern changes |
| `/daily-brief` | Morning one-pager: indices, sector tone, watchlist filings, open-position health — Telegram-ready |
| `/portfolio-review` | Holdings audit: exit signals, allocation drift, risk concentration |
| `/backtest` | Validate swing setups on historical NSE data (bundled pandas backtester — expectancy, profit factor, drawdown vs buy-and-hold) |
| `/strategy-manager` | Full strategy lifecycle: **generate** a complete rule-based system from a reference article you supply → **validate** it by backtest and mark it active when it passes → **pick** the active strategy that fits the current regime → **optimize** or retire strategies from live trade outcomes fed back by `/trade-tracker` |
| `/trade-tracker` | Connect Zerodha/Upstox (read-only MCP), match each open position to its rationale (a swing-trading idea, deep-analysis, strategy spec, or one you type), and re-validate the thesis — stop / target / time stop / broken setup / regime change → hold or early-exit call |
| `/dcf-valuation TICKER` | Story-driven DCF (Damodaran FCFF): project revenue growth + operating margin, fund growth via the sales-to-capital ratio, discount FCFF at WACC, add a disciplined terminal value → intrinsic value/share with margin of safety, a WACC×terminal-growth sensitivity grid, and reality-check flags. Bundled offline-tested engine; every input must be sourced |
| `/management-quality TICKER` | Management integrity (a hard gate) + skill grade: remuneration vs profit, related-party transactions, criminal/regulatory record, media-savvy, CFO/auditor churn & fees, owning mistakes, pledging — then qualification/experience, mindset, capital allocation, succession |

## Agents (`agents/`, all `context: fork`)

`technical-analyst`, `fundamental-analyst`, `news-sentiment`, `bull-researcher`, `bear-researcher`, `portfolio-manager` — orchestrated by `/deep-analysis`, reusable individually.

## Hooks

- **Stop → `post-deep-analysis.sh`**: moves staged reports to `artifacts/YYYY-MM-DD/TICKER.md`, sends the Telegram brief.
- **SessionStart → `session-context.sh`**: injects today's date + market open/closed status.

## Templates

Bundled per skill in `skills/<name>/assets/` — HTML where visuals help (signal report, budget dashboard, sector heatmap, fund comparison), markdown for text-first outputs (deep-analysis artifact, daily brief, Telegram format).

## Artifacts

Everything a skill produces lands under `./artifacts/` of the directory you run Claude in: `artifacts/YYYY-MM-DD/<report>` for dated outputs, `artifacts/.cache/` for reusable data downloads, `artifacts/strategies/<name>.yml` for strategy specs, and `artifacts/trades/<SYMBOL>-<date>.yml` for trade ideas that `/trade-tracker` monitors.

## Deliberately out of scope

Scheduled crons (run them outside the plugin) and any **order execution** — `/trade-tracker` reads broker positions and recommends exits, but you place every order yourself; the broker MCPs are read-only.
