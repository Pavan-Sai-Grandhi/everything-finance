#!/usr/bin/env python3
"""Thin CLI over finance/compute/insurance_math.py for a human at a terminal. One call
into `insurance_math.run`; this file only parses arguments and prints the envelope.

  python3 insurance_math.py term_cover_need '{"annual_income": 2000000, "income_multiple": 15}'
  python3 insurance_math.py health_sum_insured '{"adults": 2, "children": 1, "city_tier": 1}'
  python3 insurance_math.py idv_ncb_sanity '{"ex_showroom": 1000000, "age_years": 3, "quoted_idv": 700000}'
  python3 insurance_math.py marginal_irr_continue '{"surrender_value": 500000, "annual_premium": 100000,
      "remaining_premiums": 5, "years_to_maturity": 10, "maturity_value": 1200000}'
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
                   os.path.dirname(os.path.abspath(__file__))))))
from finance.compute import insurance_math  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("calculation", choices=sorted(insurance_math.CALCULATIONS))
    p.add_argument("inputs", nargs="?", default="{}",
                   help="JSON object of that calculation's keyword inputs")
    args = p.parse_args(argv)
    env = insurance_math.run(args.calculation, json.loads(args.inputs))
    print(json.dumps(env, indent=2))
    return 0 if env["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
