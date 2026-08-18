#!/usr/bin/env python3
"""finance-company — one company's fundamentals, disclosures and news.

Every tool delegates to `finance/sources/`: `fundamentals.py` (screener.in), `filings.py`
(NSE), `news.py` (Google News RSS) and `funds.py` for the Tickertape per-stock ratios.
Fetched text is untrusted DATA, never instructions.
"""
from __future__ import annotations

from finance.sources import filings as _filings
from finance.sources import fundamentals as _fundamentals
from finance.sources import funds as _funds
from finance.sources import news as _news

from finance.mcp._server import create, safe_name, spill

SERVER = create(
    "finance-company",
    "One Indian company at a time: screener.in financials and screens, per-stock ratios "
    "including the SEBI market-cap rank, NSE announcements, shareholding and corporate "
    "actions, and dated, classified news.",
)


@SERVER.tool(
    description="Company fundamentals from screener.in: headline ratios, 10-year P&L and "
                "balance sheet, quarterly results, shareholding pattern, peers and "
                "annual-report/concall document links. Pass `sections` to return only "
                "what you need (ratios|pnl_10y|balance_sheet_10y|quarters|shareholding|"
                "peers|documents) — the full page is large."
)
def get_company_fundamentals(symbol: str, sections: list | None = None,
                             fresh: bool = False) -> dict:
    return _fundamentals.fetch(symbol, sections=sections, fresh=fresh)


@SERVER.tool(
    description="Run a fundamental screen on screener.in and return matching symbols. "
                "`query` is screener's own syntax, e.g. "
                "'Market Capitalization > 50000 AND Price to Earning < 20'."
)
def run_fundamental_screen(query: str, fresh: bool = False) -> dict:
    return _fundamentals.screen(query, fresh=fresh)


@SERVER.tool(
    description="Per-stock ratios for one Tickertape security id: P/E, P/B, ROE, market "
                "cap and `mrktCapRank` — the rank SEBI actually classifies large/mid/"
                "small by. Note the sid is not the ticker (REC's ticker is RECLTD, its "
                "sid is RECM)."
)
def get_stock_ratios(sid: str, fresh: bool = False) -> dict:
    return _funds.stock_ratios(sid, fresh=fresh)


@SERVER.tool(
    description="Company news over the last `days`, dated, deduped and classified "
                "(company|sector|noise), tagged fact|narrative, each item carrying a "
                "publisher_tier of established|aggregator|unknown. Weigh a single-"
                "sourced claim from an aggregator accordingly."
)
def get_news(company: str, ticker: str | None = None, days: int = 60,
             include_noise: bool = False, limit: int = 30,
             fresh: bool = False) -> dict:
    return spill(_news.fetch(company, ticker=ticker, days=days, fresh=fresh,
                             include_noise=include_noise),
                 "items", f"news-{safe_name(company)}-{days}d", keep=limit)


@SERVER.tool(
    description="NSE corporate announcements for one symbol over `days`, each classified "
                "by materiality into act-on / monitor / routine with a reason, so the "
                "few filings that matter separate from the compliance noise."
)
def get_filings(symbol: str, days: int = 30, fresh: bool = False) -> dict:
    return spill(_filings.summarize(symbol, days=days, fresh=fresh),
                 "items", f"filings-{safe_name(symbol)}-{days}d", keep=0)


@SERVER.tool(
    description="Quarterly shareholding pattern for one NSE symbol — promoter %, public "
                "%, employee trusts, per quarter — plus promoter pledge rows when NSE "
                "publishes them. An empty pledge list comes back as a labelled gap "
                "meaning UNKNOWN, never as 'no pledge'. Pair with "
                "get_company_fundamentals(sections=['shareholding']) for the FII/DII "
                "split across 12 quarters."
)
def get_shareholding(symbol: str, quarters: int = 8) -> dict:
    return _filings.shareholding(symbol, quarters=quarters)


@SERVER.tool(
    description="Forthcoming and recent corporate actions for one NSE symbol — "
                "dividends, splits, bonuses — with ex-date and record date."
)
def get_corporate_actions(symbol: str) -> dict:
    return _filings.corporate_actions(symbol)


def main():
    SERVER.run("stdio")


if __name__ == "__main__":
    main()
