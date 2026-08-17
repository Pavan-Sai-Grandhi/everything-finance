#!/usr/bin/env bash
# Runs every test script in the plugin and reports the total assertion count.
# Tests are standalone (no pytest on the target box): each prints "N passed, M failed"
# and exits non-zero on failure.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

files=$(find lib finance skills -name 'test_*.py' 2>/dev/null | sort)
total_pass=0 total_fail=0 broken=0

for f in $files; do
  out=$(python3 "$f" 2>&1); rc=$?
  tail_line=$(printf '%s\n' "$out" | tail -1)
  p=$(printf '%s' "$tail_line" | sed -n 's/^\([0-9][0-9]*\) passed.*/\1/p')
  m=$(printf '%s' "$tail_line" | sed -n 's/.*, \([0-9][0-9]*\) failed.*/\1/p')
  total_pass=$((total_pass + ${p:-0}))
  total_fail=$((total_fail + ${m:-0}))
  if [ $rc -ne 0 ]; then
    broken=$((broken + 1))
    printf '  FAIL %-52s %s\n' "$f" "$tail_line"
    [ "${VERBOSE:-}" = "1" ] && printf '%s\n' "$out"
  fi
done

printf '\n%s assertions passed, %s failed, %s file(s) errored\n' \
  "$total_pass" "$total_fail" "$broken"
[ "$total_fail" -eq 0 ] && [ "$broken" -eq 0 ]
