"""End-to-end contract tests use SQLite and the real FastAPI app, without mocks."""

import json
import uuid
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from fastapi.testclient import TestClient
from app import store, engine, content
from app.main import app, REGISTRY
from app import handlers


@pytest.fixture()
def game(tmp_path):
    store.DB_FILE = tmp_path / 'test.sqlite3'
    store.init()
    client = TestClient(app)

    class Game:
        csrf = None

        def call(self, method, path, body=None, status=None, key=None):
            headers = {'idempotency-key': key or str(uuid.uuid4())}
            if self.csrf:
                headers['x-csrf-token'] = self.csrf
            response = self.client.request(method, '/api/v1' + path, json=body, headers=headers)
            if status is not None:
                assert response.status_code == status, (method, path, response.text[:1000])
            assert response.status_code < 500, (method, path, response.text[:1000])
            if response.status_code == 204:
                return None, response
            if response.status_code < 300:
                match = next(
                    (
                        op
                        for op in REGISTRY
                        if op['method'] == method
                        and __import__('re').fullmatch(
                            __import__('re').sub(r'\{[^}]+\}', r'[^/]+', op['path']), '/api/v1' + path.split('?')[0]
                        )
                    ),
                    None,
                )
                if match:
                    from app.wire import SCHEMA

                    typ = match['output'].split(' ', 1)[-1]
                    if typ.startswith('Page<'):
                        schema = {
                            'type': 'object',
                            'properties': {
                                'items': {'type': 'array', 'items': {'$ref': '#/$defs/' + typ[5:-1]}},
                                'next_cursor': {'anyOf': [{'type': 'string'}, {'type': 'null'}]},
                                'total': {'type': 'integer'},
                            },
                            'required': ['items', 'next_cursor', 'total'],
                            'additionalProperties': False,
                        }
                    elif typ.endswith('[]'):
                        schema = {'type': 'array', 'items': {'$ref': '#/$defs/' + typ[:-2]}}
                    elif typ.rstrip('?') in SCHEMA:
                        schema = {'$ref': '#/$defs/' + typ.rstrip('?')}
                    else:
                        schema = None
                    if schema and response.json().get('data') is not None:
                        validator = Draft202012Validator({**schema, '$defs': SCHEMA}, format_checker=FormatChecker())
                        failures = list(validator.iter_errors(response.json()['data']))
                        assert not failures, (match['id'], str(failures[0]), list(failures[0].absolute_path))
            return response.json().get('data'), response

        def auth(self, email='player@example.com'):
            user, registration = self.call(
                'POST',
                '/auth/register',
                {
                    'email': email,
                    'password': '123456789Strong!',
                    'display_name': '測試玩家',
                    'terms_version': '2026-10-22',
                    'privacy_version': '2026-10-22',
                },
                201,
            )
            session, _ = self.call('POST', '/auth/login', {'email': email, 'password': '123456789Strong!'}, 200)
            self.csrf = session['csrf_token']
            self.call(
                'POST',
                '/auth/email-verifications',
                {'email': email, 'token': registration.headers['X-Dev-Verification-Token']},
                200,
            )
            return self.call('GET', '/auth/session', status=200)[0]

        def new(self):
            campaign, _ = self.call('POST', '/campaigns', {'locale': 'zh-TW'}, 202)
            run, _ = self.call('GET', f'/runs/{campaign["campaign"]["current_run_id"]}', status=200)
            return campaign['campaign'], run

        def refresh(self, r):
            return self.call('GET', f'/runs/{r["id"]}', status=200)[0]

        def mutate(self, r, suffix, body, method='POST', status=200):
            x, _ = self.call(method, f'/runs/{r["id"]}/{suffix}', body, status)
            return x['run']

        def walk(self, r, to):
            if r['scene_id'] == to:
                return r
            path = {
                'HOME': ['STREET'],
                'FINANCE': ['STREET'],
                'HOSPITAL': ['STREET'],
                'WORK': ['STREET'],
                'STREET': [to],
            }
            while r['scene_id'] != to:
                nxt = path[r['scene_id']][0]
                r = self.mutate(r, 'scene-transitions', {'expected_version': r['version'], 'scene_id': nxt})
            return r

        def ready(self, r):
            if r.get('daily_phase') == 'WORK_REQUIRED':
                r = self.walk(r, 'WORK')
                r = self.mutate(
                    r,
                    'scene-transitions',
                    {'expected_version': r['version'], 'scene_id': 'WORK', 'complete_work': True},
                )
            return self.walk(r, 'HOME')

        def finance(self, r, action, params):
            r = self.walk(r, 'FINANCE')
            q, _ = self.call(
                'POST',
                f'/runs/{r["id"]}/quotes',
                {'expected_version': r['version'], 'action': action, 'params': params},
                201,
            )
            assert q['eligible'], q
            r = self.mutate(
                r,
                'transactions',
                {'expected_version': r['version'], 'quote_id': q['id'], 'confirmed': True},
                status=201,
            )
            return r, q

    result = Game()
    result.client = client
    return result


def test_account_routes_security_and_docs(game):
    ids = {x['id'] for x in REGISTRY}
    assert len(ids) == 91
    doc = game.client.get('/openapi.json').json()
    assert (
        sum(
            len([m for m in methods if m in ('get', 'post', 'put', 'patch', 'delete')])
            for methods in doc['paths'].values()
        )
        >= 91
    )
    assert all(x['path'] in doc['paths'] for x in REGISTRY)
    assert game.client.get('/docx').status_code == 200
    assert game.client.get('/').status_code == 200
    game.auth()
    game.call('GET', '/me', status=200)
    game.call('GET', '/me/settings', status=200)
    game.call('PUT', '/me/settings', {'music': False}, 200)
    preferences, _ = game.call('PUT', '/me/settings', {'tutorial_completed': True}, 200)
    assert preferences['tutorial_completed'] is True
    assert game.call('GET', '/me/settings', status=200)[0]['tutorial_completed'] is True
    game.call('GET', '/me/sessions', status=200)
    game.call('GET', '/content/scenes', status=200)
    game.call('GET', '/content/lessons', status=200)
    game.call('GET', '/content/lessons/reserve', status=200)
    game.call('POST', '/me/lesson-reads/reserve', {}, 200)
    game.call('GET', '/content/legal/TERMS', status=200)
    c, r = game.new()
    _, conflict = game.call('POST', '/campaigns', {'locale': 'zh-TW'}, 409)
    assert conflict.json()['error']['code'] == 'ACTIVE_CAMPAIGN_EXISTS'
    assert game.call('GET', '/campaigns/active', status=200)[0]['id'] == c['id']
    assert game.call('GET', '/campaigns', status=200)[0]['total'] == 1
    raw = game.client.post(f'/api/v1/runs/{r["id"]}/save', json={})
    assert raw.status_code == 403 and raw.json()['error']['code'] == 'CSRF_INVALID'
    raw = game.client.get(f'/api/v1/runs/{r["id"]}/events/not-available')
    assert raw.status_code == 404


def test_register_shows_specific_field_error(game):
    valid = {
        'email': 'hello@example.com',
        'password': '123456789Strong!',
        'display_name': '測試玩家',
        'terms_version': '2026-10-22',
        'privacy_version': '2026-10-22',
    }
    for field, value, code in [
        ('email', 'bad', 'EMAIL_INVALID'),
        ('email', 7, 'EMAIL_INVALID'),
        ('password', '1234', 'PASSWORD_LENGTH_INVALID'),
        ('display_name', '', 'DISPLAY_NAME_LENGTH_INVALID'),
        ('terms_version', 'old', 'LEGAL_VERSION_INVALID'),
    ]:
        _, response = game.call('POST', '/auth/register', {**valid, field: value}, 422)
        assert response.json()['error']['code'] == code
        assert response.json()['error']['message']


def test_login_rate_limit_and_account_erasure(game):
    game.auth('erase@example.com')
    c, r = game.new()
    for _ in range(5):
        _, response = game.call('POST', '/auth/login', {'email': 'erase@example.com', 'password': 'incorrect'}, 401)
        assert response.json()['error']['code'] == 'INVALID_CREDENTIALS'
    _, response = game.call('POST', '/auth/login', {'email': 'erase@example.com', 'password': 'incorrect'}, 429)
    assert response.json()['error']['code'] == 'RATE_LIMITED'
    game.call(
        'POST',
        '/me/deletion-requests',
        {'current_password': '123456789Strong!', 'confirmation': 'DELETE_MY_ACCOUNT'},
        202,
    )
    assert game.call('GET', '/auth/session', status=200)[0]['user'] is None
    with store.tx() as db:
        assert not db.execute('SELECT 1 FROM campaigns WHERE id=?', (c['id'],)).fetchone()
        assert not db.execute('SELECT 1 FROM users WHERE email=?', ('erase@example.com',)).fetchone()


def test_financial_conservation_quotes_and_replay(game):
    game.auth()
    c, r = game.new()
    r = game.walk(r, 'FINANCE')
    deposits, _ = game.call('GET', f'/runs/{r["id"]}/deposit-products', status=200)
    assert all(product['early_exit_rule'] for product in deposits)
    opening = r['balances']['net_worth_minor']
    r, _ = game.finance(r, 'TRANSFER', {'from_account': 'CASH', 'to_account': 'SAVINGS', 'amount_minor': 5000000})
    assert r['balances']['net_worth_minor'] == opening
    r, _ = game.finance(
        r,
        'TERM_OPEN',
        {'product_id': 'TERM_12', 'amount_minor': 3000000, 'term_months': 12, 'source_account': 'SAVINGS'},
    )
    term = game.call('GET', f'/runs/{r["id"]}/portfolio', status=200)[0]['term_deposits'][0]
    assert term['principal_minor'] == 3000000
    r, _ = game.finance(r, 'TERM_CLOSE', {'term_deposit_id': term['id']})
    assert r['balances']['net_worth_minor'] == opening
    r, _ = game.finance(r, 'STOCK_BUY', {'stock_id': 'STABLE', 'quantity': 2})
    holdings = game.call('GET', f'/runs/{r["id"]}/portfolio', status=200)[0]['holdings']
    assert next(x for x in holdings if x['stock_id'] == 'STABLE')['quantity'] == 2
    r, _ = game.finance(r, 'STOCK_SELL', {'stock_id': 'STABLE', 'quantity': 1})
    holdings = game.call('GET', f'/runs/{r["id"]}/portfolio', status=200)[0]['holdings']
    assert next(x for x in holdings if x['stock_id'] == 'STABLE')['quantity'] == 1
    r, _ = game.finance(r, 'LOAN_BORROW', {'product_id': 'SIM_LOAN', 'amount_minor': 500000, 'term_months': 12})
    assert r['balances']['net_worth_minor'] <= opening
    loan = game.call('GET', f'/runs/{r["id"]}/portfolio', status=200)[0]['loans'][0]
    r, _ = game.finance(r, 'LOAN_REPAY', {'loan_id': loan['id'], 'amount_minor': 100000})
    assert loan['outstanding_principal_minor'] > 0
    r, _ = game.finance(
        r,
        'POLICY_BUY',
        {
            'product_id': 'ACCIDENT',
            'coverage_minor': 20000000,
            'premium_period_months': 12,
            'beneficiary_label': '家人',
        },
    )
    policy = game.call('GET', f'/runs/{r["id"]}/policies', status=200)[0][0]
    assert policy['premium_minor'] > 0
    r, _ = game.finance(r, 'POLICY_SURRENDER', {'policy_id': policy['id']})
    assert game.call('GET', f'/runs/{r["id"]}/policies', status=200)[0][0]['status'] == 'SURRENDERED'
    q, _ = game.call(
        'POST',
        f'/runs/{r["id"]}/quotes',
        {'expected_version': r['version'], 'action': 'STOCK_BUY', 'params': {'stock_id': 'TECH', 'quantity': 1000000}},
        201,
    )
    assert not q['eligible']
    _, err = game.call(
        'POST',
        f'/runs/{r["id"]}/quotes',
        {
            'expected_version': r['version'],
            'action': 'STOCK_BUY',
            'params': {'stock_id': 'TECH', 'quantity': 1, 'forced_price_minor': 1},
        },
        422,
    )
    assert err.json()['error']['code'] == 'VALIDATION_ERROR'
    stale, _ = game.call(
        'POST',
        f'/runs/{r["id"]}/quotes',
        {
            'expected_version': r['version'],
            'action': 'TRANSFER',
            'params': {'direction': 'SAVINGS_TO_CASH', 'amount_minor': 100},
        },
        201,
    )
    r = game.mutate(r, 'scene-transitions', {'expected_version': r['version'], 'scene_id': 'STREET'})
    game.call(
        'POST',
        f'/runs/{r["id"]}/transactions',
        {'expected_version': r['version'], 'quote_id': stale['id'], 'confirmed': True},
        409,
    )
    r = game.walk(r, 'HOME')
    r = game.mutate(r, 'initial-allocation/complete', {'expected_version': r['version']})
    k = 'unreplayable-die'
    before = r['age']
    first, _ = game.call('POST', f'/runs/{r["id"]}/advances', {'expected_version': r['version']}, 201, k)
    second, _ = game.call('POST', f'/runs/{r["id"]}/advances', {'expected_version': r['version']}, 201, k)
    assert first == second and first['roll_value'] in range(1, 7)
    game.call('POST', f'/runs/{r["id"]}/advances', {'expected_version': r['version']}, 409, 'different-die')
    saved, _ = game.call('POST', f'/runs/{r["id"]}/save', {}, 200)
    assert saved['version'] == game.refresh(r)['version']
    history, _ = game.call('GET', f'/runs/{r["id"]}/stocks/TECH/prices', status=200)
    assert all(v['date'] <= game.refresh(r)['sim_date'] for v in history['items'])


def test_three_lives_rebirth_and_reports(game):
    game.auth()
    campaign, r = game.new()
    cid = campaign['id']
    r = game.mutate(r, 'initial-allocation/complete', {'expected_version': r['version']})
    finished = []
    for life in range(3):
        for step in range(180):
            r = game.refresh(r)
            if r['status'] == 'ENDED':
                break
            if r['status'] == 'INITIAL_ALLOCATION':
                r = game.mutate(r, 'initial-allocation/complete', {'expected_version': r['version']})
            elif r['status'] == 'EXPLORING':
                r = game.ready(r)
                game.call('POST', f'/runs/{r["id"]}/advances', {'expected_version': r['version']}, 201)
            elif r['status'] == 'EVENT_PENDING':
                e, _ = game.call('GET', f'/runs/{r["id"]}/events/{r["pending_event_id"]}', status=200)
                r = game.mutate(
                    r,
                    f'events/{e["id"]}/decisions',
                    {'expected_version': r['version'], 'choice_id': e['choices'][0]['id'], 'confirmed': True},
                )
            elif r['status'] == 'FUNDING':
                f, _ = game.call('GET', f'/runs/{r["id"]}/events/{r["pending_event_id"]}/funding', status=200)
                if f['can_pay']:
                    r = game.mutate(r, f'events/{f["event_id"]}/funding/pay', {'expected_version': r['version']})
                elif f['can_wait']:
                    r = game.mutate(r, f'events/{f["event_id"]}/funding/wait', {'expected_version': r['version']})
                elif f['can_confirm_failure']:
                    r = game.mutate(
                        r, f'events/{f["event_id"]}/funding/confirm-failure', {'expected_version': r['version']}
                    )
                else:
                    room = next((o['available_minor'] for o in f['options'] if o['kind'] == 'LOAN_BORROW'), 0)
                    if room:
                        q, _ = game.call(
                            'POST',
                            f'/runs/{r["id"]}/quotes',
                            {
                                'expected_version': r['version'],
                                'action': 'LOAN_BORROW',
                                'params': {'amount_minor': min(room, f['remaining_minor']), 'term_months': 60},
                            },
                            201,
                        )
                        assert q['eligible']
                        r = game.mutate(
                            r,
                            'transactions',
                            {'expected_version': r['version'], 'quote_id': q['id'], 'confirmed': True},
                            status=201,
                        )
                    else:
                        raise AssertionError('unreachable funding state')
            elif r['status'] == 'EVENT_RESULT':
                r = game.mutate(
                    r, f'events/{r["pending_event_id"]}/acknowledgements', {'expected_version': r['version']}
                )
            elif r['status'] == 'TURN_REVIEW':
                r = game.mutate(r, f'advances/{r["advance_id"]}/review', {'expected_version': r['version']})
            else:
                raise AssertionError(r['status'])
        assert r['status'] == 'ENDED', f'life {life + 1} did not finish in 180 commands'
        finished.append(r)
        run_report, _ = game.call('GET', f'/runs/{r["id"]}/report', status=200)
        assert run_report['ending_reason'] in ('AGE_COMPLETED', 'UNFUNDED_CRITICAL_CARE', 'NEGATIVE_NET_WORTH_7Y')
        if run_report['ending_reason'] == 'AGE_COMPLETED':
            assert r['age'] >= 90
        assert run_report['ending_net_worth_minor'] == r['balances']['net_worth_minor']
        timeline, _ = game.call('GET', f'/runs/{r["id"]}/timeline', status=200)
        events, _ = game.call('GET', f'/runs/{r["id"]}/events', status=200)
        assert len(timeline['items']) == len(events['items'])
        if life < 2:
            points, _ = game.call('GET', f'/campaigns/{cid}/rebirth-points', status=200)
            assert points and points[0]['anchor_event_id'] is None
            selected = points[-1] if len(points) > 1 else points[0]
            preview, _ = game.call('GET', f'/campaigns/{cid}/rebirth-points/{selected["id"]}', status=200)
            assert preview['point']['id'] == selected['id']
            c, _ = game.call('GET', f'/campaigns/{cid}', status=200)
            new, _ = game.call(
                'POST',
                f'/campaigns/{cid}/rebirths',
                {'expected_campaign_version': c['version'], 'point_id': selected['id'], 'confirmed': True},
                202,
            )
            r = game.call('GET', f'/runs/{new["campaign"]["current_run_id"]}', status=200)[0]
            if selected['anchor_event_id']:
                assert r['sim_date'] == selected['restore_date']
                assert r['balances']['cash_minor'] == selected['balance_preview']['cash_minor']
    result, _ = game.call('GET', f'/campaigns/{cid}/final-report', status=200)
    assert len(result['run_ids']) == 3
    assert game.call('GET', '/campaigns/active', status=200)[0] is None
    ex, _ = game.call('POST', f'/campaigns/{cid}/report-exports', {}, 202)
    exp, _ = game.call('GET', f'/report-exports/{ex["job"]["result_ref"]["id"]}', status=200)
    assert game.client.get(exp['download_url']).content.startswith(b'%PDF')
    assert game.call('GET', '/campaigns', status=200)[0]['total'] == 1


def test_all_91_paths_reachable_and_no_server_errors(game):
    """Every advertised verb/path is invoked; contextual 4xx is expected outside valid state."""
    game.auth()
    c, r = game.new()
    job_id = store.connect().execute('SELECT id FROM jobs LIMIT 1').fetchone()['id']
    variables = {
        'campaign_id': c['id'],
        'run_id': r['id'],
        'job_id': job_id,
        'event_id': 'missing',
        'advance_id': 'missing',
        'stock_id': 'STABLE',
        'term_deposit_id': 'missing',
        'quote_id': 'missing',
        'transaction_id': 'missing',
        'policy_id': 'missing',
        'claim_id': 'missing',
        'export_id': 'missing',
        'point_id': 'missing',
        'product_id': 'MEDICAL',
        'release_id': 'missing',
        'session_id': 'missing',
        'lesson_id': 'reserve',
        'notice_id': 'missing',
        'kind': 'TERMS',
    }
    records = []
    for op in [*filter(lambda x: x['id'] != 'A04', REGISTRY), *filter(lambda x: x['id'] == 'A04', REGISTRY)]:
        path = op['path']
        for key, val in variables.items():
            path = path.replace('{' + key + '}', val)
        data, res = game.call(op['method'], path, {} if op['method'] != 'GET' else None)
        assert res.status_code not in (405, 500, 501, 502, 503), op['id']
        records.append((op['id'], res.status_code))
    assert len(records) == 91 and len({id_ for id_, _ in records}) == 91


def test_claim_delayed_funding_and_uninsured_travel(game):
    game.auth()
    c, r = game.new()
    r, _ = game.finance(r, 'POLICY_BUY', {'product_id': 'MEDICAL', 'coverage_minor': 60000000})
    policy = game.call('GET', f'/runs/{r["id"]}/policies', status=200)[0][0]
    with store.tx() as db:
        inner = store.get_campaign(db, c['id'])
        run = inner['runs'][0]
        run['planned'] = [
            {'at_index': 4, 'card_id': 'FA05', 'anchor': False},
            {'at_index': 16, 'card_id': 'TR03', 'anchor': False},
        ]
        run['balances']['cash_minor'] = 0
        run['balances']['savings_minor'] = 0
        store.put_campaign(db, inner)
    r = game.walk(r, 'HOME')
    r = game.mutate(r, 'initial-allocation/complete', {'expected_version': r['version']})
    game.call('POST', f'/runs/{r["id"]}/advances', {'expected_version': r['version']}, 201)
    r = game.refresh(r)
    assert r['status'] == 'EVENT_PENDING'
    event = game.call('GET', f'/runs/{r["id"]}/events/{r["pending_event_id"]}', status=200)[0]
    r = game.mutate(r, f'events/{event["id"]}/decisions', {'expected_version': r['version'], 'choice_id': 'PREPARED'})
    assert r['status'] == 'FUNDING'
    event = game.call('GET', f'/runs/{r["id"]}/events/{event["id"]}', status=200)[0]
    assessment = game.call('GET', f'/runs/{r["id"]}/events/{event["id"]}/claim-assessment', status=200)[0]
    assert next(x for x in assessment['items'] if x['policy_id'] == policy['id'])['eligible']
    r = game.mutate(
        r,
        'claims',
        {
            'expected_version': r['version'],
            'event_id': event['id'],
            'policy_id': policy['id'],
            'benefit_code': 'MEDICAL',
            'evidence_ids': [event['evidence'][0]['id']],
        },
        status=201,
    )
    claim = game.call('GET', f'/runs/{r["id"]}/claims', status=200)[0]['items'][0]
    assert claim['status'] == 'APPROVED' and claim['paid_minor'] == 0
    f = game.call('GET', f'/runs/{r["id"]}/events/{event["id"]}/funding', status=200)[0]
    assert not f['can_pay'] and f['can_wait']
    r = game.mutate(r, f'events/{event["id"]}/funding/wait', {'expected_version': r['version']})
    claim = game.call('GET', f'/runs/{r["id"]}/claims/{claim["id"]}', status=200)[0]
    assert claim['status'] == 'PAID' and claim['paid_minor'] > 0
    f = game.call('GET', f'/runs/{r["id"]}/events/{event["id"]}/funding', status=200)[0]
    assert f['can_pay']
    r = game.mutate(r, f'events/{event["id"]}/funding/pay', {'expected_version': r['version']})
    r = game.mutate(r, f'events/{event["id"]}/acknowledgements', {'expected_version': r['version']})
    assert r['status'] in ('TURN_REVIEW', 'EVENT_PENDING')
    for _ in range(5):
        if r['status'] == 'EVENT_PENDING':
            break
        if r['status'] == 'TURN_REVIEW':
            r = game.mutate(r, f'advances/{r["advance_id"]}/review', {'expected_version': r['version']})
        if r['status'] == 'EXPLORING':
            r = game.ready(r)
            game.call('POST', f'/runs/{r["id"]}/advances', {'expected_version': r['version']}, 201)
            r = game.refresh(r)
    trip = game.call('GET', f'/runs/{r["id"]}/events/{r["pending_event_id"]}', status=200)[0]
    assert trip['title'] == '出國深度旅行'
    before = r['quality']
    r = game.mutate(r, f'events/{trip["id"]}/decisions', {'expected_version': r['version'], 'choice_id': 'BALANCED'})
    assert r['quality'] > before
    outcome = game.call('GET', f'/runs/{r["id"]}/events/{trip["id"]}', status=200)[0]['outcome']
    assert outcome['cash_delta_minor'] < 0 and outcome['quality_delta'] > 0
    assessed = game.call('GET', f'/runs/{r["id"]}/events/{trip["id"]}/claim-assessment', status=200)[0]
    assert not any(x['eligible'] for x in assessed['items'])


def test_retirement_seven_negative_years_and_no_90_truncation(monkeypatch, game):
    game.auth()
    c, r = game.new()
    r = game.mutate(r, 'initial-allocation/complete', {'expected_version': r['version']})
    with store.tx() as db:
        cc = store.get_campaign(db, c['id'])
        raw = cc['runs'][0]
        raw['planned'] = []
        raw['month_index'] = (88 - raw['start_age']) * 12
        raw['balances']['cash_minor'] = 5000000000
        raw['salary_minor'] = 0
        raw['employment_status'] = 'RETIRED'
        store.put_campaign(db, cc)

    class Fixed:
        def randint(self, _, __):
            return 5

    monkeypatch.setattr('app.ops.events.random.SystemRandom', lambda: Fixed())
    game.call('POST', f'/runs/{r["id"]}/advances', {'expected_version': r['version']}, 201)
    r = game.refresh(r)
    assert r['status'] == 'TURN_REVIEW' and r['age'] == 93
    r = game.mutate(r, f'advances/{r["advance_id"]}/review', {'expected_version': r['version']})
    assert r['status'] == 'ENDED' and r['end_reason'] == 'AGE_COMPLETED'
    s = engine.create_run(content.PERSONAS[0], 123, 25)
    s['month_index'] = 71
    s['negative_years'] = 6
    s['status'] = 'ADVANCING'
    s['target_index'] = 72
    s['balances'] = {'cash_minor': 0, 'savings_minor': 0}
    s['salary_minor'] = 0
    s['living_minor'] = 4000000
    s['bills'].append(
        {'id': 'debt', 'category': 'OTHER', 'remaining_minor': 100000000, 'status': 'OVERDUE', 'related_loan_id': None}
    )
    s['planned'] = []
    s['advance'] = {'id': 'r', 'status': 'PROCESSING'}
    engine.next_step(s)
    assert s['status'] == 'ENDED' and s['end_reason'] == 'NEGATIVE_NET_WORTH_7Y'


def test_admin_content_persona_release(game, monkeypatch):
    monkeypatch.setenv('LIFE_ADMIN_EMAIL', 'admin@example.com')
    game.auth('admin@example.com')
    assets = {}
    for kind, records in [
        ('PERSONAS', content.PERSONAS),
        ('EVENTS', content.EVENTS),
        ('PRODUCTS', content.PRODUCTS),
        ('RULESET', {'stock_count': 5}),
    ]:
        a, _ = game.call(
            'POST',
            '/admin/content-assets',
            {'kind': kind, 'content_json': json.dumps(records, ensure_ascii=False)},
            201,
        )
        assets[kind] = a['id']
    release, _ = game.call(
        'POST',
        '/admin/content-releases',
        {
            'version': 'demo-personas-v2',
            'persona_asset_id': assets['PERSONAS'],
            'event_asset_id': assets['EVENTS'],
            'product_asset_id': assets['PRODUCTS'],
            'ruleset_asset_id': assets['RULESET'],
        },
        201,
    )
    checked, _ = game.call('POST', f'/admin/content-releases/{release["id"]}/validate', {}, 200)
    assert checked['status'] == 'VALIDATED'
    published, _ = game.call('POST', f'/admin/content-releases/{release["id"]}/publish', {}, 200)
    assert published['status'] == 'PUBLISHED'
    assert game.call('GET', '/bootstrap', status=200)[0]['content_version'] == 'demo-personas-v2'
    c, r = game.new()
    assert c['content_version'] == 'demo-personas-v2'
    audits = game.call('GET', '/admin/audit-logs', status=200)[0]
    assert audits['total'] >= 1


def test_separate_frontend_bearer_cors_and_development_bypass(game, monkeypatch):
    registration = game.client.post(
        '/api/v1/auth/register',
        json={
            'email': 'separate@example.com',
            'password': '123456789Strong!',
            'display_name': '分離部署',
            'terms_version': '2026-10-22',
            'privacy_version': '2026-10-22',
        },
    )
    assert registration.status_code == 201 and registration.json()['data']['email_verified']
    login = game.client.post(
        '/api/v1/auth/login',
        json={'email': 'separate@example.com', 'password': '123456789Strong!'},
        headers={'Origin': 'http://127.0.0.1:5173'},
    )
    assert login.status_code == 200
    assert login.headers['Access-Control-Allow-Origin'] == 'http://127.0.0.1:5173'
    assert 'X-Session-Token' in login.headers['Access-Control-Expose-Headers']
    token = login.headers['X-Session-Token']
    game.client.cookies.clear()
    headers = {
        'Authorization': 'Bearer ' + token,
        'Origin': 'http://127.0.0.1:5173',
        'Idempotency-Key': str(uuid.uuid4()),
    }
    created = game.client.post('/api/v1/campaigns', json={'locale': 'zh-TW'}, headers=headers)
    assert created.status_code == 202
    assert (
        game.client.options(
            '/api/v1/campaigns',
            headers={
                'Origin': 'http://127.0.0.1:5173',
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'authorization,content-type,idempotency-key',
            },
        ).status_code
        == 200
    )
    blocked = game.client.options(
        '/api/v1/campaigns', headers={'Origin': 'https://unknown.example', 'Access-Control-Request-Method': 'POST'}
    )
    assert blocked.status_code == 400 and 'Access-Control-Allow-Origin' not in blocked.headers
    monkeypatch.setenv('LIFE_DEVELOPMENT_MODE', '0')
    assert not handlers.email_bypass()
    monkeypatch.setenv('LIFE_DEVELOPMENT_MODE', '1')
    monkeypatch.setenv('LIFE_SKIP_EMAIL_VERIFICATION', '0')
    assert not handlers.email_bypass()
