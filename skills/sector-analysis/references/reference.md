# Sector analysis method and knowledge base

Grounded in Zerodha Varsity — Sector Analysis (https://zerodha.com/varsity/module/sector-analysis/, covering cement, insurance, IT, automobiles, banking, steel, hotels, retail, real estate).

## The per-sector read — five steps, in this order

1. **Relative strength.** Compute the sector index's 1M / 3M / 6M returns (**21 / 63 / 126 trading days** — fixed so reads are comparable) and Nifty 50's over the same windows; RS = sector return − Nifty return per window. Classify:
   - **Leading** — RS positive on both 1M and 3M
   - **Improving** — 1M positive, 3M negative (early rotation, the actionable class)
   - **Weakening** — 1M negative, 3M positive
   - **Lagging** — negative on both

   If Nifty itself fell over the window, say positive RS may mean "falling less", not rising. Thin/narrow indices (Media, anything under 10 constituents) classify on noise — flag that rather than calling them leaders. Cross-check the classification against the sector index's own chart (price above/below its 50-EMA).
2. **KPI snapshot.** Pull the sector's signature KPIs from the map below for its bellwethers — current reading plus direction of travel, each with its source and period. Every KPI you did not pull is a labelled gap.
3. **Cycle + drivers.** Place the sector in the rotation cycle (rate-sensitives early, capex mid, defensives late), then name the tailwinds and headwinds — each one **sourced, per the evidence rule below, or dropped to Data gaps**.
4. **Leaders / laggards.** From the constituent set, name the 3 strongest and the weakest on the sector's primary KPI plus price-vs-50-EMA, one metric each.
5. **Position the focus stock** (only when a ticker was given). Its RS vs the *sector index* (not just Nifty), its KPI vs the sector median, whether it is a sector leader or laggard, and whether the sector tailwind/headwind helps or hurts it specifically.

## Evidence rule — a named swing factor is a question, not a finding

The KPI map below names the macro variable that swings each sector: USD-INR for IT, the monsoon for tractors, LME and Chinese spreads for metals, pet coke and freight for cement. That naming is the map doing its job — it tells you **what to go and check** for this sector, and it belongs here.

It is not a finding, and it never becomes a Tailwinds/Headwinds bullet on its own. A swing factor earns a bullet only once you hold its **current reading with a source** — a KPI you pulled (company + period), a `get_news` item (publisher + date), or an index or price series with its window stated. Where you cannot source the current reading, the factor goes under **Data gaps** naming what went unverified. A remembered direction — "USD-INR is a tailwind for IT" with nothing behind it — is a prior wearing the clothes of evidence, and the tailwinds/headwinds heading is exactly where that misleads a reader.

## Sector-specific KPIs (what "good" looks like per sector)

**Banking / NBFC** (Varsity: revenues, capital adequacy, asset quality)
- NIM (net interest margin): >3.5% strong for private banks, ~3% PSU norm
- GNPA/NNPA: falling trend matters more than level; GNPA <3% comfortable
- CASA ratio: >40% = cheap deposit franchise
- Credit growth vs deposit growth balance; CAR above regulatory minimum with buffer
- P/B is the valuation lens (not P/E); compare vs own history and peer set

**IT services**
- Revenue growth in constant currency; deal TCV trend
- EBIT margin band (large-caps ~20–25%); attrition falling = margin tailwind
- Utilization, headcount adds as leading indicators; USD-INR a sector-wide swing factor

**Automobiles**
- Monthly volume data (released ~1st of month) is the highest-frequency signal in the market
- Realization per vehicle, EBITDA margin, inventory days at dealers
- Sub-segments rotate separately: 2W (rural proxy), PV (urban), CV (capex/economy proxy), tractors (monsoon)

**Cement**
- EBITDA/tonne (₹800–1,200 healthy), capacity utilization, regional price trends
- Pet coke/power & freight costs are the margin swing

**Steel / Metals**
- Global price-taker: LME/China spreads drive everything; D/E matters (cyclical + leverage = danger)
- EBITDA/tonne, domestic premium vs import parity

**Hotels**
- ARR (average room rate), occupancy %, RevPAR = ARR × occupancy; operating leverage is extreme

**Retail**
- Same-store sales growth (SSSG), revenue per sq ft, store-add pipeline, gross margin mix

**Real estate**
- Pre-sales (bookings) > reported revenue as the lead indicator; collections, net debt, inventory years

**Insurance**
- Life: VNB margin, APE growth, persistency (13th/61st month)
- General: combined ratio <100% = underwriting profit; solvency ratio

**Pharma / FMCG** (not in the Varsity module; standard KPIs)
- Pharma: US generics price erosion, ANDA pipeline, India chronic vs acute mix
- FMCG: volume growth (not just value), rural vs urban commentary, gross margin vs input costs

## Building the constituent set

**A caller that hands you a peer list uses that list.** `deep-analysis` passes the focus stock's `peers`, and the valuation leg strikes its peer-median multiple on the same names — two legs describing the same company against two different baskets is how a report ends up saying "sector leader" and "trades at a premium to peers" about different sets.

With no list given, start from a bellwether you can name in the sector and take its peer set from `get_company_fundamentals(<SYMBOL>, sections=["peers"])` — `peers` returns real sub-sector companies (`symbol`, `name`, `sid`, `ttm_pe`, `pb`), which is the constituent set for the KPI snapshot and the leaders/laggards pass.

**Name the constituents wherever you report an aggregate.** A basket assembled for a niche with no official index is a judgement, and a reader cannot weigh an RS number without knowing whose prices are in it. Where one member moves idiosyncratically enough to shift the aggregate, say which and by how much.

Ratios and the ten fiscal years of P&L, balance sheet and cash flow arrive **one company per call**, and the deep sector KPIs (NIM/GNPA, EBITDA/tonne, VNB margin, combined ratio…) exist only at company level — no feed carries them by sector. So call it for the **3–4 names that matter**, take the sector median from those, and label the rest a gap rather than widening the fan-out.

**Take the cross-section in one call.** `get_history` and `get_news` are one name per call, but the leaders/laggards pass does not need a candle series per constituent — it needs where each name stands right now. `run_technical_screen` returns the whole basket in a single scanner call: pass the constituents as the filter set and ask for the columns you are ranking on. Reserve `get_history` for the two index series the RS windows are computed from. A call per name per metric turns a six-name sector into thirty round-trips, each re-reading the whole context, for a table one call returns.

## Sectoral index ticker map

Pass these to `get_history`: `^NSEI` (Nifty 50 benchmark), `^NSEBANK` (Bank), `NIFTY_FIN_SERVICE.NS` (Financial Services), `^CNXIT` (IT), `^CNXPHARMA` (Pharma), `^CNXAUTO` (Auto), `^CNXFMCG` (FMCG), `^CNXMETAL` (Metal), `^CNXREALTY` (Realty), `^CNXENERGY` (Energy), `^CNXPSUBANK` (PSU Bank), `^CNXMEDIA` (Media — thin index, flag it rather than calling it a leader). Known gaps: Consumer Durables & Healthcare have no Yahoo history (quote only), Oil & Gas has no ticker — list these as data gaps rather than hunting; the 11 covered indices are enough for the rotation read.

Stock-level: `<SYMBOL>.NS` for OHLCV and price-vs-50-EMA. Indicator math is shared — run `<plugin>/finance/compute/ta.py` over the candles `get_history` wrote (a short Bash snippet: `sys.path.insert(0, "<plugin>")`, `from finance.compute import ta`) rather than reimplementing, so this read agrees with the screen and `technical-analysis`.

## Rotation method notes

- Sector rotation follows the economic cycle: early recovery favors financials/auto/realty (rate-sensitive), mid-cycle favors capex (industrials, cement), late cycle favors defensives (FMCG, pharma, IT as a USD hedge).
- The actionable class is **Improving** — entering a Leading sector after both RS windows have turned positive is often chasing.
- Ranking for the top three: prioritize **Improving**, then **Leading**; tie-break on higher 1M RS, then 3M. Thin indices stay in the grid but are excluded from the top three, with the reason stated.
- Varsity's diversification caution applies: top-pick concentration in one sector ≤ 2 positions for a swing book.
