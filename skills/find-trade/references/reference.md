# find-trade method — screening + candidate grading (strategy-agnostic)

Distilled from Zerodha Varsity — *Technical Analysis* (22 chapters) and *Trading Systems* (16 chapters), fetched 2026-06-10. This file is the **method find-trade applies to whatever strategy it runs** — it is deliberately strategy-neutral. The *what to trade* (the screening filters, the entry trigger, the exits) comes from the **active strategy spec** chosen by `strategy-manager`; find-trade only supplies the disciplined *how* of executing and grading it. The single source of truth for the indicator math is `<plugin>/lib/ta.py` (shared with the backtester).

## Two-stage screening — coarse cut, then fine trigger

A strategy's `screening` block defines the **coarse universe cut** (whole Nifty 500 → a shortlist), and its `entry` block defines the **fine per-stock trigger** applied to that shortlist. Keep them distinct:

| Stage | Provider | What it does |
|---|---|---|
| `screening.fundamental` | **screener.in** | Business-quality cut: market cap, ROCE, D/E, growth — keeps swing longs out of structurally broken companies (Varsity: *technicals time the trade, fundamentals pick the universe*). Not a value screen. |
| `screening.technical` | **tradingview** (server-side) or **compute** (local `lib/ta.py`) | Chart-state cut: trend (SMA50>SMA200), momentum (RSI band), participation (volume vs average) — applied across the whole universe at once. |
| `entry` (Stage 3) | local `lib/ta.py` | The exact, testable trigger on each shortlisted stock: breakout level / reversal candle at support, with the stop and target it implies. |

The provider split exists because each tool is best at one thing: **screener.in** has the fundamentals, **TradingView** can screen thousands of charts server-side in one query, and the **local compute** path (yfinance + `lib/ta.py`) is the always-available fallback that also keeps the live screen consistent with the backtest.

## The Varsity candidate-grading checklist (TA ch. 19) — indicators last

Run every shortlisted candidate through this order before emitting a signal — it grades *any* setup, whatever the strategy:

1. **Recognizable candlestick pattern** — single (marubozu, hammer, shooting star; doji/spinning top = indecision) or multi (engulfing, harami, piercing, morning/evening star). A pattern needs location context: a hammer matters after a decline *at support*, not mid-air.
2. **S&R confirmation** — the pattern must form at a support (for longs) that also serves as the stop basis. A zone needs ≥2 historical touches, ideally months apart.
3. **Volume confirmation** — pattern/move-day volume above the 10-day average. Price up + volume up = participation; price up + volume down = suspect. (The engine reports `vol_vs_10d`; below 1.0 → flag "weak", rank last.)
4. **Dow stage** — trade with the primary trend; avoid fresh longs late in markup. HH-HL = uptrend.
5. **Indicator agreement (confirmation, not veto)** — RSI >70 overbought / <30 oversold, but in strong trends RSI holding 40–60 = healthy continuation; MACD cross direction. If indicators disagree with price action, **price action wins**.
6. **RRR gate** — Varsity minimum reward:risk ≥ 1.5 for swing trades; skip otherwise. There is always another candidate.

## Signal construction discipline (Trading Systems module)

- **Entry** at the pattern-defined trigger (breakout level / reversal-candle high), not live market price.
- **Stop** at structure — the recent swing low or breakout pivot, **not** the full consolidation low. (Anchoring the stop at the consolidation low inflates risk to ≈ the measured-move height, pinning RRR near 1.0 so nothing passes. The measured move sizes the *target*; the swing low sizes the *stop*.)
- **Target** at the next resistance; for a blue-sky stock at/above its 52-week high (no overhead resistance), use the measured move of the prior consolidation and label it "measured-move".
- **Position size from risk, never conviction**: `qty = (capital × risk%) / (entry − stop)`, default 1%. Conviction changes nothing; only the stop distance does. Never widen a stop to "give it room".
- **Expectancy mindset**: any single signal can fail; the edge is statistical, and it lives in the strategy's validated backtest — which is why find-trade refuses to run an unvalidated (`draft`) or retired (`inactive`) strategy.

## Why no built-in default strategy

Earlier this engine carried three hardcoded setups and a default fundamental query. That made it the one "strategy" that never passed the generate→validate→pick lifecycle — an un-backtested edge masquerading as the house default. find-trade now runs **only** specs from the validated library, and when the user names none it asks `strategy-manager pick` for the regime-fit choice. If the library is empty or nothing fits the tape, the correct output is **no trade**, with a pointer to build/validate a strategy — not a fabricated signal. The seed library in `strategy-manager/assets/seed-strategies/` (the common swing methods, as `draft` specs) is the starting stock to validate, not a shortcut around validation.

## Failure modes to flag in output

- Breakout on low volume → mark "weak", rank last.
- Setup against the sector trend (check the stock's sectoral index direction) → note it.
- Earnings/results date within the holding window (check screener.in company page) → warn: event risk.
- Technical screen fell back to local compute (TradingView unreachable) → say the cut approximates, doesn't equal, the provider's.
