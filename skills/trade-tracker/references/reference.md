# Trade-tracking & early-exit framework

The discipline behind `trade-tracker`: a position is only worth holding while the **reason you entered it** still holds. This file defines what "still holds" means and how the exit decision is made.

## The one rule

> Exit when the thesis is invalidated — not when you're bored, scared, or hopeful.

Every trade entered through this plugin carries a written rationale (the trade-idea artifact): an entry, a stop, a target, a time horizon, and the **specific conditions that would prove it wrong** (`thesis_invalidation`). Tracking is just re-checking those conditions on live data and acting when one fires. No artifact = no discipline; capture the rationale before tracking (SKILL §2).

## The exit decision (priority order)

`check_trade` evaluates these top-down; the first hit is the verdict:

1. **EXIT_STOP** — price breached the stoploss. Non-negotiable; the stop is where the thesis was defined to be wrong. (Uses each unadjusted session's low for longs / high for shorts on every session after the recorded fill date, so a recovered breach still counts and is dated. On the fill day, or with an unknown fill date, it checks close and labels the intrabar gap.)
2. **EXIT_THESIS** — a machine-checkable invalidation fired (e.g. *daily close below 50-EMA*, *break of pivot 3,250*). The setup that justified the entry is gone even if the hard stop hasn't printed — exit into strength rather than waiting for the stop.
3. **EXIT_TARGET** — price reached the target. Recommend booking or trailing per the plan; the position remains open until matched broker executions confirm its full exit.
4. **EXIT_TIME** — held ≥ `time_stop_sessions` with neither stop nor target hit. Dead money has an opportunity cost; a swing trade that hasn't worked in its window is telling you something.
5. **HOLD** — no evaluated mechanical condition fired. Resolve `manual_review` and data gaps before calling the rationale intact.

Two layers the tool defers to the skill (qualitative judgement):
- **`manual_review`** — invalidations the parser can't evaluate (earnings miss, pledge change, downgrade). Check them against news/filings and treat a confirmed one as EXIT_THESIS.
- **Regime change** — for strategy-linked trades, if the live regime no longer satisfies the strategy's `regime_required`, the edge is gone → recommend exit even on a mechanical HOLD.

## Reading the numbers

- The checker's `as_of` is the decision bar date. `metrics.price` is the decision close; personal `mark_price` may value the position but never triggers a stop, target or thesis decision.
- **Unrealized R** = (current − entry) / (entry − stop) for longs (flipped for shorts). R, not rupees, is the unit of discipline: +2R means the trade has paid back twice its risk. Manage on R, size on R.
- **Remaining RRR to target** = (target − price) / (price − stop). As price climbs toward target this collapses; when the remaining reward no longer justifies the open risk, trimming or tightening the stop is rational even pre-target.
- **Portfolio view**: sum the open risk (heat). The single-trade verdict is local; if total heat is high, prefer the flagged exits and resist adding.

## Broker & IndMoney data notes

- **Live state comes through `finance/compute/holdings.py`** (precedence IndMoney → broker): it normalizes whichever source is connected to one canonical position shape (symbol or name/qty/avg/ltp/pnl/value; IndMoney supplies no XIRR and no cost for linked-broker stocks). IndMoney is read-only net worth across assets; the broker MCPs are the equity fallback. State (what you hold, at what live price) and **fills** (your exact entry) are different questions — see the next bullets.
- **Fills are broker-only.** IndMoney has no order/trade history and its avg-cost must never be fed to `check_trade` as `entry`. The real fill comes from the broker's order history (or a `fill_avg` already recorded on the artifact). IndMoney-only with no recorded fill → report live health but make R-multiple/time-stop a Data gap.
- Both hosted broker MCPs are **read-only** — holdings, positions, orders, quotes; they cannot place or modify orders.
- **Holdings** = settled/delivery (CNC) stock; **Positions** = intraday + F&O (MIS/NRML). A swing trade usually shows in holdings (T+1 onward) or as an overnight position. Match on trading symbol; reconcile qty against the artifact's planned qty and note partial fills.
- Auth is per-session (Kite) or daily (Upstox); a stale session looks like "no tools" or an auth error — re-authenticate, don't guess positions.
- `average_price` from matched **broker order/trade history** is an actual execution average; a holdings average cost is not an execution record. Use only the matched execution average; feed it to `check_trade` as `entry` so R/P&L are real. Keep the artifact's planned `entry` separate (it's the trigger you designed, not necessarily where you got filled).

## Execution and learning

A recommendation is not a fill. Missing holdings or agreement to exit cannot close an artifact.
Reconcile broker executions against the full original quantity; partial exits remain open.
The `result` contract in `finance/contracts.md` requires actual exit prices, quantities, charges
and broker trade IDs. Missing inputs remain gaps. The optimizer verifies this evidence and
recomputes net R; it excludes legacy or inconsistent outcomes and requires review before
changing a strategy with an incomplete sample. Preserve the original plan stop and entry
quantity as the risk denominator. Trading-session time stops count observed sessions after
entry; their alerts request revalidation rather than guessing a calendar due date.

## What this is not

Not an auto-trader and not advice. It surfaces a disciplined verdict per position; the human places the order. A verdict is only as good as the rationale it checks — garbage thesis in, garbage exit out. Keep `thesis_invalidation` conditions concrete and testable when the trade is created.
