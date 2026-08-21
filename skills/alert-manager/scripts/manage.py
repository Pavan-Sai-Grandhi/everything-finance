#!/usr/bin/env python3
"""Thin CLI over finance/compute/alerts.py for a human at a terminal. Every operation
is one call into `alerts.manage`; this file only parses arguments and prints.

  python3 manage.py list [--subject RELIANCE]
  python3 manage.py dismiss <id>
  python3 manage.py snooze <id> <YYYY-MM-DD>
  python3 manage.py sweep
  python3 manage.py add --subject-type stock --subject-id RELIANCE --kind price_cross \
      --metric close --op "<" --level 1450 --text "stop hit" --suggest "/trade-tracker RELIANCE" \
      --severity act --dedup-key reliance-stop
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
                   os.path.dirname(os.path.abspath(__file__))))))
from finance.compute import alerts  # noqa: E402


def _fmt(a):
    trig = a.get("trigger", {})
    if "metric" in trig:
        t = f"{trig['metric']} {trig.get('op')} {trig.get('level')}"
    elif "due" in trig:
        t = f"due {trig['due']}"
    elif "check" in trig:
        t = f"check via {trig['check']}"
    else:
        t = "?"
    suggest = a.get("action", {}).get("suggest")
    line = (f"  [{a.get('severity', 'watch')}] {a['id']}  ({a['subject']['id']})  "
            f"{a.get('kind')}  — {a.get('action', {}).get('text', '')}  «{t}»")
    return line + (f"   → {suggest}" if suggest else "")


def _print(env):
    data = env["data"]
    for gap in env["gaps"]:
        print(gap, file=sys.stderr)
    action = data.get("action")
    if action == "list":
        cur = None
        for a in data["alerts"]:
            sub = a["subject"]["id"]
            if sub != cur:
                print(f"\n{sub}:")
                cur = sub
            print(_fmt(a))
        print(f"\n{data['count']} open alert(s).")
    elif action == "sweep":
        print(f"expired: {len(data['expired'])}  un-snoozed: {len(data['unsnoozed'])}")
        for i in data["expired"]:
            print(f"  expired   {i}")
        for i in data["unsnoozed"]:
            print(f"  unsnoozed {i}")
    elif env["ok"]:
        print(f"{action}: {data['alert']['id']}")
    return 0 if env["ok"] else 1


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list"); pl.add_argument("--subject")
    pd = sub.add_parser("dismiss"); pd.add_argument("alert_id")
    ps = sub.add_parser("snooze"); ps.add_argument("alert_id"); ps.add_argument("until")
    sub.add_parser("sweep")

    pa = sub.add_parser("add")
    pa.add_argument("--created-by", default="alert-manager")
    pa.add_argument("--subject-type", default="stock",
                    choices=["stock", "fund", "strategy", "portfolio"])
    pa.add_argument("--subject-id")
    pa.add_argument("--kind", default="custom")
    pa.add_argument("--metric"); pa.add_argument("--op"); pa.add_argument("--level", type=float)
    pa.add_argument("--due"); pa.add_argument("--check")
    pa.add_argument("--text"); pa.add_argument("--suggest")
    pa.add_argument("--severity", default="watch", choices=["info", "watch", "act"])
    pa.add_argument("--expires", dest="expires_at"); pa.add_argument("--dedup-key")

    args = vars(p.parse_args(argv))
    return _print(alerts.manage(args.pop("cmd"), **args))


if __name__ == "__main__":
    sys.exit(main())
