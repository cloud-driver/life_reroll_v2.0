"""Small trained decision tree plus explicit, current-state warning facts."""

import json
from functools import lru_cache
from pathlib import Path
from . import engine, content

FEATURES = [
    'reserve_months',
    'income_ratio',
    'loan_payment_ratio',
    'premium_ratio',
    'bill_ratio',
    'age',
    'medical_months',
    'critical_months',
    'locked_months',
    'stock_months',
    'waiting_policies',
    'negative_years',
]
MODEL_PATH = Path(__file__).resolve().parents[1] / 'data/radar-model.json'


def metrics(r):
    m = engine.money(r)
    living = max(1, r['living_minor'] + r['support_minor'])
    loans = sum(
        min(l['principal_minor'], l['original_minor'] // max(1, l['term_months']))
        + l['interest_minor']
        + l['principal_minor'] * l['rate_bps'] // 120000
        for l in r['loans']
        if l['status'] != 'PAID'
    )
    premium = sum(p['premium_minor'] for p in r['policies'] if p['status'] in ('ACTIVE', 'WAITING', 'GRACE'))
    liquid = m['cash_minor'] + m['savings_minor']
    burden = living + loans + premium // 12
    return {
        'liquidity_minor': liquid,
        'monthly_burden_minor': burden,
        'monthly_income_minor': r['salary_minor'],
        'reserve_months': round(liquid / max(1, burden), 1),
        'monthly_gap_minor': max(0, burden - r['salary_minor']),
        'bill_minor': m['bill_minor'],
        'loan_monthly_minor': loans,
        'annual_premium_minor': premium,
    }


def features(r):
    a = metrics(r)
    base = max(1, r['living_minor'] + r['support_minor'])
    m = engine.money(r)

    def cover(pid):
        return (
            sum(
                p['coverage_minor']
                for p in r['policies']
                if p['product_id'] == pid
                and p['status'] in ('ACTIVE', 'GRACE')
                and r['month_index'] >= p['coverage_from_index'] + content.PRODUCT_BY_ID[pid]['waiting_months']
            )
            / base
        )

    raw = [
        a['liquidity_minor'] / base,
        r['salary_minor'] / base,
        a['loan_monthly_minor'] / base,
        a['annual_premium_minor'] / 12 / base,
        m['bill_minor'] / base,
        engine.age(r),
        cover('MEDICAL'),
        cover('CRITICAL_ILLNESS'),
        m['term_minor'] / base,
        m['stocks_minor'] / base,
        sum(p['status'] == 'WAITING' for p in r['policies']),
        r['negative_years'],
    ]
    return [round(max(0, min(120, v)), 5) for v in raw]


@lru_cache(maxsize=1)
def model():
    value = json.loads(MODEL_PATH.read_text())
    if value['features'] != FEATURES or value['content_version'] != content.CONTENT_VERSION:
        raise ValueError('MODEL_UNAVAILABLE')
    return value


def predict(values, tree):
    while 'feature' in tree:
        tree = tree['left'] if values[tree['feature']] <= tree['threshold'] else tree['right']
    return tree['probability']


def read(r):
    a = metrics(r)
    facts = []
    method = 'MODEL'
    metadata = None
    try:
        artifact = model()
        p = predict(features(r), artifact['tree'])
        metadata = artifact['metadata']
        version = artifact['version']
        level = 'HIGH' if p >= 0.5 else 'WATCH' if p >= 0.15 else 'LOW'
    except (OSError, ValueError, KeyError, TypeError):
        method = 'RULES'
        version = 'current-state-fallback'
        level = 'WATCH'
    if a['bill_minor'] or any(l['status'] == 'DELINQUENT' for l in r['loans']):
        level = 'HIGH'
        facts.append('目前已有未付帳單或逾期貸款，先確認到期義務。')
    if r['status'] == 'FUNDING':
        level = 'HIGH'
        facts.insert(0, '必要治療正在籌資，請先查看事件與理賠。')
    if a['monthly_gap_minor']:
        facts.append('目前每月收入低於生活、扶養、貸款與平均保費支出。')
    elif engine.age(r) < 65 and engine.age(r) >= 64:
        facts.append('接近 65 歲退休，遊戲中的工作收入將停止。')
    elif a['reserve_months'] < 6:
        facts.append('可用資金不足目前固定支出的六個月，突發費用可能需要籌資。')
    else:
        facts.append('目前可用資金能支應至少六個月的固定支出。')
    if any(p['status'] in ('WAITING', 'GRACE') for p in r['policies']):
        facts.append('部分保單仍在等待期或寬限期，事故時可能無法給付。')
    elif engine.money(r)['stocks_minor'] + engine.money(r)['term_minor'] > a['liquidity_minor']:
        facts.append('較多資金放在股票或定存，臨時變現可能有成本。')
    else:
        facts.append('尚未入帳的理賠與投資資產，都不算可立即支付的資金。')
    return {
        'run_id': r['id'],
        'run_version': r['version'],
        'as_of': engine.sim_date(r),
        'level': level,
        'facts': facts[:2],
        'metrics': a,
        'method': method,
        'model_version': version,
        'validation': metadata,
        'horizon_months': 12,
    }
