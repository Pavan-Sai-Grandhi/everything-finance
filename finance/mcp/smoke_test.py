#!/usr/bin/env python3
"""Live end-to-end smoke test for the finance MCP servers.

Speaks the real MCP wire protocol over stdio to a real server process and calls EVERY tool
against its real upstream. Deliberately not mocked: the failure this catches is a source
changing shape or starting to block, which no fixture can see. It complements the offline
unit tests in `finance/tests/test_*.py` rather than replacing them.

A tool returning `ok:false` with a labelled gap is DEGRADED, not FAILED — that is the
contract working. Only a protocol error, an exception, or a malformed envelope fails.

Run:  python3 -m finance.mcp.smoke_test [--quick] [--server market|company|funds|personal]
"""
from __future__ import annotations

import argparse
from collections import deque
import queue
import tempfile
import json
import os
import subprocess
import threading
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.path.insert(0, ROOT)
from finance.compute.dcf import SELFTEST_SPEC as SELFTEST_DCF_SPEC  # noqa: E402

# server -> [(tool, args, what a healthy response must contain), ...]
CASES = {
    "market": [
        ("get_quote", {"symbol": "RELIANCE"}, ["close"]),
        ("get_history", {"symbol": "RELIANCE", "period": "1mo"}, ["candles_total"]),
        ("run_technical_screen",
         {"filters": [{"left": "market_cap_basic", "operation": "greater", "right": 5e11}],
          "limit": 5}, ["candidates"]),
        ("get_indices", {"names": ["NIFTY 50", "NIFTY SMALLCAP 250"]}, ["indices"]),
        ("get_index_valuation_history", {"index_name": "NIFTY 50", "years": 3}, ["pe"]),
        ("get_breadth", {"universe": 100}, ["counts"]),
        ("get_flows", {}, ["flows"]),
        ("get_macro", {}, ["macro"]),
        ("get_market_context", {"mode": "quick"}, ["digest", "market_trend"]),
        ("get_universe", {"name": "largecap20"}, ["symbols_count"]),
        ("run_stock_scan", {"spec": "SPEC", "top": 3}, ["shortlist"]),
        ("run_sector_screen", {"top": 3}, ["shortlist"]),
        ("run_strategy_screen",
         {"spec": "SPEC", "symbols": ["RELIANCE", "TCS"], "years": 2}, ["candidates"]),
        ("run_backtest",
         {"spec": "SPEC", "symbols": ["RELIANCE"], "years": 2}, ["summary"]),
        ("check_trade", {"trade": "TRADE"}, ["verdict"]),
        ("manage_alerts", {"action": "sweep"}, ["expired", "unsnoozed"]),
        ("get_prior_run", {"skill": "dcf", "subject": "RELIANCE"}, ["path"]),
    ],
    "company": [
        ("get_company_fundamentals",
         {"symbol": "RELIANCE", "sections": ["ratios"]}, ["ratios"]),
        ("get_documents", {"symbol": "RELIANCE", "annual_reports": 1, "concalls": 1},
         ["documents", "documents_total"]),
        ("run_fundamental_screen",
         {"query": "Market Cap > 100000 AND PE Ratio < 25", "limit": 25},
         ["candidates", "count"]),
        # Retired endpoint: verifies the labelled compatibility gap, never a fetch.
        ("run_saved_screen", {"screen_url": "retired://saved-screen"}, ["candidates", "count"]),
        ("get_stock_ratios", {"sid": "RELI"}, ["ticker"]),
        ("get_news", {"company": "Reliance Industries", "ticker": "RELIANCE", "days": 30,
                      "limit": 5}, ["items_total"]),
        ("get_filings", {"symbol": "RELIANCE", "days": 30}, ["material_count"]),
        ("get_shareholding", {"symbol": "VEDL", "quarters": 4}, ["quarters"]),
        ("get_corporate_actions", {"symbol": "RELIANCE"}, ["corporate_actions"]),
        ("run_dcf", {"ticker": "SMOKETEST", "inputs": SELFTEST_DCF_SPEC},
         ["intrinsic_value_per_share", "dcf_path"]),
        ("run_governance_checks", {"total_remuneration": 30.0, "net_profit": 1000.0,
                                   "fees": [2.0, 2.6], "revenues": [100.0, 102.0]},
         ["remuneration", "auditor_fee"]),
    ],
    "funds": [
        ("resolve_fund", {"name": "Bandhan Small Cap"}, ["scheme_code"]),
        ("screen_funds", {"subsector": "Small Cap Fund", "min_aum": 500, "limit": 5},
         ["funds_total"]),
        ("get_fund_holdings", {"mf_id": None, "limit": 3}, ["positions_total"]),
        ("get_nav_history", {"scheme_code": "147946"}, ["navs_total"]),
        ("get_fund_scan", {"category": "Small Cap Fund", "top": 3}, ["shortlist"]),
        ("get_fund_lookthrough", {"mf_id": None}, ["metrics"]),
    ],
    "personal": [
        ("run_insurance_math",
         # Synthetic protocol inputs (not a recommendation): every required key explicit.
         {"calculation": "term_cover_need",
          "inputs": {"annual_income": 20_00_000, "income_multiple": 10, "outstanding_loans": 0,
                     "education_corpus": 0, "annual_expenses": 8_00_000,
                     "years_to_independence": 20, "existing_corpus": 0, "existing_cover": 0}},
         ["result"]),
    ],
}

# tool -> the argument only an earlier call in the same server can supply; skipped unresolved.
RUNTIME_ARG = {"get_fund_holdings": "mf_id", "get_fund_lookthrough": "mf_id"}

# tool -> the argument that must be a real file on disk; skipped when it is missing.
FILE_ARG = {"run_strategy_screen": ("spec", "SPEC"), "run_backtest": ("spec", "SPEC"),
            "run_stock_scan": ("spec", "SPEC"), "check_trade": ("trade", "TRADE")}

# The slow rungs: valuation sampling, the daily context, the spec engines, and the
# multi-megabyte annual-report download.
SLOW = {"get_index_valuation_history", "get_market_context", "run_strategy_screen",
        "run_backtest", "run_stock_scan", "run_sector_screen", "get_fund_scan",
        "get_fund_lookthrough", "get_documents"}


class Client:
    """Minimal MCP stdio client — enough to initialize and call tools."""

    def __init__(self, python_exe, server):
        self.artifacts = tempfile.TemporaryDirectory(prefix="ef-smoke-")
        env = dict(os.environ, PYTHONPATH=ROOT + os.pathsep + os.environ.get("PYTHONPATH", ""),
                   EVERYTHING_FINANCE_ARTIFACTS=self.artifacts.name)
        try:
            self.proc = subprocess.Popen(
                [python_exe, "-m", f"finance.mcp.{server}"], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
                cwd=ROOT, env=env)
        except Exception:
            self.artifacts.cleanup()
            raise
        self.errlog = deque(maxlen=200)
        self.responses = queue.Queue()
        threading.Thread(target=self._drain_stdout, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self._id = 0
        try:
            self._rpc("initialize", {
                "protocolVersion": "2025-06-18", "capabilities": {},
                "clientInfo": {"name": "smoke", "version": "1.0"}})
            self._notify("notifications/initialized")
        except Exception:
            close(self)
            raise

    def _drain_stdout(self):
        try:
            for line in self.proc.stdout:
                self.responses.put(line)
        finally:
            self.responses.put(None)

    def _drain_stderr(self):
        for line in self.proc.stderr:
            self.errlog.append(line.rstrip())

    def _send(self, obj):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def _notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _rpc(self, method, params, timeout=300):
        self._id += 1
        want = self._id
        self._send({"jsonrpc": "2.0", "id": want, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{method} timed out")
            try:
                line = self.responses.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError(f"{method} timed out") from exc
            if not line:
                raise RuntimeError("server closed the connection")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                raise RuntimeError("RPC response must be an object")
            if msg.get("id") == want:
                if "error" in msg:
                    raise RuntimeError(f"RPC error: {msg['error']}")
                return msg["result"]

    def tools(self):
        return [t["name"] for t in self._rpc("tools/list", {}).get("tools", [])]

    def call(self, name, args):
        res = self._rpc("tools/call", {"name": name, "arguments": args})
        if res.get("isError"):
            raise RuntimeError(str(res.get("content"))[:300])
        data = res.get("structuredContent")
        if data is None:
            blocks = res.get("content") or []
            text = next((b.get("text") for b in blocks if b.get("type") == "text"), "{}")
            data = json.loads(text)
        return data


def close(client):
    try:
        client.proc.stdin.close()
        client.proc.wait(timeout=2)
    except Exception:  # noqa: BLE001
        client.proc.kill()
        client.proc.wait(timeout=2)
    finally:
        client.proc.stdout.close()
        client.proc.stderr.close()
        client.artifacts.cleanup()


def valid_envelope(env):
    """Degradation is valid only when it carries the complete typed contract."""
    return (isinstance(env, dict) and type(env.get("ok")) is bool
            and isinstance(env.get("source"), str) and bool(env["source"])
            and isinstance(env.get("fetched_at"), str) and bool(env["fetched_at"])
            and isinstance(env.get("data"), dict)
            and isinstance(env.get("gaps"), list)
            and all(isinstance(gap, str) and gap.strip() for gap in env["gaps"])
            and (env["ok"] or bool(env["gaps"])))


def run_server(server, python_exe, quick, files):
    """Every tool on one server. Returns (passed, degraded, failed, stderr_lines)."""
    print(f"\n=== finance-{server}")
    try:
        client = Client(python_exe, server)
    except Exception as exc:
        print(f"FAIL     initialize                     {exc}")
        return 0, 0, 1, []
    passed = degraded = failed = 0
    resolved = {"mf_id": None}
    try:
        declared = client.tools()
        expected = {name for name, _, _ in CASES[server]}
        missing = sorted(expected - set(declared))
        extra = sorted(set(declared) - expected)
        if missing or extra:
            failed += 1
            print(f"FAIL     {'tools/list':<30} missing={missing} unexpected={extra}")
        else:
            passed += 1
            print(f"PASS     {'tools/list':<30} {len(declared)} tools")

        for name, call_args, must_have in CASES[server]:
            if quick and name in SLOW:
                continue
            call_args = dict(call_args)
            arg = RUNTIME_ARG.get(name)
            if arg:
                if not resolved[arg]:
                    print(f"SKIP     {name:<30} no {arg} resolved upstream")
                    continue
                call_args[arg] = resolved[arg]
            if name in FILE_ARG:
                key, token = FILE_ARG[name]
                path = files.get(token)
                if not path:
                    print(f"SKIP     {name:<30} pass --{token.lower()} PATH to test it")
                    continue
                call_args[key] = path
            try:
                env = client.call(name, call_args)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAIL     {name:<30} {exc}")
                continue

            if not valid_envelope(env):
                failed += 1
                print(f"FAIL     {name:<30} malformed envelope ({type(env).__name__})")
                continue

            data = env.get("data") or {}
            if name == "resolve_fund":
                resolved["mf_id"] = data.get("mf_id")

            missing_keys = [k for k in must_have if k not in data]
            if not env.get("ok"):
                degraded += 1
                print(f"DEGRADED {name:<30} {(env.get('gaps') or ['?'])[0][:80]}")
            elif missing_keys:
                failed += 1
                print(f"FAIL     {name:<30} missing keys {missing_keys}")
            else:
                passed += 1
                print(f"PASS     {name:<30} src={env.get('source')}")
    except Exception as exc:
        failed += 1
        print(f"FAIL     protocol                       {exc}")
    finally:
        close(client)
        errlog = list(client.errlog)
    return passed, degraded, failed, errlog


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--server", choices=sorted(CASES), action="append",
                    help="test one server (repeatable); default: every server")
    ap.add_argument("--quick", action="store_true",
                    help="skip the slow valuation, context and spec-engine tools")
    ap.add_argument("--spec", help="strategy YAML for run_strategy_screen / run_backtest")
    ap.add_argument("--trade", help="trade-idea YAML for check_trade")
    args = ap.parse_args()

    files = {k: v for k, v in (("SPEC", args.spec), ("TRADE", args.trade)) if v}
    totals = [0, 0, 0]
    errlogs = {}
    for server in (args.server or sorted(CASES)):
        p, d, f, err = run_server(server, args.python, args.quick, files)
        totals = [totals[0] + p, totals[1] + d, totals[2] + f]
        errlogs[server] = err

    print(f"\n{totals[0]} passed, {totals[1]} degraded, {totals[2]} failed")
    if totals[2]:
        for server, err in errlogs.items():
            for line in err[-20:]:
                print(f"  [{server}] {line}")
    sys.exit(1 if totals[2] else 0)


if __name__ == "__main__":
    main()
