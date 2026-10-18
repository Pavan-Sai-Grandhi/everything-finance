# Seed strategy library

These are draft templates. None has been backtested, and their numeric cutoffs are design choices. A seed that parses is not a seed with an edge.

Copy a seed into `finance.paths.state_dir("strategies")` and keep it `draft` until it passes validation.

## Validation by purpose

- **Trading:** most swing seeds only have coarse `compute_filters`, which do not define a retest, a reversal candle, a trendline touch or a Fibonacci impulse. Write an explicit `entry.signal` (and register any missing feature in `compute/ta.py`) before testing the idea; the engine refuses a spec without one. `range_low` and `measured_move` use the engine's lookback range, not a hand-picked candle. Backtest the final rules, with costs and out-of-sample data, before activating. A backtest of the coarse filters does not validate the strategy described.
- **Investment:** validate the Tickertape query, universe and ranking. Active means the screen runs; it is not a buy recommendation.
- **Funds:** validate the category, scan window, AUM floor and shortlist size against `get_fund_scan`. The scan window is not the investor's holding period.

## What each swing seed still needs

| Seed | Idea | Must be defined before activation |
|---|---|---|
| `ema-pullback-swing` | Pullback to a rising moving average | Average period, how close counts as a touch, reversal candle, support and volume rule |
| `breakout-retest-swing` | Retest after a consolidation break | The prior breakout, retest window, pivot tolerance, and separate breakout and retest volume rules |
| `rsi-trendline-reversal-swing` | Reversal near a rising trendline | How the trendline is drawn, touch tolerance, reversal rule and the RSI band |
| `inside-bar-nr7-swing` | Expansion after a squeeze | Whether `coil_breakout` matches the intended squeeze, and the stop and target rule |
| `fibonacci-retracement-swing` | Retracement of a prior impulse | Impulse pivots that use only past bars, the retracement zone and the confirmation candle |

TradingView filters use SMAs and local filters use EMAs, so the local path is a different screen, not an exact fallback.

The Nifty 200-EMA gate is market context, not weekly confirmation for the stock. No seed has a weekly-timeframe rule yet; adding one needs completed weekly bars computed the same way live and in the backtest.
