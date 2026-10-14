# Trade Tracker — {{DATE}}

**Broker:** {{BROKER}} (read-only) · **Open positions tracked:** {{N}} · **Needs action today:** {{N_ACTION}}

> Lead here with anything flagged EXIT_* — what to do before the next session.

## Action required

| Symbol | Qty | Avg | LTP | Unreal. R | P&L | Verdict | Why | Action (level to watch) |
|---|---|---|---|---|---|---|---|---|
| {{SYMBOL}} | {{QTY}} | ₹{{AVG}} | ₹{{LTP}} | {{R}}R | ₹{{PNL}} | **{{VERDICT}}** | {{REASON}} | {{ACTION}} |

## No mechanical exit trigger

| Symbol | Qty | Avg | LTP | Unreal. R | P&L | Thesis check | Time left |
|---|---|---|---|---|---|---|---|
| {{SYMBOL}} | {{QTY}} | ₹{{AVG}} | ₹{{LTP}} | {{R}}R | ₹{{PNL}} | {{THESIS_STATUS}} | {{SESSIONS_LEFT}} sessions |

## Manual review (qualitative conditions to judge)

- **{{SYMBOL}}** — {{CONDITION}} → {{YOUR_FINDING}} (thesis: broken / intact)

## Regime check (strategy-linked trades)

- **{{SYMBOL}}** ({{STRATEGY}}) — required: {{REGIME_REQUIRED}}; live: {{REGIME_NOW}} → {{still valid / regime-exit}}

## Data gaps

- {{SYMBOL}}: {{what was missing — no rationale artifact / no price data / fetch blocked}}

---
*Verdicts from `check_trade` (EXIT_STOP → EXIT_THESIS → EXIT_TARGET → EXIT_TIME → HOLD), priority order. Decision data as of {{DECISION_DATE}}. R uses the actual fill and original stop; price for unrealized P&L: {{MARK_SOURCE}}. Unrealized P&L excludes charges. A HOLD still needs the manual checks listed.*

*This tool recommends; you place the order. No automated execution. Not investment advice — personal research tool.*
