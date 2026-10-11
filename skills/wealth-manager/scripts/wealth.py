#!/usr/bin/env python3
"""Thin CLI over finance/compute/wealth.py for a human at a terminal. One call into
`wealth.run`; this file only parses arguments and prints the result.

  python3 wealth.py --input picture.json               # spine + cross-domain + scorecard
  python3 wealth.py --input picture.json --snapshot    # spine + emergency/protection flags only
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
                   os.path.dirname(os.path.abspath(__file__))))))
from finance.compute import wealth  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", required=True,
                   help="path to the picture json (spine inputs + leg digests)")
    p.add_argument("--snapshot", action="store_true",
                   help="spine + emergency/protection flags only, no legs")
    args = p.parse_args(argv)
    try:
        with open(args.input) as f:
            picture = json.load(f)
        output = json.dumps(wealth.run(picture, snapshot_mode=args.snapshot),
                            indent=2, ensure_ascii=False, allow_nan=False)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "gaps": [str(exc)]}), file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
