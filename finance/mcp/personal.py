#!/usr/bin/env python3
"""finance-personal — deterministic personal-finance arithmetic on figures you supply.

Delegates to `finance/compute/insurance_math.py`. Nothing here fetches: the caller
passes sourced or explicitly assumed inputs and gets a reproducible number back.
"""
from __future__ import annotations

from finance.compute import insurance_math as _insurance_math

from finance.mcp._server import create

SERVER = create(
    "finance-personal",
    "Personal-finance math on figures you supply: term-life cover need, health sum "
    "insured, vehicle IDV/NCB sanity, and the marginal IRR of continuing an in-force "
    "endowment or ULIP.",
)


@SERVER.tool(
    description="Run one insurance calculation on inputs you supply. `calculation` is "
                "term_cover_need (larger of income-replacement and liability+goals, "
                "and the gap vs cover held) | health_sum_insured (base + super top-up, "
                "employer cover at half weight) | idv_ncb_sanity (quoted IDV vs the "
                "age-depreciated band, quoted NCB vs slab entitlement) | expected_ncb "
                "(slab entitlement for a run of claim-free years) | "
                "marginal_irr_continue (IRR of continuing a policy: forgo the "
                "surrender value, pay the remaining premiums, collect at maturity — "
                "compare it to a safe hurdle) | irr (bisection IRR of a cashflow "
                "list). `inputs` is that calculation's keyword mapping. It computes "
                "only what you give it — every figure must be sourced or a stated "
                "assumption."
)
def run_insurance_math(calculation: str, inputs: dict | None = None) -> dict:
    return _insurance_math.run(calculation, inputs)


def main():
    SERVER.run("stdio")


if __name__ == "__main__":
    main()
