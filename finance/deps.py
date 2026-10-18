"""Lazy third-party imports, in one place.

The servers run in whichever interpreter the launcher resolved, so a missing package
self-heals rather than tracebacks. Separate from `ta.py` so a module needing only PyYAML
does not drag in pandas, numpy and the TA-Lib bootstrap.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import os
import stat
import subprocess
import sys
import tempfile
import threading

_THREAD_LOCK = threading.RLock()


@contextmanager
def installation_lock():
    """Serialize installers sharing a Python environment across threads/processes."""
    key = hashlib.sha256(os.path.realpath(sys.prefix).encode()).hexdigest()[:24]
    path = os.path.join(tempfile.gettempdir(), f"finance-deps-{os.getuid()}-{key}.lock")
    with _THREAD_LOCK:
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a") as lock:
            info = os.fstat(lock.fileno())
            if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
                raise RuntimeError("unsafe dependency lock file")
            fcntl.flock(lock, fcntl.LOCK_EX)
            # Keep the inode: deleting a lock can split ownership between waiters.
            yield lock.fileno()


def _import(mod):
    return __import__(mod)


def need(mod, pip_name=None):
    """Install only a missing top-level package; preserve broken-import errors."""
    try:
        return _import(mod)
    except ModuleNotFoundError as exc:
        if exc.name != mod:
            raise
    with installation_lock() as lock_fd:
        try:
            return _import(mod)
        except ModuleNotFoundError as exc:
            if exc.name != mod:
                raise
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                               "--break-system-packages", pip_name or mod],
                              stdout=sys.stderr, pass_fds=(lock_fd,))
        return _import(mod)


def load_yaml(path):
    """Parse a YAML file, installing PyYAML if it is missing."""
    yaml = need("yaml", "pyyaml")
    with open(path) as fh:
        return yaml.safe_load(fh)
