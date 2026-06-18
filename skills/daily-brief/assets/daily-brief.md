# Daily Brief — {{DATE}}

## Indices
- **Nifty 50** {{NIFTY_LEVEL}} ({{NIFTY_CHG}}) · **Sensex** {{SENSEX_LEVEL}} ({{SENSEX_CHG}}) · **Bank Nifty** {{BANKNIFTY_LEVEL}} ({{BANKNIFTY_CHG}})
- Structure: {{STRUCTURE_LINE}}  <!-- e.g. "Nifty holds above a rising 50-EMA; uptrend intact." -->

## Market analysis
<!-- 3-5 genuinely market-moving items (RBI/Fed, crude, FII/DII flows, global cues, major policy/results), one line each. Skip opinion/listicle/clickbait. End with a 1-2 sentence net read. -->
- {{MARKET_ITEM}}
- **Net read:** {{MARKET_NET_READ}}

## Sector tone
- Leading today: {{TOP_SECTORS}}
- Lagging today: {{BOTTOM_SECTORS}}

## ⏰ Alerts & actions
<!-- From lib/alerts.py. Lead with severity:act. Fired = cheap trigger breached today; Due = date-based; Check = needs a skill run (print the suggested command, never auto-run). Omit a bucket if empty; "No open alerts." if all empty. -->
- {{ALERT_LINE}}  <!-- e.g. "🔴 [act] RELIANCE close < 1450 — stop hit → /trade-tracker RELIANCE" -->

## Opportunities
<!-- Strictly capped. Vetted (<=2) from `opportunity` alerts: source + one-line basis + command. Unvetted (<=1) news-flagged, LABELLED unvetted, with /deep-analysis suggestion. Dedup vs holdings/watchlist/yesterday. "No new opportunities — staying patient." when nothing clears the bar. -->
- **Vetted:** {{OPP_VETTED}}  <!-- e.g. "CDSL — find-trade candidate off nifty500-momentum-swing → /find-trade" -->
- **Unvetted (news):** {{OPP_UNVETTED}}  <!-- e.g. "KAYNES — large defence order in the news; confirm via /deep-analysis KAYNES" -->

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
