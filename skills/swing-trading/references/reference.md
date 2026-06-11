# Swing screening knowledge base

Distilled from Zerodha Varsity — Technical Analysis (https://zerodha.com/varsity/module/technical-analysis/, 22 chapters) and Trading Systems (https://zerodha.com/varsity/module/trading-systems/, 16 chapters). Fetched and summarized 2026-06-10.

## The Varsity TA checklist (chapter 19, "The Finale")

Run every candidate through this order — indicators come last, as confirmation only:

1. **Recognizable candlestick pattern** — single (marubozu, hammer, hanging man, shooting star, doji/spinning top as transition warnings) or multi (engulfing, harami, piercing/dark cloud, morning/evening star).
2. **S&R confirmation** — the pattern must form at a support (for longs) that also serves as the stoploss basis. A support/resistance zone needs ≥2 historical touches, preferably spaced months apart.
3. **Volume confirmation** — pattern day volume at least above the 10-day average. Price up + volume up = institutional participation; price up + volume down = suspect move.
4. **Dow stage** — trade in the direction of the primary trend; avoid fresh longs late in the markup phase (Dow phases: accumulation → markup → distribution → markdown). Higher highs/higher lows define an uptrend.
5. **Indicator agreement (bonus, not veto)** — RSI: >70 overbought / <30 oversold, but in strong trends treat RSI holding 40–60 as healthy continuation; MACD signal-line crossover direction; price vs Bollinger middle band. If indicators disagree with price action, price action wins.
6. **RRR gate** — Varsity's minimum: reward:risk ≥ 1.5 for swing trades; skip the trade otherwise, there is always another candidate.

## Candlestick rules of thumb (chapters 4–10)

- Patterns need context: a hammer only matters after a decline, at support.
- "Buy strength, sell weakness": bullish-pattern entry near the close of the confirmation candle or its high break.
- Stoploss = low of the pattern (bullish) / high of the pattern (bearish).
- Avoid trading patterns on extremely small candles (indecision) or after gaps into resistance.

## Moving averages & trend filter (chapter 13)

- 50-EMA rising and price above it = tradeable uptrend for swing longs.
- 9/21 EMA crossover useful for shorter swings; whipsaws in ranges — only apply in trending phases.

## Trading-systems discipline (Trading Systems module)

- A system needs fixed, written rules: scan universe → setup definition → entry trigger → SL → target → position size. This pipeline is that system; do not improvise mid-run.
- **Position sizing**: risk a fixed fraction (1%) of capital per trade. Qty = (capital × 1%) / (entry − SL). Conviction changes nothing; only the SL distance does.
- **Expectancy mindset**: individual signals can fail; the funnel's edge is statistical. Never widen a stoploss to "give it room".
- Momentum-portfolio chapter: monthly relative-strength ranking is a valid alternative lens — top decile 12-month performers, rebalanced, works as a momentum overlay for candidate ranking.

## Screen thresholds by risk profile

| Filter | Conservative | Default | Aggressive |
|---|---|---|---|
| Market cap | > ₹5,000 Cr | > ₹1,000 Cr | > ₹500 Cr |
| ROCE | > 15% | > 12% | > 10% |
| D/E | < 0.5 | < 1 | < 1.5 |
| P/E | < 40 | < 60 | no cap |
| Sales growth 3Y | > 10% | > 8% | > 0% |

The fundamental gate exists to keep swing longs out of structurally broken companies (a Varsity theme: technicals time the trade, fundamentals pick the universe). It is not a value screen.

## Backtest evidence (2026-06-10, bundled backtest skill, 3 large-caps × 5y)

- The **mechanical** EMA-tag pullback (no reversal candle, no S/R zone check) backtested to *negative* expectancy (−0.08R, 89 trades). The reversal-candle + tested-S/R requirements in Stage 2 are load-bearing filters, not decoration — never relax them to widen the funnel.
- The volume-confirmed 20-day breakout showed modest positive expectancy on the same sample. Re-validate with `/backtest` on a wider basket before trusting either number.

## Failure modes to flag in output

- Breakout on low volume → mark "weak", rank last.
- Setup against the sector trend (check the stock's sectoral index direction) → note it.
- Earnings/results date within the holding window (check screener.in company page) → warn: event risk.
