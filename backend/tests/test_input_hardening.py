"""Malformed account fields stay client errors without changing authentication outcomes."""

import pytest
from app import legal
from test_game import game


PASSWORD = '123456789Strong!'
REGISTRATION = {
    'email': 'hardened@example.test',
    'password': PASSWORD,
    'display_name': '測試玩家',
    'terms_version': legal.VERSION,
    'privacy_version': legal.VERSION,
}
NON_STRINGS = [5, [], {'a': 1}, False]


@pytest.mark.parametrize('email', NON_STRINGS)
def test_login_rejects_non_string_email(game, email):
    _, response = game.call('POST', '/auth/login', {'email': email, 'password': PASSWORD}, 422)
    assert response.json()['error']['code'] == 'VALIDATION_ERROR'


@pytest.mark.parametrize('password', NON_STRINGS)
def test_login_rejects_non_string_password(game, password):
    game.call('POST', '/auth/register', REGISTRATION, 201)
    _, response = game.call('POST', '/auth/login', {'email': REGISTRATION['email'], 'password': password}, 422)
    assert response.json()['error']['code'] == 'VALIDATION_ERROR'


@pytest.mark.parametrize('path', ['/auth/email-verification-requests', '/auth/password-reset-requests'])
@pytest.mark.parametrize('email', NON_STRINGS)
def test_email_requests_reject_non_string_email(game, path, email):
    _, response = game.call('POST', path, {'email': email}, 422)
    assert response.json()['error']['code'] == 'VALIDATION_ERROR'


@pytest.mark.parametrize(
    'field, code',
    [
        ('email', 'EMAIL_INVALID'),
        ('password', 'PASSWORD_LENGTH_INVALID'),
        ('display_name', 'DISPLAY_NAME_LENGTH_INVALID'),
        ('terms_version', 'LEGAL_VERSION_INVALID'),
        ('privacy_version', 'LEGAL_VERSION_INVALID'),
    ],
)
@pytest.mark.parametrize('value', NON_STRINGS)
def test_register_rejects_non_string_fields(game, field, code, value):
    _, response = game.call('POST', '/auth/register', {**REGISTRATION, field: value}, 422)
    assert response.json()['error']['code'] == code


def test_authentication_after_malformed_attempts_and_wrong_password_rate_limit(game):
    for email in NON_STRINGS:
        _, response = game.call('POST', '/auth/login', {'email': email, 'password': PASSWORD}, 422)
        assert response.json()['error']['code'] == 'VALIDATION_ERROR'
    user, _ = game.call('POST', '/auth/register', REGISTRATION, 201)
    for password in NON_STRINGS * 2:
        _, response = game.call('POST', '/auth/login', {'email': user['email'], 'password': password}, 422)
        assert response.json()['error']['code'] == 'VALIDATION_ERROR'
    session, _ = game.call('POST', '/auth/login', {'email': user['email'], 'password': PASSWORD}, 200)
    assert session['user']['id'] == user['id']
    game.csrf = session['csrf_token']
    wrong = {'email': user['email'], 'password': 'wrong string password'}
    _, response = game.call('POST', '/auth/login', wrong, 401)
    assert response.json()['error']['code'] == 'INVALID_CREDENTIALS'
    # A successful login still clears the failed-attempt counter.
    session, _ = game.call('POST', '/auth/login', {'email': user['email'], 'password': PASSWORD}, 200)
    game.csrf = session['csrf_token']
    for _ in range(5):
        _, response = game.call('POST', '/auth/login', wrong, 401)
        assert response.json()['error']['code'] == 'INVALID_CREDENTIALS'
    _, response = game.call('POST', '/auth/login', wrong, 429)
    assert response.json()['error']['code'] == 'RATE_LIMITED'


@pytest.mark.parametrize(
    'method, path, body, code',
    [
        ('POST', '/auth/email-verifications', {'email': {}}, 'VALIDATION_ERROR'),
        ('POST', '/auth/email-verifications', {'token': 5}, 'VALIDATION_ERROR'),
        ('POST', '/auth/password-resets', {'token': []}, 'VALIDATION_ERROR'),
        ('PUT', '/me/password', {'current_password': 5}, 'VALIDATION_ERROR'),
        (
            'PUT',
            '/me/password',
            {'current_password': PASSWORD, 'new_password': {}},
            'PASSWORD_LENGTH_INVALID',
        ),
        ('PATCH', '/me', {'display_name': 5}, 'VALIDATION_ERROR'),
        ('PUT', '/me/settings', {'locale': []}, 'VALIDATION_ERROR'),
        ('POST', '/me/deletion-requests', {'current_password': {}}, 'VALIDATION_ERROR'),
        (
            'POST',
            '/me/deletion-requests',
            {'current_password': PASSWORD, 'confirmation': []},
            'VALIDATION_ERROR',
        ),
    ],
)
def test_other_account_string_fields_reject_non_strings(game, method, path, body, code):
    game.auth()
    _, response = game.call(method, path, body, 422)
    assert response.json()['error']['code'] == code


@pytest.mark.parametrize(
    'method, path, body, status, code',
    [
        ('POST', '/auth/login', {}, 401, 'INVALID_CREDENTIALS'),
        # An explicit null keeps meaning "not provided", as it did before the type checks.
        ('POST', '/auth/login', {'email': None, 'password': None}, 401, 'INVALID_CREDENTIALS'),
        ('POST', '/auth/email-verifications', {'email': None, 'token': '000000'}, 422, 'VERIFICATION_CODE_EXPIRED'),
        ('POST', '/auth/password-reset-requests', {'email': None}, 202, None),
        ('POST', '/auth/login', {'email': 'player@example.com'}, 401, 'INVALID_CREDENTIALS'),
        ('POST', '/auth/register', {}, 422, 'EMAIL_INVALID'),
        ('POST', '/auth/password-resets', {}, 401, 'INVALID_TOKEN'),
        ('POST', '/auth/password-resets', {'token': 'wrong', 'new_password': 5}, 401, 'INVALID_TOKEN'),
        (
            'PUT',
            '/me/password',
            {'current_password': 'wrong', 'new_password': 5},
            401,
            'INVALID_CREDENTIALS',
        ),
        (
            'POST',
            '/me/deletion-requests',
            {'current_password': 'wrong', 'confirmation': []},
            401,
            'INVALID_CREDENTIALS',
        ),
        (
            'POST',
            '/me/deletion-requests',
            {'current_password': PASSWORD, 'confirmation': 'wrong'},
            401,
            'INVALID_CREDENTIALS',
        ),
    ],
)
def test_missing_fields_and_check_order_are_preserved(game, method, path, body, status, code):
    game.auth()
    _, response = game.call(method, path, body, status)
    assert code is None or response.json()['error']['code'] == code
