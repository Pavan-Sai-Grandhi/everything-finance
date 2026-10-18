---
name: mf-analysis
description: >-
  The plugin's mutual-fund authority — research or compare any named Indian fund, AND review the funds the user holds, across two pillars: past performance (rolling returns and drawdown computed from NAV history, risk measures from the category screen) and forward-looking quality (full look-through portfolio valuation, style + drift, AMC & manager trust), read against live market context. Runs `quick` (a fast descriptive digest other skills consume) or `deep` (the full two-pillar verdict). Use whenever the user asks about a named mutual fund, SIP choice for a specific fund, comparing funds, "is X fund good", whether to switch or replace a fund, or wants to review their MF portfolio. Finding WHICH fund in a category to pick ("best smallcap fund", "where should my SIP go") is `discover funds` — this skill judges named funds.
argument-hint: "FUND NAME(s) / 'review my funds' [--quick] (e.g. 'Parag Parikh vs UTI Nifty 50', 'is Quant Small Cap good')"
allowed-tools: WebFetch, WebSearch, Read, Write, Skill, mcp__indmoney__*, mcp__plugin_everything-finance_indmoney__*, mcp__kite__*, mcp__plugin_everything-finance_kite__*, mcp__upstox__*, mcp__plugin_everything-finance_upstox__*, mcp__finance-market__*, mcp__plugin_everything-finance_finance-market__*, mcp__finance-company__*, mcp__plugin_everything-finance_finance-company__*, mcp__finance-funds__*, mcp__plugin_everything-finance_finance-funds__*, mcp__finance-personal__resolve_holdings, mcp__plugin_everything-finance_finance-personal__resolve_holdings, mcp__finance-workflow__*, mcp__plugin_everything-finance_finance-workflow__*
---

# Mutual Fund Analysis

Judges **named** funds and the funds the user holds. A category question ("best flexicap fund",
or an empty `/mf-analysis`) hands off to `discover funds`, whose pick comes back here. Fund depth
lives here; the switch decision belongs to `portfolio-review`, which alone sees exit loads, tax,
allocation and overlap.

**Method:** `methods/funds.md`.

## Modes

- **`deep`** (default on direct invocation): the two-pillar verdict below.
- **`quick`** (another skill asked, or `--quick`): descriptive only: NAV, AUM, expense against the
  category, returns 1/3/5Y, an AUM-stability flag, and held P&L when applicable. No look-through,
  no AMC research, never a category-rank percentile. Return `{scheme, grade_lite, key_numbers,
  path}` and write only that digest to `mf-analysis.md`.

## Workflow: `deep`

1. **The market first**: `get_market_context(mode="quick")`. Take the cap-tier valuation the fund
   lives in (`NIFTY SMALLCAP 250`, `NIFTY MIDCAP 150` or `NIFTY 50`), `relative.percentile_spread`
   and `market_posture`. "Is this category worth adding to now?" and "is this fund good?" are
   different questions: answer them separately.
2. **Resolve**: `resolve_fund` on each name (it prefers Direct-Growth and says so if only Regular
   matched) for the AMFI scheme code, ISIN and Tickertape id the other tools take.
3. **Pillar 1, past performance**: `get_fund_scan` on the fund's own SEBI sub-category, once, with
   `top` raised to the `screened` count if the fund is not already in the shortlist. A fund still
   absent failed a hard gate: say so, quote the rejection count, and treat its peer standing as a
   gap; do not call again. Otherwise its `metrics` block is the record: daily-rolled returns
   (mean, median, min) with their window counts, max drawdown, NAV span and the confidence it
   earns, and standing among gated peers. One window per call, so repeat with `window="1y" | "3y"
   | "5y"`. Sortino, Sharpe and alpha come from the category screen, compared within the category
   only. Trailing returns arrive as `trailing_unscored` because their endpoints decide them.
4. **Pillar 2, forward quality**:
   - **look-through**: `get_fund_lookthrough(mf_id=…)`: weighted P/E, P/B, ROE, P/B ÷ ROE, cap
     tilt by SEBI rank, concentration, sector mix, earnings-distress dispersion and coverage,
     with ratios withheld below the coverage floor;
   - **AMC and manager trust**: pedigree, manager tenure over the credited window, alpha
     consistency, AUM stability, governance flags, each claim with its source URL (AMC
     factsheets, SEBI, AMFI, fund news);
   - **cost and overlap**: Direct-plan TER against the category; for two funds, overlap % from
     the two complete holdings sets (`get_fund_holdings`).
5. **The verdict** (below), with the two or three deciding factors and every gap.

## The verdict is a decision

End with one named recommendation and numbered concrete actions, in plain language: a shortlist
is the input to the verdict, not the verdict. Assume the reader does not work in finance; every
ratio that carries the argument gets a half-sentence of meaning. Every recommendation carries a
review trigger that is not a price: a change in the book, the manager, the mandate, the cost, or
the category's valuation percentile.

For a held fund, say explicitly whether it is unlikely to perform from here and name the
replacement, then hand the switch to `portfolio-review` (`Skill: portfolio-review`) and say why.

## Held funds

Read the book as `RULES.md` → *Reading your holdings* describes, `mf` slice. IndMoney has no
XIRR, so report held returns as P&L % unless a dated cash-flow XIRR is computed. Run each held
fund through the pillars, or `quick` when the caller only needs the digest. With no personal
source connected, say the personal layer is unavailable and give the generic verdict.

## Output

In `artifacts/funds/<SCHEME>/<YYYY-MM-DD>/` (for a comparison, the slug `<a>-vs-<b>`):

- `mf-analysis.md`: the verdict and both pillars' metrics, the record `get_prior_run` finds;
- `<SCHEME>.report.json`: the deck projection, shaped like
  `finance/report/fixtures/mf-analysis.sample.json` (12 slides). A look-through ratio withheld for
  coverage is a gap slot;
- `mf-analysis.html`: `render_report(report_json=…, template="mf-analysis", out=…)`;
- the scan work paper `get_fund_scan` writes (`fund-scan.json`, at its returned `report_path`).

In chat, the verdict with the look-through coverage stated ("ratios cover 95% of the book").

## Alerts

When the user has or sets up a SIP in a researched fund and mentions its date, a `sip_due` alert:
`subject_type: fund`, `subject_id: <scheme-slug>`, `created_by: mf-analysis`, `due: <next SIP
date>`, `severity: info`, `text: "SIP due"`, `dedup_key: sip-<scheme-slug>`. It is a reminder,
never an instruction to transact.
