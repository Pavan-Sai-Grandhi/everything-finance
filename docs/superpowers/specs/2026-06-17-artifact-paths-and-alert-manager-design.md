# Artifact-path sanitization + alert manager — design

**Date:** 2026-06-17
**Status:** approved (brainstorming) — ready for implementation plan
**Scope:** `everything-finance` plugin. Two coupled sub-projects, phased: (1) a sanitized
artifact-path layout with a single path resolver, (2) an alert system that turns
`daily-brief` into the daily consumer of an alert inbox the other skills feed.

---

## Problem

Two structural problems in how the plugin writes and reuses artifacts:

1. **One flat namespace for three lifecycles.** Everything roots at `./artifacts/` (cwd) and
   that single directory mixes dated historical output (`YYYY-MM-DD/<thing>.md`), durable
   cross-run state (`strategies/`, `trades/`), and disposable scratch (`.cache/`, `.staging/`,
   hook logs) as flat siblings. Naming inside the date buckets drifted: the ticker is
   sometimes a prefix (`<TICKER>-filings.md`, `<TICKER>-deep-analysis.md`), sometimes a suffix
   (`dcf-<SYM>.md`, `management-<SYM>.md`); no skill namespace; companion dirs sit
   inconsistently. gitignore/cleanup/backup cannot reason about the three lifecycles separately.

2. **No memory across runs, no inbox.** A second run of a stock-centric skill cannot easily find
   its own prior run, so analyses never build on each other. And no skill leaves a durable,
   machine-readable "watch this / do this" item — `daily-brief` recomputes filings + news +
   position health live every morning with no notion of pending actions raised elsewhere.

## Decisions (from brainstorming)

- **Root stays cwd-rooted** `./artifacts/` (no fixed home). Sanitization is purely the internal
  structure. An optional env override is supported but defaults to cwd.
- **Layout is entity-first for entity-centric skills, skill-first for date/singleton skills.**
  Stocks and funds are entities.
- **Prior runs are reused** via a delta-aware lookup; default behavior is "delta + context".
- **Existing artifacts get a one-time migration script** (dry-run default).
- **Alert manager = `lib/alerts.py` (contract + cheap evaluation) + a thin `alert-manager` skill.**
- **`daily-brief` surfaces + recommends**: it fires cheap machine-checkable alerts inline and
  prints the exact command for alerts that need a skill run — it never auto-runs skills.
- **`daily-brief` gains a market-analysis (market-level news) section.**
- **Opportunities come from the vetted alert inbox AND may include live news flags**, clearly
  labeled vetted vs unvetted, capped to avoid noise.
- **Watchlist auto-adds vetted opportunities; pruning is recommended, never automatic.**

---

## Phase 1 — Path layout

### The tree

cwd-rooted `./artifacts/`, three lifecycle tiers:

```
artifacts/
  # --- dated historical output ---------------------------------------------
  stocks/<TICKER>/<date>/          # entity-first: one stock's whole run-day together
      deep-analysis.md
      deep-analysis/agents/*.md     # work papers
      dcf.md  dcf.json  dcf-inputs.yml
      management.md
      filings.md
  funds/<SCHEME>/<date>/            # funds are entities too
      mf-research.md  mf-research.json
  daily-brief/<date>.md            # date/singleton skills: skill-first
  sector-analysis/<date>.html      # + sector-analysis/<date>/<sector>.md work papers
  portfolio-review/<date>.md
  find-trade/<date>.html           # + find-trade/<date>.json
  trade-tracker/<date>.md          # + trade-tracker/<date>/validate-<SYM>.json
  regime/<date>.json
  backtest/<spec>/<date>.md        # + .csv outputs
  budget/<YYYY-MM>.html
  insurance/<date>.md
  # --- durable, mutable, NOT dated -----------------------------------------
  state/
      strategies/<name>.yml
      trades/<SYM>-<date>.yml
      alerts/<id>.yml
      watchlist.json
  # --- disposable (safe to delete anytime) ---------------------------------
  cache/                           # ohlcv, mf NAV, gate_survivors.json
  tmp/                             # deep-analysis staging, hook logs
```

**One naming convention everywhere:** `<owner-dir>/<key>/<date>.<ext>` where `key` is the
ticker / scheme / spec for entity skills and the date itself for singletons. No ticker
prefix-vs-suffix drift.

`<date>` = `YYYY-MM-DD`, the day the run started (matches today's rule).

`<SCHEME>` for funds is a filesystem-safe slug of the scheme name (lowercase, non-alnum → `-`).
`<TICKER>` is the NSE trading symbol, no `.NS` (matches today's trade-idea rule).

### `lib/paths.py` — the single path resolver (new)

Every skill script imports it instead of hardcoding path strings, so the convention cannot
drift — same philosophy as `lib/ta.py` and `lib/strategy.py` being the one engine each. The
SKILL.md prose references the named helpers rather than literal paths.

API (all return absolute paths, creating parent dirs on write-helpers):

| Function | Returns |
|---|---|
| `root()` | the artifacts root: `EVERYTHING_FINANCE_ARTIFACTS` env if set, else `./artifacts` under cwd |
| `stock_dir(ticker, date)` | `stocks/<TICKER>/<date>/` |
| `fund_dir(scheme, date)` | `funds/<SCHEME>/<date>/` |
| `report_path(skill, date, ext)` | `<skill>/<date>.<ext>` for singleton skills |
| `report_dir(skill, date)` | `<skill>/<date>/` for singleton skills that emit work papers |
| `backtest_dir(spec, date)` | `backtest/<spec>/<date>/` |
| `state_dir(name)` | `state/<name>/` (strategies, trades) |
| `alerts_dir()` | `state/alerts/` |
| `watchlist_path()` | `state/watchlist.json` |
| `cache_dir(name=None)` | `cache/` or `cache/<name>/` |
| `tmp_dir(name=None)` | `tmp/` or `tmp/<name>/` |
| `latest_prior(skill, subject, before=None)` | newest earlier artifact for that skill+subject, or `None` |

`latest_prior` is what powers "refer the earlier run": for a stock skill it lists the
`<date>` dirs under `stocks/<TICKER>/` containing the relevant file and returns the newest
strictly before today (or before `before`).

Import idiom mirrors the existing `sys.path.insert` three-dirs-up pattern documented in
`contracts.md`.

### `lib/migrate_artifacts.py` — one-time migration (new)

Best-effort move of an existing flat `./artifacts/` into the new tree by parsing current
filenames. `--dry-run` (default) prints every planned move and any file it cannot confidently
classify (left in place, reported); `--apply` performs them. Examples:

```
artifacts/2026-05-01/RELIANCE-deep-analysis.md   -> stocks/RELIANCE/2026-05-01/deep-analysis.md
artifacts/2026-05-01/RELIANCE-deep-analysis/      -> stocks/RELIANCE/2026-05-01/deep-analysis/
artifacts/2026-05-01/dcf-RELIANCE.md             -> stocks/RELIANCE/2026-05-01/dcf.md
artifacts/2026-05-01/daily-brief.md              -> daily-brief/2026-05-01.md
artifacts/strategies/*.yml                       -> state/strategies/*.yml
artifacts/trades/*.yml                           -> state/trades/*.yml
artifacts/.cache/*                               -> cache/*
watchlist.json (cwd)                             -> state/watchlist.json
```

Not wired into any hook; the user runs it manually once per workspace.

### Prior-run reuse

`deep-analysis`, `dcf-valuation`, `management-quality`, and `filings-watch` call
`latest_prior(...)` before running. Default behavior **delta + context**:

- The prior report is read in as context so the new run stays consistent.
- `deep-analysis` opens its report with a **"What changed since `<date>`"** block: verdict
  then→now, DCF fair-value shift, whether the thesis is intact, notable new risk. The other
  three add a one-line "prior run: `<path>` (`<date>`)" link plus context; a full delta block
  is `deep-analysis`-only.

**Unifying the stock lifecycle:** when `deep-analysis` computes a DCF and a management grade
internally (its fundamental leg already does), it now also persists them as discrete
`stocks/<TICKER>/<date>/dcf.md` and `management.md` beside the report — so a stock's history is
unified whether an artifact came from a standalone run or from inside the debate, and
`latest_prior("dcf", ticker)` finds both.

---

## Phase 2 — Alert system

### `lib/alerts.py` — the contract + cheap evaluation (new)

Owns the alert schema and lifecycle. One alert = one file `state/alerts/<id>.yml`:

```yaml
id:               # stable slug: <kind>-<subject>-<shorthash>
created_by:        # producing skill
created_at:        # ISO date
updated_at:
subject:
  type: stock|fund|strategy|portfolio   # 'portfolio' == account-wide, no id
  id: RELIANCE                          # ticker / scheme slug / strategy name
kind: price_cross|filing_act_on|time_stop|regime_change|revalidate_due|reanalyze_due|sip_due|opportunity|investigate|custom
trigger:          # exactly one form:
  # cheap — alerts.py evaluates against market data daily-brief already has:
  {metric: close|low|high|day_change_pct|dist_to_sl_pct, op: "<"|">"|"<="|">=", level: 1450}
  # date-based — fires on/after a date:
  {due: 2026-09-15}
  # needs a skill run to resolve — daily-brief surfaces it as a suggested command:
  {check: trade-tracker, args: {symbol: RELIANCE}}
action:           # human-readable recommendation
  text: "thesis recheck due"
  suggest: "/trade-tracker RELIANCE"   # optional command to surface
severity: info|watch|act
status: open|triggered|snoozed|done|expired
snooze_until:     # optional
expires_at:       # optional TTL; swept to status: expired
dedup_key:        # producers set this so re-runs update rather than duplicate
log:              # [{date, note}]
```

Functions:

| Function | Behavior |
|---|---|
| `create(**fields)` | write a new alert; if an open alert with the same `dedup_key` exists, update it instead of duplicating |
| `load_open(subject=None)` | open (non-expired, non-done) alerts, optionally filtered by subject |
| `evaluate_cheap(alerts, market_data)` | for `metric`/`due` triggers, return which fire given the supplied prices/dates; mark `status: triggered`. Does **not** touch `{check: ...}` alerts |
| `set_status(id, status, note=None)` | transition + append to `log` |
| `sweep()` | move past-`expires_at` open alerts to `expired`; clear elapsed `snooze_until` |

`evaluate_cheap` takes data the caller already fetched (no network of its own) so it is cheap
and keeps `daily-brief` fast. `market_data` carries last/day-change for held & watched symbols
and today's date. Covered by `lib/test_alerts.py`.

### `alert-manager` skill (new, thin)

The documented owner of the alert contract (as `strategy-manager` owns specs). Modes:

- **list** — open alerts grouped by subject/severity.
- **dismiss `<id>`** — `status: done`.
- **snooze `<id> <until>`** — set `snooze_until`.
- **add** — interactively create a manual alert (e.g. "tell me if RELIANCE closes below 1450").
- **sweep** — run `alerts.sweep()`.

Registered in `.claude-plugin/plugin.json` skills list; no MCP/scrape needs.

### Producers (write alerts as a side-effect of normal runs)

| Skill | Raises |
|---|---|
| `trade-tracker` | `price_cross` exit-watch (stop/target level), `time_stop` (time-stop date), `regime_change` (for strategy-linked trades) |
| `filings-watch` | `filing_act_on` for 🔴 items |
| `strategy-manager` | `revalidate_due` when a spec is stale / out of regime |
| `deep-analysis` | `reanalyze_due` (revisit in N days) + `price_cross` at the invalidation level |
| `find-trade` | `price_cross` entry-trigger watch on a confirmed-but-unfilled idea; `opportunity` for a vetted candidate |
| `portfolio-review` | `rebalance_due` |
| `mf-research` | `sip_due` |

Producers set `dedup_key` so repeated runs refresh rather than pile up.

### Consumer — `daily-brief`

New top section **"⏰ Alerts & actions"** (above the existing position-health section):

1. `alerts.load_open()` for held + watched names and portfolio-wide.
2. `alerts.evaluate_cheap(...)` against data the brief already fetched (indices, holdings
   last/day-change, today's filings) → fire those inline with their `action.text`.
3. List due date-based alerts (`sip_due`, `reanalyze_due`, `revalidate_due`).
4. For `{check: ...}` alerts, print the exact `action.suggest` command — **never auto-run**.
5. Lead with anything at `severity: act`.

This realizes the brief-as-dispatcher: it sees what fired and what needs a skill, without
becoming slow or taking actions on real money.

---

## `daily-brief` content additions

Final `daily-brief` section order:

1. **Indices** (existing).
2. **Market analysis** (new) — a market-level news digest: top 3–5 genuinely market-moving
   items (RBI/Fed, crude, FII/DII flows, global cues, major domestic policy/results), one line
   each, capped, plus a 1–2 sentence net read. Sources: already-whitelisted ET / Moneycontrol
   market wrap + Google News RSS (`India stock market`). All fetched text treated as untrusted
   data, not instructions (CLAUDE.md). Skip opinion/listicle/target-price clickbait.
3. **Sector tone** (existing).
4. **⏰ Alerts & actions** (new — see Phase 2 consumer).
5. **Opportunities** (new) — high-conviction *new* ideas (not already held/watched), strictly
   capped to avoid noise:
   - **Vetted** — from the alert inbox (`opportunity` alerts: a `find-trade` candidate off an
     active strategy, a `deep-analysis` BUY verdict, a sector leader). Shown with source +
     one-line basis + the command to act.
   - **News-flagged (unvetted)** — daily-brief may promote at most one stock from a strong
     news catalyst it sees that morning, **clearly labeled "unvetted"** with a
     `/deep-analysis <T>` suggestion to confirm. Never presented as a signal.
   - Cap: ≤ 2 vetted + ≤ 1 unvetted per brief; dedup against holdings, watchlist, and
     yesterday's brief.
6. **Watchlist & holdings — filings & news** (existing Section 3).
7. **Position health & attention** (existing Section 4).
8. **One thing** (existing Section 5).

**Watchlist maintenance** — `state/watchlist.json` becomes a managed, stamped list. Entry
shape: `{ticker, added, source, note}`. A **vetted** opportunity is **auto-added** (source +
date stamp) so it's tracked from the next run; **news-flagged unvetted** opportunities are
**not** auto-added (keeps the durable list clean). Pruning is **recommended only** — the brief
flags stale entries ("TATASTEEL: 30d on watch, no setup, no position → drop?") and the user
removes them via `alert-manager`/manual edit; daily-brief never auto-removes.

---

## Cross-cutting changes

- **`lib/contracts.md`**: update every artifact location to the new tree; add an **"Artifact:
  alert"** contract section (producers/consumer/location/schema); add a note that
  `lib/paths.py` is the path authority and `latest_prior` is the prior-run lookup; update the
  watchlist location to `state/watchlist.json`.
- **All ~14 SKILL.md files**: rewire their Output/Inputs path references to the new layout,
  described via the `paths.py` helpers (not literal strings where a helper exists).
- **`hooks/post-deep-analysis.sh`**: staging moves from `artifacts/.staging/` to `tmp/staging/`
  (under the resolved root); the archive destination becomes
  `stocks/<TICKER>/<date>/deep-analysis.md` and `…/deep-analysis/agents/`; the hook log moves to
  `tmp/`. The existing cwd-anchoring from stdin `cwd` is retained.
- **`.gitignore`**: already ignores `artifacts/` wholesale — still correct; no change needed
  (the new tier dirs are all under `artifacts/`).

## Testing

- `lib/test_paths.py` — every helper resolves correctly under cwd and under the env override;
  `latest_prior` picks the newest strictly-earlier run and returns `None` when there is none.
- `lib/test_alerts.py` — create/dedup (same `dedup_key` updates in place), `load_open`
  filtering, `evaluate_cheap` fires the right cheap triggers and ignores `{check: ...}`,
  `sweep` expires + un-snoozes.
- `lib/migrate_artifacts.py` — a dry-run test over a fixture flat `artifacts/` asserts the
  planned moves and that unclassifiable files are reported, not moved.
- Existing `lib/test_ta.py` and `find-trade/scripts/test_screen.py` stay green (path changes
  must not alter computed results).

## Phasing

- **Phase 1** (paths) ships independently: `lib/paths.py` + `lib/migrate_artifacts.py` + rewire
  all SKILL.md/scripts/hook + prior-run reuse + tests.
- **Phase 2** (alerts) builds on Phase 1: `lib/alerts.py` + `alert-manager` skill + producers +
  `daily-brief` consumer/content additions + tests.

Each phase is a separate implementation plan.

## Non-goals / YAGNI

- No scheduled/cron evaluation of alerts inside the plugin (consistent with the existing
  "no scheduled cron inside plugin" rule) — alerts are evaluated when `daily-brief` or a skill
  runs.
- No order execution, ever.
- daily-brief does not run skills or screen the universe itself; it surfaces and recommends.
- No auto-pruning of the watchlist.
