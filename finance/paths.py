#!/usr/bin/env python3
"""The one place artifact paths are decided.

Every skill script asks this module where to read and write instead of hardcoding
strings, so the layout (below) can never drift between skills — the same reason
`ta.py` and `strategy.py` are each a single engine.

    artifacts/                         root: $EVERYTHING_FINANCE_ARTIFACTS or ./artifacts
      stocks/<TICKER>/<date>/          entity-first: a stock's whole run-day together
        deep-analysis.html  deep-analysis.report.json  deep-analysis/agents/*.md
        fundamental-analysis.html  fundamental-analysis.report.json  fundamental-analysis/agents/*.md
        dcf.md  dcf.json  dcf-inputs.yml
        management.md  filings.md
      funds/<SCHEME>/<date>/           funds are entities too
        mf-analysis.md  mf-analysis.json
      <skill>/<date>.<ext>             date/singleton skills: skill-first
      <skill>/<date>/                  ...with work papers beside the report
      backtest/<spec>/<date>/
      state/                           durable, mutable, NOT dated
        strategies/  trades/  alerts/  sectors/  watchlist.json
      cache/  tmp/                     disposable, safe to delete anytime

Naming convention everywhere: <owner-dir>/<key>/<date>.<ext>, key = ticker / scheme
/ spec for entity skills, the date itself for singletons.
"""
import os
import hashlib
import json
import re
from datetime import date as _date_cls

from finance.spine import envelope as _envelope

_SOURCE = "finance.paths"

# skill -> report filename for the prior-run lookup. Only the entity-centric skills
# that build on their own history are listed.
_STOCK_ARTIFACT = {
    # deep-analysis emits no markdown — the deck (report.html) is the deliverable and the
    # report.json is its render input and the readable prior-run artifact. The JSON, not the
    # HTML, is what get_prior_run resolves to: it carries every figure and the prose in a form
    # a later run can read to build on.
    "deep-analysis": "deep-analysis.report.json",
    # deep-analysis's fundamentals mode: its own file, so a fundamentals run and a full
    # run on the same day cannot overwrite each other and each builds on its own history.
    "fundamentals": "fundamental-analysis.report.json",
    "dcf": "dcf.md",
    "management": "management.md",
    "filings": "filings.md",
}
_FUND_ARTIFACT = {
    "mf-analysis": "mf-analysis.md",
}


def root():
    """Artifacts root: $EVERYTHING_FINANCE_ARTIFACTS if set, else ./artifacts (cwd)."""
    return os.path.abspath(os.environ.get("EVERYTHING_FINANCE_ARTIFACTS", "artifacts"))


def _today():
    return _date_cls.today().isoformat()


def _day(date, allow_month=False):
    """A validated ISO day; singleton budget reports also accept an ISO month."""
    text = _today() if date is None else str(date)
    if allow_month and re.fullmatch(r"\d{4}-\d{2}", text):
        _date_cls.fromisoformat(text + "-01")
        return text
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError("artifact date must be YYYY-MM-DD")
    return _date_cls.fromisoformat(text).isoformat()


def _component(value):
    """An entity name is one nonempty path component, never a traversal."""
    text = str(value).strip() if value is not None else ""
    if not text or text in (".", "..") or any(c in text for c in ("/", "\\", "\0")):
        raise ValueError("artifact name must be a nonempty path component")
    return text


def _namespace(value):
    """Internal cache/state namespaces may nest, but cannot escape their tier."""
    return os.path.join(*[_component(part) for part in str(value).split("/")])


def _contained(path):
    """Also refuse an existing symlink that redirects storage outside the root."""
    base = os.path.realpath(root())
    if os.path.commonpath((base, os.path.realpath(path))) != base:
        raise ValueError("artifact path escapes the configured root")
    return path


def ticker_key(ticker):
    """NSE trading symbol, uppercased, no .NS suffix — matches the trade-idea rule."""
    return _component(re.sub(r"\.NS$", "", str(ticker).strip().upper()))


def scheme_key(scheme):
    """Filesystem-safe slug of a fund scheme name: lowercase, non-alnum -> '-'."""
    return _component(re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(scheme).strip().lower())).strip("-"))


def sector_key(sector):
    """Filesystem-safe slug of a sector name: lowercase, non-alnum -> '-'."""
    return scheme_key(sector)


def _mkdir(path):
    _contained(path)
    os.makedirs(path, exist_ok=True)
    return path


def _mkparent(path):
    _contained(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def stock_dir(ticker, date=None):
    """stocks/<TICKER>/<date>/ — a stock's whole run-day, created."""
    return _mkdir(os.path.join(root(), "stocks", ticker_key(ticker), _day(date)))


def fund_dir(scheme, date=None):
    """funds/<SCHEME>/<date>/ — a fund's run-day, created."""
    return _mkdir(os.path.join(root(), "funds", scheme_key(scheme), _day(date)))


def report_path(skill, date=None, ext="md"):
    """<skill>/<date>.<ext> for a singleton skill; parent created."""
    return _mkparent(os.path.join(root(), _component(skill), f"{_day(date, allow_month=True)}.{_component(ext.lstrip('.'))}"))


def report_dir(skill, date=None):
    """<skill>/<date>/ for a singleton skill that emits work papers; created."""
    return _mkdir(os.path.join(root(), _component(skill), _day(date)))


def backtest_dir(spec, date=None):
    """backtest/<spec>/<date>/ — created."""
    return _mkdir(os.path.join(root(), "backtest", _component(spec), _day(date)))


def insurance_report_path(policy_type, date=None, ext="md"):
    """insurance/<type>/<date>.<ext> — insurance-advisor's per-type report; parent created.

    ``policy_type`` is one of term / health / vehicle (slugged). Advise mode writes here;
    Audit and Ask (not per-type) use ``report_path("insurance")``."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(policy_type).strip().lower()).strip("-")
    return _mkparent(os.path.join(root(), "insurance", _component(slug), f"{_day(date)}.{_component(ext.lstrip('.'))}"))


def state_dir(name=None, *, create=True):
    """state/ or state/<name>; read-only callers use create=False without making dirs."""
    parts = [root(), "state"] + ([_namespace(name)] if name is not None else [])
    path = os.path.join(*parts)
    return _mkdir(path) if create else _contained(path)


def alerts_dir():
    """state/alerts/ — created."""
    return state_dir("alerts")


def watchlist_path():
    """state/watchlist.json — parent (state/) created."""
    return _mkparent(os.path.join(state_dir(), "watchlist.json"))


def merchant_map_path():
    """budget/merchant-map.json — budget-tracker's durable merchant→category map.

    Durable state (not dated), but co-located with the dated budget artifacts under
    budget/ rather than state/ so a month's whole trail — the <YYYY-MM>.html reports
    and the map they build up — lives in one folder. Loaded at the start of every
    run and rewritten when the user corrects a categorization."""
    return _mkparent(os.path.join(root(), "budget", "merchant-map.json"))


def sector_cache_path(sector):
    """state/sectors/<slug>.md — the shared, monthly-refreshed sector read.

    Durable state (not dated): one current body per sector, overwritten on refresh,
    read by deep-analysis and written by both sector-analysis and deep-analysis. The
    dated trail still lives under sector-analysis/<date>/."""
    return _mkparent(os.path.join(state_dir("sectors"), f"{sector_key(sector)}.md"))


def sector_cache_age_days(sector, today=None):
    """Age in days of the cached sector read, or None if missing/unreadable.

    Reads the `generated: YYYY-MM-DD` frontmatter line written by the producer. A
    missing file or undated cache returns None — the caller treats that as stale and
    refreshes. Pure date math, no yaml dependency."""
    p = os.path.join(state_dir("sectors"), f"{sector_key(sector)}.md")
    if not os.path.isfile(p):
        return None
    try:
        with open(_contained(p)) as fh:
            match = re.search(r"^\s*generated:\s*(\d{4}-\d{2}-\d{2})", fh.read(), re.M)
        if not match:
            return None
        ref = _date_cls.fromisoformat(_day(today))
        age = (ref - _date_cls.fromisoformat(match.group(1))).days
        return age if age >= 0 else None
    except (OSError, ValueError):
        return None


def cache_dir(name=None):
    """cache/ or cache/<name>/ — created."""
    parts = [root(), "cache"] + ([_namespace(name)] if name is not None else [])
    return _mkdir(os.path.join(*parts))


def tmp_dir(name=None):
    """tmp/ or tmp/<name>/ — created."""
    parts = [root(), "tmp"] + ([_namespace(name)] if name is not None else [])
    return _mkdir(os.path.join(*parts))


def report_staging_dir(session, *, create=False):
    """Opaque session namespace; read-only hooks do not create staging directories."""
    if not isinstance(session, str) or not session.strip():
        raise ValueError("a nonempty session id is required")
    key = hashlib.sha256(session.encode()).hexdigest()
    directory = os.path.join(root(), "tmp", "report-staging", key)
    return _mkdir(directory) if create else _contained(directory)


def report_stage(session, run_id):
    """A run-specific path; creates its parent only."""
    if not re.fullmatch(r"[0-9]{20}-[a-f0-9]{32}", str(run_id)):
        raise ValueError("invalid report run id")
    return _contained(os.path.join(report_staging_dir(session, create=True), run_id))


def report_archive(ticker, day, run_id):
    """Immutable report bundle path; all publication paths are owned here."""
    if not re.fullmatch(r"[0-9]{20}-[a-f0-9]{32}", str(run_id)):
        raise ValueError("invalid report run id")
    return _mkparent(os.path.join(stock_dir(ticker, day), "runs", run_id))


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

    _contained(base)
    cutoff = _day(before)
    if not os.path.isdir(base):
        return None
    candidates = []
    for day in os.listdir(base):
        try:
            _day(day)
        except ValueError:
            continue
        if day >= cutoff:  # strictly earlier than the cutoff day
            continue
        report = _contained(os.path.join(base, day, fname))
        if os.path.isfile(report):
            candidates.append((day, "", report))
        # New immutable report bundles coexist with the legacy run-day files.
        if skill in ("deep-analysis", "fundamentals", "dcf", "management"):
            runs = _contained(os.path.join(base, day, "runs"))
            if not os.path.isdir(runs):
                continue
            for run_id in os.listdir(runs):
                if not re.fullmatch(r"[0-9]{20}-[a-f0-9]{32}", run_id):
                    continue
                bundle = _contained(os.path.join(runs, run_id))
                try:
                    with open(_contained(os.path.join(bundle, "run.json"))) as fh:
                        meta = json.load(fh)
                    mode = meta.get("mode") if isinstance(meta, dict) else None
                    expected_modes = (("fundamentals",) if skill == "fundamentals" else
                                      ("standard", "deep") if skill == "deep-analysis" else
                                      ("standard", "deep", "fundamentals"))
                    if (mode not in expected_modes or meta.get("ticker") != ticker_key(subject)
                            or meta.get("date") != day or meta.get("run_id") != run_id):
                        continue
                    candidate = _contained(os.path.join(bundle, "report.json") if skill in ("deep-analysis", "fundamentals")
                                           else os.path.join(bundle, "agents", fname))
                    if os.path.isfile(candidate) and os.path.isfile(_contained(os.path.join(bundle, "report.html"))):
                        candidates.append((day, run_id, candidate))
                except (OSError, ValueError, TypeError):
                    continue
    if not candidates:
        return None
    return max(candidates)[-1]


def prior_run(skill, subject, before=None):
    """`latest_prior` in the shared envelope — the surface `get_prior_run` exposes.

    Exists because the skills that open on their prior run (`valuation-analysis`,
    `management-analysis`, `filings-watch`) carry no Bash and so cannot call a Python
    function; a tool is the only way they can ask this module anything.

    `data.path` is None and `ok` is true when there is no earlier run: a first run is the
    normal case, not a degradation. An unresolvable `skill` is the one gap, and it names
    the keys that do resolve.
    """
    data = {"skill": skill, "subject": subject, "before": None,
            "path": None, "date": None}
    if skill not in _STOCK_ARTIFACT and skill not in _FUND_ARTIFACT:
        valid = ", ".join(sorted(set(_STOCK_ARTIFACT) | set(_FUND_ARTIFACT)))
        return _envelope(False, _SOURCE, data,
                         [f"no prior-run lookup defined for skill {skill!r} — "
                          f"valid keys: {valid}"])
    try:
        data["before"] = _day(before)
        path = latest_prior(skill, subject, before)
    except (OSError, ValueError) as exc:
        return _envelope(False, _SOURCE, data, [str(exc)])
    if path:
        data["path"] = path
        data["date"] = os.path.relpath(path, root()).split(os.sep)[2]
    return _envelope(True, _SOURCE, data, [])
