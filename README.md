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

The plugin registers four MCP servers:

- **Playwright** (`npx @playwright/mcp@latest`, **real Chrome channel** — needed to beat the Akamai walls on Moneycontrol/NSE) for JS-heavy/authenticated pages.
- **Kite** (Zerodha, `https://mcp.kite.trade/mcp`) and **Upstox** (`https://mcp.upstox.com/mcp`) — read-only broker access for `/trade-tracker`, both hosted and OAuth-gated; neither can place orders. You only need the broker you actually use. They run through `bin/mcp-bridge.sh`, a thin `mcp-remote` wrapper that gives **each Claude session its own OAuth config dir** (`~/.mcp-auth-sessions/<pid>`) so concurrent sessions register on independent callback ports and never collide on a shared one (the EADDRINUSE you'd otherwise hit when a second window connects to the same broker). It self-cleans after exited sessions — dropping their config dirs and reaping any bridge a crash/closed-terminal left orphaned (PPID 1), never a live session's. The trade-off of isolation: you authenticate **per session** (Kite already required this; Upstox is once per session rather than once per day). A reconnect within the same session reuses the stored token.
- **IndMoney** (`https://mcp.indmoney.com/mcp`) — read-only, the **primary** source for live holdings, positions and net worth across all asset classes (with per-position P&L and XIRR), superseding the single-broker equity view. It runs through the same `bin/mcp-bridge.sh` (same per-session isolation and self-healing). OAuth is mobile + OTP + MPIN, read-only by design and revocable from IndMoney settings; the first run pops a browser consent screen. It carries no order/trade history, so exact entry fills still come from the broker MCPs — IndMoney is never used to approximate an entry.

Cheap paths are preferred per the access matrix in [CLAUDE.md](CLAUDE.md): yfinance for OHLCV, Moneycontrol's `priceapi` JSON and the BSE/mfapi JSON APIs over plain curl, screener.in with auth cookies. WebFetch handles the static, non-blocking pages; Claude in Chrome is the CAPTCHA fallback. TradingView's **stock screener** is driven via the Playwright browser for find-trade's technical cut (its chart pages remain a human-facing link); all computed OHLCV still comes from yfinance.

Shared code lives in **`lib/`**: `ta.py` (one definition of every indicator/pattern — TA-Lib-backed — plus the `FEATURES` registry), `strategy.py` (the one spec→signal engine both the live `find-trade` screen and the `backtest` sit on, so they can't drift), `paths.py` (the single artifact-path authority + `latest_prior` prior-run lookup; one-time migration in `migrate_artifacts.py`), `alerts.py` (the alert contract the skills feed and `daily-brief` reads), and `contracts.md` (the data-handoff contracts between skills). See [CLAUDE.md](CLAUDE.md) → *Shared code*.

## Skills

| Skill | What it does |
|---|---|
| `/find-trade` | Run a chosen, validated strategy against the Nifty 500 — screen the universe (screener.in fundamentals + TradingView/local technical cut), build entry / SL / target / size signals; on your "yes" persists a trade-idea artifact for `/trade-tracker`. Strategy-agnostic: names a strategy or asks `/strategy-manager pick`; no hardcoded default |
| `/deep-analysis TICKER [--quick\|--deep]` | Multi-agent debate at three depths — `quick` (3 lenses + a single contest pass), `standard` (default; six lenses, debate escalates a 2nd round only on genuine divergence), `deep` (six lenses, up to 3 rounds; auto-selected for held positions). Lenses: technical, financials, management (integrity gate + skill), valuation (DCF + relative multiples → one combined stance, weighted by DCF confidence), news, sector — fed by a fetch-once data-pack; portfolio-manager verdict. Synthesized into a readable report with the raw agent work papers archived alongside. Artifact auto-archived + Telegram brief via Stop hook |
| `/fundamental-analysis TICKER` | Fundamentals-only view without the debate: the same fetch-once pack → financials (Varsity checklist + overview), management (integrity gate + skill), and valuation (DCF + confidence) legs, merged into one report |
| `/sector-analysis [sector]` | Deep-dive the sector(s) you name, or rank NSE sectoral indices and deep-dive the top three — RS, sector KPIs, tailwinds/headwinds, top picks (runs the `sector-analyst` agent). Seeds the shared monthly sector cache that `/deep-analysis` reuses |
| `/mf-research` | Mutual fund research: NAV history, rolling returns, category comparison, fund quality verdict |
| `/insurance-check` | Life + health coverage adequacy vs need, gap list, action items |
| `/budget-tracker` | Parse bank/CC statements (PDF/CSV), categorize, compare against the Monthly Budget Planning framework, discipline report |
| `/filings-watch TICKER` | NSE + BSE announcements, corporate actions, shareholding pattern changes |
| `/daily-brief` | Morning one-pager: indices, a market-moving news digest, sector tone, the open-alert inbox + actions due, a strictly-capped opportunities shortlist (vetted from the alert inbox + ≤1 labelled news flag), watchlist filings & news, open-position health — Telegram-ready. Surfaces and recommends; never auto-runs a skill or places an order |
| `/alert-manager` | The inbox for the plugin's alerts (stop levels, act-on filings, thesis rechecks due, vetted opportunities) that the other skills raise: list, add a manual watch-item, dismiss, snooze, or sweep expired. `/daily-brief` reads these every morning |
| `/portfolio-review` | Holdings audit: exit signals, allocation drift, risk concentration |
| `/backtest` | Validate a strategy spec on historical NSE data (strategy-agnostic **Backtesting.py** engine driven by the shared `lib/strategy.py` interpreter on **TA-Lib** indicators — expectancy, profit factor, drawdown vs buy-and-hold) |
| `/strategy-manager` | Full strategy lifecycle: **generate** a complete rule-based system from a reference article you supply → **validate** it by backtest and mark it active when it passes → **pick** the active strategy that fits the current regime → **optimize** or retire strategies from live trade outcomes fed back by `/trade-tracker` |
| `/trade-tracker` | Connect Zerodha/Upstox (read-only MCP), match each open position to its rationale (a find-trade idea, deep-analysis, strategy spec, or one you type), and re-validate the thesis — stop / target / time stop / broken setup / regime change → hold or early-exit call |
| `/dcf-valuation TICKER` | Story-driven DCF (Damodaran FCFF): project revenue growth + operating margin, fund growth via the sales-to-capital ratio, discount FCFF at WACC, add a disciplined terminal value → intrinsic value/share with margin of safety, a WACC×terminal-growth sensitivity grid, and reality-check flags. Bundled offline-tested engine; every input must be sourced |
| `/management-quality TICKER` | Management integrity (a hard gate) + skill grade: remuneration vs profit, related-party transactions, criminal/regulatory record, media-savvy, CFO/auditor churn & fees, owning mistakes, pledging — then qualification/experience, mindset, capital allocation, succession |

## Agents (`agents/`, all `context: fork`)

`technical-analyst`, `fundamentals-data` (fetch-once source pack) → `financials-analyst` · `management-analyst` · `valuation-analyst`, `news-sentiment`, `sector-analyst`, `bull-researcher`, `bear-researcher`, `portfolio-manager` — orchestrated by `/deep-analysis`, reusable individually. The four fundamental agents also power `/fundamental-analysis`; `sector-analyst` also powers `/sector-analysis`.

## Hooks

- **Stop → `post-deep-analysis.sh`**: archives the staged report to `artifacts/stocks/<TICKER>/<date>/deep-analysis.md` (plus its agent work papers), sends the Telegram brief. Anchors to the session cwd from the hook's stdin so it fires reliably regardless of where the hook process starts.
- **SessionStart → `session-context.sh`**: injects today's date + market open/closed status.

## Templates

Bundled per skill in `skills/<name>/assets/` — HTML where visuals help (signal report, budget dashboard, sector-analysis grid, fund comparison), markdown for text-first outputs (deep-analysis artifact, daily brief, Telegram format).

## Artifacts

Everything a skill produces lands under `./artifacts/` of the directory you run Claude in: `artifacts/YYYY-MM-DD/<report>` for dated outputs, `artifacts/.cache/` for reusable data downloads, `artifacts/strategies/<name>.yml` for strategy specs, and `artifacts/trades/<SYMBOL>-<date>.yml` for trade ideas that `/trade-tracker` monitors.

## Deliberately out of scope

Scheduled crons (run them outside the plugin) and any **order execution** — `/trade-tracker` reads broker positions and recommends exits, but you place every order yourself; the broker MCPs are read-only.
