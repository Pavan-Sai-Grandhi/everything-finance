# Session-transcript audit findings

Reviewed on 2026-09-30. Historical logs are evidence of behavior under older plugin versions, not a benchmark of the refactored plugin. Counts include child-agent logs and may include unrelated work within the project. Exact repeated arguments do not by themselves establish waste. Raw personal transcripts and credentials are not copied here.

## Coverage

- Plugin-development project: 77 JSONL files, 6,028 tool calls, 92 marked errors; the previously recorded aggregate was reproduced.
- Market-research project: 145 JSONL files, 2,653 tool calls. Parsed all tool records for this inventory; this is not a claim that every narrative turn has been individually reviewed.
- Read the existing local DMART run review and checked its leads against current implementation/instructions.

## Findings and current disposition

| Observed runtime pattern | Evidence | Disposition |
|---|---|---|
| Failed unqualified agent launches | 12 failures: terminal-analyst (8), field-analyst (4) | Current dispatch tables already use qualified profile names; compatibility tests cover those tables. No duplicate fix needed. |
| No-op waiting | 19 simple filler shell calls; 10 exact repeated ScheduleWakeup calls | Updated deep-analysis to use the host's actual completion/wait mechanism, rather than assuming automatic resumption on every client. |
| Filesystem-root searching | 43 commands matched root-search patterns | Current instructions use the skill base directory and callable data tools. This count locates review candidates, not 43 individually established defects. |
| Missing output reads | 13 Read errors explicitly indicated missing files; common names included valuation and financial leg reports | Updated orchestration to use returned paths only after writers finish, with verification before rerunning a failed worker. Session-owned publication bundles already establish explicit output paths. |
| DCF call failures | 8 marked run_dcf errors | Individually traced and replayed all eight original relative blocks: each now returns labelled gaps without exceptions or nonfinite JSON. Added the previously uncovered scalar-peer shape to permanent regression coverage. A synthetic full DCF call confirms the base result and evidence file survive. |
| Broker authentication gaps | At least 6 holdings errors explicitly require login; other broker errors remain unclassified | Do not treat these as empty portfolios or automatically retry unchanged authentication. Existing graceful-degradation rules apply; no broker login was attempted during this audit. |

## Design recommendations

Keep one source owner and pass its exact evidence paths through the workflow. Use concise leg digests to route work; read the underlying report when evaluating a claim. Caching reduces work but does not guarantee independently fetched evidence is identical.

Measure future improvements on the same request, plugin version and data snapshot: successful outputs, tool calls, error/retry counts and elapsed active work. Historical aggregate counts cannot substantiate a token-cost saving. Preserve sequential execution when requested instead of launching parallel agents for efficiency.

## Remaining review

Read narrative context around remaining error clusters, classify broker errors without exposing account data, replay any additional tool-schema failures found using sanitized fixtures, and compare completed reports with their source artifacts. No exhaustive transcript sign-off or measured runtime improvement is claimed.

## DCF error replay

The eight errors occur in two historical agent logs. Six came from one valuation leg and two from another. Causes were comparisons between numeric values and strings/dictionaries, calling `.get` on a scalar growth value, and iterating a scalar peer multiple. The current relative parser handles all eight original payloads with explicit gaps. This verifies the original relative-input failure path, not the financial validity of the historical assumptions or a complete rerun of either report. The permanent relative suite passes 76 assertions after adding scalar-peer coverage.
