import copy
import pytest
from test_game import game
from app import store, engine, content


def prepare(game):
    game.auth()
    c, r = game.new()
    r = game.mutate(r, 'initial-allocation/complete', {'expected_version': r['version']})
    return c, r


def empty_plan(c):
    with store.tx() as db:
        raw = store.get_campaign(db, c['id'])
        raw['runs'][-1]['planned'] = []
        store.put_campaign(db, raw)


def test_work_routine_is_authoritative_and_persistent(game):
    c, r = prepare(game)
    empty_plan(c)
    a, _ = game.call('POST', f'/runs/{r["id"]}/advances', {'expected_version': r['version']}, 201)
    r = game.refresh(r)
    assert r['status'] == 'TURN_REVIEW'
    r = game.mutate(r, f'advances/{a["id"]}/review', {'expected_version': r['version']})
    assert r['daily_phase'] == 'WORK_REQUIRED'
    game.call('POST', f'/runs/{r["id"]}/advances', {'expected_version': r['version']}, 409)
    r = game.walk(r, 'WORK')
    assert r['daily_phase'] == 'WORKING'
    assert game.refresh(r)['daily_phase'] == 'WORKING'
    game.call(
        'POST', f'/runs/{r["id"]}/scene-transitions', {'expected_version': r['version'], 'scene_id': 'STREET'}, 409
    )
    before = r['balances']
    date = r['sim_date']
    r = game.mutate(
        r, 'scene-transitions', {'expected_version': r['version'], 'scene_id': 'WORK', 'complete_work': True}
    )
    assert r['daily_phase'] == 'RETURN_HOME' and r['balances'] == before and r['sim_date'] == date
    r = game.walk(r, 'HOME')
    assert r['daily_phase'] == 'HOME_READY'
    r = game.walk(r, 'FINANCE')
    assert r['daily_phase'] == 'FREE_TIME'
    r = game.walk(r, 'HOME')
    assert r['daily_phase'] == 'HOME_READY'


def test_initial_work_hospital_and_unreachable_roll_are_rejected(game):
    game.auth()
    c, r = game.new()
    r = game.walk(r, 'STREET')
    game.call('POST', f'/runs/{r["id"]}/scene-transitions', {'expected_version': r['version'], 'scene_id': 'WORK'}, 409)
    game.call(
        'POST', f'/runs/{r["id"]}/scene-transitions', {'expected_version': r['version'], 'scene_id': 'HOSPITAL'}, 409
    )
    game.call('POST', f'/runs/{r["id"]}/initial-allocation/complete', {'expected_version': r['version']}, 409)


def test_turn_snapshot_summary_balances_and_events(game):
    c, r = prepare(game)
    empty_plan(c)
    opening = r['balances']['net_worth_minor']
    a, _ = game.call('POST', f'/runs/{r["id"]}/advances', {'expected_version': r['version']}, 201)
    r = game.refresh(r)
    assert a['opening_snapshot']['balances']['net_worth_minor'] == opening
    assert a['closing_snapshot']['balances']['net_worth_minor'] == r['balances']['net_worth_minor']
    assert a['summary']['net_worth_change_minor'] == r['balances']['net_worth_minor'] - opening
    assert a['summary']['event_ids'] == [] and a['summary']['income_minor'] > 0 and a['summary']['expense_minor'] > 0
    assert a['current_date'] == r['sim_date']


def test_90_years_ends_with_negative_assets(game, monkeypatch):
    c, r = prepare(game)
    with store.tx() as db:
        raw = store.get_campaign(db, c['id'])
        v = raw['runs'][0]
        v.update(
            planned=[],
            month_index=(89 - v['start_age']) * 12,
            negative_years=0,
            salary_minor=0,
            employment_status='RETIRED',
        )
        v['balances'] = {'cash_minor': 0, 'savings_minor': 0}
        store.put_campaign(db, raw)

    class Fixed:
        def randint(self, *args):
            return 1

    monkeypatch.setattr('app.ops.events.random.SystemRandom', lambda: Fixed())
    a, _ = game.call('POST', f'/runs/{r["id"]}/advances', {'expected_version': r['version']}, 201)
    r = game.refresh(r)
    assert r['age'] == 90 and r['balances']['net_worth_minor'] < 0
    r = game.mutate(r, f'advances/{a["id"]}/review', {'expected_version': r['version']})
    assert r['status'] == 'ENDED' and r['end_reason'] == 'AGE_COMPLETED'


def test_premium_grace_does_not_extend_or_duplicate_debt():
    r = engine.create_run(content.PERSONAS[0], 7, 25)
    r['balances'] = {'cash_minor': 0, 'savings_minor': 0}
    r['salary_minor'] = 0
    r['policies'] = [
        {
            'id': 'p',
            'product_id': 'MEDICAL',
            'status': 'ACTIVE',
            'coverage_from_index': 0,
            'next_premium_index': 1,
            'auto_pay': False,
            'premium_minor': 100000,
            'coverage_minor': 30000000,
        }
    ]
    for month in range(1, 7):
        r['month_index'] = month
        engine.monthly_obligations(r)
    p = r['policies'][0]
    assert p['status'] == 'LAPSED' and p['grace_until_index'] == 3
    assert len([b for b in r['bills'] if b.get('related_policy_id') == 'p']) == 1


def test_principal_and_interest_are_not_conflated():
    r = engine.create_run(content.PERSONAS[0], 1, 25)
    r['terms'] = [{'id': 'term', 'principal_minor': 1000000, 'interest_minor': 12345, 'status': 'ACTIVE'}]
    from app.wire import shape

    b = shape('Balances', engine.money(r))
    assert b['term_principal_minor'] == 1000000
    snap = shape('AssetSnapshot', engine.asset_snapshot(r))
    assert snap['term_interest_minor'] == 12345


def test_medical_event_images_hospital_and_funding(game):
    c, r = prepare(game)
    with store.tx() as db:
        raw = store.get_campaign(db, c['id'])
        raw['runs'][0]['planned'] = [{'at_index': 1, 'card_id': 'FA17', 'anchor': False}]
        store.put_campaign(db, raw)
    game.call('POST', f'/runs/{r["id"]}/advances', {'expected_version': r['version']}, 201)
    r = game.refresh(r)
    assert r['scene_id'] == 'HOSPITAL'
    e, _ = game.call('GET', f'/runs/{r["id"]}/events/{r["pending_event_id"]}', status=200)
    assert e['visual_key'] == 'FA17' and e['hospital_visit']['cost_minor'] is None
    assert not e['hospital_visit']['payment_verified']
    game.call(
        'POST',
        f'/runs/{r["id"]}/events/{e["id"]}/decisions',
        {'expected_version': r['version'], 'automatic': True, 'confirmed': True},
        409,
    )
    r = game.mutate(
        r,
        f'events/{e["id"]}/decisions',
        {'expected_version': r['version'], 'choice_id': e['choices'][0]['id'], 'confirmed': True},
    )
    e, _ = game.call('GET', f'/runs/{r["id"]}/events/{e["id"]}', status=200)
    assert e['hospital_visit']['cost_minor'] > 0
    assert e['balance_before_minor'] is not None and e['balance_after_minor'] is not None


def test_old_save_without_daily_phase_can_resume(game):
    c, r = prepare(game)
    with store.tx() as db:
        raw = store.get_campaign(db, c['id'])
        raw['runs'][0].pop('daily_phase', None)
        store.put_campaign(db, raw)
    r = game.refresh(r)
    assert r['daily_phase'] == 'HOME_READY'
    r = game.walk(r, 'FINANCE')
    assert r['daily_phase'] == 'FREE_TIME'


def test_bootstrap_verification_flag_matches_backend(game, monkeypatch):
    assert game.call('GET', '/bootstrap', status=200)[0]['email_verification_required'] is False
    monkeypatch.setenv('LIFE_SKIP_EMAIL_VERIFICATION', '0')
    assert game.call('GET', '/bootstrap', status=200)[0]['email_verification_required'] is True


def test_events_during_wait_are_queued_without_duplicate_months():
    r = engine.create_run(content.PERSONAS[0], 123, 25)
    r.update(month_index=3, target_index=3, status='ADVANCING')
    r['planned'] = [{'at_index': 2, 'card_id': 'TR01', 'anchor': False}]
    r['advance'] = {'id': 'a', 'from_date': '2026-01-01', 'status': 'PROCESSING', 'opening_state': r['initial']}
    before = r['balances'].copy()
    engine.next_step(r)
    assert r['status'] == 'EVENT_PENDING' and r['month_index'] == 3 and r['balances'] == before
    e = r['events'][-1]
    assert e['at_index'] == 2 and e['occurred_on'] == '2026-03-01'
    engine.decide(r, e['id'], e['choices'][0]['id'])
    engine.acknowledge(r, e['id'])
    assert r['status'] == 'TURN_REVIEW' and r['month_index'] == 3 and len(r['events']) == 1
