# Modular plugin — design

## Intent

New method sources are coming: Money Purse, Day Trader Telugu and SOIC, distilled from YouTube with
`yt-distill`, alongside Zerodha Varsity. Adding a source must be routine: put its rules into the
method topic they belong to, with a citation. It must not mean rewriting several skills. The same
pass removes every duplicate instruction and every second code path, so two copies can never drift.

## Decisions

### 1. Runtime rules vs development rules

- `RULES.md` is the runtime contract for whoever uses the plugin: data integrity, the source table,
  the personal/decision boundary, output conventions, how a report reads, and trading discipline.
- Claude Code does not load a plugin's instructions file. The SessionStart hook prints `RULES.md`
  into the main session, and a SubagentStart hook adds it to every plugin agent through
  `additionalContext`. Agent Plugins clients read it through `plugin.json` →
  `extensions.instructions`.
- `CLAUDE.md` is for building the plugin. It imports `@RULES.md`, then adds the architecture, the
  test runner, the method-layer authoring rules and the source priority.

### 2. One method layer, organised by topic

`methods/` holds the knowledge the skills apply. Each topic file says which skills consume it and
cites a source for every rule. A source is a citation, not a folder.

| File | Consumers |
|---|---|
| `technical.md` | technical-analysis, discover, strategy-manager, sector-analysis |
| `trading-system.md` | strategy-manager, discover, trade-tracker |
| `fundamentals.md` | financial-analysis, valuation-analysis, deep-analysis (quick pass), portfolio-review |
| `management.md` | management-analysis |
| `valuation.md` | valuation-analysis |
| `sectors.md` | sector-analysis, deep-analysis |
| `funds.md` | mf-analysis, discover, portfolio-review |
| `market.md` | market-analysis |
| `news.md` | news-scan |
| `filings.md` | filings-watch, daily-brief |
| `special-situations.md` | discover |
| `trade-management.md` | trade-tracker, daily-brief |
| `portfolio.md` | portfolio-review |
| `personal-finance.md` | wealth-manager, budget-tracker, mf-analysis |
| `insurance/{framework,term,health,vehicle}.md` | insurance-advisor |

`methods/SOURCES.md` is the registry: each source's id, kind, coverage, what has been distilled
from it, and the citation format. It also sets the priority order used to settle a disagreement.

Skills keep only workflow: inputs, tools, steps, the output block and alerts. A skill's
`references/` directory survives only for workflow detail that belongs to that one skill.

### 3. Disagreement priority

1. The plugin's own rules in `RULES.md` (data integrity, trading discipline). No source overrides them.
2. Law and the regulator's own text (SEBI, RBI, IRDAI, the Companies Act) for what a rule *is*.
3. The topic's lead source, named at the top of each topic file (Varsity for technical analysis,
   Damodaran for valuation, the management framework's authors for management).
4. Every other source, in registry order.

The higher-priority rule is the method. A lower-priority source that disagrees is recorded beside
it as a labelled variant, and is adopted only by an explicit edit to the topic file.

### 4. One code path: MCP tools

Skills and agents reach code only through MCP tools. No `python3 -m finance…`, no `PYTHONPATH`,
no `skills/*/scripts`. The hooks under `hooks/` are the one exception, because a hook cannot call
a tool.

| Moved from | To | Tool(s) |
|---|---|---|
| `python -m finance.compute.holdings` | `compute/holdings.py` | `resolve_holdings` |
| inline `ta.py` snippet | `compute/ta.py` | `get_technicals` |
| `budget-tracker/scripts/{categorize,recurring}.py` | `compute/budget.py` | `categorize_transactions`, `learn_merchant`, `detect_recurring` |
| `portfolio-review/scripts/allocation.py` (thin CLI) | — | `review_allocation` |
| `wealth-manager/scripts/wealth.py` (thin CLI) | — | `run_wealth` |
| `insurance-advisor/scripts/insurance_math.py` (thin CLI) | — | already `run_insurance_math` |
| `alert-manager/scripts/manage.py` (thin CLI) | — | already `manage_alerts` |
| `deep-analysis/scripts/{resolve_mode,escalation}.py` | `compute/debate.py` | `resolve_analysis_mode`, `decide_debate_round` |
| `strategy-manager/scripts/{select_strategy,aggregate_performance}.py` | `compute/strategy_library.py` | `select_strategy`, `review_strategy_performance` |
| `skills/_report/` (renderer, charts, templates, assets, fixtures) | `finance/report/` | `render_report` |
| `python -m finance.publication prepare`, the `publish` hook argument | `finance/report/publication.py` | `prepare_report`, `publish_report` |
| `bin/send-telegram.sh` | `finance/report/telegram.py` | `send_telegram` |

### 5. Five servers

- `finance-market`: prices, index and market state, the universe, screens, backtests, `get_technicals`.
- `finance-company`: one company's fundamentals, documents, filings, news, DCF and governance arithmetic.
- `finance-funds`: unchanged.
- `finance-personal`: the user's own money. Holdings, allocation, wealth, budget, insurance math and `check_trade`.
- `finance-workflow`: the plugin's own state and run machinery. Alerts, prior runs, the strategy
  library, analysis mode and debate rounds, and report bundles, rendering and delivery.

### 6. Deslop rules applied everywhere

- No duplicated code or instruction. Each fact is stated once, at the layer that owns it, and
  pointed at from everywhere else.
- No backward-compatibility aliases (`next_resistance`, `screener_in`, legacy staging and the like).
- No history narration ("used to", "was written before", "removed seed"). The tree states what it
  is now.
- Comments are short and only where the code cannot say it.

## Left to the builder

File-level wording, test consolidation, and whether a small helper stays private or moves to `spine`.
