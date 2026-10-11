"""Prepare and atomically archive one complete, session-owned report bundle."""
import fcntl
import json
import os
from pathlib import Path
import time
import uuid

from finance import paths


def prepare(session, ticker, day, mode, telegram=False):
    if mode not in ('standard', 'deep', 'fundamentals'):
        raise ValueError('only deck-producing modes can stage a report')
    ticker, day = paths.ticker_key(ticker), paths._day(day)
    run_id = f'{time.time_ns():020d}-{uuid.uuid4().hex}'
    directory = Path(paths.report_stage(session, run_id))
    directory.mkdir()
    metadata = {'session': session, 'ticker': ticker, 'date': day,
                'mode': mode, 'run_id': run_id, 'telegram': telegram}
    (directory/'run.json').write_text(json.dumps(metadata), encoding='utf-8')
    (directory/'agents').mkdir()
    return {'run_dir': str(directory), 'report_json': str(directory/'report.json'),
            'report_html': str(directory/'report.html'), 'agents_dir': str(directory/'agents')}


def _metadata(directory, session):
    metadata = json.loads((directory/'run.json').read_text(encoding='utf-8'))
    if not isinstance(metadata, dict) or metadata.get('session') != session:
        raise ValueError('report belongs to another session')
    if metadata.get('mode') not in ('standard', 'deep', 'fundamentals'):
        raise ValueError('invalid report mode')
    if directory.name != metadata.get('run_id'):
        raise ValueError('run identity does not match staging directory')
    # The metadata's exact session/run pair must point back to this directory.
    expected = Path(paths.report_stage(session, metadata['run_id']))
    if directory != expected:
        raise ValueError('report is not in its session staging directory')
    paths.ticker_key(metadata['ticker'])
    paths._day(metadata['date'])
    return metadata


def publish(session, run_id):
    """Move a validated bundle once; failure leaves staging available for repair.

    Caller marks readiness only after renderer checks and all work-paper writes finish.
    No network or notification is performed here.
    """
    directory = Path(paths.report_stage(session, run_id))
    # Lock sits outside the moved directory and keeps its inode for every waiter.
    with (directory.parent/(run_id+'.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if directory.is_symlink():
            raise ValueError("report staging directory cannot be a symlink")
        for base, dirs, files in os.walk(directory, followlinks=False):
            for name in dirs + files:
                if Path(base, name).is_symlink():
                    raise ValueError('report bundles cannot contain symlinks')
        metadata = _metadata(directory, session)
        if not (directory/'ready').is_file():
            raise ValueError('report has not been marked ready')
        projection = json.loads((directory/'report.json').read_text(encoding='utf-8'))
        meta = projection.get('meta') if isinstance(projection, dict) else None
        if not isinstance(meta, dict) or any(meta.get(key) != metadata[key] for key in ('ticker','date','mode')):
            raise ValueError('projection identity differs from run metadata')
        deck = directory/'report.html'
        if not deck.is_file() or deck.stat().st_size == 0:
            raise ValueError('rendered deck is missing or empty')
        if not (directory/'agents').is_dir():
            raise ValueError('work-paper directory is missing')
        destination = Path(paths.report_archive(metadata['ticker'], metadata['date'], run_id))
        if destination.exists():
            raise ValueError('archive already exists; never overwrite prior evidence')
        # Both locations belong to the artifact root. Cross-device failure is a gap,
        # not permission to publish half a report or delete the original.
        os.rename(directory, destination)
        return {'run_dir': str(destination), 'report_json': str(destination/'report.json'),
                'report_html': str(destination/'report.html'), **metadata}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    stage = commands.add_parser('prepare')
    stage.add_argument('--session', required=True)
    stage.add_argument('--ticker', required=True)
    stage.add_argument('--date', required=True)
    stage.add_argument('--telegram', action='store_true', help='send the archived deck only when the user authorized Telegram delivery')
    stage.add_argument('--mode', choices=('standard','deep','fundamentals'), required=True)
    archive = commands.add_parser('publish')
    archive.add_argument('--session', required=True)
    archive.add_argument('--run-id', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            result = prepare(args.session, args.ticker, args.date, args.mode, args.telegram)
        else:
            result = publish(args.session, args.run_id)
            from finance.report_hook import deliver
            gap = deliver(result)
            if gap:
                result['delivery_gap'] = gap
        print(json.dumps(result))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f'report publication: {exc}\n')


if __name__ == '__main__':
    main()
