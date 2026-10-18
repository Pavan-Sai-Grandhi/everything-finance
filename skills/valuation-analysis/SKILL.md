---
name: valuation-analysis
description: Work out what an Indian stock is actually worth and whether today's price is defensible — a story-driven discounted-cash-flow (FCFF) model in Aswath Damodaran's style for intrinsic value, the multiples read (P/E vs peer median and own band, PEG, EV/EBITDA, P/B·RoE for financials) for relative value, the two reconciled into one Undervalued / Fair / Overvalued stance weighted by a DCF-confidence grade. Projects revenue growth and operating margins from a coherent narrative, funds that growth via the sales-to-capital ratio, discounts free cash flow to the firm at WACC, adds a disciplined terminal value, and reports intrinsic value as a range with a margin of safety, a terminal-WACC×terminal-growth check, and reality-check flags. Reach for this skill whenever the user wants a valuation or intrinsic/fair value of one company — phrasings like "what is X really worth", "is X overvalued or undervalued", "justify this P/E", "should I buy at ₹Y", "build me a DCF", "value this stock", or wanting the numbers behind a buy/sell decision — even if they never say the word "DCF". It is for single-stock equity value specifically (not mutual-fund picks → mf-analysis, not the full multi-agent debate → deep-analysis).
argument-hint: "TICKER — every model input is sourced from the filings; the engine only computes what it is given"
allowed-tools: Read, Write, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-workflow__get_prior_run, mcp__plugin_everything-finance_finance-workflow__get_prior_run
---

# Valuation Analysis: intrinsic and relative, reconciled

A model, not a price target. A terminal-heavy or fragile DCF is reported with low confidence,
never hidden. It informs a decision; it never sizes a position.

**Method:** `methods/valuation.md`; `methods/fundamentals.md` → *Reading the published rows*.

## Workflow

0. **Prior run**: `get_prior_run(skill="dcf", subject=SYMBOL)`. If one exists, read it for the
   story and open the report with `prior run: <path> (<date>)` and what changed (fair value then
   and now, which assumption moved). The prior run supplies the story, never the numbers: every
   lever is re-sourced from this run's fetch. One that genuinely cannot be (net cash and minority
   interest are the usual pair) is marked `carried from <date>, not re-derived` in the
   Assumptions table and named in Data gaps.
1. **Base inputs**: `get_company_fundamentals(SYMBOL)` (ten-year statements, ratios, peers),
   `get_documents(SYMBOL)` (the tax note at `outline.tax_note` is the only acceptable source for
   `tax_rate`), and `get_quote(SYMBOL)` for the price; each once, reading the cached text after.
   Value revenue from operations and operating EBIT, excluding interest, investment and other
   non-operating income, and add the related cash and investments only in the equity bridge. If
   the feed exposes only `Total Revenue`, derive the operating base from the annual report or mark
   the DCF unverified; never value that income in operations and add its asset again.
2. **Diagnose, then build the story.** Set `lifecycle_stage` before any number. Build the growth
   path from the story, then set it beside `get_analyst_estimates`' revenue and EPS growth for the
   next two fiscal years; check Yahoo's year-ago figures against the annual report first, since a
   basis mismatch voids the comparison. A path well away from a consensus of three or more
   analysts says why in the Assumptions table; the consensus checks the story and is never the
   base. Then the margin path, sales-to-capital path, WACC, terminal growth and terminal ROIC,
   each with a one-line reason. The four market inputs come from `get_risk_inputs`: its 10Y yield,
   `default_spread`, `country_risk_premium` and `mature_erp` go into `wacc_buildup` as returned,
   each cited with its `source` and `as_of`; only a field it reports as a gap may be an estimate,
   labelled with its reason. Terminal growth, country premium, beta and failure probability are
   conclusions of the diagnosis, never defaults.
3. **Write the inputs file** from `assets/dcf-inputs.example.yml` to the path deep-analysis gave
   you, or standalone to `artifacts/stocks/<SYMBOL>/<YYYY-MM-DD>/dcf-inputs.yml`, every value with
   its source and date as a comment. Always include `timing` (`base_period_end` is the last day of the
   `base_revenue` period, `valuation_date` the date of the price) and `current_ebit_margin`
   (operating EBIT ÷ revenue from operations, latest FY), which lets the engine catch an EBITDA
   margin passed as an EBIT margin. For a bank, NBFC or insurer set `model_shape: equity`.
4. **Run the engine** on that file, so the audit trail and the run are one input:
   `run_dcf(ticker=SYMBOL, inputs=<the inputs file path>, relative=<step 6>, sensitivity=true,
   story=true, reverse=true)`. The full result lands at the returned `dcf_path`.
   `reverse` solves for growth against the price; `reverse_solve="margin"` gives the implied
   margin and `reverse_target=<price>` tests another price. `ok:false` means the model rejected an
   input (WACC at or below terminal growth, say): fix the input, never work around the guard.
5. **Read the flags, both grids, the reverse DCF and the market view.** A gap naming an unsourced
   discount-rate input means re-source from this run's `get_risk_inputs` and rerun. Copy
   `market_view`'s margin of safety into `dcf_mos_market` and its
   `index_value_to_price_at_method_rate` into the inputs table. Answer every flag in the write-up;
   `MARGIN_BASIS_UNCHECKED`, `MARGIN_BASIS_SUSPECT`, stale risk inputs or an unresolved
   operating/non-operating split prohibit high confidence. Where a lever genuinely changes, record
   `was → now` with the reason and cite both `dcf_path` files. Lead with the `story_sensitivity`
   grid as the range; read `story_sensitivity.duration` as alternative scenarios, judged against
   business evidence, never extended to close the gap to price. A reverse DCF with
   `solved: false` establishes nothing about cheap or dear.
6. **The relative read**: `relative = {pe, pe_basis, peer_pe, peer_pe_basis, own_pe_history,
   growth}`.
   - `pe`: the trailing P/E on earnings you have checked. The financials leg runs in the same wave,
     so scan the last two years of other income and exceptional items yourself for a one-off worth
     more than ~5% of PAT. Found one: strike the P/E on post-tax clean EPS with
     `pe_basis: adjusted`. Found none: the published TTM `Stock P/E`, `pe_basis: reported`. Could
     not look: `pe_basis: reported (unchecked)` and a gap. Carry `eps_adjustments` either way.
   - `peer_pe`: the `ttm_pe` on each `peers` row (the peer list deep-analysis passed, when it did),
     `peer_pe_basis: reported`. `get_stock_ratios` is only for a ratio a peer row lacks, and its
     P/E field is `ttm_pe`, never the annualised `pe`.
   - `own_pe_history`: the company's own band. `growth`: expected EPS growth for PEG, a labelled
     estimate with its basis; prefer next-year consensus from three or more analysts whose
     year-ago EPS matches the published one.

   Report every `relative.gaps` entry: a void peer half changes what the stance may rest on. Add
   EV/EBITDA against peers where capital structures differ, and P/B with RoE for a lender or
   insurer.
7. **Reconcile, grade and call it** per the method. A cap-tier valuation stance handed in is
   context for the relative read only.

## Report

Fill `assets/dcf-report.example.md` at the path deep-analysis gave you, or standalone at
`artifacts/stocks/<SYMBOL>/<YYYY-MM-DD>/dcf.md`. Its leading `valuation-block` is machine-read: keep
every field name exactly as the template has it. Paste the engine's `story_sensitivity_md` and
`sensitivity_md` verbatim; engine output is never retyped. Label the cash flow exactly: FCFF
discounted at WACC for an operating company, an equity cash flow discounted at cost of equity for
a financial.

Return only the `valuation-block` fields plus `path`.
