#!/usr/bin/env bash
# Hand the actual session identity to the report producer; never infer it from cwd.
set -eu
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}}"
export PYTHONPATH="$PLUGIN_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m finance.report_hook --context
