#!/bin/sh
# Runs a hosted broker MCP (Kite/Upstox/IndMoney) over stdio via mcp-remote.
#
# Every Claude session points at ONE OAuth store, so there is a single client
# registration and a single tokens.json per broker: log in from any session and
# every session is logged in. Sharing the store is only safe from mcp-remote
# 0.1.43 on, hence the version floor rather than a bare "latest".
set -eu

url="$1"
shift

MCP_REMOTE_CONFIG_DIR="${HOME}/.mcp-auth"
export MCP_REMOTE_CONFIG_DIR
mkdir -p "$MCP_REMOTE_CONFIG_DIR"
chmod 700 "$MCP_REMOTE_CONFIG_DIR" 2>/dev/null || true   # OAuth tokens live here

# Bridges orphaned by a crash or a closed terminal are invisible to a session
# that already holds a token, but one squatting the registered callback port
# forces the next login to re-register the client. A live session's bridge always
# has a live parent, so PPID 1 never matches one.
ps -o pid=,ppid=,command= -ax 2>/dev/null | while read -r pid ppid cmd; do
  [ "$ppid" = "1" ] || continue
  case "$cmd" in
    *mcp-remote*"$url"*) kill "$pid" 2>/dev/null || true ;;
  esac
done

# mcp-remote keys its files on md5(url) and coordinates concurrent logins through
# a lockfile it only writes once one is under way. Two sessions starting against
# an empty store race that window: both pick the same derived callback port, and
# whichever loses the bind re-registers the client, deleting the client_info.json
# the winner is mid-exchange on. So the first session to arrive drives the login
# and the others wait for the token it writes. Only a first login can wait —
# afterwards no session touches the callback port at all.
hash=$(
  if command -v md5 >/dev/null 2>&1; then md5 -q -s "$url"            # BSD/macOS
  else printf '%s' "$url" | md5sum | cut -d' ' -f1; fi                # GNU
)
claim="$MCP_REMOTE_CONFIG_DIR/.first-login-$hash"

have_token() {
  ls "$MCP_REMOTE_CONFIG_DIR"/mcp-remote-*/"${hash}_tokens.json" >/dev/null 2>&1
}

take_claim() {
  # exec keeps this pid, so a later session can tell whether we are still alive.
  printf '%s\n' "$$" > "$claim/owner"
}

if have_token; then
  rm -rf "$claim"
elif mkdir "$claim" 2>/dev/null; then
  take_claim
else
  owner=$(cat "$claim/owner" 2>/dev/null || true)
  case "$owner" in ''|*[!0-9]*) owner=0 ;; esac
  if [ "$owner" -eq 0 ] || ! kill -0 "$owner" 2>/dev/null; then
    rm -rf "$claim"                      # its session died mid-login; take over
    mkdir "$claim" 2>/dev/null || true
    take_claim
  else
    waited=0
    while [ "$waited" -lt 120 ]; do
      if have_token; then break; fi
      if ! kill -0 "$owner" 2>/dev/null; then break; fi
      sleep 1
      waited=$((waited + 1))
    done
  fi
fi

exec npx -y 'mcp-remote@^0.1.43' "$url" "$@"
