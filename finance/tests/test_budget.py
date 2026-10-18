#!/usr/bin/env python3
"""Offline tests for finance/compute/budget.py: categorization, the durable merchant map,
recurring-spend detection and the tool entry points."""
import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = tempfile.mkdtemp(prefix="ef-budget-")
from finance.compute import budget as B  # noqa: E402
from finance.tests.harness import check, summary  # noqa: E402



# --- token normalization: UPI / POS / handle variants collapse to one token ---
variants = [
    "UPI/DR/412345678901/ZOMATO/YESB/zomato.pay@ybl/Payment",
    "POS 4123XXXXXX5678 ZOMATO LTD",
    "UPI-ZOMATO LIMITED-zomato@okhdfcbank-HDFC-payment",
]
tokens = {B.normalize_token(v) for v in variants}
check("UPI/POS/handle variants collapse to one token", tokens == {"ZOMATO"}, tokens)
check("numeric-only and short plumbing words dropped",
      B.normalize_token("UPI/DR/99887766/SWIGGY/YBL") == "SWIGGY")

# --- taxonomy resolution + bucket rollup -------------------------------------
cat, bucket, src = B.categorize_one("UPI/ZOMATO/ybl", {})
check("taxonomy maps ZOMATO -> Dine & Entertainment / Lifestyle",
      (cat, bucket, src) == ("Dine & Entertainment", "Lifestyle", "taxonomy"),
      (cat, bucket, src))
cat, bucket, src = B.categorize_one("POS SWIGGY INSTAMART GROCERY", {})
check("overlap resolves to more-specific Groceries (INSTAMART before SWIGGY)",
      cat == "Groceries", cat)

# --- durable map wins over taxonomy ------------------------------------------
# APOLLO would be Medical by taxonomy; the user's map reclassifies it to Shopping.
m = {"APOLLO": "Shopping"}
cat, bucket, src = B.categorize_one("UPI/APOLLO PHARMACY/ybl", m)
check("durable map precedence over taxonomy", (cat, src) == ("Shopping", "map"),
      (cat, src))

# --- UNCATEGORIZED residue ---------------------------------------------------
cat, bucket, src = B.categorize_one("UPI/DR/778899/ZZOUTLET/ybl", {})
check("unknown merchant -> UNCATEGORIZED", (cat, src) == ("UNCATEGORIZED", "uncategorized"),
      (cat, src))

# --- CC-payment / transfer excluded, not counted as spend --------------------
cat, bucket, src = B.categorize_one("HDFC CREDIT CARD PAYMENT via BBPS CC", {})
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
res = B.categorize(txns, {})
check("rollup: Lifestyle = 500 (Zomato)", res["by_bucket"].get("Lifestyle") == 500, res["by_bucket"])
check("rollup: Essential = 2000 (BigBasket)", res["by_bucket"].get("Essential") == 2000, res["by_bucket"])
check("rollup: salary credit not counted as spend", "Income" not in res["by_bucket"], res["by_bucket"])
check("rollup: CC payment not counted as spend", "Excluded" not in res["by_bucket"], res["by_bucket"])
check("residue: one UNCATEGORIZED row", len(res["uncategorized"]) == 1, res["uncategorized"])

# --- correction round-trip persists through save/load ------------------------
with tempfile.TemporaryDirectory() as tmp:
    map_path = os.path.join(tmp, "merchant-map.json")
    mm = B.load_map(map_path)
    check("missing map loads as empty dict", mm == {}, mm)
    token = B.apply_correction(mm, "UPI/DR/RANDOMSHOP/ybl", "Shopping")
    check("apply_correction returns the token", token == "RANDOMSHOP", token)
    B.save_map(mm, map_path)

    reloaded = B.load_map(map_path)
    check("map round-trips through disk", reloaded == {"RANDOMSHOP": "Shopping"}, reloaded)
    cat, bucket, src = B.categorize_one("POS RANDOMSHOP OUTLET", reloaded)
    check("corrected merchant resolves via map next run", (cat, src) == ("Shopping", "map"),
          (cat, src))
    res2 = B.categorize(txns, reloaded)
    check("UNCATEGORIZED shrinks after correction", len(res2["uncategorized"]) == 0,
          res2["uncategorized"])

# --- corrupt map degrades to empty, never crashes ----------------------------
with tempfile.TemporaryDirectory() as tmp:
    bad = os.path.join(tmp, "merchant-map.json")
    with open(bad, "w") as f:
        f.write("{not json")
    try:
        B.load_map(bad)
        rejected = False
    except ValueError:
        rejected = True
    check("corrupt map cannot silently become writable empty state", rejected)

for narration in ('CHOCOLATE SHOP', 'PUBLIC BOOKSTORE', 'RENTALITY', 'DIGITAL CAFE'):
    check('substring is not a merchant token: ' + narration,
          B.categorize_one(narration, {})[0] == 'UNCATEGORIZED')

with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, 'map.json')
    B.save_map({'ZOMATO': 'Shopping'}, path)
    before = open(path).read()
    with patch.object(B.spine.os, 'replace', side_effect=OSError('simulated write failure')):
        try:
            B.save_map({'NETFLIX': 'Shopping'}, path)
        except OSError:
            pass
    check('failed save preserves prior merchant rules', open(path).read() == before)
    check('failed save cleans temporary file', os.listdir(tmp) == ['map.json'])
    learner = "import sys; from finance.compute import budget; budget.learn(sys.argv[1], 'Shopping', sys.argv[2])"
    processes = [subprocess.Popen([sys.executable, '-c', learner, 'MERCHANT' + str(i), path], cwd=ROOT,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for i in range(8)]
    results = [p.communicate(timeout=20) for p in processes]
    check('concurrent corrections succeed', all(p.returncode == 0 for p in processes), results)
    check('concurrent corrections retain all merchant rules', len(B.load_map(path)) == 9)
    with open(path, 'w') as stream: stream.write('{broken')
    try:
        B.learn('NEW', 'Shopping', path)
        refused = False
    except ValueError:
        refused = True
    check('learning refuses to overwrite corrupt state', refused and open(path).read() == '{broken')
    gaps = []
    check('read-only categorization can report and bypass corrupt map', B.load_map(path, gaps=gaps) == {} and bool(gaps))
    for bad in ('{"X": "Shopping", "X": "Medical"}', '{"X": []}', '[]'):
        with open(path, 'w') as stream: stream.write(bad)
        try:
            B.load_map(path)
            rejected = False
        except ValueError:
            rejected = True
        check('invalid merchant-map schema is rejected', rejected)

bad_rows = [dict(txns[0], amount=bad) for bad in (True, None, float('nan'), float('inf'), 'unknown')]
result = B.categorize(bad_rows + [txns[0]], {})
check('invalid amounts are labelled and excluded from spend', len(result['gaps']) == 5 and result['by_bucket'] == {'Lifestyle': 500}, result)
result = B.categorize([dict(txns[0], direction='unknown'), dict(txns[0], date='2026-02-30'), None], {})
check('invalid normalized transactions do not disappear silently', len(result['gaps']) == 3 and not result['transactions'], result)
with tempfile.TemporaryDirectory() as tmp:
    source = os.path.join(tmp, 'transactions.json')
    with open(source, 'w') as stream: json.dump(txns, stream)
    before = open(source).read()
    env = B.categorize_file(source, out=source)
    check('result output cannot overwrite statement input', not env['ok'] and open(source).read() == before, env)
    out = os.path.join(tmp, 'categorized.json')
    env = B.categorize_file(source, out=out)
    check('categorize_file summarizes and writes the annotated rows',
          env['ok'] and env['data']['categorized'] == 5 and env['data']['result_path'] == out
          and len(B.spine.read_json(out)['transactions']) == 5, env)
    check('categorize_file lists the uncategorized merchants by spend',
          [m['token'] for m in env['data']['uncategorized_merchants']] == ['RANDOMSHOP'], env)
    env = B.learn_file('UPI/DR/RANDOMSHOP/ybl', 'Shopping')
    check('learn_file records a correction in the durable map',
          env['ok'] and B.load_map()['RANDOMSHOP'] == 'Shopping', env)
    check('learn_file rejects an unsupported category', not B.learn_file('X SHOP', 'Nope')['ok'])
    env = B.categorize_file(source, out=out)
    check('a learned merchant leaves the uncategorized residue', env['data']['uncategorized'] == 0, env)
    with open(source, 'w') as stream: json.dump([{"date": "2026-05-0%d" % d, "description": "UPI/NETFLIX/ybl", "amount": 649, "direction": "debit"} for d in (1,)] , stream)
    env = B.recurring_file(source, as_of='2026-05-31')
    check('recurring_file returns the detection in the envelope',
          env['ok'] and env['data']['subscriptions'][0]['merchant'] == 'NETFLIX', env)
check('explicit merchant correction also overrides exclusion guesses',
      B.categorize_one('CRED CLUB', {'CRED': 'House rent & maintenance'})[:2] == ('House rent & maintenance', 'Essential'))



def txn(date, desc, amount):
    return {"date": date, "description": desc, "amount": amount,
            "direction": "debit", "account": "HDFC"}


def sub(res, merchant):
    for s in res["subscriptions"]:
        if s["merchant"] == merchant:
            return s
    return None


# --- monthly cadence, stable amount: high-confidence recurring ---------------
netflix = [txn(f"2026-{m:02d}-05", "UPI/NETFLIX/ybl", 649) for m in (2, 3, 4, 5, 6)]
res = B.detect_recurring(netflix, as_of="2026-06-30")
s = sub(res, "NETFLIX")
check("monthly cadence detected", s and s["cadence"] == "monthly", s)
check("high confidence at 5 occurrences", s and s["confidence"] == "high", s)
check("monthly_equivalent == amount for monthly", s and s["monthly_equivalent"] == 649, s)
check("stable monthly sub has no creep flag", s and "price_creep" not in s["flags"], s)

# --- quarterly and annual cadence -> monthly_equivalent divides --------------
quarterly = [txn(d, "UPI/SOMECLUB MEMBERSHIP/ybl", 3000)
             for d in ("2026-01-10", "2026-04-10", "2026-07-10")]
res = B.detect_recurring(quarterly, as_of="2026-07-31")
s = sub(res, "SOMECLUB")
check("quarterly cadence detected", s and s["cadence"] == "quarterly", s)
check("quarterly monthly_equivalent = amount/3", s and s["monthly_equivalent"] == 1000, s)

annual = [txn("2025-08-01", "UPI/AMAZONPRIME MEMBERSHIP/ybl", 1499),
          txn("2026-08-01", "UPI/AMAZONPRIME MEMBERSHIP/ybl", 1499)]
res = B.detect_recurring(annual, as_of="2026-08-15")
s = sub(res, "AMAZONPRIME")
check("annual cadence detected", s and s["cadence"] == "annual", s)
check("annual monthly_equivalent ~ amount/12",
      s and abs(s["monthly_equivalent"] - 1499 / 12) < 0.01, s)

# --- new flag: first appearance is the current month -------------------------
newsub = [txn("2026-06-03", "UPI/HOTSTAR/ybl", 299),
          txn("2026-07-03", "UPI/HOTSTAR/ybl", 299)]
res = B.detect_recurring(newsub, as_of="2026-06-30")  # anchored at the first month
s = sub(res, "HOTSTAR")
check("new flag when first month == current month", s and "new" in s["flags"], s)

# --- price creep: amount rose vs the prior cadence ---------------------------
creep = [txn("2026-03-01", "UPI/SPOTIFY/ybl", 119),
         txn("2026-04-01", "UPI/SPOTIFY/ybl", 119),
         txn("2026-05-01", "UPI/SPOTIFY/ybl", 149)]
res = B.detect_recurring(creep, as_of="2026-05-31")
s = sub(res, "SPOTIFY")
check("price_creep flagged when latest > prior", s and "price_creep" in s["flags"], s)
check("prior_amount reported for creep", s and s["prior_amount"] == 119, s)

# --- dormant: established cadence that lapsed (charge overdue) ----------------
dormant = [txn("2026-01-08", "UPI/GYMPASS/ybl", 1500),
           txn("2026-02-08", "UPI/GYMPASS/ybl", 1500),
           txn("2026-03-08", "UPI/GYMPASS/ybl", 1500)]
res = B.detect_recurring(dormant, as_of="2026-06-30")  # ~114 days after last charge, monthly cadence
s = sub(res, "GYMPASS")
check("dormant flagged when charge overdue", s and "dormant" in s["flags"], s)
check("dormant excluded from committed monthly total",
      res["total_committed_monthly"] == 0.0, res["total_committed_monthly"])

# --- single-period low-confidence: one sighting of a known subscription ------
single = [txn("2026-06-15", "UPI/NETFLIX/ybl", 649)]
res = B.detect_recurring(single, as_of="2026-06-30")
s = sub(res, "NETFLIX")
check("single sighting of known sub surfaced", s is not None, res["subscriptions"])
check("single sighting is low confidence", s and s["confidence"] == "low", s)
check("single sighting has unconfirmed cadence", s and s["cadence"] is None, s)
check("single sighting does not inflate committed cost", res['total_committed_monthly'] == 0, res)
check("unconfirmed monthly equivalent stays missing", s and s['monthly_equivalent'] is None, s)

# --- non-recurring variable spend is NOT surfaced ----------------------------
groceries = [txn("2026-05-02", "UPI/BIGBASKET/ybl", 2100),
             txn("2026-05-11", "UPI/BIGBASKET/ybl", 640),
             txn("2026-05-23", "UPI/BIGBASKET/ybl", 3300)]
res = B.detect_recurring(groceries, as_of="2026-05-31")
check("irregular variable spend not called recurring", sub(res, "BIGBASKET") is None,
      res["subscriptions"])

# --- committed total sums monthly-equivalents of active subs -----------------
# anchor within a monthly cadence of Netflix's last charge so neither goes dormant
mix = netflix + quarterly
res = B.detect_recurring(mix, as_of="2026-07-15")
check("committed monthly total = 649 + 1000",
      res["total_committed_monthly"] == 1649, res["total_committed_monthly"])

# --- no debits -> empty, no crash --------------------------------------------
credits = [{"date": "2026-05-01", "description": "SALARY", "amount": 100000,
            "direction": "credit", "account": "HDFC"}]
res = B.detect_recurring(credits, as_of="2026-05-31")
check("all-credit input yields no subscriptions", res["subscriptions"] == [], res)

res = B.detect_recurring(newsub, as_of="2026-06-30")
s = sub(res, "HOTSTAR")
check('as-of excludes future transactions', s and s['occurrences'] == 1 and s['last_seen'] == '2026-06-03', res)
check('future exclusions are reported', bool(res.get('gaps')), res)
irregular = [txn(d, 'SOMECLUB', 100) for d in ('2026-01-01', '2026-01-02', '2026-03-03')]
check('median alone cannot certify cadence', not B.detect_recurring(irregular)['subscriptions'])
res = B.detect_recurring([txn('2026-06-01', 'APPLE STORE', 90000)], '2026-06-30')
check('merchant alone cannot certify a subscription', res['total_committed_monthly'] == 0)
invalid = [txn('invalid', 'NETFLIX', 10), txn('2026-06-01', 'NETFLIX', float('nan'))]
res = B.detect_recurring(invalid, '2026-06-30')
check('invalid rows do not poison recurring totals', res['total_committed_monthly'] == 0 and len(res['gaps']) == 2, res)
other_account = [dict(t, account='SECOND') for t in netflix]
res = B.detect_recurring(netflix + other_account, '2026-06-30')
check('separate accounts retain separate recurrence series', len(res['subscriptions']) == 2 and res['total_committed_monthly'] == 1298, res)
transfers = [txn(t['date'], 'CREDIT CARD PAYMENT', 1000) for t in netflix]
check('card bill settlements do not count twice as recurring spending', B.detect_recurring(transfers)['total_committed_monthly'] == 0)
summary()
