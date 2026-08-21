#!/usr/bin/env python3
"""Alert schema, producers, consumers and invariants: `finance/contracts.md`
("Artifact: alert"). This module owns the storage, dedup and cheap evaluation.

Reached through: manage_alerts.
"""
import hashlib
import os
import re

import yaml

from finance import paths, spine
from finance.spine import today as _today

_SOURCE = "finance.compute.alerts"

OPEN_STATUSES = ("open", "triggered", "snoozed")
# The inbox order every consumer sees: what to act on before what to merely watch.
SEVERITY_ORDER = {"act": 0, "watch": 1, "info": 2}
_OPS = {"<": lambda a, b: a < b, ">": lambda a, b: a > b,
        "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b}

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


_ACTIONS = ("list", "add", "dismiss", "snooze", "sweep")


def manage(action, alert_id=None, subject=None, until=None, created_by="alert-manager",
           subject_type="stock", subject_id=None, kind="custom", metric=None, op=None,
           level=None, due=None, check=None, text=None, suggest=None, severity="watch",
           expires_at=None, dedup_key=None):
    """Every inbox operation in the shared envelope: list | add | dismiss | snooze | sweep.

    `list` comes back severity-first (act before watch before info) then by subject, so
    every consumer reads the same order. An unknown action, a missing alert or an
    incomplete `add` is a labelled gap.
    """
    if action == "list":
        items = load_open(subject)
        items.sort(key=lambda a: (SEVERITY_ORDER.get(a.get("severity"), 9),
                                  a.get("subject", {}).get("id") or ""))
        return spine.envelope(True, _SOURCE,
                              {"action": action, "count": len(items), "alerts": items}, [])

    if action == "sweep":
        return spine.envelope(True, _SOURCE, dict(sweep(), action=action), [])

    if action == "add":
        if metric is not None and op and level is not None:
            trigger = {"metric": metric, "op": op, "level": level}
        elif due:
            trigger = {"due": due}
        elif check:
            trigger = {"check": check}
        else:
            return spine.envelope(False, _SOURCE, {"action": action},
                                  ["add needs a trigger: metric+op+level, due, or check"])
        if not subject_id or not text:
            return spine.envelope(False, _SOURCE, {"action": action},
                                  ["add needs subject_id and the action text"])
        act = {"text": text}
        if suggest:
            act["suggest"] = suggest
        alert = create(created_by=created_by,
                       subject={"type": subject_type, "id": subject_id},
                       kind=kind, trigger=trigger, action=act, severity=severity,
                       expires_at=expires_at, dedup_key=dedup_key)
        return spine.envelope(True, _SOURCE, {"action": action, "alert": alert}, [])

    if action in ("dismiss", "snooze"):
        if not alert_id:
            return spine.envelope(False, _SOURCE, {"action": action},
                                  [f"{action} needs an alert id"])
        if action == "snooze":
            if not until:
                return spine.envelope(False, _SOURCE, {"action": action, "id": alert_id},
                                      ["snooze needs `until` as YYYY-MM-DD"])
            alert = snooze(alert_id, until, note=f"snoozed via {created_by}")
        else:
            alert = set_status(alert_id, "done", note=f"dismissed via {created_by}")
        if alert is None:
            return spine.envelope(False, _SOURCE, {"action": action, "id": alert_id},
                                  [f"no alert {alert_id}"])
        return spine.envelope(True, _SOURCE, {"action": action, "alert": alert}, [])

    return spine.envelope(
        False, _SOURCE, {"action": action},
        [f"unknown action {action!r}; expected one of {', '.join(_ACTIONS)}"])
