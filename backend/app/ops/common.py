"""Helpers shared by every operation handler: errors, auth, paging and receipts."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import secrets
from datetime import datetime

from .. import store, engine, mail


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
        '''SELECT users.*,sessions.id AS sid,sessions.csrf AS csrf,sessions.created_at AS session_created_at
        FROM sessions JOIN users ON users.id=sessions.user_id WHERE sessions.token_hash=? AND sessions.revoked=0''',
        (t_hash(token),),
    ).fetchone()
    if not row:
        return None, None
    if datetime.now().astimezone() - datetime.fromisoformat(row['session_created_at']) > store.SESSION_TTL:
        return None, None
    return row, row['sid']


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
