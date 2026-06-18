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
| WACC | cost of equity (risk-free + β×mature-ERP + λ×country-risk premium) and after-tax cost of debt, weighted | country risk scales with operating exposure λ, not incorporation — see § Diagnose first |
| Terminal growth | ≤ risk-free rate, **in the currency of the cash flows** | for a ₹ domestic firm that is the ~6.5–7% rupee G-sec, not a 4% US habit — see § Diagnose first |
| Terminal ROIC | the return the mature firm earns on new capital | > WACC only if a durable moat persists into perpetuity |
| Net debt, cash, shares, minority | latest balance sheet + shareholding | consolidated; diluted share count |

**Use one consistent money unit (₹ Crore) for every money input and ₹ Crore for the share count too, so per-share lands in ₹.** Mixing units is the most common silent error.

## Diagnose first: the corporate life cycle decides which levers move

Damodaran's first-principles method is identical in every market and at every age; what changes is *which inputs are hard, which are reliable, and which adjustments are warranted*. The single most important step — before any number — is to **place the company on its life cycle**, because the stage tells you how to think, not what to type. Set `lifecycle_stage` accordingly. Resist the temptation to import fixed "India numbers" — a flat terminal growth, a flat country premium, a standard failure probability. Each of those is an *output of the diagnosis below*, not a constant; reason it out per company.

| Stage (`lifecycle_stage`) | What drives value / is hard | Narrative vs numbers | Terminal value | Failure / distress | Cost of capital |
|---|---|---|---|---|---|
| `start_up` / `young_growth` | TAM, can it scale, unit economics; everything is hard | story dominates | speculative; value lives in the future — **terminal-heavy is correct** | real and material — apply `failure_probability` | high, fades as it de-risks |
| `high_growth` | growth rate **and how long it lasts**, path to margins | balanced, numbers start to bind | large share of value; build it from durable growth + steady-state margin | apply if still loss-making / cash-burning | moderating |
| `mature_growth` / `mature_stable` | margins, capital allocation, moat *duration*; history constrains you | numbers dominate — deviations from history need a reason | big but **disciplined by the demonstrated business**; g_T ≈ economy | ≈ 0 for a profitable cash generator — **don't apply it** | ≈ market average; small WACC changes matter |
| `decline` | cash extraction, asset/liquidation value, return of capital | liquidation mechanics dominate | small / near-zero / negative; **g_T ≤ 0** and cross-check break-up value | elevated again | elevated (distress) |

Reading this table replaces a dozen hardcoded rules: *whether* value should sit in the terminal year, *whether* a failure probability belongs, *whether* you lean on the story or the history, and *where* terminal growth should land all fall out of the stage. The engine's flags are tuned to it (`lifecycle_stage` relaxes the terminal-heavy flag for young firms and turns it into a red flag — plus a positive-terminal-growth warning — for declining ones).

### Don't fade high growth prematurely (young / high-growth)
The default 10-year fade-to-GDP assumes a company decelerates on a fixed schedule for no business reason. India's runways are often long (low penetration, young demographics, formalisation). A firm *demonstrably* compounding 30%+ should keep doing so for as long as its edge and TAM support, then fade to a *durable* rate. Set `years: 15` for a genuinely young firm so a 15–20-year story isn't crushed into 10, and read `story_sensitivity.duration`: if two extra years of the company's **demonstrated** growth closes most of the gap to price, your base case was fading too hard — that, not "overvaluation," is the finding. Build the revenue top-down from **TAM × share × take-rate** (Zomato, SpaceX) so the growth answers to a market size you can defend, and remember the **big-market delusion** both ways: a big market is already in the growth (don't add a separate premium), and a bigger market invites competition that *compresses* margins (SpaceX cut its target margin from 45%→25% when it chased the larger market) — bigger TAM travels with lower margin and heavier reinvestment, never a free margin bump.

### Country risk scales with operating EXPOSURE, not incorporation (`lambda_country`)
This is the clearest "think, don't hardcode" rule. India's equity risk premium = a mature-market ERP + an India country-risk premium (CRP, from Damodaran's country tables / sovereign spread — a number that *moves yearly*, look it up, don't memorise it). But that CRP applies to the company in proportion to **λ, its operating exposure to India**, not to where it is listed:

```
cost_of_equity = risk_free + beta·mature_erp + lambda_country·CRP
lambda_country ≈ (company's % of revenue/operations in India) / (average firm's % in India)
```

A domestic FMCG, lender, or infra play has λ ≈ 1 and carries the full CRP; an IT exporter earning mostly abroad (TCS λ ≈ 0.09, Tata Motors ≈ 1.14 because JLR is global yet it was India-heavy then) barely carries it. Setting `lambda_country` from the revenue mix is what stops you over-discounting an Indian *exporter* and under-discounting a purely domestic firm. Building WACC up this way (rather than hand-typing one number) also prevents the double-count where risk is loaded into both a high discount rate *and* a timid growth path. Terminal growth is then bounded by the risk-free **in the currency of the cash flows** — for a ₹ model of a domestic firm that is the ~6.5–7% rupee G-sec (not a 4% US habit; 4% would imply the mature firm shrinks in real terms), but for a low-λ exporter you may be modelling in a blend where a lower number is right. The point is the *bound and the currency*, not a fixed figure.

### Apply post-operating adjustments only when the diagnosis calls for them
Value the operations cleanly first, then — and only if warranted — layer these, each kept **separate** so the operating story is never quietly poisoned to express them:
- **`failure_probability`** (+ `failure_recovery`): a distress haircut, warranted when distress signals are present — negative earnings + heavy debt + reliance on external capital (early life cycle), or a decline-phase firm. Damodaran used ~10% for loss-making Zomato; he would use ~0 for a profitable mature firm. **It is conditional, not a default.**
- **`complexity_discount`**: a governance/structure haircut for what a DCF can't see — opaque cross-holdings, family-control wealth-transfer risk, promoter pledging, political dependence. Damodaran's Adani method exactly: value the operations with even *upbeat* assumptions (he got ₹945 vs a ₹3,858 price), then demand "a significant discount on intrinsic value" for the control/complexity. Use this for conglomerates and promoter-dominated groups; leave it 0 for a clean, simple business. Separating it from the operating story is the discipline — don't bake governance into a gloomy growth rate.
- **Normalisation** (no engine lever — you do it in the inputs): for cyclical/commodity firms (autos, metals, airlines), feed *normalised-through-the-cycle* margins and, where relevant, a normalised commodity price, not the current peak/trough. State the commodity-price call explicitly; it is often the real swing factor.
- **Lease / R&D capitalisation**: see the next section — apply where material (retail/QSR leases, pharma/tech R&D), regardless of stage.

Where a large gap to price *survives* a coherent, stage-appropriate valuation — as Damodaran's ₹41 Zomato survived the ₹72 offer, and his ₹945 Adani survived ₹3,858 — that gap is the finding. The goal of all of this is not to push the value up or down, but to make every lever answer to a diagnosis instead of a default.

## Capitalisation adjustments Damodaran insists on

- **Operating leases** → capitalise (asset + debt). Materially changes leverage and WACC for lease-heavy businesses (retail, airlines, QSR). Add the lease debt into `net_debt`; if you can, move the lease expense out of operating costs (raises EBIT) — at minimum, *note* the distortion if you can't.
- **R&D** → treat as capital, not a period expense, for R&D-heavy firms (pharma, semis, tech): it builds an asset amortised over its useful life, giving a truer operating margin and invested capital. If you don't restate, flag that reported margins understate the steady state.

If you cannot make these adjustments precisely, **say so in the report as a data gap** rather than quietly ignoring them.

## Running it

```bash
# fill assets/dcf-inputs.example.yml with sourced numbers, then:
python3 <skill-dir>/scripts/dcf.py --inputs <your-inputs>.yml \
    --sensitivity --story --out artifacts/stocks/<SYMBOL>/YYYY-MM-DD/dcf.json
# --story emits the growth×margin grid (the headline range for a growth company)
# or a quick worked example:
python3 <skill-dir>/scripts/dcf.py --selftest
```

The script emits a per-year FCFF table, EV/equity/per-share, the **story-driver grid** (`--story`, growth × steady-state margin — the headline range), the WACC×terminal-growth grid (`--sensitivity`, a secondary check), and **flags**. Exit 3 means the model is invalid (e.g. WACC ≤ g) — fix the inputs, don't paper over it.

## The flags the engine raises (read them as Damodaran's reality checks)

- `TERMINAL_GROWTH_ABOVE_RISKFREE` — cap g_T at the risk-free rate (in the cash-flow currency). Always.
- `TERMINAL_VALUE_HEAVY` — value concentrated in the terminal year. **Stage-aware** (set `lifecycle_stage`): for a young/high-growth firm this is *expected* (the cash flows live in the future) and only fires above ~90% with reassuring wording; for a mature firm it fires above ~75% as a "stress-test the duration/margin" prompt; for a declining firm it is a red flag pointing you to liquidation/break-up value.
- `DECLINE_POSITIVE_TERMINAL_GROWTH` — a positive perpetual growth on a firm you classified as declining; a shrinking business usually warrants g_T ≤ 0 and a liquidation cross-check.
- `NEGATIVE_ENTERPRISE_VALUE` — explicit cash flows are net-negative; reinvestment too heavy or margins too thin for the growth assumed. The model is unusable until the story is fixed.
- `NO_TERMINAL_EXCESS_RETURN` — terminal ROIC ≤ WACC means no value creation in perpetuity (correct for a no-moat firm; a red flag if you claimed a moat — and the signature of a scale-without-returns conglomerate where growth *destroys* value).
- `HIGH_MARGIN_ASSUMPTION` / `HIGH_GROWTH_ASSUMPTION` — defend these against a real peer and the TAM (not just history), and remember a bigger market travels with lower margins, not higher.
- `DISCOUNT_ON_NONPOSITIVE_EQUITY` — a failure or complexity haircut was applied to an already-negative operating equity (multiplying a negative is meaningless); when operating value is negative the story is the verdict — cross-check asset/liquidation or sum-of-parts value.

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

1. **Show a range, not a point — on the levers that matter.** Lead with the `story_sensitivity` grid (growth × steady-state margin) and its `duration` read; the single per-share number is the midpoint of an honest band, never a precise target. The WACC×g grid is a secondary check — for a growth company it perturbs the two *lowest*-leverage levers, so leading with it understates the true range and hides a premature-fade problem.
2. **Margin of safety, not fair value = buy.** Damodaran/Graham: require a discount (commonly ≥ 25–30% below intrinsic) before acting, sized to how terminal-heavy and assumption-laden the model is.
3. **Break your own story.** If a competitor launched a cheaper product tomorrow, which input collapses? If the whole thesis hangs on one heroic assumption, say that out loud.
4. **Know when DCF is fragile — and when it merely *looks* fragile.** Genuinely fragile: banks/NBFCs/insurers (FCFF ill-defined → use P/B–RoE) and violently cyclical/commodity firms (normalise through the cycle, treat DCF as one weak input). *Not* fragile, despite appearances: young loss-makers — that is precisely what story-driven DCF is for (Zomato, SpaceX), valued with a TAM-built revenue, a country-risk WACC, and a failure probability. Don't retreat to multiples just because today's earnings are negative.

Every number in the output must trace back to a sourced input. If you had to estimate one, label it an estimate. Not investment advice — personal research tool.
