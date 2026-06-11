# Trade Tracker — {{DATE}}

**Broker:** {{BROKER}} (read-only) · **Open positions tracked:** {{N}} · **Needs action today:** {{N_ACTION}}

> Lead here with anything flagged EXIT_* — what to do before the next session.

## Action required

| Symbol | Qty | Avg | LTP | Unreal. R | P&L | Verdict | Why | Action (level to watch) |
|---|---|---|---|---|---|---|---|---|
| {{SYMBOL}} | {{QTY}} | ₹{{AVG}} | ₹{{LTP}} | {{R}}R | ₹{{PNL}} | **{{VERDICT}}** | {{REASON}} | {{ACTION}} |

## Holding (rationale intact)

| Symbol | Qty | Avg | LTP | Unreal. R | P&L | Thesis check | Time left |
|---|---|---|---|---|---|---|---|
| {{SYMBOL}} | {{QTY}} | ₹{{AVG}} | ₹{{LTP}} | {{R}}R | ₹{{PNL}} | intact | {{SESSIONS_LEFT}} sessions |

## Manual review (qualitative conditions to judge)

- **{{SYMBOL}}** — {{CONDITION}} → {{YOUR_FINDING}} (thesis: broken / intact)

## Regime check (strategy-linked trades)

- **{{SYMBOL}}** ({{STRATEGY}}) — required: {{REGIME_REQUIRED}}; live: {{REGIME_NOW}} → {{still valid / regime-exit}}

## Data gaps

- {{SYMBOL}}: {{what was missing — no rationale artifact / no price data / fetch blocked}}

---
*Verdicts from `validate_trade.py` (EXIT_STOP → EXIT_THESIS → EXIT_TARGET → EXIT_TIME → HOLD), priority order. R = (price − entry)/(entry − stop).*

*This tool recommends; you place the order. No automated execution. Not investment advice — personal research tool.*
