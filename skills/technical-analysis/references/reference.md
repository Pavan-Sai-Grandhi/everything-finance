# Technical analysis method (Varsity, self-contained)

Distilled from Zerodha Varsity — Technical Analysis module (https://zerodha.com/varsity/module/technical-analysis/, 22 chapters).

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

## Working the data

- **Check the live quote against the latest EOD close before you trust a level** — a divergence beyond ~1% means one of the two is stale, and a level read off a stale close is not tradeable.
- **Indicator math is shared, not hand-rolled.** EMA/SMA/RSI/MACD/ATR/Bollinger and the candlestick patterns are defined once in `<plugin>/finance/compute/ta.py` — the same module the backtest and find-trade use, so a divergent RSI here would make the verdict inconsistent with the screen that surfaced the stock. Run it over the candles file:
  ```bash
  python3 - <<'PY'
  import json, sys, pandas as pd
  sys.path.insert(0, "<plugin>")
  from finance.compute import ta
  df = pd.DataFrame(json.load(open("<candles_path>")))
  df.index = pd.to_datetime(df.pop("date")); df = df.rename(columns=str.capitalize)
  print(ta.add_indicators(df).tail(5).to_string())   # ema20/ema50/sma200/rsi14/atr14/vol10/hh20/ll20
  PY
  ```
  `ta.ema(df["Close"], 200)`, `ta.macd(...)` and the pattern helpers cover what `add_indicators` doesn't.
- If a symbol cannot be resolved, record it as a labelled data gap.
- **TradingView is not scraped.** Its role is a human-facing link: put `https://www.tradingview.com/symbols/NSE-<TICKER>/` in the report so the user can eyeball the live chart. No chart rendering, no screenshots — the machine substance is the numeric `ta.py` read.
- Daily timeframe primary; weekly for trend context. Never intraday for this plugin's swing horizon.
