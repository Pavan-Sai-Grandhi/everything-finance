"""Company news from Google News RSS.

Google News RSS is the single source: it indexes the mainstream
Indian outlets, structured and dated, with no bot wall. Because it also indexes low-quality
aggregators, the quality filter is explicit rather than implicit in a hand-picked outlet
list — every item carries a `publisher_tier` of `established` | `aggregator` | `unknown`.

Every item is dated, deduped, classified (`company` | `sector` | `noise`) and tagged
`reported` | `narrative`. Noise (generic "stocks to watch" listicles) is filtered from the
default `data.items` view.

The classifier reads only the title; it never follows a link's directive.

Returns the shared data-spine envelope (finance/contracts.md). Reached through get_news.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta

from finance import paths
from finance import transport
from finance.spine import (envelope as _envelope, norm_symbol as _norm,
                           read_cache as _read_cache, write_cache as _write_cache)


_DATE_FORMATS = ("%Y-%m-%d", "%d %b %Y", "%b %d, %Y", "%d %B %Y", "%B %d, %Y",
                 "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y")


def _parse_date(value):
    """Coerce a feed date string to an ISO `YYYY-MM-DD`, else None.

    Handles RSS RFC-822 `pubDate` ("Fri, 19 Jun 2026 10:30:00 GMT"), ISO, and the common
    Indian-outlet display formats. An unparseable date is left None — a labelled unknown
    beats a fabricated timestamp."""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    # RSS pubDate (RFC 822) — the Google-News / outlet feed format.
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt is not None:
            return dt.date().isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    # ISO 8601 with an optional time/zone suffix.
    iso = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(iso).date().isoformat()
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _within_window(iso_date, days, today=None):
    """Is an ISO date within the last `days`? An unknown (None) date is kept — it cannot be
    proven stale, so the window narrows on recency but never drops the undated."""
    if not iso_date or not days:
        return True
    today = today or date.today()
    try:
        d = date.fromisoformat(iso_date)
    except ValueError:
        return True
    return today - d <= timedelta(days=int(days)) and d <= today


# Generic market listicles carry no company signal — filtered from the default view.
_NOISE_RE = re.compile(
    r"\b(stocks?\s+to\s+(watch|buy)|top\s+\d+\s+(stocks?|picks?)|stocks?\s+in\s+(the\s+)?news|"
    r"buzzing\s+stocks?|market\s+(wrap|today|live|recap)|things?\s+to\s+know|"
    r"f&o\s+ban|trade\s+setup|nifty\s+(today|outlook)|stocks?\s+in\s+focus)\b",
    re.IGNORECASE,
)

# Sector words — a headline that is relevant but not company-specific.
_SECTOR_RE = re.compile(
    r"\b(bank(ing|s)?|pharma|auto(mobile|s)?|it\s+sector|metals?|fmcg|realty|real\s+estate|"
    r"psu|nbfc|cement|telecom|energy|oil|gas|infra(structure)?|defen[cs]e|sector)\b",
    re.IGNORECASE,
)

# Opinion or forward-looking words mark `narrative`; everything else is an unverified `reported` event.
_NARRATIVE_RE = re.compile(
    r"\b(target\s+price|price\s+target|raises?\s+target|cuts?\s+target|upgrade[sd]?|"
    r"downgrade[sd]?|buy|sell|hold|outperform|underperform|overweight|underweight|"
    r"brokerage|broker|rating|outlook|could|may\s+\w+|should\s+you|buzz|recommend[s]?|"
    r"sees?|bets?|view|expert|forecast|estimate[sd]?)\b",
    re.IGNORECASE,
)


def _company_tokens(company, ticker):
    """The lowercase tokens that mark a headline company-specific — significant words of the
    name plus the ticker, dropping corporate-suffix noise ("ltd", "industries")."""
    stop = {"ltd", "limited", "industries", "india", "the", "and", "co", "company",
            "corporation", "corp", "enterprises", "group"}
    toks = {t for t in re.findall(r"[a-z0-9]+", (company or "").lower())
            if len(t) >= 3 and t not in stop}
    tk = _norm(ticker).lower()
    if len(tk) >= 3:
        toks.add(tk)
    return toks


def _classify(title, company, ticker):
    """Bucket a headline as `company` | `sector` | `noise`.

    Order matters: a generic listicle is noise even if it names the company; a headline that
    names the company is company-specific; an un-named headline that carries a sector word is
    sector; anything else from a company-scoped feed defaults to company."""
    t = title or ""
    if _NOISE_RE.search(t):
        return "noise"
    low = t.lower()
    if any(re.search(rf"\b{re.escape(tok)}\b", low) for tok in _company_tokens(company, ticker)):
        return "company"
    if _SECTOR_RE.search(t):
        return "sector"
    return "company"


def _tag(title):
    """Title-only triage; `reported` never means verified against a primary source."""
    return "narrative" if _NARRATIVE_RE.search(title or "") else "reported"


def _dedup_key(title):
    """A title's identity for dedup — lowercased, punctuation and runs of space removed."""
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _dedup(items):
    """Drop repeat headlines, keeping the first."""
    seen, out = set(), []
    for it in items:
        key = _dedup_key(it.get("title"))
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(it)
    return out


def _parse_rss(xml_text, origin):
    """Parse an RSS feed (Google News and most outlet feeds) into raw items.

    Returns [{title, url, date, source, origin}, ...]. Google News wraps the publisher in a
    trailing ` - <Source>` on the title and a `<source>` element; both are recovered."""
    import xml.etree.ElementTree as ET
    out = []
    try:
        root = ET.fromstring(xml_text or "")
    except ET.ParseError:
        return out
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate")
        src_el = item.find("source")
        source = (src_el.text.strip() if src_el is not None and src_el.text else "")
        # Google News appends " - Publisher" to the headline (and repeats it in <source>);
        # split it back off so the same story across wires dedups to one title.
        if " - " in title:
            head, _, tail = title.rpartition(" - ")
            tail = tail.strip()
            if head and (tail == source or origin == "Google News RSS" or not source):
                title = head.strip()
                source = source or tail
        out.append({
            "title": title,
            "url": link,
            "date": _parse_date(pub),
            "source": source or origin,
            "origin": origin,
        })
    return out


# One aggregator as the only source also returns SEO sites that restate a headline without
# reporting it, so publisher quality is explicit data on each item rather than an accident of
# which site was scraped.
#
# `established` — mainstream financial press with newsrooms and corrections policies.
_ESTABLISHED = (
    "economic times", "moneycontrol", "business standard", "livemint", "mint",
    "ndtv profit", "business today", "the hindu", "hindu businessline", "financial express",
    "bloomberg", "reuters", "cnbc", "forbes", "times of india", "the print", "outlook",
    "zeebiz", "zee business", "india today", "firstpost", "deccan herald", "the week",
)
# `aggregator` — restates other outlets' reporting; usable as corroboration, never as
# the sole evidence for a claim that moves a position.
_AGGREGATOR = (
    "equitypandit", "univest", "scanx", "sahi", "trendlyne", "marketsmojo", "5paisa",
    "angel one", "groww", "upstox", "investing.com", "simply wall st", "insider monkey",
    "stocktwits", "tickertape", "smallcase", "dhan", "religare", "samco",
)


def _publisher_tier(source):
    """Rank a publisher `established` | `aggregator` | `unknown`.

    Never drops an item — an unknown wire may still break real news. It labels the
    evidence so a caller can weigh a single-sourced claim from an aggregator differently
    from the same claim in the Economic Times."""
    s = (source or "").strip().lower()
    if not s:
        return "unknown"
    # Display labels are metadata, not authenticated publisher identity. Exact aliases
    # avoid treating "Peppermint" or "Fake Reuters News" as established publishers.
    aliases = {name for name in _ESTABLISHED}
    aliases.update({"the economic times", "moneycontrol.com", "cnbc-tv18",
                    "cnbc tv18", "the hindu businessline", "theprint"})
    if s in aliases:
        return "established"
    if s in _AGGREGATOR:
        return "aggregator"
    return "unknown"


def _fetch_google_rss(company, ticker, days):
    """Google News RSS search, scoped to the company and recency window, India edition.

    The single news source: a 100-item probe found it already indexes Moneycontrol (10),
    the Economic Times (9), Business Today, NDTV Profit, Business Standard and Mint —
    structured, dated, and with no bot wall, so scraping those outlets directly adds
    nothing."""
    import urllib.parse
    q = f'"{company}" stock when:{int(days or 60)}d'
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) +
           "&hl=en-IN&gl=IN&ceid=IN:en")
    xml_text, gap = transport.request(url, timeout=20)
    if gap:
        return [], gap
    items = _parse_rss(xml_text, "Google News RSS")
    return items, (None if items else "no RSS items returned")


def _process(raw, company, ticker, days, today=None):
    """Turn raw feed items into the dated, windowed, classified item list."""
    out = []
    for r in raw:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        iso = _parse_date(r.get("date"))
        if not _within_window(iso, days, today):
            continue
        out.append({
            "date": iso,
            "title": title,
            "url": r.get("url") or "",
            "source": r.get("source") or r.get("origin") or "",
            "origin": r.get("origin") or "",
            "kind": _classify(title, company, ticker),
            "tag": _tag(title),
            "publisher_tier": _publisher_tier(r.get("source") or r.get("origin")),
        })
    out = _dedup(out)
    # Newest first; the undated sink to the bottom (they can't claim recency).
    out.sort(key=lambda it: it["date"] or "", reverse=True)
    return out


def fetch(company, ticker=None, days=60, fresh=False, include_noise=False, today=None):
    """Fetch one company's news and return the data-spine envelope with `data.items`.

    A blocked source records a labelled gap and returns `ok:false` rather than raising or
    returning a silent empty. Noise is filtered from the default view unless
    `include_noise`, and every item carries a `publisher_tier`. `today` fixes the date the
    recency window is measured against, so a caller can window against a known day."""
    try:
        if not isinstance(company, str) or not company.strip():
            raise ValueError("company name is required")
        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            raise ValueError("days must be a positive integer")
        if isinstance(today, str):
            today = date.fromisoformat(today)
        if isinstance(today, datetime):
            today = today.date()
        if today is not None and not isinstance(today, date):
            raise ValueError("today must be an ISO date")
    except (ValueError, TypeError) as exc:
        return _envelope(False, None, {"items": [], "count": 0}, [f"news input: {exc}"])
    company = company.strip()
    ticker = _norm(ticker or company)
    # Cache the source response, not one caller's classification/noise/window view.
    key = hashlib.sha256(json.dumps([company.casefold(), days]).encode()).hexdigest()
    cache_file, cached, cache_gaps = None, None, []
    try:
        cache_file = os.path.join(paths.cache_dir("news"), f"rss-v1-{key}.json")
        cached = _read_cache(cache_file, fresh)
    except OSError:
        cache_gaps.append("news cache unavailable; fetched without cache")
    if cached is not None:
        items = cached["data"].get("items")
        if (cached.get("source") != "Google News RSS"
                or not isinstance(cached.get("fetched_at"), str)
                or not isinstance(cached.get("gaps"), list)
                or not all(isinstance(gap, str) for gap in cached.get("gaps", []))
                or not isinstance(items, list)
                or not all(isinstance(item, dict) and all(
                    item.get(key) is None or isinstance(item[key], str)
                    for key in ("title", "url", "date", "source", "origin")) for item in items)):
            cached = None
    if cached is None:
        raw, gap = _fetch_google_rss(company, ticker, days)
        cached = _envelope(bool(raw), "Google News RSS" if raw else None,
                           {"items": raw}, [f"Google News RSS: {gap}"] if gap else [])
        if raw and cache_file:
            _write_cache(cache_file, cached)
    raw = cached["data"]["items"]
    gaps = list(cached.get("gaps") or []) + cache_gaps
    source_used = cached.get("source")
    processed = _process(raw, company, ticker, days, today)
    noise = [it for it in processed if it["kind"] == "noise"]
    visible = processed if include_noise else [it for it in processed if it["kind"] != "noise"]
    undated = sum(it["date"] is None for it in visible)
    if undated:
        gaps.append(f"Google News RSS: {undated} item(s) have unknown dates; recency unverified")
    data = {
        "company": company,
        "ticker": ticker,
        "days": days,
        "count": len(visible),
        "items": visible,
        "noise_filtered": 0 if include_noise else len(noise),
        "established_count": sum(1 for it in visible
                                 if it["publisher_tier"] == "established"),
    }
    if source_used is None and not gaps:
        gaps.append("Google News RSS: no items returned")
    elif source_used is not None and not visible:
        gaps.append(f"{source_used}: {len(raw)} item(s) returned, none left after the "
                    f"{days}-day window and the noise filter ({len(noise)} noise)")
    env = _envelope(bool(visible), source_used, data, gaps)
    # Local filtering does not refresh the acquisition timestamp.
    env["fetched_at"] = cached["fetched_at"]
    return env
