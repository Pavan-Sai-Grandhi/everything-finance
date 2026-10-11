#!/usr/bin/env python3
"""Categorize a normalized transaction table — durable map first, taxonomy second.

The one place a merchant becomes a category, so the live review and any re-run agree.
Resolution order per transaction:

    durable merchant→category map  →  reference.md taxonomy tokens  →  UNCATEGORIZED

The durable map (``paths.merchant_map_path()``) is keyed by a *normalized merchant
token* (``ZOMATO``, ``SWIGGY``), not the raw narration, so UPI / POS / handle variants
of the same merchant collapse to one rule. When the user corrects a categorization,
``apply_correction`` writes that token→category back, so UNCATEGORIZED shrinks month
over month. ``normalize_token`` is the single tokenizer used for BOTH lookup and
write, which is what makes the correction round-trip stick.

CLI (the file-handoff the skill uses):
    categorize.py --txns txns.json [--map merchant-map.json] [--out out.json]
    categorize.py --learn --map merchant-map.json --merchant "<narration>" --category "<Category>"
"""
import argparse
import fcntl
import tempfile
import threading
import json
import math
from datetime import date
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
                   os.path.dirname(os.path.abspath(__file__))))))
from finance import paths  # noqa: E402

# Mirrors references/reference.md.
# Ordered: more-specific categories first so an overlapping narration resolves to the
# narrower one (SWIGGY INSTAMART -> Groceries, not Dine, because INSTAMART is scanned
# before SWIGGY). Each category rolls up into one of the five workbook buckets.
TAXONOMY = [
    ("Groceries", ["BIGBASKET", "BLINKIT", "ZEPTO", "DMART", "INSTAMART",
                   "RELIANCE FRESH", "RELIANCEFRESH", "JIOMART", "KIRANA"]),
    ("Investments", ["ZERODHA", "GROWW", "KUVERA", "COIN", "INDIAN CLEARING",
                     "BSE LIMITED", "INDIANCLEARING", "NPS", "PPF", "SIP", "MUTUAL FUND"]),
    ("Insurance premiums", ["LIC", "HDFC LIFE", "HDFCLIFE", "ICICI PRU", "ICICIPRU",
                            "STAR HEALTH", "STARHEALTH", "ACKO", "DIGIT", "POLICYBAZAAR",
                            "MAX LIFE", "TATA AIA"]),
    ("Medical", ["APOLLO", "PHARMEASY", "TATA 1MG", "1MG", "NETMEDS", "PRACTO",
                 "HOSPITAL", "CLINIC", "DIAGNOSTIC"]),
    ("Transportation", ["UBER", "OLA", "RAPIDO", "IRCTC", "IOCL", "HPCL", "BPCL",
                        "FASTAG", "FASTTAG", "METRO", "FUEL", "PETROL"]),
    ("Utilities", ["BESCOM", "TSSPDCL", "TSNPDCL", "MSEB", "JIO", "AIRTEL", "ACT ",
                   "ACTCORP", "BROADBAND", "HP GAS", "HPGAS", "INDANE", "BSNL",
                   "VI ", "VODAFONE", "ELECTRICITY", "WATER BOARD"]),
    ("House rent & maintenance", ["NOBROKER", "NO BROKER", "RENT", "MAINTENANCE",
                                  "SOCIETY", "LANDLORD"]),
    ("Dine & Entertainment", ["ZOMATO", "SWIGGY", "EATCLUB", "BOOKMYSHOW", "PVR",
                              "INOX", "NETFLIX", "SPOTIFY", "HOTSTAR", "PRIME VIDEO",
                              "DOMINOS", "MCDONALD", "KFC", "STARBUCKS", "RESTAURANT"]),
    ("Shopping", ["AMAZON", "FLIPKART", "MYNTRA", "AJIO", "NYKAA", "CROMA", "IKEA",
                  "RELIANCE DIGITAL", "MEESHO"]),
    ("Travel", ["MAKEMYTRIP", "MAKE MY TRIP", "GOIBIBO", "CLEARTRIP", "IXIGO",
                "INDIGO", "VISTARA", "AIR INDIA", "SPICEJET", "OYO", "AIRBNB", "HOTEL"]),
    ("EMIs", ["EMI", "BAJAJ FIN", "BAJAJFIN", "HDFC LTD", "HDB FIN", "ACH D",
              "NACH", "ECS"]),
    ("Income", ["SALARY", "SAL CREDIT", "DIVIDEND", "INTEREST CREDIT", "REFUND"]),
]

CATEGORY_BUCKET = {
    "Groceries": "Essential",
    "Utilities": "Essential",
    "House rent & maintenance": "Essential",
    "Medical": "Essential",
    "Insurance premiums": "Essential",
    "Transportation": "Essential",
    "Dine & Entertainment": "Lifestyle",
    "Shopping": "Lifestyle",
    "Travel": "Lifestyle",
    "ATM/Cash": "Lifestyle",
    "EMIs": "EMIs",
    "Investments": "Investments",
    "Income": "Income",
    "Transfer/CC Payment": "Excluded",
    "UNCATEGORIZED": "UNCATEGORIZED",
}

# CC-bill / self-transfer narrations that are NOT spend (the CC's own line items are).
EXCLUDE_TOKENS = ["CRED CLUB", "CARD PAYMENT", "BBPS CC", "AUTOPAY CC", "IB BILLPAY CC",
                  "CC PAYMENT", "CREDIT CARD PAYMENT"]

# ATM / cash withdrawal — surfaced as untracked spend, not analyzed spend.
ATM_TOKENS = ["ATM", "CASH WDL", "CASH WITHDRAWAL", "NWD"]

# Narration plumbing dropped when deriving the merchant token. Short (<=2 char) and
# purely-numeric words are dropped by rule, so this only lists the longer noise words.
STOPWORDS = {
    "UPI", "POS", "ACH", "NACH", "ECS", "NEFT", "IMPS", "RTGS", "PAYMENT", "PAY",
    "PVT", "LTD", "PRIVATE", "LIMITED", "INDIA", "IN", "TXN", "REF", "PURCHASE",
    "DEBIT", "CREDIT", "TRANSFER", "TRF", "BIL", "BILLPAY", "COLLECT", "REQUEST",
    "THE", "AND", "COM", "TOPUP", "RECHARGE",
}
# handle suffixes (…@ybl, …@okhdfcbank) become bare words after split — treat as noise.
HANDLE_SUFFIXES = {"YBL", "OKAXIS", "OKICICI", "OKHDFCBANK", "OKSBI", "PAYTM", "IBL",
                   "AXL", "HDFCBANK", "YESB", "AXIS", "APL", "SBI"}


def normalize_token(description):
    """Raw narration -> stable merchant token (upper, plumbing stripped, first word).

    The SAME function keys the map on lookup and on write, so a correction always
    resolves the merchant it was made against."""
    words = re.split(r"[^A-Z0-9]+", (description or "").upper())
    for w in words:
        if not w or w.isdigit() or len(w) <= 2:
            continue
        # masked card / account numbers (e.g. 4123XXXXXX5678) — mostly digits, not a name
        if sum(c.isdigit() for c in w) > len(w) / 2:
            continue
        if w in STOPWORDS or w in HANDLE_SUFFIXES:
            continue
        return w
    # nothing significant left — fall back to the cleaned narration itself
    return re.sub(r"[^A-Z0-9]+", " ", (description or "").upper()).strip()


def matches_token(description, token):
    """Narration punctuation delimits names; substrings inside other names do not."""
    return bool(re.search(r"(?<![A-Z0-9])" + re.escape(token.strip()) + r"(?![A-Z0-9])",
                          (description or "").upper()))


def _taxonomy_category(description):
    up = (description or "").upper()
    for category, tokens in TAXONOMY:
        for tok in tokens:
            if matches_token(up, tok):
                return category
    return None


def categorize_one(description, merchant_map):
    """-> (category, bucket, source). source in
    {map, taxonomy, excluded, atm, uncategorized}."""
    up = (description or "").upper()
    token = normalize_token(description)
    if token in merchant_map:
        cat = merchant_map[token]
        return cat, CATEGORY_BUCKET.get(cat, "UNCATEGORIZED"), "map"

    if any(matches_token(up, tok) for tok in EXCLUDE_TOKENS):
        return "Transfer/CC Payment", "Excluded", "excluded"

    cat = _taxonomy_category(description)
    if cat:
        return cat, CATEGORY_BUCKET[cat], "taxonomy"

    if any(matches_token(up, tok) for tok in ATM_TOKENS):
        return "ATM/Cash", "Lifestyle", "atm"

    return "UNCATEGORIZED", "UNCATEGORIZED", "uncategorized"


def validate_transactions(transactions):
    """Validate the normalized statement boundary once for both budget computations."""
    if not isinstance(transactions, list):
        raise ValueError("transactions must be a list")
    clean, gaps = [], []
    for index, row in enumerate(transactions):
        try:
            if not isinstance(row, dict):
                raise ValueError("transaction must be an object")
            when = row.get("date")
            if not isinstance(when, str) or len(when) != 10:
                raise ValueError("date must be YYYY-MM-DD")
            date.fromisoformat(when)
            direction = str(row.get("direction", "")).strip().lower()
            if direction not in ("debit", "dr", "d", "credit", "cr", "c"):
                raise ValueError("unknown transaction direction")
            raw = row.get("amount")
            try:
                amount = abs(float(raw))
            except (ValueError, TypeError, OverflowError):
                raise ValueError("amount must be a finite number") from None
            if isinstance(raw, bool) or not math.isfinite(amount):
                raise ValueError("amount must be a finite number")
            if not isinstance(row.get("description"), str) or not row["description"].strip():
                raise ValueError("description is missing")
            if row.get("account") is not None and not isinstance(row["account"], str):
                raise ValueError("account must be text")
            clean.append(dict(row, amount=amount, direction=("debit" if direction in ("debit", "dr", "d") else "credit")))
        except (ValueError, TypeError) as exc:
            gaps.append(f"Transaction {index + 1}: {exc}; skipped")
    return clean, gaps


def categorize(transactions, merchant_map):
    """Label every txn; roll up spend by bucket/category; collect the residue.

    ``transactions`` = list of normalized dicts (date, description, amount, direction,
    account). Returns the same rows annotated with ``category``/``bucket``/``token``/
    ``source``, plus ``uncategorized`` (rows needing a decision), ``by_bucket`` and
    ``by_category`` spend sums (debits only; credits are inflow, not spend)."""
    _validate_map(merchant_map)
    transactions, gaps = validate_transactions(transactions)
    out, uncat = [], []
    by_bucket, by_category = {}, {}
    for t in transactions:
        cat, bucket, source = categorize_one(t.get("description", ""), merchant_map)
        row = dict(t)
        row["category"] = cat
        row["bucket"] = bucket
        row["token"] = normalize_token(t.get("description", ""))
        row["source"] = source
        out.append(row)
        if source == "uncategorized":
            uncat.append(row)
        # spend = debits landing in a real spend bucket (skip Income / Excluded)
        if str(t.get("direction", "")).lower() in ("debit", "dr", "d") and \
                bucket not in ("Income", "Excluded", "UNCATEGORIZED"):
            amt = abs(float(t.get("amount", 0) or 0))
            by_bucket[bucket] = by_bucket.get(bucket, 0.0) + amt
            by_category[cat] = by_category.get(cat, 0.0) + amt
            if not math.isfinite(by_bucket[bucket]) or not math.isfinite(by_category[cat]):
                raise ValueError("transaction totals exceed supported numeric range")
    return {
        "transactions": out,
        "uncategorized": uncat,
        "by_bucket": by_bucket,
        "by_category": by_category,
        "gaps": gaps,
    }


def _validate_map(merchant_map):
    if not isinstance(merchant_map, dict):
        raise ValueError("merchant map must be an object")
    for token, category in merchant_map.items():
        if not isinstance(token, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9 ]*", token):
            raise ValueError("merchant-map keys must be normalized tokens")
        if not isinstance(category, str) or category not in CATEGORY_BUCKET:
            raise ValueError("merchant map contains an unsupported category")
    return merchant_map


def _unique_map(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("merchant map contains duplicate keys")
        result[key] = value
    return result


def load_map(path=None, *, gaps=None):
    """Missing map is empty. Damaged state is never silently writable.

    Read-only callers may supply a gap list to continue with taxonomy alone.
    Writers omit it and must preserve a map they cannot read and validate.
    """
    path = path or paths.merchant_map_path()
    try:
        with open(path, encoding="utf-8") as stream:
            return _validate_map(json.load(stream, object_pairs_hook=_unique_map))
    except FileNotFoundError:
        return {}
    except (ValueError, OSError) as exc:
        if gaps is None:
            raise
        gaps.append("Merchant map unreadable or invalid; using taxonomy only; saved rules preserved")
        return {}


def write_json(value, path):
    """Publish a complete JSON file atomically, preserving prior data on failure."""
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory,
                                         delete=False) as stream:
            pending = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        if pending and os.path.exists(pending):
            os.unlink(pending)
    return path


def save_map(merchant_map, path=None):
    return write_json(_validate_map(merchant_map), path or paths.merchant_map_path())


def apply_correction(merchant_map, description, category):
    """Apply one validated correction to an in-memory map."""
    if not isinstance(description, str) or not description.strip():
        raise ValueError("merchant description is required")
    token = normalize_token(description)
    _validate_map({token: category})
    merchant_map[token] = category
    return token


_MAP_LOCK = threading.RLock()


def learn(description, category, path=None):
    """Serialize the whole read-modify-write transaction across processes/threads."""
    path = os.path.realpath(path or paths.merchant_map_path())
    apply_correction({}, description, category)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _MAP_LOCK, open(path + '.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        merchant_map = load_map(path)
        token = apply_correction(merchant_map, description, category)
        save_map(merchant_map, path)
    return token



def _main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--txns", help="JSON file: list of normalized transactions")
    ap.add_argument("--map", dest="map_path", help="merchant-map.json (default: paths)")
    ap.add_argument("--out", help="write categorized result JSON here")
    ap.add_argument("--learn", action="store_true",
                    help="record one correction into the map and exit")
    ap.add_argument("--merchant", help="narration to learn (with --learn)")
    ap.add_argument("--category", help="category to assign (with --learn)")
    args = ap.parse_args(argv)

    map_path = args.map_path or paths.merchant_map_path()
    if args.learn:
        if not args.merchant or not args.category:
            ap.error("--learn needs --merchant and --category")
        token = learn(args.merchant, args.category, map_path)
        print(json.dumps({"learned": {token: args.category}, "map": map_path}))
        return 0

    if not args.txns:
        ap.error("--txns is required (or use --learn)")
    gaps = []
    merchant_map = load_map(map_path, gaps=gaps)
    with open(args.txns) as f:
        transactions = json.load(f)
    result = categorize(transactions, merchant_map)
    result.setdefault("gaps", []).extend(gaps)
    payload = json.dumps(result, indent=2, allow_nan=False)
    if args.out:
        if os.path.realpath(args.out) in (os.path.realpath(args.txns), os.path.realpath(map_path)):
            raise ValueError("output cannot overwrite transactions or merchant map")
        write_json(result, args.out)
        print(json.dumps({"out": args.out,
                          "uncategorized": len(result["uncategorized"]),
                          "categorized": len(result["transactions"])}))
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(_main())
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "gaps": [str(exc)]}), file=sys.stderr)
        sys.exit(1)
