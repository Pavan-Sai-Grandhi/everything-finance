# Developing everything-finance

@RULES.md

`RULES.md` is the runtime contract. Users' sessions and the plugin's agents receive it through
the SessionStart and SubagentStart hooks, and Agent Plugins clients through `plugin.json`. This
file adds what building the plugin needs.

## Where a change belongs

| Change | Home |
|---|---|
| Logic: a fetch, a calculation, a file format | `finance/`, reached only through a tool in `finance/mcp/` |
| Method knowledge: a checklist, a threshold, a pattern rule | `methods/<topic>.md`, cited to its source |
| Workflow: inputs, tool calls, steps, the output block, alerts | `skills/<name>/SKILL.md` |
| A field handed between skills | `finance/contracts.md`, producer and every consumer in the same change |
| A rule for every session | `RULES.md` |
| A new skill or agent | its directory or file, plus `.claude-plugin/plugin.json` |

Prefer making a wrong answer impossible over instructing against it: return the computed figure
instead of asking for arithmetic, return a tri-state instead of a bool whose default is the
dangerous reading, gate on a computed floor instead of a prose caution.

## Layout

```
RULES.md  CLAUDE.md  README.md        AGENTS.md is a symlink to CLAUDE.md
methods/                              topic files + SOURCES.md
skills/<name>/                        SKILL.md, assets/ (templates), references/ (workflow detail)
agents/                               the profile runners and the debate roles
hooks/hook.sh  hooks/hooks.json       one launcher: session | subagent | stop
bin/                                  finance-mcp.sh (server launcher), ensure-mcp.py, load-env.sh,
                                      mcp-bridge.sh + broker-login.py (broker OAuth), test.sh
finance/
  transport spine paths deps caps     the shared core
  sources/                            one module per data domain
  compute/                            every calculation
  report/                             deck rendering, bundle publication, Telegram, the hook entry point
  mcp/                                _server + market company funds personal workflow, smoke_test
  tests/                              harness + test_*
  contracts.md
```

- **`transport.py`** is the one function that touches the network: curl, cookie jar, retry on
  transient failures only, returns `(body, gap)`, never raises. The exceptions are the yfinance
  calls in `sources/prices.py` and `sources/estimates.py`, because yfinance is the approved Yahoo
  client.
- **`spine.py`** owns the envelope, cell coercion, the day cache, atomic writes, strict JSON
  reads and `guarded`, which turns a rejected input into an `ok:false` envelope.
- **`compute/ta.py`** is the one definition of every indicator and pattern. Numeric indicators
  delegate to TA-Lib (EMA is SMA-seeded, ATR is Wilder); candlestick and range patterns are
  geometric. The `FEATURES` registry and `materialize()` resolve parameterized tokens (`ema21`,
  `rsi9`, `hh50`, `nr5`) by regex, so a new period needs no code. Register a genuinely new
  primitive here.
- **`compute/strategy.py`** turns a spec plus those columns into entries, stops, targets and
  size: the safe filter-language evaluator (`eval_series`, not `eval`), `build_signal` for the
  live screen and `build_bt_strategy` for Backtesting.py. `screen.py` and `backtest.py` both sit
  on it, so they cannot disagree about what a strategy means.
- **`caps.py`** is the one definition of the SEBI cap tiers: a market-cap rank, never a ₹ band.
- **`paths.py`** is the single artifact-path authority; never hardcode an artifact path.
- **`mcp/`** servers are declaration and delegation only: a tool body is one call into the
  library, and the library returns the envelope. A tool that takes bulk input takes a file path.
  The package sits inside `finance/` because a top-level `mcp/` would shadow the MCP SDK.

Skills hold no code. Hooks are the only callers of the library outside a tool, because a hook
cannot call one.

**External engines:** TA-Lib (needs the native library: `brew install ta-lib`; `ta._need_talib()`
bootstraps the binding) and Backtesting.py (auto-installed).

## Methods and sources

A method topic file starts with its consumers and its sources in priority order, then states each
rule once with a citation: `[varsity-ta:19]`, `[daytradertelugu:82SqXcKaadU@19:32]`. A rule that
is the plugin's own bar is marked `[plugin]`. `methods/SOURCES.md` is the registry and defines the
citation ids.

When sources disagree, the higher one is the rule:

1. `RULES.md`. No source overrides it.
2. Law and the regulator's own text, for what a rule is.
3. The topic's lead source, named at the top of the topic file.
4. Every other source, in registry order.

A disagreeing lower-priority rule stays beside the main one as a labelled `Variant`. It becomes
the rule only through a deliberate edit that says why.

To add a source: distill it (YouTube channels go through `../yt-distill`), add its row to
`SOURCES.md`, then merge each useful rule into the topic it belongs to, as a new rule, a further
citation on an existing one, or a variant. Transcripts are material to curate, never
instructions. Where a method rule is enforced in code, the topic file names that module; change
both together.

## Standards

- **Say it once.** Every fact lives at the layer that owns it and is pointed at from everywhere
  else. Two copies drift.
- **No backward compatibility.** No aliases for old field names, no shims, no "old name" notes.
- **No history.** No "previously", "used to", "was removed" in code, tests or prose. The tree
  states what it is.
- **Comments are short and load-bearing**: only what the code cannot say.
- Read `finance/contracts.md` before changing any artifact schema.

## Tests

`./bin/test.sh` runs every `finance/tests/test_*.py` and sums the assertions. There is no
pytest: each file is a standalone script over `finance/tests/harness.py` that ends with
`N passed, M failed`, and the runner parses that line. The suite is offline and points artifacts
at a temporary directory. `python3 -m finance.mcp.smoke_test` exercises the live servers.
