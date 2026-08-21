#!/usr/bin/env python3
"""Thin CLI over finance/compute/allocation.py for a human at a terminal. One call into
`allocation.review_book`; this file only parses arguments and prints the result.

  python3 allocation.py --book book.json   # {holdings, targets?, breakdowns?, thresholds?}
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
                   os.path.dirname(os.path.abspath(__file__))))))
from finance.compute import allocation  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--book", required=True,
                   help="JSON: {holdings:[...], targets?:{}, breakdowns?:{}, thresholds?:{}}")
    args = p.parse_args(argv)
    with open(args.book) as f:
        book = json.load(f)
    json.dump(allocation.review_book(book), sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
