# DCF valuation method — Damodaran's story-driven FCFF (self-contained)

Distilled from Aswath Damodaran's *The Little Book of Valuation* / *Narrative and Numbers* and the connecting-the-story-with-the-numbers framing. This file is the method; `scripts/dcf.py` is the arithmetic. The engine is faithful but dumb — **it computes exactly what you feed it.** Your whole job is to build a coherent *story* and turn it into a small set of *sourced, consistent* inputs. A clean-looking per-share number on top of an incoherent story is worthless and, with real money at stake, dangerous.

## The one idea

A DCF is not a spreadsheet exercise — it is a **story disciplined by arithmetic**. Every input must answer a "why":
- Why this **revenue growth**? → total addressable market (TAM) + the company's share trajectory + a competitive edge that justifies taking share.
- Why this **operating margin**? → benchmark the steady-state margin of the best 3–5 peers; you only assume above-peer margins if the story (brand, scale, cost edge) earns it.
- Why this **reinvestment**? → growth must be *paid for*. The **sales-to-capital ratio** says how many ₹ of new sales each ₹ of investment buys.

If the story and the numbers disagree (margins no competitor has achieved, growth the TAM can't support, growth with no reinvestment), the valuation breaks. *Be an optimist or a pessimist, but be a consistent one.*

## The model the script implements (FCFF)

For each explicit-forecast year (default 10):

```
revenue_t      = revenue_{t-1} × (1 + growth_t)
EBIT_t         = revenue_t × operating_margin_t        # pre-tax operating income
NOPAT_t        = EBIT_t × (1 − tax_rate_t)             # after-tax operating income
reinvestment_t = (revenue_t − revenue_{t-1}) / sales_to_capital_t
FCFF_t         = NOPAT_t − reinvestment_t
PV_t           = FCFF_t / Π(1 + WACC_i) for i ≤ t
```

Terminal value (a *stable-growth* firm, growth tied to reinvestment via ROIC):

```
g_T (terminal growth)   ≤ risk-free rate         # nothing outgrows the economy forever
reinvest_rate_T         = g_T / terminal_ROIC    # consistent: growth needs reinvestment
FCFF_{N+1}              = revenue_N×(1+g_T) × terminal_margin × (1−tax_T) × (1 − reinvest_rate_T)
TV_N                    = FCFF_{N+1} / (WACC_T − g_T)
```

Bridge to per share:

```
EV        = Σ PV(FCFF) + PV(TV)
Equity    = EV − net_debt + non-operating_cash − minority_interest
Per share = Equity / shares_outstanding
Margin of safety = intrinsic/share ÷ current_price − 1
```

## Worked example — a story turned into numbers (runnable)

The bundled `--selftest` *is* a worked example; run `python3 scripts/dcf.py --selftest` to see every number. The story it encodes:

> "A ₹1,000 Cr-revenue firm with a real but fading edge: it grows 15%/yr for 3 years while the edge holds, then fades to 4% (≈ the economy) by year 10. Today's 12% operating margin widens to 18% by year 5 as scale kicks in — no higher, because that's where the best peers sit. Each ₹1 of new capital buys ₹2 of sales (sales-to-capital 2.0). Discount at 11%. In perpetuity it grows 4% and earns 13% on new capital (a modest, durable moat). Net debt ₹500 Cr, ₹100 Cr surplus cash, 100 Cr shares."

Result: intrinsic ≈ **₹18.2/share**, terminal value ≈ 63% of EV, no flags. If the market price were ₹60, the margin of safety is **−70%** — the story doesn't support the price, so either the story is too conservative (defend a higher growth/margin with evidence) or the stock is dear. That tension *is* the output: the model surfaces where your narrative and the price disagree. Note how every assumption traces to a "why" — that is the whole discipline.

## The valuation levers (and where to source each — authenticity is non-negotiable)

| Lever | Source it from | Sanity rule |
|---|---|---|
| Base revenue | screener.in TTM / latest FY (consolidated) | use the actual last-year figure, not a guess |
| Revenue growth path | TAM studies + company guidance (concall) + history; fade to ≈ GDP+inflation by year N | peak growth > 30% must be defended against TAM and reinvestment |
| Operating margin path | company's own trend + peer steady-state margins | above-peer margins need a stated moat; peak > 40% is rare |
| Tax rate | effective tax from P&L; trend toward statutory | India ≈ 25% statutory for most |
| Sales-to-capital | historical ΔRevenue ÷ Δ(net fixed assets + working capital); peer benchmark | asset-light (software) high (3–5+); capital-heavy (utilities, autos) low (0.5–1.5) |
| WACC | cost of equity (risk-free + β×ERP) and after-tax cost of debt, weighted | India risk-free ≈ 10y G-sec; ERP from Damodaran's India number |
| Terminal growth | ≤ risk-free rate, usually ≈ long-run nominal GDP | **never** above the risk-free rate |
| Terminal ROIC | the return the mature firm earns on new capital | > WACC only if a durable moat persists into perpetuity |
| Net debt, cash, shares, minority | latest balance sheet + shareholding | consolidated; diluted share count |

**Use one consistent money unit (₹ Crore) for every money input and ₹ Crore for the share count too, so per-share lands in ₹.** Mixing units is the most common silent error.

## Capitalisation adjustments Damodaran insists on

- **Operating leases** → capitalise (asset + debt). Materially changes leverage and WACC for lease-heavy businesses (retail, airlines, QSR). Add the lease debt into `net_debt`; if you can, move the lease expense out of operating costs (raises EBIT) — at minimum, *note* the distortion if you can't.
- **R&D** → treat as capital, not a period expense, for R&D-heavy firms (pharma, semis, tech): it builds an asset amortised over its useful life, giving a truer operating margin and invested capital. If you don't restate, flag that reported margins understate the steady state.

If you cannot make these adjustments precisely, **say so in the report as a data gap** rather than quietly ignoring them.

## Running it

```bash
# fill assets/dcf-inputs.example.yml with sourced numbers, then:
python3 <skill-dir>/scripts/dcf.py --inputs <your-inputs>.yml \
    --sensitivity --out artifacts/YYYY-MM-DD/dcf-<SYMBOL>.json
# or a quick worked example:
python3 <skill-dir>/scripts/dcf.py --selftest
```

The script emits a per-year FCFF table, EV/equity/per-share, the WACC×terminal-growth **sensitivity grid**, and **flags**. Exit 3 means the model is invalid (e.g. WACC ≤ g) — fix the inputs, don't paper over it.

## The flags the engine raises (read them as Damodaran's reality checks)

- `TERMINAL_GROWTH_ABOVE_RISKFREE` — cap g_T at the risk-free rate. Always.
- `TERMINAL_VALUE_HEAVY` (> 75% of EV in the terminal value) — the valuation rests on year-10+ assumptions; widen the sensitivity range and trust it less.
- `NEGATIVE_ENTERPRISE_VALUE` — explicit cash flows are net-negative; your reinvestment is too heavy or margins too thin for the growth you assumed. The model is unusable until the story is fixed.
- `NO_TERMINAL_EXCESS_RETURN` — terminal ROIC ≤ WACC means no value creation in perpetuity (correct for a no-moat firm; a red flag if you claimed a moat).
- `HIGH_MARGIN_ASSUMPTION` / `HIGH_GROWTH_ASSUMPTION` — defend these against a real peer and the TAM, or pull them down.

## Reverse DCF — let the price tell you its story

The forward DCF asks "given my story, what is it worth?" The **reverse DCF** flips it: "given the market price, what story must already be true?" It is often the single most decision-useful output, because it sidesteps the endless argument over your assumptions and instead tests the *market's* — which are usually far more aggressive than people realise.

Mechanically, the engine holds every assumption fixed except one lever and shifts that lever's whole path by a constant until intrinsic value/share equals the price:

```bash
python3 scripts/dcf.py --inputs <file>.yml --reverse              # implied revenue growth (default)
python3 scripts/dcf.py --inputs <file>.yml --reverse-solve margin # implied operating margin
```

It reports the **implied year-1 growth and the implied N-year revenue CAGR** (or the implied margin). Then you do the judgement: compare that number to the company's own history, management's guidance, and the size of the TAM. *Example (the bundled selftest): a ₹60 price implies ~28% revenue CAGR for a decade against a 15% base story — a demand the business has never met, which condemns the price more convincingly than any single fair-value figure.*

When it returns `solved: false`, that is a finding, not a failure: either the price sits **below** what even conservative assumptions support (the stock is cheap on that lever), or **above** any credible range (richly priced / the lever can't justify it — and if terminal ROIC ≤ WACC, growth adds no value, so the price can't be a growth story at all). Use growth as the primary lever for growth stories; use the margin version when the bull case is really a margin-expansion thesis.

## Final discipline (the devil's-advocate pass)

1. **Show a range, not a point.** Lead with the sensitivity grid; the single per-share number is the midpoint of an honest band, never a precise target.
2. **Margin of safety, not fair value = buy.** Damodaran/Graham: require a discount (commonly ≥ 25–30% below intrinsic) before acting, sized to how terminal-heavy and assumption-laden the model is.
3. **Break your own story.** If a competitor launched a cheaper product tomorrow, which input collapses? If the whole thesis hangs on one heroic assumption, say that out loud.
4. **DCF is a sanity band for stable cash flows.** For erratic/early-stage/financial firms, DCF is fragile — lean on relative valuation (P/E, P/B, P/S vs peers and own history) and say which you trust more and why.

Every number in the output must trace back to a sourced input. If you had to estimate one, label it an estimate. Not investment advice — personal research tool.
