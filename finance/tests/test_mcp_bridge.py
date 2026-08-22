#!/usr/bin/env python3
"""Tests for bin/mcp-bridge.sh — one broker login shared by every session.

Two layers:

  * static — reads the script and asserts the properties the sharing rests on.
    Always runs, costs nothing.
  * end-to-end — drives real `mcp-remote` processes through the real bridge
    against a stub broker that behaves like Kite/IndMoney (one live access token
    per user). Needs network for `npx` and takes a couple of minutes, so it runs
    only under EF_BRIDGE_E2E=1.

Run: python3 finance/tests/test_mcp_bridge.py
     EF_BRIDGE_E2E=1 python3 finance/tests/test_mcp_bridge.py
"""
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.tests.harness import check, summary  # noqa: E402
from finance.tests.bridge_sessions import Broker, BrowserBot, Session  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BRIDGE = os.environ.get("EF_BRIDGE", os.path.join(ROOT, "bin", "mcp-bridge.sh"))
E2E = os.environ.get("EF_BRIDGE_E2E") == "1"


# --- static ------------------------------------------------------------------

def test_bridge_script():
    src = open(BRIDGE).read()

    check("config dir is one shared store",
          'MCP_REMOTE_CONFIG_DIR="${HOME}/.mcp-auth"' in src)
    check("config dir is not per-session", "$PPID" not in src)
    check("pins an mcp-remote version floor", "mcp-remote@^0.1.43" in src,
          "the shared store needs 0.1.43's concurrency fixes")
    check("gates the first login", ".first-login-" in src)
    check("token store is owner-only", "chmod 700" in src)
    check("reaps orphaned bridges", '[ "$ppid" = "1" ]' in src)


# --- end to end --------------------------------------------------------------

def _session_env(work):
    home = os.path.join(work, "home")
    os.makedirs(home)
    # A private HOME keeps the test off the real token store; npm's cache stays
    # shared so npx does not re-download mcp-remote per scenario.
    return {"HOME": home, "npm_config_cache": os.path.expanduser("~/.npm")}


def _ok(resp):
    return isinstance(resp, dict) and "result" in resp


def _connect(session, timeout=60):
    try:
        session.initialize(timeout=timeout)
        return _ok(session.list_tools(timeout=30))
    except Exception as exc:  # noqa: BLE001 - the failure is the finding
        return f"{type(exc).__name__}"


def _saved_tokens(home):
    hits = []
    for root, _dirs, files in os.walk(home):
        hits += [os.path.join(root, f) for f in files if f.endswith("tokens.json")]
    return hits


def _token_accepted(broker_url, token):
    req = urllib.request.Request(
        broker_url, method="POST",
        data=json.dumps({"jsonrpc": "2.0", "id": 99,
                         "method": "tools/list", "params": {}}).encode(),
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream",
                 "Authorization": f"Bearer {token}"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except urllib.error.HTTPError:
        return False


def test_second_session_joins_a_live_one():
    """Session A is running; the user opens session B."""
    with tempfile.TemporaryDirectory() as work:
        env = _session_env(work)
        sd = os.path.join(work, "broker")
        with Broker(sd) as broker, BrowserBot(sd):
            a = Session("A", BRIDGE, broker.url, sd, env).start()
            b = Session("B", BRIDGE, broker.url, sd, env)
            try:
                a.initialize()
                a.list_tools()
                logins = len(broker.events("authorize"))

                b.start()
                b_state = _connect(b, timeout=45)
                extra = len(broker.events("authorize")) - logins
                a_state = _connect(a, timeout=30) if b_state is True else None
            finally:
                a.stop()
                b.stop()

            check("B connects without its own login", b_state is True, b_state)
            check("B triggered no second login", extra == 0, f"{extra} extra")
            check("A keeps working after B joins", a_state is True, a_state)
            check("one OAuth client for both", len(broker.events("register")) == 1,
                  f"{len(broker.events('register'))} registrations")


def test_later_session_inherits_the_token():
    """Session A logs in and exits; session B starts later."""
    with tempfile.TemporaryDirectory() as work:
        env = _session_env(work)
        sd = os.path.join(work, "broker")
        with Broker(sd) as broker, BrowserBot(sd):
            a = Session("A", BRIDGE, broker.url, sd, env).start()
            a.initialize()
            a.list_tools()
            saved = _saved_tokens(env["HOME"])
            a_token = json.load(open(saved[0]))["access_token"] if saved else None
            a.stop()

            logins = len(broker.events("authorize"))
            b = Session("B", BRIDGE, broker.url, sd, env).start()
            b_state = _connect(b, timeout=45)
            b.stop()
            extra = len(broker.events("authorize")) - logins

            check("B connects without its own login", b_state is True, b_state)
            check("B triggered no second login", extra == 0, f"{extra} extra")
            check("A's token was never revoked",
                  a_token is not None and _token_accepted(broker.url, a_token) is True,
                  "a single-token broker revokes on re-authorization")
            check("one OAuth client for both", len(broker.events("register")) == 1,
                  f"{len(broker.events('register'))} registrations")


def test_simultaneous_cold_start():
    """Two sessions start against an empty store at the same moment.

    Ungated, both race for the same derived callback port and the loser
    re-registers the OAuth client, deleting the client_info.json the winner is
    mid-exchange on — killing both logins.
    """
    with tempfile.TemporaryDirectory() as work:
        env = _session_env(work)
        sd = os.path.join(work, "broker")
        with Broker(sd) as broker, BrowserBot(sd):
            a = Session("A", BRIDGE, broker.url, sd, env).start()
            b = Session("B", BRIDGE, broker.url, sd, env).start()
            try:
                states = {n: _connect(s, timeout=90) for n, s in (("A", a), ("B", b))}
            finally:
                a.stop()
                b.stop()

            check("both sessions connect",
                  states["A"] is True and states["B"] is True, states)
            check("exactly one browser login",
                  len(broker.events("authorize")) == 1,
                  f"{len(broker.events('authorize'))} logins")
            check("nothing was revoked",
                  len(broker.events("revoked_previous_tokens")) == 0)


def test_broker_that_pins_its_redirect():
    """A broker that locks the client to the callback port it first registered.

    It rejects any re-registration outright, so a second session must reuse the
    first one's client rather than making its own.
    """
    with tempfile.TemporaryDirectory() as work:
        env = _session_env(work)
        sd = os.path.join(work, "broker")
        with Broker(sd, pin_first_redirect=True) as broker, BrowserBot(sd):
            a = Session("A", BRIDGE, broker.url, sd, env).start()
            try:
                a.initialize()
                a.list_tools()
                b = Session("B", BRIDGE, broker.url, sd, env).start()
                b_state = _connect(b, timeout=45)
                b.stop()
            finally:
                a.stop()

            check("B connects to a pinned-redirect broker", b_state is True, b_state)
            check("no registration was rejected",
                  len(broker.events("register_rejected")) == 0,
                  f"{len(broker.events('register_rejected'))} rejected")


if __name__ == "__main__":
    tests = [test_bridge_script]
    if E2E:
        if not shutil.which("npx"):
            print("  note: npx not found — skipping the end-to-end scenarios")
        else:
            tests += [test_second_session_joins_a_live_one,
                      test_later_session_inherits_the_token,
                      test_simultaneous_cold_start,
                      test_broker_that_pins_its_redirect]
    else:
        print("  note: set EF_BRIDGE_E2E=1 to also run the mcp-remote scenarios")
    for fn in tests:
        print(f"\n[{fn.__name__}]")
        fn()
    summary()
