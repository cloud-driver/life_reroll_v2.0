"""Run commands: scene moves, work and month settlement (C*)."""

from __future__ import annotations

from .. import store, engine, content
from .common import fail, require, payload_version, receipt


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
