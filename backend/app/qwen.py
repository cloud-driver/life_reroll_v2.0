"""Adapter for the user's stateful Workspace API, not OpenAI chat completions."""

from __future__ import annotations
import json
import os
import time
import threading
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

CONFIG_FILE = Path(__file__).resolve().parents[1] / 'ai-config.json'


class ProviderError(Exception):
    pass


class ConnectionUnavailable(ProviderError):
    pass


class Cancelled(Exception):
    pass


def valid_base(value):
    if not isinstance(value, str):
        return ''
    value = value.rstrip('/')
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ''
    return (
        value
        if parsed.scheme in ('http', 'https')
        and parsed.hostname
        and not (parsed.username or parsed.password or parsed.query or parsed.fragment)
        else ''
    )


def config():
    try:
        settings = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        settings = {}
    enabled = os.environ.get('LIFE_COACH_ENABLED', str(settings.get('enabled', False))).lower() in ('1', 'true', 'yes')
    base = valid_base(os.environ.get('LIFE_COACH_BASE_URL', settings.get('base_url', '')))
    # An explicit environment URL replaces the file's connection profile unless
    # fallbacks are also explicitly supplied. Tests and other installations stay isolated.
    fallbacks = os.environ.get('LIFE_COACH_FALLBACK_URLS')
    if fallbacks is not None:
        fallbacks = fallbacks.split(',')
    else:
        fallbacks = [] if 'LIFE_COACH_BASE_URL' in os.environ else settings.get('fallback_urls', [])
    if not isinstance(fallbacks, list):
        fallbacks = []
    fallbacks = list(
        dict.fromkeys(
            v
            for item in fallbacks[:4]
            if (v := valid_base(item.strip() if isinstance(item, str) else item)) and v != base
        )
    )
    try:
        timeout = max(5, min(600, float(os.environ.get('LIFE_COACH_TIMEOUT', settings.get('timeout_seconds', 180)))))
    except (ValueError, TypeError):
        timeout = 180
    return {'enabled': enabled and bool(base), 'base_url': base, 'fallback_urls': fallbacks, 'timeout': timeout}


def request(base, path, body=None, method=None, timeout=8):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
        headers={'Content-Type': 'application/json'},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read(256000))


def stop(base, chat_id):
    if not chat_id:
        return
    try:
        request(base, '/chats/' + chat_id + '/stop', {}, timeout=4)
    except (OSError, ValueError):
        pass


def open_chat(settings, is_cancelled):
    bases = list(dict.fromkeys([settings['base_url'], *settings.get('fallback_urls', [])]))
    for base in bases:
        if is_cancelled():
            raise Cancelled()
        try:
            if settings.get('fallback_urls'):
                health = request(base, '/health', timeout=3)
                if not isinstance(health, dict) or health.get('ready') is not True:
                    continue
            if is_cancelled():
                raise Cancelled()
            chat = request(base, '/chats', {'title': 'Life Reroll · 人生教練'}, timeout=3 if len(bases) > 1 else 8)
            chat_id = chat['id']
            if not isinstance(chat_id, str) or not chat_id.isalnum() or len(chat_id) > 100:
                raise ValueError('Invalid chat')
            return base, chat_id
        except (OSError, ValueError, KeyError, TypeError):
            # No generation has been submitted. A failed chat creation may leave
            # an empty upstream chat, but never a second generation.
            continue
    if is_cancelled():
        raise Cancelled()
    raise ConnectionUnavailable('PROVIDER_UNREACHABLE')


def generate(settings, system, text, on_chat, on_text, is_cancelled, max_tokens=650):
    """Each job owns one upstream chat. Never retry a submitted generation automatically."""
    if not isinstance(text, str) or len(text) > 12000 or not isinstance(system, str) or len(system) > 4000:
        raise ProviderError('Context too long')
    if type(max_tokens) is not int or not 1 <= max_tokens <= 4096:
        raise ProviderError('Invalid output limit')
    base = settings['base_url']
    chat_id = None
    raw = ''
    done = False
    stats = {}
    started = time.monotonic()
    deadline = None
    try:
        if is_cancelled():
            raise Cancelled()
        base, chat_id = open_chat(settings, is_cancelled)
        on_chat(chat_id, base)
        if is_cancelled():
            raise Cancelled()
        payload = {
            'chat_id': chat_id,
            'text': text,
            'system_prompt': system,
            'search': False,
            'memory': False,
            'temperature': 0.25,
            'max_tokens': max_tokens,
            'stream': True,
            'stream_format': 'ndjson',
        }
        req = urllib.request.Request(
            base + '/responses',
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={'Content-Type': 'application/json', 'Accept': 'application/x-ndjson'},
        )
        deadline = threading.Timer(settings['timeout'], stop, args=(base, chat_id))
        deadline.daemon = True
        deadline.start()
        with urllib.request.urlopen(req, timeout=settings['timeout']) as response:
            for line in response:
                if is_cancelled():
                    raise Cancelled()
                if time.monotonic() - started > settings['timeout']:
                    raise ProviderError('Deadline')
                if len(line) > 128000:
                    raise ProviderError('Invalid event')
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get('type') == 'delta':
                    chunk = event.get('text', '')
                    if not isinstance(chunk, str):
                        raise ProviderError('Invalid text')
                    raw += chunk
                    if len(raw) > 12000:
                        raise ProviderError('Reply too large')
                    on_text(raw)
                elif event.get('type') == 'done':
                    done = True
                    stats = event.get('stats') or {}
                    break
                elif event.get('type') in ('error', 'interrupted'):
                    raise ProviderError('Incomplete generation')
        if is_cancelled():
            raise Cancelled()
        if not done or stats.get('truncated'):
            raise ProviderError('Incomplete reply')
        return raw
    except Cancelled:
        stop(base, chat_id)
        raise
    except ProviderError:
        stop(base, chat_id)
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        stop(base, chat_id)
        raise ProviderError(type(exc).__name__) from exc
    finally:
        if deadline:
            deadline.cancel()
        # Chats contain fictional game context only; archive each finished or stopped job.
        if chat_id:
            try:
                request(base, '/chats/' + chat_id, method='DELETE', timeout=4)
            except (OSError, ValueError):
                pass
