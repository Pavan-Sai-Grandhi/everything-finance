#!/usr/bin/env bash
# The one place plugin secrets are located and loaded, so every entry point (the MCP
# launcher, the Claude hooks) resolves them identically across clients.
#
# ef_load_secrets <plugin_root> <data_dir> — sources the first existing file of:
#   1. <plugin_root>/.env    a .env next to the plugin (the default)
#   2. <data_dir>/.env       the client's persistent data dir (for read-only installs)
#
# Both paths come from vars every client injects (CLAUDE_PLUGIN_ROOT/DATA under Claude Code,
# PLUGIN_ROOT/DATA under any Agent Plugins client), so neither is tied to one vendor.
# Sourced here, never passed on a command line, so secrets never reach `ps`, mcp.json, or
# the transcript. A missing file is not an error: the caller degrades the affected source
# to a labelled gap. Template of the keys: <plugin_root>/.env.example.
ef_load_secrets() {
  local root="${1:-}" data="${2:-}" f seed allexport_was_set=0
  case "$-" in *a*) allexport_was_set=1 ;; esac
  local candidates=()
  [ -n "$root" ] && candidates+=("$root/.env")
  [ -n "$data" ] && candidates+=("$data/.env")
  for f in "${candidates[@]}"; do
    if [ -f "$f" ]; then
      set -a
      # shellcheck disable=SC1090
      . "$f"
      [ "$allexport_was_set" -eq 1 ] || set +a
      printf '[everything-finance] secrets loaded from %s\n' "$f" >&2
      return 0
    fi
  done

  # No .env anywhere. When the client gave us a persistent data dir (the installed-plugin
  # case, where $root is read-only and its path is unknowable up front), seed a template
  # there from .env.example so the user has a known file to fill in, then re-run.
  if [ -n "$data" ] && [ -f "$root/.env.example" ] && mkdir -p "$data" 2>/dev/null; then
    # Publish a complete private file without overwriting a concurrent writer.
    seed=$(mktemp "$data/.env-seed.XXXXXX") || return 0
    if cp "$root/.env.example" "$seed" && chmod 600 "$seed" \
       && ln "$seed" "$data/.env" 2>/dev/null; then
      printf '[everything-finance] no .env found — seeded a template at %s; fill it in to enable authenticated sources\n' \
        "$data/.env" >&2
    fi
    rm -f "$seed"
  else
    printf '[everything-finance] no .env found (searched: %s) — public sources work; copy .env.example to a searched path to enable authenticated ones\n' \
      "${candidates[*]}" >&2
  fi
  return 0
}
