"""Handlers for the 91 documented operations. API paths are registered in main.py."""

from __future__ import annotations
import copy
import hashlib
import hmac
import json
import os
import random
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta
from . import store, engine, finance, content, ai, qwen, rebirth, mail, legal


def fail(code):
    raise ValueError(code)


def email_bypass():
    return mail.bypass()


def require(flag, code='STATE_CONFLICT'):
    if not flag:
        fail(code)


def serial(value):
    return json.loads(store.j(value))


def page(xs):
    return {'items': xs, 'next_cursor': None, 'total': len(xs)}


def hash_password(password):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return salt.hex() + ':' + key.hex()


def check_password(password, encoded):
    try:
        salt, hash_ = encoded.split(':')
        key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(key.hex(), hash_)
    except (ValueError, TypeError):
        return False


def t_hash(v):
    return hashlib.sha256(v.encode()).hexdigest()


def user_view(u):
    return {
        'id': u['id'],
        'email': u['email'],
        'email_verified': bool(u['verified']),
        'roles': [u['role']],
        'display_name': u['display_name'],
        'created_at': u['created_at'],
    }


def get_user(db, request):
    bearer = request.headers.get('authorization', '')
    token = bearer[7:] if bearer.lower().startswith('bearer ') else request.cookies.get('life_session', '')
    if not token:
        return None, None
    row = db.execute(
        'SELECT users.*,sessions.id AS sid,sessions.csrf AS csrf FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token_hash=? AND sessions.revoked=0',
        (t_hash(token),),
    ).fetchone()
    if row:
        created = db.execute('SELECT created_at FROM sessions WHERE id=?', (row['sid'],)).fetchone()['created_at']
        if datetime.now().astimezone() - datetime.fromisoformat(created) > timedelta(days=30):
            return None, None
    return (row, row['sid']) if row else (None, None)


def verify_csrf(request, u):
    if request.method not in ('POST', 'PATCH', 'PUT', 'DELETE') or not u:
        return
    if request.headers.get('authorization', '').lower().startswith('bearer '):
        return
    require(hmac.compare_digest(request.headers.get('x-csrf-token', ''), u['csrf']), 'CSRF_INVALID')


def payload_version(body, r):
    require(body.get('expected_version') == r['version'], 'STALE_VERSION')


def receipt(r, resource=None, notices=None):
    return {'operation_id': engine.uid(), 'run': engine.change(r), 'resource': resource, 'notices': notices or []}


def job(db, user, type_, ref=None):
    type_ = {'REBIRTH': 'REBIRTH_PLAN', 'DELETE_ACCOUNT': 'ACCOUNT_ERASURE'}.get(type_, type_)
    j = {
        'id': engine.uid(),
        'type': type_,
        'status': 'SUCCEEDED',
        'result_ref': ref,
        'retryable': False,
        'attempt': 1,
        'poll_after_ms': 0,
        'error_code': None,
        'progress_percent': 100,
        'stage': '已完成',
    }
    db.execute('INSERT INTO jobs VALUES(?,?,?,?)', (j['id'], user, type_, store.j(j)))
    return j


def queue_reply(j, c=None, r=None):
    return {'job': j, 'campaign': public_campaign(c) if c else None, 'run_version': r['version'] if r else None}


def public_campaign(c):
    return {
        k: copy.deepcopy(v) for k, v in c.items() if k not in ('seed', 'persona', 'runs', 'story', 'exports', 'notices')
    } | {
        'current_run_id': c['runs'][-1]['id'] if c['runs'] else None,
        'run_ids': [r['id'] for r in c['runs']],
        'rebirths_remaining': max(0, 3 - len(c['runs'])) if c['status'] != 'COMPLETED' else 0,
        'persona': {k: v for k, v in c['persona'].items() if k != 'family_history'},
    }


def owned_campaign(db, p, u):
    c = store.get_campaign(db, p['campaign_id'], u['id'])
    require(c, 'NOT_FOUND')
    return c


def owned_run(db, p, u):
    c, r = store.find_run(db, p['run_id'], u['id'])
    require(r, 'NOT_FOUND')
    r.setdefault('daily_phase', 'HOME_READY' if r['scene_id'] in ('HOME', 'STREET') else 'FREE_TIME')
    return c, r


def result(operation, db, request, body, u, p, q):
    """All mutations use the surrounding BEGIN IMMEDIATE in main.dispatch."""
    op = operation
    if op[0] == 'A':
        return account(op, db, request, body, u, p)
    if op[0] == 'B':
        return basics(op, db, body, u, p, q)
    if op[0] == 'H':
        return admin(op, db, body, u, p, q)
    require(u, 'UNAUTHENTICATED')
    if op == 'C01':
        require(u['verified'], 'EMAIL_NOT_VERIFIED')
        require(
            not db.execute("SELECT 1 FROM campaigns WHERE user_id=? AND status!='COMPLETED'", (u['id'],)).fetchone(),
            'ACTIVE_CAMPAIGN_EXISTS',
        )
        published = [
            json.loads(row['body'])
            for row in db.execute('SELECT body FROM admin_releases')
            if json.loads(row['body'])['status'] == 'PUBLISHED'
        ]
        release = max(published, key=lambda item: item['created_at']) if published else None
        personas = content.PERSONAS
        if release:
            asset = db.execute(
                'SELECT body FROM admin_assets WHERE id=?', (release['assets']['persona_asset_id'],)
            ).fetchone()
            personas = json.loads(asset['body'])
        seed = secrets.randbits(64)
        persona = copy.deepcopy(random.Random(seed).choice(personas))
        r = engine.create_run(persona, seed)
        r['planned'] = ai.propose_plan(persona, r['planned'], r['start_age'])
        story = ai.refine_story(
            persona, [{**x, 'title': content.EVENT_BY_ID[x['card_id']]['title']} for x in r['planned']]
        )
        r['story_text'] = story
        c = {
            'id': engine.uid(),
            'status': 'ACTIVE',
            'version': 1,
            'content_version': release['version'] if release else content.CONTENT_VERSION,
            'created_at': engine.now(),
            'runs': [r],
            'persona': persona,
            'seed': seed,
            'story': story,
            'notices': [],
            'exports': [],
        }
        r['campaign_id'] = c['id']
        db.execute(
            'INSERT INTO campaigns VALUES(?,?,?,?,?)', (c['id'], u['id'], c['status'], store.j(c), c['created_at'])
        )
        j = job(db, u['id'], 'LIFE_PLAN', {'type': 'run', 'id': r['id'], 'href': f'/api/v1/runs/{r["id"]}'})
        return 202, queue_reply(j, c, r)
    if op == 'C02':
        found = store.active_campaign(db, u['id'])
        return 200, public_campaign(found) if found else None
    if op == 'C03':
        return 200, page(
            [
                public_campaign(c)
                for c in store.list_campaigns(db, u['id'])
                if not q.get('status') or c['status'] == q['status']
            ]
        )
    if op in ('C04', 'C05', 'G02', 'G03', 'G04', 'G05', 'G06'):
        c = owned_campaign(db, p, u)
        return campaign_command(op, db, c, body, u, p)
    if op in ('C12', 'C13', 'G07'):
        if op == 'G07':
            for c in store.list_campaigns(db, u['id']):
                ex = next((x for x in c['exports'] if x['id'] == p['export_id']), None)
                if ex:
                    return 200, ex
            fail('NOT_FOUND')
        row = db.execute('SELECT * FROM jobs WHERE id=?', (p['job_id'],)).fetchone()
        require(row and (row['user_id'] == u['id'] or u['role'] == 'CONTENT_ADMIN'), 'NOT_FOUND')
        j = json.loads(row['body'])
        if op == 'C12':
            return 200, j
        require(j['status'] == 'FAILED' and j['retryable'], 'JOB_NOT_RETRYABLE')
        j['attempt'] += 1
        j['status'] = 'SUCCEEDED'
        db.execute('UPDATE jobs SET body=? WHERE id=?', (store.j(j), j['id']))
        return 202, queue_reply(j)
    c, r = owned_run(db, p, u)
    if op[0] == 'C':
        return run_command(op, db, c, r, body, p)
    if op[0] == 'D':
        return events_command(op, db, c, r, body, p, q)
    if op[0] == 'E':
        return finance_command(op, db, c, r, body, p, q)
    if op[0] == 'F':
        return insurance_command(op, db, c, r, body, p, q)
    if op == 'G01':
        return 200, engine.report(r)
    fail('NOT_FOUND')


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


def basics(op, db, b, u, p, q):
    releases = [
        json.loads(row['body'])
        for row in db.execute('SELECT body FROM admin_releases')
        if json.loads(row['body'])['status'] == 'PUBLISHED'
    ]
    published = max(releases, key=lambda item: item['created_at']) if releases else None
    active_version = published['version'] if published else content.CONTENT_VERSION
    if op == 'B01':
        return 200, {
            'api_version': 'v1',
            'content_version': active_version,
            'terms_version': legal.VERSION,
            'privacy_version': legal.VERSION,
            'simulated_products': True,
            'development_email_bypass': email_bypass(),
            'email_verification_required': not email_bypass(),
            'feature_flags': {'ai_configured': qwen.config()['enabled']},
        }
    if op == 'B08':
        require(p['kind'] in ('TERMS', 'PRIVACY'), 'NOT_FOUND')
        return 200, legal.document(p['kind'])
    require(u, 'UNAUTHENTICATED')
    requested = q.get('content_version')
    if requested and requested != active_version:
        require(
            db.execute(
                "SELECT 1 FROM campaigns WHERE user_id=? AND json_extract(body,'$.content_version')=? LIMIT 1",
                (u['id'], requested),
            ).fetchone(),
            'CONTENT_VERSION_NOT_FOUND',
        )
    if op == 'B02':
        return 200, content.SCENES
    if op == 'B03':
        return 200, page([l for l in content.LESSONS if not q.get('topic') or l['id'] == q['topic']])
    if op == 'B04':
        l = next((v for v in content.LESSONS if v['id'] == p['lesson_id']), None)
        require(l, 'NOT_FOUND')
        return 200, l
    if op == 'B05':
        require(any(x['id'] == p['lesson_id'] for x in content.LESSONS), 'NOT_FOUND')
        settings = json.loads(u['settings'])
        settings.setdefault('read_lessons', [])
        if p['lesson_id'] not in settings['read_lessons']:
            settings['read_lessons'].append(p['lesson_id'])
        db.execute('UPDATE users SET settings=? WHERE id=?', (store.j(settings), u['id']))
        return 200, {'accepted': True, 'message': '已記錄教學閱讀'}
    all_notices = [n for c in store.list_campaigns(db, u['id']) for n in c.get('notices', [])]
    if op == 'B06':
        return 200, page([n for n in all_notices if not q.get('unread_only') or not n.get('read_at')])
    if op == 'B07':
        for c in store.list_campaigns(db, u['id']):
            for n in c['notices']:
                if n['id'] == p['notice_id']:
                    n['read_at'] = engine.now()
                    store.put_campaign(db, c)
                    return 200, {'accepted': True, 'message': '已讀'}
        fail('NOT_FOUND')
    fail('NOT_FOUND')


def campaign_command(op, db, c, b, u, p):
    if op == 'C04':
        return 200, public_campaign(c)
    if op == 'C05':
        return 200, [engine.public_run(r) for r in c['runs']]
    current = c['runs'][-1]
    if op == 'G05':
        require(c['status'] == 'COMPLETED', 'REPORT_NOT_READY')
        return 200, c['final_report']
    if op == 'G06':
        require(c['status'] == 'COMPLETED', 'REPORT_NOT_READY')
        existing = next((v for v in c['exports'] if v['status'] == 'READY'), None)
        if not existing:
            ex = {'id': engine.uid(), 'status': 'READY', 'format': 'PDF', 'expires_at': None}
            ex['download_url'] = f'/api/v1/report-exports/{ex["id"]}/download'
            c['exports'].append(ex)
            store.put_campaign(db, c)
            existing = ex
        j = job(
            db,
            u['id'],
            'REPORT_EXPORT',
            {'type': 'export', 'id': existing['id'], 'href': f'/api/v1/report-exports/{existing["id"]}'},
        )
        return 202, queue_reply(j, c)
    require(c['status'] == 'AWAITING_REBIRTH' and len(c['runs']) < 3, 'REBIRTH_NOT_AVAILABLE')
    points = rebirth.points(current)
    if op == 'G02':
        return 200, points
    if op == 'G03':
        point = next((x for x in points if x['id'] == p['point_id']), None)
        require(point, 'INVALID_REBIRTH_POINT')
        return 200, {
            'point': point,
            'preserved_facts': ['職業與病史', '準備點的資產負債、保單與家庭', '錨點事件與外部條件'],
            'rerolled_scope': ['錨點後的非固定事件', '新輪的投資波動序列'],
            'rebirths_after_commit': 2 - len(c['runs']),
            'campaign_version': c['version'],
        }
    require(b.get('confirmed') is True and b.get('expected_campaign_version') == c['version'], 'STALE_VERSION')
    point = next((x for x in points if x['id'] == b.get('point_id')), None)
    require(point, 'INVALID_REBIRTH_POINT')
    anchor = next((x['anchor'] for x in current['snapshots'] if x['point_id'] == point['id']), None)
    new = rebirth.restore(c['persona'], current, point['id'], secrets.randbits(64))
    new['run_index'] = len(c['runs']) + 1
    c['runs'].append(new)
    c['status'] = 'ACTIVE'
    c['version'] += 1
    new['campaign_id'] = c['id']
    new['planned'] = ai.propose_plan(c['persona'], new['planned'], new['start_age'], new['month_index'], anchor)
    new['story_text'] = ai.refine_story(
        c['persona'], [{**x, 'title': content.EVENT_BY_ID[x['card_id']]['title']} for x in new['planned']]
    )
    store.put_campaign(db, c)
    j = job(db, u['id'], 'REBIRTH', {'type': 'run', 'id': new['id'], 'href': f'/api/v1/runs/{new["id"]}'})
    return 202, queue_reply(j, c, new)


def run_command(op, db, c, r, b, p):
    if op == 'C06':
        return 200, engine.public_run(r)
    if op == 'C10' or op == 'C11':
        if op == 'C10':
            r['saved_at'] = engine.now()
            store.put_campaign(db, c)
        return 200, {
            'run_id': r['id'],
            'version': r['version'],
            'saved_at': r['saved_at'],
            'resume_route': f'/runs/{r["id"]}',
            'scene_id': r['scene_id'],
        }
    require(r['status'] != 'ENDED', 'ACTION_NOT_ALLOWED')
    if op == 'C07':
        payload_version(b, r)
        require(r['status'] == 'INITIAL_ALLOCATION' and r['scene_id'] == 'HOME', 'STATE_CONFLICT')
        r['status'] = 'EXPLORING'
        r['daily_phase'] = 'HOME_READY'
        reply = receipt(r)
    elif op == 'C08':
        payload_version(b, r)
        require(r['status'] in ('INITIAL_ALLOCATION', 'EXPLORING'), 'STATE_CONFLICT')
        target = b.get('scene_id')
        phase = r.get('daily_phase', 'HOME_READY')
        if b.get('complete_work') is True:
            require(
                r['status'] == 'EXPLORING' and r['scene_id'] == 'WORK' and target == 'WORK' and phase == 'WORKING',
                'ACTION_NOT_ALLOWED',
            )
            r['daily_phase'] = 'RETURN_HOME'
        else:
            available = next((s['connections'] for s in content.SCENES if s['id'] == r['scene_id']), [])
            require(target in available, 'SCENE_NOT_REACHABLE')
            if r['status'] == 'INITIAL_ALLOCATION':
                require(target in ('HOME', 'STREET', 'FINANCE'), 'ACTION_NOT_ALLOWED')
            else:
                destinations = {
                    'HOME_READY': ('HOME', 'STREET', 'FINANCE'),
                    'FREE_TIME': ('HOME', 'STREET', 'FINANCE'),
                    'WORK_REQUIRED': ('STREET', 'WORK'),
                    'WORKING': (),
                    'RETURN_HOME': ('STREET', 'HOME'),
                }
                require(target in destinations.get(phase, ()), 'ACTION_NOT_ALLOWED')
            r['scene_id'] = target
            if r['status'] == 'EXPLORING':
                if target == 'WORK':
                    r['daily_phase'] = 'WORKING'
                elif target == 'HOME' and phase in ('RETURN_HOME', 'FREE_TIME'):
                    r['daily_phase'] = 'HOME_READY'
                elif target == 'FINANCE':
                    r['daily_phase'] = 'FREE_TIME'
        reply = receipt(r)
    elif op == 'C09':
        payload_version(b, r)
        require(r['status'] in ('INITIAL_ALLOCATION', 'EXPLORING') and r['scene_id'] == 'HOME', 'ACTION_NOT_ALLOWED')
        option = b.get('lifestyle')
        require(option in ('BASIC', 'BALANCED', 'COMFORT'), 'VALIDATION_ERROR')
        old = r['lifestyle']
        r['lifestyle'] = option
        r['living_minor'] = (
            max(2000000, r['persona']['annual_income_minor'] // 28)
            * {'BASIC': 75, 'BALANCED': 100, 'COMFORT': 140}[option]
            // 100
        )
        offsets = {'BASIC': -4, 'BALANCED': 0, 'COMFORT': 5}
        r['quality'] = max(0, min(100, r['quality'] + offsets[option] - offsets[old]))
        reply = receipt(r)
    else:
        fail('NOT_FOUND')
    store.put_campaign(db, c)
    return 200, reply


def update_campaign_if_ended(c, r):
    if r['status'] == 'ENDED':
        c['version'] += 1
        if len(c['runs']) >= 3:
            c['status'] = 'COMPLETED'
            c['final_report'] = ai.refine_feedback(engine.final_report(c))
        else:
            c['status'] = 'AWAITING_REBIRTH'


def event_view(r, e):
    v = copy.deepcopy(e)
    cfg = content.HOSPITAL_EVENTS.get(e.get('card_id'))
    if cfg:
        cost = max(0, -(e.get('outcome') or {}).get('cash_delta_minor', 0)) if e.get('outcome') else None
        bills = [b for b in r['bills'] if b.get('event_id') == e['id']]
        funding = e.get('funding')
        outstanding = (
            max(0, funding['required_minor'] - funding['paid_minor'])
            if funding
            else sum(b['remaining_minor'] for b in bills)
        )
        claims = [c for c in r['claims'] if c['event_id'] == e['id']]
        v['hospital_visit'] = {k: cfg[k] for k in ('department', 'service', 'description', 'fee_label', 'mixed_cost')}
        v['hospital_visit'].update(
            cost_minor=cost,
            paid_minor=None if cost is None else max(0, cost - outstanding),
            outstanding_minor=None if cost is None else outstanding,
            claims_paid_minor=sum(c['paid_minor'] for c in claims),
            claims_pending_minor=sum(
                c['approved_minor'] - c['paid_minor'] for c in claims if c['status'] == 'APPROVED'
            ),
            bill_ids=[b['id'] for b in bills],
            payment_verified=cost is not None and outstanding == 0,
        )
    return v


def events_command(op, db, c, r, b, p, q):
    if op == 'D04':
        return 200, page(
            [
                event_view(r, e)
                for e in r['events']
                if (not q.get('status') or e['status'] == q['status']) and (not q.get('kind') or e['kind'] == q['kind'])
            ]
        )
    if op == 'D12':
        if q.get('from_date') and q.get('to_date'):
            require(q['from_date'] <= q['to_date'], 'INVALID_DATE_RANGE')
        return 200, page(
            [
                {
                    'id': e['id'],
                    'date': e['occurred_on'],
                    'title': e['title'],
                    'kind': 'EVENT',
                    'event_id': e['id'],
                    'snapshot_id': next(
                        (s['point_id'] for s in r['snapshots'] if s['at_index'] == e['at_index']), None
                    ),
                }
                for e in r['events']
                if (not q.get('from_date') or e['occurred_on'] >= q['from_date'])
                and (not q.get('to_date') or e['occurred_on'] <= q['to_date'])
            ]
        )
    if op == 'D01':
        payload_version(b, r)
        require(
            r['status'] == 'EXPLORING' and r['scene_id'] == 'HOME' and r.get('daily_phase') == 'HOME_READY',
            'ACTION_NOT_ALLOWED',
        )
        v = random.SystemRandom().randint(1, 6)
        r['advance'] = {
            'id': engine.uid(),
            'run_id': r['id'],
            'roll_value': v,
            'from_date': engine.sim_date(r),
            'target_date': f'{2026 + (r["month_index"] + v * 12) // 12}-{(r["month_index"] + v * 12) % 12 + 1:02d}-01',
            'status': 'PROCESSING',
            'blocking_event_id': None,
            'remaining_months': v * 12,
            'opening_snapshot': engine.asset_snapshot(r),
            'opening_state': engine.snapshot(r),
            'ledger_start': len(r['ledger']),
            'event_start': len(r['events']),
        }
        r['target_index'] = r['month_index'] + 12 * v
        r['status'] = 'ADVANCING'
        engine.next_step(r)
        engine.change(r)
        update_campaign_if_ended(c, r)
        store.put_campaign(db, c)
        return 201, copy.deepcopy(r['advance'])
    if op == 'D02':
        require(r['advance'] and r['advance']['id'] == p['advance_id'], 'NOT_FOUND')
        return 200, r['advance']
    if op == 'D03':
        payload_version(b, r)
        require(r['status'] == 'TURN_REVIEW' and r['advance']['id'] == p['advance_id'], 'STATE_CONFLICT')
        r['advance']['status'] = 'COMPLETED'
        if engine.age(r) >= 90:
            engine.end(r, 'AGE_COMPLETED')
        else:
            r['status'] = 'EXPLORING'
            r['daily_phase'] = 'WORK_REQUIRED' if r['employment_status'] == 'EMPLOYED' else 'HOME_READY'
        reply = receipt(r)
        update_campaign_if_ended(c, r)
        store.put_campaign(db, c)
        return 200, reply
    e = engine.event_by_id(r, p['event_id'])
    require(e, 'NOT_FOUND')
    if op == 'D05':
        return 200, event_view(r, e)
    if op == 'D08':
        require(r['status'] == 'FUNDING' and r['pending_event'] == e['id'], 'STATE_CONFLICT')
        return 200, engine.funding(r, e)
    payload_version(b, r)
    if op == 'D06':
        engine.decide(r, e['id'], b.get('choice_id'))
        reply = receipt(r)
    elif op == 'D07':
        engine.acknowledge(r, e['id'])
        reply = receipt(r)
    elif op == 'D09':
        require(r['status'] == 'FUNDING' and r['pending_event'] == e['id'], 'STATE_CONFLICT')
        f = engine.funding(r, e)
        require(f['can_pay'], 'INSUFFICIENT_FUNDS')
        engine.spend(r, f['remaining_minor'], 'MEDICAL', '必要治療費', e['id'])
        e['funding']['paid_minor'] += f['remaining_minor']
        e['status'] = 'RESOLVED'
        r['status'] = 'EVENT_RESULT'
        reply = receipt(r)
        e['balance_after_minor'] = r['balances']['cash_minor'] + r['balances']['savings_minor']
    elif op == 'D10':
        require(r['status'] == 'FUNDING', 'STATE_CONFLICT')
        f = engine.funding(r, e)
        require(f['can_wait'], 'WAIT_NOT_AVAILABLE')
        old = r['month_index']
        r['month_index'] += 1
        engine.monthly_market(r)
        engine.monthly_obligations(r)
        if r['status'] != 'ENDED':
            r['status'] = 'FUNDING'
            r['advance']['status'] = 'PAUSED_FUNDING'
        reply = receipt(r, notices=[f'等待期間結算了 {r["month_index"] - old} 個月。'])
    elif op == 'D11':
        require(r['status'] == 'FUNDING', 'STATE_CONFLICT')
        f = engine.funding(r, e)
        require(f['can_confirm_failure'], 'FUNDING_AVAILABLE')
        e['status'] = 'RESOLVED'
        engine.end(r, 'UNFUNDED_CRITICAL_CARE')
        reply = receipt(r)
    else:
        fail('NOT_FOUND')
    update_campaign_if_ended(c, r)
    store.put_campaign(db, c)
    return 200, reply


def finance_command(op, db, c, r, b, p, q):
    if op == 'E01':
        return 200, {
            'balances': engine.money(r),
            'holdings': [
                {
                    'stock_id': s['id'],
                    'quantity': r['holdings'].get(s['id'], 0),
                    'cost_basis_minor': r['holding_cost_minor'].get(s['id'], 0),
                    'market_value_minor': r['holdings'].get(s['id'], 0) * r['prices'][s['id']],
                }
                for s in content.STOCKS
            ],
            'term_deposits': r['terms'],
            'loans': r['loans'],
            'monthly_salary_minor': r['salary_minor'],
            'monthly_living_minor': r['living_minor'],
            'monthly_support_minor': r['support_minor'],
            'annual_premium_minor': sum(v['premium_minor'] for v in r['policies'] if v['status'] == 'ACTIVE'),
            'as_of': engine.sim_date(r),
            'run_version': r['version'],
        }
    if op == 'E02':
        return 200, [
            {**s, 'price_minor': r['prices'][s['id']], 'as_of': engine.sim_date(r), 'is_simulated': True}
            for s in content.STOCKS
        ]
    if op == 'E03':
        require(p['stock_id'] in content.STOCK_BY_ID, 'NOT_FOUND')
        if q.get('from_date') and q.get('to_date'):
            require(q['from_date'] <= q['to_date'], 'INVALID_DATE_RANGE')
        require(not q.get('to_date') or q['to_date'] <= engine.sim_date(r), 'INVALID_DATE_RANGE')
        return 200, page(
            [
                x
                for x in r['price_history'][p['stock_id']]
                if (not q.get('from_date') or x['date'] >= q['from_date'])
                and (not q.get('to_date') or x['date'] <= q['to_date'])
            ]
        )
    if op == 'E04':
        return 200, [
            {
                'id': 'SAVINGS',
                'kind': 'SAVINGS',
                'name': '活存（模擬）',
                'annual_rate_bps': 80,
                'term_months': 0,
                'minimum_minor': 0,
                'early_exit_rule': '活存可隨時提領，無提前解約限制。',
                'is_simulated': True,
            },
            *[
                {
                    'id': f'TERM_{n}',
                    'kind': 'TERM',
                    'name': f'{n} 個月定存（模擬）',
                    'annual_rate_bps': 220,
                    'term_months': n,
                    'minimum_minor': 1000000,
                    'early_exit_rule': '已計息打七折',
                    'is_simulated': True,
                }
                for n in (6, 12, 24, 36)
            ],
        ]
    if op == 'E05':
        return 200, [
            {
                'id': 'SIM_LOAN',
                'name': '信用借款（模擬）',
                'annual_rate_bps': 700,
                'max_term_months': 60,
                'max_principal_minor': r['salary_minor'] * 24,
                'eligibility_summary': '依收入及目前債務評估',
            }
        ]
    if op == 'E06':
        if q.get('from_date') and q.get('to_date'):
            require(q['from_date'] <= q['to_date'], 'INVALID_DATE_RANGE')
        return 200, page(
            [
                x
                for x in r['ledger']
                if (not q.get('category') or x['category'] == q['category'])
                and (not q.get('from_date') or x['sim_date'] >= q['from_date'])
                and (not q.get('to_date') or x['sim_date'] <= q['to_date'])
            ]
        )
    if op == 'E07':
        start = q.get('from_date')
        stop = q.get('to_date')
        require(start and stop and start <= stop <= engine.sim_date(r), 'INVALID_DATE_RANGE')
        entries = [x for x in r['ledger'] if start <= x['sim_date'] <= stop]
        prior = [v['net_worth_minor'] for v in r['networth_history'] if v['date'] < start]
        covered = [v['net_worth_minor'] for v in r['networth_history'] if v['date'] <= stop]
        opening = prior[-1] if prior else engine.money({**r, **r['initial']})['net_worth_minor']
        closing = covered[-1] if covered else opening
        return 200, {
            'from_date': start,
            'to_date': stop,
            'income_minor': sum(x['amount_minor'] for x in entries if x['cashflow_class'] == 'INCOME'),
            'expense_minor': -sum(x['amount_minor'] for x in entries if x['cashflow_class'] == 'EXPENSE'),
            'premium_minor': -sum(x['amount_minor'] for x in entries if x['category'] == 'PREMIUM'),
            'claims_paid_minor': sum(x['amount_minor'] for x in entries if x['category'] == 'CLAIM'),
            'net_worth_change_minor': closing - opening,
            'event_ids': [x['id'] for x in r['events'] if start <= x['occurred_on'] <= stop],
        }
    if op == 'E08':
        payload_version(b, r)
        quoted = finance.quote(r, b.get('action'), b.get('params', {}))
        r['quotes'].append(quoted)
        store.put_campaign(db, c)
        return 201, quoted
    if op == 'E09':
        quoted = finance.item(r['quotes'], p['quote_id'])
        require(quoted, 'NOT_FOUND')
        return 200, quoted
    if op == 'E10':
        payload_version(b, r)
        require(b.get('confirmed') is True, 'VALIDATION_ERROR')
        quoted = finance.item(r['quotes'], b.get('quote_id'))
        require(quoted, 'NOT_FOUND')
        transaction = finance.execute(r, quoted)
        res = transaction['result_resource']
        if res:
            res = {**res, 'href': f'/api/v1/runs/{r["id"]}/transactions/{transaction["id"]}'}
        reply = receipt(r, res)
        store.put_campaign(db, c)
        return 201, reply
    if op == 'E11':
        trans = finance.item(r['transactions'], p['transaction_id'])
        require(trans, 'NOT_FOUND')
        return 200, trans
    if op == 'E12':
        payload_version(b, r)
        require(r['status'] in ('EXPLORING', 'INITIAL_ALLOCATION') and r['scene_id'] == 'FINANCE', 'ACTION_NOT_ALLOWED')
        term = finance.item(r['terms'], p['term_deposit_id'])
        require(term and term['status'] == 'ACTIVE', 'NOT_FOUND')
        require(isinstance(b.get('auto_renew'), bool), 'VALIDATION_ERROR')
        term['auto_renew'] = b['auto_renew']
        reply = receipt(r)
        store.put_campaign(db, c)
        return 200, reply
    if op == 'E13':
        return 200, page([v for v in r['bills'] if not q.get('status') or v['status'] == q['status']])
    if op == 'E14':
        return 200, [
            {
                'code': x,
                'label': name,
                'monthly_living_minor': max(2000000, r['persona']['annual_income_minor'] // 28) * scale // 100,
                'quality_effect_summary': msg,
                'effective_from': engine.sim_date(r),
            }
            for x, name, scale, msg in (
                ('BASIC', '精簡', 75, '支出較低，生活品質可能受影響'),
                ('BALANCED', '均衡', 100, '基本生活方案'),
                ('COMFORT', '舒適', 140, '支出較高，生活體驗提升'),
            )
        ]
    fail('NOT_FOUND')


def insurance_command(op, db, c, r, b, p, q):
    if op == 'F01':
        return 200, [
            content.product_view(product)
            for product in content.PRODUCTS
            if not q.get('category') or product['category'] == q['category']
        ]
    if op == 'F02':
        product = content.PRODUCT_BY_ID.get(p['product_id'])
        require(product, 'NOT_FOUND')
        return 200, content.product_view(product)
    if op == 'F03':
        return 200, [x for x in r['policies'] if not q.get('status') or x['status'] == q['status']]
    if op == 'F04':
        policy = finance.item(r['policies'], p['policy_id'])
        require(policy, 'NOT_FOUND')
        return 200, policy
    if op == 'F05':
        payload_version(b, r)
        require(r['status'] in ('EXPLORING', 'INITIAL_ALLOCATION') and r['scene_id'] == 'FINANCE', 'ACTION_NOT_ALLOWED')
        policy = finance.item(r['policies'], p['policy_id'])
        require(policy and isinstance(b.get('auto_pay'), bool), 'VALIDATION_ERROR')
        policy['auto_pay'] = b['auto_pay']
        reply = receipt(r)
        store.put_campaign(db, c)
        return 200, reply
    if op == 'F06':
        needs = []
        for topic, cat, need in (
            ('醫療', 'MEDICAL', min(120000000, r['salary_minor'] * 10)),
            ('意外', 'ACCIDENT', min(100000000, r['salary_minor'] * 8)),
            ('重大疾病', 'CRITICAL_ILLNESS', r['salary_minor'] * 12),
            ('長照', 'LONG_TERM_CARE', r['salary_minor'] * 8),
            ('身故家庭扶養', 'LIFE', r['support_minor'] * 96),
        ):
            cover = sum(
                v['coverage_minor'] for v in r['policies'] if v['product_id'] == cat and v['status'] == 'ACTIVE'
            )
            needs.append(
                {
                    'topic': topic,
                    'estimated_need_minor': need,
                    'covered_minor': cover,
                    'gap_minor': max(0, need - cover),
                    'explanation': '依當前收入與扶養需求估算；沒有預知將來事件',
                }
            )
        annual = sum(x['premium_minor'] for x in r['policies'] if x['status'] in ('ACTIVE', 'WAITING', 'GRACE'))
        return 200, {
            'as_of': engine.sim_date(r),
            'needs': needs,
            'annual_premium_minor': annual,
            'premium_burden_ratio': round(annual / (r['salary_minor'] * 12), 3) if r['salary_minor'] > 0 else None,
            'liquidity_months': round(
                (r['balances']['cash_minor'] + r['balances']['savings_minor'])
                / max(1, r['living_minor'] + r['support_minor']),
                2,
            ),
        }
    if op == 'F09':
        return 200, page(
            [
                x
                for x in r['claims']
                if (not q.get('status') or x['status'] == q['status'])
                and (not q.get('event_id') or x['event_id'] == q['event_id'])
            ]
        )
    if op == 'F10':
        claim = finance.item(r['claims'], p['claim_id'])
        require(claim, 'NOT_FOUND')
        return 200, claim
    if op == 'F11':
        payload_version(b, r)
        claim = finance.item(r['claims'], p['claim_id'])
        require(claim and claim['status'] == 'NEEDS_INFO' and r['status'] != 'ENDED', 'STATE_CONFLICT')
        event = engine.event_by_id(r, claim['event_id'])
        provided = set(b.get('evidence_ids', []))
        require(provided and provided <= set(v['id'] for v in event['evidence']), 'EVIDENCE_INVALID')
        claim['required_evidence_ids'] = []
        assess_claim(r, event, claim)
        reply = receipt(r)
        store.put_campaign(db, c)
        return 200, reply
    event = engine.event_by_id(r, p['event_id'] if op == 'F07' else b.get('event_id'))
    require(event, 'NOT_FOUND')
    if op == 'F07':
        return 200, {
            'event_id': event['id'],
            'items': [
                {
                    'policy_id': policy['id'],
                    'benefit_code': policy['product_id'],
                    'eligible': policy['id'] in event.get('eligible_policy_ids', []),
                    'estimated_minor': min(
                        policy['coverage_minor'], max(0, -(event.get('outcome') or {}).get('cash_delta_minor', 0))
                    ),
                    'reason_codes': []
                    if policy['id'] in event.get('eligible_policy_ids', [])
                    else ['NOT_COVERED_AT_EVENT'],
                    'evidence_ids': [v['id'] for v in event['evidence']],
                }
                for policy in r['policies']
            ],
        }
    require(op == 'F08' and r['status'] in ('FUNDING', 'EVENT_PENDING', 'EVENT_RESULT', 'EXPLORING'), 'STATE_CONFLICT')
    payload_version(b, r)
    require(event.get('outcome') is not None, 'STATE_CONFLICT')
    policy = finance.item(r['policies'], b.get('policy_id'))
    require(policy, 'NOT_FOUND')
    require(b.get('benefit_code') in (None, policy['product_id']), 'VALIDATION_ERROR')
    require(
        not any(v['event_id'] == event['id'] and v['policy_id'] == policy['id'] for v in r['claims']), 'CLAIM_DUPLICATE'
    )
    claim = {
        'id': engine.uid(),
        'policy_id': policy['id'],
        'policy_product_id': policy['product_id'],
        'event_id': event['id'],
        'benefit_code': policy['product_id'],
        'status': 'SUBMITTED',
        'approved_minor': 0,
        'paid_minor': 0,
        'payable_index': None,
        'reason_codes': [],
        'explanation': '依事故時有效的保障與證據審查',
        'required_evidence_ids': [],
        'ledger_entry_ids': [],
        'recipient': 'PLAYER',
    }
    r['claims'].append(claim)
    provided = set(b.get('evidence_ids', []))
    valid = set(v['id'] for v in event['evidence'])
    require(provided <= valid, 'EVIDENCE_INVALID')
    if not provided:
        claim['status'] = 'NEEDS_INFO'
        claim['required_evidence_ids'] = list(valid)
    else:
        assess_claim(r, event, claim)
    reply = receipt(r, {'type': 'claim', 'id': claim['id'], 'href': f'/api/v1/runs/{r["id"]}/claims/{claim["id"]}'})
    store.put_campaign(db, c)
    return 201, reply


def assess_claim(r, e, claim):
    policy = finance.item(r['policies'], claim['policy_id'])
    cfg = content.PRODUCT_BY_ID[policy['product_id']]
    if policy['id'] not in e.get('eligible_policy_ids', []):
        claim['status'] = 'REJECTED'
        claim['reason_codes'] = ['NOT_COVERED_AT_EVENT']
        claim['explanation'] = '事故當時尚未生效、等待期內、已失效或保障種類不相符。'
        return
    gross = max(0, -(e.get('outcome') or {}).get('cash_delta_minor', 0))
    if cfg['benefit_type'] == 'REIMBURSEMENT':
        prior = sum(
            v['approved_minor']
            for v in r['claims']
            if v is not claim
            and v['event_id'] == e['id']
            and content.PRODUCT_BY_ID[v['policy_product_id']]['benefit_type'] == 'REIMBURSEMENT'
        )
        coverage = max(0, min(policy['coverage_minor'], gross - prior))
    else:
        coverage = policy['coverage_minor']
    claim['approved_minor'] = coverage
    claim['status'] = 'APPROVED'
    claim['payable_index'] = r['month_index'] + cfg['claim_delay_months']
    if cfg['claim_delay_months'] == 0:
        engine.income(r, coverage, 'CLAIM', '意外理賠實際入帳', e['id'])
        claim['status'] = 'PAID'
        claim['paid_minor'] = coverage
    claim['explanation'] = (
        '條款核准；未入帳時不能直接用於支付。' if claim['status'] == 'APPROVED' else '條款核准且款項已入帳。'
    )


def admin(op, db, b, u, p, q):
    if op == 'H09':
        return 200, {'accepted': True, 'message': 'alive'}
    if op == 'H10':
        db.execute('SELECT 1').fetchone()
        return 200, {'accepted': True, 'message': 'database ready'}
    require(u, 'UNAUTHENTICATED')
    require(u['role'] == 'CONTENT_ADMIN', 'FORBIDDEN')
    if op == 'H01':
        kind = b.get('kind')
        raw = b.get('content_json', '')
        require(
            kind in ('PERSONAS', 'EVENTS', 'PRODUCTS', 'RULESET')
            and isinstance(raw, str)
            and len(raw.encode()) < 2 * 1024 * 1024,
            'CONTENT_INVALID',
        )
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            fail('CONTENT_INVALID')
        require(isinstance(parsed, (dict, list)), 'CONTENT_INVALID')
        entry = {
            'id': engine.uid(),
            'kind': kind,
            'sha256': hashlib.sha256(raw.encode()).hexdigest(),
            'validation_errors': [],
        }
        db.execute('INSERT INTO admin_assets VALUES(?,?,?,?)', (entry['id'], kind, raw, entry['sha256']))
        db.execute(
            'INSERT INTO admin_audit VALUES(?,?,?,?)',
            (engine.uid(), u['id'], f'ASSET_UPLOAD:{entry["id"]}', engine.now()),
        )
        return 201, entry
    if op == 'H02':
        version = b.get('version')
        require(isinstance(version, str) and 1 <= len(version) <= 60, 'CONTENT_INVALID')
        assets = {}
        for field, kind in (
            ('persona_asset_id', 'PERSONAS'),
            ('event_asset_id', 'EVENTS'),
            ('product_asset_id', 'PRODUCTS'),
            ('ruleset_asset_id', 'RULESET'),
        ):
            x = db.execute('SELECT * FROM admin_assets WHERE id=?', (b.get(field),)).fetchone()
            require(x and x['kind'] == kind, 'CONTENT_INVALID')
            assets[field] = x['id']
        release = {
            'id': engine.uid(),
            'version': version,
            'status': 'DRAFT',
            'assets': assets,
            'validation_errors': [],
            'persona_count': 0,
            'stock_count': 5,
            'product_count': 0,
            'created_at': engine.now(),
        }
        try:
            db.execute('INSERT INTO admin_releases VALUES(?,?,?)', (release['id'], version, store.j(release)))
        except sqlite3.IntegrityError:
            fail('VERSION_EXISTS')
        db.execute(
            'INSERT INTO admin_audit VALUES(?,?,?,?)', (engine.uid(), u['id'], f'RELEASE_DRAFT:{version}', engine.now())
        )
        return 201, release
    if op == 'H03':
        return 200, page(
            [json.loads(x['body']) for x in db.execute('SELECT body FROM admin_releases ORDER BY version DESC')]
        )
    if op == 'H07':
        return 200, page(
            [
                json.loads(x['body'])
                for x in db.execute('SELECT body FROM jobs')
                if (not q.get('status') or json.loads(x['body'])['status'] == q['status'])
                and (not q.get('type') or json.loads(x['body'])['type'] == q['type'])
            ]
        )
    if op == 'H08':
        return 200, page(
            [
                dict(x)
                for x in db.execute('SELECT id,actor_id,action,created_at FROM admin_audit ORDER BY created_at DESC')
                if (not q.get('from_date') or x['created_at'][:10] >= q['from_date'])
                and (not q.get('to_date') or x['created_at'][:10] <= q['to_date'])
            ]
        )
    row = db.execute('SELECT * FROM admin_releases WHERE id=?', (p['release_id'],)).fetchone()
    require(row, 'NOT_FOUND')
    release = json.loads(row['body'])
    if op == 'H04':
        return 200, release
    if op == 'H05':
        require(release['status'] in ('DRAFT', 'VALIDATED'), 'STATE_CONFLICT')
        datasets = {}
        for field, key in (
            ('persona_asset_id', 'PERSONAS'),
            ('event_asset_id', 'EVENTS'),
            ('product_asset_id', 'PRODUCTS'),
            ('ruleset_asset_id', 'RULESET'),
        ):
            raw = db.execute('SELECT body FROM admin_assets WHERE id=?', (release['assets'][field],)).fetchone()
            datasets[key] = json.loads(raw['body'])
        errors = []
        if (
            not isinstance(datasets['PERSONAS'], list)
            or not datasets['PERSONAS']
            or any(
                not isinstance(x, dict)
                or not {'id', 'occupation', 'industry', 'annual_income_minor', 'commute_mode', 'family_history'}
                <= x.keys()
                or x['annual_income_minor'] <= 0
                for x in datasets['PERSONAS']
            )
        ):
            errors.append('人設欄位無效')
        if (
            not isinstance(datasets['EVENTS'], list)
            or not datasets['EVENTS']
            or any(
                not isinstance(x, dict) or not {'id', 'kind', 'condition', 'choices', 'effect'} <= x.keys()
                for x in datasets['EVENTS']
            )
        ):
            errors.append('事件結構無效')
        if (
            not isinstance(datasets['PRODUCTS'], list)
            or not datasets['PRODUCTS']
            or any(
                not isinstance(x, dict)
                or not {'id', 'category', 'coverage_options_minor', 'waiting_months', 'premium_rate_bps'} <= x.keys()
                for x in datasets['PRODUCTS']
            )
        ):
            errors.append('保單結構無效')
        if not isinstance(datasets['RULESET'], dict) or datasets['RULESET'].get('stock_count') != 5:
            errors.append('股票數量必須為 5')
        # The 1.0 engine supports curated built-in risk rules only. Fail closed for custom mechanics.
        if not errors:
            if (
                datasets['EVENTS'] != content.EVENTS
                or datasets['PRODUCTS'] != content.PRODUCTS
                or datasets['RULESET'] != {'stock_count': 5}
            ):
                errors.append('本版只允許更換人設池；事件、保險與規則引擎必須符合已審核發布內容。')
        release['validation_errors'] = errors
        release['persona_count'] = len(datasets['PERSONAS']) if isinstance(datasets['PERSONAS'], list) else 0
        release['product_count'] = len(datasets['PRODUCTS']) if isinstance(datasets['PRODUCTS'], list) else 0
        release['status'] = 'DRAFT' if errors else 'VALIDATED'
        db.execute('UPDATE admin_releases SET body=? WHERE id=?', (store.j(release), release['id']))
        return 200, release
    if op == 'H06':
        require(release['status'] == 'VALIDATED', 'CONTENT_NOT_VALIDATED')
        release['status'] = 'PUBLISHED'
        db.execute('UPDATE admin_releases SET body=? WHERE id=?', (store.j(release), release['id']))
        db.execute(
            'INSERT INTO admin_audit VALUES(?,?,?,?)',
            (engine.uid(), u['id'], f'RELEASE_PUBLISH:{release["version"]}', engine.now()),
        )
        return 200, release
    fail('NOT_FOUND')
