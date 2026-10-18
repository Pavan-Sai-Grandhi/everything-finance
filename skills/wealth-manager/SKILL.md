---
name: wealth-manager
description: The whole-picture financial advisor — builds your total net worth across every IndMoney asset class (equity, funds, real estate, gold, EPF, FDs, debt, cash, US stocks, insurance value), then orchestrates the three personal-finance spokes (portfolio-review, insurance-advisor, budget-tracker) in cheap mode to produce one financial-health scorecard and a prioritized cross-domain action plan — the calls no single spoke can make ("fix protection before adding equity", "your emergency fund is one month"). Use when the user asks about their overall finances, net worth, "how am I doing financially", "where should my next rupee go", a financial health check, or how their investments/insurance/spending fit together.
argument-hint: "[--snapshot | --full-review]"
allowed-tools: Read, Write, Agent, mcp__indmoney__*, mcp__plugin_everything-finance_indmoney__*, mcp__kite__*, mcp__plugin_everything-finance_kite__*, mcp__upstox__*, mcp__plugin_everything-finance_upstox__*, mcp__finance-personal__resolve_holdings, mcp__plugin_everything-finance_finance-personal__resolve_holdings, mcp__finance-personal__run_wealth, mcp__plugin_everything-finance_finance-personal__run_wealth, mcp__finance-workflow__render_report, mcp__plugin_everything-finance_finance-workflow__render_report
---

# Wealth Manager

The only skill that sees the whole picture: the net-worth spine across asset classes no spoke
touches, and investments, protection and cashflow weighed together to answer "where does my next
rupee go", often overruling the single-domain instinct. It orchestrates and never re-derives:
each domain's depth is a spoke run in its cheap mode, and this skill holds digests, not reports.
Every market number arrives inside a leg digest; the hub calls no market or company tool.

**Method:** `methods/personal-finance.md`.

## Modes

- **`full-review`** (default): the spine, all three legs, the cross-domain figures, the scorecard
  and the plan.
- **`snapshot`** (`--snapshot`, "quick check", "big picture"): the spine and its allocation with
  the emergency-fund and gross-protection flags; no legs, no deck.

## 1. The net-worth spine

1. Call IndMoney `networth_snapshot`, and `networth_holdings` once per asset type, and write each
   payload under the artifacts `tmp/wealth/` directory. The snapshot is the net-worth source: its
   `investments` rows are the per-class breakdown (pass it as both `snapshot` and `breakdown`) and
   its `liabilities.total` is the picture's `liabilities` (`as_of` = the fetch date, `source` =
   "IndMoney networth_snapshot"). `networth_allocation_breakdown` is per asset type, not the whole
   book. Without IndMoney, use the connected brokers' holdings and positions.
2. Resolve the positions with `resolve_holdings` (`RULES.md` → *Reading your holdings*), slice
   `all`, passing the portfolio file when one exists.

## 2. The three legs (full-review only)

Run each available leg once in its mode and keep only its digest and path. When agents are not
allowed, run the legs one after another here.

| Leg | Profile | Spoke and mode | Digest |
|---|---|---|---|
| Investments | `everything-finance:terminal-analyst` | `portfolio-review --quick` (stocks and funds; funds defer to `mf-analysis` inside it) | `investments-block` |
| Protection | `everything-finance:desk-analyst` | `insurance-advisor`, Audit | `protection-block` |
| Cashflow | `everything-finance:desk-analyst` | `budget-tracker --quick` | `cashflow-block` |

Each dispatch names the skill, its mode, an output path under `artifacts/wealth/<date>/`, and the
leg's inputs. No profile can reach a broker, so hand the investments leg the payload paths written
in section 1; protection and cashflow work from the policy and statement files the user supplied.

## 3. Cross-domain computation

Write the picture JSON (`finance/contracts.md` → *Artifact: net-worth spine + financial-health
scorecard*) and call `run_wealth(picture=<file>, snapshot=<true in snapshot mode>)`:

```json
{ "snapshot": <networth_snapshot | null>, "breakdown": <same snapshot | null>,
  "positions": <resolve_holdings envelope | null>,
  "liabilities": {"total": <₹>, "as_of": "YYYY-MM-DD", "source": "<evidence>"},
  "legs": {"investments": {…}, "protection": {…}, "cashflow": {…}},
  "profile": {"age": <n>, "dependents": <n>, "monthly_expenses": <₹ | absent>,
              "equity_band": {"min_pct": <stated %>, "max_pct": <stated %>},
              "emergency_reserve": {"available_value": <confirmed ₹>, "as_of": "YYYY-MM-DD", "source": "<evidence>"}} }
```

Omit unavailable blocks. The engine owns every number.

- **Liabilities** come from first-party evidence or explicit user confirmation, dated and sourced.
  Never infer zero or back out debt as whatever balances the assets; preserve `allocation_basis`.
- **Emergency reserve** is a dated, accessible amount after encumbrances, withdrawal limits,
  near-term commitments and costs. A cash or FD total is only `observed_liquid`. Flag stale evidence.
- Ask for dependents and monthly expenses when needed. Use only an explicitly stated
  `equity_band`, never one derived from age. A recurring-expense floor gives only
  `months_upper_bound`, never an assessed runway.
- `holdings_xirr.avg` is a descriptive mean of separate histories, not portfolio XIRR; report its
  `method` and coverage.
- `risk_posture` is the personal balance-sheet posture, distinct from market-analysis's
  `market_posture`; a `risk_on` market never loosens a posture the foundation has gated.

## 4. Synthesis and output

Write the report at `artifacts/wealth/<date>.md` from `assets/wealth-report.md`: the net-worth
summary and allocation table, the scorecard per domain with the overall, at most five
cross-domain actions ordered by the method's stack (each with a next step and the spoke to run),
and every absent leg or uncovered class as a gap. Net-worth values are sensitive: the full detail
stays in the artifact; chat gets the scorecard, the plan and the headline net worth.

**The deck**: write `artifacts/wealth/<date>.report.json`, shaped like
`finance/report/fixtures/wealth-report.sample.json` (cover verdict and headline stats, the spine,
each leg's verdict, the scorecard, the cross-domain reads with the runway gauge, the plan, the
gaps), and `render_report(template="wealth-report", out=artifacts/wealth/<date>.html)`. Every
figure traces to the `.md`.

`snapshot` writes a compact spine-only note: net worth, allocation, the emergency-fund and
gross-protection flags.

Degradation: without IndMoney, a tradeable-only spine with the non-tradeable classes named as
gaps; a leg without data or a failed leg is "not assessed — run /<spoke>" on the scorecard, and
the review still verdicts on the rest.
