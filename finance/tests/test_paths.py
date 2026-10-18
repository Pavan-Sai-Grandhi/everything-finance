#!/usr/bin/env python3
"""Offline tests for the path resolver. No network."""
import json
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

    rd = paths.report_dir("sector-analysis", "2026-05-01")
    check("report_dir created", os.path.isdir(rd) and rd.endswith(os.path.join(
        "sector-analysis", "2026-05-01")), rd)

    bd = paths.backtest_dir("ema-pullback-swing", "2026-05-01")
    check("backtest_dir path", bd == os.path.join(
        root, "backtest", "ema-pullback-swing", "2026-05-01"), bd)

    check("state_dir(strategies)", paths.state_dir("strategies") ==
          os.path.join(root, "state", "strategies"))
    check("alerts_dir", paths.alerts_dir() == os.path.join(root, "state", "alerts"))
    check("cache_dir named", paths.cache_dir("ohlcv") == os.path.join(root, "cache", "ohlcv"))
    check("tmp_dir named", paths.tmp_dir("staging") == os.path.join(root, "tmp", "staging"))

    mmp = paths.merchant_map_path()
    check("merchant_map_path under budget/",
          mmp == os.path.join(root, "budget", "merchant-map.json"), mmp)
    check("merchant_map_path parent created", os.path.isdir(os.path.dirname(mmp)))

def bundle(ticker, day, mode, n):
    """An archived deep-analysis bundle, as publication leaves it."""
    run_id = f"{n:020d}-{'a' * 32}"
    run = os.path.join(paths.stock_dir(ticker, day), "runs", run_id)
    os.makedirs(os.path.join(run, "agents"))
    with open(os.path.join(run, "run.json"), "w") as f:
        json.dump({"mode": mode, "ticker": ticker, "date": day, "run_id": run_id}, f)
    for name in ("report.json", "report.html", "agents/dcf.md"):
        with open(os.path.join(run, name), "w") as f:
            f.write("x")
    return run


with tempfile.TemporaryDirectory() as tmp:
    _clean_env()
    os.chdir(tmp)

    check("latest_prior none when no history",
          paths.latest_prior("deep-analysis", "INFY", before="2026-06-01") is None)
    runs = {day: bundle("INFY", day, "standard", i) for i, day in
            enumerate(("2026-04-01", "2026-05-10", "2026-06-15"))}
    got = paths.latest_prior("deep-analysis", "infy.NS", before="2026-06-01")
    check("latest_prior picks the newest strictly-earlier bundle",
          got == os.path.join(runs["2026-05-10"], "report.json"), got)
    check("a bundle's valuation paper is the prior dcf run",
          paths.latest_prior("dcf", "INFY", before="2026-06-01") ==
          os.path.join(runs["2026-05-10"], "agents", "dcf.md"))
    dd = paths.stock_dir("INFY", "2026-05-11")
    with open(os.path.join(dd, "dcf.md"), "w") as f:
        f.write("x")
    check("a standalone dcf.md on a later day wins",
          paths.latest_prior("dcf", "INFY", before="2026-06-01") == os.path.join(dd, "dcf.md"))
    check("a run-day file named like a deck is not a prior deep-analysis run",
          paths.latest_prior("filings", "INFY", before="2026-06-01") is None)

with tempfile.TemporaryDirectory() as tmp:
    _clean_env()
    os.chdir(tmp)
    deep = bundle("TCS", "2026-05-20", "deep", 1)
    fund = bundle("TCS", "2026-05-25", "fundamentals", 2)
    check("a fundamentals bundle is not the prior deep-analysis run",
          paths.latest_prior("deep-analysis", "TCS", before="2026-06-01") ==
          os.path.join(deep, "report.json"))
    check("a fundamentals bundle IS the prior fundamentals run",
          paths.latest_prior("fundamentals", "TCS", before="2026-06-01") ==
          os.path.join(fund, "report.json"))
    os.remove(os.path.join(fund, "report.html"))
    check("a bundle without its deck is incomplete and skipped",
          paths.latest_prior("fundamentals", "TCS", before="2026-06-01") is None)

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

with tempfile.TemporaryDirectory() as tmp:
    os.chdir(tmp)
    _clean_env()
    for create in (lambda: paths.stock_dir("../ESCAPE"),
                   lambda: paths.stock_dir("TCS", "../elsewhere"),
                   lambda: paths.backtest_dir("../ESCAPE"),
                   lambda: paths.report_path(os.path.join(tmp, "absolute")),
                   lambda: paths.cache_dir("../outside"),
                   lambda: paths.fund_dir("---")):
        try:
            create()
            rejected = False
        except ValueError:
            rejected = True
        check("invalid artifact component is refused before writing", rejected)
    check("nested internal cache namespaces still work",
          paths.cache_dir("tickertape/ratios").endswith("tickertape/ratios"))
    check("monthly budget paths still work",
          paths.report_path("budget", "2026-05", "html").endswith("2026-05.html"))
    invalid = paths.prior_run("dcf", "../ESCAPE")
    check("invalid prior-run subject degrades in its envelope", not invalid["ok"] and invalid["gaps"])


with tempfile.TemporaryDirectory() as tmp:
    os.chdir(tmp)
    _clean_env()
    p = paths.state_dir("trades", create=False)
    check("read-only state lookup returns the authoritative path without creating it",
          p == os.path.join(os.getcwd(), "artifacts", "state", "trades") and not os.path.exists(p))


summary()
