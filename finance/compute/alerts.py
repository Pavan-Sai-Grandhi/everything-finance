"""Alert schema, producers, consumers and invariants: `finance/contracts.md`
("Artifact: alert"). This module owns the storage, dedup and cheap evaluation.

Reached through: manage_alerts.
"""
import fcntl
from functools import wraps
import threading
import uuid
import warnings
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

_THREAD_LOCK = threading.RLock()
_LOCAL = threading.local()


def _transaction(fn):
    """Serialize complete read/modify/write operations across threads and processes."""
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with _THREAD_LOCK:
            if getattr(_LOCAL, 'active', False):
                return fn(*args, **kwargs)
            with open(os.path.join(paths.alerts_dir(), '.store.lock'), 'a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                _LOCAL.active = True
                try:
                    return fn(*args, **kwargs)
                finally:
                    _LOCAL.active = False
    return wrapped


def _slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(s).strip().lower())).strip("-")


def _path(alert_id):
    if not isinstance(alert_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", alert_id):
        raise ValueError("invalid alert id")
    return paths._contained(os.path.join(paths.alerts_dir(), f"{alert_id}.yml"))


def _date(value):
    if value is None:
        raise ValueError("alert dates cannot be null")
    return paths._day(value)


def _validate(alert, expected_id=None):
    if not isinstance(alert, dict):
        raise ValueError("alert must be a mapping")
    if expected_id is not None and alert.get('id') != expected_id:
        raise ValueError("alert id differs from its filename")
    _path(alert.get('id'))
    if alert.get('status') not in (*OPEN_STATUSES, 'done', 'expired') or alert.get('severity') not in SEVERITY_ORDER:
        raise ValueError("invalid alert status or severity")
    subject, action, trigger = alert.get('subject'), alert.get('action'), alert.get('trigger')
    if not isinstance(subject, dict) or not all(isinstance(subject.get(k), str) and subject[k].strip() for k in ('id','type')):
        raise ValueError("invalid alert subject")
    if not isinstance(action, dict) or not isinstance(action.get('text'), str) or not action['text'].strip():
        raise ValueError("alert action text is required")
    if not isinstance(trigger, dict) or sum(key in trigger for key in ('due','metric','check')) != 1:
        raise ValueError("alert requires exactly one trigger type")
    if 'due' in trigger:
        trigger['due'] = _date(trigger['due'])
    elif 'metric' in trigger:
        if not isinstance(trigger['metric'], str) or not trigger['metric'].strip() or trigger.get('op') not in _OPS or spine.f(trigger.get('level')) is None:
            raise ValueError("invalid metric trigger")
    elif not isinstance(trigger['check'], str) or not trigger['check'].strip() or ('args' in trigger and not isinstance(trigger['args'], dict)):
        raise ValueError("invalid check trigger")
    for field in ('created_at','updated_at','expires_at','snooze_until'):
        if field in alert:
            alert[field] = _date(alert[field])
    if alert['status'] == 'snoozed' and not alert.get('snooze_until'):
        raise ValueError("snoozed alert requires a date")
    if not isinstance(alert.get('log', []), list):
        raise ValueError("alert log must be a list")
    return alert


def _save(alert):
    _validate(alert)
    spine.atomic_write(_path(alert["id"]), lambda stream: yaml.safe_dump(
        alert, stream, sort_keys=False, default_flow_style=False))
    return alert


@_transaction
def load_all(gaps=None):
    """Every alert on disk, as a list of dicts."""
    d = paths.alerts_dir()
    out = []
    for fn in sorted(os.listdir(d)):
        if fn.endswith(".yml"):
            try:
                with open(_path(fn[:-4])) as f:
                    a = _validate(yaml.safe_load(f), fn[:-4])
                out.append(a)
            except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
                gap = f"alert {fn}: unreadable or invalid ({type(exc).__name__}); preserved, skipped"
                if gaps is not None:
                    gaps.append(gap)
                else:
                    warnings.warn(gap, RuntimeWarning)
    return out


def _is_open(a, today=None):
    today = today or _today()
    if a.get("status") not in OPEN_STATUSES:
        return False
    if a.get("expires_at") and _date(a["expires_at"]) < today:
        return False
    su = a.get("snooze_until")
    if a.get("status") == "snoozed" and su and str(su) > today:
        return False
    return True


def load_open(subject=None, gaps=None):
    """Open (non-done, non-expired, not currently snoozed) alerts, optionally filtered
    to a subject id (accepts the id string or a subject dict)."""
    today = _today()
    if isinstance(subject, dict):
        subject = subject.get("id")
    out = [a for a in load_all(gaps) if _is_open(a, today)]
    if subject is not None:
        out = [a for a in out if a.get("subject", {}).get("id") == subject]
    return out


def _gen_id(kind, subject, dedup_key):
    short = uuid.uuid4().hex
    return f"{kind}-{_slug(subject.get('id') or subject.get('type'))}-{short}"


@_transaction
def create(created_by, subject, kind, trigger, action, severity="watch",
           expires_at=None, snooze_until=None, dedup_key=None, gaps=None):
    """Write a new alert. If an open alert with the same `dedup_key` already exists,
    update it in place (trigger/action/severity/expiry refreshed, log note appended)
    instead of piling up a duplicate. Returns the alert dict."""
    today = _today()
    if not isinstance(subject, dict) or not subject.get('id') or not isinstance(trigger, dict) or not isinstance(action, dict):
        raise ValueError("subject, trigger and action must be valid mappings")
    if severity not in SEVERITY_ORDER:
        raise ValueError("unknown alert severity")
    if expires_at is not None:
        expires_at = _date(expires_at)
    if snooze_until is not None:
        snooze_until = _date(snooze_until)
    if 'due' in trigger:
        trigger = dict(trigger, due=_date(trigger['due']))
    if 'metric' in trigger and (trigger.get('op') not in _OPS or spine.f(trigger.get('level')) is None):
        raise ValueError("metric triggers require a supported operator and finite level")
    if dedup_key:
        for a in load_all(gaps):
            if (a.get("status") in OPEN_STATUSES and a.get("dedup_key") == dedup_key
                    and (not a.get("expires_at") or a["expires_at"] >= today)):
                if a.get("subject") != subject or a.get("kind") != kind:
                    raise ValueError("dedup key belongs to another alert subject or kind")
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


@_transaction
def set_status(alert_id, status, note=None):
    """Transition an alert's status and append a log line. Returns the alert, or None
    if it doesn't exist."""
    if status not in (*OPEN_STATUSES, "done", "expired"):
        raise ValueError("unknown alert status")
    p = _path(alert_id)
    if not os.path.isfile(p):
        return None
    with open(p) as f:
        a = yaml.safe_load(f)
    a["status"] = status
    a["updated_at"] = _today()
    a.setdefault("log", []).append({"date": _today(), "note": note or f"-> {status}"})
    return _save(a)


@_transaction
def snooze(alert_id, until, note=None):
    """Hide an alert from `load_open` until the given date. Returns the alert, or None."""
    p = _path(alert_id)
    if not os.path.isfile(p):
        return None
    with open(p) as f:
        a = yaml.safe_load(f)
    a["snooze_until"] = _date(until)
    a["status"] = "snoozed"
    a["updated_at"] = _today()
    a.setdefault("log", []).append({"date": _today(), "note": note or f"snoozed until {until}"})
    return _save(a)


@_transaction
def evaluate_cheap(alerts, market_data):
    """Decide which `metric`/`due` triggers fire given data the caller already fetched
    — no network of its own. `{check: ...}` alerts are left untouched (they need a
    skill run). Fired alerts are marked `status: triggered` on disk; returns the list
    of fired alerts.

    market_data: {"date": "YYYY-MM-DD", "prices": {SYMBOL: {metric: value, ...}}}.
    """
    today = _date(market_data.get("date") or _today())
    prices = market_data.get("prices") or {}
    fired = []
    current = {a["id"]: a for a in load_all()}
    for supplied in alerts:
        a = current.get(supplied.get("id"))
        if a is None or not _is_open(a, today):
            continue
        trig = a.get("trigger", {}) or {}
        if "due" in trig:
            if today >= str(trig["due"]):
                fired.append(a)
        elif "metric" in trig:
            row = prices.get(a.get("subject", {}).get("id"))
            if not isinstance(row, dict):
                continue
            val = spine.f(row.get(trig["metric"]))
            level = spine.f(trig.get("level"))
            op = _OPS.get(trig.get("op"))
            if val is None or level is None or op is None:
                continue
            if op(val, level):
                fired.append(a)
        # {check: ...} triggers are intentionally not evaluated here.
    for a in fired:
        if a.get("status") != "triggered":
            set_status(a["id"], "triggered", note="cheap trigger fired")
            a["status"] = "triggered"
    return fired


@_transaction
def sweep(gaps=None):
    """Housekeeping: expire alerts past `expires_at`, and un-snooze those whose
    `snooze_until` has elapsed. Returns {"expired": [...], "unsnoozed": [...]} of ids."""
    today = _today()
    expired, unsnoozed = [], []
    for a in load_all(gaps):
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


_ACTIONS = ("list", "add", "dismiss", "snooze", "sweep", "evaluate")


def _manage(action, alert_id=None, subject=None, until=None, created_by="alert-manager",
           subject_type="stock", subject_id=None, kind="custom", metric=None, op=None,
           level=None, due=None, check=None, text=None, suggest=None, severity="watch",
           expires_at=None, dedup_key=None, prices=None, as_of=None):
    """Every inbox operation in the shared envelope: list | add | dismiss | snooze | sweep |
    evaluate.

    `list` comes back severity-first (act before watch before info) then by subject, so
    every consumer reads the same order. An unknown action, a missing alert or an
    incomplete `add` is a labelled gap.
    """
    gaps = []
    if action == "list":
        items = load_open(subject, gaps)
        items.sort(key=lambda a: (SEVERITY_ORDER.get(a.get("severity"), 9),
                                  a.get("subject", {}).get("id") or ""))
        return spine.envelope(True, _SOURCE,
                              {"action": action, "count": len(items), "alerts": items}, gaps)

    if action == "evaluate":
        if not isinstance(prices, dict):
            return spine.envelope(False, _SOURCE, {"action": action},
                                  ["evaluate needs `prices` as {SYMBOL: {metric: value}}"])
        fired = evaluate_cheap(load_open(subject, gaps), {"date": as_of, "prices": prices})
        return spine.envelope(True, _SOURCE,
                              {"action": action, "count": len(fired), "fired": fired}, gaps)

    if action == "sweep":
        return spine.envelope(True, _SOURCE, dict(sweep(gaps), action=action), gaps)

    if action == "add":
        trigger_types = sum((any(value is not None for value in (metric, op, level)), due is not None, check is not None))
        if trigger_types != 1:
            return spine.envelope(False, _SOURCE, {"action": action}, ["add requires exactly one trigger type"])
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
                       expires_at=expires_at, dedup_key=dedup_key, gaps=gaps)
        return spine.envelope(True, _SOURCE, {"action": action, "alert": alert}, gaps)

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
        return spine.envelope(True, _SOURCE, {"action": action, "alert": alert}, gaps)

    return spine.envelope(
        False, _SOURCE, {"action": action},
        [f"unknown action {action!r}; expected one of {', '.join(_ACTIONS)}"])


@wraps(_manage)
def manage(*args, **kwargs):
    try:
        return _manage(*args, **kwargs)
    except ValueError as exc:  # the validators' own messages say what to correct
        return spine.envelope(False, _SOURCE, {}, [f"alert operation rejected: {exc}"])
    except (OSError, TypeError, KeyError, yaml.YAMLError) as exc:
        return spine.envelope(False, _SOURCE, {}, [f"alert operation failed: {type(exc).__name__}"])
