#!/usr/bin/env bash
# Launcher for one local finance MCP server: finance-mcp.sh <market|company|funds>
#
# Resolves an interpreter that can import the MCP SDK: the ambient python3 when it already
# has `mcp` (no venv, instant start), else a venv under the client's persistent data dir —
# $CLAUDE_PLUGIN_DATA under Claude Code, $PLUGIN_DATA under any Agent Plugins 1.0.0 client
# (both name a directory that survives plugin updates) — built once with
# --system-site-packages so it inherits the scientific stack the plugin already needs
# (yfinance, pandas, TA-Lib) and installs only the SDK on top.
#
# Secrets are read from a .env (see bin/load-env.sh for the search path) into the
# environment here, so they never land in mcp.json, in `ps` output, or in the transcript.
set -euo pipefail

SERVER_NAME="${1:-}"
# Claude Code injects CLAUDE_PLUGIN_ROOT/DATA; an Agent Plugins client injects PLUGIN_ROOT/DATA.
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}}"
DATA_DIR="${CLAUDE_PLUGIN_DATA:-${PLUGIN_DATA:-$PLUGIN_ROOT/.data}}"
VENV="$DATA_DIR/venv"

# stdout is the MCP wire protocol — every diagnostic must go to stderr.
log() { printf '[finance-mcp:%s] %s\n' "${SERVER_NAME:-?}" "$*" >&2; }

case "$SERVER_NAME" in
  market|company|funds) ;;
  *)
    log "FATAL: server name must be market, company or funds (got '${SERVER_NAME}')"
    exit 2
    ;;
esac

if [ ! -f "$PLUGIN_ROOT/finance/mcp/$SERVER_NAME.py" ]; then
  log "FATAL: server module not found at $PLUGIN_ROOT/finance/mcp/$SERVER_NAME.py"
  exit 1
fi

# Optional secrets (screener.in, TradingView cookies). Absent is fine: the public paths
# still work and the affected tool degrades to a labelled gap rather than failing.
# shellcheck source=load-env.sh
. "$(dirname "${BASH_SOURCE[0]}")/load-env.sh"
ef_load_secrets "$PLUGIN_ROOT" "$DATA_DIR"

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

export PYTHONPATH="$PLUGIN_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m "finance.mcp.$SERVER_NAME"
