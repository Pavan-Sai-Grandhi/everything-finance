# Daily Brief — {{DATE}}

## Indices
- **Nifty 50** {{NIFTY_LEVEL}} ({{NIFTY_CHG}}) · **Sensex** {{SENSEX_LEVEL}} ({{SENSEX_CHG}}) · **Bank Nifty** {{BANKNIFTY_LEVEL}} ({{BANKNIFTY_CHG}})
- Structure: {{STRUCTURE_LINE}}  <!-- e.g. "Nifty holds above a rising 50-EMA; uptrend intact." -->

## Sector tone
- Leading today: {{TOP_SECTORS}}
- Lagging today: {{BOTTOM_SECTORS}}

## Watchlist & holdings — filings & news
<!-- Per watchlist ticker AND broker holding: 🔴/🟡 filings (via filings.py) + 1-2 market-moving news items (Google News RSS). Dedupe filing vs headline of the same event. "Nothing material." is the normal, correct entry. SOURCE = filing | news. -->
- **{{TICKER}}**: {{MATERIALITY_EMOJI}} {{ITEM_SUMMARY}} ({{SOURCE}}, {{ITEM_DATE}})

## Positions & attention
<!-- One line per OPEN POSITION (broker holdings/positions, or watchlist.json fallback).
     STATE ∈ ON-TRACK | NEAR-SL | TARGET-ZONE | SL-HIT | TARGET-HIT | STALE | NEEDS-ATTENTION.
     Source = broker (kite/upstox) | file. Sort NEEDS-ATTENTION / NEAR-SL / SL-HIT to the top. -->
| Position | Src | CMP | vs Avg | Day | SL dist | State |
|---|---|---|---|---|---|---|
| {{TICKER}} ({{QTY}}) | {{SRC}} | ₹{{CMP}} | {{PNL_PCT}} | {{DAY_CHG}} | {{SL_DIST}}% | {{STATE}} |

{{ATTENTION_CALLOUT}}  <!-- If any SL-HIT / NEEDS-ATTENTION: one blunt sentence each (e.g. "🔴 TITAN: auditor resigned today — see /trade-tracker"). Omit entirely if none. -->

## One thing
{{ONE_THING}}

---
*{{DATA_GAPS_LINE}}*
