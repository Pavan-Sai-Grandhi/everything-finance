---
name: strategy-manager
description: Own the full lifecycle of rule-based trading strategies for Indian markets — (1) GENERATE a complete strategy from a reference article you supply, (2) VALIDATE it by backtest and mark it active when it passes, (3) PICK the active strategy that fits the current market regime, and (4) OPTIMIZE or retire strategies from live trade outcomes fed back by trade-tracker. Use whenever the user asks to design/build a strategy, validate or backtest one, "what strategy should I run now / in this market", review or tune a strategy's live performance, or activate/deactivate a strategy.
argument-hint: "[generate <article URL/file> | validate <name> | pick | optimize <name|all> | <name to inspect>]"
allowed-tools: WebFetch, Read, Write, Bash, Skill, mcp__Claude_in_Chrome__*, mcp__playwright__*
---

# Strategy Manager — generate → validate → pick → optimize

This skill owns a strategy's whole life. A strategy lives as a spec at `artifacts/strategies/<name>.yml` (schema: `assets/strategy-spec.example.yml`) and moves through a lifecycle:

```
 mode: generate            mode: validate              mode: optimize
 (from article)            (backtest passes)           (live edge decays)
   ┌────────┐  draft   ┌────────┐  active   ┌───────────────┐  inactive
   │ DRAFT  ├─────────▶│ ACTIVE │◀─────────▶│ OPTIMIZE/RETIRE│
   └────────┘          └───┬────┘           └───────────────┘
                           │ mode: pick (runtime regime-fit) → hand to swing-trading
```

`status` is the lifecycle state (`draft | active | inactive`); **regime-fit is NOT a status** — it's decided fresh each time in `pick` mode against the live tape. Read `references/reference.md` first for the system framework, the activation thresholds, the selection logic, and the optimization rules this skill enforces.

**Sources for this skill only:** the **reference article(s) the user provides** (URL via WebFetch/curl, or a local file via Read — the strategy source, REQUIRED for `generate`), yfinance via the bundled scripts (`regime.py`, `select_strategy.py`, `aggregate_performance.py`), TradingView via computer-use (mandatory visual study in `generate`), `Skill` calls to `backtest` (validation) and `sector-pulse` (leadership), and the trade-idea artifacts under `artifacts/trades/` (closed-trade outcomes for `optimize`).

## Route to a mode

- A reference article / "design a strategy from this" → **GENERATE**.
- "backtest / validate <name>", or right after generate → **VALIDATE**.
- "what should I trade now", "pick a strategy", "which strategy fits this market" → **PICK**.
- "review / tune / optimize <name>", "is <name> still working", "should I retire <name>" → **OPTIMIZE**.
- A bare strategy name with no verb → inspect it (print status, expectancy, live_performance, regime-fit now) and offer the relevant next mode.

---

## Mode 1 — GENERATE (from a reference article)

This skill ships **no strategies of its own** — the trade logic always comes from the article. It supplies the *system framework* (completeness, expectancy, %-risk sizing, regime gate).

1. **Ingest the reference(s) — REQUIRED.** URL → `WebFetch`/curl; local file → `Read`. If the user gives none, **stop and ask** for a URL/file/pasted rules. Extract — and quote the source for — the strategy's universe, entry, exit, ranking/rebalance, indicators, and the regime it claims (reference.md extraction table). Never invent trade logic.
2. **Read the regime as context.** `python3 <skill-dir>/scripts/regime.py --out artifacts/YYYY-MM-DD/regime.json` (Nifty trend, India VIX, breadth, risk posture). Layer macro if the user wants it; call `sector-pulse` for leadership. This informs `regime_required`, not the entry trigger.
3. **Complete the system.** Fill every component the article omits from the framework — sizing (default 1% risk), risk caps (heat 6%), and `regime_required` from the article's claimed conditions (minimum structural gate if it's silent). A spec missing universe/entry/exit/sizing/risk/regime is incomplete; don't emit it.
4. **TradingView visual study — REQUIRED.** Confirm the article's rules on 2–3 representative symbols via the connected browser (Claude in Chrome / Cowork computer-use / Playwright real Chrome), apply the article's indicators on its timeframe, screenshot into `artifacts/YYYY-MM-DD/tv/`. If no browser is connected, **stop and ask the user to connect one**; leave `indicator_study` `PENDING`. Never fabricate screenshots or enter the user's TradingView credentials.
5. **Emit the spec as `status: draft`.** Fill `assets/strategy-spec.example.yml` → `artifacts/strategies/<name>.yml` with `source_references` populated, `lifecycle.generated_at` set, `expectancy_assumptions`/`live_performance` null. Write the rationale doc → `artifacts/YYYY-MM-DD/strategy-<name>.md` citing the article for each trade rule and the framework for the risk layer. **A draft is not tradeable** — immediately offer VALIDATE.

## Mode 2 — VALIDATE (backtest → active)

Turn a draft into an active strategy *only if it earns it*.

1. Run the backtest engine via `Skill` → `backtest` against the spec (`strategy:<name>`): it reads `entry`/`exit`/`sizing`, tests the mechanical rules on historical NSE data, and writes results into the spec's `expectancy_assumptions` (`win_rate`, `expectancy_R`, `profit_factor`, `n_trades`, `validated_by`).
2. **Apply the activation gate (reference.md):** mark `status: active` **only if** `expectancy_R > 0.2` over **≥ ~30 trades**. Otherwise it stays `draft` (0–0.2R = fragile/no edge) or you mark it `inactive` (< 0R = no edge) — say which and why. On activation set `lifecycle.validated_at` and `activated_at`.
3. If the visual study never ran (`indicator_study` PENDING) it cannot go active — finish the TradingView step first.
4. Report the verdict honestly with the backtest's own caveats (in-sample, survivorship, regime concentration). A passed backtest is a hypothesis that survived history, not a guaranteed edge.

## Mode 3 — PICK (select the active strategy that fits now)

Answer "what should I trade in this market" from the **validated library**, not from a fresh opinion.

1. Refresh the regime: `python3 <skill-dir>/scripts/regime.py --out artifacts/YYYY-MM-DD/regime.json`.
2. Select: `python3 <skill-dir>/scripts/select_strategy.py --strategies artifacts/strategies --regime artifacts/YYYY-MM-DD/regime.json --out artifacts/YYYY-MM-DD/selection.json`. It keeps only `status: active` specs, tests each `regime_required` against the live regime, and ranks the fitting ones by edge (live expectancy if available, else backtest).
3. Present the **selected** strategy (and the ranked runners-up), plus the ones rejected for regime-fit and why. If **none fit** (exit 11) say so plainly — the disciplined move is to stand aside, not to force a misfit strategy; suggest GENERATE/OPTIMIZE if the library is thin. If there are **no active specs** (exit 12), there's nothing validated to run — point to GENERATE→VALIDATE.
4. Hand off: tell the user to run `/swing-trading strategy:<selected>` to screen live candidates against it.

## Mode 4 — OPTIMIZE (learn from live trades; retire what's broken)

Close the loop with reality. `trade-tracker` writes a `result` block (realized R, exit reason) into each trade-idea artifact when it closes; those are the input.

1. Aggregate: `python3 <skill-dir>/scripts/aggregate_performance.py --trades artifacts/trades --strategies artifacts/strategies [--strategy <name>] --out artifacts/YYYY-MM-DD/performance.json`. It groups closed trades by their `strategy` link and computes realized win rate, expectancy_R, profit factor, and an exit-reason breakdown, then recommends **KEEP / OPTIMIZE / DEACTIVATE** (rules in reference.md: needs ≥ 10 closed trades to act; negative live expectancy → deactivate; positive but decaying well below backtest → optimize).
2. Write the realized numbers into the spec's `live_performance` (re-run with `--update-spec` to do it, or write them yourself), with a `drift_note` comparing live vs backtest.
3. Act on the recommendation:
   - **DEACTIVATE** → set `status: inactive`, `lifecycle.deactivated_at`/`deactivated_reason` (the script does this with `--update-spec`). The strategy stops being selectable. Tell the user the edge is gone and why.
   - **OPTIMIZE** → propose a concrete rule change driven by the diagnostic (e.g. TIME exits dominate the losers → tighten `time_stop_sessions`; stops too tight → widen to structure). **Bump `version`, append an `optimization_log` entry, then re-run VALIDATE** — an optimized strategy must re-pass the backtest gate before it's active again. Never tune parameters and call it active without re-validation (that's in-sample curve-fitting).
   - **KEEP** → record the live numbers, no change.

## How other skills consume this
`swing-trading` runs only an **active, regime-fitting** spec (use PICK to choose it); `backtest` is the validation engine this skill drives; `deep-analysis` checks a ticker against an active strategy's regime/archetype; `trade-tracker` reads a trade's linked strategy `regime_required` for its regime-exit check and feeds closed trades back here for OPTIMIZE.

End every mode with the standard risk note. A strategy is a hypothesis at generate, a survivor at validate, a fit at pick, and a living thing at optimize — never a guaranteed edge.
