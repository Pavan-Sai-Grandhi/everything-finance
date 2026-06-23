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
- DCF gated by its own confidence: the `valuation-analyst` grades each DCF low/med/high from terminal-value weight and assumption stretch. A high-confidence DCF is a real valuation input (margin of safety vs intrinsic estimate); a low-confidence one (terminal-heavy, aggressive, or a bank/violent cyclical) is a sanity band only and the call leans on relative P/E·P/B. Buy meaningfully below intrinsic estimate; never let a low-confidence DCF drive a buy on intrinsic value alone (Varsity's distrust of terminal-value-heavy valuations, made explicit).

## Reading annual reports & concalls (ch. 3)

Priority order when time-boxed: MD&A (management's own story + risks) → auditor's report (qualifications = stop) → related-party transactions → contingent liabilities → cash flow statement → notes on revenue recognition. In concalls: guidance changes, capex plans, margin commentary, and what management dodges. Quote specifics (numbers, page/quarter) in the report — no vague "fundamentals look strong".

## Technical layer

The technical-analyst agent carries its own Varsity TA method (bundled in that agent's `references/`): trend stage (Dow), S/R map, pattern, volume, RSI/MACD as confirmation. For a deep-dive its job is broader than a trade signal: where is the stock in its primary trend, what are the levels that would invalidate a bullish or bearish thesis.

## Sector layer

The `sector-analyst` agent (its own bundled Varsity sector method) places the stock in its sector: the sector's relative strength and rotation state, the signature KPIs, the live tailwinds/headwinds, and whether the stock is a leader or laggard within it. A great company in a lagging sector, or a laggard inside a leading one, changes the call — so the bull/bear researchers and the portfolio-manager weigh this read alongside the technical, fundamental, and news legs, not as decoration.

## Debate protocol

- The debate runs **up to 3 rounds, with early-stop on convergence**. Round 1: bull and bear each produce 3 strongest arguments tied to phase-1 evidence + what would change their mind. Round r>1: each side is fed the other's previous-round report and must add new load-bearing evidence or explicitly concede — restating a prior round is not a valid turn. After each round the orchestrator checks whether either side introduced a *new* evidence-tied argument; if neither did, the debate stops there.
- A FAIL on the management integrity gate is near-fatal to the bull case — the side must engage it or concede; the portfolio-manager treats it as an AVOID override.
- The portfolio-manager judges the full transcript once at the end and must state: position (Buy/Accumulate/Hold/Avoid/Exit), conviction (low/med/high), suggested allocation cap (% of portfolio), entry zone if Buy, and the invalidation (price level or fundamental event that kills the thesis). It weights the DCF by its stated confidence (above).
- Disagreement is the product: if bull and bear both sound right after the rounds, the verdict should usually be Hold/Avoid with the specific uncertainty named.

## screener.in extraction map

- `https://www.screener.in/company/<SYMBOL>/consolidated/` — ratios table, quarterly results, shareholding trend (prefer consolidated; fall back to standalone and say so)
- "Documents" section on the same page — annual report PDFs, concall transcripts/notes/PPT links
- Peer comparison table — sector median P/E, ROCE for relative valuation
Extract tables only; never the whole page.
