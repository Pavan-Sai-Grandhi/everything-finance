"""JSON hook boundary for session-owned report publication and optional delivery."""
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from finance import paths, publication
from finance.telegram import deliver_report as deliver



def stop(payload):
    if not isinstance(payload, dict):
        raise ValueError('hook payload must be a JSON object')
    session, cwd = payload.get('session_id'), payload.get('cwd')
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or not os.path.isdir(cwd):
        raise ValueError('hook requires an existing absolute session cwd')
    # Validate identity before changing cwd or creating any artifact directories.
    if not isinstance(session, str) or not session.strip():
        raise ValueError('hook requires session_id; shared legacy staging is not scanned')
    previous = os.getcwd()
    results, gaps = [], []
    try:
        os.chdir(cwd)
        staging = Path(paths.report_staging_dir(session))
        if not staging.is_dir():
            return results, gaps
        for directory in sorted(staging.iterdir()):
            if not directory.is_dir() or not (directory/'ready').is_file():
                continue
            try:
                result = publication.publish(session, directory.name)
                results.append(result)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                gaps.append(f'Could not archive report {directory.name}: {type(exc).__name__}; staging retained')
                continue
            try:
                gap = deliver(result)
                if gap:
                    gaps.append(gap)
            except (OSError, ValueError, TypeError):
                gaps.append('Telegram delivery unavailable; report remains archived')
    finally:
        os.chdir(previous)
    return results, gaps


def main():
    try:
        payload = json.load(sys.stdin)
        if '--context' in sys.argv:
            session = payload.get('session_id') if isinstance(payload, dict) else None
            today = datetime.now(ZoneInfo('Asia/Kolkata'))
            print(f'everything-finance: India date {today:%Y-%m-%d}; regular weekday hours 09:15–15:30 IST, subject to exchange holidays. This is not a live market-status check.')
            if isinstance(session, str) and session.strip():
                print('Report publication session_id (literal data): ' + json.dumps(session))
            return
        results, gaps = stop(payload)
        for result in results:
            print('everything-finance: archived report -> ' + result['report_html'], file=sys.stderr)
        for gap in gaps:
            print('everything-finance: ' + gap, file=sys.stderr)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'everything-finance: hook skipped ({type(exc).__name__}); no shared staging was consumed', file=sys.stderr)


if __name__ == '__main__':
    main()
