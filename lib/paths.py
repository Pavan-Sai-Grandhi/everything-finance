#!/usr/bin/env python3
"""The one place artifact paths are decided.

Every skill script asks this module where to read and write instead of hardcoding
strings, so the layout (below) can never drift between skills — the same reason
`ta.py` and `strategy.py` are each a single engine.

    artifacts/                         root: $EVERYTHING_FINANCE_ARTIFACTS or ./artifacts
      stocks/<TICKER>/<date>/          entity-first: a stock's whole run-day together
        deep-analysis.md  deep-analysis/agents/*.md
        dcf.md  dcf.json  dcf-inputs.yml
        management.md  filings.md
      funds/<SCHEME>/<date>/           funds are entities too
        mf-research.md  mf-research.json
      <skill>/<date>.<ext>             date/singleton skills: skill-first
      <skill>/<date>/                  ...with work papers beside the report
      backtest/<spec>/<date>/
      state/                           durable, mutable, NOT dated
        strategies/  trades/  alerts/  watchlist.json
      cache/  tmp/                     disposable, safe to delete anytime

Naming convention everywhere: <owner-dir>/<key>/<date>.<ext>, key = ticker / scheme
/ spec for entity skills, the date itself for singletons.
"""
import os
import re
from datetime import date as _date_cls

# skill -> (entity kind, report filename) for the prior-run lookup. Only the
# entity-centric skills that build on their own history are listed.
_STOCK_ARTIFACT = {
    "deep-analysis": "deep-analysis.md",
    "dcf": "dcf.md",
    "dcf-valuation": "dcf.md",
    "management": "management.md",
    "management-quality": "management.md",
    "filings": "filings.md",
    "filings-watch": "filings.md",
}
_FUND_ARTIFACT = {
    "mf-research": "mf-research.md",
}


def root():
    """Artifacts root: $EVERYTHING_FINANCE_ARTIFACTS if set, else ./artifacts (cwd)."""
    return os.path.abspath(os.environ.get("EVERYTHING_FINANCE_ARTIFACTS", "artifacts"))


def _today():
    return _date_cls.today().isoformat()


def _day(date):
    """Normalise a date arg (None -> today, date object or 'YYYY-MM-DD' -> string)."""
    if date is None:
        return _today()
    if isinstance(date, _date_cls):
        return date.isoformat()
    return str(date)


def ticker_key(ticker):
    """NSE trading symbol, uppercased, no .NS suffix — matches the trade-idea rule."""
    return re.sub(r"\.NS$", "", str(ticker).strip().upper())


def scheme_key(scheme):
    """Filesystem-safe slug of a fund scheme name: lowercase, non-alnum -> '-'."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(scheme).strip().lower())).strip("-")


def _mkdir(path):
    os.makedirs(path, exist_ok=True)
    return path


def _mkparent(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


# --- dated historical output -------------------------------------------------

def stock_dir(ticker, date=None):
    """stocks/<TICKER>/<date>/ — a stock's whole run-day, created."""
    return _mkdir(os.path.join(root(), "stocks", ticker_key(ticker), _day(date)))


def fund_dir(scheme, date=None):
    """funds/<SCHEME>/<date>/ — a fund's run-day, created."""
    return _mkdir(os.path.join(root(), "funds", scheme_key(scheme), _day(date)))


def report_path(skill, date=None, ext="md"):
    """<skill>/<date>.<ext> for a singleton skill; parent created."""
    return _mkparent(os.path.join(root(), skill, f"{_day(date)}.{ext.lstrip('.')}"))


def report_dir(skill, date=None):
    """<skill>/<date>/ for a singleton skill that emits work papers; created."""
    return _mkdir(os.path.join(root(), skill, _day(date)))


def backtest_dir(spec, date=None):
    """backtest/<spec>/<date>/ — created."""
    return _mkdir(os.path.join(root(), "backtest", str(spec), _day(date)))


# --- durable, mutable, not dated ---------------------------------------------

def state_dir(name=None):
    """state/ or state/<name>/ (strategies, trades, alerts) — created."""
    parts = [root(), "state"] + ([name] if name else [])
    return _mkdir(os.path.join(*parts))


def alerts_dir():
    """state/alerts/ — created."""
    return state_dir("alerts")


def watchlist_path():
    """state/watchlist.json — parent (state/) created."""
    return _mkparent(os.path.join(state_dir(), "watchlist.json"))


# --- disposable --------------------------------------------------------------

def cache_dir(name=None):
    """cache/ or cache/<name>/ — created."""
    parts = [root(), "cache"] + ([name] if name else [])
    return _mkdir(os.path.join(*parts))


def tmp_dir(name=None):
    """tmp/ or tmp/<name>/ — created."""
    parts = [root(), "tmp"] + ([name] if name else [])
    return _mkdir(os.path.join(*parts))


# --- prior-run lookup --------------------------------------------------------

def latest_prior(skill, subject, before=None):
    """Newest earlier artifact for (skill, subject), or None.

    Lists the <date> dirs under the subject's entity folder, keeps those that hold
    the skill's report file, and returns the path to the newest one strictly before
    `before` (or before today). This is what powers "refer the earlier run" — no
    directories are created.
    """
    if skill in _STOCK_ARTIFACT:
        base = os.path.join(root(), "stocks", ticker_key(subject))
        fname = _STOCK_ARTIFACT[skill]
    elif skill in _FUND_ARTIFACT:
        base = os.path.join(root(), "funds", scheme_key(subject))
        fname = _FUND_ARTIFACT[skill]
    else:
        raise ValueError(f"no prior-run lookup defined for skill {skill!r}")

    cutoff = _day(before)
    if not os.path.isdir(base):
        return None
    candidates = []
    for day in os.listdir(base):
        if day >= cutoff:  # strictly earlier than the cutoff day
            continue
        report = os.path.join(base, day, fname)
        if os.path.isfile(report):
            candidates.append((day, report))
    if not candidates:
        return None
    return max(candidates)[1]
