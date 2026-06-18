#!/usr/bin/env python3
"""One-time migration of an old flat ./artifacts/ tree into the layout `paths.py`
now owns. Best-effort: it classifies each file by the old naming convention and
moves it; anything it cannot confidently place is left where it is and reported.

    python3 lib/migrate_artifacts.py            # dry-run (default): print the plan
    python3 lib/migrate_artifacts.py --apply    # actually move files

Run once per workspace from the directory that holds ./artifacts. Not wired into
any hook.
"""
import argparse
import os
import re
import shutil
import sys

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# singleton-skill basenames in an old date dir -> destination skill dir
_SINGLETON = {
    "daily-brief": "daily-brief",
    "regime": "regime",
    "find-trade": "find-trade",
    "portfolio-review": "portfolio-review",
    "trade-tracker": "trade-tracker",
    "insurance": "insurance",
    "insurance-check": "insurance",
}


def _stock_dest(name, date):
    """Classify a file/dir inside a date bucket that belongs to a stock entity.
    Returns the destination relative to root, or None."""
    base, ext = os.path.splitext(name)
    if name.endswith("-deep-analysis.md"):
        t = name[:-len("-deep-analysis.md")]
        return f"stocks/{t}/{date}/deep-analysis.md"
    if base.endswith("-deep-analysis") and ext == "":  # the agents/ work-paper dir
        t = base[:-len("-deep-analysis")]
        return f"stocks/{t}/{date}/deep-analysis"
    if name.endswith("-filings.md"):
        t = name[:-len("-filings.md")]
        return f"stocks/{t}/{date}/filings.md"
    if name.startswith("dcf-"):
        rest = name[len("dcf-"):]
        for suf, out in (("-inputs.yml", "dcf-inputs.yml"), (".json", "dcf.json"),
                         (".md", "dcf.md")):
            if rest.endswith(suf):
                t = rest[:-len(suf)]
                return f"stocks/{t}/{date}/{out}"
    if name.startswith("management-") and name.endswith(".md"):
        t = name[len("management-"):-len(".md")]
        return f"stocks/{t}/{date}/management.md"
    return None


def _date_bucket_dest(name, date):
    """Destination for a file/dir inside an old artifacts/<date>/ bucket, or None."""
    stock = _stock_dest(name, date)
    if stock:
        return stock
    base, ext = os.path.splitext(name)
    if base in _SINGLETON:
        return f"{_SINGLETON[base]}/{date}{ext}"
    if base in _SINGLETON and ext == "":  # work-paper dir for a singleton
        return f"{_SINGLETON[base]}/{date}"
    return None


def plan(root):
    """Return (moves, unclassified). moves is [(src_abs, dest_abs)]; unclassified is
    [(src_abs, reason)]. Nothing is touched."""
    moves, unclassified = [], []

    def add(src, dest_rel):
        moves.append((src, os.path.join(root, dest_rel)))

    for entry in sorted(os.listdir(root)):
        src = os.path.join(root, entry)
        if entry in ("stocks", "funds", "state", "cache", "tmp"):
            continue  # already-migrated tiers
        if _DATE.match(entry) and os.path.isdir(src):
            for item in sorted(os.listdir(src)):
                dest = _date_bucket_dest(item, entry)
                isrc = os.path.join(src, item)
                if dest:
                    add(isrc, dest)
                else:
                    unclassified.append((isrc, "unrecognised name in date bucket"))
            continue
        if entry == "strategies" and os.path.isdir(src):
            for f in sorted(os.listdir(src)):
                add(os.path.join(src, f), f"state/strategies/{f}")
            continue
        if entry == "trades" and os.path.isdir(src):
            for f in sorted(os.listdir(src)):
                add(os.path.join(src, f), f"state/trades/{f}")
            continue
        if entry == ".cache" and os.path.isdir(src):
            for f in sorted(os.listdir(src)):
                add(os.path.join(src, f), f"cache/{f}")
            continue
        if entry == ".staging" and os.path.isdir(src):
            for f in sorted(os.listdir(src)):
                add(os.path.join(src, f), f"tmp/staging/{f}")
            continue
        if entry == "watchlist.json":
            add(src, "state/watchlist.json")
            continue
        unclassified.append((src, "top-level entry with no migration rule"))

    return moves, unclassified


def apply(moves):
    for src, dest in moves:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(src, dest)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default="artifacts", help="old artifacts root (default: ./artifacts)")
    p.add_argument("--apply", action="store_true", help="perform the moves (default: dry-run)")
    args = p.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"no artifacts dir at {root} — nothing to migrate")
        return 0

    moves, unclassified = plan(root)
    rel = lambda p: os.path.relpath(p, root)
    print(f"{'APPLYING' if args.apply else 'DRY-RUN'} — {len(moves)} move(s), "
          f"{len(unclassified)} left in place\n")
    for src, dest in moves:
        print(f"  move  {rel(src)}  ->  {rel(dest)}")
    for src, reason in unclassified:
        print(f"  keep  {rel(src)}  ({reason})")

    if args.apply:
        apply(moves)
        print("\ndone.")
    else:
        print("\nre-run with --apply to perform these moves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
