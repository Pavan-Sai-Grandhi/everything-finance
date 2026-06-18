#!/usr/bin/env python3
"""The alert contract: durable "watch this / do this" items that skills raise as a
side-effect of a normal run and `daily-brief` surfaces every morning.

One alert is one file at `state/alerts/<id>.yml`. Skills are the producers; this
module owns the schema, deduplication, and the *cheap* evaluation (metric/date
triggers checked against data the caller already has — never its own network call,
so `daily-brief` stays fast). Triggers that need a skill run to resolve carry a
`{check: <skill>}` form and are surfaced as a suggested command, never auto-run.

Alert schema (all keys optional unless noted):

    id:          <kind>-<subject>-<shorthash>   (generated)
    created_by:  producing skill                (required)
    created_at / updated_at: ISO date
    subject:     {type: stock|fund|strategy|portfolio, id: RELIANCE}   (required)
    kind:        price_cross | filing_act_on | time_stop | regime_change |
                 revalidate_due | reanalyze_due | rebalance_due | sip_due |
                 opportunity | investigate | custom                    (required)
    trigger:     exactly one of                 (required)
                   {metric: close|low|high|day_change_pct|dist_to_sl_pct, op: "<", level: 1450}
                   {due: 2026-09-15}
                   {check: trade-tracker, args: {symbol: RELIANCE}}
    action:      {text: "...", suggest: "/trade-tracker RELIANCE"}     (required: text)
    severity:    info | watch | act             (default: watch)
    status:      open | triggered | snoozed | done | expired
    snooze_until / expires_at: ISO date         (optional)
    dedup_key:   producers set this so re-runs update in place           (recommended)
    log:         [{date, note}]
"""
import hashlib
import os
import re
import sys
from datetime import date as _date_cls

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

import yaml  # noqa: E402

OPEN_STATUSES = ("open", "triggered", "snoozed")
_OPS = {"<": lambda a, b: a < b, ">": lambda a, b: a > b,
        "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b}


def _today():
    return _date_cls.today().isoformat()


def _slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(s).strip().lower())).strip("-")


def _path(alert_id):
    return os.path.join(paths.alerts_dir(), f"{alert_id}.yml")


def _save(alert):
    with open(_path(alert["id"]), "w") as f:
        yaml.safe_dump(alert, f, sort_keys=False, default_flow_style=False)
    return alert


def load_all():
    """Every alert on disk, as a list of dicts."""
    d = paths.alerts_dir()
    out = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".yml"):
            with open(os.path.join(d, fn)) as f:
                a = yaml.safe_load(f)
            if a:
                out.append(a)
    return out


def _is_open(a, today=None):
    today = today or _today()
    if a.get("status") in ("done", "expired"):
        return False
    su = a.get("snooze_until")
    if a.get("status") == "snoozed" and su and str(su) > today:
        return False
    return True


def load_open(subject=None):
    """Open (non-done, non-expired, not currently snoozed) alerts, optionally filtered
    to a subject id (accepts the id string or a subject dict)."""
    today = _today()
    if isinstance(subject, dict):
        subject = subject.get("id")
    out = [a for a in load_all() if _is_open(a, today)]
    if subject is not None:
        out = [a for a in out if a.get("subject", {}).get("id") == subject]
    return out


def _gen_id(kind, subject, dedup_key):
    seed = dedup_key or f"{kind}:{subject.get('id')}:{_today()}"
    short = hashlib.md5(seed.encode()).hexdigest()[:6]
    return f"{kind}-{_slug(subject.get('id') or subject.get('type'))}-{short}"


def create(created_by, subject, kind, trigger, action, severity="watch",
           expires_at=None, snooze_until=None, dedup_key=None):
    """Write a new alert. If an open alert with the same `dedup_key` already exists,
    update it in place (trigger/action/severity/expiry refreshed, log note appended)
    instead of piling up a duplicate. Returns the alert dict."""
    today = _today()
    if dedup_key:
        for a in load_open():
            if a.get("dedup_key") == dedup_key:
                a.update(trigger=trigger, action=action, severity=severity,
                         updated_at=today)
                if expires_at:
                    a["expires_at"] = expires_at
                a.setdefault("log", []).append({"date": today, "note": "refreshed"})
                return _save(a)

    alert = {
        "id": _gen_id(kind, subject, dedup_key),
        "created_by": created_by,
        "created_at": today,
        "updated_at": today,
        "subject": subject,
        "kind": kind,
        "trigger": trigger,
        "action": action,
        "severity": severity,
        "status": "open",
        "dedup_key": dedup_key,
        "log": [{"date": today, "note": f"created by {created_by}"}],
    }
    if expires_at:
        alert["expires_at"] = expires_at
    if snooze_until:
        alert["snooze_until"] = snooze_until
        alert["status"] = "snoozed"
    return _save(alert)


def set_status(alert_id, status, note=None):
    """Transition an alert's status and append a log line. Returns the alert, or None
    if it doesn't exist."""
    p = _path(alert_id)
    if not os.path.isfile(p):
        return None
    with open(p) as f:
        a = yaml.safe_load(f)
    a["status"] = status
    a["updated_at"] = _today()
    a.setdefault("log", []).append({"date": _today(), "note": note or f"-> {status}"})
    return _save(a)


def snooze(alert_id, until, note=None):
    """Hide an alert from `load_open` until the given date. Returns the alert, or None."""
    p = _path(alert_id)
    if not os.path.isfile(p):
        return None
    with open(p) as f:
        a = yaml.safe_load(f)
    a["snooze_until"] = until
    a["status"] = "snoozed"
    a["updated_at"] = _today()
    a.setdefault("log", []).append({"date": _today(), "note": note or f"snoozed until {until}"})
    return _save(a)


def evaluate_cheap(alerts, market_data):
    """Decide which `metric`/`due` triggers fire given data the caller already fetched
    — no network of its own. `{check: ...}` alerts are left untouched (they need a
    skill run). Fired alerts are marked `status: triggered` on disk; returns the list
    of fired alerts.

    market_data: {"date": "YYYY-MM-DD", "prices": {SYMBOL: {metric: value, ...}}}
    (a bare {SYMBOL: {...}} mapping is also accepted, with date defaulting to today).
    """
    today = str(market_data.get("date") or _today())
    prices = market_data.get("prices", market_data)
    fired = []
    for a in alerts:
        trig = a.get("trigger", {}) or {}
        if "due" in trig:
            if today >= str(trig["due"]):
                fired.append(a)
        elif "metric" in trig:
            row = prices.get(a.get("subject", {}).get("id"))
            if not isinstance(row, dict):
                continue
            val = row.get(trig["metric"])
            op = _OPS.get(trig.get("op"))
            if val is None or op is None:
                continue
            if op(val, trig["level"]):
                fired.append(a)
        # {check: ...} triggers are intentionally not evaluated here.
    for a in fired:
        if a.get("status") != "triggered":
            set_status(a["id"], "triggered", note="cheap trigger fired")
            a["status"] = "triggered"
    return fired


def sweep():
    """Housekeeping: expire alerts past `expires_at`, and un-snooze those whose
    `snooze_until` has elapsed. Returns {"expired": [...], "unsnoozed": [...]} of ids."""
    today = _today()
    expired, unsnoozed = [], []
    for a in load_all():
        if a.get("status") in ("done", "expired"):
            continue
        exp = a.get("expires_at")
        if exp and str(exp) < today:
            set_status(a["id"], "expired", note="past expires_at")
            expired.append(a["id"])
            continue
        su = a.get("snooze_until")
        if su and str(su) <= today:
            a.pop("snooze_until", None)
            a["status"] = "open"
            a["updated_at"] = today
            a.setdefault("log", []).append({"date": today, "note": "snooze elapsed"})
            _save(a)
            unsnoozed.append(a["id"])
    return {"expired": expired, "unsnoozed": unsnoozed}
