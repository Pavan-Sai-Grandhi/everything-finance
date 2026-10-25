---
name: mf-analysis
description: >-
  The plugin's mutual-fund authority — research or compare any named Indian fund, AND review the funds the user holds. Judges equity, index and debt funds on two pillars: the record (rolling returns, what every SIP in the fund earned and how often it ended in loss, the worst drawdown and how long it took to recover, all computed from NAV history) and the fund itself (what the full book is priced at, whether it matches the style it claims, how concentrated and how churned it is, whether size has caught up with it, and who runs it), diagnoses why a fund is trailing, and answers separately whether the category is worth adding to now. Runs `quick` (a fast descriptive digest other skills consume) or `deep` (the full verdict). Use whenever the user asks about a named mutual fund, SIP choice for a specific fund, comparing funds, "is X fund good", "why is X underperforming", whether to stop a SIP, a debt or gilt fund versus an FD, whether to switch or replace a fund, or wants to review their MF portfolio. Finding WHICH fund in a category to pick ("best smallcap fund", "where should my SIP go") is `discover funds` — this skill judges named funds.
argument-hint: "FUND NAME(s) / 'review my funds' [--quick] (e.g. 'Parag Parikh vs UTI Nifty 50', 'is Quant Small Cap good', 'SBI Magnum Gilt')"
allowed-tools: WebFetch, WebSearch, Read, Write, Skill, mcp__indmoney__*, mcp__plugin_everything-finance_indmoney__*, mcp__kite__*, mcp__plugin_everything-finance_kite__*, mcp__upstox__*, mcp__plugin_everything-finance_upstox__*, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-funds__*, mcp__plugin_everything-finance_finance-funds__*, mcp__finance-personal__resolve_holdings, mcp__plugin_everything-finance_finance-personal__resolve_holdings, mcp__finance-workflow__*, mcp__plugin_everything-finance_finance-workflow__*
---

# Mutual Fund Analysis

Judges **named** funds and the funds the user holds. A category question ("best flexicap fund",
or an empty `/mf-analysis`) hands off to `discover funds`, whose pick comes back here. Fund
depth lives here; the switch decision belongs to `portfolio-review`, which alone sees exit
loads, tax, allocation and overlap.

**Method:** `methods/funds.md` for the fund, `methods/market.md` → *Is now a good time to add?*
for the category. Every rule this skill applies is stated there with its source; this file is
the order to apply them in.

## Modes

- **`deep`** (default on direct invocation): the workflow below.
- **`quick`** (another skill asked, or `--quick`): descriptive only. NAV, AUM, Direct TER against
  the category, trailing 1/3/5Y returns, an AUM-stability flag, a **plan flag** when the holding
  is a Regular plan or an IDCW option, and held P&L when applicable. No look-through, no AMC
  research, never a category-rank percentile. Return `{scheme, grade_lite, key_numbers, flags,
  path}` and write only that digest to `mf-analysis.md`.

## Workflow: `deep`

### 1. Identify the fund and its branch

`resolve_fund` on each name for the AMFI scheme code, ISIN and Tickertape id (it prefers
Direct-Growth and says so if only Regular matched). Read the SEBI sub-category, then take one
branch:

- **active equity** (including hybrid with equity above 65%): steps 2–8;
- **index fund or ETF**: steps 2–4, then § *Index branch*;
- **debt fund**: step 2, then § *Debt branch*;
- **sector or thematic fund**: say first that it is a sector call, not a core holding, run the
  active-equity steps, and add the sector's own reading (`Skill: sector-analysis <sector>`)
  when the verdict hinges on it.

### 2. Plan hygiene and category fit

- **Plan and option**: Direct and Growth, or name the switch as an action for a held fund.
  Read `exitLoad` from `screen_funds` before any switch is suggested. A fund of funds pays two
  expense ratios; say so.
- **Category fit**: when the holder's horizon is known, test it against the category's floor in
  `methods/funds.md` → *The category comes before the fund*, and confirm it with the fund's own
  SIP record from step 4. A horizon shorter than the floor is the first finding, ahead of any
  fund merit. Unknown horizon is a stated assumption, not a silent one.

### 3. The category, now

`get_market_context(mode="quick")`. Take the cap tier the fund lives in (`NIFTY SMALLCAP 250`,
`NIFTY MIDCAP 150` or `NIFTY 50`), its valuation percentile, `relative.percentile_spread`,
`breadth.pct_above_sma200` and `market_posture`, and read them by `methods/market.md` → *Is now
a good time to add?*. The answer is about fresh money (now, or staged), never about stopping a
SIP. Keep it apart from the fund grade throughout.

### 4. Pillar 1: the record

`get_fund_scan` on the fund's own SEBI sub-category, with `top` raised to the `screened` count
if the fund is not already in the shortlist. A fund still absent failed a hard gate: say so,
quote the rejection count, and treat its peer standing as a gap; do not call again. Repeat
with `window="1y" | "3y" | "5y"`; each call returns that window's metrics. From each:

- **rolling** (mean, median, min, window count) and the fund's rank among gated peers: the
  consistency test is its standing across all three windows, not its best one;
- **sip**: the share of SIPs of that length that ended below the money put in, and the median
  and worst XIRR. Lead the record with the 5Y figure; quote the 1Y figure to set expectations
  for a new SIP;
- **drawdown**: depth, peak, trough, recovery date or "not yet recovered", days underwater;
- Sharpe, Sortino, alpha and standard deviation, compared within the category only; trailing
  returns arrive as `trailing_unscored` and never lead.

Then **whose record is it**: manager and tenure from the AMC's dated factsheet. If the manager
or the strategy changed inside a credited window, that window belongs to someone else; say
which windows survive. A fund too young for any window has no record: carry the manager's
record from earlier schemes, labelled as theirs, and let pillar 2 carry the verdict.

### 5. Pillar 2: the fund itself

- **Look-through**: `get_fund_lookthrough(mf_id=…)`: weighted P/E, P/B, ROE, P/B ÷ ROE, cap tilt
  by SEBI rank, concentration, sector mix, earnings-distress dispersion and coverage, with ratios
  withheld below the coverage floor. Compare the P/E with the category's (`category_pe` from the
  scan). Name the right multiple for a book heavy in banks or insurers.
- **Style claim against the book**: name the style the fund claims from its scheme document and
  the AMC's own letters, then test it as `methods/funds.md` → *Does the book match the claimed
  style?* sets out. Style drift from `allocation_history` in `get_fund_holdings`.
- **Construction**: holding count, top-10 weight, top-3 sector weight, the largest position,
  and the closet-indexer test (a long list, even weights and a low `tracking_error`).
- **Turnover** from the AMC factsheet, read against the claimed style. **Cash** from
  `equity_weight`.
- **Size**: AUM against the category's agility ceiling (the scan's `aum_agility`), the AUM
  trend, and for small and mid caps the liquidity stress-test days from the AMC's disclosure.
- **Cost**: Direct TER against the category, stated as a share of the 20-year corpus. For two
  funds, overlap % from the two complete holdings sets (`get_fund_holdings`).

### 6. Who runs it

Each claim with its source URL and date. The manager's other schemes and how they stand in their
own categories (from the scans when the verdict hinges on it, else a stated gap); the AMC's
bench and whether the philosophy is the house's or one person's; insiders' investment in the
scheme; conduct and regulatory history (SEBI orders, `get_news` on the AMC and the scheme); any
gating of inflows.

### 7. Diagnose, when it trails

If the fund sits in the bottom half of its category on the 1Y or 3Y rolling rank, or the holder
asks why it lags, work through `methods/funds.md` → *Diagnosing underperformance* in order and
name the cause the evidence supports. The same-style test uses the scan's peers: name two
funds of the same style and say whether they trail too. End with whether the cause is one that
passes or one that stays.

### 8. The verdict

Below, with the two or three deciding factors and every gap.

### Index branch

After steps 2–4: the decision fields are Direct TER and `tracking_error` against other funds
tracking the same index (`screen_funds` on the sub-category, matched by index name in the scheme
name), Direct against Direct, measured against the index's TRI. Alpha, capture and style checks
do not apply; look-through only confirms the book is the index. For an ETF, add its premium or
discount to NAV and its trading volume from `get_quote`, and say that a SIP needs an index
fund. For large caps, say whether an active fund the user named has beaten this index fund
after cost over rolling windows; if not, the index fund is the answer.

### Debt branch

In this order, from `methods/funds.md` → *Debt funds*:

1. **Horizon match**: the holder's horizon against the category's SEBI mandate.
2. **Credit quality**: the rating mix from the AMC factsheet (sovereign and AAA share, share
   below AA), the largest single issuer for a credit-risk fund, and whether any extra yield over
   a higher-quality peer is worth it.
3. **Rate sensitivity**: YTM, modified duration and TER from the dated factsheet into
   `run_debt_scenarios`; report its fall, flat and rise rows. A rate view is the holder's, if
   they state one; never supply one.
4. **The rest**: AUM (larger is better for debt), Direct TER, manager, and the tax rule.
5. **Against an FD**: the same pre-tax yield is taxed alike; compare on yield, liquidity and
   credit, not on tax.

Step 4 runs for a debt fund too: its drawdown episode shows what a rate or credit shock did.
Skip it for overnight and liquid funds, whose NAV barely moves.

## The verdict is a decision

End with one named recommendation and numbered concrete actions, in plain language: a shortlist
is the input to the verdict, not the verdict. Assume the reader does not work in finance; every
ratio that carries the argument gets a half-sentence of meaning. The grade is Hold-worthy,
Watch or Avoid; the category answer (add now, stage it, or wait) sits beside it, never inside
it. Every recommendation carries a review trigger that is not a price: a change in the book,
the manager, the mandate, the cost, the size, or the category's valuation percentile.

A held SIP in the red after one to three years is never by itself a reason to stop it. Say what
the fund's own SIP record shows at that length, and what would be a reason.

For a held fund, say explicitly whether it is unlikely to perform from here and name the
replacement, then hand the switch to `portfolio-review` (`Skill: portfolio-review`) and say why.

## Held funds

Read the book as `RULES.md` → *Reading your holdings* describes, `mf` slice. IndMoney has no
XIRR, so report held returns as P&L % unless a dated cash-flow XIRR is computed. Run each held
fund through the workflow, or `quick` when the caller only needs the digest. Flag every Regular
plan and IDCW option. With no personal source connected, say the personal layer is unavailable
and give the generic verdict.

## Output

In `artifacts/funds/<SCHEME>/<YYYY-MM-DD>/` (for a comparison, the slug `<a>-vs-<b>`):

- `mf-analysis.md`: the verdict and every step's findings, the record `get_prior_run` finds;
- `<SCHEME>.report.json`: the deck projection, shaped like
  `finance/report/fixtures/mf-analysis.sample.json`. The SIP view and the drawdown episode go
  in `perf.checks` and `perf.cards`; style claim, turnover, cash and size in
  `style.concentration`; the diagnosis in `peer.read`; the manager and AMC checks in
  `trust.checks`; the category answer in `cost.band`. A look-through ratio withheld for coverage
  is a gap slot;
- `mf-analysis.html`: `render_report(report_json=…, template="mf-analysis", out=…)`;
- the scan work paper `get_fund_scan` writes (`fund-scan.json`, at its returned `report_path`).

In chat, the verdict, the category answer and the look-through coverage ("ratios cover 95% of
the book").

## Alerts

When the user has or sets up a SIP in a researched fund and mentions its date, a `sip_due` alert:
`subject_type: fund`, `subject_id: <scheme-slug>`, `created_by: mf-analysis`, `due: <next SIP
date>`, `severity: info`, `text: "SIP due"`, `dedup_key: sip-<scheme-slug>`. It is a reminder,
never an instruction to transact.
