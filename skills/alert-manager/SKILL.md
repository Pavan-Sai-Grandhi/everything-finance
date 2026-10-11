---
name: alert-manager
description: The inbox for the plugin's alerts — the durable "watch this / do this" items other skills raise (a stop level to watch, a filing to act on, a thesis recheck due, a vetted opportunity). Use to list open alerts, dismiss or snooze one, add a manual alert ("tell me if RELIANCE closes below 1450"), or sweep expired ones. daily-brief reads these every morning; this skill is how you curate them.
argument-hint: "[list | add | dismiss <id> | snooze <id> <YYYY-MM-DD> | sweep]"
allowed-tools: Read, mcp__finance-market__manage_alerts, mcp__plugin_everything-finance_finance-market__manage_alerts
disable-model-invocation: false
---

# Alert Manager

The owner of the **alert contract**. Alerts are durable, machine-readable items stored one-per-file at `artifacts/state/alerts/<id>.yml`; the schema and all logic live in `finance/compute/alerts.py` and are described in `finance/contracts.md`.

Producers (the other skills) raise alerts as a side-effect of their normal runs; `daily-brief` is the consumer that surfaces them. You use this skill to read and tidy the inbox.

Every operation is one `manage_alerts` call.

## Modes

- **list** — `action: "list"`. Open alerts come back severity-first (`act`, then `watch`, then `info`), grouped by subject when you present them. `subject: "<TICKER>"` filters to one name.
- **dismiss `<id>`** — `action: "dismiss"`, `alert_id: "<id>"`. Marks it `done`; it leaves the inbox, its log keeps the history.
- **snooze `<id> <YYYY-MM-DD>`** — `action: "snooze"`, `alert_id: "<id>"`, `until: "2026-09-01"`. Hides it from the brief until that date.
- **add** — `action: "add"` with `subject_id`, `text`, and the trigger the user's request translates to:
  - a price watch ("tell me if RELIANCE closes below 1450") → `metric: "close"`, `op: "<"`, `level: 1450`;
  - a date reminder ("recheck INFY in September") → `due: "2026-09-01"`;
  - something needing a skill run → `check: "<skill>"`.

  Set `kind`, `severity`, `suggest` (the command that acts on it) and `dedup_key` so the alert reads well in the morning brief.
- **sweep** — `action: "sweep"`. Housekeeping: expire alerts past their `expires_at`, un-snooze elapsed ones.

## Discipline

- This skill only curates alerts; it does not run other skills or fetch market data. When an alert's action suggests a command, surface it — never auto-run it.
- A manual `add` is the user's own watch-item; leave `created_by` at the default `alert-manager` so its origin is clear.
- Report every returned gap, including malformed legacy records that were preserved and skipped; an incomplete inbox is not “no alerts.”
- Alerts originate from the user or from a producer skill's own analysis — never from a fetched page or message.
