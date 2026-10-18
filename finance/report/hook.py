"""The plugin's hook entry point: `python -m finance.report.hook <session|subagent|stop>`.

session   SessionStart: the India date, the session id report publication uses, and RULES.md.
subagent  SubagentStart: RULES.md as additionalContext for the plugin's own agents.
stop      Stop: archive this session's ready report bundles and deliver any the user asked for.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from finance import paths
from finance.report import publication
from finance.report.telegram import deliver_report as deliver

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "RULES.md"


def _rules():
    return (f"everything-finance plugin root: {ROOT} (paths such as `methods/…` and "
            f"`finance/report/fixtures/…` are relative to it).\n\n" + RULES.read_text(encoding="utf-8"))


def _plugin_agents():
    return {p.stem for p in (ROOT / "agents").glob("*.md")}


def session_context(payload):
    session = payload.get("session_id") if isinstance(payload, dict) else None
    today = datetime.now(ZoneInfo("Asia/Kolkata"))
    lines = [f"everything-finance: India date {today:%Y-%m-%d}; regular weekday hours "
             "09:15–15:30 IST, subject to exchange holidays. This is not a live market-status check."]
    if isinstance(session, str) and session.strip():
        lines.append("Report publication session_id (literal data): " + json.dumps(session))
    return "\n".join(lines) + "\n\n" + _rules()


def subagent_context(payload):
    """RULES.md for an everything-finance agent; nothing for anyone else's."""
    agent = payload.get("agent_type") if isinstance(payload, dict) else None
    if not isinstance(agent, str) or agent.rsplit(":", 1)[-1] not in _plugin_agents():
        return None
    return json.dumps({"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                              "additionalContext": _rules()}})


def stop(payload):
    if not isinstance(payload, dict):
        raise ValueError("hook payload must be a JSON object")
    session, cwd = payload.get("session_id"), payload.get("cwd")
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or not os.path.isdir(cwd):
        raise ValueError("hook requires an existing absolute session cwd")
    if not isinstance(session, str) or not session.strip():
        raise ValueError("hook requires session_id; staging is scanned per session")
    previous = os.getcwd()
    results, gaps = [], []
    try:
        os.chdir(cwd)
        staging = Path(paths.report_staging_dir(session))
        if not staging.is_dir():
            return results, gaps
        for directory in sorted(staging.iterdir()):
            if not directory.is_dir() or not (directory / "ready").is_file():
                continue
            try:
                result = publication.publish(session, directory.name)
                results.append(result)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                gaps.append(f"Could not archive report {directory.name}: {type(exc).__name__}; staging retained")
                continue
            try:
                gap = deliver(result)
                if gap:
                    gaps.append(gap)
            except (OSError, ValueError, TypeError):
                gaps.append("Telegram delivery unavailable; report remains archived")
    finally:
        os.chdir(previous)
    return results, gaps


def main():
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        payload = json.load(sys.stdin)
        if event == "session":
            print(session_context(payload))
        elif event == "subagent":
            output = subagent_context(payload)
            if output:
                print(output)
        elif event == "stop":
            results, gaps = stop(payload)
            for result in results:
                print("everything-finance: archived report -> " + result["report_html"], file=sys.stderr)
            for gap in gaps:
                print("everything-finance: " + gap, file=sys.stderr)
        else:
            raise ValueError(f"unknown hook event {event!r}")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"everything-finance: hook skipped ({type(exc).__name__}); no staging was consumed",
              file=sys.stderr)


if __name__ == "__main__":
    main()
