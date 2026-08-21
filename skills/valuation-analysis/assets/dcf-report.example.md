<!-- valuation-block
combined_stance: Undervalued | Fair | Overvalued
dcf_mos: <±x%>          dcf_confidence: low | med | high   terminal_weight: <x%>
pe: <x>   peg: <x>   peer_median_pe: <x>   ev_ebitda: <x|n/a>   relative_stance: <undervalued|fair|overvalued>
axis: valuation
-->
# Valuation — <COMPANY> (<SYMBOL>) · <YYYY-MM-DD>

> Story-driven FCFF DCF (Damodaran) triangulated with the multiples read. A model, not a price target. Every input is sourced below.

**Combined stance: Undervalued / Fair / Overvalued** — <one line on what the DCF and the relative read jointly say, and which led, by confidence>.

## Stage diagnosis
- **Life-cycle stage:** <start_up | young_growth | high_growth | mature_growth | mature_stable | decline> — <one line on why, and what it implies: where value should sit, whether failure risk applies, story-vs-numbers balance>.
- **Country-risk exposure (λ):** <~1 fully domestic | ~0.x for a firm earning <…>% abroad> — so India's CRP is loaded at <…>%, not in full.

## The story
<3–4 sentences: the narrative the numbers encode — what drives growth, why margins land where they do, what it costs to grow. The numbers below must be consistent with this story.>

## Assumptions (each traced to a source)
| Lever | Value / path | Source / justification |
|---|---|---|
| Base revenue | ₹<…> Cr | `Total Revenue` FY<…> (consolidated) |
| Revenue growth | <…>% → fade to <…>% by Y<N> | TAM×share×take-rate / guidance / history |
| Operating margin | <…>% → <…>% by Y<…> | current margin; peer steady-state (normalised through-cycle if cyclical) |
| Tax rate | <…>% | annual report FY<…> tax note (effective → statutory) |
| Sales-to-capital | <…> | historical ΔRev/ΔInvCapital; peer benchmark |
| WACC | <…>% | CoE (rf <…>% + β<…> bottom-up/sector ×mature-ERP <…>% + λ<…>×CRP <…>%) + after-tax CoD |
| Terminal growth | <…>% | ≤ risk-free <…>% in the cash-flow currency |
| Terminal ROIC | <…>% | excess return ROIC−WACC = <…>pp (the terminal driver); >0 only for a named durable moat, else convergence |
| Net debt / cash / shares | ₹<…> Cr / ₹<…> Cr / <…> Cr | `Total Debt` − `Cash and Equivalent`; `Common Shares Outstanding` |
| Post-operating adjustments | failure prob <…>% / complexity discount <…>% | <only if warranted — distress signals / governance-complexity; else "none">|

Lease / R&D capitalisation: <applied | not material | data gap — explain>.

## Intrinsic value
- **Intrinsic value/share: ₹<…>** (equity ₹<…> Cr; EV ₹<…> Cr)
- <If haircuts applied: going-concern ₹<…>/sh → ₹<…>/sh after <failure/complexity> adjustment.>
- Current price: ₹<…> → **DCF margin of safety: <±…>%** (`dcf_mos`)
- Terminal value = <…>% of EV

### Sensitivity — the levers that move value (story-driver grid: growth × steady-state margin)
| growth shift ↓ / margin → | <m−3%> | **<m>** | <m+3%> |
|---|---|---|---|
| <g−4%> | … | … | … |
| **<g>** | … | **<base>** | … |
| <g+4%> | … | … | … |

Lead with this **range** (and the `duration` read: does extending the *demonstrated* growth a couple of years close the gap to price?). The WACC × terminal-growth grid is a secondary check — for a growth firm it perturbs the lowest-leverage levers.

## Reverse DCF — what ₹<price> already assumes
- To justify ₹<price>, the market is pricing in **~<implied>% revenue growth** (year 1) ≈ **~<implied CAGR>% over <N> years** — vs your base story of <base>% and the company's <history>% history / <guidance> guidance.
- **Plausible?** <yes/no and why — TAM, peer precedent, guidance>. <If solved:false, quote the reason — price below conservative value (cheap) or beyond any credible assumption (richly priced).>
- (If the bull thesis is margin-led, also: implied operating margin of **~<m>%** vs <base/peer>%.)

## Relative value — multiples vs peers
| Multiple | Company | Peer median | Own 5y band | Reads as |
|---|---|---|---|---|
| P/E | <…> | <…> (<n> peers: <names>) | <…>th percentile | <cheap / in line / dear> |
| PEG | <…> | — | — | growth basis: <forward / historical EPS CAGR — labelled estimate>; PEG assumes equal risk and a linear growth↔P/E link |
| EV/EBITDA <or P/B · RoE for a bank / NBFC / insurer> | <…> | <…> | — | <…> |

**Relative stance:** <undervalued / fair / overvalued> — <one line on what the multiples alone say>.

## Reconciliation
- <Does the relative read confirm or contradict the DCF?>
- <Is the gap to the peer median explained by fundamentals — higher growth, lower risk — before any of it is called mis-pricing? Name the part that stays unexplained.>

## DCF confidence: <low / med / high>
- **Terminal-value weight:** <…>% of EV — <supports high / pulls toward low>.
- **Assumption stretch:** projected <growth/margin> vs a demonstrated history of <…> — <inside history / above it>.
- **Structural override:** <none | bank/NBFC/insurer → low | violently cyclical → low>.
- **Therefore:** <the DCF led / both carried equal weight / the relative read led and the DCF is a sanity band only>.

## Margin of safety
- vs CMP ₹<…>: **<±…>%** blended across the DCF intrinsic range and the relative read.
- Discount I'd require before acting: <…>% (higher when terminal-heavy / assumption-laden).

## Flags & honesty checks
- <each engine flag, addressed>
- **Devil's advocate:** if <competitor/event> happened, <which input> collapses and the value falls to ≈ ₹<…>.

## Data gaps
- <anything not sourceable or not capitalised — labelled, not hidden>

---
A terminal-heavy or fragile DCF is reported with low confidence, never hidden; this informs a decision, it does not size a position. Not investment advice — personal research tool.
