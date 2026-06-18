---
name: mf-research
description: Research Indian mutual funds — NAV history, rolling returns, category comparison, expense/risk metrics, and a fund-quality verdict. Use whenever the user asks about a mutual fund, SIP choice, comparing funds, "is X fund good", which index/flexicap/smallcap fund to pick, or wants to review their MF portfolio — even casual phrasings like "where should my SIP go".
argument-hint: "FUND NAME(s) or category (e.g. 'flexicap', 'Parag Parikh vs UTI Nifty 50')"
allowed-tools: WebFetch, Read, Write, Bash
---

# Mutual Fund Research

Read `references/reference.md` for the Varsity personal-finance grounding (rolling returns over point-to-point, risk metrics, selection criteria).

**Data sources for this skill only:** AMFI NAV data via `https://api.mfapi.in/mf` (free JSON: search `https://api.mfapi.in/mf/search?q=NAME`, history `https://api.mfapi.in/mf/<code>`), Tickertape and Moneycontrol fund pages for expense ratio, AUM, portfolio composition. No other sites.

## Workflow

1. **Resolve funds.** Map the user's fund names to mfapi scheme codes (prefer Direct-Growth plans; say so if only Regular found). For a category request, pick the 4–6 largest/most-held funds in that category plus the relevant index fund as benchmark.

2. **Compute, don't eyeball.** Write a small Python script (pandas optional, stdlib fine) over the NAV history JSON:
   - 1/3/5-year **rolling returns** (daily-rolled, annualized): mean, median, min, % of windows beating the benchmark fund (align windows by identical start dates across funds)
   - Point-to-point 1/3/5Y CAGR (for familiarity, clearly labeled inferior)
   - Max drawdown and worst 1-year window
   - Sharpe: use a 6% risk-free rate (₹ repo-rate proxy) and compare within category only
   Cache downloaded NAV JSON under `artifacts/cache/mf/` and write the computed metrics to `artifacts/cache/mf/results.json` — every number in the report must be reproducible from these files.

3. **Qualitative layer** — expense ratio (Direct), AUM, fund manager tenure, top-10 holdings concentration, portfolio overlap if comparing two equity funds. Known failure modes (hit in testing): Moneycontrol hard-blocks WebFetch, and Tickertape's `-M_XXXX` slugs are unguessable — a wrong slug **silently serves a different fund's data**. So: use Playwright for these sites when available; with WebFetch, try the AMC's own factsheet page first; and ALWAYS verify the fund name on the fetched page matches the requested fund before using any number. Cache what you used as `artifacts/cache/mf/qualitative.json` (values + source URLs) so claims are verifiable later. If no source works, report "qualitative layer unavailable" as a data gap — never guess TER/AUM.

4. **Verdict per fund** using the reference.md criteria: Hold-worthy / Watch / Avoid, with the 2–3 deciding factors. For category questions, a ranked shortlist with the boring-but-correct default named first (Varsity leans index-first for large-cap exposure).

## Output

Write to the fund's entity dir `artifacts/funds/<SCHEME>/YYYY-MM-DD/` (`paths.fund_dir(scheme, date)`; for a two-fund comparison use the slug `<scheme-a>-vs-<scheme-b>` as the scheme key so the comparison sits in its own folder):
- `mf-research.md` — the written verdict + the metrics table (the durable, greppable record; this is the file `paths.latest_prior("mf-research", scheme)` finds on a re-run).
- `mf-research.html` — the rich render of `assets/fund-comparison.html` (rolling-return table, drawdown, cost comparison; benchmark row's own "consistency" cell is "—").

Summarize the verdict in chat. When comparing two active equity funds, include a portfolio-overlap line (top-holdings intersection %) if holdings data was obtainable. Note data gaps (e.g., fund too young for 5Y rolling). End with: "Not investment advice — personal research tool."

## Alerts this skill raises (via `lib/alerts.py`)

If the user has (or sets up) a SIP in a researched fund and mentions its date, raise a **`sip_due`** alert (`subject: {type: fund, id: <scheme-slug>}`, `created_by: mf-research`, `trigger: {due: <next-SIP-date>}`, `severity: info`, `action.text: "SIP due"`, `dedup_key: sip-<scheme-slug>`). It is a date reminder `daily-brief` lists among due actions; never an instruction to transact.
