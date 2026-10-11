#!/usr/bin/env python3
"""Resolve a usable MCP interpreter; serialize repair of the shared environment."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys

PROBE = 'from mcp.server.mcpserver import MCPServer'


def usable(python):
    try:
        return subprocess.run([str(python), '-c', PROBE], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def resolve(python, data):
    if usable(python):
        return str(python)
    data = Path(data)
    data.mkdir(parents=True, exist_ok=True)
    venv = data / 'venv'
    interpreter = venv / 'bin' / 'python'
    # The lock file is permanent: unlinking it could give a waiter a different inode.
    # Kernel ownership releases the lock even if bootstrap is interrupted or killed.
    with (data / '.mcp-bootstrap.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if usable(interpreter):
            return str(interpreter)
        print('[finance-mcp] preparing shared MCP environment', file=sys.stderr)
        subprocess.run([str(python), '-m', 'venv', '--system-site-packages', str(venv)],
                       check=True, stdout=sys.stderr)
        subprocess.run([str(interpreter), '-m', 'pip', 'install', '--quiet',
                        '--disable-pip-version-check', 'mcp>=2,<3'],
                       check=True, stdout=sys.stderr)
        if not usable(interpreter):
            raise RuntimeError('installed SDK does not provide the required MCPServer API')
        return str(interpreter)


if __name__ == '__main__':
    try:
        print(resolve(sys.argv[1], sys.argv[2]))
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'[finance-mcp] cannot prepare SDK: {exc}', file=sys.stderr)
        sys.exit(1)
