#!/usr/bin/env python3
"""Primitives every data-spine fetcher shares — the envelope, coercion, the day cache.

`transport.py` owns the network; this owns the shape of what comes back. Each domain
fetcher (`prices`, `market`, `funds`, `fundamentals`, `news`, `filings`) imports from here
rather than carrying its own copy, so the envelope contract and the cache-freshness rule
have exactly one definition. See `lib/contracts.md`.
"""
import json
import os
from datetime import date, datetime

# Values that mean "absent" in a scraped cell. A blank must coerce to None, never 0 — a
# fabricated zero silently poisons an average or a percentage series.
_BLANKS = {"", "-", "--", "NA", "N.A.", "N/A", "NONE", "NULL"}


def envelope(ok, source, data, gaps):
    """The contract every data-spine fetch returns (see lib/contracts.md)."""
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
        return float(text.replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


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


def today():
    return date.today().isoformat()


def read_cache(path, fresh, stamp_key="date", max_age_days=0):
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
    stamp = (blob.get("data") or {}).get(stamp_key)
    if not stamp:
        return None
    if max_age_days <= 0:
        return blob if stamp == today() else None
    try:
        age = (date.today() - date.fromisoformat(stamp)).days
    except (TypeError, ValueError):
        return None
    return blob if age <= max_age_days else None


def write_cache(path, env, stamp_key="date"):
    """Stamp the envelope with today's date and persist it. Failure to write is ignored."""
    env.setdefault("data", {}).setdefault(stamp_key, today())
    try:
        with open(path, "w") as fh:
            json.dump(env, fh, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass
