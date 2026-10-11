# Seed strategy library

These are draft research templates, not validated trading systems or recommended allocations. Numeric cutoffs are design assumptions. No bundled seed includes performance evidence, and field resolvability alone does not establish an edge.

Copy a selected seed to the path returned by `finance.paths.state_dir("strategies")` under the session artifact root. Preserve the draft until the applicable validation is complete; never activate all seeds simply because they parse.

## Validation by purpose

- **Trading:** compare the prose setup with the exact expressions the engine executes. Most swing seeds contain coarse `compute_filters`; those are not a mechanical definition of a retest, reversal candle, trendline touch or Fibonacci impulse. Define an explicit `entry.signal` and any required feature in the shared TA registry before testing that idea. The engine refuses missing/empty signals before fetching; it never converts screening filters into an entry automatically. Check stop/target meanings as well: `range_low` and `measured_move` use the engine's lookback range, not a manually selected squeeze candle. Backtest the exact final rules, with costs and out-of-sample evidence, before activation. A result for a coarse proxy does not validate the prose strategy.
- **Investment:** validate the approved fundamental query, universe and ranking. Activation makes the screen executable for research; it is not a buy recommendation and has no trading expectancy.
- **Funds:** validate the category, scan window, AUM floor and shortlist size against `get_fund_scan`. A historical scan window does not define the investor's holding horizon, and a large-cap equity fund does not guarantee capital protection.

## Swing ideas and unresolved definitions

| Seed | Intended idea | What must be made explicit before activation |
|---|---|---|
| `ema-pullback-swing` | Pullback to a rising moving average | Average period, proximity, reversal candle, support and volume confirmation |
| `breakout-retest-swing` | Retest after a consolidation break | Prior breakout, elapsed retest window, pivot tolerance and separate breakout/retest volume rules |
| `rsi-trendline-reversal-swing` | Reversal near a rising trendline | Trendline construction, touch tolerance, reversal and the exact RSI band |
| `inside-bar-nr7-swing` | Expansion after a squeeze | Verify `coil_breakout` matches the intended squeeze and choose the exact stop/target rule |
| `fibonacci-retracement-swing` | Retracement of an identified impulse | Causal impulse pivots, retracement zone and confirmation candle |

TradingView filters are coarse provider-specific cuts. SMA filters and local EMA filters are different definitions; do not describe the compute path as an exact fallback unless equivalence has been established. The shared local entry engine owns the final executed expressions.

A Nifty daily EMA200 gate is market context, not a weekly confirmation for the stock. True multi-timeframe confirmation needs separately defined, completed weekly bars and the same causal rule in live and historical execution; no seed currently establishes that overlay.

## Retired source

The former `soic-crossperiod-screener-in` seed was removed because repository policy approves screener.in only for document discovery. Legacy saved-screen calls return a gap without fetching. Re-author any user copy with approved decision data; do not silently replace unavailable cross-period conditions with point-in-time proxies.

General educational references and old screen-result counts do not validate the exact cutoffs or execution rules. Recheck the sources and retain evidence with a user strategy when developing it.
