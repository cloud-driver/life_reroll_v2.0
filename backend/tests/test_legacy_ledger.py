from test_game import game
from app import store, engine


def test_ledger_without_counter_account_reads_without_changing_save(game):
    game.auth()
    campaign, run = game.new()
    with store.tx() as db:
        c = store.get_campaign(db, campaign['id'])
        r = c['runs'][-1]
        engine.income(r, 10000, 'SALARY', '舊版薪資紀錄')
        engine.ledger(r, 'TRANSFER', -1000, cashflow='INTERNAL', description='舊版轉帳紀錄')
        store.put_campaign(db, c)
        before = db.execute('SELECT body FROM campaigns WHERE id=?', (c['id'],)).fetchone()[0]
    data, _ = game.call('GET', f'/runs/{run["id"]}/ledger', status=200)
    assert len(data['items']) == 2
    assert all(x['counter_account'] == '' for x in data['items'])
    assert [x['amount_minor'] for x in data['items']] == [10000, -1000]
    with store.tx(read_only=True) as db:
        assert db.execute('SELECT body FROM campaigns WHERE id=?', (campaign['id'],)).fetchone()[0] == before
