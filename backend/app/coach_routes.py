"""Authenticated full-game coaching and isolated, bounded anonymous demo coaching."""

from starlette.concurrency import run_in_threadpool
import hashlib
import json
import re
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from . import coach, handlers, store, qwen
from .zh import traditional

router = APIRouter(prefix='/api/v1', tags=['AI 人生教練'])


def envelope(data, status=200):
    return JSONResponse({'data': data, 'meta': {'api_version': 'v1'}}, status_code=status)


from .errors import response as error_response


def error(exc):
    return error_response(exc)


def owner(db, request, demo=False):
    token = request.headers.get('x-demo-coach-token', '')
    if (demo or request.url.path.startswith('/api/v1/coach/')) and re.fullmatch(r'[0-9a-f]{64}', token):
        return 'demo:' + hashlib.sha256(token.encode()).hexdigest(), None
    user, _ = handlers.get_user(db, request)
    if user and not demo:
        handlers.verify_csrf(request, user)
        return 'user:' + user['id'], user
    raise ValueError('UNAUTHENTICATED')


def fields(body):
    kind = body.get('kind', 'COACH')
    topic = body.get('topic', 'overview')
    question = body.get('question', '')
    if kind not in ('COACH', 'REVIEW') or topic not in coach.TOPICS or type(body.get('retry', False)) is not bool:
        raise ValueError('VALIDATION_ERROR')
    if not isinstance(question, str) or len(question) > 240:
        raise ValueError('QUESTION_LENGTH_INVALID')
    question = traditional(question.strip())
    if kind == 'REVIEW':
        question = '請回顧本輪的選擇與取捨，並給下一輪一個可嘗試的方向。'
        topic = 'review'
    elif not question:
        raise ValueError('QUESTION_REQUIRED')
    return kind, topic, question


async def parse_body(request):
    raw = await request.body()
    if len(raw) > 16384:
        raise ValueError('VALIDATION_ERROR')
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError('VALIDATION_ERROR')
    if not isinstance(body, dict):
        raise ValueError('VALIDATION_ERROR')
    return body


@router.get('/runs/{run_id}/coach')
def latest(run_id: str, request: Request, kind: str = 'COACH', topic: str = 'overview'):
    try:
        if kind not in ('COACH', 'REVIEW') or topic not in coach.TOPICS:
            raise ValueError('VALIDATION_ERROR')
        with store.tx() as db:
            who, user = owner(db, request)
            if not user:
                raise ValueError('UNAUTHENTICATED')
            c, r = handlers.owned_run(db, {'run_id': run_id}, user)
            value = coach.latest(db, who, {'run_id': r['id'], 'run_version': r['version']}, kind, topic)
        return envelope(value)
    except ValueError as exc:
        return error(exc)


@router.post('/runs/{run_id}/coach')
async def ask(run_id: str, request: Request):
    try:
        body = await parse_body(request)
    except ValueError as exc:
        return error(exc)
    return await run_in_threadpool(ask_sync, run_id, request, body)


def ask_sync(run_id: str, request: Request, body):
    try:
        if not isinstance(body, dict) or set(body) - {'kind', 'topic', 'question', 'expected_version', 'retry'}:
            raise ValueError('VALIDATION_ERROR')
        kind, topic, question = fields(body)
        with store.tx() as db:
            who, user = owner(db, request)
            if not user:
                raise ValueError('UNAUTHENTICATED')
            c, r = handlers.owned_run(db, {'run_id': run_id}, user)
            key = request.headers.get('idempotency-key', '')
            request_hash = coach.digest([run_id, body])
            existing = db.execute(
                'SELECT j.body,r.request_hash FROM coach_requests r JOIN coach_jobs j ON j.id=r.job_id WHERE r.owner=? AND r.key=?',
                (who, key),
            ).fetchone()
            if existing:
                if existing['request_hash'] != request_hash:
                    raise ValueError('IDEMPOTENCY_KEY_REUSED')
                return envelope(coach.public(coach.recover(db, json.loads(existing['body']))), 202)
            if type(body.get('expected_version')) is not int or body['expected_version'] != r['version']:
                raise ValueError('STALE_VERSION')
            if kind == 'REVIEW' and r['status'] != 'ENDED':
                raise ValueError('REPORT_NOT_READY')
            context = coach.run_context(c, r, topic, kind)
            peer = hashlib.sha256((request.client.host if request.client else 'unknown').encode()).hexdigest()
            job, task = coach.prepare(
                db, who, peer, context, kind, topic, question, key, body.get('retry', False), request_hash
            )
        coach.submit(task)
        return envelope(job, 202)
    except (ValueError, TypeError, KeyError) as exc:
        return error(exc if isinstance(exc, ValueError) else ValueError('VALIDATION_ERROR'))


@router.post('/coach/demo')
async def demo_ask(request: Request):
    try:
        body = await parse_body(request)
    except ValueError as exc:
        return error(exc)
    return await run_in_threadpool(demo_ask_sync, request, body)


def demo_ask_sync(request: Request, body):
    try:
        if not isinstance(body, dict) or set(body) - {'kind', 'topic', 'question', 'snapshot', 'retry'}:
            raise ValueError('VALIDATION_ERROR')
        kind, topic, question = fields(body)
        with store.tx() as db:
            who, _ = owner(db, request, demo=True)
            context = coach.demo_context(body.get('snapshot'), topic, kind)
            peer = hashlib.sha256((request.client.host if request.client else 'unknown').encode()).hexdigest()
            job, task = coach.prepare(
                db,
                who,
                peer,
                context,
                kind,
                topic,
                question,
                request.headers.get('idempotency-key', ''),
                body.get('retry', False),
            )
        coach.submit(task)
        return envelope(job, 202)
    except (ValueError, TypeError, KeyError) as exc:
        return error(exc if isinstance(exc, ValueError) else ValueError('VALIDATION_ERROR'))


@router.get('/coach/demo/latest')
def demo_latest(request: Request):
    try:
        with store.tx() as db:
            who, _ = owner(db, request, demo=True)
            row = db.execute(
                'SELECT body FROM coach_jobs WHERE owner=? ORDER BY created_at DESC LIMIT 1', (who,)
            ).fetchone()
            value = coach.public(coach.recover(db, json.loads(row['body']))) if row else None
        return envelope(value)
    except ValueError as exc:
        return error(exc)


@router.get('/coach/jobs/{job_id}')
def get_job(job_id: str, request: Request):
    try:
        with store.tx() as db:
            who, _ = owner(db, request)
            job = coach.recover(db, coach.load(db, job_id, who))
        return envelope(coach.public(job))
    except ValueError as exc:
        return error(exc)


@router.post('/coach/jobs/{job_id}/cancel')
def cancel_job(job_id: str, request: Request, background_tasks: BackgroundTasks):
    try:
        with store.tx() as db:
            who, _ = owner(db, request)
            job = coach.load(db, job_id, who)
            if job['status'] in coach.ACTIVE:
                job.update(status='CANCELLED', text='', progress='已停止', notice='已停止這次回答，遊戲進度不受影響。')
                db.execute('UPDATE coach_jobs SET body=? WHERE id=?', (store.j(job), job_id))
                if job.get('_chat_id'):
                    background_tasks.add_task(qwen.stop, job['_base_url'], job['_chat_id'])
        return envelope(coach.public(job))
    except ValueError as exc:
        return error(exc)
