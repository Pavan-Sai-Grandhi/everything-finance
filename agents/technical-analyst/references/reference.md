# Technical analysis method (self-contained)

Distilled from Zerodha Varsity — Technical Analysis module (https://zerodha.com/varsity/module/technical-analysis/, 22 chapters). This agent is forked; everything it needs is in this file.

## The checklist (Varsity ch. 19) — work in this order

1. **Candlestick pattern** — single (marubozu, hammer, hanging man, shooting star; doji/spinning top = indecision/transition) or multi (engulfing, harami, piercing/dark cloud, morning/evening star). Patterns need location context: a hammer matters after a decline at support, not mid-air.
2. **S&R** — a level needs ≥2 historical touches, ideally months apart. Support basis for longs doubles as the stoploss basis. Map S1/S2 and R1/R2 with touch evidence.
3. **Volume** — pattern/move day vs 10-day average. Price up + volume up = participation; price up + volume down = suspect. Accumulation vs distribution signature over recent weeks.
4. **Dow stage** — primary trend via higher-highs/higher-lows (or LH-LL); phase: accumulation → markup → distribution → markdown. Note where in the phase the stock sits; late-markup longs are chasing.
5. **Indicators — confirmation only, never veto of price structure**: RSI >70 overbought / <30 oversold, but in strong trends RSI holding 40–60 = healthy continuation; MACD signal-line cross direction; price vs Bollinger middle band. Divergences (price HH, RSI LH) are warnings worth flagging.
6. **Levels for the debate**: the bull thesis dies below a specific support; the bear thesis dies above a specific resistance. Name both with evidence.

## Moving averages

- 50-EMA rising with price above = tradeable uptrend; 200-EMA position = long-term regime.
- 9/21 EMA crossovers for short swings; unreliable in ranges — say "range, crossover signals untrustworthy" when applicable.

## Data sources

- **yfinance** (`<SYMBOL>.NS`) is the primary OHLCV source for everything computed here — no bot-wall, gives clean daily candles + volume. Prefer OHLCV already passed in by the orchestrator over re-fetching.
- NSE quote pages (Playwright real Chrome, homepage cookie-bootstrap first) only when yfinance lacks a symbol.
- **TradingView is not scraped** — its pages are Akamai-walled and yfinance already supplies the data. Its role is a human-facing link: put `https://www.tradingview.com/symbols/NSE-<TICKER>/` in the report so the user can eyeball the live chart. (If a chart *image* in the report is wanted, self-render a candlestick PNG from the cached OHLCV — don't screenshot TradingView.)
- Daily timeframe primary; weekly for trend context. Never intraday for this plugin's swing horizon.

## Report discipline

Every level cites evidence (touch dates/counts). Indicators never override price structure. Missing data → "DATA GAP" sections, not guesses.
