#!/usr/bin/env python3
"""Thin CLI over lib/alerts.py — the documented owner of the alert contract (the
way strategy-manager owns specs). All real logic lives in lib/alerts.py; this just
exposes it on the command line for the skill.

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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "lib"))
import alerts  # noqa: E402

_SEV_ORDER = {"act": 0, "watch": 1, "info": 2}


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


def cmd_list(args):
    items = alerts.load_open(args.subject)
    if not items:
        print("no open alerts.")
        return 0
    items.sort(key=lambda a: (_SEV_ORDER.get(a.get("severity"), 9), a["subject"]["id"]))
    cur = None
    for a in items:
        sub = a["subject"]["id"]
        if sub != cur:
            print(f"\n{sub}:")
            cur = sub
        print(_fmt(a))
    print(f"\n{len(items)} open alert(s).")
    return 0


def cmd_dismiss(args):
    r = alerts.set_status(args.id, "done", note="dismissed via alert-manager")
    print("dismissed." if r else f"no alert {args.id}")
    return 0 if r else 1


def cmd_snooze(args):
    r = alerts.snooze(args.id, args.until, note="snoozed via alert-manager")
    print(f"snoozed until {args.until}." if r else f"no alert {args.id}")
    return 0 if r else 1


def cmd_sweep(args):
    res = alerts.sweep()
    print(f"expired: {len(res['expired'])}  un-snoozed: {len(res['unsnoozed'])}")
    for i in res["expired"]:
        print(f"  expired   {i}")
    for i in res["unsnoozed"]:
        print(f"  unsnoozed {i}")
    return 0


def cmd_add(args):
    if args.metric:
        trigger = {"metric": args.metric, "op": args.op, "level": args.level}
    elif args.due:
        trigger = {"due": args.due}
    elif args.check:
        trigger = {"check": args.check}
    else:
        print("error: one of --metric/--op/--level, --due, or --check is required",
              file=sys.stderr)
        return 2
    action = {"text": args.text}
    if args.suggest:
        action["suggest"] = args.suggest
    a = alerts.create(
        created_by=args.created_by,
        subject={"type": args.subject_type, "id": args.subject_id},
        kind=args.kind, trigger=trigger, action=action, severity=args.severity,
        expires_at=args.expires, dedup_key=args.dedup_key)
    print(f"created {a['id']}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list"); pl.add_argument("--subject"); pl.set_defaults(fn=cmd_list)
    pd = sub.add_parser("dismiss"); pd.add_argument("id"); pd.set_defaults(fn=cmd_dismiss)
    ps = sub.add_parser("snooze"); ps.add_argument("id"); ps.add_argument("until")
    ps.set_defaults(fn=cmd_snooze)
    pw = sub.add_parser("sweep"); pw.set_defaults(fn=cmd_sweep)

    pa = sub.add_parser("add")
    pa.add_argument("--created-by", default="alert-manager")
    pa.add_argument("--subject-type", default="stock",
                    choices=["stock", "fund", "strategy", "portfolio"])
    pa.add_argument("--subject-id", required=True)
    pa.add_argument("--kind", default="custom")
    pa.add_argument("--metric"); pa.add_argument("--op"); pa.add_argument("--level", type=float)
    pa.add_argument("--due"); pa.add_argument("--check")
    pa.add_argument("--text", required=True); pa.add_argument("--suggest")
    pa.add_argument("--severity", default="watch", choices=["info", "watch", "act"])
    pa.add_argument("--expires"); pa.add_argument("--dedup-key")
    pa.set_defaults(fn=cmd_add)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
