#!/usr/bin/env python3
"""Lazy third-party imports, in one place.

Skill scripts are run directly by a user, not installed, so a missing dependency has to
self-heal rather than traceback. Kept separate from `ta.py` so a script needing only PyYAML
does not drag in pandas, numpy and the TA-Lib native bootstrap.
"""
import subprocess
import sys


def need(mod, pip_name=None):
    """Import `mod`, pip-installing it (PEP 668 override) on first miss."""
    try:
        return __import__(mod)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet",
                               "--break-system-packages", pip_name or mod])
        return __import__(mod)


def load_yaml(path):
    """Parse a YAML file, installing PyYAML if it is missing."""
    yaml = need("yaml", "pyyaml")
    with open(path) as fh:
        return yaml.safe_load(fh)
