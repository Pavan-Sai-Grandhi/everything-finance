# From lenses to a verdict

**Consumers:** deep-analysis, the debate agents (debate-researcher, contest-researcher) and the
portfolio-manager. **Sources, in priority order:** `varsity-fa`,
`varsity-ta`, `damodaran`, `moneypurse`, `plugin`.

This file owns what belongs to no single lens: how the lenses combine into one call, and how the
debate runs. Each lens's own method lives in its topic file.

## What each lens decides

| Lens | The question it answers | Method |
|---|---|---|
| Financials | Do the numbers hold up, and what is this business? | `fundamentals.md` |
| Valuation | What is it worth, and what does today's price assume? | `valuation.md` |
| Management | Can the people running it be trusted with either? | `management.md` |
| Technical | Where is the price in its own structure, and which level kills a thesis? | `technical.md` |
| News | What is being said, and does a filing stand behind it? | `news.md` |
| Sector | Will the industry be bigger and as profitable in five years, and does the stock swim with it? | `sectors/framework.md` and the sector file |

A lens that could not run is uncertainty, never neutrality: name it in the gaps and price it as risk.

## Combining the lenses [plugin]

- **Integrity is a gate, not a weight.** A management integrity FAIL makes the call AVOID whatever
  the numbers, the chart or the valuation say. FLAG is a concern short of disqualifying, and
  "PASS (partial, k of 7)" is uncertainty; neither is a clean pass.
- **Valuation is weighted by its own confidence** [damodaran]. A high-confidence DCF leads the
  valuation call on margin of safety; medium corroborates; low (terminal-heavy, aggressive, a
  bank or a violent cyclical) is a sanity band only, and relative valuation carries the call.
  Never let a low-confidence DCF drive a buy on intrinsic value alone. Two margins of safety are
  reported: `dcf_mos_market`, at the Indian market's own implied return, carries the stock call;
  `dcf_mos`, at the build-up's rate, is the absolute read. Their difference is how dear the market
  is, a sizing input.
- **The sector's growth story bounds the call; its relative strength times it.**
  `structural_decline` caps the call at HOLD for a holder and AVOID for a new buyer, however cheap
  the stock: a cheap stock in a shrinking industry usually stays cheap. `structural_growth` with
  weak relative strength is a timing question for size and entry, not a reason to reject.
- **Agreement across independent lenses is the strongest signal**, in either direction. A number
  is corroborated only when another leg reports the same metric from an independent source: the
  same metric, not similar digits, and not the same article read by two legs.
- **Market context governs sizing only.** `risk_off` or a wide volatility band tightens the
  allocation cap and the risk per trade; it never changes the call.

## The call [plugin]

The action is one of BUY, ACCUMULATE, HOLD, TRIM, AVOID, EXIT, with conviction low, med or high.

- **It names the action.** HOLD sells no share unless the thesis breaks. A plan that sells any
  shares as the base case, now or on a bounce or breakdown short of invalidation, is TRIM,
  however small the sale. EXIT sells everything.
- **For a holder the question is hold, trim or exit**, not whether to enter. Give that call with
  the quantity reasoning and what would take the rest off. An unknown holding status means the
  guidance is entry-framed; say why. Never infer a holding from the report's tone.
- **The call rests on the thesis, not the position.** Position size, an unrealized loss or gain,
  tax and "selling at the low" set the quantity and the trigger levels; they never move the call.
- **What the business is worth and what to do are separate.** An "overvalued but held, chart
  intact" HOLD is a different object from a "we could not see enough" HOLD.
- **Disagreement is the product.** If both sides still sound right after the debate, the call is
  usually HOLD or AVOID with the controlling uncertainty named, not a split-the-difference
  ACCUMULATE. The reverse failure is a HOLD that rests on comfort: when valuation, price
  structure and the debate's landing point agree, the call follows them.
- **Conviction caps size**: a low-conviction BUY is a starter allocation only.
- Every BUY or ACCUMULATE carries an entry zone, a stop and a target with the reward:risk stated,
  an allocation cap as % of the portfolio, and the size formula from `RULES.md`.
- Every call carries its **invalidation**, a checkable price level or fundamental event, and a
  **review trigger**.

## The debate [plugin]

The verdict-relevant axes are `valuation`, `growth_durability`, `balance_sheet_risk`,
`governance` and `technical_structure`.

- **Round 1**: each side makes its three strongest arguments, every one tied to a specific figure,
  level or citation in a leg report, plus what would change its mind. No outside facts and no
  generic narrative ("the sector is exciting", "markets are risky").
- **A later round is a turn, not a restatement.** Given the other side's previous round and the
  round's directive, a side either adds new load-bearing evidence, concedes explicitly, or
  reports `new_evidence: false`, which is an honest, debate-ending answer.
  - **cross-examine**: the sides argued different axes and neither case has been tested. Answer
    the opponent's axis directly and on its own terms before returning to your own.
  - **rebut**: both are on the same axis. Attack the evidence under the opposing claim: the
    source, the period, the basis, the arithmetic.
- **What ends a debate** is a concession, both sides restating one claim, no new evidence from
  either side after round 1, or round 3 (`decide_debate_round` applies this). Never
  non-engagement: arguments that never met have not survived scrutiny, and that caps conviction.
- **Missing evidence is uncertainty**, which either side may cite; it is not proof of
  concealment, and it weakens any argument that leans on it.
- **A concession is not a proof.** Before a conceded point decides the verdict, re-derive it from
  the leg report it cites; a forked agent arguing an assigned side conceding shows the argument
  was persuasive, not that the number is right.
- Weigh the debate by where it landed: the strongest surviving points after rebuttal, not the
  opening ones.

Side-specific weights: valuation alone is a weak lead bear argument unless extreme (a
low-confidence, terminal-heavy DCF is itself a bear point), so pair it with a deterioration. The
business, its industry, its financials and its management carry most of a decision, valuation a
fifth to a third [moneypurse:aDxVzunmnxg@01:27]. A
management integrity FAIL is near-fatal to a bull case: engage it or concede, never wave it away.
