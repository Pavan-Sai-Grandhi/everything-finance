# Varsity due-diligence checklist (self-contained method)

Grounded in Zerodha Varsity — Fundamental Analysis (https://zerodha.com/varsity/module/fundamental-analysis/). The scorecard is **six checks**, each PASS / FLAG / FAIL with the number that decided it; `varsity_score` is the count of PASS. A check you cannot source is a **data gap**, which is uncertainty — never a neutral PASS.

Every claim carries a number and the row or page it came from. "Strong fundamentals" without a metric is a defect.

## The six checks

### 1. Returns — ROE > 15% sustained, ROCE > 15% and above the cost of capital

ROCE above the cost of capital is the moat signal: it is the one ratio that says the business earns more than the money it consumes. **DuPont the ROE** before you trust it — net margin (`Net Income` ÷ `Total Revenue`) × asset turnover (`Total Revenue` ÷ `Total Assets`) × leverage (`Total Assets` ÷ `Total Equity`). An ROE carried by the leverage term is a red flag, not a quality signal, and it will show up again in check 3. Read all three over the available fiscal years, not one.

### 2. Margins — stable or expanding operating margin over five years

**Operating margin = `PBIT` ÷ `Total Revenue`.** One-off spikes are suspect; the shape of the five-year trend is the finding, and a step change needs a reason from the segment note or MD&A. Where the trend moved, decompose it against the published cost lines — `Raw Materials`, `Power & Fuel Cost`, `Employee Cost`, `Selling & Administrative Expenses` — and name which one moved.

### 3. Balance-sheet safety — D/E < 1, interest coverage > 3

**D/E = `Total Debt` ÷ `Total Equity`** (near zero preferred for non-financials). **Interest coverage = `PBIT` ÷ `Interest & Other Items`**; because that denominator bundles other financing items, the coverage it yields is conservative — say so where it lands near the threshold. Cross-read `Cash and Equivalent` for net debt: a gross-debt FLAG on a company holding more cash than debt is a wrong FLAG.

### 4. Cash reality — CFO tracking EBITDA over a cycle

Profit without cash is accounting, not business. CFO/EBITDA ≈ 1 across a cycle; persistent divergence means the earnings are on paper. `cash_flow_10y` carries all three inputs: **`Cash from Operating Activities`** is CFO, **`Capital Expenditures`** is capex, and **`Free Cash Flow`** is a published line, not something you compute. It runs ten fiscal years — but the annual P&L appends an eleventh, trailing-twelve-month column that the cash flow does NOT, so the last cash-flow column (FY) is a different period from the last P&L column (TTM). Pair CFO to EBITDA by `period_kinds`, never by `[-1]`, or a fiscal-year CFO is silently divided by a TTM EBITDA. FCF positive across a cycle is the standard for a mature firm; a young firm burning cash is a different question, not automatically a fail. Read `Changes in Working Capital` beside them — CFO propped up by a working-capital release is the same finding the receivable-days check reaches from the other side.

### 5. Promoter holding & pledge — stable or rising, pledging not increasing

`shareholding` carries six quarters of `Promoters`, `FIIs`, `DIIs`, `Retail`, `Others` and **`Promoter Pledge (% of promoter holding)`** — note the denominator is the promoter stake, not the share capital. Falling promoter holding or rising pledge is the finding; *why* it moved is `management-analysis`'s call, not this one's.

### 6. Growth — revenue CAGR > 10% over five years for a growth thesis

Compute it off `Total Revenue`, and read it beside EPS: `Earnings Per Share` now ties to `Net Income`, so revenue growth that does not reach EPS has been eaten by cost, interest, tax or dilution — check `Common Shares Outstanding` for the dilution case. A CAGR is a two-point measurement; state the endpoints and show the intervening years if the path was lumpy.

## Beyond the six — read these, score them in the flags

- **Working-capital cycle.** Receivable days (`Total Receivables` ÷ `Total Revenue` × 365) and inventory days (`Total Inventory`). Receivable days creeping up while revenue grows is the channel-stuffing signature.
- **Goodwill.** A rising `Goodwill & Intangibles` line is acquisition-funded growth; the impairment risk sits there.
- **Payout.** `Payout Ratio %` and `Dividend Per Share` against the growth story — a high payout alongside a high-growth claim is a contradiction one of the two sides has to answer.

## Reading the published rows — the vocabulary and its traps

`get_company_fundamentals` returns **ten fiscal years** of balance sheet and cash flow, and **ten fiscal years plus a trailing-twelve-month column** of P&L, thirteen quarters, and **six quarters** of shareholding, under the source's own published labels. Because only the P&L carries the TTM column, the last column is not the same period across the three statements — pair by each table's `period_kinds` (FY/TTM/interim), never by index. Three of those labels also mean something other than what a reader expects:

| Row | What it actually is |
|---|---|
| `Total Revenue` | **Includes other income.** There is no separable other-income line, so a revenue figure and any margin struck on it carry treasury income inside them. Where other income is material, the annual report's revenue note separates it. |
| `EBITDA` | Struck **after** other income — it is not an operating profit. Margin work runs on `PBIT`. The derived `EBITDA Margin %` row inherits the same caveat. |
| `Taxes & Other Items` | Tax **plus** non-controlling interest, not tax. **Never derive an effective tax rate from it** — for a group with minorities it overstates the rate by several points. The effective rate comes from the annual report's tax note. |
| `Total Liabilities` | Liabilities **excluding** equity. The balance-sheet total is `Total Liabilities & Shareholders Equity`. Reading the first as the second halves the number. |

Absent entirely, and therefore a labelled gap wherever a check needs one: capital work-in-progress, any separable other-income line, and the effective tax rate.

## What the primary documents must supply

`get_documents` returns each document's `text_path`; `Read` it and cite the filing itself — a page or note reference — never a précis of it.

- **Annual report** — the **tax note** is *required* from here for any effective-rate work; nothing on the feed can supply it. Then read for: auditor qualifications and emphases of matter, contingent liabilities, segment revenue and EBIT mix, related-party transactions, and the MD&A's account of what moved. The full cash-flow statement is the fallback for what `cash_flow_10y` does not break out — the non-cash adjustments, the working-capital movement line by line, and acquisition spend sitting inside investing.
- **Latest concall** — guidance actually given, and two or three management statements with the quarter cited. Read the Q&A as asked and answered.

Three to five specific, cited annual-report findings is the bar. A finding with no page behind it is not a finding.

## The Company Overview

Self-contained: a reader meeting the company here should come away oriented without opening anything else. What it does; segment revenue and EBIT mix in %; geography split; flagship products or brands; the end-markets it sells into; and the moat that protects the economics — named as a mechanism (switching cost, scale, licence, brand, network), not as an adjective. Sourced from the annual report's segment note and MD&A, with the mix percentages tying to the published `Total Revenue`.

## Verdict

**investment-grade** — the six checks pass or the flags are explained and bounded; the business is one you could own on the numbers. **watch** — a real defect with a plausible path back, or too many gaps to judge. **avoid** — a check fails structurally (cash that does not follow profit, leverage-carried returns, deteriorating working capital with no explanation).

Confidence low/med/high reflects how much of the scorecard came from primary documents versus how much stayed a gap. Missing evidence is uncertainty, not a neutral pass.
