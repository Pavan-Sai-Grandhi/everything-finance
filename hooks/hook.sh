#!/usr/bin/env bash
# hook.sh <session|subagent|stop>. Python owns parsing and every file operation.
set -eu
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}}"
if [ "${1:-}" = stop ]; then
  . "$PLUGIN_DIR/bin/load-env.sh"
  ef_load_secrets "$PLUGIN_DIR" "${CLAUDE_PLUGIN_DATA:-${PLUGIN_DATA:-}}"
fi
export PYTHONPATH="$PLUGIN_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m finance.report.hook "$@"
