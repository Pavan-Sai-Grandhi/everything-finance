"""The one place artifact paths are decided, so the layout cannot drift between producers.

    artifacts/                         root: $EVERYTHING_FINANCE_ARTIFACTS or ./artifacts
      stocks/<TICKER>/<date>/          a stock's run-day: dcf.md, dcf-inputs.yml,
                                       management.md, filings.md, the leg reports
        runs/<run-id>/                 an archived deep-analysis bundle: report.json,
                                       report.html, run.json, agents/*.md
      funds/<SCHEME>/<date>/           mf-analysis.md and the deck
      <skill>/<date>.<ext>             singleton skills
      <skill>/<date>/                  their work papers
      backtest/<spec>/<date>/
      state/                           durable and mutable: strategies/ trades/ alerts/
                                       sectors/ watchlist.json
      cache/  tmp/                     disposable
"""
import os
import hashlib
import json
import re
from datetime import date as _date_cls

from finance.spine import envelope as _envelope

_SOURCE = "finance.paths"
_RUN_ID = re.compile(r"[0-9]{20}-[a-f0-9]{32}")

# skill -> (its file in a stock run-day folder, the bundle modes that carry it, its path in a bundle)
_STOCK_PRIOR = {
    "deep-analysis": (None, ("standard", "deep"), "report.json"),
    "fundamentals": (None, ("fundamentals",), "report.json"),
    "dcf": ("dcf.md", ("standard", "deep", "fundamentals"), "agents/dcf.md"),
    "management": ("management.md", ("standard", "deep", "fundamentals"), "agents/management.md"),
    "filings": ("filings.md", (), None),
}
_FUND_PRIOR = {"mf-analysis": "mf-analysis.md"}


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


def state_dir(name=None, *, create=True):
    """state/ or state/<name>; read-only callers use create=False without making dirs."""
    parts = [root(), "state"] + ([_namespace(name)] if name is not None else [])
    path = os.path.join(*parts)
    return _mkdir(path) if create else _contained(path)


def alerts_dir():
    """state/alerts/ — created."""
    return state_dir("alerts")


def merchant_map_path():
    """budget/merchant-map.json: the durable merchant→category map, kept beside the monthly
    budget reports it builds up."""
    return _mkparent(os.path.join(root(), "budget", "merchant-map.json"))


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
    if not _RUN_ID.fullmatch(str(run_id)):
        raise ValueError("invalid report run id")
    return _contained(os.path.join(report_staging_dir(session, create=True), run_id))


def report_archive(ticker, day, run_id):
    """Immutable report bundle path; all publication paths are owned here."""
    if not _RUN_ID.fullmatch(str(run_id)):
        raise ValueError("invalid report run id")
    return _mkparent(os.path.join(stock_dir(ticker, day), "runs", run_id))


def _bundle_candidates(base, day, ticker, modes, inner):
    runs = _contained(os.path.join(base, day, "runs"))
    if not modes or not os.path.isdir(runs):
        return
    for run_id in os.listdir(runs):
        if not _RUN_ID.fullmatch(run_id):
            continue
        bundle = _contained(os.path.join(runs, run_id))
        try:
            with open(_contained(os.path.join(bundle, "run.json"))) as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            continue
        if (not isinstance(meta, dict) or meta.get("mode") not in modes
                or meta.get("ticker") != ticker or meta.get("date") != day
                or meta.get("run_id") != run_id):
            continue
        candidate = _contained(os.path.join(bundle, inner))
        if os.path.isfile(candidate) and os.path.isfile(_contained(os.path.join(bundle, "report.html"))):
            yield day, run_id, candidate


def latest_prior(skill, subject, before=None):
    """The newest artifact for (skill, subject) strictly before `before` (default today), or
    None. Reads run-day files and archived bundles; creates nothing."""
    if skill in _STOCK_PRIOR:
        base = os.path.join(root(), "stocks", ticker_key(subject))
        fname, modes, inner = _STOCK_PRIOR[skill]
    elif skill in _FUND_PRIOR:
        base = os.path.join(root(), "funds", scheme_key(subject))
        fname, modes, inner = _FUND_PRIOR[skill], (), None
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
        if day >= cutoff:
            continue
        if fname:
            report = _contained(os.path.join(base, day, fname))
            if os.path.isfile(report):
                candidates.append((day, "", report))
        if skill in _STOCK_PRIOR:
            candidates.extend(_bundle_candidates(base, day, ticker_key(subject), modes, inner))
    return max(candidates)[-1] if candidates else None


def prior_run(skill, subject, before=None):
    """`latest_prior` in the envelope `get_prior_run` returns. No earlier run is `ok` with a
    null path: a first run is the normal case, not a gap."""
    data = {"skill": skill, "subject": subject, "before": None,
            "path": None, "date": None}
    if skill not in _STOCK_PRIOR and skill not in _FUND_PRIOR:
        valid = ", ".join(sorted(set(_STOCK_PRIOR) | set(_FUND_PRIOR)))
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
