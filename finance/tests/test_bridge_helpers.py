#!/usr/bin/env python3
"""Offline failure-path tests for the local broker integration harness."""
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.error
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from finance.tests import bridge_sessions as helpers
from finance.tests.harness import check, run


def test_broker_start_failure_cleans_process_and_preserves_existing_directory():
    with tempfile.TemporaryDirectory() as root:
        existing = Path(root) / 'existing'
        existing.mkdir()
        (existing / 'evidence').write_text('preserve')
        with patch.object(helpers.subprocess, 'Popen') as spawn:
            try:
                helpers.Broker(str(existing)).__enter__()
            except FileExistsError:
                pass
            check('caller-owned directory is never deleted', (existing / 'evidence').read_text() == 'preserve' and not spawn.called)
        broker = helpers.Broker(str(Path(root) / 'failed'))
        proc = Mock()
        proc.poll.return_value = None
        proc.wait.side_effect = [subprocess.TimeoutExpired('stub', 5), 0]
        with patch.object(helpers.subprocess, 'Popen', return_value=proc), patch.object(helpers.time, 'sleep'):
            try:
                broker.__enter__()
                failed = False
            except RuntimeError:
                failed = True
        check('startup timeout is explicit', failed)
        check('startup timeout terminates and reaps stubborn broker', proc.terminate.called and proc.kill.called and proc.wait.call_count == 2)
        check('startup timeout closes diagnostic stream', broker._log.closed)
        broker = helpers.Broker(str(Path(root) / 'spawn-error'))
        with patch.object(helpers.subprocess, 'Popen', side_effect=OSError('spawn failed')):
            try:
                broker.__enter__()
            except OSError:
                pass
        check('spawn error also closes diagnostic stream', broker._log.closed)


def test_browser_is_loopback_only_and_does_not_follow_redirects():
    bot = helpers.BrowserBot('/unused')
    for url in ('https://example.com/auth', 'http://example.com:80/auth', 'file:///tmp/x',
                'http://user@localhost:8000/auth', 'http://localhost/auth', 'http://localhost:bad/', None):
        with patch.object(helpers.urllib.request, 'build_opener') as create:
            bot._login(url)
            check('nonlocal/malformed browser input is never opened', not create.called)
    for url in ('http://127.0.0.1:8000/authorize', 'http://localhost:8000/callback', 'http://[::1]:8000/callback'):
        check('explicit loopback URL accepted', helpers._local_url(url))
    opener = Mock()
    err = urllib.error.HTTPError('http://localhost:8000/authorize', 302, 'redirect',
                                 {'Location': 'https://external.invalid/callback'}, io.BytesIO())
    opener.open.side_effect = err
    with patch.object(helpers.urllib.request, 'build_opener', return_value=opener):
        bot._login('http://localhost:8000/authorize')
    check('external callback redirect is never fetched', opener.open.call_count == 1)
    first = urllib.error.HTTPError('http://localhost:8000/authorize', 302, 'redirect',
                                   {'Location': 'http://127.0.0.1:8001/callback'}, io.BytesIO())
    second = urllib.error.HTTPError('http://127.0.0.1:8001/callback', 302, 'redirect',
                                    {'Location': 'https://external.invalid'}, io.BytesIO())
    opener.open.reset_mock()
    opener.open.side_effect = [first, second]
    with patch.object(helpers.urllib.request, 'build_opener', return_value=opener):
        bot._login('http://localhost:8000/authorize')
    check('callback redirects cannot escape via default opener', opener.open.call_count == 2)


def test_session_response_is_consumed_and_unstarted_stop_is_safe():
    with tempfile.TemporaryDirectory() as root:
        session = helpers.Session('fixture', '/unused', 'http://localhost:8000', root)
        session.stop()
        session._responses[7] = {'id': 7, 'result': {}}
        check('completed RPC response is consumed', session.wait_for(7)['id'] == 7 and not session._responses)
        session.stderr_lines.extend(str(i) for i in range(3000))
        check('stderr diagnostic history is bounded', len(session.stderr_lines) == 2000)


def test_concurrent_stub_registrations_have_unique_identity():
    import importlib.util
    from concurrent.futures import ThreadPoolExecutor
    with tempfile.TemporaryDirectory() as root:
        spec = importlib.util.spec_from_file_location('bridge_fixture', helpers.STUB_BROKER)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {'STUB_STATE_DIR': root, 'STUB_PIN_FIRST_REDIRECT': '0'}):
            spec.loader.exec_module(module)
        def register(_):
            handler = object.__new__(module.Handler)
            handler._body = lambda: b'{"redirect_uris":["http://localhost:8000/callback"]}'
            handler._json = lambda status, body: body
            return handler._register()['client_id']
        with ThreadPoolExecutor(max_workers=8) as pool:
            identities = list(pool.map(register, range(40)))
        check('concurrent fixture registrations retain unique clients', len(set(identities)) == 40 and len(module.clients) == 40)


if __name__ == '__main__':
    run(globals())
