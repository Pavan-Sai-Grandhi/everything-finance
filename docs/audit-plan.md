# Plugin audit and refactor

Branch: `codex/plugin-audit-refactor`. Baseline: clean `main` at task start.

The user authorized a full file audit and implementation of substantiated fixes. The
work preserves the shared source/compute/MCP architecture and existing public behavior
except where it violates a documented invariant. No speculative features or dependencies.

1. Inventory all tracked plugin files, local design/run notes, and available project
   session transcripts. Review sources, computations, workflows, reports, and runtime
   integration in separate ownership groups; retain a coverage ledger.
2. Establish offline regression baseline. Initial runner: 2,363 assertions passed,
   zero assertion failures, one file errored because an inherited artifact environment
   variable pointed outside this checkout. Isolate test outputs before further testing.
3. Reproduce findings at the responsible layer, then fix with focused regression
   tests. Priorities: authentic missing-data handling, strategy/backtest agreement,
   financial arithmetic, cache identity/freshness, safe artifact persistence, and
   workflow contracts that prevent redundant or invented work.
4. Align documentation and producer/consumer contracts with corrected behavior.
   Keep intentional client manifests and CLI adapters; avoid deleting compatibility
   surfaces merely because they look repetitive.
5. Review integrated changes, run the full offline suite plus relevant shell/MCP
   integration checks, and document coverage, residual limits and grounded suggestions.

Live financial sources and authenticated broker/Telegram operations are not needed
for offline defect reproduction. Verification must never mutate personal positions,
send messages, or use real credentials. Synthetic fixtures are test inputs, not facts
for an investment view.
