#!/usr/bin/env bash
# Stop hook: publish any deep-analysis reports staged during this turn.
#
# The deep-analysis skill writes a finished report to artifacts/.staging/<TICKER>.md and the
# raw agent work papers to artifacts/.staging/<TICKER>/agents/*.md (relative to the SESSION cwd).
# This hook:
#   1. archives each staged report to  artifacts/YYYY-MM-DD/<TICKER>-deep-analysis.md
#   2. archives its work papers to      artifacts/YYYY-MM-DD/<TICKER>-deep-analysis/agents/
#   3. extracts the "## Telegram Brief" section (or the first 12 lines as fallback)
#   4. sends it via the Telegram bot API
# No staged files -> exit 0 silently, so the hook is a no-op on ordinary turns.
#
# RELIABILITY: Stop hooks do not always run with their process cwd equal to the session cwd, so a
# bare relative "artifacts/.staging" can silently miss the files. We read `cwd` from the hook's
# stdin JSON (Claude Code passes it) and cd there before looking — making the publish deterministic
# regardless of where the hook process starts. Every run appends to artifacts/.deep-analysis-hook.log
# so a miss is diagnosable instead of silent.

set -u

# --- Anchor to the session cwd from the hook's stdin payload -------------------------------------
input=""
if [ ! -t 0 ]; then input=$(cat); fi
cwd=$(printf '%s' "$input" | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
[ -n "$cwd" ] && [ -d "$cwd" ] && cd "$cwd" 2>/dev/null || true

STAGING="artifacts/.staging"
log() { printf '%s %s\n' "$(date '+%F %T')" "$1" >> artifacts/.deep-analysis-hook.log 2>/dev/null; }

[ -d "$STAGING" ] || exit 0
shopt -s nullglob
staged=("$STAGING"/*.md)
if [ ${#staged[@]} -eq 0 ]; then
  # No final reports — clean up any empty staging dir and leave.
  rmdir "$STAGING" 2>/dev/null || true
  exit 0
fi

today=$(date +%F)
outdir="artifacts/$today"
mkdir -p "$outdir"
log "stop hook fired in $(pwd); ${#staged[@]} staged report(s)"

# Secrets: optional. Missing token => archive only, note the gap.
if [ -f "$HOME/.claude/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$HOME/.claude/.env"
  set +a
fi

for f in "${staged[@]}"; do
  ticker=$(basename "$f" .md)
  dest="$outdir/$ticker-deep-analysis.md"
  mv "$f" "$dest"
  log "archived report -> $dest"
  echo "everything-finance: archived deep-analysis report -> $dest" >&2

  # Work papers: artifacts/.staging/<TICKER>/  ->  artifacts/YYYY-MM-DD/<TICKER>-deep-analysis/
  if [ -d "$STAGING/$ticker" ]; then
    papers="$outdir/$ticker-deep-analysis"
    rm -rf "$papers"
    mv "$STAGING/$ticker" "$papers"
    log "archived work papers -> $papers/"
    echo "everything-finance: archived agent work papers -> $papers/" >&2
  fi

  # Pull the brief: the section under "## Telegram Brief", else head of file.
  brief=$(awk '/^## Telegram Brief/{flag=1; next} /^## /{flag=0} flag' "$dest")
  [ -n "$brief" ] || brief=$(head -n 12 "$dest")

  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    if curl -sS -m 15 -X POST \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=📊 ${ticker} — deep analysis (${today})
${brief}" \
        >/dev/null; then
      log "telegram brief sent for $ticker"
      echo "everything-finance: telegram brief sent for $ticker" >&2
    else
      log "telegram send FAILED for $ticker (report still archived)"
      echo "everything-finance: telegram send FAILED for $ticker (report still archived)" >&2
    fi
  else
    log "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set — brief not sent for $ticker"
    echo "everything-finance: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set in ~/.claude/.env — brief not sent" >&2
  fi
done

rmdir "$STAGING" 2>/dev/null || true
exit 0
