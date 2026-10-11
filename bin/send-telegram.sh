#!/usr/bin/env bash
# Invoke only for a user-authorized send. The text stays in a local input file.
set -eu
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}}"
. "$PLUGIN_DIR/bin/load-env.sh"
ef_load_secrets "$PLUGIN_DIR" "${CLAUDE_PLUGIN_DATA:-${PLUGIN_DATA:-}}"
export PYTHONPATH="$PLUGIN_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m finance.telegram "$@"
