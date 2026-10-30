"""Scenario correctness, isolation and asynchronous insight lifecycle."""

import copy
import json
import time
import uuid
import pytest
from fastapi.testclient import TestClient
from app import engine, store, content, finance, rebirth, radar, scenarios, insights
from app.main import app
from test_game import game


def ended(game):
    game.auth()
    c, r = game.new()
    with store.tx() as db:
        c = store.get_campaign(db, c['id'])
        raw = c['runs'][-1]
        raw['snapshots'] = [
            {
                'point_id': engine.uid(),
                'at_index': 24,
                'title': content.EVENT_BY_ID['CH07']['title'],
                'anchor': {'at_index': 24, 'card_id': 'CH07', 'anchor': False},
                'state': engine.snapshot(raw),
            }
        ]
        engine.end(raw, 'AGE_COMPLETED')
        c['status'] = 'AWAITING_REBIRTH'
        c['version'] += 1
        store.put_campaign(db, c)
    return c, copy.deepcopy(raw)


def start(game, c, r, key=None):
    return game.call(
        'POST',
        f'/runs/{r["id"]}/branches',
        {'expected_version': r['version'], 'expected_campaign_version': c['version']},
        202,
        key=key,
    )[0]


def wait(game, job):
    deadline = time.monotonic() + 15
    while job['status'] in insights.ACTIVE:
        assert time.monotonic() < deadline, job
        time.sleep(0.02)
        job = game.call('GET', f'/insights/jobs/{job["id"]}', status=200)[0]
    return job


def test_radar_current_facts_no_future_leak_and_missing_model(game, monkeypatch):
    game.auth()
    c, r = game.new()
    value, _ = game.call('GET', f'/runs/{r["id"]}/radar', status=200)
    assert value['method'] == 'MODEL' and value['run_version'] == r['version'] and len(value['facts']) == 2
    assert value['validation']['balanced_accuracy'] >= 0.85
    with store.tx(read_only=True) as db:
        raw = store.get_campaign(db, c['id'])['runs'][-1]
    before = radar.read(raw)
    changed = copy.deepcopy(raw)
    changed.update(seed=9, planned=[{'secret_future': 'never expose'}], story_text={'secret': 'story'})
    assert radar.read(changed) == before
    assert not {'seed', 'planned', 'persona', 'snapshots'} & value.keys()
    changed['bills'].append({'status': 'OVERDUE', 'remaining_minor': 10000, 'related_loan_id': None})
    assert radar.read(changed)['level'] == 'HIGH'
    monkeypatch.setattr(radar, 'model', lambda: (_ for _ in ()).throw(OSError()))
    assert radar.read(changed)['method'] == 'RULES' and radar.read(changed)['level'] == 'HIGH'


def test_async_jobs_idempotency_cache_privacy_and_save_immutability(game):
    c, r = ended(game)
    before = store.j(c)
    key = str(uuid.uuid4())
    t = time.monotonic()
    job = start(game, c, r, key)
    assert (
        time.monotonic() - t < 1 and start(game, c, r, key)['id'] == job['id'] and start(game, c, r)['id'] == job['id']
    )
    game.call(
        'POST',
        f'/runs/{r["id"]}/branches',
        {'expected_version': r['version'] + 1, 'expected_campaign_version': c['version']},
        409,
        key=key,
    )
    job = wait(game, job)
    assert job['status'] == 'COMPLETE' and job['completed_points'] == job['total_points'] == 2
    assert all(v['samples'] == 24 for x in job['results'] for v in x['variants'].values())
    assert not any(k.startswith('_') for k in job) and all(set(x) == {'point_id', 'variants'} for x in job['results'])
    assert (
        game.call('GET', f'/runs/{r["id"]}/branches', status=200)[0]['id'] == job['id']
        and start(game, c, r)['id'] == job['id']
    )
    with store.tx(read_only=True) as db:
        assert store.j(store.get_campaign(db, c['id'])) == before


def test_only_ended_current_lives_allow_branches(game):
    game.auth()
    c, r = game.new()
    body = {'expected_version': r['version'], 'expected_campaign_version': c['version']}
    game.call('GET', f'/runs/{r["id"]}/branches', status=409)
    game.call('POST', f'/runs/{r["id"]}/branches', body, 409)
    with store.tx() as db:
        c = store.get_campaign(db, c['id'])
        engine.end(c['runs'][-1], 'AGE_COMPLETED')
        c['status'] = 'COMPLETED'
        store.put_campaign(db, c)
    game.call('GET', f'/runs/{r["id"]}/branches', status=409)
    game.call('POST', f'/runs/{r["id"]}/branches', body, 409)


def test_analysis_auth_csrf_body_validation_and_foreign_owner(game, monkeypatch):
    c, r = ended(game)
    monkeypatch.setattr(insights, 'submit', lambda task: None)
    job = start(game, c, r)
    assert TestClient(app).get(f'/api/v1/runs/{r["id"]}/radar').status_code == 401
    assert game.client.post(f'/api/v1/insights/jobs/{job["id"]}/cancel', json={}).status_code == 403
    game.call(
        'POST', f'/runs/{r["id"]}/branches', {'expected_version': True, 'expected_campaign_version': c['version']}, 409
    )
    game.call(
        'POST',
        f'/runs/{r["id"]}/branches',
        {'expected_version': r['version'], 'expected_campaign_version': c['version'], 'seed': 3},
        422,
    )
    game.call(
        'POST',
        f'/runs/{r["id"]}/branches',
        {'expected_version': r['version'], 'expected_campaign_version': c['version']},
        400,
        key='short',
    )
    assert (
        game.client.post(
            f'/api/v1/runs/{r["id"]}/branches', content='[', headers={'x-csrf-token': game.csrf}
        ).status_code
        == 422
    )
    game.auth('other@example.com')
    game.call('GET', f'/runs/{r["id"]}/branches', status=404)
    game.call('GET', f'/insights/jobs/{job["id"]}', status=404)
    game.call('POST', f'/insights/jobs/{job["id"]}/cancel', {}, 404)


def test_cancel_resume_restart_and_obsolete_worker(game, monkeypatch):
    c, r = ended(game)
    tasks = []
    monkeypatch.setattr(insights, 'submit', tasks.append)
    job = start(game, c, r)
    result = scenarios.compare(c['persona'], r, rebirth.points(r)[0], [1, 2])
    task = tasks[0]
    insights.update(task[0], job['id'], task[2], lambda j: j.update(results=[result], completed_points=1))
    stopped = game.call('POST', f'/insights/jobs/{job["id"]}/cancel', {}, 200)[0]
    assert stopped['status'] == 'CANCELLED' and stopped['completed_points'] == 1
    assert insights.update(task[0], job['id'], task[2], lambda j: j.update(status='COMPLETE')) is None
    resumed = start(game, c, r)
    assert resumed['id'] == job['id'] and resumed['completed_points'] == 1
    assert insights.update(task[0], job['id'], task[2], lambda j: j.update(status='COMPLETE')) is None
    with store.tx() as db:
        raw = json.loads(db.execute('SELECT body FROM insight_jobs WHERE id=?', (job['id'],)).fetchone()[0])
        raw['_instance'] = 'old-process'
        db.execute('UPDATE insight_jobs SET body=? WHERE id=?', (store.j(raw), job['id']))
    recovered = game.call('GET', f'/insights/jobs/{job["id"]}', status=200)[0]
    assert recovered['status'] == 'FAILED' and recovered['completed_points'] == 1
    start(game, c, r)
    insights.work(*tasks[-1])
    completed = game.call('GET', f'/insights/jobs/{job["id"]}', status=200)[0]
    assert completed['status'] == 'COMPLETE' and completed['results'][0] == result


def test_owner_concurrency_failure_and_account_erasure(game, monkeypatch):
    c, r = ended(game)
    tasks = []
    monkeypatch.setattr(insights, 'submit', tasks.append)
    job = start(game, c, r)
    with store.tx() as db:
        c['version'] += 1
        store.put_campaign(db, c)
    game.call(
        'POST',
        f'/runs/{r["id"]}/branches',
        {'expected_version': r['version'], 'expected_campaign_version': c['version']},
        429,
    )
    monkeypatch.setattr(scenarios, 'compare', lambda *args: (_ for _ in ()).throw(RuntimeError('private detail')))
    insights.work(*tasks[0])
    failed = game.call('GET', f'/insights/jobs/{job["id"]}', status=200)[0]
    assert failed['status'] == 'FAILED' and 'private detail' not in json.dumps(failed)
    game.call(
        'POST',
        '/me/deletion-requests',
        {'current_password': '123456789Strong!', 'confirmation': 'DELETE_MY_ACCOUNT'},
        202,
    )
    with store.tx(read_only=True) as db:
        assert (
            db.execute('SELECT COUNT(*) FROM insight_jobs').fetchone()[0] == 0
            and db.execute('SELECT COUNT(*) FROM insight_requests').fetchone()[0] == 0
        )
    assert insights.update(tasks[0][0], job['id'], tasks[0][2], lambda j: j.update(status='COMPLETE')) is None


def test_restore_anchor_once_and_unchanged_source():
    r = engine.create_run(content.PERSONAS[0], 123, 28)
    r['month_index'] = 17
    r['balances']['cash_minor'] = 1000000
    r['snapshots'] = [
        {
            'point_id': 'anchor',
            'at_index': 18,
            'title': '固定事件',
            'anchor': {'at_index': 18, 'card_id': 'CH07', 'anchor': False},
            'state': engine.snapshot(r),
        }
    ]
    before = copy.deepcopy(r)
    for seed in range(50):
        restored = rebirth.restore(r['persona'], r, 'anchor', seed)
        assert restored['balances'] == r['balances'] and restored['month_index'] == 17
        assert [p for p in restored['planned'] if p['card_id'] == 'CH07'] == [
            {'at_index': 18, 'card_id': 'CH07', 'anchor': True}
        ]
    assert r == before


def test_reproducible_paired_strategies_no_original_future_and_cancel():
    r = engine.create_run(content.PERSONAS[0], 123, 28)
    before = copy.deepcopy(r)
    point = rebirth.points(r)[0]
    safe = rebirth.preview_source(r)
    assert not {'seed', 'planned', 'story_text'} & safe.keys()
    assert rebirth.points(safe) == rebirth.points(r)
    a = scenarios.compare(r['persona'], r, point, [1, 2, 3, 4])
    r['seed'] = 456
    r['planned'] = []
    b = scenarios.compare(r['persona'], r, point, [1, 2, 3, 4])
    assert a == b
    r['seed'] = before['seed']
    r['planned'] = before['planned']
    assert r == before
    assert scenarios.compare(r['persona'], safe, point, [1, 2, 3, 4]) == a
    assert a['variants']['BASIC']['quality']['median'] <= a['variants']['CURRENT']['quality']['median']
    assert (
        a['variants']['BASIC']['net_change_minor']['median'] >= a['variants']['CURRENT']['net_change_minor']['median']
    )
    assert scenarios.rollout(scenarios.hypothetical(r, 2), cancel=lambda: True) is None


def test_waiting_period_debts_and_retirement_are_preserved():
    r = engine.create_run(content.PERSONAS[0], 22, 28)
    r['scene_id'] = 'FINANCE'
    r['balances']['cash_minor'] = 300000000
    for pid in ('MEDICAL', 'CRITICAL_ILLNESS'):
        finance.execute(
            r,
            finance.quote(
                r,
                'POLICY_BUY',
                {
                    'product_id': pid,
                    'coverage_minor': content.PRODUCT_BY_ID[pid]['coverage_options_minor'][0],
                    'auto_pay': True,
                },
            ),
        )
    finance.execute(r, finance.quote(r, 'LOAN_BORROW', {'amount_minor': 10000000, 'term_months': 24}))
    r['snapshots'] = [
        {
            'point_id': 'waiting',
            'at_index': 1,
            'title': '等待期事件',
            'anchor': {'at_index': 1, 'card_id': 'CH07', 'anchor': True},
            'state': engine.snapshot(r),
        }
    ]
    restored = rebirth.restore(r['persona'], r, 'waiting', 666)
    assert (
        restored['policies'] == r['policies']
        and restored['loans'] == r['loans']
        and all(p['status'] == 'WAITING' for p in restored['policies'])
    )
    assert scenarios.rollout(restored, months=12)['months'] >= 12
    old = engine.create_run(content.PERSONAS[0], 5, 28)
    old['month_index'] = 70 * 12
    old['salary_minor'] = 0
    old['balances']['cash_minor'] = 0
    result = scenarios.rollout(scenarios.hypothetical(old, 77), months=12)
    assert result['shortage'] and result['net_change_minor'] < 0


def test_global_capacity_and_bounded_retries(game, monkeypatch):
    c, r = ended(game)
    monkeypatch.setattr(insights, 'submit', lambda task: None)
    first = start(game, c, r)
    with store.tx() as db:
        owner = db.execute('SELECT owner FROM insight_jobs WHERE id=?', (first['id'],)).fetchone()['owner']
        other = engine.uid()
        third = engine.uid()
        for user_id in (other, third):
            db.execute(
                'INSERT INTO users(id,email,password_hash,display_name,verified,role,settings,created_at) VALUES(?,?,?,?,?,?,?,?)',
                (user_id, user_id + '@example.test', 'unused', '測試', 1, 'PLAYER', '{}', engine.now()),
            )
        body = {'expected_version': r['version'], 'expected_campaign_version': c['version']}
        insights.prepare(db, other, c, r, str(uuid.uuid4()), body)
        with pytest.raises(ValueError, match='ANALYSIS_BUSY'):
            insights.prepare(db, third, c, r, str(uuid.uuid4()), body)
        for _ in range(7):
            job = json.loads(db.execute('SELECT body FROM insight_jobs WHERE id=?', (first['id'],)).fetchone()[0])
            job['status'] = 'CANCELLED'
            db.execute('UPDATE insight_jobs SET body=? WHERE id=?', (store.j(job), first['id']))
            insights.prepare(db, owner, c, r, str(uuid.uuid4()), body)
        job['status'] = 'CANCELLED'
        db.execute('UPDATE insight_jobs SET body=? WHERE id=?', (store.j(job), first['id']))
        with pytest.raises(ValueError, match='RATE_LIMITED'):
            insights.prepare(db, owner, c, r, str(uuid.uuid4()), body)
