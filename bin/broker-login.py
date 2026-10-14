#!/usr/bin/env python3
"""Coordinate first login without stealing claims or killing unrelated bridges."""
import fcntl
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def run(url, version, store, args):
    key = hashlib.md5(url.encode()).hexdigest()  # mcp-remote's persisted URL key
    token = Path(store) / f'mcp-remote-{version}' / f'{key}_tokens.json'
    command = ['npx', '-y', f'mcp-remote@{version}', url, *args]
    # Never remove this inode: a waiter may already have it open.
    with (Path(store) / f'.first-login-{key}.lock').open('a') as lock:
        while not token.is_file():
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(.2)
        if token.is_file():
            # A saved token needs no callback ownership. Let the pinned SDK refresh it.
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.execvp(command[0], command)
        # Keep ownership in the bridge too: killing this supervisor must not let
        # a competing login start while its child still owns the callback.
        child = subprocess.Popen(command, start_new_session=True, pass_fds=(lock.fileno(),))
        def forward(signum, _frame):
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass
            raise SystemExit(128 + signum)
        signal.signal(signal.SIGTERM, forward)
        signal.signal(signal.SIGINT, forward)
        try:
            # A slow login keeps ownership; waiting longer never lets a second login start.
            while child.poll() is None and not token.is_file():
                time.sleep(.2)
            fcntl.flock(lock, fcntl.LOCK_UN)
            return child.wait()
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()


if __name__ == '__main__':
    try:
        sys.exit(run(sys.argv[1], sys.argv[2], os.environ['MCP_REMOTE_CONFIG_DIR'], sys.argv[3:]))
    except (OSError, KeyError) as exc:
        print(f'[mcp-bridge] cannot start broker bridge: {exc}', file=sys.stderr)
        sys.exit(1)
