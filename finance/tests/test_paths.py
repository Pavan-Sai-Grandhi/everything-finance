#!/usr/bin/env python3
"""Offline tests for the path resolver. No network. Each test runs inside a temp
dir so it never touches a real workspace. Run: python3 finance/tests/test_paths.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance import paths
from finance.tests.harness import check, summary


def _clean_env():
    os.environ.pop("EVERYTHING_FINANCE_ARTIFACTS", None)


# --- root resolution ---------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    _clean_env()
    os.chdir(tmp)
    tmp = os.getcwd()  # resolve macOS /var -> /private/var symlink
    check("root defaults to cwd/artifacts", paths.root() == os.path.join(tmp, "artifacts"),
          paths.root())

with tempfile.TemporaryDirectory() as tmp:
    override = os.path.join(tmp, "elsewhere")
    os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = override
    check("root honours env override", paths.root() == override, paths.root())
    _clean_env()

# --- key normalisation -------------------------------------------------------
check("ticker strips .NS and upper-cases", paths.ticker_key("reliance.NS") == "RELIANCE")
check("scheme slugifies", paths.scheme_key("Parag Parikh Flexi Cap — Direct") ==
      "parag-parikh-flexi-cap-direct", paths.scheme_key("Parag Parikh Flexi Cap — Direct"))

# --- dated helpers create dirs and follow the convention ---------------------
with tempfile.TemporaryDirectory() as tmp:
    _clean_env()
    os.chdir(tmp)
    root = paths.root()

    sd = paths.stock_dir("reliance.NS", "2026-05-01")
    check("stock_dir path", sd == os.path.join(root, "stocks", "RELIANCE", "2026-05-01"), sd)
    check("stock_dir created", os.path.isdir(sd))

    fd = paths.fund_dir("PPFAS Flexi Cap", "2026-05-01")
    check("fund_dir path", fd == os.path.join(root, "funds", "ppfas-flexi-cap", "2026-05-01"), fd)

    rp = paths.report_path("daily-brief", "2026-05-01", "md")
    check("report_path path", rp == os.path.join(root, "daily-brief", "2026-05-01.md"), rp)
    check("report_path parent created", os.path.isdir(os.path.dirname(rp)))

    rp2 = paths.report_path("find-trade", "2026-05-01", ".json")
    check("report_path strips leading dot in ext", rp2.endswith("2026-05-01.json"), rp2)

    ip = paths.insurance_report_path("Term", "2026-05-01")
    check("insurance_report_path per-type path",
          ip == os.path.join(root, "insurance", "term", "2026-05-01.md"), ip)
    check("insurance_report_path parent created", os.path.isdir(os.path.dirname(ip)))

    rd = paths.report_dir("sector-analysis", "2026-05-01")
    check("report_dir created", os.path.isdir(rd) and rd.endswith(os.path.join(
        "sector-analysis", "2026-05-01")), rd)

    bd = paths.backtest_dir("ema-pullback-swing", "2026-05-01")
    check("backtest_dir path", bd == os.path.join(
        root, "backtest", "ema-pullback-swing", "2026-05-01"), bd)

    check("state_dir(strategies)", paths.state_dir("strategies") ==
          os.path.join(root, "state", "strategies"))
    check("alerts_dir", paths.alerts_dir() == os.path.join(root, "state", "alerts"))
    check("watchlist_path", paths.watchlist_path() ==
          os.path.join(root, "state", "watchlist.json"))
    check("cache_dir named", paths.cache_dir("ohlcv") == os.path.join(root, "cache", "ohlcv"))
    check("tmp_dir named", paths.tmp_dir("staging") == os.path.join(root, "tmp", "staging"))

    mmp = paths.merchant_map_path()
    check("merchant_map_path under budget/",
          mmp == os.path.join(root, "budget", "merchant-map.json"), mmp)
    check("merchant_map_path parent created", os.path.isdir(os.path.dirname(mmp)))

# --- sector cache ------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    _clean_env()
    os.chdir(tmp)
    root = paths.root()

    check("sector_key slugifies", paths.sector_key("IT services") == "it-services",
          paths.sector_key("IT services"))
    scp = paths.sector_cache_path("Banking / NBFC")
    check("sector_cache_path under state/sectors",
          scp == os.path.join(root, "state", "sectors", "banking-nbfc.md"), scp)
    check("sector_cache_path parent created", os.path.isdir(os.path.dirname(scp)))

    check("sector_cache_age_days None when absent",
          paths.sector_cache_age_days("pharma") is None)
    with open(paths.sector_cache_path("pharma"), "w") as f:
        f.write("---\ngenerated: 2026-05-01\nrs_class: Leading\n---\nbody\n")
    check("sector_cache_age_days computes from frontmatter",
          paths.sector_cache_age_days("pharma", today="2026-05-31") == 30,
          paths.sector_cache_age_days("pharma", today="2026-05-31"))
    with open(paths.sector_cache_path("auto"), "w") as f:
        f.write("no frontmatter date here\n")
    check("sector_cache_age_days None when undated",
          paths.sector_cache_age_days("auto") is None)

# --- latest_prior ------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    _clean_env()
    os.chdir(tmp)

    check("latest_prior none when no history",
          paths.latest_prior("deep-analysis", "INFY", before="2026-06-01") is None)

    # seed three runs; ask before 2026-06-01 -> newest strictly earlier is 2026-05-10
    for day in ("2026-04-01", "2026-05-10", "2026-06-15"):
        d = paths.stock_dir("INFY", day)
        with open(os.path.join(d, "deep-analysis.md"), "w") as f:
            f.write("x")

    got = paths.latest_prior("deep-analysis", "infy.NS", before="2026-06-01")
    check("latest_prior picks newest strictly-earlier",
          got == os.path.join(paths.stock_dir("INFY", "2026-05-10"), "deep-analysis.md"), got)

    # a dcf run on a day with no dcf.md is not matched
    got2 = paths.latest_prior("dcf", "INFY", before="2026-06-01")
    check("latest_prior None when report file absent for that skill", got2 is None, got2)

    dd = paths.stock_dir("INFY", "2026-05-09")
    with open(os.path.join(dd, "dcf.md"), "w") as f:
        f.write("x")
    check("latest_prior finds dcf.md",
          paths.latest_prior("dcf", "INFY", before="2026-06-01") ==
          os.path.join(dd, "dcf.md"))

# --- deep-analysis's two report modes never share a file ---------------------
# A fundamentals run and a full run on the same day must both survive: the full run carries
# the debate and the verdict, so an overwrite loses the more expensive artifact silently.
check("deep-analysis and fundamentals map to different filenames",
      paths._STOCK_ARTIFACT["deep-analysis"] != paths._STOCK_ARTIFACT["fundamentals"],
      (paths._STOCK_ARTIFACT["deep-analysis"], paths._STOCK_ARTIFACT["fundamentals"]))
check("fundamentals filename is fundamental-analysis.md",
      paths._STOCK_ARTIFACT["fundamentals"] == "fundamental-analysis.md",
      paths._STOCK_ARTIFACT["fundamentals"])
check("the five stock artifact keys map one-to-one onto five files",
      sorted(paths._STOCK_ARTIFACT.values()) ==
      ["dcf.md", "deep-analysis.md", "filings.md", "fundamental-analysis.md", "management.md"],
      sorted(paths._STOCK_ARTIFACT.values()))

with tempfile.TemporaryDirectory() as tmp:
    _clean_env()
    os.chdir(tmp)

    same_day = paths.stock_dir("TCS", "2026-05-20")
    for fname in ("deep-analysis.md", "fundamental-analysis.md"):
        with open(os.path.join(same_day, fname), "w") as f:
            f.write(fname)

    check("both same-day reports survive side by side",
          sorted(os.listdir(same_day)) == ["deep-analysis.md", "fundamental-analysis.md"],
          sorted(os.listdir(same_day)))
    check("full run's file still holds its own content",
          open(os.path.join(same_day, "deep-analysis.md")).read() == "deep-analysis.md")

    got_deep = paths.latest_prior("deep-analysis", "TCS", before="2026-06-01")
    got_fund = paths.latest_prior("fundamentals", "TCS", before="2026-06-01")
    check("latest_prior('deep-analysis') resolves to deep-analysis.md",
          got_deep == os.path.join(same_day, "deep-analysis.md"), got_deep)
    check("latest_prior('fundamentals') resolves to fundamental-analysis.md",
          got_fund == os.path.join(same_day, "fundamental-analysis.md"), got_fund)
    check("the two prior-run lookups do not shadow each other", got_deep != got_fund,
          (got_deep, got_fund))

    # each mode builds on its OWN history: a later fundamentals-only day must not become
    # the prior run for a full analysis, and vice versa.
    fund_only = paths.stock_dir("TCS", "2026-05-25")
    with open(os.path.join(fund_only, "fundamental-analysis.md"), "w") as f:
        f.write("x")
    check("a fundamentals-only day is not the prior deep-analysis run",
          paths.latest_prior("deep-analysis", "TCS", before="2026-06-01") ==
          os.path.join(same_day, "deep-analysis.md"))
    check("a fundamentals-only day IS the prior fundamentals run",
          paths.latest_prior("fundamentals", "TCS", before="2026-06-01") ==
          os.path.join(fund_only, "fundamental-analysis.md"))

    deep_only = paths.stock_dir("TCS", "2026-05-28")
    with open(os.path.join(deep_only, "deep-analysis.md"), "w") as f:
        f.write("x")
    check("a full-run-only day is not the prior fundamentals run",
          paths.latest_prior("fundamentals", "TCS", before="2026-06-01") ==
          os.path.join(fund_only, "fundamental-analysis.md"))

summary()
