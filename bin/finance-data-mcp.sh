#!/usr/bin/env bash
# Launcher for the local `finance-data` MCP server.
#
# Resolves an interpreter that can import the MCP SDK, then execs the server over stdio.
# Two paths, cheapest first:
#   1. the ambient python3, if it already has `mcp` — no venv, instant start;
#   2. otherwise a venv under $CLAUDE_PLUGIN_DATA (the directory Claude Code provides for
#      exactly this: installed dependencies that survive plugin updates), created once.
#
# The venv is built with --system-site-packages so it inherits the heavy scientific stack
# the plugin already needs (yfinance, pandas, TA-Lib) and installs only the SDK on top.
#
# Secrets are read from ~/.claude/.env into the environment here and never written into
# .mcp.json, never printed, and never passed on a command line where `ps` could see them.
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SERVER="$PLUGIN_ROOT/mcp_server/finance_data.py"
DATA_DIR="${CLAUDE_PLUGIN_DATA:-$PLUGIN_ROOT/.data}"
VENV="$DATA_DIR/venv"

# stdout is the MCP wire protocol — every diagnostic must go to stderr.
log() { printf '[finance-data] %s\n' "$*" >&2; }

# Optional secrets (screener.in cookies). Absent is fine: the public paths still work and
# the affected tool degrades to a labelled gap rather than failing.
if [ -f "$HOME/.claude/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$HOME/.claude/.env"
  set +a
fi

if [ ! -f "$SERVER" ]; then
  log "FATAL: server not found at $SERVER"
  exit 1
fi

PY=""
if command -v python3 >/dev/null 2>&1 && python3 -c 'import mcp' >/dev/null 2>&1; then
  PY="$(command -v python3)"
elif [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'import mcp' >/dev/null 2>&1; then
  PY="$VENV/bin/python"
else
  log "MCP SDK not found — bootstrapping a venv at $VENV (one time)"
  mkdir -p "$DATA_DIR"
  if ! python3 -m venv --system-site-packages "$VENV" >&2; then
    log "FATAL: could not create venv. Install the SDK manually: pip install 'mcp>=2,<3'"
    exit 1
  fi
  if ! "$VENV/bin/pip" install --quiet --disable-pip-version-check 'mcp>=2,<3' >&2; then
    log "FATAL: could not install the MCP SDK (offline?). Retry, or: pip install 'mcp>=2,<3'"
    exit 1
  fi
  PY="$VENV/bin/python"
  log "bootstrap complete"
fi

exec "$PY" "$SERVER"
