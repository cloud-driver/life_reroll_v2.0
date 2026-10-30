"""Dice advances and life events (D*)."""

from __future__ import annotations

import copy
import random

from .. import store, engine, content, ai
from .common import fail, require, page, payload_version, receipt


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
