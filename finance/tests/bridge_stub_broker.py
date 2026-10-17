#!/usr/bin/env python3
"""A stand-in for a hosted broker MCP, for finance/tests/test_mcp_bridge.py.

Speaks the OAuth/MCP subset needed for mcp-remote login-sharing tests. It is
not a protocol conformance or PKCE-security test server (it does not validate
verifiers or refresh-token ownership). It carries the broker traits the bridge has to survive:

  * one live access token per user — issuing a new one revokes every earlier
    token, so a needless re-authorization logs another session out;
  * single-use refresh tokens, as IndMoney issues them: redeeming one rotates it,
    and a second redemption of the same token is refused (`refresh_rejected`);
  * access tokens that really expire (`STUB_EXPIRES_IN` seconds, default 3600);
  * optionally (STUB_PIN_FIRST_REDIRECT=1) a client locked to the callback port
    of its first registration, refusing to register on any other;
  * optionally (STUB_NO_AUTH=1) no OAuth at all, as Kite serves.

Registrations, authorizations, token issues and revocations are appended to
events.jsonl for the test to assert on.
"""
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, urlencode

STATE_DIR = os.environ["STUB_STATE_DIR"]
PIN_FIRST_REDIRECT = os.environ.get("STUB_PIN_FIRST_REDIRECT") == "1"
NO_AUTH = os.environ.get("STUB_NO_AUTH") == "1"
EXPIRES_IN = int(os.environ.get("STUB_EXPIRES_IN", "3600"))

EVENTS = os.path.join(STATE_DIR, "events.jsonl")
_lock = threading.Lock()

clients = {}        # client_id -> {redirect_uris}
codes = {}          # code -> {client_id, redirect_uri, challenge}
live_tokens = {}    # access token -> expiry (epoch seconds) the broker still honours
refresh_tokens = set()  # unredeemed refresh tokens
pinned_first = {"port": None}   # set by the first registration when pinning


def record(kind, **fields):
    with _lock:
        with open(EVENTS, "a") as fh:
            fh.write(json.dumps({"event": kind, "ts": time.time(), **fields}) + "\n")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # -- plumbing ---------------------------------------------------------
    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body=b"", ctype="application/json", extra=None):
        self.send_response(code)
        if body:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, code, obj, extra=None):
        self._send(code, json.dumps(obj).encode(), extra=extra)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    @property
    def origin(self):
        return f"http://{self.headers.get('Host')}"

    # -- OAuth discovery --------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path

        if NO_AUTH and path.startswith("/.well-known/"):
            return self._send(404, b"{}")

        if path.startswith("/.well-known/oauth-protected-resource"):
            return self._json(200, {
                "resource": f"{self.origin}/mcp",
                "authorization_servers": [self.origin],
            })

        if path.startswith("/.well-known/oauth-authorization-server") or \
           path.startswith("/.well-known/openid-configuration"):
            return self._json(200, {
                "issuer": self.origin,
                "authorization_endpoint": f"{self.origin}/authorize",
                "token_endpoint": f"{self.origin}/token",
                "registration_endpoint": f"{self.origin}/register",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
            })

        if path == "/authorize":
            return self._authorize()

        if path == "/mcp":
            # No server-initiated SSE stream here; 405 is how a streamable-HTTP
            # server says so, and the client then stops asking.
            return self._send(405, b"")

        return self._send(404, b"{}")

    def do_DELETE(self):
        if urlparse(self.path).path == "/mcp":
            return self._send(200, b"")
        return self._send(404, b"{}")

    def _authorize(self):
        q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        client_id, redirect_uri = q.get("client_id"), q.get("redirect_uri")
        record("authorize", client_id=client_id, redirect_uri=redirect_uri)

        client = clients.get(client_id)
        if not client or redirect_uri not in client["redirect_uris"]:
            return self._json(400, {"error": "invalid_request",
                                    "error_description": "unknown client or redirect_uri"})

        code = uuid.uuid4().hex
        codes[code] = {"client_id": client_id, "redirect_uri": redirect_uri,
                       "challenge": q.get("code_challenge")}
        params = {"code": code}
        if q.get("state"):
            params["state"] = q["state"]
        sep = "&" if "?" in redirect_uri else "?"
        self._send(302, b"", extra={"Location": f"{redirect_uri}{sep}{urlencode(params)}"})

    # -- registration / token / mcp ---------------------------------------
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/register":
            return self._register()
        if path == "/token":
            return self._token()
        if path == "/mcp":
            return self._mcp()
        return self._send(404, b"{}")

    def _register(self):
        req = json.loads(self._body() or b"{}")
        uris = req.get("redirect_uris") or []
        record("register", redirect_uris=uris)

        if PIN_FIRST_REDIRECT:
            with _lock:
                if pinned_first["port"] is None and uris:
                    pinned_first["port"] = urlparse(uris[0]).port
                pinned = pinned_first["port"]
            if not any(urlparse(u).port == pinned for u in uris):
                record("register_rejected", redirect_uris=uris, pinned_port=pinned)
                return self._json(400, {
                    "error": "invalid_redirect_uri",
                    "error_description": f"redirect_uri must use port {pinned}",
                })

        client_id = "client-" + uuid.uuid4().hex
        clients[client_id] = {"redirect_uris": uris}
        return self._json(201, {
            "client_id": client_id,
            "client_id_issued_at": int(time.time()),
            "redirect_uris": uris,
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "none",
        })

    def _token(self):
        raw = self._body().decode()
        form = {k: v[0] for k, v in parse_qs(raw).items()}
        grant = form.get("grant_type")

        if grant == "authorization_code":
            entry = codes.pop(form.get("code", ""), None)
            if not entry:
                return self._json(400, {"error": "invalid_grant"})
        elif grant == "refresh_token":
            with _lock:
                redeemed = form.get("refresh_token") in refresh_tokens
                refresh_tokens.discard(form.get("refresh_token"))
            if not redeemed:
                record("refresh_rejected")
                return self._json(400, {"error": "invalid_grant"})
        else:
            return self._json(400, {"error": "unsupported_grant_type"})

        token, refresh = uuid.uuid4().hex, uuid.uuid4().hex
        with _lock:
            # One live token per user: minting a new one kills every earlier one.
            revoked = list(live_tokens)
            live_tokens.clear()
            live_tokens[token] = time.time() + EXPIRES_IN
            refresh_tokens.add(refresh)
        # Recorded outside the lock — record() takes it too, and it is not reentrant.
        if revoked:
            record("revoked_previous_tokens", count=len(revoked))
        record("token_issued", grant_type=grant, token=token)
        return self._json(200, {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": EXPIRES_IN,
            "refresh_token": refresh,
        })

    def _mcp(self):
        auth = self.headers.get("Authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else None
        body = self._body()

        if not NO_AUTH and (not token or live_tokens.get(token, 0) < time.time()):
            record("mcp_401", had_token=bool(token))
            return self._json(401, {"error": "invalid_token"}, extra={
                "WWW-Authenticate":
                    f'Bearer resource_metadata="{self.origin}/.well-known/oauth-protected-resource/mcp"',
            })

        msg = json.loads(body or b"{}")
        if isinstance(msg, list):
            msg = msg[0]
        method, mid = msg.get("method"), msg.get("id")

        if mid is None:  # a notification
            return self._send(202)

        if method == "initialize":
            result = {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "stub-broker", "version": "1.0.0"},
            }
        elif method == "tools/list":
            record("tools_list", token=token)
            result = {"tools": [{
                "name": "get_holdings",
                "description": "Stub holdings",
                "inputSchema": {"type": "object", "properties": {}},
            }]}
        else:
            return self._json(200, {"jsonrpc": "2.0", "id": mid,
                                    "error": {"code": -32601, "message": "not implemented"}})

        return self._json(200, {"jsonrpc": "2.0", "id": mid, "result": result})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    with open(os.path.join(STATE_DIR, "port"), "w") as fh:
        fh.write(str(srv.server_address[1]))
    srv.serve_forever()
