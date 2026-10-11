#!/usr/bin/env python3
"""Thin CLI over finance/compute/insurance_math.py for a human at a terminal. One call
into `insurance_math.run`; this file only parses arguments and prints the envelope.

  python3 insurance_math.py term_cover_need '{"annual_income": 2000000, "income_multiple": 15, "outstanding_loans": 0, "education_corpus": 0, "annual_expenses": 800000, "years_to_independence": 15, "existing_corpus": 0, "existing_cover": 0}'
  python3 insurance_math.py health_sum_insured '{"base_target": 1000000, "total_target": 5000000, "deductible": 1000000, "personal_cover": 500000, "employer_cover": 0}'
  python3 insurance_math.py idv_ncb_sanity '{"ex_showroom": 1000000, "age_years": 3, "quoted_idv": 700000}'
  python3 insurance_math.py marginal_irr_continue '{"surrender_value": 500000, "annual_premium": 100000,
      "remaining_premiums": 5, "years_to_maturity": 10, "maturity_value": 1200000}'
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
                   os.path.dirname(os.path.abspath(__file__))))))
from finance.compute import insurance_math  # noqa: E402


def _json_inputs(text):
    def object_values(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise ValueError("duplicate JSON keys are ambiguous")
            values[key] = value
        return values

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("JSON numbers must be finite")
        return number

    try:
        value = json.loads(text, object_pairs_hook=object_values,
                           parse_float=finite_float, parse_constant=finite_float)
        if not isinstance(value, dict):
            raise ValueError("inputs must be a JSON object")
        return value
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid inputs: {exc}") from None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("calculation", choices=sorted(insurance_math.CALCULATIONS))
    p.add_argument("inputs", nargs="?", default="{}", type=_json_inputs,
                   help="JSON object of that calculation's keyword inputs")
    args = p.parse_args(argv)
    env = insurance_math.run(args.calculation, args.inputs)
    print(json.dumps(env, indent=2, allow_nan=False))
    return 0 if env["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
