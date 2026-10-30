"""Bounded, persistent background scenario jobs, separate from LLM requests."""

import concurrent.futures
import hashlib
import json
import logging
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from . import engine, store, scenarios, rebirth, content

INSTANCE = uuid.uuid4().hex
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='life-scenarios')
ACTIVE = ('QUEUED', 'RUNNING')
PUBLIC = (
    'id',
    'run_id',
    'run_version',
    'campaign_version',
    'status',
    'completed_points',
    'total_points',
    'results',
    'horizon_months',
    'samples',
    'notice',
    'created_at',
    'method_version',
)


def digest(value):
    return hashlib.sha256(store.j(value).encode()).hexdigest()


def public(job):
    return {k: job[k] for k in PUBLIC}


def context(c, r):
    return digest(
        [
            c['id'],
            c['version'],
            r['id'],
            r['version'],
            scenarios.VERSION,
            scenarios.SAMPLES,
            scenarios.HORIZON,
            content.CONTENT_VERSION,
        ]
    )


def recover(db, job):
    if job['status'] in ACTIVE and (job['_instance'] != INSTANCE or time.time() - job['_started'] > 240):
        job.update(status='FAILED', notice='分析已中斷，已完成的結果仍可閱讀；可繼續分析。')
        db.execute('UPDATE insight_jobs SET body=?,updated_at=? WHERE id=?', (store.j(job), time.time(), job['id']))
    return job


def load(db, id_, owner):
    row = db.execute('SELECT body FROM insight_jobs WHERE id=? AND owner=?', (id_, owner)).fetchone()
    if row is None:
        raise ValueError('NOT_FOUND')
    return recover(db, json.loads(row['body']))


def latest(db, owner, c, r):
    row = db.execute(
        'SELECT body FROM insight_jobs WHERE owner=? AND context_key=? ORDER BY created_at DESC LIMIT 1',
        (owner, context(c, r)),
    ).fetchone()
    return public(recover(db, json.loads(row['body']))) if row else None


def prepare(db, owner, c, r, key, body):
    if not isinstance(key, str) or not 8 <= len(key) <= 128:
        raise ValueError('IDEMPOTENCY_KEY_REQUIRED')
    request_hash = digest([r['id'], body])
    old = db.execute(
        'SELECT r.request_hash,j.body FROM insight_requests r JOIN insight_jobs j ON j.id=r.job_id WHERE r.owner=? AND r.key=?',
        (owner, key),
    ).fetchone()
    if old:
        if old['request_hash'] != request_hash:
            raise ValueError('IDEMPOTENCY_KEY_REUSED')
        return public(recover(db, json.loads(old['body']))), None
    if (
        type(body.get('expected_version')) is not int
        or body['expected_version'] != r['version']
        or type(body.get('expected_campaign_version')) is not int
        or body['expected_campaign_version'] != c['version']
    ):
        raise ValueError('STALE_VERSION')
    if (
        r['status'] != 'ENDED'
        or c['status'] != 'AWAITING_REBIRTH'
        or c['runs'][-1]['id'] != r['id']
        or len(c['runs']) >= 3
    ):
        raise ValueError('REBIRTH_NOT_AVAILABLE')
    count = db.execute(
        'SELECT COUNT(*) FROM insight_requests WHERE owner=? AND created_at>?', (owner, time.time() - 60)
    ).fetchone()[0]
    if count >= 8:
        raise ValueError('RATE_LIMITED')
    for row in db.execute("SELECT body FROM insight_jobs WHERE json_extract(body,'$.status') IN ('QUEUED','RUNNING')"):
        recover(db, json.loads(row['body']))
    ctx = context(c, r)
    cached = db.execute(
        'SELECT body FROM insight_jobs WHERE owner=? AND context_key=? ORDER BY created_at DESC LIMIT 1', (owner, ctx)
    ).fetchone()
    job = recover(db, json.loads(cached['body'])) if cached else None
    if job and job['status'] in (*ACTIVE, 'COMPLETE'):
        db.execute('INSERT INTO insight_requests VALUES(?,?,?,?,?)', (owner, key, request_hash, job['id'], time.time()))
        return public(job), None
    active = db.execute(
        "SELECT owner FROM insight_jobs WHERE json_extract(body,'$.status') IN ('QUEUED','RUNNING')"
    ).fetchall()
    if len(active) >= 2 or any(row['owner'] == owner for row in active):
        raise ValueError('ANALYSIS_BUSY')
    now = time.time()
    if job is None:
        job = {
            'id': engine.uid(),
            'run_id': r['id'],
            'run_version': r['version'],
            'campaign_version': c['version'],
            'status': 'QUEUED',
            'completed_points': 0,
            'total_points': len(rebirth.points(r)),
            'results': [],
            'horizon_months': scenarios.HORIZON,
            'samples': scenarios.SAMPLES,
            'notice': '正在背景比較，可以先查看回顧或選擇回溯日期。',
            'created_at': engine.now(),
            'method_version': scenarios.VERSION,
            '_seeds': [secrets.randbits(64) for _ in range(scenarios.SAMPLES)],
            '_instance': INSTANCE,
            '_started': now,
            '_attempt': engine.uid(),
        }
        db.execute(
            'INSERT INTO insight_jobs VALUES(?,?,?,?,?,?,?)', (job['id'], owner, r['id'], ctx, now, now, store.j(job))
        )
    else:
        job.update(
            status='QUEUED',
            notice='從尚未完成的日期繼續分析；既有結果已保留。',
            _instance=INSTANCE,
            _started=now,
            _attempt=engine.uid(),
        )
        db.execute('UPDATE insight_jobs SET body=?,updated_at=? WHERE id=?', (store.j(job), now, job['id']))
    db.execute('INSERT INTO insight_requests VALUES(?,?,?,?,?)', (owner, key, request_hash, job['id'], now))
    return public(job), (str(store.DB_FILE), job['id'], job['_attempt'], c['persona'], rebirth.preview_source(r))


@contextmanager
def connection(path):
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def update(path, id_, attempt, mutate):
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT body FROM insight_jobs WHERE id=?', (id_,)).fetchone()
        if row is None:
            return None
        job = json.loads(row['body'])
        if job['status'] not in ACTIVE or job['_attempt'] != attempt:
            return None
        mutate(job)
        db.execute('UPDATE insight_jobs SET body=?,updated_at=? WHERE id=?', (store.j(job), time.time(), id_))
        return job


def work(path, id_, attempt, persona, current):
    last_check = 0
    stopped = False

    def cancelled():
        nonlocal last_check, stopped
        if time.monotonic() - last_check > 0.15:
            last_check = time.monotonic()
            with connection(path) as db:
                row = db.execute('SELECT body FROM insight_jobs WHERE id=?', (id_,)).fetchone()
                j = json.loads(row['body']) if row else {}
                stopped = j.get('status') not in ACTIVE or j.get('_attempt') != attempt
        return stopped

    try:
        job = update(path, id_, attempt, lambda j: j.update(status='RUNNING'))
        if job is None:
            return
        done = {v['point_id'] for v in job['results']}
        for point in rebirth.points(current):
            if cancelled():
                return
            if point['id'] in done:
                continue
            value = scenarios.compare(persona, current, point, job['_seeds'], cancelled)
            if value is None:
                return

            def publish(j):
                j['results'].append(value)
                j['completed_points'] = len(j['results'])

            if update(path, id_, attempt, publish) is None:
                return
        update(
            path,
            id_,
            attempt,
            lambda j: j.update(status='COMPLETE', notice='比較完成。先看準備時間與資金壓力，再決定從哪一天開始。'),
        )
    except Exception:
        # Never publish partial numeric results for a failed point.
        logging.getLogger(__name__).exception('Scenario job failed: %s', id_)
        update(
            path,
            id_,
            attempt,
            lambda j: j.update(status='FAILED', notice='這次分析未完成，已完成的日期仍可閱讀；可稍後繼續。'),
        )


def submit(task):
    if task:
        POOL.submit(work, *task)
