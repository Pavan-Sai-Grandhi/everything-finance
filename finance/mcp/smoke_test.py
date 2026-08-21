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
        ("run_strategy_screen",
         {"spec": "SPEC", "symbols": ["RELIANCE", "TCS"], "years": 2}, ["candidates"]),
        ("run_backtest",
         {"spec": "SPEC", "symbols": ["RELIANCE"], "years": 2}, ["summary"]),
        ("check_trade", {"trade": "TRADE"}, ["verdict"]),
        ("manage_alerts", {"action": "sweep"}, ["expired", "unsnoozed"]),
    ],
    "company": [
        ("get_company_fundamentals",
         {"symbol": "RELIANCE", "sections": ["ratios"]}, ["ratios"]),
        ("get_documents", {"symbol": "RELIANCE", "annual_reports": 1, "concalls": 1},
         ["documents", "documents_total"]),
        ("run_fundamental_screen",
         {"query": "Market Capitalization > 100000 AND Price to Earning < 25"},
         ["candidates", "count"]),
        ("get_stock_ratios", {"sid": "RELI"}, ["ticker"]),
        ("get_news", {"company": "Reliance Industries", "ticker": "RELIANCE", "days": 30,
                      "limit": 5}, ["items_total"]),
        ("get_filings", {"symbol": "RELIANCE", "days": 30}, ["material_count"]),
        ("get_shareholding", {"symbol": "VEDL", "quarters": 4}, ["quarters"]),
        ("get_corporate_actions", {"symbol": "RELIANCE"}, ["corporate_actions"]),
        ("run_dcf", {"ticker": "SMOKETEST", "inputs": SELFTEST_DCF_SPEC},
         ["intrinsic_value_per_share", "dcf_path"]),
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
         {"calculation": "term_cover_need", "inputs": {"annual_income": 20_00_000}},
         ["result"]),
    ],
}

# tool -> the argument only an earlier call in the same server can supply; skipped unresolved.
RUNTIME_ARG = {"get_fund_holdings": "mf_id", "get_fund_lookthrough": "mf_id"}

# tool -> the argument that must be a real file on disk; skipped when it is missing.
FILE_ARG = {"run_strategy_screen": ("spec", "SPEC"), "run_backtest": ("spec", "SPEC"),
            "check_trade": ("trade", "TRADE")}

# The slow rungs: valuation sampling, the daily context, the spec engines, and the
# multi-megabyte annual-report download.
SLOW = {"get_index_valuation_history", "get_market_context", "run_strategy_screen",
        "run_backtest", "get_fund_scan", "get_fund_lookthrough", "get_documents"}


class Client:
    """Minimal MCP stdio client — enough to initialize and call tools."""

    def __init__(self, python_exe, server):
        env = dict(os.environ, PYTHONPATH=ROOT + os.pathsep + os.environ.get("PYTHONPATH", ""))
        self.proc = subprocess.Popen(
            [python_exe, "-m", f"finance.mcp.{server}"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
            cwd=ROOT, env=env)
        self.errlog = []
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self._id = 0
        self._rpc("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "smoke", "version": "1.0"}})
        self._notify("notifications/initialized")

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
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("server closed the connection")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") == want:
                if "error" in msg:
                    raise RuntimeError(f"RPC error: {msg['error']}")
                return msg["result"]
        raise TimeoutError(f"{method} timed out")

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
        client.proc.wait(timeout=10)
    except Exception:  # noqa: BLE001
        client.proc.kill()


def run_server(server, python_exe, quick, files):
    """Every tool on one server. Returns (passed, degraded, failed, stderr_lines)."""
    print(f"\n=== finance-{server}")
    client = Client(python_exe, server)
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

            if not isinstance(env, dict) or not {"ok", "data", "gaps"} <= set(env):
                failed += 1
                print(f"FAIL     {name:<30} malformed envelope: {sorted(env)[:6]}")
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
    finally:
        errlog = list(client.errlog)
        close(client)
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
