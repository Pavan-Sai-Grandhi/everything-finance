#!/usr/bin/env python3
"""Report publication is atomic, contained, session-specific and evidence-preserving."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from finance import paths
from finance.report import hook, publication
from finance.tests.harness import check, run


def stage(session='session-a'):
    result = publication.prepare(session, 'TESTCO', '2026-01-02', 'standard')
    directory = Path(result['run_dir'])
    (directory/'report.json').write_text(json.dumps({'meta': {'ticker':'TESTCO','date':'2026-01-02','mode':'standard'}}))
    (directory/'report.html').write_text('<!doctype html><html>fixture deck</html>')
    (directory/'agents'/'verdict.md').write_text('Synthetic verdict')
    (directory/'agents'/'dcf.md').write_text('Synthetic valuation')
    (directory/'agents'/'management.md').write_text('Synthetic governance')
    return directory


def test_publish_preserves_complete_runs_and_rejects_incomplete():
    with tempfile.TemporaryDirectory() as work, mock.patch.dict(os.environ, {'EVERYTHING_FINANCE_ARTIFACTS':work}):
        first = stage()
        try:
            publication.publish('session-a',first.name)
            check('unready bundle cannot publish',False)
        except ValueError:
            check('unready bundle cannot publish', first.exists())
        (first/'ready').touch()
        result = publication.publish('session-a',first.name)
        archived = Path(result['run_dir'])
        check('one move archives all files',not first.exists() and (archived/'report.html').exists() and (archived/'agents/verdict.md').exists())
        second = stage()
        (second/'ready').touch()
        newer = publication.publish('session-a',second.name)
        check('same-day rerun cannot overwrite prior evidence',newer['run_dir']!=result['run_dir'] and (archived/'report.json').exists())
        prior = paths.prior_run('deep-analysis','TESTCO',before='2026-01-03')
        check('prior-run lookup resolves the latest complete bundle',prior['data']['path']==newer['report_json'] and prior['data']['date']=='2026-01-02',prior)
        check('prior valuation resolves published bundle work paper',paths.latest_prior('dcf','TESTCO',before='2026-01-03')==str(Path(newer['run_dir'])/'agents/dcf.md'))
        check('prior governance resolves published bundle work paper',paths.latest_prior('management','TESTCO',before='2026-01-03')==str(Path(newer['run_dir'])/'agents/management.md'))
        check('fundamentals lookup does not consume a standard report',paths.latest_prior('fundamentals','TESTCO',before='2026-01-03') is None)
        third = stage()
        (third/'ready').touch()
        with mock.patch.object(publication.os,'rename',side_effect=OSError('fixture disk failure')):
            try:
                publication.publish('session-a',third.name)
                check('publication failure retains staging',False)
            except OSError:
                check('publication failure retains staging',(third/'report.json').exists() and (third/'report.html').exists())


def test_session_and_projection_identity_cannot_mix():
    with tempfile.TemporaryDirectory() as work, mock.patch.dict(os.environ, {'EVERYTHING_FINANCE_ARTIFACTS':work}):
        directory = stage()
        (directory/'ready').touch()
        try:
            publication.publish('session-b',directory.name)
            check('another session cannot publish this report',False)
        except (ValueError,OSError):
            check('another session cannot publish this report',directory.exists())
        (directory/'report.json').write_text(json.dumps({'meta':{'ticker':'OTHER','date':'2026-01-02','mode':'standard'}}))
        try:
            publication.publish('session-a',directory.name)
            check('mismatched projection identity fails',False)
        except ValueError:
            check('mismatched projection identity fails',directory.exists())
        (directory/'agents'/'outside').symlink_to(work)
        try:
            publication.publish('session-a',directory.name)
            check('linked content cannot enter bundle',False)
        except ValueError:
            check('linked content cannot enter bundle',directory.exists())


def test_hook_only_publishes_ready_bundles_from_its_session():
    with tempfile.TemporaryDirectory(prefix='ef hook " ') as work, mock.patch.dict(os.environ, {'EVERYTHING_FINANCE_ARTIFACTS':work}):
        ours, theirs = stage(), stage('session-b')
        (ours/'ready').touch(); (theirs/'ready').touch()
        with mock.patch('finance.report.telegram.transport.request') as network:
            result, gaps = hook.stop({'cwd':work,'session_id':'session-a'})
        check('hook publishes only its own session',len(result)==1 and not ours.exists() and theirs.exists(),gaps)
        check('credentials alone never authorize delivery',not network.called)
        again, gaps = hook.stop({'cwd':work,'session_id':'session-a'})
        check('repeat Stop does not republish or resend',again==[] and gaps==[])
        try:
            hook.stop({'cwd':work})
            check('missing session cannot scan shared staging',False)
        except ValueError:
            check('missing session cannot scan shared staging',theirs.exists())


def test_private_document_upload_does_not_expose_token_or_retry():
    from finance import transport
    import subprocess
    with tempfile.TemporaryDirectory() as work, mock.patch.dict(os.environ, {'EVERYTHING_FINANCE_ARTIFACTS':work,'TELEGRAM_BOT_TOKEN':'fixture-secret','TELEGRAM_CHAT_ID':'fixture-chat'}):
        directory = stage()
        (directory/'ready').touch()
        result = publication.publish('session-a',directory.name)
        result['telegram'] = True
        seen = []
        def curl(cmd, **kwargs):
            seen.append((cmd,kwargs))
            upload = cmd[cmd.index('--data-binary')+1][1:]
            payload = Path(upload).read_bytes()
            check('multipart upload contains the actual archived deck',b'fixture deck' in payload and b'fixture-chat' in payload)
            Path(cmd[cmd.index('-o')+1]).write_text('{"ok": false, "description": "fixture-secret"}')
            return subprocess.CompletedProcess(cmd,0,stdout='200',stderr='fixture-secret')
        with mock.patch.object(transport.subprocess,'run',side_effect=curl):
            gap = hook.deliver(result)
        check('delivery failure preserves archived evidence',Path(result['report_html']).exists() and bool(gap))
        check('token absent from command and diagnostic',len(seen)==1 and 'fixture-secret' not in str(seen[0][0]) and 'fixture-secret' not in gap)
        check('private URL supplied on stdin without redirects','fixture-secret' in seen[0][1]['input'] and '-L' not in seen[0][0])


def test_shell_hook_parses_escaped_cwd_and_keeps_stdout_clean():
    import shutil
    import subprocess
    root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='ef " hook ') as work, mock.patch.dict(os.environ, {'EVERYTHING_FINANCE_ARTIFACTS':work}):
        directory = stage()
        (directory/'ready').touch()
        plugin = Path(work)/'plugin'
        (plugin/'bin').mkdir(parents=True)
        shutil.copy2(root/'bin/load-env.sh',plugin/'bin/load-env.sh')
        for name in ('finance', 'agents'):
            (plugin/name).symlink_to(root/name,target_is_directory=True)
        shutil.copy2(root/'RULES.md',plugin/'RULES.md')
        (plugin/'.env').write_text('# empty synthetic credentials\n')
        env = {**os.environ,'CLAUDE_PLUGIN_ROOT':str(plugin),'CLAUDE_PLUGIN_DATA':'','PLUGIN_DATA':'','TELEGRAM_BOT_TOKEN':'','TELEGRAM_CHAT_ID':''}
        launcher = str(root/'hooks/hook.sh')
        payload = json.dumps({'cwd':work,'session_id':'session-a'})
        result = subprocess.run(['bash',launcher,'stop'],input=payload,env=env,cwd='/tmp',capture_output=True,text=True,timeout=10)
        check('Stop consumes JSON cwd correctly',result.returncode==0 and not directory.exists(),result.stderr)
        check('Stop does not put diagnostics on stdout',result.stdout=='')
        context = subprocess.run(['bash',launcher,'session'],input=payload,env=env,cwd='/tmp',capture_output=True,text=True,timeout=10)
        check('SessionStart provides exact session identity','"session-a"' in context.stdout and context.returncode==0,context.stderr)
        check('SessionStart carries the runtime rules','## Data integrity' in context.stdout,context.stdout[:200])
        agent = json.dumps({'agent_type':'everything-finance:debate-researcher'})
        sub = subprocess.run(['bash',launcher,'subagent'],input=agent,env=env,cwd='/tmp',capture_output=True,text=True,timeout=10)
        extra = json.loads(sub.stdout)['hookSpecificOutput'] if sub.stdout else {}
        check('SubagentStart hands the rules to a plugin agent',
              extra.get('hookEventName')=='SubagentStart' and '## How a report reads' in extra.get('additionalContext',''),sub.stderr)
        other = subprocess.run(['bash',launcher,'subagent'],input=json.dumps({'agent_type':'Explore'}),env=env,cwd='/tmp',capture_output=True,text=True,timeout=10)
        check('SubagentStart leaves other agents alone',other.returncode==0 and other.stdout=='')


def test_publish_report_tool_archives_and_reports_delivery():
    with tempfile.TemporaryDirectory() as work, mock.patch.dict(os.environ, {'EVERYTHING_FINANCE_ARTIFACTS':work}):
        env = publication.prepare_report('session-a','TESTCO','2026-01-02','standard')
        check('prepare_report returns the bundle paths',env['ok'] and env['data']['agents_dir'].endswith('agents'),env)
        check('prepare_report refuses a mode with no deck',not publication.prepare_report('session-a','TESTCO','2026-01-02','quick')['ok'])
        directory = stage()
        (directory/'ready').touch()
        env = publication.publish_report('session-a',directory.name)
        check('publish_report archives a ready bundle',env['ok'] and Path(env['data']['report_html']).is_file() and not directory.exists(),env)
        check('publish_report on a missing bundle is a labelled gap',not publication.publish_report('session-a',directory.name)['ok'])


if __name__ == '__main__':
    run(globals())
