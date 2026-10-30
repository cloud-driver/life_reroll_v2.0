"""Simulated policies and claims (F*)."""

from __future__ import annotations

from .. import store, engine, finance, content
from .common import require, page, payload_version, receipt


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
