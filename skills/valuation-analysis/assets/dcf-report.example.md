<!-- valuation-block
combined_stance: Undervalued | Fair | Overvalued
dcf_mos: <±x%>          dcf_confidence: low | med | high   terminal_weight: <x%>
pe: <x>   pe_basis: reported | adjusted | reported (unchecked)   peg: <x>
eps_adjustments: <what the one-off scan found, or `none`>
peer_median_pe: <x|n/a>   peers_priced: <n>   ev_ebitda: <x|n/a>   relative_stance: <undervalued|fair|overvalued|not computable>
axis: valuation
-->
# Valuation — <COMPANY> (<SYMBOL>) · <YYYY-MM-DD>

## Findings

<Everything from this leg that could change a verdict, in 3-6 plain sentences — each with its number and where it came from. A reader who stops here has the leg's whole case.>


> <FCFF discounted at WACC | equity cash flow discounted at cost of equity>, compared with the multiples read. A model, not a price target. Observed inputs carry sources and dates; forecast assumptions carry explicit rationales.

**Combined stance: Undervalued / Fair / Overvalued** — <one line on what the DCF and the relative read jointly say, and which led, by confidence>.

## Stage diagnosis
- **Life-cycle stage:** <start_up | young_growth | high_growth | mature_growth | mature_stable | decline> — <one line on why, and what it implies: where value should sit, whether failure risk applies, story-vs-numbers balance>.
- **Country-risk exposure (λ):** <~1 fully domestic | ~0.x for a firm earning <…>% abroad> — so India's CRP is loaded at <…>%, not in full.

## The story
<3–4 sentences: the narrative the numbers encode — what drives growth, why margins land where they do, what it costs to grow. The numbers below must be consistent with this story.>

## Inputs and assumptions (sources, dates and rationales)

<When revising a valuation, cite both immutable DCF evidence paths and add a `was → now` line per changed lever with the reason it moved. A same-day call is not automatically a revision of another session’s valuation.>
| Lever | Value / path | Source / justification |
|---|---|---|
| Base revenue | ₹<…> Cr | Revenue from Operations FY<…> (consolidated; non-operating income excluded) |
| Revenue growth | <…>% → fade to <…>% by Y<N> | TAM×share×take-rate / guidance / history |
| Operating margin | <…>% → <…>% by Y<…> | current margin; peer steady-state (normalised through-cycle if cyclical) |
| Tax rate | <…>% | annual report FY<…> tax note (effective → statutory) |
| Sales-to-capital | <…> | historical ΔRev/ΔInvCapital; peer benchmark |
| WACC | <…>% → <…>% | CoE (default-free rf = G-sec <…>% − sovereign spread <…>%; + β<…>×mature-ERP <…>% + λ<…>×CRP <…>%) + after-tax CoD; source dates <…> |
| Terminal growth | <…>% | ≤ default-free risk-free <…>% in the cash-flow currency |
| Terminal ROIC | <…>% | excess return ROIC−WACC = <…>pp (the terminal driver); >0 only for a named durable moat, else convergence |
| Net debt / cash / shares | ₹<…> Cr / ₹<…> Cr / <…> Cr | `Total Debt` − `Cash and Equivalent`; `Common Shares Outstanding` |
| Post-operating adjustments | failure prob <…>% / complexity discount <…>% | <only if warranted — distress signals / governance-complexity; else "none">|

Lease / R&D capitalisation: <applied | not material | data gap — explain>.

## Intrinsic value
<For equity-shaped runs, use earnings/ROE/cost-of-equity labels throughout. The discounted cash-flow total is equity value before adjustments, not enterprise value. Do not present an equity-mode margin-shift scenario as an operating forecast.>
- **Intrinsic value/share: ₹<…>** (equity ₹<…> Cr; EV ₹<…> Cr)
- <If haircuts applied: going-concern ₹<…>/sh → ₹<…>/sh after <failure/complexity> adjustment.>
- Current price: ₹<…> → **DCF margin of safety: <±…>%** (`dcf_mos`)
- Terminal value = <…>% of EV

### Sensitivity — the levers that move value (story-driver grid: growth × steady-state margin)
<paste `story_sensitivity_md` from the engine verbatim — do not retype the numbers>

Explain what this scenario range varies and holds fixed; it is not a probability interval. Evaluate the `duration` cases against independent business evidence. Do not choose a growth duration merely because it closes the gap to the market price. For an unavailable grid, report its data gap instead of inventing a range.

<details><summary>Terminal WACC × terminal growth (secondary mechanical check; explicit WACC and operations stay fixed)</summary>

<paste `sensitivity_md` from the engine verbatim>

</details>

## Reverse DCF — what ₹<price> already assumes
- Holding the other model assumptions fixed, one solved path matching ₹<price> implies **~<implied>% revenue growth** (year 1) ≈ **~<implied CAGR>% over <N> years** — vs your base story of <base>% and the company's <history>% history / <guidance> guidance.
- **Plausible?** <yes/no and why — TAM, peer precedent, guidance>. <If solved:false, quote the reason and omit implied assumptions. Failure to bracket or converge does not establish that the stock is cheap or expensive. A solved root need not be unique.>
- (If the bull thesis is margin-led, also: implied operating margin of **~<m>%** vs <base/peer>%.)

## Relative value — multiples vs peers
| Multiple | Company | Peer median | Own 5y band | Reads as |
|---|---|---|---|---|
| P/E | <…> (<reported / adjusted>) | <…> (<n> peers, <reported / adjusted>: <names>) | <…>th percentile | <cheap / in line / dear / not comparable> |
| PEG | <…> | — | — | growth basis: <forward / historical EPS CAGR — labelled estimate>; PEG assumes equal risk and a linear growth↔P/E link |
| EV/EBITDA <or P/B · RoE for a bank / NBFC / insurer> | <…> | <…> | — | <…> |

<Where the engine's `relative.gaps` is non-empty — a peer set under three, or a basis mismatch — say here that the peer half is void and what the stance rests on instead.>

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
