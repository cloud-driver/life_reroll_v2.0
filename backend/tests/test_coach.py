import copy
import json
import threading
import time
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from fastapi.testclient import TestClient
from test_game import game
from app import coach, content, engine, qwen, store
from app.main import app
from app.zh import traditional


def ask(game, r, question='目前資金有哪些取捨？', **extra):
    return game.call(
        'POST',
        f'/runs/{r["id"]}/coach',
        {'expected_version': r['version'], 'question': question, 'topic': 'finance', **extra},
        202,
    )[0]


def finished(game, id_):
    for _ in range(200):
        job = game.call('GET', f'/coach/jobs/{id_}', status=200)[0]
        if job['status'] not in coach.ACTIVE:
            return job
        time.sleep(0.01)
    raise AssertionError('coach job did not finish')


def test_conversion_and_reasoning_never_displayed():
    assert traditional('这笔保险理赔还没有到账，软件开发。') == '這筆保險理賠還沒有到帳，軟體開發。'
    assert coach.clean_reply('<think>简体推理私密内容</think>这笔钱尚未到账。[1][99]', 2) == '這筆錢尚未到帳。[1]'
    assert coach.clean_reply('<think>暂时还在思考', 2) == ''
    assert coach.clean_reply('<script>bad</script>这是解释', 2) == 'bad這是解釋'
    assert traditional('保險理賠 TWD 1,234.56 元') == '保險理賠 TWD 1,234.56 元'
    context = {'sources': [{'text': '可用資金 100,000.00 元'}]}
    assert coach.supported_amounts('可用資金為 100,000 元。', context)
    assert coach.supported_amounts('可用資金為 10 萬元。', context)
    assert not coach.supported_amounts('保證給付 900,000 元。', context)


def test_grounded_context_excludes_future_and_account_data():
    r = engine.create_run(content.PERSONAS[0], 17)
    r['campaign_id'] = 'campaign'
    before = copy.deepcopy(r)
    context = coach.run_context({'runs': [r]}, r, 'finance', 'COACH')
    raw = json.dumps(context, ensure_ascii=False)
    assert r == before
    assert all(
        x not in raw for x in ('"planned"', '"seed"', 'family_history', 'password', 'email', 'effect_multiplier_bps')
    )
    assert context['run_version'] == r['version'] and context['sources'][0]['label'] == '目前資金'
    assert '核准後延遲' in raw and '未入帳' in raw


def test_current_choice_preview_uses_engine_without_changing_save():
    r = engine.create_run(content.PERSONAS[0], 17)
    r['planned'] = [{'at_index': 1, 'card_id': 'TR01', 'anchor': False}]
    r.update(month_index=1, target_index=1, status='ADVANCING')
    r['advance'] = {'id': 'preview', 'from_date': '2026-01-01', 'status': 'PROCESSING', 'opening_state': r['initial']}
    engine.next_step(r)
    assert r['status'] == 'EVENT_PENDING'
    before = copy.deepcopy(r)
    event = engine.event_by_id(r, r['pending_event'])
    text = coach.choices_text(r, event)
    assert '規則試算' in text and '生活品質' in text and '每月薪資' in text
    assert r == before


def test_fallback_idempotency_cache_alias_and_unchanged_run(game):
    game.auth()
    c, r = game.new()
    before = game.refresh(r)
    key = str(uuid.uuid4())
    body = {'expected_version': r['version'], 'question': '目前可用資金？', 'topic': 'finance'}
    job = game.call('POST', f'/runs/{r["id"]}/coach', body, 202, key)[0]
    assert job['status'] == 'FALLBACK' and job['model'] is None
    assert job['sources'] and not any(k.startswith('_') for k in job)
    assert game.refresh(r) == before
    assert game.call('POST', f'/runs/{r["id"]}/coach', body, 202, key)[0]['id'] == job['id']
    # A cached answer also journals the second request key.
    alias = str(uuid.uuid4())
    assert game.call('POST', f'/runs/{r["id"]}/coach', body, 202, alias)[0]['id'] == job['id']
    _, response = game.call('POST', f'/runs/{r["id"]}/coach', {**body, 'question': '不同問題'}, 409, alias)
    assert response.json()['error']['code'] == 'IDEMPOTENCY_KEY_REUSED'
    updated = game.walk(r, 'FINANCE')
    assert updated['version'] != r['version']
    # Confirming a lost POST still returns its original answer after the player moves.
    assert game.call('POST', f'/runs/{r["id"]}/coach', body, 202, key)[0]['id'] == job['id']
    game.call('POST', f'/runs/{r["id"]}/coach', body, 409)


def test_full_permissions_validation_csrf_and_erasure(game):
    game.auth()
    c, r = game.new()
    job = ask(game, r)
    path = f'/api/v1/runs/{r["id"]}/coach'
    assert game.client.post(path, json={'question': '你好'}).status_code == 403
    game.call('POST', f'/runs/{r["id"]}/coach', {'expected_version': r['version'], 'question': '長' * 241}, 422)
    game.call(
        'POST', f'/runs/{r["id"]}/coach', {'expected_version': r['version'], 'question': '', 'kind': 'REVIEW'}, 409
    )
    game.call(
        'POST',
        f'/runs/{r["id"]}/coach',
        {'expected_version': r['version'], 'question': '你好', 'chat_id': 'someone-else'},
        422,
    )
    assert game.client.post(path, content='bad-json', headers={'X-CSRF-Token': game.csrf}).status_code == 422
    outsider = TestClient(app)
    assert outsider.get('/api/v1/coach/jobs/' + job['id']).status_code == 401
    original = dict(game.client.cookies)
    other = TestClient(app)
    game.client = other
    game.auth('other-coach@example.com')
    game.call('GET', f'/coach/jobs/{job["id"]}', status=404)
    game.call('GET', f'/runs/{r["id"]}/coach', status=404)
    game.client = TestClient(app)
    game.client.cookies.update(original)
    session = game.client.get('/api/v1/auth/session').json()['data']
    game.csrf = session['csrf_token']
    game.call(
        'POST',
        '/me/deletion-requests',
        {'current_password': '123456789Strong!', 'confirmation': 'DELETE_MY_ACCOUNT'},
        202,
    )
    with store.connect() as db:
        assert not db.execute('SELECT 1 FROM coach_jobs WHERE id=?', (job['id'],)).fetchone()
        assert not db.execute('SELECT 1 FROM coach_requests WHERE job_id=?', (job['id'],)).fetchone()


def test_demo_capabilities_separate_even_when_logged_in(game):
    game.auth()
    _, r = game.new()
    snap = {'age': 28, 'year': 2026, 'rolls': 0, 'cash': 18000000, 'savings': 30000000, 'stocks': 8000000}
    token = 'a' * 64
    headers = {'X-Demo-Coach-Token': token, 'Idempotency-Key': str(uuid.uuid4())}
    body = {'snapshot': snap, 'topic': 'finance', 'question': '可用資金和淨資產差在哪？'}
    response = game.client.post('/api/v1/coach/demo', json=body, headers=headers)
    assert response.status_code == 202, response.text
    job = response.json()['data']
    assert job['status'] == 'FALLBACK' and job['run_id'] == 'demo'
    assert game.client.get('/api/v1/coach/jobs/' + job['id'], headers=headers).status_code == 200
    assert game.client.get('/api/v1/coach/demo/latest', headers=headers).json()['data']['id'] == job['id']
    assert (
        game.client.get('/api/v1/coach/jobs/' + job['id'], headers={'X-Demo-Coach-Token': 'b' * 64}).status_code == 404
    )
    assert game.client.get('/api/v1/coach/jobs/' + job['id']).status_code == 404
    assert TestClient(app).post('/api/v1/coach/demo', json=body).status_code == 401
    assert (
        game.client.post(
            '/api/v1/coach/demo', json={**body, 'snapshot': {**snap, 'cash': True}}, headers=headers
        ).status_code
        == 422
    )
    assert (
        game.client.post(
            '/api/v1/coach/demo', json={**body, 'snapshot': {**snap, 'year': 2027}}, headers=headers
        ).status_code
        == 422
    )


def test_background_reply_does_not_lock_game_and_can_cancel(game, monkeypatch):
    game.auth()
    _, r = game.new()
    started = threading.Event()
    release = threading.Event()
    monkeypatch.setenv('LIFE_COACH_ENABLED', '1')

    def slow(settings, system, text, on_chat, on_text, is_cancelled, **kwargs):
        on_text('这笔保险还未到账。')
        started.set()
        release.wait(3)
        if is_cancelled():
            raise qwen.Cancelled()
        return '这笔保险还未到账，请以目前可用资金判断。'

    monkeypatch.setattr(qwen, 'generate', slow)
    job = ask(game, r)
    assert started.wait(2)
    try:
        partial = game.call('GET', f'/coach/jobs/{job["id"]}', status=200)[0]
        assert partial['text'] == '這筆保險還未到帳。'
        begin = time.monotonic()
        moved = game.walk(r, 'FINANCE')
        assert time.monotonic() - begin < 1
        assert moved['balances'] == r['balances']
        game.call('POST', f'/runs/{r["id"]}/coach', {'expected_version': moved['version'], 'question': '再問一題'}, 429)
        stopped = game.call('POST', f'/coach/jobs/{job["id"]}/cancel', {}, 200)[0]
        assert stopped['status'] == 'CANCELLED' and stopped['text'] == ''
    finally:
        release.set()
    time.sleep(0.05)
    assert finished(game, job['id'])['status'] == 'CANCELLED'


def test_grounded_review_recovery_and_retry(game, monkeypatch):
    game.auth()
    c, r = game.new()
    with store.tx() as db:
        raw = store.get_campaign(db, c['id'])
        raw['runs'][0]['status'] = 'ENDED'
        raw['runs'][0]['end_reason'] = 'AGE_COMPLETED'
        store.put_campaign(db, raw)
    r = game.refresh(r)
    job = ask(game, r, kind='REVIEW', topic='review')
    assert job['kind'] == 'REVIEW' and '下一輪可嘗試' in job['text']
    assert any('期初淨資產' in source['text'] for source in job['sources'])
    monkeypatch.setenv('LIFE_COACH_ENABLED', '1')
    monkeypatch.setattr(
        qwen,
        'generate',
        lambda *a, **kw: (
            '值得保留：这些是已经完成的选择。\n值得留意：资金还未到账。\n下一轮可尝试：比较预算与生活品质。'
        ),
    )
    retry = ask(game, r, kind='REVIEW', topic='review', retry=True)
    result = finished(game, retry['id'])
    assert result['status'] == 'COMPLETE' and '資金還未到帳' in result['text']
    assert result['id'] != job['id']
    with store.tx() as db:
        row = db.execute('SELECT body FROM coach_jobs WHERE id=?', (result['id'],)).fetchone()
        raw = json.loads(row['body'])
        raw['status'] = 'RUNNING'
        raw['_instance'] = 'old-process'
        db.execute('UPDATE coach_jobs SET body=? WHERE id=?', (store.j(raw), raw['id']))
    assert finished(game, result['id'])['status'] == 'FALLBACK'


@contextmanager
def provider(events):
    captured = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
            captured.append((self.path, data))
            self.send_response(200)
            self.send_header(
                'Content-Type', 'application/x-ndjson' if self.path.endswith('/responses') else 'application/json'
            )
            self.end_headers()
            if self.path.endswith('/chats'):
                self.wfile.write(b'{"id":"abc123"}')
            elif self.path.endswith('/stop'):
                self.wfile.write(b'{"ok":true}')
            else:
                for event in events:
                    self.wfile.write(json.dumps(event, ensure_ascii=False).encode() + b'\n')

        def do_DELETE(self):
            captured.append((self.path, 'archive'))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {'base_url': f'http://127.0.0.1:{server.server_port}/api/v1', 'timeout': 5}, captured
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_workspace_protocol_stream_completion_and_no_external_memory():
    events = [
        {'type': 'created', 'chat_id': 'abc123'},
        {'type': 'delta', 'text': '保险'},
        {'type': 'delta', 'text': '理赔尚未到账。'},
        {'type': 'done', 'stats': {}},
    ]
    seen = []
    with provider(events) as (settings, calls):
        text = qwen.generate(settings, 'system', 'question', lambda *x: None, seen.append, lambda: False)
        payload = next(data for path, data in calls if path.endswith('/responses'))
        assert text == '保险理赔尚未到账。' and len(seen) == 2
        assert payload['stream_format'] == 'ndjson' and payload['memory'] is False and payload['search'] is False
        assert 'messages' not in payload and 'model' not in payload and payload['chat_id'] == 'abc123'
        assert calls[-1][1] == 'archive'


@pytest.mark.parametrize(
    'tail', [[], [{'type': 'error', 'text': 'failed'}], [{'type': 'done', 'stats': {'truncated': True}}]]
)
def test_workspace_incomplete_stream_is_never_success(tail):
    with provider([{'type': 'delta', 'text': 'partial'}, *tail]) as (settings, calls):
        with pytest.raises(qwen.ProviderError):
            qwen.generate(settings, 'system', 'question', lambda *x: None, lambda x: None, lambda: False)
        assert any(path.endswith('/stop') for path, _ in calls)


def test_provider_failure_falls_back_without_touching_run(game, monkeypatch):
    game.auth()
    _, r = game.new()
    before = game.refresh(r)
    monkeypatch.setenv('LIFE_COACH_ENABLED', '1')

    def fail(*args, **kwargs):
        raise qwen.ProviderError('offline')

    monkeypatch.setattr(qwen, 'generate', fail)
    result = finished(game, ask(game, r)['id'])
    assert result['status'] == 'FALLBACK' and '遊戲資料說明' in result['notice']
    assert game.refresh(r) == before


def test_invented_amount_is_replaced_with_verified_game_explanation(game, monkeypatch):
    game.auth()
    _, r = game.new()
    monkeypatch.setenv('LIFE_COACH_ENABLED', '1')
    monkeypatch.setattr(qwen, 'generate', lambda *args, **kwargs: '系统保证你现在可以获得 999,999,999 元补助。')
    result = finished(game, ask(game, r)['id'])
    assert result['status'] == 'FALLBACK' and '999,999,999' not in result['text']


def test_oversized_reply_uses_short_explanation_without_changing_save(game, monkeypatch):
    game.auth()
    _, r = game.new()
    before = game.refresh(r)
    monkeypatch.setenv('LIFE_COACH_ENABLED', '1')
    monkeypatch.setattr(qwen, 'generate', lambda *args, **kwargs: '先比較日常支出與資金，並留意生活品質。' * 20)
    result = finished(game, ask(game, r)['id'])
    assert result['status'] == 'FALLBACK' and len(result['text']) <= 180
    assert game.refresh(r) == before


def test_short_fallbacks_cover_demo_topics_and_final_life():
    for topic in coach.TOPICS:
        assert len(coach.fallback({'run_id': 'full'}, 'COACH', topic)) <= 120
    assert len(coach.fallback({'run_id': 'demo'}, 'COACH', 'overview')) <= 120
    review = coach.fallback({'run_id': 'full', 'run_index': 3}, 'REVIEW', 'review')
    assert len(review) <= 120 and len(review.splitlines()) == 3
    assert '未來可嘗試' in review and '下一輪' not in review


def test_abandoned_other_players_jobs_release_capacity_after_restart(game, monkeypatch):
    game.auth()
    _, r = game.new()
    base = ask(game, r)
    with store.tx() as db:
        raw = json.loads(db.execute('SELECT body FROM coach_jobs WHERE id=?', (base['id'],)).fetchone()['body'])
        for i in range(4):
            old = {**raw, 'id': uuid.uuid4().hex, 'status': 'RUNNING', '_instance': 'old-process'}
            db.execute(
                'INSERT INTO coach_jobs VALUES(?,?,?,?,?,?,?,?,?)',
                (
                    old['id'],
                    f'demo:old-{i}',
                    'demo',
                    uuid.uuid4().hex,
                    'hash',
                    'context',
                    time.time(),
                    time.time(),
                    store.j(old),
                ),
            )
    monkeypatch.setenv('LIFE_COACH_ENABLED', '1')
    monkeypatch.setattr(qwen, 'generate', lambda *args, **kwargs: '請依目前資金與支出，保留可以立即使用的生活預備金。')
    result = finished(game, ask(game, r, '請說明目前的安排。')['id'])
    assert result['status'] == 'COMPLETE'
    with store.connect() as db:
        assert all(
            json.loads(row['body'])['status'] == 'FALLBACK'
            for row in db.execute("SELECT body FROM coach_jobs WHERE owner LIKE 'demo:old-%'")
        )
