import copy
import random
import pytest
from app import engine, content, finance, handlers, store
from test_game import game


def test_market_reloads_deterministically_and_keeps_recorded_prices():
    r = engine.create_run(content.PERSONAS[0], 12345, 25)
    old = copy.deepcopy(r['price_history'])
    twin = copy.deepcopy(r)
    changes = []
    for month in range(1, 121):
        r['month_index'] = month
        twin['month_index'] = month
        previous = r['prices'].copy()
        engine.monthly_market(r)
        engine.monthly_market(twin)
        assert r['prices'] == twin['prices']
        changes.extend(r['prices'][s] / previous[s] - 1 for s in r['prices'])
    assert all(r['price_history'][s][:1] == old[s] for s in old)
    assert all(p >= 100 for p in r['prices'].values())
    assert min(changes) < -0.1 and max(changes) > 0.05


def test_stock_round_trip_costs_and_quote_conservation():
    r = engine.create_run(content.PERSONAS[0], 23456, 25)
    r['scene_id'] = 'FINANCE'
    r['balances']['cash_minor'] = 10000000
    before = r['balances']['cash_minor']
    qty = 100
    gross = qty * r['prices']['STABLE']
    buy = finance.quote(r, 'STOCK_BUY', {'stock_id': 'STABLE', 'quantity': qty})
    assert buy['fees_minor'] == gross * 30 // 10000
    finance.execute(r, buy)
    sell = finance.quote(r, 'STOCK_SELL', {'stock_id': 'STABLE', 'quantity': qty})
    finance.execute(r, sell)
    assert r['balances']['cash_minor'] == before - buy['fees_minor'] - sell['fees_minor']
    assert r['holdings'].get('STABLE', 0) == 0


@pytest.mark.parametrize('password', ['short', 'x' * 129, 12])
def test_reset_length_error_keeps_valid_token_and_password(game, password):
    game.auth()
    # A genuine reset challenge in the isolated fixture; no external email.
    _, response = game.call('POST', '/auth/password-reset-requests', {'email': 'player@example.com'}, 202)
    token = response.headers['X-Dev-Verification-Token']
    with store.tx(read_only=True) as db:
        before = db.execute('SELECT password_hash FROM users').fetchone()[0]
    _, response = game.call('POST', '/auth/password-resets', {'token': token, 'new_password': password}, 422)
    assert response.json()['error']['code'] == 'PASSWORD_LENGTH_INVALID'
    assert '12' in response.json()['error']['message']
    with store.tx(read_only=True) as db:
        assert db.execute('SELECT password_hash FROM users').fetchone()[0] == before
        assert db.execute('SELECT 1 FROM tokens WHERE token_hash=?', (handlers.t_hash(token),)).fetchone()
    game.call('POST', '/auth/password-resets', {'token': token, 'new_password': 'ValidNewPassword!20261023'}, 200)
