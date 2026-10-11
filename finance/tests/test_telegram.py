#!/usr/bin/env python3
"""Offline checks for authorized-delivery mechanics; no message is sent."""
import os
from pathlib import Path
import sys
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from finance import telegram
from finance.tests.harness import check, run


def test_missing_credentials_and_long_text_do_not_send():
    with mock.patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN':'','TELEGRAM_CHAT_ID':''}), mock.patch.object(telegram.transport,'request') as request:
        check('missing credentials are a delivery gap',bool(telegram.send_text('fixture')) and not request.called)
    with mock.patch.object(telegram.transport,'request') as request:
        check('oversized Unicode text refuses before sending',bool(telegram.send_text('😀'*2049)) and not request.called)


def test_text_uses_private_nonretrying_transport():
    with mock.patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN':'fixture-token','TELEGRAM_CHAT_ID':'fixture-chat'}):
        with mock.patch.object(telegram.transport,'request',return_value=('{"ok": true}',None)) as request:
            gap=telegram.send_text('fixture <plain text>')
        args, kw=request.call_args
        check('successful send is confirmed by structured response',gap is None)
        check('text sent as plain multipart fields',kw['form']=={'chat_id':'fixture-chat','text':'fixture <plain text>'})
        check('credential-bearing URL remains private with no retries',kw['private_url'] is True and kw['retries']==0)
        with mock.patch.object(telegram.transport,'request',return_value=('{"ok":false,"description":"fixture-token"}',None)):
            gap=telegram.send_text('fixture')
        check('provider failure cannot echo credentials',bool(gap) and 'fixture-token' not in gap)


if __name__ == '__main__':
    run(globals())
