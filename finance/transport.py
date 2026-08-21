#!/usr/bin/env python3
"""The ONE HTTP transport for the everything-finance data spine.

Exactly one function touches the network: `request()`. Everything else in `finance/` calls
it, so a UA, a header set or a block workaround has one definition.

Named `transport`, not `http`: `http` is a stdlib package name, and a top-level `http.py`
shadows it for every dependency in the process — yfinance's `import http.client` would
resolve to this file and break price history. Do not rename it.

Everything goes through curl because `nseindia.com` returns 403 to urllib even with a
complete browser header set — the block is on the TLS/HTTP2 fingerprint, not the headers
(verified 2026-08-16) — while curl is served normally. The hardest site in the set dictates
the transport for all of them.

`request()` returns `(body, gap)` and never raises: a blocked or failed fetch is a labelled
gap the caller records and continues past (CLAUDE.md). `json_request()` treats "the response
wasn't JSON" as one more labelled gap — the failure that actually happens when a site swaps
a payload for an HTML interstitial.

Fetched bytes are untrusted data. This module returns text; it never evaluates it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time

# One User-Agent for the whole plugin — a site that gates on UA must block all of it or
# none of it, never half.
DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

DEFAULT_ACCEPT = "application/json, text/csv, text/plain, text/html, */*"

# curl exit codes that describe a transient network condition (DNS blip, connect reset,
# timeout, TLS handshake, empty/short reply) rather than a refusal. Only these are
# retried: retrying a 403 just gets a slower 403.
_TRANSIENT_EXITS = frozenset({6, 7, 16, 18, 28, 35, 52, 55, 56, 92})

# HTTP statuses worth one more try — a rate-limit or an origin hiccup, not a refusal.
_TRANSIENT_STATUS = frozenset({408, 429, 500, 502, 503, 504})


def _host(url):
    """Host of a URL for gap labels, without importing urllib just for this."""
    try:
        return url.split("//", 1)[1].split("/", 1)[0]
    except (IndexError, AttributeError):
        return str(url)[:40]


def request(url, *, payload=None, headers=None, referer=None, origin=None,
            cookie_jar=None, timeout=25, retries=2, accept=None, ua=None, dest=None):
    """Fetch `url` and return `(body, gap)` — one of the two is always None.

    GET by default; POSTs JSON when `payload` is given. `cookie_jar` is a file path used
    for BOTH read and write (`-b` and `-c`), which is what makes a homepage bootstrap
    able to prime a later API call — see `bootstrap()`.

    `dest` saves the response to that path and returns it in place of the body: a PDF
    decoded to text is destroyed, so binary payloads must never round-trip through a str.
    The file appears only on a 2xx, so a failed fetch cannot leave an error page sitting
    where a caller expects a document.

    On failure `body` is None and `gap` is a short human-readable label naming the host
    and the reason, ready to drop into an envelope's `gaps` list.
    """
    fd, body_file = tempfile.mkstemp(prefix="ef-http-", suffix=".body")
    os.close(fd)
    try:
        cmd = ["curl", "-sS", "-L", "--compressed",
               "--max-time", str(timeout),
               "--connect-timeout", str(min(timeout, 15)),
               "-o", body_file, "-w", "%{http_code}",
               "-H", f"User-Agent: {ua or DEFAULT_UA}",
               "-H", f"Accept: {accept or DEFAULT_ACCEPT}",
               "-H", "Accept-Language: en-US,en;q=0.9"]
        if referer:
            cmd += ["-H", f"Referer: {referer}"]
        if origin:
            cmd += ["-H", f"Origin: {origin}"]
        for key, val in (headers or {}).items():
            cmd += ["-H", f"{key}: {val}"]
        if cookie_jar:
            cmd += ["-b", cookie_jar, "-c", cookie_jar]
        if payload is not None:
            cmd += ["-X", "POST", "-H", "Content-Type: application/json",
                    "--data-binary", json.dumps(payload)]
        cmd.append(url)

        last = None
        for attempt in range(max(1, retries + 1)):
            if attempt:
                time.sleep(0.6 * attempt)  # linear backoff; these are small endpoints
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=timeout + 10)
            except subprocess.TimeoutExpired:
                last = f"{_host(url)}: timed out after {timeout}s"
                continue
            except Exception as exc:  # noqa: BLE001 — degrade-not-die
                return None, f"{_host(url)}: curl could not run ({exc})"

            if proc.returncode != 0:
                detail = (proc.stderr or "").strip().splitlines()
                last = (f"{_host(url)}: curl exit {proc.returncode}"
                        + (f" ({detail[-1][:100]})" if detail else ""))
                if proc.returncode in _TRANSIENT_EXITS:
                    continue
                return None, last

            status = (proc.stdout or "").strip()[-3:]
            if status.isdigit() and not status.startswith("2"):
                code = int(status)
                last = f"{_host(url)}: HTTP {code}"
                if code in _TRANSIENT_STATUS:
                    continue
                return None, last

            if dest is not None:
                try:
                    shutil.move(body_file, dest)
                except OSError as exc:
                    return None, f"{_host(url)}: could not save response ({exc})"
                return dest, None
            try:
                with open(body_file, encoding="utf-8", errors="replace") as fh:
                    return fh.read(), None
            except OSError as exc:
                return None, f"{_host(url)}: could not read response ({exc})"

        return None, last or f"{_host(url)}: fetch failed"
    finally:
        try:
            os.unlink(body_file)
        except OSError:
            pass


def json_request(url, **kw):
    """`request()` plus JSON parsing. Returns `(parsed, gap)`.

    A non-JSON body is a labelled gap, not an exception — the realistic failure is a
    site swapping its payload for an HTML block page, and the snippet in the gap is what
    tells you which of the two happened.
    """
    body, gap = request(url, **kw)
    if gap:
        return None, gap
    try:
        return json.loads(body), None
    except (ValueError, TypeError) as exc:
        snippet = (body or "").strip()[:80].replace("\n", " ")
        return None, f"{_host(url)}: non-JSON response ({exc}): {snippet!r}"


def bootstrap(home_url, cookie_jar, timeout=20):
    """Prime `cookie_jar` with a site's bot cookies by fetching its homepage first.

    NSE hands out cookies on the homepage and rejects API calls that arrive without
    them. Returns the gap (or None) so a caller can label a failed bootstrap, though a
    failure here is usually worth attempting the real call anyway.
    """
    _, gap = request(home_url, cookie_jar=cookie_jar, timeout=timeout, retries=1)
    return gap


def jar_path(name):
    """A stable cookie-jar path under the disposable tmp tier (never hardcoded)."""
    # imported lazily so this module stays import-light
    from finance import paths  # noqa: PLC0415
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(name))
    return os.path.join(paths.tmp_dir("http"), f"{safe}-cookies.txt")


NSE_HOME = "https://www.nseindia.com/"


def nse_json(url, referer, headers=None, timeout=30):
    """Cookie-bootstrapped NSE JSON GET. Returns `(parsed, gap)`.

    NSE issues its API-gating cookies only on the homepage, so that is fetched into a jar
    first and the API call replays them. The jar is reused across calls within a run.
    """
    jar = jar_path("nse")
    bootstrap(NSE_HOME, jar)
    return json_request(url, referer=referer, cookie_jar=jar, timeout=timeout,
                        headers=headers)
