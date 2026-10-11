# Audit status

Work is in progress on `codex/plugin-audit-refactor`; the full-plugin objective is
not complete. After the user's correction, all parallel agents were interrupted
before they edited source. Implementation and verification are sequential.

## Implemented and reproduced

Each regression below failed against the original implementation before its fix.

| Area | Corrected behavior | Regression file |
|---|---|---|
| Test runner | Isolates personal artifact environment; rejects missing/zero assertions and an empty test collection | `finance/tests/test_runner.py` |
| Shared cache | Wrong-shaped JSON and future stamps are cache misses; writes replace atomically; impossible source dates are rejected | `finance/tests/test_spine.py` |
| Universe | Stale snapshots retain provenance across repeated calls; custom baskets have separate paths | `finance/tests/test_universe.py` |
| Relative valuation | Missing, nonpositive, and nonfinite company P/E cannot produce a valuation stance or PEG; invalid peer bases do not count | `finance/tests/test_relval.py` |
| MCP bulk files | Later calls cannot overwrite earlier result evidence; directory failures degrade; negative inline limits do not expose almost the full dataset | `finance/tests/test_server.py` |
| Holdings/allocation/wealth | Retains reported current values and zeros; shares one valuation helper; cost alone is not market value; rejects nonfinite personal amounts | `finance/tests/test_holdings.py`, `test_allocation.py`, `test_wealth.py` |
| Allocation | Explicit percentage weights convert using book value; partial supplied cap mix retains incomplete coverage | `finance/tests/test_allocation.py` |
| Wealth protection | Missing required cover assessment cannot certify strong protection or support adding risk; `act` concentration severity reaches scorecard | `finance/tests/test_wealth.py` |
| Live screening | Uses the same explicit entry condition as backtesting; a prose archetype no longer changes the entry price to a historical high | `finance/tests/test_screen.py` |
| Strategy selection | Missing trend, EMA, VIX or breadth evidence fails a required regime condition | `skills/strategy-manager/scripts/test_strategy_scripts.py` |
| Fund sources | Rejects partial name matches and invalid NAV values; projects client-filter columns and separates screen caches by requested fields/page limit | `finance/tests/test_funds.py` |
| Trade checks | Actual fill/date only; shared EMA; complete price-condition grammar; personal mark separated from decision price; validated/sorted bars and preserved gaps | `finance/tests/test_trade_check.py` |
| Trade lifecycle and learning | Full execution evidence and reconciled net returns required; incomplete/legacy outcomes cannot change lifecycle or rank; traversal/duplicate execution checks; atomic locked updates | `skills/strategy-manager/scripts/test_strategy_scripts.py` |
| Artifact paths | Rejects traversal and invalid dates, preserves valid nested caches/monthly budgets, degrades invalid prior-run inputs and sector dates | `finance/tests/test_paths.py` |

Verification uses synthetic offline fixtures; the latest full-suite result is recorded below. The installed MCP SDK also accepted and dispatched a basket-only
technical screen through a stubbed source, proving the public schema correction without a
network call. No broker actions or Telegram messages were sent.

Additional reproduced fixes:

| Area | Corrected behavior | Regression file |
|---|---|---|
| Backtest accounts | Marks open equity, includes zero-trade account capital and initial cash high-water mark; avoids last-bar finalization lookahead; computes R from actual fill/original stop; immutable full-precision evidence | `finance/tests/test_backtest.py` |
| Shared strategy parser and data | Requires entry conditions; accepts one string or a list; case-insensitive operators; shared risk validation; source gaps and bar dates retained; removes undated OHLCV loader and no-op alias | `finance/tests/test_screen.py`, `test_backtest.py`, `test_universe.py` |
| Plugin metadata | Nine invalid YAML descriptions use block scalars preserving exact text; every skill/agent frontmatter is parsed by the runtime YAML library in conformance tests | `finance/tests/test_agent_plugin.py` |
| MCP screening | Public schema accepts list or dictionary; basket-only dictionaries retain their symbols instead of becoming invalid filters | `finance/tests/test_agent_plugin.py`, `test_prices.py` + installed SDK dispatch |
| HTTP transport | Invalid setup degrades; only valid 2xx succeeds; protocols restricted to HTTP(S); transient retry exercised; binary publication is atomic and preserves old evidence on failure | `finance/tests/test_transport.py` |
| News | Shared atomic raw-feed cache serves different ticker/noise/date views locally; unknown dates stay unknown; exact publisher labels replace substring trust; reported claims are never auto-tagged verified facts | `finance/tests/test_news.py` |
| Fundamental screening | Intersects repeated bounds; rejects malformed/nonfinite/contradictory queries; verifies projected fields client-side; excludes missing/failed rows with gaps; validates limits before fetching | `finance/tests/test_fundamentals.py` |
| Exchange filings | All lists check issuer before selecting; ampersands query-encoded; XML booleans and numeric facts validated; conflicts and unreadable pledge evidence remain gaps; no pledge does not mean no other encumbrances | `finance/tests/test_filings.py` |

Integrated verification on 2026-09-13: `./bin/test.sh` returned **2,999 assertions
passed, 0 failed, 0 files errored**. `git diff --check`, Python compilation and the
runner shell syntax check passed. The conformance suite now parses all skill and
agent YAML frontmatter. These gates do not establish complete file coverage or
live-provider compatibility.

## Remaining work, in order

1. Finish trading-engine review: live/backtest
   target and stop semantics, warmup consistency and exit-reason labels;
   source-price adjustment versus original nominal trade levels. The core realized/unrealized lifecycle is corrected, but validate live broker payloads before release.
2. Finish source validation: fund-cache migration and pagination completeness;
   shareholding date ordering and XBRL context/denominator
   interpretation; source-response validation and URL trust boundaries. Resolve the remaining
   direct yfinance call versus the sole-transport rule. Review every source and test.
3. Finish DCF/wealth/remaining compute review: grid centers versus base valuation,
   zero sales-to-capital inputs, missing-data coverage and emergency liquidity,
   aggregation/ranking edge cases, alert mutation integrity.
4. Finish runtime and workflow review: launch/login concurrency; report
   staging/archive safety; hook date/time handling and cross-session isolation. All eight
   agent profiles have been read. Repeated report guidance remains because isolated agent
   contexts may need it; consolidation needs evidence about instruction loading.
5. Read every remaining skill/reference/agent/template/fixture/script, plus all local
   intent notes. Verify rendered reports. Reconcile README/contracts and scope of
   approved source rules. Keep justified compatibility adapters rather than deleting
   them simply for appearing repetitive.
6. Review the final diff and run appropriate focused and full gates; publish a
   file-by-file coverage ledger and final findings/suggestions. Do not claim a
   bug-free plugin or complete coverage based only on the green unit suite.

## Transcript evidence so far

Read the local DMART run review at `docs/.local/2026-08-25-dmart-run-review.md`.
It documents busy-waiting, unsupported tool payloads, unqualified agent launches,
repeated schema failures and filesystem-wide searches. Some were already fixed;
each needs comparison against current behavior rather than another speculative fix.

An aggregate scan of the project-specific Claude JSONL directory covered 77 files
(24 top-level sessions, including their subagent logs): 6,028 tool calls, 92 marked
tool errors and 36 exact repeated name+argument calls within a file. These are
development-session observations, not financial facts or a measured runtime
benchmark. Exact repeats may be legitimate verification. No credential contents
or full personal transcripts are copied into this repository.

## Trade-workflow scenario review

Sequential review of the old instructions exposed two unsafe transitions: a missing broker
position or agreement to a recommended exit explicitly closed the artifact; the result recipe
then copied unrealized metrics into realized returns. The corrected recipe requires full broker
exit executions, quantity reconciliation and actual charges. Scenarios checked against the new
producer/consumer contract: agreement without execution stays open; partial exits stay open;
missing holdings requires reconciliation; confirmed execution with missing costs closes with
unknown derived returns and is excluded from learning; complete evidence enters the verified
sample; duplicate IDs or inconsistent arithmetic produce REVIEW. No subagent eval or live
broker action was used.

Migration is intentionally evidence-preserving: no personal artifacts are edited. Legacy closed
results need actual broker references and charges; old cached live scores are ignored until the
aggregator recomputes eligibility. A future cleanup must not backfill these with guesses.

## Scope tracking

`docs/audit-coverage.csv` inventories all 209 original tracked files plus new regression files. Its states
are progress markers, not blanket approval. *(Superseded 2026-10-11 — see "Final integrated review":
no `traced-and-changed`, `initial-read`, `metadata-validated` or `pending` rows remain; the
current states are `final-reviewed`, `final-verified`, `final-checked`, `reviewed`,
`reviewed-fixed` and `removed`.)* New audit documents
are work records and are not included as original plugin files.

The production files changed in the table above and their matching tests have been
read and traced. `finance/compute/rolling.py`,
`relative_strength.py`, `finance/deps.py`, MCP declarations, launchers, hooks and
manifests have an initial read with unresolved follow-up items. `finance/sources/funds.py` has now been read fully; its memo freshness, parser resource cleanup, degraded enrichment and pagination limits remain to examine. The initial review
agents supplied leads, not a completed coverage ledger. *(This paragraph records the 2026-09 state; the remaining files received the sequential
audit and final integrated review on 2026-10-11.)* News, filings and fundamental sources/tests and the news method were read fully in this continuation; source trust
and filing-context interpretation still need final cross-component review.

## Sequential continuation: company data and workflow corrections

Company cache keys now include explicit SID overrides; section-specific responses recompute
success from actual requested content. Unknown section names fail before fetching and one
malformed endpoint degrades independently. Fundamental field matching no longer silently
accepts ambiguous prefixes. Tickertape lookup validates identity, rejects conflicting exact
matches and uses collision-resistant cache paths.

The quick research pass is now a local leaf with keep/reject/review, not an invented numeric
score or recursive dispatch. Discover preserves the deterministic scan order among keeps and
separates unresolved candidates. Broker absence requires a complete account check; incomplete
coverage is unknown. Mode resolution parses contained YAML state with exact identity, status
and read-failure gaps. Debate continuation validates digest types before interpreting agreement
or round caps. Standard runs one round, deep at most three.

Manual instruction review covered quick with missing fundamentals (review), incomplete broker
coverage (unknown), one-sided evidence exhaustion (continue within the cap), and malformed
round digests (stop with gaps). These are sequential contract checks, not measured agent evals.

Live-price regression fixtures exposed quantity/risk disagreement after rounding and floating
point rejection of a valid 1.5 ratio. Sizing now uses the published prices. A separate regression
exposed specs lowering the mandatory RRR floor: shared validation rejects these before universe
or price fetches in both live and historical orchestration. Backtests still use source precision
and next-open execution; actual fill risk is distinct from the published signal-bar plan.

Source policy remains unresolved pending the user's answer: `run_saved_screen` screens through
screener.in although the approved source table limits it to document indexing. No policy change
or live saved-screen fetch has been made while that question is pending.

## Runtime continuation: smoke checks and secret loading

Read both launchers, both hooks, hook configuration, secret loader, broker tests and the
complete smoke harness. Confirmed smoke failures: blocking readline defeated the timeout;
initialization exceptions escaped the per-server result and leaked a child; malformed envelopes
could crash or count as degradation. Deadline-aware response queuing, startup cleanup and typed
envelope validation correct these. Stderr retention is bounded. Each smoke child uses a private
temporary artifact root, so its alert sweep and compute output cannot touch personal state.

Secret-template publication now uses a private temporary file and atomic no-replace hard link.
It cannot truncate credentials written by another launcher, and templates are owner-only.
Loading existing credentials preserves the caller's export-all setting. Session context uses
India's date and describes weekday scheduling without claiming the market is currently open.

Verification: full offline suite returned 2,884 assertions, zero failures/errors. Two subsequent
smoke isolation assertions brought that focused file to 13 passing assertions. Shell syntax,
Python compilation and diff whitespace checks pass. A real installed-SDK stdio run of only
finance-personal passed tools/list and deterministic insurance math (2 passed, zero degraded
or failed). No live market/provider or broker calls and no Telegram sends were performed.

Remaining runtime findings are concrete:
first-login claim creation has a missing-owner race and a timed-out waiter can launch a competing
login; orphan detection assumes PPID 1 means abandoned. The Stop hook parses JSON with sed,
publishes/deletes groups non-atomically, shares staging across sessions, bypasses paths.py and
may expose credential-bearing curl errors. These need a coherent ownership/publication refactor,
not isolated string substitutions. No such changes are claimed complete yet.

## Shared launcher bootstrap

The finance launcher delegates interpreter selection and environment repair to a standard-library
helper. A permanent lock file uses kernel flock ownership; every waiter rechecks the SDK under
that lock, and process exit releases ownership without stale-PID recovery. The probe imports the
MCPServer API the plugin uses rather than accepting any package named mcp. Installation output
stays on stderr, leaving stdout available for interpreter selection and the server protocol.

Three concurrent offline subprocess starts performed one installation and selected the same
interpreter. Additional failure injection proved an unsuccessful repair returns no interpreter
and releases the lock for a successful retry. Runtime tests: 11 passed. Full suite before those
last two failure assertions: 2,889 passed, zero failures/errors. The helper also selected the
installed real SDK interpreter without installation. Shell syntax, compilation and diff checks
passed. Broker OAuth coordination remains separately unresolved.

## Broker first-login ownership

Replaced mkdir/PID claim recovery and the 120-second fall-through with kernel locking in
`bin/broker-login.py`. A waiter never launches a rival while a live login owns the lock.
Only a saved token or acquiring ownership permits launch. The pinned mcp-remote version and
shared token location remain unchanged. The wrapper validates missing URL arguments and no
longer kills unrelated processes based on PPID 1. Signals go to its own child process group.
The bridge inherits the lock descriptor, preserving ownership if its supervisor is killed.

Offline subprocess evidence: three cold starts create one login; terminating the owner permits
one replacement; killing the supervisor while its bridge survives does not create a competing
login. Protocol stdout contains only the child output. Runtime tests: 17 assertions passed.
Full suite before the final SIGKILL assertion: 2,896 passed, zero failures/errors. Diff and syntax
checks pass. No actual broker/OAuth action was performed. Existing optional pinned mcp-remote
integration scenarios still need execution before claiming provider-level compatibility; tests
here establish our coordination logic, not the external SDK's refresh behavior.

The earlier PID/timeout findings above are now addressed. Report publication remains the next
runtime refactor: session-owned staging, validated JSON/cwd, atomic evidence publication,
paths.py ownership and safe Telegram diagnostics must be changed together with their producer.

## Publication foundation (producer/hook migration still pending)

Added session-owned, uniquely identified report bundles in finance/publication.py, with all paths
owned by paths.py. Publication validates identity, rejects symlinks and incomplete runs, and moves
the complete bundle in one rename under a kernel lock. Same-day reruns preserve earlier evidence.
A failed move retains staging. Prior-run lookup accepts complete bundles and preserves legacy
support. The additive contract and CLI are documented in finance/contracts.md.

Nine focused publication assertions pass, including session separation, identity mismatch,
missing readiness, immutable reruns, failed move recovery and mode-specific prior-run selection.
Existing path tests pass (65 assertions). Full suite: 2,906 passed, zero failures/errors. Compilation
and diff checks pass. The writer, session-context handoff and Stop hook are NOT migrated yet;
therefore the old pipeline remains unsafe and publication refactoring is not claimed complete.
Next step is to wire those producers/consumers together and remove their flat shared staging,
then handle Telegram delivery without leaking credentials or losing archive evidence.

## Publication pipeline wired (2026-09-15)

The writer/orchestrator now uses prepared session bundles and marks readiness after render checks
and completed work papers. Normal completion explicitly invokes the shared loader/publisher wrapper;
Stop is recovery for that exact JSON session_id/cwd. SessionStart exposes the literal session identity.
Hook payloads are parsed as JSON; absent/invalid identity or cwd never falls back to scanning shared
staging. Legacy flat staged files are preserved for explicit inspection, not automatically assigned.

The old shell file-move/delete loop is removed. Python publishes the whole bundle, then optionally
sends the archived deck through transport.request. Telegram requires prepare --telegram from user
authorization; credentials alone do not enable it. Tokens are sent to curl through stdin, uploads use
private temporary files, private URLs follow no redirects, and sends have no automatic retry. Errors
never expose response bodies or curl stderr, and cannot undo archiving. The API and producer/consumer
contracts, README and report-writer instructions now agree with this behavior.

Verification: full suite 2,917 passed, zero failures/errors. After final multipart input validation,
transport tests passed 64 assertions. Publication tests passed 21 assertions including the actual
shell wrapper for Stop and explicit publish, escaped cwd, repeated Stop, session identity, no
unauthorized delivery, real archived bytes in a mocked multipart send, and safe failure diagnostics.
No actual Telegram request was made. Earlier notes saying the hook migration is pending are superseded.

Remaining report concerns: renderer/template visual audit and avoiding shared dated valuation/
management leg writes before taking bundle snapshots. Publication now prevents mixed staged papers,
but those separate leg producer contracts still need isolation; do not claim the entire analysis
pipeline is concurrency-safe until they are addressed.

## Valuation and management output isolation

Reproduced DCF result overwrite with two same-day calls. The engine now writes content-addressed
JSON containing exact supplied inputs, full calculation and relative read. Identical evidence
reuses its path; changed evidence cannot overwrite it. Removed the implicit same-day revision
ledger, which incorrectly treated another session as a revision. The compatibility field remains
empty; report authors cite old/new evidence paths and explain intentional assumption changes.
DCF and backtest now share the atomic evidence writer in spine.py rather than duplicating it.

The two leg skill workflows honor explicit bundle report/input paths. Deep-analysis passes those
paths before dispatch and no longer relies on late snapshots of shared dated files. Prior-run
lookup finds archived bundle dcf.md and management.md, retaining standalone legacy support.
Tool metadata, report template guidance and contracts describe immutable DCF paths.

Verification: full suite 2,923 passed, zero failures/errors. Publication/path scenarios passed 23
assertions. DCF focused tests passed 129 after one additional storage-failure assertion; backtest
focused tests passed 174. Compilation and diff checks pass. These are persistence and workflow
proofs, not completion of the DCF valuation-method or governance-policy audits. Those remain next,
along with report rendering, remaining source issues and the file-coverage inventory.

## DCF scenario consistency

Regression tests reproduced four sensitivity defects: a WACC buildup grid centered on an invented
11% rate; terminal-WACC perturbations also changed young-company explicit discount rates; the
zero-shift story cell erased negative operating margins; explicit terminal-margin inputs did not
shift with the story scenario. Fixed these in the responsible scenario builders. Reverse margin
solving now uses the same signed explicit/terminal path. Finite positive sales-to-capital validation
replaces the branch that turned a zero ratio into zero reinvestment.

Full suite: 2,932 assertions passed, zero failures/errors. One subsequent reverse-solve regression
passed, bringing DCF focused checks to 138. Compilation and diff checks passed. These reproduce
internal model invariants with synthetic inputs; they do not establish source authenticity or
validate every financial-method assumption. Remaining DCF audit includes type/range/finite checks,
default input assumptions, equity-shaped negative earnings, terminal and recovery constraints,
and the reference's recommendation rules. Governance policy, remaining sources and unread files
also remain within the active goal.

## DCF input boundaries

Reproduced silent coercion of fractional/bool horizons, bool path entries, empty paths and numeric
text, along with accepted NaN/infinity, invalid recovery fractions, financing weights and growth
below -100%. Added checks in the existing path/scalar/rate resolvers rather than a parallel model
validator. Glide timing now refuses fractional/bool or out-of-horizon years; default-free-rate
confirmation requires literal true. Negative operating margins remain supported. Reverse-margin
output no longer clips the negative years that the solver used.

Fresh full suite: 2,948 assertions passed, zero failures/errors. DCF focused tests: 153 passed.
Compilation and diff checks passed. Broader financial-method review is still incomplete: input
source/default assumptions, equity-shaped valuation, negative equity/failure interpretation,
reverse-solver bracketing and rounding of derived risk inputs need examination. These tests prove
specific numerical boundaries, not that all valuations or all plugin files are now correct.

## Discovery gate failures

Read stock_scan.py and its tests fully. Reproduced widening to the full screen after a named
universe failed, use of candidates from ok:false quality responses, unknown ranking fallback and
whole-run abort from one price-loader exception. Required gates now stop the shortlist; validation
runs before fetching; per-symbol failures degrade independently. Source gaps survive a usable
universe response, gate/universe exceptions degrade, malformed candidates refuse and duplicates
are removed before ranking. Trading instructions no longer permit seven-day shared survivor files
or momentum substitution when a required fundamental gate fails.

Full suite before the last two focused cases: 2,952 assertions passed, zero failures/errors.
Stock-scan focused checks: 22 passed. Compilation and diff checks pass. Remaining stock-scan
work: dated/aligned price evidence, preserving source price gaps, immutable output publication,
and the unresolved saved-screen source policy. This is not a complete discovery audit yet.

## Stock-scan evidence and dates

The source adapter now retains gaps, source and fetch timestamp; validates dated positive finite
closes without silently deleting bad bars; and sorts history. Ranking refuses mixed endpoints or
mismatched comparison sessions. Relative context checks each window rather than requiring equal
full-history lengths. Candidates carry actual price dates; top-level as_of no longer stamps stale
prices with today's run date. Stock-scan output uses the shared immutable evidence writer, so a
changed rerun cannot overwrite the shortlist a downstream reader already received.

Full suite: 2,961 assertions passed, zero failures/errors. Focused stock-scan checks: 29 passed.
Regression evidence includes source-gap retention, stale endpoint exclusion, matching windows
with unequal total histories, misaligned relative windows, invalid injected prices and rerun
preservation. Diff checks pass. Saved-screen source-policy reconciliation remains outstanding;
source-price freshness/adjustment validation and shared sector RS behavior require their own audit.

## Sector screening and shared RS

Read sector_scan.py, its tests and relative_strength.py fully. Reproduced NaN becoming Lagging,
invalid prices producing returns and one sector failure aborting the scan. Shared RS now rejects
nonfinite/bool/nonpositive price endpoints and invalid lookbacks; missing or nonfinite RS cannot
be classified. Stock and sector scans reuse prices.close_history and a common loader boundary,
removing the duplicated adapter. Sector windows require 127 prices and matching benchmark dates;
source gaps remain visible. Invalid limits refuse before fetch. Sector output is immutable and its
observation date is separate from generation date. Failed/invalid valuation rows cannot rank.

Full suite: 2,972 assertions passed, zero failures/errors. Two subsequent valuation cases passed,
bringing sector-focused checks to 30. Compilation and diff checks pass. No network calls were
made. Sector method/reference review, source freshness and saved-screen policy still remain;
these code checks do not prove complete plugin coverage.

## Alert storage and lifecycle

Read alerts.py and its test file fully. Reproduced collisions between distinct same-day alerts,
snoozed dedup refresh waking the alert, unsafe path IDs and non-atomic status writes. The store now
uses unique IDs, contained paths, reentrant thread/process transactions and atomic replacement.
Dedup refresh preserves snooze state and refuses cross-subject/key collisions. Completed records
remain when a new alert is raised. Cheap evaluation reloads persisted status, preventing stale
snapshots from resurrecting dismissed alerts. Dates/statuses/severities and metric threshold
validity are checked; manage returns labelled failures on storage/validation errors.

Full suite: 2,984 assertions passed, zero failures/errors. Alert-focused checks: 50 passed, including
three concurrent processes with nine refreshes retained in one alert log, interrupted-publication
preservation, stale-status evaluation and malformed dates. Diff checks pass. Remaining alert work:
malformed legacy YAML must degrade per record rather than hide the whole inbox; complete trigger
shape validation, expiry/dedup boundary behavior and historical market-date semantics still need
review. No personal alert files were touched; all tests used temporary stores.

## Alert legacy-record degradation

Added one shared record validator for reads and writes. Malformed YAML, scalar records, mismatched
IDs and invalid record fields are skipped independently and preserved with named gaps, keeping
valid alerts visible. Manage list/add/sweep carry these gaps; direct library readers can collect
them or receive warnings. Trigger types must be unambiguous, dates cannot be null, and expired
unswept alerts cannot absorb a new reminder. Validation happens before atomic publication.

Full suite before the additional null-date case: 2,992 assertions passed, zero failures/errors.
Alert-focused tests: 59 passed. Compilation and diff checks passed. All fixtures were temporary;
no personal records were read or changed. Alert date semantics (calendar reminders versus dated
market snapshots) and the consumer instructions still require final review before this domain
can be marked complete.

## Daily-brief and alert consumer review

Read daily-brief SKILL/reference/Telegram template and alert-manager SKILL fully. Corrected personal
broker-mark leakage into decision inputs, unverified close-event wording, invented four-week time
stops and an instruction claiming alert-manager edits watchlists. Quote/history requests use the
unique held/watched symbol set; completed-close triggers remain distinct from intraday marks and
actual exits. Inbox gaps are explicitly reported. The fallback positions example is valid JSON.

Moved deck delivery into finance/telegram.py and added the authorized text sender used by the
brief, removing direct-curl instructions. Both use the shared transport; the wrapper loads secrets
consistently. Six new offline sender assertions cover missing credentials, Unicode length,
private/nonretrying transport and credential-safe errors. Publication regressions remain green.
Full suite: 2,999 assertions passed, zero failures/errors. No message was sent. Remaining brief
issues include atomic watchlist maintenance, same-day report output isolation and visual review;
calendar-vs-market-snapshot alert semantics remain for the compute consumer boundary.

### Dependency bootstrap protocol and concurrency repair (2026-09-15)

Read finance/deps.py completely and traced its callers plus the TA-Lib bootstrap.
A generic ImportError formerly triggered pip even for an installed package with a broken
ABI or missing transitive dependency. Only a missing requested top-level module now
qualifies for bootstrap. Pip and Homebrew installer output is routed to stderr, preserving
MCP stdout. Shared thread/kernel locking is keyed to the Python environment; callers
recheck imports after acquiring ownership. Installer children inherit the lock descriptor
so parent exit does not release ownership while an installer is still running. The TA-Lib
bootstrap uses the same lock and missing-module rule. Existing native setup behavior is
retained; package-version/native-wheel policy still needs a separate deployment review.

Validation: 15 offline dependency assertions (including three concurrent processes and
one fake install), 64 technical-analysis assertions, and diff whitespace check pass.
No real installer or provider was invoked. This is focused validation; the most recent
full-suite result remains 2,999 assertions before these added tests.

### Strategy exit validation (2026-09-15)

Read finance/compute/strategy.py in full and traced screening/backtest validation.
Unknown stop names silently became recent_swing_low; zero holding periods silently
became 20 sessions, and fractional/boolean periods were coerced. Negative/nonfinite
trailing multipliers could reach trade management. Shared exit validation now rejects
these before universe/history fetches and at direct live/backtest construction.
The recent-swing-low backtest branch requires the same ten bars as the live rolling
minimum. The example documents positive holding periods and nonnegative trailing
multipliers. No artifact fields changed.

Thirty regression assertions failed before the repair and pass after it. Full suite
now passes 3,044 assertions, zero failures/errors, including the dependency changes.
Remaining strategy issues: free-text target substring interpretation, differences in
fixed-target versus trailing/signal live representation, automatic stop-floor method
assumptions, and seed strategies' approximation of their reference rules. These remain
open; validation fixes alone do not establish live/backtest semantic equivalence.

### Exact strategy target rules (2026-09-15)

Replaced target substring matching with a shared exact vocabulary. The example mixed
next_resistance and measured_move and silently selected measured_move; misspellings
also silently became a risk-multiple target. Unknown/free-text targets now fail input
validation. Dynamic modes require their actual trail or signal. Updated the example
and five draft seeds to executable values with explicit notes on prior-high/Fibonacci/
squeeze approximations; these drafts are not promoted to validated strategies.

Live dynamic exits previously invented a fixed min-RRR target while the backtest
used no take-profit. They now return a labelled skip, as the plugin requires a fixed
objective for a live entry; dynamic backtesting remains available. This is an explicit
live-mode limitation, not a claim of dynamic-strategy support across both paths.
Contracts, discover, strategy generation, and backtest reference agree. Legacy prose
strategy files require an author-selected exact rule rather than automatic migration.

Eight regression assertions failed before the repair. Full suite after repair and
additional dynamic-mode checks: 3,061 assertions passed, zero failures/errors.
No network calls or personal-data writes were used. Remaining method work includes
source fidelity of each draft's stop/entry/objective, automatic stop widening, and
actual execution risk beyond the signal-bar proxy. Full-file coverage remains open.

### Quote issuer boundary and price cache paths (2026-09-15)

Read sources/prices.py and test_prices.py completely. Quote retrieval accepted the first
scanner row, even for a different stock; malformed scanner identities could also raise.
Quote success now requires exactly one requested NSE row and a finite positive close.
Malformed row shapes are excluded, and cached quote identity/source/success are checked
before reuse. Price-cache filenames now hash the request tuple, preventing symbol or
period strings from becoming filesystem components and separating adjustment modes.
Old cache filenames are ignored and left intact.

Focused validation: 59 price assertions pass, including wrong first row, duplicate
issuer rows, corrupt shapes, invalid closes, wrong cached issuer, and contained/distinct
cache identity. No provider fetched. Candle validation, false settled-session inference,
history-cache shape verification, scanner screen gap propagation and yfinance's direct
network path remain open. The two old unsettled-bar tests mirror implementation and
will be replaced when that boundary is repaired; they do not prove settled-bar behavior.

Full suite after quote repair: 3,076 assertions passed, zero failures/errors.

### Candle validation and truthful missing-data reporting (2026-09-15)

The source checked only whether close was non-NaN and called all rejected bars
unsettled, hiding genuinely missing historical observations. A shared candle validator
now checks dates, positive finite prices, nonnegative volume, OHLC geometry and duplicate
sessions; invalid/ambiguous rows are excluded and counted as bars_dropped_invalid with
gaps. Histories are sorted. Cache reuse verifies issuer, period, adjustment, validated
series and summary; new envelopes record adjustment. Removed the unsupported
bars_dropped_unsettled claim and updated contracts. Current-day bars explicitly report
unverified completion; completed-session verification and consumer gating remain open.

Replaced eight implementation-mirroring assertions with actual fake-provider history
checks. Full suite: 3,077 assertions passed, zero failures/errors. Three subsequent
cache/current-day assertions also pass in the focused 63-assertion price suite. No real
provider calls. Partial series still carry gaps; source trust/session verification and
transport unification remain necessary before full price-layer completion.

### Scanner screen input and output boundaries (2026-09-15)

Screen formerly allowed string/boolean/fractional inputs, arbitrary payload range
overrides, malformed-response-as-no-match, duplicate candidates and BSE rows that
downstream NSE tools could misidentify. Requests now validate columns/filter container/
limit, enforce NSE and the public limit, and responses retain only unique usable NSE
candidates. Invalid rows and response shape are labelled gaps. Breadth already forwards
those gaps with actual denominators; no second interpretation was added there.

Focused price suite: 72 assertions pass. The malformed-row/parser and prior quote/cache
checks remain green. Full request-filter vocabulary/semantic verification, provider
field typing and completed-session evidence remain separate open boundary work.

Full suite after scanner changes: 3,089 assertions passed, zero failures/errors.

### Packaging inventory and paths containing spaces (2026-09-15)

Read both plugin manifests, both MCP manifests, marketplace, hook manifest, gitignore,
.env.example and all four empty package markers. Hook command paths lacked shell
quotes, breaking installs under paths containing spaces. Both now quote the expanded
path. Added real shell execution against harmless stub hooks in a temporary spaced
directory: both assertions failed before and pass after the fix. The .data launcher
fallback was only partly excluded via generic venv/env rules; now its entire runtime
state is ignored. Git check-ignore confirms new runtime filenames are excluded.

Packaging conformance suite: 255 assertions pass. No real hook, broker or messaging
endpoint ran. Existing manifest formats remain unchanged; cross-client installation
claims and final release packaging remain to be verified. Previous full suite remains
3,089 assertions before these two added packaging tests.

### Market-cap classifier input semantics (2026-09-15)

Read finance/caps.py completely and traced its funds/lookthrough consumers. Generic
financial-number coercion accepted a percentage as an ordinal rank; fractional ranks
also classified. Prefix matching mapped mixed/ambiguous labels (large and mid cap,
smallish, microfinance) to a single tier. Rank parsing now requires a finite positive
integer value, and fallback labels match exact normalized single-tier terms. Unknown
labels remain unknown. Existing rank thresholds and rank-over-label precedence remain.

Nine new assertions failed before repair. Focused proof: 102 lookthrough and 253 funds
assertions pass; diff whitespace check passes. No providers or personal data used.
AMFI freshness/coverage and provider label trust remain source-layer questions; this
change does not infer classification from market-cap amounts.

### Document snapshots, index isolation and truthful extraction gaps (2026-09-23)

Read sources/documents.py completely. URL-addressed text was overwritten on refresh,
invalidating earlier citations. Extraction now runs in a private temporary directory
and publishes immutable URL-plus-content-hash text via the shared evidence helper;
the URL metadata pointer is atomically updated after successful extraction. Legacy
metadata is ignored for fresh extraction, while older files remain intact. Cached
metadata validates URL/kind, snapshot namespace and file counts. More thorough cached
content validation and publisher/content-type trust remain open.

Document counts now reject invalid/coerced inputs before fetching. Disabled sections
do not generate missing-document gaps; malformed index lists/entries degrade locally,
URLs deduplicate before the count, and per-document failures preserve other results.
Empty extraction no longer asserts the cause is a scanned PDF. Outline absence is
explicitly a heading-matcher miss, with saved-text search permitted before reporting
a gap; contracts and both financial/management skills were updated.

Focused proof: 109 document assertions pass, including changed-content refresh keeping
the prior citation, wrong counts, malformed neighbors and disabled sections. The earlier
full-suite process/log no longer exists after environment restoration; no result is
claimed for it. A fresh full-suite run is in progress. No live document/source fetched.

Fresh full-suite verification completed: 3,114 assertions passed, zero failures/errors.

### Cached document content verification (2026-09-23)

Count/line checks accepted same-length edits to financial figures in cached documents.
The cache now verifies snapshot bytes against the SHA-256 encoded in the path, reports
corruption, and attempts replacement. If the source is unavailable, no corrupted text
path is returned. Publisher is derived from the current URL on cache reuse instead of
trusting cached metadata for that label.

Two regression assertions failed before the fix. Focused document suite now passes
113 assertions, including successful repair and failed-repair degradation. No external
source was fetched; the previous full-suite result remains 3,114 before these four
new assertions. Publisher approval, HTML challenge detection and date-label interpretation
remain open source-boundary issues.

### Document format validation (2026-09-23)

Non-PDF downloads were decoded with replacement characters and cached indiscriminately.
A .pdf URL returning HTML now fails format validation; non-PDF content requires valid
UTF-8 and no binary controls, and known access/login/error titles are refused. Cache
metadata records the internal validation version so old unchecked entries re-extract.
The public document-row schema is unchanged. These checks establish supported format,
not authenticity; publisher/redirect approval remains open. Unknown challenge pages
can still require human assessment of the extracted primary document.

Four bad-format regressions failed before the change and now pass. Focused document
suite: 117 assertions passed, zero failures. No real document was fetched.

### NAV observation alignment and rolling input validation (2026-09-23)

Read compute/rolling.py completely and traced its fund_scan consumer. nav_metrics
appended a date before parsing its NAV; a failed value conversion left arrays misaligned.
Malformed observations now fail the fund's metrics, with the worker returning a labelled
gap so other funds continue. Rolling calculations validate equal array lengths, ordered
unique calendar dates, finite positive NAVs and a positive window. Drawdown rejects bad
NAVs as well. Fund scanning now carries worker/source gaps into its output even when
metrics remain usable; previously those gaps were discarded.

Six rolling regressions failed before the repair. Focused proofs passed (20 rolling
and 70 fund-scan assertions before the additional worker-degradation assertion). Full
suite launched including that worker check. No market provider accessed. Window method,
finite derived outputs, benchmark alignment and complete fund-score review remain open.

Full suite completed: 3,131 assertions passed, zero failures/errors.

### Fund scanner request semantics (2026-09-23)

Completed the full fund_scan.py read. Unknown windows silently became 3y, and top=0
silently became one shortlisted fund. Invalid worker counts and numeric gates could
fail after fetching. The scanner now validates its window, count, workers, category
shape and finite nonnegative numeric options before fetching; agility ceilings must
be positive. The report wrapper returns an error envelope without writing an artifact
for invalid inputs. Focused fund suite passes 89 assertions, including 18 new checks
covering local rejection and public error envelopes. Full suite launched.

During the initial red test, legacy behavior progressed into artifact creation using
the ambient personal artifacts setting; the sandbox denied that write. The test now
mocks the additional AMFI source as well, and passing validation stops before any
source. No claim is made that the initial failing test was fully isolated. Remaining
fund work includes AMFI ambiguity, plan identity, scoring comparability, mandate display,
mutable output paths and source freshness.

Full suite completed: 3,149 assertions passed, zero failures/errors.

### Fund scanner AMFI identity ambiguity (2026-09-23)

The cross-provider join selected the shortest matching scheme name and accepted
extra identifying tokens, potentially attaching a different scheme's NAV history.
The scanner now requires exact identifying token equality after its documented
plan/noise terms and one distinct Direct-Growth AMFI code. Ambiguous/no matches
become a labelled gap, duplicate rows for the same code remain usable, and malformed
registry neighbors do not abort matching. Existing typed fund lookup is separate;
this change concerns the automatic category-scanner join only.

Focused fund-scan suite: 93 assertions pass. Regression cases cover multiple codes,
more-specific scheme names, duplicate identity rows and malformed neighbors. No
source call is needed for these checks. Name changes/aliases may now require an
explicit verified identity mapping; the scanner does not guess that mapping.

### Immutable fund-scan evidence (2026-09-23)

Fund-scan reports wrote directly to one category/day path, so later calls could replace
evidence cited by earlier results. Publication now reuses spine.publish_evidence and
returns a content-hashed JSON path. Identical content reuses its path, changed content
retains both versions, and failure keeps the computed shortlist plus a gap/null path.
The optional out argument is now a filename-prefix hint, matching sector/stock scans;
contracts specify that consumers must use report_path.

Two preservation regressions failed before repair. Focused fund-scan suite now passes
97 assertions, including snapshot publication failure. No provider access was needed.
Previous full suite remains 3,149 before the subsequent identity/snapshot assertions.

### Fund mandate-purity display (2026-09-23)

The ranked text table chose the first truthy small/mid/large allocation for its purity
column, independent of the category being scored. It could show small-cap exposure for
a large-cap mandate and replace an actual zero with a different tier. The renderer now
uses the category's existing purity_field configuration to select the displayed metric;
zero stays zero and categories without a single-tier purity metric show unavailable.
No artifact schema or scoring calculation changed.

Three regression assertions failed before repair. The focused fund-scan suite now
passes 101 assertions, covering large, mid, small (zero) and flexi-cap display. Remaining
method issues include out-of-range purity values, threshold assumptions and score
comparability; this presentation fix does not resolve those.

### Invalid cap percentages cannot earn scores (2026-09-23)

cap_purity clamped out-of-range provider percentages into [0,1], so 120% earned a
perfect score and -5% became a real zero allocation. Values outside [0,100] now yield
an unavailable component with a named source-field gap. They add no score coverage and
do not trigger a mandate-underallocation claim based on an impossible number. Original
provider cap-mix fields remain visible alongside the gap for auditability.

Two assertions failed before repair; the focused fund-scan suite now passes 103,
including an offline full scanner pass proving gap propagation and score exclusion.
Full suite launched. Methodological choices such as peer comparability and automatic
missing-weight redistribution remain separate review items.

Full suite completed: 3,163 assertions passed, zero failures/errors.

### Finite rolling-return outputs (2026-09-23)

A finite long-window CAGR could become infinity because the endpoint ratio overflowed
before annualisation. Rolling returns now use log-space growth and expm1, and reject
unrepresentable outputs with ValueError (handled as an affected-fund gap by the scanner).
Rolling statistics reject nonfinite/boolean values; scaled summation and midpoint
calculation avoid overflow for representable means/medians. Oversized window products
also reject instead of silently behaving as an empty history.

Five numeric regressions failed before repair. Focused proof: 27 rolling assertions
and 103 fund-scan assertions pass, including large finite summary values. Calendar
window choice and matched benchmark endpoints remain methodology work; numerical
validation does not establish those assumptions.

### Look-through weight validity and unused math removal (2026-09-23)

Read compute/lookthrough.py fully. Negative/missing/nonfinite holding weights and
contradictory equity totals could inflate coverage or distort concentration. The
portfolio boundary now rejects invalid percentages, overfull books and listed weight
above the supplied allocation; explicit zero is preserved rather than treated as absent.
The public report returns a consistent unusable shape with source and validation gaps.
A tiny tolerance covers floating-point roundoff, not unexplained excess positions.

Removed the unused CAGR helper: repository-wide call tracing found only its own tests,
and it compressed missing observations into fewer periods. No production consumer
needed it. Focused look-through suite: 114 assertions pass; full suite launched.
Remaining: unknown-denominator coverage, differing P/B/ROE holding subsets, accounting
interpretation of weighted ROE and loss-making holdings, and unsupported method claims.

Full suite completed: 3,182 assertions passed, zero failures/errors.

### Joint P/B–ROE coverage and interpretation (2026-09-23)

P/B divided by ROE used independently aggregated inputs and the minimum of their
coverage percentages, which overstates the unknown intersection. The helper now
accepts holdings and recomputes both inputs over the same usable set. Disjoint 60%
coverage with 20% overlap correctly withholds the result; a 60% common set excludes
unmatched ratios from the value. The internal aggregate-number helper signature was
removed so callers cannot assert joint coverage without supplying the holdings.

Updated contracts and MF guidance to require matched coverage and removed the
unsupported claim that this ratio survives bad data or always breaks valuation ties.
Also reconciled the guidance with the engine's 60% publishable / 85% decision-grade
thresholds. Undefined nonpositive joint ROE preserves actual coverage and reports
the actual reason, rather than falsely blaming low coverage.

Three overlap regressions failed before repair. Full suite: 3,185 assertions passed,
zero failures/errors. After the small undefined-value diagnostic refinement, the
focused look-through suite passes 119 assertions, including two additional checks.
Accounting interpretation of portfolio-weighted ROE and unverified method thresholds
remain open; this fixes subset consistency, not all valuation-method assumptions.

### Missing equity denominator and source precision (2026-09-24)

Look-through no longer substitutes listed weight for a missing equity allocation;
a nonempty book without that denominator returns an unusable report. The loader
preserves missing allocation as None instead of converting it to zero. Tracing the
producer also found that it rounded the total to two decimals while leaving positions
more precise; a valid book could then appear inconsistent. The source now sums with
math.fsum and retains precision, using a new holdings cache namespace to bypass old
rounded entries. The sum is still based on disclosed provider rows: it is not independent
proof of completeness, and the contract explicitly states that limit.

Two new regression assertions failed before the repair. Focused proof: 120 look-through
and 254 fund-source assertions pass. Full suite launched after consolidating the source
sum into one computation. Unknown provider omissions, holdings duplicate identities and
invalid source row handling remain pending source-boundary work.

Full suite completed: 3,189 assertions passed, zero failures/errors.

### Holdings parsing cannot silently inflate coverage (2026-09-25)

The pending regression reproduced a crash on a non-object holding row. Other invalid
rows were silently discarded, so the denominator could shrink and make a partial book
appear fully covered. The source now checks allocation shape, row weights and asset
types, security identities, duplicate IDs and aggregate weights. Valid positions remain
available, but any invalid or ambiguous allocation leaves equity_weight null with an
explicit gap. No valid positions means ok:false. The validated cache namespace bypasses
previously parsed books that did not enforce these invariants.

A second regression reproduced a crash on non-list sector data. Optional sector and
allocation-history containers now degrade independently; invalid sector rows are labelled,
and duplicate or excessive sector distributions are withheld. These optional-data gaps
do not invalidate otherwise valid holding weights. The contract documents this distinction.
Existing fixture assertions now acknowledge its missing cash weight instead of claiming
complete coverage. All tests used local mocked providers and temporary artifact roots.

Proof: 271 fund-source assertions and 120 look-through assertions passed; full runner
completed with 3,206 assertions passed, zero failures and zero errored files. git diff
--check passed. This is a bounded source-boundary repair, not completion of the overall
audit. Provider omissions remain unknowable from the disclosed list alone; fund holdings
freshness, ratio-enrichment gaps and avoiding enrichment for already unusable books remain
open alongside the broader audit items above. No subagents were used.

### Fund enrichment preserves gaps and avoids futile requests (2026-09-25)

Tracing the holdings-to-report path found that an unknown coverage denominator still
triggered the full stock-ratio enrichment fan-out. The loader now retains available
equity positions and source gaps without making those requests; the report remains
unusable. Enrichment also fetched repeated security IDs repeatedly and discarded gaps
on ok:true partial responses. It now fetches distinct IDs once while preserving all
input positions and propagating successful-response gaps. Repeated positions are not
silently removed or reweighted by enrichment; the holdings producer validates its book.

Missing ratios no longer imply an unlisted/newly-listed security. Metric gap language
now describes missing usable inputs, rather than asserting that approved sources never
publish the metric. Missing cap rank likewise describes what was returned, not what a
publisher does or does not publish. Producer/consumer contracts were updated.

Four new regression assertions failed before the fixes. Focused proof: 274 fund-source
and 122 look-through assertions pass. An intermediate full run caught a wording check
for the existing unpriced status; the clearer message retains that status term. Final
full run: 3,211 assertions passed, zero failures and zero errored files. git diff --check
passed. All new source calls were mocked. No agents or live financial requests used.

Remaining source audit: stock_ratios still assumes mapping-shaped payloads and a worker
exception can abort enrichment. That boundary needs direct regression evidence and a
producer-level repair; do not conceal it with a blanket caller exception handler.

### Malformed ratio payloads and cache identity (2026-09-25)

Direct regression fixtures reproduced an AttributeError in stock_ratios on a malformed
payload; malformed nested info/ratio containers and non-text identity fields had similar
unchecked paths. The source parser now returns an explanatory false envelope for those
responses. An end-to-end enrichment fixture verifies that one malformed holding retains
its weight and gap while another holding still receives its ratios. This repairs the
source boundary without swallowing arbitrary exceptions around the thread pool.

A separate regression proved that cache sanitization collapsed A&B and A_B: the second
request returned the first security's cached ratios. The shared fund cache path helper
now hashes the complete key, following the existing Tickertape cache pattern. This also
protects fund and NAV cache identities, while ignoring and lazily repopulating disposable
legacy entries. The old filename-spelling assertion was replaced by namespace containment;
the behavioral collision regression proves exact identity separation.

Proof: 282 fund-source assertions pass. Final full suite: 3,219 assertions passed, zero
failed and zero errored files; git diff --check passed. Fixtures were offline and isolated.
No subagents used. This closes the malformed-payload issue recorded in the previous entry;
it does not claim all possible worker exceptions are handled. Numeric-content validity,
source identity confirmation, cap-list memo freshness and the broader audit remain open.

### AMFI cache lifetime and workbook ownership (2026-09-25)

The cap-index memo was permanent for a running server, including failed reads, and
ignored artifact-root changes. A fake-clock regression proved that a new day and a new
session root both reused the original map. The memo now carries its day/root context:
within that context enrichment shares one map; on change it re-enters the existing disk
cache policy. This retains the 30-day source refresh policy without bypassing it forever.
Failed reads remain shared during a day rather than triggering retries per holding.

A concurrent offline download regression also proved that the PID-based workbook path
was shared by requests in the same process. Each request now owns a TemporaryDirectory;
cleanup applies on early returns as well as success. The read-only openpyxl workbook is
closed in a finally block before deleting its downloaded file. No added dependencies.

Proof: the clock/root and concurrent-file regressions failed before their repairs;
287 focused fund-source assertions now pass. Full suite: 3,224 assertions passed, zero
failed and zero errored files. git diff --check passed. No live fetches or subagents used.
Remaining AMFI work includes approved-host enforcement in workbook link discovery,
rank validation/duplicate handling, and source-period freshness claims; these are not
proven complete by the cache-lifetime checks.

### Approved AMFI workbook URLs and redirect boundary (2026-09-25)

Seven failing regression assertions showed that workbook discovery accepted unrelated
hosts, lookalike hosts, user-info tricks, HTTP, nonstandard ports and file URLs solely
because their filename matched; it also left path-relative links unresolved. Discovery
now uses urljoin/urlsplit and permits HTTPS on the existing www.amfiindia.com and
portal.amfiindia.com source hosts only, with no credentials or nonstandard ports.
The existing portal-host fixture caught an initially too-narrow host check; both actual
source hosts are covered. Legacy workbook caches are bypassed.

Host checking alone was insufficient because curl followed arbitrary redirects. The
shared transport now exposes follow_redirects=False, and both AMFI index and workbook
requests use it. A 3xx becomes a labelled source gap. Private URLs retain their existing
no-redirect behavior. Other source callers retain existing redirect behavior pending their
own trust-boundary audit; this is not a claim of global host enforcement. Standard-library
URL parsing and the existing transport remain the sole owners; no second network path.

Proof: 294 fund-source and 66 transport assertions passed. Final full suite: 3,233
assertions passed, zero failures and zero errored files. git diff --check passed. Tests
used mocked transport/subprocess calls; no live financial fetches or subagents used.
A legitimate future AMFI redirect or new host will now require updating the approved
endpoint; until then the plugin reports a gap instead of crossing the source boundary.

### AMFI rank validity and unambiguous joins (2026-09-25)

A workbook regression reproduced three defects: rank 100.9 was truncated into rank 100,
nonpositive ranks were accepted, and duplicate symbol/ISIN identities silently selected
one row. The parser now reuses caps.cap_label's finite positive integer validation,
excludes ambiguous identities, and reports excluded-row counts while preserving unrelated
valid records. The symbol and ISIN lookup maps therefore cannot choose conflicting rows
by iteration order. A separate failing join regression showed that RELIANCE plus REC's
ISIN selected RELIANCE's rank; conflicting ticker/ISIN evidence now withholds the rank
with a gap. The existing renamed-ticker ISIN fallback remains covered and passing.

Both workbook and stock-ratio cache namespaces bypass previously computed classifications.
The data contract documents the validation and partial-book behavior. Proof: 298 focused
fund-source assertions pass; full suite reports 3,237 passed, zero failed, zero errored
files. git diff --check passed. Offline fixtures only, no subagents.

The AMFI source-period selection still needs review (including future-dated filenames),
and the full plugin/report/transcript coverage audit remains incomplete. This entry
proves rank parsing and identity-join repairs only, not the entire cap-source policy.

### Future source periods and insurance IRR input audit (2026-09-25)

Three failing fixed-clock regressions proved that future AMFI periods could win link
selection and bypass validation through the disk cache. Discovery now chooses only
non-future dates, and cache reads enforce the same source-date invariant. The relative
link test now uses an elapsed period. This does not prove publication freshness or
that the source has released the most recent expected half-year edition.

Read all 352 lines of insurance_math.py and traced its public run envelope and tests.
The IRR solver returned -99% for empty/all-zero flows, and invalid numeric/bracket inputs
could return fabricated endpoint results or raise outside the envelope. The solver now
requires finite numeric flows/bounds/tolerance, a valid bracket above -100%, and positive
tolerance; absent positive or negative cash flows return no solution. Arithmetic errors
are labelled by the public adapter. Seven regression assertions failed before this repair.

Proof: 301 fund-source assertions and 58 insurance-math assertions pass. Full suite:
3,251 passed, zero failed and zero errored files. git diff --check passed. Updated the
coverage ledger to reflect the insurance full-file read and its remaining issues; no
blanket completion claim. Offline fixtures only, no subagents.

Insurance follow-ups from the full read: unsupported/default sizing assumptions (45%
expense substitution, fixed city/family health-cover rules, employer discount), >5-year
IDV assumption, input clamping/nonfinite outputs outside IRR, NPV overflow/underflow and
multiple-root ambiguity, and premium-timing prose versus implemented t0 payments. These
need separate evidence and method review; current tests do not prove them correct.

### Insurance IRR stability, ambiguity and timing (2026-09-26)

Regression examples proved that monetary NPV tolerance made tiny cash flows return
0.5% instead of 10%, a 400-period flow failed through discount-factor underflow, and a
narrow bracket selected one of two IRRs without revealing the ambiguity. The solver now
normalizes flows, evaluates NPV sign with discounted/scaled Horner recurrence, and stops
on absolute rate-interval tolerance. Sign comparisons avoid multiplying extreme values.
Leading/trailing zero flows do not change roots. A bounded iteration that does not
converge returns no supported solution instead of an unchecked midpoint.

Exactly one cash-flow sign change is supported. Flows with multiple changes are
conservatively withheld: some have multiple roots, and this API does not establish
uniqueness for them. This limitation is documented rather than pretending all such flows
have no mathematical root. Added checks also cover negative returns and reversed flows.
No new dependency. The private NPV helper has no remaining callers under its old name.

Continuation-math prose now matches implementation: premiums at t0 through n-1, surrender
opportunity cost at t0. Removed the docstring's automatic surrender recommendation; a
cash-flow comparison alone does not decide coverage, taxes or guarantees.

Proof: 64 focused insurance-math assertions pass. Full suite: 3,257 assertions passed,
zero failures and zero errored files; git diff --check passed. Offline only, no agents.
Sizing assumptions and numeric validation for the other insurance calculations remain
open; the full plugin and transcript audit is still incomplete.

### Insurance numeric boundaries and explicit expense inputs (2026-09-28)

Completed verification of the preceding validation changes: the existing runner handle
reported successful completion, with 3,274 assertions passing. Sixteen regression cases
had shown successful recommendations from negative amounts/ages, fractional household
counts, boolean numeric inputs, invalid fractions, nonfinite inputs or computed overflow.
The calculations now share numeric validation, reject supplied negatives instead of
clamping them to zero, and require integral counts and at least one insured person.
The public adapter checks finite JSON output. An unsolved continuation IRR now returns
ok:false with its gap while retaining the cash-flow evidence (another reproduced defect).
These validations do not endorse the existing sizing methodology.

Read the insurance workflow plus shared and term references in full. The term function
silently invented annual expenses as 45% of income. A new regression reproduced that
behavior; positive support horizons now require an explicit expense figure. Missing
expenses with no runway remain null, while explicit zero remains valid. Workflow/reference
and handoff instructions now forbid bypassing the gap by zeroing the support horizon.
The old default assertion now tests the same arithmetic with a supplied figure.

Proof: 83 insurance-math assertions pass; final full suite: 3,276 passed, zero failed,
zero errored files. git diff --check passed. Coverage ledger updated for files read;
no live source requests or subagents. Remaining substantive issues include default income
multiples, health-cover sizing methodology, >5-year vehicle IDV, unsourced categorical
insurance claims, and the wider incomplete plugin/transcript audit.

### Vehicle IDV outside the age schedule (2026-09-28)

Read the vehicle reference, personal MCP declaration and insurance CLI adapter in full.
Verified the relevant rule against New India's published private-car policy (pages 2–3),
linked with retrieval date in the vehicle reference. The implementation's automatic
50% retention beyond five years was unsupported. Two regression assertions reproduced
that invented check and the absence of a discontinued-model input.

The source-backed correction now returns null IDV bounds/status plus idv_gap for cases
outside the age schedule; the envelope propagates the gap while preserving the independent
NCB calculation. Exactly five years remains covered by the existing schedule. Workflow,
reference and contracts explicitly distinguish an unknown check from approval. The
screening tolerance is identified as an assumption. No additional dependency or network
path was introduced; browsing here was developer research on an approved insurer source.

Proof: 86 focused insurance assertions pass; full suite reports 3,279 passed, zero failed,
zero errored files. git diff --check passed. No subagents used. Remaining vehicle review:
price-input basis, NCB entitlement assumptions, add-on generalisations and legal/PA claims.
Insurance health/term methodology and the broader audit remain incomplete.

### Health sizing: explicit scenarios replace hidden recommendations (2026-09-28)

Read the health reference in full and traced every result-field consumer. The old model
converted city/family/age buckets into a cover recommendation, applied an unexplained
half-weight to employer cover, and produced a fixed large top-up without a deductible
input. These assumptions contradicted the tool's stated role as arithmetic on supplied
figures. Replaced that model with explicit base/total targets, deductible and separate
personal/employer amounts. Targets are labelled scenarios requiring an explained basis.
The result exposes current and planned deductible gaps and a top-up target; it does not
claim policy eligibility, combine reimbursements or recommend an additional purchase.

Verified deductible versus top-up sum-insured semantics against HDFC ERGO's product FAQ,
linked with retrieval date in the reference. No universal household sizing amounts were
inferred from that source. Updated producer/result contract, MCP description, workflow,
health reference and CLI example together. This is an intentional input/result migration:
old demographic-only calls fail with a gap; no compatibility wrapper recreates the old
unsupported assumptions. Examples that merely asserted the hardcoded policy were removed
and replaced by scenario arithmetic, invalid-input and legacy-rejection tests.

Five new assertions failed before the refactor. Focused insurance suite: 85 passed.
Full suite: 3,278 passed, zero failures, zero errored files. Count falls by one because
obsolete implementation-mirroring assertions were replaced. New CLI example executed
successfully with synthetic amounts. git diff --check passed. No subagents or personal
account activity. Remaining insurance work includes term multiplier defaults, scoring
and legal/reference claims, NCB assumptions and vehicle price basis; wider audit ongoing.

### Term scenarios require explicit inputs (2026-09-28)

Following the health-model refactor, traced all term-cover callers. Seven missing-input
regressions showed that the engine supplied a 12x multiplier and silently converted
unknown liabilities, goals, corpus and existing cover to zero. All eight term inputs are
now required. A null expense figure is permitted only with a zero support horizon; the
existing positive-horizon validation remains. Arithmetic/output structure is retained,
while the caller must explain the scenario rather than inherit an invisible recommendation.

Updated the personal MCP description, workflow, shared/term references, CLI and tests.
Removed the reference's automatic education/bonus/expense substitutions and categorical
income-multiple/retirement defaults. Current facts remain gaps when unknown; forward
assumptions require a rationale. Tests use an explicitly complete synthetic household so
numeric validation checks still exercise their intended fields, not just missing-key errors.

Proof: 93 focused insurance assertions pass; full suite 3,286 passed, zero failed,
zero errored files. The updated CLI example executed successfully on synthetic data.
git diff --check passed. No subagents or live research needed for this input-contract
change. Insurance scoring/legal/reference claims, NCB/default hurdle assumptions, vehicle
price basis and broader plugin/transcript review remain open.

### Insurance CLI trust boundary and missing hurdle (2026-09-28)

Subprocess tests reproduced malformed JSON tracebacks, non-object input reaching the
calculator, duplicate keys silently selecting the last financial input, and nonstandard
nonfinite JSON values. The thin CLI now uses argparse's typed-input boundary with the
standard JSON hooks: malformed/ambiguous inputs return a concise usage error (exit 2)
and no result. Numeric overflow during JSON decoding is rejected too. Valid requests
continue to delegate once to the shared calculation library; no second math path.

A separate failing regression proved that a missing hurdle supplied an implicit 7%
benchmark and emitted a comparison verdict. The continuation result now preserves the
computed IRR/cash flows but leaves the hurdle/comparison null with a gap when no hurdle
was supplied. Explicit comparisons remain supported. Updated the workflow, MCP description
and contract; removed the workflow's automatic surrender instruction based on IRR alone.

Proof: 101 focused insurance assertions pass, including real subprocess CLI calls.
Full suite: 3,294 passed, zero failed, zero errored files. git diff --check passed.
Coverage ledger marks the CLI review/fix complete; remaining insurance and wider audit
scope is unchanged. No live fetches or subagents used for this work.

### Missing NCB evidence and coverage checkpoint (2026-09-28)

Closed the pending missing-NCB-default defect: three regression assertions showed absent
claim history/quoted bonus turning into a passing check. Vehicle results now preserve
unknown NCB status with ncb_gap while retaining independently available IDV and schedule
results. Explicit zero remains valid. Contract/workflow aligned; 105 focused insurance
assertions and git diff --check pass. Full-suite verification is deferred to the next
integration batch; the last full run was 3,294 passing assertions before this change.

User requested remaining scope. The current ledger contains 221 files: 84 pending and
137 with some recorded work (many still partial). Transcript review and final integration
remain incomplete. These counts measure recorded coverage, not completion percentage.
Acknowledged that overly incremental fixes and repeated full-suite runs slowed coverage;
remaining work should proceed in coherent domain passes with batched integration checks.

### Market-context missing-evidence pass (2026-09-28)

Read the complete shared context implementation and its tests, traced the strategy regime consumer, and reproduced twelve failures before fixing them. Missing VIX no longer becomes normal volatility; missing/invalid breadth cannot authorize risk-on. Incomplete sector coverage withholds the frozen gate percentage and exposes coverage counts while retaining individual observations and upstream gaps. Invalid close series no longer silently lose observations before EMA calculations. Missing Nifty evidence no longer acquires today’s date. Relative valuation with missing history no longer claims similar pricing. One index snapshot now serves cap valuation and sector ranking; valuation-history gaps are forwarded. Updated the handoff contract.

Proof: `python3 finance/tests/test_context.py` — 87 passed, 0 failed. Broader verification deferred until the domain pass is complete. Context cache validation, atomic persistence, valuation numeric validation/methodology, component observation dates and transition-history filtering remain open; this is not a complete domain sign-off.

### Market-context artifact lifecycle (2026-09-28)

Replaced unconditional JSON reuse with implementation-version, generation-date, request-window, shape, enum, observation-date and finite-JSON checks. Atomic temporary-file replacement preserves the previous snapshot on failed publication. Thread/process locks serialize quick cache lookup and computation; failed storage returns evidence with a labelled gap. Custom output no longer suppresses canonical publication and is honored for cache hits. Prior-reading selection filters filenames and records before limiting, excluding today/future entries. Pure valuation classifiers reject invalid numeric inputs; outlier explanations now identify the statistical heuristic without inventing an earnings-collapse cause.

Focused cache proofs cover incompatible snapshots, interrupted replacement/cleanup, nonfinite write rejection, four simultaneous callers computing once, history-window changes, custom-output reuse and read-only storage degradation. Context-domain numeric/date alignment and upstream valuation normalization remain to finish; full suite deferred to the completed domain pass.

### Market-analysis skill and report contract (2026-09-28)

Read the entire skill, reference and Markdown template, plus the valuation-source path and alert producer. Fixed instructions that would overwrite the full canonical context with a text digest. Replaced invalid `{from,to}` alert trigger with the actual flattened `check` API, carrying transition evidence in the text and excluding missing-evidence fallbacks from genuine regime alerts. Verified the documented alert call in temporary storage. Clarified compatible quick reuse and the actual deep/raw-tool distinction. Rewrote unsupported sample figures and causal/allocation assertions as explicit methodology limits; corrected the false claim that P/E and earnings-yield ranks have the same direction. Template now distinguishes missing values, sector coverage and component dates.

The generic system skill validator rejects the pre-existing Claude `argument-hint` metadata; retained client compatibility and directly verified YAML parsing/name/description instead. No live financial sources, broker state or messages were used. Coverage ledger updated for all five context/skill files. Valuation source normalization and date alignment remain open.

### Valuation history sampling integrity (2026-09-28)

Read the full market-source test file and traced archive sampling to context percentiles. Six regression failures demonstrated double-weighted holiday fallback observations, swallowed fetch gaps, absent coverage metadata, future-relative observation dates and infinite-value percentile contamination. Fixed these in the source/ranking owners. History now validates the observation window, normalizes numeric metrics, preserves partial-fetch gaps and exposes unique sample count plus actual date range. Forced refreshes now consume the snapshot-request budget even when files exist; the documented budget unit is a snapshot request, not individual holiday fallback HTTP attempts. Raw valuation percentiles propagate live-source gaps and require at least one computed rank for success. Context carries coverage metadata into the saved artifact and digest.

Validation: market source 197 assertions passed; context 105 assertions passed before the additive coverage-digest change, rerun below. Archive CSV date/identity verification, snapshot-cache validation and full source-module review remain open.

### Archive observation identity and permanent caches (2026-09-28)

Three failing regressions confirmed that CSV row dates were ignored, future-dated permanent caches were trusted, and future requests reached transport. Archive parsing now requires each named row to match the requested session and rejects duplicate canonical index identities. Snapshot cache reuse requires the validated format version, numeric structure and an actual date inside the requested fallback window. Legacy unvalidated entries are refetched. Atomic cache replacement prevents partial publication. Invalid/future dates and invalid fallback windows fail before network access. The fixture server now generates matching row dates for each URL rather than disguising one fixed session as a full history.

Market-source focused run after the main change: 200 passed; final duplicate-identity regression added and rerun. No live network calls. Source-module remainder still pending; coverage ledger records partial review rather than completion.

### Live market flow integrity and cache consolidation (2026-09-28)

Read the remainder of `sources/market.py`. Flow parsing had classified every non-FII category as DII and attached the last row’s date to mixed-session figures. It now recognizes categories explicitly, validates dates and buy/sell/net arithmetic, selects one session, withholds duplicate category/session evidence and reports missing counterpart data. Changed flow cache namespace prevents old permissive snapshots from bypassing validation. Malformed live-index row-list payloads now degrade through the envelope. Removed the duplicated non-atomic daily cache implementation in favor of `spine.read_cache`/`write_cache`, preserving existing date-stamp semantics.

Proof: 209 market-source checks and 105 context checks passed; diff whitespace check clean. Remaining source findings: breadth numeric/identity coverage and hidden market-cap floor, macro window labels/source gaps, live-index duplicate identity and date metadata, and archive snapshot request-budget/cache interaction. Full source sign-off remains pending.

### Breadth coverage and macro windows (2026-09-28)

Removed the hidden fixed-rupee breadth floor, validated universe input before path/transport, excluded duplicate stock identities and invalid/nonpositive price inputs, and exposed requested coverage plus each metric’s own denominator. Context retains counts and the report template no longer applies a total-universe denominator to a partially priced metric. Macro preserves source gaps, validates/sorts unique dated finite observations, withholds 1M changes without the 22-close sample and positive base, and supplies the base date plus actual history coverage. Non-5y requests no longer fill the legacy five-year percentile field; the generic rank carries the requested period. Hash-based macro cache keys avoid path interpolation. Validated cache namespaces bypass old permissive results.

Proof: 219 market-source assertions and 105 context assertions passed. Remaining domain concerns include live-index duplicate/date normalization, cross-component freshness, extreme arithmetic, archive request-budget/cache validation interaction and consolidated integration checks; no full-domain completion claimed.

### Live-index identity and cross-session gates (2026-09-28)

Live-index parsing now withholds duplicate canonical identities, converts invalid nonpositive price/multiple values to gaps/nulls and preserves the supplied observation timestamp. Filtering returns failure for missing requested indices, accepts one string as one name and leaves the original snapshot intact. New cache namespace excludes older permissive snapshots. VIX and sector histories carry observation dates and cannot pass market-context gates if their sessions differ from Nifty; mixed sector sessions are also withheld. Context format version advanced so earlier same-day artifacts cannot bypass the new rules.

Focused proof: 224 market-source assertions and 107 context assertions passed. Started broader integration verification in `/tmp/ef-market-domain-suite.txt`. Source timestamps remain raw provenance when supplied; this is not exchange-calendar certification of the latest completed session.

### Allocation input and concentration review (2026-09-29)

Read allocation engine, all existing tests, and its CLI in full. Six regressions demonstrated invalid negative/nonfinite/over-total breakdown acceptance, category normalization loss and per-row single-stock testing that missed combined cross-account exposure. Fixed breakdown validation and alias summation, combined same-ticker holdings before concentration checks, and removed substring matching from the small/micro bucket selector. Negative positions are unsupported by the long-only allocation model and now appear as excluded-value gaps instead of shrinking the denominator. CLI handles validation/I/O errors with nonzero status and emits strict finite JSON on success.

Proof: 51 allocation and 55 holdings checks passed. Remaining allocation review: threshold/target validation, missing-value implications for action wording, tag provenance and coverage, precision in rebalancing moves, and realistic CLI error checks. No completion claim for the allocation domain.

### Allocation targets and incomplete-book actions (2026-09-29)

Nine regressions exposed invalid target sums, incomplete-book rebalancing instructions and rounded-percentage rupee errors. Targets now normalize unique asset names and require a finite nonnegative 100% split; concentration thresholds validate recognized keys and percentage bounds. Rebalancing requires every supplied holding to be valued and its asset class known; incomplete coverage retains descriptive splits but nulls move amounts and emits no rebalance instructions. Partial-book concentration flags now ask for review rather than prescribe trims. Complete-book moves use exact category values. Actual CLI subprocess checks cover invalid-target rejection with structured stderr and no partial report.

Focused allocation checks: rerun after all changes; broader suite was last 3363/0 before allocation changes. Remaining allocation concerns include report-side provenance and default-threshold methodology, cross-broker alias identity, and broader integration.

### Portfolio-review instruction and denominator pass (2026-09-29)

Read the full portfolio skill/reference and verified its directory inventory (no report asset exists). Fixed unconditional time-stop and corporate-action cost-adjustment instructions, inconsistent reporting-basis switching, direct XIRR/category-return comparisons, undocumented fund escalation bound, compact market-return field assumptions and invalid alert producer schema. Removed automatic valuation-driven portfolio-limit changes and age-based targets; reference now separates heuristics from findings and fixed-total moves from fresh-inflow scenarios. Documented preservation of withheld allocation actions. Corrected AMC concentration to use its documented fund-sleeve denominator and explicitly label it; whole-book allocation percentages remain distinct.

Allocation proof: 65 assertions passed including stock-heavy-book AMC concentration. Skills/reference final integration remains pending; this pass used no live financial/account actions.

### Wealth missing-evidence health gates (2026-09-29)

Read the complete wealth engine, skill, reference and CLI; inspected the existing wealth tests. Seven failing regressions demonstrated invalid emergency balances/expenses, recurring-expense-floor overconfidence, gap-only investment “strong” scores and empty-allocation diversification claims. These are now not assessed. Recurring-only runway retains a labelled upper bound rather than an assessed month count; confirmed severe investment findings remain reportable despite other missing evidence. Wealth orchestration instructions now explicitly honor sequential/no-agent preferences and each mode’s actual artifact scope.

Proof: 91 wealth assertions passed. Major wealth findings still open: mixed-fund equity classification, cash/FD liquidity eligibility, snapshot/breakdown reconciliation and liabilities, weighted-XIRR presentation, age-based automatic risk advice, and scorecard coverage propagation. Full wealth review remains incomplete.

### Explicit wealth allocation targets (2026-09-29)

Removed the automatic 100-minus-age/default-70 equity ceiling and its can-add-risk recommendation. Risk posture accepts a stated `profile.equity_band` with valid percentage bounds; absent/invalid bands yield unknown. Weak or unassessed foundations now take precedence even when exposure exceeds a target. Comparisons use descriptive above/within/below-target labels and create a review action, not permission to add growth assets. Updated every located label consumer in contracts, skill, reference and the fully read Markdown report template. Legacy direct function age arguments remain accepted but do not supply targets.

Proof: 99 wealth checks passed including four ages with no stated range, invalid bounds and foundation precedence. Equity-exposure composition and net-worth/liquidity reconciliation remain separate unresolved inputs to this comparison.

### Wealth equity-composition integrity (2026-09-29)

Seven failing regressions exposed all-funds-as-equity and crypto-as-equity arithmetic plus short substring aliases that classified unrelated labels. Fund wrappers are now recognized before direct equity/debt/international labels, and category matching uses word boundaries with explicit plural/stem handling. Known Indian/US direct-equity exposure remains visible separately; unresolved fund, other, retirement and insurance composition prevents a false total-equity verdict. Tradeable-only books also cannot establish whole-net-worth equity share. Updated the contract and report language to preserve that distinction.

Proof: 107 wealth assertions passed, including corrected old expectations that had encoded the all-funds-as-equity error. Sourced fund look-through reconciliation into the whole net-worth spine remains an open capability requirement, alongside liabilities and liquidity validation; withholding the unsupported number is an interim integrity fix, not completion of the wealth domain.

### Wealth breakdown reconciliation (2026-09-29)

Six failing regressions showed silent invalid-asset exclusion, complete status despite unequal snapshot/breakdown totals, false diversification, substitution for a reported zero denominator, negative allocation percentages and unseen liquid balances interpreted as zero. Invalid rows and reconciliation mismatches now produce incomplete coverage with explicit gaps; allocation_total retains the observed asset sum without fabricating a liability adjustment. Nonpositive net worth withholds percentage calculations. observed_liquid retains the known subtotal, while incomplete coverage withholds liquid/assessed emergency runway and net-worth scoring. Contract and report coverage labels migrated together.

Proof: 113 wealth assertions passed. Actual liability schema, asset encumbrance/FD withdrawal eligibility, nested payload handling and dates remain to audit; matching sums alone cannot establish economic liquidity.

### Holding XIRR summary semantics (2026-09-29)

The wealth engine’s weighted holding-XIRR mean was insufficiently distinguished from portfolio return and could crash on mixed string/numeric rates. Rates now normalize through the shared numeric parser, invalid/boolean entries are omitted with named gaps, weights use only positive current values, and normalization avoids unnecessary value-times-rate overflow. Summary exposes weighted_count, the explicit descriptive method, and null portfolio_xirr; report/skill/contract prohibit promoting this statistic into a book return. Malformed position collection rows are handled once before consumers.

Proof: 117 wealth checks passed, including mixed percentage-string/numeric rates, invalid values, weighting coverage and portfolio-return semantics. Full dated-cashflow portfolio XIRR computation remains outside this descriptive summary; first-party portfolio return still needs separate attribution. Other wealth-domain tasks remain open.

### Emergency reserve availability (2026-09-29)

Removed the assumption that all cash/FD market value is emergency-eligible. The existing observed subtotal remains visible, while assessed liquid value now comes from a dated, sourced profile.emergency_reserve balance confirmed as accessible. The skill explicitly reconciles encumbrances, restrictions, commitments and withdrawal costs before supplying it. Source/date travel into report data; missing/invalid/future evidence is a gap, and explicit zero is distinguished from unknown. A confirmed reserve can be assessed independently of an incomplete asset book. Removed the automatic FD/sweep placement instruction from the action plan.

Proof: 123 wealth assertions passed, including absent/malformed/future/negative evidence and explicit zero. Reserve recency remains visible rather than silently certified as current. Liability integration, complete exposure reconciliation and remaining CLI/scorecard edges remain open.

### Wealth scorecard coverage and CLI errors (2026-09-29)

Runway status now uses unrounded values, preventing 5.96/2.96/0.96-month readings from crossing 6/3/1-month gates through display rounding. Invalid savings rates and cashflow gaps withhold reassuring scores; unresolved policy red flags prevent strong-protection certification while known adverse findings remain reportable. Overall scores expose assessed/total domain counts and completeness. Wealth CLI validates object-shaped input blocks and returns structured errors without partial JSON output. Updated the report template, contracts and coverage ledger for all wealth files read.

Focused proof: 132 wealth checks passed, including actual CLI subprocess rejection. Full integration suite running in `/tmp/ef-wealth-pass-suite.txt`; liability/exposure integration and render-template review remain open.

### Explicit liability evidence and net-worth reconciliation (2026-09-29)

Repository/schema discovery found no verified broker liability payload contract. Added an explicit canonical picture.liabilities total/date/source handoff instead of guessing vendor fields. Shared dated-amount validation now serves liabilities and accessible reserve evidence. The engine subtracts supplied debt once, checks reported net worth against the result, or calculates net when absent. Leveraged asset composition uses gross assets and declares allocation_basis, preventing >100% sleeve percentages caused by dividing assets by net worth. Without snapshot or liability evidence, an asset subtotal is marked incomplete. Skill, report and contracts preserve denominator/evidence distinctions.

Six new focused cases cover exact reconciliation, gross denominator, computed net, inconsistent net, missing debt evidence and malformed debt provenance. Fund-exposure reconciliation, stale/mixed observation dates and remaining render integration remain open.

### Wealth HTML projection and fixture review (2026-09-29)

Read the full wealth HTML template/sample projection and renderer. Missing runway previously caused template arithmetic failure; zero caps divided by zero, long runway markers escaped the chart, and target labels ignored supplied limits. Moved the gauge into the existing chart-helper owner with finite-input validation, explicit gap rendering, dynamic scale/labels and accessible description. Removed unescaped disclaimer HTML. Revised the synthetic sample to avoid all-funds-as-equity, weighted-XIRR-as-book-return, connection-as-completeness, automatic insurance amounts and statuses inconsistent with engine bands. Fixture remains explicitly synthetic.

Renderer regressions cover missing/invalid/long runway, supplied target labels and escaped disclaimer data. Full visual layout inspection and the remaining chart/template/security audit remain open; these rendering checks alone do not establish pixel-level quality.

### Report prose boundary and partial-allocation charts (2026-09-29)

Found direct safe-markup bypasses in authored daily-brief prose and deck disclaimers. Added one standard-library HTMLParser formatter in the renderer: preserves basic emphasis/code/breaks and HTTP(S) source links, discards executable tags/event/style attributes and unsafe link schemes. Templates now use that formatter for these prose fields. Chart-generated markup and bundled runtime remain distinct. Stacked allocation bars no longer renormalize partial samples to fill 100%; an explicit unclassified segment retains coverage. Invalid/over-total percentages yield gaps, segment padding stays within its width, and palette colors are constrained rather than interpolated into unsafe attributes.

Proof: 99 renderer checks passed covering chart coverage, invalid numbers, attribute injection, active prose markup and retained source hyperlinks. This is not a full renderer security or visual sign-off: other chart parameters and template data attributes remain in the audit queue.

### Atomic report publication and projection validation (2026-09-29)

Renderer now rejects non-object projections, duplicate keys, nonfinite literals and overflowing float literals before rendering. Template selection accepts bundled-style names only, and output cannot resolve to the input JSON. HTML is written to a sibling temporary file, flushed, and atomically replaced; failed replacement preserves the previous report and cleans the temporary file. CLI reports expected validation/storage/template errors as structured nonzero failures.

Proof: 106 renderer assertions passed, including simulated publication failure, prior-report preservation/cleanup, duplicate/nonfinite/root-shape rejection and source-overwrite prevention. Existing template tests render every bundled sample. Visual QA and remaining charts/template attribute review still pending.


### Chart continuity and actual browser evidence (2026-09-29)

The previous status turn yielded new evidence: the first browser process was terminal with a sandbox launch failure. Retried the local offline browser check with escalation; Chrome completed all five sample pages with no page errors. Wealth, fund and sector sample sections fit their slide boxes; deep-analysis slides 7 and 12 exceed their 1620px boxes (1673px and 1672px respectively). Viewed the wealth screenshot. This is not a visual sign-off: deep-analysis clipping and full disclosure/print/viewport checks remain outstanding. Daily brief is not a deck and requires its own measurement selector. Browser evidence is in /tmp/ef-visual-audit/measurements.json and wealth.png (temporary diagnostic artifacts).

Read the complete chart helper file. Line charts previously joined observations across None gaps, and the technical chart crashed when the last close was missing. Both now use the same contiguous-run renderer. A missing latest close gets no current-price marker or label; empty/misaligned/nonfinite series produce a labelled gap. Line colors use a constrained palette syntax and line widths are validated, preventing raw SVG attribute injection from these fields. Technical marker now sits at the actual x-coordinate rather than an arbitrary four-unit offset.

Proof: reproduced the missing-close TypeError and continuity failure before the fix; all 112 renderer assertions now pass. Other chart families still require validation and proportionality fixes; full runtime and template audit remains open.


### Report overflow and keyboard/print integration (2026-09-29)

The fixed-height deck runtime hid overflowing evidence on screen and applied the same clipping plus size containment during print. Long sections now scroll on screen, while print uses natural section height (at least one design page) and allows continuation pages. Up/down, paging, Home/End scroll an overflowing section; left/right continue navigating. Native Space/Enter activation of focused disclosures and buttons is no longer intercepted by slide navigation.

Replaced the old fallback-font, detached-section layout check (which silently skipped browser failures and did not exercise the runtime) with an explicit browser integration gate. Run the renderer test with EF_REPORT_BROWSER_CHECK=1, EF_REPORT_NODE pointing to Node if necessary, and NODE_PATH pointing to an installed Playwright module. A requested browser check fails on unavailable runtime/launch errors. check_report_layout.cjs blocks HTTP(S), renders all five sample types, injects long content, verifies scrolling/navigation/disclosure activation, verifies print section geometry, and checks the brief at phone width.

Proof: 113 renderer assertions passed with actual Chrome integration enabled. Separately generated the deep-analysis sample PDF: 17 pages, and extracted text confirms both the previously clipped integrity footer and full debate conclusion survive. Continuation pages are an intentional tradeoff for preserving variable-length evidence; this does not certify all report content, chart security or visual design. Full copied deck runtime review remains open.


### Budget recurrence and merchant matching (2026-09-29)

Read both budget scripts, both test files, skill, reference and the relevant contract. Reproduced substring merchant false positives (e.g. PUBLIC containing LIC), future-transaction lookahead in historical recurrence, single-charge costs promoted to a monthly obligation, median-only cadence falsely certifying irregular charges, and a malformed-date crash.

Taxonomy/exclusion/ATM matches now require narration token boundaries. Recurrence excludes and labels malformed or post-as-of debit rows, separates accounts, excludes card settlements/investments/ATM withdrawals, and requires every interval to agree with the cadence band. Single familiar-merchant charges remain low-confidence candidates with null cadence/monthly cost; they do not inflate the observed recurring total. Skill/reference/contract migrated together, preserving the old total field name with explicit observed-pattern semantics. Imports must be deduplicated by source transaction identity upstream.

Focused proof: 22 categorizer + 28 recurring checks pass. Broader suite launched in /tmp/ef-report-budget-suite.txt. Budget audit is partial: durable-map corruption/atomicity/concurrency, categorizer numeric validation, refunds/ATM cashflow semantics, ambiguous merchant identity, unsupported target claims and dashboard integration remain.

Integration result: `./bin/test.sh` completed successfully — **3481 assertions passed, 0 failed, 0 files errored**. Browser checks were separately enabled and passed (113 renderer assertions); the default suite explicitly reports that optional gate as not requested.


### Durable budget corrections and shared statement validation (2026-09-29)

Reproduced silent corrupt-map replacement and lost-update risk. Read-only categorization now reports invalid/unreadable maps and uses taxonomy without altering the file; learning refuses to overwrite state it cannot validate. Duplicate JSON keys, invalid categories and malformed key shapes are rejected. Atomic sibling-file publication preserves the old file on failure, and the correction CLI holds a thread/process lock over the whole load/update/save operation. Explicit corrections now also precede exclusion heuristics, matching the documented map-first contract.

Both budget scripts use one normalized-transaction validator in the existing categorizer owner. Invalid dates, directions, descriptions or amounts generate indexed gaps instead of fabricated zeroes/nonfinite totals or uncaught crashes. Outputs use strict JSON, atomic publication and input-overwrite guards. No new storage service or alternate artifact owner was introduced.

Read the budget dashboard. Corrected hardcoded green bucket gauges, unsupported recurring-commitment labels, missing gap display and unknown savings-rate presentation. Skill/reference now explain escaping, status classes and numeric style bounds. Removed assumed private-workbook existence/contents and an unsupported universal lender ceiling; framework bands are explicitly optional comparisons. Income reconciliation distinguishes refunds, transfers, borrowing and ATM cash from income/final spending.

Proof: 35 categorizer and 28 recurring assertions pass. Tests include eight concurrent correction subprocesses retaining all rules, simulated replace failure preserving prior state and cleaning temporary files, damaged-map refusal, explicit read degradation, schema rejection and input-file preservation. Last broad suite remains 3481 assertions from before this batch; rendered budget dashboard and remaining integration items are not yet signed off.


### Seed library review and retired unapproved screening source (2026-09-29)

Read every seed and its README, the saved-screen implementation/tests and its callers. Found a direct conflict with AGENTS.md: screener.in is approved for document discovery only, yet saved screens supplied decision candidates. Retired the fetch/cache/parser implementation, retaining a small compatibility endpoint that always returns a source-policy gap and no candidates. Investment-spec validation rejects unsupported providers before any fetch and requires a universe. Removed the bundled community saved-screen seed; skills, contracts, MCP description and example spec now explain explicit re-authoring without silently substituting different criteria. A compatibility smoke case remains, using a non-network placeholder URL.

The 13 remaining seeds are all draft, with null validation dates and consistent names. Investment specs pass structural completeness only. Added positive P/E bounds to the profitable/value and GARP screens so upper bounds alone cannot admit negative earnings multiples. Removed stale active/match-count annotations and corrected capital-protection claims in the large-cap fund seed. Rewrote the seed guide to distinguish coarse screens from exact entry rules, daily index context from true weekly confirmation, and SMA-provider filters from EMA-based local rules. None of these idea templates has been activated or performance-certified.

Proof: 7 retired-provider checks + 31 stock-scan checks pass, including no-network/no-cache refusal and rejection before injected fetches. Seed YAML/lifecycle/structural checks passed for all 13 retained files. The first broad run identified missing smoke coverage for the retained compatibility endpoint; restored its explicit no-fetch smoke case and the plugin contract test now passes all 255 assertions. Broad rerun is in /tmp/ef-source-policy-suite.txt. The remaining core strategy audit must examine activation safeguards against validating coarse proxies as exact prose setups.

Broad rerun completed: 3492 assertions passed, 0 failed, 0 file(s) errored.


### Explicit entry invariant across live and historical execution (2026-09-29)

Reproduced that a prose-only or empty entry silently inherited coarse compute filters, so a live screen/backtest could act on a different setup than the described strategy. Removed that fallback at the shared strategy owner. entry.signal must be a nonempty machine expression/list; missing or empty signals produce a labelled failure before prices/universe fetches. Updated the synthetic live-screen self-test to state the exact rules it already exercised instead of claiming a candle setup. Contracts, generation guidance, example spec and seed guide describe the deliberate migration: author the intended entry and revalidate, never copy coarse conditions automatically.

Also corrected the discovery/provider fallback wording: local rules are not proven equivalent to TradingView filters. Proof: six new live/backtest rejection assertions reproduced failures first, then passed; 153 screen checks and 174 backtest checks pass. Full suite: **3498 assertions passed, 0 failed, 0 files errored** (/tmp/ef-explicit-entry-suite.txt).

Read the alert CLI, empty test-package marker and both broker integration helpers. The CLI delegates correctly to the validated alert owner. Broker helper review found follow-up work around startup-failure cleanup, state concurrency and restricting browser-stub navigation to loopback; these remain explicitly partial in the coverage ledger.


### Broker integration fixture isolation and lifecycle (2026-09-30)

Fixed test-harness defects found in the full helper read. Broker startup no longer recursively deletes a caller's directory; it requires fresh test state. Spawn/port-readiness failure closes the diagnostic stream and terminates/reaps the process, escalating to kill only after a bounded wait. Session diagnostics use a bounded deque, consumed RPC responses are removed, waits use monotonic time and stopping an unstarted session is safe.

The simulated OAuth browser now accepts only explicit HTTP loopback URLs with ports and no embedded credentials, uses the no-redirect opener for both authorization and callback legs, and refuses external or chained redirects. Failed local authorization requests do not crash the worker. Concurrent fixture registrations use UUIDs instead of a racy map-length-derived ID. Clarified that this stub verifies login-sharing behavior, not PKCE/refresh-token protocol conformance; no production auth logic was replaced.

Proof: 20 new offline helper assertions plus 8 existing bridge-script assertions pass. Tests cover caller-directory preservation, spawn/startup failure cleanup and kill fallback, external initial/callback URLs, bounded response/log storage and 40 concurrent unique client registrations. Full pinned mcp-remote integration remains unverified; no live broker, account, browser login or external network was used for these tests. Last broad suite remains 3498 assertions before this helper batch.


### DCF numerical correctness and reverse-solving audit (2026-09-30)

Read the complete DCF implementation and test file. Reverse solving previously assumed an increasing response, missed endpoint roots, and returned success after exhausting iterations. It now bisects either response direction, accepts endpoint solutions, preserves solved-input precision and reports nonconvergence explicitly. Unbracketed endpoints no longer produce an unsupported cheap/expensive conclusion; the result acknowledges possible interior/multiple roots. Invalid targets, tolerances, iteration limits, current prices and risk-free rates are rejected, as are nonfinite valuation totals.

Reproduced a second defect: the WACC audit detail rounded the default-free rate before reusing it in consistency validation and scenarios, rejecting matching high-precision inputs. That computational field now retains precision. Extremely large integers now become a labelled input gap instead of escaping as OverflowError. Updated the shared contract.

Proof: regression checks failed before each fix; focused DCF suite now passes 171 assertions (/tmp/ef-dcf-precision-tests.txt). This does not certify the financial methodology: implicit assumptions, equity-model semantics, CLI persistence and optional-scenario isolation remain open. The prior status-only turn made no implementation progress; this continuation resumed from the current branch and reproduced the next defects.

Integration verification after the broker-helper and DCF changes: `./bin/test.sh` passed **3536 assertions, 0 failed, 0 files errored** (/tmp/ef-dcf-integration-suite.txt). `git diff --check` passed. Optional browser and real broker integration were not enabled in this run.


### DCF command-line publication safety (2026-09-30)

Reproduced three CLI defects: input/output aliasing destroyed the input specification, malformed JSON escaped as an uncaught exception, and direct output writes could destroy previous evidence on failure. The command now rejects canonical-path and existing-inode aliases, reports input/model/publication failures with controlled exit codes, serializes strict JSON before publication and replaces the destination only after a completed, flushed temporary write. Pending files are cleaned after failed publication. YAML parser errors are normalized at the input loader.

Proof: 178 focused DCF assertions pass (/tmp/ef-dcf-cli-tests.txt), including normal publication, same-path/symlink/hardlink rejection, malformed input, injected replace failure preserving old evidence and temporary-file cleanup. `git diff --check` passes. Latest full suite remains 3536 assertions before this isolated CLI batch. Duplicate-key input rejection and remaining methodology/optional-scenario issues are still explicitly open.


### DCF unambiguous inputs and synthetic example (2026-09-30)

Reproduced silent last-value-wins behavior in top-level and nested JSON/YAML assumptions. The model loader now rejects repeated fields, non-string YAML keys and merge-key overrides using a local SafeLoader subclass; unrelated YAML consumers are unchanged. The contract documents the deliberate rejection of overrides.

Read the full bundled DCF example. It now explicitly labels all sample numbers synthetic, distinguishes suggested evidence from actual citations, uses crore shares rather than currency for share counts, and requires explaining accounting-versus-modeled cash-flow discrepancies rather than declaring every discrepancy an error. Removed unsupported terminal-value and named-company haircut phrasing. Financial-methodology guidance remains partial, particularly the equity-model suggestion.

Proof: 185 focused DCF assertions pass (/tmp/ef-dcf-duplicates-tests.txt), including nested duplicate fields, merge overrides, non-string keys and valid YAML. The bundled synthetic example loads and computes; `git diff --check` passes. Latest broad suite remains 3536 assertions from before these CLI/parser changes.


### Equity-shaped DCF input invariants (2026-09-30)

Traced the documented equity adaptation through the calculation. The label previously suppressed margin checks but accepted operating-company margins/taxes, net debt and debt-weighted discount buildups. Those inputs contradict the existing contract that base_revenue is already after-tax earnings and the output values equity. Added validation at the responsible model/rate owners: explicit and terminal margins equal one, tax rates zero, net debt zero, and buildup financing weights wholly equity. Updated the contract, reference and example migration comments. Corrected an existing test fixture that retained a 20% FCFF terminal margin in an equity model.

Proof: six incompatible input combinations were accepted before the fix and rejected afterward; all 191 DCF assertions pass (/tmp/ef-dcf-equity-tests.txt). This is not a financial-methodology sign-off: equity output naming, scenario behavior, source provenance and model assumptions remain under review.


### Optional DCF isolation and report-consumer consistency (2026-09-30)

Reproduced that requesting reverse valuation without a current price discarded a valid base DCF; a sensitivity exception did the same. The compute owner now isolates expected model/numeric failures for each requested optional calculation. It preserves the base, emits named gaps, persists those gaps with the full result and forwards them through the MCP envelope and CLI. Invalid base inputs still reject the valuation.

Read the full DCF report template. Removed its stale instruction to translate failed reverse solving into cheap/expensive judgments, described solved roots as conditional and potentially nonunique, removed price-anchored growth-duration guidance and clarified evidence versus forecast assumptions and equity-mode labels. Remaining blended-value/MoS methodology is not signed off.

Proof: 195 focused DCF assertions pass, including missing reverse target, injected sensitivity failure, base preservation and persisted gaps. Full suite after the accumulated DCF changes: **3560 assertions passed, 0 failed, 0 files errored** (/tmp/ef-dcf-complete-batch-suite.txt). Template prose was edited after that run; `git diff --check` passes. Optional browser/live broker checks were not enabled.


### Valuation instruction consistency and price anchoring (2026-09-30)

Read the entire 207-line valuation reference and the skill entrypoint. Both instructed the analyst to extend high growth and promote it to the base case when doing so closed the gap to market price. Replaced this circular calibration with independent-evidence requirements and explicit conditional duration scenarios. Removed the reference's false interpretation of unbracketed reverse solves and its synthetic worked example presented as real business history. Corrected share-count units and the unsupported claim that an accounting-versus-FCFF discrepancy necessarily proves an input error. Engine story-grid commentary and returned note now describe conditional scenarios rather than claiming their drivers always dominate valuation.

Verification: repository plugin compatibility checks pass 255 assertions; `git diff --check` passes. The system skill quick-validator rejects the pre-existing `argument-hint` metadata, which this repository supports; preserved metadata rather than removing a working client feature. An initially mistyped test path did not run; corrected to finance/tests/test_agent_plugin.py. No independent behavioral evaluation or financial-methodology certification is claimed. Remaining reference issues include unsupported numerical anecdotes, beta/terminal assertions, lease/tax assumptions and margin-of-safety semantics.


### Rolling-return endpoint coverage (2026-09-30)

Read the complete rolling-return implementation and test file. Found that the next available observation had no lateness bound: even a century-later endpoint counted as a one-year rolling return. An existing numeric-overflow test encoded that mistake and also passed vacuously for an empty result. Corrected the numeric test to request a genuine century-long window and require one result. The shared rolling owner now excludes endpoints more than seven calendar days late, an explicit calendar tolerance documented in the contract. Fund metrics cannot award confidence solely from a long span when there are no eligible windows; shortlist flags report missing rolling coverage.

Proof: three regressions failed before the changes. Rolling tests pass 31 assertions; fund-scan tests pass 103. An existing ten-day fixture's confidence expectation was updated from low to unknown because it contains no one-year windows. `git diff --check` passes. Full fund-scan test-file review remains pending; only relevant callers/fixtures were inspected this turn. Broader source calendar alignment and partial-window coverage remain review topics.


### Fund-scan required return coverage and funnel accounting (2026-09-30)

Read the complete fund-scan test file and traced the NAV-to-ranking path. A fund with zero eligible rolling windows could still meet the composite-weight threshold using other metrics and be shortlisted for that window. Added the required-window gate before percentile ranking. Empty results now preserve the number that passed screening before NAV rejection, and explain missing inputs/coverage instead of automatically advising the user to loosen investment gates. Updated the rolling coverage contract.

Proof: three regressions failed before the fix; all 106 fund-scan assertions now pass (/tmp/ef-fund-window-tests.txt). `git diff --check` passes. The full test file is reviewed; remaining scanner issues include comparison periods, coverage differences and the justification of fixed policy thresholds. Latest broad suite remains 3560 assertions before the rolling/fund-coverage changes.


### Document reporting periods versus filing dates (2026-09-30)

Read all 513 lines of document tests and the full 376-line source. Found an existing test endorsing the largest year anywhere in a label, which lets a refiled old annual report displace a newer reporting period. The label parser now prioritizes an explicit annual-report/financial-year period, handles full and abbreviated fiscal ranges by their ending year, and treats unresolved multiple years as ambiguous. Existing fallback paths report the recency gap.

Proof: five assertions failed before the fix, including actual download selection of an old refiled report. All 120 document assertions now pass (/tmp/ef-document-period-tests.txt); `git diff --check` passes. This is not a complete trust-boundary sign-off: document publisher/redirect validation and same-year monthly/quarterly label ordering remain open.


### Look-through arithmetic and publication gate (2026-09-30)

Read the complete look-through test file and traced its aggregation/gating implementation. Existing tests correctly cover matched holding sets, but did not catch weighted products or reciprocal sums overflowing from finite inputs. Arithmetic means and harmonic multiples now scale their calculations; an unrepresentable result is unavailable rather than a confident zero/infinity. The publication gate withholds missing/nonfinite calculated values even when input coverage is complete, retaining the actual coverage and a named reason.

Proof: five numeric/gate regressions failed before the fix; 127 look-through assertions pass (/tmp/ef-lookthrough-numeric-tests.txt). Full integration run started in /tmp/ef-fund-document-integration.txt. Whole-report confidence and heuristic threshold semantics remain under review.

Integration verification for the rolling-return, fund eligibility, document-period and look-through fixes: **3575 assertions passed, 0 failed, 0 files errored** (/tmp/ef-fund-document-integration.txt). `git diff --check` passes. Optional browser/live broker gates were not enabled.


### Insurance test review and RSI reference parity (2026-09-30)

Read all insurance-math tests and the complete TA test file. Insurance fixtures explicitly supply assumptions, cover finite-output validation, single-root IRR and incomplete-policy evidence; all 105 checks pass. Legal/policy reference accuracy is separate and remains open.

TA review found an RSI postprocessor forcing 50 whenever the trailing period had no price change. This erased Wilder smoothing from preceding rises/falls and contradicted AGENTS.md's reference-engine invariant. Removed the override at the shared indicator owner; exact installed TA-Lib values now feed both live and historical consumers. Updated the flat-series expectation and added rising-to-flat/falling-to-flat regressions. The contract requires revalidation of affected RSI strategies rather than automatic activation.

Proof: all three RSI parity checks failed before the fix and all 66 TA checks pass afterward. Full integration is running in /tmp/ef-rsi-integration-suite.txt.

RSI integration verification completed: **3577 assertions passed, 0 failed, 0 files errored** (/tmp/ef-rsi-integration-suite.txt). `git diff --check` passes. Coverage ledger now has 22 pending files; partial and initial reviews still need completion. Optional browser/live broker gates were not enabled.


### Filing identity and same-day alert preservation (2026-09-30)

Read filings-watch and its full reference, then traced item and alert deduplication. Distinct disclosures could be dropped first by the source's 80-character headline prefix and again by the skill's date-only alert key. The source now deduplicates complete returned date/attachment/headline evidence and emits a stable filing_id; the skill uses that ID plus ticker. Versioned the source cache because previously discarded rows cannot be recovered by transforming an old snapshot. Corrected the instruction to manufacture a four-quarter table when coverage is missing and clarified that public ownership cannot be added to institutional subsets as retail.

Proof: four identity regressions failed before the fix; 71 filing assertions and 255 plugin compatibility assertions pass. `git diff --check` passes. Reference review remains partial: regulatory/corporate-action mechanics and unsupported ownership/pledge conclusions need primary-source verification.


### Filing request boundary and shared cache reuse (2026-09-30)

Confirmed the filings summary constructed its cache path before validating symbol/lookback inputs. It now uses the existing ticker-path validator and rejects invalid/noninteger/negative/out-of-calendar lookbacks before cache or fetch operations. Replaced direct cache writes with spine.read_cache/write_cache, preserving snapshot publication atomically and using the reserved fetch stamp. Cache reads also verify requested symbol and window.

Proof: eight invalid-request regressions failed before the fix; all 82 filing assertions pass afterward (/tmp/ef-filings-request-tests.txt), including cache reuse, failed replace preserving earlier bytes and temporary-file cleanup. The initial red test incompletely mocked corporate actions and reached that fetch path; the process completed, the missing mock was fixed and the red tests rerun offline before implementation. A sandbox process lookup was unavailable; an escalated read confirmed no test process remained and the original session returned terminal. `git diff --check` passed before the final test-only addition.


### Expanded runtime transcript inventory and orchestration portability (2026-09-30)

Reproduced the 77-file development inventory, then parsed tool records from all 145 JSONL files in the separate market-research project (2653 calls). Added docs/audit-transcript-findings.md with aggregate evidence, limitations and current disposition. Runtime logs include 12 unqualified agent failures, 19 simple no-op waits, 43 root-search command matches and eight DCF errors. Current qualified dispatch tables already address the agent-name failures; no redundant implementation was added.

Found a remaining host-specific assumption in deep-analysis: ending a turn was claimed to always cause automatic completion-driven resumption. Replaced it with the actual host's event/wait mechanism, explicit sequential adaptation when required, and output-path checks after writers finish. Corrected the claim that cache reuse guarantees identical bytes across independent fetches; legs should share exact returned evidence.

Proof: 255 plugin compatibility assertions pass (/tmp/ef-transcript-orchestration-tests.txt); `git diff --check` passes. This is aggregate tool-record coverage and targeted context review, not exhaustive narrative review or a fresh end-to-end financial run. No subagents or live broker calls were used.


### Historical DCF errors individually replayed (2026-09-30)

Traced all eight run_dcf tool failures in the market-research transcripts to two valuation-agent logs (six and two errors). All failures originated in malformed relative fields: sentence-valued historical multiples, row/map/scalar peer values, or scalar growth. Replayed every original relative block locally through the current parser: eight of eight return explicit gaps, with no exception or nonfinite JSON. Existing implementation already owns and handles these cases, so no new parser was added. Added the missing scalar-peer shape to the permanent regression cases.

Proof: 76 relative-valuation assertions pass (/tmp/ef-transcript-relval-tests.txt). A synthetic complete DCF call with scalar peers/growth preserves a valid base valuation, the relative gaps and saved evidence. Updated docs/audit-transcript-findings.md to close this replay item without claiming historical investment conclusions are correct.


### Filings evidence preservation and interpretation (2026-09-30)

The source parser still truncated headlines before the new identity/deduplication layer. Two disclosures without attachments could collapse if they differed after character 240. Two regression assertions reproduced the loss; preserve the full source headline and invalidate prior truncated caches with version 3. Report summaries can shorten display text without altering evidence. All 84 filing assertions pass (/tmp/ef-filings-headline-tests.txt).

Removed the filings skill's redundant corporate-actions call: get_filings already includes it. Reworked its reference to distinguish stake changes from investor intent or cash flows, public ownership from retail, and pledge denominators. Removed arbitrary pledge/crash and order-size rules and generic buyback support/eligibility promises. Consulted primary NSE shareholding and pledge documentation for category/denominator definitions; no decision figures were imported from web search. Current transaction-specific rules must come from the applicable disclosure, not this static reference.

Read the financial-analysis reference and special-situations checklist in full; their methodology issues remain explicitly open in the coverage ledger. Deep-analysis reference full-read state now recorded.


### Governance gate arithmetic (2026-10-11)

Read `finance/compute/governance.py`, its tests, the MCP declaration and the management-analysis reference. A FAIL here makes the management grade AVOID, so false verdicts are material. Defects: the 5%/10% MD/WTD ceiling was applied to total directors' pay (6% total with one MD was a FAIL); NaN, infinite, boolean, string and negative figures reached the comparisons, and a NaN net profit returned PASS; the fee series dropped missing years and then paired its tail with an unfiltered revenue series; a negative prior profit produced a positive "growth" percentage and missed a fee rising into a deepening loss; a fee with no benchmark series returned PASS; the loss-year reason cited central-government approval that the 2017 amendment replaced with a shareholders' special resolution.

Fix: the MD/WTD ceiling now applies only to a new optional `executive_remuneration` figure (threaded through `checks`, `run_governance_checks` and the CLI) and is reported as not checked without it; invalid inputs return NOT-CHECKED; revenue and profit series must align one-to-one with fee years; a profit fall is a direct comparison, with a percentage only on a positive base; PASS requires an aligned positive-base revenue series. Breach reasons name the special-resolution route and that reported PAT approximates s.198 net profit. Tool description and reference corrected; non-director KMP are named as outside s.197.

Proof: the new regressions failed before the fix (wrong FAIL on the MD case; `TypeError` on the new figure). Afterward 75 governance and 255 plugin compatibility assertions pass; full runner 3,621 assertions, 0 failed; `git diff --check` passes. Statutory wording was not re-fetched from a primary source in this pass.


### Fund-tool boundaries and screen completeness (2026-10-11)

`get_fund_lookthrough(workers=0|non-int)` raised from `ThreadPoolExecutor`; it now returns a labelled envelope before any fetch. Tickertape fund ids/sids and AMFI scheme codes reached request URLs unvalidated (`../stocks/info/X`, `?` queries); they are now single path segments / positive integers, rejected before cache or transport. `screen()` let NaN/text `min_aum` and invalid page limits reach `float()`/JSON. A full final page at the page cap ended pagination silently, and a partial universe after a failed later page was cached as the category; truncation is now a gap and incomplete pagination is never cached (premium-field gaps still cache). Proof: 30 funds and 7 look-through regressions failed first; 333 funds and 134 look-through assertions pass.

### One index P/E ranking method (2026-10-11)

`get_market_context` ranked P/E after excluding samples ≥3× median while `get_index_valuation_history` (also used by sector-scan) ranked the raw series, so one index could carry two P/E percentiles (fixture: 80.0 vs 66.7). `robust_pe_percentile` now lives in `sources/market.py` and serves both; the tool exposes `pe.excluded` and a gap naming the heuristic. Contract updated. 226 market and 107 context assertions pass.

### Trade revalidation, warmup and exit labels (2026-10-11)

`check_trade` read only the latest bar, so a stop pierced on any earlier post-fill session and then recovered returned HOLD. Every full session after the fill is now scanned and the first breaching session is named; the fill session and unknown-fill cases keep the close-only rule. Nominal plan levels are now compared with unadjusted bars (`adjusted=False`); MA conditions use the adjusted series and go to manual review if it does not end on the decision bar. Trade-tracker skill/reference and contracts updated. Four regressions failed first; 73 pass.

`floor_stop` returned an unfloored stop on NaN ATR (`max(nan, …)`/`min(stop, nan)`), so backtest warmup bars could trade where live `build_signal` skips; it now rejects nonfinite input and the backtest skips that bar. Backtest exit labels required exact equality with SL/TP, so stops/targets gapped through at the open became TIME or SIGNAL/OTHER, distorting the exit mix the optimizer reads; long-side ≤SL / ≥TP now label correctly. 178 backtest, 153 screen assertions pass. Live broker payload validation still needs a real authenticated session and was not attempted.


### Source boundaries: shareholding, documents, transport (2026-10-11)

Shareholding assumed NSE returns newest-first and read the pledge from `out[0]`'s XBRL; rows are now sorted by their own period date. The payload-supplied XBRL URL was fetched unchecked; only HTTPS `nseindia.com` hosts are fetched. `quarters` was unvalidated — a negative value sliced from the end, and the red test reached live NSE because nothing stopped it before the fetch; it is now rejected first and the regression forbids network. Document links from the screener index were downloaded from any host; IP literals, loopback and local-network names are refused (a public host that redirects to a private address remains a residual). Documented `yf.download` as the single sanctioned exception to the one-transport rule. 98 filings and 128 documents assertions pass.

### Skill, reference and template pass (2026-10-11)

Technical-analysis computed indicators on raw candles (`get_history` defaults `adjusted=False`) while claiming parity with adjusted discover/backtest; now adjusted, with a compatibility check. Sector reference claimed 11 screened indices including Media; the screen covers the ten in `SECTOR_YF`. Sector skill's "2–3 tailwinds/headwinds" quota removed; uncovered sectors get a basket-or-gap rule. MF reference withheld below ~85% while the engine withholds below 60%, and promised an earnings-growth look-through metric that does not exist. MF skill's "raise `top` until the fund has a row" could never succeed for a gated-out fund (rejections are a tally); it now states the gate result after one call. Rolling-return "never lost money" claims scoped to observed lump-sum windows. Financial-analysis had no bank/NBFC/insurer carve-out (D/E < 1 would fail every bank), compared post-tax CFO with pre-tax EBITDA including other income, and invited a double NCI deduction; all corrected with `varsity_score` denominator and contract updated. Management scorecard template lacked NOT-CHECKED/partial PASS. Special-situations checklist made a redundant corporate-actions call. Discover's signal template still used the retired breakout/pullback taxonomy. Two unreferenced legacy templates removed. All five decks render; 113 render assertions pass including the headless-Chrome scroll/navigation/print check (Playwright via NODE_PATH). Manifests are mutually consistent.

Wealth: a tradeable-only holding with no current value was silently dropped; it is now a named gap with incomplete coverage.

### Remaining limits (2026-10-11)

Not done because they need live, authenticated or external state: broker payload validation (Kite/Upstox/IndMoney live shapes), MCP smoke test against live sources, Telegram delivery. Not changed by design: fund look-through into wealth equity share (labelled gap, not inferred). Statutory s.197 wording and Varsity thresholds were checked against sources on 2026-10-11 (see 'Live verification and content re-read'). The yfinance-versus-transport conflict is resolved at the rule: CLAUDE.md/AGENTS.md and `transport.py` now name `yf.download` as the single sanctioned exception, matching the source table's designation of yfinance as the approved Yahoo client; re-implementing Yahoo over curl would change adjusted-OHLC semantics that can only be verified live. Launch/login concurrency re-read: `ensure-mcp.py` serializes venv repair under a persistent lock and rechecks after acquiring it; `broker-login.py` keeps one kernel-locked login owner per broker URL (shared with the child via `pass_fds`), waiters never steal the callback, and a saved token execs directly. No defect found. In a development checkout that registers brokers both from the repo `.mcp.json` and the installed plugin, the duplicate bridge waits on the lock and can hit the client's 30s connect timeout while a first login is pending — expected, not a code fault.


### Final integrated review and documentation reconciliation (2026-10-11)

The earlier "every file reviewed" claim was premature: 154 ledger rows were still `traced-and-changed`, `reviewed-partial-fixes` or `traced-and-added`, and README/contracts had not been reconciled. This pass closes both.

Whole-tree checks: every module compiles; all four MCP servers import under the real SDK venv and expose 17/11/6/1 tools (README counts confirmed; the new governance parameter is in the live schema); all shell scripts pass `bash -n`; every YAML/JSON file and every SKILL/agent frontmatter parses; no debug leftovers in added lines; every tool name and repo path cited in 60 docs exists (three hits were bundle-relative `agents/` work papers, not repo paths). The full suite was run behind a recording HTTP(S) proxy — verified to capture transport's curl — and made **zero** outbound requests, substantiating README's offline claim.

Read the integrated diff of all 60 changed production files (spine, transport, paths, publication/hook/telegram, every source, every compute module, MCP servers, skill scripts, bin and hooks). Two further defects found and fixed with failing-first regressions:
- `allocation.concentration_flags` matched cap categories exactly against `("small","micro")`, so "Small Cap" — the label `caps.cap_label` itself emits — or "smallcap" silently escaped the small+micro concentration flag. It now normalises through `caps.cap_bucket`; the unused constant was removed. 67 allocation assertions pass.
- `alerts.manage` collapsed every rejection to `alert operation failed: ValueError`, hiding the validators' own explanations (e.g. a dedup key owned by another subject). Validation messages are now returned; other errors still report only their type. 60 alert assertions pass.
Also corrected a stale secrets comment in `bin/finance-mcp.sh`.

Documentation: README corrected for the SessionStart hook (date and regular hours, not live market status), `/sector-analysis` and `/mf-analysis` scope (category ranking is `discover`), deck rendering through `_report`, removed templates, module layout and the proxy-verified offline claim. CLAUDE.md/AGENTS.md (one file via symlink) layout and transport rule updated. contracts.md gained the missing `governance.py` composite-tool row and today's source boundaries.

Ledger states now: `final-reviewed` (production code diff read), `final-verified` (tests: green and offline-proven), `final-checked` (docs/assets: parse plus tool/path validation; content traced earlier), plus `reviewed`/`reviewed-fixed`/`removed`. No `pending`, `partial`, `traced-and-changed`, `reviewed-partial-fixes` or `traced-and-added` rows remain. This is a disciplined review, not a proof of a bug-free plugin; live-only checks remain as listed under Remaining limits.


### Live verification and content re-read (2026-10-11)

**Live MCP smoke test** (`finance/mcp/smoke_test.py`, real upstreams, artifacts isolated in a scratch root): first run 32 passed / 3 degraded / 0 failed. Two degradations were real defects, now fixed:
- **Negative net receivables/payables invalidated every fund book.** Live Bandhan Small Cap holdings carry a −0.72% "Net Receivables/Payables" line; the parser required 0–100%, marked the book incomplete and withheld the look-through (equity weight unknown). Non-equity lines may now be negative; equity rows must stay 0–100%. Live look-through went from DEGRADED to decision-grade (P/E 17.68 at 94.5% coverage, cap mix 80% small).
- **Sector weights were always withheld.** The live `sectorWeightage` is a per-sector dated history with stray points; the parser expected flat `latest`/`value`. Now uses the newest dated `sectorDistribution` snapshot (54 sectors summing to 100%, as of 2026-08-31) and reports `sector_weights_as_of`. Holdings cache namespace bumped to v3.
- The insurance smoke case still sent pre-explicit-input arguments; updated with synthetic complete inputs.
Spec/trade tools were exercised with a runnable seed and a synthetic trade: `run_backtest` and `check_trade` PASS live; `run_strategy_screen` ran live and returned a labelled empty result; `run_stock_scan` verified live on an investment seed (80 → 40 → 37 → 3, as-of 2026-10-09). Final run: 36 passed / 3 expected degradations / 0 failed.

**Further live-found defect:** `funds.screen` matched `subsector` case-sensitively, so all three fund seeds ("mid cap fund", "large cap fund", "flexi cap fund") screened zero funds live while "Mid Cap Fund" returned 28. Matching is now case- and whitespace-insensitive; live lowercase returns 28.

**Broker payload validation:** Kite requires an interactive OAuth login, which is the user's to perform; not attempted. Instead validated the normalizer against Kite Connect's documented holdings schema: `quantity` is the settled (T+2) quantity and `t1_quantity` is separate, so a stock bought the previous session (quantity 0) was dropped as a closed line. Held quantity is now settled + T+1 with `unsettled_qty` labelled (Kite documents no total formula; the sum is stated as the plugin's reading).

**Primary-source checks:** s.197 (compiled Act text; India Code returned 403): the 11% / 5% / 10% figures and MD/WTD scope are right, but exceeding a cap needs general-meeting approval under the provisos (plus a defaulted secured lender's prior approval), and a no/inadequate-profit year falls under Schedule V, which itself requires a special resolution. The earlier "special resolution for any breach" and "beyond Schedule V needs a special resolution" wording was corrected in code, tool description, reference and scorecard. Varsity: the financial-analysis bars (ROE/ROCE > 15%, D/E < 1, interest cover > 3, CAGR > 10%) are not Varsity's checklist (ROE > 25% / > 20% in prose, GPM > 20%, revenue/PAT CAGR > 15%, positive CFO, "not highly leveraged"); the reference now attributes them to the plugin. Sector KPI bands and insurance premium/CSR bands are labelled unsourced heuristics; the "typical endowment IRR 4–5%" and "~9 points" tax-overstatement claims were replaced with method.

**Content re-read of all 56 docs/assets** previously only parse-checked, plus automated checks that every documented `tool(param=…)` uses parameters present in the live MCP schemas and every `get_prior_run` skill key resolves. Fixes: `field-analyst` lacked `get_prior_run` though management-analysis calls it (granted, with a regression that checks each dispatched skill's prior-run needs against its agent's grant; the dual-name grant test was generalised to single-tool grants); discover's special-situations step and reference contradicted the one-call filings rule and the engine's signal-close entry; filings-watch claimed 12 quarters of Tickertape shareholding (live: six); backtesting.md still described the removed `compute_filters` fallback. Fund seeds and the DCF inputs example were run through the engine's own validators.

Proof: full suite 3,722 assertions, 0 failed; `git diff --check` clean; every new regression failed before its fix. Telegram delivery verified end to end on 2026-10-11 with the user's authorization: one plain-text test message sent through `bin/send-telegram.sh` (shared secrets loader, no credentials in arguments); Telegram acknowledged it. Kite live payload validation was declined by the user; broker handling rests on documented schemas. Upstox's published holdings schema defines `quantity` as the **total** holding (unlike Kite's settled T+2 quantity), so the shared T+1 rule would have double-counted Upstox T+1 shares; normalization is now per broker (Kite adds `t1_quantity`; Upstox keeps `quantity` and only labels the T+1 part unless `quantity` < `t1_quantity` proves exclusion), with a regression that failed first. IndMoney's official MCP (`mcp.indmoney.com`) publishes no response schema, did not connect this session, and no real `networth_holdings` result exists in the available transcripts, so its field mapping remains validated only by fixtures until an authenticated session is available.


### Live broker payloads: IndMoney and Upstox (2026-10-11)

With the user's reconnection, read-only calls were made to IndMoney (`networth_holdings` for `IND_STOCK` and `MF`, `networth_snapshot`) and Upstox (`get-holdings`). Only structure was used; tests and scratch checks use structure-faithful payloads with dummy values. Kite remained skipped by the user's choice.

**Upstox:** the live shape (`{"status","data":[…]}` with `trading_symbol`, `quantity`, `t1_quantity`, `average_price`, `last_price`, `pnl`) normalizes correctly under the per-broker T+1 rule.

**IndMoney — the live payload normalized to zero positions**, so every IndMoney path (portfolio-review, trade-tracker, daily-brief, held-fund review, wealth) saw an empty book. Causes and fixes, each with a failing-first regression:
- The response is a JSON string under `result`; the container search never decoded strings. Now decoded once (never evaluated).
- Live field names (`total_units`, `unit_price`, `total_pnl`, `investment`) were unmapped; `investment_code` is IndMoney's internal id and is kept as `instrument_code`, never a ticker.
- `networth_holdings` requires `asset_type` and serves one type per call, but every skill called it bare with one `--indmoney` file. The CLI now accepts `--indmoney` repeatedly and combines rows; trade-tracker, portfolio-review, daily-brief, mf-analysis and wealth-manager now call it per asset type.
- Stocks held through a linked broker report cost equal to current value with zero P&L — IndMoney's own `data_notes` state invested value exists only for INDmoney holdings. Such rows now carry unknown cost (`cost_basis: unreported_by_linked_broker`) instead of a fabricated zero gain, and the resolver raises a gap naming the connected broker to `--prefer` for their cost. Rows are not fuzzy-merged with the broker: IndMoney has no NSE symbol or ISIN and company names differ.
- No XIRR field exists in the live payload; skills, README and contracts that promised IndMoney XIRR (including portfolio-review's "XIRR-driven laggards") were corrected.

**Wealth spine read nothing from the live snapshot** (no total, empty allocation): the `result` envelope was not decoded, `total_networth` was not a recognised key, and per-class rows live under `investments[asset_type, current_value]`. Fixed; wealth-manager now passes the snapshot as both snapshot and breakdown and transcribes `liabilities.total` (dated, sourced) so assets − liabilities reconciles with IndMoney's net worth. `US_STOCK_WALLET` now maps to cash, not US equity. Found alongside: with no observed assets, a supplied liability produced a negative net worth equal to minus the loan; now no net worth is computed.

Proof: full suite 3,741 assertions, 0 failed; `git diff --check` clean.

### Kite live check (2026-10-12)

After the user completed the Kite authorization, read-only `get_holdings` and `get_positions` were called once (positions empty). Only structure was used; tests use structure-faithful rows with dummy values. The live shape is a bare list of rows with `tradingsymbol`, `exchange`, `isin`, `quantity`, `t1_quantity`, `realised_quantity`, `average_price`, `last_price`, `pnl`; quantities and P&L normalized correctly. Defects found, each with a failing-first regression:
- **Series-suffixed symbols** (`…-BE` trade-for-trade, `…-RR` REIT) were passed through as tickers, so quotes, filings and trade-artifact matching by NSE symbol would miss them. The base symbol is now the ticker; the raw symbol, exchange and ISIN are carried.
- **Every broker row was treated as a stock.** ETFs (ISIN `INF…`), a REIT (series RR) and a sovereign gold bond on BSE (ISIN `IN0…`) entered the equity slice that drives stock concentration and per-stock deep dives. Class now comes from those published identifiers only, and the equity slice excludes them.
- In wealth, "sovereign gold bond" matched the `bond` needle and was counted as debt; it is now gold, and government securities are debt.

Proof: full suite 3,749 assertions, 0 failed; `git diff --check` clean. All three brokers (Kite, Upstox, IndMoney) are now validated against live payloads.

### Close-out (2026-10-12)

Upstox live `get-holdings` re-read and normalized correctly. The user confirmed the audit list complete: all code, documentation, live-source and live-broker (Kite, Upstox, IndMoney) items are done. Final suite: 3,749 assertions, 0 failed. Nothing committed.
