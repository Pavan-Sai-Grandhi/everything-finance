"""The one HTTP transport: `request()` is the only function in `finance/` that touches the
network, so a user agent, a header set or a block workaround has one definition. The
exception is yfinance in `sources/prices.py` and `sources/estimates.py`: it is the approved
Yahoo client and carries its own HTTP stack.

Named `transport`, not `http`, because a top-level `http.py` would shadow the stdlib package
for every dependency (yfinance's `import http.client` included).

Everything goes through curl because nseindia.com refuses urllib on its TLS fingerprint, and
the hardest site in the set dictates the transport for all of them. `request()` returns
`(body, gap)` and never raises; fetched bytes are untrusted text, never evaluated.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

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
    """Host label without credentials, query strings or unvalidated URL text."""
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        return (f"{host}:{parsed.port}" if parsed.port else host) or "request"
    except (ValueError, TypeError, AttributeError):
        return "request"


def request(url, *, payload=None, headers=None, referer=None, origin=None,
            cookie_jar=None, timeout=25, retries=2, accept=None, ua=None, dest=None,
            form=None, form_files=None, private_url=False, follow_redirects=True):
    """Fetch `url` and return `(body, gap)` — one of the two is always None.

    GET by default; POSTs JSON when `payload` is given. `cookie_jar` is a file path used
    for BOTH read and write (`-b` and `-c`), which is what makes a homepage bootstrap
    able to prime a later API call — see `bootstrap()`.

    `dest` saves the response to that path and returns it in place of the body: a PDF
    decoded to text is destroyed, so binary payloads must never round-trip through a str.
    The file appears only on a 2xx, so a failed fetch cannot leave an error page sitting
    where a caller expects a document.

    `follow_redirects=False` keeps a source's approved URL boundary intact: a redirect
    returns a gap instead of fetching an unchecked destination. Private URLs always
    refuse redirects.

    On failure `body` is None and `gap` is a short human-readable label naming the host
    and the reason, ready to drop into an envelope's `gaps` list.
    """
    body_file = None
    upload_file = None
    try:
        if not isinstance(url, str) or any(ord(c) < 32 for c in url):
            raise ValueError("invalid URL")
        parsed = urlsplit(url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            raise ValueError("an HTTP(S) URL without credentials is required")
        parsed.port  # validate a supplied port before invoking curl
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("timeout must be finite and positive")
        if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
            raise ValueError("retries must be a nonnegative integer")
        if headers is not None and not isinstance(headers, dict):
            raise ValueError("headers must be a mapping")
        request_headers = {"User-Agent": ua or DEFAULT_UA,
                           "Accept": accept or DEFAULT_ACCEPT,
                           "Accept-Language": "en-US,en;q=0.9"}
        if referer:
            request_headers["Referer"] = referer
        if origin:
            request_headers["Origin"] = origin
        request_headers.update(headers or {})
        for key, value in request_headers.items():
            if (not isinstance(key, str) or not key or ":" in key
                    or not isinstance(value, str)
                    or any(ord(c) < 32 or ord(c) == 127 for c in key + value)):
                raise ValueError("invalid HTTP header")
        encoded = json.dumps(payload, allow_nan=False) if payload is not None else None
        if form is not None or form_files is not None:
            if (payload is not None or (form is not None and not isinstance(form, dict))
                    or (form_files is not None and not isinstance(form_files, dict))):
                raise ValueError("multipart fields must be mappings and cannot accompany JSON")
            import uuid
            boundary = 'ef-' + uuid.uuid4().hex
            pieces = []
            for name, value in (form or {}).items():
                if not isinstance(name, str) or not name.isidentifier() or not isinstance(value, str):
                    raise ValueError("invalid multipart field")
                pieces.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode() + value.encode() + b'\r\n')
            for name, path in (form_files or {}).items():
                if not isinstance(name, str) or not name.isidentifier():
                    raise ValueError("invalid multipart file field")
                filename = os.path.basename(path)
                if any(ord(c) < 32 or ord(c) == 127 or c in ('\\', '"') for c in filename):
                    raise ValueError("invalid upload filename")
                with open(path, 'rb') as upload:
                    content = upload.read()
                pieces.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + content + b'\r\n')
            pieces.append(f'--{boundary}--\r\n'.encode())
            fd, upload_file = tempfile.mkstemp(prefix='ef-upload-')
            with os.fdopen(fd, 'wb') as upload:
                upload.write(b''.join(pieces))
            request_headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
        # Stage beside the destination so replacement is atomic even across volumes.
        staging_dir = os.path.dirname(os.path.abspath(dest)) if dest is not None else None
        fd, body_file = tempfile.mkstemp(prefix="ef-http-", suffix=".body", dir=staging_dir)
        os.close(fd)
        cmd = ["curl", "-sS", "-L", "--compressed", "--globoff",
               "--proto", "=http,https", "--proto-redir", "=http,https",
               "--max-time", str(timeout),
               "--connect-timeout", str(min(timeout, 15)),
               "-o", body_file, "-w", "%{http_code}"]
        for key, val in request_headers.items():
            cmd += ["-H", f"{key}: {val}"]
        if cookie_jar:
            cmd += ["-b", cookie_jar, "-c", cookie_jar]
        if payload is not None:
            cmd += ["-X", "POST", "-H", "Content-Type: application/json",
                    "--data-binary", encoded]
        if upload_file is not None:
            cmd += ['--data-binary', '@' + upload_file]
        if private_url or not follow_redirects:
            cmd.remove('-L')
        if private_url:
            if parsed.scheme != 'https':
                raise ValueError("private URLs require HTTPS")
            cmd += ['--config', '-']
        else:
            cmd.append(url)

        last = None
        for attempt in range(max(1, retries + 1)):
            if attempt:
                time.sleep(0.6 * attempt)  # linear backoff; these are small endpoints
            try:
                kwargs = {'input': 'url = ' + json.dumps(url, ensure_ascii=False) + '\n'} if private_url else {}
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      timeout=timeout + 10, **kwargs)
            except subprocess.TimeoutExpired:
                last = f"{_host(url)}: timed out after {timeout}s"
                continue
            except Exception as exc:  # noqa: BLE001 — degrade-not-die
                return None, f"{_host(url)}: curl could not run ({type(exc).__name__})"

            if proc.returncode != 0:
                # stderr can echo signed URLs or request credentials.
                last = f"{_host(url)}: curl exit {proc.returncode}"
                if proc.returncode in _TRANSIENT_EXITS:
                    continue
                return None, last

            status = (proc.stdout or "").strip()
            if len(status) != 3 or not status.isascii() or not status.isdigit() or not 100 <= int(status) <= 599:
                return None, f"{_host(url)}: missing or invalid HTTP status"
            if not status.startswith("2"):
                code = int(status)
                last = f"{_host(url)}: HTTP {code}"
                if code in _TRANSIENT_STATUS:
                    continue
                return None, last

            if dest is not None:
                try:
                    os.replace(body_file, dest)
                except OSError as exc:
                    return None, f"{_host(url)}: could not save response ({exc})"
                return dest, None
            try:
                with open(body_file, encoding="utf-8", errors="replace") as fh:
                    return fh.read(), None
            except OSError as exc:
                return None, f"{_host(url)}: could not read response ({exc})"

        return None, last or f"{_host(url)}: fetch failed"
    except Exception as exc:  # request setup must degrade just like network failures
        return None, f"{_host(url)}: request failed ({type(exc).__name__})"
    finally:
        if upload_file is not None:
            try:
                os.unlink(upload_file)
            except OSError:
                pass
        if body_file is not None:
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
    from finance import paths  # noqa: PLC0415 — keeps this module import-light
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
