#!/bin/sh
# Runs a hosted broker MCP (Kite/Upstox/IndMoney) over stdio via mcp-remote.
#
# Every Claude session points at ONE OAuth store, so there is a single client
# registration and a single tokens.json per broker: log in from any session and
# every session is logged in.
#
# The version is PINNED EXACTLY, not floored (`@X` not `@^X`). mcp-remote stores
# its client registration and tokens under a per-version subdir
# (`$MCP_REMOTE_CONFIG_DIR/mcp-remote-<version>/`). A floating range (`^0.1.43`)
# lets npx drift onto a newer patch across sessions, landing in a fresh empty
# subdir every time it bumps — so a login that succeeded yesterday is invisible
# today and you re-authenticate on every open. An exact pin keeps the token dir
# stable, which is the whole point of a shared store. Only 0.1.43+ is safe to
# share, so the pin must stay >= 0.1.43; bump it deliberately, never with `^`.
set -eu

MCP_REMOTE_VERSION=0.1.49   # exact pin — see note above; do not use a `^`/`~` range

if [ "$#" -lt 1 ]; then
  printf 'usage: mcp-bridge.sh URL [mcp-remote options]\n' >&2
  exit 2
fi
url="$1"
shift

MCP_REMOTE_CONFIG_DIR="${HOME}/.mcp-auth"
export MCP_REMOTE_CONFIG_DIR
mkdir -p "$MCP_REMOTE_CONFIG_DIR"
chmod 700 "$MCP_REMOTE_CONFIG_DIR"

# Kernel-owned coordination replaces stale PID claims and global process reaping.
# The helper preserves stdio and forwards termination only to its own bridge.
exec python3 "$(dirname "$0")/broker-login.py" "$url" "$MCP_REMOTE_VERSION" "$@"
