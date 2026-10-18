# Trading systems

**Consumers:** strategy-manager, discover (trade path), trade-tracker. **Sources, in priority
order:** `varsity-ts`, `quantinsti`, `marketcalls`, `fortraders`, `plugin`.

This is the system framework only: the discipline that turns any strategy idea into a complete,
risk-bounded, testable spec. It ships no strategies. Trade logic always comes from a reference
article the user supplies; the framework supplies the risk layer.

## A complete system [varsity-ts]

A spec missing any of these is incomplete and is not emitted:

1. **Universe**: what is tradable, with any fundamental or liquidity gate.
2. **Entry trigger**: an exact, testable condition, a price or level event plus indicator or
   volume confirmation. "Looks good" is not a trigger.
3. **Exit**: a stoploss where the thesis is wrong, a target where you book, and a time stop for a
   swing or positional system.
4. **Position sizing** from risk, not conviction.
5. **Risk caps**: per-trade risk, total open risk (portfolio heat), concentration, rebalance cadence.
6. **Regime condition**: when the system may run. Most retail write-ups omit it; supply it.

A system is a fixed, written rule set executed without improvisation. The rules carry the edge
across many trades; any single trade can fail.

## Reading a strategy out of an article [varsity-ts] [plugin]

Extract each element and quote the source for it. Whatever the article does not state is
completed from this framework, never by inventing trade logic, and flagged as added.

| Element | Pull from the article | If the article is silent |
|---|---|---|
| Universe | an index, a liquidity or fundamental filter, a watchlist | ask, or default to a broad liquid set (nifty500) and say so |
| Entry | the exact condition | cannot be inferred: ask |
| Exit | stop and target; trailing or rebalance rules | add a structure stop, a minimum-RRR target and a time stop |
| Ranking | for baskets: metric, hold count, weighting, cadence | none for single-name setups |
| Indicators | exactly those named, and the timeframe | use what entry and exit imply; state it |
| Regime | the conditions it claims to work in | apply the minimum structural gate and say so |

Encode the source's actual exit. A trailing stop is a trailing stop, not a long time stop; a
moving-average exit is a signal exit. Reserve a fixed target for setups whose source names one.

## Expectancy [varsity-ts]

```
Expectancy (R) = (Win% × Avg win in R) − (Loss% × Avg loss in R)
```

1R is the initial risk, entry minus stop. A 35% win rate with 2.5R winners beats a 65% win rate
with 0.5R winners: win rate alone decides nothing. An article's claimed numbers are not your
results; an unvalidated system is a hypothesis.

| Backtest expectancy | Verdict [plugin] |
|---|---|
| below 0R | no edge |
| 0 to 0.2R | no tradeable edge (fragile) |
| above 0.2R over at least ~30 trades | edge |

Fewer than 30 trades overrides the table: the run is inconclusive, whatever the expectancy. 0.9R
over 12 trades is an anecdote.

## Sizing and risk [varsity-ts]

```
qty = (capital × risk_per_trade%) / (entry − stop)
```

Default risk is 1% per trade. Conviction never changes size; only the stop distance does. Never
widen a stop to give a trade room. Cap portfolio heat, the sum of open per-trade risk, at 6%
[plugin], so a cluster of correlated stops cannot blow a hole in the book. Equal-weight a ranked
basket unless the source says otherwise.

## Building the signal [varsity-ts] [plugin]

- **Entry**: planned at the signal bar's close, the price the backtest sizes from (its fills are
  at the next open), so live and backtest share one rule. A pattern trigger such as a breakout
  level is a manual change: state it, recompute the stop distance and size, and do not call it
  the validated rule.
- **Stop at structure**: the recent swing low or the breakout pivot, not the full consolidation
  low. Anchoring at the consolidation low inflates risk to about the measured move and pins RRR
  near 1.
- **Target** at the next resistance. For a stock at or above its 52-week high with no overhead
  resistance, use the measured move of the prior consolidation and label it so.
- The edge is statistical and lives in the strategy's validated backtest. That is why only an
  active, validated spec produces a signal, and why there is no built-in default strategy: a
  house setup would be the one strategy that never passed validation. An empty library or a tape
  nothing fits produces no trade.

## The regime gate [varsity-ts] [plugin]

The regime decides whether and how big a strategy runs today; it never changes what it trades.
Set `regime_required` from the conditions the article claims. Regime fit is checked at selection
time, not stored in `status`: an active strategy stays active across regimes and is simply not
selected while the tape does not fit.

Indian macro context, which sets risk-on or risk-off and never the trigger:

- repo-rate direction: cutting helps rate-sensitives (financials, autos, realty), hiking favours
  defensives;
- CPI: cooling supports cuts, hot inflation pressures multiples;
- USD-INR: a weak rupee helps exporters (IT, pharma) and hurts importers and oil;
- FII/DII flows: sustained FII selling caps upside; DII buying cushions;
- India VIX: below ~13 complacent, 13–20 normal, above 20 fear; size down as it rises.

The rate cycle has no approved data source, so it enters only when the user supplies it.

## Lifecycle [plugin]

| Status | Meaning | Tradeable |
|---|---|---|
| `draft` | generated from an article; backtest or the numeric indicator study not yet passed | no |
| `active` | passed the activation gate (expectancy above 0.2R over at least ~30 trades, indicator study done) | only when selected for a fitting regime |
| `inactive` | failed the backtest, deactivated by live results, or retired by hand | no |

Learning from live trades:

- A live close counts only with broker execution ids, the full exit quantity, the original risk
  and actual charges. Fix an incomplete close from broker history, never from unrealized marks.
- At least ten verified closes before live data changes anything; fewer is noise.
- Live expectancy below 0R over the sample: deactivate. Ten trades is the minimum to act, not
  proof the edge is gone for good.
- Live expectancy positive but below `max(0.1R, 0.5 × backtest)`: the edge is decaying; optimize.
  Diagnose from the exit-reason breakdown, propose one rule change, bump `version`, log it, and
  re-validate. Tuning to live results without re-validation is curve-fitting.

`finance/compute/strategy_library.py` enforces these thresholds.

## Backtest honesty [quantinsti] [marketcalls] [fortraders] [varsity-ts]

1. **Look-ahead**: signals on bar t's close execute at bar t+1's open; indicators use trailing
   windows only; when stop and target fall inside one bar, the stop is assumed hit first.
2. **Survivorship**: today's index members miss the delisted losers. The price source does not
   reconstruct historical membership; always disclose it, and never apply a guessed adjustment.
3. **Overfitting**: parameters come from the source article, fixed before the run. To tune,
   split train/test: tune on the older 70%, report only the untouched recent 30%.
4. **Costs**: the engine charges an assumed ~0.25% round trip. Test a higher cost before trusting
   a small edge.

Reading the results:

- **Profit factor** is gross winning over gross losing P&L; above 1 means the closes made money.
  Check the sample and whether one outlier carries it.
- **Drawdown** is the worst single account's daily drawdown, not a portfolio's.
- **Yearly breakdown**: an edge that exists only in one bull year is a bull-market detector.
  Compare years in R.
- **Against buy-and-hold**: each symbol is its own account and the strategy is often in cash;
  compare symbol by symbol over the same dates.
- **Exit breakdown**: TIME exits above 50% with a fixed target mean the target and time stop do
  not fit the universe's volatility. If the source trails, the fix is a trailing stop, not a
  longer time stop. With a trailing stop, an SL exit is often a trailed winner: read it with its R.
- A passed backtest is a hypothesis that survived history, not a guaranteed edge. Live edge
  degrades; sizing discipline is what survives.
