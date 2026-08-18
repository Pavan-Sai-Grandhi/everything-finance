# Live data-authenticity smoke test

Every tool called against its real upstream, with each value questioned: is it fresh,
complete, internally consistent, and does an independent source agree? A green unit
suite cannot answer this — all 1,595 offline assertions pass with a dead source.

Run: 2026-08-18, market open. Environment: `finance/mcp/*` through the real MCP SDK.

## Discrepancies found

### D1 — India VIX reported NaN, and a missing value scored as "lowest in 5 years"  ✅ FIXED
**Severity: high.** `get_macro` returned `india_vix.last = NaN` with
`percentile_5y = 0.0`.

Root cause, one line: `macro()` filtered `close is not None` — but **NaN is not None**,
so it passed. `percentile(pool, NaN)` then returned `0.0`, because every comparison
against NaN is False, so nothing counts as "below" it. A value that did not exist was
reported as the calmest market in five years. Volatility band governs position sizing.

Upstream cause: yfinance publishes a session's Open/High/Low before the close settles,
so the newest bar carries a NaN close. It affected `^NSEI` too, not just VIX.

Fixed at the source — `prices.history()` drops unsettled bars and records a labelled
gap naming the real as-of date. Also hardened `spine.f()` (the one numeric coercion)
to reject NaN/inf, `market.percentile()` to return None for a NaN target and exclude
NaN from its pool, and `trade_check`'s close filter.

Verified: VIX now reads 11.31 at percentile 11.4 — matching what `context._volatility()`
computes by an independent path, which had its own NaN guard and was always correct.

### D2 — NaN was emitted onto the MCP wire as invalid JSON  ✅ FIXED
**Severity: high.** `json.dumps` writes a bare `NaN` literal, which strict JSON parsers
reject; the tool response could fail to decode client-side. Closed by D1's fix.
Regression-tested by asserting a settled series serialises without `NaN`.

### D3 — the spilled candle file carried NaN  ✅ FIXED
`get_history` kept the wire clean only because the inline slice takes the first rows
while the bad bar is last. The spilled file — which the tool tells the model to read —
held it. Python's `json.load` accepts NaN silently, so the hazard moved one layer down.
Closed by the same source fix.

### D4 — a poisoned day-cache could not be refreshed through the tool  ✅ FIXED
`get_macro` had no `fresh`, so the cached NaN envelope would have been served all day
even after the code was fixed. `fresh` added.

### D5 — screener.in served a stale RELIANCE page: ₹2,951 against a true ₹1,316  ✅ FIXED
**Severity: high.** `get_company_fundamentals("RELIANCE")` returned Current Price
₹2,951 with only 4 headline ratios, stamped `cached_on: 2026-08-18` (today). A forced
fresh fetch returned ₹1,316 with 9 ratios — matching TradingView, Yahoo, and
Tickertape's market cap. The stale page was internally consistent (High/Low 3,217 /
2,221 brackets 2,951), so nothing downstream could have caught it; it read as
authoritative and would have gone into a DCF.

The cache file was overwritten by the fresh fetch before the mechanism could be traced,
so the exact origin is **not proven**. Two contributing defects were found and fixed:

1. The freshness stamp was written with `setdefault`, so an envelope already carrying
   `cached_on` (or `date`, which NSE payloads use) kept the inherited value instead of
   recording when we actually cached. Now assigned directly, at all three sites.
2. A thin parse was never questioned. `fetch()` validated the P&L table but not the
   ratios block, so a 4-ratio page passed as complete. It now raises a labelled gap
   below `_MIN_RATIOS` (6), since a real page carries ~9.

### D6 — four different date formats across the tools  ✅ FIXED
**Severity: medium.** CLAUDE.md mandates `YYYY-MM-DD`, but NSE-sourced tools passed
their raw strings through:

| tool | before | after |
|---|---|---|
| `get_filings` | `17-Aug-2026` | `2026-08-17` |
| `get_shareholding` | `30-JUN-2026` | `2026-06-30` |
| `get_corporate_actions` | `05-Jun-2026` | `2026-06-05` |
| `get_flows.session` | `17-Aug-2026` | `2026-08-17` |
| `get_news`, `get_history`, `get_nav_history` | already ISO | unchanged |

Filings could not be sorted or compared against news or candles — date arithmetic
across two tools raises or silently mis-orders, which is how `daily-brief` merges
them. Fixed with one `spine.iso_date()` beside the one numeric coercion, applied at
the NSE parse sites. Garbage returns None rather than a wrong date.

### D7 — a malformed trade file produced a confident HOLD  ✅ FIXED
**Severity: high.** `check_trade` on a trade file whose levels sat outside the `plan:`
block returned `verdict: HOLD`, `reasons: ["rationale intact: no stop/target/thesis/
time trigger"]`, and **no gap** — a clean "nothing triggered" when nothing had been
checked. The stop was never read, so a breach could not have been detected. The
trade-tracker skill explicitly accepts a rationale the user types, so a hand-written
or mis-keyed file is the expected case, not an exotic one.

The tool is correct on a well-formed file: it read entry/stop/target, computed
`unrealized_R 1.32`, and returned `EXIT_STOP` with "low 1298.10 vs stop 1400.00" when
the stop was breached. The defect was only in the vacuous case.

Now, with no stop, no target and no `thesis_invalidation`, the verdict carries a gap —
"this HOLD is the absence of a check, not a passed one" — plus a `manual_review` entry.
A well-formed plan, and a thesis-only trade, still return clean.

## Verified authentic

| Tool | Evidence |
|---|---|
| `get_quote` | RELIANCE ₹1,316.00, mcap ₹17.7 L Cr, volume 1.34 Cr, dated today |
| `get_history` | 125 sessions for 6mo; every candle low ≤ O,C ≤ high; dates ascending, no dupes; volume on >90% |
| **cross-source** | **TradingView quote ₹1316.00 vs Yahoo EOD ₹1316.00 — 0.00% divergence** |
| `get_indices` | NIFTY 50 24,287.65, P/E 20.53, P/B 2.95, DY 1.17 — all in sane bands; 139 indices upstream |
| `get_index_valuation_history` | 62 month-end samples over 5y (by design, documented); percentiles in 0–100 |
| **cross-source** | **valuation-history current P/E 20.53 == get_indices P/E 20.53** |
| `get_breadth` | 291/492 above 50DMA, 311/473 above 200DMA, dated today; the two sub-universes differ honestly because fewer names have 200 sessions of history |
| `get_flows` | session 17-Aug-2026: FII −₹2,535 Cr, DII +₹5,101 Cr — both sides present, signs opposite |
| `get_macro` | USDINR 95.59, gold $4,463, Brent $91.25, US10Y 4.72 — all in sane bands (post-fix) |
| `get_market_context` | trend/volatility computed off the last settled bar, as-of 2026-08-14 |
| MCP layer | 25 tools across 3 servers, exact map match, no tool on two servers, SDK not shadowed |
| launcher | all three servers complete the JSON-RPC handshake and answer a live `get_quote` |
| `get_company_fundamentals` | post-fix: 9 ratios, ₹1,316, mcap ₹17.8 L Cr, P/E 23.8, ROE 8.91, AR + concall links |
| **cross-source** | **screener ₹1,316 == TradingView ₹1,316 == Yahoo ₹1,316; screener mcap ₹17.8 L Cr ≈ Tickertape ₹17.9 L Cr** |
| `get_stock_ratios` | RELIANCE: P/E 22.18, P/B 1.65, ROE 7.71, EPS 59.69, sector tagged |
| `get_news` | 74 items/30d, all dated, none outside the window, none future-dated, all deduped, publisher tier on every item |
| `get_shareholding` | 8 quarters; promoter 50.48% + public 49.52% = 100.00%; **empty pledge correctly labelled "UNKNOWN, not nil"** |
| `get_filings` | 11 filings in 30d, all dated and materiality-classified |
| `resolve_fund` | Nippon India Small Cap → AMFI 118778, ISIN INF204K01K15, plan Direct, Tickertape M_NIMS |
| `get_nav_history` | 3,351 NAVs, 2013-01-02 → 2026-08-17 (1d old), ascending, unique dates, no NaN, no >25% day jumps |
| **`get_fund_holdings`** | **273 positions, weights sum 100.0% — the 20-row truncation this plugin's source boundary exists to prevent does not occur** |
| `screen_funds` | full Small Cap category with AUM and expense ratios in range |
| `run_fundamental_screen` | degrades to a labelled gap without cookies, never a silent empty |
| `get_market_context` | trend "range", posture "neutral", 1,565-char digest, VIX flowing correctly post-fix; a second `quick` call costs 0.00s, so the daily artifact is genuinely shared |
| `run_backtest` | 96 trades over 3 symbols/3y; exit breakdown (37 SL / 22 TARGET / 22 TIME / 15 SIGNAL) sums exactly to 96; expectancy −0.015R reported honestly rather than flattered |
| `run_strategy_screen` | 3 live signals, each **RRR exactly 2.00**, risk ₹4,957–4,993 against a 1%-of-₹5,00,000 budget, stop < entry < target — the trading-discipline rules hold on real prices |
| `check_trade` | well-formed plan → `unrealized_R 1.32`; breached stop → `EXIT_STOP` with the evidence |
| `get_fund_scan` | ranked Small Cap shortlist with scores, and a gap telling the caller to read `flags` before treating a rank as a recommendation |
| `get_fund_lookthrough` | 273 positions / 269 equity; P/E 29.21 at 96.5% coverage marked "decision-grade"; **`earnings_growth` withheld** (`coverage 0.0`, `confidence: unavailable`) with the gap "it is absent, not zero" |

## Coverage

Company tools (`get_company_fundamentals`, `run_fundamental_screen`, `get_stock_ratios`,
`get_news`, `get_filings`, `get_shareholding`, `get_corporate_actions`), fund tools
(`resolve_fund`, `screen_funds`, `get_fund_holdings`, `get_nav_history`,
`get_fund_scan`, `get_fund_lookthrough`), and the strategy engines
(`run_strategy_screen`, `run_backtest`, `check_trade`).

Nothing. All 25 tools were exercised against live upstreams.

Not covered by this pass, and worth knowing: the personal servers (kite / upstox /
indmoney) were not exercised — they need the user's own authenticated session, and
this pass deliberately touched no account data.
