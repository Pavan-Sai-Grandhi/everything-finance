#!/usr/bin/env bash
# Session-owned publication; JSON parsing and filesystem operations live in Python.
set -eu
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}}"
. "$PLUGIN_DIR/bin/load-env.sh"
ef_load_secrets "$PLUGIN_DIR" "${CLAUDE_PLUGIN_DATA:-${PLUGIN_DATA:-}}"
export PYTHONPATH="$PLUGIN_DIR${PYTHONPATH:+:$PYTHONPATH}"
if [ "$#" -gt 0 ]; then
  exec python3 -m finance.publication "$@"
fi
exec python3 -m finance.report_hook
