# Deep-analysis knowledge base

This file owns what belongs to no single lens: **how the six lenses combine into one verdict**, and **the debate protocol**. Each lens's own method lives with the skill that runs it — `financial-analysis`, `management-analysis`, `valuation-analysis`, `technical-analysis`, `news-scan` and `sector-analysis` each carry it in their `references/`. Grounded in Zerodha Varsity — Fundamental Analysis (https://zerodha.com/varsity/module/fundamental-analysis/) and Technical Analysis (https://zerodha.com/varsity/module/technical-analysis/).

## What each lens decides

| Lens | The question it answers |
|---|---|
| Financials | Do the numbers hold up, and what is this business actually? |
| Valuation | What is it worth, and what does today's price already assume? |
| Management | Can the people running it be trusted with either? |
| Technical | Where is the price in its own structure, and which level kills a thesis? |
| News | What is being said, and does a filing stand behind it? |
| Sector | Does the stock swim with its industry or against it? |

## Combining them

Three rules decide the verdict and belong to no lens on its own.

**Integrity is a gate, not a weight.** A FAIL on the management leg's integrity gate is near-fatal to the bull case — that side must engage it or concede, and the portfolio-manager treats it as an AVOID override whatever the numbers, the chart or the valuation say. In `quick` the lens does not run; its absence is weighed as uncertainty, never as a pass.

**Valuation is weighted by its own confidence.** The valuation leg returns a combined Undervalued / Fair / Overvalued stance *and* a DCF-confidence grade. A high-confidence DCF leads the call on margin of safety against intrinsic value; a low-confidence one (terminal-heavy, aggressive, or a bank or violent cyclical) is a sanity band only and the call leans on the relative read. Never let a low-confidence DCF drive a buy on intrinsic value alone.

**The sector read can move the call.** A great company in a lagging sector, or a laggard inside a leading one, changes the position — the researchers and the portfolio-manager weigh it alongside the rest, not as decoration.

A lens that could not run is uncertainty, not neutrality. The synthesis names it in Data Gaps and the portfolio-manager prices it as risk.

## Debate protocol

**Round 1** — each researcher produces its three strongest arguments, every one tied to a specific figure, level or cite from a leg report, plus what would change its mind.

**A later round is a turn, not a restatement.** Fed the other side's previous round, a researcher adds new load-bearing evidence, explicitly concedes, or reports `new_evidence: false` — an honest, debate-ending answer, not a failed turn.

**A round is worth running while the two sides still have something to test**, which `escalation.py` decides from the `debate-block` digests and which comes in two shapes:

- **Different axes** — say a bull on `technical_structure` against a bear on `valuation`. Neither case has been tested at all; the run has two unopposed monologues. The next round is a **cross-examination**: each side answers the opponent's axis on its own terms first. Stopping here would hand the portfolio-manager arguments that never met, and would reward a side for choosing an axis its opponent will not touch.
- **Same axis, distinct claims** — a real clash. The next round is a **rebuttal**: attack the evidence under the opposing claim.

The verdict-relevant axes are `valuation`, `growth_durability`, `balance_sheet_risk`, `governance` and `technical_structure`. What ends a debate is a concession, both sides restating one claim, `new_evidence: false` on both sides, or the mode's round cap — never non-engagement.

**The portfolio-manager must state**, once, on the full transcript: the action (Buy / Accumulate / Hold / Avoid / Exit) and, separately, what the business is worth — they come apart routinely, and an "overvalued but held, chart intact" Hold is a different object from a "we could not see enough" Hold. Plus conviction (low / med / high), the allocation cap as a % of portfolio, the entry zone if Buy, the hold/trim/exit call when the ticker is a live holding, and the invalidation — the price level or fundamental event that kills the thesis.

**Disagreement is the product.** If bull and bear both still sound right after the rounds, the verdict should usually be Hold or Avoid with the specific uncertainty named, not a split-the-difference Accumulate.
