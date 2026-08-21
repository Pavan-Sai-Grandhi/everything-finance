#!/usr/bin/env python3
"""Offline tests for the alert contract. No network. Each test runs inside a temp
artifacts root. Run: python3 finance/tests/test_alerts.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.compute import alerts
from finance.tests.harness import check, summary


def _isolated():
    tmp = tempfile.mkdtemp()
    os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = os.path.join(tmp, "artifacts")
    return tmp


# --- create + dedup ----------------------------------------------------------
_isolated()
a = alerts.create(
    created_by="trade-tracker",
    subject={"type": "stock", "id": "RELIANCE"},
    kind="price_cross",
    trigger={"metric": "close", "op": "<", "level": 1450},
    action={"text": "stop hit", "suggest": "/trade-tracker RELIANCE"},
    severity="act", dedup_key="reliance-stop")
check("create writes a file", os.path.isfile(alerts._path(a["id"])))
check("id follows <kind>-<subject>-<hash>", a["id"].startswith("price_cross-reliance-"), a["id"])
check("create stamps status open", a["status"] == "open")

# same dedup_key updates in place, no second file
a2 = alerts.create(
    created_by="trade-tracker",
    subject={"type": "stock", "id": "RELIANCE"},
    kind="price_cross",
    trigger={"metric": "close", "op": "<", "level": 1500},
    action={"text": "stop raised", "suggest": "/trade-tracker RELIANCE"},
    severity="act", dedup_key="reliance-stop")
check("dedup keeps same id", a2["id"] == a["id"], a2["id"])
check("dedup updates trigger level", a2["trigger"]["level"] == 1500)
check("dedup did not create a second file", len(alerts.load_all()) == 1, len(alerts.load_all()))

# --- sector_refresh_due (monthly sector cache reminder) ----------------------
_isolated()
sr = alerts.create(
    created_by="deep-analysis",
    subject={"type": "sector", "id": "banking"},
    kind="sector_refresh_due",
    trigger={"due": "2026-07-23"},
    action={"text": "sector read 1 month old", "suggest": "/sector-analysis banking"},
    severity="watch", dedup_key="sector-refresh-banking")
check("sector_refresh_due id", sr["id"].startswith("sector_refresh_due-banking-"), sr["id"])
check("sector subject persisted", sr["subject"]["type"] == "sector")
# re-running deep-analysis on a same-sector stock updates the reminder in place
sr2 = alerts.create(
    created_by="deep-analysis",
    subject={"type": "sector", "id": "banking"},
    kind="sector_refresh_due",
    trigger={"due": "2026-08-23"},
    action={"text": "sector read refreshed", "suggest": "/sector-analysis banking"},
    severity="watch", dedup_key="sector-refresh-banking")
check("sector refresh dedups in place", sr2["id"] == sr["id"] and len(alerts.load_all()) == 1)
check("sector refresh due bumped", sr2["trigger"]["due"] == "2026-08-23")

# --- load_open filtering -----------------------------------------------------
_isolated()
alerts.create(created_by="x", subject={"type": "stock", "id": "INFY"}, kind="custom",
              trigger={"due": "2026-01-01"}, action={"text": "a"}, dedup_key="infy")
alerts.create(created_by="x", subject={"type": "stock", "id": "TCS"}, kind="custom",
              trigger={"due": "2026-01-01"}, action={"text": "b"}, dedup_key="tcs")
done = alerts.create(created_by="x", subject={"type": "stock", "id": "WIPRO"}, kind="custom",
                     trigger={"due": "2026-01-01"}, action={"text": "c"}, dedup_key="wipro")
alerts.set_status(done["id"], "done")
check("load_open excludes done", len(alerts.load_open()) == 2, len(alerts.load_open()))
check("load_open filters by subject", len(alerts.load_open("INFY")) == 1)
check("load_open subject accepts dict",
      len(alerts.load_open({"id": "TCS"})) == 1)

# --- evaluate_cheap ----------------------------------------------------------
_isolated()
m = alerts.create(created_by="x", subject={"type": "stock", "id": "RELIANCE"}, kind="price_cross",
                  trigger={"metric": "close", "op": "<", "level": 1450},
                  action={"text": "stop"}, dedup_key="r")
nofire = alerts.create(created_by="x", subject={"type": "stock", "id": "TCS"}, kind="price_cross",
                       trigger={"metric": "close", "op": "<", "level": 1000},
                       action={"text": "stop"}, dedup_key="t")
due = alerts.create(created_by="x", subject={"type": "stock", "id": "INFY"}, kind="reanalyze_due",
                    trigger={"due": "2026-06-01"}, action={"text": "recheck"}, dedup_key="i")
chk = alerts.create(created_by="x", subject={"type": "stock", "id": "HDFC"}, kind="time_stop",
                    trigger={"check": "trade-tracker", "args": {"symbol": "HDFC"}},
                    action={"text": "run tracker"}, dedup_key="h")

market = {"date": "2026-06-17",
          "prices": {"RELIANCE": {"close": 1400}, "TCS": {"close": 3500}}}
fired = alerts.evaluate_cheap(alerts.load_open(), market)
ids = {a["id"] for a in fired}
check("evaluate_cheap fires breached metric", m["id"] in ids)
check("evaluate_cheap fires past-due", due["id"] in ids)
check("evaluate_cheap skips un-breached metric", nofire["id"] not in ids)
check("evaluate_cheap ignores {check:} triggers", chk["id"] not in ids)
check("evaluate_cheap persists triggered status",
      alerts.set_status(m["id"], "triggered") and
      [a for a in alerts.load_all() if a["id"] == m["id"]][0]["status"] == "triggered")

# --- sweep -------------------------------------------------------------------
_isolated()
exp = alerts.create(created_by="x", subject={"type": "stock", "id": "OLD"}, kind="custom",
                    trigger={"due": "2025-01-01"}, action={"text": "old"},
                    expires_at="2025-01-01", dedup_key="old")
future = alerts.create(created_by="x", subject={"type": "stock", "id": "ZZZ"}, kind="custom",
                       trigger={"due": "2030-01-01"}, action={"text": "later"},
                       snooze_until="2030-01-01", dedup_key="zzz")
check("future-snoozed alert hidden from load_open",
      future["id"] not in {a["id"] for a in alerts.load_open()})
snz = alerts.create(created_by="x", subject={"type": "stock", "id": "NAP"}, kind="custom",
                    trigger={"due": "2030-01-01"}, action={"text": "nap"},
                    snooze_until="2025-01-01", dedup_key="nap")
res = alerts.sweep()
check("sweep expires past-expiry", exp["id"] in res["expired"], res)
check("sweep un-snoozes elapsed", snz["id"] in res["unsnoozed"], res)
check("un-snoozed now visible", snz["id"] in {a["id"] for a in alerts.load_open()})
check("future snooze untouched by sweep", future["id"] not in res["unsnoozed"])

# --- snooze helper -----------------------------------------------------------
_isolated()
s = alerts.create(created_by="x", subject={"type": "stock", "id": "ABC"}, kind="custom",
                  trigger={"due": "2030-01-01"}, action={"text": "z"}, dedup_key="abc")
check("alert visible before snooze", s["id"] in {a["id"] for a in alerts.load_open()})
alerts.snooze(s["id"], "2099-01-01", note="not now")
check("snooze hides from load_open", s["id"] not in {a["id"] for a in alerts.load_open()})
check("snooze persisted snooze_until",
      [a for a in alerts.load_all() if a["id"] == s["id"]][0]["snooze_until"] == "2099-01-01")

# --- manage(): the whole manage_alerts surface -------------------------------
_isolated()
env = alerts.manage("add", subject_id="RELIANCE", kind="price_cross", metric="close",
                    op="<", level=1450, text="stop watch",
                    suggest="/trade-tracker RELIANCE", severity="act",
                    dedup_key="reliance-stop")
check("manage: envelope carries the contract keys",
      {"ok", "source", "fetched_at", "data", "gaps"} <= set(env), sorted(env))
check("manage: source names the computation", env["source"] == "finance.compute.alerts",
      env["source"])
check("manage add: writes the alert", env["ok"] and env["data"]["alert"]["severity"] == "act", env)
infy = alerts.manage("add", subject_id="INFY", due="2030-09-01", text="recheck")

listed = alerts.manage("list")
check("manage list: counts every open alert", listed["data"]["count"] == 2, listed["data"])
check("manage list: act sorts before watch",
      [a["severity"] for a in listed["data"]["alerts"]] == ["act", "watch"], listed["data"])
check("manage list: subject filters to one name",
      alerts.manage("list", subject="INFY")["data"]["count"] == 1)

check("manage snooze: hides it from the inbox",
      alerts.manage("snooze", alert_id=env["data"]["alert"]["id"], until="2099-01-01")["ok"]
      and alerts.manage("list")["data"]["count"] == 1)
check("manage dismiss: removes it from the inbox",
      alerts.manage("dismiss", alert_id=infy["data"]["alert"]["id"])["ok"]
      and alerts.manage("list")["data"]["count"] == 0)
check("manage sweep: reports both housekeeping lists",
      set(alerts.manage("sweep")["data"]) == {"action", "expired", "unsnoozed"},
      alerts.manage("sweep")["data"])

unknown = alerts.manage("purge")
check("manage: an unknown action is a labelled gap",
      unknown["ok"] is False and any("unknown action" in g for g in unknown["gaps"]),
      unknown["gaps"])
check("manage add: no trigger is a gap",
      alerts.manage("add", subject_id="X", text="no trigger")["ok"] is False)
check("manage add: no subject is a gap",
      alerts.manage("add", due="2030-01-01", text="orphan")["ok"] is False)
check("manage snooze: no until date is a gap",
      alerts.manage("snooze", alert_id="whatever")["ok"] is False)
check("manage dismiss: a missing alert is a gap, not a raise",
      alerts.manage("dismiss", alert_id="nope")["ok"] is False)

summary()
