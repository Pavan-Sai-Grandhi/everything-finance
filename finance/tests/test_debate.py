#!/usr/bin/env python3
"""Offline tests for finance/compute/debate.py: deep-analysis mode resolution and the
bull/bear round rule. Trade-store reads run inside temp artifact roots."""
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_sandbox = tempfile.TemporaryDirectory()
os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = _sandbox.name
from finance.compute import debate as D  # noqa: E402
from finance.tests.harness import check, summary  # noqa: E402



def write_trade(root, symbol, date, status):
    d = os.path.join(root, "state", "trades")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{symbol}-{date}.yml"), "w") as f:
        f.write(f"symbol: {symbol}\nstatus: {status}\n")


# --- step 1: explicit flag wins -----------------------------------------------
r = D.resolve_mode("RRKABEL --quick", symbol="RRKABEL", holding="no")
check("--quick → quick", r["mode"] == "quick", r)
check("--quick reason mentions flag", "flag" in r["reason"].lower(), r)

r = D.resolve_mode("--deep RRKABEL", symbol="RRKABEL", holding="no")
check("--deep → deep", r["mode"] == "deep", r)

r = D.resolve_mode("RRKABEL --deep --quick", symbol="RRKABEL", holding="no")
check("--deep beats --quick", r["mode"] == "deep", r)

# explicit flag overrides holding auto-escalation
r = D.resolve_mode("RRKABEL --quick", symbol="RRKABEL", holding="yes")
check("--quick beats broker holding", r["mode"] == "quick", r)

# --- the fundamentals-only mode ----------------------------------------------
check("fundamentals is a valid mode", "fundamentals" in D.MODES,
      D.MODES)

r = D.resolve_mode("RRKABEL --fundamentals", symbol="RRKABEL", holding="no")
check("--fundamentals → fundamentals", r["mode"] == "fundamentals", r)
check("--fundamentals reason mentions flag", "flag" in r["reason"].lower(), r)

# it names the question, not the rigour — so it outranks both depth flags
r = D.resolve_mode("RRKABEL --fundamentals --deep", symbol="RRKABEL", holding="no")
check("--fundamentals beats --deep", r["mode"] == "fundamentals", r)
r = D.resolve_mode("RRKABEL --quick --fundamentals", symbol="RRKABEL", holding="no")
check("--fundamentals beats --quick", r["mode"] == "fundamentals", r)

# and, being an explicit flag, it beats the holding auto-escalation on both halves
r = D.resolve_mode("RRKABEL --fundamentals", symbol="RRKABEL", holding="yes")
check("--fundamentals beats broker holding", r["mode"] == "fundamentals", r)

with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"EVERYTHING_FINANCE_ARTIFACTS": root}):
    write_trade(root, "RRKABEL", "2026-06-01", "open")
    r = D.resolve_mode("RRKABEL --fundamentals", symbol="RRKABEL", holding="no")
    check("--fundamentals beats an open trade artifact", r["mode"] == "fundamentals", r)

# no flag never selects it — a fundamentals-only read is always asked for
r = D.resolve_mode("RRKABEL fundamentals", symbol="RRKABEL", holding="no")
check("bare word 'fundamentals' is not the flag", r["mode"] == "standard", r)

# --- step 3: default ----------------------------------------------------------
r = D.resolve_mode("RRKABEL", symbol="RRKABEL", holding="no")
check("no flag, not held → standard", r["mode"] == "standard", r)
check("default reason", "default" in r["reason"].lower(), r)

# --- step 2: holding auto-escalation -----------------------------------------
r = D.resolve_mode("RRKABEL", symbol="RRKABEL", holding="yes")
check("broker holding → deep", r["mode"] == "deep", r)
check("holding reason note", "override with --quick" in r["reason"], r)

with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"EVERYTHING_FINANCE_ARTIFACTS": root}):
    write_trade(root, "RRKABEL", "2026-06-01", "open")
    r = D.resolve_mode("RRKABEL", symbol="RRKABEL", holding="no")
    check("open trade artifact → deep", r["mode"] == "deep", r)

with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"EVERYTHING_FINANCE_ARTIFACTS": root}):
    write_trade(root, "RRKABEL", "2026-06-01", "closed")
    r = D.resolve_mode("RRKABEL", symbol="RRKABEL", holding="no")
    check("closed trade artifact → standard", r["mode"] == "standard", r)

with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"EVERYTHING_FINANCE_ARTIFACTS": root}):
    write_trade(root, "OTHERCO", "2026-06-01", "open")
    r = D.resolve_mode("RRKABEL", symbol="RRKABEL", holding="no")
    check("open trade for a different symbol is ignored", r["mode"] == "standard", r)

for args in ("RRKABEL", "RRKABEL --quick", "RRKABEL --deep", "RRKABEL --fundamentals"):
    m = D.resolve_mode(args, symbol="RRKABEL", holding="no")["mode"]
    check(f"'{args}' resolves inside VALID_MODES", m in D.MODES, m)

# --- the broker tri-state: unknown is not "no" -------------------------------
r = D.resolve_mode("PRAJIND", symbol="PRAJIND", holding="unknown")
check("unknown → standard (same depth as 'no')", r["mode"] == "standard", r)
check("unknown does NOT claim the ticker is unheld",
      "not a held position" not in r["reason"], r)
check("unknown reports a gap", len(r["gaps"]) == 1, r)
check("the gap names the escalation that was missed",
      "deep" in r["gaps"][0] and "holding" in r["gaps"][0], r)

r = D.resolve_mode("RRKABEL", symbol="RRKABEL", holding="no")
check("'no' still says 'not a held position'", "not a held position" in r["reason"], r)
check("'no' raises no gap", r["gaps"] == [], r)

r = D.resolve_mode("RRKABEL", symbol="RRKABEL", holding="yes")
check("'yes' raises no gap", r["gaps"] == [], r)

# unknown must not suppress the open-trade half — that is a local file read that
# always works, and it escalates on its own
with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"EVERYTHING_FINANCE_ARTIFACTS": root}):
    write_trade(root, "RRKABEL", "2026-06-01", "open")
    r = D.resolve_mode("RRKABEL", symbol="RRKABEL", holding="unknown")
    check("unknown broker + open trade artifact → deep", r["mode"] == "deep", r)
    check("open-trade escalation raises no gap", r["gaps"] == [], r)

# every result carries the key, so the synthesis can union gaps unconditionally
for h in D.HOLDING_STATES:
    check(f"holding={h} returns a gaps key",
          "gaps" in D.resolve_mode("X", symbol="X", holding=h))

# a typo'd state is a crash, not a silent default to the dangerous reading
try:
    D.resolve_mode("X", symbol="X", holding="maybe")
    check("bad holding state raises", False)
except ValueError as e:
    check("bad holding state raises ValueError", "maybe" in str(e), e)



# A YAML record is not a bag of lines; nested rationale/example statuses do not count.
for status_text, expected in (("status: 'open' # filled", "deep"),
                               ("status: closed\nnotes: |\n  status: open", "standard"),
                               ("status: closed\nhistory:\n  status: open", "standard")):
    with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"EVERYTHING_FINANCE_ARTIFACTS":root}):
        d=os.path.join(root,"state","trades");os.makedirs(d)
        with open(os.path.join(d,"RRKABEL-fixture.yml"),"w") as out:
            out.write("symbol: RRKABEL\n"+status_text+"\n")
        result=D.resolve_mode("RRKABEL",symbol="RRKABEL",holding="no")
        check("mode uses the parsed top-level trade status",result["mode"]==expected,result)
with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"EVERYTHING_FINANCE_ARTIFACTS":root}):
    d=os.path.join(root,"state","trades");os.makedirs(d)
    with open(os.path.join(d,"RRKABEL-bad.yml"),"w") as out:out.write("status: [broken")
    result=D.resolve_mode("RRKABEL",symbol="RRKABEL",holding="no")
    check("unreadable matching record cannot prove no open position",bool(result["gaps"]) and "not a held" not in result["reason"],result)
with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside, patch.dict(os.environ, {"EVERYTHING_FINANCE_ARTIFACTS":root}):
    write_trade(outside,"RRKABEL","2026-06-01","open")
    os.symlink(os.path.join(outside,"state"),os.path.join(root,"state"))
    result=D.resolve_mode("RRKABEL",symbol="RRKABEL",holding="no")
    check("trade-store symlink escape is refused with a gap",result["mode"]=="standard" and bool(result["gaps"]),result)




def dig(axis, claim, conceded=False, new_evidence=True):
    return {"axis": axis, "claim": claim, "conceded": conceded,
            "new_evidence": new_evidence}


# --- the engagement rule ------------------------------------------------------
# same axis, distinct evidence-tied claims, neither conceded → escalate to rebut
r = D.next_round(
    dig("valuation", "trades at 18x vs peer median 28x — cheap"),
    dig("valuation", "18x is fair given decelerating EPS growth"))
check("same-axis clash → escalate", r["escalate"] is True, r)
check("same-axis directive is rebut", r["directive"] == D.REBUT, r)

# different axes → escalate to cross-examine: neither side has tested the other
r = D.next_round(
    dig("technical_structure", "reclaimed the 200-DMA on rising volume"),
    dig("valuation", "reverse-DCF implies 28% CAGR vs a 3-year stagnation"))
check("different axes → ESCALATE", r["escalate"] is True, r)
check("different-axes directive is cross-examine",
      r["directive"] == D.CROSS_EXAMINE, r)
check("different-axes reason names non-engagement",
      "tested the other" in r["reason"], r)
check("different axes is not a gap", r["gaps"] == [], r)

r = D.next_round(
    dig("valuation", "cheap vs peers"),
    dig("balance_sheet_risk", "D/E 1.8, interest cover 2.1"))
check("different axes (second pair) → escalate", r["escalate"] is True, r)

# --- what actually ends a debate ---------------------------------------------
r = D.next_round(
    dig("growth_durability", "order book covers 3 years"),
    dig("growth_durability", "agreed, growth visibility is real", conceded=True))
check("a concession → stop", r["escalate"] is False, r)
check("concession reason names the side", "bear conceded" in r["reason"], r)

r = D.next_round(
    dig("valuation", "cheap", conceded=True),
    dig("governance", "pledging", conceded=True))
check("both conceded → stop", r["escalate"] is False, r)
check("both-conceded reason", "both sides conceded" in r["reason"], r)

# a concession outranks non-engagement — differing axes do not resurrect a
# debate one side has already given up
r = D.next_round(
    dig("technical_structure", "uptrend intact", conceded=True),
    dig("valuation", "no margin of safety"))
check("concession beats the differing-axes escalation", r["escalate"] is False, r)

r = D.next_round(
    dig("governance", "promoter pledging at 40%"),
    dig("governance", "Promoter pledging at 40%!"))
check("restated identical claim → stop", r["escalate"] is False, r)
check("restatement reason", "restate" in r["reason"], r)

r = D.next_round(
    dig("technical_structure", "broke 200-DMA on volume"),
    dig("technical_structure", ""))
check("empty claim → stop", r["escalate"] is False, r)
check("empty claim is reported as a gap", any("bear" in g for g in r["gaps"]), r)

# --- a malformed digest is a contract bug, reported as such -------------------
r = D.next_round(dig("vibes", "feels expensive"),
                               dig("vibes", "feels cheap"))
check("unrecognised axis → stop", r["escalate"] is False, r)
check("unrecognised axis is reported as a gap", len(r["gaps"]) == 2, r)
check("the gap names the offending value", "'vibes'" in r["gaps"][0], r)
check("unrecognised-axis reason does not claim convergence",
      "converged" not in r["reason"], r)

# --- round cap ----------------------------------------------------------------
clash = (dig("valuation", "cheap"), dig("valuation", "dear"))
check("round 2 still escalates", D.next_round(*clash, round_no=2)["escalate"] is True)
r = D.next_round(*clash, round_no=3)
check("round 3 is the cap", r["escalate"] is False, r)
check("cap reason names the cap", "cap" in r["reason"], r)

# --- exhaustion: new_evidence false on both sides ends the debate --------------
stale = (dig("valuation", "cheap", new_evidence=False),
         dig("valuation", "dear", new_evidence=False))
r = D.next_round(*stale, round_no=2)
check("deep r2, neither side new → stop", r["escalate"] is False, r)
check("exhaustion reason", "new evidence" in r["reason"], r)

# one side still bringing evidence keeps it alive
r = D.next_round(dig("valuation", "cheap", new_evidence=True),
                               dig("valuation", "dear", new_evidence=False), round_no=2)
check("deep r2, one side still new → escalate", r["escalate"] is True, r)

# exhaustion is not consulted in round 1 — every side is new there by definition
r = D.next_round(*stale, round_no=1)
check("round 1 ignores new_evidence", r["escalate"] is True, r)

# --- shape --------------------------------------------------------------------
for r in (D.next_round(*clash),
          D.next_round(*stale, round_no=2)):
    check("every result carries the four keys",
          set(r) == {"escalate", "reason", "directive", "gaps"}, r)
check("no directive when not escalating",
      D.next_round(*clash, round_no=3)["directive"] is None)



for bad in (None, [], {"axis": "valuation", "claim": "x", "conceded": "false", "new_evidence": True},
            {"axis": [], "claim": "x", "conceded": False, "new_evidence": True},
            {"axis": "valuation", "claim": 123, "conceded": False, "new_evidence": True},
            {"axis": "valuation", "claim": "x", "conceded": False, "new_evidence": "false"}):
    try:
        r=D.next_round(bad,dig("valuation","other"),round_no=3)
        valid=not r["escalate"] and bool(r["gaps"]) and "converged" not in r["reason"]
    except Exception:
        valid=False
    check("malformed digest is diagnosed even at the round cap", valid,bad)
for kwargs in ({"round_no":0},{"round_no":True}):
    try:
        r=D.next_round(*clash,**kwargs)
        valid=not r["escalate"] and bool(r["gaps"])
    except Exception:
        valid=False
    check("invalid debate controls cannot schedule another round",valid,kwargs)
for bull,bear in (("EPS growth > 10%","EPS growth < 10%"), ("Cash flow is -10","Cash flow is 10")):
    r=D.next_round(dig("valuation",bull),dig("valuation",bear))
    check("opposite numeric claims are not normalized into agreement",r["escalate"],r)



# --- tool entry points ---------------------------------------------------------
env = D.mode_report("RRKABEL --quick", symbol="RRKABEL", holding="no")
check("mode_report wraps the resolution in the envelope", env["ok"] and env["data"]["mode"] == "quick", env)
check("mode_report refuses a bad holding state", not D.mode_report("X", "X", "maybe")["ok"])
env = D.round_report(*clash, round_no=1)
check("round_report carries the directive", env["ok"] and env["data"]["directive"] == D.REBUT, env)
env = D.round_report(dig("vibes", "x"), dig("valuation", "y"))
check("round_report marks a broken digest not ok", not env["ok"] and env["gaps"], env)

summary()
