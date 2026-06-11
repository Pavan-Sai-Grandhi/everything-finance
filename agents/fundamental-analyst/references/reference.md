# Fundamental analysis method (self-contained)

Distilled from Zerodha Varsity — Fundamental Analysis module (https://zerodha.com/varsity/module/fundamental-analysis/, 16 chapters). This agent is forked; everything it needs is in this file.

## Due-diligence checklist (Varsity ch. 12–13)

**Profitability & efficiency**
- ROE > 15% sustained — DuPont it (margin × turnover × leverage); leverage-driven ROE is a red flag
- ROCE > 15%; ROCE > cost of capital = moat signal
- EBITDA margin stable/expanding over 5y; one-off spikes are suspect

**Balance-sheet safety**
- D/E < 1 (near 0 preferred for non-financials); interest coverage > 3
- Promoter pledging: any increase = flag; stake stable or rising
- Working-capital cycle not deteriorating (receivable days creeping up = channel-stuffing risk)

**Cash reality**
- CFO tracking EBITDA (CFO/EBITDA ≈ 1 over a cycle); profit without cash is accounting
- FCF positive across a cycle for mature firms

**Growth & valuation**
- Revenue CAGR > 10% (5y) for a growth thesis
- P/E vs own 5y band and peer median; P/B for financials; P/S for loss-makers
- DCF as a sanity band with margin of safety — distrust terminal-value-heavy valuations

## Annual report — priority reading order (ch. 3)

MD&A (management's story + risks) → auditor's report (qualifications = stop) → related-party transactions → contingent liabilities → cash flow statement → revenue-recognition notes. Concalls: guidance changes, capex plans, margin commentary, dodged questions.

## screener.in extraction map

- `https://www.screener.in/company/<SYMBOL>/consolidated/` — ratios, 10y trends, quarterly results, shareholding, peer table (prefer consolidated; fall back to standalone and say so)
- Same page, "Documents" — annual report PDFs, concall transcripts/PPTs
- Extract tables only, never full page HTML
- Authenticated features need `SCREENER_SESSION_ID`/`SCREENER_CSRF_TOKEN` from `~/.claude/.env` (sessionid/csrftoken cookies); public company pages need no auth

## Report discipline

Every claim carries a number and a source (quarter, page, table). "Strong fundamentals" without a metric is a defect. Missing documents → proceed on screener.in numbers, mark the gap.
