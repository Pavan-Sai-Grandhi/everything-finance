# Plugin audit, 2026-09 to 2026-10

Branch `codex/plugin-audit-refactor`. Every fix below has a regression test that failed before the fix. The suite grew from 2,363 to 3,749 assertions with no failures, and it makes no network requests (checked behind a recording proxy). The full per-section log is in the history of commit c72c415.

## What changed, by area

### Sources

- Prices. A quote must match exactly one requested NSE row with a positive close. Candles are validated (dates, OHLC geometry, volume, duplicates) and invalid bars are counted as gaps. Cache file names hash the request.
- Funds. Name lookups reject partial matches. NAV values, fund ids and scheme codes are validated before any request. An incomplete screen page is a gap and is never cached. Subsector matching ignores case. Negative "net receivables" lines no longer invalidate a fund book. Sector weights come from the newest dated snapshot.
- AMFI. Only approved workbook URLs are fetched. Fractional or ambiguous ranks are rejected. Future periods are ignored.
- Market. FII/DII flows check categories, dates and buy/sell arithmetic. Index P/E percentiles use one method (`robust_pe_percentile`) in both `get_market_context` and `get_index_valuation_history`. Breadth reports its own denominator.
- Filings and shareholding. Filings deduplicate on the full headline and carry a stable `filing_id`. Shareholding sorts by period date. XBRL is fetched only from HTTPS `nseindia.com`.
- Documents. Extracted text is stored by URL plus content hash, so a refresh cannot change an earlier citation. Links to IP literals, loopback and local hosts are refused.
- screener.in saved screens are retired. The endpoint returns a source-policy gap, because the source table approves screener.in for documents only.
- `yf.download` is the one documented exception to the single-transport rule.

### Compute

- Strategy, screen and backtest share one entry rule. An empty or prose-only `entry.signal` fails before any fetch. Unknown stop and target names fail validation. A NaN ATR no longer produces an unfloored stop. Exit labels handle gaps through the stop or target.
- Backtests mark open equity, use the actual fill for R, and avoid last-bar lookahead.
- `check_trade` scans every session after the fill for a stop breach and compares plan levels with unadjusted bars.
- DCF. Reverse solving works in either direction and reports nonconvergence. Inputs reject NaN, booleans, duplicate keys and out-of-range rates. Results are content-addressed, so a rerun cannot overwrite earlier evidence. A failed optional calculation keeps the base valuation.
- Relative valuation. A missing or nonpositive P/E cannot produce a stance or PEG.
- Governance. The MD/WTD remuneration ceiling applies only to the new `executive_remuneration` input. Invalid inputs return NOT-CHECKED. s.197 wording was checked against the Act.
- Funds. Rolling returns bound endpoint lateness and stay finite. Fund scan requires the requested return window before ranking. Look-through validates weights and does not substitute listed weight for a missing equity share.
- Market context. Missing VIX or breadth is reported as missing, never read as normal or risk-on.
- Alerts. IDs are unique, writes are atomic and locked, malformed records are skipped with a gap, and validation messages are returned to the caller.
- Holdings, allocation and wealth. Kite T+1 quantity is added; Upstox `quantity` is already the total. Kite series suffixes (`-BE`, `-RR`) are stripped from tickers. ETFs, REITs and gold bonds are classified from ISIN and series. IndMoney's live payload (a JSON string under `result`, with its own field names) now normalizes. Linked-broker rows with no reported cost carry unknown cost instead of a zero gain. Wealth no longer applies a default equity ceiling, counts all cash as emergency reserve, or treats a missing assessment as strong.
- Insurance math. Term and health sizing need explicit inputs. IRR handles tiny cash flows and multiple roots.
- Budget. Merchant matching uses word boundaries. Recurrence ignores future transactions. Category maps are validated and written atomically.

### Runtime and reports

- Reports publish as session-owned bundles in one locked rename (`finance/publication.py`). The Stop hook parses its JSON input and publishes only that session's bundle.
- Telegram sends go through `finance/telegram.py` over the shared transport. Tokens never appear in arguments or errors.
- Launcher and broker login use kernel locks, so concurrent starts run one install and one login.
- Hook paths are quoted, so installs under paths with spaces work.
- The renderer rejects invalid projections, sanitizes authored prose and writes HTML atomically. Long deck sections scroll on screen and continue across pages in print.

### Skills and docs

- Financial-analysis thresholds are attributed to the plugin, not to Varsity, and banks, NBFCs and insurers are exempt from the D/E rule.
- Valuation no longer extends growth until the DCF matches the market price.
- Technical analysis computes on adjusted candles, the same as discover and backtest.
- README, CLAUDE.md and `finance/contracts.md` match the code.

## Live checks

Run on 2026-10-11 and 2026-10-12. The MCP smoke test against live sources passed 36 checks with 3 expected degradations. One Telegram test message was delivered. Read-only holdings calls to Kite, Upstox and IndMoney were used only for payload structure. The tests use dummy values.

## Known limits

- A public document host that redirects to a private address is not blocked.
- Fund look-through does not feed the wealth equity share. It stays a labelled gap.
- Sector KPI bands and insurance premium bands are unsourced heuristics and are labelled as such.
