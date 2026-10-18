"""Budget computations over a normalized statement table: categories and recurring spend.

A transaction resolves durable merchant map → taxonomy tokens → UNCATEGORIZED. The map is
keyed by `normalize_token`, the one tokenizer used for both lookup and correction, so a
correction always resolves the merchant it was made against. Recurring detection groups
debits by the same token and account.
"""
from datetime import date
import fcntl
import math
import os
import re
import statistics
import threading

from finance import paths, spine

_SOURCE = "finance.compute.budget"

# Most-specific first: SWIGGY INSTAMART resolves to Groceries because INSTAMART is
# scanned before SWIGGY.
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

# Card-bill and self-transfer narrations are not spend; the card's own line items are.
EXCLUDE_TOKENS = ["CRED CLUB", "CARD PAYMENT", "BBPS CC", "AUTOPAY CC", "IB BILLPAY CC",
                  "CC PAYMENT", "CREDIT CARD PAYMENT"]
ATM_TOKENS = ["ATM", "CASH WDL", "CASH WITHDRAWAL", "NWD"]

# Words of three or more letters that are narration plumbing, not a merchant name.
STOPWORDS = {
    "UPI", "POS", "ACH", "NACH", "ECS", "NEFT", "IMPS", "RTGS", "PAYMENT", "PAY",
    "PVT", "LTD", "PRIVATE", "LIMITED", "INDIA", "IN", "TXN", "REF", "PURCHASE",
    "DEBIT", "CREDIT", "TRANSFER", "TRF", "BIL", "BILLPAY", "COLLECT", "REQUEST",
    "THE", "AND", "COM", "TOPUP", "RECHARGE",
}
HANDLE_SUFFIXES = {"YBL", "OKAXIS", "OKICICI", "OKHDFCBANK", "OKSBI", "PAYTM", "IBL",
                   "AXL", "HDFCBANK", "YESB", "AXIS", "APL", "SBI"}

# label, min gap days, max gap days, months per charge
CADENCE_BANDS = [
    ("monthly", 24, 38, 1),
    ("quarterly", 80, 100, 3),
    ("annual", 350, 400, 12),
]
# Recurring by nature: a single sighting is surfaced as a low-confidence candidate.
SUBSCRIPTION_HINTS = {"NETFLIX", "SPOTIFY", "HOTSTAR", "PRIME", "YOUTUBE", "APPLE",
                      "GOOGLE", "ADOBE", "AUDIBLE", "LINKEDIN", "ICLOUD", "GYM",
                      "CULT", "CULTFIT", "SWIGGY ONE", "ZOMATO GOLD"}
AMOUNT_SPREAD_TOL = 0.30
CREEP_THRESHOLD = 0.05
DORMANT_FACTOR = 1.6
_UNCATEGORIZED_SHOWN = 20


def normalize_token(description):
    """Raw narration -> stable merchant token: upper-case, plumbing stripped, first word."""
    words = re.split(r"[^A-Z0-9]+", (description or "").upper())
    for w in words:
        if not w or w.isdigit() or len(w) <= 2:
            continue
        if sum(c.isdigit() for c in w) > len(w) / 2:  # masked card or account number
            continue
        if w in STOPWORDS or w in HANDLE_SUFFIXES:
            continue
        return w
    return re.sub(r"[^A-Z0-9]+", " ", (description or "").upper()).strip()


def matches_token(description, token):
    """A token matches a whole word run, never a substring inside another name."""
    return bool(re.search(r"(?<![A-Z0-9])" + re.escape(token.strip()) + r"(?![A-Z0-9])",
                          (description or "").upper()))


def _taxonomy_category(description):
    for category, tokens in TAXONOMY:
        if any(matches_token(description, tok) for tok in tokens):
            return category
    return None


def categorize_one(description, merchant_map):
    """-> (category, bucket, source); source in {map, taxonomy, excluded, atm, uncategorized}."""
    token = normalize_token(description)
    if token in merchant_map:
        category = merchant_map[token]
        return category, CATEGORY_BUCKET.get(category, "UNCATEGORIZED"), "map"
    if any(matches_token(description, tok) for tok in EXCLUDE_TOKENS):
        return "Transfer/CC Payment", "Excluded", "excluded"
    category = _taxonomy_category(description)
    if category:
        return category, CATEGORY_BUCKET[category], "taxonomy"
    if any(matches_token(description, tok) for tok in ATM_TOKENS):
        return "ATM/Cash", "Lifestyle", "atm"
    return "UNCATEGORIZED", "UNCATEGORIZED", "uncategorized"


def validate_transactions(transactions):
    """-> (clean rows with a positive amount and debit|credit direction, gaps)."""
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
            clean.append(dict(row, amount=amount,
                              direction="debit" if direction in ("debit", "dr", "d") else "credit"))
        except (ValueError, TypeError) as exc:
            gaps.append(f"Transaction {index + 1}: {exc}; skipped")
    return clean, gaps


def categorize(transactions, merchant_map):
    """Label every row and sum debit spend by bucket and category."""
    _validate_map(merchant_map)
    transactions, gaps = validate_transactions(transactions)
    rows, uncategorized = [], []
    by_bucket, by_category = {}, {}
    for t in transactions:
        category, bucket, source = categorize_one(t["description"], merchant_map)
        row = dict(t, category=category, bucket=bucket,
                   token=normalize_token(t["description"]), source=source)
        rows.append(row)
        if source == "uncategorized":
            uncategorized.append(row)
        if t["direction"] == "debit" and bucket not in ("Income", "Excluded", "UNCATEGORIZED"):
            by_bucket[bucket] = by_bucket.get(bucket, 0.0) + t["amount"]
            by_category[category] = by_category.get(category, 0.0) + t["amount"]
            if not math.isfinite(by_bucket[bucket]) or not math.isfinite(by_category[category]):
                raise ValueError("transaction totals exceed supported numeric range")
    return {"transactions": rows, "uncategorized": uncategorized,
            "by_bucket": by_bucket, "by_category": by_category, "gaps": gaps}


def _validate_map(merchant_map):
    if not isinstance(merchant_map, dict):
        raise ValueError("merchant map must be an object")
    for token, category in merchant_map.items():
        if not isinstance(token, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9 ]*", token):
            raise ValueError("merchant-map keys must be normalized tokens")
        if not isinstance(category, str) or category not in CATEGORY_BUCKET:
            raise ValueError("merchant map contains an unsupported category")
    return merchant_map


def load_map(path=None, *, gaps=None):
    """A missing map is empty. An unreadable one raises, unless the caller only reads and
    passes `gaps`, in which case it is reported and categorization uses the taxonomy."""
    try:
        return _validate_map(spine.read_json(path or paths.merchant_map_path()))
    except FileNotFoundError:
        return {}
    except (ValueError, OSError):
        if gaps is None:
            raise
        gaps.append("Merchant map unreadable or invalid; using taxonomy only; saved rules preserved")
        return {}


def save_map(merchant_map, path=None):
    return spine.write_json(_validate_map(merchant_map), path or paths.merchant_map_path())


def apply_correction(merchant_map, description, category):
    if not isinstance(description, str) or not description.strip():
        raise ValueError("merchant description is required")
    token = normalize_token(description)
    _validate_map({token: category})
    merchant_map[token] = category
    return token


_MAP_LOCK = threading.RLock()


def learn(description, category, path=None):
    """Record one correction; the read-modify-write holds a lock across processes."""
    path = os.path.realpath(path or paths.merchant_map_path())
    apply_correction({}, description, category)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _MAP_LOCK, open(path + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        merchant_map = load_map(path)
        token = apply_correction(merchant_map, description, category)
        save_map(merchant_map, path)
    return token


def _day(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("date must be YYYY-MM-DD")
    return date.fromisoformat(value)


def _cadence(gap_days):
    for label, lo, hi, months_per_charge in CADENCE_BANDS:
        if lo <= gap_days <= hi:
            return label, months_per_charge
    return None, None


def detect_recurring(transactions, as_of=None):
    """Recurring debits with cadence, confidence and new / price_creep / dormant flags.

    `as_of` (default: the latest debit) anchors the current month and the dormancy check.
    Dormant charges and single-sighting candidates stay out of the committed total.
    """
    transactions, gaps = validate_transactions(transactions)
    anchor = _day(as_of) if as_of is not None else None
    debits = []
    for row in transactions:
        if row["direction"] != "debit" or row["amount"] == 0:
            continue
        if anchor is not None and _day(row["date"]) > anchor:
            gaps.append("Transaction after as-of date; excluded from recurrence")
            continue
        debits.append(row)
    if not debits:
        return {"as_of": anchor.isoformat() if anchor else None,
                "current_month": anchor.isoformat()[:7] if anchor else None,
                "total_committed_monthly": 0.0, "subscriptions": [],
                "flagged": {"new": [], "price_creep": [], "dormant": []}, "gaps": gaps}

    as_of = anchor or max(_day(t["date"]) for t in debits)
    current_month = as_of.isoformat()[:7]

    groups = {}
    for t in debits:
        category, bucket, _ = categorize_one(t["description"], {})
        if bucket in ("Excluded", "Income", "Investments") or category == "ATM/Cash":
            continue
        groups.setdefault((normalize_token(t["description"]), t.get("account", "")), []).append(t)

    subs = []
    for (token, account), rows in groups.items():
        rows = sorted(rows, key=lambda r: r["date"])
        dates = [_day(r["date"]) for r in rows]
        amounts = [r["amount"] for r in rows]
        months = sorted({r["date"][:7] for r in rows})
        n = len(rows)
        desc = rows[-1]["description"]

        cadence, months_per_charge, cadence_days, confidence = None, None, None, None
        if n >= 2:
            intervals = [(dates[i] - dates[i - 1]).days for i in range(1, n)]
            cadence_days = statistics.median(intervals)
            cadence, months_per_charge = _cadence(cadence_days)
            median_amount = statistics.median(amounts)
            spread = (max(amounts) - min(amounts)) / median_amount if median_amount else 0
            regular = cadence and all(_cadence(gap)[0] == cadence for gap in intervals)
            if regular and spread <= AMOUNT_SPREAD_TOL + CREEP_THRESHOLD:
                confidence = "high" if n >= 3 else "medium"
        if confidence is None:
            if n == 1 and (token in SUBSCRIPTION_HINTS
                           or any(matches_token(desc, h) for h in SUBSCRIPTION_HINTS)):
                cadence, months_per_charge, confidence = None, None, "low"
            else:
                continue

        latest = amounts[-1]
        flags = []
        if months[0] == current_month:
            flags.append("new")
        if n >= 2:
            if latest > statistics.median(amounts[:-1]) * (1 + CREEP_THRESHOLD):
                flags.append("price_creep")
            if confidence in ("high", "medium") and cadence_days \
                    and (as_of - dates[-1]).days > cadence_days * DORMANT_FACTOR:
                flags.append("dormant")

        subs.append({
            "merchant": token,
            "account": account,
            "description": desc,
            "category": categorize_one(desc, {})[0],
            "cadence": cadence,
            "amount": round(latest, 2),
            "monthly_equivalent": (round(latest / months_per_charge, 2)
                                   if months_per_charge is not None else None),
            "occurrences": n,
            "months_observed": months,
            "last_seen": dates[-1].isoformat(),
            "confidence": confidence,
            "prior_amount": round(statistics.median(amounts[:-1]), 2) if n >= 2 else None,
            "flags": flags,
        })

    subs.sort(key=lambda s: s["monthly_equivalent"] or 0, reverse=True)
    committed = sum(s["monthly_equivalent"] for s in subs
                    if "dormant" not in s["flags"] and s["monthly_equivalent"] is not None)
    return {
        "as_of": as_of.isoformat(),
        "current_month": current_month,
        "total_committed_monthly": round(committed, 2),
        "subscriptions": subs,
        "flagged": {flag: [s["merchant"] for s in subs if flag in s["flags"]]
                    for flag in ("new", "price_creep", "dormant")},
        "gaps": gaps,
    }


def _output(out, *inputs):
    if any(os.path.realpath(out) == os.path.realpath(p) for p in inputs):
        raise ValueError("output cannot overwrite an input")
    return out


@spine.guarded(_SOURCE)
def categorize_file(transactions, out=None):
    """Categorize a transactions JSON file; the annotated rows go to `out`."""
    gaps = []
    merchant_map = load_map(gaps=gaps)
    result = categorize(spine.read_json(transactions), merchant_map)
    result["gaps"] = gaps + result["gaps"]
    out = _output(out or os.path.join(paths.tmp_dir("budget"), "categorized.json"),
                  transactions, paths.merchant_map_path())
    spine.write_json(result, out)
    residue = {}
    for row in result["uncategorized"]:
        entry = residue.setdefault(row["token"], {"token": row["token"], "count": 0,
                                                  "total": 0.0, "example": row["description"]})
        entry["count"] += 1
        entry["total"] = round(entry["total"] + row["amount"], 2)
    merchants = sorted(residue.values(), key=lambda e: e["total"], reverse=True)
    return spine.envelope(True, _SOURCE, {
        "categorized": len(result["transactions"]),
        "uncategorized": len(result["uncategorized"]),
        "by_bucket": result["by_bucket"],
        "by_category": result["by_category"],
        "uncategorized_merchants": merchants[:_UNCATEGORIZED_SHOWN],
        "uncategorized_merchants_total": len(merchants),
        "result_path": out,
    }, result["gaps"])


@spine.guarded(_SOURCE)
def learn_file(merchant, category):
    token = learn(merchant, category)
    return spine.envelope(True, _SOURCE, {"token": token, "category": category,
                                          "map_path": paths.merchant_map_path()}, [])


@spine.guarded(_SOURCE)
def recurring_file(transactions, as_of=None, out=None):
    """Recurring spend over a transactions JSON file spanning current and prior months."""
    result = detect_recurring(spine.read_json(transactions), as_of=as_of)
    if out:
        spine.write_json(result, _output(out, transactions))
    gaps = result.pop("gaps")
    return spine.envelope(True, _SOURCE, dict(result, result_path=out), gaps)
