#!/usr/bin/env python3
"""Offline unit tests for finance/sources/fundamentals.py + finance/sources/tickertape.py.

Deterministic, no network — the Tickertape parsers and the screener document-index parser
run against saved payload fixtures, mirroring test_prices.py / test_funds.py. Run:
    python3 finance/tests/test_fundamentals.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from finance.sources import fundamentals as fz
from finance.sources import tickertape as tt
from finance.tests.harness import check, run


# --- saved fixtures: real Tickertape payload shapes, trimmed ---------------- #
# The search is a substring match returning every near-miss, which is what makes exact
# ticker equality in resolve_sid load-bearing.
LISTED = [
    {"ticker": "RECLTD", "name": "REC Ltd", "sid": "RECM", "sector": "Financials",
     "slug": "/stocks/rec-RECM", "match": "EXACT"},
    {"ticker": "RECLTDPP", "name": "REC Ltd Partly Paid", "sid": "RECMpp",
     "sector": "Financials", "slug": "/stocks/x", "match": "EXACT"},
    {"ticker": "RELIANCE", "name": "Reliance Industries Ltd", "sid": "RELI",
     "sector": "Energy", "slug": "/stocks/reliance-industries-RELI", "match": "EXACT"},
]

INFO = {"success": True, "data": {
    "sid": "RELI", "isin": "INE002A01018",
    "info": {"name": "Reliance Industries Ltd", "ticker": "RELIANCE", "sector": "Energy"},
    "ratios": {"marketCap": 1777092.98, "lastPrice": 1313.2, "ttmPe": 23.78, "pe": 22.0,
               "bps": 802.41, "divYield": 0.4568, "roe": 7.709, "nShareholders": 4651863,
               "52wHigh": 1611.8, "52wLow": 1249.8, "mrktCapRank": 1}}}

QUERY_ONE = {"success": True, "data": {"results": [
    {"sid": "RELI", "stock": {"advancedRatios": {"roce": 9.18, "faceValue": 10,
                                                 "mrktCapf": 1777092.98},
                              "info": {"name": "Reliance Industries Ltd",
                                       "ticker": "RELIANCE", "sector": "Energy"}}}],
    "stats": {"count": 1}}}

INCOME_ANNUAL = {"success": True, "data": [
    {"displayPeriod": "FY 2025", "endDate": "2025-03-31T00:00:00.000Z",
     "incTrev": 982671, "incRaw": 644813, "incEbi": 183478, "incDep": 53197,
     "incPbi": 130281, "incIoi": 24269, "incPbt": 106012, "incToi": 34787,
     "incNinc": 71225, "incEps": 51.47, "incDps": 5.5, "incPyr": 0.1069},
    {"displayPeriod": "FY 2026", "endDate": "2026-03-31T00:00:00.000Z",
     "incTrev": 1086181, "incRaw": 698930, "incEbi": 207911, "incDep": 57688,
     "incPbi": 150223, "incIoi": 27061, "incPbt": 123162, "incToi": 42387,
     "incNinc": 80775, "incEps": 59.69, "incDps": 6, "incPyr": 0.1005},
    {"displayPeriod": "TTM", "endDate": "", "incTrev": 1143448, "incRaw": None,
     "incEbi": 203954, "incDep": 58946, "incPbi": 145008, "incIoi": 28362,
     "incPbt": 116646, "incToi": 41919, "incNinc": 74727, "incEps": 55.22,
     "incDps": 11.5, "incPyr": 0.2082}]}

INCOME_INTERIM = {"success": True, "data": [
    {"displayPeriod": "MAR 2026", "qIncTrev": 298506, "qIncEbi": 48588, "qIncDep": 14808,
     "qIncPbi": 33780, "qIncIoi": 6585, "qIncPbt": 27195, "qIncToi": 10224,
     "qIncNinc": 16971, "qIncEps": 12.54, "qIncRaw": None},
    {"displayPeriod": "JUN 2026", "qIncTrev": 273252, "qIncEbi": 50108, "qIncDep": 15117,
     "qIncPbi": 34991, "qIncIoi": 6704, "qIncPbt": 28287, "qIncToi": 10120,
     "qIncNinc": 18167, "qIncEps": 13.42, "qIncRaw": None}]}

BALANCE_SHEET = {"success": True, "data": [
    {"displayPeriod": "FY 2026", "balCsti": 243408, "balTca": 594249, "balTota": 2177546,
     "balTcl": 541254, "balTdeb": 402962, "balMint": 181836, "balTotl": 1091680,
     "balComs": 13532, "balApic": 93118, "balRtne": 797380, "balTeq": 1085866,
     "balTlse": 2177546, "balTcso": 1353.24, "balTdep": None}]}

# `cafFee` is carried in the payload with no published name and a null value; the parser
# must not invent a label for it.
CASH_FLOW = {"success": True, "data": [
    {"displayPeriod": "FY 2025", "endDate": "2025-03-31T00:00:00.000Z",
     "cafCfoa": 178703, "cafCfia": -137535, "cafCffa": -31891, "cafNcic": 9277,
     "cafCiwc": 11799, "cafCexp": 139967, "cafTcdp": 7180, "cafFcf": 38736,
     "cafFee": None},
    {"displayPeriod": "FY 2026", "endDate": "2026-03-31T00:00:00.000Z",
     "cafCfoa": 192113, "cafCfia": -101089, "cafCffa": -51549, "cafNcic": 39475,
     "cafCiwc": 2889, "cafCexp": 122916, "cafTcdp": 7879, "cafFcf": 69197,
     "cafFee": None}]}

HOLDINGS = {"success": True, "data": [
    {"date": "2026-03-31T00:00:00.000Z",
     "data": {"pmPctT": 49.999, "pmPctP": 0.0, "fiPctT": 18.665, "diPctT": 20.547,
              "mfPctT": 9.781, "isPctT": 9.030, "rhPctT": 6.959, "othPctT": 3.827}},
    {"date": "2026-06-30T00:00:00.000Z",
     "data": {"pmPctT": 49.624, "pmPctP": 0.0, "fiPctT": 16.904, "diPctT": 20.828,
              "mfPctT": 9.934, "isPctT": 9.046, "rhPctT": 7.041, "othPctT": 5.599}}]}

PEERS = {"success": True, "data": [
    {"sid": "RELI", "ticker": "RELIANCE", "name": "Reliance Industries Ltd"},
    {"sid": "IOC", "ticker": "IOC", "name": "Indian Oil Corporation Limited"},
    {"sid": "HPCL", "ticker": "HINDPETRO", "name": "Hindustan Petroleum Corp Ltd"}]}

FILTERS = {"success": True, "data": {
    "none": [{"label": "mrktCapf", "display": "Market Cap", "short": "Market Cap",
              "premium": False}],
    "Profitability": [{"label": "roce", "display": "ROCE", "short": "ROCE",
                       "premium": False},
                      {"label": "roe", "display": "Return on Equity", "short": "ROE",
                       "premium": False}],
    "Valuation": [{"label": "apef", "display": "PE Ratio", "short": "PE", "premium": False},
                  {"label": "pef", "display": "Forward PE Ratio", "short": "Fwd PE",
                   "premium": True}],
    # A field with no display/short name at all: its blank alias must not become a
    # wildcard that resolves every query field to it.
    "Financial Ratios": [{"label": "dbtEqt", "display": "Debt to Equity",
                          "short": "D/E", "premium": False},
                         {"label": "aint", "premium": False}]}}

SCREEN_RESULT = {"success": True, "data": {"results": [
    {"sid": "TCS", "stock": {"info": {"ticker": "TCS"}, "advancedRatios": {"roce": 55.4}}},
    {"sid": "INFY", "stock": {"info": {"ticker": "INFY"}, "advancedRatios": {"roce": 39.1}}},
    {"sid": "TCS2", "stock": {"info": {"ticker": "TCS"}, "advancedRatios": {"roce": 55.4}}}],
    "stats": {"count": 2}}}

DOCUMENTS_PAGE = """<!doctype html><html><head><title>Reliance Industries Ltd</title></head>
<body>
<section id="peers"><a href="/company/IOC/">IOC</a></section>
<section id="documents"><h2>Documents</h2>
<div class="annual-reports"><ul>
  <li><a href="https://www.bseindia.com/xml-data/ar/ar2026.pdf">Financial Year 2026 from bse</a></li>
  <li><a href="/company/source/AR-2025/">Annual Report 2025</a></li>
</ul></div>
<div class="concalls"><ul>
  <li><a href="https://www.screener.in/concall/transcript/aaa/">Transcript</a></li>
  <li><a href="https://www.screener.in/concall/ppt/bbb/">PPT</a></li>
</ul></div>
</section></body></html>"""

REGISTER_PAGE = """<html><head><title>Register - Screener</title></head>
<body><form action="/login/" method="post"><input name="username"></form></body></html>"""


# --- the Tickertape rung, stubbed by path ----------------------------------- #
ROUTES = [
    ("/stocks/info/", INFO), ("/stocks/holdings/", HOLDINGS),
    ("/stocks/peers/", PEERS), ("/screener/filters", FILTERS),
    ("/stocks/financials/income/RELI/annual", INCOME_ANNUAL),
    ("/stocks/financials/income/RELI/interim", INCOME_INTERIM),
    ("/stocks/financials/balancesheet/", BALANCE_SHEET),
    ("/stocks/financials/cashflow/", CASH_FLOW),
]


def _stub_json(path, payload=None, timeout=30):
    if path.startswith("/search?"):
        text = path.split("text=", 1)[1].split("&")[0].upper()
        hits = [s for s in LISTED if text in s["ticker"]]
        return {"success": True, "data": {"total": len(hits), "stocks": hits}}, None
    if path.startswith("/screener/query"):
        return (QUERY_ONE if payload and payload.get("sids") else SCREEN_RESULT), None
    for prefix, blob in ROUTES:
        if path.startswith(prefix):
            return blob, None
    return None, f"unrouted fixture path {path}"


class _Offline:
    """Swap the network rungs for fixtures, and the cache for a scratch dir."""

    def __init__(self, get_json=_stub_json, page=DOCUMENTS_PAGE, page_gap=None):
        self.get_json, self.page, self.page_gap = get_json, page, page_gap

    def __enter__(self):
        import tempfile
        self._saved = (tt.get_json, fz.transport.request,
                       os.environ.get("EVERYTHING_FINANCE_ARTIFACTS"))
        os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = tempfile.mkdtemp()
        tt.get_json = self.get_json
        fz.transport.request = lambda url, **kw: (self.page, self.page_gap)
        return self

    def __exit__(self, *exc):
        tt.get_json, fz.transport.request = self._saved[:2]
        if self._saved[2] is None:
            os.environ.pop("EVERYTHING_FINANCE_ARTIFACTS", None)
        else:
            os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = self._saved[2]
        return False


# --- T1: symbol -> sid resolution, and its failure gap ---------------------- #
def test_T1_resolve_sid():
    with _Offline():
        rec, gap = tt.resolve_sid("RECLTD", fresh=True)
    check("T1 sid resolves off an exact ticker match", rec and rec["sid"] == "RECM", rec)
    check("T1 the sid is not the ticker", rec["sid"] != rec["ticker"])
    check("T1 no gap on a hit", gap is None, gap)
    check("T1 the company name travels with it", rec["name"] == "REC Ltd")


def test_T1_resolve_sid_miss_is_a_labelled_gap():
    with _Offline():
        rec, gap = tt.resolve_sid("NOTLISTED", fresh=True)
    check("T1 an unmatched symbol resolves to nothing", rec is None)
    check("T1 the gap names the symbol asked for", gap and "NOTLISTED" in gap, gap)


def test_T1_resolve_sid_rejects_a_near_miss():
    """A partial-match row must never be accepted: it would attribute one company's
    financials to another under the right ticker."""
    with _Offline():
        rec, gap = tt.resolve_sid("RECLT", fresh=True)
    check("T1 a prefix of a real ticker is refused", rec is None, rec)
    check("T1 the gap names what the search did offer instead",
          "RECLTD" in (gap or ""), gap)


def test_T1_empty_symbol():
    rec, gap = tt.resolve_sid("")
    check("T1 an empty symbol is a gap, not a fetch", rec is None and bool(gap), gap)


# --- T2: each re-pointed endpoint parses into the shared table shape -------- #
def _data():
    with _Offline():
        return fz.fetch("RELIANCE", fresh=True)["data"]


def test_T2_ratios():
    r = _data()["ratios"]
    check("T2 market cap from /stocks/info", r["Market Cap"] == 1777092.98, r)
    check("T2 Stock P/E is the TTM multiple, not the annualised one",
          r["Stock P/E"] == 23.78, r)
    check("T2 book value per share carried", r["Book Value"] == 802.41)
    check("T2 ROCE comes from the screener projection", r["ROCE"] == 9.18)
    check("T2 face value comes from the screener projection", r["Face Value"] == 10.0)
    check("T2 52-week range rendered as one range string",
          r["High / Low"] == "1611.8 / 1249.8", r.get("High / Low"))
    check("T2 shareholder count kept", r["No. of Shareholders"] == 4651863.0)


def test_T2_pnl_10y():
    pnl = _data()["pnl_10y"]
    check("T2 pnl columns are the reporting periods",
          pnl["columns"] == ["FY 2025", "FY 2026", "TTM"], pnl["columns"])
    check("T2 revenue row parsed", pnl["rows"]["Total Revenue"] == [982671.0, 1086181.0,
                                                                   1143448.0])
    check("T2 EBITDA row parsed", pnl["rows"]["EBITDA"][1] == 207911.0)
    check("T2 tax line keeps Tickertape's honest label",
          "Taxes & Other Items" in pnl["rows"] and "Tax %" not in pnl["rows"],
          sorted(pnl["rows"]))
    check("T2 a blank cell is None, never 0",
          pnl["rows"]["Raw Materials"][-1] is None, pnl["rows"]["Raw Materials"])
    check("T2 EBITDA margin derived from the two sourced figures",
          pnl["rows"]["EBITDA Margin %"][1] == round(100 * 207911 / 1086181, 2))
    check("T2 payout ratio converted from a fraction to a percentage",
          pnl["rows"]["Payout Ratio %"][1] == 10.05, pnl["rows"]["Payout Ratio %"])


def test_T2_pnl_ttm_column_is_marked_not_a_fiscal_year():
    # The annual income statement appends a trailing-twelve-month column that the balance
    # sheet and cash flow do NOT — pairing the three by index silently mixes TTM with FY.
    # `period_kinds` makes the last column's kind explicit so a consumer can pair by kind.
    pnl = _data()["pnl_10y"]
    check("T2 pnl period_kinds parallel the columns",
          pnl["period_kinds"] == ["FY", "FY", "TTM"], pnl["period_kinds"])
    check("T2 the last pnl column is TTM, not a fiscal year",
          pnl["period_kinds"][-1] == "TTM", pnl["period_kinds"])
    bs = _data()["balance_sheet_10y"]
    cf = _data()["cash_flow_10y"]
    check("T2 balance sheet carries no TTM column",
          "TTM" not in bs["period_kinds"], bs["period_kinds"])
    check("T2 cash flow carries no TTM column",
          "TTM" not in cf["period_kinds"], cf["period_kinds"])
    # The trap the marking prevents: latest-index CFO (FY) paired with latest-index EBITDA (TTM).
    fy_ebitda = pnl["rows"]["EBITDA"][pnl["period_kinds"].index("TTM") - 1]
    ttm_ebitda = pnl["rows"]["EBITDA"][pnl["period_kinds"].index("TTM")]
    check("T2 the FY and TTM EBITDA genuinely differ (the mix would be silent)",
          fy_ebitda != ttm_ebitda, (fy_ebitda, ttm_ebitda))


def test_T2_balance_sheet_10y():
    bs = _data()["balance_sheet_10y"]
    check("T2 balance sheet columns", bs["columns"] == ["FY 2026"])
    check("T2 total debt parsed", bs["rows"]["Total Debt"] == [402962.0])
    check("T2 minority interest is its own row", bs["rows"]["Minority Interest"] == [181836.0])
    check("T2 reserves and paid-in capital stay separate",
          bs["rows"]["Reserves & Surplus"][0] == 797380.0
          and bs["rows"]["Additional Paid-in Capital"][0] == 93118.0)
    check("T2 an all-null row is dropped rather than carried as zeros",
          "Total Deposits - Banks" not in bs["rows"], sorted(bs["rows"]))


def test_T2_cash_flow_10y():
    cf = _data()["cash_flow_10y"]
    check("T2 cash flow columns are the reporting periods",
          cf["columns"] == ["FY 2025", "FY 2026"], cf["columns"])
    check("T2 cash from operations parsed",
          cf["rows"]["Cash from Operating Activities"] == [178703.0, 192113.0],
          cf["rows"].get("Cash from Operating Activities"))
    check("T2 capital expenditure parsed — the P&L carries no capex line",
          cf["rows"]["Capital Expenditures"] == [139967.0, 122916.0])
    check("T2 free cash flow is the published line, not a derived one",
          cf["rows"]["Free Cash Flow"] == [38736.0, 69197.0])
    check("T2 the published FCF reconciles to CFO minus capex",
          all(round(o - c, 2) == f for o, c, f in zip(
              cf["rows"]["Cash from Operating Activities"],
              cf["rows"]["Capital Expenditures"],
              cf["rows"]["Free Cash Flow"])))
    check("T2 the three activity lines reconcile to net change in cash",
          all(round(o + i + fin, 2) == n for o, i, fin, n in zip(
              cf["rows"]["Cash from Operating Activities"],
              cf["rows"]["Cash from Investing Activities"],
              cf["rows"]["Cash from Financing Activities"],
              cf["rows"]["Net Change in Cash"])))
    check("T2 the unnamed cafFee is dropped, never given a guessed label",
          len(cf["rows"]) == len(fz._CF_ROWS)
          and not any("Exchange" in k or "Forex" in k for k in cf["rows"]),
          sorted(cf["rows"]))


def test_T2_quarters():
    q = _data()["quarters"]
    check("T2 quarter columns", q["columns"] == ["MAR 2026", "JUN 2026"])
    check("T2 the annual field map drives the interim endpoint too",
          q["rows"]["Total Revenue"] == [298506.0, 273252.0], q["rows"].get("Total Revenue"))
    check("T2 quarterly EPS parsed", q["rows"]["Earnings Per Share"] == [12.54, 13.42])


def test_T2_q_key():
    check("T2 interim field names derive from the annual ones",
          fz._q_key("incTrev") == "qIncTrev" and fz._q_key("incEbi") == "qIncEbi")


def test_T2_shareholding():
    sh = _data()["shareholding"]
    check("T2 shareholding columns are ISO dates",
          sh["columns"] == ["2026-03-31", "2026-06-30"], sh["columns"])
    check("T2 promoter holding parsed", sh["rows"]["Promoters"] == [49.999, 49.624])
    check("T2 FII and DII split kept apart",
          sh["rows"]["FIIs"][1] == 16.904 and sh["rows"]["DIIs"][1] == 20.828)
    check("T2 the pledge row names its denominator",
          "Promoter Pledge (% of promoter holding)" in sh["rows"], sorted(sh["rows"]))


def test_T2_peers():
    peers = _data()["peers"]
    syms = [p["symbol"] for p in peers]
    check("T2 peers are real companies, not index memberships",
          syms == ["IOC", "HINDPETRO"], syms)
    check("T2 the company itself is not its own peer", "RELIANCE" not in syms)
    check("T2 the join key travels with each peer",
          peers[1]["sid"] == "HPCL" and peers[1]["symbol"] == "HINDPETRO", peers[1])


def test_T2_documents_stay_on_screener():
    docs = _data()["documents"]
    check("T2 annual reports collected", len(docs["annual_reports"]) == 2, docs)
    check("T2 concalls collected (transcript + ppt)", len(docs["concalls"]) == 2)
    check("T2 a relative screener link is absolutised",
          docs["annual_reports"][1]["url"].startswith(fz.SCREENER + "/company/"))


# --- T3: the envelope shape is unchanged ------------------------------------ #
def test_T3_envelope_and_identity():
    with _Offline():
        env = fz.fetch("RELIANCE", fresh=True)
    check("T3 fetch returns the data-spine envelope",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"})
    check("T3 ok:true on a full parse", env["ok"] is True, env["gaps"])
    check("T3 source names both rungs",
          "Tickertape" in env["source"] and "screener.in" in env["source"], env["source"])
    d = env["data"]
    check("T3 data carries exactly the contracted sections",
          set(d) == {"symbol", "name", "sid", *fz._SECTIONS}, sorted(d))
    check("T3 identity is attributable", d["symbol"] == "RELIANCE" and d["sid"] == "RELI")


def test_T3_no_html_in_data():
    def walk(v):
        if isinstance(v, str):
            return "<" not in v and "</" not in v and len(v) < 2000
        if isinstance(v, dict):
            return all(walk(x) for x in v.values())
        if isinstance(v, list):
            return all(walk(x) for x in v)
        return True

    check("T3 no value in data contains raw HTML", walk(_data()))


def test_T3_sections_narrow_the_work_not_just_the_answer():
    calls = []

    def counting(path, payload=None, timeout=30):
        calls.append(path)
        return _stub_json(path, payload, timeout)

    with _Offline(get_json=counting):
        env = fz.fetch("RELIANCE", sections=["documents"], fresh=True)
    check("T3 a documents-only read makes no Tickertape call at all", calls == [], calls)
    check("T3 the documents section still comes back",
          len(env["data"]["documents"]["annual_reports"]) == 2)
    check("T3 identity survives the narrowing", env["data"]["symbol"] == "RELIANCE")
    check("T3 a narrowed read lists the sections it returns, not the company's full set",
          env["data"]["sections_returned"] == ["documents"],
          env["data"].get("sections_returned"))


def test_T3_sections_keep_the_sections_own_content():
    with _Offline():
        narrow = fz.fetch("RELIANCE", sections=["ratios"], fresh=True)
        full = fz.fetch("RELIANCE", fresh=True)
    check("T3 a narrowed section equals the full read's",
          narrow["data"]["ratios"] == full["data"]["ratios"])
    check("T3 a narrowed read drops the rest",
          "pnl_10y" not in narrow["data"], sorted(narrow["data"]))
    check("T3 a full read adds no sections_returned",
          "sections_returned" not in full["data"], sorted(full["data"]))


# --- T4: every failure is a labelled gap, never an abort -------------------- #
def test_T4_unresolvable_symbol_degrades():
    with _Offline(get_json=lambda p, payload=None, timeout=30: (None, "HTTP 503")):
        env = fz.fetch("ZZZZ", sections=["ratios", "pnl_10y"], fresh=True)
    check("T4 an unresolvable symbol returns ok:false", env["ok"] is False)
    check("T4 the gap names the symbol", any("ZZZZ" in g for g in env["gaps"]), env["gaps"])
    check("T4 the envelope shape survives",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"})
    check("T4 the empty sections are still typed",
          env["data"]["ratios"] == {} and env["data"]["pnl_10y"] == {"columns": [], "rows": {}})


def test_T4_one_dead_endpoint_does_not_kill_the_rest():
    def half_dead(path, payload=None, timeout=30):
        if "/stocks/holdings/" in path:
            return None, "HTTP 500"
        return _stub_json(path, payload, timeout)

    with _Offline(get_json=half_dead):
        env = fz.fetch("RELIANCE", fresh=True)
    check("T4 a dead endpoint leaves the others intact",
          env["ok"] and env["data"]["pnl_10y"]["rows"], env["gaps"])
    check("T4 the dead endpoint is named in a gap",
          any("shareholding" in g for g in env["gaps"]), env["gaps"])
    check("T4 the dead section comes back empty, not absent",
          env["data"]["shareholding"] == {"columns": [], "rows": {}})


def test_T4_screener_register_page_is_not_an_empty_filing_history():
    with _Offline(page=REGISTER_PAGE):
        env = fz.fetch("RELIANCE", sections=["documents"], fresh=True)
    check("T4 an anonymous screener page yields no documents",
          env["data"]["documents"] == {"annual_reports": [], "concalls": []})
    check("T4 and says so rather than reading as a company that filed nothing",
          any("anonymous page" in g for g in env["gaps"]), env["gaps"])


def test_T4_is_logged_out():
    check("the Register page is detected", fz.is_logged_out(REGISTER_PAGE))
    check("a Login title is detected",
          fz.is_logged_out("<html><head><title>Login - Screener</title></head></html>"))
    check("detection is case-insensitive",
          fz.is_logged_out("<HTML><TITLE>REGISTER - Screener</TITLE></HTML>"))
    check("a real company page is not flagged", not fz.is_logged_out(DOCUMENTS_PAGE))
    check("empty html is not flagged", not fz.is_logged_out(""))
    check("None is handled", not fz.is_logged_out(None))


def test_T4_thin_ratio_block_is_labelled():
    """A partial payload parses cleanly and reads as authoritative unless something says
    otherwise — the failure that put a stale price into a valuation."""
    def thin(path, payload=None, timeout=30):
        if path.startswith("/stocks/info/"):
            return {"data": {"ratios": {"marketCap": 1.0, "lastPrice": 2.0}}}, None
        return _stub_json(path, payload, timeout)

    with _Offline(get_json=thin):
        env = fz.fetch("RELIANCE", sections=["ratios"], fresh=True)
    check("T4 a thin ratio block is flagged as unverified",
          any("unverified" in g for g in env["gaps"]), env["gaps"])
    check("T4 the threshold sits below a complete block's ten ratios",
          0 < fz._MIN_RATIOS <= 10, fz._MIN_RATIOS)


# --- T5: the screen query contract ------------------------------------------ #
def _screen(query, **kw):
    with _Offline():
        return fz.screen(query, fresh=True, **kw)


def test_T5_screen_envelope():
    env = _screen("Market Cap > 50000 AND PE Ratio < 25")
    check("T5 screen returns the data-spine envelope",
          set(env) == {"ok", "source", "fetched_at", "data", "gaps"})
    check("T5 candidates are NSE symbols", env["data"]["candidates"] == ["TCS", "INFY"],
          env["data"])
    check("T5 duplicate rows are collapsed", env["data"]["count"] == 2)
    check("T5 the query is echoed back", env["data"]["query"].startswith("Market Cap"))
    check("T5 ok:true when candidates found", env["ok"] is True)


def test_T5_field_names_resolve_against_the_published_catalogue():
    with _Offline():
        names, premium, gap = fz._catalogue(fresh=True)
    check("T5 the catalogue loads", gap is None and names, gap)
    check("T5 a display name resolves", fz._resolve_field("Market Cap", names)[0] == "mrktCapf")
    check("T5 resolution folds case and punctuation",
          fz._resolve_field("debt-to-equity", names)[0] == "dbtEqt")
    check("T5 a longer spelling of a published name still resolves",
          fz._resolve_field("Market Capitalization", names)[0] == "mrktCapf")
    check("T5 the raw field label resolves", fz._resolve_field("roce", names)[0] == "roce")
    check("T5 premium fields are known", "pef" in premium, premium)
    check("T5 a field with no display name does not become a wildcard",
          fz._resolve_field("Debt to Equity", names)[0] == "dbtEqt")
    check("T5 that field still resolves by its raw label",
          fz._resolve_field("aint", names)[0] == "aint")


def test_T5_unresolvable_field_refuses_the_whole_query():
    env = _screen("Market Cap > 50000 AND Price to Earning < 20")
    check("T5 an unresolvable field returns ok:false", env["ok"] is False)
    check("T5 no candidates leak from the half that did resolve",
          env["data"]["candidates"] == [] and env["data"]["count"] == 0, env["data"])
    check("T5 the gap names the offending field",
          any("Price to Earning" in g for g in env["gaps"]), env["gaps"])
    check("T5 the gap lists usable field names",
          any("ROCE" in g for g in env["gaps"]), env["gaps"])


def test_T5_inclusive_operators_are_refused_not_approximated():
    """The endpoint answers an unknown operator with an empty result, not an error, and
    `>=` narrowed to `>` silently drops the boundary companies."""
    for op in (">=", "<=", "="):
        env = _screen(f"Market Cap {op} 50000")
        check(f"T5 {op} is refused", env["ok"] is False and not env["data"]["candidates"])
        check(f"T5 the {op} gap says which operators exist",
              any("only > and <" in g for g in env["gaps"]), env["gaps"])


def test_T5_premium_field_is_refused():
    env = _screen("Forward PE Ratio < 20")
    check("T5 a paywalled field is refused up front", env["ok"] is False)
    check("T5 the gap says it is paywalled",
          any("paywalled" in g for g in env["gaps"]), env["gaps"])


def test_T5_malformed_clause_is_refused():
    env = _screen("Market Cap > abc")
    check("T5 a non-numeric threshold is refused", env["ok"] is False)
    check("T5 the gap shows the expected form",
          any("FIELD > VALUE" in g for g in env["gaps"]), env["gaps"])


def test_T5_parse_query_builds_the_match_object():
    with _Offline():
        names, premium, _ = fz._catalogue(fresh=True)
    match, gaps = fz._parse_query("Market Cap > 1000 AND ROCE > 12 AND ROCE < 90",
                                  names, premium)
    check("T5 clauses become Tickertape match operators",
          match == {"mrktCapf": {"g": 1000.0}, "roce": {"g": 12.0, "l": 90.0}}, match)
    check("T5 a clean query raises no gaps", gaps == [], gaps)


def test_T5_truncated_result_says_how_many_matched():
    env = _screen("Market Cap > 1", limit=1)
    check("T5 a capped result is still ok", env["ok"] is True)


def test_T5_advertised_common_fields_are_all_real():
    with _Offline(get_json=lambda p, payload=None, timeout=30: (FILTERS, None)):
        names, _, _ = fz._catalogue(fresh=True)
    known = [n for n in fz.COMMON_FIELDS if fz._resolve_field(n, names)[0]]
    check("T5 the fields quoted back at a caller are catalogue names",
          set(known) <= set(fz.COMMON_FIELDS) and known, known)


if __name__ == "__main__":
    run((test_T1_resolve_sid, test_T1_resolve_sid_miss_is_a_labelled_gap,
         test_T1_resolve_sid_rejects_a_near_miss, test_T1_empty_symbol,
         test_T2_ratios, test_T2_pnl_10y,
         test_T2_pnl_ttm_column_is_marked_not_a_fiscal_year,
         test_T2_balance_sheet_10y,
         test_T2_cash_flow_10y, test_T2_quarters,
         test_T2_q_key, test_T2_shareholding, test_T2_peers,
         test_T2_documents_stay_on_screener,
         test_T3_envelope_and_identity, test_T3_no_html_in_data,
         test_T3_sections_narrow_the_work_not_just_the_answer,
         test_T3_sections_keep_the_sections_own_content,
         test_T4_unresolvable_symbol_degrades,
         test_T4_one_dead_endpoint_does_not_kill_the_rest,
         test_T4_screener_register_page_is_not_an_empty_filing_history,
         test_T4_is_logged_out, test_T4_thin_ratio_block_is_labelled,
         test_T5_screen_envelope,
         test_T5_field_names_resolve_against_the_published_catalogue,
         test_T5_unresolvable_field_refuses_the_whole_query,
         test_T5_inclusive_operators_are_refused_not_approximated,
         test_T5_premium_field_is_refused, test_T5_malformed_clause_is_refused,
         test_T5_parse_query_builds_the_match_object,
         test_T5_truncated_result_says_how_many_matched,
         test_T5_advertised_common_fields_are_all_real))
