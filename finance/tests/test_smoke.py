#!/usr/bin/env python3
"""Offline subprocess checks for the live-smoke harness itself."""
import contextlib
import io
import json
import os
import subprocess
import sys
import time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.mcp import smoke_test as smoke
from finance.tests.harness import check, run


@contextlib.contextmanager
def fake_server(body):
    real_popen = subprocess.Popen
    processes = []
    def start(*args, **kwargs):
        process = real_popen([sys.executable, '-u', '-c', body], **kwargs)
        processes.append(process)
        return process
    with mock.patch.object(smoke.subprocess, 'Popen', side_effect=start):
        try:
            yield processes
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=2)


SERVER = '''import sys,json,time
for line in sys.stdin:
    msg=json.loads(line)
    if 'id' not in msg: continue
    if msg['method'] != 'initialize': time.sleep(.3)
    print(json.dumps({'jsonrpc':'2.0','id':msg['id'],'result':{}}),flush=True)
'''


def test_rpc_deadline_covers_silent_server():
    with fake_server(SERVER):
        client = smoke.Client(sys.executable, 'personal')
        artifact_dir = client.artifacts.name
        check('smoke artifacts are isolated from the configured personal root', artifact_dir != os.environ.get('EVERYTHING_FINANCE_ARTIFACTS') and os.path.isdir(artifact_dir))
        started = time.monotonic()
        try:
            client._rpc('tools/list', {}, timeout=.05)
            check('silent server must time out', False)
        except TimeoutError:
            check('silent server must time out', True)
        check('timeout does not wait for a newline', time.monotonic()-started < .2)
        smoke.close(client)
        check('closed server is reaped', client.proc.poll() is not None)
        check('temporary smoke artifacts are removed', not os.path.exists(artifact_dir))


def test_failed_initialization_is_counted_and_reaped():
    script = "import sys,json,time; m=json.loads(sys.stdin.readline()); print(json.dumps({'id':m['id'],'error':{'message':'fixture'}}),flush=True); time.sleep(5)"
    with fake_server(script) as processes, contextlib.redirect_stdout(io.StringIO()):
        try:
            result = smoke.run_server('personal', sys.executable, False, {})
        except Exception:
            result = None
        recorded = result is not None and result[2] == 1
        reaped = processes[0].poll() is not None
    check('startup failure becomes a failed server result', recorded)
    check('startup failure cleans up the child', reaped)


def test_malformed_envelopes_cannot_pass_or_crash():
    malformed = [None, 12, [], {'ok':False,'data':{},'gaps':[]},
                 {'ok':'false','source':'fixture','fetched_at':'now','data':{},'gaps':[]},
                 {'ok':False,'source':'fixture','fetched_at':'now','data':[], 'gaps':['gap']}]
    for envelope in malformed:
        client = mock.Mock()
        client.tools.return_value = ['run_insurance_math']
        client.call.return_value = envelope
        client.errlog = []
        only_insurance = {'personal': [c for c in smoke.CASES['personal'] if c[0] == 'run_insurance_math']}
        with mock.patch.object(smoke,'Client',return_value=client), mock.patch.object(smoke,'close'), \
                mock.patch.dict(smoke.CASES, only_insurance), contextlib.redirect_stdout(io.StringIO()):
            try:
                result = smoke.run_server('personal',sys.executable,False,{})
            except Exception:
                result = None
        check('malformed envelope fails without aborting harness',result is not None and result[2]==1,envelope)


if __name__ == '__main__':
    run(globals())
