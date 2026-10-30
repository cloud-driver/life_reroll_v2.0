"""Account, session and profile operations (A*)."""

from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta

from .. import store, engine, mail, legal
from .common import fail, email_bypass, require, page, hash_password, check_password, t_hash, user_view


def account(op, db, request, b, u, p):
    if op == 'A01':
        raw_email = b.get('email', '')
        require(isinstance(raw_email, str), 'EMAIL_INVALID')
        email = raw_email.strip().lower()
        password = b.get('password', '')
        display = b.get('display_name', '')
        require(
            isinstance(email, str) and re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email) and len(email) <= 254,
            'EMAIL_INVALID',
        )
        require(isinstance(password, str) and 12 <= len(password) <= 128, 'PASSWORD_LENGTH_INVALID')
        require(isinstance(display, str) and 2 <= len(display.strip()) <= 30, 'DISPLAY_NAME_LENGTH_INVALID')
        require(
            b.get('terms_version') == legal.VERSION and b.get('privacy_version') == legal.VERSION,
            'LEGAL_VERSION_INVALID',
        )
        display = display.strip()
        id_ = engine.uid()
        role = (
            'CONTENT_ADMIN'
            if email == os.environ.get('LIFE_ADMIN_EMAIL', '').strip().lower() and os.environ.get('LIFE_ADMIN_EMAIL')
            else 'PLAYER'
        )
        try:
            db.execute(
                'INSERT INTO users(id,email,password_hash,display_name,verified,role,created_at) VALUES(?,?,?,?,?,?,?)',
                (id_, email, hash_password(password), display, 0, role, engine.now()),
            )
        except sqlite3.IntegrityError:
            fail('EMAIL_UNAVAILABLE')
        user = db.execute('SELECT * FROM users WHERE id=?', (id_,)).fetchone()
        token, task = mail.prepare_verification(db, user)
        request.state.mail_tasks.append(task)
        db.execute('INSERT INTO legal_acceptances VALUES(?,?,?,?)', (id_, legal.VERSION, legal.VERSION, engine.now()))
        if email_bypass():
            db.execute('UPDATE users SET verified=1 WHERE id=?', (id_,))
        user = db.execute('SELECT * FROM users WHERE id=?', (id_,)).fetchone()
        out = user_view(user)
        if mail.expose_tokens():
            out['dev_verification_token'] = token
        return 201, out
    if op == 'A02':
        email = (b.get('email') or '').strip().lower()
        h = t_hash(email)
        stamp = int(time.time())
        attempts = db.execute('SELECT * FROM login_attempts WHERE email_hash=?', (h,)).fetchone()
        if attempts and stamp - attempts['first_at'] < 600 and attempts['count'] >= 5:
            fail('RATE_LIMITED')
        row = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if not row or not check_password(b.get('password', ''), row['password_hash']):
            # Handle invalid credentials as a successful request outcome so the failure counter commits.
            count = attempts['count'] + 1 if attempts and stamp - attempts['first_at'] < 600 else 1
            start = attempts['first_at'] if attempts and stamp - attempts['first_at'] < 600 else stamp
            db.execute(
                'INSERT INTO login_attempts VALUES(?,?,?) ON CONFLICT(email_hash) DO UPDATE SET count=excluded.count,first_at=excluded.first_at',
                (h, count, start),
            )
            return 401, {'_login_error': 'INVALID_CREDENTIALS'}
        db.execute('DELETE FROM login_attempts WHERE email_hash=?', (h,))
        if email_bypass() and not row['verified']:
            db.execute('UPDATE users SET verified=1 WHERE id=?', (row['id'],))
            row = db.execute('SELECT * FROM users WHERE id=?', (row['id'],)).fetchone()
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        sid = engine.uid()
        db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,0)', (sid, row['id'], t_hash(token), csrf, engine.now()))
        return 200, {'user': user_view(row), 'csrf_token': csrf, 'session_id': sid, '_cookie_token': token}
    if op == 'A03':
        return 200, {
            'user': user_view(u) if u else None,
            'csrf_token': u['csrf'] if u else None,
            'session_id': u['sid'] if u else None,
        }
    if op == 'A05' or op == 'A07':
        email = (b.get('email') or '').strip().lower()
        row = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        token = None
        if op == 'A05':
            # Only the signed-in account can request another verification email.
            if row and u and row['id'] == u['id'] and not row['verified']:
                token, task = mail.prepare_verification(db, row)
                request.state.mail_tasks.append(task)
        elif row:
            token = secrets.token_urlsafe(32)
            _, task = mail.enqueue(db, row, 'RESET', token)
            db.execute("DELETE FROM tokens WHERE user_id=? AND purpose='RESET'", (row['id'],))
            db.execute(
                'INSERT INTO tokens VALUES(?,?,?,?)',
                (t_hash(token), row['id'], 'RESET', (datetime.now().astimezone() + timedelta(hours=1)).isoformat()),
            )
            request.state.mail_tasks.append(task)
        msg = {'accepted': True, 'message': '若信箱適用，將收到通知。'}
        if token and mail.expose_tokens():
            msg['dev_token'] = token
        return 202, msg
    if op == 'A06':
        require(u, 'UNAUTHENTICATED')
        email = b.get('email') or (u['email'] if u else '')
        require(isinstance(email, str), 'VALIDATION_ERROR')
        row = db.execute('SELECT * FROM users WHERE email=?', (email.strip().lower(),)).fetchone()
        if not row:
            return 422, {'_account_error': 'INVALID_VERIFICATION_CODE'}
        if u and row['id'] != u['id']:
            return 422, {'_account_error': 'INVALID_VERIFICATION_CODE'}
        code = mail.verify(db, row, b.get('token', ''))
        # Return normally so failed-attempt increments commit too.
        if code:
            return (429 if code == 'VERIFICATION_ATTEMPTS_EXCEEDED' else 422), {'_account_error': code}
        return 200, {'accepted': True, 'message': '信箱驗證成功'}
    if op == 'A08':
        token = b.get('token', '')
        purpose = 'RESET'
        row = db.execute('SELECT * FROM tokens WHERE token_hash=? AND purpose=?', (t_hash(token), purpose)).fetchone()
        require(row and row['expires_at'] > engine.now(), 'INVALID_TOKEN')
        new = b.get('new_password', '')
        require(isinstance(new, str) and 12 <= len(new) <= 128, 'PASSWORD_LENGTH_INVALID')
        db.execute('UPDATE users SET password_hash=? WHERE id=?', (hash_password(new), row['user_id']))
        db.execute('UPDATE sessions SET revoked=1 WHERE user_id=?', (row['user_id'],))
        db.execute('DELETE FROM tokens WHERE token_hash=?', (t_hash(token),))
        return 200, {'accepted': True, 'message': '已重設密碼'}
    require(u, 'UNAUTHENTICATED')
    if op == 'A04':
        db.execute('UPDATE sessions SET revoked=1 WHERE id=?', (u['sid'],))
        return 204, None
    if op == 'A09':
        require(check_password(b.get('current_password', ''), u['password_hash']), 'INVALID_CREDENTIALS')
        new = b.get('new_password', '')
        require(isinstance(new, str) and 12 <= len(new) <= 128, 'PASSWORD_LENGTH_INVALID')
        db.execute('UPDATE users SET password_hash=? WHERE id=?', (hash_password(new), u['id']))
        db.execute('UPDATE sessions SET revoked=1 WHERE user_id=? AND id!=?', (u['id'], u['sid']))
        return 200, {'accepted': True, 'message': '密碼已更新，其他裝置已登出'}
    if op == 'A10':
        return 200, user_view(u)
    if op == 'A11':
        display = b.get('display_name', '')
        require(isinstance(display, str) and 2 <= len(display) <= 30, 'VALIDATION_ERROR')
        db.execute('UPDATE users SET display_name=? WHERE id=?', (display, u['id']))
        return 200, user_view(db.execute('SELECT * FROM users WHERE id=?', (u['id'],)).fetchone())
    if op == 'A12':
        return 200, page(
            [
                {'id': x['id'], 'created_at': x['created_at'], 'current': x['id'] == u['sid']}
                for x in db.execute('SELECT * FROM sessions WHERE user_id=? AND revoked=0', (u['id'],))
            ]
        )
    if op == 'A13':
        row = db.execute('UPDATE sessions SET revoked=1 WHERE id=? AND user_id=?', (p['session_id'], u['id']))
        require(row.rowcount, 'NOT_FOUND')
        return 204, None
    if op == 'A14':
        return 200, json.loads(u['settings']) or {'tutorial_complete': False, 'music': True}
    if op == 'A15':
        require(
            isinstance(b, dict)
            and set(b)
            <= set(
                (
                    'locale',
                    'sound_enabled',
                    'music',
                    'reduced_motion',
                    'text_scale',
                    'tutorial_completed',
                    'tutorial_complete',
                )
            ),
            'VALIDATION_ERROR',
        )
        if 'reduced_motion' in b:
            require(type(b['reduced_motion']) is bool, 'VALIDATION_ERROR')
        if 'text_scale' in b:
            require(type(b['text_scale']) in (int, float) and b['text_scale'] in (1, 1.2, 1.5), 'VALIDATION_ERROR')
        stored = json.loads(u['settings'])
        stored.update(b)
        db.execute('UPDATE users SET settings=? WHERE id=?', (store.j(stored), u['id']))
        return 200, stored
    if op == 'A16':
        require(
            check_password(b.get('current_password', ''), u['password_hash'])
            and b.get('confirmation') == 'DELETE_MY_ACCOUNT',
            'INVALID_CREDENTIALS',
        )
        # Erase the local account and its game history atomically; no queued worker is needed.
        receipt_id = engine.uid()
        deleted_at = engine.now()
        db.execute('DELETE FROM coach_jobs WHERE owner=?', ('user:' + u['id'],))
        db.execute('DELETE FROM insight_jobs WHERE owner=?', (u['id'],))
        for table in ('campaigns', 'jobs', 'idempotency', 'tokens', 'sessions'):
            db.execute(f'DELETE FROM {table} WHERE user_id=?', (u['id'],))
        db.execute('DELETE FROM login_attempts WHERE email_hash=?', (t_hash(u['email']),))
        db.execute('DELETE FROM users WHERE id=?', (u['id'],))
        return 202, {'job_id': receipt_id, 'scheduled_at': deleted_at}
    fail('NOT_FOUND')
