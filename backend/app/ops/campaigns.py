"""Campaign-level commands: rebirth, reports and exports (C04/C05, G02-G06)."""

from __future__ import annotations

import copy
import json
import random
import secrets

from .. import store, engine, content, ai, rebirth
from .common import require, job, queue_reply, public_campaign


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


def create_campaign(db, u):
    """C01: pick a persona from the newest published release and plan the first run."""
    require(u['verified'], 'EMAIL_NOT_VERIFIED')
    require(
        not db.execute("SELECT 1 FROM campaigns WHERE user_id=? AND status!='COMPLETED'", (u['id'],)).fetchone(),
        'ACTIVE_CAMPAIGN_EXISTS',
    )
    release = store.published_release(db)
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
    story = ai.refine_story(persona, [{**x, 'title': content.EVENT_BY_ID[x['card_id']]['title']} for x in r['planned']])
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
    db.execute('INSERT INTO campaigns VALUES(?,?,?,?,?)', (c['id'], u['id'], c['status'], store.j(c), c['created_at']))
    j = job(db, u['id'], 'LIFE_PLAN', {'type': 'run', 'id': r['id'], 'href': f'/api/v1/runs/{r["id"]}'})
    return 202, queue_reply(j, c, r)
