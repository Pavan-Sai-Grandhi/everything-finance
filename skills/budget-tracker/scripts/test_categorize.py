#!/usr/bin/env python3
"""Offline tests for categorize.py — durable-map precedence, token normalization,
UNCATEGORIZED residue, correction round-trip. No network, temp dir for map I/O.
Run: python3 skills/budget-tracker/scripts/test_categorize.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
import categorize as C  # noqa: E402
from finance.tests.harness import check, summary  # noqa: E402


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
    try:
        C.load_map(bad)
        rejected = False
    except ValueError:
        rejected = True
    check("corrupt map cannot silently become writable empty state", rejected)

for narration in ('CHOCOLATE SHOP', 'PUBLIC BOOKSTORE', 'RENTALITY', 'DIGITAL CAFE'):
    check('substring is not a merchant token: ' + narration,
          C.categorize_one(narration, {})[0] == 'UNCATEGORIZED')

# Atomic publication and concurrent CLI corrections use only temporary state.
import json
import subprocess
from unittest.mock import patch
with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, 'map.json')
    C.save_map({'ZOMATO': 'Shopping'}, path)
    before = open(path).read()
    with patch.object(C.os, 'replace', side_effect=OSError('simulated write failure')):
        try:
            C.save_map({'NETFLIX': 'Shopping'}, path)
        except OSError:
            pass
    check('failed save preserves prior merchant rules', open(path).read() == before)
    check('failed save cleans temporary file', os.listdir(tmp) == ['map.json'])
    processes = [subprocess.Popen([sys.executable, C.__file__, '--learn', '--map', path,
                                  '--merchant', 'MERCHANT' + str(i), '--category', 'Shopping'],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for i in range(8)]
    results = [p.communicate(timeout=20) for p in processes]
    check('concurrent corrections succeed', all(p.returncode == 0 for p in processes), results)
    check('concurrent corrections retain all merchant rules', len(C.load_map(path)) == 9)
    with open(path, 'w') as stream: stream.write('{broken')
    p = subprocess.run([sys.executable, C.__file__, '--learn', '--map', path,
                        '--merchant', 'NEW', '--category', 'Shopping'], capture_output=True, text=True)
    check('learning refuses to overwrite corrupt state', p.returncode != 0 and open(path).read() == '{broken')
    gaps = []
    check('read-only categorization can report and bypass corrupt map', C.load_map(path, gaps=gaps) == {} and bool(gaps))
    for bad in ('{"X": "Shopping", "X": "Medical"}', '{"X": []}', '[]'):
        with open(path, 'w') as stream: stream.write(bad)
        try:
            C.load_map(path)
            rejected = False
        except ValueError:
            rejected = True
        check('invalid merchant-map schema is rejected', rejected)

bad_rows = [dict(txns[0], amount=bad) for bad in (True, None, float('nan'), float('inf'), 'unknown')]
result = C.categorize(bad_rows + [txns[0]], {})
check('invalid amounts are labelled and excluded from spend', len(result['gaps']) == 5 and result['by_bucket'] == {'Lifestyle': 500}, result)
result = C.categorize([dict(txns[0], direction='unknown'), dict(txns[0], date='2026-02-30'), None], {})
check('invalid normalized transactions do not disappear silently', len(result['gaps']) == 3 and not result['transactions'], result)
with tempfile.TemporaryDirectory() as tmp:
    source = os.path.join(tmp, 'transactions.json')
    with open(source, 'w') as stream: json.dump(txns, stream)
    before = open(source).read()
    p = subprocess.run([sys.executable, C.__file__, '--txns', source, '--out', source, '--map', os.path.join(tmp, 'map.json')], capture_output=True, text=True)
    check('result output cannot overwrite statement input', p.returncode != 0 and open(source).read() == before)
check('explicit merchant correction also overrides exclusion guesses',
      C.categorize_one('CRED CLUB', {'CRED': 'House rent & maintenance'})[:2] == ('House rent & maintenance', 'Essential'))
summary()
