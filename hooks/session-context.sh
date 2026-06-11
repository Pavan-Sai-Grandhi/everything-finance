#!/usr/bin/env bash
# SessionStart hook: one line of market context so date-sensitive skills
# (swing-trading, daily-brief, filings-watch) know whether NSE/BSE are trading today.
# Weekday check only — exchange holidays are noted as "verify if holiday".

set -u
today=$(date +%F)
dow=$(date +%u) # 1=Mon .. 7=Sun

if [ "$dow" -ge 6 ]; then
  status="closed (weekend)"
else
  status="open on a normal weekday schedule, 09:15–15:30 IST (verify it is not an exchange holiday)"
fi

echo "everything-finance plugin: today is $today; Indian markets are $status."
exit 0
