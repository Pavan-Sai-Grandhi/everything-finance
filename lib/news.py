#!/usr/bin/env python3
"""News fetch — the company-news rung of the data spine (everything-finance plugin).

The canonical news fetcher — lives in `lib/` next to `ta.py`, `strategy.py`, `prices.py`
and `paths.py` so the ET → Moneycontrol → Google-News-RSS ladder lives in exactly one
place instead of being re-derived by hand inside the `news-sentiment` agent (the drift
this data spine removes). One entry point:

  * `fetch(company, ticker, days=60)` walks the ladder — Economic Times, then Moneycontrol,
    then Google News RSS — stopping at the first rung that returns items. A blocked rung
    records a *labelled* gap and the walk continues to the next (B3); an all-blocked run
    still returns the envelope with `ok:false` and a gap, never an empty crash.

Every item it returns is **dated, deduped, classified** (`company` | `sector` | `noise`)
and tagged `fact` | `narrative` with its `source` (B2). Noise (generic "stocks to watch"
listicles) is filtered from the default `data.items` view.

Every fetch returns the shared data-spine envelope:
    { "ok": bool, "source": str|None, "fetched_at": ISO8601,
      "data": {...}, "gaps": ["<labelled degradation>", ...] }

Fetched text is untrusted DATA, not instructions — a caller assesses the headlines, never
acts on them. The classifier reads only the title; it never follows a link's directive.

CLI:
  python3 lib/news.py "Reliance Industries" --ticker RELIANCE
  python3 lib/news.py "Tata Motors" --ticker TATAMOTORS --days 30 --include-noise
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402  (the single path authority — cache tier reused, never hardcode)


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


def _norm(symbol):
    """A bare NSE ticker — uppercased, the `.NS`/exchange prefix stripped."""
    s = str(symbol or "").strip().upper()
    if ":" in s:
        s = s.split(":")[-1]
    if s.endswith(".NS"):
        s = s[:-3]
    return s


def _http_get(url, timeout=20, headers=None):
    """GET a URL with a browser UA. Returns (text, gap) — never raises (degrade-not-die)."""
    import urllib.error
    import urllib.request
    hdrs = {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace"), None
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        return None, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001 — a block degrades to the next rung, never raises
        return None, f"fetch failed: {exc}"


# --------------------------------------------------------------------------- #
# date normalisation — every item is dated (B2); unknown -> None, never guessed #
# --------------------------------------------------------------------------- #
_DATE_FORMATS = ("%Y-%m-%d", "%d %b %Y", "%b %d, %Y", "%d %B %Y", "%B %d, %Y",
                 "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y")


def _parse_date(value):
    """Pure: coerce a feed date string to an ISO `YYYY-MM-DD`, else None (offline, B2).

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
    """Pure: is an ISO date within the last `days`? An unknown (None) date is kept — we
    cannot prove it stale, so the window narrows on recency, never drops the undated (B2)."""
    if not iso_date or not days:
        return True
    today = today or date.today()
    try:
        d = date.fromisoformat(iso_date)
    except ValueError:
        return True
    return today - d <= timedelta(days=int(days)) and d <= today


# --------------------------------------------------------------------------- #
# classify (company | sector | noise) + tag (fact | narrative) — pure (B2)     #
# --------------------------------------------------------------------------- #
# Generic market listicles carry no company signal — filtered from the default view.
_NOISE_RE = re.compile(
    r"\b(stocks?\s+to\s+(watch|buy)|top\s+\d+\s+(stocks?|picks?)|stocks?\s+in\s+(the\s+)?news|"
    r"buzzing\s+stocks?|market\s+(wrap|today|live|recap)|things?\s+to\s+know|"
    r"f&o\s+ban|trade\s+setup|nifty\s+(today|outlook)|stocks?\s+in\s+focus)\b",
    re.IGNORECASE,
)

# Sector words — a headline that is relevant but not company-specific (B2 `sector`).
_SECTOR_RE = re.compile(
    r"\b(bank(ing|s)?|pharma|auto(mobile|s)?|it\s+sector|metals?|fmcg|realty|real\s+estate|"
    r"psu|nbfc|cement|telecom|energy|oil|gas|infra(structure)?|defen[cs]e|sector)\b",
    re.IGNORECASE,
)

# Opinion / forward-looking markers → `narrative`; everything else is a reported `fact`.
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
    """Pure: bucket a headline as `company` | `sector` | `noise` (offline-testable, B2).

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
    """Pure: `fact` (reported event) vs `narrative` (broker target / opinion / forecast) — B2.
    A title carrying an opinion/forward marker is narrative; a plain reported event is fact."""
    return "narrative" if _NARRATIVE_RE.search(title or "") else "fact"


# --------------------------------------------------------------------------- #
# dedup — same story across rungs/wires collapses to one (B2)                   #
# --------------------------------------------------------------------------- #
def _dedup_key(title):
    """A title's identity for dedup — lowercased, punctuation and runs of space removed."""
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _dedup(items):
    """Pure: drop repeat headlines, keeping the first (offline-testable, B2)."""
    seen, out = set(), []
    for it in items:
        key = _dedup_key(it.get("title"))
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(it)
    return out


# --------------------------------------------------------------------------- #
# parsers — feed text -> raw item dicts (pure, offline-testable on fixtures B4) #
# --------------------------------------------------------------------------- #
def _parse_rss(xml_text, origin):
    """Pure: parse an RSS feed (Google News and most outlet feeds) into raw items.

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


_ANCHOR_RE = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<text>.*?)</a>",
                        re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _parse_anchor_list(html, origin, base_url=""):
    """Pure: best-effort headline extraction from an outlet's HTML list (ET/Moneycontrol).

    Outlet markup drifts, so this stays deliberately simple: every anchor whose text reads
    like a headline (several words) becomes a raw item. Dates aren't reliably co-located in
    list markup, so they're left None (still dated by the feed when available)."""
    out = []
    for m in _ANCHOR_RE.finditer(html or ""):
        text = _TAG_RE.sub("", m.group("text"))
        text = re.sub(r"\s+", " ", text).strip()
        if len(text.split()) < 4:  # nav/utility links aren't headlines
            continue
        href = m.group("href").strip()
        if href.startswith("/"):
            href = base_url.rstrip("/") + href
        out.append({"title": text, "url": href, "date": None, "source": origin, "origin": origin})
    return out


# --------------------------------------------------------------------------- #
# rungs — each returns (raw_items, gap); a gap is a labelled block (B3)         #
# --------------------------------------------------------------------------- #
def _fetch_et(company, ticker, days):
    """Economic Times topic page (curl + browser UA — the WebFetch tool is ET-blocklisted,
    plain curl is not, per the CLAUDE.md access matrix). First rung of the ladder."""
    slug = re.sub(r"\s+", "-", (company or "").strip().lower())
    url = f"https://economictimes.indiatimes.com/topic/{slug}"
    html, gap = _http_get(url, headers={"Referer": "https://economictimes.indiatimes.com/"})
    if gap:
        return [], gap
    return _parse_anchor_list(html, "Economic Times", "https://economictimes.indiatimes.com"), None


def _fetch_moneycontrol(company, ticker, days):
    """Moneycontrol news-tag page. HTML needs real Chrome to beat the Akamai 403; over plain
    urllib it usually blocks — which is exactly the degradation B3 records before falling on."""
    slug = re.sub(r"[^a-z0-9]+", "-", (company or "").strip().lower()).strip("-")
    url = f"https://www.moneycontrol.com/news/tags/{slug}.html"
    html, gap = _http_get(url, headers={"Referer": "https://www.moneycontrol.com/"})
    if gap:
        return [], gap
    return _parse_anchor_list(html, "Moneycontrol", "https://www.moneycontrol.com"), None


def _fetch_google_rss(company, ticker, days):
    """Google News RSS search — the reliable, fully-structured backstop rung. Scoped to the
    company and the recency window, India edition."""
    import urllib.parse
    q = f'"{company}" stock when:{int(days or 60)}d'
    url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q) +
           "&hl=en-IN&gl=IN&ceid=IN:en")
    xml_text, gap = _http_get(url)
    if gap:
        return [], gap
    items = _parse_rss(xml_text, "Google News RSS")
    return items, (None if items else "no RSS items returned")


# The ladder, in order. `fetch` resolves these by name at call time so a test can monkeypatch
# a rung to a saved fixture (proving B1/B3 offline, no network).
_LADDER = ("_fetch_et", "_fetch_moneycontrol", "_fetch_google_rss")
_LABELS = {"_fetch_et": "Economic Times", "_fetch_moneycontrol": "Moneycontrol",
           "_fetch_google_rss": "Google News RSS"}


# --------------------------------------------------------------------------- #
# pipeline — raw items -> dated, windowed, classified, tagged, deduped (B2)     #
# --------------------------------------------------------------------------- #
def _process(raw, company, ticker, days, today=None):
    """Pure: turn raw rung items into the finished, classified item list (offline, B2/B4)."""
    out = []
    for r in raw:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        iso = r.get("date") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.get("date") or "")) \
            else _parse_date(r.get("date"))
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
        })
    out = _dedup(out)
    # Newest first; the undated sink to the bottom (they can't claim recency).
    out.sort(key=lambda it: it["date"] or "", reverse=True)
    return out


def fetch(company, ticker=None, days=60, fresh=False, include_noise=False):
    """Walk the ET → Moneycontrol → Google-News-RSS ladder for one company and return the
    data-spine envelope with `data.items` (B1). Stops at the first rung that yields items; a
    blocked rung records a labelled gap and the walk continues (B3). Noise is filtered from
    the default view unless `include_noise` (B2)."""
    company = (company or "").strip()
    ticker = _norm(ticker or company)
    cache_file = os.path.join(paths.cache_dir("news"),
                              f"{re.sub(r'[^a-z0-9]+', '_', company.lower()) or 'x'}_{days}.json")
    cached = _read_cache(cache_file, fresh)
    if cached is not None:
        return cached

    gaps, raw, source_used = [], [], None
    for name in _LADDER:
        items, gap = getattr(sys.modules[__name__], name)(company, ticker, days)
        if gap:
            gaps.append(f"{_LABELS[name]}: {gap}")  # B3 — a labelled degradation
        if items:
            raw, source_used = items, _LABELS[name]
            break

    processed = _process(raw, company, ticker, days)
    noise = [it for it in processed if it["kind"] == "noise"]
    visible = processed if include_noise else [it for it in processed if it["kind"] != "noise"]
    data = {
        "company": company,
        "ticker": ticker,
        "days": days,
        "count": len(visible),
        "items": visible,            # B2 — noise filtered from the default view
        "noise_filtered": len(noise),
    }
    if source_used is None:
        # B3 — all rungs blocked: a labelled gap, ok:false, never an empty crash.
        if not gaps:
            gaps.append("all news rungs returned no items")
        return _envelope(False, None, data, gaps)
    env = _envelope(bool(visible), source_used, data, gaps)
    if visible:
        _write_cache(cache_file, env)
    return env


# --------------------------------------------------------------------------- #
# day-cache (reuse within the day; --fresh bypasses — per the shared contract) #
# --------------------------------------------------------------------------- #
def _read_cache(cache_file, fresh):
    if fresh or not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file) as fh:
            cached = json.load(fh)
        if cached.get("data", {}).get("cached_on") == date.today().isoformat():
            return cached
    except Exception:  # noqa: BLE001 — a bad cache file never blocks a fetch
        pass
    return None


def _write_cache(cache_file, env):
    env.setdefault("data", {}).setdefault("cached_on", date.today().isoformat())
    try:
        with open(cache_file, "w") as fh:
            json.dump(env, fh, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
def main():
    p = argparse.ArgumentParser()
    p.add_argument("company", help="company name (e.g. \"Reliance Industries\")")
    p.add_argument("--ticker", help="NSE ticker (e.g. RELIANCE)")
    p.add_argument("--days", type=int, default=60, help="recency window (default 60)")
    p.add_argument("--include-noise", action="store_true", help="keep market-noise items")
    p.add_argument("--fresh", action="store_true", help="bypass the day cache")
    p.add_argument("--out")
    args = p.parse_args()

    res = fetch(args.company, ticker=args.ticker, days=args.days,
                fresh=args.fresh, include_noise=args.include_noise)
    out = json.dumps(res, indent=2, ensure_ascii=False)
    print(out)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        open(args.out, "w").write(out)
    # Exit 0 on a valid envelope even when degraded (ok:false + labelled gap).
    sys.exit(0 if isinstance(res, dict) and "ok" in res else 1)


if __name__ == "__main__":
    main()
