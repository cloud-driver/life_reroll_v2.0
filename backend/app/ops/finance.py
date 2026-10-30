"""Cash, savings, stocks, term deposits and loans (E*)."""

from __future__ import annotations

from .. import store, engine, finance, content
from .common import fail, require, page, payload_version, receipt


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
