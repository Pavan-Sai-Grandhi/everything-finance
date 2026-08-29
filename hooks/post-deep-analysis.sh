#!/usr/bin/env bash
# Stop hook: publish any deep-analysis decks staged during this turn.
#
# The deep-analysis skill emits NO markdown — the deck is the deliverable. It stages a render
# input to <root>/tmp/staging/<TICKER>.report.json (or, in fundamentals mode,
# <root>/tmp/staging/<TICKER>.fundamentals.report.json), the rendered deck beside it as
# <TICKER>.report.html, and the raw leg work papers to <root>/tmp/staging/<TICKER>/agents/*.md
# (relative to the SESSION cwd), where <root> = $EVERYTHING_FINANCE_ARTIFACTS or ./artifacts
# (matching finance/paths.py). This hook:
#   1. archives each staged deck   to  <root>/stocks/<TICKER>/YYYY-MM-DD/<report>.html
#   2. archives its render input   to  <root>/stocks/<TICKER>/YYYY-MM-DD/<report>.report.json
#      (the report.json is the prior-run artifact — paths.py _STOCK_ARTIFACT points get_prior_run at it)
#   3. archives its work papers     to  <root>/stocks/<TICKER>/YYYY-MM-DD/<report>/agents/
#   4. reads the Telegram brief from the report.json's coverage.brief string
#   5. sends the self-contained deck AS a Telegram document (openable on mobile) with the brief as
#      its caption — a file:// path would be a dead local link on the phone; no deck -> brief only
# <report> is `deep-analysis` or `fundamental-analysis` — the two modes keep separate files so a
# fundamentals run and a full run on the same day cannot overwrite each other (finance/paths.py
# `_STOCK_ARTIFACT` is the authority on both names).
# No staged files -> exit 0 silently, so the hook is a no-op on ordinary turns.
#
# A Stop hook's process cwd is not guaranteed to equal the session cwd, so a bare relative
# "tmp/staging" can silently miss the files. The `cwd` in the hook's stdin JSON is authoritative —
# cd there first. Every run appends to <root>/tmp/deep-analysis-hook.log so a miss is diagnosable.

set -u

# Resolve the plugin dir before the cd below moves us to the session cwd.
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# --- Anchor to the session cwd from the hook's stdin payload -------------------------------------
input=""
if [ ! -t 0 ]; then input=$(cat); fi
cwd=$(printf '%s' "$input" | sed -n 's/.*"cwd"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
[ -n "$cwd" ] && [ -d "$cwd" ] && cd "$cwd" 2>/dev/null || true

ROOT="${EVERYTHING_FINANCE_ARTIFACTS:-artifacts}"
STAGING="$ROOT/tmp/staging"
mkdir -p "$ROOT/tmp"
log() { printf '%s %s\n' "$(date '+%F %T')" "$1" >> "$ROOT/tmp/deep-analysis-hook.log" 2>/dev/null; }
# Anything worth logging is worth telling the session about; stderr is the hook's visible channel.
say() { log "$1"; printf 'everything-finance: %s\n' "$1" >&2; }

[ -d "$STAGING" ] || exit 0
shopt -s nullglob
staged=("$STAGING"/*.report.json)
if [ ${#staged[@]} -eq 0 ]; then
  # No staged decks — clean up any empty staging dir and leave.
  rmdir "$STAGING" 2>/dev/null || true
  exit 0
fi

today=$(date +%F)
log "stop hook fired in $(pwd); ${#staged[@]} staged deck(s)"

# Secrets: optional. Missing token => archive only, note the gap.
# shellcheck source=../bin/load-env.sh
. "$PLUGIN_DIR/bin/load-env.sh"
ef_load_secrets "$PLUGIN_DIR" "${CLAUDE_PLUGIN_DATA:-}"

for f in "${staged[@]}"; do
  base=$(basename "$f" .report.json)
  case "$base" in
    *.fundamentals) ticker="${base%.fundamentals}"; report="fundamental-analysis"; label="fundamental analysis" ;;
    *)              ticker="$base";                 report="deep-analysis";        label="deep analysis" ;;
  esac
  outdir="$ROOT/stocks/$ticker/$today"
  mkdir -p "$outdir"

  # Render input (also the prior-run artifact): <base>.report.json -> <outdir>/<report>.report.json
  json_dest="$outdir/$report.report.json"
  mv "$f" "$json_dest"
  say "archived $label render input -> $json_dest"

  # Deck: <base>.report.html -> <outdir>/<report>.html. The deck is the deliverable; a run that
  # somehow staged only the JSON still archives it and sends the brief.
  deck_abs=""
  if [ -f "$STAGING/$base.report.html" ]; then
    deck_dest="$outdir/$report.html"
    mv "$STAGING/$base.report.html" "$deck_dest"
    deck_abs="$(cd "$(dirname "$deck_dest")" 2>/dev/null && pwd)/$(basename "$deck_dest")"
    say "archived report deck -> $deck_dest"
  else
    say "no rendered deck staged for $ticker (render input archived; brief still sent)"
  fi

  # Work papers: <root>/tmp/staging/<TICKER>/  ->  <root>/stocks/<TICKER>/<date>/<report>/
  if [ -d "$STAGING/$ticker" ]; then
    papers="$outdir/$report"
    rm -rf "$papers"
    mv "$STAGING/$ticker" "$papers"
    say "archived leg work papers -> $papers/"
  fi

  # Pull the brief from the render input's coverage.brief string (byte-identical to the deck's
  # brief slide). Fall back to the cover verdict line if the field is missing.
  brief=$(python3 -c 'import json,sys
try:
    d=json.load(open(sys.argv[1]))
    c=d.get("coverage",{}) or {}
    b=c.get("brief","")
    if not b:
        cov=d.get("cover",{}) or {}
        b=cov.get("verdict","") or ""
    print(b if isinstance(b,str) else "\n".join(b))
except Exception:
    pass' "$json_dest" 2>/dev/null)
  caption="📊 ${ticker} — ${label} (${today})
${brief}"

  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    # The deck is self-contained (fonts embedded, no external assets) and ~1.5 MB — well under
    # Telegram's 50 MB bot limit — so send it AS THE DOCUMENT the user can open on their phone,
    # with the brief as the caption. A file:// path would be a dead local link on mobile.
    # No deck rendered -> fall back to a plain brief message so the headline still lands.
    # curl exits 0 even when Telegram replies {"ok":false,...} (HTTP 4xx), so test the body.
    if [ -n "$deck_abs" ]; then
      resp=$(curl -sS -m 60 \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendDocument" \
        -F "chat_id=${TELEGRAM_CHAT_ID}" \
        -F "document=@${deck_abs};filename=${ticker}-${report}.html;type=text/html" \
        -F "caption=${caption}" 2>&1)
      if printf '%s' "$resp" | grep -q '"ok":true'; then
        say "telegram deck + brief sent for $ticker"
      else
        say "telegram sendDocument FAILED for $ticker (deck still archived): $(printf '%s' "$resp" | head -c 200)"
      fi
    else
      resp=$(curl -sS -m 15 -X POST \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=${caption}" 2>&1)
      if printf '%s' "$resp" | grep -q '"ok":true'; then
        say "telegram brief sent for $ticker (no deck to attach)"
      else
        say "telegram send FAILED for $ticker: $(printf '%s' "$resp" | head -c 200)"
      fi
    fi
  else
    say "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set in .env — brief not sent for $ticker"
  fi
done

rmdir "$STAGING" 2>/dev/null || true
exit 0
