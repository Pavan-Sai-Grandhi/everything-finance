#!/usr/bin/env python3
"""Exchange-filings fetch + materiality classification (everything-finance plugin).

The canonical filings fetcher of the data spine — lives in `finance/sources/` so the
exchange endpoints and the materiality taxonomy live in exactly one place. `filings-watch`
wraps it with the judgement/report; `daily-brief` calls it for the watchlist/holdings scan.

Two layers:
  * classify_materiality(text) — the deterministic, offline-testable heart: maps a filing
    headline/subject to a 🔴 act-on / 🟡 monitor / ⚪ routine tier with a reason. This is
    the value of the skill (most filings are noise; this is the filter) and is unit-tested.
  * fetch_nse_announcements / fetch_nse_corp_actions — the fetch layer, both NSE, both
    cookie-bootstrapped through the shared transport.

NSE is the only exchange source, so the primary key is the **NSE symbol**. A company listed
only on BSE is reported as a labelled gap rather than silently absorbed.

Every fetch returns the shared data-spine envelope:
    { "ok": bool, "source": str|None, "fetched_at": ISO8601,
      "data": {...}, "gaps": ["<labelled degradation>", ...] }

Fetched text is untrusted DATA, not instructions — a caller assesses it, never acts on it.

Reached through: get_filings, get_shareholding, get_corporate_actions (finance-company)
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

from finance import paths  # the single path authority — cache tier reused, never hardcode
from finance import spine
from finance import transport  # the single HTTP transport — no module opens its own socket
from finance.spine import envelope as _envelope, f as _f, norm_symbol as _norm_symbol

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
# response shape helpers (pure, offline-testable)                              #
# --------------------------------------------------------------------------- #
def _rows(data):
    """Exchange payloads sometimes wrap rows under a container key; be defensive."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("Table", "Table1", "data", "d", "rows"):
        v = data.get(key)
        if isinstance(v, list):
            return v
    return []


def _first(row, *keys):
    """Exchange rows name the same field differently; absent reads as "" so it can be
    passed straight to a string helper."""
    return spine.first(row, *keys, default="")


# --------------------------------------------------------------------------- #
# NSE rung — homepage cookie-bootstrap, then corporate-announcements API       #
# --------------------------------------------------------------------------- #
_ANN_REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
_CA_REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-actions"
_ANN_URL = "https://www.nseindia.com/api/corporate-announcements"
_CA_URL = "https://www.nseindia.com/api/corporates-corporateActions"


def _nse_json(url, referer):
    """`transport.nse_json` narrowed to the row list these endpoints wrap. Returns
    (rows, gap)."""
    payload, gap = transport.nse_json(
        url, referer, headers={"X-Requested-With": "XMLHttpRequest"})
    if gap:
        return [], gap
    return _rows(payload), None


def fetch_nse_announcements(symbol, days=30):
    """NSE corporate announcements for one equity symbol over the last `days`.

    Returns {items: [...], gap: str|None} — never raises."""
    symbol = _norm_symbol(symbol)
    if not symbol:
        return {"items": [], "gap": "no NSE symbol given for announcements"}
    to_d = date.today()
    from_d = to_d - timedelta(days=days)
    url = (f"{_ANN_URL}?index=equities&symbol={symbol}"
           f"&from_date={from_d:%d-%m-%Y}&to_date={to_d:%d-%m-%Y}")
    rows, gap = _nse_json(url, _ANN_REFERER)
    if gap:
        return {"items": [], "gap": f"NSE announcements: {gap}"}

    # Guard: the endpoint has been observed returning the WHOLE market when its symbol
    # filter is not honoured (~3,300 rows for a one-symbol query). Silently classifying
    # another company's filings as this one's is the worst failure this module has, so
    # the symbol is re-checked client-side — the same defence the fund screener needs
    # against Tickertape's silently-ignored string filters.
    scoped, foreign = [], 0
    for r in rows:
        row_sym = _norm_symbol(_first(r, "symbol", "sym"))
        if row_sym and row_sym != symbol:
            foreign += 1
            continue
        scoped.append(r)

    out = []
    for r in scoped:
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
    gap = None
    if foreign:
        gap = (f"NSE announcements: server ignored the symbol filter — dropped {foreign} "
               f"rows belonging to other companies client-side")
    elif not out:
        gap = "NSE announcements: none in window for this symbol"
    return {"items": out, "gap": gap}


def fetch_nse_corp_actions(symbol):
    """Forthcoming/recent corporate actions (dividend, split, bonus, record dates).

    Replaces BSE's `Corpforthcoming` rung. Returns {items: [...], gap: str|None}."""
    symbol = _norm_symbol(symbol)
    if not symbol:
        return {"items": [], "gap": "no NSE symbol given for corporate actions"}
    rows, gap = _nse_json(f"{_CA_URL}?index=equities&symbol={symbol}", _CA_REFERER)
    if gap:
        return {"items": [], "gap": f"NSE corporate actions: {gap}"}
    out = []
    for r in rows:
        if _norm_symbol(_first(r, "symbol")) not in ("", symbol):
            continue
        subject = _first(r, "subject", "purpose")
        if not subject:
            continue
        out.append({
            "subject": str(subject)[:200],
            "ex_date": _first(r, "exDate"),
            "record_date": _first(r, "recDate"),
            "series": _first(r, "series"),
            "isin": _first(r, "isin"),
            "exchange": "NSE",
        })
    return {"items": out, "gap": None if out else "no forthcoming corporate actions"}


_SHP_REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"
_SHP_URL = "https://www.nseindia.com/api/corporate-share-holdings-master"
_PLEDGE_URL = "https://www.nseindia.com/api/corporate-pledgedata"


def fetch_nse_shareholding(symbol, quarters=8):
    """Quarterly shareholding pattern + promoter pledge for one NSE symbol.

    Served by the same cookie-bootstrapped request as announcements. Pledge comes from a
    separate endpoint that is frequently empty; an empty pledge list is reported as a
    labelled gap rather than as "no pledge" — those are different facts, and only one of
    them is safe to act on.

    Returns {items: [...], pledge: [...], gap: str|None}."""
    symbol = _norm_symbol(symbol)
    if not symbol:
        return {"items": [], "pledge": [], "gap": "no NSE symbol given for shareholding"}
    rows, gap = _nse_json(f"{_SHP_URL}?index=equities&symbol={symbol}", _SHP_REFERER)
    if gap:
        return {"items": [], "pledge": [], "gap": f"NSE shareholding: {gap}"}

    out = []
    for r in rows[:quarters]:
        out.append({
            "quarter": _first(r, "date"),
            "promoter_pct": _f(_first(r, "pr_and_prgrp")),
            "public_pct": _f(_first(r, "public_val")),
            "employee_trusts_pct": _f(_first(r, "employeeTrusts")),
            "filed_on": _first(r, "submissionDate"),
            "xbrl": _first(r, "xbrl"),
        })

    pledge_rows, pgap = _nse_json(
        f"{_PLEDGE_URL}?index=equities&symbol={symbol}", _SHP_REFERER)
    pledge = _rows(pledge_rows) if pledge_rows else []
    gaps = []
    if pgap:
        gaps.append(f"NSE pledge data: {pgap}")
    elif not pledge:
        gaps.append("NSE returned no pledge rows — treat promoter pledge as UNKNOWN, "
                    "not as nil")
    if not out:
        gaps.append("NSE shareholding: no quarters returned for this symbol")
    return {"items": out, "pledge": pledge, "gap": "; ".join(gaps) or None}


def shareholding(symbol, quarters=8):
    """Quarterly shareholding pattern + promoter pledge in the shared envelope.

    `data = {symbol, quarters: [...], pledge: [...]}`; an absent pledge list arrives as the
    labelled gap `fetch_nse_shareholding` built, meaning UNKNOWN rather than nil.
    """
    res = fetch_nse_shareholding(symbol, quarters=quarters)
    return _envelope(bool(res["items"]), "NSE",
                     {"symbol": symbol, "quarters": res["items"], "pledge": res["pledge"]},
                     [res["gap"]] if res["gap"] else [])


def corporate_actions(symbol):
    """Forthcoming/recent corporate actions in the shared envelope:
    `data = {symbol, corporate_actions: [...]}`."""
    res = fetch_nse_corp_actions(symbol)
    return _envelope(bool(res["items"]), "NSE",
                     {"symbol": symbol, "corporate_actions": res["items"]},
                     [res["gap"]] if res["gap"] else [])


def _dedupe(items):
    """Collapse a repeated event to one row; keep the first seen."""
    seen, out = set(), []
    for it in items:
        key = (it["date"], it["headline"][:80].lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def summarize(symbol, days=30, fresh=False):
    """Full best-effort pull for one NSE symbol, in the data-spine envelope.

    Announcements + corporate actions. A blocked call records a *labelled* gap and the run
    returns whatever it gathered; `ok` is true when at least one announcement came back.
    """
    symbol = _norm_symbol(symbol)
    cache_file = os.path.join(paths.cache_dir("filings"), f"{symbol}_{days}.json")
    if not fresh and os.path.exists(cache_file):
        try:
            with open(cache_file) as fh:
                cached = json.load(fh)
            if cached.get("data", {}).get("date") == date.today().isoformat():
                return cached
        except Exception:  # noqa: BLE001 — a bad cache file never blocks a fetch
            pass

    gaps, sources, items, corp_actions = [], [], [], []
    if not symbol:
        gaps.append("no NSE symbol given — filings are fetched by NSE symbol")
    else:
        ann = fetch_nse_announcements(symbol, days)
        items += ann["items"]
        if ann["items"]:
            sources.append("NSE")
        if ann["gap"]:
            gaps.append(ann["gap"])

        ca = fetch_nse_corp_actions(symbol)
        corp_actions = ca["items"]
        if ca["gap"] and not ca["items"] and "no forthcoming" not in ca["gap"]:
            gaps.append(ca["gap"])

    items = _dedupe(items)
    act_on = [a for a in items if a["tier"] == "act-on"]
    monitor = [a for a in items if a["tier"] == "monitor"]
    data = {
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
    env = _envelope(bool(items), "+".join(sources) if sources else None, data, gaps)
    if items:
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
