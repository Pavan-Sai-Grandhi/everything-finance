# Fundamental analysis

**Consumers:** financial-analysis, valuation-analysis (the published-row vocabulary),
deep-analysis (the quick pass), portfolio-review (the drift check). **Sources, in priority
order:** `varsity-fa`, `moneypurse`, `plugin`.

The scorecard is **seven checks**, each PASS / FLAG / FAIL with the number that decided it.
`checklist_score` is the count of PASS out of the checks that apply. A check you cannot source is
a data gap: uncertainty, never a PASS. Every claim carries a number and the row or page it came
from; "strong fundamentals" without a metric is a defect.

The thresholds below are the plugin's bars for a non-financial company [plugin]. Varsity's
equity-research checklist is stricter in places: ROE above 25% (above 20% in its prose), gross
margin above 20%, revenue and PAT CAGR above 15%, positive operating cash flow, "not highly
leveraged"; its ratio chapters say only that D/E above 1 needs care, with no interest-cover number
[varsity-fa]. Call a threshold "the plugin's bar", and read each metric against the company's own
history and its peers.

**Banks, NBFCs and insurers** lend borrowed money and mix lending into their cash flow, so checks
3 and 4 are NOT-APPLICABLE, not FAIL. Judge balance-sheet safety on capital adequacy and asset
quality (GNPA/NNPA trend, provisioning), and returns on ROA and ROE, from the annual report and
investor presentation; `methods/sectors/banking.md` and `methods/sectors/insurance.md` list the KPIs.

## The seven checks

### 1. Returns: ROE above 15% sustained, ROCE above 15% and above the cost of capital

ROCE above the cost of capital is the moat signal: the business earns more than the money it
consumes; below it, the shortfall is paid out of equity until the reserves run down
[moneypurse:YA7sdbN4_68@01:52]. The 15% floor is roughly what an FD, PPF or a fund returned with
no effort at the time of the recording, so a business earning less is not paying for its risk
[moneypurse:5-ZdmTjODVk@12:28]. DuPont the ROE before trusting it: net margin (`Net Income` ÷ `Total Revenue`) × asset
turnover (`Total Revenue` ÷ `Total Assets`) × leverage (`Total Assets` ÷ `Total Equity`). An ROE
carried by the leverage term is a red flag and shows up again in check 3: shrinking the equity base
with debt is the usual way an ROE is dressed up [moneypurse:YA7sdbN4_68@15:25]. Read all three across
the available years.

### 2. Margins: stable or expanding operating margin over five years

Operating margin = `PBIT` ÷ `Total Revenue`. One-off spikes are suspect; the five-year shape is
the finding, and a step change needs a reason from the segment note or MD&A. Where the trend
moved, decompose it against `Raw Materials`, `Power & Fuel Cost`, `Employee Cost` and
`Selling & Administrative Expenses`, and name the line that moved.

Read the level only against same-sector peers [moneypurse:a5vIDbjhT1E@14:50]. A margin held above
a peer's year after year is pricing power from product, brand, technology or cost
[moneypurse:a5vIDbjhT1E@09:04]; a thin margin turned over fast can out-earn a fat one, which check
1's asset-turnover term shows [moneypurse:a5vIDbjhT1E@16:01].

### 3. Balance-sheet safety: D/E below 1, interest coverage above 3

D/E = `Total Debt` ÷ `Total Equity` (near zero preferred). Interest coverage = `PBIT` ÷
`Interest & Other Items`; the denominator bundles other financing items, so the coverage is
conservative; say so near the threshold. Read `Cash and Equivalent` for net debt: a gross-debt FLAG
on a company holding more cash than debt is wrong.

D/E between 1 and 2, or coverage between 2 and 3, is a FLAG that needs a stated reason. D/E
above 2, coverage below 2, or D/E climbing year on year (1.5 to 3) is a FAIL
[moneypurse:nMwjjn8kVK8@06:22] [moneypurse:nMwjjn8kVK8@06:37] [moneypurse:nMwjjn8kVK8@14:52].
Variant [moneypurse:nMwjjn8kVK8@13:48]: coverage struck on EBITDA, since depreciation is not
cash; the plugin's PBIT basis is the stricter and is the rule.

### 4. Cash reality: CFO tracking EBITDA over a cycle

Profit without cash is accounting. CFO is after tax and excludes treasury income, while `EBITDA`
is before tax and includes other income, so compare CFO with EBITDA minus tax paid minus material
other income, summed across a cycle; a ratio near 1 is the standard. A raw CFO/EBITDA of 0.7–0.8
for a full taxpayer is not a divergence by itself. A shortfall that persists after working capital
and tax means the earnings exist only on paper.

`cash_flow_10y` carries `Cash from Operating Activities` (CFO), `Capital Expenditures` and a
published `Free Cash Flow`. FCF positive across a cycle is the standard for a mature firm; a young
firm burning cash is a different question. Count the years as well as the sum: CFO positive in
at least seven or eight of the ten is the mark of a cash generator [moneypurse:5V5QugxC7cs@20:08]. Read `Changes in Working Capital` beside them: CFO
propped up by a working-capital release is the receivable-days finding from the other side.

### 5. Promoter holding and pledge: stable or rising, pledging not increasing

`shareholding` carries six quarters of `Promoters`, `FIIs`, `DIIs`, `Retail`, `Others` and
`Promoter Pledge (% of promoter holding)`; the pledge denominator is the promoter stake, not share
capital. Falling holding or rising pledge is the finding; why it moved belongs to
`methods/management.md`. An empty NSE pledge list means unknown, never zero.

### 6. Growth: revenue CAGR above 10% over five years for a growth thesis

Compute it on `Total Revenue` and read it beside EPS: `Earnings Per Share` ties to `Net Income`,
so revenue growth that does not reach EPS was eaten by cost, interest, tax or dilution (check
`Common Shares Outstanding`). A CAGR is a two-point measurement; state the endpoints and show the
years between if the path was lumpy.

### 7. Earnings quality: reported profit is the profit the business earned

Every multiple is struck on reported EPS, so a profit line inflated by something outside the
operating business misprices the company everywhere at once. In order of how often they matter:

- **Other income.** `Total Revenue` includes it with no separate line, so read the quarterly
  series. A large recurring other-income contribution (a mark-to-market gain on a listed stake,
  treasury income, a revaluation) is not operating profit even when it repeats. Management's own
  clean or adjusted PAT in the results release or concall is the primary source for the split.
- **Exceptional items**: the `Add/(Less): Exceptional items` row. Both directions matter: a charge
  that flatters next year's comparison is the same distortion.
- **Minority interest.** The feed's `Net Income` is already after the non-controlling share; any
  reconstruction from PBT deducts it exactly once, using the annual report's NCI line.

Compute **clean EPS**: strip recurring non-operating income and exceptional items from PBT, apply
the effective tax rate from the annual report's tax note, deduct the minority share once, and
divide by the weighted-average share count from the EPS note (`Common Shares Outstanding` is a
period-end count). State each step and its source; where a component is not disclosed at the
needed granularity, give a bracketed range with the assumption named.

| Adjustment vs reported PAT | Verdict |
|---|---|
| below 5% | PASS: reported earnings are the earnings |
| 5–20%, or any non-recurring size | FLAG: quote both figures wherever the multiple appears |
| above 20% and recurring | FAIL: every multiple struck on reported EPS is wrong |

Report `clean_eps` and `eps_adjustments` whatever the verdict; `none` is a finding.

## Read beside the seven, scored in the flags

- **Working-capital cycle.** Receivable days (`Total Receivables` ÷ `Total Revenue` × 365) and
  inventory days (`Total Inventory`). Receivable days rising while revenue grows is the
  channel-stuffing signature.
- **Liquidity.** Current ratio = `Total Current Assets` ÷ `Total Current Liabilities`, healthy at
  1.33–3; quick ratio = (`Total Current Assets` − `Total Inventory`) ÷ `Total Current Liabilities`,
  healthy at 1–2.5 [moneypurse:BCaSBH0dGjk@06:47] [moneypurse:BCaSBH0dGjk@14:10]. Below the band a
  small company may have to borrow or issue shares to meet the year's bills; a large, cash-efficient
  one can run 0.75–1 [moneypurse:BCaSBH0dGjk@07:02]. Above it, look for idle cash or swelling
  inventory and receivables [moneypurse:BCaSBH0dGjk@10:12]. Not for banks, NBFCs or insurers.
- **Goodwill.** A rising `Goodwill & Intangibles` line is acquisition-funded growth, with the
  impairment risk sitting there.
- **Payout.** A high `Payout Ratio %` beside a high-growth claim is a contradiction one side must
  answer.

## Reading the published rows

`get_company_fundamentals` returns ten fiscal years of balance sheet and cash flow, ten years plus
a trailing-twelve-month column of P&L, thirteen quarters, and six quarters of shareholding, under
Tickertape's own labels. Only the P&L has the TTM column, so the last column is a different
period across the three statements: pair by each table's `period_kinds`, never by index. Four
labels mean something other than they say:

| Row | What it is |
|---|---|
| `Total Revenue` | includes other income; the annual report's revenue note separates it |
| `EBITDA` | struck after other income, so not an operating profit; margins run on `PBIT`, and `EBITDA Margin %` inherits the caveat |
| `Taxes & Other Items` | tax plus non-controlling interest; never derive an effective tax rate from it |
| `Total Liabilities` | excludes equity; the balance-sheet total is `Total Liabilities & Shareholders Equity` |

Absent, so a labelled gap wherever a check needs it: capital work-in-progress, a separate
other-income line, and the effective tax rate.

## What the primary documents supply

`get_documents` returns each document's `text_path` and an `outline` of note line numbers. Read
the lines you need and cite the filing itself, a page or note, never a précis.

- **Annual report**: the tax note (required for any effective-rate work), auditor
  qualifications and emphases of matter, contingent liabilities, segment revenue and EBIT mix,
  related-party transactions, and the MD&A's account of what moved. The full cash-flow statement
  is the fallback for what `cash_flow_10y` does not break out.
- **Latest concall**: guidance actually given, and two or three management statements with the
  quarter. Read the Q&A as asked and answered.

Judge on the consolidated statements when subsidiaries carry the story, and on the standalone to
isolate the core business; a large gap between the two is a finding the segment note explains
[moneypurse:g35Wg5cj6zo@07:16].

Three to five specific, cited annual-report findings is the bar.

## The company overview

Self-contained: a reader meeting the company here comes away oriented. What it does; segment
revenue and EBIT mix in %, tying to the published `Total Revenue`; geography; flagship products
or brands; end-markets; and the moat named as a mechanism (switching cost, scale, licence, brand,
network), not an adjective, and tested against named competitors and substitutes, including ones
from outside the industry [moneypurse:5V5QugxC7cs@14:30]. Growth that rides a commodity price or a
one-off demand spike is not a moat: it reverses when the price or the spike does
[moneypurse:2bDua8Lmc48@17:18].

## Verdict

- **investment-grade**: the checks pass, or the flags are explained and bounded.
- **watch**: a real defect with a plausible path back, or too many gaps to judge.
- **avoid**: a check fails structurally: cash that does not follow profit, leverage-carried
  returns, working capital deteriorating without explanation, reported earnings that are not the
  earnings.

Confidence reflects how much of the scorecard came from primary documents rather than gaps.
