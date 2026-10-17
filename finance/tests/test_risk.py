#!/usr/bin/env python3
"""Offline unit tests for finance/sources/risk.py (India DCF discount-rate inputs)."""
import atexit
import contextlib
import os
import shutil
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

_TMP_ROOT = tempfile.mkdtemp(prefix="ef-test-risk-")
os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = os.path.join(_TMP_ROOT, "artifacts")
atexit.register(shutil.rmtree, _TMP_ROOT, True)

from finance import deps, transport  # noqa: E402
from finance.sources import risk  # noqa: E402
from finance.tests.harness import check, run  # noqa: E402


@contextlib.contextmanager
def swap(module, attr, fake):
    orig = getattr(module, attr)
    setattr(module, attr, fake)
    try:
        yield
    finally:
        setattr(module, attr, orig)


def _workbook(path, india=True, mature=0.0423):
    """The ERPs-by-country sheet as Damodaran lays it out (dummy values)."""
    openpyxl = deps.need("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ERPs by country"
    ws.append(["Country and Equity Risk Premiums"])
    ws.append(["Date of update:", datetime(2026, 1, 1)])
    ws.append(["Enter the current risk premium for a mature equity market", None, None, None,
               mature])
    ws.append([None])
    ws.append(["Country", "Africa", "Moody's rating", "Rating-based Default Spread",
               "Total Equity Risk Premium", "Country Risk Premium",
               "Sovereign CDS, net of Swiss CDS", "Total Equity Risk Premium2",
               "Country Risk Premium3"])
    ws.append(["Albania", "Eastern Europe", "Ba3", 0.0306, 0.0889, 0.0466, "NA", "NA", "NA"])
    if india:
        ws.append(["India", "Asia", "Baa3", 0.0187, 0.0708, 0.0285, 0.0066, 0.0524, 0.0101])
    wb.save(path)


def test_parse_reads_the_india_row_by_label():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "ctryprem.xlsx")
        _workbook(path)
        row, gap = risk.parse_country_risk(path)
    check("no gap on a complete workbook", gap is None, gap)
    check("vintage read from 'Date of update'", row["as_of"] == "2026-01-01", row)
    check("rating-based columns, not the CDS-based duplicates",
          row["default_spread"] == 0.0187 and row["country_risk_premium"] == 0.0285
          and row["total_equity_risk_premium"] == 0.0708, row)
    check("mature-market ERP read from its labelled row", row["mature_erp"] == 0.0423, row)
    check("Moody's rating carried", row["rating"] == "Baa3", row)


def test_parse_missing_country_or_field_is_a_gap():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "ctryprem.xlsx")
        _workbook(path, india=False)
        row, gap = risk.parse_country_risk(path)
        check("absent country -> no row, labelled gap", row is None and "India" in gap, gap)
        _workbook(path, mature="n/a")
        row, gap = risk.parse_country_risk(path)
        check("unreadable mature ERP -> named in the gap, not invented",
              row["mature_erp"] is None and "mature_erp" in gap, gap)
        bad = os.path.join(d, "bad.xlsx")
        open(bad, "w").write("<html>blocked</html>")
        row, gap = risk.parse_country_risk(bad)
        check("an HTML block page is a gap, not a crash", row is None and "unreadable" in gap, gap)


def test_fetch_derives_default_free_rate_only_from_both_halves():
    def fake_json(url, **kw):
        return {"data": [{"s": "TVC:IN10Y", "d": [7.385, "India 10 Year"]}]}, None

    def fake_request(url, dest=None, **kw):
        _workbook(dest)
        return dest, None

    with swap(transport, "json_request", fake_json), swap(transport, "request", fake_request):
        env = risk.fetch(fresh=True)
    data = env["data"]
    check("envelope ok with no gaps", env["ok"] and env["gaps"] == [], env["gaps"])
    check("yield converted to a decimal with its source",
          data["india_10y"]["value"] == 0.07385 and "TVC:IN10Y" in data["india_10y"]["source"])
    check("default-free rate = yield − default spread",
          data["default_free_risk_free"] == round(0.07385 - 0.0187, 6), data)

    def blocked(url, **kw):
        return None, "HTTP 403"

    with swap(transport, "json_request", blocked), swap(transport, "request", fake_request):
        env = risk.fetch(fresh=True)
    check("a failed yield is a labelled gap and the rate is not derived",
          env["data"]["india_10y"] is None and env["data"]["default_free_risk_free"] is None
          and any("10Y" in g for g in env["gaps"]), env["gaps"])
    check("the other half still comes back", env["ok"] and env["data"]["country_risk"])

    def junk(url, **kw):
        return {"data": [{"s": "TVC:IN10Y", "d": [None, "x"]}]}, None

    with swap(transport, "json_request", junk), swap(transport, "request", fake_request):
        env = risk.fetch(fresh=True)
    check("a null close is a gap, never a zero yield", env["data"]["india_10y"] is None)


def test_yield_refreshes_daily_while_the_country_vintage_is_reused():
    import json
    from datetime import date, timedelta
    from finance import paths
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    folder = paths.cache_dir("risk")
    for name, row in (("india-10y", {"value": 0.07, "as_of": yesterday, "source": "TradingView TVC:IN10Y"}),
                      ("country-risk", {"default_spread": 0.0187, "mature_erp": 0.0423,
                                        "country_risk_premium": 0.0285, "as_of": "2026-01-01"})):
        with open(os.path.join(folder, f"{name}.json"), "w") as fh:
            json.dump({"data": {"row": row, "_cached_on": yesterday}}, fh)
    downloads = []

    def fake_json(url, **kw):
        return {"data": [{"s": "TVC:IN10Y", "d": [7.40, "India 10 Year"]}]}, None

    def no_download(url, dest=None, **kw):
        downloads.append(url)
        return None, "should not download"

    with swap(transport, "json_request", fake_json), swap(transport, "request", no_download):
        env = risk.fetch()
    check("yesterday's yield is refetched", env["data"]["india_10y"]["value"] == 0.074, env["data"])
    check("a day-old country vintage is reused without a download",
          downloads == [] and env["data"]["country_risk"]["mature_erp"] == 0.0423, downloads)


if __name__ == "__main__":
    run(globals())
