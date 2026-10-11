#!/usr/bin/env python3
"""Exchange-filings fetch + materiality classification.

`filings-watch` wraps this with the judgement/report; `daily-brief` calls it for the
watchlist/holdings scan. `classify_materiality` is the deterministic heart — most filings
are noise, and this is the filter that finds the few that are not.

NSE is the only exchange source, so the primary key is the NSE symbol. A company listed
only on BSE is reported as a labelled gap rather than silently absorbed.

Returns the shared data-spine envelope (finance/contracts.md).

Reached through: get_filings, get_shareholding, get_corporate_actions.
"""
from __future__ import annotations

import json
import hashlib
import os
from datetime import date, timedelta
from urllib.parse import urlencode, urlsplit

from finance import paths
from finance import spine
from finance import transport
from finance.spine import envelope as _envelope, f as _f, norm_symbol as _norm_symbol

# Keep this taxonomy in sync with references/reference.md.
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


def _symbol_url(endpoint, symbol, **params):
    return endpoint + "?" + urlencode({"index": "equities", "symbol": symbol, **params})


def _scope_rows(rows, symbol, label):
    """An ignored server-side filter must never attribute another issuer's filings."""
    scoped = [row for row in rows if isinstance(row, dict)
              and _norm_symbol(_first(row, "symbol", "sym")) == symbol]
    dropped = len(rows) - len(scoped)
    gap = (f"{label}: dropped {dropped} foreign, unidentified or malformed rows"
           if dropped else None)
    return scoped, gap


def fetch_nse_announcements(symbol, days=30):
    """NSE corporate announcements for one equity symbol over the last `days`.

    Returns {items: [...], gap: str|None} — never raises."""
    symbol = _norm_symbol(symbol)
    if not symbol:
        return {"items": [], "gap": "no NSE symbol given for announcements"}
    to_d = date.today()
    from_d = to_d - timedelta(days=days)
    url = _symbol_url(_ANN_URL, symbol, from_date=from_d.strftime("%d-%m-%Y"),
                      to_date=to_d.strftime("%d-%m-%Y"))
    rows, gap = _nse_json(url, _ANN_REFERER)
    if gap:
        return {"items": [], "gap": f"NSE announcements: {gap}"}

    scoped, scope_gap = _scope_rows(rows, symbol, "NSE announcements")

    out = []
    for r in scoped:
        subject = _first(r, "attchmntText", "desc")
        category = _first(r, "desc", "smIndustry")
        head = (category + " — " + subject).strip(" —") if subject else category
        if not head:
            continue
        tier, emoji, reason = classify_materiality(head)
        out.append({
            "date": spine.iso_date(_first(r, "an_dt", "sort_date")),
            "headline": head,
            "category": category,
            "tier": tier, "emoji": emoji, "why": reason,
            "attachment": _first(r, "attchmntFile"),
            "exchange": "NSE",
        })
    gap = scope_gap or ("NSE announcements: none in window for this symbol" if not out else None)
    return {"items": out, "gap": gap}


def fetch_nse_corp_actions(symbol):
    """Forthcoming/recent corporate actions (dividend, split, bonus, record dates).

    Returns {items: [...], gap: str|None}."""
    symbol = _norm_symbol(symbol)
    if not symbol:
        return {"items": [], "gap": "no NSE symbol given for corporate actions"}
    rows, gap = _nse_json(_symbol_url(_CA_URL, symbol), _CA_REFERER)
    if gap:
        return {"items": [], "gap": f"NSE corporate actions: {gap}"}
    rows, scope_gap = _scope_rows(rows, symbol, "NSE corporate actions")
    out = []
    for r in rows:
        subject = _first(r, "subject", "purpose")
        if not subject:
            continue
        out.append({
            "subject": str(subject)[:200],
            "ex_date": spine.iso_date(_first(r, "exDate")),
            "record_date": spine.iso_date(_first(r, "recDate")),
            "series": _first(r, "series"),
            "isin": _first(r, "isin"),
            "exchange": "NSE",
        })
    return {"items": out, "gap": scope_gap or (None if out else "no forthcoming corporate actions")}


_SHP_REFERER = "https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern"
_SHP_URL = "https://www.nseindia.com/api/corporate-share-holdings-master"
_PLEDGE_URL = "https://www.nseindia.com/api/corporate-pledgedata"


_PLEDGE_TAGS = {
    "pledged_pct": "EncumberedShareUnderPledgedAsPercentageOfTotalNumberOfShares",
    "encumbered_pct": "EncumberedSharesHeldAsPercentageOfTotalNumberOfShares",
    "pledged_shares": "NumberOfSharesEncumberedUnderPledged",
    "encumbered_shares": "NumberOfSharesEncumbered",
}
_PLEDGE_FLAG = "WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged"


def _nse_document_url(url):
    """An exchange-hosted HTTPS document link; payload-supplied URLs are untrusted."""
    if not isinstance(url, str):
        return False
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (host == "nseindia.com" or host.endswith(".nseindia.com"))


def pledge_from_xbrl(url):
    """Promoter pledge from the quarter's SEBI shareholding XBRL — the filed source.

    NSE's pledge JSON endpoint is usually empty, which leaves pledge UNKNOWN. The XBRL
    behind the same filing may carry it, including an explicit `false` that settles
    the one distinction that matters: a company that filed "no pledge" versus one whose
    pledge nobody could read.

    Percentages are filed as fractions of the promoter holding (0.7299 = 72.99%).
    Returns {declared, pledged_pct, encumbered_pct, ..., source} or None.
    """
    if not _nse_document_url(url):
        return None
    body, gap = transport.request(url, timeout=45, referer=_SHP_REFERER)
    if gap or not body:
        return None
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(body)
    except (ET.ParseError, TypeError):
        return None
    by_tag = {}
    for element in root.iter():
        local = element.tag.rsplit("}", 1)[-1]
        if local in {*_PLEDGE_TAGS.values(), _PLEDGE_FLAG}:
            by_tag.setdefault(local, []).append(element)
    if not by_tag:
        return None
    gaps, invalid = [], set()

    def fact(tag, parse):
        values = set()
        for element in by_tag.get(tag, []):
            if element.get("{http://www.w3.org/2001/XMLSchema-instance}nil") in ("true", "1"):
                continue
            value = parse((element.text or "").strip())
            if value is None:
                invalid.add(tag)
            else:
                values.add(value)
        if tag in invalid or len(values) > 1:
            invalid.add(tag)
            gaps.append(f"NSE XBRL: invalid or conflicting {tag}; left unknown")
            return None
        return next(iter(values)) if values else None

    def number(text, fraction):
        value = _f(text)
        if value is None or value < 0:
            return None
        if fraction and value > 1 or not fraction and not value.is_integer():
            return None
        return value

    declared = fact(_PLEDGE_FLAG, lambda value: {"true": True, "1": True,
                                                "false": False, "0": False}.get(value.lower()))
    out = {"declared": declared, "source": url, "gaps": gaps}
    for key, tag in _PLEDGE_TAGS.items():
        fraction = key.endswith("_pct")
        value = fact(tag, lambda text: number(text, fraction))
        out[key] = round(value * 100, 2) if value is not None and fraction else value
    if declared is False:
        pledged = ("pledged_pct", "pledged_shares")
        if any(_PLEDGE_TAGS[key] in invalid or (out[key] or 0) > 0 for key in pledged):
            out["declared"] = None
            gaps.append("NSE XBRL: no-pledge declaration conflicts with pledge figures; reconcile filing")
        else:
            for key in pledged:
                if out[key] is None:
                    out[key] = 0
        # A pledge is only one form of encumbrance. The declaration says nothing
        # about the other forms, so their missing values must remain unknown.
    if out["declared"] is None and out["pledged_pct"] is None and out["pledged_shares"] is None:
        gaps.append("NSE XBRL: promoter pledge UNKNOWN, not nil")
    return out


def fetch_nse_shareholding(symbol, quarters=8):
    """Quarterly shareholding pattern + promoter pledge for one NSE symbol.

    Served by the same cookie-bootstrapped request as announcements. Pledge comes from a
    separate endpoint that is frequently empty; an empty pledge list is reported as a
    labelled gap rather than as "no pledge" — those are different facts, and only one of
    them is safe to act on.

    Returns {items: [...], pledge: [...], gap: str|None}."""
    if type(quarters) is not int or quarters <= 0:
        return {"items": [], "pledge": [], "gap": "quarters must be a positive integer"}
    symbol = _norm_symbol(symbol)
    if not symbol:
        return {"items": [], "pledge": [], "gap": "no NSE symbol given for shareholding"}
    rows, gap = _nse_json(_symbol_url(_SHP_URL, symbol), _SHP_REFERER)
    if gap:
        return {"items": [], "pledge": [], "gap": f"NSE shareholding: {gap}"}

    rows, scope_gap = _scope_rows(rows, symbol, "NSE shareholding")
    # Newest filing first by its own period date; the latest XBRL carries the pledge.
    rows = sorted(rows, key=lambda r: spine.iso_date(_first(r, "date")) or "", reverse=True)
    out = []
    for r in rows[:quarters]:
        out.append({
            "quarter": spine.iso_date(_first(r, "date")),
            "promoter_pct": _f(_first(r, "pr_and_prgrp")),
            "public_pct": _f(_first(r, "public_val")),
            "employee_trusts_pct": _f(_first(r, "employeeTrusts")),
            "filed_on": spine.iso_date(_first(r, "submissionDate")),
            "xbrl": _first(r, "xbrl"),
        })

    pledge_rows, pgap = _nse_json(
        _symbol_url(_PLEDGE_URL, symbol), _SHP_REFERER)
    pledge, pledge_gap = _scope_rows(pledge_rows, symbol, "NSE pledge data")
    gaps = [g for g in (scope_gap, pledge_gap) if g]
    if pgap:
        gaps.append(f"NSE pledge data: {pgap}")

    # The JSON endpoint is usually empty; the filing's own XBRL is not.
    summary = pledge_from_xbrl(out[0]["xbrl"]) if out else None
    if summary is not None:
        gaps.extend(summary.get("gaps", []))
    if summary is None and not pledge:
        gaps.append("promoter pledge unreadable from both the NSE endpoint and the "
                    "quarter's XBRL — UNKNOWN, not nil")
    if not out:
        gaps.append("NSE shareholding: no quarters returned for this symbol")
    return {"items": out, "pledge": pledge, "pledge_summary": summary,
            "gap": "; ".join(gaps) or None}


def shareholding(symbol, quarters=8):
    """Quarterly shareholding pattern + promoter pledge in the shared envelope.

    `data = {symbol, quarters: [...], pledge: [...]}`; an absent pledge list arrives as the
    labelled gap `fetch_nse_shareholding` built, meaning UNKNOWN rather than nil.
    """
    res = fetch_nse_shareholding(symbol, quarters=quarters)
    return _envelope(bool(res["items"]), "NSE",
                     {"symbol": symbol, "quarters": res["items"], "pledge": res["pledge"],
                      "pledge_summary": res.get("pledge_summary")},
                     [res["gap"]] if res["gap"] else [])


def corporate_actions(symbol):
    """Forthcoming/recent corporate actions in the shared envelope:
    `data = {symbol, corporate_actions: [...]}`."""
    res = fetch_nse_corp_actions(symbol)
    return _envelope(bool(res["items"]), "NSE",
                     {"symbol": symbol, "corporate_actions": res["items"]},
                     [res["gap"]] if res["gap"] else [])


def _dedupe(items):
    """Collapse identical filing evidence, preserving distinct same-day disclosures."""
    seen, out = set(), []
    for it in items:
        key = (it["date"], it.get("attachment") or "", it["headline"])
        if key in seen:
            continue
        seen.add(key)
        identity = hashlib.sha256(json.dumps(key, ensure_ascii=False).encode("utf-8")).hexdigest()
        out.append({**it, "filing_id": identity})
    return out


def summarize(symbol, days=30, fresh=False):
    """Full best-effort pull for one NSE symbol, in the data-spine envelope.

    Announcements + corporate actions. A blocked call records a *labelled* gap and the run
    returns whatever it gathered; `ok` is true when at least one announcement came back.
    """
    try:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol must be a nonempty NSE symbol")
        symbol = paths.ticker_key(_norm_symbol(symbol))
        if type(days) is not int or not 0 <= days < date.today().toordinal():
            raise ValueError("days must be a nonnegative integer within the supported calendar")
    except ValueError as exc:
        return _envelope(False, "NSE", {"items": []}, [f"invalid filings request: {exc}"])
    # Older snapshots may already have discarded distinct filings by headline prefix.
    cache_file = os.path.join(paths.cache_dir("filings"), f"v3_{symbol}_{days}.json")
    cached = spine.read_cache(cache_file, fresh)
    if cached and cached["data"].get("symbol") == symbol and cached["data"].get("days") == days:
        return cached

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
        if ca["gap"] and "no forthcoming" not in ca["gap"]:
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
        spine.write_cache(cache_file, env)
    return env
