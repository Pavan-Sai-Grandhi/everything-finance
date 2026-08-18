---
name: mf-analysis
description: The plugin's mutual-fund authority — research or compare any Indian fund, scan a whole SEBI category down to a shortlist, AND review the funds the user holds, across two pillars: past performance (rolling returns and drawdown computed from NAV history, risk measures from the category screen) and forward-looking quality (full look-through portfolio valuation, style + drift, AMC & manager trust), read against live market context. Runs `quick` (a fast descriptive digest other skills consume) or `deep` (the full two-pillar verdict). Use whenever the user asks about a mutual fund, SIP choice, comparing funds, "is X fund good", which index/flexicap/smallcap fund to pick, whether to switch or replace a fund, or wants to review their MF portfolio — even casual phrasings like "where should my SIP go".
argument-hint: "FUND NAME(s) / category / 'review my funds' [--quick] (e.g. 'best smallcap fund', 'Parag Parikh vs UTI Nifty 50')"
allowed-tools: WebFetch, WebSearch, Read, Write, Bash, Skill, mcp__indmoney__*, mcp__kite__*, mcp__upstox__*, mcp__finance-market__*, mcp__finance-company__*, mcp__finance-funds__*
---

# Mutual Fund Analysis

The single fund authority: research/compare any fund, **scan a category down to a shortlist**, and review the funds the user holds. Two pillars — **past performance** (NAV-derived) and **forward-looking quality** (look-through valuation, style, AMC/manager trust) — so a verdict reflects *potential*, not just trailing returns. `portfolio-review` defers all fund-level depth here.

Read `references/reference.md` for the grounding: the Varsity performance hierarchy, the forward-looking framework, and the analytics that decide close calls (P/B ÷ ROE, earnings-distress dispersion, coverage as a gate).

## Sources for this skill only

- **`resolve_fund`** — name → AMFI scheme code + ISIN + plan + Tickertape fund id. Call first; the other tools take ids, not names.
- **`screen_funds`** — the raw universe of a SEBI sub-category (every fund with AUM, TER, returns, risk, cap mix).
- **`get_fund_scan`** — that universe gated and scored into a ranked shortlist, rolling returns and drawdown recomputed from NAV history.
- **`get_fund_lookthrough`** — the priced read of what a fund owns.
- **`get_fund_holdings`** — the **complete** position list plus sector weights, 90-99% weight coverage.
- **`get_stock_ratios`** — per-holding P/E, P/B, ROE and **`mrktCapRank`** (the SEBI cap rank).
- **`get_nav_history`** — the daily NAV series the rolling-return and drawdown math is computed from.
- **`get_market_context`** — the market this analysis is read against.
- **`get_company_fundamentals`** — the cross-check for a specific holding when a ratio looks wrong.
- **IndMoney / broker** (`mcp__indmoney__*`, `mcp__kite__*`, read-only) — **only for what the user owns**: which funds are held, units, invested value, current value, XIRR, SIPs. Nothing else.
- AMC/manager trust is qualitative web research (AMC factsheets, SEBI/AMFI, ValueResearch, fund news) — **every claim carries its source URL**. No other sites.

> **The personal/decision boundary (CLAUDE.md rule 3) is a hard rule here:** a personal source never supplies a number that shapes the verdict — holdings come from `get_fund_holdings`, cap classification from `get_stock_ratios.mrktCapRank`, returns and ranks computed from `get_nav_history`, news from `get_news`.

## Depth modes

- **`deep`** (default on direct user invocation) — the full analysis below.
- **`quick`** (another skill requested it, or the user passed `--quick`) — descriptive only: NAV, AUM, expense vs category, returns 1/3/5Y, AUM-stability flag, and held XIRR when applicable. **No look-through fetch, no AMC research, and never a category-rank percentile.** Return the compact digest `{scheme, grade_lite, key_numbers, path}` and skip straight to Output.

## Workflow (`deep`)

1. **Read the market first.** Call `get_market_context` (mode `quick`). Take `valuation["NIFTY SMALLCAP 250" | "NIFTY MIDCAP 150" | "NIFTY 50"]` for the tier the fund lives in, plus `relative.percentile_spread` and `market_posture`. **"Is this category worth adding to now?" and "which fund inside it is best?" are different questions** — answer them separately and say so.

2. **Resolve or scan.**
   - Named funds → `resolve_fund` (prefers Direct-Growth; says so if only Regular matched).
   - **A category question** ("best smallcap fund") → run the scan:

     ```
     get_fund_scan(category="Small Cap Fund", top=5,
                   market_context="artifacts/market-analysis/<date>.json")
     ```

     It applies the Varsity checklist as **hard gates** (Direct-Growth only, AUM viability floor, fund age ≥ the window being credited, TER ceiling that catches a Regular-plan figure mislabelled Direct), then scores the survivors on rolling return, worst-window return, max drawdown, Sortino, cost and cap purity — **rolling returns and drawdown computed from NAV history, never taken from a vendor field**. It returns the ranked shortlist and a tally of what was gated out; the shortlist JSON at `report_path` carries the components behind each score. `market_context` carries the cap tier's valuation stance through verbatim, so the "which fund" and "is this category worth adding to now" answers stay separate.

3. **Pillar 1 — past performance.** The scan's per-fund `metrics` block *is* the record, recomputed from NAV history: daily-rolled rolling returns (mean / median / **min**) with the count of windows behind them, max drawdown, NAV span and the confidence that span earns. For a **named** fund, scan its own SEBI sub-category with `top` raised until the fund has its own row — that also gives its standing among peers. One window per call, so repeat with `window="1y" | "3y" | "5y"`. Sortino/Sharpe/alpha ride along from the category screen — compare them **within the category only**. Trailing 1/3/5Y arrive as `trailing_unscored` because their endpoints decide them. A fund whose *minimum* 5Y rolling return is positive has never lost money for any 5-year holder — that is the kind of statement to produce.

4. **Pillar 2 — forward-looking quality.**
   - **Look-through** — `get_fund_lookthrough(mf_id=<MF_ID>)`. Returns weighted portfolio P/E, P/B, ROE, **P/B ÷ ROE**, cap-tilt by **SEBI market-cap rank**, top-5/top-10 and Herfindahl concentration, sector mix, **earnings-distress dispersion** (share of book at ROE < 8%) and coverage. **Coverage gates the numbers**: below the threshold the ratios are withheld rather than printed as fact.
   - **AMC / manager trust** — fund-house pedigree, manager tenure ≥ 3y over the window being credited, alpha consistency, AUM stability, governance flags. Each claim sourced.
   - **Cost & overlap** — Direct-plan TER vs category; for two funds, portfolio overlap % from the two full holdings sets.

5. **Verdict — make the call.** See below. State the 2-3 deciding factors and every data gap.

## The verdict is a decision, not a menu

End with **one named recommendation and numbered concrete actions**, in plain language. Do not present a ranked shortlist and leave the choice open — a shortlist is the *input* to the verdict, not the verdict. Assume the reader does not work in finance: no unexplained jargon, and every ratio that carries the argument gets a half-sentence of what it means.

Every recommendation carries a **review trigger that is not a price** — a change in the fund's book, manager, mandate, cost or the category's valuation percentile that would change the answer. "Review if it falls 10%" is not a trigger; "review if the manager changes or small-cap P/B drops below its median" is.

**When the user holds funds:** say explicitly whether a **held** fund is unlikely to perform from here and name the replacement. But **the switch decision belongs to `portfolio-review`** — it alone sees exit loads, capital-gains tax, the whole book's allocation and overlap. So hand off (`Skill: portfolio-review`) rather than deciding the rebalance here, and say why: this skill judges *funds*, that skill judges *the book*.

## Held-fund review

MF rows come through the shared `finance/compute/holdings.py` resolver, **not** a raw IndMoney read. The resolver runs in script context and cannot call MCP tools, so invoke IndMoney `networth_holdings`, write the raw payload under `paths.tmp_dir("holdings")`, then take the fund slice:

```bash
PYTHONPATH=<plugin> python3 -m finance.compute.holdings --indmoney <ind.json> --mf-only
```

Each row carries invested / current / XIRR. Cap-split comes from the look-through (`get_stock_ratios.mrktCapRank`), never from a personal source's own breakdown field. Run each held fund through the pillars above (or `quick` when the caller only needs the digest). If neither IndMoney nor a broker is connected, **say the personalised layer is unavailable and give the generic verdict** — never infer a holding.

## Output

Write to `artifacts/funds/<SCHEME>/YYYY-MM-DD/` (`paths.fund_dir`; for a comparison use the slug `<a>-vs-<b>`, for a category scan `<category>-scan`):
- `mf-analysis.md` — the verdict + both-pillar metrics (the durable record `paths.latest_prior` finds on a re-run).
- `mf-analysis.html` — the rich render of `assets/fund-comparison.html`.
- the scan and look-through work papers — `get_fund_scan` writes `fund-scan.json` and returns its `report_path`.

`quick` writes only the compact digest to `mf-analysis.md` — no HTML, no work papers.

Summarize the verdict in chat with the look-through coverage stated ("ratios cover 95% of the book").

## Data integrity

- Portfolio ratios come only from the look-through compute — every figure traceable to the cached holdings weights and per-holding ratios.
- **Coverage is a gate, not a footnote.** Ratios computed on a partial book are withheld, not caveated: a partial-book number is not an approximation, it describes a different fund.
- **Cap-tilt is classified by SEBI market-cap rank** (top 100 large / 101-250 mid / 251+ small), never by absolute ₹Cr bands — a small-cap fund's biggest holdings are by construction its largest names, so bands report it as "0% small-cap".
- **Never explain a trailing-window number with a calendar-year number.** "The trailing 1Y is weak but CY2025 was worse" compares two different windows and is not an argument.
- **Low ROE is not automatically a cycle trough.** Distinguish a cyclical industry at the bottom of its cycle from a company underperforming a healthy sector — the first can mean-revert, the second is a mistake in the book. A P/E on collapsed earnings is not cheap.
- Holdings staleness, look-through coverage and every gated-out fund are always surfaced.

## Alerts this skill raises (via `finance/compute/alerts.py`)

If the user has (or sets up) a SIP in a researched fund and mentions its date, raise a **`sip_due`** alert (`subject: {type: fund, id: <scheme-slug>}`, `created_by: mf-analysis`, `trigger: {due: <next-SIP-date>}`, `severity: info`, `action.text: "SIP due"`, `dedup_key: sip-<scheme-slug>`). It is a date reminder `daily-brief` lists among due actions; never an instruction to transact.
