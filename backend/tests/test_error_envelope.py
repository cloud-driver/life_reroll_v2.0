"""Framework-level failures and unreadable input answer in the public {data, error} envelope."""

import pytest
from fastapi.testclient import TestClient
from app import handlers, main
from app.main import app
from test_game import game

HEADERS = {'content-type': 'application/json', 'idempotency-key': 'envelope-test'}


def error_of(response, status, code):
    assert response.status_code == status, response.text[:300]
    body = response.json()
    assert body['data'] is None and body['error']['code'] == code
    assert any('一' <= ch <= '鿿' for ch in body['error']['message'])
    return body['error']


def test_unknown_route_and_wrong_method_use_the_envelope(game):
    error_of(game.client.get('/api/v1/no-such-resource'), 404, 'NOT_FOUND')
    error_of(game.client.get('/api/v1/runs/a%2Fb'), 404, 'NOT_FOUND')
    wrong_method = game.client.delete('/api/v1/bootstrap')
    error_of(wrong_method, 405, 'METHOD_NOT_ALLOWED')
    assert 'GET' in wrong_method.headers['allow']


def test_oversized_body_is_refused_with_or_without_a_declared_length(game):
    huge = b'{"email":"' + b'a' * (main.MAX_BODY_BYTES + 1) + b'"}'
    error_of(game.client.post('/api/v1/auth/login', content=huge, headers=HEADERS), 413, 'PAYLOAD_TOO_LARGE')

    def chunks():
        for start in range(0, len(huge), 65536):
            yield huge[start : start + 65536]

    error_of(game.client.post('/api/v1/auth/login', content=chunks(), headers=HEADERS), 413, 'PAYLOAD_TOO_LARGE')
    # A body at the limit is still parsed and answered as an ordinary credential failure.
    padded = b'{"email":"a@example.com","password":"' + b'x' * 1000 + b'"}'
    error_of(game.client.post('/api/v1/auth/login', content=padded, headers=HEADERS), 401, 'INVALID_CREDENTIALS')


@pytest.mark.parametrize('raw', [b'{"amount_minor": NaN}', b'{"amount_minor": Infinity}', b'{"x": -Infinity}'])
def test_non_finite_numbers_are_a_validation_error(game, raw):
    game.auth()
    _, run = game.new()
    headers = {**HEADERS, 'x-csrf-token': game.csrf}
    reply = game.client.post(f'/api/v1/runs/{run["id"]}/scene-transitions', content=raw, headers=headers)
    error_of(reply, 422, 'VALIDATION_ERROR')
    assert game.refresh(run)['version'] == run['version']


@pytest.mark.parametrize('raw', [b'[1,2]', b'"text"', b'7', b'[' * 100000])
def test_non_object_bodies_are_a_validation_error(game, raw):
    error_of(game.client.post('/api/v1/auth/login', content=raw, headers=HEADERS), 422, 'VALIDATION_ERROR')


def test_escaped_exception_hides_details_behind_the_envelope(game, monkeypatch):
    def explode(*_):
        raise RuntimeError('private traceback secret')

    monkeypatch.setattr(handlers, 'get_user', explode)
    quiet = TestClient(app, raise_server_exceptions=False)
    reply = quiet.get('/api/v1/report-exports/anything/download')
    error_of(reply, 503, 'SERVICE_UNAVAILABLE')
    assert 'secret' not in reply.text


@pytest.mark.parametrize('raw', [b'{bad', b'{"email": "a@example.com",}', b'\xff\xfe'])
def test_malformed_json_is_a_validation_error_not_a_credential_failure(game, raw):
    error_of(game.client.post('/api/v1/auth/login', content=raw, headers=HEADERS), 422, 'VALIDATION_ERROR')
