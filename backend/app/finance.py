"""Twelve finance actions; quote and execution share one calculator."""

from __future__ import annotations
from datetime import datetime, timedelta
from .engine import uid, now, age, sim_date, ledger, income, spend
from .content import STOCK_BY_ID, PRODUCT_BY_ID, CONTENT_VERSION, STOCK_TRADE_FEE_BPS

FIELDS = {
    'TRANSFER': {'amount_minor', 'direction'},
    'TERM_OPEN': {'amount_minor', 'term_months', 'auto_renew', 'source_account'},
    'TERM_CLOSE': {'term_deposit_id'},
    'STOCK_BUY': {'stock_id', 'quantity'},
    'STOCK_SELL': {'stock_id', 'quantity'},
    'LOAN_BORROW': {'amount_minor', 'term_months'},
    'LOAN_REPAY': {'loan_id', 'amount_minor'},
    'POLICY_BUY': {'product_id', 'coverage_minor', 'auto_pay', 'beneficiary_label'},
    'POLICY_SURRENDER': {'policy_id'},
    'POLICY_REINSTATE': {'policy_id'},
    'POLICY_PREMIUM_PAY': {'policy_id'},
    'BILL_PAY': {'bill_id', 'amount_minor'},
}


def item(items, id_):
    return next((v for v in items if v['id'] == id_), None)


def amount(params, key='amount_minor'):
    val = params.get(key)
    if isinstance(val, bool) or not isinstance(val, int) or val <= 0 or val > 100000000000:
        raise ValueError('VALIDATION_ERROR')
    return val


def normalize(action, params):
    if not isinstance(params, dict):
        raise ValueError('VALIDATION_ERROR')
    params = params.copy()
    if action == 'TRANSFER' and 'from_account' in params:
        f = params.pop('from_account')
        t = params.pop('to_account', None)
        params['direction'] = {('CASH', 'SAVINGS'): 'CASH_TO_SAVINGS', ('SAVINGS', 'CASH'): 'SAVINGS_TO_CASH'}.get(
            (f, t), 'INVALID'
        )
    if action == 'TERM_OPEN':
        if params.pop('product_id', None) not in (None, 'TERM', 'TERM_6', 'TERM_12', 'TERM_24', 'TERM_36'):
            raise ValueError('VALIDATION_ERROR')
        if params.get('source_account') not in (None, 'CASH', 'SAVINGS'):
            raise ValueError('VALIDATION_ERROR')
    if action == 'LOAN_BORROW':
        if params.pop('product_id', None) not in (None, 'SIM_LOAN'):
            raise ValueError('VALIDATION_ERROR')
        params.pop('claim_id', None)
    if action == 'POLICY_BUY':
        if params.pop('premium_period_months', 12) != 12:
            raise ValueError('VALIDATION_ERROR')
        beneficiary = params.get('beneficiary_label', '家人')
        if not isinstance(beneficiary, str) or len(beneficiary) > 40:
            raise ValueError('VALIDATION_ERROR')
        params['beneficiary_label'] = beneficiary
    return params


def quote(r, action, params):
    params = normalize(action, params)
    if action not in FIELDS or not isinstance(params, dict) or set(params) - FIELDS[action]:
        raise ValueError('VALIDATION_ERROR')
    if r['status'] not in ('INITIAL_ALLOCATION', 'EXPLORING', 'FUNDING'):
        raise ValueError('ACTION_NOT_ALLOWED')
    if r['status'] == 'FUNDING' and action in ('STOCK_BUY', 'TERM_OPEN', 'POLICY_BUY', 'POLICY_REINSTATE'):
        raise ValueError('ACTION_NOT_ALLOWED')
    if r['status'] != 'FUNDING' and r['scene_id'] != 'FINANCE':
        raise ValueError('ACTION_NOT_ALLOWED')
    if r['status'] == 'EXPLORING' and r.get('daily_phase', 'FREE_TIME') not in ('FREE_TIME', 'HOME_READY'):
        raise ValueError('ACTION_NOT_ALLOWED')
    liquid = r['balances']['cash_minor'] + r['balances']['savings_minor']
    effects = []
    reasons = []
    warnings = []
    delta = 0
    fee = 0
    coverage = []
    related = None

    def effect(account, d, description):
        effects.append({'account': account, 'delta_minor': d, 'available_on': sim_date(r), 'description': description})

    if action == 'TRANSFER':
        v = amount(params)
        direction = params.get('direction')
        if direction not in ('CASH_TO_SAVINGS', 'SAVINGS_TO_CASH'):
            raise ValueError('VALIDATION_ERROR')
        src, dst = (
            ('cash_minor', 'savings_minor') if direction == 'CASH_TO_SAVINGS' else ('savings_minor', 'cash_minor')
        )
        if r['balances'][src] < v:
            reasons.append('INSUFFICIENT_FUNDS')
        effect('CASH' if src == 'cash_minor' else 'SAVINGS', -v, '轉出')
        effect('CASH' if dst == 'cash_minor' else 'SAVINGS', v, '轉入')
    elif action == 'TERM_OPEN':
        v = amount(params)
        months = params.get('term_months')
        if months not in (6, 12, 24, 36):
            raise ValueError('VALIDATION_ERROR')
        source = params.get('source_account')
        available = r['balances']['cash_minor' if source == 'CASH' else 'savings_minor'] if source else liquid
        if available < v:
            reasons.append('INSUFFICIENT_FUNDS')
        effect(source or 'CASH', -v, '開立定存')
        effect('TERM', v, '本金；到期計息')
    elif action == 'TERM_CLOSE':
        t = item(r['terms'], params.get('term_deposit_id'))
        if not t or t['status'] != 'ACTIVE':
            reasons.append('NOT_FOUND')
        else:
            related = t['id']
            v = t['principal_minor'] + t['interest_minor'] * 7 // 10
            effect('TERM', -t['principal_minor'] - t['interest_minor'], '提前解約，利息只計70%')
            effect('CASH', v, '解約入帳')
            warnings.append('提早解約使已累積利息打七折。')
    elif action in ('STOCK_BUY', 'STOCK_SELL'):
        sid = params.get('stock_id')
        qty = params.get('quantity')
        if sid not in STOCK_BY_ID or isinstance(qty, bool) or not isinstance(qty, int) or qty < 1 or qty > 1000000:
            raise ValueError('VALIDATION_ERROR')
        related = sid
        gross = qty * r['prices'][sid]
        fee = max(100, gross * STOCK_TRADE_FEE_BPS // 10000)
        if action == 'STOCK_BUY':
            delta = -(gross + fee)
            if liquid < -delta:
                reasons.append('INSUFFICIENT_FUNDS')
            effect('CASH', delta, '含模擬交易費 0.3%')
            effect('STOCKS', gross, '持股市值')
        else:
            if r['holdings'].get(sid, 0) < qty:
                reasons.append('INSUFFICIENT_SHARES')
            delta = gross - fee
            effect('STOCKS', -gross, '出售目前持股')
            effect('CASH', delta, '扣交易費後入帳')
        warnings.append('價格只保證本確認單版本；股價與報酬皆可能下跌。')
    elif action == 'LOAN_BORROW':
        v = amount(params)
        months = params.get('term_months')
        if months not in (12, 24, 36, 60):
            raise ValueError('VALIDATION_ERROR')
        debt = sum(l['principal_minor'] for l in r['loans'] if l['status'] != 'PAID')
        if v + debt > r['salary_minor'] * 24 or r['salary_minor'] <= 0:
            reasons.append('LOAN_LIMIT_EXCEEDED')
        delta = v
        effect('CASH', v, '借款入帳')
        effect('LOAN', v, '同額本金負債；年息 7%')
    elif action == 'LOAN_REPAY':
        l = item(r['loans'], params.get('loan_id'))
        v = amount(params)
        if not l or l['status'] == 'PAID':
            reasons.append('NOT_FOUND')
        elif v > l['principal_minor'] + l['interest_minor']:
            reasons.append('AMOUNT_EXCEEDS_DUE')
        if liquid < v:
            reasons.append('INSUFFICIENT_FUNDS')
        delta = -v
        effect('CASH', -v, '提前償還')
        effect('LOAN', -v, '減少負債')
        related = params.get('loan_id')
    elif action == 'POLICY_BUY':
        pid = params.get('product_id')
        p = PRODUCT_BY_ID.get(pid)
        if not p:
            raise ValueError('VALIDATION_ERROR')
        cover = amount(params, 'coverage_minor')
        if cover not in p['coverage_options_minor']:
            raise ValueError('VALIDATION_ERROR')
        if age(r) > 75:
            reasons.append('AGE_NOT_ELIGIBLE')
        if any(x['product_id'] == pid and x['status'] in ('ACTIVE', 'WAITING', 'GRACE') for x in r['policies']):
            reasons.append('DUPLICATE_COVERAGE')
        # Simulated age adjustment; historical family risk is not a diagnosis.
        annual = cover * p['premium_rate_bps'] * (100 + max(0, age(r) - 40) * 2) // 1000000
        delta = -annual
        if liquid < annual:
            reasons.append('INSUFFICIENT_FUNDS')
        effect('CASH', delta, '首期年繳模擬保費')
        coverage.append(f'{p["name"]}，下個月生效，等待 {p["waiting_months"]} 個月。')
        warnings.append('這是虛構商品及費率，不是法國巴黎人壽的正式保單。')
        related = pid
    elif action in ('POLICY_SURRENDER', 'POLICY_REINSTATE', 'POLICY_PREMIUM_PAY'):
        p = item(r['policies'], params.get('policy_id'))
        if not p:
            reasons.append('NOT_FOUND')
        else:
            related = p['id']
            if action == 'POLICY_SURRENDER':
                if p['status'] in ('SURRENDERED', 'EXPIRED'):
                    reasons.append('ACTION_NOT_ALLOWED')
                coverage.append('解約後立即不再享有新的事故保障；本商品無解約金。')
            elif action == 'POLICY_REINSTATE':
                if p['status'] != 'LAPSED':
                    reasons.append('ACTION_NOT_ALLOWED')
                delta = -p['premium_minor']
            else:
                if p['status'] != 'GRACE':
                    reasons.append('ACTION_NOT_ALLOWED')
                delta = -p['premium_minor']
            if delta and liquid < -delta:
                reasons.append('INSUFFICIENT_FUNDS')
            if delta:
                effect('CASH', delta, '補繳模擬保費')
    elif action == 'BILL_PAY':
        b = item(r['bills'], params.get('bill_id'))
        v = amount(params)
        if not b or b['status'] == 'PAID':
            reasons.append('NOT_FOUND')
        elif v > b['remaining_minor']:
            reasons.append('AMOUNT_EXCEEDS_DUE')
        if liquid < v:
            reasons.append('INSUFFICIENT_FUNDS')
        delta = -v
        related = params.get('bill_id')
        effect('CASH', delta, '清償既有未付帳單')
    return {
        'id': uid(),
        'action': action,
        'params': params,
        'run_id': r['id'],
        'run_version': r['version'],
        'created_at': now(),
        'expires_at': (datetime.now().astimezone() + timedelta(minutes=5)).isoformat(timespec='seconds'),
        'cash_delta_minor': delta,
        'fees_minor': fee,
        'effects': effects,
        'coverage_changes': coverage,
        'effective_on': sim_date(r),
        'related_resource_id': related,
        'product_version': CONTENT_VERSION if action.startswith('POLICY') else None,
        'eligible': not reasons,
        'denial_reasons': reasons,
        'warnings': warnings,
        'summary': f'{action} 操作確認：請先檢查費用與風險。',
        'used': False,
        'expires_at_index': r['month_index'],
    }


def execute(r, q):
    if q['used']:
        raise ValueError('QUOTE_ALREADY_EXECUTED')
    if datetime.now().astimezone() > datetime.fromisoformat(q['expires_at']):
        raise ValueError('QUOTE_EXPIRED')
    if q['run_version'] != r['version'] or q['expires_at_index'] != r['month_index']:
        raise ValueError('QUOTE_STALE')
    if not q['eligible']:
        raise ValueError('QUOTE_NOT_ELIGIBLE')
    current = quote(r, q['action'], q['params'])
    if (
        not current['eligible']
        or current['cash_delta_minor'] != q['cash_delta_minor']
        or current['effects'] != q['effects']
    ):
        raise ValueError('QUOTE_STALE')
    action = q['action']
    p = q['params']
    resource = None
    amount_minor = abs(q['cash_delta_minor'])
    if action == 'TRANSFER':
        src, dst = (
            ('cash_minor', 'savings_minor') if p['direction'] == 'CASH_TO_SAVINGS' else ('savings_minor', 'cash_minor')
        )
        r['balances'][src] -= p['amount_minor']
        r['balances'][dst] += p['amount_minor']
        ledger(r, 'TRANSFER', -p['amount_minor'], cashflow='INTERNAL')
        ledger(r, 'TRANSFER', p['amount_minor'], cashflow='INTERNAL')
    elif action == 'TERM_OPEN':
        if p.get('source_account'):
            account = p['source_account']
            balance = 'cash_minor' if account == 'CASH' else 'savings_minor'
            r['balances'][balance] -= p['amount_minor']
            ledger(r, 'TRANSFER', -p['amount_minor'], account=account, cashflow='INTERNAL', description='定存開立')
        else:
            spend(r, p['amount_minor'], 'TRANSFER', '定存開立', cashflow='INTERNAL')
        resource = {'type': 'term_deposit', 'id': uid()}
        r['terms'].append(
            {
                'id': resource['id'],
                'product_id': 'TERM',
                'principal_minor': p['amount_minor'],
                'interest_minor': 0,
                'opened_on': sim_date(r),
                'matures_index': r['month_index'] + p['term_months'],
                'term_months': p['term_months'],
                'rate_bps': 220,
                'auto_renew': bool(p.get('auto_renew', False)),
                'status': 'ACTIVE',
            }
        )
    elif action == 'TERM_CLOSE':
        t = item(r['terms'], p['term_deposit_id'])
        v = t['principal_minor'] + t['interest_minor'] * 7 // 10
        t['status'] = 'CLOSED'
        r['balances']['cash_minor'] += t['principal_minor']
        ledger(r, 'PRINCIPAL', t['principal_minor'], cashflow='INTERNAL', description='解約本金返還')
        income(r, v - t['principal_minor'], 'INTEREST', '解約利息入帳')
        resource = {'type': 'term_deposit', 'id': t['id']}
    elif action == 'STOCK_BUY':
        spend(r, amount_minor - q['fees_minor'], 'TRANSFER', '購入股票本金', cashflow='INTERNAL')
        spend(r, q['fees_minor'], 'FEE', '股票交易費')
        sid = p['stock_id']
        r['holdings'][sid] = r['holdings'].get(sid, 0) + p['quantity']
        r['holding_cost_minor'][sid] = r['holding_cost_minor'].get(sid, 0) + p['quantity'] * r['prices'][sid]
        resource = {'type': 'stock', 'id': sid}
    elif action == 'STOCK_SELL':
        sid = p['stock_id']
        held = r['holdings'][sid]
        cost = r['holding_cost_minor'].get(sid, 0) * p['quantity'] // held
        r['holding_cost_minor'][sid] -= cost
        r['holdings'][sid] -= p['quantity']
        income_amount = p['quantity'] * r['prices'][sid]
        # Market value change is a capital gain/loss only once sold, and not gross sale proceeds.
        gain = income_amount - cost
        r['balances']['cash_minor'] += cost
        ledger(r, 'PRINCIPAL', cost, cashflow='INTERNAL', description='出售股票本金返還')
        if gain >= 0:
            income(r, gain, 'REALIZED_PNL', '已實現股票獲利')
        else:
            spend(r, -gain, 'REALIZED_PNL', '已實現股票損失', force_bill=False)
        spend(r, q['fees_minor'], 'FEE', '股票交易費')
        resource = {'type': 'stock', 'id': sid}
    elif action == 'LOAN_BORROW':
        income_amt = p['amount_minor']
        r['balances']['cash_minor'] += income_amt
        ledger(r, 'PRINCIPAL', income_amt, cashflow='INTERNAL', description='借入本金，不計收入')
        resource = {'type': 'loan', 'id': uid()}
        r['loans'].append(
            {
                'id': resource['id'],
                'product_id': 'SIM_LOAN',
                'original_minor': income_amt,
                'principal_minor': income_amt,
                'interest_minor': 0,
                'rate_bps': 700,
                'term_months': p['term_months'],
                'next_due_on': sim_date(r),
                'status': 'ACTIVE',
            }
        )
    elif action == 'LOAN_REPAY':
        l = item(r['loans'], p['loan_id'])
        v = p['amount_minor']
        interest = min(l['interest_minor'], v)
        spend(r, interest, 'INTEREST', '清償借款利息')
        spend(r, v - interest, 'PRINCIPAL', '清償借款本金', cashflow='INTERNAL')
        l['interest_minor'] -= interest
        l['principal_minor'] -= v - interest
        if l['principal_minor'] == 0 and l['interest_minor'] == 0:
            l['status'] = 'PAID'
        resource = {'type': 'loan', 'id': l['id']}
    elif action == 'POLICY_BUY':
        product = PRODUCT_BY_ID[p['product_id']]
        spend(r, amount_minor, 'PREMIUM', '模擬首期保費')
        resource = {'type': 'policy', 'id': uid()}
        r['policies'].append(
            {
                'id': resource['id'],
                'product_id': product['id'],
                'product_version': CONTENT_VERSION,
                'coverage_minor': p['coverage_minor'],
                'premium_minor': amount_minor,
                'premium_period_months': 12,
                'status': 'WAITING',
                'issued_on': sim_date(r),
                'coverage_from_index': r['month_index'] + 1,
                'next_premium_index': r['month_index'] + 12,
                'auto_pay': bool(p.get('auto_pay', True)),
                'cash_value_minor': 0,
                'beneficiary_label': p.get('beneficiary_label', '家人'),
            }
        )
    elif action == 'POLICY_SURRENDER':
        policy = item(r['policies'], p['policy_id'])
        policy['status'] = 'SURRENDERED'
        resource = {'type': 'policy', 'id': policy['id']}
    elif action in ('POLICY_REINSTATE', 'POLICY_PREMIUM_PAY'):
        policy = item(r['policies'], p['policy_id'])
        spend(r, amount_minor, 'PREMIUM', '補繳保費')
        policy['status'] = 'WAITING' if action == 'POLICY_REINSTATE' else 'ACTIVE'
        if action == 'POLICY_REINSTATE':
            policy['coverage_from_index'] = r['month_index'] + 1
        policy['next_premium_index'] = r['month_index'] + 12
        for b in r['bills']:
            if b.get('related_policy_id') == policy['id'] and b['status'] != 'PAID':
                b['remaining_minor'] = 0
                b['status'] = 'PAID'
        resource = {'type': 'policy', 'id': policy['id']}
    elif action == 'BILL_PAY':
        bill = item(r['bills'], p['bill_id'])
        spend(r, p['amount_minor'], 'BILL_PAYMENT', '清償之前已入帳的應付款', cashflow='INTERNAL')
        bill['remaining_minor'] -= p['amount_minor']
        bill['status'] = 'PAID' if bill['remaining_minor'] == 0 else 'OPEN'
        resource = {'type': 'bill', 'id': bill['id']}
    q['used'] = True
    tx = {
        'id': uid(),
        'quote_id': q['id'],
        'action': action,
        'status': 'COMPLETED',
        'ledger_entry_ids': [x['id'] for x in r['ledger'][-4:]],
        'result_resource': resource,
        'created_at': now(),
    }
    r['transactions'].append(tx)
    return tx
