#!/usr/bin/env python3
"""The one assertion harness for this plugin's tests.

There is no pytest on the target box, so every test file is a standalone script run as
`python3 <file>`. This module holds the counters, the assertion call, the float
comparators, and the summary line: `bin/test.sh` parses the **last** line of a run with
`sed`, so it must stay exactly `N passed, M failed`.
"""
import sys

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    """Count one assertion. `detail` is printed only when it fails."""
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def approx(a, b, tol=0.01):
    """Absolute float compare. None is not approximately anything."""
    return a is not None and b is not None and abs(a - b) <= tol


def rel_approx(a, b, tol=1e-6):
    """Relative float compare, for values whose magnitude is not known up front."""
    return (a is not None and b is not None
            and abs(a - b) <= tol * max(1.0, abs(a), abs(b)))


def summary():
    """Print the count line bin/test.sh parses, then exit non-zero on any failure."""
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


def run(tests):
    """Run test functions in order and summarize.

    `tests` is either a namespace dict — every top-level `test_*` callable in it, in
    name order — or an explicit sequence of functions when order is load-bearing.
    """
    if isinstance(tests, dict):
        tests = [fn for name, fn in sorted(tests.items())
                 if name.startswith("test_") and callable(fn)]
    for fn in tests:
        print(f"\n[{fn.__name__}]")
        fn()
    summary()
