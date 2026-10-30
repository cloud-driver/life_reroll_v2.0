"""Dispatch for the documented /api/v1 operations. API paths are registered in main.py.

Each operation id's letter selects a domain module in app/ops (A accounts, B basics,
C campaigns/runs, D events, E finance, F insurance, G reports, H admin).
"""

from __future__ import annotations

import json

from . import store, engine
from .ops.accounts import account
from .ops.admin import admin
from .ops.basics import basics
from .ops.campaigns import campaign_command, create_campaign
from .ops.common import (
    email_bypass,
    fail,
    get_user,
    owned_campaign,
    owned_run,
    page,
    public_campaign,
    queue_reply,
    require,
    t_hash,
    user_view,
    verify_csrf,
)
from .ops.events import events_command
from .ops.finance import finance_command
from .ops.insurance import assess_claim, insurance_command
from .ops.runs import run_command

# Re-exported for routers, insights and tests that address helpers as handlers.<name>.
__all__ = [
    'assess_claim',
    'email_bypass',
    'events_command',
    'get_user',
    'owned_run',
    'result',
    't_hash',
    'user_view',
    'verify_csrf',
]


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
        return create_campaign(db, u)
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
