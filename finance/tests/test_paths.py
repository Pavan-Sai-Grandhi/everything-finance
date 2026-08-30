#!/usr/bin/env python3
"""Offline tests for the path resolver. No network."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance import paths
from finance.tests.harness import check, summary


def _clean_env():
    os.environ.pop("EVERYTHING_FINANCE_ARTIFACTS", None)


with tempfile.TemporaryDirectory() as tmp:
    _clean_env()
    os.chdir(tmp)
    tmp = os.getcwd()
    check("root defaults to cwd/artifacts", paths.root() == os.path.join(tmp, "artifacts"),
          paths.root())

with tempfile.TemporaryDirectory() as tmp:
    override = os.path.join(tmp, "elsewhere")
    os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = override
    check("root honours env override", paths.root() == override, paths.root())
    _clean_env()

check("ticker strips .NS and upper-cases", paths.ticker_key("reliance.NS") == "RELIANCE")
check("scheme slugifies", paths.scheme_key("Parag Parikh Flexi Cap — Direct") ==
      "parag-parikh-flexi-cap-direct", paths.scheme_key("Parag Parikh Flexi Cap — Direct"))

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

    rp2 = paths.report_path("discover", "2026-05-01", ".json")
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

with tempfile.TemporaryDirectory() as tmp:
    _clean_env()
    os.chdir(tmp)

    check("latest_prior none when no history",
          paths.latest_prior("deep-analysis", "INFY", before="2026-06-01") is None)

    for day in ("2026-04-01", "2026-05-10", "2026-06-15"):
        d = paths.stock_dir("INFY", day)
        with open(os.path.join(d, "deep-analysis.report.json"), "w") as f:
            f.write("x")

    got = paths.latest_prior("deep-analysis", "infy.NS", before="2026-06-01")
    check("latest_prior picks newest strictly-earlier",
          got == os.path.join(paths.stock_dir("INFY", "2026-05-10"), "deep-analysis.report.json"), got)

    got2 = paths.latest_prior("dcf", "INFY", before="2026-06-01")
    check("latest_prior None when report file absent for that skill", got2 is None, got2)

    dd = paths.stock_dir("INFY", "2026-05-09")
    with open(os.path.join(dd, "dcf.md"), "w") as f:
        f.write("x")
    check("latest_prior finds dcf.md",
          paths.latest_prior("dcf", "INFY", before="2026-06-01") ==
          os.path.join(dd, "dcf.md"))

check("deep-analysis and fundamentals map to different filenames",
      paths._STOCK_ARTIFACT["deep-analysis"] != paths._STOCK_ARTIFACT["fundamentals"],
      (paths._STOCK_ARTIFACT["deep-analysis"], paths._STOCK_ARTIFACT["fundamentals"]))
check("fundamentals filename is fundamental-analysis.report.json",
      paths._STOCK_ARTIFACT["fundamentals"] == "fundamental-analysis.report.json",
      paths._STOCK_ARTIFACT["fundamentals"])
check("the five stock artifact keys map one-to-one onto five files",
      sorted(paths._STOCK_ARTIFACT.values()) ==
      ["dcf.md", "deep-analysis.report.json", "filings.md", "fundamental-analysis.report.json", "management.md"],
      sorted(paths._STOCK_ARTIFACT.values()))

with tempfile.TemporaryDirectory() as tmp:
    _clean_env()
    os.chdir(tmp)

    same_day = paths.stock_dir("TCS", "2026-05-20")
    for fname in ("deep-analysis.report.json", "fundamental-analysis.report.json"):
        with open(os.path.join(same_day, fname), "w") as f:
            f.write(fname)

    check("both same-day reports survive side by side",
          sorted(os.listdir(same_day)) == ["deep-analysis.report.json", "fundamental-analysis.report.json"],
          sorted(os.listdir(same_day)))
    check("full run's file still holds its own content",
          open(os.path.join(same_day, "deep-analysis.report.json")).read() == "deep-analysis.report.json")

    got_deep = paths.latest_prior("deep-analysis", "TCS", before="2026-06-01")
    got_fund = paths.latest_prior("fundamentals", "TCS", before="2026-06-01")
    check("latest_prior('deep-analysis') resolves to deep-analysis.report.json",
          got_deep == os.path.join(same_day, "deep-analysis.report.json"), got_deep)
    check("latest_prior('fundamentals') resolves to fundamental-analysis.report.json",
          got_fund == os.path.join(same_day, "fundamental-analysis.report.json"), got_fund)
    check("the two prior-run lookups do not shadow each other", got_deep != got_fund,
          (got_deep, got_fund))

    fund_only = paths.stock_dir("TCS", "2026-05-25")
    with open(os.path.join(fund_only, "fundamental-analysis.report.json"), "w") as f:
        f.write("x")
    check("a fundamentals-only day is not the prior deep-analysis run",
          paths.latest_prior("deep-analysis", "TCS", before="2026-06-01") ==
          os.path.join(same_day, "deep-analysis.report.json"))
    check("a fundamentals-only day IS the prior fundamentals run",
          paths.latest_prior("fundamentals", "TCS", before="2026-06-01") ==
          os.path.join(fund_only, "fundamental-analysis.report.json"))

    deep_only = paths.stock_dir("TCS", "2026-05-28")
    with open(os.path.join(deep_only, "deep-analysis.report.json"), "w") as f:
        f.write("x")
    check("a full-run-only day is not the prior fundamentals run",
          paths.latest_prior("fundamentals", "TCS", before="2026-06-01") ==
          os.path.join(fund_only, "fundamental-analysis.report.json"))

with tempfile.TemporaryDirectory() as tmp:
    _clean_env()
    os.chdir(tmp)

    day = paths.stock_dir("INFY", "2026-05-20")
    with open(os.path.join(day, "dcf.md"), "w") as f:
        f.write("x")

    env = paths.prior_run("dcf", "INFY", before="2026-06-01")
    check("prior_run returns the shared envelope shape",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"}, sorted(env))
    check("prior_run names the computation as its source",
          env["source"] == "finance.paths", env["source"])
    check("prior_run resolves the prior run's path",
          env["data"]["path"] == os.path.join(day, "dcf.md"), env["data"])
    check("prior_run carries the run day beside the path",
          env["data"]["date"] == "2026-05-20", env["data"])
    check("a resolved prior run raises no gap", env["ok"] is True and env["gaps"] == [],
          env["gaps"])

    none_env = paths.prior_run("management", "INFY", before="2026-06-01")
    check("no prior run is ok:true with a null path — a first run is not a degradation",
          none_env["ok"] is True and none_env["data"]["path"] is None, none_env)
    check("no prior run raises no gap either", none_env["gaps"] == [], none_env["gaps"])

    check("prior_run honours `before` exclusively",
          paths.prior_run("dcf", "INFY", before="2026-05-20")["data"]["path"] is None)
    check("prior_run defaults `before` to today",
          paths.prior_run("dcf", "INFY")["data"]["before"] == paths._today())

    bad = paths.prior_run("valuation-analysis", "INFY")
    check("an unresolvable skill key is a labelled gap, not a raise",
          bad["ok"] is False and len(bad["gaps"]) == 1, bad)
    check("the gap names every key that does resolve",
          all(k in bad["gaps"][0] for k in
              ("deep-analysis", "fundamentals", "dcf", "management", "filings",
               "mf-analysis")), bad["gaps"])

    fund_day = paths.fund_dir("Bandhan Small Cap Fund", "2026-05-20")
    with open(os.path.join(fund_day, "mf-analysis.md"), "w") as f:
        f.write("x")
    check("prior_run reaches the fund artifacts too",
          paths.prior_run("mf-analysis", "Bandhan Small Cap Fund",
                          before="2026-06-01")["data"]["path"] ==
          os.path.join(fund_day, "mf-analysis.md"))

summary()
