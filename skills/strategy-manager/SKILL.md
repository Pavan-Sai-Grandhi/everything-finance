---
name: strategy-manager
description: Own the full lifecycle of rule-based trading strategies for Indian markets — (1) GENERATE a complete strategy from a reference article you supply, (2) VALIDATE it by backtest and mark it active when it passes, (3) PICK the active strategy that fits the current market regime, and (4) OPTIMIZE or retire strategies from live trade outcomes fed back by trade-tracker. Use whenever the user asks to design/build a strategy, validate or backtest one, "what strategy should I run now / in this market", review or tune a strategy's live performance, or activate/deactivate a strategy.
argument-hint: "[generate <article URL/file> | validate <name> | pick | optimize <name|all> | <name to inspect>]"
allowed-tools: WebFetch, Read, Write, Bash, Skill, mcp__Claude_in_Chrome__*, mcp__playwright__*
---

# Strategy Manager — generate → validate → pick → optimize

This skill owns a strategy's whole life. A strategy lives as a spec at `artifacts/state/strategies/<name>.yml` (schema: `assets/strategy-spec.example.yml`) and moves through a lifecycle:

```
 mode: generate            mode: validate              mode: optimize
 (from article)            (backtest passes)           (live edge decays)
   ┌────────┐  draft   ┌────────┐  active   ┌───────────────┐  inactive
   │ DRAFT  ├─────────▶│ ACTIVE │◀─────────▶│ OPTIMIZE/RETIRE│
   └────────┘          └───┬────┘           └───────────────┘
                           │ mode: pick (runtime regime-fit) → hand to find-trade
```

`status` is the lifecycle state (`draft | active | inactive`); **regime-fit is NOT a status** — it's decided fresh each time in `pick` mode against the live tape. Read `references/reference.md` first for the system framework, the activation thresholds, the selection logic, and the optimization rules this skill enforces.

**Sources for this skill only:** the **reference article(s) the user provides** (URL via WebFetch/curl, or a local file via Read — the strategy source, REQUIRED for `generate`), yfinance via the bundled scripts (`regime.py`, `select_strategy.py`, `aggregate_performance.py`), TradingView via computer-use (mandatory visual study in `generate`), `Skill` calls to `backtest` (validation) and `sector-analysis` (leadership), and the trade-idea artifacts under `artifacts/state/trades/` (closed-trade outcomes for `optimize`).

## Route to a mode

- A reference article / "design a strategy from this" → **GENERATE**.
- "backtest / validate <name>", or right after generate → **VALIDATE**.
- "what should I trade now", "pick a strategy", "which strategy fits this market" → **PICK**.
- "review / tune / optimize <name>", "is <name> still working", "should I retire <name>" → **OPTIMIZE**.
- A bare strategy name with no verb → inspect it (print status, expectancy, live_performance, regime-fit now) and offer the relevant next mode.

---

## Mode 1 — GENERATE (from a reference article)

This skill invents **no trade logic of its own** — it always comes from the article. It supplies the *system framework* (completeness, expectancy, %-risk sizing, regime gate). A **seed library of pre-generated drafts** (common swing methods distilled from a reference article) lives in `assets/seed-strategies/` — these are starting points the user copies into `artifacts/state/strategies/` and must still VALIDATE; they are `status: draft`, never a shortcut around the backtest gate.

1. **Ingest the reference(s) — REQUIRED.** URL → `WebFetch`/curl; local file → `Read`. If the user gives none, **stop and ask** for a URL/file/pasted rules. Extract — and quote the source for — the strategy's universe, entry, exit, ranking/rebalance, indicators, and the regime it claims (reference.md extraction table). Never invent trade logic.
2. **Read the regime as context.** `python3 <skill-dir>/scripts/regime.py --out artifacts/regime/YYYY-MM-DD.json` (Nifty trend, India VIX, breadth, risk posture). Layer macro if the user wants it; call `sector-analysis` for leadership. This informs `regime_required`, not the entry trigger.
3. **Complete the system.** Fill every component the article omits from the framework — sizing (default 1% risk), risk caps (heat 6%), `regime_required` from the article's claimed conditions (minimum structural gate if it's silent), and the **`screening` block** (how find-trade cuts the universe): the `fundamental` cut (provider `screener.in` + a query) and the `technical` cut (provider `tradingview` with server-side filter rows, or `compute` with local `lib/ta.py` predicates when TradingView can't express the filter — e.g. NR-bars, fib zones). A spec missing universe/screening/entry/exit/sizing/risk/regime is incomplete; don't emit it.
   - **Map the article's exit to the engine's exit vocabulary — don't approximate it.** The engine expresses more than a fixed target, so encode the source's *actual* exit: a **trailing stop** → `trail_atr: <mult>` with `target: trailing` (a long `time_stop` is not a substitute — it caps winners and the optimizer misreads it); a **moving-average / indicator exit** (a "close back above the 5-SMA" mean-reversion exit, a "close below the 20-EMA" trend break) → `exit_signal: "<expr>"` in `entry.signal`'s grammar. Reserve `measured_move`/`min_rrr` targets for setups whose source names a fixed objective. If the source's exit genuinely can't be expressed, say so in the rationale — but reach for `trail_atr`/`exit_signal` first.
4. **TradingView visual study — REQUIRED.** Confirm the article's rules on 2–3 representative symbols on real TradingView charts, screenshot into `artifacts/strategy-manager/YYYY-MM-DD/tv/`. Never fabricate screenshots.
   - **Use the bundled authenticated path: `scripts/tv_study.cjs`.** It logs into TradingView with the **same cookies find-trade uses** (`TRADINGVIEW_SESSIONID` / `TRADINGVIEW_SESSIONID_SIGN` from `~/.claude/.env`) so the chart loads already-signed-in — no "Join for free" wall blocking indicator add, no per-session login. The script reads the cookies straight from the sourced env; **the values never pass through a tool call** (CLAUDE.md: never echo secrets). Run:
     ```bash
     set -a; source ~/.claude/.env; set +a
     node <skill-dir>/scripts/tv_study.cjs --check                      # verify the session is live
     node <skill-dir>/scripts/tv_study.cjs --symbol NTPC --date 2023-06-30 --out artifacts/strategy-manager/YYYY-MM-DD/tv
     ```
   - **Apply EMA20/EMA50/SMA200 once to your TradingView *default layout* and save it** — a logged-in chart loads that layout, so every study inherits the MAs without automating the indicator dialog per run (which is brittle). Pick representative *winning* setups from the backtest trade log (TARGET/trailing exits) so the study confirms the rule on real signals, not arbitrary dates.
   - **If `--check` reports `logged_in:false`** the cookies are stale — ask the user to recopy `sessionid`/`sessionid_sign` from a browser they're logged into (DevTools → Application → Cookies → tradingview.com). Leave `indicator_study` `PENDING` until the study is done; never fabricate it.
5. **Emit the spec as `status: draft`.** Fill `assets/strategy-spec.example.yml` → `artifacts/state/strategies/<name>.yml` with `source_references` populated, `lifecycle.generated_at` set, `expectancy_assumptions`/`live_performance` null. Write the rationale doc → `artifacts/strategy-manager/YYYY-MM-DD/<name>.md` citing the article for each trade rule and the framework for the risk layer. **A draft is not tradeable** — immediately offer VALIDATE.
   - **Quote every free-text value, then round-trip the file before trusting it.** Any string that can contain a `:`, `#`, parentheses, or a path — `validated_by`, `target`, `deactivated_reason`, `optimization_log` notes — must be double-quoted, or a `key: value` fragment inside it reads as a nested map and the spec silently becomes unloadable (backtest/find-trade then crash on it). After writing, verify it parses: `python3 -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" artifacts/state/strategies/<name>.yml`.

## Mode 2 — VALIDATE (backtest → active)

Turn a draft into an active strategy *only if it earns it*.

1. Run the backtest engine via `Skill` → `backtest` against the spec (`strategy:<name>`): it reads `entry`/`exit`/`sizing`, tests the mechanical rules on historical NSE data, and writes results into the spec's `expectancy_assumptions` (`win_rate`, `expectancy_R`, `profit_factor`, `n_trades`, `validated_by`).
2. **Apply the activation gate (reference.md):** mark `status: active` **only if** `expectancy_R > 0.2` over **≥ ~30 trades**. Otherwise it stays `draft` (0–0.2R = fragile/no edge) or you mark it `inactive` (< 0R = no edge) — say which and why. On activation set `lifecycle.validated_at` and `activated_at`.
3. If the visual study never ran (`indicator_study` PENDING) it cannot go active — finish the TradingView step first.
4. Report the verdict honestly with the backtest's own caveats (in-sample, survivorship, regime concentration). A passed backtest is a hypothesis that survived history, not a guaranteed edge.

## Mode 3 — PICK (select the active strategy that fits now)

Answer "what should I trade in this market" from the **validated library**, not from a fresh opinion.

1. Refresh the regime: `python3 <skill-dir>/scripts/regime.py --out artifacts/regime/YYYY-MM-DD.json`.
2. Select: `python3 <skill-dir>/scripts/select_strategy.py --regime artifacts/regime/YYYY-MM-DD.json --out artifacts/strategy-manager/YYYY-MM-DD/selection.json` (`--strategies` defaults to `artifacts/state/strategies`). It keeps only `status: active` specs, tests each `regime_required` against the live regime, and ranks the fitting ones by edge (live expectancy if available, else backtest).
3. Present the **selected** strategy (and the ranked runners-up), plus the ones rejected for regime-fit and why. If **none fit** (exit 11) say so plainly — the disciplined move is to stand aside, not to force a misfit strategy; suggest GENERATE/OPTIMIZE if the library is thin. If there are **no active specs** (exit 12), there's nothing validated to run — point to GENERATE→VALIDATE.
4. Hand off: tell the user to run `/find-trade strategy:<selected>` to screen live candidates against it (or just `/find-trade`, which calls this pick itself when no strategy is named).

## Mode 4 — OPTIMIZE (learn from live trades; retire what's broken)

Close the loop with reality. `trade-tracker` writes a `result` block (realized R, exit reason) into each trade-idea artifact when it closes; those are the input.

1. Aggregate: `python3 <skill-dir>/scripts/aggregate_performance.py [--strategy <name>] --out artifacts/strategy-manager/YYYY-MM-DD/performance.json` (`--trades`/`--strategies` default to `artifacts/state/trades` and `artifacts/state/strategies`). It groups closed trades by their `strategy` link and computes realized win rate, expectancy_R, profit factor, and an exit-reason breakdown, then recommends **KEEP / OPTIMIZE / DEACTIVATE** (rules in reference.md: needs ≥ 10 closed trades to act; negative live expectancy → deactivate; positive but decaying well below backtest → optimize).
2. Write the realized numbers into the spec's `live_performance` (re-run with `--update-spec` to do it, or write them yourself), with a `drift_note` comparing live vs backtest.
3. Act on the recommendation:
   - **DEACTIVATE** → set `status: inactive`, `lifecycle.deactivated_at`/`deactivated_reason` (the script does this with `--update-spec`). The strategy stops being selectable. Tell the user the edge is gone and why.
   - **OPTIMIZE** → propose a concrete rule change driven by the diagnostic (e.g. TIME exits dominate the losers → tighten `time_stop_sessions`; stops too tight → widen to structure). **Bump `version`, append an `optimization_log` entry, then re-run VALIDATE** — an optimized strategy must re-pass the backtest gate before it's active again. Never tune parameters and call it active without re-validation (that's in-sample curve-fitting).
   - **KEEP** → record the live numbers, no change.

## Alerts this skill raises (via `lib/alerts.py`)

When a spec goes stale — the live regime has drifted away from an active strategy's `regime_required`, or OPTIMIZE flags decaying live expectancy — raise a **`revalidate_due`** alert (`subject: {type: strategy, id: <name>}`, `created_by: strategy-manager`, `severity: watch`, `action.text` = why it's stale, `action.suggest: "/strategy-manager validate <name>"` or `optimize <name>`, `trigger: {check: strategy-manager}`, `dedup_key: revalidate-<name>`). `daily-brief` lists it among due actions until a re-validation clears it.

## How other skills consume this
`find-trade` runs only an **active, regime-fitting** spec — and when the user names none, it calls this skill's PICK mode to choose one (it has no default of its own); it reads the spec's `screening`/`entry`/`exit`/`sizing`. `backtest` is the validation engine this skill drives; `deep-analysis` checks a ticker against an active strategy's regime/archetype; `trade-tracker` reads a trade's linked strategy `regime_required` for its regime-exit check and feeds closed trades back here for OPTIMIZE.

End every mode with the standard risk note. A strategy is a hypothesis at generate, a survivor at validate, a fit at pick, and a living thing at optimize — never a guaranteed edge.
