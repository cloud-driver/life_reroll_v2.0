"""Authenticated local/enterprise training APIs; all writes are idempotent."""

import hashlib
import json
import time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from . import (
    handlers,
    store,
    engine,
    training_service as svc,
    training_catalog as catalog,
    training_engine as sim,
    training_jobs as jobs,
    training_materials as materials,
)

router = APIRouter(prefix='/api/v1/training', tags=['通路情境訓練'])
from .errors import response as error_response


def fail(error):
    return error_response(error)


def handle(op, db, u, b, p, tasks):
    uid = u['id'] if u else None
    is_admin = svc.admin(db, u)
    if op == 'capabilities':
        return {
            'llm': jobs.status(),
            'stock_count': 20,
            'version': catalog.VERSION,
            'formats': ['pdf', 'docx', 'pptx', 'txt', 'md'],
            'max_upload_bytes': materials.MAX_BYTES,
        }
    if op == 'catalog':
        return {
            'products': catalog.products(),
            'stocks': catalog.STOCKS,
            'sources': catalog.SOURCES,
            'base_course': catalog.base_course() if is_admin else None,
            'event_templates': catalog.EVENTS if is_admin else [],
        }
    svc.require(u, 'UNAUTHENTICATED')
    if op == 'session':
        return {'is_instructor': is_admin, 'user': handlers.user_view(u), 'llm': jobs.status()}
    if op == 'courses':
        rows = db.execute(
            "SELECT owner,body FROM training_courses WHERE owner=? OR owner IS NULL ORDER BY created_at DESC", (uid,)
        ).fetchall()
        return [
            {
                k: v
                for k, v in json.loads(r['body']).items()
                if is_admin
                and (r['owner'] == uid or r['owner'] is None)
                or k in ('id', 'title', 'audience', 'status', 'revision', 'created_at', 'review_notice')
            }
            for r in rows
        ]
    if op == 'runs':
        return [
            {
                'id': r['id'],
                'class_title': r['title'],
                'state': {
                    'course_title': r['course_title'],
                    'status': r['status'],
                    'month': r['month'],
                    'horizon_months': r['horizon'],
                },
            }
            for r in db.execute(
                '''SELECT r.id,json_extract(c.body,'$.title') title,
   json_extract(r.body,'$._course.title') course_title,json_extract(r.body,'$.status') status,
   json_extract(r.body,'$.month') month,json_extract(r.body,'$._course.rules.horizon_months') horizon
   FROM training_runs r JOIN training_classes c ON c.id=r.class_id WHERE r.user_id=? ORDER BY r.created_at DESC LIMIT 100''',
                (uid,),
            )
        ]
    if op == 'join':
        return svc.join(db, u, b.get('code'))
    if op == 'run':
        return {'id': p['run_id'], 'state': sim.public(svc.owned_run(db, uid, p['run_id']))}
    if op == 'action':
        return svc.action(db, u, p['run_id'], b)
    if op == 'quote':
        r = svc.owned_run(db, uid, p['run_id'])
        svc.require(r['version'] == b.get('expected_version'), 'STALE_VERSION')
        svc.require(isinstance(b.get('params'), dict))
        return sim.quote(r, b.get('action'), b['params'])
    svc.require(is_admin, 'INSTRUCTOR_REQUIRED')
    if op == 'materials':
        return [
            jobs.recover_material(db, r)
            for r in db.execute(
                'SELECT id,owner,name,kind,body,created_at FROM training_materials WHERE owner=? ORDER BY created_at DESC',
                (uid,),
            ).fetchall()
        ]
    if op == 'material_add':
        active = db.execute(
            "SELECT count(*) FROM training_materials WHERE json_extract(body,'$.status')='PARSING'"
        ).fetchone()[0]
        svc.require(active < 4, 'MATERIAL_QUEUE_FULL')
        total = db.execute(
            'SELECT coalesce(sum(length(raw)),0) FROM training_materials WHERE owner=?', (uid,)
        ).fetchone()[0]
        svc.require(total < 64 * 1024 * 1024, 'MATERIAL_STORAGE_LIMIT')
        svc.require(
            db.execute('SELECT count(*) FROM training_materials WHERE owner=?', (uid,)).fetchone()[0] < 100,
            'MATERIAL_COUNT_LIMIT',
        )
        name, kind, raw = materials.decode(b.get('name'), b.get('data_base64'))
        svc.require(total + len(raw) <= 64 * 1024 * 1024, 'MATERIAL_STORAGE_LIMIT')
        id = engine.uid()
        value = {
            'status': 'PARSING',
            'sections': [],
            'message': '正在背景擷取文字，可繼續編課。',
            'source_url': svc.url(b.get('source_url', '')),
            'sha256': hashlib.sha256(raw).hexdigest(),
            '_instance': jobs.INSTANCE,
        }
        db.execute(
            'INSERT INTO training_materials VALUES(?,?,?,?,?,?,?)',
            (id, uid, name, kind, raw, store.j(value), time.time()),
        )
        svc.audit(db, uid, 'MATERIAL_ADD:' + id)
        tasks.append(('material', str(store.DB_FILE), id))
        return {'id': id, 'name': name, 'status': 'PARSING'}
    if op == 'material_retry':
        svc.require(
            db.execute(
                "SELECT count(*) FROM training_materials WHERE json_extract(body,'$.status')='PARSING'"
            ).fetchone()[0]
            < 4,
            'MATERIAL_QUEUE_FULL',
        )
        row = db.execute('SELECT * FROM training_materials WHERE id=? AND owner=?', (p['material_id'], uid)).fetchone()
        svc.require(row, 'NOT_FOUND')
        m = jobs.recover_material(db, row)
        svc.require(m['status'] != 'PARSING', 'MATERIAL_PARSING')
        m.update(status='PARSING', _instance=jobs.INSTANCE)
        db.execute('UPDATE training_materials SET body=?,created_at=? WHERE id=?', (store.j(m), time.time(), row['id']))
        tasks.append(('material', str(store.DB_FILE), row['id']))
        return {'accepted': True}
    if op == 'products':
        return svc.all_products(db, uid)
    if op == 'product_add':
        kind = b.get('kind')
        svc.require(kind in catalog.KINDS)
        sid = 'custom-source-' + engine.uid()
        source = {
            'id': sid,
            'title': svc.text(b.get('source_title'), 1, 160, '來源文件名稱'),
            'url': svc.url(b.get('source_url', '')),
            'locator': svc.text(b.get('source_locator'), 1, 120, '頁碼／條號'),
        }
        mid = b.get('material_id')
        if mid:
            row = db.execute('SELECT body,name FROM training_materials WHERE id=? AND owner=?', (mid, uid)).fetchone()
            svc.require(row, 'NOT_FOUND')
            m = json.loads(row['body'])
            svc.require_ready(m, row['name'])
            source.update(title=row['name'], material_id=mid, text=m['sections'][0]['text'][:1200])
        else:
            svc.require(source['url'], 'PRODUCT_SOURCE_REQUIRED')
        facts = b.get('facts')
        svc.require(
            isinstance(facts, list)
            and 1 <= len(facts) <= 8
            and all(isinstance(x, str) and 1 <= len(x.strip()) <= 200 for x in facts),
            'PRODUCT_FACTS_INVALID',
        )
        svc.require(b.get('reviewed') is True, 'PRODUCT_REVIEW_REQUIRED')
        pr = {
            'id': 'CUSTOM_' + engine.uid(),
            'name': svc.text(b.get('name'), 1, 100, '商品名稱'),
            'kind': kind,
            'provider': svc.text(b.get('provider'), 1, 100, '保險公司／來源單位'),
            'source': source,
            'facts': facts,
            'retrieved_at': engine.now()[:10],
            'simulation': catalog.ASSUMPTIONS,
            'simulation_notice': '所有費用、給付與投資配置採教學假設，並非該商品正式報價。',
        }
        db.execute('INSERT INTO training_products VALUES(?,?,?)', (pr['id'], uid, store.j(pr)))
        svc.audit(db, uid, 'PRODUCT_ADD:' + pr['id'])
        return pr
    if op == 'course_add':
        return svc.save_course(db, uid, b)
    if op == 'course_save':
        return svc.save_course(db, uid, b, p['course_id'])
    if op == 'course_clone':
        row, c = svc.course(db, p['course_id'])
        svc.require(row['owner'] == uid or row['owner'] is None, 'FORBIDDEN')
        value = {**c, 'title': c['title'] + '（新版草稿）', 'reviewed': False}
        return svc.save_course(db, uid, value)
    if op == 'publish':
        c = svc.owned_course(db, uid, p['course_id'])
        svc.require(c['status'] == 'DRAFT', 'PUBLISHED_IMMUTABLE')
        svc.require(c['version'] == b.get('expected_version'), 'STALE_VERSION')
        svc.require(not c['unresolved'], 'UNRESOLVED_ITEMS')
        svc.require(c['reviewed'], 'REVIEW_REQUIRED')
        svc.validate_course(db, uid, c)
        c['status'] = 'PUBLISHED'
        c['version'] += 1
        db.execute("UPDATE training_courses SET status='PUBLISHED',body=? WHERE id=?", (store.j(c), c['id']))
        svc.audit(db, uid, 'COURSE_PUBLISH:' + c['id'])
        return c
    if op == 'classes':
        return [
            svc.class_view(json.loads(r[0]))
            for r in db.execute(
                "SELECT body FROM training_classes WHERE owner=? AND coalesce(json_extract(body,'$.trial'),0)=0 ORDER BY created_at DESC",
                (uid,),
            )
        ]
    if op == 'class_add':
        return svc.create_class(db, uid, b)
    if op == 'class_close':
        row = db.execute('SELECT body FROM training_classes WHERE id=? AND owner=?', (p['class_id'], uid)).fetchone()
        svc.require(row, 'NOT_FOUND')
        c = json.loads(row[0])
        c['status'] = 'CLOSED'
        db.execute('UPDATE training_classes SET body=? WHERE id=?', (store.j(c), c['id']))
        svc.audit(db, uid, 'CLASS_CLOSE:' + c['id'])
        return svc.class_view(c)
    if op == 'report':
        return svc.class_report(db, uid, p['class_id'])
    if op == 'preview':
        row, c = svc.course(db, p['course_id'])
        svc.require(row['owner'] == uid or row['owner'] is None, 'FORBIDDEN')
        counts = []
        for seed in range(200):
            counts.append(sum(e['template']['topic'] == c['rules']['emphasis_topic'] for e in sim.plan(c, seed)))
        return {
            'samples': 200,
            'with_topic': sum(n > 0 for n in counts),
            'mean_occurrences': round(sum(counts) / 200, 2),
            'notice': '這是教案排程抽樣，不是真實事故機率。保證出現的設定只用於本課程。',
        }
    if op == 'trial':
        row, c = svc.course(db, p['course_id'])
        svc.require(row['owner'] == uid or row['owner'] is None, 'FORBIDDEN')
        id = engine.uid()
        class_id = engine.uid()
        value = {
            'id': class_id,
            'code': engine.uid()[:8].upper(),
            'title': '講師試玩：' + c['title'],
            'course_title': c['title'],
            'course_id': c['id'],
            'revision': c['revision'],
            'status': 'CLOSED',
            'course': c,
            'scenario_seed': 12345,
            'trial': True,
            'created_at': engine.now(),
        }
        db.execute(
            'INSERT INTO training_classes VALUES(?,?,?,?,?)',
            (class_id, uid, value['code'], store.j(value), value['created_at']),
        )
        r = sim.create(c, 12345)
        db.execute('INSERT INTO training_runs VALUES(?,?,?,?,?)', (id, class_id, uid, store.j(r), engine.now()))
        return {'id': id, 'state': sim.public(r), 'notice': '講師私人試玩，不計入正式班次成效。'}
    if op == 'ai_jobs':
        return [
            jobs.public_job(jobs.job(db, uid, r[0]))
            for r in db.execute(
                'SELECT id FROM training_ai_jobs WHERE owner=? ORDER BY created_at DESC LIMIT 30', (uid,)
            ).fetchall()
        ]
    if op == 'ai_add':
        c = svc.owned_course(db, uid, b.get('course_id'))
        svc.require(c['status'] == 'DRAFT', 'PUBLISHED_IMMUTABLE')
        j = jobs.create_ai_job(db, uid, c)
        if j['status'] == 'QUEUED':
            tasks.append(('ai', str(store.DB_FILE), uid, j['id']))
        return jobs.public_job(j)
    if op in ('ai_retry', 'ai_cancel', 'ai_apply'):
        j = jobs.job(db, uid, p['job_id'])
        if op == 'ai_cancel':
            if j['status'] not in ('APPLIED', 'COMPLETE', 'CANCELLED'):
                j.update(status='CANCELLED', message='已取消；原教案仍保留。', _finished=time.time())
                jobs.save(db, j)
                if j.get('_chat_id'):
                    tasks.append(('stop', j['_base_url'], j['_chat_id']))
            return jobs.public_job(j)
        if op == 'ai_retry':
            svc.require(jobs.enabled(), 'LLM_DISABLED')
            svc.require(j['status'] not in ('RUNNING', 'QUEUED'), 'AI_JOB_RUNNING')
            svc.require(j['status'] in ('WAITING_PROVIDER', 'FAILED', 'INTERRUPTED'), 'AI_JOB_NOT_RETRYABLE')
            svc.require(
                db.execute(
                    "SELECT count(*) FROM training_ai_jobs WHERE json_extract(body,'$.status') IN ('QUEUED','RUNNING')"
                ).fetchone()[0]
                < 2,
                'AUTHORING_BUSY',
            )
            c = svc.owned_course(db, uid, j['course_id'])
            svc.require(c['version'] == j['course_version'], 'STALE_VERSION')
            for key in ('_started', '_finished', '_chat_id', '_base_url'):
                j.pop(key, None)
            j.update(
                status='QUEUED',
                _instance=jobs.INSTANCE,
                created_at=time.time(),
                result=None,
                error_code=None,
                progress_chars=0,
            )
            jobs.save(db, j)
            tasks.append(('ai', str(store.DB_FILE), uid, j['id']))
            return jobs.public_job(j)
        svc.require(j['status'] != 'APPLIED', 'AI_JOB_ALREADY_APPLIED')
        svc.require(j['status'] not in ('QUEUED', 'RUNNING', 'WAITING_PROVIDER'), 'AI_JOB_NOT_COMPLETE')
        svc.require(j['status'] == 'COMPLETE' and j['result'], 'AI_JOB_NO_RESULT')
        c = svc.owned_course(db, uid, j['course_id'])
        svc.require(c['version'] == j['course_version'], 'STALE_VERSION')
        try:
            result = jobs.validate_result({'contract_version': 'training-author-v1', **j['result']}, c)
        except (ValueError, TypeError, KeyError):
            raise ValueError('AI_OUTPUT_INVALID')
        c.update(
            events=result['events'], unresolved=result['unresolved'], reviewed=False, expected_version=c['version']
        )
        updated = svc.save_course(db, uid, c, c['id'])
        updated['mode'] = 'AI_DRAFT'
        db.execute('UPDATE training_courses SET body=? WHERE id=?', (store.j(updated), updated['id']))
        j.update(
            status='APPLIED',
            message='已套用到草稿，仍需核對來源、處理待確認事項並重新審核。',
            applied_version=updated['version'],
        )
        jobs.save(db, j)
        return updated
    raise ValueError('NOT_FOUND')


def submit(tasks):
    for kind, *args in tasks:
        if kind == 'stop':
            from . import qwen

            qwen.stop(*args)
        else:
            (jobs.submit_material if kind == 'material' else jobs.submit_ai)(*args)


def dispatch(op, request, b):
    try:
        tasks = []
        with store.tx(read_only=request.method == 'GET' and op not in ('materials', 'ai_jobs')) as db:
            u, _ = handlers.get_user(db, request)
            handlers.verify_csrf(request, u)
            key = request.headers.get('idempotency-key', '')
            digest = hashlib.sha256((request.url.path + '\n' + store.j(b)).encode()).hexdigest()
            write = request.method != 'GET'
            if write:
                svc.require(u, 'UNAUTHENTICATED')
                svc.require(8 <= len(key) <= 128, 'IDEMPOTENCY_KEY_REQUIRED')
                old = db.execute(
                    'SELECT request_hash,reply_json FROM idempotency WHERE user_id=? AND key=? AND operation=?',
                    (u['id'], key, 'TRAINING_' + op),
                ).fetchone()
                if old:
                    svc.require(old['request_hash'] == digest, 'IDEMPOTENCY_KEY_REUSED')
                    return JSONResponse(json.loads(old['reply_json']))
            result = handle(op, db, u, b, request.path_params, tasks)
            value = {'data': result, 'meta': {'api_version': 'v1', 'training_version': catalog.VERSION}}
            if write:
                db.execute(
                    'INSERT INTO idempotency VALUES(?,?,?,?,?)',
                    (u['id'], key, 'TRAINING_' + op, digest, store.j(value)),
                )
        return JSONResponse(value, background=BackgroundTask(submit, tasks))
    except ValueError as exc:
        return fail(exc)
    except (TypeError, KeyError, OverflowError, AttributeError):
        return fail('INVALID_INPUT')


def endpoint(op):
    async def run(request: Request):
        try:
            if request.method == 'GET':
                b = {}
            else:
                chunks = []
                size = 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 12 * 1024 * 1024:
                        raise ValueError('REQUEST_TOO_LARGE')
                    chunks.append(chunk)
                try:
                    b = json.loads(b''.join(chunks))
                except (UnicodeError, json.JSONDecodeError):
                    raise ValueError('INVALID_INPUT')
                svc.require(isinstance(b, dict))
            return await run_in_threadpool(dispatch, op, request, b)
        except ValueError as exc:
            return fail(exc)

    run.__name__ = 'training_' + op
    return run


for method, path, op in [
    ('GET', '/capabilities', 'capabilities'),
    ('GET', '/catalog', 'catalog'),
    ('GET', '/session', 'session'),
    ('GET', '/courses', 'courses'),
    ('GET', '/runs', 'runs'),
    ('POST', '/join', 'join'),
    ('GET', '/runs/{run_id}', 'run'),
    ('POST', '/runs/{run_id}/actions', 'action'),
    ('POST', '/runs/{run_id}/quotes', 'quote'),
    ('GET', '/admin/materials', 'materials'),
    ('POST', '/admin/materials', 'material_add'),
    ('POST', '/admin/materials/{material_id}/retry', 'material_retry'),
    ('GET', '/admin/products', 'products'),
    ('POST', '/admin/products', 'product_add'),
    ('POST', '/admin/courses', 'course_add'),
    ('PUT', '/admin/courses/{course_id}', 'course_save'),
    ('POST', '/admin/courses/{course_id}/clone', 'course_clone'),
    ('POST', '/admin/courses/{course_id}/publish', 'publish'),
    ('POST', '/admin/courses/{course_id}/preview', 'preview'),
    ('POST', '/admin/courses/{course_id}/trial', 'trial'),
    ('GET', '/admin/classes', 'classes'),
    ('POST', '/admin/classes', 'class_add'),
    ('POST', '/admin/classes/{class_id}/close', 'class_close'),
    ('GET', '/admin/classes/{class_id}/report', 'report'),
    ('GET', '/admin/ai-jobs', 'ai_jobs'),
    ('POST', '/admin/ai-jobs', 'ai_add'),
    ('POST', '/admin/ai-jobs/{job_id}/retry', 'ai_retry'),
    ('POST', '/admin/ai-jobs/{job_id}/cancel', 'ai_cancel'),
    ('POST', '/admin/ai-jobs/{job_id}/apply', 'ai_apply'),
]:
    router.add_api_route(path, endpoint(op), methods=[method])
