# Wealth Review — {{DATE}}

## Net worth
- **Total net worth:** {{TOTAL_NETWORTH}}  <!-- ₹x.x Cr, Indian grouping -->
- **Equity share:** {{EQUITY_SHARE_PCT}}% (equity + funds + US)  ·  **Liquid pool:** {{LIQUID}} (cash + FDs)
- **Coverage:** {{COVERAGE}}  <!-- complete | tradeable-only (IndMoney not connected) -->

### Asset-class allocation
<!-- One row per net-worth bucket, largest first. Full ₹ detail lives here in the artifact, not in chat. -->
| Asset class | Value | % of net worth |
|---|---|---|
| {{CLASS_LABEL}} | {{CLASS_VALUE}} | {{CLASS_PCT}}% |

**Holdings XIRR:** {{XIRR_SUMMARY}}  <!-- avg across N holdings; best {{BEST}}, worst {{WORST}}; or "unavailable (broker/manual source)" -->

## Financial-health scorecard
<!-- Status ∈ strong | adequate | weak | critical | not assessed. One falsifiable line each. -->
| Domain | Status | Read |
|---|---|---|
| Net worth & allocation | {{NW_STATUS}} | {{NW_LINE}} |
| Investments | {{INV_STATUS}} | {{INV_LINE}} |
| Protection | {{PROT_STATUS}} | {{PROT_LINE}} |
| Cashflow | {{CF_STATUS}} | {{CF_LINE}} |
| Emergency fund | {{EF_STATUS}} | {{EF_LINE}} |

**Overall:** {{OVERALL}}  <!-- the worst assessed domain -->

## Cross-domain read
<!-- The calls no single spoke can make. -->
- **Emergency fund:** {{EF_MONTHS}} months of runway vs a 3-6 month target ({{EF_EXPENSE_BASIS}}).
- **Protection vs net worth:** {{PROT_CROSS_LINE}}
- **Risk posture:** {{RISK_LINE}}  <!-- fix-foundation-first | balanced | can-add-risk | reduce-risk -->

## Prioritized action plan
<!-- Max ~5, ordered ACROSS domains (protection/emergency fund before fresh equity). Each: the move + the concrete next step + the spoke to run for depth. -->
1. **{{ACTION_TEXT}}** — {{ACTION_NEXT_STEP}} → `{{ACTION_RUN}}`

## Data gaps
<!-- Every absent leg / uncovered asset class, labelled. "None." if the picture was complete. -->
- {{DATA_GAP}}

---
*This is a personal-finance research tool, not investment or financial advice. Net-worth figures are your own first-party data; verify any action with the source. **Not investment advice — personal research tool.***
