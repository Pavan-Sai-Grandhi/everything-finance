"""Explicitly authorized Telegram delivery through the shared transport."""
import json
import os
from pathlib import Path
from finance import spine, transport

_SOURCE = "finance.report.telegram"


def deliver_report(result):
    """One explicitly authorized attempt. Never retry an uncertain message send."""
    if result.get('telegram') is not True:
        return None
    token, chat = os.environ.get('TELEGRAM_BOT_TOKEN'), os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        return 'Telegram credentials missing; report remains archived'
    projection = json.loads(Path(result['report_json']).read_text(encoding='utf-8'))
    coverage = projection.get('coverage') or {}
    brief = coverage.get('brief', '') if isinstance(coverage, dict) else ''
    if not isinstance(brief, str):
        brief = ''
    caption = f"{result['ticker']} — {result['mode']} ({result['date']})\n{brief}"
    # Conservative UTF-16 length bound accommodates Telegram caption limits.
    caption = caption.encode('utf-16-le')[:2000].decode('utf-16-le', errors='ignore')
    body, gap = transport.request(f'https://api.telegram.org/bot{token}/sendDocument',
        form={'chat_id': chat, 'caption': caption}, form_files={'document': result['report_html']},
        private_url=True, retries=0, timeout=60)
    if gap:
        return 'Telegram delivery failed or uncertain; report remains archived'
    try:
        response = json.loads(body)
        if isinstance(response, dict) and response.get('ok') is True:
            return None
    except (ValueError, TypeError):
        pass
    return 'Telegram rejected the document or returned an invalid response; report remains archived'


def send_text(text):
    if not isinstance(text, str) or not text.strip():
        return 'Telegram message is empty'
    if len(text.encode('utf-16-le')) // 2 > 4096:
        return 'Telegram message exceeds the text limit; shorten it before sending'
    token, chat = os.environ.get('TELEGRAM_BOT_TOKEN'), os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        return 'Telegram credentials missing; message not sent'
    body, gap = transport.request(f'https://api.telegram.org/bot{token}/sendMessage',
        form={'chat_id': chat, 'text': text}, private_url=True, retries=0, timeout=25)
    if gap:
        return 'Telegram delivery failed or uncertain; do not retry automatically'
    try:
        response = json.loads(body)
        if isinstance(response, dict) and response.get('ok') is True:
            return None
    except (ValueError, TypeError):
        pass
    return 'Telegram rejected the message or returned an invalid response'


@spine.guarded(_SOURCE)
def send_text_file(text_file):
    """Send one user-authorized message from a local text file; never retried."""
    gap = send_text(Path(text_file).read_text(encoding="utf-8"))
    return spine.envelope(gap is None, _SOURCE, {"sent": gap is None}, [gap] if gap else [])
