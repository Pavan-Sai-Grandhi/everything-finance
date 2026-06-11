# Deep-analysis knowledge base

Grounded in Zerodha Varsity — Fundamental Analysis (https://zerodha.com/varsity/module/fundamental-analysis/, 16 chapters) and Technical Analysis (https://zerodha.com/varsity/module/technical-analysis/). Fetched and summarized 2026-06-10.

## Fundamental due-diligence checklist (Varsity ch. 12–13, "Investment Due Diligence" / "Equity Research")

The fundamental-analyst agent works through this; the bull/bear researchers attack or defend each line:

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
- DCF as a sanity band, not a price: Varsity's emphasis — apply a margin of safety, buy only meaningfully below intrinsic estimate, and distrust terminal-value-heavy valuations

## Reading annual reports & concalls (ch. 3)

Priority order when time-boxed: MD&A (management's own story + risks) → auditor's report (qualifications = stop) → related-party transactions → contingent liabilities → cash flow statement → notes on revenue recognition. In concalls: guidance changes, capex plans, margin commentary, and what management dodges. Quote specifics (numbers, page/quarter) in the report — no vague "fundamentals look strong".

## Technical layer

The technical-analyst agent carries its own Varsity TA method (bundled in that agent's `references/`): trend stage (Dow), S/R map, pattern, volume, RSI/MACD as confirmation. For a deep-dive its job is broader than a trade signal: where is the stock in its primary trend, what are the levels that would invalidate a bullish or bearish thesis.

## Debate protocol

- Bull and bear researchers must each produce: 3 strongest arguments, each tied to evidence from phase-1 reports; 1 explicit rebuttal of the opposing side's likely best point; what would change their mind.
- The portfolio-manager verdict must state: position (Buy/Accumulate/Hold/Avoid/Exit), conviction (low/med/high), suggested allocation cap (% of portfolio), entry zone if Buy, and the invalidation (price level or fundamental event that kills the thesis).
- Disagreement is the product: if bull and bear both sound right, the verdict should usually be Hold/Avoid with the specific uncertainty named.

## screener.in extraction map

- `https://www.screener.in/company/<SYMBOL>/consolidated/` — ratios table, quarterly results, shareholding trend (prefer consolidated; fall back to standalone and say so)
- "Documents" section on the same page — annual report PDFs, concall transcripts/notes/PPT links
- Peer comparison table — sector median P/E, ROCE for relative valuation
Extract tables only; never the whole page.
