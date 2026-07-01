# Deep-analysis knowledge base

Grounded in Zerodha Varsity — Fundamental Analysis (https://zerodha.com/varsity/module/fundamental-analysis/, 16 chapters) and Technical Analysis (https://zerodha.com/varsity/module/technical-analysis/). Fetched and summarized 2026-06-10.

## Fundamental due-diligence checklist (Varsity ch. 12–13, "Investment Due Diligence" / "Equity Research")

Source data is fetched once by `fundamentals-data` into a shared pack; the `financials-analyst` works through this checklist off that pack (with `management-analyst` and `valuation-analyst` as its sibling legs); the bull/bear researchers attack or defend each line:

**Profitability & efficiency**
- ROE > 15% sustained (DuPont it: margin × turnover × leverage — leverage-driven ROE is a red flag)
- ROCE > 15%; ROCE > cost of capital is the moat signal
- EBITDA margin stable or expanding over 5 years; one-off margin spikes are suspect

**Balance-sheet safety**
- Debt/Equity < 1 (near 0 preferred for non-financials); interest coverage > 3
- No persistent pledging of promoter shares; promoter holding stable or rising
- Working-capital cycle not deteriorating (receivable days creeping up = channel stuffing risk)

**Cash reality check**
- CFO positive and tracking EBITDA (CFO/EBITDA ≈ 1 over a cycle); profits without cash are accounting, not business
- FCF positive across a cycle for mature firms

**Growth & valuation**
- Revenue CAGR > 10% (5y) for a growth thesis
- P/E vs own 5y band and vs sector median; P/B < 1.5 with decent ROE is the classic value zone (Varsity), P/S for loss-makers
- Valuation is **multi-method**: the `valuation-analyst` triangulates **intrinsic** (story-driven FCFF DCF) and **relative** (P/E, PEG, peer-median multiples, EV/EBITDA, own historical band) into one combined stance — Undervalued / Fair / Overvalued. Per Damodaran, multiples are shortcuts to the same DCF drivers, so a difference vs peers is explained by fundamentals (growth/risk) first, before being called mis-pricing.
- The combined stance is **weighted by DCF confidence** (low/med/high, graded from terminal-value weight and assumption stretch). High-confidence DCF leads the call (margin of safety vs intrinsic); a low-confidence one (terminal-heavy, aggressive, or a bank/violent cyclical) is a sanity band only and the call leans on the relative read. Buy meaningfully below intrinsic estimate; never let a low-confidence DCF drive a buy on intrinsic value alone (Varsity's distrust of terminal-value-heavy valuations, made explicit). The relative figures are computed deterministically by `scripts/relval.py` (median not mean; PEG with its equal-risk/linearity caveat flagged).

## Reading annual reports & concalls (ch. 3)

Priority order when time-boxed: MD&A (management's own story + risks) → auditor's report (qualifications = stop) → related-party transactions → contingent liabilities → cash flow statement → notes on revenue recognition. In concalls: guidance changes, capex plans, margin commentary, and what management dodges. Quote specifics (numbers, page/quarter) in the report — no vague "fundamentals look strong".

## Technical layer

The technical-analyst agent carries its own Varsity TA method (bundled in that agent's `references/`): trend stage (Dow), S/R map, pattern, volume, RSI/MACD as confirmation. For a deep-dive its job is broader than a trade signal: where is the stock in its primary trend, what are the levels that would invalidate a bullish or bearish thesis.

## Sector layer

The `sector-analyst` agent (its own bundled Varsity sector method) places the stock in its sector: the sector's relative strength and rotation state, the signature KPIs, the live tailwinds/headwinds, and whether the stock is a leader or laggard within it. A great company in a lagging sector, or a laggard inside a leading one, changes the call — so the bull/bear researchers and the portfolio-manager weigh this read alongside the technical, fundamental, and news legs, not as decoration.

## Depth modes (token-tiered)

The run scales to the question — see `SKILL.md` for the resolution logic:

- **`quick`** (~4 agents) — lite data-pack (screener envelope only); three legs (technical, financials, valuation); a single `contest-researcher` stages both sides in one pass instead of a bull/bear loop. Banner-labelled "Quick read — not full diligence". Management/news/sector do not run.
- **`standard`** (default, ~7–8 agents) — full data-pack; all six legs; one debate round, escalating to a second **only on genuine divergence**.
- **`deep`** (~12 agents) — full data-pack; all six legs; the full up-to-3-rounds convergence loop. Auto-selected for live holdings / open trades.

## Debate protocol

- **`deep`** runs **up to 3 rounds, with early-stop on convergence**. Round 1: bull and bear each produce 3 strongest arguments tied to phase-1 evidence + what would change their mind. Round r>1: each side is fed the other's previous-round report and must add new load-bearing evidence or explicitly concede — restating a prior round is not a valid turn. After each round the orchestrator checks whether either side introduced a *new* evidence-tied argument; if neither did, the debate stops there.
- **`standard`** runs **one round, escalating to a second only on genuine divergence**, decided deterministically by `scripts/escalation.py` from the two round-1 digest blocks: both top points must sit on the *same* verdict-relevant axis (valuation / growth durability / balance-sheet risk / governance / technical structure) with distinct evidence-tied claims and no concession. Top points that talk past each other, agree, or include a concession → stop at round 1. One round is the baseline; the second is opt-in on evidence.
- **`quick`** replaces the debate with a single `contest-researcher` pass (strongest bull + strongest bear + a balance-of-evidence lean). A `genuinely split` lean prompts a one-line suggestion to re-run at standard/deep; it never auto-escalates.
- A FAIL on the management integrity gate is near-fatal to the bull case — the side must engage it or concede; the portfolio-manager treats it as an AVOID override. (Management runs only in standard/deep; in quick its absence is weighed as uncertainty.)
- The portfolio-manager judges the full transcript (or the contest) once at the end and must state: position (Buy/Accumulate/Hold/Avoid/Exit), conviction (low/med/high), suggested allocation cap (% of portfolio), entry zone if Buy, and the invalidation (price level or fundamental event that kills the thesis). It weights the DCF by its stated confidence (above).
- Disagreement is the product: if bull and bear both sound right after the rounds, the verdict should usually be Hold/Avoid with the specific uncertainty named.

## screener.in extraction map

- `https://www.screener.in/company/<SYMBOL>/consolidated/` — ratios table, quarterly results, shareholding trend (prefer consolidated; fall back to standalone and say so)
- "Documents" section on the same page — annual report PDFs, concall transcripts/notes/PPT links
- Peer comparison table — sector median P/E, ROCE for relative valuation
Extract tables only; never the whole page.
