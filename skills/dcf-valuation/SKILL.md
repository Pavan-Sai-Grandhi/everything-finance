---
name: dcf-valuation
description: Compute what an Indian stock is actually worth per share with a story-driven discounted-cash-flow (FCFF) model in Aswath Damodaran's style — project revenue growth and operating margins from a coherent narrative, fund that growth via the sales-to-capital ratio, discount free cash flow to the firm at WACC, add a disciplined terminal value, and report intrinsic value as a range with a margin of safety, a WACC×terminal-growth sensitivity grid, and reality-check flags. Reach for this skill whenever the user wants a valuation or intrinsic/fair value of one company — phrasings like "what is X really worth", "is X overvalued or undervalued", "justify this P/E", "should I buy at ₹Y", "build me a DCF", "value this stock", or wanting the numbers behind a buy/sell decision — even if they never say the word "DCF". It is for single-stock equity intrinsic value specifically (not mutual-fund picks → mf-analysis, not historical strategy testing → backtest, not the full multi-agent debate → deep-analysis, which invokes this skill for its valuation leg).
argument-hint: "TICKER (or 'inputs <file.yml>') — supply sourced financials; the model only computes what you feed it"
allowed-tools: Read, Write, Bash, WebFetch, mcp__finance-market__*, mcp__finance-company__*
---

# DCF Valuation — story-driven intrinsic value (Damodaran FCFF)

Read `references/reference.md` first — it owns the method: the life-cycle diagnosis, the levers and where to source each, country risk and beta, the terminal excess-return call, the post-operating adjustments, the capitalisation adjustments, every engine flag, and the devil's-advocate discipline. This SKILL is the workflow on top of the shared engine `finance/compute/dcf.py`.

**Sources for this skill only:** `finance-company` `get_company_fundamentals` (consolidated financials, and the `documents` links to the annual report / filings, which you read with `WebFetch`) and `finance-market` `get_quote` (current price).

## Workflow

0. **Check for a prior run.** Call `paths.latest_prior("dcf", SYMBOL)` — if an earlier `dcf.md` exists, read it for context so this valuation stays consistent with the last story, and open the report with a one-line `prior run: <path> (<date>)` link noting what changed (fair value then→now, which assumption moved). No prior run is the normal first-time case.
1. **Gather the sourced base inputs** — base revenue (latest FY/TTM), the revenue-growth and operating-margin history, effective tax rate, net debt, cash & non-operating assets, minority interest, diluted shares, historical **sales-to-capital** (≈ ΔRevenue ÷ Δ(net fixed assets + working capital)), and CMP for the margin-of-safety comparison. Invoked as `deep-analysis`'s valuation leg, these arrive in the data-pack — do not re-fetch.
2. **Diagnose the life-cycle stage, then build the story.** Set `lifecycle_stage` before any number, then the growth path, margin path, sales-to-capital path, WACC, terminal growth and terminal ROIC, each with a one-line justification. The reference's § "Diagnose first" governs all of it: **terminal growth, country premium, beta and failure probability are conclusions of the diagnosis, never defaults.**
3. **Write the inputs file** from `assets/dcf-inputs.example.yml` → `artifacts/stocks/<SYMBOL>/YYYY-MM-DD/dcf-inputs.yml` (`paths.stock_dir(symbol, date)`), every value carrying a source comment.
4. **Run the engine** (forward valuation + both sensitivity grids + reverse DCF):
   ```bash
   PYTHONPATH=<plugin> python3 -m finance.compute.dcf --inputs artifacts/stocks/<SYMBOL>/YYYY-MM-DD/dcf-inputs.yml \
       --sensitivity --story --reverse --out artifacts/stocks/<SYMBOL>/YYYY-MM-DD/dcf.json
   ```
   Exit 3 = model-invalid (e.g. WACC ≤ terminal growth) — fix the input, never override the guard. The script auto-installs `pyyaml` if missing. `--reverse` defaults to solving for **growth** against `current_price`; add `--reverse-solve margin` for the implied-margin version, or `--reverse-target <price>` to test a different price.
5. **Read the flags, BOTH grids, and the reverse DCF.** Address every flag raised in the write-up. **Lead with the `story_sensitivity` grid (growth × steady-state margin) as the range**, WACC×g as a secondary check, and read `story_sensitivity.duration` for a premature fade. Then act on the reverse DCF: if the price-implied growth is one no one in the sector has sustained, that *is* the verdict; if it is roughly what the company has already demonstrated and you can name the moat, **lengthen the high-growth window, re-run, and report that as the base case** (extend the duration, never bump the rate). On `solved: false`, read its `reason`.

## Produce this report

Fill `assets/dcf-report.example.md` → `artifacts/stocks/<SYMBOL>/YYYY-MM-DD/dcf.md`:

- **Stage diagnosis** (one line): the life-cycle stage and the country-risk exposure (λ) — these set everything below.
- **The story** (3–4 sentences): the narrative the numbers encode.
- **Assumptions table**: each lever, its value/path, the source or justification.
- **Intrinsic value**: per share, equity value, EV — with the **story-driver (growth × margin) grid as the headline range**, and the WACC×g grid as a secondary check. Where a post-operating adjustment applies, report the clean going-concern value and the adjusted value separately (failure haircut for a distressed/young firm, complexity discount for a governance-heavy conglomerate).
- **Margin of safety** vs the current price, and the discount you'd require given how assumption-laden/terminal-heavy the model is.
- **Reverse DCF — what the price implies**: the growth (or margin) today's price is pricing in, set against history / guidance / TAM. State plainly whether that implied assumption is plausible — and whether it merely matches the company's demonstrated track record (in which case the price is defensible and your base case was too conservative). This is often the most decision-useful line in the whole report.
- **Flags & honesty checks**: every engine flag, plus your own devil's-advocate ("which assumption, if wrong, breaks this?").
- **Data gaps**: anything you couldn't source or couldn't capitalise (leases/R&D) — labelled, not hidden.

## Boundaries

A young, loss-making, cash-burning company is **in scope** — that is exactly what story-driven DCF is *for*. Build revenue from TAM × share × take-rate, set the steady-state margin from where the business model lands at scale, fund growth with the sales-to-capital ratio, discount at a country-risk-inclusive WACC, and apply a `failure_probability`. Never refuse a valuation just because earnings are negative today.

DCF is genuinely **fragile** in two cases, where you should lean on relative valuation (P/E, P/B, P/S vs peers and own 5y band) and say which you trust and why: **(1) banks / NBFCs / insurers** (FCFF is ill-defined — value on equity/P/B/RoE instead), and **(2) violently cyclical / commodity firms** where fuel, forex, or commodity swings throw FCFF around so hard that any single forecast is arbitrary (normalise through a cycle and treat the DCF as one weak input). The fix for a *young* firm is a failure probability and a story-driver range, **not** abandoning the DCF.

End on the model's own limit: this is a model, not a price target.
