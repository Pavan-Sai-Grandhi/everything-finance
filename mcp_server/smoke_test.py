#!/usr/bin/env python3
"""Live end-to-end smoke test for the finance-data MCP server.

Speaks the real MCP wire protocol over stdio to a real server process and calls EVERY tool
against its real upstream. Deliberately not mocked: the failure this catches is a source
changing shape or starting to block, which no fixture can see. It complements the offline
unit tests in `lib/test_*.py` rather than replacing them.

A tool returning `ok:false` with a labelled gap is DEGRADED, not FAILED — that is the
contract working. Only a protocol error, an exception, or a malformed envelope fails.

Run:  python3 mcp_server/smoke_test.py [--quick]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERVER = os.path.join(HERE, "finance_data.py")

# (tool, args, what a healthy response must contain)
CASES = [
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
    ("get_company_fundamentals",
     {"symbol": "RELIANCE", "sections": ["ratios"]}, ["ratios"]),
    ("run_fundamental_screen",
     {"query": "Market Capitalization > 100000 AND Price to Earning < 25"},
     ["candidates", "count"]),
    ("resolve_fund", {"name": "Bandhan Small Cap"}, ["scheme_code"]),
    ("screen_funds", {"subsector": "Small Cap Fund", "min_aum": 500, "limit": 5},
     ["funds_total"]),
    ("get_nav_history", {"scheme_code": "147946"}, ["navs_total"]),
    ("get_news", {"company": "Reliance Industries", "ticker": "RELIANCE", "days": 30,
                  "limit": 5}, ["items_total"]),
    ("get_filings", {"symbol": "RELIANCE", "days": 30}, ["material_count"]),
    ("get_corporate_actions", {"symbol": "RELIANCE"}, ["corporate_actions"]),
    ("get_shareholding", {"symbol": "VEDL", "quarters": 4}, ["quarters"]),
    ("get_fund_holdings", {"mf_id": None, "limit": 3}, ["positions_total"]),
    ("get_stock_ratios", {"sid": None}, ["ticker"]),
    ("get_market_context", {"mode": "quick"}, ["digest", "market_trend"]),
]

# tool -> the argument only an earlier call can supply; skipped if unresolved.
RUNTIME_ARG = {"get_fund_holdings": "mf_id", "get_stock_ratios": "sid"}


class Client:
    """Minimal MCP stdio client — enough to initialize and call tools."""

    def __init__(self, python_exe):
        self.proc = subprocess.Popen(
            [python_exe, SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1, cwd=ROOT)
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

    def _rpc(self, method, params, timeout=180):
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

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self.proc.kill()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--quick", action="store_true",
                    help="skip the slow valuation-history and market-context tools")
    args = ap.parse_args()

    skip = {"get_index_valuation_history", "get_market_context"} if args.quick else set()
    client = Client(args.python)
    passed = degraded = failed = 0
    resolved = {"mf_id": None, "sid": None}
    try:
        for name, call_args, must_have in CASES:
            if name in skip:
                continue
            call_args = dict(call_args)
            arg = RUNTIME_ARG.get(name)
            if arg:
                if not resolved[arg]:
                    print(f"SKIP     {name:<30} no {arg} resolved upstream")
                    continue
                call_args[arg] = resolved[arg]
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
            if name == "get_fund_holdings":
                rows = data.get("positions") or []
                resolved["sid"] = (rows[0] or {}).get("sid") if rows else None

            missing = [k for k in must_have if k not in data]
            if not env.get("ok"):
                degraded += 1
                print(f"DEGRADED {name:<30} {(env.get('gaps') or ['?'])[0][:80]}")
            elif missing:
                failed += 1
                print(f"FAIL     {name:<30} missing keys {missing}")
            else:
                passed += 1
                print(f"PASS     {name:<30} src={env.get('source')}")
    finally:
        errlog = list(client.errlog)
        client.close()

    print(f"\n{passed} passed, {degraded} degraded, {failed} failed")
    if failed and errlog:
        print("\nserver stderr (last 20 lines):")
        for line in errlog[-20:]:
            print(f"  {line}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
