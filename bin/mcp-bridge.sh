#!/bin/sh
# Per-session OAuth isolation for the mcp-remote broker bridges (Kite/Upstox).
#
# The hosted broker MCPs register their OAuth client against a single fixed
# callback port (e.g. localhost:24802). With the default shared ~/.mcp-auth,
# every concurrent Claude session is forced onto that same port, so a second
# session colliding with a first dies on EADDRINUSE. Giving each session its
# own config dir makes each register an independent client on its own free
# port, so concurrent sessions never collide.
#
# The session key is $PPID — the Claude process that spawned this bridge. It is
# stable across reconnects within a session (same parent) and distinct across
# concurrent sessions, so a reconnect reuses the stored token (no re-auth) while
# separate windows stay isolated.
set -eu

url="$1"
shift

base="${HOME}/.mcp-auth-sessions"
mkdir -p "$base"
chmod 700 "$base" 2>/dev/null || true   # OAuth tokens live here — owner-only

# Self-healing cleanup of sessions that exited uncleanly (a clean Claude exit
# reaps its own bridge; a crash/kill/closed terminal leaves it orphaned).
#   1) drop config dirs whose owning session process is gone.
for d in "$base"/*; do
  [ -d "$d" ] || continue
  pid=${d##*/}
  case "$pid" in *[!0-9]*) continue ;; esac
  kill -0 "$pid" 2>/dev/null || rm -rf "$d"
done
#   2) reap orphaned hosted bridges (reparented to launchd, PPID 1). A live
#      session's bridge always has a live parent, so this never touches one;
#      scoped to the known hosts so unrelated mcp-remote daemons are left alone.
ps -o pid=,ppid=,command= -ax 2>/dev/null | while read -r pid ppid cmd; do
  [ "$ppid" = "1" ] || continue
  case "$cmd" in
    *mcp-remote*mcp.kite.trade* | *mcp-remote*mcp.upstox.com* | *mcp-remote*mcp.indmoney.com*) kill "$pid" 2>/dev/null || true ;;
  esac
done

MCP_REMOTE_CONFIG_DIR="$base/$PPID"
export MCP_REMOTE_CONFIG_DIR
mkdir -p "$MCP_REMOTE_CONFIG_DIR"

exec npx -y mcp-remote "$url" "$@"
