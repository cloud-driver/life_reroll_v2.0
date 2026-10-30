"""Real routes/transactions; SMTP is captured so tests cannot send external mail."""

import json
import time
import threading
import pytest
from app import mail, store, legal
from test_game import game

PASSWORD = 'FixturePassword20261022!'


@pytest.fixture
def smtp(game, monkeypatch):
    monkeypatch.setenv('LIFE_EMAIL_MODE', 'smtp')
    monkeypatch.setenv('LIFE_SKIP_EMAIL_VERIFICATION', '1')  # Never bypasses SMTP mode.
    monkeypatch.setattr(
        mail, 'config', lambda: {'mode': 'smtp', 'otp_secret': 'isolated-test-secret-with-more-than-32-chars'}
    )
    tasks = []
    monkeypatch.setattr(mail, 'submit', lambda task: tasks.append(task) if task else None)
    return game, tasks


def register(g, email='verify@example.test'):
    return g.call(
        'POST',
        '/auth/register',
        {
            'email': email,
            'password': PASSWORD,
            'display_name': '驗證測試員',
            'terms_version': legal.VERSION,
            'privacy_version': legal.VERSION,
        },
        201,
    )


def login(g, email='verify@example.test'):
    data, _ = g.call('POST', '/auth/login', {'email': email, 'password': PASSWORD}, 200)
    g.csrf = data['csrf_token']
    return data


def age_delivery(uid):
    with store.tx() as db:
        db.execute('UPDATE mail_deliveries SET created_at=created_at-61 WHERE user_id=?', (uid,))


def test_strict_registration_hash_only_and_single_use(smtp):
    g, tasks = smtp
    user, response = register(g)
    assert not user['email_verified'] and 'X-Dev-Verification-Token' not in response.headers
    assert g.call('GET', '/bootstrap', status=200)[0]['email_verification_required']
    assert len(tasks) == 1 and len(tasks[0][-1]) == 6 and tasks[0][-1].isascii()
    code = tasks[0][-1]
    with store.tx() as db:
        challenge = dict(db.execute('SELECT * FROM email_challenges').fetchone())
        assert challenge['code_hash'] == mail.code_hash(user['email'], code)
        assert code not in json.dumps(challenge)
        consent = db.execute('SELECT * FROM legal_acceptances').fetchone()
        assert consent['terms_version'] == legal.VERSION and consent['privacy_version'] == legal.VERSION
    g.call('POST', '/auth/email-verifications', {'email': user['email'], 'token': code}, 401)
    login(g)
    g.call('POST', '/campaigns', {'locale': 'zh-TW'}, 403)
    state = g.call('GET', '/me/email-verification', status=200)[0]
    assert state['delivery_status'] == 'QUEUED' and state['retry_after_seconds'] > 0
    g.call('POST', '/auth/email-verifications', {'token': code}, 200)
    assert g.call('GET', '/auth/session', status=200)[0]['user']['email_verified']
    g.call('POST', '/auth/email-verifications', {'token': code}, 422)
    g.new()


def test_attempts_commit_lockout_expiry_and_resend(smtp):
    g, tasks = smtp
    user, _ = register(g)
    login(g)
    code = tasks[-1][-1]
    wrong = '000000' if code != '000000' else '111111'
    for n in range(5):
        g.call('POST', '/auth/email-verifications', {'token': wrong}, 429 if n == 4 else 422)
        assert g.call('GET', '/me/email-verification', status=200)[0]['attempts_remaining'] == 4 - n
    g.call('POST', '/auth/email-verifications', {'token': code}, 429)
    # A05's public request route.
    from app.main import REGISTRY

    path = next(x['path'][7:] for x in REGISTRY if x['id'] == 'A05')
    g.call('POST', path, {'email': user['email']}, 429)
    age_delivery(user['id'])
    g.call('POST', path, {'email': user['email']}, 202)
    latest = tasks[-1][-1]
    assert latest != code
    g.call('POST', '/auth/email-verifications', {'token': code}, 422)
    with store.tx() as db:
        db.execute('UPDATE email_challenges SET expires_at=?', (time.time() - 1,))
    g.call('POST', '/auth/email-verifications', {'token': latest}, 422)
    age_delivery(user['id'])
    g.call('POST', path, {'email': user['email']}, 202)
    g.call('POST', '/auth/email-verifications', {'token': tasks[-1][-1]}, 200)


def test_ownership_csrf_and_resend_privacy(smtp):
    g, tasks = smtp
    first, _ = register(g)
    code = tasks[-1][-1]
    other, _ = register(g, 'other@example.test')
    login(g, 'other@example.test')
    g.call('POST', '/auth/email-verifications', {'email': first['email'], 'token': code}, 422)
    with store.tx() as db:
        assert db.execute('SELECT attempts FROM email_challenges WHERE user_id=?', (first['id'],)).fetchone()[0] == 0
    assert g.client.post('/api/v1/auth/email-verifications', json={'token': tasks[-1][-1]}).status_code == 403
    assert g.call('GET', '/me/email-verification', status=200)[0]['email'] == other['email']
    g.call('POST', '/auth/logout', {}, 204)
    g.csrf = None
    g.call('GET', '/me/email-verification', status=401)
    from app.main import REGISTRY

    path = next(x['path'][7:] for x in REGISTRY if x['id'] == 'A05')
    before = len(tasks)
    g.call('POST', path, {'email': first['email']}, 202)
    assert len(tasks) == before


def test_background_delivery_does_not_lock_game_and_recovers(smtp, monkeypatch):
    g, tasks = smtp
    user, _ = register(g)
    task = tasks[-1]
    entered = threading.Event()
    release = threading.Event()

    def fake_send(*args):
        entered.set()
        assert release.wait(5)

    monkeypatch.setattr(mail, 'send', fake_send)
    worker = threading.Thread(target=mail.work, args=task)
    worker.start()
    assert entered.wait(3)
    try:
        with store.tx() as db:
            assert db.execute('SELECT status FROM mail_deliveries').fetchone()[0] == 'SENDING'
            db.execute('UPDATE users SET display_name=? WHERE id=?', ('可同時操作', user['id']))
    finally:
        release.set()
        worker.join(5)
    with store.tx() as db:
        assert db.execute('SELECT status FROM mail_deliveries').fetchone()[0] == 'SENT'
    age_delivery(user['id'])
    with store.tx() as db:
        row = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
        _, task = mail.prepare_verification(db, row)
    monkeypatch.setattr(mail, 'send', lambda *args: (_ for _ in ()).throw(OSError('private provider error')))
    mail.work(*task)
    with store.tx() as db:
        row = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
        state = mail.state(db, row)
        assert state['delivery_status'] == 'FAILED' and state['retry_after_seconds'] == 0
        _, task = mail.prepare_verification(db, row)
        db.execute("UPDATE mail_deliveries SET instance_id='old-process' WHERE id=?", (task[1],))
        mail.recover(db)
        assert db.execute('SELECT status FROM mail_deliveries WHERE id=?', (task[1],)).fetchone()[0] == 'FAILED'


def test_limits_and_account_erasure_cascade(smtp):
    g, tasks = smtp
    user, _ = register(g)
    login(g)
    with store.tx() as db:
        row = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
        for _ in range(5):
            db.execute('UPDATE mail_deliveries SET created_at=created_at-61 WHERE user_id=?', (user['id'],))
            mail.prepare_verification(db, row)
        db.execute('UPDATE mail_deliveries SET created_at=created_at-61 WHERE user_id=?', (user['id'],))
        with pytest.raises(ValueError, match='EMAIL_RATE_LIMITED'):
            mail.prepare_verification(db, row)
    g.call('POST', '/me/deletion-requests', {'current_password': PASSWORD, 'confirmation': 'DELETE_MY_ACCOUNT'}, 202)
    for task in tasks:
        mail.work(*task)  # Deleted queued tasks must not send or recreate rows.
    with store.tx() as db:
        for table in ('email_challenges', 'mail_deliveries', 'legal_acceptances'):
            assert db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0


def test_reset_delivery_and_versioned_legal(smtp):
    g, tasks = smtp
    user, _ = register(g)
    from app.main import REGISTRY

    path = next(x['path'][7:] for x in REGISTRY if x['id'] == 'A07')
    _, response = g.call('POST', path, {'email': user['email']}, 202)
    reset = tasks[-1][-1]
    assert tasks[-1][-2] == 'RESET' and len(reset) > 30
    assert 'X-Dev-Verification-Token' not in response.headers
    with store.tx() as db:
        assert reset not in db.execute('SELECT token_hash FROM tokens').fetchone()[0]
    path = next(x['path'][7:] for x in REGISTRY if x['id'] == 'A08')
    g.call('POST', path, {'token': reset, 'new_password': PASSWORD + 'new'}, 200)
    g.call('POST', path, {'token': reset, 'new_password': PASSWORD}, 401)
    for kind, title in [('TERMS', '服務條款'), ('PRIVACY', '隱私政策')]:
        document = g.call('GET', '/content/legal/' + kind, status=200)[0]
        assert document['title'] == title and document['version'] == legal.VERSION
        assert '知與科技' in document['body'] and legal.CONTACT in document['body'] and len(document['body']) > 1000


def test_settings_partial_validation_preserves_other_fields(game):
    game.auth()
    game.call('PUT', '/me/settings', {'text_scale': 1.5, 'tutorial_completed': True}, 200)
    settings, _ = game.call('PUT', '/me/settings', {'reduced_motion': True}, 200)
    assert settings['text_scale'] == 1.5 and settings['tutorial_completed'] and settings['reduced_motion']
    for invalid in [{'reduced_motion': 'false'}, {'reduced_motion': 0}, {'text_scale': True}, {'text_scale': 4}]:
        game.call('PUT', '/me/settings', invalid, 422)
    assert game.call('GET', '/me/settings', status=200)[0]['reduced_motion']


def test_mail_configuration_requires_explicit_development(monkeypatch, tmp_path):
    monkeypatch.setenv('LIFE_MAIL_CONFIG', str(tmp_path / 'absent.json'))
    for key in ('LIFE_SMTP_HOST', 'LIFE_SMTP_FROM', 'LIFE_OTP_SECRET'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv('LIFE_EMAIL_MODE')
    assert not mail.bypass()
    with pytest.raises(ValueError, match='MAIL_NOT_CONFIGURED'):
        mail.config()
    monkeypatch.setenv('LIFE_EMAIL_MODE', 'development')
    monkeypatch.setenv('LIFE_DEVELOPMENT_MODE', '0')
    with pytest.raises(ValueError, match='MAIL_NOT_CONFIGURED'):
        mail.config()
    assert not mail.expose_tokens() and not mail.bypass()


def test_unconfigured_registration_rolls_back_instead_of_stranding_user(smtp, monkeypatch):
    g, tasks = smtp
    monkeypatch.setattr(mail, 'config', lambda: (_ for _ in ()).throw(ValueError('MAIL_NOT_CONFIGURED')))
    response = g.client.post(
        '/api/v1/auth/register',
        json={
            'email': 'blocked@example.test',
            'password': PASSWORD,
            'display_name': '寄信測試員',
            'terms_version': legal.VERSION,
            'privacy_version': legal.VERSION,
        },
    )
    assert response.status_code == 503 and response.json()['error']['code'] == 'MAIL_NOT_CONFIGURED'
    with store.tx() as db:
        for table in ('users', 'email_challenges', 'mail_deliveries', 'legal_acceptances'):
            assert db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0
    assert not tasks and PASSWORD not in response.text


def test_queue_bound_and_encrypted_smtp(smtp, monkeypatch):
    g, tasks = smtp
    user, _ = register(g)
    with store.tx() as db:
        row = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
        db.execute('UPDATE mail_deliveries SET created_at=created_at-61')
        for n in range(11):
            db.execute(
                'INSERT INTO mail_deliveries VALUES(?,?,?,?,?,?,?,?)',
                ('busy' + str(n), user['id'], 'RESET', 'QUEUED', time.time(), time.time(), mail.INSTANCE, None),
            )
        # Use another user to isolate the global cap from the per-account rate cap.
        with pytest.raises(ValueError, match='MAIL_BUSY'):
            mail.enqueue(db, {'id': 'new-user', 'email': 'new@example.test'}, 'VERIFY', '000000')
    events = []
    cfg = {
        'mode': 'smtp',
        'host': 'smtp.example.test',
        'port': 587,
        'from_email': 'sender@example.test',
        'from_name': '知與科技',
        'tls': 'starttls',
        'username': 'sender',
        'password': 'fixture',
    }
    monkeypatch.setattr(mail, 'config', lambda: cfg)

    class SMTP:
        def __init__(self, host, port, **kwargs):
            assert host == cfg['host'] and port == 587 and kwargs['timeout'] == 20

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def ehlo(self):
            events.append('ehlo')

        def starttls(self, context):
            assert context.check_hostname
            events.append('tls')

        def login(self, *args):
            events.append('login')

        def send_message(self, message):
            assert message['To'] == 'recipient@example.test' and '123456' in message.get_content()
            assert message['Date'] and message['Message-ID']
            assert 'fixture' not in str(message)
            events.append('send')

    monkeypatch.setattr(mail.smtplib, 'SMTP', SMTP)
    mail.send('recipient@example.test', 'VERIFY', '123456')
    assert events == ['ehlo', 'tls', 'ehlo', 'login', 'send']
