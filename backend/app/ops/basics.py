"""Public bootstrap and content catalogue operations (B*)."""

from __future__ import annotations

import json

from .. import store, engine, content, qwen, legal
from .common import fail, email_bypass, require, page


def basics(op, db, b, u, p, q):
    published = store.published_release(db)
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
