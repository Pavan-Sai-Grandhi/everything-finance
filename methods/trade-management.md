# Managing an open trade

**Consumers:** trade-tracker, daily-brief (position health), portfolio-review (trading
positions). **Sources, in priority order:** `varsity-ts`, `plugin`.

A position is worth holding only while the reason you entered it still holds.

> Exit when the thesis is invalidated, not when you are bored, scared or hopeful. [varsity-ts]

Every trade carries a written rationale, the trade-idea artifact: an entry, a stop, a target, a
time horizon and the specific conditions that would prove it wrong (`thesis_invalidation`).
Tracking re-checks those conditions on live data. No rationale means no discipline: capture it
before tracking.

## The exit decision, in priority order [plugin]

`check_trade` evaluates these top-down; the first hit is the verdict.

1. **EXIT_STOP**: price breached the stop, where the thesis was defined to be wrong. Every
   session after the fill is checked on its low (long) or high (short), so a breach that later
   recovered still counts, with its date. On the fill day, or with no fill date, only the close
   counts, because the day's range may predate the entry.
2. **EXIT_THESIS**: a machine-checkable invalidation fired (a daily close below the 50-EMA, a
   break of a pivot). The setup is gone even before the stop prints; exit into strength.
3. **EXIT_TARGET**: price reached the target. Book or trail per the plan.
4. **EXIT_TIME**: held for `time_stop_sessions` with neither stop nor target hit. Dead money has an
   opportunity cost.
5. **HOLD**: no mechanical condition fired. Resolve `manual_review` and data gaps before calling
   the rationale intact.

Two layers need judgement:

- **`manual_review`**: invalidations the parser cannot evaluate (an earnings miss, a pledge
  change, a downgrade). Check them against filings and news; a confirmed one is EXIT_THESIS.
- **Regime change**: for a strategy-linked trade, if the live regime no longer satisfies the
  strategy's `regime_required`, the edge that justified the trade is gone; recommend an exit even
  on a mechanical HOLD.

A verdict is a recommendation. An artifact closes only when broker executions cover the whole
entry quantity.

## Position states [plugin]

For a one-line health read, report the first state that applies:

| State | Condition |
|---|---|
| SL-HIT / TARGET-HIT | the latest completed-session close crossed the level; give its date. A price event, not an execution |
| NEAR-SL | price within 2% of the stop: be at the screen today |
| TARGET-ZONE | price within 2% of the target: decide to book or trail today |
| STALE | past the time stop, still between stop and target with no progress |
| ON-TRACK | none of the above |

An intraday cross is labelled intraday. A time stop needs the matched strategy or trade artifact
and the confirmed entry date; without them it is unassessed.

## Reading the numbers [varsity-ts]

- **Unrealized R** = (price − entry) / (entry − stop) for a long, flipped for a short. R, not
  rupees, is the unit of discipline: +2R has paid back twice its risk.
- **Remaining reward:risk to target** = (target − price) / (price − stop). It collapses as price
  nears the target; when the remaining reward no longer justifies the open risk, trimming or
  tightening the stop is rational before the target.
- **Portfolio heat**: sum the open risk. If it is high, prefer the flagged exits and resist adding.
- `check_trade`'s `as_of` is the decision bar. A personal `mark_price` may value the position; it
  never triggers a stop, target or thesis decision.

## Broker data notes [plugin]

- **Holdings** are settled delivery (CNC) stock; **positions** are intraday and F&O (MIS/NRML). A
  swing trade usually shows in holdings from T+1, or as an overnight position. Match on trading
  symbol and reconcile quantity against the artifact, noting partial fills.
- The matched execution average from order history is the entry; a holdings average cost is not
  an execution record. Keep the plan's `entry` separate: it is the trigger you designed, not
  necessarily where you were filled.
- Kite authenticates per session and Upstox daily; a stale session looks like missing tools or an
  auth error. Re-authenticate; never guess positions.

## Recording a close [plugin]

`result` is written from broker fills and charges only: the quantity-weighted exit price, the last
execution date and the trade ids. Net P&L is fills minus charges; realized R is net P&L ÷
((fill − original stop) × quantity), reversed for a short. The original stop and the entry
quantity stay the risk denominator after partial exits. Unknown charges or stop leave those
fields null with a gap, and the performance review skips the close.

A trading-session time stop counts observed sessions after entry; its alert asks for
re-validation rather than guessing a calendar date.
