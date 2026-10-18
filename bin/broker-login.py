#!/usr/bin/env python3
"""Broker MCP bridge supervisor: one login per broker, shared by every Claude session.

Each session starts its own mcp-remote proxy per broker, all reading one token store.

1. **One refresher.** The brokers rotate refresh tokens, so concurrent refreshes leave every
   loser on a dead token. One refresher, under a cross-process lock, keeps the stored token
   ahead of expiry; proxies re-read the store on every request and never refresh.
2. **One detached login.** A browser login runs in one `mcp-remote-client` with a 15-minute
   window, under a lock, so it outlives the session that started it (Claude's connect limit
   and mcp-remote's 30-second auth limit are far shorter than typing an OTP), and no second
   tab opens while it runs.
3. **Proxies never open a tab.** They run with a PATH whose `open` records the request, so the
   login above is the only place a tab can come from. A login opened in the background is not
   reopened for `RELOGIN_COOLDOWN`; starting or reconnecting a session can always open one.
4. **Non-OAuth brokers pass through.** Kite has no token to wait for.

usage: broker-login.py URL MCP_REMOTE_VERSION [mcp-remote options]   (via bin/mcp-bridge.sh)
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "everything-finance-bridge/1.0"     # the brokers' edge rejects urllib's default agent
REFRESH_AHEAD = float(os.environ.get("EF_BRIDGE_REFRESH_AHEAD", 600))   # seconds before expiry
KEEPER_INTERVAL = float(os.environ.get("EF_BRIDGE_KEEPER_INTERVAL", 30))
LOGIN_WINDOW = int(os.environ.get("EF_BRIDGE_LOGIN_WINDOW", 900))       # seconds to finish a login
RELOGIN_COOLDOWN = 1800   # a background login is not reopened sooner than this
STALE_VERIFIER_DAYS = 1


def log(msg):
    print(f"[mcp-bridge] {msg}", file=sys.stderr, flush=True)


def login_wait():
    """How long a starting session waits for a login in progress: just under Claude's own
    connect limit (MCP_TIMEOUT, milliseconds), so a login finished in time connects at once."""
    if os.environ.get("EF_BRIDGE_LOGIN_WAIT"):
        return float(os.environ["EF_BRIDGE_LOGIN_WAIT"])
    try:
        limit = float(os.environ["MCP_TIMEOUT"]) / 1000.0
    except (KeyError, ValueError):
        limit = 30.0
    return max(5.0, min(limit - 8.0, 300.0))


class Store:
    """mcp-remote's files for one broker URL under the pinned version dir."""

    def __init__(self, root, version, url):
        self.url = url
        self.key = hashlib.md5(url.encode()).hexdigest()  # mcp-remote's persisted URL key
        self.root = Path(root)
        self.dir = self.root / f"mcp-remote-{version}"
        self.tokens = self.dir / f"{self.key}_tokens.json"
        self.client = self.dir / f"{self.key}_client_info.json"
        self.login_log = self.root / f"login-{self.key}.log"
        self.login_started = self.root / f".login-started-{self.key}"
        self.no_browser = self.root / ".no-browser"

    def lock(self, kind):
        # Lock files are never removed: a waiter may already hold this inode open.
        return (self.root / f".{kind}-{self.key}.lock").open("a")

    def read(self, path):
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return None

    def fresh(self, ahead):
        """True when the stored access token outlives `ahead` seconds (or has no expiry)."""
        tokens = self.read(self.tokens)
        if not isinstance(tokens, dict) or not tokens.get("access_token"):
            return False
        expires_at = tokens.get("expires_at")
        return not isinstance(expires_at, (int, float)) or expires_at / 1000.0 - time.time() > ahead

    def save_tokens(self, tokens):
        self.dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".tokens-")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as fh:
                json.dump(tokens, fh, indent=2)
            os.replace(tmp, self.tokens)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def proxy_env(self):
        """The environment for a proxy: an `open` that never launches a browser."""
        self.no_browser.mkdir(exist_ok=True)
        for name in ("open", "xdg-open"):
            shim = self.no_browser / name
            if not shim.is_file():
                shim.write_text("#!/bin/sh\nprintf '%s proxy asked to open a login; left to the "
                                "bridge\\n' \"$(date)\" >> \"$(dirname \"$0\")/requests.log\"\n")
                shim.chmod(0o755)
        return {**os.environ, "PATH": f"{self.no_browser}{os.pathsep}{os.environ.get('PATH', '')}"}

    def sweep(self):
        """mcp-remote leaves a PKCE verifier file per process; drop day-old ones."""
        cutoff = time.time() - STALE_VERIFIER_DAYS * 86400
        for path in self.dir.glob("*_code_verifier_*.txt"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass


def _request(url, data=None, headers=None, timeout=15):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, resp.read()


def needs_oauth(store):
    """A broker that registered an OAuth client, or answers an anonymous initialize with 401."""
    if store.client.is_file():
        return True
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "clientInfo": {"name": "bridge-probe", "version": "1"}}})
    try:
        _request(store.url, body.encode(), {"Content-Type": "application/json",
                                            "Accept": "application/json, text/event-stream"})
        return False
    except urllib.error.HTTPError as exc:
        return exc.code == 401
    except OSError:
        return False  # offline: let mcp-remote report the failure itself


def _token_endpoint(store):
    """(token_endpoint, resource) from the broker's own OAuth metadata, or (None, None)."""
    parts = urllib.parse.urlsplit(store.url)
    origin = f"{parts.scheme}://{parts.netloc}"
    try:
        _, raw = _request(f"{origin}/.well-known/oauth-protected-resource{parts.path}")
        prm = json.loads(raw)
        issuer = (prm.get("authorization_servers") or [origin])[0].rstrip("/")
        _, raw = _request(f"{issuer}/.well-known/oauth-authorization-server")
        return json.loads(raw).get("token_endpoint"), prm.get("resource")
    except (OSError, ValueError, AttributeError, IndexError):
        return None, None


def refresh(store, ahead):
    """Refresh the stored token once across every process. True when a fresh token is stored."""
    with store.lock("refresh") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if store.fresh(ahead):
            return True  # another process refreshed while we waited
        tokens, client = store.read(store.tokens), store.read(store.client)
        if not (isinstance(tokens, dict) and tokens.get("refresh_token")
                and isinstance(client, dict) and client.get("client_id")):
            return False
        endpoint, resource = _token_endpoint(store)
        if not endpoint:
            log("token refresh skipped: the broker's OAuth metadata did not load")
            return False
        form = {"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
                "client_id": client["client_id"]}
        if client.get("client_secret"):
            form["client_secret"] = client["client_secret"]
        if resource:
            form["resource"] = resource
        try:
            _, raw = _request(endpoint, urllib.parse.urlencode(form).encode(),
                              {"Content-Type": "application/x-www-form-urlencoded",
                               "Accept": "application/json"}, timeout=20)
            issued = json.loads(raw)
        except urllib.error.HTTPError as exc:
            log(f"token refresh refused (HTTP {exc.code}); a browser login is needed")
            return False
        except (OSError, ValueError) as exc:
            log(f"token refresh failed ({type(exc).__name__}); will retry")
            return False
        if not issued.get("access_token"):
            return False
        expires_in = issued.get("expires_in")
        store.save_tokens({**issued,
                           "refresh_token": issued.get("refresh_token") or tokens["refresh_token"],
                           "expires_at": (int(time.time() * 1000 + expires_in * 1000)
                                          if isinstance(expires_in, (int, float)) else None)})
        log("refreshed the broker token")
        return True


def start_login(store, version, args, cooldown=0):
    """Open one browser login unless one is running, or one opened within `cooldown` seconds.
    True when this call opened it."""
    try:
        if time.time() - store.login_started.stat().st_mtime < cooldown:
            return False
    except OSError:
        pass
    lock = store.lock("login")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return False  # a login is in progress in another session; no second tab
    if store.fresh(0):
        lock.close()
        return False
    store.login_started.touch()
    # The login child inherits the locked descriptor, so the lock lasts exactly as long as the
    # login does — whichever session started it, and even after that session is gone.
    with store.login_log.open("w") as out:
        subprocess.Popen(
            ["npx", "-y", "-p", f"mcp-remote@{version}", "mcp-remote-client", store.url,
             "--auth-timeout", str(LOGIN_WINDOW), *args],
            stdin=subprocess.DEVNULL, stdout=out, stderr=out, start_new_session=True,
            pass_fds=(lock.fileno(),))
    lock.close()
    log(f"opened a browser login for {store.url}; it stays open {LOGIN_WINDOW // 60} minutes")
    return True


def ensure_token(store, version, args):
    """True once a usable token is stored: refreshed if possible, else after one login."""
    if store.fresh(REFRESH_AHEAD):
        return True
    if store.read(store.tokens) and refresh(store, REFRESH_AHEAD):
        return True
    if store.fresh(0):
        return True  # inside the refresh window but still valid; the keeper retries
    start_login(store, version, args)
    deadline = time.monotonic() + login_wait()
    while time.monotonic() < deadline:
        if store.fresh(0):
            return True
        time.sleep(0.5)
    return False


def keep_fresh(store, version, args, stop):
    """Refresh ahead of expiry for as long as this session's proxy runs."""
    while not stop.wait(KEEPER_INTERVAL):
        if store.fresh(REFRESH_AHEAD):
            continue
        if not refresh(store, REFRESH_AHEAD) and not store.fresh(0):
            start_login(store, version, args, cooldown=RELOGIN_COOLDOWN)


def run(url, version, root, args):
    store = Store(root, version, url)
    store.dir.mkdir(parents=True, exist_ok=True)
    store.sweep()
    proxy = ["npx", "-y", f"mcp-remote@{version}", url, *args]
    if not needs_oauth(store):
        os.execvp(proxy[0], proxy)
    if not ensure_token(store, version, args):
        log(f"{url} is waiting for a browser login. Finish it in the open tab, then reconnect "
            "this server (/mcp). Other sessions will not open another tab meanwhile.")
        return 1
    # The proxy shares this process's stdio; the supervisor stays to keep the token fresh.
    child = subprocess.Popen(proxy, start_new_session=True, env=store.proxy_env())

    def forward(signum, _frame):
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)
    signal.signal(signal.SIGHUP, forward)
    stop = threading.Event()
    threading.Thread(target=keep_fresh, args=(store, version, args, stop), daemon=True).start()
    try:
        return child.wait()
    finally:
        stop.set()
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)


if __name__ == "__main__":
    try:
        sys.exit(run(sys.argv[1], sys.argv[2], os.environ["MCP_REMOTE_CONFIG_DIR"], sys.argv[3:]))
    except (OSError, KeyError, IndexError) as exc:
        log(f"cannot start broker bridge: {exc}")
        sys.exit(1)
