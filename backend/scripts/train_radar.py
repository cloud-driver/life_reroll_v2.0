"""Reproducible offline CART training on independent game-engine scenarios.

Run from backend: .venv/bin/python scripts/train_radar.py
No player records, network, future seeds or external ML dependencies.
"""

import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import engine, content, finance, radar, scenarios


def sample(index, split):
    rng = random.Random(f'radar-data-v1:{split}:{index}')
    p = rng.choice(content.PERSONAS)
    r = engine.create_run(p, rng.getrandbits(64), rng.randint(25, 30))
    r['month_index'] = rng.randint(0, (94 - r['start_age']) * 12)
    r['lifestyle'] = rng.choice(['BASIC', 'BALANCED', 'COMFORT'])
    r['living_minor'] = (
        max(2000000, p['annual_income_minor'] // 28)
        * {'BASIC': 75, 'BALANCED': 100, 'COMFORT': 140}[r['lifestyle']]
        // 100
    )
    r['support_minor'] = rng.choice([0, 0, r['living_minor'] // 2, r['living_minor']])
    base = r['living_minor'] + r['support_minor']
    r['salary_minor'] = 0 if engine.age(r) >= 65 else r['salary_minor'] * rng.choice([0, 75, 100, 100, 150, 200]) // 100
    r['employment_status'] = 'RETIRED' if engine.age(r) >= 65 else 'EMPLOYED'
    r['balances']['cash_minor'] = int(base * 10 ** rng.uniform(-1.5, 2.2))
    r['scene_id'] = 'FINANCE'
    r['status'] = 'EXPLORING'
    for pid in rng.sample(['MEDICAL', 'ACCIDENT', 'CRITICAL_ILLNESS', 'LONG_TERM_CARE'], rng.randint(0, 3)):
        q = finance.quote(
            r,
            'POLICY_BUY',
            {
                'product_id': pid,
                'coverage_minor': content.PRODUCT_BY_ID[pid]['coverage_options_minor'][0],
                'auto_pay': True,
            },
        )
        if q['eligible']:
            finance.execute(r, q)
            r['policies'][-1]['coverage_from_index'] -= rng.choice([0, 8, 20])
    if r['salary_minor'] and rng.random() < 0.35:
        q = finance.quote(
            r,
            'LOAN_BORROW',
            {'amount_minor': r['salary_minor'] * rng.randint(2, 20), 'term_months': rng.choice([12, 24, 60])},
        )
        if q['eligible']:
            finance.execute(r, q)
        r['balances']['cash_minor'] = int(base * 10 ** rng.uniform(-1.5, 1.3))
    for kind in rng.sample(['TERM_OPEN', 'STOCK_BUY'], rng.randint(0, 2)):
        amount = r['balances']['cash_minor'] * rng.randint(1, 8) // 10
        if amount < 1000000:
            continue
        params = (
            {'amount_minor': amount, 'term_months': 36, 'auto_renew': True}
            if kind == 'TERM_OPEN'
            else {'stock_id': rng.choice(content.STOCKS)['id'], 'quantity': max(1, amount // 10000)}
        )
        q = finance.quote(r, kind, params)
        if q['eligible']:
            finance.execute(r, q)
    x = radar.features(r)
    v = scenarios.rollout(scenarios.hypothetical(r, rng.getrandbits(64)), months=12)
    return x, int(v['shortage'])


def train(rows, depth=0):
    n = len(rows)
    positive = sum(y for _, y in rows)
    leaf = {'probability': round((positive + 1) / (n + 2), 5), 'samples': n}
    if depth >= 6 or n < 40 or positive in (0, n):
        return leaf
    best = None
    loss = n
    for f in range(len(radar.FEATURES)):
        ordered = sorted((x[f], y) for x, y in rows)
        lp = 0
        for i in range(n - 1):
            lp += ordered[i][1]
            ln = i + 1
            rn = n - ln
            if ln < 20 or rn < 20 or ordered[i][0] == ordered[i + 1][0]:
                continue
            score = 2 * lp * (ln - lp) / ln + 2 * (positive - lp) * (rn - positive + lp) / rn
            if score < loss:
                loss = score
                best = (f, (ordered[i][0] + ordered[i + 1][0]) / 2)
    if best is None:
        return leaf
    f, t = best
    left = [r for r in rows if r[0][f] <= t]
    right = [r for r in rows if r[0][f] > t]
    return {'feature': f, 'threshold': t, 'left': train(left, depth + 1), 'right': train(right, depth + 1)}


if __name__ == '__main__':
    start = time.monotonic()
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2400
    training = [sample(i, 'train') for i in range(n)]
    validation = [sample(i, 'validation') for i in range(max(400, n // 3))]
    tree = train(training)
    tp = tn = fp = fn = 0
    brier = 0
    for x, y in validation:
        p = radar.predict(x, tree)
        brier += (p - y) ** 2
        if p >= 0.5 and y:
            tp += 1
        elif p >= 0.5:
            fp += 1
        elif y:
            fn += 1
        else:
            tn += 1
    metadata = {
        'training_samples': n,
        'validation_samples': len(validation),
        'horizon_months': 12,
        'label': 'one-year funding gap, unpaid bill or delinquent loan under the documented scenario policy',
        'sensitivity': round(tp / max(1, tp + fn), 4),
        'specificity': round(tn / max(1, tn + fp), 4),
        'balanced_accuracy': round((tp / max(1, tp + fn) + tn / max(1, tn + fp)) / 2, 4),
        'brier_score': round(brier / len(validation), 4),
        'confusion': {'tp': tp, 'tn': tn, 'fp': fp, 'fn': fn},
        'split': 'independent synthetic state and future seeds; validation never used for fitting',
        'scenario_version': scenarios.VERSION,
        'scope': 'synthetic game scenarios only; not real-world financial prediction',
    }
    artifact = {
        'version': 'radar-cart-20261023-2',
        'content_version': content.CONTENT_VERSION,
        'features': radar.FEATURES,
        'metadata': metadata,
        'tree': tree,
    }
    radar.MODEL_PATH.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'metadata': metadata, 'seconds': round(time.monotonic() - start, 2)}, ensure_ascii=False))
