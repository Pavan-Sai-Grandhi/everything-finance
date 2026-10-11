# Wealth Review — {{DATE}}

## Net worth
- **Total net worth:** {{TOTAL_NETWORTH}}  <!-- ₹x.x Cr, Indian grouping -->
- **Equity share:** {{EQUITY_SHARE_PCT_OR_UNAVAILABLE}} · **Known direct-equity share:** {{KNOWN_EQUITY_SHARE_PCT}}%  ·  **Liquid pool:** {{LIQUID_OR_UNAVAILABLE}} (confirmed accessible reserve, evidence {{RESERVE_AS_OF}} / {{RESERVE_SOURCE}}; observed cash + FDs: {{OBSERVED_LIQUID}})
- **Coverage:** {{COVERAGE}}  <!-- complete | incomplete (reconciliation/data gap) | tradeable-only -->

**Reported liabilities:** {{LIABILITIES_TOTAL_OR_UNAVAILABLE}} · {{LIABILITIES_SOURCE_AND_DATE}}

### Asset-class allocation

*Denominator: {{ALLOCATION_BASIS}}. With sourced liabilities, percentages describe gross assets, not leveraged net worth.*
<!-- One row per net-worth bucket, largest first. Full ₹ detail lives here in the artifact, not in chat. -->
| Asset class | Value | % of stated denominator |
|---|---|---|
| {{CLASS_LABEL}} | {{CLASS_VALUE}} | {{CLASS_PCT}}% |

**Holdings XIRR:** {{XIRR_SUMMARY}}  <!-- descriptive current-value-weighted mean over weighted_count holdings, NOT portfolio XIRR; best/worst can have different holding periods; or unavailable -->

## Financial-health scorecard
<!-- Status ∈ strong | adequate | weak | critical | not assessed. One falsifiable line each. -->
| Domain | Status | Read |
|---|---|---|
| Net worth & allocation | {{NW_STATUS}} | {{NW_LINE}} |
| Investments | {{INV_STATUS}} | {{INV_LINE}} |
| Protection | {{PROT_STATUS}} | {{PROT_LINE}} |
| Cashflow | {{CF_STATUS}} | {{CF_LINE}} |
| Emergency fund | {{EF_STATUS}} | {{EF_LINE}} |

**Overall:** {{OVERALL}} · assessed {{ASSESSED_DOMAINS}}/{{TOTAL_DOMAINS}} domains. <!-- The worst assessed domain; incomplete coverage is not a comprehensive health verdict. -->

## Cross-domain read
<!-- The calls no single spoke can make. -->
- **Emergency fund:** {{EF_LINE}} ({{EF_EXPENSE_BASIS}}). <!-- Recurring-only estimates are upper bounds, not assessed runway. -->
- **Protection vs net worth:** {{PROT_CROSS_LINE}}
- **Risk posture:** {{RISK_LINE}}  <!-- unknown | fix-foundation-first | within-target | below-target | above-target; use the stated range, never an age-derived target -->

## Prioritized action plan
<!-- Max ~5, ordered ACROSS domains (protection/emergency fund before fresh equity). Each: the move + the concrete next step + the spoke to run for depth. -->
1. **{{ACTION_TEXT}}** — {{ACTION_NEXT_STEP}} → `{{ACTION_RUN}}`

## Data gaps
<!-- Every absent leg / uncovered asset class, labelled. "None." if the picture was complete. -->
- {{DATA_GAP}}

---
*Net-worth figures are your own first-party data; verify any action against the source. Not investment advice — personal research tool.*
