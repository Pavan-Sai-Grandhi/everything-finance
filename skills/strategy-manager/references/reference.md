# Trading-system design framework

This file is the **system framework only** — the discipline that turns *any* strategy idea into a complete, risk-bounded, testable spec. It deliberately ships **no strategies, archetypes, or canned rule sets**: the trade logic always comes from the **reference article(s) the user supplies**, never from here. The framework is grounded in Zerodha Varsity's *Trading Systems* module teaching on system design and expectancy (https://zerodha.com/varsity/module/trading-systems/) — the *system*, not its example strategies.

## Reading a strategy out of a reference article

When the user hands you an article/blog/PDF/screenshot, extract — and **quote the source for** — these elements. Whatever the article doesn't state is a gap you complete from the framework below (never by inventing trade logic):

| Element | What to pull from the article | If the article is silent |
|---|---|---|
| **Universe** | What it trades (an index, a liquidity/fundamental filter, a watchlist) | Ask the user, or default to a broad liquid set (e.g. nifty500) and say so |
| **Entry trigger** | The exact, testable condition (price/level event + indicator/volume confirm) | Cannot be inferred — ask; a system with no defined entry is not a system |
| **Exit** | Stop rule **and** target rule; trailing/rebalance if stated | Add a framework stop (structure-based) + min-RRR target + time stop; flag as added |
| **Ranking/rebalance** | For basket systems: the ranking metric, hold count, weighting, cadence | null for single-name setups |
| **Indicators / timeframe** | Exactly the indicators and timeframe the article names (for the TradingView study) | Use what the entry/exit imply; state the assumption |
| **Regime it claims** | The market conditions it says it works in ("trending up", "range-bound", …) | Apply the minimum structural gate and say you did |

Quote-trace every **trade rule** back to the source. The framework only ever supplies the **risk layer** (sizing, caps, regime gate) — keep that boundary explicit in the rationale.

## Components of a complete rule-based system (non-negotiable)

A system the generator emits MUST specify every one of these — a spec missing any is incomplete and must not be handed to the user:
1. **Universe** — what's tradable (e.g., Nifty 500, with optional fundamental/liquidity gate).
2. **Entry trigger** — an exact, testable condition (not "looks good"): a price/level event + indicator/volume confirmation.
3. **Exit** — both a **stoploss** (where the thesis is wrong) and a **target** (where you book), plus a **time stop** for swing/positional systems.
4. **Position sizing** — how much to buy, derived from risk, not conviction.
5. **Risk caps** — per-trade risk, max open risk (portfolio heat), concentration limits, rebalance cadence.
6. **Regime condition** — when the system is allowed to be active (the layer most retail write-ups omit — supply it even when the article doesn't).

Core discipline: a system is a *fixed, written rule set* executed without improvisation. Discretion is the enemy of expectancy — the rules carry the edge across many trades; any single trade can fail. The generator's job is to make the article's idea this explicit and this bounded.

## Expectancy — the number that decides if a system is worth trading

```
Expectancy (in R) = (Win% × Avg Win in R) − (Loss% × Avg Loss in R)
```
where 1R = the initial risk (entry − stop). Expectancy > 0 is the minimum bar; > 0.2R with a real sample (≥ ~30 trades) is a tradeable edge. A 35% win rate with 2.5R winners beats a 65% win rate with 0.5R winners — **win rate alone is marketing**; expectancy and reward:risk together decide. The generator leaves `expectancy_assumptions` null until `/backtest` fills them — an article's claimed numbers are not your results, and an unvalidated system is a hypothesis.

## Position sizing — fixed fractional / percent-risk

Risk a fixed fraction of capital per trade (default 1%):
```
qty = (capital × risk_per_trade_pct/100) / (entry − stop)
```
Conviction does not change size — only the stop distance does. **Portfolio heat** = sum of open per-trade risk; cap it (default 6%) so a cluster of correlated stops can't blow a hole in the book. For basket/ranked systems, equal-weighting is a sane default unless the article specifies otherwise.

## Regime gate — the framework's risk overlay (not the strategy)

The regime read decides *whether* and *how big* a strategy runs today; it never changes *what* it trades. Set the spec's `regime_required` from **the conditions the article claims**. Crucially, regime-fit is checked at **selection time** (`pick` mode), not baked into `status`: an `active` strategy stays active across regimes and is simply *not selected* while the tape doesn't fit it (a trend-following method on a downtrending tape, a calm-VIX mean-reversion method when VIX spikes). This keeps the lifecycle status (did it earn its edge?) separate from the runtime question (does the tape suit it right now?).

Indian-context macro overlay (sets risk-on/off, never the trigger):
- **Repo rate direction** (RBI): cutting = tailwind for rate-sensitives (financials, autos, realty); hiking = headwind, favor defensives.
- **CPI/inflation**: cooling supports rate cuts; hot inflation pressures multiples.
- **USD-INR**: weak rupee helps exporters (IT, pharma), hurts importers/oil.
- **FII/DII flows**: sustained FII selling caps upside even on good micro; DII support cushions.
- **India VIX**: < ~13 complacent, 13–20 normal, > 20 fear — size down as VIX rises.

Source macro from the daily-brief/sector references when the user wants the overlay; otherwise the script's trend+VIX read is the minimum regime gate.

## Strategy lifecycle (strategy-manager owns this)

A spec moves through three states. `status` is the lifecycle; regime-fit is decided separately at selection.

| status | meaning | set by | tradeable? |
|---|---|---|---|
| **draft** | generated from an article; backtest not yet passed (or visual study pending) | `generate` | No |
| **active** | backtest passed the activation gate; eligible to be selected when the tape fits | `validate` (or re-`validate` after optimize) | Only via `pick` when regime fits |
| **inactive** | retired — failed backtest, deactivated by live performance, or manual | `validate` (fail) / `optimize` (deactivate) | No |

### Activation gate (validate)
Promote `draft → active` **only if** the backtest gives `expectancy_R > 0.2` over **≥ ~30 trades** with the visual study done. Mapping (same as the backtest skill): `< 0R` = no edge → `inactive`; `0–0.2R` = fragile → stays `draft`; `> 0.2R, ≥30 trades` = edge → `active`; `< 30 trades` = inconclusive → stays `draft` regardless of the number. Record `expectancy_assumptions` + `lifecycle.validated_at`/`activated_at`. Win rate alone never activates anything — expectancy and sample size decide.

### Selection (pick)
Among `status: active` specs, keep those whose `regime_required` the live `regime.json` satisfies (trend match, Nifty vs 200-EMA, VIX ≤ cap, breadth ≥ floor — `select_strategy.py`), then rank by edge: **live `expectancy_R` if the strategy has closed trades, else backtest `expectancy_R`**, tie-broken by profit factor. The best fit is the recommendation. Zero fits → stand aside (don't force a misfit). Zero active specs → nothing validated to run.

### Optimization & retirement (optimize)
Live trades from `trade-tracker` (closed trade-idea artifacts carrying a `result.realized_R` + `strategy` link) are the truth that backtests only approximate. `aggregate_performance.py` groups them per strategy and recommends:
- **Need ≥ 10 closed trades to act** — below that, never change a strategy on live data (noise).
- **DEACTIVATE** when realized `expectancy_R < 0` over the sample — the edge is gone; set `status: inactive` with a reason. A negative live expectancy is not "bad luck" past 10+ trades; it's a dead strategy.
- **OPTIMIZE** when realized expectancy is positive but well below backtest (`< max(0.1R, 0.5 × backtest)`) — the edge is decaying. Use the **exit-reason breakdown** as the diagnostic (TIME exits dominating the losers → time stop too long / target too far; STOP exits clustering → stop too tight or entry too early), propose **one** concrete rule change, bump `version`, append an `optimization_log` entry, and **re-run validate** — an optimized strategy must re-pass the activation gate before it trades again. Tuning to live results without re-validation is curve-fitting.
- **KEEP** when live expectancy holds up — just record `live_performance`.

## What a managed strategy is NOT

Not a proven edge and not advice. The article's backtest is theirs (their data, possibly curve-fit); your own backtest is in-sample history; live performance is the only real verdict, and it decays. The lifecycle exists so a strategy is never trusted beyond what it has earned: a hypothesis at generate, a survivor at validate, a fit at pick, and — only after enough real trades — a kept or retired thing at optimize. Position-sizing discipline, not prediction, is what keeps the account alive.
