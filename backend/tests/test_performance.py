"""Performance boundaries must preserve state, privacy, and HTTP contracts."""

import asyncio
import copy
import json
import threading
import time
import httpx
from app import engine, store, content, handlers, scenarios, rebirth
from app.main import app
from test_game import game


def test_run_index_migration_ownership_append_rollback_and_delete(game, monkeypatch):
    user = game.auth()['user']['id']
    c, r = game.new()
    with store.tx() as db:
        c = store.get_campaign(db, c['id'])
        db.execute('DROP TRIGGER campaign_runs_insert')
        db.execute('DROP TRIGGER campaign_runs_update')
        db.execute('DROP TABLE campaign_runs')
    store.init()
    store.init()
    with store.tx() as db:
        loaded, run = store.find_run(db, r['id'], user)
        assert loaded == c and run['id'] == r['id']
        assert store.find_run(db, r['id'], 'other') == (None, None)
        assert store.find_run(db, 'missing', user) == (None, None)
        new = copy.deepcopy(run)
        new['id'] = 'second-run'
        c['runs'].append(new)
        store.put_campaign(db, c)
        assert store.find_run(db, 'second-run', user)[1] == new
    try:
        with store.tx() as db:
            c['runs'].append({**new, 'id': 'rolled-back'})
            store.put_campaign(db, c)
            raise ValueError('rollback')
    except ValueError:
        pass
    with store.tx() as db:
        assert store.find_run(db, 'rolled-back', user) == (None, None)
        assert db.execute('SELECT count(*) FROM campaign_runs').fetchone()[0] == 2
        db.execute('DELETE FROM campaigns WHERE id=?', (c['id'],))
        assert db.execute('SELECT count(*) FROM campaign_runs').fetchone()[0] == 0


def test_no_event_months_do_not_copy_history_but_event_restore_is_exact(monkeypatch):
    r = engine.create_run(content.PERSONAS[0], 9)
    r['planned'] = [{'at_index': 6, 'card_id': 'CH07', 'anchor': False}]
    expected = copy.deepcopy(r)
    for i in range(1, 6):
        expected['month_index'] = i
        engine.monthly_market(expected)
        engine.monthly_obligations(expected)
        engine.checkpoint(expected)
    captured = []
    original = engine.snapshot

    def capture(run):
        captured.append(run['month_index'])
        return original(run)

    monkeypatch.setattr(engine, 'snapshot', capture)
    r['status'] = 'ADVANCING'
    r['target_index'] = 12
    r['advance'] = {'id': 'test', 'from_date': engine.sim_date(r)}
    engine.next_step(r)
    assert captured == [5]
    actual = r['snapshots'][0]['state']
    reference = original(expected)
    # Separate runs assign fresh ledger IDs; compare every accounting field.
    for state in (actual, reference):
        state['ledger'] = [{k: v for k, v in entry.items() if k != 'id'} for entry in state['ledger']]
    assert actual == reference
    assert r['events'][0]['card_id'] == 'CH07'


def test_branch_trim_matches_full_history_simulation():
    r = engine.create_run(content.PERSONAS[0], 11)
    for i in range(1, 121):
        r['month_index'] = i
        engine.monthly_market(r)
        engine.monthly_obligations(r)
        engine.checkpoint(r)
    r['initial'] = engine.snapshot(r)
    source = rebirth.preview_source(r)
    before = copy.deepcopy(source)
    point = rebirth.points(source)[0]
    seeds = list(range(4))
    reference = {}
    for strategy in ('CURRENT', 'BASIC'):
        reference[strategy] = scenarios.summarize(
            [
                scenarios.rollout(rebirth.restore(r['persona'], source, point['id'], seed), strategy=strategy)
                for seed in seeds
            ]
        )
    assert scenarios.compare(r['persona'], source, point, seeds)['variants'] == reference
    assert source == before


def test_slow_database_work_does_not_block_async_loop(game, monkeypatch):
    original = handlers.result
    entered = threading.Event()
    release = threading.Event()

    def slow(op, *args):
        if op == 'B01':
            entered.set()
            release.wait(3)
        return original(op, *args)

    monkeypatch.setattr(handlers, 'result', slow)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            task = asyncio.create_task(client.get('/api/v1/bootstrap'))
            try:
                for _ in range(100):
                    if entered.is_set():
                        break
                    await asyncio.sleep(0.01)
                assert entered.is_set()
                assert not task.done(), 'slow synchronous handler blocked the event loop'
                response = await asyncio.wait_for(client.get('/api/v1/auth/session'), 1)
                assert response.status_code == 200
            finally:
                release.set()
                await task

    asyncio.run(run())
