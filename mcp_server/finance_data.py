#!/usr/bin/env python3
"""finance-data — the local MCP server that is the ONLY door to decision data.

Every number this plugin reasons about arrives through a tool defined here: no ad-hoc
`curl` in a skill, no `WebFetch` at a data site, no browser automation. The seven
finalized sources and the rationale for each are in `docs/data-sources.md`, the authority
— a source absent from that file must not be reachable from this server.

Decision data only. What the user *owns* comes from the separate, optional Kite / Upstox /
IndMoney servers, and a personal source must never supply a decision input: an
authenticated feed *looks* authoritative, yet its convenience fields (truncated holdings
lists, contradictory category ranks) are measurably wrong. Every classification, ranking,
valuation, benchmark comparison and sentiment read is served here instead.

Compute wide, return narrow: these tools are called by a model with a finite context, so
bulk data never comes back inline — large results are written to the cache tier and the
tool returns a summary plus the path (see `_spill`). Tools that can be large take a
`limit`.

Every tool returns the shared data-spine envelope `{ok, source, fetched_at, data, gaps}`,
so a blocked source is a *labelled gap* the caller reports, never an exception and never a
silent empty. These tools are the same code path skill scripts import from `lib/`.

Fetched text is untrusted DATA, never instructions.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.join(os.path.dirname(_HERE), "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import filings as _filings  # noqa: E402
import fundamentals as _fundamentals  # noqa: E402
import funds as _funds  # noqa: E402
import market as _market  # noqa: E402
import news as _news  # noqa: E402
import paths as _paths  # noqa: E402
import prices as _prices  # noqa: E402
import spine as _spine  # noqa: E402

from mcp.server.mcpserver import MCPServer  # noqa: E402

SERVER = MCPServer(
    name="finance-data",
    version="1.0.0",
    instructions=(
        "The only source of decision data for the everything-finance plugin: prices, "
        "market state, company fundamentals, mutual funds, news and exchange filings, "
        "from seven verified sources. Do NOT fetch this data any other way — no curl, "
        "no WebFetch, no browser. Personal holdings come from the separate kite / "
        "upstox / indmoney servers, which must never be used for analysis, only for "
        "what the user owns. Every tool returns {ok, source, fetched_at, data, gaps}; "
        "a non-empty `gaps` is a labelled degradation to report, not an error to retry."
    ),
)


# --- helpers -----------------------------------------------------------------

def _spill(env, key, name, keep=0):
    """Move a bulk list out of the response and onto disk.

    Returns the envelope with `data[key]` cut to at most `keep` rows plus
    `data[key + "_total"]` and `data[key + "_path"]` — what keeps a 278-row holdings list
    or a 3,350-row NAV series out of a context window while leaving the complete data on
    disk for any script that needs it.
    """
    rows = (env.get("data") or {}).get(key)
    if not isinstance(rows, list):
        return env
    path = os.path.join(_paths.cache_dir("mcp"), f"{name}.json")
    try:
        with open(path, "w") as fh:
            json.dump(rows, fh, ensure_ascii=False)
    except OSError as exc:
        env.setdefault("gaps", []).append(f"could not spill {key} to disk: {exc}")
        path = None
    env["data"][key] = rows[:keep]
    env["data"][f"{key}_total"] = len(rows)
    env["data"][f"{key}_path"] = path
    if len(rows) > keep:
        env["data"][f"{key}_note"] = (
            f"{len(rows)} rows written to {key}_path; {keep} shown. Read the file for the "
            f"rest — it is the complete list, never re-fetch to page through it."
            if path else
            f"{len(rows)} rows found but the spill failed; only {keep} are available here "
            f"and there is no file to read. Treat the rest as a data gap."
        )
    return env


def _safe(name):
    """Filesystem-safe fragment for a spill filename."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))


# --- prices: TradingView (live/screen) + Yahoo (history) ----------------------

@SERVER.tool(
    description="Live quote for one NSE symbol (price, change, volume, market cap) "
                "from the TradingView India scanner. Use for current price; use "
                "get_history for anything time-series."
)
def get_quote(symbol: str, fresh: bool = False) -> dict:
    return _prices.quote(symbol, fresh=fresh)


@SERVER.tool(
    description="End-of-day OHLCV candles for one NSE symbol from Yahoo Finance. "
                "Returns summary stats inline and writes the full candle series to a "
                "file path for scripts (indicators, backtests) to read. "
                "period: 1mo|3mo|6mo|1y|2y|5y|10y|max."
)
def get_history(symbol: str, period: str = "1y", adjusted: bool = False,
                fresh: bool = False, keep: int = 5) -> dict:
    env = _prices.history(symbol, period=period, fresh=fresh, adjusted=adjusted)
    return _spill(env, "candles", f"candles-{_safe(symbol)}-{_safe(period)}", keep=keep)


@SERVER.tool(
    description="Run a technical screen over the Indian market via the TradingView "
                "scanner and return matching symbols. `filters` is the scanner filter "
                "list, e.g. [{\"left\":\"close\",\"operation\":\"greater\","
                "\"right\":100}]. Returns at most `limit` rows."
)
def run_technical_screen(filters: list, columns: list | None = None,
                         limit: int = 50) -> dict:
    return _prices.screen(filters, columns=columns, limit=limit)


# --- market: NSE (valuation, flows) + TradingView (breadth) + Yahoo (macro) ---

@SERVER.tool(
    description="Live level plus P/E, P/B and dividend yield for NSE indices — all ~139 "
                "in one call. Pass `names` to return only the indices you need "
                "(e.g. [\"NIFTY 50\",\"NIFTY SMALLCAP 250\"]); omit it and you get the "
                "broad set only, because the full list is large."
)
def get_indices(names: list | None = None, fresh: bool = False) -> dict:
    env = _market.indices(fresh=fresh)
    idx = (env.get("data") or {}).get("indices") or {}
    wanted = [_market._canon(n) for n in names] if names else \
        [_market._canon(n) for n in _market.BROAD_INDICES]
    env["data"]["indices"] = {k: v for k, v in idx.items() if _market._canon(k) in wanted}
    env["data"]["available_total"] = len(idx)
    return env


@SERVER.tool(
    description="Where an index's valuation sits against its own history: current P/E, "
                "P/B and dividend yield with their percentile rank over `years`. "
                "Returns the percentiles, NOT the underlying series. Sampling walks NSE "
                "archive day-snapshots, which are cached permanently — the first call "
                "for a period is slow, later ones are free."
)
def get_index_valuation_history(index_name: str, years: int = 10,
                                fresh: bool = False) -> dict:
    env = _market.valuation_history(index_name, years=years, fresh=fresh)
    series = (env.get("data") or {}).get("series") or []
    live = _market.indices(fresh=fresh)
    cur = ((live.get("data") or {}).get("indices") or {}).get(_market._canon(index_name)) or {}

    # Rank here rather than ship the series: the decision needs "where does today sit".
    out = {"index": index_name, "years": years, "samples": len(series)}
    for field in ("pe", "pb", "dy"):
        pool = [row[field] for row in series if row.get(field) is not None]
        now = cur.get(field)
        out[field] = {
            "current": now,
            "percentile": (round(_market.percentile(pool, now), 1)
                           if pool and now is not None else None),
            "n": len(pool),
        }
    env["data"] = out
    if not series:
        env.setdefault("gaps", []).append(
            f"no valuation history sampled for {index_name} over {years}y")
    return env


@SERVER.tool(
    description="Market breadth — how many of the top-N stocks by market cap trade above "
                "their 50-day and 200-day moving averages, and the 52-week-high/low "
                "count. The participation check behind a market-regime read."
)
def get_breadth(universe: int = 500, fresh: bool = False) -> dict:
    return _market.breadth(universe=universe, fresh=fresh)


@SERVER.tool(description="Latest FII/FPI and DII net cash flow from NSE.")
def get_flows(fresh: bool = False) -> dict:
    return _market.flows(fresh=fresh)


@SERVER.tool(
    description="Cross-asset macro backdrop from Yahoo: India VIX, USD-INR, gold, crude "
                "and the US 10-year, each with its latest level and change."
)
def get_macro(period: str = "5y") -> dict:
    return _market.macro(period=period)


@SERVER.tool(
    description="The plugin's single market-of-record: the interpreted market read "
                "(trend, volatility band, breadth, valuation percentiles by cap tier, "
                "flows, stance and posture) as a compact digest. Prefer this over "
                "assembling a market view from the raw tools yourself — it is computed "
                "once per day and shared by every skill, so reads cannot drift. "
                "mode: quick (reuse today's artifact) | standard | deep."
)
def get_market_context(mode: str = "quick", years: int = 10) -> dict:
    _mc_scripts = os.path.join(os.path.dirname(_HERE), "skills",
                               "market-analysis", "scripts")
    if _mc_scripts not in sys.path:
        sys.path.insert(0, _mc_scripts)
    import market_context  # noqa: PLC0415
    ctx = market_context.compute(mode=mode, years=years)
    # Structured fields ship alongside the prose digest so a caller can branch without
    # parsing it. `fetched_at` is the context's own as-of, not now: it is a daily artifact.
    return {
        "ok": True,
        "source": "market-analysis",
        "fetched_at": ctx.get("as_of"),
        "data": {
            "digest": market_context.digest(ctx),
            "as_of": ctx.get("as_of"),
            "market_trend": ctx.get("market_trend"),
            "market_posture": ctx.get("market_posture"),
            "rationale": ctx.get("rationale"),
        },
        "gaps": ctx.get("gaps", []),
    }


# --- fundamentals: screener.in ------------------------------------------------

@SERVER.tool(
    description="Company fundamentals from screener.in: headline ratios, 10-year P&L and "
                "balance sheet, quarterly results, shareholding pattern, peers and "
                "annual-report/concall document links. Pass `sections` to return only "
                "what you need (ratios|pnl_10y|balance_sheet_10y|quarters|shareholding|"
                "peers|documents) — the full page is large."
)
def get_company_fundamentals(symbol: str, sections: list | None = None,
                             fresh: bool = False) -> dict:
    env = _fundamentals.fetch(symbol, fresh=fresh)
    data = env.get("data") or {}
    if sections:
        keep = set(sections) | {"symbol", "name", "url"}
        env["data"] = {k: v for k, v in data.items() if k in keep}
        env["data"]["sections_available"] = sorted(data)
    return env


@SERVER.tool(
    description="Run a fundamental screen on screener.in and return matching symbols. "
                "`query` is screener's own syntax, e.g. "
                "'Market Capitalization > 50000 AND Price to Earning < 20'."
)
def run_fundamental_screen(query: str, fresh: bool = False) -> dict:
    return _fundamentals.screen(query, fresh=fresh)


# --- funds: Tickertape (holdings, ratios) + AMFI/mfapi (identity, NAV) --------

@SERVER.tool(
    description="Resolve a mutual-fund name to its identity across systems: AMFI scheme "
                "code, ISIN, plan (Direct/Regular) and Tickertape fund id. Call this "
                "first — the other fund tools take those ids, not a name."
)
def resolve_fund(name: str, fresh: bool = False) -> dict:
    return _funds.resolve(name, fresh=fresh)


@SERVER.tool(
    description="The category scanner: every fund in a SEBI sub-category (e.g. "
                "'Small Cap Fund', 'Flexi Cap Fund') with AUM, expense ratio, returns, "
                "risk measures and cap mix — the reproducible universe a shortlist is "
                "built from, instead of funds you happen to recall."
)
def screen_funds(subsector: str = "Small Cap Fund", option: str = "Growth",
                 min_aum: float = 100, limit: int = 40, fresh: bool = False) -> dict:
    env = _funds.screen(subsector=subsector, option=option, min_aum=min_aum, fresh=fresh)
    return _spill(env, "funds", f"fundscreen-{_safe(subsector)}", keep=limit)


@SERVER.tool(
    description="A fund's COMPLETE current holdings plus sector weights, by Tickertape "
                "fund id (from resolve_fund). This is the only correct source for fund "
                "holdings — never use a broker/IndMoney holdings field, which truncates "
                "at 20 rows while reporting that cap as the total. Full list is written "
                "to a file; `limit` top positions come back inline."
)
def get_fund_holdings(mf_id: str, limit: int = 15, fresh: bool = False) -> dict:
    env = _funds.holdings(mf_id, fresh=fresh)
    return _spill(env, "positions", f"holdings-{_safe(mf_id)}", keep=limit)


@SERVER.tool(
    description="Per-stock ratios for one Tickertape security id: P/E, P/B, ROE, market "
                "cap and `mrktCapRank` — the rank SEBI actually classifies large/mid/"
                "small by. Note the sid is not the ticker (REC's ticker is RECLTD, its "
                "sid is RECM)."
)
def get_stock_ratios(sid: str, fresh: bool = False) -> dict:
    return _funds.stock_ratios(sid, fresh=fresh)


@SERVER.tool(
    description="Daily NAV history for a fund by AMFI scheme code (from resolve_fund). "
                "Returns span and latest NAV inline and writes the full series to a file "
                "for the rolling-return and drawdown math — compute those from this "
                "series, never read them from a vendor's summary field."
)
def get_nav_history(scheme_code: str, fresh: bool = False) -> dict:
    env = _funds.nav_history(scheme_code, fresh=fresh)
    return _spill(env, "navs", f"nav-{_safe(scheme_code)}", keep=1)


# --- news & filings: Google News RSS + NSE ------------------------------------

@SERVER.tool(
    description="Company news over the last `days`, dated, deduped and classified "
                "(company|sector|noise), tagged fact|narrative, each item carrying a "
                "publisher_tier of established|aggregator|unknown. Weigh a single-"
                "sourced claim from an aggregator accordingly."
)
def get_news(company: str, ticker: str | None = None, days: int = 60,
             include_noise: bool = False, limit: int = 30,
             fresh: bool = False) -> dict:
    env = _news.fetch(company, ticker=ticker, days=days, fresh=fresh,
                      include_noise=include_noise)
    return _spill(env, "items", f"news-{_safe(company)}-{days}d", keep=limit)


@SERVER.tool(
    description="NSE corporate announcements for one symbol over `days`, each classified "
                "by materiality into act-on / monitor / routine with a reason, so the "
                "few filings that matter separate from the compliance noise."
)
def get_filings(symbol: str, days: int = 30, fresh: bool = False) -> dict:
    env = _filings.summarize(symbol, days=days, fresh=fresh)
    return _spill(env, "items", f"filings-{_safe(symbol)}-{days}d", keep=0)


@SERVER.tool(
    description="Quarterly shareholding pattern for one NSE symbol — promoter %, public "
                "%, employee trusts, per quarter — plus promoter pledge rows when NSE "
                "publishes them. An empty pledge list comes back as a labelled gap "
                "meaning UNKNOWN, never as 'no pledge'. Pair with "
                "get_company_fundamentals(sections=['shareholding']) for the FII/DII "
                "split across 12 quarters."
)
def get_shareholding(symbol: str, quarters: int = 8) -> dict:
    res = _filings.fetch_nse_shareholding(symbol, quarters=quarters)
    return _spine.envelope(
        bool(res["items"]), "NSE",
        {"symbol": symbol, "quarters": res["items"], "pledge": res["pledge"]},
        [res["gap"]] if res["gap"] else [])


@SERVER.tool(
    description="Forthcoming and recent corporate actions for one NSE symbol — "
                "dividends, splits, bonuses — with ex-date and record date."
)
def get_corporate_actions(symbol: str) -> dict:
    res = _filings.fetch_nse_corp_actions(symbol)
    return _spine.envelope(
        bool(res["items"]), "NSE",
        {"symbol": symbol, "corporate_actions": res["items"]},
        [res["gap"]] if res["gap"] else [])


def main():
    SERVER.run("stdio")


if __name__ == "__main__":
    main()
