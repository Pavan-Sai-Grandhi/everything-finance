#!/usr/bin/env bash
# hook.sh <session|subagent|stop>. Python owns parsing and every file operation.
set -eu
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}}"
if [ "${1:-}" = stop ]; then
  . "$PLUGIN_DIR/bin/load-env.sh"
  ef_load_secrets "$PLUGIN_DIR" "${CLAUDE_PLUGIN_DATA:-${PLUGIN_DATA:-}}"
fi
export PYTHONPATH="$PLUGIN_DIR${PYTHONPATH:+:$PYTHONPATH}"
# Run from the plugin so a `finance/` in the session directory cannot shadow it; stop
# switches to the session directory its payload names.
cd "$PLUGIN_DIR"
exec python3 -m finance.report.hook "$@"
