# Technical analysis

**Consumers:** technical-analysis, discover (trade candidates), strategy-manager (indicator
study), sector-analysis. **Sources, in priority order:** `varsity-ta`, `plugin`.

Every indicator value comes from `get_technicals`, which runs `finance/compute/ta.py`: the same
definitions the screens and the backtest use (EMA is SMA-seeded, ATR is Wilder). Never compute an
indicator by hand.

## The checklist: work in this order [varsity-ta:19]

The order is part of the method. Indicators come last because they confirm; price action and
support/resistance decide.

1. **Candlestick pattern.** Single-candle: marubozu, hammer, hanging man, shooting star; a doji or
   spinning top means indecision. Multi-candle: engulfing, harami, piercing / dark cloud, morning
   and evening star. A pattern needs location: a hammer matters after a decline at support, not
   mid-air.
2. **Support and resistance.** A level needs at least two historical touches, ideally months
   apart. For a long, the support that makes the case is also the stop's basis. Map S1/S2 and
   R1/R2 with their touch dates.
3. **Volume.** Compare the pattern or move day with the 10-day average. Price up on rising volume
   is participation; price up on falling volume is suspect. Read the accumulation or distribution
   signature over recent weeks.
4. **Dow stage.** The primary trend from higher highs and higher lows (or lower highs and lower
   lows), and the phase: accumulation, markup, distribution, markdown. Trade with the primary
   trend; a fresh long late in markup is chasing.
5. **Indicators, as confirmation only.** RSI above 70 is overbought and below 30 oversold, but in
   a strong trend RSI holding 40–60 is healthy continuation. Note the MACD signal-line cross and
   price against the Bollinger middle band. A divergence (price makes a higher high, RSI a lower
   high) is a warning worth flagging. When indicators disagree with price action, price action
   wins.
6. **Reward:risk.** At least 1.5 for a swing trade (`RULES.md` sets the floor). Below it, skip;
   there is always another candidate.

For a thesis, name the two levels that kill it: the support whose break ends the bull case and
the resistance whose break ends the bear case, each with its touch evidence.

## Moving averages [varsity-ta]

- Price above a rising 50-EMA is a tradeable uptrend; position against the 200-EMA is the
  long-term regime.
- 9/21-EMA crossovers time short swings but fail in ranges; in a range, say crossover signals are
  untrustworthy.

## Reading the data [plugin]

- Read on split- and bonus-adjusted daily candles, the basis the screens and the backtest use;
  raw bars across a corporate action corrupt every average and older level.
- Check the live quote against the latest close. A gap beyond about 1% means one of them is
  stale, and a level struck on a stale close is not tradeable.
- The feed's last bar can be an unclosed session with a provisional high or low. Strike levels on
  closed sessions only (`get_technicals(drop_last=true)`), read the live bar from `get_quote`, and
  label an intraday reading as intraday.
- Daily is the primary timeframe, weekly is context. No intraday reads at this plugin's swing
  horizon.
- TradingView is a link for the reader (`https://www.tradingview.com/symbols/NSE-<TICKER>/`), never
  a data source.

## Grading a trade candidate [varsity-ta:19]

Run every shortlisted candidate through the checklist above before emitting a signal. These
failures are flagged in the output:

- a breakout on volume below the 10-day average: "weak", ranked last;
- a setup against its sector index's trend;
- a results date or board meeting inside the holding window (from `get_filings`; none found is a
  gap, not proof of no event): event risk.
