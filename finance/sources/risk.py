"""India discount-rate inputs for the DCF, each with its source and date.

Two sources, each the reference for its number:

- **TradingView** (`TVC:IN10Y` on the global scanner) — the live India 10-year government
  bond yield, the same scanner `get_quote` reads.
- **Damodaran, NYU Stern** (`ctryprem.xlsx`) — India's sovereign rating, rating-based
  default spread and country risk premium, and the mature-market equity risk premium, all
  from one dated vintage. The dataset is refreshed each January with a mid-year update, so
  its own `Date of update` travels with every figure.

Returns the shared envelope. Nothing here is estimated: a number either comes back with its
source and date or the field is absent and named in `gaps`. Fetched bytes are untrusted data.

Reached through get_risk_inputs.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, datetime

from finance import deps, paths, transport
from finance.spine import envelope as _envelope, f as _f, read_cache as _read_cache
from finance.spine import write_cache as _write_cache

_TV_GLOBAL_SCAN = "https://scanner.tradingview.com/global/scan"
_IN10Y = "TVC:IN10Y"
DAMODARAN_CTRYPREM = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/ctryprem.xlsx"
_SOURCE = "TradingView + Damodaran (NYU Stern)"
_ERP_SHEET = "ERPs by country"
# The yield moves every session; Damodaran's dataset is one vintage refreshed a few times a year.
_YIELD_CACHE_DAYS = 0
_COUNTRY_CACHE_DAYS = 7


def _cached(name, fresh, max_age_days, fetcher, gaps):
    """One half of the inputs, from its own cache when young enough, else `fetcher()`."""
    path = os.path.join(paths.cache_dir("risk"), f"{name}.json")
    cached = _read_cache(path, fresh, max_age_days=max_age_days)
    if isinstance(cached, dict) and isinstance(cached["data"].get("row"), dict):
        return cached["data"]["row"]
    row, gap = fetcher()
    if gap:
        gaps.append(gap)
    elif row:
        _write_cache(path, {"data": {"row": row}})
    return row


def india_10y():
    """(row, gap): the India 10Y G-sec yield as a decimal, with TradingView's own label."""
    body = {"symbols": {"tickers": [_IN10Y], "query": {"types": []}},
            "columns": ["close", "description"]}
    payload, gap = transport.json_request(
        _TV_GLOBAL_SCAN, payload=body, timeout=20,
        origin="https://www.tradingview.com", referer="https://www.tradingview.com/")
    if gap:
        return None, f"India 10Y yield (TradingView): {gap}"
    rows = payload.get("data") if isinstance(payload, dict) else None
    row = next((r for r in rows or [] if isinstance(r, dict) and r.get("s") == _IN10Y), None)
    vals = row.get("d") if row else None
    pct = _f(vals[0]) if isinstance(vals, list) and len(vals) == 2 else None
    if pct is None or not 0 < pct < 25:
        return None, "India 10Y yield (TradingView): no usable TVC:IN10Y close in the response"
    return {"value": round(pct / 100, 6), "as_of": date.today().isoformat(),
            "source": f"TradingView {_IN10Y}", "label": str(vals[1])[:80]}, None


def parse_country_risk(xlsx_path, country="India"):
    """(row, gap) from a downloaded `ctryprem.xlsx`.

    The sheet is a human-edited workbook, so the parse anchors on labels, not cell addresses:
    the mature-market ERP sits on the row whose text starts "Enter the current risk premium
    for a mature", the vintage on "Date of update:", and the country row's columns are read
    from the header row that begins "Country"."""
    openpyxl = deps.need("openpyxl")
    try:
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 — any unreadable workbook is a labelled gap
        return None, f"Damodaran country-risk workbook unreadable ({type(exc).__name__})"
    try:
        if _ERP_SHEET not in wb.sheetnames:
            return None, f"Damodaran workbook has no '{_ERP_SHEET}' sheet"
        vintage = mature = header = found = None
        for cells in wb[_ERP_SHEET].iter_rows(values_only=True):
            first = cells[0] if cells else None
            text = first.strip() if isinstance(first, str) else ""
            nums = [c for c in cells[1:] if _f(c) is not None and not isinstance(c, bool)]
            if text.startswith("Date of update") and vintage is None:
                stamp = next((c for c in cells[1:] if isinstance(c, (datetime, date))), None)
                vintage = stamp.date().isoformat() if isinstance(stamp, datetime) else (
                    stamp.isoformat() if stamp else None)
            elif text.lower().startswith("enter the current risk premium for a mature") and nums:
                mature = _f(nums[0])
            elif text == "Country" and header is None:
                header = [str(c).strip() if c is not None else "" for c in cells]
            elif header and text == country:
                found = dict(zip(header, cells))
                break
    finally:
        wb.close()

    def col(name):
        v = _f(found.get(name)) if found else None
        return round(v, 6) if v is not None else None

    row = {"country": country, "as_of": vintage, "source": DAMODARAN_CTRYPREM,
           "rating": found.get("Moody's rating") if found else None,
           "default_spread": col("Rating-based Default Spread"),
           "country_risk_premium": col("Country Risk Premium"),
           "total_equity_risk_premium": col("Total Equity Risk Premium"),
           "mature_erp": mature}
    missing = [k for k in ("as_of", "rating", "default_spread", "country_risk_premium",
                           "mature_erp") if row[k] in (None, "")]
    if found is None:
        return None, f"Damodaran workbook has no '{country}' row"
    if missing:
        return row, f"Damodaran country-risk fields not found: {', '.join(missing)}"
    return row, None


def country_risk(country="India"):
    """(row, gap): download the current workbook and parse `country`."""
    with tempfile.TemporaryDirectory(prefix="ctryprem-") as work:
        dest = os.path.join(work, "ctryprem.xlsx")
        got, gap = transport.request(DAMODARAN_CTRYPREM, dest=dest, timeout=60)
        if gap or not got:
            return None, f"Damodaran country-risk download failed ({gap or 'empty response'})"
        return parse_country_risk(dest, country)


def fetch(fresh=False):
    """India DCF discount-rate inputs, each with its source and as-of date.

    `default_free_risk_free` is derived only when both halves arrived: the 10Y yield minus
    the default spread, the rupee rate the valuation reference's WACC build-up starts from.
    The yield is refetched each day; the country-risk vintage is reused for a week."""
    gaps = []
    gsec = _cached("india-10y", fresh, _YIELD_CACHE_DAYS, india_10y, gaps)
    crp = _cached("country-risk", fresh, _COUNTRY_CACHE_DAYS, country_risk, gaps)
    data = {"india_10y": gsec, "country_risk": crp, "default_free_risk_free": None}
    if gsec and crp and crp.get("default_spread") is not None:
        data["default_free_risk_free"] = round(gsec["value"] - crp["default_spread"], 6)
    else:
        gaps.append("default-free rupee rate not derived: needs both the 10Y yield and the "
                    "default spread")
    return _envelope(bool(gsec or crp), _SOURCE, data, gaps)
