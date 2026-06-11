#!/usr/bin/env bash
# Stop hook: publish any deep-analysis reports staged during this turn.
#
# The deep-analysis skill writes finished reports to artifacts/.staging/<TICKER>.md
# (relative to the session cwd). This hook:
#   1. moves each staged report to artifacts/YYYY-MM-DD/<TICKER>.md
#   2. extracts the "## Telegram Brief" section (or the first 12 lines as fallback)
#   3. sends it via the Telegram bot API
# No staged files -> exit 0 silently, so the hook is a no-op on ordinary turns.

set -u

STAGING="artifacts/.staging"
[ -d "$STAGING" ] || exit 0
shopt -s nullglob
staged=("$STAGING"/*.md)
[ ${#staged[@]} -gt 0 ] || exit 0

today=$(date +%F)
outdir="artifacts/$today"
mkdir -p "$outdir"

# Secrets: optional. Missing token => archive only, note the gap.
if [ -f "$HOME/.claude/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$HOME/.claude/.env"
  set +a
fi

for f in "${staged[@]}"; do
  ticker=$(basename "$f" .md)
  dest="$outdir/$ticker.md"
  mv "$f" "$dest"
  echo "everything-finance: archived deep-analysis artifact -> $dest" >&2

  # Pull the brief: the section under "## Telegram Brief", else head of file.
  brief=$(awk '/^## Telegram Brief/{flag=1; next} /^## /{flag=0} flag' "$dest")
  [ -n "$brief" ] || brief=$(head -n 12 "$dest")

  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    curl -sS -m 15 -X POST \
      "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
      --data-urlencode "text=📊 ${ticker} — deep analysis (${today})
${brief}" \
      >/dev/null \
      && echo "everything-finance: telegram brief sent for $ticker" >&2 \
      || echo "everything-finance: telegram send FAILED for $ticker (report still archived)" >&2
  else
    echo "everything-finance: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set in ~/.claude/.env — brief not sent" >&2
  fi
done

rmdir "$STAGING" 2>/dev/null || true
exit 0
