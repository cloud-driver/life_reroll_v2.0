"""Bounded SMTP delivery and single-use email challenges. No raw codes in SQLite."""

import concurrent.futures
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import smtplib
import sqlite3
import ssl
import time
import uuid
from contextlib import contextmanager
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path
from . import store, engine

INSTANCE = uuid.uuid4().hex
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix='life-mail')
ACTIVE = ('QUEUED', 'SENDING')
TTL = 600
COOLDOWN = 60
MAX_ATTEMPTS = 5


def config():
    path = Path(os.environ.get('LIFE_MAIL_CONFIG', str(Path(__file__).resolve().parents[1] / 'mail-config.json')))
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        value = {}
    for key, env in {
        'host': 'LIFE_SMTP_HOST',
        'port': 'LIFE_SMTP_PORT',
        'username': 'LIFE_SMTP_USER',
        'password': 'LIFE_SMTP_PASSWORD',
        'from_email': 'LIFE_SMTP_FROM',
        'from_name': 'LIFE_SMTP_FROM_NAME',
        'otp_secret': 'LIFE_OTP_SECRET',
        'tls': 'LIFE_SMTP_TLS',
    }.items():
        if env in os.environ:
            value[key] = os.environ[env]
    value['mode'] = os.environ.get('LIFE_EMAIL_MODE', 'smtp')
    if value['mode'] == 'development' and os.environ.get('LIFE_DEVELOPMENT_MODE') != '1':
        raise ValueError('MAIL_NOT_CONFIGURED')
    if value['mode'] not in ('smtp', 'development'):
        raise ValueError('MAIL_NOT_CONFIGURED')
    if value['mode'] == 'smtp':
        if not all(value.get(k) for k in ('host', 'from_email', 'otp_secret')):
            raise ValueError('MAIL_NOT_CONFIGURED')
        if len(value['otp_secret']) < 32 or value.get('tls', 'starttls') not in ('starttls', 'ssl'):
            raise ValueError('MAIL_NOT_CONFIGURED')
        try:
            value['port'] = int(value.get('port', 587))
            if not 1 <= value['port'] <= 65535:
                raise ValueError('MAIL_NOT_CONFIGURED')
        except (TypeError, ValueError):
            raise ValueError('MAIL_NOT_CONFIGURED')
    else:
        value['otp_secret'] = 'explicit-isolated-development-test-key'
    return value


def expose_tokens():
    return os.environ.get('LIFE_EMAIL_MODE') == 'development' and os.environ.get('LIFE_DEVELOPMENT_MODE') == '1'


def bypass():
    return expose_tokens() and os.environ.get('LIFE_SKIP_EMAIL_VERIFICATION') == '1'


def code_hash(email, code):
    return hmac.new(
        config()['otp_secret'].encode(), ('VERIFY:' + email + ':' + code).encode(), hashlib.sha256
    ).hexdigest()


def recover(db):
    now = time.time()
    db.execute(
        "UPDATE mail_deliveries SET status='FAILED',error_code='DELIVERY_INTERRUPTED',updated_at=? WHERE status IN ('QUEUED','SENDING') AND (instance_id!=? OR created_at<?)",
        (now, INSTANCE, now - 120),
    )
    db.execute(
        'DELETE FROM mail_deliveries WHERE created_at<? AND status NOT IN (\'QUEUED\',\'SENDING\')', (now - 7 * 86400,)
    )
    db.execute('DELETE FROM email_challenges WHERE expires_at<?', (now - 86400,))


def enqueue(db, user, purpose, token):
    cfg = config()
    recover(db)
    now = time.time()
    previous = db.execute(
        'SELECT * FROM mail_deliveries WHERE user_id=? AND purpose=? ORDER BY created_at DESC LIMIT 1',
        (user['id'], purpose),
    ).fetchone()
    if previous and previous['status'] != 'FAILED' and now - previous['created_at'] < COOLDOWN:
        raise ValueError('EMAIL_COOLDOWN')
    if (
        db.execute(
            'SELECT COUNT(*) FROM mail_deliveries WHERE user_id=? AND created_at>?', (user['id'], now - 3600)
        ).fetchone()[0]
        >= 6
    ):
        raise ValueError('EMAIL_RATE_LIMITED')
    if db.execute("SELECT COUNT(*) FROM mail_deliveries WHERE status IN ('QUEUED','SENDING')").fetchone()[0] >= 12:
        raise ValueError('MAIL_BUSY')
    id_ = engine.uid()
    status = 'DEVELOPMENT' if cfg['mode'] == 'development' else 'QUEUED'
    db.execute(
        'INSERT INTO mail_deliveries VALUES(?,?,?,?,?,?,?,?)',
        (id_, user['id'], purpose, status, now, now, INSTANCE, None),
    )
    task = None if status == 'DEVELOPMENT' else (str(store.DB_FILE), id_, user['email'], purpose, token)
    return id_, task


def prepare_verification(db, user):
    old = db.execute('SELECT code_hash FROM email_challenges WHERE user_id=?', (user['id'],)).fetchone()
    code = f'{secrets.randbelow(1000000):06d}'
    if old and hmac.compare_digest(old['code_hash'], code_hash(user['email'], code)):
        code = f'{(int(code) + 1) % 1000000:06d}'
    id_, task = enqueue(db, user, 'VERIFY', code)
    now = time.time()
    db.execute(
        'INSERT INTO email_challenges VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET code_hash=excluded.code_hash,expires_at=excluded.expires_at,attempts=0,sent_at=excluded.sent_at,delivery_id=excluded.delivery_id',
        (user['id'], code_hash(user['email'], code), now + TTL, 0, now, id_),
    )
    return code, task


def verify(db, user, code):
    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code):
        return 'INVALID_VERIFICATION_CODE'
    row = db.execute('SELECT * FROM email_challenges WHERE user_id=?', (user['id'],)).fetchone()
    if not row or row['expires_at'] <= time.time():
        return 'VERIFICATION_CODE_EXPIRED'
    if row['attempts'] >= MAX_ATTEMPTS:
        return 'VERIFICATION_ATTEMPTS_EXCEEDED'
    if not hmac.compare_digest(row['code_hash'], code_hash(user['email'], code)):
        db.execute('UPDATE email_challenges SET attempts=attempts+1 WHERE user_id=?', (user['id'],))
        return 'VERIFICATION_ATTEMPTS_EXCEEDED' if row['attempts'] + 1 >= MAX_ATTEMPTS else 'INVALID_VERIFICATION_CODE'
    db.execute('UPDATE users SET verified=1 WHERE id=?', (user['id'],))
    db.execute('DELETE FROM email_challenges WHERE user_id=?', (user['id'],))
    db.execute("DELETE FROM tokens WHERE user_id=? AND purpose='VERIFY'", (user['id'],))
    return None


def state(db, user):
    recover(db)
    row = db.execute('SELECT * FROM email_challenges WHERE user_id=?', (user['id'],)).fetchone()
    delivery = db.execute(
        "SELECT * FROM mail_deliveries WHERE user_id=? AND purpose='VERIFY' ORDER BY created_at DESC LIMIT 1",
        (user['id'],),
    ).fetchone()
    status = delivery['status'] if delivery else 'NONE'
    now = time.time()
    return {
        'email': user['email'],
        'verified': bool(user['verified']),
        'delivery_status': status,
        'retry_after_seconds': max(0, int(COOLDOWN - (now - delivery['created_at']) + 0.999))
        if delivery and status != 'FAILED'
        else 0,
        'expires_in_seconds': max(0, int(row['expires_at'] - now)) if row else 0,
        'attempts_remaining': max(0, MAX_ATTEMPTS - row['attempts']) if row else MAX_ATTEMPTS,
        'development': status == 'DEVELOPMENT',
    }


@contextmanager
def connection(path):
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def update(path, id_, status, error=None):
    with connection(path) as db:
        row = db.execute(
            "UPDATE mail_deliveries SET status=?,updated_at=?,error_code=? WHERE id=? AND instance_id=? AND status IN ('QUEUED','SENDING')",
            (status, time.time(), error, id_, INSTANCE),
        )
        return bool(row.rowcount)


def send(to, purpose, token):
    cfg = config()
    message = EmailMessage()
    message['From'] = formataddr((cfg.get('from_name', 'Life Reroll'), cfg['from_email']))
    message['To'] = to
    message['Date'] = formatdate(localtime=True)
    message['Message-ID'] = make_msgid(domain=cfg['from_email'].rsplit('@', 1)[-1])
    if purpose == 'VERIFY':
        message['Subject'] = 'Life Reroll｜信箱驗證碼'
        message.set_content(
            f'你的 Life Reroll 信箱驗證碼是：\n\n{token}\n\n請回到剛才註冊的遊戲頁面輸入驗證碼。驗證碼於 10 分鐘內有效，最多可嘗試 5 次；重寄後舊碼立即失效。\n\n若不是你本人操作，請忽略此信，不要把驗證碼提供給他人。\n\n知與科技 · Life Reroll\n這是帳號驗證通知，不含行銷訊息。'
        )
    else:
        message['Subject'] = 'Life Reroll｜密碼重設通知'
        message.set_content(
            f'請回到 Life Reroll 的「忘記密碼」輸入以下一次性重設碼，並設定新密碼：\n\n{token}\n\n重設碼一小時內有效。若不是你本人操作，請忽略此信；未完成重設不會改變原密碼。\n\n知與科技 · Life Reroll'
        )
    context = ssl.create_default_context()
    cls = smtplib.SMTP_SSL if cfg.get('tls', 'starttls') == 'ssl' else smtplib.SMTP
    kwargs = {'timeout': 20}
    if cls is smtplib.SMTP_SSL:
        kwargs['context'] = context
    with cls(cfg['host'], cfg['port'], **kwargs) as server:
        server.ehlo()
        if cfg.get('tls', 'starttls') != 'ssl':
            server.starttls(context=context)
            server.ehlo()
        if cfg.get('username'):
            server.login(cfg['username'], cfg.get('password', ''))
        server.send_message(message)


def work(path, id_, to, purpose, token):
    if not update(path, id_, 'SENDING'):
        return
    try:
        send(to, purpose, token)
        update(path, id_, 'SENT')
    except Exception:
        # Provider details and credentials stay out of public errors and logs.
        logging.getLogger(__name__).warning('Mail delivery failed: %s', id_)
        update(path, id_, 'FAILED', 'SMTP_UNAVAILABLE')


def submit(task):
    if task:
        POOL.submit(work, *task)


def submit_all(tasks):
    for task in tasks:
        submit(task)
