# Market Read — {{as_of}}

*Computed {{generated}} from `artifacts/market-analysis/{{generated}}.json`. `as_of` is the last available Nifty bar; show "unavailable" if null. Other components may have different dates.*

## The call

**Posture: {{market_posture}} · Trend: {{market_trend}}**

{{rationale}}

{{one-paragraph plain-language read: what the market is doing, and the single tension that matters most for a decision right now}}

## Trend

| | |
|---|---|
| Nifty 50 | {{trend_detail.close}} |
| vs 50-EMA | {{trend_detail.ema50}} ({{above/below}}) |
| vs 200-EMA | {{trend_detail.ema200}} ({{above/below}}) |
| 50-EMA slope | {{rising/falling}} |
| From 52w high | {{trend_detail.pct_from_52w_high}}% |

## Breadth — is the move broad?

| Measure | Reading |
|---|---|
| Above 50-DMA | {{breadth.pct_above_sma50}}% of {{breadth.counts.above_sma50.of}} priced stocks |
| Above 200-DMA | {{breadth.pct_above_sma200}}% of {{breadth.counts.above_sma200.of}} priced stocks |
| Near 52w high | {{breadth.pct_near_52w_high}}% |
| Near 52w low | {{breadth.pct_near_52w_low}}% |
| Sectors above 50-EMA | {{breadth.pct_sectors_above_ema50 or unavailable}}; coverage {{breadth.sectors_available}}/{{breadth.sectors_expected}} |

{{one line: broad / narrow / diverging from the index, and what that implies}}

## Volatility

India VIX **{{volatility.vix}}** — {{volatility.band}}, {{volatility.percentile_1y}}th percentile of 1 year, {{volatility.percentile_5y}}th of 5.

## Valuation by cap tier

*Level, and percentile against that index's own {{history_years}}-year history. The blend inverts dividend-yield percentile as a valuation heuristic.*

| Index | P/E | %ile | P/B | %ile | Div yld | %ile | Stance |
|---|---|---|---|---|---|---|---|
| Nifty 50 | | | | | | | |
| Midcap 150 | | | | | | | |
| Smallcap 250 | | | | | | | |

{{pe_pctile_note, sample coverage and how many outliers were excluded}}

**Relative:** smallcap/largecap P/B {{relative.smallcap_vs_largecap_pb_ratio}}, percentile spread {{relative.percentile_spread}}. {{relative.read}}

## Flows

Session {{flows_session}} — FII net ₹{{FII.net_cr}} Cr, DII net ₹{{DII.net_cr}} Cr. {{describe this session only; a trend needs more sessions}}

## Macro backdrop

| Series | Level | 1M | 5y %ile |
|---|---|---|---|
| India VIX | | | |
| USDINR | | | |
| Gold | | | |
| Brent | | | |
| US 10Y | | | |

{{one line on what this does to risk appetite}}

## Sector leadership

**Leaders (1Y):** {{sectors.leaders}}
**Laggards (1Y):** {{sectors.laggards}}

## What this implies

- **Sizing:** {{what the posture means for position size}}
- **Allocation:** {{what the cap-tier valuation means for where new money goes}}
- **Watch:** {{the specific level, breadth reading, or flow reversal that would change the read}}

## Data gaps

{{each gap, named — including the rate cycle when no primary source was available}}

---
*Market context is an input to a decision, never a forecast. Not investment advice — personal research tool.*
