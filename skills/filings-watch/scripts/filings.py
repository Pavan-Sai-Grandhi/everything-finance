#!/usr/bin/env python3
"""Exchange-filings fetch + materiality classification (everything-finance plugin).

The reusable core of filings-watch, factored into a script so OTHER skills share it
without re-deriving the BSE endpoints or the materiality taxonomy — daily-brief calls
it for the watchlist/holdings filing scan, and filings-watch itself wraps it with the
NSE-browser shareholding-pledge read (which genuinely needs a real browser) and the
final judgement/report.

Two layers:
  * classify_materiality(text) — the deterministic, offline-testable heart: maps a filing
    headline/subject to a 🔴 act-on / 🟡 monitor / ⚪ routine tier with a reason. This is
    the value of the skill (most filings are noise; this is the filter) and is unit-tested.
  * fetch_bse_announcements / fetch_bse_corp_actions — BSE public JSON API over plain HTTP
    (browser UA + Referer, per CLAUDE.md). Networked, best-effort, degrade-not-die: a
    fingerprint block ("No Record Found!" everywhere) returns [] with a flagged note rather
    than raising, so a caller's whole brief never aborts on one source.

CLI:
  python3 filings.py --scrip 500325 --days 30 [--out f.json]   # RELIANCE BSE scrip code
  python3 filings.py --classify "Audited financial results for the quarter ended..."
  python3 filings.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta

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
# BSE JSON fetchers (best-effort, degrade-not-die)                            #
# --------------------------------------------------------------------------- #
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Referer": "https://www.bseindia.com/",
    "Accept": "application/json, text/plain, */*",
}


def _get_json(url):
    """GET a URL with the browser headers, parse JSON. Returns (data, error)."""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except Exception as exc:
        return None, str(exc)


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


def fetch_bse_announcements(scrip, days=30):
    """BSE announcements for a scrip code over the last `days`. Returns a dict
    {announcements: [...], note: str|None} — never raises."""
    to_d = date.today()
    from_d = to_d - timedelta(days=days)
    url = ("https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w?strCat=-1"
           f"&strPrevDate={from_d:%Y%m%d}&strScrip={scrip}&strSearch=P"
           f"&strToDate={to_d:%Y%m%d}&strType=C")
    data, err = _get_json(url)
    if err:
        return {"announcements": [], "note": f"BSE announcements fetch failed: {err}"}
    rows = _rows(data)
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
        })
    note = None
    if not out:
        # the "No Record Found!" fingerprint block, or genuinely silent
        note = ("no BSE announcements returned — genuinely quiet, or a fingerprint "
                "block; verify via the browser/NSE path before assuming nil")
    return {"announcements": out, "note": note}


def fetch_bse_corp_actions(scrip):
    """Forthcoming corporate actions (dividend/split/bonus/buyback ex-dates)."""
    url = f"https://api.bseindia.com/BseIndiaAPI/api/Corpforthcoming/w?scripcode={scrip}"
    data, err = _get_json(url)
    if err:
        return {"corporate_actions": [], "note": f"BSE corp-actions fetch failed: {err}"}
    rows = _rows(data)
    out = []
    for r in rows:
        out.append({
            "purpose": _first(r, "Purpose", "purpose"),
            "ex_date": _first(r, "Ex_date", "ExDate", "BCRD_FROM")[:10],
            "record_date": _first(r, "RD_Date", "RecordDate")[:10],
        })
    return {"corporate_actions": out, "note": None if out else "no forthcoming actions"}


def summarize(scrip, days):
    """Full best-effort pull for one scrip — what daily-brief and filings-watch call."""
    ann = fetch_bse_announcements(scrip, days)
    ca = fetch_bse_corp_actions(scrip)
    material = [a for a in ann["announcements"] if a["tier"] in ("act-on", "monitor")]
    return {
        "scrip": scrip, "days": days,
        "material_count": len(material),
        "act_on": [a for a in ann["announcements"] if a["tier"] == "act-on"],
        "monitor": [a for a in ann["announcements"] if a["tier"] == "monitor"],
        "routine_count": sum(1 for a in ann["announcements"] if a["tier"] == "routine"),
        "corporate_actions": ca["corporate_actions"],
        "notes": [n for n in (ann["note"], ca["note"]) if n],
    }


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
    p.add_argument("--days", type=int, default=30)
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
    res = summarize(args.scrip, args.days)
    out = json.dumps(res, indent=2, ensure_ascii=False)
    print(out)
    if args.out:
        import os
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        open(args.out, "w").write(out)


if __name__ == "__main__":
    main()
