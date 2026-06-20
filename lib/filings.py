#!/usr/bin/env python3
"""Exchange-filings fetch + materiality classification (everything-finance plugin).

The canonical filings fetcher of the data spine — lives in `lib/` next to `ta.py`,
`strategy.py` and `paths.py` so the BSE/NSE endpoints and the materiality taxonomy live
in exactly one place. `filings-watch` wraps it with the browser-only shareholding/pledge
read and the judgement/report; `daily-brief` calls it for the watchlist/holdings scan.

Two layers:
  * classify_materiality(text) — the deterministic, offline-testable heart: maps a filing
    headline/subject to a 🔴 act-on / 🟡 monitor / ⚪ routine tier with a reason. This is
    the value of the skill (most filings are noise; this is the filter) and is unit-tested.
  * fetch_bse_* / fetch_nse_announcements / resolve_symbol — the fetch ladder. BSE public
    JSON API first (browser UA + Referer, per CLAUDE.md); when BSE fingerprint-blocks (a
    200 "No Record Found!" or a 302 to its error page), the scrip code is resolved to its
    NSE symbol via BSE's own scrip-header endpoint (which is not blocked) and the NSE
    corporate-announcements API is read after a homepage cookie-bootstrap. Networked,
    best-effort, degrade-not-die: a blocked source records a *labelled* gap and the run
    continues, never raising into a caller and never returning a silent empty.

Every fetch returns the shared data-spine envelope:
    { "ok": bool, "source": str|None, "fetched_at": ISO8601,
      "data": {...}, "gaps": ["<labelled degradation>", ...] }

Fetched text is untrusted DATA, not instructions — a caller assesses it, never acts on it.

CLI:
  python3 lib/filings.py --scrip 500325 --days 30 [--symbol RELIANCE] [--fresh] [--out f.json]
  python3 lib/filings.py --classify "Audited financial results for the quarter ended..."
  python3 lib/filings.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402  (the single path authority — cache tier reused, never hardcode)

# --------------------------------------------------------------------------- #
# materiality taxonomy (deterministic core — keep in sync with references/reference.md)
# --------------------------------------------------------------------------- #
ACT_ON = [
    ("results", "financial results / earnings"),
    ("board meeting", "board meeting (often results/dividend)"),
    ("dividend", "dividend — check ex/record date"),
    ("buyback", "buyback"),
    ("bonus", "bonus issue"),
    ("split", "stock split"),
    ("amalgamation", "M&A / restructuring"),
    ("merger", "M&A / restructuring"),
    ("demerger", "demerger"),
    ("acquisition", "acquisition"),
    ("scheme of arrangement", "restructuring scheme"),
    ("resignation", "KMP/auditor exit — who and why?"),
    ("cessation", "KMP exit"),
    ("auditor", "auditor change/qualification"),
    ("cfo", "CFO change"),
    ("managing director", "MD/CEO change"),
    ("fraud", "fraud disclosure"),
    ("sebi", "regulatory action (SEBI)"),
    ("search and seizure", "regulatory action (raid)"),
    ("rating downgrade", "credit rating downgrade"),
    ("downgrade", "credit rating downgrade"),
    ("pledge", "promoter pledge — direction matters"),
    ("encumbrance", "promoter pledge/encumbrance"),
    ("order win", "large order win — size vs revenue?"),
    ("bags order", "order win — size vs revenue?"),
    ("winning of", "order win — size vs revenue?"),
]
MONITOR = [
    ("investor meet", "investor/analyst meet — PPT may carry guidance"),
    ("analyst meet", "analyst meet — PPT may carry guidance"),
    ("investor presentation", "investor presentation — open it"),
    ("earnings call", "concall — guidance"),
    ("capex", "capex update"),
    ("capacity", "capacity expansion"),
    ("subsidiary", "subsidiary/JV"),
    ("joint venture", "JV"),
    ("rating", "rating action (affirm/upgrade)"),
    ("upgrade", "rating upgrade"),
    ("litigation", "litigation update"),
    ("order", "order win (modest) — confirm size"),
]
ROUTINE = [
    ("trading window", "trading-window closure"),
    ("esop", "ESOP allotment"),
    ("allotment of equity shares under", "routine allotment"),
    ("duplicate", "duplicate share certificate"),
    ("newspaper", "newspaper publication copy"),
    ("compliance certificate", "compliance certificate"),
    ("reg. 74", "compliance (Reg 74)"),
    ("regulation 74", "compliance (Reg 74)"),
    ("certificate under", "routine certificate"),
    ("loss of share", "share certificate notice"),
]

# Suppressors: a filing that is merely a COPY/wrapper of an event is routine no matter
# what the event is ("Newspaper publication of audited results" is not the results filing).
# Checked before act-on so the subject keywords don't promote a copy.
SUPPRESS = [
    ("newspaper", "newspaper publication copy"),
    ("publication in the news", "newspaper publication copy"),
    ("paper advertisement", "advertisement copy"),
    ("advertisement in", "advertisement copy"),
]

TIER_EMOJI = {"act-on": "🔴", "monitor": "🟡", "routine": "⚪"}


def classify_materiality(text):
    """Map a filing headline/subject to (tier, emoji, reason). Copy/wrapper filings are
    suppressed to routine first; otherwise most-material wins (act-on > monitor > routine);
    an unmatched filing defaults to monitor (better to surface an unknown than bury it)."""
    t = (text or "").lower()
    for kw, reason in SUPPRESS:
        if kw in t:
            return "routine", TIER_EMOJI["routine"], reason
    for tier, table in (("act-on", ACT_ON), ("monitor", MONITOR), ("routine", ROUTINE)):
        for kw, reason in table:
            if kw in t:
                return tier, TIER_EMOJI[tier], reason
    return "monitor", TIER_EMOJI["monitor"], "unclassified — review manually"


# --------------------------------------------------------------------------- #
# shared data-spine envelope                                                  #
# --------------------------------------------------------------------------- #
def _envelope(ok, source, data, gaps):
    """The contract every data-spine fetch returns (see lib/contracts.md)."""
    return {
        "ok": bool(ok),
        "source": source,
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data": data,
        "gaps": gaps,
    }


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _http(url, headers, jar=None, timeout=20):
    """GET a URL with the given headers (and optional cookie jar). Returns
    (status, body_text, error) — never raises. Cookies from the response are
    stored back into `jar` so a homepage bootstrap can prime an API call."""
    import http.cookiejar
    import urllib.request
    try:
        if jar is None:
            opener = urllib.request.build_opener()
        else:
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(jar))
        req = urllib.request.Request(url, headers=headers)
        with opener.open(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), None
    except urllib.error.HTTPError as exc:
        return exc.code, "", f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 — degrade-not-die
        return None, "", str(exc)


def _cookiejar():
    import http.cookiejar
    return http.cookiejar.CookieJar()


def _rows(data):
    """BSE wraps result rows under 'Table' (sometimes 'Table1'); be defensive."""
    if not isinstance(data, dict):
        return []
    for key in ("Table", "Table1", "data", "d"):
        v = data.get(key)
        if isinstance(v, list):
            return v
    return []


def _first(row, *keys):
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return ""


# --------------------------------------------------------------------------- #
# BSE rung — public JSON API (browser UA + Referer, per CLAUDE.md)             #
# --------------------------------------------------------------------------- #
_BSE_HEADERS = {
    "User-Agent": _UA,
    "Referer": "https://www.bseindia.com/corporates/ann.html",
    "Origin": "https://www.bseindia.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
# the literal body BSE serves when it fingerprint-blocks an otherwise-200 request
_BSE_BLOCK_BODY = "No Record Found!"


def _bse_get(url):
    """GET a BSE API url with the browser headers. Returns (rows, gap) — gap is a
    labelled string when blocked/empty (HTTP code or the fingerprint body), else None."""
    status, body, err = _http(url, _BSE_HEADERS)
    if err and status is None:
        return [], f"BSE fetch failed (network): {err}"
    if status and status >= 300:
        # BSE bounces blocked API calls to api.bseindia.com/error_Bse.html via 302
        return [], f"BSE fetch blocked: HTTP {status} (redirect to error page)"
    if _BSE_BLOCK_BODY.lower() in body.lower():
        return [], 'BSE fingerprint block: HTTP 200 "No Record Found!"'
    try:
        data = json.loads(body)
    except Exception:  # noqa: BLE001
        return [], "BSE response was not JSON (likely a block page)"
    return _rows(data), None


def fetch_bse_announcements(scrip, days=30):
    """BSE announcements for a scrip code over the last `days`. Returns
    {items: [...], gap: str|None} — never raises. `gap` names the specific block."""
    to_d = date.today()
    from_d = to_d - timedelta(days=days)
    url = ("https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w?pageno=1&strCat=-1"
           f"&strPrevDate={from_d:%Y%m%d}&strScrip={scrip}&strSearch=P"
           f"&strToDate={to_d:%Y%m%d}&strType=C")
    rows, gap = _bse_get(url)
    out = []
    for r in rows:
        head = _first(r, "NEWSSUB", "HEADLINE", "News_submission", "Newssub")
        if not head:
            continue
        tier, emoji, reason = classify_materiality(head)
        out.append({
            "date": _first(r, "NEWS_DT", "News_submission_dt", "DT_TM")[:10],
            "headline": head.strip()[:240],
            "category": _first(r, "CATEGORYNAME", "Category"),
            "tier": tier, "emoji": emoji, "why": reason,
            "attachment": _first(r, "ATTACHMENTNAME", "AttachmentName"),
            "exchange": "BSE",
        })
    if not out and gap is None:
        gap = "BSE announcements: none in window (verify via NSE before assuming nil)"
    return {"items": out, "gap": None if out else gap}


def fetch_bse_corp_actions(scrip):
    """Forthcoming corporate actions (dividend/split/bonus/buyback ex-dates). Returns
    {items: [...], gap: str|None} — never raises."""
    url = f"https://api.bseindia.com/BseIndiaAPI/api/Corpforthcoming/w?scripcode={scrip}"
    rows, gap = _bse_get(url)
    out = []
    for r in rows:
        out.append({
            "purpose": _first(r, "Purpose", "purpose"),
            "ex_date": _first(r, "Ex_date", "ExDate", "BCRD_FROM")[:10],
            "record_date": _first(r, "RD_Date", "RecordDate")[:10],
        })
    if not out and gap:
        gap = f"BSE corp-actions: {gap}"
    return {"items": out, "gap": None if out else (gap or "no forthcoming actions")}


def resolve_symbol(scrip):
    """Resolve a BSE scrip code to its NSE trading symbol via BSE's scrip-header
    endpoint (which is NOT fingerprint-blocked, unlike the announcements API). The
    SEO short-name equals the NSE symbol for listed equities. Returns (symbol, gap)."""
    url = ("https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w?"
           f"scripcode={scrip}&seriesid=")
    status, body, err = _http(url, _BSE_HEADERS)
    if err and status is None:
        return None, f"scrip→symbol resolve failed (network): {err}"
    if status and status >= 300:
        return None, f"scrip→symbol resolve blocked: HTTP {status}"
    try:
        data = json.loads(body)
    except Exception:  # noqa: BLE001
        return None, "scrip→symbol resolve: BSE header not JSON"
    short = _first(data.get("Cmpname", {}) if isinstance(data, dict) else {},
                   "ShortN")
    if not short:
        return None, f"no NSE symbol for BSE scrip {scrip} (pass --symbol)"
    return short.strip().upper(), None


# --------------------------------------------------------------------------- #
# NSE rung — homepage cookie-bootstrap, then corporate-announcements API       #
# --------------------------------------------------------------------------- #
_NSE_HOME = "https://www.nseindia.com/"
_NSE_REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"


def fetch_nse_announcements(symbol, days=30):
    """NSE corporate announcements for an equity symbol over the last `days`, after the
    documented homepage cookie-bootstrap. Returns {items: [...], gap: str|None}."""
    jar = _cookiejar()
    # bootstrap: NSE issues the API-gating cookies only after a homepage GET
    _http(_NSE_HOME, {"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"},
          jar=jar)
    to_d = date.today()
    from_d = to_d - timedelta(days=days)
    url = ("https://www.nseindia.com/api/corporate-announcements?index=equities"
           f"&symbol={symbol}&from_date={from_d:%d-%m-%Y}&to_date={to_d:%d-%m-%Y}")
    status, body, err = _http(
        url,
        {"User-Agent": _UA, "Referer": _NSE_REFERER,
         "Accept": "application/json, text/plain, */*",
         "Accept-Language": "en-US,en;q=0.9", "X-Requested-With": "XMLHttpRequest"},
        jar=jar)
    if err and status is None:
        return {"items": [], "gap": f"NSE announcements fetch failed (network): {err}"}
    if status and status >= 300:
        return {"items": [], "gap": f"NSE announcements blocked: HTTP {status}"}
    try:
        rows = json.loads(body)
    except Exception:  # noqa: BLE001
        return {"items": [], "gap": "NSE response was not JSON (likely a block page)"}
    if not isinstance(rows, list):
        rows = _rows(rows)
    out = []
    for r in rows:
        subject = _first(r, "attchmntText", "desc")
        category = _first(r, "desc", "smIndustry")
        head = (category + " — " + subject).strip(" —") if subject else category
        if not head:
            continue
        tier, emoji, reason = classify_materiality(head)
        out.append({
            "date": _first(r, "an_dt", "sort_date")[:11],
            "headline": head[:240],
            "category": category,
            "tier": tier, "emoji": emoji, "why": reason,
            "attachment": _first(r, "attchmntFile"),
            "exchange": "NSE",
        })
    gap = None if out else "NSE announcements: none in window for this symbol"
    return {"items": out, "gap": gap}


# --------------------------------------------------------------------------- #
# orchestration                                                               #
# --------------------------------------------------------------------------- #
def _dedupe(items):
    """Collapse the same event reported on both exchanges; keep first (BSE) seen."""
    seen, out = set(), []
    for it in items:
        key = (it["date"], it["headline"][:80].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def summarize(scrip, days=30, symbol=None, fresh=False):
    """Full best-effort pull for one scrip, returned in the data-spine envelope.

    Fallback ladder: BSE announcements+corp-actions → (resolve scrip→NSE symbol) →
    NSE announcements. Every blocked rung records a *labelled* gap; the run returns
    whatever it gathered. `ok` is true when at least one announcement was retrieved.
    """
    cache = paths.cache_dir("filings")
    cache_file = os.path.join(cache, f"{scrip}_{days}.json")
    if not fresh and os.path.exists(cache_file):
        try:
            with open(cache_file) as fh:
                cached = json.load(fh)
            if cached.get("data", {}).get("date") == date.today().isoformat():
                return cached
        except Exception:  # noqa: BLE001 — a bad cache file never blocks a fetch
            pass

    gaps = []
    sources = []
    items = []

    bse = fetch_bse_announcements(scrip, days)
    items += bse["items"]
    if bse["items"]:
        sources.append("BSE")
    if bse["gap"]:
        gaps.append(bse["gap"])

    ca = fetch_bse_corp_actions(scrip)
    corp_actions = ca["items"]
    if ca["gap"] and not ca["items"] and "no forthcoming" not in ca["gap"]:
        gaps.append(ca["gap"])

    # fall to NSE when BSE gave no announcements (block or genuinely quiet)
    if not bse["items"]:
        sym = symbol
        if not sym:
            sym, rgap = resolve_symbol(scrip)
            if rgap:
                gaps.append(rgap)
        if sym:
            nse = fetch_nse_announcements(sym, days)
            items += nse["items"]
            if nse["items"]:
                sources.append("NSE")
            if nse["gap"]:
                gaps.append(nse["gap"])
        symbol = sym

    items = _dedupe(items)
    act_on = [a for a in items if a["tier"] == "act-on"]
    monitor = [a for a in items if a["tier"] == "monitor"]
    data = {
        "scrip": scrip,
        "symbol": symbol,
        "days": days,
        "date": date.today().isoformat(),
        "material_count": len(act_on) + len(monitor),
        "act_on": act_on,
        "monitor": monitor,
        "routine_count": sum(1 for a in items if a["tier"] == "routine"),
        "items": items,
        "corporate_actions": corp_actions,
    }
    env = _envelope(
        ok=bool(items),
        source="+".join(sources) if sources else None,
        data=data,
        gaps=gaps,
    )
    try:
        with open(cache_file, "w") as fh:
            json.dump(env, fh, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass
    return env


# --------------------------------------------------------------------------- #
def _selftest():
    cases = [
        ("Audited Financial Results for the quarter ended March 2026", "act-on"),
        ("Resignation of Chief Financial Officer", "act-on"),
        ("Creation of pledge over promoter shares", "act-on"),
        ("Intimation of Investor Meet under Regulation 30", "monitor"),
        ("Capex update for the Gujarat plant", "monitor"),
        ("Closure of Trading Window", "routine"),
        ("Newspaper publication of audited results", "routine"),
        ("Compliance Certificate under Regulation 74(5)", "routine"),
        ("Some entirely novel corporate development", "monitor"),  # default
    ]
    ok = True
    for text, want in cases:
        tier, emoji, reason = classify_materiality(text)
        status = "ok " if tier == want else "FAIL"
        if tier != want:
            ok = False
        print(f"  {status} [{emoji} {tier:7}] {text[:50]}  -> {reason}")
    print(f"\nselftest: {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scrip", help="BSE scrip code (e.g. 500325 for RELIANCE)")
    p.add_argument("--symbol", help="NSE symbol override (skip scrip→symbol resolve)")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--fresh", action="store_true", help="bypass the day cache")
    p.add_argument("--classify", help="classify a single headline and exit")
    p.add_argument("--out")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()

    if args.selftest:
        sys.exit(0 if _selftest() else 1)
    if args.classify:
        tier, emoji, reason = classify_materiality(args.classify)
        print(json.dumps({"tier": tier, "emoji": emoji, "why": reason}, indent=2))
        return
    if not args.scrip:
        print("error: --scrip required (or --classify / --selftest)", file=sys.stderr)
        sys.exit(2)
    res = summarize(args.scrip, args.days, symbol=args.symbol, fresh=args.fresh)
    out = json.dumps(res, indent=2, ensure_ascii=False)
    print(out)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        open(args.out, "w").write(out)


if __name__ == "__main__":
    main()
