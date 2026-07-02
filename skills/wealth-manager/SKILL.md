---
name: wealth-manager
description: The whole-picture financial advisor — builds your total net worth across every IndMoney asset class (equity, funds, real estate, gold, EPF, FDs, debt, cash, US stocks, insurance value), then orchestrates the three personal-finance spokes (portfolio-review, insurance-advisor, budget-tracker) in cheap mode to produce one financial-health scorecard and a prioritized cross-domain action plan — the calls no single spoke can make ("fix protection before adding equity", "your emergency fund is one month"). Use when the user asks about their overall finances, net worth, "how am I doing financially", "where should my next rupee go", a financial health check, or how their investments/insurance/spending fit together.
argument-hint: "[--snapshot | --full-review]"
allowed-tools: Read, Write, Bash, Agent, Skill, mcp__indmoney__*, mcp__kite__*, mcp__upstox__*
---

# Wealth Manager

The capstone of the personal-finance cluster. Every spoke owns one domain and sees only that domain; **this is the only thing that sees the whole picture and the interactions between domains**. It does two things no spoke can: it builds the total net-worth spine across the asset classes no spoke touches (real estate, gold, EPF, FDs, cash, US equity, insurance value), and it weighs investments, protection, and cashflow *together* to answer "where does my next rupee go" — often overruling the single-domain instinct (protection before a hot stock; emergency fund before more equity).

It **orchestrates, it does not re-derive**: each domain's depth is a forked leg-runner that invokes the spoke in its cheap mode and returns a compact digest. The orchestrator holds digests, not full reports — the deep-analysis IO hygiene, binding from day one. Read `references/reference.md` for the financial-health framework and the prioritization rubric.

**Sources for this skill only:** live net worth + holdings via the shared spine — **IndMoney** (`networth_snapshot` / `networth_allocation_breakdown` / `networth_holdings`, read-only) first, **broker MCP** (Kite/Upstox) equity fallback, `portfolio.yml` last — normalized through `lib/holdings.py`. All domain depth is delegated to the spokes; fetch nothing a spoke owns here.

## Depth mode — resolve first

- **`full-review`** (default on direct invocation) — net-worth spine → fork all available legs → digests → cross-domain computation → scorecard + prioritized plan.
- **`snapshot`** (user passed `--snapshot` or asked for a "quick check / big picture") — net-worth spine + net-worth-level allocation + emergency-fund and gross-protection flags only. **No leg fan-out.** Cheap; skip Sections 2 and straight to a compact spine-only output.

## Section 1 — Net-worth spine

The data foundation, and the only place the non-tradeable classes are seen. `lib/holdings.py` and `scripts/wealth.py` run in script context and **cannot call MCP tools** — so the handoff (same file-pattern as everywhere in this plugin) is:

1. Invoke IndMoney `networth_snapshot`, `networth_allocation_breakdown`, and `networth_holdings` (and, if IndMoney is absent, any connected broker's holdings+positions). **Write each raw payload to a temp file** under `paths.tmp_dir("wealth")`.
2. Normalize the holdings into canonical positions:
   ```
   python3 <plugin>/lib/holdings.py --indmoney <networth_holdings.json> [--kite <k.json>|--upstox <u.json>] [--portfolio <portfolio.yml>] > positions.json
   ```
3. Build the spine — total net worth, per-class allocation, liquid pool, equity share, XIRR summary — from the two net-worth payloads + the positions envelope. This is done inside `wealth.py` (Section 3); you assemble the **picture JSON** it reads (Section 3).

Degradation: IndMoney not connected → the spine is built from broker + `portfolio.yml` (tradeable-only), the net-worth-level allocation is flagged incomplete, and the non-tradeable classes are named as gaps. Never fabricate an asset value.

## Section 2 — Orchestrate the three legs (full-review only)

Fork **one `wealth-leg` sub-agent per available leg, in parallel** (all Agent calls in one message). Each runs its spoke in cheap mode in isolation, writes the spoke's full report, and returns **only its digest** + the report `path`:

| Leg | Spoke + mode | Digest returned |
|---|---|---|
| Investments | `portfolio-review --quick` (covers stocks **and** funds — funds already deferred to `mf-analysis` inside it) | `investments-block` |
| Protection | `insurance-advisor` (Audit) | `protection-block` (distilled from the audit) |
| Cashflow | `budget-tracker --quick` | `cashflow-block` |

Funds are **not** a separate leg — they ride inside the investments leg. Pass each leg-runner the connected data source it needs and an `output_path` under `paths.report_dir("wealth")`. A leg whose data is absent returns a "data needed" digest rather than failing; a leg agent that errors is a labelled scorecard gap, never an abort of the run.

**IO hygiene:** you receive digests + paths, not report bodies. Transcribe each returned digest block into the `legs` object of the picture JSON below — Read a leg's full report only if you need a specific detail for the write-up.

## Section 3 — Cross-domain computation & scorecard

Assemble the **picture JSON** — the raw net-worth payloads, the positions envelope, the three leg digests, and any user profile (age, dependents, stated monthly expenses) — and run the engine:

```
python3 <plugin>/skills/wealth-manager/scripts/wealth.py --input <picture.json> [--snapshot]
```

Picture shape (leg blocks are the digests you transcribed; omit a leg that didn't run):
```json
{ "snapshot": <networth_snapshot raw|null>, "breakdown": <networth_allocation_breakdown raw|null>,
  "positions": <holdings.py envelope|null>,
  "legs": { "investments": {…investments-block…}, "protection": {…protection-block…}, "cashflow": {…cashflow-block…} },
  "profile": { "age": <n>, "dependents": <n>, "monthly_expenses": <₹|absent> } }
```

`wealth.py` owns every number: the spine, the **emergency-fund runway**, the **protection-vs-net-worth** read, the **risk posture** (all gated by the foundation — see reference.md), and the **financial-health scorecard** with the prioritized action plan. Deterministic; you never eyeball a figure. Ask once for age / dependents / monthly expenses if not derivable — missing expenses makes the emergency-fund read "not assessed", not fabricated.

## Section 4 — Synthesis & output

You synthesize directly from the compact digests + the engine output — no separate synthesizer agent (digests are small). Save the report to `artifacts/wealth/YYYY-MM-DD.md` (`paths.report_path("wealth")`), filling `assets/wealth-report.md`:

- **Net-worth summary** — total, the asset-class allocation table, equity share, liquid pool. (Full ₹ detail here in the artifact.)
- **Financial-health scorecard** — the status per domain (net worth & allocation, investments, protection, cashflow, emergency fund) with one line each, and the overall.
- **Prioritized cross-domain action plan (max ~5)** — ordered by what matters most *across* domains, each with a concrete next step and the spoke to run for depth (`/portfolio-review`, `/insurance-advisor`, `/budget-tracker`, `/mf-analysis`).
- **Data gaps** — every absent leg / uncovered asset class, labelled.

Net-worth values are sensitive: the **full net-worth detail lives in the artifact**; in **chat** give only the scorecard, the plan, and the headline net-worth figure. End with the standard risk note: *Not investment advice — personal research tool.*

`snapshot` writes a compact spine-only note (net worth, allocation, emergency-fund + gross-protection flags) — no scorecard, no plan.

## Section 5 — Error handling & degradation (CLAUDE.md)

A missing source or leg never aborts the review — continue and label the gap:

- **IndMoney not connected** → partial spine from broker + `portfolio.yml`, tradeable-only; net-worth-level allocation flagged incomplete; non-tradeable classes named as gaps.
- **A leg's data absent** → that leg returns "data needed"; the scorecard marks the domain "not assessed — run /<spoke>"; the run still verdicts on the rest.
- **A leg agent fails** → labelled scorecard gap, never an aborted review.
- **Missing age / expenses** → the read that needs them (risk band, emergency-fund runway) is labelled not-assessed, never fabricated.
- Never fabricate a missing asset value or premium — a labelled gap beats a confident fabrication.
