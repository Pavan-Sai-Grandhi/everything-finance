# Trade-tracking & early-exit framework

The discipline behind `trade-tracker`: a position is only worth holding while the **reason you entered it** still holds. This file defines what "still holds" means and how the exit decision is made. Grounded in the same risk discipline as the rest of the plugin (CLAUDE.md trading rules).

## The one rule

> Exit when the thesis is invalidated — not when you're bored, scared, or hopeful.

Every trade entered through this plugin carries a written rationale (the trade-idea artifact): an entry, a stop, a target, a time horizon, and the **specific conditions that would prove it wrong** (`thesis_invalidation`). Tracking is just re-checking those conditions on live data and acting when one fires. No artifact = no discipline; capture the rationale before tracking (SKILL §2).

## The exit decision (priority order)

`validate_trade.py` evaluates these top-down; the first hit is the verdict:

1. **EXIT_STOP** — price breached the stoploss. Non-negotiable; the stop is where the thesis was defined to be wrong. (Uses the bar's low for longs / high for shorts, plus the live LTP, so an intrabar breach counts.)
2. **EXIT_THESIS** — a machine-checkable invalidation fired (e.g. *daily close below 50-EMA*, *break of pivot 3,250*). The setup that justified the entry is gone even if the hard stop hasn't printed — exit into strength rather than waiting for the stop.
3. **EXIT_TARGET** — price reached the target. Book, or trail per the plan; either way the original trade is complete.
4. **EXIT_TIME** — held ≥ `time_stop_sessions` with neither stop nor target hit. Dead money has an opportunity cost; a swing trade that hasn't worked in its window is telling you something.
5. **HOLD** — none of the above. The rationale is intact; do nothing.

Two layers the script defers to the skill (qualitative judgement):
- **`manual_review`** — invalidations the parser can't evaluate (earnings miss, pledge change, downgrade). Check them against news/filings and treat a confirmed one as EXIT_THESIS.
- **Regime change** — for strategy-linked trades, if the live regime no longer satisfies the strategy's `regime_required`, the edge is gone → recommend exit even on a mechanical HOLD.

## Reading the numbers

- **Unrealized R** = (current − entry) / (entry − stop) for longs (flipped for shorts). R, not rupees, is the unit of discipline: +2R means the trade has paid back twice its risk. Manage on R, size on R.
- **Remaining RRR to target** = (target − price) / (price − stop). As price climbs toward target this collapses; when the remaining reward no longer justifies the open risk, trimming or tightening the stop is rational even pre-target.
- **Portfolio view**: sum the open risk (heat). The single-trade verdict is local; if total heat is high, prefer the exits the script flags and resist adding.

## Broker data notes (Kite / Upstox MCP)

- Both hosted MCPs are **read-only** — they expose holdings, positions, orders, quotes; they cannot place or modify orders. That matches this plugin's hard rule: it recommends exits, the user executes them.
- **Holdings** = settled/delivery (CNC) stock; **Positions** = intraday + F&O (MIS/NRML). A swing trade usually shows in holdings (T+1 onward) or as an overnight position. Match on trading symbol; reconcile qty against the artifact's planned qty and note partial fills.
- Auth is per-session (Kite) or daily (Upstox); a stale session looks like "no tools" or an auth error — re-authenticate, don't guess positions.
- The MCP's `average_price` is the **actual fill**; feed it to the validator as `--entry` so R/P&L are real. Keep the artifact's planned `entry` separate (it's the trigger you designed, not necessarily where you got filled).

## What this is not

Not an auto-trader and not advice. It surfaces a disciplined verdict per position; the human places the order. A verdict is only as good as the rationale it checks — garbage thesis in, garbage exit out. Keep `thesis_invalidation` conditions concrete and testable when the trade is created.
