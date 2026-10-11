#!/usr/bin/env python3
"""Offline dependency bootstrap checks; never invokes a real installer."""
from pathlib import Path
import sys
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from finance import deps
from finance.tests.harness import check, run


def test_existing_dependency_does_not_install():
    with mock.patch.object(deps.subprocess, 'check_call') as install:
        check('existing module reused', deps.need('json').__name__ == 'json')
        check('existing module needs no installer', not install.called)


def test_broken_import_is_not_missing_distribution():
    for failure in [ImportError('binary ABI mismatch'), ModuleNotFoundError('transitive missing', name='other_library')]:
        with mock.patch('builtins.__import__', side_effect=failure), mock.patch.object(deps.subprocess, 'check_call') as install:
            try:
                deps.need('fixture_package')
            except ImportError as exc:
                check('original broken-package error preserved', exc is failure)
            else:
                check('broken-package error must propagate', False)
            check('broken package not blindly reinstalled', not install.called)


def test_missing_dependency_rechecks_under_lock_and_keeps_stdout_clean():
    missing = ModuleNotFoundError('missing', name='fixture_package')
    sentinel = object()
    with mock.patch.object(deps, '_import', side_effect=[missing, missing, sentinel]), mock.patch.object(deps.subprocess, 'check_call') as install:
        check('installed dependency imported', deps.need('fixture_package', 'fixture-distribution') is sentinel)
        args, kwargs = install.call_args
        check('installer uses running interpreter', args[0][:3] == [sys.executable, '-m', 'pip'])
        check('installer diagnostics go to stderr', kwargs.get('stdout') is sys.stderr)
        check('installer inherits lock if parent exits', len(kwargs.get('pass_fds', ())) == 1)
    with mock.patch.object(deps, '_import', side_effect=[missing, sentinel]), mock.patch.object(deps.subprocess, 'check_call') as install:
        check('waiter sees completed install', deps.need('fixture_package') is sentinel)
        check('waiter does not install again', not install.called)


def test_concurrent_processes_install_once():
    import os
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        script = r"""
import pathlib, sys, time
from finance import deps
root = pathlib.Path(sys.argv[1])
sys.prefix = str(root)
def fake_import(mod):
    if not (root / 'installed').exists():
        raise ModuleNotFoundError('missing', name=mod)
    return 'ready'
def fake_install(*args, **kwargs):
    with (root / 'installs').open('a') as stream:
        stream.write('install\n')
    time.sleep(0.15)
    (root / 'installed').write_text('ready')
deps._import = fake_import
deps.subprocess.check_call = fake_install
print(deps.need('fixture_package'))
"""
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]))
        processes = [subprocess.Popen([sys.executable, '-c', script, directory],
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
                     for _ in range(3)]
        results = [process.communicate(timeout=15) for process in processes]
        check('concurrent callers all complete', all(p.returncode == 0 for p in processes))
        check('one install across three processes', (Path(directory) / 'installs').read_text().splitlines() == ['install'])
        check('stdout contains only caller output', all(out == 'ready\n' for out, err in results))


if __name__ == '__main__':
    run(globals())
