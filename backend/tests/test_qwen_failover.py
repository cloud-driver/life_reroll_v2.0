"""Endpoint selection must fail over before, and never replay after, generation."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import pytest
from app import qwen


@contextmanager
def workspace(ready=True, chat_status=200, complete=True):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, value, status=200):
            self.send_response(status)
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

        def do_GET(self):
            calls.append(('GET', self.path))
            self.reply({'ready': ready}, 200 if ready else 503)

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
            calls.append(('POST', self.path))
            if self.path.endswith('/chats'):
                self.reply({'id': 'owned123'}, chat_status)
            elif self.path.endswith('/stop'):
                self.reply({'ok': True})
            else:
                assert data['chat_id'] == 'owned123'
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"type":"delta","text":"connected"}\n')
                if complete:
                    self.wfile.write(b'{"type":"done","stats":{}}\n')

        def do_DELETE(self):
            calls.append(('DELETE', self.path))
            self.reply({'ok': True})

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/api/v1', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def generate(primary, backup, on_chat=lambda *a: None, cancelled=lambda: False):
    return qwen.generate(
        {'base_url': primary, 'fallback_urls': [backup], 'timeout': 5},
        'system',
        'question',
        on_chat,
        lambda x: None,
        cancelled,
    )


def test_unreachable_primary_uses_backup_and_keeps_actual_chat_host():
    with workspace(ready=False) as (primary, first), workspace() as (backup, second):
        chats = []
        assert generate(primary, backup, lambda *a: chats.append(a)) == 'connected'
        assert first == [('GET', '/api/v1/health')]
        assert chats == [('owned123', backup)]
        assert second[-1] == ('DELETE', '/api/v1/chats/owned123')
        assert sum(path.endswith('/responses') for _, path in second) == 1


def test_healthy_primary_does_not_contact_backup():
    with workspace() as (primary, first), workspace() as (backup, second):
        assert generate(primary, backup) == 'connected'
        assert not second and sum(path.endswith('/responses') for _, path in first) == 1


def test_both_unavailable_never_submit_a_generation():
    with workspace(ready=False) as (primary, first), workspace(ready=False) as (backup, second):
        with pytest.raises(qwen.ConnectionUnavailable, match='PROVIDER_UNREACHABLE'):
            generate(primary, backup)
        assert first == second == [('GET', '/api/v1/health')]


def test_chat_creation_failure_can_switch_before_generation():
    with workspace(chat_status=503) as (primary, first), workspace() as (backup, second):
        assert generate(primary, backup) == 'connected'
        assert not any(path.endswith('/responses') for _, path in first)
        assert sum(path.endswith('/responses') for _, path in second) == 1


def test_incomplete_generation_is_never_replayed_on_backup():
    with workspace(complete=False) as (primary, first), workspace() as (backup, second):
        with pytest.raises(qwen.ProviderError):
            generate(primary, backup)
        assert not second
        assert ('POST', '/api/v1/chats/owned123/stop') in first
        assert sum(path.endswith('/responses') for _, path in first) == 1


def test_cancel_after_backup_chat_stops_and_archives_only_its_owner():
    with workspace(ready=False) as (primary, first), workspace() as (backup, second):
        cancelled = False

        def on_chat(*args):
            nonlocal cancelled
            assert args == ('owned123', backup)
            cancelled = True

        with pytest.raises(qwen.Cancelled):
            generate(primary, backup, on_chat, lambda: cancelled)
        assert first == [('GET', '/api/v1/health')]
        assert ('POST', '/api/v1/chats/owned123/stop') in second
        assert not any(path.endswith('/responses') for _, path in second)
        assert second[-1] == ('DELETE', '/api/v1/chats/owned123')


def test_cancel_before_connection_does_not_probe_or_create():
    with workspace() as (primary, first), workspace() as (backup, second):
        with pytest.raises(qwen.Cancelled):
            generate(primary, backup, cancelled=lambda: True)
        assert not first and not second


def test_explicit_environment_url_does_not_inherit_private_fallbacks(monkeypatch, tmp_path):
    path = tmp_path / 'config.json'
    path.write_text(
        json.dumps({'enabled': True, 'base_url': 'http://primary/api/v1', 'fallback_urls': ['http://private/api/v1']})
    )
    monkeypatch.setattr(qwen, 'CONFIG_FILE', path)
    monkeypatch.setenv('LIFE_COACH_ENABLED', '1')
    monkeypatch.setenv('LIFE_COACH_BASE_URL', 'http://override/api/v1')
    monkeypatch.delenv('LIFE_COACH_FALLBACK_URLS', raising=False)
    assert qwen.config()['fallback_urls'] == []
    monkeypatch.setenv('LIFE_COACH_FALLBACK_URLS', 'http://backup/api/v1,http://backup/api/v1,javascript:bad')
    assert qwen.config()['fallback_urls'] == ['http://backup/api/v1']
