"""Session plumbing for the bin/mcp-bridge.sh end-to-end test.

Support module for finance/tests/test_mcp_bridge.py; not a test itself.

A Session is one Claude window: it runs the bridge under its own parent shell (so
$PPID differs, exactly as it does for two Claude processes), speaks JSON-RPC over
the bridge's stdio, and completes the browser leg of OAuth by fetching the
authorize URL a shimmed `open` on PATH records instead of launching a browser.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STUB_BROKER = os.path.join(HERE, "bridge_stub_broker.py")

_SHIM = """#!/bin/sh
# Shadows /usr/bin/open on PATH so the test never launches a real browser.
# mcp-remote's `open` package calls `open <url>`; we just record the URL.
printf '%s\\n' "$1" >> "$STUB_STATE_DIR/authorize_urls"
exit 0
"""


def shim_bin(parent):
    """A PATH entry whose `open` records the URL instead of opening a browser."""
    d = os.path.join(parent, "shim-bin")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "open")
    with open(path, "w") as fh:
        fh.write(_SHIM)
    os.chmod(path, 0o755)
    return d


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surfaces the OAuth 302 instead of following it."""

    def redirect_request(self, *_a, **_k):
        return None


class Broker:
    """The stub broker MCP, running for the length of a `with` block."""

    def __init__(self, state_dir, pin_first_redirect=False):
        self.state_dir = state_dir
        self.env = {"STUB_STATE_DIR": state_dir}
        if pin_first_redirect:
            self.env["STUB_PIN_FIRST_REDIRECT"] = "1"

    def __enter__(self):
        shutil.rmtree(self.state_dir, ignore_errors=True)
        os.makedirs(self.state_dir)
        # stderr goes to a file, not a pipe: an undrained pipe fills up and
        # wedges the broker mid-request.
        self.log_path = os.path.join(self.state_dir, "broker.log")
        self._log = open(self.log_path, "wb")
        self.proc = subprocess.Popen(
            [sys.executable, "-u", STUB_BROKER, "0"],
            env={**os.environ, **self.env},
            stdout=self._log, stderr=self._log,
        )
        port_file = os.path.join(self.state_dir, "port")
        for _ in range(100):
            if os.path.exists(port_file):
                self.port = int(open(port_file).read())
                self.url = f"http://127.0.0.1:{self.port}/mcp"
                return self
            time.sleep(0.05)
        raise RuntimeError("stub broker never bound a port: "
                           + open(self.log_path).read())

    def __exit__(self, *exc):
        self.proc.terminate()
        self.proc.wait(timeout=5)
        self._log.close()

    def events(self, kind=None):
        path = os.path.join(self.state_dir, "events.jsonl")
        if not os.path.exists(path):
            return []
        rows = [json.loads(line) for line in open(path) if line.strip()]
        return [r for r in rows if kind is None or r["event"] == kind]


class Session:
    """One Claude session talking to one broker through bin/mcp-bridge.sh."""

    def __init__(self, name, bridge, url, state_dir, env=None):
        self.name, self.bridge, self.url = name, bridge, url
        self.state_dir = state_dir
        self.extra_env = env or {}
        self.shim = shim_bin(state_dir)
        self.stderr_lines = []
        self._responses = {}
        self._next_id = 1

    def start(self):
        env = {
            **os.environ,
            **self.extra_env,
            "STUB_STATE_DIR": self.state_dir,
            "PATH": self.shim + os.pathsep + os.environ["PATH"],
        }
        # `; exit $?` stops sh from exec-ing the bridge in place, so the bridge
        # gets a distinct parent pid per session — the same shape as two Claude
        # processes each spawning their own stdio server.
        self.proc = subprocess.Popen(
            ["sh", "-c", '"$0" "$@"; exit $?', self.bridge, self.url],
            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0,
            start_new_session=True,   # own process group, so stop() can reap npx+node too
        )
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()
        return self

    def _pump_stdout(self):
        for raw in self.proc.stdout:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if "id" in msg:
                self._responses[msg["id"]] = msg

    def _pump_stderr(self):
        for raw in self.proc.stderr:
            self.stderr_lines.append(raw.decode(errors="replace").rstrip())

    def stderr(self):
        return "\n".join(self.stderr_lines)

    def send(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if notify:
            self.proc.stdin.write((json.dumps(msg) + "\n").encode())
            self.proc.stdin.flush()
            return None
        mid = self._next_id
        self._next_id += 1
        msg["id"] = mid
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        self.proc.stdin.flush()
        return mid

    def wait_for(self, mid, timeout=60):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if mid in self._responses:
                return self._responses[mid]
            if self.proc.poll() is not None:
                raise RuntimeError(
                    f"[{self.name}] bridge exited rc={self.proc.returncode}\n{self.stderr()}")
            time.sleep(0.05)
        raise TimeoutError(f"[{self.name}] no response to id={mid} in {timeout}s\n{self.stderr()}")

    def initialize(self, timeout=60):
        mid = self.send("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": self.name, "version": "1.0"},
        })
        resp = self.wait_for(mid, timeout)
        self.send("notifications/initialized", notify=True)
        return resp

    def list_tools(self, timeout=60):
        return self.wait_for(self.send("tools/list"), timeout)

    def stop(self):
        """Tear down the whole session: sh -> npx -> node, not just the shell."""
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            self.proc.wait(timeout=5)


class BrowserBot:
    """Stands in for the user: fetches every authorize URL mcp-remote opens."""

    def __init__(self, state_dir):
        self.state_dir = state_dir
        self._stop = threading.Event()

    def __enter__(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self):
        path = os.path.join(self.state_dir, "authorize_urls")
        seen = 0
        while not self._stop.is_set():
            if os.path.exists(path):
                urls = [u for u in open(path).read().splitlines() if u.strip()]
                while seen < len(urls):
                    self._login(urls[seen])
                    seen += 1
            self._stop.wait(0.1)

    def _login(self, url):
        """Authorize, then hand the code to the callback the broker redirects to.

        Split in two rather than following the 302 automatically: mcp-remote
        prints the authorize URL just before it binds its callback port, so the
        retry on the callback leg stands in for the seconds a human browser takes.
        """
        try:
            urllib.request.build_opener(_NoRedirect).open(url, timeout=10)
            return                                   # no redirect: nothing to deliver
        except urllib.error.HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308):
                return
            callback = exc.headers.get("Location")

        deadline = time.time() + 30
        while time.time() < deadline and not self._stop.is_set():
            try:
                urllib.request.urlopen(callback, timeout=10).read()
                return
            except urllib.error.HTTPError:
                return
            except Exception:  # noqa: BLE001 - callback port not up yet
                self._stop.wait(0.25)
