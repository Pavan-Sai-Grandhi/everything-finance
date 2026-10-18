# Valuation

**Consumers:** valuation-analysis, deep-analysis (the portfolio-manager weighs the result).
**Sources, in priority order:** `damodaran`, `plugin`.

The method is Damodaran's story-driven FCFF valuation, reconciled with a relative-multiples read
[damodaran]. `run_dcf` is the arithmetic; the job here is a coherent story turned into a small set
of sourced, consistent inputs. A clean per-share number on an incoherent story is worthless.

## The one idea

A DCF is not a spreadsheet exercise — it is a **story disciplined by arithmetic**. Every input must answer a "why":
- Why this **revenue growth**? → total addressable market (TAM) + the company's share trajectory + a competitive edge that justifies taking share.
- Why this **operating margin**? → benchmark the steady-state margin of the best 3–5 peers; you only assume above-peer margins if the story (brand, scale, cost edge) earns it.
- Why this **reinvestment**? → growth must be *paid for*. The **sales-to-capital ratio** says how many ₹ of new sales each ₹ of investment buys.

If the story and the numbers disagree (margins no competitor has achieved, growth the TAM can't support, growth with no reinvestment), the valuation breaks. *Be an optimist or a pessimist, but be a consistent one.*

## The model `run_dcf` implements (FCFF)

For each explicit-forecast year (default 10):

```
revenue_t      = revenue_{t-1} × (1 + growth_t)
EBIT_t         = revenue_t × operating_margin_t        # pre-tax operating income
NOPAT_t        = EBIT_t × (1 − tax_rate_t)             # after-tax operating income
reinvestment_t = (revenue_t − revenue_{t-1}) / sales_to_capital_t
FCFF_t         = NOPAT_t − reinvestment_t
PV_t           = FCFF_t / Π(1 + WACC_i) for i ≤ t
```

With `timing`, each year's cash is taken at mid-year and the whole value is rolled forward from the base period's end to the price date; without it every flow is a full year late and the result carries `TIMING_UNADJUSTED`.

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

## The valuation levers (and where to source each)

The rows named below are Tickertape's labels; `methods/fundamentals.md` → *Reading the published rows* says what each really is and how to pair periods.

| Lever | Source it from | Sanity rule |
|---|---|---|
| Base revenue | annual-report **Revenue from Operations** (latest FY or TTM) | exclude interest, investment and other non-operating income; if the feed only exposes `Total Revenue`, derive the operating figure from the annual report rather than double-counting non-operating assets |
| Revenue growth path | TAM studies + company guidance (concall) + Revenue from Operations history, cross-checked against `get_analyst_estimates`' consensus for the next two years; fade to ≈ GDP+inflation by year N | peak growth > 30% must be defended against TAM and reinvestment |
| Operating margin path | the company's own trend + peer steady-state margins | use operating EBIT ÷ Revenue from Operations. The published `OPM %` is EBITDA-like, not EBIT; above-peer margins need a stated moat and peak > 40% is rare |
| Tax rate | **the annual report's tax note**, via `get_documents` | never derived from `Taxes & Other Items`; India ≈ 25% statutory for most |
| Sales-to-capital | historical **ΔRevenue ÷ reinvestment**, reinvestment sourced per § below; peer benchmark | asset-light (software) high (3–5+); capital-heavy (utilities, autos) low (0.5–1.5) |
| WACC | cost of equity (default-free risk-free + β×mature-ERP + λ×country-risk premium) and after-tax cost of debt, weighted | for INR, default-free risk-free = Indian government-bond yield − sovereign default spread; then add India CRP once. β is a **bottom-up/sector** beta, never raw regression β; see § Country risk |
| Terminal growth | ≤ default-free risk-free rate, **in the currency of the cash flows** | use the adjusted rupee rate, not the unadjusted G-sec yield — see § Country risk |
| Terminal ROIC | the return the mature firm earns on new capital | the excess return (ROIC−WACC), not g_T, is what moves terminal value; default to convergence (= WACC), set > WACC only if a durable moat persists — see § Terminal value |
| Net debt | `balance_sheet_10y` **`Total Debt`** − **`Cash and Equivalent`** | consolidated; add capitalised lease debt (see § Capitalisation adjustments) |
| Shares, minority | **`Common Shares Outstanding`**, **`Minority Interest`** | share count in crore shares (a count, not currency) so per-share lands in ₹; confirm dilution against the annual report |

### Sourcing the reinvestment (the sales-to-capital lever)

Growth has to be paid for, so this lever decides how much of the revenue path the firm keeps. Reinvestment takes Damodaran's form, and each term is sourced separately:

```
reinvestment_t = capex_t − depreciation_t + ΔWC_t
sales_to_capital = (revenue_t − revenue_{t-1}) ÷ reinvestment_t
```

| Term | Source | Status |
|---|---|---|
| capex | `cash_flow_10y` **`Capital Expenditures`** | published |
| depreciation | `pnl_10y` **`Depreciation & Amortization`** | published |
| ΔWC | Δ(**`Total Receivables`** + **`Total Inventory`** − **`Accounts Payable`**) from `balance_sheet_10y` | **derived — label it so** |

**ΔWC is the one derived term, and it is derived deliberately.** `cash_flow_10y` carries a row named `Changes in Working Capital`, and it is not one: across RELIANCE, TCS, HINDUNILVR, INFY, MARUTI and ASIANPAINT it reconciles neither to the balance-sheet working-capital movement (TCS reads −16,594 against a balance-sheet +7,962, and the two agree in sign in only 16 of 24 company-years) nor to the CFO-minus-earnings residual. Its composition is not determinable from what the source publishes, so it does not enter the reinvestment. Use the balance-sheet delta, say in the inputs file that it is derived, and take the working-capital movement from the annual report's cash-flow statement when the story turns on it.

Take the ratio over **several years, not one** — a single year's capex is lumpy, and one large project year makes an asset-light firm look capital-heavy. Where reinvestment is negative or near zero (a firm harvesting, or one year of asset sales), the ratio is meaningless: fall back to the peer benchmark and say which year forced it.

**Cross-check the base year against the published `Free Cash Flow`.** `cash_flow_10y` carries FCF over the same ten years, so the model's year-0 FCFF has a sourced figure to sit beside. They are not the same quantity — FCFF is pre-financing and after cash taxes on EBIT, the published line is `Cash from Operating Activities − Capital Expenditures` — so they need not match, and a material gap requires reconciliation of definitions, timing, interest, taxes and reinvestment before it can validate or invalidate an input.

**Use ₹ Crore for money inputs and crore shares for the share count, so per-share lands in ₹.** Check units explicitly before calculation.

## Diagnose first: the corporate life cycle decides which levers move

Damodaran's first-principles method is identical in every market and at every age; what changes is *which inputs are hard, which are reliable, and which adjustments are warranted*. The single most important step — before any number — is to **place the company on its life cycle**, because the stage tells you how to think, not what to type. Set `lifecycle_stage` accordingly. Resist the temptation to import fixed "India numbers" — a flat terminal growth, a flat country premium, a standard failure probability. Each of those is an *output of the diagnosis below*, not a constant; reason it out per company.

| Stage (`lifecycle_stage`) | What drives value / is hard | Narrative vs numbers | Terminal value | Failure / distress | Cost of capital |
|---|---|---|---|---|---|
| `start_up` / `young_growth` | TAM, can it scale, unit economics; everything is hard | story dominates | speculative; value lives in the future — **terminal-heavy is correct** | real and material — apply `failure_probability` | high, fades as it de-risks |
| `high_growth` | growth rate **and how long it lasts**, path to margins | balanced, numbers start to bind | large share of value; build it from durable growth + steady-state margin | apply if still loss-making / cash-burning | moderating |
| `mature_growth` / `mature_stable` | margins, capital allocation, moat *duration*; history constrains you | numbers dominate — deviations from history need a reason | big but **disciplined by the demonstrated business**; g_T ≈ economy | ≈ 0 for a profitable cash generator — **don't apply it** | ≈ market average; small WACC changes matter |
| `decline` | cash extraction, asset/liquidation value, return of capital | liquidation mechanics dominate | small / near-zero / negative; **g_T ≤ 0** and cross-check break-up value | elevated again | elevated (distress) |

The engine's flags are tuned to the stage: `lifecycle_stage` relaxes the terminal-heavy flag for young firms and turns it into a red flag — plus a positive-terminal-growth warning — for declining ones.

### Choose the growth duration from evidence

Forecast duration and growth rate are separate assumptions. Choose both from the business evidence: addressable market, competitive position, reinvestment capacity and plausible limits on market share. Historical growth is evidence of past performance, not proof that it will persist. A longer horizon is a scenario to evaluate, not an automatic entitlement for a young company.

Use `story_sensitivity.duration` to show how extending the assumed high-growth period affects value. A scenario matching the market price does not make it the correct base case. Revise the base only when independent evidence changes the business case; record that evidence and the old/new assumptions. Reverse DCF is a conditional comparison, not a calibration target. Growth, margins and reinvestment must remain mutually consistent when the market opportunity changes.

### Country risk scales with operating EXPOSURE, not incorporation (`lambda_country`)
This is the clearest "think, don't hardcode" rule. India's equity risk premium = a mature-market ERP + an India country-risk premium (CRP, from Damodaran's country tables — a number that *moves yearly*; `get_risk_inputs` returns the current vintage with its date, never memorise it). But that CRP applies to the company in proportion to **λ, its operating exposure to India**, not to where it is listed:

```
default_free_risk_free = local_government_bond_yield − sovereign_default_spread
cost_of_equity = default_free_risk_free + beta·mature_erp + lambda_country·CRP
lambda_country ≈ (company's % of revenue/operations in India) / (average firm's % in India)
```

A domestic FMCG, lender, or infra play has λ ≈ 1 and carries the full CRP; an exporter carries less according to its operating exposure. Setting `lambda_country` from the revenue mix stops you over-discounting an Indian exporter and under-discounting a domestic firm. The local government bond is not default-free: subtract the sovereign default spread before treating its yield as the rupee risk-free rate, then add country equity risk once through CRP. Feeding the full G-sec yield into `risk_free` and adding CRP again double-counts sovereign risk. `get_risk_inputs` supplies the bond yield, sovereign spread, mature-market ERP and CRP from one dated vintage; cite each with its date. Terminal growth is bounded by that **adjusted default-free rupee rate**, not by the headline G-sec yield.

**The build-up's premium is a view on the market, so measure it against the market.** Mature ERP plus India's rating-based CRP is what Damodaran's tables say Indian equities should earn; the NIFTY 500's own P/E, P/B and dividend yield, with analysts' consensus earnings growth for its constituents, imply what buyers are pricing them to earn today — the same solve Damodaran runs on the S&P 500 for his mature-market premium. When the build-up asks more, it values the whole index below its price, and every stock inherits that discount before its own story enters. `run_dcf` therefore returns `market_view`: the market's implied return, the value rebased to it, and the index's value-to-price at the method's rate. The two answer different questions. The method-rate value asks whether the stock is worth its price in absolute terms; the market-view value asks whether it is dear against the alternative of owning the market. A gap that closes at the market's return is the market's valuation, which the market context carries into sizing; the gap that survives it is this company's.

For a young/high-growth company, risk should converge as the business matures: the explicit cost of capital fades toward a defensible mature `terminal_wacc`. A flat high-growth WACC for every forecast year while abruptly switching to a lower terminal WACC is internally inconsistent. Mature/stable firms may justifiably have a flat path.

**Beta is the business's risk, not the share price's wobble.** Use a **bottom-up/sector beta** — the unlevered beta of the company's business(es), relevered for its own debt — never the stock's raw *regression* beta. A volatile, momentum-driven share price throws up a regression beta of 1.3–1.6 that says nothing about how risky the *operations* are; feeding it in inflates WACC by 1–2% and quietly depresses value for no business reason (a hidden conservatism that masquerades as rigour). Most Indian operating businesses sit at a bottom-up beta of ~0.8–1.2; reach for higher only when the *business* (not the tape) is genuinely more cyclical or operationally levered. The engine raises `BETA_LOOKS_LIKE_REGRESSION` above 1.3 as a prompt to check this.

### Terminal value is an excess-return decision, not a growth-rate one
The terminal value usually dominates a DCF — and that is **normal for a going concern, not a defect** (most of any stock's value is future cash flow). Damodaran's myth-buster: *the growth rate is barely the issue; the **excess return — terminal ROIC minus WACC — is the whole ballgame.*** If terminal ROIC = WACC, the firm earns its cost of capital on new investment, growth creates no value, and g_T is irrelevant to the terminal number. So the engine **defaults terminal ROIC to convergence (= WACC)** — the honest base case, because competition erodes excess returns. You raise it above WACC *only* when you can name a durable moat (brand, network, switching costs, regulatory/scale edge) that plausibly persists into perpetuity, and the size of that spread is then the single most consequential — and most scrutinised — assumption in the model. A heavy terminal value (the `TERMINAL_VALUE_HEAVY` flag) is therefore an instruction to look *harder* at two things — the high-growth path leading into the terminal year and that excess-return spread — not a reason to distrust the model. The output reports `terminal_excess_return` so the spread is explicit.

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

## The flags the engine raises (read them as Damodaran's reality checks)

- `TERMINAL_GROWTH_ABOVE_RISKFREE` — cap g_T at the **default-free** rate in the cash-flow currency. The engine rejects this inconsistency rather than merely warning.
- `TERMINAL_VALUE_HEAVY` — value concentrated in the terminal year. **Stage-aware** (set `lifecycle_stage`): for a young/high-growth firm this is *expected* and only fires above ~90%; for a mature firm it fires above ~75% (read it per § Terminal value); for a declining firm it is a red flag pointing you to liquidation/break-up value.
- `BETA_LOOKS_LIKE_REGRESSION` — the input beta is above ~1.3, the tell-tale of a raw regression beta on a volatile stock rather than a bottom-up/sector (business-risk) beta. Confirm it's the unlevered-relevered industry beta; a regression beta over-discounts and depresses value for no business reason.
- `DECLINE_POSITIVE_TERMINAL_GROWTH` — a positive perpetual growth on a firm you classified as declining; a shrinking business usually warrants g_T ≤ 0 and a liquidation cross-check.
- `NEGATIVE_ENTERPRISE_VALUE` — explicit cash flows are net-negative; reinvestment too heavy or margins too thin for the growth assumed. The model is unusable until the story is fixed.
- `NO_TERMINAL_EXCESS_RETURN` — terminal ROIC ≤ WACC means no value creation in perpetuity (correct for a no-moat firm; a red flag if you claimed a moat — and the signature of a scale-without-returns conglomerate where growth *destroys* value).
- `HIGH_MARGIN_ASSUMPTION` / `HIGH_GROWTH_ASSUMPTION` — defend these against a real peer and the TAM (not just history), and remember a bigger market travels with lower margins, not higher.
- `DISCOUNT_ON_NONPOSITIVE_EQUITY` — a failure or complexity haircut was applied to an already-negative operating equity (multiplying a negative is meaningless); when operating value is negative the story is the verdict — cross-check asset/liquidation or sum-of-parts value.

## Reverse DCF — let the price tell you its story

The forward DCF asks "given my story, what is it worth?" The **reverse DCF** flips it: "given the market price, what story must already be true?" It is often the single most decision-useful output, because it sidesteps the endless argument over your assumptions and instead tests the *market's* — which are usually far more aggressive than people realise.

Mechanically, the engine holds other assumptions fixed and shifts one path by a constant to match the target price. For growth it reports implied year-one growth and revenue CAGR; for margin it shifts the explicit and terminal margins together. Compare a solved path with sourced history, guidance and market constraints. A company's past growth or a named competitive advantage alone does not establish the duration or probability of that path.

When it returns `solved: false`, report the reason and omit implied assumptions. The target may be unbracketed, an optional input may be absent, or the solver may not converge. None establishes that the stock is cheap or expensive. Even a solved path is conditional on every fixed assumption and need not be the only root. Use growth for a growth scenario; margin solving applies only to an FCFF margin scenario, not the equity adaptation's fixed unit margin.

## Relative valuation — multiples as the second view

Multiples are **DCF in shorthand**: every one of them traces to the same drivers — cash flow/payout, growth, risk. That is what makes the relative read a genuine second view rather than decoration, and it is why a higher multiple than peers can be entirely *justified*. It also survives the cases where the DCF is fragile, so it runs on every company.

- **Peer group built for comparability** — same industry, similar size, growth and risk. `get_company_fundamentals` returns real sub-sector peers, each row carrying `ttm_pe` and `pb` already, plus a `sid` for any other ratio via `get_stock_ratios`. Still read the list: a peer set that ignores size/growth/risk makes the median meaningless, and a four-name list is thin enough that one outlier matters.
- **Median, not mean.** Multiple distributions are right-skewed (a few very-high outliers); the **median** is the representative peer value, and the engine enforces it.
- **Consistent definitions.** Same trailing-vs-forward basis across the peer set; same numerator/denominator (equity multiples like P/E to equity, enterprise multiples like EV/EBITDA to the firm). State the basis.
- **PEG = P/E ÷ expected EPS growth (%).** A cross-check that normalises P/E for growth — but it hides two assumptions: **equal risk** across the peer set and a **linear** growth↔P/E relationship. Flag both; PEG is never a standalone verdict. The growth input is a labelled estimate (forward/analyst or historical EPS CAGR, basis stated), never fabricated.
- **Own-band percentile.** Where the company's P/E sits inside its own historical band is the one comparison immune to a bad peer set.
- **Same earnings basis on both sides.** A P/E struck on earnings adjusted for one-offs is not comparable to peers struck on reported earnings — a recurring fair-value gain can halve a reported multiple, so the two bases can differ by 2x on the same company. Declare `pe_basis` and `peer_pe_basis`; when they differ the peer read is directional only and does not carry the stance.
- **A peer median needs peers.** Under three priced peers is one company's accident, not a centre. The engine voids the peer half below that floor and returns the gap; report it and lean on the own band rather than presenting a stance the peer set could not support.
- **Pick the multiple to the business.** P/E for profitable firms; **P/B with RoE** for banks, NBFCs and insurers (EV/EBITDA and FCFF are both ill-defined there); P/S or EV/Sales for loss-makers; **EV/EBITDA** where capital structure differs across the peer set.

## Reconcile and grade confidence

**Reconcile before you judge.** A difference vs peers is **explained by fundamentals first** — higher growth or lower risk legitimately justify a higher multiple — and only the unexplained residue is mis-pricing. State whether the relative read **confirms or contradicts** the DCF, and why.

**Grade DCF confidence — low / med / high** from two stated, checkable factors, so the grade is auditable:

- **Terminal-value weight** — terminal value as a % of enterprise value (`terminal_value_fraction`). Below ~60% supports *high*; above ~75% pulls toward *low*.
- **Assumption stretch** — projected growth and margin against the company's *demonstrated* history. Inside history supports *high*; well above it pulls toward *low*. Any engine flag (`BETA_LOOKS_LIKE_REGRESSION`, `MARGIN_BASIS_SUSPECT`, `MARGIN_BASIS_UNCHECKED`, a rejected model) pulls it down.

Two structural cases **override to low** whatever the grid says: **banks / NBFCs / insurers**, and **violently cyclical / commodity** firms (§ When the DCF is fragile).

For a lender or insurer, run the DCF as an **equity-shaped** model rather than bending the firm-side levers silently: pass `model_shape: equity` alongside `base_revenue` = net income, `operating_margin` = 1.0, `tax_rate` = 0 (the stream is already post-tax), `sales_to_capital` = marginal return on reinvested equity/regulatory capital, `terminal_roic` = sustainable ROE, `net_debt` = 0, and a discount rate that is a **cost of equity, not WACC**. The engine rejects a visibly equity-shaped stream left under the default FCFF label. In equity mode it also rejects any explicit/terminal margin other than 1, any explicit/terminal tax rate other than 0, nonzero net debt, or a buildup with debt weight. Set terminal fields explicitly when adapting an existing FCFF input file; its old terminal margin/tax assumptions must not survive. The stance still leads on P/B×RoE and peer multiples — the equity DCF is the sanity band.

**Combine into one stance, weighted by that grade:**

| DCF confidence | How the two views combine |
|---|---|
| high | Lead with the DCF — the intrinsic-vs-price gap drives the call; the relative read corroborates or qualifies |
| med | DCF and relative carry equal weight; agreement raises conviction, disagreement lowers it |
| low | Lean on the relative read; the DCF is a sanity band only, reported with its weakness stated |

**When the relative read is void** — under three priced peers, or a basis mismatch — the *low* row has nothing to lean on. Say so: the stance rests on a low-confidence DCF and the own band alone, and the combined stance carries that as its stated weakness rather than borrowing confidence it does not have.

Emit a single **Undervalued / Fair / Overvalued** with a margin-of-safety range blending the DCF intrinsic range and the relative read. The stance is the company's: weigh the DCF at the market's implied return (`dcf_mos_market`), and report the method-rate margin (`dcf_mos`) beside it as the absolute read. When the market view was skipped, the stance rests on `dcf_mos` and Findings says why.

## When the DCF is fragile

A young, loss-making, cash-burning company is **in scope**: that is what story-driven DCF is for.
Build revenue from TAM × share × take-rate, set the steady-state margin from where the business
model lands at scale, fund growth with the sales-to-capital ratio, discount at a
country-risk-inclusive WACC, and apply a `failure_probability`. Never refuse a valuation because
earnings are negative today; the fix for a young firm is a failure probability and a range, not
abandoning the DCF.

The DCF is genuinely fragile in two cases, where the stance leans on the relative read and says
which view it trusts: **banks, NBFCs and insurers** (FCFF is ill-defined; value on equity, P/B and
RoE), and **violently cyclical or commodity firms**, where fuel, forex or commodity swings make any
single forecast arbitrary (normalise through a cycle and treat the DCF as one weak input). Both
force DCF confidence to low.

## Final discipline (the devil's-advocate pass)

1. **Show a range, not a point — on the levers that matter.** Lead with the `story_sensitivity` grid (growth-path × explicit-and-terminal margin shifts) and its separate `duration` read; the single per-share number is the midpoint of an honest band, never a precise target. The terminal-WACC×terminal-growth grid is a secondary mechanical check: it leaves explicit WACC and operations unchanged, so it is not a coherent whole-company risk scenario and must not be labelled as one.
2. **Margin of safety, not fair value = buy.** Damodaran/Graham: require a discount (commonly ≥ 25–30% below intrinsic) before acting, sized to how terminal-heavy and assumption-laden the model is.
3. **Break your own story.** If a competitor launched a cheaper product tomorrow, which input collapses? If the whole thesis hangs on one heroic assumption, say that out loud.
4. **Say which view you trust.** The combined stance names whether the DCF or the multiples led it, and the confidence grade that decided.
