#!/usr/bin/env python3
"""Offline shell entry-point tests using only temporary credentials and state."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from finance.tests.harness import check, run
ROOT = Path(__file__).resolve().parents[2]


def test_secrets_loader_preserves_shell_state_and_precedence():
    with tempfile.TemporaryDirectory() as work:
        root, data = Path(work)/'plugin', Path(work)/'data'
        root.mkdir(); data.mkdir()
        (root/'.env').write_text('EF_FIXTURE_VALUE=plugin\n')
        (data/'.env').write_text('EF_FIXTURE_VALUE=data\n')
        script = '. "$1"; set -a; ef_load_secrets "$2" "$3"; printf "%s:%s" "$EF_FIXTURE_VALUE" "$-"'
        result = subprocess.run(['bash','-c',script,'fixture',str(ROOT/'bin/load-env.sh'),str(root),str(data)],capture_output=True,text=True)
        value, flags = result.stdout.split(':')
        check('plugin credentials take precedence',value=='plugin')
        check('loading secrets preserves caller allexport', 'a' in flags)
        check('credential values stay out of diagnostics','plugin\n' not in result.stderr)


def test_seeded_template_is_private_and_existing_file_survives():
    with tempfile.TemporaryDirectory() as work:
        root, data = Path(work)/'plugin', Path(work)/'data'
        root.mkdir()
        (root/'.env.example').write_text('EF_FIXTURE_VALUE=\n')
        script = 'umask 022; . "$1"; ef_load_secrets "$2" "$3"'
        args = ['bash','-c',script,'fixture',str(ROOT/'bin/load-env.sh'),str(root),str(data)]
        first = subprocess.run(args,capture_output=True,text=True)
        check('missing credentials seed successfully',first.returncode==0 and (data/'.env').exists())
        check('seeded credentials are owner-only',(data/'.env').stat().st_mode & 0o777 == 0o600)
        (data/'.env').write_text('EF_FIXTURE_VALUE=existing\n')
        second = subprocess.run(args,capture_output=True,text=True)
        check('existing credentials are preserved',second.returncode==0 and (data/'.env').read_text()=='EF_FIXTURE_VALUE=existing\n')


def test_shared_bootstrap_installs_once_for_concurrent_starts():
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        fake = work / 'fake-python'
        fake.write_text('#!' + sys.executable + '\n' + r"""
import os,pathlib,shutil,sys,time
here=pathlib.Path(sys.argv[0]).parent
if sys.argv[1]=='-c':
    sys.exit(0 if (here/'ready').exists() else 1)
if sys.argv[2]=='venv':
    target=pathlib.Path(sys.argv[-1])/'bin'
    target.mkdir(parents=True,exist_ok=True)
    shutil.copy2(sys.argv[0],target/'python')
elif sys.argv[2]=='pip':
    with open(here/'installs','a') as f: f.write('install\n')
    time.sleep(.2)
    if (here/'fail').exists(): sys.exit(1)
    (here/'ready').touch()
""")
        fake.chmod(0o755)
        data = work / 'data'
        args = [sys.executable,str(ROOT/'bin/ensure-mcp.py'),str(fake),str(data)]
        children = [subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(3)]
        try:
            results = [child.communicate(timeout=10) for child in children]
            check('concurrent startup resolves all interpreters',all(child.returncode==0 for child in children),results)
            check('bootstrap installs only once',(data/'venv/bin/installs').read_text().splitlines()==['install'])
            check('stdout contains only the selected interpreter',all(out.strip()==str(data/'venv/bin/python') for out,err in results),results)
            (data/'venv/bin/ready').unlink()
            (data/'venv/bin/fail').touch()
            failed = subprocess.run(args,capture_output=True,text=True,timeout=10)
            check('failed repair cannot return an interpreter',failed.returncode!=0 and not failed.stdout)
            (data/'venv/bin/fail').unlink()
            recovered = subprocess.run(args,capture_output=True,text=True,timeout=10)
            check('failed repair releases the lock for a later retry',recovered.returncode==0 and recovered.stdout.strip()==str(data/'venv/bin/python'))
        finally:
            for child in children:
                if child.poll() is None: child.kill()
                child.wait()


def test_broker_cold_starts_share_one_login():
    """Offline: a fake npx stands in for both the login (`mcp-remote-client`) and the proxy."""
    import hashlib
    import time
    url = 'https://fixture.invalid/mcp'
    key = hashlib.md5(url.encode()).hexdigest()
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        store = work / 'auth'
        (store / 'mcp-remote-0.1.49').mkdir(parents=True)
        (store / 'mcp-remote-0.1.49' / f'{key}_client_info.json').write_text('{"client_id": "c"}')
        token = store / 'mcp-remote-0.1.49' / f'{key}_tokens.json'
        logins = store / 'logins'
        fake = work / 'npx'
        fake.write_text('#!' + sys.executable + '\n' + r"""
import json,os,pathlib,sys,time
store=pathlib.Path(os.environ['MCP_REMOTE_CONFIG_DIR'])
if 'mcp-remote-client' in sys.argv:
    with open(store/'logins','a') as f: f.write('login\n')
    time.sleep(float(os.environ.get('EF_FIXTURE_LOGIN_DELAY', '.5')))
    for p in (store/'mcp-remote-0.1.49').glob('*_client_info.json'):
        (p.parent/p.name.replace('client_info','tokens')).write_text(json.dumps(
            {'access_token':'a','expires_at':(time.time()+3600)*1000}))
    sys.exit(0)
print('ready',flush=True)
sys.stdin.read()
""")
        fake.chmod(0o755)
        env = {**os.environ, 'PATH': str(work) + os.pathsep + os.environ['PATH'],
               'MCP_REMOTE_CONFIG_DIR': str(store), 'EF_BRIDGE_LOGIN_WAIT': '10'}
        args = [sys.executable, str(ROOT / 'bin/broker-login.py'), url, '0.1.49']

        def start(extra=None):
            return subprocess.Popen(args, env={**env, **(extra or {})}, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        children = [start() for _ in range(3)]
        try:
            results = [child.communicate(timeout=20) for child in children]
            check('cold broker starts all connect', all(c.returncode == 0 for c in children), results)
            check('one login serves every cold start', logins.read_text().splitlines() == ['login'])
            check('coordination does not pollute protocol stdout',
                  all(out == 'ready\n' for out, _ in results), results)

            token.unlink()
            logins.unlink()
            starter = start({'EF_FIXTURE_LOGIN_DELAY': '2', 'EF_BRIDGE_LOGIN_WAIT': '0.5'})
            out, err = starter.communicate(timeout=10)
            check('a session that gives up says how to finish the login',
                  starter.returncode == 1 and 'reconnect' in err, (out, err))
            deadline = time.monotonic() + 10
            while not token.exists() and time.monotonic() < deadline:
                time.sleep(.1)
            check('the login finishes after the session that opened it is gone', token.exists())
            later = start()
            out, err = later.communicate(timeout=10)
            check('the next session connects with no second login',
                  later.returncode == 0 and logins.read_text().splitlines() == ['login'], (out, err))
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=5)


if __name__ == '__main__':
    run(globals())
