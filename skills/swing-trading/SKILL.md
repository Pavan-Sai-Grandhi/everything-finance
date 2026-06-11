---
name: swing-trading
description: Screen the Nifty 500 for swing trade candidates by combining screener.in fundamental filters with technical rules, emit entry/stoploss/target signals, and — on the user's confirmation — persist a trade-idea artifact the trade-tracker skill monitors. Use whenever the user asks to screen stocks, find swing trades, scan the market, look for setups, run the pipeline, or asks "anything worth trading this week?" — even if they don't say "screen" explicitly.
argument-hint: "[optional: sector filter | 'aggressive'/'conservative' | strategy:<name>]"
allowed-tools: WebFetch, Read, Write, Bash, mcp__playwright__*
---

# Swing Trading Pipeline (Nifty 500)

Three-stage funnel: fundamental gate → technical setup scan → signal construction, then an optional **commit** step that persists the chosen idea for the `trade-tracker` skill. Read `references/reference.md` first for the screening thresholds and the technical checklist this skill enforces.

**Strategy spec (optional):** if invoked with `strategy:<name>` (or the user references a managed strategy), load `artifacts/strategies/<name>.yml` from `strategy-manager`. Two gates, in order:
1. **Status** — if `status` is not `active` (`draft` = not yet backtested, `inactive` = retired), return zero candidates and say so: a non-active strategy isn't validated to trade; point the user to `/strategy-manager validate <name>`.
2. **Regime fit** — even when active, a strategy only runs while the tape fits its `regime_required`. If you weren't handed a fresh selection, defer the choice to `/strategy-manager pick` (it checks regime-fit across the active library) rather than overriding it here. If the user explicitly forces this named strategy, you may proceed but flag any conflict between its `regime_required` and the current regime.

When cleared, use the spec's `universe`, `entry`, `exit`, and `sizing` as the screen definition instead of the defaults below. Without a spec, use the defaults here. Either way the discipline rules (CLAUDE.md) bind.

**Sites/sources for this skill only:** screener.in (fundamental screen, auth cookies), yfinance (EOD OHLCV — primary price source), NSE (Nifty 500 constituents). TradingView is not scraped — include a `tradingview.com/symbols/NSE-<SYMBOL>/` link in the report for the user's own chart check. Do not use other sites.

## Stage 1 — Fundamental gate (screener.in)

Build the screen at `https://www.screener.in/screens/new/` — **authentication required**: the query-URL form 302-redirects to login for anonymous clients (verified 2026-06), so use `SCREENER_SESSION_ID`/`SCREENER_CSRF_TOKEN` from `~/.claude/.env` (sessionid/csrftoken cookies). If cookies are missing/expired: reuse the most recent `gate_survivors.json` from `artifacts/.cache/` if < 7 days old (fundamentals move slowly), else skip the gate, pre-rank the Nifty 500 by 6-month momentum instead, and flag "fundamental gate skipped — screener auth unavailable" in data gaps. Default query (relax per user's risk profile, see reference.md):

```
Market Capitalization > 1000 AND
Return on capital employed > 12 AND
Debt to equity < 1 AND
Profit growth > 0 AND
Sales growth 3Years > 8 AND
Price to Earning < 60
```

Extract only the results table (name, NSE code, CMP, ROCE, D/E). Cap at ~60 survivors; if more, tighten ROCE to >15. If a smaller test/time cap forces a subset, **sample by 3-month momentum rank, not by ROCE** — top-ROCE subsets skew toward expensive compounders mid-pullback and starve the breakout/pullback setups. Save survivors to `artifacts/.cache/gate_survivors.json`.

## Stage 2 — Technical setup scan

For each survivor (batch, don't fetch one page per indicator), pull ~6 months of daily candles. Source order: **yfinance via a Python script (`<SYMBOL>.NS`, batched — fastest and proven)**, NSE quote/chart API via Playwright real Chrome only if yfinance lacks the symbol. Cache OHLCV under `artifacts/.cache/`. Keep a stock only if it matches at least one setup from reference.md:

1. **Pullback to support in an uptrend** — price above rising 50-EMA, retraced to a tested S/R zone or the EMA itself, reversal candle (hammer/bullish engulfing/piercing) at the zone within the **last 3 sessions** (EOD data rarely catches "forming" on the scan day itself).
2. **Range breakout with volume** — close above a ≥4-week consolidation high on volume > 1.5× 10-day average.
3. **Momentum continuation** — recent 52-week-high stock consolidating with RSI holding 40–60, no lower lows.

Volume confirmation is mandatory — a pattern without above-average volume gets flagged "weak" and ranked last, not dropped silently.

## Stage 3 — Signal construction

For each finalist produce, using the discipline rules in the plugin CLAUDE.md:

- **Entry**: pattern-defined trigger level (breakout level / reversal-candle high), not market price.
- **Stoploss**: the most recent swing low or breakout pivot — NOT the full consolidation low. (For a measured-move setup this matters: anchoring the SL at the consolidation low makes risk ≈ the measured-move height, pinning RRR near 1.0 so nothing passes the gate. The measured move sizes the *target*; the recent swing low sizes the *stop*.)
- **Target**: next resistance; for blue-sky stocks at/above their 52-week high (no overhead resistance), use the measured move of the prior consolidation as the target and label it "measured-move". If RRR < 1.5 at that target, drop the candidate and say so.
- **Position size**: qty for 1% capital risk (ask the user for capital once; default ₹5,00,000 if they don't say).

## Output

Render `assets/signal-report.html` (bundled with this skill) filled with the candidate table (ticker, setup type, entry, SL, target, RRR, volume confirmation, fundamental snapshot), save to `artifacts/YYYY-MM-DD/swing-trading.html`, and summarize the top 3 in chat. Include a **Data gaps** section for any stock/source that failed to fetch.

## Stage 4 — Suggest & commit (hand-off to trade-tracker)

After the report, **suggest the single highest-conviction candidate** (or the top 2–3 if genuinely tied) in one line each: ticker, setup, entry/SL/target, RRR, and the one-sentence thesis. Then ask plainly: *"Want me to track <TICKER>? (yes / pick another / no)"*

**Only on an explicit "yes"** (or the user naming which candidate to track) persist a **trade-idea artifact** — this is the contract `trade-tracker` reads to monitor the position later:

- Path: `artifacts/trades/<SYMBOL>-<YYYY-MM-DD>.yml` (SYMBOL = NSE trading symbol, no `.NS`). Create `artifacts/trades/` if needed. If a file for the same symbol+date exists, append `-2` etc. rather than overwriting.
- Fill **every** field of the schema below from the screen you just ran — do not leave the thesis or invalidation conditions blank, since those are exactly what `trade-tracker` re-checks:

```yaml
symbol: TITAN                     # NSE trading symbol, no .NS suffix
exchange: NSE
source_skill: swing-trading
strategy: null                    # strategy spec name if screened with strategy:<name>, else null
created: 2026-06-11               # YYYY-MM-DD
status: idea                      # idea | open | closed  (trade-tracker promotes idea→open on a matching broker fill)
setup: range-breakout             # the matched setup type
direction: long
rationale: >                      # the thesis in plain words — WHY this trade
  Multi-line free text: the setup, the leadership/fundamental backdrop, and the
  specific conditions that must stay true for the thesis to hold.
thesis_invalidation:              # machine-checkable kill conditions trade-tracker tests
  - "daily close below 50-EMA"
  - "break of breakout pivot 3,250"
plan:
  entry: 3300                     # trigger level (not live price)
  stop: 3180                      # initial stoploss
  target: 3600                    # first target
  rrr: 2.5
  time_stop_sessions: 20          # exit if neither stop nor target hit by N sessions
  entry_basis: "close above 4-week high on >1.5x 10-day volume"
sizing:
  capital: 500000
  risk_per_trade_pct: 1.0
  qty: 41                         # suggested qty at 1% risk
regime_at_creation: "Nifty above 200-EMA, India VIX 12 — risk-on"
fundamental_snapshot: "ROCE 22%, D/E 0.1, sales 3Y 14%"
tradingview: "https://www.tradingview.com/symbols/NSE-TITAN/"
notes: ""
```

Confirm the saved path in chat and tell the user they can run `/trade-tracker` once they execute (or to re-validate any time). If the user says no, persist nothing. End with the standard risk note.
