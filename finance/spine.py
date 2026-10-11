#!/usr/bin/env python3
"""Primitives every data-spine fetcher shares — the envelope, coercion, the day cache.

`transport.py` owns the network; this owns the shape of what comes back. Each domain
fetcher (`prices`, `market`, `funds`, `fundamentals`, `news`, `filings`) imports from here
rather than carrying its own copy, so the envelope contract and the cache-freshness rule
have exactly one definition. See `finance/contracts.md`.
"""
import json
import hashlib
import os
import tempfile
from datetime import date, datetime

# Values that mean "absent" in a scraped cell. A blank must coerce to None, never 0 — a
# fabricated zero silently poisons an average or a percentage series.
_BLANKS = {"", "-", "--", "NA", "N.A.", "N/A", "NONE", "NULL"}


def envelope(ok, source, data, gaps):
    """The contract every data-spine fetch returns (see finance/contracts.md)."""
    return {
        "ok": bool(ok),
        "source": source,
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data": data,
        "gaps": gaps,
    }


def f(value):
    """Coerce a scraped cell to float, else None. Tolerates thousands separators and `%`."""
    if value is None:
        return None
    try:
        text = str(value).strip()
        if text.upper() in _BLANKS:
            return None
        out = float(text.replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None
    # NaN and inf are not usable values. A missing close may reflect provider
    # gaps or an unfinished session; its cause cannot be inferred from NaN alone.
    return out if out == out and out not in (float("inf"), float("-inf")) else None


_MONTHS = {m: i for i, m in enumerate(
    ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"], 1)}


def iso_date(value):
    """Coerce a source's date string to YYYY-MM-DD, else None.

    NSE serves DD-Mon-YYYY ("17-Aug-2026") and DD-MON-YYYY, Yahoo and mfapi serve ISO.
    Left as-is they cannot be compared or sorted against each other, and a consumer
    doing date arithmetic across two tools raises or silently mis-orders.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            return None
    parts = text.replace("/", "-").split("-")
    if len(parts) >= 3:
        d, mon, y = parts[0].strip(), parts[1].strip().upper()[:3], parts[2].strip()[:4]
        month = _MONTHS.get(mon)
        if month and d.isdigit() and y.isdigit():
            try:
                return date(int(y), month, int(d)).isoformat()
            except ValueError:
                return None
    return None


def pct(numerator, denominator, places=2):
    """`numerator/denominator` as a percentage, or None if either is missing or the
    denominator is zero. Coerces through `f`, so a published blank never becomes 0%."""
    n, d = f(numerator), f(denominator)
    return round(100.0 * n / d, places) if n is not None and d else None


def first(row, *keys, default=None):
    """First present, non-empty value among `keys`, else `default`."""
    if not isinstance(row, dict):
        return default
    for k in keys:
        if k in row and row[k] not in (None, "", [], {}):
            return row[k]
    return default


def norm_symbol(value):
    """A bare NSE symbol — uppercased, exchange prefix and `.NS` suffix stripped."""
    s = str(value or "").strip().upper()
    if ":" in s:
        s = s.split(":")[-1]
    if s.endswith(".NS"):
        s = s[:-3]
    return s


# Reserved: a source's own "date" must never be mistaken for our fetch stamp.
CACHE_STAMP = "_cached_on"

def today():
    return date.today().isoformat()


def read_cache(path, fresh, stamp_key=CACHE_STAMP, max_age_days=0):
    """The cached envelope, or None. `max_age_days=0` means it must carry today's stamp.

    A corrupt or unreadable cache file returns None — it never blocks a fetch.
    """
    if fresh or not os.path.exists(path):
        return None
    try:
        with open(path) as fh:
            blob = json.load(fh)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(blob, dict) or not isinstance(blob.get("data"), dict):
        return None
    stamp = blob["data"].get(stamp_key)
    if not stamp:
        return None
    if max_age_days <= 0:
        return blob if stamp == today() else None
    try:
        age = (date.today() - date.fromisoformat(stamp)).days
    except (TypeError, ValueError):
        return None
    return blob if 0 <= age <= max_age_days else None


def write_cache(path, env, stamp_key=CACHE_STAMP):
    """Stamp the envelope with our fetch date and persist it. A failed write is ignored.

    Assigned under a reserved key, never setdefault under a shared one: several sources
    publish their own `date` in `data`, and an inherited value makes the stamp a no-op —
    freshness would then be judged by the source's opinion of the date rather than by
    when we fetched. The source's own date field is left untouched.
    """
    env.setdefault("data", {})[stamp_key] = today()
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=os.path.dirname(os.path.abspath(path)),
                                         delete=False, encoding="utf-8") as fh:
            pending = fh.name
            json.dump(env, fh, ensure_ascii=False)
        os.replace(pending, path)
    except Exception:  # noqa: BLE001
        pass
    finally:
        if pending and os.path.exists(pending):
            os.unlink(pending)


def publish_evidence(prefix, suffix, write):
    """Publish immutable evidence for both CSV and JSON, after a complete write."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=os.path.dirname(os.path.abspath(prefix)),
                                         encoding="utf-8", newline="", delete=False) as stream:
            temporary = stream.name
            write(stream)
        digest = hashlib.sha256()
        with open(temporary, "rb") as stream:
            for block in iter(lambda: stream.read(65536), b""):
                digest.update(block)
        path = f"{prefix}-{digest.hexdigest()}{suffix}"
        os.replace(temporary, path)
        return path
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
