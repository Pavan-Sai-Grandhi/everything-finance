#!/usr/bin/env python3
"""Offline unit tests for lib/fundamentals.py (the data-spine fundamentals fetcher).

Deterministic, no network — the screener.in parsers run against a saved page fixture,
mirroring test_prices.py / test_news.py / test_filings.py / test_ta.py. Each test names the
section-D acceptance criterion it proves. Run:
    python3 lib/test_fundamentals.py   # exits 0
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fundamentals as fz  # noqa: E402

_passed = 0
_failed = 0


def check(name, cond, extra=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ok   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name} {extra}")


# --- saved fixture: a trimmed screener.in consolidated company page --------- #
COMPANY_FIXTURE = """<!doctype html><html><body>
<ul id="top-ratios">
  <li><span class="name">Market Cap</span><span class="value"> ₹ <span class="number">19,89,000</span> Cr.</span></li>
  <li><span class="name">Current Price</span><span class="value"> ₹ <span class="number">2,951</span></span></li>
  <li><span class="name">High / Low</span><span class="value"> ₹ <span class="number">3,217</span> / <span class="number">2,221</span></span></li>
  <li><span class="name">Stock P/E</span><span class="value"><span class="number">24.3</span></span></li>
</ul>

<section id="profit-loss"><h2>Profit &amp; Loss</h2>
<div class="responsive-holder"><table class="data-table">
<thead><tr><th class="text"></th><th>Mar 2022</th><th>Mar 2023</th><th>Mar 2024</th><th>TTM</th></tr></thead>
<tbody>
<tr><td class="text">Sales&nbsp;+</td><td>7,21,634</td><td>8,76,396</td><td>9,01,064</td><td>9,64,693</td></tr>
<tr><td class="text">Net Profit&nbsp;+</td><td>60,705</td><td>66,702</td><td>69,621</td><td>79,020</td></tr>
<tr><td class="text">EPS in Rs</td><td>89.78</td><td>98.62</td><td>102.94</td><td>116.84</td></tr>
</tbody></table></div></section>

<section id="balance-sheet"><h2>Balance Sheet</h2>
<table class="data-table">
<thead><tr><th class="text"></th><th>Mar 2022</th><th>Mar 2023</th><th>Mar 2024</th></tr></thead>
<tbody>
<tr><td class="text">Total Liabilities</td><td>15,99,964</td><td>16,84,371</td><td>17,55,986</td></tr>
<tr><td class="text">Borrowings&nbsp;+</td><td>2,66,305</td><td>3,15,506</td><td>3,24,059</td></tr>
</tbody></table></section>

<section id="quarters"><h2>Quarterly Results</h2>
<table class="data-table">
<thead><tr><th class="text"></th><th>Dec 2023</th><th>Mar 2024</th><th>Jun 2024</th></tr></thead>
<tbody>
<tr><td class="text">Sales&nbsp;+</td><td>2,48,160</td><td>2,64,834</td><td>2,57,823</td></tr>
<tr><td class="text">Net Profit&nbsp;+</td><td>19,641</td><td>21,243</td><td>17,448</td></tr>
</tbody></table></section>

<section id="shareholding"><h2>Shareholding Pattern</h2>
<table class="data-table">
<thead><tr><th class="text"></th><th>Mar 2024</th><th>Jun 2024</th></tr></thead>
<tbody>
<tr><td class="text">Promoters&nbsp;+</td><td>50.30</td><td>50.31</td></tr>
<tr><td class="text">FIIs&nbsp;+</td><td>22.06</td><td>21.92</td></tr>
<tr><td class="text">Public&nbsp;+</td><td>11.45</td><td>11.50</td></tr>
</tbody></table></section>

<section id="peers"><h2>Peer comparison</h2>
<table class="data-table"><tbody>
<tr><td><a href="/company/RELIANCE/consolidated/">Reliance Industr</a></td><td>2951</td></tr>
<tr><td><a href="/company/ONGC/consolidated/">ONGC</a></td><td>270</td></tr>
<tr><td><a href="/company/IOC/consolidated/">IOC</a></td><td>175</td></tr>
</tbody></table></section>

<section id="documents"><h2>Documents</h2>
<div class="annual-reports"><ul>
  <li><a href="https://www.bseindia.com/xml-data/ar/ar2024.pdf">Financial Year 2024 from bse</a></li>
  <li><a href="https://www.nseindia.com/ar2023.pdf">Financial Year 2023 from nse</a></li>
</ul></div>
<div class="concalls"><ul>
  <li><a href="https://www.screener.in/concall/transcript/aaa/">Transcript</a></li>
  <li><a href="https://www.screener.in/concall/ppt/bbb/">PPT</a></li>
</ul></div>
</section>
</body></html>"""

# --- saved fixture: a screener.in screen result page ------------------------ #
SCREEN_FIXTURE = """<html><body><table class="data-table">
<thead><tr><th>S.No.</th><th>Name</th><th>CMP</th></tr></thead>
<tbody>
<tr><td>1</td><td><a href="/company/RELIANCE/">Reliance Industr</a></td><td>2951</td></tr>
<tr><td>2</td><td><a href="/company/TCS/">TCS</a></td><td>3890</td></tr>
<tr><td>3</td><td><a href="/company/RELIANCE/">Reliance Industr</a></td><td>2951</td></tr>
</tbody></table></body></html>"""


# --- D1: fetch parses screener.in once into the typed data fields ----------- #
def _company_data():
    return fz._parse_company(COMPANY_FIXTURE, "RELIANCE")


def test_D1_ratios():
    d = _company_data()
    check("D1 ratios is a dict", isinstance(d["ratios"], dict))
    check("D1 single-number ratio is a float", d["ratios"]["Stock P/E"] == 24.3, d["ratios"])
    check("D1 ratio strips ₹/commas", d["ratios"]["Market Cap"] == 1989000.0, d["ratios"])
    check("D1 multi-number ratio kept as text", d["ratios"]["High / Low"] == "3,217 / 2,221")


def test_D1_pnl_10y():
    d = _company_data()
    pnl = d["pnl_10y"]
    check("D1 pnl columns are the periods", pnl["columns"] == ["Mar 2022", "Mar 2023", "Mar 2024", "TTM"])
    check("D1 pnl Sales row parsed to numbers", pnl["rows"]["Sales"] == [721634.0, 876396.0, 901064.0, 964693.0])
    check("D1 pnl Net Profit present", pnl["rows"]["Net Profit"][-1] == 79020.0)
    check("D1 pnl label '+' affordance stripped", "Sales" in pnl["rows"] and "Sales+" not in pnl["rows"])


def test_D1_balance_sheet_and_quarters():
    d = _company_data()
    check("D1 balance_sheet parsed", d["balance_sheet_10y"]["rows"]["Borrowings"][0] == 266305.0)
    check("D1 quarters parsed", d["quarters"]["rows"]["Net Profit"] == [19641.0, 21243.0, 17448.0])
    check("D1 quarters columns are quarter labels", d["quarters"]["columns"][0] == "Dec 2023")


def test_D1_shareholding():
    d = _company_data()
    sh = d["shareholding"]["rows"]
    check("D1 promoter holding parsed", sh["Promoters"] == [50.30, 50.31])
    check("D1 FII holding parsed", sh["FIIs"][0] == 22.06)


def test_D1_peers():
    d = _company_data()
    syms = [p["symbol"] for p in d["peers"]]
    check("D1 peers extracted with symbols", "ONGC" in syms and "IOC" in syms)
    check("D1 peer self-link kept once", syms.count("RELIANCE") == 1)
    check("D1 peer name captured", d["peers"][0]["name"] == "Reliance Industr")


def test_D1_documents():
    d = _company_data()
    docs = d["documents"]
    check("D1 annual reports collected", len(docs["annual_reports"]) == 2)
    check("D1 concalls collected (transcript + ppt)", len(docs["concalls"]) == 2)
    check("D1 annual-report url kept", docs["annual_reports"][0]["url"].endswith("ar2024.pdf"))


# --- D2: screen(query) returns the candidate symbol list envelope ----------- #
def test_D2_screen_parses_candidates():
    cands = fz._parse_screen(SCREEN_FIXTURE)
    check("D2 screen extracts candidate symbols", cands == ["RELIANCE", "TCS"])
    check("D2 screen de-dupes repeated rows", cands.count("RELIANCE") == 1)


def test_D2_screen_envelope(monkeypatch=None):
    # Drive screen() offline by stubbing the HTTP rung with the saved fixture.
    orig = fz._http_get
    fz._http_get = lambda url, timeout=20, cookie=None: (SCREEN_FIXTURE, None)
    try:
        env = fz.screen("Market Capitalization > 50000")
    finally:
        fz._http_get = orig
    check("D2 screen returns the data-spine envelope",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"})
    check("D2 envelope carries candidates", env["data"]["candidates"] == ["RELIANCE", "TCS"])
    check("D2 envelope count matches", env["data"]["count"] == 2)
    check("D2 ok:true when candidates found", env["ok"] is True)


# --- D3: output extracts tables/fields only — never raw page HTML ----------- #
def test_D3_no_html_in_data():
    d = _company_data()

    def walk(v):
        if isinstance(v, str):
            return "<" not in v and "</" not in v and len(v) < 2000
        if isinstance(v, dict):
            return all(walk(x) for x in v.values())
        if isinstance(v, list):
            return all(walk(x) for x in v)
        return True

    check("D3 no value in data contains raw HTML tags", walk(d))
    check("D3 data has only the typed fields",
          set(d) == {"symbol", "ratios", "pnl_10y", "balance_sheet_10y", "quarters",
                     "shareholding", "peers", "documents"})


# --- fetch() composition offline (D1/D3 end-to-end) ------------------------- #
def test_fetch_envelope_offline():
    orig = fz._http_get
    fz._http_get = lambda url, timeout=20, cookie=None: (COMPANY_FIXTURE, None)
    try:
        env = fz.fetch("RELIANCE", fresh=True)
    finally:
        fz._http_get = orig
    check("fetch returns the data-spine envelope",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"})
    check("fetch ok:true with a parsed page", env["ok"] is True)
    check("fetch data carries the typed fields", env["data"]["pnl_10y"]["rows"]["Sales"][0] == 721634.0)


def test_fetch_all_blocked_degrades():
    orig = fz._http_get
    fz._http_get = lambda url, timeout=20, cookie=None: (None, "HTTP 403")
    try:
        env = fz.fetch("ZZZZ", fresh=True)
    finally:
        fz._http_get = orig
    check("fetch all-blocked returns ok:false", env["ok"] is False)
    check("fetch all-blocked carries a labelled gap", len(env["gaps"]) >= 1)
    check("fetch all-blocked still has the envelope shape",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"})


def test_to_number():
    check("to_number strips ₹ and commas", fz._to_number(" ₹ 19,89,000 Cr.") == 1989000.0)
    check("to_number parens are negative", fz._to_number("(1,234)") == -1234.0)
    check("to_number blank is None", fz._to_number("-") is None and fz._to_number("") is None)
    check("to_number percent stripped", fz._to_number("50.30%") == 50.30)


def test_envelope_shape():
    env = fz._envelope(True, "screener.in", {"x": 1}, [])
    check("envelope has the contract keys",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"})


# --- D4 is this file passing: every test above runs offline on fixtures ----- #
def main():
    for fn in (test_D1_ratios, test_D1_pnl_10y, test_D1_balance_sheet_and_quarters,
               test_D1_shareholding, test_D1_peers, test_D1_documents,
               test_D2_screen_parses_candidates, test_D2_screen_envelope,
               test_D3_no_html_in_data, test_fetch_envelope_offline,
               test_fetch_all_blocked_degrades, test_to_number, test_envelope_shape):
        fn()
    print(f"\n{'=' * 48}\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
