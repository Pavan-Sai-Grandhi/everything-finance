"""finance-personal: the user's own money, computed from files and figures they supply.

Nothing here reaches a decision source except `check_trade`, which reads market history to
re-validate a trade. Personal payloads arrive as file paths written by the caller.
"""
from __future__ import annotations

from finance.compute import allocation as _allocation
from finance.compute import budget as _budget
from finance.compute import holdings as _holdings
from finance.compute import insurance_math as _insurance_math
from finance.compute import trade_check as _trade_check
from finance.compute import wealth as _wealth

from finance.mcp._server import create, spill

SERVER = create(
    "finance-personal",
    "The user's own money: canonical holdings from broker payloads, the allocation and "
    "concentration review, the net-worth picture and health scorecard, budget "
    "categorization and recurring spend, insurance arithmetic, and open-trade "
    "re-validation.",
)


@SERVER.tool(
    description="Canonical positions from personal-source payload files, precedence "
                "IndMoney -> broker -> watchlist positions. `indmoney` is a list of "
                "networth_holdings payload paths, one per asset_type call (they combine); "
                "`kite`, `upstox`, `broker` are holdings+positions payload paths; "
                "`portfolio` is the watchlist positions block (JSON or YAML). `slice`: "
                "all | equity | mf. `prefer` moves one source to the front. Gaps name "
                "unconnected sources and IndMoney rows held through a linked broker that "
                "carry no cost. Positions spill to `positions_path`."
)
def resolve_holdings(indmoney: list | None = None, kite: str | None = None,
                     upstox: str | None = None, broker: str | None = None,
                     portfolio: str | None = None, prefer: str = "indmoney",
                     slice: str = "all", keep: int = 50) -> dict:
    return spill(_holdings.resolve_files(indmoney=indmoney, kite=kite, upstox=upstox,
                                         broker=broker, portfolio=portfolio, prefer=prefer,
                                         slice=slice),
                 "positions", f"holdings-{slice}", keep=keep)


@SERVER.tool(
    description="Allocation and concentration review of a book. `book` is a JSON file "
                "{holdings, targets?, breakdowns?, thresholds?}: holdings are canonical "
                "positions tagged with sector, market_cap, amc, style, asset_class, kind "
                "and value; breakdowns carry pre-aggregated cap and style splits. Returns "
                "per-dimension breakdowns with coverage, asset-class drift against the "
                "targets, and ranked concentration flags. Rebalancing amounts appear only "
                "when every holding is valued and classified."
)
def review_allocation(book: str) -> dict:
    return _allocation.review_file(book)


@SERVER.tool(
    description="The net-worth spine, cross-domain reads and financial-health scorecard. "
                "`picture` is a JSON file {snapshot, breakdown, positions, liabilities, "
                "legs: {investments, protection, cashflow}, profile} assembled from the "
                "IndMoney payloads, the resolve_holdings envelope and the three leg "
                "digests. `snapshot: true` returns the spine with the emergency-fund and "
                "protection reads only."
)
def run_wealth(picture: str, snapshot: bool = False) -> dict:
    return _wealth.report(picture, snapshot=snapshot)


@SERVER.tool(
    description="Categorize a normalized transactions JSON file (rows of date, "
                "description, amount, direction, account): durable merchant map, then the "
                "taxonomy, then UNCATEGORIZED. Returns spend by bucket and category and "
                "the uncategorized merchants by spend; the annotated rows go to "
                "`result_path`. An unreadable merchant map is a gap and the taxonomy is used."
)
def categorize_transactions(transactions: str, out: str | None = None) -> dict:
    return _budget.categorize_file(transactions, out=out)


@SERVER.tool(
    description="Record one merchant -> category correction in the durable merchant map, "
                "keyed by the merchant token of `merchant` (a narration). The category "
                "must be one the taxonomy supports. Refuses to write over an unreadable map."
)
def learn_merchant(merchant: str, category: str) -> dict:
    return _budget.learn_file(merchant, category)


@SERVER.tool(
    description="Recurring spend in a transactions JSON file spanning the current and "
                "prior months: cadence (monthly, quarterly, annual), confidence, the "
                "committed monthly total, and new / price_creep / dormant flags. `as_of` "
                "(YYYY-MM-DD, default the latest debit) anchors the current month. A "
                "single sighting is a low-confidence candidate outside the total."
)
def detect_recurring(transactions: str, as_of: str | None = None,
                     out: str | None = None) -> dict:
    return _budget.recurring_file(transactions, as_of=as_of, out=out)


@SERVER.tool(
    description="Run one insurance calculation on inputs you supply. `calculation` is "
                "term_cover_need (larger of income-replacement and liability+goals, "
                "and the gap vs cover held; requires annual_income, income_multiple, outstanding_loans, "
                "education_corpus, annual_expenses, years_to_independence, existing_corpus, existing_cover) "
                "| health_sum_insured (explicit base_target, total_target, "
                "deductible, personal_cover, employer_cover; nominal base/top-up and deductible gaps) "
                "| idv_ncb_sanity (quoted IDV vs the "
                "age-depreciated band, quoted NCB vs slab entitlement) | expected_ncb "
                "(slab entitlement for a run of claim-free years) | "
                "marginal_irr_continue (IRR of continuing a policy: forgo the "
                "surrender value, pay the remaining premiums, collect at maturity — "
                "compare only to an explicitly supplied hurdle_rate) | irr (bisection IRR of a cashflow "
                "list). `inputs` is that calculation's keyword mapping. It computes "
                "only what you give it — every figure must be sourced or a stated "
                "assumption."
)
def run_insurance_math(calculation: str, inputs: dict | None = None) -> dict:
    return _insurance_math.run(calculation, inputs)


@SERVER.tool(
    description="Re-validate one open trade against the plan that opened it and return "
                "HOLD or an EXIT_* verdict with its reason: stop breached, thesis "
                "invalidation fired, target reached, or time stop. `trade` is the path to "
                "a trade-idea YAML. Pass the broker's actual fill as `entry` (default: the "
                "recorded fill_avg) and the quantity still held as `qty`. A personal `ltp` "
                "values unrealized P&L only; exit decisions use market price history. "
                "Sessions are counted after entry_date. The verdict is a recommendation, "
                "not proof that an exit happened. Invalidations this cannot "
                "check mechanically come back under `manual_review` for you to judge."
)
def check_trade(trade: str, ohlcv: str | None = None, ltp: float | None = None,
                entry: float | None = None, qty: float | None = None,
                sessions_held: int | None = None) -> dict:
    return _trade_check.check(trade, ohlcv=ohlcv, ltp=ltp, entry=entry, qty=qty,
                              sessions_held=sessions_held)


def main():
    SERVER.run("stdio")


if __name__ == "__main__":
    main()
