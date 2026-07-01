#!/usr/bin/env python3
"""Offline tests for categorize.py — durable-map precedence, token normalization,
UNCATEGORIZED residue, correction round-trip. No network, temp dir for map I/O.
Run: python3 skills/budget-tracker/scripts/test_categorize.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import categorize as C  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name}  {detail}")


# --- token normalization: UPI / POS / handle variants collapse to one token ---
variants = [
    "UPI/DR/412345678901/ZOMATO/YESB/zomato.pay@ybl/Payment",
    "POS 4123XXXXXX5678 ZOMATO LTD",
    "UPI-ZOMATO LIMITED-zomato@okhdfcbank-HDFC-payment",
]
tokens = {C.normalize_token(v) for v in variants}
check("UPI/POS/handle variants collapse to one token", tokens == {"ZOMATO"}, tokens)
check("numeric-only and short plumbing words dropped",
      C.normalize_token("UPI/DR/99887766/SWIGGY/YBL") == "SWIGGY")

# --- taxonomy resolution + bucket rollup -------------------------------------
cat, bucket, src = C.categorize_one("UPI/ZOMATO/ybl", {})
check("taxonomy maps ZOMATO -> Dine & Entertainment / Lifestyle",
      (cat, bucket, src) == ("Dine & Entertainment", "Lifestyle", "taxonomy"),
      (cat, bucket, src))
cat, bucket, src = C.categorize_one("POS SWIGGY INSTAMART GROCERY", {})
check("overlap resolves to more-specific Groceries (INSTAMART before SWIGGY)",
      cat == "Groceries", cat)

# --- durable map wins over taxonomy ------------------------------------------
# APOLLO would be Medical by taxonomy; the user's map reclassifies it to Shopping.
m = {"APOLLO": "Shopping"}
cat, bucket, src = C.categorize_one("UPI/APOLLO PHARMACY/ybl", m)
check("durable map precedence over taxonomy", (cat, src) == ("Shopping", "map"),
      (cat, src))

# --- UNCATEGORIZED residue ---------------------------------------------------
cat, bucket, src = C.categorize_one("UPI/DR/778899/ZZOUTLET/ybl", {})
check("unknown merchant -> UNCATEGORIZED", (cat, src) == ("UNCATEGORIZED", "uncategorized"),
      (cat, src))

# --- CC-payment / transfer excluded, not counted as spend --------------------
cat, bucket, src = C.categorize_one("HDFC CREDIT CARD PAYMENT via BBPS CC", {})
check("CC bill payment excluded", (bucket, src) == ("Excluded", "excluded"), (bucket, src))

# --- categorize() rollup: debits only, income/excluded not spend -------------
txns = [
    {"date": "2026-05-02", "description": "UPI/ZOMATO/ybl", "amount": 500,
     "direction": "debit", "account": "HDFC"},
    {"date": "2026-05-03", "description": "UPI/BIGBASKET/ybl", "amount": 2000,
     "direction": "debit", "account": "HDFC"},
    {"date": "2026-05-01", "description": "ACME CORP SALARY CREDIT", "amount": 100000,
     "direction": "credit", "account": "HDFC"},
    {"date": "2026-05-05", "description": "HDFC CARD PAYMENT", "amount": 8000,
     "direction": "debit", "account": "HDFC"},
    {"date": "2026-05-06", "description": "UPI/DR/RANDOMSHOP/ybl", "amount": 300,
     "direction": "debit", "account": "HDFC"},
]
res = C.categorize(txns, {})
check("rollup: Lifestyle = 500 (Zomato)", res["by_bucket"].get("Lifestyle") == 500, res["by_bucket"])
check("rollup: Essential = 2000 (BigBasket)", res["by_bucket"].get("Essential") == 2000, res["by_bucket"])
check("rollup: salary credit not counted as spend", "Income" not in res["by_bucket"], res["by_bucket"])
check("rollup: CC payment not counted as spend", "Excluded" not in res["by_bucket"], res["by_bucket"])
check("residue: one UNCATEGORIZED row", len(res["uncategorized"]) == 1, res["uncategorized"])

# --- correction round-trip persists through save/load ------------------------
with tempfile.TemporaryDirectory() as tmp:
    map_path = os.path.join(tmp, "merchant-map.json")
    mm = C.load_map(map_path)
    check("missing map loads as empty dict", mm == {}, mm)
    token = C.apply_correction(mm, "UPI/DR/RANDOMSHOP/ybl", "Shopping")
    check("apply_correction returns the token", token == "RANDOMSHOP", token)
    C.save_map(mm, map_path)

    reloaded = C.load_map(map_path)
    check("map round-trips through disk", reloaded == {"RANDOMSHOP": "Shopping"}, reloaded)
    # the previously-UNCATEGORIZED merchant now resolves from the map
    cat, bucket, src = C.categorize_one("POS RANDOMSHOP OUTLET", reloaded)
    check("corrected merchant resolves via map next run", (cat, src) == ("Shopping", "map"),
          (cat, src))
    res2 = C.categorize(txns, reloaded)
    check("UNCATEGORIZED shrinks after correction", len(res2["uncategorized"]) == 0,
          res2["uncategorized"])

# --- corrupt map degrades to empty, never crashes ----------------------------
with tempfile.TemporaryDirectory() as tmp:
    bad = os.path.join(tmp, "merchant-map.json")
    with open(bad, "w") as f:
        f.write("{not json")
    check("corrupt map loads as empty dict", C.load_map(bad) == {})

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
